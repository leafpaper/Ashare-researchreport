"""export_agents.py — 一份源文件,三家 harness:把 `agents/*.md`(Claude Code 子代理定义)导出成
Codex 与 OpenCode 各自认的子代理格式,外加 Codex 读的 `agents/openai.yaml`。

为什么要有这个脚本:判断链的 10 个 sub-agent 只在 `agents/*.md` 里维护一份(唯一真相源),
其它 harness 的文件**全部由本脚本生成**,测试 `test_export_agents.py` 保证生成物与源同步——
手改 adapters/ 下的文件会被测试判红。

目标格式(各家只认自己的):

| harness   | 放哪                                  | 格式 | 字段来源 |
|-----------|---------------------------------------|------|----------|
| Claude Code | ~/.claude/agents/company-analysis/*.md | 原样 | tools / disallowedTools / model |
| OpenCode  | ~/.config/opencode/agents/*.md        | md + frontmatter(description / mode / permission) | tools → permission 映射 |
| Codex     | ~/.codex/agents/*.toml                | TOML(name / description / developer_instructions) | body 原文 |

`model` 不导出:别家的模型由会话决定(OpenCode 接 DeepSeek 就是 `deepseek/deepseek-v4-pro`),
写死 claude 模型名会让别家报错。Claude Code 自己那份保留 v8.12 钉死的模型。

CLI:
    python -m scripts.export_agents            # 写 adapters/{codex,opencode}/ + agents/openai.yaml
    python -m scripts.export_agents --check    # 只比对,不写;有漂移退出码 1(CI / 测试用)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"
ADAPTERS = ROOT / "adapters"
CODEX_DIR = ADAPTERS / "codex" / "agents"
OPENCODE_DIR = ADAPTERS / "opencode" / "agents"
OPENAI_YAML = AGENTS_DIR / "openai.yaml"

SKILL_NAME = "company-analysis"

# Claude Code 工具名 → OpenCode permission 键。OpenCode 的 permission 只有这几类,
# Read/Glob/Grep 属于读,没有开关;Write 归 edit;Bash 归 bash;WebSearch/WebFetch 归 webfetch。
_OPENCODE_PERMS = {
    "edit": ("Write", "Edit"),
    "bash": ("Bash",),
    "webfetch": ("WebSearch", "WebFetch"),
}

SKILL_ROOT_NOTE = (
    "> **路径约定**:skill 根目录由主 agent 在 prompt 里以 `{skill_root}` 给出"
    "(OpenCode / Codex 默认 `~/.agents/skills/company-analysis`);下文 `references/` `scripts/` `agents/` "
    "都相对它。工具名按本 harness 的叫法理解(Read = 读文件,Bash = 跑命令,Grep = 搜索)。\n\n"
)

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)


def parse_agent(path: Path) -> dict:
    """读一个 Claude Code 子代理 md:frontmatter(YAML)+ body。"""
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f"{path.name}: 没有 frontmatter")
    meta = yaml.safe_load(m.group(1)) or {}
    for key in ("name", "description"):
        if not meta.get(key):
            raise ValueError(f"{path.name}: frontmatter 缺 {key}")
    if meta["name"] != path.stem:
        raise ValueError(f"{path.name}: name={meta['name']} 与文件名不一致")
    tools = [t.strip() for t in str(meta.get("tools", "")).split(",") if t.strip()]
    disallowed = [t.strip() for t in str(meta.get("disallowedTools", "")).split(",") if t.strip()]
    return {
        "name": meta["name"],
        "description": str(meta["description"]).strip(),
        "tools": tools,
        "disallowed": disallowed,
        "body": m.group(2).strip() + "\n",
        "path": path,
    }


def load_agents() -> list[dict]:
    return [parse_agent(p) for p in sorted(AGENTS_DIR.glob("*.md"))]


def short_description(desc: str) -> str:
    """多行 description 取第一句(各家列表只显示一行)。"""
    first = desc.splitlines()[0].strip()
    return first[:200]


# ----------------------------------------------------------------- OpenCode
def opencode_permission(agent: dict) -> dict:
    perm = {}
    for key, names in _OPENCODE_PERMS.items():
        allowed = any(n in agent["tools"] for n in names)
        denied = all(n in agent["disallowed"] or n not in agent["tools"] for n in names)
        perm[key] = "allow" if allowed and not denied else "deny"
    return perm


def render_opencode(agent: dict) -> str:
    front = {
        "description": short_description(agent["description"]),
        "mode": "subagent",
        "permission": opencode_permission(agent),
    }
    fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).rstrip()
    header = (
        f"<!-- 由 scripts/export_agents.py 从 agents/{agent['name']}.md 生成,别手改;"
        f"改源文件后重跑 python -m scripts.export_agents -->\n\n"
        + SKILL_ROOT_NOTE
    )
    return f"---\n{fm}\n---\n\n{header}{agent['body']}"


# ----------------------------------------------------------------- Codex
def _toml_basic_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _toml_multiline(s: str) -> str:
    # 三引号字面串不能含 ''';body 里没有, 但守一下
    return "'''\n" + s.replace("'''", "'''" + "\\''") + "'''"


def render_codex(agent: dict) -> str:
    body = (
        f"# 由 scripts/export_agents.py 从 agents/{agent['name']}.md 生成,别手改;"
        f"改源文件后重跑 python -m scripts.export_agents\n"
        f"name = {_toml_basic_string(agent['name'])}\n"
        f"description = {_toml_basic_string(short_description(agent['description']))}\n"
        f"developer_instructions = {_toml_multiline(SKILL_ROOT_NOTE + agent['body'])}\n"
    )
    return body


# ----------------------------------------------------------------- Codex skill metadata
def render_openai_yaml() -> str:
    data = {
        "interface": {
            "display_name": "Company Analysis",
            "short_description": "上市公司投资分析:判断链五节点 + 首页决断卡 + 附录A-E(A股/美股/港股)",
            "default_prompt": "/company-analysis <公司名> [代码] [--review | --compare]",
        },
        "policy": {"allow_implicit_invocation": True},
    }
    return (
        "# Codex 读的 skill 元数据(Agent Skills 可选文件);由 scripts/export_agents.py 生成\n"
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    )


# ----------------------------------------------------------------- driver
def expected_files() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for agent in load_agents():
        out[OPENCODE_DIR / f"{agent['name']}.md"] = render_opencode(agent)
        out[CODEX_DIR / f"{agent['name']}.toml"] = render_codex(agent)
    out[OPENAI_YAML] = render_openai_yaml()
    return out


def check() -> list[str]:
    """返回漂移清单(空 = 同步)。"""
    drift = []
    for path, content in expected_files().items():
        if not path.exists():
            drift.append(f"缺文件: {path.relative_to(ROOT)}")
        elif path.read_text(encoding="utf-8") != content:
            drift.append(f"内容过期: {path.relative_to(ROOT)}")
    return drift


def write_all() -> list[Path]:
    written = []
    for path, content in expected_files().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")
            written.append(path)
    return written


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    ap = argparse.ArgumentParser(description="agents/*.md → Codex / OpenCode 子代理文件")
    ap.add_argument("--check", action="store_true", help="只比对不写;有漂移退出码 1")
    args = ap.parse_args()
    if args.check:
        drift = check()
        for line in drift:
            print("✗", line)
        print("✓ adapters/ 与 agents/*.md 同步" if not drift else f"{len(drift)} 处漂移, 跑 python -m scripts.export_agents")
        return 1 if drift else 0
    written = write_all()
    for p in written:
        print("写入", p.relative_to(ROOT))
    print(f"完成: {len(written)} 个文件更新, {len(expected_files())} 个生成物")
    return 0


if __name__ == "__main__":
    sys.exit(main())
