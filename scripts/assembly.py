"""assembly — v8 摘要层装配: 决断卡 / 赚钱面板 / Top3 / 主页 metadata / 变化区块。

**零人工抄写**: 唯一输入是五个节点 md 顶部的 fenced YAML verdict 块(契约见 verdict_block)
与 audit 红旗产物; 装配只搬运与合并, 不产任何新结论——
  · 决断卡五行 = 五个节点的 verdict 原文(赔率行机器拼上合理价区间与现价);
  · 面板 = 质地节点自选指标 + 红标反查(red_flags), 结论行引用质地子判定①②;
  · Top3 = 红旗清单两源同池机器带出(red_flags.top3);
  · 主页 metadata = 行动档位人话(决策 verdict)+ 质地字段;
  · 变化区块 = 新旧 YAML 块 diff(增量复查票 09 直接复用)。
  · 读者看得到的档位一律过 gear_plain()(链手册 §4.1 人话词典), 契约枚举只留给机器。

产物过 assembly.schema.json; 渲染(首页/五章/附录A-E)在 assemble_report_v8。
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from . import derivation
from . import periods
from . import red_flags as rf
from . import verdict_block

NODE_SCHEMAS = {
    "quality": "node-quality",
    "state": "node-state",
    "odds": "node-odds",
    "path": "node-path",
    "decision": "node-decision",
}
NODE_FILES = {node: f"node-{node}.md" for node in NODE_SCHEMAS}
NODE_LABELS = dict(rf.NODE_LABELS, decision="⑤怎么办")

# 决断卡五行: (问题, 出处节点) —— 问题名由 assembly.schema.json 锁定
CARD_ROWS = (
    ("是不是好公司", "quality"),
    ("在变好吗", "state"),
    ("贵不贵", "odds"),
    ("扛得住吗", "path"),
    ("怎么办", "decision"),
)

# 面板结论行引用的两个质地子判定(05: 面板不下新结论)
PANEL_CONCLUSION_QUESTIONS = {"biz_model": "生意模式赚钱吗", "quality_true": "赚钱质量真吗"}

# 行动档位的三档态度带(进攻/观望/撤退)。「跨两档」= 跨越两个带(如 核心仓→回避),
# 增量复查硬规则 2 用它判「建议全量重跑」; 东山中报场景 A(等证据临界→回避)= 跨一档, 不触发。
GEAR_BANDS = {"核心仓": 0, "期权仓": 0, "等证据临界": 1, "不追高": 1, "减仓": 2, "回避": 2}

# 行动档位: 契约枚举(链手册 §2.2, YAML 里的 action_gear)→ 读者面叫法(链手册 §4.1 人话词典「行动档位(六档)」)。
# 同一档在报告里只许有一个叫法:⑤正文按词典写「先观察等证据」, 首页区块却直接印枚举「等证据临界」,
# 立讯 11-13 评审判为同档两名(v8.15 D3)。凡读者看得到的档位(首页事实条、报告头、较上版变化)一律过这里;
# CARD_METADATA 与站点分组仍用枚举原词(机器读)。
GEAR_PLAIN = {
    "核心仓": "核心仓",
    "期权仓": "期权小仓",
    "等证据临界": "先观察等证据",
    "不追高": "贵但好·不追高",
    "减仓": "减仓",
    "回避": "回避",
}


def gear_plain(gear: str) -> str:
    """契约档位 → 读者面叫法(未知值原样返回)。"""
    return GEAR_PLAIN.get(gear, gear)

# 质地字段(主页卡片)= verdict 的第一个短语
_QUALITY_FIELD_SPLIT = re.compile(r"[———,,;;((\(]")


class AssemblyError(ValueError):
    """节点块缺失 / 不过 schema / 引用不到红旗——装配拒绝产出半成品。"""


# ---------------------------------------------------------------- 输入

def _load_blocks(nodes_dir, schema_of, what: str) -> dict[str, dict]:
    """读 nodes/ 下五个节点 md 的顶部 YAML 块, 每块按 `schema_of(node)` 校验; 任一不合法即抛错。"""
    nodes_dir = Path(nodes_dir)
    blocks, problems = {}, []
    for node, fname in NODE_FILES.items():
        path = nodes_dir / fname
        if not path.exists():
            problems.append(f"{fname}: 文件不存在")
            continue
        try:
            data, errs = verdict_block.load_and_validate(path, schema_of(node))
        except verdict_block.BlockNotFound as exc:
            problems.append(f"{fname}: {exc}")
            continue
        problems.extend(f"{fname} → {e}" for e in errs)
        blocks[node] = data
    if problems:
        raise AssemblyError(f"{what}:\n  - " + "\n  - ".join(problems))
    return blocks


def load_nodes(nodes_dir) -> dict[str, dict]:
    """读**本版** run 的五个节点块并逐个过**当前完整契约**。任一不合法即抛错。"""
    return _load_blocks(nodes_dir, NODE_SCHEMAS.__getitem__, "节点 YAML 块不合契约")


def load_baseline_nodes(nodes_dir) -> dict[str, dict]:
    """读**上版** run 的五个节点块,只校验「较上版变化」区块真正消费的字段(change-baseline schema)。

    上版产于更早的契约时(如票 11 之前没有 series / derivation / depth_pct),拿今天的完整契约去卡它,
    会把一份完好的上版判成不合格,变化区块整个算不出来。实测:东山 08-24 那份增量复查做契约迁移后重装配,
    不带 --prev-run-dir 就静默丢了「较上版变化」,带上又被 08-19 的旧契约节点挡住 —— 两头都是错。
    校验范围 = 消费范围(同票 10 compare-member-source 的原则)。

    ⚠️ 只用于**比对**。要**复用**上版节点(triage --apply-reuse 拷进本版)时,那份节点会成为本版的一部分,
    仍须过当前完整契约 —— 这由 init_run 的硬规则 1 用 `load_nodes` 严格把关,别在那里换成本函数。
    """
    return _load_blocks(nodes_dir, lambda _node: "change-baseline", "上版节点块缺「较上版变化」要用的字段")


def load_node_bodies(nodes_dir, nodes: dict[str, dict] | None = None,
                     table_layout: str = "reader") -> dict[str, str]:
    """读五个节点 md 的正文(剥掉顶部 YAML 块与写手自带的章节标题行)。

    给了 `nodes`(已过 schema 的五块)就顺手把③赔率正文里的
    `{{sotp}}` / `{{discount_rate}}` / `{{dcf}}` 占位换成机器渲染的表(票 11)——
    **装配与 lint 必须传同一个 nodes**, 否则 R10「报告与节点同步」会拿展开前的正文
    去比展开后的报告, 每次都判不同步。
    `table_layout="rows"` 只给 lint 的 R3 / R4 用(SOTP 按逻辑行展开, 见 derivation.render_sotp_rows)。
    """
    nodes_dir = Path(nodes_dir)
    bodies = {}
    for node, fname in NODE_FILES.items():
        path = nodes_dir / fname
        if not path.exists():
            continue
        body = strip_yaml_block(path.read_text(encoding="utf-8"), node)
        if node == "odds" and nodes:
            body = derivation.expand_tables(body, nodes.get("odds") or {}, layout=table_layout)
        bodies[node] = body
    return bodies


_TOP_BLOCK = re.compile(r"\A\s*```yaml[ \t]*\n.*?\n[ \t]*```[ \t]*\n?", re.DOTALL)
_LEADING_HEADING = re.compile(r"\A\s*(#{1,2} [^\n]*)\n")
# 章节标题的识别词(只有这类标题才由装配统一发, 正文内的小标题一概保留)
CHAPTER_KEYWORDS = {
    "quality": ("①", "质地"), "state": ("②", "状态"), "odds": ("③", "赔率"),
    "path": ("④", "路径"), "decision": ("⑤", "怎么办"),
}


def strip_yaml_block(md_text: str, node: str | None = None) -> str:
    """去掉顶部 YAML 块; 正文若自带本章的章节标题(# / ##)一并去掉——章标题由装配统一发。"""
    body = _TOP_BLOCK.sub("", md_text, count=1)
    m = _LEADING_HEADING.match(body)
    if m and node and any(kw in m.group(1) for kw in CHAPTER_KEYWORDS[node]):
        body = body[m.end():]
    return body.strip("\n")


# ---------------------------------------------------------------- 决断卡 / 面板 / metadata

def _fmt_number(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def odds_card_text(odds: dict) -> str:
    """赔率行 = verdict + 合理价区间两端 (+ 现价对比 / 不同向标记), 机器拼装。"""
    anchor = odds["anchor_range"]
    low, high = anchor["low"], anchor["high"]
    unit = low.get("unit") or high.get("unit") or ""
    text = f"{odds['verdict']};合理价区间 {_fmt_number(low['value'])}-{_fmt_number(high['value'])}"
    if unit:
        text += f" {unit}"
    if not anchor.get("same_direction", True):
        text += "(两端不同向:取决于口径)"
    price = odds.get("current_price")
    if price:
        text += f" vs 现价 {_fmt_number(price['value'])}"
        p_unit = price.get("unit") or unit
        if p_unit:
            text += f" {p_unit}"
    return text


def build_verdict_card(nodes: dict[str, dict]) -> list[dict]:
    """决断卡五行 = 五个节点 verdict 原文(赔率行拼合理价区间), 一行一处权威。"""
    card = []
    for question, node in CARD_ROWS:
        block = nodes.get(node)
        if not block:
            raise AssemblyError(f"决断卡缺 {node} 节点块")
        text = odds_card_text(block) if node == "odds" else block["verdict"]
        card.append({"question": question, "verdict": text, "source_node": node})
    return card


def quality_field(quality_verdict: str) -> str:
    """主页质地字段 = 质地 verdict 的第一个短语(如「部分好——真卡位+平庸财务」→「部分好」)。"""
    return _QUALITY_FIELD_SPLIT.split(quality_verdict, 1)[0].strip() or quality_verdict.strip()


def _sub_verdict(block: dict, question: str) -> dict:
    for sub in block.get("sub_verdicts") or []:
        if sub.get("question") == question:
            return sub
    raise AssemblyError(f"质地节点缺子判定「{question}」(面板结论行的引用来源)")


def build_panel(nodes: dict[str, dict], flags: list[dict]) -> dict:
    """赚钱面板 = 质地节点自选 3-5 指标(原样搬运)+ 结论行引用质地子判定①②。

    面板零新结论:结论行是引用, 红标由 red_flags 反查(见 build_assembly 的 red_mark_map)。
    """
    quality = nodes["quality"]
    panel_src = quality["panel"]
    conclusion = {}
    for key, question in PANEL_CONCLUSION_QUESTIONS.items():
        sub = _sub_verdict(quality, question)
        conclusion[key] = f"{sub['judgment']} {sub['question']}"
    return {
        "industry_reason": panel_src["industry_reason"],
        "conclusion": conclusion,
        "indicators": [dict(i) for i in panel_src["indicators"]],
    }


def build_metadata(
    company: str, date: str, nodes: dict[str, dict], next_disclosure_date: str | None = None
) -> dict:
    """主页 metadata: verdict = 行动档位人话(决策 verdict), 另带质地字段与预约披露日。"""
    decision = nodes["decision"]
    meta = {
        "company": company,
        "date": date,
        "action_gear": decision["action_gear"],
        "verdict_plain": decision["verdict"],
        "quality_field": quality_field(nodes["quality"]["verdict"]),
    }
    if next_disclosure_date:
        meta["next_disclosure_date"] = next_disclosure_date
    return meta


# ---------------------------------------------------------------- 变化区块(增量复查)

def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


# 翻转比对只看 verdict 首短语(判定态度), 破折号/顿号后的论据措辞不算——
# 重评写手必然重写论据, 全文比对会把「买完完美未来(数字更新)」也判成翻转(research/03 场景 A 反例)。
_VERDICT_PHRASE_SPLIT = re.compile(r"[———,,;;::((\(·、]")


def _verdict_phrase(verdict: str) -> str:
    return _norm(_VERDICT_PHRASE_SPLIT.split(str(verdict or ""), 1)[0]) or _norm(verdict)


# 子判定比对只认判定符号(质地的 ✓/⚠️/✗ 可机检); 状态/赔率/路径的子判定是自由文本,
# 重评必然重写措辞, 拿文本比对等于把「数字更新」也判成翻转。
_JUDGMENT_SYMBOLS = {"✓", "⚠️", "✗"}


def _sub_symbol_changes(before: dict, after: dict) -> list[str]:
    old = {s["question"]: s["judgment"] for s in before.get("sub_verdicts") or []}
    new = {s["question"]: s["judgment"] for s in after.get("sub_verdicts") or []}
    return [
        f"{q} {old[q]}→{j}"
        for q, j in new.items()
        if q in old and old[q] != j
        and old[q] in _JUDGMENT_SYMBOLS and j in _JUDGMENT_SYMBOLS
    ]


def _flip_kind(before: dict | None, after: dict | None) -> str | None:
    """翻转种类: "verdict"=判定语(首短语)真变了 / "sub"=判定语没变但子判定符变了 / None=没翻。

    两种都算翻转(进 flipped_nodes、可触发硬规则 2), 但对读者的措辞不同——
    「部分好→部分好」喊"翻转"是自相矛盾(delivery 评审票 09 Round 2), 子判定级的要说"子判定变化"。
    """
    if not before or not after:
        return None
    if _verdict_phrase(before.get("verdict")) != _verdict_phrase(after.get("verdict")):
        return "verdict"
    if _sub_symbol_changes(before, after):
        return "sub"
    return None


def _node_flipped(before: dict | None, after: dict | None) -> bool:
    """判定翻转 = verdict 首短语变化, 或任一子判定的判定符变化(质地 ✓/⚠️/✗ 可机检)。"""
    return _flip_kind(before, after) is not None


def gear_distance(before: str, after: str) -> int:
    """行动档位跨了几档(按进攻/观望/撤退三带算; 未知档位按 0 处理)。"""
    return abs(GEAR_BANDS.get(after, 0) - GEAR_BANDS.get(before, 0))


# 🟢/ℹ️ 是绿灯与信息更新, 不许借「红旗」名头(计数与条目都要分组, 文案与统计必须同源)
SOFT_FLAG_LEVELS = ("🟢", "ℹ️")


def flag_change_is_soft(item: dict) -> bool:
    level = item.get("level") or ""
    if level:
        return level in SOFT_FLAG_LEVELS
    return any(lv in (item.get("note") or "") for lv in SOFT_FLAG_LEVELS)


def soft_flag_label(item: dict) -> str:
    """🟢 = 绿灯更新, ℹ️ = 信息更新 —— 两种分开叫(立讯 11-13 终检:北向减持 ℹ️ 被标成「绿灯更新」)。"""
    level = item.get("level") or ("🟢" if "🟢" in (item.get("note") or "") else "ℹ️")
    return "绿灯更新" if level == "🟢" else "信息更新"


# ---------------------------------------------------------------- 较上版变化: 读者面短说法

# 判定句的「取值域」段 = 第一个不在括号里的破折号 / 逗号 / 分号之前(与 build_html 决断卡分行同一口径)
_VERDICT_HEAD_STOPS = "—,，;；"
_HEAD_PAREN_OPEN, _HEAD_PAREN_CLOSE = "(（【[", ")）】]"

# 取值域里的内部词 → 人话(链手册 §4.1「② 在变好吗的四档」那一行)。
# 「仅注意力」是手册里的分级名(好消息只引来关注、还没有实锤), 读者面不出现;按长串优先替换。
VERDICT_HEAD_PLAIN = (
    ("变好但仅注意力·未确认", "在变好,但还没实锤"),
    ("变好但仅注意力", "在变好,但还没实锤"),
    ("变好但未确认", "在变好,但还没实锤"),
    ("变好+证据确认", "在变好,有实锤"),
    ("↑未确认", "↑在变好,但还没实锤"),
    ("↑确认", "↑在变好,有实锤"),
)
# 括注里带这些内部词就整段不要(「高尾险·扛不住(高信仰 5/5)」→「高尾险·扛不住」)
_HEAD_INTERNAL = re.compile(r"[(（][^()（）]*(?:高信仰|信仰体检|注意力|λ|三元组)[^()（）]*[)）]")
# 取值域后面跟的长括注是理由不是取值(东山 08-24:「高尾险·不可承受(上版 9 条证伪 0 触发,但地板只兜现价 3.7%,…)」);
# 短括注是取值的一部分(「便宜(有余地)」), 留着
_HEAD_LONG_ASIDE = re.compile(r"\s*[(（][^()（）]{9,}[)）]")


def verdict_head(text: str) -> str:
    """判定句 → 取值域那一段(破折号/逗号/分号之前;括号里的分隔符不算)。"""
    text = str(text or "").strip()
    depth = 0
    for i, ch in enumerate(text):
        if ch in _HEAD_PAREN_OPEN:
            depth += 1
        elif ch in _HEAD_PAREN_CLOSE:
            depth = max(depth - 1, 0)
        elif depth == 0 and ch in _VERDICT_HEAD_STOPS:
            return text[:i].strip() or text
    return text


def plain_verdict_head(text: str) -> str:
    """较上版变化的上版/本版两列:只放取值域段, 并按人话词典换掉内部词 —— 两列同一处理, 口径对称。

    上版 YAML 的判定原文整句贴进来, 会带出「高信仰体检 6/7」「仅注意力」这类手册词(立讯 11-13 终检);
    整句的理由本来就在本版的决断卡与各章里, 这张表只回答「从哪一档变到哪一档」。
    """
    head = _HEAD_LONG_ASIDE.sub("", _HEAD_INTERNAL.sub("", verdict_head(text))).strip()
    for old, new in VERDICT_HEAD_PLAIN:
        if old in head:
            return head.replace(old, new)
    return head


# 证伪条件的短名:首句只列「哪几条」, 全文在下面的逐条清单里
_FALS_PERIOD_LEAD = re.compile(r"^\s*([^:：]{1,14})[:：]\s*")
_FALS_PERIOD_HINT = re.compile(r"\d|年报|季报|中报|年末|半年|全年")
# 括注 / 逗号 / 分号 / 句号处收刀;夹在两个数字之间的逗号是千分位(「1,000 亿」), 不算
_FALS_STOP = re.compile(r"[(（，;；。]|(?<!\d),|,(?!\d)")
FALS_SHORT_MAX = 26


def falsification_short(condition: str) -> str:
    """证伪条件 → 短名:去掉开头的期别前缀(「2026 年报:」), 截到第一个括注或逗号之前。

    立讯 11-13 首句把整条「2026 年报:全年经营现金流净额 <100 亿(FY2025 为 173.25 亿), 或三季报…」
    原样塞进去(终检判为表述 FIX)。短名只给首句用, 逐条清单照旧列全文。
    """
    text = str(condition or "").strip()
    m = _FALS_PERIOD_LEAD.match(text)
    if m and _FALS_PERIOD_HINT.search(m.group(1)) and len(text) > m.end():
        text = text[m.end():]
    stop = next((m for m in _FALS_STOP.finditer(text) if m.start() > 0), None)
    if stop:
        text = text[:stop.start()]
    text = text.strip()
    if len(text) > FALS_SHORT_MAX:
        spaces = [i for i, ch in enumerate(text[:FALS_SHORT_MAX]) if ch == " "]
        text = (text[:spaces[-1]] if spaces and spaces[-1] > 6 else text[:FALS_SHORT_MAX]).rstrip() + "…"
    return text


# 提名红旗 id 尾巴上的期别后缀(-2026h1 / -2026q3 / -fy2025 / -20261110): 写手给**延续性**风险换期别时
# 只换这一截(立讯 11-13: state-growth-quality-2026h1 → state-growth-quality-2026q3)。去掉后相同 = 同一风险族。
_PERIOD_SUFFIX = re.compile(
    r"[-_](?:fy)?(?:19|20)\d{2}(?:[-_]?(?:q[1-4]|h[12]|fy|a|\d{2}(?:\d{2})?))?$", re.IGNORECASE
)


def flag_family(flag_id: str) -> str:
    """提名红旗的「风险族」= id 去掉期别后缀(可叠加, 如 -2026-h1)。"""
    base = str(flag_id or "")
    while True:
        new = _PERIOD_SUFFIX.sub("", base)
        if new == base or not new:
            return base
        base = new


def _flag_label(flag: dict) -> str:
    # 读者面文字: 脚本条用人话标题(display_title), 不印「Z=2.837」这类规则名
    return flag.get("display_title") or flag.get("title") or flag.get("id", "")


def _flag_changes(before: list[dict], after: list[dict]) -> list[dict]:
    """红旗按 id diff: 新增 / 解除 / 级别变化 / **延续**(v8.15 D4)。

    延续 = 同一节点、同为提名、id 去掉期别后缀后相同(flag_family)—— 写手给持续存在的风险换了期别,
    旧 diff 会报成「解除一条 + 新增一条」, 读者以为那条风险解除了。现在合成一条 change="replaced",
    `replaces` 指向上版 id。脚本红旗的 id 不含期别(只由 framework + signal 骨架决定), 不参与这条。
    """
    old = {f["id"]: f for f in before}
    new = {f["id"]: f for f in after}
    added = [fid for fid in new if fid not in old]
    gone = [fid for fid in old if fid not in new]

    successor: dict[str, str] = {}             # 新 id → 上版 id
    claimed: set[str] = set()
    for fid in added:
        flag = new[fid]
        if flag.get("source") != "nomination":
            continue
        fam = flag_family(fid)
        for oid in gone:
            prev = old[oid]
            if (oid not in claimed and prev.get("source") == "nomination"
                    and prev.get("node") == flag.get("node") and flag_family(oid) == fam):
                successor[fid] = oid
                claimed.add(oid)
                break

    changes = []
    for fid, flag in new.items():
        if fid in successor:
            prev = old[successor[fid]]
            level_txt = (f";级别 {prev['level']}→{flag['level']}"
                         if prev.get("level") != flag.get("level") else "")
            changes.append({
                "id": fid, "change": "replaced", "replaces": prev["id"], "level": flag["level"],
                "note": f"{flag['level']} {_flag_label(flag)}(接替上版「{_flag_label(prev)}」{level_txt})",
            })
        elif fid not in old:
            changes.append({"id": fid, "change": "triggered", "level": flag["level"],
                            "note": f"{flag['level']} {_flag_label(flag)}"})
        elif old[fid]["level"] != flag["level"]:
            changes.append({
                "id": fid,
                "change": "level_changed",
                "level": flag["level"],
                "note": f"{_flag_label(flag)}:{old[fid]['level']}→{flag['level']}",
            })
    for fid, flag in old.items():
        if fid not in new and fid not in claimed:
            changes.append({"id": fid, "change": "resolved", "level": flag["level"],
                            "note": f"{flag['level']} {_flag_label(flag)}"})
    return changes


def _cond_key(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


# 证伪条件匹配:写手重评时常顺手改措辞(补一个数、换个标点), 逐字比对会把上版已触发的那条
# 当成「本轮新触发」(和④正文「本轮新亮两条、累计三条」对不上)。先归一空白逐字比, 再退到高相似度。
_COND_SIMILARITY = 0.9


def _match_condition(cond: str, prev: dict[str, bool]) -> bool | None:
    key = _cond_key(cond)
    if key in prev:
        return prev[key]
    best, best_ratio = None, 0.0
    for k, was in prev.items():
        ratio = difflib.SequenceMatcher(None, key, k).ratio()
        if ratio > best_ratio:
            best, best_ratio = was, ratio
    return best if best_ratio >= _COND_SIMILARITY else None


def _falsification_changes(before: dict | None, after: dict | None) -> list[dict]:
    if not before or not after:
        return []
    old = {_cond_key(f["condition"]): bool(f.get("triggered")) for f in before.get("falsifications") or []}
    out = []
    for item in after.get("falsifications") or []:
        cond, now = item["condition"], bool(item.get("triggered"))
        was = _match_condition(cond, old)
        if now and not was:
            out.append({"condition": cond, "change": "triggered"})
        elif was and not now:
            out.append({"condition": cond, "change": "cleared"})
    return out


def _falsification_tally(after: dict | None, fals_changes: list[dict]) -> dict:
    """证伪口径与④对齐:本轮新触发 vs 累计已触发(上版已触发、本版仍触发的不算新增)。"""
    total = sum(1 for f in (after or {}).get("falsifications") or [] if f.get("triggered"))
    new = sum(1 for c in fals_changes if c["change"] == "triggered")
    return {"triggered_total": total, "triggered_new": new, "carried_over": max(total - new, 0)}


def _with_period_labels(delta: dict) -> dict:
    """指标 delta 补人话期别(triage 带了 before_period / after_period 才有); 期长不同给一句提示。"""
    out = dict(delta)
    basis = delta.get("period_basis") or "report"
    if delta.get("before_period"):
        out["before_label"] = periods.period_label(delta["before_period"], basis)
    if delta.get("after_period"):
        out["after_label"] = periods.period_label(delta["after_period"], basis)
    note = periods.period_note(delta.get("before_period"), delta.get("after_period"), basis)
    if note:
        out["period_note"] = note
    return out


def build_change_block(
    prev_nodes: dict[str, dict],
    nodes: dict[str, dict],
    prev_flags: list[dict],
    flags: list[dict],
    metric_deltas: list[dict] | None = None,
) -> dict:
    """「较上版变化」区块:新旧 YAML 块 diff, 首句人话答「判断变了没」。

    硬规则 2(票 03/09):质地判定翻转 或 档位跨两档 → advised=True(照常产出, 首页明示建议全量)。
    """
    gear_before = prev_nodes["decision"]["action_gear"]
    gear_after = nodes["decision"]["action_gear"]
    flip_kinds = {
        n: kind for n in rf.NODES
        if (kind := _flip_kind(prev_nodes.get(n), nodes.get(n)))
    }
    flipped = [n for n in rf.NODES if n in flip_kinds]
    flag_changes = _flag_changes(prev_flags, flags)
    fals_changes = _falsification_changes(prev_nodes.get("path"), nodes.get("path"))
    tally = _falsification_tally(nodes.get("path"), fals_changes)

    reasons = []
    if flip_kinds.get("quality") == "verdict":
        reasons.append(
            f"质地判定翻转({prev_nodes['quality']['verdict']} → {nodes['quality']['verdict']})"
        )
    elif flip_kinds.get("quality") == "sub":
        details = "、".join(_sub_symbol_changes(prev_nodes["quality"], nodes["quality"]))
        reasons.append(f"质地子判定变化(判定语未变:{details})")
    distance = gear_distance(gear_before, gear_after)
    if distance >= 2:
        reasons.append(f"行动档位跨两档({gear_plain(gear_before)} → {gear_plain(gear_after)})")
    advice = {
        "advised": bool(reasons),
        "reason": ";".join(reasons) + ",建议全量重跑重锚" if reasons else None,
    }

    return {
        "alpha_summary": _alpha_summary(
            gear_before, gear_after, flip_kinds, flag_changes, fals_changes, nodes, tally, prev_nodes
        ),
        "gear_before": gear_before,
        "gear_after": gear_after,
        "triad_before": dict(prev_nodes["decision"]["triad"]),
        "triad_after": dict(nodes["decision"]["triad"]),
        "flipped_nodes": flipped,
        "flip_kinds": flip_kinds,
        "red_flag_changes": flag_changes,
        "falsification_changes": fals_changes,
        "falsification_tally": tally,
        "metric_deltas": [_with_period_labels(d) for d in metric_deltas or []],
        "full_rerun_advice": advice,
    }


def _alpha_summary(gear_before, gear_after, flip_kinds, flag_changes, fals_changes, nodes,
                   tally: dict | None = None, prev_nodes: dict | None = None) -> str:
    """首句人话答「判断变了没」——只陈述机器测得的变化, 不自产解释, **只写要点**。

    (字段名 alpha_summary 是契约名, 读者看不到; 首句不出现「阿尔法 / 三元组 / 节点」这类流水线词, v8.15 D3)
    顺序 = 读者最先要知道的:档位 → 哪章判定从哪档到哪档 → 本轮新亮了哪几条证伪(短名) → 红旗增减计数。
    立讯 11-13 终检:旧首句把整条证伪原文塞进来(一条就 70 字), 判定翻转只说「②状态判定翻转」不说翻到哪;
    现在证伪只列短名(falsification_short), 判定写取值域两端(plain_verdict_head), 全文都在下面的逐条清单里。
    措辞纪律: 「翻转」只留给判定语真变的章; 判定语未变、子判定符变的说「子判定变化」;
    🟢 叫绿灯、ℹ️ 叫信息更新, 都不借「红旗」名头(文案与折叠组计数同源, 见 flag_change_is_soft);
    证伪分「本轮新触发」与「累计」, 上版已触发的不算本轮新增(与④口径一致)。
    """
    tally = tally or _falsification_tally(nodes.get("path"), fals_changes)
    triggered = [c for c in fals_changes if c["change"] == "triggered"]
    hard = [c for c in flag_changes if not flag_change_is_soft(c)]
    soft = [c for c in flag_changes if flag_change_is_soft(c)]
    verdict_flips = [n for n in rf.NODES if flip_kinds.get(n) == "verdict"]
    sub_flips = [n for n in rf.NODES if flip_kinds.get(n) == "sub"]
    parts = []
    if gear_before != gear_after:
        parts.append(f"行动档位 {gear_plain(gear_before)}→{gear_plain(gear_after)}")
    for n in verdict_flips:
        if prev_nodes and prev_nodes.get(n):
            parts.append(f"{NODE_LABELS[n]} {plain_verdict_head(prev_nodes[n].get('verdict'))}"
                         f"→{plain_verdict_head(nodes[n].get('verdict'))}")
        else:
            parts.append(f"{NODE_LABELS[n]}判定翻转")
    if sub_flips:
        parts.append("、".join(NODE_LABELS[n] for n in sub_flips) + "子判定变化(判定语未变)")
    if triggered:
        names = "、".join(falsification_short(c["condition"]) for c in triggered)
        text = f"证伪本轮新触发 {len(triggered)} 条({names})"
        if tally["triggered_total"] > len(triggered):
            text += f",累计已触发 {tally['triggered_total']} 条"
        parts.append(text)
    flag_bits = [
        (label, sum(1 for c in hard if c["change"] == kind))
        for kind, label in (("triggered", "新增"), ("resolved", "解除"),
                            ("replaced", "延续上版"), ("level_changed", "级别变化"))
    ]
    if any(n for _, n in flag_bits):
        parts.append("红旗" + "、".join(f"{label} {n} 条" for label, n in flag_bits if n))
    greens = sum(1 for c in soft if soft_flag_label(c) == "绿灯更新")
    if greens:
        parts.append(f"绿灯 {greens} 条")
    if len(soft) - greens:
        parts.append(f"信息更新 {len(soft) - greens} 条")
    if not parts:
        carried = (f",上版已触发的 {tally['triggered_total']} 条证伪仍未解除"
                   if tally["triggered_total"] else "")
        return (
            f"判断没变:行动档位维持「{gear_plain(gear_after)}」,各章判定都没翻,"
            f"没有新触发的证伪{carried},红旗没有增减(⑤的判定:{nodes['decision']['verdict']})"
        )
    return "判断变了:" + ";".join(parts)


# ---------------------------------------------------------------- 总装

def build_assembly(
    company: str,
    date: str,
    nodes: dict[str, dict],
    script_flags: list[dict],
    prev_nodes: dict[str, dict] | None = None,
    prev_script_flags: list[dict] | None = None,
    metric_deltas: list[dict] | None = None,
    appendices: list[dict] | None = None,
    next_disclosure_date: str | None = None,
) -> dict:
    """五个节点块 + 脚本红旗 → 装配产物(过 assembly.schema.json)。"""
    flags = rf.merge(script_flags, rf.collect_nominations(nodes))
    flag_errs = rf.validate_flags(flags)
    if flag_errs:
        raise AssemblyError("附录D 红旗清单不合契约:\n  - " + "\n  - ".join(flag_errs))

    panel = build_panel(nodes, flags)
    product = {
        "verdict_card": build_verdict_card(nodes),
        "panel": panel,
        "top3": rf.top3(flags),
        "metadata": build_metadata(company, date, nodes, next_disclosure_date),
        "red_flags": flags,
        "red_mark_map": rf.red_mark_map(flags, panel["indicators"]),
    }
    intro = nodes["decision"].get("front_page_intro")
    if intro:
        product["front_page_intro"] = intro          # 首页唯一人工位: decision-writer 的 3-5 句导读
    if appendices is not None:
        product["appendices"] = appendices
    if prev_nodes:
        prev_flags = rf.merge(list(prev_script_flags or []), rf.collect_nominations(prev_nodes))
        product["change_block"] = build_change_block(
            prev_nodes, nodes, prev_flags, flags, metric_deltas
        )

    errs = verdict_block.validate(product, "assembly")
    if errs:
        raise AssemblyError("装配产物不过 schema:\n  - " + "\n  - ".join(errs))
    return product
