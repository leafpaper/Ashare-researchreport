# Phase 6: 质量环与发布 (v8.0 — 机器门控 + 两 reviewer 并行 + 出片发布)

> **谁读这份**:**主 agent**。本文件讲「怎么把装配好的报告验收、修正、出片、发布」,不讲报告怎么写。
>
> **🧭 你在这里**:[SKILL.md 协调器](../SKILL.md) → [Phase 3 判断链写作与装配](phase3-node-writing.md) → **Phase 6 质量环与发布**(终点)
>
> **接收自**:`{run_dir}/nodes/node-*.md`(五块)+ `{run_dir}/assembly/assembly.json` + `{run_dir}/{company}-analysis-{date}.md`
> **输出**:`*.html` + `{run_dir}/phase6-review-log.md` + GitHub Pages(leafpaper/Inves-Report)
> **质量环规模**:机器门控(`lint_v8`)+ 2 个 LLM reviewer 并行 + 修正 agent 落地 FIX + **PASS 线 = 判断类 FIX 归零**
> (表述类只落地不重审;3 轮上限)+ 终检(HTML 走查一次)。
>
> **v8.11 为什么这样改(成本账)**:金山办公一份报告 ≈ $74,其中主会话 $43、子代理 $31;子代理 25 个里 19 个是评审与修正。
> 三份报告 Round 3 全部仍 FAIL —— reviewer 每轮都还挑得出表述项,按「双 PASS」判定永远收敛不了,「3 轮上限」实际是必跑 3 轮。
> 主 agent 自己 Edit 了 21 次节点正文,每次都在几十万 token 的上下文上叠一轮。
> 改法只动编排:**主 agent 不动手、表述类不重审、HTML 只在终检读一次**;reviewer 读什么一个字没减(附录C 技术面越权那条就是从装配后的报告里抓出来的)。
>
> **v7 → v8 变了什么**:9 章节骨架比对 / 章节字数下限 / artifact 覆盖率 / 20 项 LLM 清单 / 3 个 reviewer
> 全部删除——它们校验的是「四套机制互抄一致」和「写够字数」,v8 把复述层删了、把长度改成上限,
> 那套校验对 v8 报告只会误判。取而代之:机器查结构性质(`scripts/lint_v8.py`),LLM 查判断链逻辑与可读性。

---

## 角色定义

你有两个身份:

**身份 A — 质量环调度员**:跑机器门控、派两个 reviewer、按 FIX 分诊结果派修正 agent。
你**不改判断、也不改措辞**——节点 md(YAML 块与正文)永远只有写手能动;你唯一亲手改的是 `assets/html/` 模板与脚本(那是 skill 代码)。

**身份 B — 发布经理**:把过关的报告出成 v8 仪表盘 HTML,推到 GitHub Pages,更新主页卡片。

---

## 前置条件

| 项 | 检查 |
|---|---|
| 五个节点块 | `{run_dir}/nodes/node-{quality,state,odds,path,decision}.md`,Phase 3 逐波 `verdict_block` 已过 |
| 装配产物 | `{run_dir}/assembly/assembly.json` + `{run_dir}/{company}-analysis-{date}.md`(`assemble_report_v8` 退出 0) |
| 采集产物 | `{artifacts_dir}/audit_report.json`(红旗闭环要它)+ 附录 A/B/C/E 的挂载源 |
| 往返目录 | `{run_dir}/reviewer_responses/`(`init_run` 已建) |

---

## Part A: 质量环

### Step 0(强制门控):机器规则 — 任一 fail 直接 BLOCK

```
{PYBIN} -m scripts.lint_v8 --run-dir {run_dir} --artifacts-dir {artifacts_dir}
# 退出码 0 = fail 项全过(warn 不阻断)→ 进 Step 1
# 退出码 1 = BLOCK,按 FAIL 项修完再来,不许让 reviewer「绕过」机器规则
# 退出码 2 = run 目录不完整(缺 nodes/),回 Phase 3
```

**为什么先跑它**:LLM 自审看不见自己的结构性错误(写者=审者)。确定性的 schema 校验 + 重算比对 + grep
能挡住的,不该花 LLM 的注意力。

