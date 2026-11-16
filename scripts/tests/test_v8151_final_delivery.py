"""v8.15.1 回归测试: 立讯精密 002475 2026-11-13 增量复查的终检(reviewer 走查成品 HTML)开出的八条。

每个 TestCase 对应一条(编号与 CHANGELOG v8.15.1 一致):
  1  ③④章首先出图、判定句被挤到图下 → 图挪到判定句与子判定表之后
  2  较上版变化:首句只写要点(证伪列短名)、上版/本版两列只放取值域并说人话、ℹ️ 叫「信息更新」
  3  首屏流水线标签:「company-analysis v8.0」「机器带出」「同业分位 20% 分位」
  4  Top3 同主题去重(same_theme_as)+ 同级时提名当代表
  5  图上文字与正文对不上:占比尺图例、阶梯图「左尾」与写死的条数
  6  附录标题露出写手指令与版本号
  7  ③分部表拆成四列主表 + 三列理由表;情景表表头说中文;lint R3/R4 仍按逻辑行判
  8  lint R2w 认人话标题里的数字与短语

运行:
    python -m unittest scripts.tests.test_v8151_final_delivery
"""
from __future__ import annotations

import ast
import copy
import re
import tempfile
import unittest
from pathlib import Path

from scripts import assemble_report_v8 as arv8
from scripts import assembly, build_html, derivation, lint_v8, verdict_block
from scripts import red_flags as rf
from scripts.tests import dongshan_fixture as fx
from scripts.tests.test_assembly_v8 import build, write_run_dir
from scripts.tests.test_delivery_html_v8 import build_dongshan

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent


def _flag(fid, level="🟠", node="quality", source="nomination", refs=None, title=None, **extra):
    return dict({"id": fid, "level": level, "title": title or fid, "evidence": f"{fid} 的证据",
                 "source": source, "node": node, "metric_refs": list(refs or [])}, **extra)


# ============================================================================
# 1 章首图挪到判定句与子判定表之后
# ============================================================================

class Test1FiguresAfterVerdict(unittest.TestCase):
    BODY = ('<p><strong>判定:已被价格计入</strong></p>\n<div class="tblwrap"><table><tr><td>子判定</td>'
            '</tr></table></div>\n<details class="drill"><summary>推导</summary><div class="dd">…</div></details>')

    def test_figures_go_after_sub_verdict_table_before_first_fold(self):
        out = build_html.place_figures(self.BODY, '<figure class="meter"></figure>')
        self.assertLess(out.index("判定:"), out.index("<figure"))
        self.assertLess(out.index("</table></div>"), out.index("<figure"))
        self.assertLess(out.index("<figure"), out.index('<details class="drill">'))

    def test_without_fold_falls_back_after_first_table_then_end(self):
        no_fold = self.BODY.split("\n<details")[0]
        out = build_html.place_figures(no_fold + "\n<p>尾段</p>", "<figure></figure>")
        self.assertLess(out.index("</table></div>"), out.index("<figure>"))
        self.assertLess(out.index("<figure>"), out.index("尾段"))
        bare = build_html.place_figures("<p>只有判定</p>", "<figure></figure>")
        self.assertTrue(bare.endswith("<figure></figure>"))
        self.assertEqual(build_html.place_figures(self.BODY, ""), self.BODY)

    def test_full_build_odds_and_path_open_with_verdict(self):
        with tempfile.TemporaryDirectory() as td:
            _, html, _, _ = build_dongshan(td)
        for node, fig in (("odds", 'class="meter"'), ("path", 'class="ladder"')):
            sec = re.search(rf'<section class="chB" id="ch-{node}">.*?</section>', html, re.S).group(0)
            body = sec[sec.index('<div class="bd">'):]
            self.assertLess(body.index("判定"), body.index(fig), node)
            if '<details class="drill">' in body:            # fixture 的④没有折叠段 → 图在判定之后即可
                self.assertLess(body.index(fig), body.index('<details class="drill">'), node)


