#!/bin/bash
#
# company-analysis skill — 卸载(三家 harness 的安装位置都清)
#
#   curl -fsSL https://raw.githubusercontent.com/leafpaper/claude-company-analysis/main/uninstall.sh | bash
#

removed=0
for d in \
  "$HOME/.claude/skills/company-analysis" \
  "$HOME/.claude/agents/company-analysis" \
  "$HOME/.agents/skills/company-analysis"; do
  if [ -d "$d" ]; then rm -rf "$d"; echo "已删除 $d"; removed=1; fi
done
# Codex / OpenCode 的子代理文件与别的 skill 混放在同一目录,只删本 skill 的 10 个
for name in data-collector doc-analyst node-quality node-odds node-path node-state decision-writer reviewer-logic reviewer-delivery compare-judge; do
  for f in "$HOME/.codex/agents/$name.toml" "$HOME/.config/opencode/agents/$name.md"; do
    if [ -f "$f" ]; then rm -f "$f"; echo "已删除 $f"; removed=1; fi
  done
done
[ "$removed" = 1 ] && echo "卸载完成,重启你的 agent 后生效。" || echo "没有找到任何安装,可能已经卸载。"
