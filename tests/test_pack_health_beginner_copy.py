from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forager_ai.analysis.mod_graph import build_graph, to_graphviz_dot
from forager_ai.pack.health_copy import humanize_conflict_type, pack_health_graph_node_cap


class PackHealthBeginnerCopyTests(unittest.TestCase):
    def test_to_graphviz_dot_uses_friendly_edge_labels(self) -> None:
        manifest = {
            "mods": [
                {"id": "create", "dependencies": ["flywheel"]},
                {"id": "flywheel"},
            ],
            "compats": [{"affected_mods": ["create", "ars_nouveau"], "rule_name": "tuned"}],
        }
        graph = build_graph(manifest, max_render_nodes=20)
        dot = to_graphviz_dot(graph)
        self.assertIn('label="Needs"', dot)
        self.assertNotIn('label="depends_on"', dot)
        self.assertIn("Works with", dot)
        self.assertNotIn('label="compat"', dot)

    def test_humanize_conflict_type_maps_known_enums(self) -> None:
        self.assertEqual(humanize_conflict_type("missing_dependency"), "Missing requirement")
        self.assertEqual(humanize_conflict_type("known_incompatibility"), "Known bad pairing")
        self.assertEqual(humanize_conflict_type("custom_issue"), "Custom Issue")

    def test_pack_health_graph_node_cap_scales_with_pack_size(self) -> None:
        self.assertEqual(pack_health_graph_node_cap(50), 140)
        self.assertEqual(pack_health_graph_node_cap(200), 100)
        self.assertEqual(pack_health_graph_node_cap(400), 72)

    def test_build_graph_stable_for_same_inputs(self) -> None:
        manifest = {"mods": [{"id": "a"}, {"id": "b", "dependencies": ["a"]}]}
        g1 = build_graph(manifest, max_render_nodes=10)
        g2 = build_graph(manifest, max_render_nodes=10)
        self.assertEqual(
            to_graphviz_dot(g1),
            to_graphviz_dot(g2),
        )
        self.assertEqual(json.dumps(g1, sort_keys=True), json.dumps(g2, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
