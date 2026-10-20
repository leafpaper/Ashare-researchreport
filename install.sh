#!/bin/bash
#
# company-analysis skill — 一键安装 (v8.13)
#
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/leafpaper/Ashare-researchreport/main/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- codex        # 只装给 Codex
#   curl -fsSL .../install.sh | bash -s -- opencode     # 只装给 OpenCode(DeepSeek 走这个)
#   curl -fsSL .../install.sh | bash -s -- all          # 三家都装
#   ./install.sh claude                                  # 在克隆下来的仓库根目录里跑, 不下载
#
# 不带参数 = 自动探测: PATH 上有哪家 CLI 就装给哪家; 一家都没有就装给 Claude Code。
#
# 装到哪:
#   Claude Code : ~/.claude/skills/company-analysis  +  ~/.claude/agents/company-analysis/*.md
#   Codex       : ~/.agents/skills/company-analysis  +  ~/.codex/agents/*.toml
#   OpenCode    : ~/.agents/skills/company-analysis  +  ~/.config/opencode/agents/*.md
#   (Codex 与 OpenCode 共用 ~/.agents/skills 那一份 skill 本体)

set -e

TARGET="${1:-${CA_TARGET:-auto}}"
REPO_TARBALL="https://github.com/leafpaper/Ashare-researchreport/archive/refs/heads/main.tar.gz"

# ------------------------------------------------ 源:本地仓库 or 下载
if [ -f "$(dirname "$0")/SKILL.md" ] 2>/dev/null; then
  SRC="$(cd "$(dirname "$0")" && pwd)"
  echo "源: 本地仓库 $SRC"
else
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  echo "下载 $REPO_TARBALL ..."
  curl -fsSL "$REPO_TARBALL" | tar -xz -C "$TMP"
  SRC="$TMP/Ashare-researchreport-main"
fi

# ------------------------------------------------ 目标
case "$TARGET" in
  auto)
    TARGETS=""
    command -v claude   >/dev/null 2>&1 && TARGETS="$TARGETS claude"
    command -v codex    >/dev/null 2>&1 && TARGETS="$TARGETS codex"
    command -v opencode >/dev/null 2>&1 && TARGETS="$TARGETS opencode"
    [ -z "$TARGETS" ] && TARGETS="claude"
    ;;
  all)    TARGETS="claude codex opencode" ;;
  claude|codex|opencode) TARGETS="$TARGET" ;;
  *) echo "未知目标: $TARGET(可选 claude / codex / opencode / all)"; exit 1 ;;
esac
echo "安装目标:$TARGETS"

# ------------------------------------------------ skill 本体
install_body() {   # $1 = 目标 skill 目录
  local dst="$1"
  rm -rf "$dst"
  mkdir -p "$dst"
  for item in SKILL.md README.md CHANGELOG.md LICENSE .env.sample phases references scripts assets agents; do
    cp -R "$SRC/$item" "$dst/"
  done
  rm -rf "$dst/scripts/__pycache__" "$dst/scripts/tests/__pycache__"
  # 校验:数量从源算, 不写死(以前写死清单漏过 schema 与 phase 文件)
  for pair in "phases:*.md" "references:*.md" "agents:*.md" "scripts:*.py" "scripts/schemas:*.schema.json"; do
    local d="${pair%%:*}" g="${pair##*:}"
    local want got
    want=$(find "$SRC/$d" -maxdepth 1 -name "$g" | wc -l | tr -d ' ')
    got=$(find "$dst/$d" -maxdepth 1 -name "$g" | wc -l | tr -d ' ')
    [ "$want" = "$got" ] || { echo "❌ $d 复制不完整: 期望 $want 实际 $got"; exit 1; }
  done
  echo "  skill 本体 → $dst"
}

AGENTS_SHARED="$HOME/.agents/skills/company-analysis"
for t in $TARGETS; do
  case "$t" in
    claude)
      install_body "$HOME/.claude/skills/company-analysis"
      mkdir -p "$HOME/.claude/agents/company-analysis"
      cp "$SRC"/agents/*.md "$HOME/.claude/agents/company-analysis/"
      echo "  子代理(Claude Code) → ~/.claude/agents/company-analysis/ ($(ls "$SRC"/agents/*.md | wc -l | tr -d ' ') 个)"
      ;;
    codex)
      [ -d "$AGENTS_SHARED" ] || install_body "$AGENTS_SHARED"
      mkdir -p "$HOME/.codex/agents"
      cp "$SRC"/adapters/codex/agents/*.toml "$HOME/.codex/agents/"
      echo "  子代理(Codex) → ~/.codex/agents/*.toml ($(ls "$SRC"/adapters/codex/agents/*.toml | wc -l | tr -d ' ') 个)"
      ;;
    opencode)
      [ -d "$AGENTS_SHARED" ] || install_body "$AGENTS_SHARED"
      mkdir -p "$HOME/.config/opencode/agents"
      cp "$SRC"/adapters/opencode/agents/*.md "$HOME/.config/opencode/agents/"
      echo "  子代理(OpenCode) → ~/.config/opencode/agents/*.md ($(ls "$SRC"/adapters/opencode/agents/*.md | wc -l | tr -d ' ') 个)"
      ;;
  esac
done

# 同一次安装里 codex/opencode 共用的本体只装一次;若之前已有旧版, 强制刷新一遍
case " $TARGETS " in *" codex "*|*" opencode "*) install_body "$AGENTS_SHARED" ;; esac

cat <<EOF

============================================
  ✅ 安装完成 (v8.13):$TARGETS
============================================

下一步(必做):
  1. Python 依赖(3.11+):
       pip3 install --user -r ~/.claude/skills/company-analysis/scripts/requirements.txt
       (Codex / OpenCode 用 ~/.agents/skills/company-analysis/scripts/requirements.txt)
  2. Tushare token(A 股 / 港股必需, 只看美股可跳过):
       echo 'export TUSHARE_TOKEN="your_token"' >> ~/.zshrc && source ~/.zshrc
  3. 自检:
       cd <skill 目录> && python3 -m scripts.check_env
  4. 重启你的 agent, 然后:
       Claude Code : /company-analysis 贵州茅台 600519.SH
       OpenCode    : /company-analysis 贵州茅台 600519.SH   (DeepSeek: 先 /connect 接 deepseek)
       Codex       : \$company-analysis 贵州茅台 600519.SH   (需打开多代理模式)

  想钉死解释器(如 venv 里的 python):设环境变量 CA_PYBIN 为它的完整路径。
  各家怎么派子代理、已知限制:references/harness.md
EOF
