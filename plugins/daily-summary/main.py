"""每日群聊总结插件 - 主模块"""
import os
import sqlite3
import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain

# 默认配置
DEFAULT_CONFIG = {
    "summary_time": "08:00",
    "api_base": "https://api.deepseek.com/v1",
    "api_key": "",
    "model": "deepseek-chat",
    "max_tokens": 2000,
    "temperature": 0.7,
    "target_groups": [],  # 空列表 = 所有群，否则只对指定群
    "timezone": "Asia/Shanghai",
}

DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "messages.db"
CONFIG_PATH = Path(__file__).parent / "config.json"
ACTIVE_TIMEZONE = DEFAULT_CONFIG["timezone"]

DATE_ARG_PATTERN = r"(?:今天|昨天|昨日|前天|大前天|\d+天前|\d{4}-\d{2}-\d{2})"
TIME_ARG_PATTERN = r"(?:[01]?\d|2[0-3]):[0-5]\d"
RANGE_SEPARATOR_PATTERN = r"(?:到|至|~|～|-|–|—)"


def _get_local_tz():
    try:
        return ZoneInfo(ACTIVE_TIMEZONE)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _now_local() -> datetime:
    return datetime.now(_get_local_tz())


def _timestamp_to_local(timestamp: str) -> datetime:
    dt = datetime.fromisoformat(timestamp)
    if dt.tzinfo is None:
        # Older records were written by a UTC container as naive timestamps.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_get_local_tz())


def _build_summary_prompt(msgs: list[dict], period_label: str = "昨日") -> str:
    lines = []
    for m in msgs:
        t = _timestamp_to_local(m["timestamp"]).strftime("%m-%d %H:%M")
        lines.append(f"[{t}] {m['user_name']}: {m['content']}")
    chat_log = "\n".join(lines)

    return f"""请总结以下QQ 群聊记录，用中文生成一份简洁的{period_label}摘要。要求：

📌 **主要话题** — 列出{period_label}讨论最多的2-5个话题，每个一句话概括
😂 **有趣发言** — 摘录1-3条有意思的发言或梗
❓ **待解决问题** — 提取群友提出的尚未解决的技术/生活问题（如果有）
📊 **活跃度** — 一句话描述{period_label}活跃情况（参与人数、消息量、活跃时段）

格式用 Markdown，适当用 emoji 点缀，控制在 500 字以内。

群聊记录：
{chat_log}"""


def _ensure_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            date TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_date_group ON messages(date, group_id)")
    conn.commit()
    conn.close()


def _load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def _save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _parse_date_arg(arg: str) -> tuple[str, str]:
    yesterday = "昨日"
    before_yesterday = "前天"
    two_days_before = "大前天"
    day_suffix = "天前"
    today = "今天"

    aliases = {
        "今天": (0, today),
        "昨天": (1, yesterday),
        yesterday: (1, yesterday),
        before_yesterday: (2, before_yesterday),
        two_days_before: (3, two_days_before),
    }
    if arg in aliases:
        days_ago, label = aliases[arg]
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", arg):
        target = datetime.strptime(arg, "%Y-%m-%d").date()
        return target.strftime("%Y-%m-%d"), arg
    else:
        number_text = arg[:-len(day_suffix)] if arg.endswith(day_suffix) else arg
        if not number_text.isdigit():
            raise ValueError("unsupported date argument")
        days_ago = int(number_text)
        label = today if days_ago == 0 else f"{days_ago}{day_suffix}"

    target = _now_local().date() - timedelta(days=days_ago)
    return target.strftime("%Y-%m-%d"), label


def _parse_hhmm(value: str) -> int:
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", value)
    if not match:
        raise ValueError("unsupported time argument")
    return int(match.group(1)) * 60 + int(match.group(2))