# ============================================================================
# 2 较上版变化
# ============================================================================

LUX_CASH = ("2026 年报:全年经营现金流净额 <100 亿(FY2025 为 173.25 亿), "
            "或三季报累计经营现金流仍为负(2026H1 为 −24.46 亿)")
LUX_DEBT = ("2026 年末短期借款 >1,000 亿(2026H1 为 935.69 亿), 或货币资金对短期借款的覆盖倍数跌破 0.7 倍"
            "(2026H1 为 0.77 倍), 或出现债券展期、评级下调")


class Test2ChangeBlock(unittest.TestCase):
    def test_falsification_short_names(self):
        self.assertEqual(assembly.falsification_short(LUX_CASH), "全年经营现金流净额 <100 亿")
        self.assertEqual(assembly.falsification_short(LUX_DEBT), "2026 年末短期借款 >1,000 亿")   # 千分位不是逗号
        self.assertEqual(assembly.falsification_short("商誉任一减值。"), "商誉任一减值")
        long = assembly.falsification_short("毛利率连续两个季度低于上年同期且差距超过两个百分点并且没有给出解释")
        self.assertTrue(long.endswith("…") and len(long) <= assembly.FALS_SHORT_MAX + 1)

    def test_plain_verdict_head_maps_internal_words(self):
        cases = {
            "↑变好但仅注意力·未确认——规模在变大、AI 那条腿也是真的": "↑在变好,但还没实锤",
            "↑变好+证据确认——实锤到了": "↑在变好,有实锤",
            "↑未确认": "↑在变好,但还没实锤",
            "高尾险·不可承受——最深一级跌到破净;高信仰体检 6/7": "高尾险·不可承受",
            "高尾险·扛不住,高信仰 5/5": "高尾险·扛不住",
            "高尾险·扛不住(高信仰 5/5)": "高尾险·扛不住",
            "高尾险·不可承受(上版 9 条证伪 0 触发,但地板只兜现价 3.7%)": "高尾险·不可承受",
            "便宜(有余地)": "便宜(有余地)",
            "横盘——收入还在涨": "横盘",
        }
        for verdict, want in cases.items():
            self.assertEqual(assembly.plain_verdict_head(verdict), want, verdict)

    def _lux_like(self):
        """立讯 11-13 的形状:档位 先观察→回避、②从「仅注意力」翻到横盘、两条证伪新亮、一条 ℹ️。"""
        prev, after = fx.nodes(), fx.scenario_a_nodes()
        prev["state"]["verdict"] = "↑变好但仅注意力·未确认——规模在变大,但它只占营收 9.5%"
        prev["path"]["verdict"] = "高尾险·不可承受——最深一级跌到破净;高信仰体检 6/7"
        after["state"]["verdict"] = "横盘——收入还在涨,但三季报检验三条判据全落在证伪一侧"
        after["path"]["verdict"] = "高尾险·不可承受——最坏情形最深落到每股 13.1 元"
        prev["path"]["falsifications"] = [{"condition": LUX_CASH, "triggered": False},
                                          {"condition": LUX_DEBT, "triggered": False}]
        after["path"]["falsifications"] = [{"condition": LUX_CASH, "triggered": True},
                                           {"condition": LUX_DEBT, "triggered": True}]
        for n in (prev, after):
            n["decision"]["triad"] = fx.triad_of(n)
        after["path"]["red_flag_nominations"] = list(after["path"].get("red_flag_nominations") or []) + [
            _flag("path-northbound-info", level="ℹ️", node="path", title="北向资金减持 7,327 万股")]
        product = build(nodes=after, prev_nodes=prev, prev_script_flags=fx.script_flags())
        self.assertEqual(verdict_block.validate(product, "assembly"), [])
        return product

    def test_headline_is_points_only(self):
        cb = self._lux_like()["change_block"]
        head = cb["alpha_summary"]
        self.assertTrue(head.startswith("判断变了:行动档位 先观察等证据→回避;②状态 ↑在变好,但还没实锤→横盘;"))
        self.assertIn("证伪本轮新触发 2 条(全年经营现金流净额 <100 亿、2026 年末短期借款 >1,000 亿)", head)
        self.assertNotIn("FY2025 为 173.25 亿", head)             # 证伪全文不进首句
        self.assertNotIn("仅注意力", head)
        self.assertIn("信息更新 1 条", head)
        self.assertNotIn("绿灯", head)                           # 只有 ℹ️, 没有 🟢
        md = arv8.render_change_block(cb)
        self.assertIn(f"**证伪本轮新触发**:{LUX_CASH}", md)      # 全文仍在逐条清单里

    def test_triad_columns_symmetric_and_plain(self):
        product = self._lux_like()
        cb = product["change_block"]
        md = arv8.render_change_block(cb)
        self.assertIn("| ② 在变好吗 | ↑在变好,但还没实锤 | 横盘 |", md)
        self.assertIn("| ④ 扛得住吗 | 高尾险·不可承受 | 高尾险·不可承受 |", md)
        html = build_html.render_change_block(product)
        for word in ("高信仰", "仅注意力", "规模在变大", "最深落到每股"):    # 两列都不贴整句
            self.assertNotIn(word, md)
            self.assertNotIn(word, html)
        self.assertIn("<td>↑在变好,但还没实锤</td><td>横盘</td>", html)

    def test_info_is_not_called_green(self):
        product = self._lux_like()
        md = arv8.render_change_block(product["change_block"])
        self.assertIn("- **信息更新**:ℹ️ 北向资金减持", md)
        self.assertNotIn("绿灯更新", md)
        html = build_html.render_change_block(product)
        self.assertIn("<b>信息更新</b>", html)
        summary = re.search(r"<summary>(.*?)</summary>", html).group(1)
        self.assertIn("信息变化", summary)
        self.assertNotIn("绿灯", summary)
        self.assertEqual(assembly.soft_flag_label({"level": "🟢"}), "绿灯更新")
        self.assertEqual(assembly.soft_flag_label({"level": "ℹ️"}), "信息更新")
        self.assertEqual(assembly.soft_flag_label({"note": "🟢 PB 分位偏低"}), "绿灯更新")


