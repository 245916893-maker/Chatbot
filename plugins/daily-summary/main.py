""""每日群聊总结插件 - 主模块"""
import os
import sqlite3
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

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
}

DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "messages.db"
CONFIG_PATH = Path(__file__).parent / "config.json"


def _build_summary_prompt(msgs: list[dict]) -> str:
    lines = []
    for m in msgs:
        t = datetime.fromisoformat(m["timestamp"]).strftime("%H:%M")
        lines.append(f"[{t}] {m['user_name']}: {m['content']}")
    chat_log = "\n".join(lines)

    return f"""请总结以下QQ群聊记录，用中文生成一份简洁的昨日摘要。要求：

📌 **主要话题** — 列出昨日讨论最多的2-5个话题，每个一句话概括
😂 **有趣发言** — 摘录1-3条有意思的发言或梗
❓ **待解决问题** — 提取群友提出的尚未解决的技术/生活问题（如果有）
📊 **活跃度** — 一句话描述昨日活跃情况（参与人数、消息量、活跃时段）

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


@register("daily-summary", "WorkBuddy", "QQ群每日聊天总结：自动收集消息并生成每日摘要", "1.0.0",
          "https://github.com/245916893-maker/Chatbot")
class DailySummary(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        _ensure_db()
        self.config = _load_config()
        self._last_run_date: str | None = None
        self._task: asyncio.Task | None = None

    async def _start_scheduler(self):
        """启动后台调度任务"""
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("每日总结调度器已启动，每日执行时间: %s", self.config["summary_time"])

    async def _scheduler_loop(self):
        while True:
            now = datetime.now()
            target = datetime.strptime(self.config["summary_time"], "%H:%M").time()
            target_dt = datetime.combine(now.date(), target)

            # 如果今天的目标时间还没到，等；否则等明天
            if now >= target_dt:
                target_dt += timedelta(days=1)

            wait_seconds = (target_dt - now).total_seconds()
            # 最多等60s再检查一次，避免时间漂移
            await asyncio.sleep(min(wait_seconds, 60))

            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            if self._last_run_date != today_str and now.hour == target.hour == now.hour:
                self._last_run_date = today_str
                await self._daily_run()

    async def _daily_run(self):
        """执行每日总结"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        logger.info("开始生成 %s 的每日总结", yesterday)

        groups = self.config["target_groups"]
        if not groups:
            groups = self._get_tracked_groups()

        for gid in groups:
            try:
                summary = await self._generate_summary(gid, yesterday)
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

        now = datetime.now()
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
        """手动生成昨日聊天总结"""
        gid = event.message_obj.group_id
        if not gid:
            yield event.plain_result("⚠️ 请在群聊中使用此命令")
            return

        yield event.plain_result("🤔 正在生成昨日聊天总结，请稍候...")

        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        summary = await self._generate_summary(gid, yesterday)
        if summary:
            yield event.plain_result(summary)
        else:
            yield event.plain_result("📭 昨日该群无聊天记录")

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

    async def _generate_summary(self, group_id: str, date_str: str) -> str | None:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.execute(
            "SELECT user_name, content, timestamp FROM messages WHERE group_id=? AND date=? ORDER BY timestamp ASC",
            (group_id, date_str),
        )
        msgs = [{"user_name": r[0], "content": r[1], "timestamp": r[2]} for r in cursor.fetchall()]
        conn.close()

        if not msgs:
            return None

        if len(msgs) > 500:
            msgs = msgs[-500:]

        prompt = _build_summary_prompt(msgs)
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
