# A股研报

**输入一只股票，拿到一份能直接读的研报：是不是好公司、在变好吗、贵不贵、扛得住吗、现在该怎么办。**

它自己拉财报数据、下载并精读年报原文、跑一遍会计审计框架，最后收成一张五行决断卡。
支持 A 股、港股、美股。全程说人话，每个关键数字都能回到出处。
装在 Claude Code、OpenCode（可接 DeepSeek）或 Codex 里用，一条命令触发。

<p align="center">
  <a href="https://github.com/leafpaper/a-share-research-report/actions/workflows/tests.yml"><img src="https://github.com/leafpaper/a-share-research-report/actions/workflows/tests.yml/badge.svg" alt="tests"></a>
  <img src="https://img.shields.io/badge/version-v8.14-blue" alt="version">
  <img src="https://img.shields.io/badge/markets-A%E8%82%A1%20%7C%20%E6%B8%AF%E8%82%A1%20%7C%20%E7%BE%8E%E8%82%A1-green" alt="markets">
  <img src="https://img.shields.io/badge/agents-Claude%20Code%20%7C%20OpenCode%20%7C%20Codex-orange" alt="agents">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="license">
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/readme/hero-dark.svg">
    <img src="./assets/readme/hero-light.svg" alt="报告首页：决断卡五行 + 赚不赚钱面板" width="920">
  </picture>
</p>

<p align="center"><sub>报告首页（示意图，数据取自 <a href="https://leafpaper.github.io/Inves-Report/reports/688111_金山办公/分析报告_dashboard.html">金山办公 688111</a> 的真实分析）</sub></p>

---

## 一条命令，一份研报

```
/company-analysis 金山办公
```

跑完你会拿到一个 HTML 文件，打开就是上面那张首页。它背后做了四件事：

| 做什么 | 怎么做 |
|---|---|
| 拉数据 | 三表、财务指标、股东与解禁、资金流、同业对标 |
| 读原文 | 下载年报、季报 PDF 逐页精读，结论带页码出处，不靠第三方摘要 |
| 查红旗 | 11 个会计审计框架机械扫雷：盈余质量、财务造假概率、破产风险、关联交易…… |
| 算价格 | 把股价拆成「已经赚到的」和「为想象多付的」，反推现价在赌什么，再给合理价区间 |

## 先看成品

说明书不如实物。四份真实报告，点开就能读：

