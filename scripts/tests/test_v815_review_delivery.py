"""v8.15 回归测试: 立讯精密 002475 2026-11-13 增量复查评审打出来的交付缺陷。

每个 TestCase 对应一条缺陷(编号与 CHANGELOG v8.15 一致):
  L2  附录挂载洗掉本机路径与「由 scripts/X.py 自动生成」脚注
  L3  渲染层内部词(面板 peer / 占比尺 F·N / 决断卡 chip 「本节点」)
  D1  公允价值变动 / 投资收益按最新报告期判, 证据写明期别
  D2a 提名 supersedes 更正脚本红旗 + 🟢/ℹ️ 不给组凑条数
  D2b 脚本红旗的人话标题 + 一句后果(id 不变)
  D3  较上版变化: 人话首句、读者面档位名、指标 delta 带期别、证伪本轮 vs 累计
  D4  红旗 diff 识别延续条目 + 股东户数 NaN 占位行导致的误解除
  D5  附录C 的 🔴 换成 ▼(源头 + 旧产物挂载时映射)
  E   segment_band 假跨档(维度混算 / 合计行 / 新旧分类名)
  F   前十大股东减持剔除北向等名义持有人与财务投资者

运行:
    python -m unittest scripts.tests.test_v815_review_delivery
"""
from __future__ import annotations

import ast
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts import assemble_report_v8 as arv8
from scripts import assembly, build_html, financial_audit as fa, lint_v8, periods, triage
from scripts import red_flags as rf
from scripts import verdict_block
from scripts.tests import dongshan_fixture as fx
from scripts.tests.test_assembly_v8 import build, write_run_dir

YI = 1e8
SCRIPTS = Path(__file__).resolve().parent.parent


# ============================================================================
# D1 公允价值变动 / 投资收益: 最新报告期, 证据写期别
# ============================================================================

def _income_rows(rows):
    return pd.DataFrame([
        {"end_date": d, "fv_value_chg_gain": fv * YI, "invest_income": inv * YI,
         "operate_profit": 100 * YI, "revenue": 1000 * YI, "total_profit": 100 * YI}
        for d, fv, inv in rows
    ])


def _bs_rows(dates):
    return pd.DataFrame([{"end_date": d, "lt_eqt_invest": 100 * YI} for d in dates])


class TestD1LatestPeriod(unittest.TestCase):
    def _flags(self, rows):
        bundle = {"income": _income_rows(rows), "balancesheet": _bs_rows(["20241231", "20251231"])}
        return {f.signal: f for f in fa._related_party_exposure(bundle)}

    def test_luxshare_fy_negative_but_ytd_positive_does_not_fire(self):
        """立讯实测: FY2025 公允价值变动 −6.19 亿, 2026 前三季度 +5.50 亿 → 不触发(旧规则取年报行误报)。"""
        flags = self._flags([("20251231", -6.186, 67.6), ("20260630", 3.58, 42.9), ("20260930", 5.50, 61.6)])
        self.assertNotIn("公允价值变动大额负值", flags)
        self.assertNotIn("投资收益大额负值", flags)

    def test_latest_negative_fires_with_period_in_evidence(self):
        flags = self._flags([("20251231", 1.0, 5.0), ("20260930", -2.5, -0.8)])
        fv = flags["公允价值变动大额负值"]
        self.assertIn("2026 前三季度累计", fv.evidence)
        self.assertIn("2026-09-30", fv.evidence)                # end_date 写明
        self.assertIn("2025 年报", fv.evidence)                  # 顺带给上一完整年度做参照
        self.assertNotIn("最新期", fv.evidence)
        self.assertIn("2026 前三季度累计", fv.plain_title)
        self.assertIn("投资收益大额负值", flags)

    def test_annual_latest_has_no_redundant_fy_reference(self):
        flags = self._flags([("20241231", 1.0, 5.0), ("20251231", -2.0, 5.0)])
        ev = flags["公允价值变动大额负值"].evidence
        self.assertIn("2025 年报", ev)
        self.assertNotIn("上一完整年度", ev)

    def test_id_is_unchanged(self):
        """id 只由 framework + signal 骨架决定 —— 证据改写不打断已发布报告的引用。"""
        self.assertEqual(rf.flag_id("Related-Party Exposure", "公允价值变动大额负值"),
                         "related-party-exposure-c5ca8c")


