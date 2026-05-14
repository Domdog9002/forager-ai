from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


def _gv_esc(value: Any) -> str:
    """Escape text for double-quoted Graphviz identifiers / edge labels."""
    t = str(value or "")
    t = t.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return t[:240]


# Lightweight starter ruleset. Expand over time.
KNOWN_HARD_CONFLICTS: List[Tuple[str, str, str]] = [
    ("optifine", "rubidium", "Renderer conflicts can cause startup/crash issues."),
    ("optifine", "embeddium", "Renderer conflicts can cause startup/crash issues."),
]

KNOWN_SOFT_CONFLICTS: List[Tuple[str, str, str]] = [
    ("create", "ars_nouveau", "Balance and progression tuning usually needed."),
]


@dataclass(frozen=True)
class GraphEdge:
    src: str
    dst: str
    relation: str  # depends_on | compat | soft_conflict | hard_conflict | scan_finding
    note: str = ""


def _mod_id_from_entry(entry: Dict[str, Any]) -> str:
    for key in ("mod_id", "id", "slug", "name"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower().replace(" ", "_").replace("-", "_")
    return "unknown_mod"


def _normalize_scan_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    for old, new in ((" ", "_"), ("-", "_")):
        text = text.replace(old, new)
    return text or "unknown_mod"


def _edge_key(lo: str, hi: str, relation: str, note: str) -> Tuple[str, str, str, str]:
    return (lo, hi, relation, (note or "")[:160])


def build_graph(
    manifest: Dict[str, Any],
    *,
    scan_mods: Optional[List[Dict[str, Any]]] = None,
    scan_conflicts: Optional[List[Dict[str, Any]]] = None,
    max_render_nodes: int = 160,
) -> Dict[str, Any]:
    """Build an undirected compatibility graph for Pack Health.

    When ``scan_mods`` / ``scan_conflicts`` are supplied (resolver scan output), the graph
    includes jar-derived mods and pairwise links for scan findings — not only
    ``pack.manifest.json`` rows (often empty for linked CurseForge/Modrinth profiles).

    Large packs are **capped** for Graphviz: prefer mods mentioned in conflicts, expand
    along declared dependency edges, then fill toward ``max_render_nodes``.
    """
    mods = manifest.get("mods", [])
    compats = manifest.get("compats", [])

    nodes: Set[str] = set()
    edges: List[GraphEdge] = []
    seen_edge: Set[Tuple[str, str, str, str]] = set()

    def add_edge(lo: str, hi: str, relation: str, note: str = "") -> None:
        if not lo or not hi or lo == hi or lo == "unknown_mod" or hi == "unknown_mod":
            return
        a, b = (lo, hi) if lo < hi else (hi, lo)
        ek = _edge_key(a, b, relation, note)
        if ek in seen_edge:
            return
        seen_edge.add(ek)
        edges.append(GraphEdge(src=a, dst=b, relation=relation, note=note))

    # Manifest mods + dependency edges.
    for mod in mods:
        if not isinstance(mod, dict):
            continue
        mod_id = _mod_id_from_entry(mod)
        nodes.add(mod_id)

        deps = mod.get("dependencies", [])
        if isinstance(deps, list):
            for dep in deps:
                if isinstance(dep, str) and dep.strip():
                    dep_id = _normalize_scan_id(dep)
                    nodes.add(dep_id)
                    add_edge(mod_id, dep_id, "depends_on", "")

    # Resolver scan mods (jars + sparse manifest) + dependency edges.
    if scan_mods:
        for mod in scan_mods:
            if not isinstance(mod, dict):
                continue
            mid = _normalize_scan_id(mod.get("id") or mod.get("name") or "")
            if mid in ("", "unknown_mod"):
                continue
            nodes.add(mid)
            for dep in mod.get("dependencies") or []:
                if isinstance(dep, str) and dep.strip():
                    did = _normalize_scan_id(dep)
                    if did not in ("", "unknown_mod"):
                        nodes.add(did)
                        add_edge(mid, did, "depends_on", "")

    # Compat relations from manifest.
    for compat in compats:
        if not isinstance(compat, dict):
            continue
        affected = compat.get("affected_mods", [])
        if not isinstance(affected, list):
            continue
        normalized = [_normalize_scan_id(m) for m in affected if isinstance(m, str) and m.strip()]
        normalized = [m for m in normalized if m != "unknown_mod"]
        for m in normalized:
            nodes.add(m)
        for i in range(len(normalized)):
            for j in range(i + 1, len(normalized)):
                add_edge(
                    normalized[i],
                    normalized[j],
                    "compat",
                    str(compat.get("rule_name", "compat_rule")),
                )

    present = set(nodes)

    # Heuristic starter pairs (OptiFine vs Embeddium, Create vs Ars, …).
    findings: List[Dict[str, str]] = []
    for a, b, note in KNOWN_HARD_CONFLICTS:
        if a in present and b in present:
            add_edge(a, b, "hard_conflict", note)
            findings.append({"severity": "high", "mods": f"{a} <-> {b}", "note": note})
    for a, b, note in KNOWN_SOFT_CONFLICTS:
        if a in present and b in present:
            add_edge(a, b, "soft_conflict", note)
            findings.append({"severity": "medium", "mods": f"{a} <-> {b}", "note": note})

    # Pairwise edges from resolver scan findings (incompatible_versions, duplicates, …).
    if scan_conflicts:
        for conflict in scan_conflicts:
            if not isinstance(conflict, dict):
                continue
            raw_affected = conflict.get("affected_mods") or []
            if not isinstance(raw_affected, list):
                continue
            aff = [_normalize_scan_id(x) for x in raw_affected if str(x).strip()]
            aff = list(dict.fromkeys([a for a in aff if a != "unknown_mod"]))
            if len(aff) < 2:
                continue
            sev = str(conflict.get("severity") or "").strip().lower()
            ctype = str(conflict.get("type") or "").strip().lower()
            note = f"{ctype} ({sev})" if ctype or sev else "scan"
            for i in range(len(aff)):
                for j in range(i + 1, len(aff)):
                    add_edge(aff[i], aff[j], "scan_finding", note)

    # Cap node count for Graphviz / Streamlit (full ATM-style packs = hundreds of jars).
    if len(nodes) > max_render_nodes:
        hot: Set[str] = set()
        if scan_conflicts:
            for conflict in scan_conflicts:
                if not isinstance(conflict, dict):
                    continue
                for x in conflict.get("affected_mods") or []:
                    hid = _normalize_scan_id(x)
                    if hid != "unknown_mod":
                        hot.add(hid)
        keep: Set[str] = set(hot) if hot else set()
        adj: Dict[str, Set[str]] = defaultdict(set)
        for e in edges:
            if e.relation == "depends_on":
                adj[e.src].add(e.dst)
                adj[e.dst].add(e.src)
        q: deque[str] = deque(sorted(keep))
        while q and len(keep) < max_render_nodes:
            cur = q.popleft()
            for nbr in adj.get(cur, ()):
                if nbr not in keep and len(keep) < max_render_nodes:
                    keep.add(nbr)
                    q.append(nbr)
        if len(keep) < min(32, max_render_nodes) and scan_mods:
            for mod in scan_mods:
                if len(keep) >= max_render_nodes:
                    break
                if isinstance(mod, dict) and mod.get("id"):
                    keep.add(_normalize_scan_id(mod["id"]))
        if not keep:
            keep = set(sorted(nodes)[:max_render_nodes])
        elif len(keep) > max_render_nodes:
            must = hot & keep
            if len(must) > max_render_nodes:
                keep = set(sorted(must)[:max_render_nodes])
            else:
                pool = sorted(set(nodes) - must)
                keep = set(must)
                for pid in pool:
                    if len(keep) >= max_render_nodes:
                        break
                    keep.add(pid)
        nodes = {n for n in nodes if n in keep}
        edges = [e for e in edges if e.src in keep and e.dst in keep]

    node_list = sorted(nodes)
    return {
        "nodes": node_list,
        "edges": [e.__dict__ for e in edges],
        "findings": findings,
    }


def to_graphviz_dot(graph: Dict[str, Any]) -> str:
    lines = ["graph ModGraph {"]
    lines.append('  rankdir="LR";')
    lines.append(
        '  graph [fontname="Helvetica", bgcolor="#111827", pad="0.2", margin="0.1", '
        'fontcolor="#e2e8f0", labeljust="l"];'
    )
    lines.append('  node [shape=box, style="filled,rounded", fillcolor="#334155", fontcolor="#f8fafc"];')
    lines.append('  edge [fontname="Helvetica", color="#94a3b8", fontcolor="#cbd5e1", fontsize=10];')

    for node in graph.get("nodes", []):
        safe = _gv_esc(node)
        lines.append(f'  "{safe}";')

    for edge in graph.get("edges", []):
        src = _gv_esc(edge.get("src", ""))
        dst = _gv_esc(edge.get("dst", ""))
        relation = str(edge.get("relation", "") or "")
        note = str(edge.get("note", "") or "")
        color = "#94a3b8"
        label = relation
        if relation == "depends_on":
            color = "#38bdf8"
            label = "Needs"
        elif relation == "compat":
            color = "#34d399"
            label = f"Works with: {note}" if note else "Works with"
        elif relation == "soft_conflict":
            color = "#fbbf24"
            label = "May clash"
        elif relation == "hard_conflict":
            color = "#f87171"
            label = "Do not mix"
        elif relation == "scan_finding":
            color = "#fb923c"
            label = f"Issue link: {note}" if note else "Issue link"
        esc_lbl = _gv_esc(label)
        lines.append(f'  "{src}" -- "{dst}" [color="{color}", label="{esc_lbl}"];')

    lines.append("}")
    return "\n".join(lines)