# ============================================================================
# 3 首屏流水线标签
# ============================================================================

class Test3FrontPageLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as td:
            cls.product, cls.html, _, _ = build_dongshan(td)

    def _visible(self):
        no_comment = re.sub(r"<!--.*?-->", "", self.html, flags=re.S)
        no_style = re.sub(r"<style>.*?</style>|<script>.*?</script>", "", no_comment, flags=re.S)
        return re.sub(r"<[^>]+>", " ", no_style)

    def test_no_pipeline_label_or_version_in_visible_text(self):
        visible = self._visible()
        self.assertNotIn("company-analysis", visible)
        self.assertNotIn("机器带出", visible)
        self.assertNotRegex(visible, r"\bv\d+\.\d+")
        hero = re.search(r'<header class="hero">.*?</header>', self.html, re.S).group(0)
        self.assertIn("基准日 2026-06-22", hero)
        self.assertNotIn("company-analysis", hero)

    def test_version_kept_in_comment_from_skill_md(self):
        meta = re.search(r'version:\s*"?([\w.]+)', (REPO / "SKILL.md").read_text(encoding="utf-8")).group(1)
        self.assertEqual(build_html.skill_version(), f"v{meta}")
        self.assertRegex(self.html, r"<!-- 生成工具: company-analysis v")

    def test_top3_chip_links_to_appendix_d(self):
        self.assertIn('<a class="chip" href="#appx-D">全部风险见附录D</a>', self.html)

    def test_peer_note_no_double_percentile(self):
        self.assertEqual(build_html.peer_note("20% 分位(六家精密制造同业中倒数第二)"),
                         "同业 20% 分位(六家精密制造同业中倒数第二)")
        self.assertEqual(build_html.peer_note("电子特气同业连本公司 5 家:毛利第 4"),
                         "电子特气同业连本公司 5 家:毛利第 4")
        self.assertEqual(build_html.peer_note("第 2 名"), "同业分位 第 2 名")
        self.assertNotIn("同业分位 0% 分位", build_html.render_panel(self.product))

    def test_handbook_example_indicator_name_has_no_peer_suffix(self):
        """「ROE + 同业分位」是写手照手册示例抄的指标名(渲染层不拼), 源头示例改掉。"""
        for rel in ("agents/node-quality.md", "references/node-quality.md"):
            text = (REPO / rel).read_text(encoding="utf-8")
            self.assertNotIn("name: ROE + 同业分位", text, rel)
            self.assertNotIn("ROE+peer 分位", text, rel)