| # | 规则 | 级别 | 判什么 |
|:-:|---|:--:|---|
| R1 | 五块 schema 校验 | fail | 五个节点 YAML 块逐块过 `scripts/schemas/` |
| R2 | 红旗闭环 | fail | Top3 与红旗清单**重算一致**(装配没重跑也在这里现形);🔴 致命红旗必须在归属节点叙述过 |
| R3 | 数字唯一 home | fail | 同一数字跨章出现时,异地那处必须带出处引用(①-⑤ / 附录A-E) |
| R4 | 章预算 | warn | 70/60/70/60/50 行上限 + 主体合计 400 行(**没有下限**——下沉附录是规定动作) |
| R5 | 合理价区间 | fail | 同向标记必填、不同向必写分歧原因、两端不倒置、verdict 与现价方向不自相矛盾 |
| R6 | 外链引用 | fail | 正文禁「详见 xxx.md」「[x](x.md)」(指向本报告附录的 `#锚点` 合法) |
| R7 | 决策字段 + 封顶 | fail | 决策块九个必填字段;**有 🔴 → 行动档位强制「回避」且 `gear_cap.triggered=true`** |
| R8 | 越权发声 | fail | 仓位 / 行动档位 / 买卖建议只能出现在⑤(写明「归⑤/见⑤」的引用行豁免) |
| R9 | 无记忆性反例 | fail | 禁「跌久了该涨 / 估值压久了该修复」当买入理由 |
| R10 | 报告与节点同步 | fail | 主报告五章正文 = 节点 md 正文(改完没重装配 = 脱节) |
| R2w | 🟠 高级红旗归家 | warn | 🟠 未在归属节点叙述——提示补一句,不阻断 |
| R11 | 散文密度 | warn | 四条形状判据(期间对比 / 编号项 / 核销清单 / 逐项短并列)+ 正向断言 + 图上文字;票 12 多样本标定后精确率 75%,**定位器不是判官** |
| R12 | 推导闭合 | fail + warn | ③估值推导十条算术闭合 + 三张表真渲染 |
| R13 | 证伪清单同源 | fail | ⑤ 每条退出线在 ④ 的证伪清单里找得到源(没有 = 孤儿条) |
| R14 | 机器块无过程注释 | warn | 节点 YAML 里不留「正在/待定稿/暂按」这类会过期的时态词 |
| R15 | 三元组同源 | fail | ⑤ triad 三格与②③④ verdict 逐字相等 |
| R16 | ③锚引用过期 | fail | 别的节点抄的「X~Y 元」只有一端对得上③锚,或「合理价低端/高端 N 元」与③不符 |
| R17 | 已兑现倍数不超增长退出 | fail | 按**自身历史倍数**给已兑现利润定价时,不得高于基准情景的退出倍数(按同业倍数定价的分部不判——当期同业倍数与五年后的终值倍数不可比) |
| R18 | 红旗清单与审计同步 | fail | 写手读的 `red_flags.json` 必须覆盖 `audit_report.json` 现有的每条脚本红旗(audit 重跑后忘了重出 → 写手面板引不到 id,而装配从 audit 重算所以成品不漏、没人会发现) |

**修复指引**:

| 症状 | 怎么修 |
|---|---|
| R1 / R2(🔴 未归家)/ R5 / R7 | **判断问题** → fresh-restart 对应写手(prompt 注入 lint 报错原文);主 agent 不许手改 YAML 块 |
| R2(Top3 漂移 / 清单不一致)/ R10 | 重跑 `assemble_report_v8`——十有八九是改了节点却忘了重装配 |
| R3 / R6 / R8 / R9 | 多半是措辞 → **按节点分组、并行派修正 agent**(scope=仅表述,prompt 粘 lint 报错原文),改完重跑装配。主 agent 不 Edit 节点 md |
| R4 warn | 看能不能把表格/时序下沉附录;下沉不了就留着,不阻断 |
| R13 / R15 / R16 | 上游节点改了、下游抄本没跟上 → SendMessage 让下游写手**照节点文件**重抄(YAML 也归写手改),然后重装配 |
| R18 | 重出红旗清单后让引不到 id 的写手补面板:`python -m scripts.red_flags --audit-json {artifacts_dir}/audit_report.json --out {artifacts_dir}/red_flags.json`(重跑过 `financial_audit` 就要跟着跑这一条) |