class TestPeriods(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(periods.period_label("20251231"), "2025 年报")
        self.assertEqual(periods.period_label("20260630"), "2026 上半年累计")
        self.assertEqual(periods.period_label("20260930"), "2026 前三季度累计")
        self.assertEqual(periods.period_label("20260331"), "2026 一季度")
        self.assertEqual(periods.period_label("20260917", "trade_date"), "2026-09-17 收盘")

    def test_note_only_when_lengths_differ(self):
        self.assertIn("6 个月 vs 9 个月", periods.period_note("20260630", "20260930"))
        self.assertIsNone(periods.period_note("20250930", "20260930"))
        self.assertIsNone(periods.period_note("20260917", "20261112", "trade_date"))


# ============================================================================
# F 前十大股东减持: 剔除名义持有人与财务投资者
# ============================================================================

def _top10(rows, end="20260930"):
    return pd.DataFrame([
        {"end_date": end, "ann_date": "20261030", "holder_name": n, "hold_change": c, "holder_type": t}
        for n, c, t in rows
    ])


LUXSHARE_TOP10 = [          # 立讯 2026-09-30 实测(股)
    ("立讯有限公司", 0.0, "一般企业"),
    ("香港中央结算有限公司", -73272177.0, "一般企业"),
    ("HKSCCNOMINEESLIMITED", None, "一般企业"),
    ("中国人寿保险股份有限公司-传统-普通保险产品-005L-CT001沪", 26237157.0, "保险投资组合"),
    ("阿布达比投资局-自有资金", -3723893.0, "投资公司"),
    ("太白投资有限公司-自有资金(R)", 3654295.0, "一般企业"),
    ("招商银行股份有限公司-兴全合润混合型证券投资基金", -610480.0, "开放式投资基金"),
]


class TestFTop10Insiders(unittest.TestCase):
    def _flags(self, rows, total_share_wan=774334.0):
        bundle = {"top10_holders": _top10(rows),
                  "daily_basic": pd.DataFrame([{"trade_date": "20261112", "total_share": total_share_wan}])}
        return {f.signal: f for f in fa._top10_insider_selling(bundle)}

    def test_luxshare_northbound_is_not_governance(self):
        flags = self._flags(LUXSHARE_TOP10)
        self.assertNotIn("前十大股东减持", flags)              # 控股股东零变动 → 不是治理红旗
        north = flags["北向资金持股变动"]
        self.assertIn("ℹ️", north.severity)
        self.assertEqual(north.framework, "Shareholder Flow")   # 归股东结构/资金面, 不归治理
        self.assertIn("7,327 万股", north.evidence)
        self.assertIn("0.95%", north.evidence)

    def test_small_northbound_move_is_silent(self):
        flags = self._flags([("香港中央结算有限公司", -4149627.0, "一般企业")], total_share_wan=110000.0)
        self.assertEqual(flags, {})

    def test_employee_platforms_typed_investment_company_still_count(self):
        """华特实测: 员工持股平台在 Tushare 是「投资公司」, 白名单只认一般企业/自然人会漏掉真内部人。"""
        flags = self._flags([
            ("广东华特投资有限公司", 0.0, "投资公司"),
            ("厦门华弘多福投资合伙企业(有限合伙)", -1159900.0, "投资公司"),
            ("厦门华和多福投资合伙企业(有限合伙)", -680000.0, "投资公司"),
            ("张穗萍", -1191770.0, "自然人"),
            ("全国社保基金五零三组合", None, "社保基金、社保机构"),
        ])
        gov = flags["前十大股东减持"]
        self.assertEqual(gov.value, 3031670)
        self.assertIn("厦门华弘多福", gov.evidence)
        self.assertIn("2026-09-30", gov.evidence)

    def test_fund_and_insurer_selling_is_not_insider(self):
        flags = self._flags([
            ("袁永刚", 0.0, "自然人"),
            ("中国人寿保险股份有限公司-传统-普通保险产品-005L-CT001沪", -9742271.0, "保险投资组合"),
            ("招商银行股份有限公司-睿远成长价值混合型证券投资基金", -9677610.0, "其他金融产品"),
        ])
        self.assertNotIn("前十大股东减持", flags)

    def test_net_not_gross(self):
        """旧规则名为「净减持」实为毛减持(只加负数), 现在增减相抵。"""
        flags = self._flags([("甲控股有限公司", -2_000_000.0, "一般企业"),
                             ("乙产业投资有限公司", 1_500_000.0, "一般企业")])
        self.assertNotIn("前十大股东减持", flags)


# ============================================================================
# D4(下) 股东户数: NaN 占位行不能让规则静默失效
# ============================================================================

class TestShareholderFlowNaN(unittest.TestCase):
    def test_luxshare_placeholder_rows_are_ignored(self):
        """立讯实测: 2026-07-31 / 08-10 / 09-06 / 09-18 / 10-20 只有公告日没有户数 → 旧规则取到 NaN,
        「长期户数上升」被增量复查报成解除, 而④正文写 5 月末→9 月末 +40.1%。"""
        rows = [("20260529", "20260609", 397768), ("20260609", "20260609", 397768),
                ("20260630", "20260702", 487393), ("20260630", "20260825", 513997),
                ("20260702", "20260702", 487393), ("20260731", "20260922", None),
                ("20260906", "20260922", None), ("20260930", "20261030", 557188),
                ("20261020", "20261021", None)]
        df = pd.DataFrame([{"end_date": e, "ann_date": a, "holder_num": n} for e, a, n in rows])
        flags = {f.signal: f for f in fa._shareholder_flow({"stk_holdernumber": df})}
        long_up = flags["长期户数上升（筹码分散）"]
        self.assertIn("557188", long_up.evidence)
        self.assertIn("20260609: 397768", long_up.evidence)
        self.assertIn("🟡", flags["股东户数变化"].severity)
        # 同一期(0630)两次披露取后一次 513997, 不取先披露的 487393
        self.assertEqual(rf.flag_id("Shareholder Flow", "长期户数上升（筹码分散）"), "shareholder-flow-69ab57")


# ============================================================================
# D2b 脚本红旗的人话标题(id 不变)
# ============================================================================

class TestD2bPlainTitles(unittest.TestCase):
    def test_every_redflag_call_has_plain_title_and_note(self):
        """源码级守门: financial_audit 里每一处 RedFlag(...) 都带 plain_title 与 plain_note。"""
        tree = ast.parse((SCRIPTS / "financial_audit.py").read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "RedFlag"]
        self.assertGreaterEqual(len(calls), 30)
        for call in calls:
            kws = {k.arg for k in call.keywords}
            self.assertTrue({"plain_title", "plain_note"} <= kws, f"第 {call.lineno} 行的 RedFlag 缺人话字段")

    def _altman(self, z_target: float):
        # 构造一份 Z 落在目标值附近的报表(只靠营收/总资产一项调 Z)
        inc = pd.DataFrame([{"end_date": "20251231", "operate_profit": 0.0, "revenue": z_target * 100}])
        bs = pd.DataFrame([{"end_date": "20251231", "total_assets": 100.0, "total_cur_assets": 0.0,
                            "total_cur_liab": 0.0, "total_liab": 50.0, "undistr_porfit": 0.0}])
        return fa._altman({"income": inc, "balancesheet": bs})[0]

    def test_altman_gray_zone_plain_title(self):
        flag = self._altman(2.837)
        self.assertEqual(flag.signal, "Z=2.837")
        self.assertEqual(flag.plain_title, "破产风险指标 Z 值 2.84,落在灰色地带")
        self.assertIn("1.81", flag.plain_note)

    def test_normalize_carries_display_fields_without_touching_id(self):
        audit = {"red_flags": [self._altman(2.837).to_dict()]}
        item = rf.normalize_audit(audit)[0]
        self.assertEqual(item["id"], "altman-z-score-d676ac")     # 与已发布报告里的 id 一致
        self.assertEqual(item["title"], "Z=2.837")                 # 契约 title 不动
        self.assertEqual(item["display_title"], "破产风险指标 Z 值 2.84,落在灰色地带")
        self.assertTrue(item["display_note"])
        self.assertEqual(verdict_block.validate({"red_flags": [item]}, "appendix-d"), [])

    def test_top3_and_md_use_plain_text(self):
        audit = fx.audit_result()
        for entry in audit["red_flags"]:
            if entry["signal"] == "PB 历史分位":
                entry["plain_title"] = "市净率 22.09 倍,处于近一年 100% 分位"
                entry["plain_note"] = "近一年市净率在 4.57~22.31 倍之间,现在偏高"
        product = build(script_flags=rf.normalize_audit(audit))
        item = next(t for t in product["top3"] if t["red_flag_id"] == fx.PB_FLAG_ID)
        self.assertEqual(item["title"], "市净率 22.09 倍,处于近一年 100% 分位")
        self.assertEqual(item["evidence"], "近一年市净率在 4.57~22.31 倍之间,现在偏高")
        md = arv8.render_top3(product["top3"])
        self.assertIn("**🟠 市净率 22.09 倍,处于近一年 100% 分位**", md)
        self.assertNotIn("**🟠 PB 历史分位**", md)
        html = build_html.render_top3(product)
        self.assertIn("市净率 22.09 倍,处于近一年 100% 分位", html)
        self.assertNotIn(">PB 历史分位<", html)

    def test_old_audit_json_falls_back(self):
        """老 audit JSON 没有 plain_* 字段: 展示退回 title/evidence, 不报错。"""
        item = rf.normalize_audit(fx.audit_result())[0]
        self.assertNotIn("display_title", item)
        self.assertEqual(rf.display_title(item), item["title"])
        self.assertEqual(rf.display_note(item), item["evidence"])


# ============================================================================
# D2a supersedes 更正通道 + 🟢/ℹ️ 不提级
# ============================================================================

def _nominate(nodes, node, item):
    nodes = copy.deepcopy(nodes)
    nodes[node].setdefault("red_flag_nominations", [])
    nodes[node]["red_flag_nominations"] = list(nodes[node]["red_flag_nominations"] or []) + [item]
    return nodes


CORRECTION = {
    "id": "pb-history-period-fix", "level": "🟡", "title": "PB 分位口径其实是近一年, 不代表长期贵",
    "evidence": "近一年 PB 区间 [4.57, 22.31], 拉长到五年只在 60% 分位",
    "source": "nomination", "metric_refs": ["pb"], "supersedes": fx.PB_FLAG_ID,
}


class TestD2aSupersedes(unittest.TestCase):
    def test_superseded_script_flag_leaves_top3_but_stays_in_appendix_d(self):
        before = build()
        self.assertIn(fx.PB_FLAG_ID, [i for t in before["top3"] for i in t["red_flag_ids"]])
        product = build(nodes=_nominate(fx.nodes(), "odds", CORRECTION))
        top_ids = [i for t in product["top3"] for i in t["red_flag_ids"]]
        self.assertNotIn(fx.PB_FLAG_ID, top_ids)
        old = next(f for f in product["red_flags"] if f["id"] == fx.PB_FLAG_ID)
        self.assertEqual(old["superseded_by"], "pb-history-period-fix")
        appendix = arv8.render_appendix_d(product["red_flags"])
        self.assertIn("已由人工复核条目「PB 分位口径其实是近一年", appendix)
        self.assertIn("更正自动审计条目「PB 历史分位」", appendix)

    def test_superseded_flag_no_longer_drives_red_marks(self):
        product = build(nodes=_nominate(fx.nodes(), "odds", CORRECTION))
        pb_mark = product["red_mark_map"]["by_metric"].get("pb")
        self.assertNotIn(fx.PB_FLAG_ID, [f["id"] for f in (pb_mark or {}).get("flags", [])])

    def test_correction_does_not_boost_the_group(self):
        """更正 = 顶替, 不是叠加: PB 组的排序键条数不因更正而增加。"""
        flags = rf.merge(fx.script_flags(), rf.collect_nominations(_nominate(fx.nodes(), "odds", CORRECTION)))
        pb = next(g for g in rf.group_flags(flags) if g["key"] == "pb")
        self.assertEqual(pb["size"], 2)                 # PB vs ROE 🟠 + 更正条 🟡(被更正的 PB 分位不计)

    def test_green_nomination_does_not_lift_rank(self):
        """09-18 立讯实测: 给某组补一条 🟢 提名就把它从 Top3 #2 顶到 #1 —— 现在 🟢/ℹ️ 不凑条数。"""
        base = [t["red_flag_id"] for t in build()["top3"]]
        green = {"id": "ocf-context-note", "level": "🟢", "title": "现金流背离有季节性,年末通常回正",
                 "evidence": "近三年 Q1 OCF 均为负, 全年均为正", "source": "nomination",
                 "metric_refs": ["ocf_ni"]}
        after = [t["red_flag_id"] for t in build(nodes=_nominate(fx.nodes(), "quality", green))["top3"]]
        self.assertEqual(base, after)

    def test_info_flag_does_not_corroborate(self):
        flags = [
            {"id": "a", "level": "🟠", "title": "x", "evidence": "x", "source": "script", "node": "odds",
             "metric_refs": ["pb"]},
            {"id": "b", "level": "ℹ️", "title": "PB 分位中性", "evidence": "x", "source": "script",
             "node": "odds", "metric_refs": ["pb"]},
        ]
        self.assertEqual(rf.group_flags(flags)[0]["size"], 1)

    def test_cannot_supersede_fatal_or_nomination(self):
        fatal = rf.normalize_audit({"red_flags": [{"framework": "Altman Z-Score", "signal": "Z=1.2",
                                                    "severity": "🔴 致命", "evidence": "x"}]})
        nom = dict(CORRECTION, supersedes=fatal[0]["id"], node="quality")
        with self.assertRaises(rf.RedFlagError):
            rf.merge(fatal, [nom])
        a = dict(CORRECTION, id="n1", node="odds", supersedes=None)
        b = dict(CORRECTION, id="n2", node="odds", supersedes="n1")
        with self.assertRaises(rf.RedFlagError):
            rf.merge([], [a, b])

    def test_dangling_supersedes_is_tolerated_and_linted(self):
        nom = dict(CORRECTION, supersedes="related-party-exposure-c5ca8c")
        flags = rf.merge(fx.script_flags(), [dict(nom, node="quality")])
        self.assertTrue(flags[-1]["supersedes_missing"])
        _, warn = lint_v8.rule_red_flag_closure({}, flags, None)
        self.assertTrue(any("supersedes" in f for f in warn.findings))

    def test_node_schema_accepts_supersedes(self):
        block = copy.deepcopy(fx.nodes()["odds"])
        block["red_flag_nominations"] = [dict(CORRECTION, node="odds")]
        self.assertEqual(verdict_block.validate(block, "node-odds"), [])
        bad = copy.deepcopy(block)
        bad["red_flag_nominations"][0]["supersedes"] = "有 空格"
        self.assertTrue(verdict_block.validate(bad, "node-odds"))

    def test_handbooks_document_supersedes(self):
        for name in ("node-quality.md", "node-state.md", "node-odds.md", "node-path.md"):
            text = (SCRIPTS.parent / "references" / name).read_text(encoding="utf-8")
            self.assertIn("supersedes", text, name)


# ============================================================================
# D3 较上版变化: 人话 + 期别 + 证伪口径
# ============================================================================

class TestD3ChangeBlock(unittest.TestCase):
    DELTAS = [
        {"name": "归母净利(年内累计)", "before": "78.43 亿", "after": "130.57 亿",
         "before_period": "20260630", "after_period": "20260930", "period_basis": "report"},
        {"name": "PB", "before": "4.33", "after": "3.28",
         "before_period": "20260917", "after_period": "20261112", "period_basis": "trade_date"},
    ]

    def _cb(self, after_nodes=None, deltas=None):
        product = build(nodes=after_nodes or fx.scenario_a_nodes(), prev_nodes=fx.nodes(),
                        prev_script_flags=fx.script_flags(), metric_deltas=deltas or self.DELTAS)
        self.assertEqual(verdict_block.validate(product, "assembly"), [])
        return product["change_block"]

    def test_md_block_speaks_plainly_and_labels_periods(self):
        md = arv8.render_change_block(self._cb())
        for word in ("阿尔法", "三元组", "等证据临界"):
            self.assertNotIn(word, md)
        self.assertIn("| 行动档位 | 先观察等证据 | 回避 |", md)
        self.assertIn("| ② 在变好吗 |", md)
        self.assertIn("78.43 亿(2026 上半年累计)", md)
        self.assertIn("130.57 亿(2026 前三季度累计)", md)
        self.assertIn("4.33(2026-09-17 收盘)", md)
        self.assertIn("6 个月 vs 9 个月", md)                       # 期长不同要让读者看得出来

    def test_html_block_matches_md(self):
        product = build(nodes=fx.scenario_a_nodes(), prev_nodes=fx.nodes(),
                        prev_script_flags=fx.script_flags(), metric_deltas=self.DELTAS)
        html = build_html.render_change_block(product)
        self.assertIn("130.57 亿(2026 前三季度累计)", html)
        self.assertIn("6 个月 vs 9 个月", html)
        self.assertNotIn("三元组", html)
        self.assertIn("先观察等证据", html)

    def test_falsification_new_vs_cumulative(self):
        """上版已触发的那条不算本轮新增;首句与④一样说「本轮新触发 / 累计」。"""
        prev = fx.nodes()
        prev["path"]["falsifications"][2]["triggered"] = True           # 上版已触发「商誉任一减值」
        after = fx.scenario_a_nodes()
        after["path"]["falsifications"][2]["triggered"] = True
        # 写手重评时顺手改了措辞(补了个字)—— 不能因此把它当成本轮新触发
        after["path"]["falsifications"][2]["condition"] = "商誉任一减值。"
        product = build(nodes=after, prev_nodes=prev, prev_script_flags=fx.script_flags())
        cb = product["change_block"]
        self.assertEqual(cb["falsification_tally"],
                         {"triggered_total": 2, "triggered_new": 1, "carried_over": 1})
        self.assertIn("证伪本轮新触发 1 条、累计已触发 2 条", cb["alpha_summary"])
        md = arv8.render_change_block(cb)
        self.assertIn("**证伪累计已触发**:2 条", md)

    def test_triage_metric_deltas_carry_periods(self):
        before = {"latest_vitals": {"latest_period": "20260630", "latest_revenue": 1745.04e8},
                  "valuation": {"pb": 4.33, "snapshot_date": "20260917"},
                  "profitability": {"roe_latest": 10.0, "roe_trend": {"2024": 9.0, "2025": 10.0}}}
        after = {"latest_vitals": {"latest_period": "20260930", "latest_revenue": 2850.12e8},
                 "valuation": {"pb": 3.28, "snapshot_date": "20261112"},
                 "profitability": {"roe_latest": 20.0, "roe_trend": {"2025": 20.0}}, "annual_period": "20251231"}
        deltas = {d["name"]: d for d in triage.metric_deltas(before, after)}
        rev = deltas["营收(年内累计)"]
        self.assertEqual((rev["before_period"], rev["after_period"], rev["period_basis"]),
                         ("20260630", "20260930", "report"))
        self.assertEqual(deltas["PB"]["period_basis"], "trade_date")
        self.assertEqual(deltas["ROE"]["before_period"], "20251231")   # 老 metrics.json 退到 roe_trend 最大年

    def test_gear_plain_matches_handbook_dictionary(self):
        """读者面档位名 = 链手册 §4.1 人话词典「行动档位(六档)」那一行。"""
        text = (SCRIPTS.parent / "references" / "judgment-chain.md").read_text(encoding="utf-8")
        row = next(l for l in text.splitlines() if l.startswith("| 行动档位(六档)"))
        for enum, plain in assembly.GEAR_PLAIN.items():
            self.assertIn(plain, row, f"{enum} → {plain} 不在 §4.1 词典里")


# ============================================================================
# D4 红旗 diff 识别延续条目
# ============================================================================

class TestD4Succession(unittest.TestCase):
    def _flag(self, fid, level="🟠", node="state", source="nomination", title=None):
        return {"id": fid, "level": level, "title": title or fid, "evidence": "e", "source": source,
                "node": node, "metric_refs": []}

    def test_period_suffix_swap_is_replacement(self):
        before = [self._flag("state-growth-quality-2026h1", title="增收不增利")]
        after = [self._flag("state-growth-quality-2026q3", title="三季报检验落空")]
        changes = assembly._flag_changes(before, after)
        self.assertEqual([(c["id"], c["change"], c.get("replaces")) for c in changes],
                         [("state-growth-quality-2026q3", "replaced", "state-growth-quality-2026h1")])
        self.assertIn("接替上版「增收不增利」", changes[0]["note"])

    def test_family_needs_same_node_and_nomination(self):
        before = [self._flag("x-risk-2026h1", node="state")]
        after = [self._flag("x-risk-2026q3", node="path")]
        kinds = sorted(c["change"] for c in assembly._flag_changes(before, after))
        self.assertEqual(kinds, ["resolved", "triggered"])

    def test_family_strip(self):
        self.assertEqual(assembly.flag_family("state-growth-quality-2026q3"), "state-growth-quality")
        self.assertEqual(assembly.flag_family("path-nom-x-fy2025"), "path-nom-x")
        self.assertEqual(assembly.flag_family("odds-nom-ex-equity-pe"), "odds-nom-ex-equity-pe")

    def test_pre_v89_baseline_ids_are_renormalized(self):
        """东山 08-24 已上线版本实测:基线快照产于 v8.9 之前(id 含数值), 较上版变化报出
        「红旗新增 F=5/9 / 红旗解除 F=5/9」成对噪音。换算成当前 id 后同一条红旗只算一条。"""
        old = {"id": "piotroski-f-score-c262c9", "level": "🟡", "title": "F=5/9", "evidence": "e",
               "source": "script", "node": "quality", "metric_refs": ["f_score"],
               "framework": "Piotroski F-Score"}
        new = dict(old, id=rf.flag_id("Piotroski F-Score", "F=5/9"))
        fixed = rf.renormalize_script_ids([old])
        self.assertEqual(fixed[0]["id"], new["id"])
        self.assertEqual(old["id"], "piotroski-f-score-c262c9")          # 不改调用方的原对象
        self.assertEqual(assembly._flag_changes(fixed, [new]), [])
        nom = {"id": "keep-me", "source": "nomination", "title": "x", "framework": "X"}
        self.assertEqual(rf.renormalize_script_ids([nom])[0]["id"], "keep-me")

    def test_change_block_reports_continuation_not_resolution(self):
        prev = _nominate(fx.nodes(), "state", self._flag("state-growth-quality-2026h1", title="增收不增利"))
        after = _nominate(fx.nodes(), "state", self._flag("state-growth-quality-2026q3", title="三季报落空"))
        product = build(nodes=after, prev_nodes=prev, prev_script_flags=fx.script_flags())
        cb = product["change_block"]
        self.assertNotIn("解除红旗", cb["alpha_summary"])
        self.assertIn("延续上版的红旗 1 条", cb["alpha_summary"])
        self.assertIn("**红旗延续**", arv8.render_change_block(cb))
        self.assertEqual(verdict_block.validate(product, "assembly"), [])


# ============================================================================
# E segment_band: 同维度、剔合计、新旧名归一
# ============================================================================

def _mainbz(path, rows):
    pd.DataFrame([{"ts_code": "002475.SZ", "end_date": d, "bz_item": i, "bz_code": c, "bz_sales": v * YI}
                  for d, i, c, v in rows]).to_parquet(path)


LUX_H1_DIRTY = [   # 立讯 baseline 的 2026H1: 新旧两套名字成对、金额一分不差, 外加三个维度的合计行
    ("20260630", "通讯及数据中心", "P", 166.0886), ("20260630", "通讯互联产品及精密组件", "P", 166.0886),
    ("20260630", "消费电子", "P", 1224.76), ("20260630", "消费性电子", "P", 1224.76),
    ("20260630", "汽车电子", "P", 323.9137), ("20260630", "汽车互联产品及精密组件", "P", 323.9137),
    ("20260630", "其它连接器", "P", 30.28092), ("20260630", "其他", "P", 30.28092),
    ("20260630", "产品", "P", 1745.043), ("20260630", "行业", "I", 1745.043),
    ("20260630", "消费电子", "I", 1224.76), ("20260630", "地区", "D", 1745.043),
    ("20260630", "外销", "D", 1460.592), ("20260630", "内销", "D", 284.4518),
]
LUX_H1_CLEAN = [
    ("20260630", "通讯及数据中心", "P", 166.0886), ("20260630", "消费电子", "P", 1224.76),
    ("20260630", "汽车电子", "P", 323.9137), ("20260630", "其他", "P", 30.28092),
    ("20260630", "产品", "P", 1745.043), ("20260630", "地区", "D", 1745.043),
]
LUX_FY2025 = [
    ("20251231", "通讯及数据中心", "P", 245.6761), ("20251231", "消费电子", "P", 2642.659),
    ("20251231", "汽车电子", "P", 392.5537), ("20251231", "其他", "P", 42.55547),
    ("20251231", "产品", "P", 3323.444),
]


class TestESegmentBand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _cmp(self, before, after):
        b, a = self.dir / "b.parquet", self.dir / "a.parquet"
        _mainbz(b, before)
        _mainbz(a, after)
        return triage.compare_segments(b, a)

    def test_luxshare_false_crossing_is_gone(self):
        """立讯实测证据「产品 33.3%→0.0%; 消费性电子 23.4%→0.0%; 消费电子 23.4%→70.2%」全是假跨档。"""
        res = self._cmp(LUX_H1_DIRTY, LUX_H1_CLEAN)
        self.assertFalse(res["triggered"])
        self.assertIn("消费电子 70.2%→70.2%", res["evidence"])
        self.assertIn("消费电子=消费性电子", res["evidence"])
        self.assertNotIn("产品", res["evidence"].split(";")[0].replace("产品口径", ""))

    def test_luxshare_fy2025_to_h1_same_caliber(self):
        """同口径重算: 消费电子 79.5%→70.2%、汽车电子 11.8%→18.6%、通讯及数据中心 7.4%→9.5%, 均未跨档。"""
        res = self._cmp(LUX_FY2025, LUX_H1_CLEAN)
        self.assertFalse(res["triggered"])
        for txt in ("消费电子 79.5%→70.2%", "汽车电子 11.8%→18.6%", "通讯及数据中心 7.4%→9.5%",
                    "2025 年报→2026 上半年累计"):
            self.assertIn(txt, res["evidence"])

    def test_rename_without_alias_evidence_is_uncertain_not_crossing(self):
        old_names = [("20250630", "消费性电子", "P", 977.99), ("20250630", "汽车互联产品及精密组件", "P", 86.58),
                     ("20250630", "通讯互联产品及精密组件", "P", 110.98)]
        res = self._cmp(old_names, LUX_H1_CLEAN)
        self.assertIsNone(res["triggered"])
        self.assertIn("口径变更", res["evidence"])
        self.assertIn("消费性电子", res["evidence"])

    def test_real_crossing_still_fires(self):
        res = self._cmp([("20251231", "PCB", "P", 96.42), ("20251231", "光模块", "P", 3.58)],
                        [("20260630", "PCB", "P", 88.0), ("20260630", "光模块", "P", 12.0)])
        self.assertTrue(res["triggered"])
        self.assertIn("光模块 3.6%→12.0%", res["evidence"])


# ============================================================================
# L2 附录挂载洗机器出处 / D5 附录C 符号
# ============================================================================

class TestL2D5Appendix(unittest.TestCase):
    SNAPSHOT = (
        "# 数据快照: 立讯精密 (002475.SZ)\n\n**生成日期**: 2026-11-13\n"
        "**数据源**: `C:\\Users\\someone\\.claude\\output\\立讯精密\\raw_data` (Tushare parquet)\n\n"
        "> 本文是报告**附录A 财务与经营明细**的底稿, 全部由脚本从 Tushare parquet 直接拼装, 无 LLM 参与。\n\n"
        "| 期 | 营收 |\n|---|---|\n| 2026Q3 | 2,850 亿 |\n\n"
        "来源见 https://static.cninfo.com.cn/finalpage/2026-10-30/1.PDF 与 xueqiu.com/home/x\n\n---\n\n"
        "*由 `scripts/data_snapshot.py` 自动生成 (确定性 Python 拼装, LLM 不参与)。挂载为报告附录A。*\n"
    )

    def test_strip_machine_provenance(self):
        out = arv8._strip_machine_provenance(self.SNAPSHOT)
        self.assertNotRegex(out, r"[A-Za-z]:\\|someone")
        self.assertNotIn("scripts/", out)
        self.assertNotIn("自动生成", out)
        self.assertNotIn("LLM", out)
        self.assertIn("**数据源**: Tushare parquet", out)
        self.assertIn("https://static.cninfo.com.cn/finalpage/2026-10-30/1.PDF", out)   # 网址不误伤
        self.assertIn("xueqiu.com/home/x", out)
        self.assertIn("| 2026Q3 | 2,850 亿 |", out)

    def test_mounting_strips_and_maps_appendix_c(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "data_snapshot.md").write_text(self.SNAPSHOT, encoding="utf-8")
            (d / "capital_flow.md").write_text(
                "# 资金\n\n| 主力控盘度 | 🔴 高度控盘 |\n\n*由 `scripts/capital_flow.py` 自动生成*\n",
                encoding="utf-8")
            (d / "technical_analysis.md").write_text("### 🔴 看空信号\n\n- 长期弱势 🔴\n", encoding="utf-8")
            sections, records = arv8.build_appendices([], [d])
            text = "\n".join(sections)
            appx_c = next(s for s in sections if s.startswith("## 附录C"))
            self.assertNotIn("🔴", appx_c)
            self.assertIn("▼ 高度控盘", appx_c)
            self.assertIn("▼ 看空信号", appx_c)
            self.assertNotRegex(text, r"[A-Za-z]:\\|scripts/\w+\.py")
            # 采集产物文件本身不动(排障还要看)
            self.assertIn("scripts/capital_flow.py", (d / "capital_flow.md").read_text(encoding="utf-8"))

    def test_phase_aside_in_heading_is_stripped(self):
        out = arv8._strip_machine_provenance("## §3 技术面警示 (供 Phase 3 §九 消费)\n正文(见附录A)")
        self.assertEqual(out, "## §3 技术面警示\n正文(见附录A)")

    def test_appendix_b_peer_word_and_cli_hint(self):
        old = ("**Peer 选取规则**: **人工指定**(`--peer-codes`)—— 不按行业分类自动选\n"
               "> ⚠️ 本表同业是自动选的。选错时用 `--peer-codes 600xxx.SH,300yyy.SZ` 重跑, 本表即按人工指定的同业出。\n"
               "## §2 目标公司在 peer 中的分位\n下表显示 甲 相对 peer group 的分位:\n"
               "| 指标 | 目标值 | Peer 中位数 |\n对比维度从 5 家 peer 扩展到全行业")
        out = arv8._appendix_b_reader_words(old)
        self.assertNotRegex(out, r"(?i)peer")
        for txt in ("**同业选取规则**: **人工指定**—— 不按行业分类自动选", "在同业中的分位",
                    "相对同业组的分位", "| 同业中位数 |", "5 家同业扩展到"):
            self.assertIn(txt, out)

    def test_source_modules_no_longer_emit_red_circle(self):
        """产出的字符串里不再有 🔴(模块 docstring 里那句符号约定说明除外)。"""
        for name in ("capital_flow.py", "technical_analysis.py"):
            tree = ast.parse((SCRIPTS / name).read_text(encoding="utf-8"))
            doc = ast.get_docstring(tree, clean=False)
            emitted = [n.value for n in ast.walk(tree)
                       if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != doc]
            self.assertFalse([v for v in emitted if "🔴" in v], name)
            self.assertTrue([v for v in emitted if "▼" in v], name)


# ============================================================================
# L3 渲染层内部词
# ============================================================================

class TestL3RenderWords(unittest.TestCase):
    def test_panel_tile_and_md_header_say_peer_in_chinese(self):
        nodes = fx.nodes()
        product = build(nodes=nodes)
        html = build_html.render_panel(product)
        self.assertNotIn("peer", html.replace("ROE + peer 分位", ""))     # 指标名是写手写的, 不归渲染层
        self.assertIn("同业分位 0% 分位", html)
        md = arv8.render_panel(product["panel"], product["red_mark_map"])
        self.assertIn("| 同业分位 |", md)
        self.assertNotIn("| peer 分位 |", md)

    def test_chip_title_has_no_internal_word(self):
        chip = build_html._load_chip(["🟠", "🟡"])
        self.assertNotIn("节点", chip)
        self.assertIn("这一章", chip)

    def test_hero_fact_gear_uses_reader_name(self):
        facts = build_html.render_hero_facts(build())
        self.assertIn("先观察等证据", facts)
        self.assertNotIn("等证据临界", facts)


if __name__ == "__main__":
    unittest.main()