def _format_minutes(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _combine_local(date_str: str, minutes: int, *, end_of_minute: bool = False) -> datetime:
    date_value = datetime.strptime(date_str, "%Y-%m-%d").date()
    dt = datetime.combine(
        date_value,
        datetime.min.time(),
        tzinfo=_get_local_tz(),
    ) + timedelta(minutes=minutes)
    if end_of_minute:
        dt += timedelta(seconds=59, microseconds=999999)
    return dt


def _whole_day_range(date_str: str) -> tuple[datetime, datetime]:
    return _combine_local(date_str, 0), _combine_local(date_str, 23 * 60 + 59, end_of_minute=True)


def _range_label(start_dt: datetime, end_dt: datetime) -> str:
    return f"{start_dt.strftime('%Y-%m-%d %H:%M')} 至 {end_dt.strftime('%Y-%m-%d %H:%M')}"


def _time_range_pattern(date_count: int) -> re.Pattern:
    sep = rf"(?:\s*{RANGE_SEPARATOR_PATTERN}\s*|\s+)"
    if date_count == 2:
        pattern = (
            rf"^\s*(?P<start_date>{DATE_ARG_PATTERN})\s+"
            rf"(?P<start_time>{TIME_ARG_PATTERN}){sep}"
            rf"(?P<end_date>{DATE_ARG_PATTERN})\s+"
            rf"(?P<end_time>{TIME_ARG_PATTERN})\s*$"
        )
    else:
        pattern = (
            rf"^\s*(?P<date>{DATE_ARG_PATTERN})\s+"
            rf"(?P<start_time>{TIME_ARG_PATTERN}){sep}"
            rf"(?P<end_time>{TIME_ARG_PATTERN})\s*$"
        )
    return re.compile(pattern)


def _time_only_range_pattern() -> re.Pattern:
    sep = rf"(?:\s*{RANGE_SEPARATOR_PATTERN}\s*|\s+)"
    return re.compile(
        rf"^\s*(?P<start_time>{TIME_ARG_PATTERN}){sep}(?P<end_time>{TIME_ARG_PATTERN})\s*$"
    )


def _parse_summary_query(raw_message: str) -> tuple[str, datetime, datetime]:
    """Parse /summary query. Defaults to yesterday, all day."""
    query = raw_message.strip().split(maxsplit=1)
    query = query[1].strip() if len(query) > 1 else ""

    if not query:
        date_str, label = _parse_date_arg("昨日")
        start_dt, end_dt = _whole_day_range(date_str)
        return label, start_dt, end_dt

    cross_day_match = _time_range_pattern(2).fullmatch(query)
    if cross_day_match:
        start_date, _ = _parse_date_arg(cross_day_match.group("start_date"))
        end_date, _ = _parse_date_arg(cross_day_match.group("end_date"))
        start_dt = _combine_local(start_date, _parse_hhmm(cross_day_match.group("start_time")))
        end_dt = _combine_local(
            end_date,
            _parse_hhmm(cross_day_match.group("end_time")),
            end_of_minute=True,
        )
        if end_dt < start_dt:
            raise ValueError("time range end before start")
        return _range_label(start_dt, end_dt), start_dt, end_dt

    same_day_match = _time_range_pattern(1).fullmatch(query)
    if same_day_match:
        date_str, label = _parse_date_arg(same_day_match.group("date"))
        start_min = _parse_hhmm(same_day_match.group("start_time"))
        end_min = _parse_hhmm(same_day_match.group("end_time"))
        if end_min < start_min:
            raise ValueError("same-day time range cannot cross midnight")
        start_dt = _combine_local(date_str, start_min)
        end_dt = _combine_local(date_str, end_min, end_of_minute=True)
        return f"{label} {_format_minutes(start_min)}-{_format_minutes(end_min)}", start_dt, end_dt

    time_only_match = _time_only_range_pattern().fullmatch(query)
    if time_only_match:
        date_str, label = _parse_date_arg("今天")
        start_min = _parse_hhmm(time_only_match.group("start_time"))
        end_min = _parse_hhmm(time_only_match.group("end_time"))
        if end_min < start_min:
            raise ValueError("time range cannot cross midnight without an end date")
        start_dt = _combine_local(date_str, start_min)
        end_dt = _combine_local(date_str, end_min, end_of_minute=True)
        return f"{label} {_format_minutes(start_min)}-{_format_minutes(end_min)}", start_dt, end_dt

    if re.fullmatch(DATE_ARG_PATTERN, query):
        date_str, label = _parse_date_arg(query)
        start_dt, end_dt = _whole_day_range(date_str)
        return label, start_dt, end_dt

    raise ValueError("unsupported summary query")


@register("daily-summary", "WorkBuddy", "QQ群每日聊天总结：自动收集消息并生成每日摘要", "1.0.0",
          "https://github.com/245916893-maker/Chatbot")
class DailySummary(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        _ensure_db()
        self.config = _load_config()
        global ACTIVE_TIMEZONE
        ACTIVE_TIMEZONE = self.config.get("timezone", DEFAULT_CONFIG["timezone"])
        self._last_run_date: str | None = None
        self._task: asyncio.Task | None = None

    async def _start_scheduler(self):
        """启动后台调度任务"""
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("每日总结调度器已启动，每日执行时间: %s", self.config["summary_time"])

    async def _scheduler_loop(self):
        while True:
            now = _now_local()
            target = datetime.strptime(self.config["summary_time"], "%H:%M").time()
            target_dt = datetime.combine(now.date(), target, tzinfo=_get_local_tz())

            # 如果今天的目标时间还没到，等；否则等明天
            if now >= target_dt:
                target_dt += timedelta(days=1)

            wait_seconds = (target_dt - now).total_seconds()
            # 最多等60s再检查一次，避免时间漂移
            await asyncio.sleep(min(wait_seconds, 60))

            now = _now_local()
            today_str = now.strftime("%Y-%m-%d")

            if self._last_run_date != today_str and now.hour == target.hour and now.minute == target.minute:
                self._last_run_date = today_str
                await self._daily_run()

    async def _daily_run(self):
        """执行每日总结"""
        yesterday = (_now_local() - timedelta(days=1)).strftime("%Y-%m-%d")
        logger.info("开始生成 %s 的每日总结", yesterday)
        start_dt, end_dt = _whole_day_range(yesterday)

        groups = self.config["target_groups"]
        if not groups:
            groups = self._get_tracked_groups()

        for gid in groups:
            try:
                summary = await self._generate_summary(gid, start_dt, end_dt, "昨日")
                if summary:
                    await self._send_to_group(gid, summary)
                    logger.info("已发送群 %s 的每日总结", gid)
            except Exception as e:
                logger.error("群 %s 总结失败: %s", gid, e)

    # ---------- 消息监听 ----------

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        gid = event.message_obj.group_id
        if not gid:
            return

        uid = event.message_obj.sender.user_id
        uname = event.message_obj.sender.nickname or str(uid)
        content = event.message_str or ""
        if not content.strip():
            return

        now = _now_local()
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO messages (group_id, user_id, user_name, content, timestamp, date) VALUES (?,?,?,?,?,?)",
            (gid, uid, uname, content, now.isoformat(), now.strftime("%Y-%m-%d")),
        )
        conn.commit()
        conn.close()

    # ---------- 手动触发 ----------

    @filter.command("summary")
    async def cmd_summary(self, event: AstrMessageEvent):
        """Generate chat summary. Usage: /summary [date] [HH:MM-HH:MM] or /summary [date HH:MM date HH:MM]."""
        gid = event.message_obj.group_id
        if not gid:
            yield event.plain_result("⚠️ 请在群聊中使用此命令")
            return

        try:
            period_label, start_dt, end_dt = _parse_summary_query(event.message_str)
        except ValueError:
            yield event.plain_result(
                "⚠️ 用法：/summary [昨日|前天|大前天|YYYY-MM-DD|N天前] [HH:MM-HH:MM]\n"
                "或：/summary 起始日期 HH:MM 到 结束日期 HH:MM"
            )
            return

        yield event.plain_result(f"🤔 正在生成{period_label}聊天总结，请稍候...")

        summary = await self._generate_summary(gid, start_dt, end_dt, period_label)
        if summary:
            yield event.plain_result(summary)
        else:
            yield event.plain_result(f"📭 {period_label}该群无聊天记录")

    @filter.command("summary_help")
    async def cmd_summary_help(self, event: AstrMessageEvent):
        """Show daily-summary usage."""
        yield event.plain_result(
            "用法：/summary [昨日|前天|大前天|YYYY-MM-DD|N天前] [HH:MM-HH:MM]\n"
            "也可跨天：/summary 起始日期 HH:MM 到 结束日期 HH:MM\n"
            "例如：/summary 大前天 14:00-16:30\n"
            "/summary 2026-05-24 14:00-15:30\n"
            "/summary 今天 14:00 到 15:00\n"
            "/summary 14:00-15:00\n"
            "/summary 前天 22:30 到 今天 01:15\n"
            "/summary 2026-05-23 22:30 到 2026-05-24 01:15"
        )

    @filter.command("zongjie")
    async def cmd_zongjie(self, event: AstrMessageEvent):
        """手动生成昨日聊天总结（中文别名）"""
        async for r in self.cmd_summary(event):
            yield r

    @filter.command("summary_config")
    async def cmd_config(self, event: AstrMessageEvent):
        """查看/修改插件配置：/summary_config [key] [value]"""
        msg = event.message_str.strip()
        parts = msg.split()
        if len(parts) < 2:
            yield event.plain_result(f"📋 当前配置:\n```json\n{json.dumps(self.config, ensure_ascii=False, indent=2)}\n```")
            return

        key = parts[1]
        if key not in self.config:
            yield event.plain_result(f"❌ 未知配置项: {key}")
            return

        if len(parts) >= 3:
            val = parts[2]
            if isinstance(self.config[key], int):
                val = int(val)
            elif isinstance(self.config[key], list):
                val = json.loads(val)
            self.config[key] = val
            _save_config(self.config)
            yield event.plain_result(f"✅ {key} = {val}")
        else:
            yield event.plain_result(f"📋 {key} = {self.config[key]}")

    # ---------- 核心逻辑 ----------

    async def _generate_summary(
        self,
        group_id: str,
        start_dt: datetime,
        end_dt: datetime,
        period_label: str | None = None,
    ) -> str | None:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.execute(
            "SELECT user_name, content, timestamp FROM messages WHERE group_id=? ORDER BY timestamp ASC",
            (group_id,),
        )
        msgs = []
        for user_name, content, timestamp in cursor.fetchall():
            local_dt = _timestamp_to_local(timestamp)
            if local_dt < start_dt or local_dt > end_dt:
                continue
            msgs.append({"user_name": user_name, "content": content, "timestamp": timestamp})
        conn.close()

        if not msgs:
            return None

        if len(msgs) > 500:
            msgs = msgs[-500:]

        prompt = _build_summary_prompt(msgs, period_label or _range_label(start_dt, end_dt))
        summary = await self._call_llm(prompt)
        return summary

    async def _call_llm(self, prompt: str) -> str:
        cfg = self.config
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        }
        payload = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": "你是一个专业的群聊总结助手，擅长从聊天记录中提炼关键信息。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": cfg["max_tokens"],
            "temperature": cfg["temperature"],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{cfg['api_base'].rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    raise RuntimeError(f"LLM API 调用失败 ({resp.status}): {err}")
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def _send_to_group(self, group_id: str, content: str):
        """向指定群发送消息"""
        insts = self.context.platform_manager.get_insts()
        if not insts:
            logger.error("没有可用的平台实例")
            return

        # 使用第一个 OneBot/QQ 平台实例
        for inst in insts:
            try:
                adapter = inst.adapter
                await inst.send_message(
                    {
                        "type": "group",
                        "group_id": group_id,
                        "message": [{"type": "text", "data": {"text": content}}],
                    }
                )
                return
            except Exception as e:
                logger.debug("平台 %s 发送失败: %s", type(adapter).__name__, e)
        logger.error("无法发送消息到群 %s", group_id)

    def _get_tracked_groups(self) -> list[str]:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.execute("SELECT DISTINCT group_id FROM messages")
        groups = [r[0] for r in cursor.fetchall()]
        conn.close()
        return groups

    async def terminate(self):
        if self._task:
            self._task.cancel()
        logger.info("每日总结插件已停止")