### Step 1: 两个 reviewer 并行(循环轮只审 md,不出片、不读 HTML)

```python
Agent(subagent_type="reviewer-logic", run_in_background=True, description="维度1 判断链逻辑",
      prompt=f"""评审判断链逻辑(第 {round} 轮)。
run_dir     = {run_dir}
artifacts_dir = {artifacts_dir}
report_path = {run_dir}/{company}-analysis-{date}.md
lint_v8 已全绿(schema/红旗闭环/数字home/合理价区间/封顶/越权/外链/同步都查过了),别重复机器规则。
{round ≥ 2 时:上轮 FIX 列表在 {run_dir}/reviewer_responses/round_{round-1}_merged_fix.md,已应用;先逐条核销,再全文过一遍。}
按 agents/reviewer-logic.md 的 5 项检查出判定与 FIX。判定只由判断类 FIX 决定;表述类照列,不算 FAIL。
响应只回评审结论,不要回放文件内容。""")

Agent(subagent_type="reviewer-delivery", run_in_background=True, description="维度2 可读性与交付",
      prompt=f"""评审可读性与交付(第 {round} 轮,循环轮模式:只审 md,本轮没有 HTML)。run_dir / artifacts_dir / report_path 同上。
{round ≥ 2 时:上轮 FIX 已应用,列表同上;先核销再过一遍。}
按 agents/reviewer-delivery.md 的 2.1 结论先行 + 2.2 全说人话出判定与 FIX;2.3 走查清单留给终检。
判定只由判断类 FIX(含 front)决定;表述类照列,不算 FAIL。""")
```

两个都 `run_in_background=True`,等系统的 task-notification 收齐两份响应。
**循环轮不出片**:HTML 只在 Step 4 终检时出一次、读一次(版式走查不随文字修改变化,每轮都读是纯浪费;
金山办公实测 reviewer 在循环里分页读了 10 万字 HTML,没有一条 FIX 是 md 里看不出来的)。

**收到响应后**:两份原文 Write 到

```
{run_dir}/reviewer_responses/round_{N}_logic.md
{run_dir}/reviewer_responses/round_{N}_delivery.md
```

(不依赖 context 记忆——修正循环是 fresh-restart,状态只能落文件。)

### Step 2: 合并判定 + FIX 分诊

```
{PYBIN} -m scripts.review_loop --run-dir {run_dir} --round {N}
```

输出 JSON(主 agent **只看这个**,不读 reviewer 响应全文):

```json
{
  "overall_pass": false,
  "needs_new_round": true,
  "next_step": "落地全部 FIX → 重装配 + lint → Round+1",
  "judgments": {"logic": "FAIL", "delivery": "FAIL"},
  "fix_count": 4,
  "fix_by_node": {"odds": 1, "state": 1, "front": 1, "delivery": 1},
  "fix_by_kind": {"判断": 2, "表述": 2},
  "judgment_fixes": 2,
  "restart_writers": ["node-odds", "node-state", "decision-writer"],
  "restart_scope": {"node-odds": "判断+表述", "node-state": "仅表述", "decision-writer": "判断+表述"},
  "delivery_fixes": 1,
  "fix_list_path": "…/round_1_merged_fix.md",
  "diff_repeat": false
}
```

**PASS 线 = `judgment_fixes == 0`**(判断类 + front 归零)。reviewer 自报的 PASS/FAIL 只留档,不当判定用;
表述类 FIX 照单落地,但**不触发新一轮**。两种情况 fail-closed 不放行:判定认不出(UNKNOWN)、reviewer 说 FAIL 却一条可解析 FIX 都没给。

| JSON | 主 agent 的动作 |
|---|---|
| `diff_repeat: true` | → **转人工**(两轮之间节点 md 一个字没变 = 改回原状的对抗) |
| `overall_pass: true` | → Step 3 落地表述类 FIX(若有)→ 重装配 + lint → **Step 4 终检** |
| `needs_new_round: true` 且 `round < 3` | → Step 3 落地全部 FIX → 重装配 + lint → Round+1 |
| `needs_new_round: true` 且 `round == 3` | → **转人工**,附累计 FIX |