# ============================================================================
# 4 Top3 同主题去重 + 同级提名当代表
# ============================================================================

def _lux_flags(theme: bool) -> list[dict]:
    """立讯 11-13 的红旗形状(id 与分组键照抄), theme=True 时③提名声明与①提名同主题。"""
    script = [
        _flag("altman-z-score-d676ac", source="script", refs=["z_score"],
              title="Z=2.837", display_title="破产风险指标 Z 值 2.84,落在灰色地带"),
        _flag("buffett-quality-6fb171", source="script", refs=["receivables"]),
        _flag("buffett-quality-c95859", level="🟡", source="script", refs=["non_operating"]),
    ]
    ex_equity = _flag("odds-nom-ex-equity-pe", node="odds", refs=["pe_ttm"],
                      title="剔掉不具名联营,市盈率从 21.7 倍翻到 43.4 倍")
    if theme:
        ex_equity["same_theme_as"] = "equity-method-associates-unnamed"
    noms = [
        _flag("equity-method-associates-unnamed", refs=["non_operating"],
              title="贡献归母三成的联营企业一家未具名"),
        _flag("state-growth-quality-2026q3", node="state"),
        ex_equity,
        _flag("odds-nom-peer-pe-artifact", level="🟡", node="odds", refs=["pe_ttm"]),
        _flag("path-nom-short-debt-refi", node="path", refs=["z_score", "debt_ratio"],
              title="短期借款破千亿且已超过货币资金,经营现金流转负,招股书自认可能无法重续"),
        _flag("path-nom-itc337-vpd", node="path", refs=["litigation"]),
        _flag("path-nom-pledge-control-loss", node="path", refs=["pledge_ratio"]),
    ]
    return rf.merge(script, noms)


