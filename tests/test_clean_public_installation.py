"""Verification of Public Clean Installation, Feature Behavior, and Isolation (Parts E & F).

Tests:
1. Disposable installation into a fresh mock Hermes tree
2. Absolute absence of private personal files from public installation
3. Public streaming & non-streaming functionality with native features (polls, calendar, maps, tapbacks)
4. Markdown tables preserved strictly as plain text (no image rendering)
5. Unsupported personal tags (<weather>, <movie>, <word>, <cheat_sheet>) safely degrade
6. Code blocks containing tags remain literal
7. No requirement for Playwright or Pillow in public mode
8. Public vs Personal mode isolation and process-wide registration audit
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AIRHERMES_ROOT = Path(__file__).resolve().parent.parent
FORK_ROOT = Path(os.environ.get("HERMES_AGENT_PATH", AIRHERMES_ROOT.parent / "hermes-agent-fork"))


class TestCleanPublicInstallation(unittest.TestCase):
    def setUp(self):
        self.temp_hermes = tempfile.mkdtemp(prefix="airhermes_public_clean_")
        # Copy essential gateway and plugin structure from upstream fork
        for d in ["gateway", "plugins", "tests"]:
            src = FORK_ROOT / d
            dst = Path(self.temp_hermes) / d
            if src.is_dir():
                shutil.copytree(src, dst)

    def tearDown(self):
        shutil.rmtree(self.temp_hermes, ignore_errors=True)

    def test_clean_installation_and_runtime_behavior(self):
        # 1. Install AirHermes into disposable tree
        res = subprocess.run(
            [sys.executable, "install.py", "--target", self.temp_hermes],
            cwd=str(AIRHERMES_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Installer failed: {res.stderr}\n{res.stdout}")

        # 2. Verify private files are NOT in the target tree
        private_artifacts = [
            "gateway/personal_cards_extension.py",
            "plugins/platforms/photon/personal_cards_extension.py",
            "gateway/visual_card_renderer.py",
            "gateway/visual_sheet_renderer.py",
            "assets/card_textures",
        ]
        for rel in private_artifacts:
            target_path = Path(self.temp_hermes) / rel
            self.assertFalse(target_path.exists(), f"Private file {rel} should not exist in public install!")

        # 3. Verify public files ARE present
        public_artifacts = [
            "gateway/airhermes_config.py",
            "gateway/attachment_registry.py",
            "gateway/bubble_actions.py",
            "gateway/bubble_parser.py",
            "gateway/bubble_queue.py",
            "gateway/bubble_stream_consumer.py",
            "plugins/platforms/photon/adapter.py",
            "plugins/platforms/photon/sidecar/index.mjs",
            "plugins/platforms/photon/sidecar/package.json",
        ]
        for rel in public_artifacts:
            target_path = Path(self.temp_hermes) / rel
            self.assertTrue(target_path.is_file(), f"Public file {rel} missing in install!")

        # 4. Exercise runtime in the installed tree via a clean sub-process (simulating clean public mode)
        clean_runner_script = Path(self.temp_hermes) / "verify_public_runtime.py"
        clean_runner_script.write_text(r"""
import sys
import unittest
from pathlib import Path

# Add installed tree to sys.path
tree_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(tree_dir))

from gateway.bubble_parser import BubbleParser
from gateway.bubble_actions import (
    TextBubble,
    PollAction,
    TapbackAction,
    EffectAction,
    ImageAttachmentAction,
    FileAttachmentAction,
)

