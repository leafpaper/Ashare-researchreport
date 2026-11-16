"""Financial anomaly detection using classic academic & investor frameworks.

This module consumes a bundle produced by TushareCollector.collect_all() and
runs 10 classic financial health checks, returning a structured dict of
"red flags" ranked by severity.

Frameworks implemented:
    1. Piotroski F-Score (9 签号)            — 财务健康评分 0-9
    2. Beneish M-Score (8 变量)               — 盈余操纵检测
    3. Altman Z-Score                         — 破产预警（3 档）
    4. DuPont 3/5 分解                        — ROE 归因
    5. Buffett Quality Checks                 — 利润质量、应收/存货增速、非经占比
    6. Sloan Accrual Anomaly                  — 高应计 → 低未来收益
    7. Governance Red Flags（v4 新）           — 质押、减持、股权激励折价
    8. Shareholder Flow Signal（v4 新）        — 户数 × 户均矩阵
    9. Forward Guidance Anomaly（v4 新）       — 业绩预告方向、披露及时性
   10. Related-Party / Subsidiary Exposure    — 长期股权投资波动、权益法损失

Usage:
    from scripts.financial_audit import audit
    result = audit(bundle_dir=Path("output/实丰文化_audit/raw_data"))
    # result["red_flags"] 是按 severity 排序的清单
    # result["markdown"] 是 markdown 格式报告

CLI:
    python3 -m scripts.financial_audit output/实丰文化_audit/raw_data/
"""
from __future__ import annotations
import sys

import argparse
import re
import json
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

try:                                    # 包内导入(python -m scripts.financial_audit / 测试)
    from .periods import iso as period_iso, period_label
except ImportError:                     # 直接按文件跑(python scripts/financial_audit.py)
    from periods import iso as period_iso, period_label  # type: ignore[no-redef]


# ============================================================================
# Data classes
# ============================================================================

SEVERITY_ORDER = {"🔴 致命": 0, "🟠 高": 1, "🟡 中": 2, "🟢 低": 3, "ℹ️ 信息": 4}


@dataclass
class RedFlag:
    framework: str          # 大师框架名
    signal: str             # 信号名
    severity: str           # 🔴 致命 / 🟠 高 / 🟡 中 / 🟢 低 / ℹ️ 信息
    value: Any              # 数值（触发阈值的那个数字）
    threshold: str          # 阈值描述
    evidence: str           # 证据（涉及的字段/期间）
    implication: str        # 蕴含（投资含义）
    # 读者向展示(v8.15): signal 是规则名/公式串(「Z=2.837」「F=5/9」), 首页 Top3 卡与红标浮层
    # 用这两句人话。**不进 id**(id 只由 framework + signal 骨架决定, 见 red_flags.flag_id),
    # 所以改这里的措辞不会打断已发布报告节点 YAML 里的红旗引用。
    plain_title: str = ""   # 人话标题(带关键数字与期别, 如「破产风险指标 Z 值 2.84,落在灰色地带」)
    plain_note: str = ""    # 一句后果(这条信号对读者意味着什么)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# Utilities
# ============================================================================