class Test4ThemeDedupe(unittest.TestCase):
    def test_same_level_nomination_represents_group(self):
        top = rf.top3(_lux_flags(theme=False))
        debt = next(t for t in top if "altman-z-score-d676ac" in t["red_flag_ids"])
        self.assertEqual(debt["red_flag_id"], "path-nom-short-debt-refi")
        self.assertIn("短期借款破千亿", debt["title"])
        self.assertEqual(debt["node"], "path")

    def test_without_declaration_two_cards_share_the_associates_theme(self):
        ids = [t["red_flag_id"] for t in rf.top3(_lux_flags(theme=False))]
        self.assertEqual(ids, ["path-nom-short-debt-refi", "odds-nom-ex-equity-pe",
                               "equity-method-associates-unnamed"])

    def test_declared_theme_gets_one_card_and_frees_a_slot(self):
        top = rf.top3(_lux_flags(theme=True))
        self.assertEqual([t["red_flag_id"] for t in top],
                         ["path-nom-short-debt-refi", "odds-nom-ex-equity-pe", "path-nom-itc337-vpd"])
        theme = top[1]
        self.assertEqual(set(theme["red_flag_ids"]), {"odds-nom-ex-equity-pe", "odds-nom-peer-pe-artifact",
                                                      "equity-method-associates-unnamed",
                                                      "buffett-quality-c95859"})

    def test_theme_merge_dedupes_without_boosting(self):
        """主题组的名次 = 最强成员组本来的名次;多拉进来的条目不给它加分。"""
        flags = rf.merge(
            [],
            [_flag("a1", refs=["m_a"]), _flag("b1", node="path", refs=["m_b"]),
             _flag("b2", level="🟡", node="path", refs=["m_b"]),
             _flag("c1", refs=["m_c"], same_theme_as="a1"),
             _flag("c2", level="🟡", refs=["m_c"]), _flag("c3", level="🟡", refs=["m_c"])],
        )
        groups = {g["key"]: g for g in rf.group_flags(flags)}
        merged = groups["m_c"]                         # c 组(3 条)是主题里最强的成员组, 顶位
        self.assertEqual(merged["size"], 3)            # 不是 1 + 3 = 4
        self.assertEqual(set(merged["theme_keys"]), {"m_a", "m_c"})
        self.assertNotIn("m_a", groups)

    def test_theme_target_superseded_redirects_to_corrector(self):
        flags = rf.merge(
            [_flag("s1", source="script", refs=["m_s"])],
            [_flag("fix", refs=["m_fix"], supersedes="s1"), _flag("x", node="path", refs=["m_x"], same_theme_as="s1")],
        )
        groups = rf.group_flags(flags)
        merged = next(g for g in groups if any(f["id"] == "x" for f in g["flags"]))
        self.assertIn("fix", {f["id"] for f in merged["flags"]})

    def test_missing_theme_target_is_tolerated_and_linted(self):
        flags = rf.merge([], [_flag("x", refs=["m"], same_theme_as=["gone-id"])])
        self.assertTrue(flags[0]["same_theme_missing"])
        _, warn = lint_v8.rule_red_flag_closure({"quality": "x 的证据"}, flags, None)
        self.assertTrue(any("same_theme_as" in f for f in warn.findings))

    def test_appendix_d_lists_all_and_explains(self):
        md = arv8.render_appendix_d(_lux_flags(theme=True))
        self.assertIn("equity-method-associates-unnamed", md)
        self.assertIn("(与「贡献归母三成的联营企业一家未具名」讲同一件事,首页合并成一张卡)", md)

    def test_schema_accepts_string_and_list(self):
        for value in ("equity-method-associates-unnamed", ["a-1", "b-2"]):
            flag = _flag("odds-nom-ex-equity-pe", node="odds", same_theme_as=value)
            self.assertEqual(verdict_block.validate({"red_flags": [flag]}, "appendix-d"), [], value)
        bad = _flag("x", same_theme_as="有空格 的 id")
        self.assertTrue(verdict_block.validate({"red_flags": [bad]}, "appendix-d"))

    def test_html_card_leads_with_representative(self):
        flags = _lux_flags(theme=True)
        product = {"red_flags": flags, "top3": rf.top3(flags)}
        html = build_html.render_top3(product)
        first = html.split('<div class="rk')[1]
        self.assertIn('href="#flag-path-nom-short-debt-refi"', first.split("</a>")[0])
        self.assertIn("破产风险指标 Z 值 2.84", first)          # Z 值留在卡底链接

    def test_handbooks_document_same_theme(self):
        for name in ("node-quality", "node-state", "node-odds", "node-path"):
            text = (REPO / "references" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn("same_theme_as", text, name)
        self.assertIn("same_theme_as", (REPO / "references" / "judgment-chain.md").read_text(encoding="utf-8"))


# ============================================================================
# 5 图上文字与正文统一
# ============================================================================

class Test5FigureWords(unittest.TestCase):
    def test_pfn_legend_uses_body_words(self):
        nodes = fx.nodes()
        fig = build_html.render_pfn_bar(nodes)
        self.assertIn("公司必须做到的任务,不是白送的机会", fig)
        nodes["odds"]["derivation"]["p_f_n"]["kind"] = "free_option"
        legend = re.search(r"<small>(.*?)</small>", build_html.render_pfn_bar(nodes)).group(1)
        self.assertIn("白送的机会", legend)
        self.assertNotRegex(legend, r"[A-Za-z]")                   # 不再挂「free option」

    def test_ladder_says_worst_case_and_no_hardcoded_count(self):
        nodes = copy.deepcopy(fx.nodes())
        fig = build_html.render_left_tail_ladder(nodes)
        self.assertNotIn("左尾", fig)
        self.assertIn("最坏情形有多深", fig)
        self.assertIn("另有量不到股价的最坏情形", fig)
        self.assertNotRegex(fig, r"另有 \d+ 条")

    def test_handbook_dictionary_matches_legend(self):
        text = (REPO / "references" / "judgment-chain.md").read_text(encoding="utf-8")
        row = next(l for l in text.splitlines() if l.startswith("| free option vs embedded obligation"))
        self.assertIn(build_html.PFN_KIND_PLAIN["embedded_obligation"], row)


# ============================================================================
# 6 附录标题洗掉写手指令与版本号
# ============================================================================

class Test6AppendixWriterNotes(unittest.TestCase):
    CASES = {
        "## §4 业绩预告 vs 实际兑现对比 (★ 若 actual 已存在, 主报告必须用 actual, 禁止用预告口径)":
            "## §4 业绩预告 vs 实际兑现对比",
        "| 公告日 | 预告净利区间(万) | **实际归母净利(★ income)** | 兑现状态 |":
            "| 公告日 | 预告净利区间(万) | **实际归母净利** | 兑现状态 |",
        "## §9 限售股解禁日历 (未来 12 个月) ★ v5.1.2 新增": "## §9 限售股解禁日历 (未来 12 个月)",
        "## §4 行业全员估值分布 (v5.1.2,行业 元器件 共 6 家)": "## §4 行业全员估值分布 (行业 元器件 共 6 家)",
        "## §9 北向资金加权建仓成本 (v5.1.2 新增)": "## §9 北向资金加权建仓成本",
        "*★ 户数变化是核心信号: 户数↓ + 户均↑ = 机构吸筹 (capital_flow.md §3 已自动判定)。*":
            "*户数变化是核心信号: 户数↓ + 户均↑ = 机构吸筹。*",
        "| ★ 实控人家族合计持股 | 🟡 家族相对控盘 | 合计 **33.26%** |":
            "| 实控人家族合计持股 | 🟡 家族相对控盘 | 合计 **33.26%** |",
        "### 2.1 利润表关键科目 (来自 income.parquet 最新行 end_date=20260630)":
            "### 2.1 利润表关键科目 (截至 2026-06-30)",          # 表名字段名不要, 期别留下
    }

    def test_strip_writer_notes(self):
        for raw, want in self.CASES.items():
            self.assertEqual(arv8._strip_writer_notes(raw), want, raw)

    def test_legacy_control_note_loses_table_names_and_fake_number(self):
        old = ("**v4.5 口径说明**: 控盘指标用 **top10_holders(含限售)** 作为主口径, 旧版 top10_float(仅流通) "
               "的 22.61% 等数字降为补充(对限售比例高的公司会严重低估真实控盘)。")
        out = arv8._strip_writer_notes(old)
        self.assertEqual(out, arv8.CONTROL_NOTE_PLAIN)
        for word in ("v4.5", "top10", "22.61%"):
            self.assertNotIn(word, out)

    def test_urls_and_citations_survive(self):
        line = "来源 https://x.com/v1.2/a 与(见附录A),版本无关"
        self.assertEqual(arv8._strip_writer_notes(line), line)

    def test_mounting_cleans_all_three_appendices(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "data_snapshot.md").write_text("\n".join(list(self.CASES)[:3]) + "\n", encoding="utf-8")
            (d / "peer_analysis.md").write_text(list(self.CASES)[3] + "\n", encoding="utf-8")
            (d / "capital_flow.md").write_text(
                "# 资金\n\n**v4.5 口径说明**: 控盘指标用 **top10_holders(含限售)** 作为主口径, 旧版 "
                "top10_float(仅流通) 的 22.61% 等数字降为补充。\n\n" + list(self.CASES)[4] + "\n",
                encoding="utf-8")
            sections, _ = arv8.build_appendices([], [d])
        text = "\n".join(sections)
        self.assertNotRegex(text, r"★|v\d+\.\d+|禁止用预告|22\.61%|top10_holders")
        self.assertIn("北向资金加权建仓成本", text)

    def test_snapshot_heading_asof(self):
        from scripts import data_snapshot
        self.assertEqual(data_snapshot._asof("20260630"), "2026-06-30")
        self.assertEqual(data_snapshot._asof(None), "?")

    def test_collector_sources_no_longer_emit_them(self):
        """源头三个采集脚本:输出的标题/表头/说明行里不再有写手指令、版本标签、写死的 22.61%。"""
        for name in ("data_snapshot.py", "peer_collector.py", "capital_flow.py"):
            tree = ast.parse((SCRIPTS / name).read_text(encoding="utf-8"))
            emitted = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                       and isinstance(n.value, str) and n.value.lstrip().startswith(("#", "|", "*", "\n*"))]
            emitted += [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)]
            for s in emitted:
                self.assertNotRegex(s, r"★ 若 actual|v5\.1\.2|v4\.5 口径|22\.61%|★ income|\.parquet 最新行",
                                    f"{name}: {s[:60]}")


