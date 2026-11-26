"""Unit tests for WantedFeed packaging, 3-pattern title generation, BST scheduler & KPI loop."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from publish import wantedfeed_packager as wf


class _FakeLLM:
    def __init__(self, payload: dict | str):
        self._payload = payload

    def generate(self, prompt: str, *, json_mode: bool = False) -> str:
        return json.dumps(self._payload) if isinstance(self._payload, dict) else self._payload


class WantedFeedPackagerTests(unittest.TestCase):
    def test_three_pattern_titles_avoid_all_caps_hook_verbatim(self) -> None:
        titles = wf.build_three_pattern_titles(
            "IShowSpeed Survived 6 Stars For 52 Hours",
            "IShowSpeed",
            hook_text="AFTER 52 HOURS IN GTA 6",
            summary="IShowSpeed pulls off a wild military base escape.",
        )
        for key, value in titles.items():
            self.assertLess(len(value), 60, f"{key} too long: {value}")
            self.assertTrue(value.endswith("#GTA6 #Shorts"), f"{key} missing suffix: {value}")
            self.assertNotIn("AFTER 52 HOURS", value, f"{key} copied ALL-CAPS hook verbatim: {value}")

        self.assertTrue(titles["pattern_2_mechanic"].startswith("What Happens When "))
        self.assertTrue(titles["pattern_2_mechanic"].endswith("? #GTA6 #Shorts"))
        self.assertTrue(titles["pattern_3_contrast"].startswith("GTA 6 vs GTA 5: "))

    def test_three_pattern_titles_llm_override_and_allcaps_rejection(self) -> None:
        good_llm = _FakeLLM({
            "pattern_1_reaction": "IShowSpeed Loses His Mind",
            "pattern_2_mechanic": "What Happens When You Steal Jets?",
            "pattern_3_contrast": "GTA 6 vs GTA 5: Jet Physics",
        })
        out = wf.build_three_pattern_titles(
            "Jet Steal", "IShowSpeed", hook_text="WAIT FOR IT", summary="Jet steal test", llm=good_llm
        )
        self.assertEqual(out["pattern_1_reaction"], "IShowSpeed Loses His Mind #GTA6 #Shorts")
        self.assertEqual(out["pattern_2_mechanic"], "What Happens When You Steal Jets? #GTA6 #Shorts")
        self.assertEqual(out["pattern_3_contrast"], "GTA 6 vs GTA 5: Jet Physics #GTA6 #Shorts")

        # Shouted LLM output falls back cleanly to sentence-case titles
        shouted_llm = _FakeLLM({
            "pattern_1_reaction": "INSANE SCREAMING CLIP",
            "pattern_2_mechanic": "WHAT HAPPENS WHEN YOU TRY THIS?",
            "pattern_3_contrast": "GTA 6 VS GTA 5 INSANE",
        })
        fallback_out = wf.build_three_pattern_titles(
            "Jet Steal Test", "IShowSpeed", hook_text="AFTER 52 HOURS", summary="He steals a fighter jet", llm=shouted_llm
        )
        self.assertNotIn("INSANE SCREAMING", fallback_out["pattern_1_reaction"])
        self.assertNotIn("WHAT HAPPENS", fallback_out["pattern_2_mechanic"])

    def test_placeholder_blocker_and_bst_rotation(self) -> None:
        with self.assertRaises(ValueError):
            wf.validate_no_placeholders({"caption": "Follow [Streamer Name] now"})

        ref_now = datetime(2026, 11, 27, 13, 0, tzinfo=timezone.utc)
        s1 = wf.schedule_slot_bst("KaiCenat", now=ref_now, existing_slots=[])
        s2 = wf.schedule_slot_bst("KaiCenat", now=ref_now, existing_slots=[s1])
        self.assertTrue(s2["rotation_deferred"])
        dt1 = datetime.fromisoformat(s1["scheduled_bst"])
        dt2 = datetime.fromisoformat(s2["scheduled_bst"])
        self.assertGreaterEqual((dt2 - dt1).total_seconds(), 12 * 3600)

    def test_build_package_output_shapes(self) -> None:
        pkg = wf.build_package(
            clip_path=Path("clip_demo.mp4"),
            channel_name="IShowSpeed",
            title="IShowSpeed Survived 6 Stars For 52 Hours",
            hook_text="AFTER 52 HOURS IN GTA 6",
            summary="IShowSpeed pulls off a wild military base escape.",
            duration_s=35.0,
            platform_hint="YouTube",
        )
        self.assertIn("Credit: @IShowSpeed on YouTube", pkg["platforms"]["meta_reels"]["caption"])
        self.assertNotIn("AFTER 52 HOURS", pkg["titles"]["pattern_2_mechanic"])
        self.assertNotIn("AFTER 52 HOURS", pkg["titles"]["pattern_3_contrast"])


if __name__ == "__main__":
    unittest.main()
