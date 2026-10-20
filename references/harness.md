# 跨 harness 调度对照表(v8.13)

> **谁读这份**:主 agent,在它要「派一个子代理」的时候。本 skill 的编排文档用一套中性写法描述派活,
> 每种 harness 把它翻译成自己的工具调用。判断链、手册、脚本、schema 与 harness 无关。

## 1. 编排文档里的中性写法

```text
▶ 派 node-odds(③赔率,并行)
prompt = f"""…"""
```

- `▶ 派 X` = 用 **X** 这个子代理定义启动一个**全新**实例(没有上一次的记忆)。
- `并行` = 不等它,接着派下一个;`前台` = 等它回来再走。
- 「等完成报告回来」= 收齐每个并行子代理的最终响应(各家机制见 §2)。
- 子代理的名字(`data-collector` / `doc-analyst` / `node-quality` / `node-odds` / `node-path` / `node-state` /
  `decision-writer` / `reviewer-logic` / `reviewer-delivery` / `compare-judge`)在三家 harness 里**完全一样**。

## 2. 各家怎么翻译

| 动作 | Claude Code | OpenCode(含 DeepSeek) | Codex |
|---|---|---|---|
| 子代理定义在哪 | `~/.claude/agents/company-analysis/*.md`(源文件) | `~/.config/opencode/agents/*.md`(由 `adapters/opencode/` 装入) | `~/.codex/agents/*.toml`(由 `adapters/codex/` 装入) |
| `▶ 派 X` | `Agent` 工具,`subagent_type="X"` | Task 工具(或消息里 `@X`) | 多代理模式下按名字 spawn 子代理 X |
| 并行 | `run_in_background=True`,多个 Agent 调用一次发出 | 同一条回复里发多个 Task 调用 | 同一条回复里 spawn 多个(默认并发上限 6) |
| 前台 | `run_in_background=False` | 单个 Task 调用,等结果 | 单个 spawn,等结果 |
| 等完成报告回来 | 系统的 task-notification | Task 调用的返回值 | 子代理完成事件 / wait |
| 指定模型 | 源文件 frontmatter `model: claude-opus-5-5`(v8.12 钉死) | 会话模型(OpenCode 接 DeepSeek:`deepseek/deepseek-v4-pro`),子代理文件不写 model | 会话模型,子代理文件不写 model |
| 转人工通知 | PushNotification(没有就写 `_failure_report.md`) | 写 `_failure_report.md` 并在响应里说明 | 同左 |
| 重启同一个子代理 | 再调一次 Agent(没有 resume) | 再调一次 Task | 再 spawn 一次 |

**三家共同的硬规则**:子代理之间不共享记忆,修正循环只能 fresh-restart + 把上轮 FIX 原文注入新 prompt;
状态一律落文件(`main-log.md` / `runs/{date}/` / `reviewer_responses/`),不靠对话上下文。

## 3. 路径

| | Claude Code | OpenCode / Codex |
|---|---|---|
| skill 根目录 `{skill_root}` | `~/.claude/skills/company-analysis` | `~/.agents/skills/company-analysis` |
| 输出 | `{skill_root}/output/{company}/`(Claude Code 另有 `~/.claude/output` 优先规则,见 `scripts/config.py`) | `{skill_root}/output/{company}/` |
| Python 解释器 | 环境变量 `CA_PYBIN` 优先,其余按 SKILL.md Step 0 | 同左 |
| Tushare token | 环境变量 `TUSHARE_TOKEN` | 同左 |

**给子代理的 prompt 里永远带 `{skill_root}`**(手册、schema、脚本路径都相对它)—— Claude Code 的子代理能凭约定找到,
OpenCode / Codex 的子代理只认 prompt 里写的路径。

## 4. 已知限制(写在这里免得你去猜)

- **Codex 多代理模式**是实验功能,要在它的配置里打开;有用户报告过桌面端认不出自定义子代理类型。
  打不开的话退而求其次:主 agent 自己按 `adapters/codex/agents/X.toml` 的 `developer_instructions` 逐个扮演,串行跑
  (贵,但能出报告)。
- **OpenCode** 直接扫 `~/.claude/skills` 与 `~/.agents/skills`,skill 本体装一份即可;子代理要装到它自己的目录。
- **DeepSeek 没有自己的 harness**,官方推荐的就是 OpenCode 接 DeepSeek provider。模型换了,
  估值锚会漂(见 v8.12 manifest 记模型的规则),换模型后第一次跑建议全量而不是 `--review`。
- 作者只在 Claude Code 上实跑过完整流水线;Codex / OpenCode 的子代理文件由 `scripts/export_agents.py`
  从同一份源生成并有测试守同步,但端到端未在作者机器上验证过。跑出问题请带 `main-log.md` 开 issue。