# ============================================================================
# 7 ③分部表拆表 + 表头中文;lint R3/R4 按逻辑行
# ============================================================================

def _lux_sotp_derivation() -> dict:
    deriv = copy.deepcopy(fx.nodes()["odds"]["derivation"])
    deriv["sotp"]["profit_label"] = "近四季利润(扣非剔联营按分部毛利分摊;末两行为账面/现金,倍数 1x)"
    return deriv


class Test7SotpTables(unittest.TestCase):
    def test_main_table_has_four_columns_and_short_head(self):
        table = derivation.render_sotp(_lux_sotp_derivation())
        self.assertIn("| 分部 | 近四季利润 | 倍数 | 估值 |", table)
        self.assertNotIn("倍数理由与证伪指标", table)
        main = table.split("\n\n")[0]
        self.assertTrue(all(l.count("|") == 5 for l in main.splitlines()), main)   # 四列 = 五根竖线

    def test_long_head_and_total_note_go_below_the_table(self):
        table = derivation.render_sotp(_lux_sotp_derivation())
        self.assertIn("注:「近四季利润」的口径——扣非剔联营按分部毛利分摊;末两行为账面/现金,倍数 1x。", table)
        self.assertIn("注:只认已并表利润,不走净资产法。", table)

    def test_reasons_table_three_columns(self):
        table = derivation.render_sotp(_lux_sotp_derivation())
        self.assertIn("| 分部 | 为什么给这个倍数 | 什么情况算看错 |", table)
        self.assertIn("| 精密组件 | 并表效应为主 | 并表满一年后增速归零 |", table)

    def test_ttm_header_word(self):
        self.assertEqual(derivation.split_profit_label("TTM 扣非归母"), ("近四季扣非归母", ""))
        self.assertEqual(derivation.split_profit_label("TTM 收入(2025H2+2026H1 自算)"),
                         ("近四季收入", "2025H2+2026H1 自算"))
        self.assertEqual(derivation.split_profit_label(""), ("年化利润", ""))

    def test_dcf_header_in_chinese(self):
        head = derivation.render_dcf(fx.nodes()["odds"]["derivation"]).splitlines()[0]
        self.assertEqual(head, "| 情景 | 概率 | 收入 5 年年复合增速 | 成熟净利率 | 第 5 年市盈率 | 折现值 |")
        self.assertNotRegex(head, r"CAGR|PE")

    def test_rows_layout_keeps_old_logical_rows_for_lint(self):
        deriv = _lux_sotp_derivation()
        rows = derivation.render_sotp_rows(deriv)
        self.assertIn("倍数理由与证伪指标", rows.splitlines()[0])
        self.assertTrue(rows.splitlines()[-1].endswith("只认已并表利润,不走净资产法 |"))
        body = "x\n\n{{sotp}}\n"
        self.assertIn("| 分部 | 近四季利润 | 倍数 | 估值 |", derivation.expand_tables(body, {"derivation": deriv}))
        self.assertEqual(derivation.expand_tables(body, {"derivation": deriv}, layout="rows"), "x\n\n" + rows + "\n")

    def test_r3_citation_in_total_note_still_counts(self):
        """东山实测:合计行的「净负债 153.5 亿」(home ①)靠合计行末格注里的出处交代来源;
        拆表后注挪到表下, 按物理行判就成了异地裸数字。R3 按逻辑行判 → 仍过。"""
        nodes = fx.nodes()
        nodes["odds"]["derivation"]["sotp"]["note"] = "净负债取自①质地的资产负债表"
        with tempfile.TemporaryDirectory() as td:
            run_dir = write_run_dir(Path(td), nodes)
            q = run_dir / "nodes" / "node-quality.md"
            q.write_text(q.read_text(encoding="utf-8") + "\n有息净负债 120 亿。\n", encoding="utf-8")
            loaded = assembly.load_nodes(run_dir / "nodes")
            reader = assembly.load_node_bodies(run_dir / "nodes", loaded)
            rows = assembly.load_node_bodies(run_dir / "nodes", loaded, table_layout="rows")
        self.assertFalse(lint_v8.rule_number_home(reader).passed)       # 按物理行:误报
        self.assertTrue(lint_v8.rule_number_home(rows).passed)          # 按逻辑行:与拆表前一致

    def test_r4_counts_logical_rows(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = write_run_dir(Path(td), fx.nodes())
            loaded = assembly.load_nodes(run_dir / "nodes")
            reader = assembly.load_node_bodies(run_dir / "nodes", loaded)
            rows = assembly.load_node_bodies(run_dir / "nodes", loaded, table_layout="rows")
        self.assertGreater(len(reader["odds"].splitlines()), len(rows["odds"].splitlines()))
        # lint_run 用逻辑行数章预算(拆表是排版, 不该让写手的章凭空超预算)
        src = (SCRIPTS / "lint_v8.py").read_text(encoding="utf-8")
        self.assertIn("rule_budget(row_bodies)", src)
        self.assertIn("rule_number_home(row_bodies)", src)


# ============================================================================
# 8 lint R2w 认人话标题
# ============================================================================

class Test8R2wPlainTitle(unittest.TestCase):
    FLAG = {"id": "altman-z-score-d676ac", "level": "🟠", "title": "Z=2.837",
            "evidence": "营运资本/TA=0.064|留存收益/TA=0.088", "source": "script", "node": "quality",
            "metric_refs": ["z_score"]}

    def _warns(self, flag, body):
        _, warn = lint_v8.rule_red_flag_closure({"quality": body}, [flag], None)
        return warn.findings

    def test_plain_title_number_counts_as_narrated(self):
        body = "偿债缓冲偏薄:破产风险指标的 Z 值 2.84。"
        self.assertTrue(self._warns(self.FLAG, body))                     # 只认旧 title → 漏认
        plain = dict(self.FLAG, display_title="破产风险指标 Z 值 2.84,落在灰色地带")
        self.assertFalse(self._warns(plain, body))

    def test_plain_title_phrase_counts_too(self):
        plain = dict(self.FLAG, display_title="破产风险指标 Z 值 2.84,落在灰色地带")
        self.assertFalse(self._warns(plain, "这家公司的 Z 值落在灰色地带。"))

    def test_short_generic_phrases_are_not_fingerprints(self):
        plain = dict(self.FLAG, display_title="应收账款增速比营收快 25 个百分点")
        tokens = lint_v8.flag_tokens(plain)
        self.assertIn("25个百分点", tokens)
        self.assertNotIn("个百分点", tokens)


if __name__ == "__main__":
    unittest.main()
