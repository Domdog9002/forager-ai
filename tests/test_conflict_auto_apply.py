from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forager_ai.pack.conflict_auto_apply import (
    apply_auto_action,
    effective_auto_action,
    rebuild_remove_duplicates_action,
    summarize_auto_action,
)


class ConflictAutoApplyTests(unittest.TestCase):
    def test_summarize_remove_duplicates_preview(self) -> None:
        action = {
            "action": "remove_duplicates",
            "keep_mod": "all_the_leaks",
            "remove_mods": ["allthetweaks"],
        }
        mods_by_id = {
            "all_the_leaks": {"id": "all_the_leaks", "name": "All The Leaks"},
            "allthetweaks": {"id": "allthetweaks", "name": "AllTheTweaks"},
        }
        preview = summarize_auto_action(action, mods_by_id=mods_by_id)
        self.assertIn("Keep All The Leaks", preview)
        self.assertIn("disable AllTheTweaks", preview)
        self.assertNotIn("Multiple mods provide", preview)

    def test_effective_auto_action_respects_override(self) -> None:
        item = {
            "conflict_id": "duplicate_x",
            "description": "Multiple mods provide similar functionality: A, B",
            "action": {
                "action": "remove_duplicates",
                "keep_mod": "a",
                "remove_mods": ["b"],
            },
        }
        override = rebuild_remove_duplicates_action(
            keep_mod="b",
            affected_mods=["a", "b"],
        )
        merged = effective_auto_action(item, override)
        self.assertEqual(merged.get("keep_mod"), "b")
        self.assertEqual(merged.get("remove_mods"), ["a"])

    def test_apply_remove_duplicates_disables_jar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mods_dir = Path(tmp) / "mods"
            mods_dir.mkdir()
            keep = mods_dir / "all_the_leaks-1.0.jar"
            drop = mods_dir / "allthetweaks-1.0.jar"
            keep.write_bytes(b"keep")
            drop.write_bytes(b"drop")
            mods_by_id = {
                "all_the_leaks": {"id": "all_the_leaks", "name": "All The Leaks", "file_name": keep.name},
                "allthetweaks": {"id": "allthetweaks", "name": "AllTheTweaks", "file_name": drop.name},
            }
            jar_rows = [
                {
                    "name": keep.name,
                    "rel": f"mods/{keep.name}",
                    "path": str(keep),
                    "disabled": False,
                },
                {
                    "name": drop.name,
                    "rel": f"mods/{drop.name}",
                    "path": str(drop),
                    "disabled": False,
                },
            ]
            action = {
                "action": "remove_duplicates",
                "keep_mod": "all_the_leaks",
                "remove_mods": ["allthetweaks"],
            }
            result = apply_auto_action(tmp, action, mods_by_id=mods_by_id, jar_rows=jar_rows)
            self.assertTrue(result.ok)
            self.assertTrue(keep.is_file())
            self.assertFalse(drop.is_file())
            self.assertTrue((mods_dir / f"{drop.name}.disabled").is_file())


if __name__ == "__main__":
    unittest.main()
