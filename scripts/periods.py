"""periods — 报告期 / 交易日的人话标签(审计红旗证据、分诊指标 delta、较上版变化区块共用)。

A 股定期报告的利润表与现金流量表是**年内累计**口径:三季报的「营收」是前三季度合计,
半年报是上半年合计。两期并排时期长不同(6 个月 vs 9 个月)就不能直接比 —— 读者得看得见期别。

立讯 002475 实测:公允价值变动规则取了 FY2025 年报行(−6.19 亿)却写「最新期」,
而 2026 前三季度该项是 +5.50 亿;较上版变化区块把 2026H1 与 2026 前三季的累计营收并排, 没标期别。
"""
from __future__ import annotations

import re

_YMD = re.compile(r"^(\d{4})-?(\d{2})-?(\d{2})$")

# 报告期末(月日)→ (人话期别, 累计月数)
_REPORT_ENDS = {
    "0331": ("一季度", 3),
    "0630": ("上半年", 6),
    "0930": ("前三季度", 9),
    "1231": ("年报", 12),
}


def _parse(end_date) -> tuple[str, str, str] | None:
    m = _YMD.match(str(end_date or "").strip())
    return m.groups() if m else None


def is_report_period(end_date) -> bool:
    """end_date 是不是标准报告期末(0331/0630/0930/1231)。"""
    parts = _parse(end_date)
    return bool(parts) and (parts[1] + parts[2]) in _REPORT_ENDS


def period_months(end_date) -> int | None:
    """报告期的累计月数(一季度 3 / 上半年 6 / 前三季度 9 / 年报 12); 非报告期末返回 None。"""
    parts = _parse(end_date)
    if not parts:
        return None
    hit = _REPORT_ENDS.get(parts[1] + parts[2])
    return hit[1] if hit else None


def iso(end_date) -> str:
    """'20260930' → '2026-09-30'; 认不出原样返回。"""
    parts = _parse(end_date)
    return "-".join(parts) if parts else str(end_date or "")


def period_label(end_date, basis: str = "report") -> str:
    """人话期别标签。

    basis="report"(默认): 报告期 → 「2025 年报」「2026 上半年累计」「2026 前三季度累计」「2026 一季度」;
    basis="trade_date": 交易日 → 「2026-09-17 收盘」;
    认不出的日期原样返回(不编造期别)。
    """
    parts = _parse(end_date)
    if not parts:
        return str(end_date or "")
    if basis == "trade_date":
        return f"{iso(end_date)} 收盘"
    hit = _REPORT_ENDS.get(parts[1] + parts[2])
    if not hit:
        return iso(end_date)
    name, months = hit
    if months == 12:
        return f"{parts[0]} 年报"
    if months == 3:
        return f"{parts[0]} 一季度"
    return f"{parts[0]} {name}累计"


def period_note(before_period, after_period, basis: str = "report") -> str | None:
    """两期并排时的口径提示: 期长不同 → 返回一句人话; 同长或认不出 → None。"""
    if basis != "report":
        return None
    mb, ma = period_months(before_period), period_months(after_period)
    if mb is None or ma is None or mb == ma:
        return None
    return f"两期长度不同({mb} 个月 vs {ma} 个月),是累计数,不能直接当增速读"