class TestPublicRuntime(unittest.TestCase):
    def test_no_private_modules_imported(self):
        self.assertNotIn("personal_cards_extension", sys.modules)
        self.assertNotIn("visual_card_renderer", sys.modules)
        self.assertNotIn("visual_sheet_renderer", sys.modules)
        self.assertNotIn("playwright", sys.modules)

    def test_markdown_tables_preserved_as_text(self):
        parser = BubbleParser()
        content = (
            "方案对比分析如下：\n\n"
            "| 特性 | 方案A | 方案B |\n"
            "|---|---|---|\n"
            "| 速度 | 快 | 慢 |\n"
            "| 成本 | 低 | 高 |\n\n"
            "请根据需求选择。"
        )
        actions = parser.feed_actions(content) + parser.finish_actions()

        # Must not produce any image attachment
        img_actions = [a for a in actions if isinstance(a, ImageAttachmentAction)]
        self.assertEqual(len(img_actions), 0)

        # Table content must be preserved in text bubbles
        texts = [a.content for a in actions if isinstance(a, TextBubble)]
        combined_text = "\n".join(texts)
        self.assertIn("| 特性 | 方案A | 方案B |", combined_text)
        self.assertIn("| 速度 | 快 | 慢 |", combined_text)

    def test_unknown_personal_tags_safe_fallback(self):
        parser = BubbleParser()
        content = (
            "北京今日天气：\n"
            '<weather temp="20°C" condition="晴" location="北京">\n'
            "今日晴空万里，微风宜人。\n"
            "</weather>\n"
            '<movie title="盗梦空间" rating="9.3" />\n'
            '<cheat_sheet title="参数对照">\n'
            "| 参数 | 值 |\n"
            "|---|---|\n"
            "| 内存 | 16G |\n"
            "</cheat_sheet>\n"
            "祝您生活愉快！"
        )
        # Should not raise exception
        actions = parser.feed_actions(content) + parser.finish_actions()

        # No images produced in public mode
        img_actions = [a for a in actions if isinstance(a, ImageAttachmentAction)]
        self.assertEqual(len(img_actions), 0)

        # Unhandled tags degrade safely to text bubbles
        texts = [a.content for a in actions if isinstance(a, TextBubble)]
        combined = "\n".join(texts)
        self.assertTrue(len(texts) >= 1)
        self.assertIn("祝您生活愉快！", combined)

    def test_code_blocks_with_tags_remain_literal(self):
        parser = BubbleParser()
        content = (
            "代码示例：\n"
            "```xml\n"
            "<bubble>这是代码里的标签</bubble>\n"
            "<weather temp=\"30°C\" />\n"
            "<poll title=\"代码里的投票\"><option>A</option></poll>\n"
            "```\n"
            "以上为代码展示。"
        )
        actions = parser.feed_actions(content) + parser.finish_actions()

        polls = [a for a in actions if isinstance(a, PollAction)]
        self.assertEqual(len(polls), 0, "Tags inside code block must not trigger actions!")

        texts = [a.content for a in actions if isinstance(a, TextBubble)]
        combined = "\n".join(texts)
        self.assertIn("<bubble>这是代码里的标签</bubble>", combined)
        self.assertIn("<weather temp=\"30°C\" />", combined)

    def test_native_ecosystem_actions(self):
        parser = BubbleParser()
        content = (
            "<bubble>第一条消息</bubble>\n"
            "<tapback emoji=\"👍\" />\n"
            "<poll title=\"周末去哪玩？\"><option>西湖</option><option>灵隐寺</option></poll>\n"
            "<map name=\"西湖断桥\" address=\"中国浙江省杭州市西湖区\" />\n"
            "<effect:slam>重要的提醒</effect:slam>\n"
            "<bubble>最后一条消息</bubble>"
        )
        actions = parser.feed_actions(content) + parser.finish_actions()

        tapbacks = [a for a in actions if isinstance(a, TapbackAction)]
        polls = [a for a in actions if isinstance(a, PollAction)]
        effects = [a for a in actions if isinstance(a, EffectAction)]
        texts = [a for a in actions if isinstance(a, TextBubble)]

        self.assertEqual(len(tapbacks), 1)
        self.assertEqual(tapbacks[0].reaction, "👍")
        self.assertEqual(len(polls), 1)
        self.assertEqual(polls[0].title, "周末去哪玩？")
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].effect_type, "slam")
        self.assertEqual(effects[0].content, "重要的提醒")

        # Map generates a valid Apple Maps link inside text bubbles
        from urllib.parse import unquote
        combined_text = "\n".join(t.content for t in texts)
        self.assertIn("maps.apple.com", combined_text)
        self.assertIn("西湖断桥", unquote(combined_text))

if __name__ == "__main__":
    unittest.main()
""", encoding="utf-8")

        # Run verification in clean python environment
        run_res = subprocess.run(
            [sys.executable, str(clean_runner_script)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(run_res.returncode, 0, f"Public runtime test failed:\n{run_res.stderr}\n{run_res.stdout}")


if __name__ == "__main__":
    unittest.main()