`next_step` 字段已把上表算好,照它走。

### Step 3: 落地 FIX(修正 agent,主 agent 不动手)

**为什么主 agent 不亲自改**:主会话上下文是修正 agent 的十倍(金山实测平均 25 万 vs 2-5 万 token),
同一处措辞改动由主 agent 做贵十倍,而且它改的越多、后面每一次调用越贵。
修正 agent 拿到的信息**一个字不少于主 agent 手改时手里的**:FIX 原文、两份 reviewer 响应全文路径、lint 报错原文全在文件里,
prompt 里点名即可。

1. **`restart_writers` 里每个写手各派一个修正 agent,全部并行 `run_in_background=True`**,prompt 模板:

   ```python
   Agent(subagent_type="{agent}", run_in_background=True, description="修正 {节点}",
         prompt=f"""修正{节点}节点(第 {round} 轮 FIX,这是重跑:只看当前文件状态,不要假设你记得任何上下文)。
   run_dir = {run_dir} · artifacts_dir = {artifacts_dir} · PYBIN = {PYBIN}
   scope = {restart_scope[agent]}   ← 「仅表述」= 只改正文,顶部 YAML 块一个字不动;「判断+表述」= YAML 与正文都可改
   本轮开给你的 FIX(原文):
   {该节点在 round_{round}_merged_fix.md 里的那几行}
   reviewer 完整理由见 {run_dir}/reviewer_responses/round_{round}_logic.md 与 round_{round}_delivery.md(只读与你相关的段)。
   改完自跑 {PYBIN} -m scripts.verdict_block --schema {schema} --file {run_dir}/nodes/node-{node}.md,退出 0 才算完。
   完成报告只回:判定 / 改了哪几条 FIX / 没改的说明为什么。""")
   ```

   lint 措辞类(R3 / R6 / R8 / R9)报红也走同一模板,把 lint 报错原文粘进 FIX 位置。
2. **交付类 FIX**(`delivery_fixes > 0`)→ 主 agent 改 `assets/html/report-v8.{html,css}` 或渲染逻辑(skill 代码,不是报告内容),不惊动写手。
3. **每个修正 agent 回来后主 agent 复核** `verdict_block` 退出码(不信自证),然后**重跑两条命令,缺一不可**:

   ```
   {PYBIN} -m scripts.assemble_report_v8 --run-dir {run_dir} --company {company} --date {date} \
       --ticker {ticker} --artifacts-dir {artifacts_dir}
   {PYBIN} -m scripts.lint_v8 --run-dir {run_dir} --artifacts-dir {artifacts_dir}
   ```

4. 按 `next_step`:有判断类 → Round+1(重新并行两个 reviewer,prompt 注明「上轮 FIX 已应用」);
   没有 → Step 4 终检。

每轮写一行 `main-log.md`:`- {ts} reviewer Round N judgment_fixes=K / 表述 M,next={next_step}`。

### Step 4: 终检(HTML 走查一次,不进循环)

质量环收敛(`overall_pass`)且最后一批 FIX 已落地、lint 全绿之后:

1. 出片:`{PYBIN} -m scripts.build_html --company {company} --run-dir {run_dir}`(退出 0)。
2. 派**一个** reviewer-delivery,终检模式:

   ```python
   Agent(subagent_type="reviewer-delivery", run_in_background=False, description="终检 HTML 走查",
         prompt=f"""终检模式(不是循环轮)。run_dir / artifacts_dir / report_path 同前;
   html_path = {run_dir}/{company}-analysis-{date}.html
   只做 agents/reviewer-delivery.md 的 2.3 走查清单 + 2.2f 形状复核;不再评判断、不开判断类 FIX。
   只允许开 [FIX-delivery-表述] 与 [FIX-{node}-表述]。响应写到 {run_dir}/reviewer_responses/final_delivery.md 的格式。""")
   ```