| 公司 | 结论 | 这份报告在讲什么 |
|---|---|---|
| [金山办公 688111](https://leafpaper.github.io/Inves-Report/reports/688111_金山办公/分析报告_dashboard.html) | 先观察 · 0 仓位 | 净利润同比 +237%，其中 17.56 亿是两只关联方基金的账面重估，扣非口径都挡不住 |
| [华特气体 688268](https://leafpaper.github.io/Inves-Report/reports/688268_华特气体/分析报告_dashboard.html) | 回避 | 增长是真的，但要先分清有多少来自涨价、多少来自放量 |
| [中际旭创 300308](https://leafpaper.github.io/Inves-Report/reports/300308_中际旭创/分析报告_dashboard.html) | 回避 | 利润率顶格，护城河却建在外采芯片上 |
| [东山精密 002384](https://leafpaper.github.io/Inves-Report/reports/002384_东山精密/分析报告_dashboard.html) | 先观察 · 0 仓位 | 卡位是真的，但股价早已付完账 |
| [PCB 与光模块 产业链对比](https://leafpaper.github.io/Inves-Report/compare/pcb-optics/) | 两家都不放 | 同一条链的两端，分散不了同一个风险 |

全部报告：[leafpaper.github.io/Inves-Report](https://leafpaper.github.io/Inves-Report)

---

## 安装

需要 Python 3.11+。分析 A 股或港股还要一个 [Tushare](https://tushare.pro/register) token，只看美股可以不配。

**1. 装 skill**（不带参数自动探测你装了哪家 agent，也可以点名 `claude` / `opencode` / `codex` / `all`）

```bash
# Mac / Linux
curl -fsSL https://raw.githubusercontent.com/leafpaper/a-share-research-report/main/install.sh | bash
```
```powershell
# Windows，在克隆下来的仓库根目录里跑
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

**2. 装依赖、配 token**

```bash
pip3 install --user -r ~/.claude/skills/company-analysis/scripts/requirements.txt   # OpenCode / Codex 在 ~/.agents/skills/ 下
echo 'export TUSHARE_TOKEN="你的token"' >> ~/.zshrc && source ~/.zshrc           # Windows 用系统环境变量
```

**3. 重启 agent，开跑**

| 你用的 agent | 装到哪 | 怎么触发 |
|---|---|---|
| Claude Code | `~/.claude/skills/company-analysis/` | `/company-analysis 贵州茅台` |
| OpenCode | `~/.agents/skills/company-analysis/` | 同上；接 DeepSeek 先 `/connect deepseek` |
| Codex | 同上 | `$company-analysis 贵州茅台`，需打开多代理模式 |

说「分析一下茅台」「复查一下茅台」「茅台和五粮液比比」同样会触发。
只在 Claude Code 上完整实跑验证过，OpenCode 与 Codex 的细节和限制见 [`references/harness.md`](./references/harness.md)。

## 三种用法

| 命令 | 什么时候用 | 得到什么 |
|---|---|---|
| `/company-analysis 金山办公` | 第一次看一家公司 | 完整研报：首页决断卡 + 五章正文 + 附录 |
| `/company-analysis 金山办公 --review` | 财报季 | 只重评变了的部分，首页多一块「较上版变化」，第一句回答结论变了没 |
| `/company-analysis 东山精密 --compare` | 同行里只想买一家 | 把各家决断卡并排，回答「钱该放哪家」，只引用各家报告已有的证据 |

---

## 它怎么判断

先弄清「是不是一家好公司」，再决定「现在这个价格该不该买」。这是两件事，报告把它们分开说。

| | 问题 | 它怎么答 |
|---|---|---|
| ① 质地 | 是不是好公司 | 生意赚不赚钱、赚的钱是不是真的、护城河在不在、管理层可不可信、财务底子稳不稳 |
| ② 状态 | 在变好吗 | 只认财报、订单、官方披露这类实锤，传闻一律打折；并写明**该等什么**：哪份报告、哪个数字过哪条线 |
| ③ 赔率 | 贵不贵 | 股价拆成「已经赚到的」和「为想象多付的」，想象占比越大，越是必须兑现的任务 |
| ④ 路径 | 扛得住吗 | 先量最坏能跌到哪，方向对但中途腰斩拿不住，照样亏 |
| ⑤ 决策 | 现在该怎么办 | 行动档位、仓位、该等什么、什么情况下认错 |

②③④ 任何一项是「差」，现在就不是好下注。好公司不等于现在能买。

**它不做什么**：不打分，没有综合评分和权重；不替你下单，不做量化回测；不保证结论正确。
它保证的是每个数字有出处、每个结论有证据、机器能查出来的自相矛盾一条不放过。

## 免责声明

**本项目是研究工具，不是投资建议。** 它输出的判定、档位与仓位，是一套公开方法在公开数据上的推演结果，不构成任何证券的买卖建议。
数据来自 [Tushare Pro](https://tushare.pro)、[yfinance](https://github.com/ranaroussi/yfinance) 和交易所公开披露的定期报告，可能有口径差异、滞后或抽取错误；大模型生成的判断同样可能出错，报告里的「信息缺口」和「降级标注」就是为了让你看见它哪里没把握。
**据此做出的任何投资决策，风险由你自己承担。** 真要下注之前，请自己回原始公告核对一遍。

---

## 给开发者

<details>
<summary><b>报告结构</b></summary>

| 部分 | 内容 |
|---|---|
| 首页 | 决断卡五行、赚不赚钱面板（3-5 个指标带走势图与红标）、Top3 风险、3-5 句导读 |
| ① 质地 | 五个子判定 ✓ / ⚠️ / ✗，每个给最硬的一两条证据 |
| ② 状态 | 实锤与传闻分级、故事四关、临界点（该等什么，全报告唯一出处） |
| ③ 赔率 | 合理价区间 + 三种估值方法的完整推导，十条算术闭合机检 |
| ④ 路径 | 左尾清单（每条量到价格）、高信仰体检、证伪与退出清单 |
| ⑤ 怎么办 | 行动档位、仓位（全报告唯一出处）、该等什么、什么情况下我错了 |
| 附录 A-E | 财务明细 / 同业对标 / 舆情资金与技术面 / 红旗总清单 / 数据来源与信息缺口 |

首页、附录、Top3 由脚本从五个节点的机器块装配，人工只写导读那几句。
方法内核来自「贝叶斯之美」系列，完整定义见 [`references/judgment-chain.md`](./references/judgment-chain.md)。

</details>

<details>
<summary><b>流水线</b></summary>

```
Phase 1  采集      data-collector：结构化数据 + PDF 下载解析 + 11 框架审计 + 红旗清单
Phase 2  精读      doc-analyst：读 PDF 原文，产出带页码引用的文档精析
Phase 3  判断链    第一波  ①质地 ∥ ③赔率
                   第二波  ④路径 ∥ ②状态     （④的左尾深度要用③的价格区间当分母）
                   第三波  ⑤决策             （吃前四个节点的机器块）
                   装配    首页 + 五章 + 附录A-E
Phase 6  质量环    lint_v8 18 条 → reviewer-logic ∥ reviewer-delivery → 修正循环 → 终检 → 出片发布
```

波次由 `scripts/node_graph.py` 按依赖图算出来，增量复查用同一套调度跑任意节点子集。
写手只读「判断链手册 + 自己那一份节点手册」，跨节点只允许引用对方的判定，不许重新推导。
派子代理的写法与 agent 无关，各家对照表见 [`references/harness.md`](./references/harness.md)。

</details>

<details>
<summary><b>质量门控：三道关</b></summary>

1. **机器门控 `lint_v8`**，18 条规则，不过就不许出片。例如：同一个数字只能有一个出处；有致命红旗时行动档位强制回避；仓位和买卖建议只能出现在⑤；⑤引用的退出线必须在④里找得到。
2. **两个 reviewer 并行评审**，一个只查判断链逻辑，一个只查可读性与交付；判断类问题归零才算过，最多三轮，HTML 版式在终检时走查一次。
3. **五百多个单元测试**，每个被真实报告打出来的缺陷都会变成一条回归测试。

</details>

<details>
<summary><b>仓库结构</b></summary>

| 目录 | 放什么 |
|---|---|
| [`SKILL.md`](./SKILL.md) | 主 agent 的调度说明书 |
| [`agents/`](./agents/) | 10 个 sub-agent 定义（唯一真相源）：采集 / 精读 / 四个节点写手 / 决策 / 两个 reviewer / 对比裁决 |
| [`adapters/`](./adapters/) | 同一批子代理的 OpenCode 与 Codex 版本，由 `scripts/export_agents.py` 生成 |
| [`references/`](./references/) | 判断链手册、四份节点手册、HTML 规范、跨 agent 对照表 |
| [`phases/`](./phases/) | 各阶段执行细则：判断链写作、质量环发布、增量复查、产业链对比 |
| [`scripts/`](./scripts/) | 34 个 Python 脚本：数据采集 / 审计 / 装配 / 15 份 JSON Schema / lint / 出片 |
| [`scripts/tests/`](./scripts/tests/) | 单元测试 |
| [`assets/html/`](./assets/html/) | 报告与对比页的 HTML / CSS 模板 |
| [`.scratch/`](./.scratch/) | v8 重构期的设计留档与实现票，不参与运行 |

</details>

<details>
<summary><b>版本</b></summary>

完整记录见 [CHANGELOG.md](./CHANGELOG.md)。

| 版本 | 关键变化 |
|---|---|
| **v8.14** | 改名「A股研报」，README 重写，仓库改名 `a-share-research-report` |
| **v8.13** | 装上就能用：Agent Skills 标准 frontmatter、一键装到 Claude Code / OpenCode / Codex、子代理文件一源三出 |
| **v8.11** | 质量环省钱四条：干净会话硬规则 / 主 agent 不改节点 / 判断类归零即通过 / HTML 只在终检读一次 |
| **v8.10** | 首个轻资产订阅制样本（金山办公）打出 5 个采集缺陷与 6 条流水线修补 |
| **v8.9** | 已兑现倍数不超增长退出；技术面并入附录C；红旗 id 归一化 |
| **v8.3** | 产业链对比 `--compare` |
| **v8.1** | 增量复查 `--review` |
| **v8.0** | 判断链收敛：9 章改为首页 + 五章 + 附录；删除全部评分机制 |

</details>

### 贡献

欢迎 issue / PR。重点方向：更多审计框架、更多市场（日股 / 欧股）、机构持仓数据源。改代码前先跑一遍测试：

```bash
python -m unittest discover -s scripts/tests -t .
```

**License**: [MIT](./LICENSE) · **作者**: [@leafpaper](https://github.com/leafpaper) ·
**思路借鉴**: [terancejiang/Turtle_investment_framework](https://github.com/terancejiang/Turtle_investment_framework)
