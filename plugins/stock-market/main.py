"""免费 A 股行情插件。"""
from __future__ import annotations

import asyncio
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

PERSISTENT_LIBS = Path("/AstrBot/data/python_libs")
if PERSISTENT_LIBS.exists() and str(PERSISTENT_LIBS) not in sys.path:
    sys.path.insert(0, str(PERSISTENT_LIBS))

CN_TZ = ZoneInfo("Asia/Shanghai")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}
INDEX_SECIDS = {
    "上证指数": "1.000001",
    "深证成指": "0.399001",
    "创业板指": "0.399006",
}
INDEX_SYMBOLS = ["sh000001", "sz399001", "sz399006"]
QUOTE_FIELDS = "f12,f13,f14,f2,f3,f4,f5,f6,f15,f16,f17,f18,f20,f21"
ALL_A_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"


@dataclass
class Quote:
    code: str
    name: str
    price: float | None
    pct: float | None
    change: float | None
    open: float | None
    high: float | None
    low: float | None
    prev_close: float | None
    volume: float | None
    amount: float | None
    market: int | None = None


def _now_label() -> str:
    return datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M")


def _num(value: Any) -> float | None:
    if value in (None, "-", ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _fmt(value: float | None, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "--"
    return f"{value:.{digits}f}{suffix}"


def _fmt_signed(value: float | None, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "--"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{digits}f}{suffix}"


def _fmt_amount(value: float | None) -> str:
    if value is None:
        return "--"
    if abs(value) >= 1_0000_0000_0000:
        return f"{value / 1_0000_0000_0000:.2f}万亿"
    if abs(value) >= 1_0000_0000:
        return f"{value / 1_0000_0000:.2f}亿"
    if abs(value) >= 1_0000:
        return f"{value / 1_0000:.2f}万"
    return f"{value:.0f}"


def _quote_from_em(item: dict[str, Any]) -> Quote:
    return Quote(
        code=str(item.get("f12") or ""),
        name=str(item.get("f14") or ""),
        price=_num(item.get("f2")),
        pct=_num(item.get("f3")),
        change=_num(item.get("f4")),
        volume=_num(item.get("f5")),
        amount=_num(item.get("f6")),
        high=_num(item.get("f15")),
        low=_num(item.get("f16")),
        open=_num(item.get("f17")),
        prev_close=_num(item.get("f18")),
        market=int(item["f13"]) if str(item.get("f13", "")).isdigit() else None,
    )


def _get_json(url: str, timeout: float = 15) -> dict[str, Any]:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if data.get("rc") not in (0, None):
        raise RuntimeError(f"EastMoney rc={data.get('rc')}")
    return data


def _eastmoney_quotes(secids: list[str]) -> list[Quote]:
    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get"
        f"?fltt=2&invt=2&fields={QUOTE_FIELDS}&secids={','.join(secids)}"
    )
    data = _get_json(url)
    rows = (data.get("data") or {}).get("diff") or []
    return [_quote_from_em(row) for row in rows]


def _eastmoney_all_a() -> list[Quote]:
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=6000&po=1&np=1&fltt=2&invt=2&fid=f3"
        f"&fs={ALL_A_FS}&fields={QUOTE_FIELDS}"
    )
    data = _get_json(url, timeout=25)
    rows = (data.get("data") or {}).get("diff") or []
    return [_quote_from_em(row) for row in rows]


def _quote_from_tencent(payload: str) -> Quote:
    parts = payload.split("~")
    while len(parts) < 38:
        parts.append("")
    amount = _num(parts[37])
    if amount is not None:
        # Tencent amount is reported in ten-thousand yuan.
        amount *= 10_000
    return Quote(
        code=parts[2],
        name=parts[1],
        price=_num(parts[3]),
        prev_close=_num(parts[4]),
        open=_num(parts[5]),
        volume=_num(parts[36]),
        amount=amount,
        change=_num(parts[31]),
        pct=_num(parts[32]),
        high=_num(parts[33]),
        low=_num(parts[34]),
    )


def _tencent_quotes(symbols: list[str]) -> list[Quote]:
    url = f"https://qt.gtimg.cn/q={','.join(symbols)}"
    resp = requests.get(
        url,
        headers={"User-Agent": HEADERS["User-Agent"], "Referer": "https://gu.qq.com/"},
        timeout=15,
    )
    resp.raise_for_status()
    text = resp.content.decode("gbk", errors="replace")
    quotes: list[Quote] = []
    for match in re.finditer(r'v_[A-Za-z0-9_]+="(.*?)";', text):
        payload = match.group(1)
        if payload:
            quotes.append(_quote_from_tencent(payload))
    return quotes


