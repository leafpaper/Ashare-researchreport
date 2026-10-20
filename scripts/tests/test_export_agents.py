"""单元测试: export_agents — agents/*.md 是唯一真相源, adapters/ 下的 Codex / OpenCode 文件必须与它同步。

跑:
    python -m unittest scripts.tests.test_export_agents
"""
from __future__ import annotations

import tomllib
import unittest

import yaml

from scripts import export_agents as ex


class TestExportAgents(unittest.TestCase):
    def test_adapters_are_in_sync_with_source(self):
        """手改 adapters/ 或改了 agents/*.md 没重跑导出 → 这条判红。"""
        self.assertEqual(ex.check(), [], "跑 python -m scripts.export_agents 重新生成")

    def test_every_source_agent_has_both_targets(self):
        names = {a["name"] for a in ex.load_agents()}
        self.assertEqual(len(names), 10)
        files = ex.expected_files()
        self.assertEqual({p.stem for p in files if p.suffix == ".toml"}, names)
        self.assertEqual({p.stem for p in files if p.parent == ex.OPENCODE_DIR}, names)
        self.assertIn(ex.OPENAI_YAML, files)

    def test_codex_toml_parses_and_keeps_body(self):
        for agent in ex.load_agents():
            data = tomllib.loads(ex.render_codex(agent))
            self.assertEqual(data["name"], agent["name"])
            self.assertTrue(data["description"])
            self.assertIn(agent["body"].strip()[:60], data["developer_instructions"], agent["name"])
            self.assertNotIn("model", data)        # 模型由会话决定, 不能写死 claude 模型名

    def test_opencode_permission_mapping(self):
        by_name = {a["name"]: a for a in ex.load_agents()}
        self.assertEqual(ex.opencode_permission(by_name["reviewer-logic"]),
                         {"edit": "deny", "bash": "deny", "webfetch": "deny"})      # 只读评审
        self.assertEqual(ex.opencode_permission(by_name["data-collector"]),
                         {"edit": "allow", "bash": "allow", "webfetch": "allow"})   # 采集要联网
        self.assertEqual(ex.opencode_permission(by_name["node-odds"]),
                         {"edit": "allow", "bash": "allow", "webfetch": "deny"})    # 写手不联网

    def test_opencode_frontmatter_parses(self):
        for agent in ex.load_agents():
            text = ex.render_opencode(agent)
            fm = yaml.safe_load(text.split("---\n")[1])
            self.assertEqual(fm["mode"], "subagent")
            self.assertEqual(set(fm["permission"]), {"edit", "bash", "webfetch"})
            self.assertNotIn("model", fm)


if __name__ == "__main__":
    unittest.main()