def _safe_float(x) -> float | None:
    try:
        if x is None:
            return None
        v = float(x)
        if math.isnan(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _load_bundle(bundle_dir: Path) -> dict[str, pd.DataFrame]:
    """Load all *.parquet files from bundle_dir."""
    bundle = {}
    for p in bundle_dir.glob("*.parquet"):
        try:
            bundle[p.stem] = pd.read_parquet(p)
        except Exception:
            pass
    return bundle


def _annual(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to annual rows (end_date ending in 1231), sorted ascending."""
    if df is None or df.empty or "end_date" not in df.columns:
        return pd.DataFrame()
    mask = df["end_date"].astype(str).str.endswith("1231")
    ann = df.loc[mask].copy()
    if ann.empty:
        return ann
    ann["_year"] = ann["end_date"].astype(str).str[:4].astype(int)
    ann = ann.sort_values("_year").drop_duplicates("_year", keep="last")
    return ann


def _latest_row(df: pd.DataFrame, col: str = "end_date") -> pd.Series | None:
    """Return the single row with the largest end_date (latest reporting period)."""
    if df is None or df.empty or col not in df.columns:
        return None
    return df.sort_values(col, ascending=False).iloc[0]


def _latest_period_row(df: pd.DataFrame) -> pd.Series | None:
    """最新报告期那一行(含季报/半年报, **年内累计**口径)。

    与 `_invest_income_in_operating_profit` 同一取法(同一 end_date 的重复行取首条)。
    `_annual()` 只取 1231 行 —— 拿它判「最新期」会把去年年报当成最新(立讯 v8.15 D1)。
    """
    if df is None or df.empty or "end_date" not in df.columns:
        return None
    d = df.copy()
    d["end_date"] = d["end_date"].astype(str)
    return d.drop_duplicates("end_date").sort_values("end_date").iloc[-1]


def _period_words(end_date) -> str:
    """证据里的期别: 「2026 前三季度累计(截至 2026-09-30)」—— 人话 + end_date 两样都在。"""
    return f"{period_label(end_date)}(截至 {period_iso(end_date)})"


# ============================================================================
# Framework 1: Piotroski F-Score
# ============================================================================

def _piotroski(bundle: dict) -> list[RedFlag]:
    """Compute Piotroski F-Score (0-9). F <= 3 is weak, F >= 7 is strong.

    Uses the latest 2 annual reports.
    """
    flags: list[RedFlag] = []
    inc = _annual(bundle.get("income", pd.DataFrame()))
    bs = _annual(bundle.get("balancesheet", pd.DataFrame()))
    cf = _annual(bundle.get("cashflow", pd.DataFrame()))
    fi = _annual(bundle.get("fina_indicator", pd.DataFrame()))

    if len(inc) < 2 or len(bs) < 2 or len(cf) < 2:
        return flags  # 数据不足

    y_now, y_prev = inc.iloc[-1], inc.iloc[-2]
    bs_now, bs_prev = bs.iloc[-1], bs.iloc[-2]
    cf_now, cf_prev = cf.iloc[-1], cf.iloc[-2]

    score = 0
    details: list[tuple[str, bool, str]] = []

    # 1. NI > 0
    ni = _safe_float(y_now.get("n_income_attr_p"))
    ok = (ni or 0) > 0
    score += int(ok); details.append(("NI > 0", ok, f"NI={ni}"))

    # 2. ROA > 0
    ta_now = _safe_float(bs_now.get("total_assets"))
    roa = (ni or 0) / ta_now if ta_now else None
    ok = (roa or 0) > 0
    score += int(ok); details.append(("ROA > 0", ok, f"ROA≈{roa:.3f}" if roa else "ROA=?"))

    # 3. OCF > 0
    ocf = _safe_float(cf_now.get("n_cashflow_act"))
    ok = (ocf or 0) > 0
    score += int(ok); details.append(("OCF > 0", ok, f"OCF={ocf}"))

    # 4. OCF > NI (利润质量)
    ok = (ocf or 0) > (ni or 0)
    score += int(ok); details.append(("OCF > NI", ok, f"OCF={ocf}, NI={ni}"))

    # 5. ROA 同比↑
    ni_prev = _safe_float(y_prev.get("n_income_attr_p"))
    ta_prev = _safe_float(bs_prev.get("total_assets"))
    roa_prev = (ni_prev or 0) / ta_prev if ta_prev else None
    ok = (roa or 0) > (roa_prev or 0)
    score += int(ok); details.append(("ROA↑", ok, f"{roa_prev:.3f}→{roa:.3f}" if roa is not None and roa_prev is not None else "n/a"))

    # 6. 资产负债率↓
    tl_now = _safe_float(bs_now.get("total_liab")) or 0
    tl_prev = _safe_float(bs_prev.get("total_liab")) or 0
    dta_now = tl_now / ta_now if ta_now else None
    dta_prev = tl_prev / ta_prev if ta_prev else None
    ok = (dta_now or 1) < (dta_prev or 1)
    score += int(ok); details.append(("资产负债率↓", ok, f"{dta_prev:.3f}→{dta_now:.3f}" if dta_now is not None and dta_prev is not None else "n/a"))

    # 7. 流动比率↑
    tca_now = _safe_float(bs_now.get("total_cur_assets")) or 0
    tcl_now = _safe_float(bs_now.get("total_cur_liab")) or 0
    tca_prev = _safe_float(bs_prev.get("total_cur_assets")) or 0
    tcl_prev = _safe_float(bs_prev.get("total_cur_liab")) or 0
    cr_now = tca_now / tcl_now if tcl_now else None
    cr_prev = tca_prev / tcl_prev if tcl_prev else None
    ok = (cr_now or 0) > (cr_prev or 0)
    score += int(ok); details.append(("流动比率↑", ok, f"{cr_prev:.3f}→{cr_now:.3f}" if cr_now and cr_prev else "n/a"))

    # 8. 毛利率↑
    rev_now = _safe_float(y_now.get("revenue")) or 0
    rev_prev = _safe_float(y_prev.get("revenue")) or 0
    cos_now = _safe_float(y_now.get("oper_cost")) or 0
    cos_prev = _safe_float(y_prev.get("oper_cost")) or 0
    gm_now = (rev_now - cos_now) / rev_now if rev_now else None
    gm_prev = (rev_prev - cos_prev) / rev_prev if rev_prev else None
    ok = (gm_now or 0) > (gm_prev or 0)
    score += int(ok); details.append(("毛利率↑", ok, f"{gm_prev:.3f}→{gm_now:.3f}" if gm_now is not None and gm_prev is not None else "n/a"))

    # 9. 资产周转率↑
    at_now = rev_now / ta_now if ta_now else None
    at_prev = rev_prev / ta_prev if ta_prev else None
    ok = (at_now or 0) > (at_prev or 0)
    score += int(ok); details.append(("资产周转率↑", ok, f"{at_prev:.3f}→{at_now:.3f}" if at_now is not None and at_prev is not None else "n/a"))

    # 综合评分
    if score <= 3:
        sev = "🟠 高"
        implication = "Piotroski F-Score 低，财务健康恶化中，Graham 会避开"
    elif score >= 7:
        sev = "🟢 低"
        implication = "Piotroski F-Score 优，综合财务状况强"
    else:
        sev = "🟡 中"
        implication = "Piotroski 中等，需结合其他框架判断"
    flags.append(RedFlag(
        framework="Piotroski F-Score",
        signal=f"F={score}/9",
        severity=sev,
        value=score,
        threshold="F≤3 警示 / F≥7 优秀",
        evidence=" | ".join(f"{n}={'✓' if o else '✗'}({d})" for n, o, d in details),
        implication=implication,
        plain_title=f"财务健康九项体检得 {score} 分(满分 9 分)",
        plain_note=(
            "九项里过关不到一半,盈利、现金流、负债与效率在同时走弱" if score <= 3 else
            "九项过了大半,盈利、现金流与负债结构整体健康" if score >= 7 else
            "过关项目一半上下,单看这一项下不了结论,要看是哪几项没过"
        ),
    ))
    return flags


# ============================================================================
# Framework 2: Beneish M-Score (盈余操纵检测)
# ============================================================================

def _beneish(bundle: dict) -> list[RedFlag]:
    """Compute Beneish M-Score using 2 latest annual reports.

    M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI + 0.115*DEPI
        - 0.172*SGAI + 4.679*TATA - 0.327*LVGI
    M > -1.78: 可能存在盈余操纵
    """
    flags: list[RedFlag] = []
    inc = _annual(bundle.get("income", pd.DataFrame()))
    bs = _annual(bundle.get("balancesheet", pd.DataFrame()))
    cf = _annual(bundle.get("cashflow", pd.DataFrame()))

    if len(inc) < 2 or len(bs) < 2 or len(cf) < 2:
        return flags

    y_now, y_prev = inc.iloc[-1], inc.iloc[-2]
    bs_now, bs_prev = bs.iloc[-1], bs.iloc[-2]
    cf_now, cf_prev = cf.iloc[-1], cf.iloc[-2]

    def f(row, key): return _safe_float(row.get(key)) or 0

    rev_n, rev_p = f(y_now, "revenue"), f(y_prev, "revenue")
    ar_n, ar_p = f(bs_now, "accounts_receiv"), f(bs_prev, "accounts_receiv")
    ta_n, ta_p = f(bs_now, "total_assets"), f(bs_prev, "total_assets")
    ppe_n, ppe_p = f(bs_now, "fix_assets"), f(bs_prev, "fix_assets")
    ca_n, ca_p = f(bs_now, "total_cur_assets"), f(bs_prev, "total_cur_assets")
    sga_n, sga_p = f(y_now, "sell_exp") + f(y_now, "admin_exp"), f(y_prev, "sell_exp") + f(y_prev, "admin_exp")
    tl_n, tl_p = f(bs_now, "total_liab"), f(bs_prev, "total_liab")
    gp_n = rev_n - f(y_now, "oper_cost")
    gp_p = rev_p - f(y_prev, "oper_cost")
    ni_n = f(y_now, "n_income")
    ocf_n = f(cf_now, "n_cashflow_act")

    try:
        # DSRI: 应收账款日数变化
        dsri = (ar_n / rev_n) / (ar_p / rev_p) if rev_n and rev_p and ar_p else 1.0
        # GMI: 毛利率恶化
        gmi = (gp_p / rev_p) / (gp_n / rev_n) if rev_n and rev_p and gp_n else 1.0
        # AQI: 非流动资产（去 PPE）/ 总资产 变化
        nca_n = ta_n - ca_n - ppe_n
        nca_p = ta_p - ca_p - ppe_p
        aqi = (nca_n / ta_n) / (nca_p / ta_p) if ta_n and ta_p and nca_p else 1.0
        # SGI: 销售增长指数
        sgi = rev_n / rev_p if rev_p else 1.0
        # DEPI: 折旧率恶化
        dep_n = f(cf_now, "depr_fa_coga_dpba")
        dep_p = f(cf_prev, "depr_fa_coga_dpba")
        depi = (dep_p / (dep_p + ppe_p)) / (dep_n / (dep_n + ppe_n)) if (dep_n + ppe_n) and (dep_p + ppe_p) else 1.0
        # SGAI: SGA/销售比
        sgai = (sga_n / rev_n) / (sga_p / rev_p) if rev_n and rev_p and sga_p else 1.0
        # LVGI: 负债率上升
        lvgi = (tl_n / ta_n) / (tl_p / ta_p) if ta_n and ta_p and tl_p else 1.0
        # TATA: 总应计 / 总资产
        tata = (ni_n - ocf_n) / ta_n if ta_n else 0.0

        m_score = (-4.84 + 0.92*dsri + 0.528*gmi + 0.404*aqi + 0.892*sgi
                   + 0.115*depi - 0.172*sgai + 4.679*tata - 0.327*lvgi)

        sev = "🟠 高" if m_score > -1.78 else "🟢 低"
        implication = (
            "M > -1.78，存在盈余操纵可能（Beneish 经典阈值）"
            if m_score > -1.78
            else "M ≤ -1.78，盈余操纵概率低（Beneish 经典阈值）"
        )
        flags.append(RedFlag(
            framework="Beneish M-Score",
            signal=f"M={m_score:.3f}",
            severity=sev,
            value=round(m_score, 3),
            threshold="M > -1.78 警示",
            evidence=f"DSRI={dsri:.2f}|GMI={gmi:.2f}|AQI={aqi:.2f}|SGI={sgi:.2f}|TATA={tata:.3f}|LVGI={lvgi:.2f}",
            implication=implication,
            plain_title=(f"利润操纵嫌疑指标 M 值 {m_score:.2f},"
                         f"{'高于' if m_score > -1.78 else '低于'}警示线 -1.78"),
            plain_note=(
                "按应收、毛利、应计等八项算,账面利润有被「做」出来的嫌疑,要逐项核对应收与应计"
                if m_score > -1.78 else
                "按应收、毛利、应计等八项算,操纵嫌疑低"
            ),
        ))
    except (ZeroDivisionError, TypeError):
        pass
    return flags


# ============================================================================
# Framework 3: Altman Z-Score (破产预警)
# ============================================================================

def _altman(bundle: dict) -> list[RedFlag]:
    flags: list[RedFlag] = []
    inc = _annual(bundle.get("income", pd.DataFrame()))
    bs = _annual(bundle.get("balancesheet", pd.DataFrame()))
    daily_basic = bundle.get("daily_basic", pd.DataFrame())

    if len(inc) < 1 or len(bs) < 1:
        return flags

    y, b = inc.iloc[-1], bs.iloc[-1]
    def f(row, key): return _safe_float(row.get(key)) or 0

    ta = f(b, "total_assets")
    if not ta:
        return flags
    tca = f(b, "total_cur_assets")
    tcl = f(b, "total_cur_liab")
    tl = f(b, "total_liab")
    re = f(b, "undistr_porfit")  # 留存收益
    ebit = f(y, "operate_profit")
    rev = f(y, "revenue")

    # 市值
    mv = 0.0
    if not daily_basic.empty and "total_mv" in daily_basic.columns:
        latest = daily_basic.sort_values("trade_date", ascending=False).iloc[0]
        mv = (_safe_float(latest.get("total_mv")) or 0) * 1e4  # 万元→元

    if not tl:
        return flags

    z = (1.2 * (tca - tcl) / ta
         + 1.4 * re / ta
         + 3.3 * ebit / ta
         + 0.6 * mv / tl
         + 1.0 * rev / ta)

    if z < 1.81:
        sev = "🔴 致命"
        implication = "Z < 1.81，处于破产风险区（Altman 经典阈值）"
        zone, note = "破产风险区", "低于 1.81:营运资金、留存利润与盈利对负债的缓冲太薄,偿债风险高"
    elif z < 2.99:
        sev = "🟠 高"
        implication = "Z ∈ [1.81, 2.99)，灰色地带，财务健康警示"
        zone, note = "灰色地带", "介于 1.81 和 2.99 之间:偿债缓冲偏薄,利润或融资一收紧就会吃紧"
    else:
        sev = "🟢 低"
        implication = "Z ≥ 2.99，财务健康度安全"
        zone, note = "安全区", "高于 2.99:负债有足够的利润与资产缓冲"
    flags.append(RedFlag(
        framework="Altman Z-Score",
        signal=f"Z={z:.3f}",
        severity=sev,
        value=round(z, 3),
        threshold="Z<1.81 破产风险 / Z>2.99 安全",
        evidence=f"营运资本/TA={(tca-tcl)/ta:.3f}|RE/TA={re/ta:.3f}|EBIT/TA={ebit/ta:.3f}|MV/TL={mv/tl:.3f}|S/TA={rev/ta:.3f}",
        implication=implication,
        plain_title=f"破产风险指标 Z 值 {z:.2f},落在{zone}",
        plain_note=note,
    ))
    return flags


# ============================================================================
# Framework 4: DuPont 5-Factor (扩展，含杠杆+税率)
# ============================================================================

def _dupont(bundle: dict) -> list[RedFlag]:
    flags: list[RedFlag] = []
    inc = _annual(bundle.get("income", pd.DataFrame()))
    bs = _annual(bundle.get("balancesheet", pd.DataFrame()))
    fi = _annual(bundle.get("fina_indicator", pd.DataFrame()))

    if len(inc) < 2 or len(bs) < 2:
        return flags

    # 使用 fina_indicator 里的 ROE 做对比
    roe_now = _safe_float(fi.iloc[-1].get("roe")) if not fi.empty else None
    roe_prev = _safe_float(fi.iloc[-2].get("roe")) if len(fi) >= 2 else None

    y_now, y_prev = inc.iloc[-1], inc.iloc[-2]
    b_now, b_prev = bs.iloc[-1], bs.iloc[-2]
    def f(row, key): return _safe_float(row.get(key)) or 0

    for label, y, b in [("最新", y_now, b_now), ("上期", y_prev, b_prev)]:
        rev = f(y, "revenue")
        ni = f(y, "n_income_attr_p")
        ta = f(b, "total_assets")
        te = f(b, "total_hldr_eqy_exc_min_int")
        if rev and ta and te:
            nm = ni / rev  # 净利率
            at = rev / ta  # 资产周转
            lev = ta / te  # 权益乘数
            calc_roe = nm * at * lev
            # 注释：记录（仅信息）
            flags.append(RedFlag(
                framework="DuPont",
                signal=f"{label}ROE 分解",
                severity="ℹ️ 信息",
                value=round(calc_roe, 4),
                threshold="仅展示归因",
                evidence=f"净利率={nm:.3%} × 资产周转={at:.3f} × 权益乘数={lev:.2f}",
                implication=f"ROE={calc_roe:.2%}；来自净利率 {nm:.2%}、周转 {at:.2f}、杠杆 {lev:.2f}",
                plain_title=f"{'最近一年' if label == '最新' else '上一年'}净资产回报率 {calc_roe:.1%} 的来源",
                plain_note=f"净利率 {nm:.2%} × 资产周转 {at:.2f} 次 × 杠杆 {lev:.2f} 倍",
            ))

    # ROE 急剧恶化 (≥10pp)
    if roe_now is not None and roe_prev is not None and (roe_prev - roe_now) > 10:
        flags.append(RedFlag(
            framework="DuPont",
            signal="ROE 急剧恶化",
            severity="🔴 致命",
            value=roe_now,
            threshold="同比下降 > 10pp",
            evidence=f"ROE {roe_prev:.2f}% → {roe_now:.2f}%",
            implication="盈利能力系统性下滑，需追查杠杆/周转/净利率哪一项崩塌",
            plain_title=f"净资产回报率一年掉了 {roe_prev - roe_now:.1f} 个百分点",
            plain_note=f"从 {roe_prev:.2f}% 降到 {roe_now:.2f}%,要查是利润率、周转还是杠杆塌了",
        ))
    return flags


# ============================================================================
# Framework 5: Buffett Quality Checks
# ============================================================================

def _buffett_quality(bundle: dict) -> list[RedFlag]:
    flags: list[RedFlag] = []
    inc = _annual(bundle.get("income", pd.DataFrame()))
    bs = _annual(bundle.get("balancesheet", pd.DataFrame()))
    cf = _annual(bundle.get("cashflow", pd.DataFrame()))

    if len(inc) < 2 or len(bs) < 2 or len(cf) < 2:
        return flags

    y_now, y_prev = inc.iloc[-1], inc.iloc[-2]
    b_now, b_prev = bs.iloc[-1], bs.iloc[-2]
    c_now, _ = cf.iloc[-1], cf.iloc[-2]
    def f(row, key): return _safe_float(row.get(key)) or 0

    # 1. OCF/NI
    ocf = f(c_now, "n_cashflow_act")
    ni = f(y_now, "n_income_attr_p")
    if ni and abs(ni) > 1e4:
        ratio = ocf / ni
        if ratio < 0.8:
            flags.append(RedFlag(
                framework="Buffett Quality",
                signal="利润质量偏弱（OCF/NI）",
                severity="🟠 高" if ratio < 0.5 else "🟡 中",
                value=round(ratio, 3),
                threshold="OCF/NI < 0.8 警示，<0.5 严重",
                evidence=f"OCF={ocf/1e8:.2f}亿 / NI={ni/1e8:.2f}亿",
                implication="净利润含水分，可能是应收/存货虚增而非真实现金流入",
                plain_title=f"经营现金流只有净利润的 {ratio:.0%}",
                plain_note=f"经营现金流 {ocf/1e8:.2f} 亿对净利润 {ni/1e8:.2f} 亿,利润没有同步变成现金,"
                           "可能压在应收账款或存货里",
            ))

    # 2. 应收增速 vs 营收增速
    rev_n, rev_p = f(y_now, "revenue"), f(y_prev, "revenue")
    ar_n, ar_p = f(b_now, "accounts_receiv"), f(b_prev, "accounts_receiv")
    if rev_p and ar_p and rev_n:
        rev_g = rev_n / rev_p - 1
        ar_g = ar_n / ar_p - 1
        if ar_g - rev_g > 0.2:
            flags.append(RedFlag(
                framework="Buffett Quality",
                signal="应收账款增速远高于营收",
                severity="🟠 高",
                value=round(ar_g - rev_g, 3),
                threshold="应收增速 - 营收增速 > 20pp",
                evidence=f"应收增速 {ar_g:.1%} vs 营收增速 {rev_g:.1%}",
                implication="收入可能通过放宽信用条件获得，未来回款压力大",
                plain_title=f"应收账款增速比营收快 {(ar_g - rev_g) * 100:.0f} 个百分点",
                plain_note=f"应收增 {ar_g:.1%}、营收增 {rev_g:.1%},收入可能靠放宽赊账换来,后面回款压力大",
            ))

    # 3. 存货增速 vs 营收增速
    inv_n, inv_p = f(b_now, "inventories"), f(b_prev, "inventories")
    if rev_p and inv_p and rev_n:
        rev_g = rev_n / rev_p - 1
        inv_g = inv_n / inv_p - 1
        if inv_g - rev_g > 0.3:
            flags.append(RedFlag(
                framework="Buffett Quality",
                signal="存货增速远高于营收",
                severity="🟡 中",
                value=round(inv_g - rev_g, 3),
                threshold="存货增速 - 营收增速 > 30pp",
                evidence=f"存货增速 {inv_g:.1%} vs 营收增速 {rev_g:.1%}",
                implication="存货积压，未来可能计提跌价准备",
                plain_title=f"存货增速比营收快 {(inv_g - rev_g) * 100:.0f} 个百分点",
                plain_note=f"存货增 {inv_g:.1%}、营收增 {rev_g:.1%},货压在仓库里,后面可能要计提跌价",
            ))

    # 4. 商誉/净资产
    goodwill = f(b_now, "goodwill")
    te = f(b_now, "total_hldr_eqy_exc_min_int")
    if te:
        gw_ratio = goodwill / te
        if gw_ratio > 0.3:
            flags.append(RedFlag(
                framework="Buffett Quality",
                signal="商誉占净资产过高",
                severity="🟠 高" if gw_ratio > 0.5 else "🟡 中",
                value=round(gw_ratio, 3),
                threshold="商誉/净资产 > 30% 警示",
                evidence=f"商誉={goodwill/1e8:.2f}亿 / 净资产={te/1e8:.2f}亿",
                implication="并购驱动增长，存在商誉减值悬崖风险",
                plain_title=f"商誉占净资产 {gw_ratio:.0%}",
                plain_note=f"商誉 {goodwill/1e8:.2f} 亿,增长靠并购堆出来,标的一旦不及预期就要减值",
            ))

    # 5. 非经常性损益比例（通过 income 的 total_profit - operate_profit 估算）
    op_profit = f(y_now, "operate_profit")
    total_profit = f(y_now, "total_profit")
    if total_profit and abs(total_profit) > 1e4:
        non_op = total_profit - op_profit
        if abs(total_profit):
            non_op_ratio = abs(non_op) / abs(total_profit)
            if non_op_ratio > 0.3:
                flags.append(RedFlag(
                    framework="Buffett Quality",
                    signal="非经常性损益占比过高",
                    severity="🟠 高" if non_op_ratio > 0.5 else "🟡 中",
                    value=round(non_op_ratio, 3),
                    threshold="|非经|/|利润总额| > 30% 警示",
                    evidence=f"非经常性 {non_op/1e8:.3f}亿 / 总利润 {total_profit/1e8:.3f}亿",
                    implication="利润质量低，依赖投资收益/公允价值变动等非主业来源",
                    plain_title=f"营业外收支占利润总额 {non_op_ratio:.0%}",
                    plain_note="利润有一大块不是主营赚的,这部分往后未必还有",
                ))

    flags.extend(_invest_income_in_operating_profit(bundle))
    return flags


def _invest_income_in_operating_profit(bundle: dict) -> list[RedFlag]:
    """投资收益 + 公允价值变动占营业利润的比重(按最新一期, 含半年报)。

    上面第 5 条用 `利润总额 − 营业利润` 估非经常性 —— 那只抓得到**营业外**收支。
    可投资收益与公允价值变动是**计在营业利润里面**的, 整块从这个缝里漏过去:
    金山办公 688111 2026H1 投资收益 19.14 亿 / 营业利润 27.45 亿 = 70%(上年同期 17%),
    净利润同比 +237%, 而营业外收支只有 0.21 亿 —— 第 5 条一声不吭。
    后果是 ROE、净利率、同行分位全被一次性收益顶高, 判质地的人看不到这层。
    """
    flags: list[RedFlag] = []
    inc = bundle.get("income", pd.DataFrame())
    if inc is None or inc.empty or "end_date" not in inc.columns:
        return flags
    inc = inc.drop_duplicates("end_date").sort_values("end_date")
    now = inc.iloc[-1]

    def f(row, key):
        return _safe_float(row.get(key)) or 0

    op_profit = f(now, "operate_profit")
    if not op_profit or op_profit <= 0:
        return flags
    invest = f(now, "invest_income") + f(now, "fv_value_chg_gain")
    ratio = invest / op_profit
    if ratio <= 0.30:
        return flags

    # 同比:上年同期(end_date 减 10000)有则一起写进证据 —— 「一直这样」和「今年突然」不是一回事
    period = str(now.get("end_date", ""))
    prev_txt = ""
    try:
        prev = inc[inc["end_date"].astype(str) == str(int(period) - 10000)]
        if not prev.empty:
            p = prev.iloc[-1]
            p_op = f(p, "operate_profit")
            if p_op > 0:
                p_ratio = (f(p, "invest_income") + f(p, "fv_value_chg_gain")) / p_op
                prev_txt = f", 上年同期 {p_ratio*100:.0f}%"
    except (TypeError, ValueError):
        pass

    flags.append(RedFlag(
        framework="Buffett Quality",
        signal="投资收益占营业利润过高",
        severity="🟠 高" if ratio > 0.5 else "🟡 中",
        value=round(ratio, 3),
        threshold="(投资收益+公允价值变动)/营业利润 > 30% 警示",
        evidence=f"{period}: 投资收益类 {invest/1e8:.2f}亿 / 营业利润 {op_profit/1e8:.2f}亿{prev_txt}",
        implication="这块不是主营赚的(理财、处置、联营重估都在里面)，"
                    "ROE / 净利率 / 同行分位会被一次性顶高——判质地要用扣除后的口径",
        plain_title=f"投资收益与公允价值变动占营业利润 {ratio:.0%}({period_label(period)})",
        plain_note=f"投资类收益 {invest/1e8:.2f} 亿对营业利润 {op_profit/1e8:.2f} 亿{prev_txt.replace(', ', ',')};"
                   "这块不是主营赚的(理财、处置、联营收益都在里面),回报率与利润率会被它顶高",
    ))
    return flags


# ============================================================================
# Framework 6: Sloan Accrual Anomaly
# ============================================================================

def _sloan(bundle: dict) -> list[RedFlag]:
    """高应计 → 未来收益弱（Sloan 1996）"""
    flags: list[RedFlag] = []
    inc = _annual(bundle.get("income", pd.DataFrame()))
    cf = _annual(bundle.get("cashflow", pd.DataFrame()))
    bs = _annual(bundle.get("balancesheet", pd.DataFrame()))

    if len(inc) < 1 or len(cf) < 1 or len(bs) < 1:
        return flags

    y, c, b = inc.iloc[-1], cf.iloc[-1], bs.iloc[-1]
    def f(row, key): return _safe_float(row.get(key)) or 0

    ni = f(y, "n_income")
    ocf = f(c, "n_cashflow_act")
    ta = f(b, "total_assets")

    if ta:
        accruals = ni - ocf
        accrual_ratio = accruals / ta
        if abs(accrual_ratio) > 0.10:
            sev = "🟠 高" if accrual_ratio > 0.10 else "🟡 中"
            flags.append(RedFlag(
                framework="Sloan Accrual",
                signal="高应计比例",
                severity=sev,
                value=round(accrual_ratio, 3),
                threshold="|NI-OCF|/TA > 10%",
                evidence=f"应计={accruals/1e8:.3f}亿 / TA={ta/1e8:.2f}亿",
                implication="正向应计过高暗示未来收益会回归（Sloan 异象）",
                plain_title=f"账面利润与经营现金流的差额占总资产 {accrual_ratio:+.0%}",
                plain_note=("账面利润远高于现金流入,这类利润往后容易回落" if accrual_ratio > 0 else
                            "现金流入远高于账面利润,本身不是坏事,要看是不是预收款或一次性回款"),
            ))
    return flags


# ============================================================================
# Framework 7: Governance Red Flags (v4)
# ============================================================================

def _governance(bundle: dict) -> list[RedFlag]:
    flags: list[RedFlag] = []

    # 1. 质押集中度
    pd_df = bundle.get("pledge_detail", pd.DataFrame())
    if not pd_df.empty and "holding_pledge_ratio" in pd_df.columns:
        # 取每个股东最近一次的质押记录
        pd_sorted = pd_df.sort_values("ann_date", ascending=False).drop_duplicates("holder_name", keep="first")
        high_pledge = pd_sorted[pd_sorted["holding_pledge_ratio"].astype(float) > 50]
        if not high_pledge.empty:
            names = high_pledge["holder_name"].tolist()
            flags.append(RedFlag(
                framework="Governance",
                signal="高比例质押股东",
                severity="🟠 高",
                value=len(names),
                threshold="持股质押比例 > 50% 警示",
                evidence=f"涉及 {len(names)} 位股东: {', '.join(names[:3])}",
                implication="平仓风险 + 融资压力；若股价下跌可能引发被动减持",
                plain_title=f"{len(names)} 位股东质押超过各自持股的一半",
                plain_note="股价一旦下跌可能触发平仓,形成被动减持",
            ))

    # 2. 前十大股东里的「内部人」净减持(top10_holders 的 hold_change)
    flags.extend(_top10_insider_selling(bundle))

    # 3. 股权激励深度折价（若 stk_rewards 有授予价，与市价对比）
    sr = bundle.get("stk_rewards", pd.DataFrame())
    daily_basic = bundle.get("daily_basic", pd.DataFrame())
    if not sr.empty and not daily_basic.empty:
        # 取 CEO 级别
        ceo_rows = sr[sr["name"].str.contains("董事长|总经理|CEO", na=False)]
        if not ceo_rows.empty:
            # 如有 hold_vol 字段，报告
            latest_ceo = ceo_rows.sort_values("ann_date", ascending=False).iloc[0]
            hold_vol = _safe_float(latest_ceo.get("hold_vol"))
            reward = _safe_float(latest_ceo.get("reward"))
            if hold_vol and reward:
                if hold_vol / reward > 100:  # 持股数 / 年薪元 > 100 股/元
                    sev = "ℹ️ 信息"; impl = "管理层持股远大于年薪，利益对齐良好"
                elif hold_vol / reward < 10:
                    sev = "🟡 中"; impl = "管理层薪酬驱动 > 持股驱动，对齐弱"
                else:
                    sev = "ℹ️ 信息"; impl = "持股/年薪比中等"
                flags.append(RedFlag(
                    framework="Governance",
                    signal=f"CEO({latest_ceo['name']}) 利益对齐",
                    severity=sev,
                    value=round(hold_vol / reward, 2),
                    threshold="持股量/年薪 > 100 利好 / < 10 警示",
                    evidence=f"持股 {hold_vol/1e4:.1f}万股 / 年薪 {reward/1e4:.1f}万元",
                    implication=impl,
                    plain_title=f"{latest_ceo['name']}持股 {hold_vol/1e4:.1f} 万股、年薪 {reward/1e4:.1f} 万元",
                    plain_note=impl.replace("，", ","),
                ))
    return flags


# 名义持有人: 替别人持股的通道账户, 它们的增减是**底层投资者**在买卖, 不是公司内部人的动作。
#   · 香港中央结算有限公司 = 陆股通(北向)A 股的名义持有人;
#   · 香港中央结算(代理人)有限公司 / HKSCC NOMINEES LIMITED = H 股的名义持有人;
#   · 中国证券金融股份有限公司 = 证金(稳市场资金), 不是产业方。
# 立讯 002475 2026-09-30 实测: 「前十大股东减持 7,761 万股」里 7,327 万股是香港中央结算,
# 控股股东零变动, 却被当成治理红旗上了增量复查的「新增红旗」(v8.15 F)。
NOMINEE_HOLDER_PATTERNS = ("香港中央结算", "HKSCC", "中国证券金融")
NORTHBOUND_HOLDER = "香港中央结算有限公司"
# 财务投资者 = 基金/保险/社保/养老金/银行券商/QFII 自有资金账户等: 它们的调仓是资金面, 不是 Lynch 说的
# 「内部人减持」。剩下的(控股股东、产业方、员工持股平台、自然人)才算内部人。
# ⚠️ 不能按 holder_type 白名单只认「一般企业 / 自然人」: 中际旭创的控股股东(山东中际投资控股)、
# 华特气体的三个员工持股平台在 Tushare 里都是「投资公司」—— 白名单会把真正的内部人漏掉。
FINANCIAL_HOLDER_TYPE = re.compile(r"基金|保险|社保|养老|金融|证券|银行|QFII|信托|资产管理|理财|年金")
FINANCIAL_HOLDER_NAME = re.compile(r"基金|保险|养老|社保|私募|资管|资产管理|信托|年金|理财|自有资金|QFII", re.I)


def _is_nominee(name: str) -> bool:
    squashed = re.sub(r"\s+", "", str(name or "")).upper()
    return any(p.upper() in squashed for p in NOMINEE_HOLDER_PATTERNS)


def _is_financial_investor(name: str, holder_type) -> bool:
    if holder_type is not None and not (isinstance(holder_type, float) and math.isnan(holder_type)):
        if FINANCIAL_HOLDER_TYPE.search(str(holder_type)):
            return True
    return bool(FINANCIAL_HOLDER_NAME.search(str(name or "")))


def _top10_insider_selling(bundle: dict) -> list[RedFlag]:
    """前十大股东减持(治理)+ 北向持股变动(资金面, ℹ️)。

    旧规则把最新一期所有 hold_change<0 的行相加 —— 名为「净减持」, 实为毛减持, 而且把
    北向(香港中央结算)、财务投资者的调仓一并算成「内部人减持」。现在:
      ① 剔除名义持有人(NOMINEE_HOLDER_PATTERNS);
      ② 再剔除财务投资者(_is_financial_investor), 剩下的内部人增减相抵算**净**变动, 净减持 > 100 万股才报;
      ③ 北向那一行若变动 ≥ 总股本 0.5%, 另出一条 ℹ️ 资金面提示(归股东结构, 不归治理)。
    """
    flags: list[RedFlag] = []
    th = bundle.get("top10_holders", pd.DataFrame())
    if th is None or th.empty or "hold_change" not in th.columns or "end_date" not in th.columns:
        return flags
    th = th.copy()
    th["end_date"] = th["end_date"].astype(str)
    latest_period = th["end_date"].max()
    recent = th[th["end_date"] == latest_period].copy()
    if "ann_date" in recent.columns:            # 同一期多次披露(更正公告)取最后一次
        recent = recent.sort_values("ann_date").drop_duplicates("holder_name", keep="last")
    recent["chg_"] = pd.to_numeric(recent["hold_change"], errors="coerce").fillna(0.0)
    names = recent["holder_name"].astype(str)
    nominee = names.map(_is_nominee)
    types = recent["holder_type"] if "holder_type" in recent.columns else pd.Series(None, index=recent.index)
    financial = pd.Series(
        [_is_financial_investor(n, t) for n, t in zip(names, types)], index=recent.index
    )
    insiders = recent[~nominee & ~financial]

    # 持股是**期末时点**数, hold_change 是较上一期的变动 —— 不是「年内累计」, 别套报告期累计的说法
    period_txt = f"{period_iso(latest_period)} 期末较上一期,"
    when = f"{period_iso(latest_period)} 较上期"
    net = float(insiders["chg_"].sum())
    if net < -1_000_000:                         # 内部人净减持超过 100 万股
        sellers = insiders[insiders["chg_"] < 0].sort_values("chg_")
        who = "、".join(f"{r.holder_name} {r.chg_ / 1e4:,.0f} 万股" for r in sellers.head(3).itertuples())
        flags.append(RedFlag(
            framework="Governance",
            signal="前十大股东减持",
            severity="🟡 中",
            value=int(abs(net)),
            threshold="前十大里内部人(控股股东/产业方/持股平台/自然人)净减持 > 100 万股;已剔除北向等名义持有人与基金保险等财务投资者",
            evidence=f"{period_txt}内部人净减持 {abs(net) / 1e4:,.0f} 万股({who})",
            implication="内部人士减持是最重要的负面信号之一（Lynch）",
            plain_title=f"大股东与产业方净减持 {abs(net) / 1e4:,.0f} 万股({when})",
            plain_note=f"减持方:{who};控股股东或产业资本在卖,是最值得警惕的信号之一",
        ))

    north = recent[names == NORTHBOUND_HOLDER]
    if not north.empty:
        chg = float(north["chg_"].iloc[0])
        total_share = None
        db = bundle.get("daily_basic", pd.DataFrame())
        if db is not None and not db.empty and "total_share" in db.columns:
            total_share = _safe_float(db.sort_values("trade_date").iloc[-1].get("total_share"))
        share_pct = abs(chg) / (total_share * 1e4) if total_share else None   # total_share 单位万股
        if chg and share_pct is not None and share_pct >= 0.005:
            verb = "增持" if chg > 0 else "减持"
            flags.append(RedFlag(
                framework="Shareholder Flow",
                signal="北向资金持股变动",
                severity="ℹ️ 信息",
                value=int(chg),
                threshold="陆股通(香港中央结算)单期变动 ≥ 总股本 0.5% 提示",
                evidence=f"{period_txt}香港中央结算{verb} {abs(chg) / 1e4:,.0f} 万股(约占总股本 {share_pct:.2%})",
                implication="北向是名义持有人, 变动反映外资仓位, 属资金面信号, 不是公司治理问题",
                plain_title=f"北向资金{verb} {abs(chg) / 1e4:,.0f} 万股({when})",
                plain_note=f"约占总股本 {share_pct:.2%};这是外资仓位变化,属资金面信号,不是公司治理问题",
            ))
    return flags


# ============================================================================
# Framework 8: Shareholder Flow Signal (v4)
# ============================================================================

def _shareholder_flow(bundle: dict) -> list[RedFlag]:
    """Analyze stk_holdernumber: 户数↓户均↑ = 机构接盘（+）；户数↑户均↓ = 散户涌入（-）"""
    flags: list[RedFlag] = []
    sn = bundle.get("stk_holdernumber", pd.DataFrame())
    if sn.empty or "holder_num" not in sn.columns:
        return flags
    # 先丢掉户数为空的行, 再按 end_date 去重(同一期多次披露取**最后一次**公告):
    # Tushare 会给只有公告日、没有户数的占位行(立讯 2026-07-31 / 08-10 / 09-06 / 09-18 / 10-20 全是 NaN),
    # 旧写法 tail(4) 取到它们 → 最新一期户数 = 0 → 两条规则静默不触发, 增量复查把
    # 「长期户数上升」报成「解除」, 而④正文写着 5 月末→9 月末 +40.1%(v8.15 D4)。
    sn = sn.copy()
    sn["holder_num"] = pd.to_numeric(sn["holder_num"], errors="coerce")
    sn = sn[sn["holder_num"] > 0]
    sn["end_date"] = sn["end_date"].astype(str)
    order = ["end_date", "ann_date"] if "ann_date" in sn.columns else ["end_date"]
    sn = sn.sort_values(order).drop_duplicates(subset=["end_date"], keep="last").tail(4)
    if len(sn) < 2:
        return flags

    # 最近两期对比
    prev, cur = sn.iloc[-2], sn.iloc[-1]
    n_prev = _safe_float(prev.get("holder_num")) or 0
    n_cur = _safe_float(cur.get("holder_num")) or 0
    if n_prev and n_cur:
        change_pct = (n_cur - n_prev) / n_prev
        direction = "↑" if change_pct > 0.05 else "↓" if change_pct < -0.05 else "→"
        if direction == "↑":
            sev = "🟡 中"
            impl = f"{prev['end_date']}→{cur['end_date']} 户数 +{change_pct:.1%}，散户/新进投资者涌入，**高位接盘风险**"
        elif direction == "↓":
            sev = "🟢 低"
            impl = f"{prev['end_date']}→{cur['end_date']} 户数 {change_pct:.1%}，散户减少 / 机构或大户接盘"
        else:
            sev = "ℹ️ 信息"
            impl = "户数变化温和"
        flags.append(RedFlag(
            framework="Shareholder Flow",
            signal="股东户数变化",
            severity=sev,
            value=int(n_cur),
            threshold="户数变化方向作为资金流向信号",
            evidence=f"{prev['end_date']}: {int(n_prev)} → {cur['end_date']}: {int(n_cur)}（{change_pct:+.1%}）",
            implication=impl,
            plain_title=(f"股东户数{'增加' if change_pct > 0 else '减少'} {abs(change_pct):.1%}"
                         if direction != "→" else "股东户数基本持平")
                        + f"({period_iso(prev['end_date'])} → {period_iso(cur['end_date'])})",
            plain_note=("新进散户增多,股价拉升后往往伴随高位接盘风险" if direction == "↑" else
                        "散户在离场,筹码向机构或大户集中" if direction == "↓" else
                        "户数变化温和,没有方向性信号"),
        ))

    # 趋势判断
    if len(sn) >= 4:
        all_num = sn["holder_num"].astype(float).tolist()
        if all_num[-1] < all_num[-4] * 0.8:
            flags.append(RedFlag(
                framework="Shareholder Flow",
                signal="长期户数下降（筹码集中）",
                severity="🟢 低",
                value=int(all_num[-1]),
                threshold="近四次披露户数下降 > 20%(跨度见证据)",
                evidence=f"{sn.iloc[0]['end_date']}: {int(all_num[0])} → {sn.iloc[-1]['end_date']}: {int(all_num[-1])}",
                implication="筹码向机构/大户集中，可能存在布局信号",
                plain_title=f"股东户数累计减少 {1 - all_num[-1] / all_num[0]:.0%}"
                            f"({period_iso(sn.iloc[0]['end_date'])} → {period_iso(sn.iloc[-1]['end_date'])})",
                plain_note="筹码在向机构或大户集中",
            ))
        elif all_num[-1] > all_num[-4] * 1.2:
            flags.append(RedFlag(
                framework="Shareholder Flow",
                signal="长期户数上升（筹码分散）",
                severity="🟡 中",
                value=int(all_num[-1]),
                threshold="近四次披露户数上升 > 20%(跨度见证据)",
                evidence=f"{sn.iloc[0]['end_date']}: {int(all_num[0])} → {sn.iloc[-1]['end_date']}: {int(all_num[-1])}",
                implication="筹码分散，通常伴随股价拉升后的散户涌入，需警惕高位风险",
                plain_title=f"股东户数累计增加 {all_num[-1] / all_num[0] - 1:.0%}"
                            f"({period_iso(sn.iloc[0]['end_date'])} → {period_iso(sn.iloc[-1]['end_date'])})",
                plain_note="筹码在分散,常见于股价拉升后散户涌入,要警惕高位接盘",
            ))
    return flags


# ============================================================================
# Framework 9: Forward Guidance Anomaly (v4)
# ============================================================================

def _forecast_anomaly(bundle: dict) -> list[RedFlag]:
    flags: list[RedFlag] = []
    fc = bundle.get("forecast_vip", pd.DataFrame())
    if fc.empty:
        return flags
    # 最新一条预告
    latest = fc.sort_values("ann_date", ascending=False).iloc[0]
    ftype = str(latest.get("type") or "")
    p_min = _safe_float(latest.get("p_change_min"))
    p_max = _safe_float(latest.get("p_change_max"))

    # 预告方向
    if any(k in ftype for k in ["首亏", "预亏", "续亏"]):
        sev = "🔴 致命" if "首亏" in ftype else "🟠 高"
        flags.append(RedFlag(
            framework="Forecast Anomaly",
            signal=f"业绩预告: {ftype}",
            severity=sev,
            value=ftype,
            threshold="首亏/预亏/续亏 = 负面预告",
            evidence=f"{latest.get('ann_date')} 预告类型={ftype}，变动 {p_min}%~{p_max}%，净利下限 {_safe_float(latest.get('net_profit_min'))}万",
            implication="管理层主动披露亏损警示，比财报更即时",
            plain_title=f"业绩预告:{ftype}",
            plain_note="管理层自己预告亏损,比正式财报来得更早",
        ))
    elif any(k in ftype for k in ["略减", "预减"]):
        flags.append(RedFlag(
            framework="Forecast Anomaly",
            signal=f"业绩预告: {ftype}",
            severity="🟡 中",
            value=ftype,
            threshold="预减 = 边际负面",
            evidence=f"{latest.get('ann_date')} 预告类型={ftype}，变动 {p_min}%~{p_max}%",
            implication="盈利能力下滑，需关注是否一次性还是持续",
            plain_title=f"业绩预告:{ftype}",
            plain_note="管理层自己预告利润下滑,要分清是一次性还是会持续",
        ))

    # 预告区间过宽
    if p_min is not None and p_max is not None:
        width = abs(p_max - p_min)
        if width > 50:
            flags.append(RedFlag(
                framework="Forecast Anomaly",
                signal="预告区间过宽",
                severity="🟡 中",
                value=f"{p_min}%~{p_max}%",
                threshold="区间宽度 > 50pp",
                evidence=f"最新预告区间宽度 {width}pp",
                implication="管理层对下期业绩不确定性大，可能预示波动",
                plain_title=f"业绩预告上下限相差 {width:.0f} 个百分点",
                plain_note="管理层自己也看不准下一期,业绩波动可能大",
            ))
    return flags


# ============================================================================
# Framework 10: Valuation Anomaly (PE/PB/PS 历史分位 + Gordon 错配)
# ============================================================================

def _valuation(bundle: dict) -> list[RedFlag]:
    """估值审计：PE/PB/PS 历史分位 + PB vs ROE 错配 + 股息率"""
    flags: list[RedFlag] = []
    db = bundle.get("daily_basic", pd.DataFrame())
    fi = _annual(bundle.get("fina_indicator", pd.DataFrame()))
    if db.empty:
        return flags

    db_sorted = db.sort_values("trade_date", ascending=False).copy()
    latest = db_sorted.iloc[0]

    # 最新估值快照
    pe_ttm = _safe_float(latest.get("pe_ttm"))
    pb = _safe_float(latest.get("pb"))
    ps_ttm = _safe_float(latest.get("ps_ttm"))
    dv_ratio = _safe_float(latest.get("dv_ratio"))  # 股息率 %
    total_mv = _safe_float(latest.get("total_mv"))  # 万元
    trade_date = str(latest.get("trade_date"))

    # 1. PE_TTM 为 NaN（亏损标志）
    if pe_ttm is None:
        flags.append(RedFlag(
            framework="Valuation",
            signal="PE_TTM 不可用（TTM 净利为负）",
            severity="🟠 高",
            value="NaN",
            threshold="TTM 净利 > 0",
            evidence=f"{trade_date} pe_ttm 缺失 = 过去 12 个月累计亏损",
            implication="公司处于亏损状态，PE 估值方法不适用；应看 PB / PS / EV-EBITDA",
            plain_title="过去 12 个月累计亏损,市盈率算不出来",
            plain_note="亏损期不能用市盈率估值,要看市净率、市销率",
        ))

    # 2. PB 历史分位数（3 年）
    if pb is not None and "pb" in db_sorted.columns:
        pb_series = db_sorted["pb"].dropna().astype(float)
        if len(pb_series) >= 100:
            pct = (pb_series <= pb).sum() / len(pb_series)
            if pct > 0.8:
                sev, impl = "🟠 高", f"PB 处于近 1 年 {pct:.0%} 分位，估值偏高"
            elif pct > 0.6:
                sev, impl = "🟡 中", f"PB 处于近 1 年 {pct:.0%} 分位，略偏高"
            elif pct < 0.2:
                sev, impl = "🟢 低", f"PB 处于近 1 年 {pct:.0%} 分位，估值偏低（可能有投资机会）"
            else:
                sev, impl = "ℹ️ 信息", f"PB 处于近 1 年 {pct:.0%} 分位，中性"
            flags.append(RedFlag(
                framework="Valuation",
                signal="PB 历史分位",
                severity=sev,
                value=round(pb, 2),
                threshold=">80% 分位警示 / <20% 可能机会",
                evidence=f"当前 PB={pb:.2f}，近 1 年范围 [{pb_series.min():.2f}, {pb_series.max():.2f}]",
                implication=impl,
                plain_title=f"市净率 {pb:.2f} 倍,处于近一年 {pct:.0%} 分位",
                plain_note=f"近一年市净率在 {pb_series.min():.2f}~{pb_series.max():.2f} 倍之间,"
                           + ("现在偏高" if pct > 0.6 else "现在偏低" if pct < 0.2 else "现在居中"),
            ))

    # 3. PB vs ROE 错配（Gordon 简化：PB 合理值 ≈ ROE/8%）
    if pb is not None and len(fi) > 0:
        roe_latest = _safe_float(fi.iloc[-1].get("roe"))  # 百分数
        if roe_latest is not None:
            fair_pb = roe_latest / 8.0 if roe_latest > 0 else 0.5  # 8% 为 WACC 近似
            # evidence 会原样上首页 Top3 → 写成人话, 算法只留括注
            # (华特 R1 交付 FIX: 「当前 PB=6.21 / 合理 PB (ROE/8%) ≈ 0.85 = 7.3x」这种公式串上了首页)
            basis = (f"按净资产回报率 {roe_latest:.1f}% 应配约 {fair_pb:.2f} 倍(回报率÷8%)"
                     if roe_latest > 0 else
                     f"净资产回报率 {roe_latest:.1f}% 为负,按保守口径最多配 {fair_pb:.2f} 倍")
            if fair_pb > 0 and pb > fair_pb * 2:
                flags.append(RedFlag(
                    framework="Valuation",
                    signal="PB vs ROE 严重错配",
                    severity="🟠 高",
                    value=round(pb / fair_pb, 2),
                    threshold="PB / 合理PB > 2 警示",
                    evidence=f"市净率 {pb:.2f} 倍;{basis},现价是它的 {pb/fair_pb:.1f} 倍",
                    implication=f"ROE={roe_latest:.1f}% 理论配 PB {fair_pb:.1f}x，当前 PB {pb:.2f}x 暗示市场透支预期",
                    plain_title=f"市净率 {pb:.2f} 倍,是回报率撑得起的 {pb/fair_pb:.1f} 倍",
                    plain_note=f"{basis},多出来的部分全靠市场预期兑现",
                ))
            elif fair_pb > 0 and pb < fair_pb * 0.5:
                flags.append(RedFlag(
                    framework="Valuation",
                    signal="PB vs ROE 低估机会",
                    severity="🟢 低",
                    value=round(pb / fair_pb, 2),
                    threshold="PB / 合理PB < 0.5",
                    evidence=f"市净率 {pb:.2f} 倍;{basis},现价不到它的一半",
                    implication=f"ROE={roe_latest:.1f}% 配 PB {fair_pb:.1f}x，当前 {pb:.2f}x 被低估",
                    plain_title=f"市净率 {pb:.2f} 倍,不到回报率撑得起的一半",
                    plain_note=f"{basis},价格可能被低估",
                ))

    # 4. PS 历史分位
    if ps_ttm is not None and "ps_ttm" in db_sorted.columns:
        ps_series = db_sorted["ps_ttm"].dropna().astype(float)
        if len(ps_series) >= 100:
            pct = (ps_series <= ps_ttm).sum() / len(ps_series)
            if pct > 0.85:
                flags.append(RedFlag(
                    framework="Valuation",
                    signal="PS 历史分位过高",
                    severity="🟡 中",
                    value=round(ps_ttm, 2),
                    threshold=">85% 分位警示",
                    evidence=f"当前 PS_TTM={ps_ttm:.2f}，处于近 1 年 {pct:.0%} 分位",
                    implication="营收估值倍数偏高，若增速不匹配需警惕回归",
                    plain_title=f"市销率 {ps_ttm:.2f} 倍,处于近一年 {pct:.0%} 分位",
                    plain_note="按收入算的估值在近一年高位,增速跟不上就会往回落",
                ))

    # 5. 股息率（Graham 防御性）
    if dv_ratio is not None:
        if dv_ratio < 0.5:  # < 0.5%
            flags.append(RedFlag(
                framework="Valuation",
                signal="股息率极低",
                severity="🟡 中",
                value=round(dv_ratio, 3),
                threshold="< 0.5% 视为非防御性",
                evidence=f"当前股息率 {dv_ratio:.2f}%",
                implication="Graham 防御型投资需股息率 > 2%；当前股息不足以构成估值保护",
                plain_title=f"股息率只有 {dv_ratio:.2f}%",
                plain_note="分红几乎不构成估值保护,回报全靠股价",
            ))
        elif dv_ratio > 3.0:
            flags.append(RedFlag(
                framework="Valuation",
                signal="股息率较高",
                severity="🟢 低",
                value=round(dv_ratio, 3),
                threshold="> 3% 具备防御性",
                evidence=f"当前股息率 {dv_ratio:.2f}%",
                implication="股息率高，估值回归时有保护",
                plain_title=f"股息率 {dv_ratio:.2f}%",
                plain_note="分红能在估值回落时提供一层保护",
            ))

    # 6. 市值 vs ROE 的综合警示（简化版"小盘高估"信号）
    if total_mv is not None and pe_ttm is None and pb is not None and pb > 5:
        flags.append(RedFlag(
            framework="Valuation",
            signal="小盘亏损 + 高 PB 双杀",
            severity="🟠 高",
            value=f"mv={total_mv/1e4:.1f}亿, PB={pb:.1f}x",
            threshold="市值 < 100 亿 + 亏损 + PB > 5",
            evidence=f"总市值 {total_mv/1e4:.1f}亿元，当前亏损，PB={pb:.2f}x",
            implication="小盘亏损股享受高 PB 溢价，通常来自概念/题材驱动，缺乏基本面支撑",
            plain_title=f"市值 {total_mv/1e4:.0f} 亿、仍在亏损,市净率却有 {pb:.1f} 倍",
            plain_note="亏损的小盘股享受高估值,多半是题材驱动,缺基本面支撑",
        ))
    return flags


# ============================================================================
# Framework 11: Related-Party / Subsidiary Exposure (实丰文化启发)
# ============================================================================

def _related_party_exposure(bundle: dict) -> list[RedFlag]:
    """长期股权投资波动 + 权益法损失 = 参股公司爆雷（实丰文化超隆光电案例）

    长期股权投资波动是**年末余额对年末余额**(年报对年报, 期别写在证据里);
    投资收益 / 公允价值变动两条判的是「最新期」, 所以取**最新报告期**那一行(年内累计口径),
    证据写明期别。旧写法三条都走 `_annual()` —— 立讯 002475 的公允价值变动取了 FY2025 年报行
    (−6.19 亿)却写「最新期」, 而 2026 前三季度该项是 +5.50 亿, 这条错的红旗上了首页 Top3(v8.15 D1)。
    最新期已转正就不触发。
    """
    flags: list[RedFlag] = []
    def f(row, key): return _safe_float(row.get(key)) or 0

    # 1. 长期股权投资大幅波动(年报对年报)
    bs = _annual(bundle.get("balancesheet", pd.DataFrame()))
    if len(bs) >= 2:
        b_now, b_prev = bs.iloc[-1], bs.iloc[-2]
        lei_now, lei_prev = f(b_now, "lt_eqt_invest"), f(b_prev, "lt_eqt_invest")
        if lei_prev and lei_now:
            change = (lei_now - lei_prev) / lei_prev
            if abs(change) > 0.3:
                flags.append(RedFlag(
                    framework="Related-Party Exposure",
                    signal="长期股权投资大幅波动",
                    severity="🟠 高" if change < 0 else "🟡 中",
                    value=round(change, 3),
                    threshold="长期股权投资变动 > 30%",
                    evidence=f"{b_prev.get('end_date')}: {lei_prev/1e4:.0f}万 → {b_now.get('end_date')}: {lei_now/1e4:.0f}万（{change:+.1%}）",
                    implication="参股公司价值大幅波动，可能存在权益法爆雷风险（实丰文化超隆光电案例）",
                    plain_title=f"长期股权投资一年{'增加' if change > 0 else '减少'} {abs(change):.0%}"
                                f"({period_label(b_now.get('end_date'))})",
                    plain_note="参股公司价值大幅波动,要防联营企业亏损拖累利润",
                ))

    # 2/3 判「最新期」: 最新报告期那一行(季报/半年报是年内累计)
    income = bundle.get("income", pd.DataFrame())
    y = _latest_period_row(income)
    if y is None:
        return flags
    period = str(y.get("end_date"))
    ann = _annual(income)
    last_fy = ann.iloc[-1] if len(ann) and str(ann.iloc[-1].get("end_date")) != period else None

    def _fy_ref(key: str) -> str:
        """最新期不是年报时, 顺手给上一完整年度做参照(读者要能分清「今年」和「去年全年」)。"""
        if last_fy is None:
            return ""
        return f";上一完整年度 {period_label(last_fy.get('end_date'))} 为 {f(last_fy, key)/1e8:.3f}亿"

    # 2. 投资收益大额负值
    inv_inc = f(y, "invest_income")
    if inv_inc < -10_000_000:  # 小于 -1000 万
        flags.append(RedFlag(
            framework="Related-Party Exposure",
            signal="投资收益大额负值",
            severity="🟠 高",
            value=inv_inc,
            threshold="最新报告期(年内累计)投资收益 < -1000 万",
            evidence=f"{_period_words(period)}投资收益 {inv_inc/1e8:.3f}亿{_fy_ref('invest_income')}",
            implication="参股公司权益法损失拖累，查 fina_mainbz 或 PDF 找源头",
            plain_title=f"投资收益亏损 {abs(inv_inc)/1e8:.2f} 亿({period_label(period)})",
            plain_note="参股公司或理财在亏钱,直接拖累利润,要查清是哪一笔",
        ))

    # 3. 公允价值变动大额负值
    fv_chg = f(y, "fv_value_chg_gain")
    if fv_chg < -10_000_000:
        flags.append(RedFlag(
            framework="Related-Party Exposure",
            signal="公允价值变动大额负值",
            severity="🟠 高",
            value=fv_chg,
            threshold="最新报告期(年内累计)公允价值变动 < -1000 万",
            evidence=f"{_period_words(period)}公允价值变动 {fv_chg/1e8:.3f}亿{_fy_ref('fv_value_chg_gain')}",
            implication="或有对价冲回 / 金融资产重估；需查明具体来源",
            plain_title=f"公允价值变动亏损 {abs(fv_chg)/1e8:.2f} 亿({period_label(period)})",
            plain_note="金融资产重估或或有对价冲回造成的账面损失,要查明来源",
        ))
    return flags


# ============================================================================
# Main orchestrator
# ============================================================================

FRAMEWORKS = [
    ("Piotroski F-Score", _piotroski),
    ("Beneish M-Score", _beneish),
    ("Altman Z-Score", _altman),
    ("DuPont 分解", _dupont),
    ("Buffett Quality Checks", _buffett_quality),
    ("Sloan Accrual Anomaly", _sloan),
    ("Governance Red Flags", _governance),
    ("Shareholder Flow", _shareholder_flow),
    ("Forward Guidance Anomaly", _forecast_anomaly),
    ("Valuation Anomaly", _valuation),
    ("Related-Party Exposure", _related_party_exposure),
]


def audit(bundle_dir: Path) -> dict[str, Any]:
    """Run all 10 frameworks on the bundle, return structured result."""
    bundle = _load_bundle(bundle_dir)
    all_flags: list[RedFlag] = []
    framework_status: dict[str, str] = {}
    for name, fn in FRAMEWORKS:
        try:
            flags = fn(bundle)
            if flags:
                all_flags.extend(flags)
                framework_status[name] = f"✅ {len(flags)} 个信号"
            else:
                framework_status[name] = "⚠️ 数据不足或无信号"
        except Exception as e:
            framework_status[name] = f"❌ 错误: {e}"

    # 按 severity 排序
    all_flags.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 99))

    return {
        "bundle_dir": str(bundle_dir),
        "framework_status": framework_status,
        "red_flags": [f.to_dict() for f in all_flags],
        "summary": _format_markdown(bundle_dir, framework_status, all_flags),
    }


def _format_markdown(bundle_dir: Path, status: dict[str, str], flags: list[RedFlag]) -> str:
    lines = [
        f"# 财务异常审计报告",
        f"",
        f"**数据源**: {bundle_dir}",
        f"**审计日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"## §1 框架执行状态（10 个经典框架）",
        f"",
    ]
    for fw, st in status.items():
        lines.append(f"- **{fw}**: {st}")
    # 按严重度汇总
    from collections import Counter
    sev_counts = Counter(f.severity for f in flags)

    lines += [
        f"",
        f"## §2 异常信号统计",
        f"",
        f"| 严重度 | 数量 |",
        f"|-------|:----:|",
    ]
    for sev in ["🔴 致命", "🟠 高", "🟡 中", "🟢 低", "ℹ️ 信息"]:
        if sev_counts.get(sev, 0):
            lines.append(f"| {sev} | {sev_counts[sev]} |")
    lines += [
        f"",
        f"**合计**: {len(flags)} 个信号",
        f"",
        f"## §3 红旗清单（按严重度排序）",
        f"",
    ]
    for i, f in enumerate(flags, 1):
        lines += [
            f"### {i}. [{f.severity}] {f.framework} — {f.signal}",
            f"",
            f"- **触发值**: `{f.value}`",
            f"- **阈值**: {f.threshold}",
            f"- **证据**: {f.evidence}",
            f"- **蕴含**: {f.implication}",
            f"",
        ]
    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

def main():
    for stream in (sys.stdout, sys.stderr):      # Windows 控制台 GBK 下 print emoji 会炸
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    ap = argparse.ArgumentParser(description="Run financial anomaly audit.")
    ap.add_argument("bundle_dir", help="Path to raw_data/ directory")
    ap.add_argument("--out", default=None, help="Output markdown path (default: {parent}/audit_report.md)")
    ap.add_argument("--json", default=None, help="Also write structured JSON to this path")
    args = ap.parse_args()

    bundle_dir = Path(args.bundle_dir)
    result = audit(bundle_dir)

    out_path = Path(args.out) if args.out else bundle_dir.parent / "audit_report.md"
    out_path.write_text(result["summary"], encoding="utf-8")
    print(f"[OK] Markdown audit report → {out_path}")

    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                                    encoding="utf-8")
        print(f"[OK] JSON → {args.json}")

    # 打印摘要到 stdout
    print("\n" + result["summary"][:3500])


if __name__ == "__main__":
    main()