def _tencent_symbol_for_code(code: str) -> str:
    if code.startswith(("5", "6", "9")) or code.startswith(("11", "13")):
        return f"sh{code}"
    return f"sz{code}"


def _tencent_search_code(query: str) -> str | None:
    encoded = urllib.parse.quote(query)
    url = f"https://smartbox.gtimg.cn/s3/?q={encoded}&t=gp"
    resp = requests.get(
        url,
        headers={"User-Agent": HEADERS["User-Agent"], "Referer": "https://gu.qq.com/"},
        timeout=10,
    )
    resp.raise_for_status()
    text = resp.content.decode("utf-8", errors="replace")
    match = re.search(r'v_hint="(.*?)"', text)
    if not match:
        return None
    for item in match.group(1).split("^"):
        parts = item.split("~")
        if len(parts) >= 5 and parts[0] in {"sh", "sz"} and parts[4].startswith("GP"):
            return parts[1]
    return None


def _secid_for_code(code: str) -> str:
    if code.startswith(("5", "6", "9")) or code.startswith(("11", "13")):
        return f"1.{code}"
    return f"0.{code}"


def _try_akshare_index_quotes() -> list[Quote]:
    import akshare as ak

    df = ak.stock_zh_index_spot_em()
    code_col = "代码"
    name_col = "名称"
    result: list[Quote] = []
    for code in ("000001", "399001", "399006"):
        matched = df[df[code_col].astype(str) == code]
        if matched.empty:
            continue
        row = matched.iloc[0]
        result.append(
            Quote(
                code=str(row.get(code_col, code)),
                name=str(row.get(name_col, "")),
                price=_num(row.get("最新价")),
                pct=_num(row.get("涨跌幅")),
                change=_num(row.get("涨跌额")),
                volume=_num(row.get("成交量")),
                amount=_num(row.get("成交额")),
                high=_num(row.get("最高")),
                low=_num(row.get("最低")),
                open=_num(row.get("今开")),
                prev_close=_num(row.get("昨收")),
            )
        )
    if len(result) < 3:
        raise RuntimeError("AkShare index result incomplete")
    return result