3. 响应落 `{run_dir}/reviewer_responses/final_delivery.md`。有 FIX → 按 Step 3 落地(表述类派修正 agent、交付类主 agent 改模板)
   → 重装配 + lint → 重新 `build_html`。**终检只跑一次**,落地后不再派 reviewer(lint 与 build_html 自检兜底)。
4. → Part B / Part C。

---

## Part B: HTML 出片

```
{PYBIN} -m scripts.build_html --company {company} --run-dir {run_dir}
```

脚本会:**先跑一次 `lint_v8`(fail 阻断)** → 读 `assembly/assembly.json`(结构化件)+ 主报告 md(正文)→
按 `assets/html/report-v8.{html,css}` 渲染 B 仪表盘版式 → 红标三通道与附录D 反查 → 成品自检
(决断卡五行 / Top3 / 面板指标 / 五章 / 附录一个都不能少)。

退出码 0 = 出片成功;2 = 自检未命中(stderr 列出缺了什么);1 = lint 未过或渲染失败。

**绝对禁止**:手写 HTML、凭记忆重写 CSS、自创组件 class。模板是唯一真相源,
版式规范见 `references/html-template-guide.md`。

---

## Part C: GitHub Pages 发布(主页动态联动)

**目标仓库**:`leafpaper/Inves-Report`。`$INVES_REPORT_DIR` 为环境变量(Mac/Linux 如 `/tmp/Inves-Report`,
Windows 如 `C:\Inves-Report`);下面写法为 Mac/Linux,Windows 把 `mkdir -p`→`New-Item -ItemType Directory -Force`、
`cp`→`Copy-Item`、`$INVES_REPORT_DIR`→`$env:INVES_REPORT_DIR`,`cd` / `git` 两边通用。

```
1. cd $INVES_REPORT_DIR && git pull origin main       # 不存在则先 git clone

2. mkdir -p $INVES_REPORT_DIR/reports/{CompanySlug}_{CompanyNameCN}

3. cp {run_dir}/{company}-analysis-{date}.html \
      $INVES_REPORT_DIR/reports/{CompanySlug}_{CompanyNameCN}/分析报告_dashboard.html

4. {PYBIN} -m scripts.update_index --company {company} --repo $INVES_REPORT_DIR --force
   # 解析主报告的 CARD_METADATA + assembly.json → card-metadata.json → upsert data/reports.json
   # v8 卡片字段:verdict = 行动档位人话 / quality = 质地字段 / action_gear / next_disclosure_date
   # ⚠️ 报告若不在默认 output/ 根下(config 的 PLUGIN_ROOT/output 优先规则), 补 --output-dir {output_root}

   # 同一条命令会顺带把 reports.data.js 刷成 reports.json 的快照(file:// 本地预览读它,
   # 线上读 reports.json)。仓库里没这个文件才需要补 --refresh-preview-data。

5. cd $INVES_REPORT_DIR
   git add reports/{CompanySlug}_{CompanyNameCN}/ data/reports.json reports.data.js
   git commit -m "feat: 新增/更新 {company} 投资分析报告"
   git push origin main
```

**失败处理**:push 失败 → 保存 HTML 到本地并通知用户手动上传(不重试超过一次)。

---

## Part D: 信息缺口补查(触发式)

**触发**:附录E(`data_sources.md`)里有 ⚠️/❌ 状态的缺口,**或**某个写手的完成报告带了「降级标注」
(缺什么、什么事件能补上)。没有触发条件就跳过本 Part。

**5 步补查**(对每条缺口依次执行,找到即停,但每步都要登记):

| 步 | 动作 | 为什么在这个位置 |
|:-:|---|---|
| D.1 | WebFetch 巨潮资讯公告索引,按关键词过滤后取 PDF | 缺口多半来自没读的临时公告,巨潮覆盖最广、时效最高 |
| D.2 | WebFetch 公司官网 IR / 投资者关系页 | 官方口径,二手转述之上 |
| D.3 | `{PYBIN} -m scripts.pdf_reader {pdf} --search "{关键词正则}"` | 已下载 PDF 的全文命中 |
| D.4 | WebSearch `site:cninfo.com.cn` / `site:sse.com.cn` / `site:sec.gov` + 关键词 | 事件性信息 |
| D.5 | Tushare 结构化接口(`fina_mainbz` / `stk_rewards` / `stk_managers` / `top10_holders` / `forecast_vip` …) | 结构化兜底,对事件性信息覆盖差,放最后 |

