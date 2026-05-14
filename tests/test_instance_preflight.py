from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forager_ai.backend.conflict_resolver import ConflictResolver, ConflictSeverity, ConflictType, ModConflict
from forager_ai.backend.conflict_scan import build_conflict_scan_report
from forager_ai.diagnostics.instance_preflight import (
    build_launch_target_preflight_report,
    compute_scan_fidelity,
    enrich_scan_fidelity,
    try_read_disk_manifest_versions,
)


class InstancePreflightTests(unittest.TestCase):
    def test_try_read_disk_manifest_versions_roundtrip(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            mc, lo, pres = try_read_disk_manifest_versions(tmp)
            self.assertFalse(pres)
            self.assertIsNone(mc)
            self.assertIsNone(lo)

            p = Path(tmp) / "pack.manifest.json"
            p.write_text(
                json.dumps({"minecraft_version": "1.21.1", "loader": "neoforge", "mods": []}),
                encoding="utf-8",
            )
            mc2, lo2, pres2 = try_read_disk_manifest_versions(tmp)
            self.assertTrue(pres2)
            self.assertEqual(mc2, "1.21.1")
            self.assertEqual(lo2, "neoforge")

    def test_compute_scan_fidelity_jar_gt_mods(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            mods = Path(tmp) / "mods"
            mods.mkdir()
            for i in range(3):
                (mods / f"m{i}.jar").write_bytes(b"x")
            scan = {
                "mods": [
                    {"id": "one", "name": "One", "source": "local_jar"},
                    {"id": "two", "name": "Two", "source": "local_jar"},
                ]
            }
            sf = compute_scan_fidelity(
                pack_root=tmp,
                scan=scan,
                hub_mc="1.20.1",
                hub_loader="forge",
                effective_mc="1.20.1",
                effective_loader="forge",
                disk_mc=None,
                disk_loader=None,
                disk_present=False,
            )
            self.assertEqual(sf["jar_mod_files"], 3)
            self.assertEqual(sf["mods_indexed"], 2)
            self.assertEqual(sf["confidence"], "low")
            self.assertFalse(sf["jar_mod_parity"])

    def test_preflight_prefers_disk_manifest_versions(self) -> None:
        import tempfile
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "pack.manifest.json"
            p.write_text(
                json.dumps({"minecraft_version": "1.21.1", "loader": "fabric", "mods": []}),
                encoding="utf-8",
            )
            (Path(tmp) / "mods").mkdir()
            launcher = MagicMock()
            launcher.get_system_info = MagicMock(
                return_value={"java_installations": ["x"], "config": {"default_memory": 8192}, "instances_count": 1}
            )
            rep = build_launch_target_preflight_report(
                game_root=tmp,
                label="t",
                minecraft_version="1.20.1",
                loader="forge",
                launcher=launcher,
                conflict_resolver=ConflictResolver(tmp),
            )
            echo = rep.get("manifest_echo") or {}
            self.assertEqual(echo.get("minecraft_version"), "1.21.1")
            self.assertEqual(echo.get("loader"), "fabric")
            sf = rep.get("scan_fidelity") or {}
            self.assertEqual(sf.get("minecraft_source"), "pack.manifest.json")
            self.assertTrue(sf.get("hub_row_overridden"))

    def test_conflict_summary_matches_serialized_length(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            manifest = {"minecraft_version": "1.20.1", "loader": "forge", "mods": []}
            r = build_conflict_scan_report(
                resolver=ConflictResolver(tmp),
                manifest=manifest,
                pack_root=tmp,
                pack_name="x",
            )
            conflicts = r.get("conflicts") if isinstance(r.get("conflicts"), list) else []
            summary = r.get("summary") or {}
            self.assertEqual(int(summary.get("total_conflicts") or 0), len(conflicts))

    def test_enrich_scan_fidelity_log_hits_downgrade(self) -> None:
        base = compute_scan_fidelity(
            pack_root="x",
            scan={"mods": []},
            hub_mc="1.20.1",
            hub_loader="forge",
            effective_mc="1.20.1",
            effective_loader="forge",
            disk_mc=None,
            disk_loader=None,
            disk_present=False,
        )
        ll = {
            "overall_severity": "critical",
            "hits": [{"severity": "critical", "pattern_id": "x", "snippet": "a"}],
            "log_path": "/tmp/latest.log",
            "note": "tail only",
        }
        out = enrich_scan_fidelity(base, launch_log=ll)
        self.assertEqual(out.get("confidence"), "low")
        self.assertIn("launch_log_path", out)

    def test_lock_verify_skipped_when_many_jars(self) -> None:
        import tempfile
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "mods").mkdir()
            Path(tmp, "forager_mods.lock.json").write_text('{"jars":[]}', encoding="utf-8")
            launcher = MagicMock()
            launcher.get_system_info = MagicMock(
                return_value={"java_installations": ["x"], "config": {"default_memory": 8192}, "instances_count": 1}
            )
            with patch("forager_ai.diagnostics.instance_preflight._count_jar_mod_files", return_value=301):
                rep = build_launch_target_preflight_report(
                    game_root=tmp,
                    label="t",
                    minecraft_version="1.20.1",
                    loader="forge",
                    launcher=launcher,
                    conflict_resolver=ConflictResolver(tmp),
                )
            lv = rep.get("lock_verify") or {}
            self.assertTrue(lv.get("skipped"))

    def test_skip_conflict_ids_filters_report(self) -> None:
        import tempfile
        from unittest.mock import patch

        c_keep = ModConflict(
            id="keep_me",
            type=ConflictType.KNOWN_INCOMPATIBILITY,
            severity=ConflictSeverity.HIGH,
            affected_mods=["a", "b"],
            description="d1",
            suggested_resolution="s1",
        )
        c_drop = ModConflict(
            id="drop_me",
            type=ConflictType.KNOWN_INCOMPATIBILITY,
            severity=ConflictSeverity.MEDIUM,
            affected_mods=["c"],
            description="d2",
            suggested_resolution="s2",
        )

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ConflictResolver, "analyze_mod_list", return_value=[c_keep, c_drop]):
                r = build_conflict_scan_report(
                    resolver=ConflictResolver(tmp),
                    manifest={"minecraft_version": "1.20.1", "loader": "forge", "mods": []},
                    pack_root=tmp,
                    pack_name="x",
                    skip_conflict_ids={"drop_me"},
                )
            ids = {c["id"] for c in (r.get("conflicts") or [])}
            self.assertEqual(ids, {"keep_me"})
            self.assertEqual(int((r.get("summary") or {}).get("total_conflicts") or 0), 1)


if __name__ == "__main__":
    unittest.main()