class StockData:
    def __init__(self) -> None:
        self._all_a_cache: tuple[float, list[Quote]] | None = None

    def market_overview(self) -> str:
        source = "腾讯财经公开行情"
        indexes = _tencent_quotes(INDEX_SYMBOLS)

        all_quotes = []
        try:
            all_quotes = self._get_all_a()
        except Exception as exc:
            logger.warning("[stock-market] market breadth unavailable: %s", exc)
        tradable = [q for q in all_quotes if q.pct is not None]
        up = sum(1 for q in tradable if q.pct and q.pct > 0)
        down = sum(1 for q in tradable if q.pct and q.pct < 0)
        flat = max(0, len(tradable) - up - down)
        amount = sum((q.amount or 0) for q in tradable) or None
        top_up = sorted(tradable, key=lambda q: q.pct or -999, reverse=True)[:5]
        top_down = sorted(tradable, key=lambda q: q.pct or 999)[:5]

        lines = [f"📈 A股实时概览（{_now_label()}，数据源：{source}）"]
        for q in indexes:
            lines.append(
                f"{q.name} { _fmt(q.price) }，{_fmt_signed(q.pct, suffix='%')} "
                f"({_fmt_signed(q.change)})"
            )
        if tradable:
            lines.append(
                f"全市场：上涨 {up} / 下跌 {down} / 平盘 {flat}，成交额约 {_fmt_amount(amount)}"
            )
        else:
            lines.append("全市场涨跌家数暂时取不到，但指数行情可用。")
        if top_up:
            lines.append("领涨：" + "，".join(f"{q.name} {_fmt_signed(q.pct, suffix='%')}" for q in top_up))
        if top_down:
            lines.append("领跌：" + "，".join(f"{q.name} {_fmt_signed(q.pct, suffix='%')}" for q in top_down))
        lines.append("免费公开行情可能有延迟，仅供群聊参考，不构成投资建议。")
        return "\n".join(lines)

    def stock_quote(self, query: str) -> str:
        query = query.strip()
        if not query:
            return "用法：/stock 600519 或 /stock 贵州茅台"
        code = self._resolve_code(query)
        if not code:
            return f"没找到「{query}」对应的 A 股股票。可以试试直接输入 6 位代码，例如 /stock 600519。"
        quote = _tencent_quotes([_tencent_symbol_for_code(code)])
        if not quote:
            quote = _eastmoney_quotes([_secid_for_code(code)])
        if not quote:
            return f"没有取到 {query} 的行情。"
        q = quote[0]
        return "\n".join(
            [
                f"📊 {q.name}（{q.code}）实时行情（{_now_label()}，数据源：腾讯财经公开行情）",
                f"最新价：{_fmt(q.price)}，涨跌幅：{_fmt_signed(q.pct, suffix='%')}，涨跌额：{_fmt_signed(q.change)}",
                f"今开：{_fmt(q.open)}，最高：{_fmt(q.high)}，最低：{_fmt(q.low)}，昨收：{_fmt(q.prev_close)}",
                f"成交额：{_fmt_amount(q.amount)}",
                "免费公开行情可能有延迟，仅供群聊参考，不构成投资建议。",
            ]
        )

    def _get_all_a(self) -> list[Quote]:
        now = time.time()
        if self._all_a_cache and now - self._all_a_cache[0] < 300:
            return self._all_a_cache[1]
        quotes = _eastmoney_all_a()
        if len(quotes) < 1000:
            raise RuntimeError(f"market breadth result incomplete: {len(quotes)} rows")
        self._all_a_cache = (now, quotes)
        return quotes

    def _resolve_code(self, query: str) -> str | None:
        compact = query.strip().upper()
        match = re.search(r"\b(\d{6})\b", compact)
        if match:
            return match.group(1)

        code = _tencent_search_code(query)
        if code:
            return code

        try:
            quotes = self._get_all_a()
        except Exception:
            return None
        exact = [q for q in quotes if q.name == query or q.code == query]
        if exact:
            return exact[0].code
        contains = [q for q in quotes if query in q.name]
        if contains:
            return contains[0].code
        return None


@register("stock-market", "WorkBuddy", "免费 A 股行情查询插件", "1.0.0",
          "https://github.com/245916893-maker/Chatbot")
class StockMarketPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data = StockData()

    @filter.command("market")
    @filter.command("gushi")
    @filter.command("股市")
    async def cmd_market(self, event: AstrMessageEvent):
        """查询今日 A 股概览。"""
        yield event.plain_result("正在获取免费实时行情，请稍候...")
        try:
            report = await asyncio.to_thread(self.data.market_overview)
        except Exception as exc:
            logger.error("[stock-market] market overview failed: %s", exc)
            report = f"行情获取失败：{exc}"
        yield event.plain_result(report)

    @filter.command("stock")
    @filter.command("股票")
    async def cmd_stock(self, event: AstrMessageEvent):
        """查询个股行情。"""
        parts = event.message_str.strip().split(maxsplit=1)
        query = parts[1] if len(parts) > 1 else ""
        try:
            report = await asyncio.to_thread(self.data.stock_quote, query)
        except Exception as exc:
            logger.error("[stock-market] stock quote failed: %s", exc)
            report = f"个股行情获取失败：{exc}"
        yield event.plain_result(report)

    @filter.command("stock_help")
    @filter.command("行情帮助")
    async def cmd_stock_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "免费行情命令：\n"
            "/market 或 /股市：查看今日 A 股概览\n"
            "/stock 600519：查看个股行情\n"
            "/stock 贵州茅台：按股票名称查询\n"
            "也可以 @机器人 说「今天股市怎么样」。"
        )

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_market_question(self, event: AstrMessageEvent):
        """被 @ 时，识别自然语言股市查询。"""
        if not getattr(event, "is_at_or_wake_command", False):
            return
        text = event.message_str.strip()
        if text.startswith("/"):
            return
        if not re.search(r"(今天|今日|实时|现在)?\s*(A股|股市|大盘|行情)", text, re.I):
            return

        try:
            report = await asyncio.to_thread(self.data.market_overview)
        except Exception as exc:
            logger.error("[stock-market] natural market query failed: %s", exc)
            report = f"行情获取失败：{exc}"
        result = event.plain_result(report)
        result.stop_event()
        yield result
