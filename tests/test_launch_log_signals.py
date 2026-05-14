from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forager_ai.diagnostics.launch_log_signals import analyze_launch_log_tail


class LaunchLogSignalsTests(unittest.TestCase):
    def test_detects_class_not_found(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "logs"
            logs.mkdir(parents=True)
            (logs / "latest.log").write_text(
                "... Caused by: java.lang.ClassNotFoundException com.example.Missing\n",
                encoding="utf-8",
            )
            out = analyze_launch_log_tail(tmp, max_chars=5000)
            self.assertEqual(out.get("overall_severity"), "critical")
            hits = out.get("hits") or []
            self.assertTrue(any(h.get("pattern_id") == "class_not_found" for h in hits if isinstance(h, dict)))


if __name__ == "__main__":
    unittest.main()