**判定分档**:✅ 直接回答了缺口 / ⚠️ 只找到相关上下文或代理指标 / ❌ 空手 / ⏭️ 明确不适用。
整体状态:至少 1 步 ✅ 且交叉验证 = **已解决**;有 ⚠️ 其余 ❌ = **部分解决**(必须写「还需要什么数据才能升级」);
全 ❌/⏭️ = **未找到**(必须写「信息可得性:低 / 原则上不可得」+ 原因)。

**★ 补到的数据往哪写(v8 落点)**:

| 补到的是什么 | 落点 |
|---|---|
| 改变某个子判定的证据 | **fresh-restart 对应节点写手**(判断变了,主 agent 不代笔) |
| 只是补充明细 / 时序 / 表格 | 采集产物(`data_snapshot.md` 等)→ 重跑装配,自动进附录 |
| 缺口状态本身 | `data_sources.md`(附录E 的挂载源)→ 重跑装配 |

补完一律重跑 `assemble_report_v8` + `lint_v8`;**不要只改附录E 而不动判断**——那是孤岛化。

---

## 输出

1. `{run_dir}/{company}-analysis-{date}.html` — v8 仪表盘 HTML
2. `{run_dir}/phase6-review-log.md` — 质量环日志
3. `{run_dir}/reviewer_responses/round_*.md` — 两 reviewer 往返 + 合并 FIX 列表
4. GitHub Pages 更新

### 质量环日志格式

```markdown
# Phase 6 质量环日志: {company}
**日期:** {YYYY-MM-DD} · **run:** runs/{date}/

## 机器门控 lint_v8
| 轮次 | 退出码 | fail 项 | warn 项 |
|:-:|:-:|---|---|
| 初次 | 1 | R8 越权发声 / R10 报告与节点同步 | R2w 🟠 归家 ×2 |
| 修正后 | 0 | — | R2w 🟠 归家 ×2 |

## reviewer 往返
| 轮次 | logic | delivery | 判断类 | 表述类 | 修正 agent(scope) | next_step |
|:-:|:-:|:-:|:-:|:-:|---|---|
| 1 | FAIL | FAIL | 2 | 2 | node-odds(判断+表述), node-state(仅表述), decision-writer(判断+表述) | Round+1 |
| 2 | FAIL | FAIL | 0 | 3 | node-path(仅表述) | 终检 |
| 终检 | — | 1 条 delivery | 0 | 1 | 主 agent 改模板 | 出片 |

## 交付
**HTML:** ✅(决断卡 5 / Top3 3 / 五章 + 附录A-E)
**发布:** ✅ leafpaper/Inves-Report / ❌(原因)
**缺口补查(Part D):** 未触发 / N 条,{已解决 x / 部分 y / 未找到 z}
```

---

## 质检清单

- [ ] `lint_v8` 退出码 0(fail 项全过);warn 项已在日志里记账
- [ ] `review_loop` 最后一轮 `overall_pass: true`(判断类 FIX 归零;或 3 轮上限已转人工并通知用户)
- [ ] 每轮 reviewer 响应都落在 `{run_dir}/reviewer_responses/`,没有只存在 context 里的判定(金山 Round 3 就没落盘,`review_loop` 根本没跑)
- [ ] 所有节点 FIX(判断类 + 表述类)都由**修正 agent** 落地,主 agent 没有 Edit 过任何节点 md
- [ ] 终检跑过一次:`final_delivery.md` 在,HTML 是终检 FIX 落地后重出的
- [ ] 每次 FIX 应用后都重跑了「装配 + lint」两条命令
- [ ] `build_html` 退出 0 且成品自检无缺项
- [ ] 主页卡片字段(行动档位 / 质地 / 下次预约披露日)已随 `update_index` 更新
- [ ] Part D 若触发:每条缺口有 5 步记录 + 明确整体状态 + 补到的数据已回到判断或附录
- [ ] `main-log.md` 有 Phase 6 的启停、每轮判定、转人工(若有)记录
