"""
Conflict Resolution System
Advanced mod conflict detection and resolution with AI assistance.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from enum import Enum

from ..launcher.mod_downloader import ModInfo

# Bump when ``analyze_mod_list`` / guardrail signatures change (Streamlit ``@st.cache_resource`` key).
_CONFLICT_RESOLVER_API_REV = 2


def _normalize_mod_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    for old, new in ((" ", "_"), ("-", "_")):
        text = text.replace(old, new)
    return text


class ConflictSeverity(Enum):
    """Severity levels for mod conflicts."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConflictType(Enum):
    """Types of mod conflicts."""
    DUPLICATE_CONTENT = "duplicate_content"
    INCOMPATIBLE_VERSIONS = "incompatible_versions"
    MISSING_DEPENDENCY = "missing_dependency"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    RESOURCE_CONFLICT = "resource_conflict"
    API_CONFLICT = "api_conflict"
    PERFORMANCE_IMPACT = "performance_impact"
    KNOWN_INCOMPATIBILITY = "known_incompatibility"


DEFAULT_KNOWN_MOD_PAIRS: List[Tuple[str, str, ConflictSeverity, str, str]] = [
    (
        "optifine",
        "embeddium",
        ConflictSeverity.HIGH,
        "Renderer stacks are commonly incompatible in modern Forge packs.",
        "Prefer Embeddium for Forge 1.20.1 performance and remove OptiFine.",
    ),
    (
        "optifine",
        "rubidium",
        ConflictSeverity.HIGH,
        "Renderer stacks are commonly incompatible in modern Forge packs.",
        "Prefer the maintained renderer stack for your Minecraft version.",
    ),
    (
        "create",
        "ars_nouveau",
        ConflictSeverity.MEDIUM,
        "Create automation and Ars Nouveau magic usually need progression and recipe tuning.",
        "Add a compatibility rule that documents intended progression gates.",
    ),
    (
        "create",
        "irons_spellbooks",
        ConflictSeverity.MEDIUM,
        "Create tech progression and Iron's Spells loot/combat progression can overlap.",
        "Review loot, spellbook, and crafting progression before release.",
    ),
    (
        "origins",
        "ars_nouveau",
        ConflictSeverity.LOW,
        "Origin powers can change how spellcasting, mana recovery, and movement progression feel.",
        "Playtest origin-specific magic progression and document exceptions.",
    ),
]


@dataclass
class ModConflict:
    """Represents a conflict between mods."""
    id: str
    type: ConflictType
    severity: ConflictSeverity
    affected_mods: List[str]
    description: str
    suggested_resolution: str
    auto_resolvable: bool = False
    resolution_actions: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.resolution_actions is None:
            self.resolution_actions = []


@dataclass
class ModCompatibility:
    """Compatibility information for a mod."""
    mod_id: str
    compatible_with: List[str]
    incompatible_with: List[str]
    requires: List[str]
    conflicts_with: List[str]
    performance_impact: str  # low, medium, high
    stability_rating: float  # 0.0 to 1.0
    last_updated: str


class ConflictResolver:
    """Advanced conflict resolution system."""
    
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Conflict database
        self.conflicts_db = self.data_dir / "conflicts.json"
        self.compatibility_db = self.data_dir / "compatibility.json"
        self.resolution_rules = self.data_dir / "resolution_rules.json"
        
        # Load databases
        self.known_conflicts: Dict[str, ModConflict] = self._load_conflicts()
        self.compatibility_data: Dict[str, ModCompatibility] = self._load_compatibility()
        self.rules: Dict[str, Any] = self._load_resolution_rules()
    
    def _load_conflicts(self) -> Dict[str, ModConflict]:
        """Load known conflicts database."""
        if not self.conflicts_db.exists():
            return {}
        
        try:
            with open(self.conflicts_db, 'r', encoding='utf-8') as f:
                data = json.load(f)
                conflicts = {}
                for conflict_id, conflict_data in data.items():
                    # Convert string enums back to enum objects
                    conflict_data['type'] = ConflictType(conflict_data['type'])
                    conflict_data['severity'] = ConflictSeverity(conflict_data['severity'])
                    conflicts[conflict_id] = ModConflict(**conflict_data)
                return conflicts
        except (json.JSONDecodeError, KeyError, ValueError):
            return {}
    
    def _load_compatibility(self) -> Dict[str, ModCompatibility]:
        """Load compatibility database."""
        if not self.compatibility_db.exists():
            return {}
        
        try:
            with open(self.compatibility_db, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {mod_id: ModCompatibility(**compat_data) 
                       for mod_id, compat_data in data.items()}
        except (json.JSONDecodeError, KeyError):
            return {}
    
    def _load_resolution_rules(self) -> Dict[str, Any]:
        """Load resolution rules."""
        if not self.resolution_rules.exists():
            return self._create_default_rules()
        
        try:
            with open(self.resolution_rules, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return self._create_default_rules()
    
    def _create_default_rules(self) -> Dict[str, Any]:
        """Create default resolution rules."""
        rules = {
            "duplicate_content": {
                "priority_order": ["official", "popular", "recent", "stable"],
                "auto_resolve": True,
                "keep_newest": True
            },
            "missing_dependency": {
                "auto_download": True,
                "suggest_alternatives": True,
                "required_only": False
            },
            "incompatible_versions": {
                "prefer_stable": True,
                "auto_update": False,
                "suggest_compatible": True
            },
            "performance_thresholds": {
                "max_mods": 200,
                "max_memory_impact": 0.7,
                "max_startup_time": 300
            }
        }
        
        # Save default rules
        with open(self.resolution_rules, 'w', encoding='utf-8') as f:
            json.dump(rules, f, indent=2)
        
        return rules
    
    def analyze_mod_list(
        self,
        mods: List[ModInfo],
        *,
        pack_manifest: Optional[Dict[str, Any]] = None,
    ) -> List[ModConflict]:
        """Analyze a list of mods for conflicts.

        ``pack_manifest`` supplies the pack's declared Minecraft version and loader so guardrails
        match the active profile (linked CurseForge/Modrinth rows are often not 1.20.1 Forge).
        """
        conflicts = []
        
        # Create mod lookup
        mod_lookup = {_normalize_mod_id(mod.id): mod for mod in mods}
        
        # Check for duplicate content
        conflicts.extend(self._check_duplicate_content(mods))
        
        # Check dependencies
        conflicts.extend(self._check_dependencies(mods, mod_lookup))
        
        # Check known incompatibilities
        conflicts.extend(self._check_known_incompatibilities(mods))
        conflicts.extend(self._check_known_mod_pairs(mods))
        
        # Check version conflicts
        conflicts.extend(self._check_version_conflicts(mods))
        conflicts.extend(self._check_loader_guardrails(mods, pack_manifest=pack_manifest))
        
        # Check performance impact
        conflicts.extend(self._check_performance_impact(mods))
        
        # Check resource conflicts
        conflicts.extend(self._check_resource_conflicts(mods))
        
        return conflicts
    
    def _check_duplicate_content(self, mods: List[ModInfo]) -> List[ModConflict]:
        """Check for mods that provide duplicate content."""
        conflicts = []
        
        # Group mods by similar names/functionality
        content_groups = {}
        for mod in mods:
            # Simple heuristic: group by similar names
            base_name = _normalize_mod_id(mod.name).replace("_", "")
            categories = {str(cat).strip().lower() for cat in (mod.categories or [])}
            duplicate_family = None
            for family, markers in {
                "minimap": {"minimap", "map", "journeymap"},
                "performance": {"performance", "optimization", "renderer"},
                "storage": {"storage", "inventory", "backpack"},
                "magic": {"magic", "spell", "mana"},
                "worldgen": {"worldgen", "biome", "dimension"},
            }.items():
                if categories.intersection(markers):
                    duplicate_family = family
                    break
            group_key = duplicate_family or base_name
            
            # Check for common duplicate patterns
            for existing_name, existing_mods in content_groups.items():
                similarity = self._calculate_name_similarity(group_key, existing_name)
                threshold = 0.8 if duplicate_family is None else 1.0
                if similarity >= threshold:
                    existing_mods.append(mod)
                    break
            else:
                content_groups[group_key] = [mod]
        
        # Find groups with multiple mods
        for group_name, group_mods in content_groups.items():
            if len(group_mods) > 1:
                conflict = ModConflict(
                    id=f"duplicate_{group_name}",
                    type=ConflictType.DUPLICATE_CONTENT,
                    severity=ConflictSeverity.MEDIUM,
                    affected_mods=[mod.id for mod in group_mods],
                    description=f"Multiple mods provide similar functionality: {', '.join(mod.name for mod in group_mods)}",
                    suggested_resolution="Keep only one mod from this group",
                    auto_resolvable=True,
                    resolution_actions=[
                        {
                            "action": "remove_duplicates",
                            "keep_mod": self._select_best_mod(group_mods).id,
                            "remove_mods": [mod.id for mod in group_mods[1:]]
                        }
                    ]
                )
                conflicts.append(conflict)
        
        return conflicts
    
    def _check_dependencies(self, mods: List[ModInfo], mod_lookup: Dict[str, ModInfo]) -> List[ModConflict]:
        """Check for missing or circular dependencies."""
        conflicts = []
        
        for mod in mods:
            if mod.dependencies:
                for dep_id in mod.dependencies:
                    normalized_dep = _normalize_mod_id(dep_id)
                    if normalized_dep not in mod_lookup:
                        # Missing dependency
                        conflict = ModConflict(
                            id=f"missing_dep_{_normalize_mod_id(mod.id)}_{normalized_dep}",
                            type=ConflictType.MISSING_DEPENDENCY,
                            severity=ConflictSeverity.HIGH,
                            affected_mods=[_normalize_mod_id(mod.id)],
                            description=f"Mod '{mod.name}' requires '{dep_id}' which is not installed",
                            suggested_resolution=f"Install dependency '{dep_id}'",
                            auto_resolvable=True,
                            resolution_actions=[
                                {
                                    "action": "install_dependency",
                                    "dependency_id": normalized_dep,
                                    "required_by": _normalize_mod_id(mod.id)
                                }
                            ]
                        )
                        conflicts.append(conflict)
        
        # Check for circular dependencies
        circular_deps = self._find_circular_dependencies(mods)
        for cycle in circular_deps:
            conflict = ModConflict(
                id=f"circular_dep_{'_'.join(cycle)}",
                type=ConflictType.CIRCULAR_DEPENDENCY,
                severity=ConflictSeverity.CRITICAL,
                affected_mods=cycle,
                description=f"Circular dependency detected: {' -> '.join(cycle)}",
                suggested_resolution="Remove one mod from the dependency cycle",
                auto_resolvable=False
            )
            conflicts.append(conflict)
        
        return conflicts
    
    def _check_known_incompatibilities(self, mods: List[ModInfo]) -> List[ModConflict]:
        """Check against known incompatibility database."""
        conflicts = []
        
        for mod in mods:
            mod_id = _normalize_mod_id(mod.id)
            if mod_id in self.compatibility_data:
                compat = self.compatibility_data[mod_id]
                
                # Check for incompatible mods
                for other_mod in mods:
                    other_id = _normalize_mod_id(other_mod.id)
                    incompatible = {_normalize_mod_id(item) for item in compat.incompatible_with}
                    conflicts_with = {_normalize_mod_id(item) for item in compat.conflicts_with}
                    if other_id != mod_id and (other_id in incompatible or other_id in conflicts_with):
                        conflict = ModConflict(
                            id=f"incompatible_{mod_id}_{other_id}",
                            type=ConflictType.KNOWN_INCOMPATIBILITY,
                            severity=ConflictSeverity.HIGH,
                            affected_mods=[mod_id, other_id],
                            description=f"'{mod.name}' is known to be incompatible with '{other_mod.name}'",
                            suggested_resolution="Remove one of the incompatible mods",
                            auto_resolvable=False
                        )
                        conflicts.append(conflict)
        
        return conflicts

    def _check_known_mod_pairs(self, mods: List[ModInfo]) -> List[ModConflict]:
        """Check starter built-in compatibility/progression rules."""
        present = {_normalize_mod_id(mod.id): mod for mod in mods}
        conflicts: List[ModConflict] = []
        for left, right, severity, description, resolution in DEFAULT_KNOWN_MOD_PAIRS:
            if left in present and right in present:
                conflicts.append(
                    ModConflict(
                        id=f"known_pair_{left}_{right}",
                        type=ConflictType.KNOWN_INCOMPATIBILITY,
                        severity=severity,
                        affected_mods=[left, right],
                        description=description,
                        suggested_resolution=resolution,
                        auto_resolvable=False,
                    )
                )
        return conflicts
    
    def _check_version_conflicts(self, mods: List[ModInfo]) -> List[ModConflict]:
        """Check for version compatibility issues."""
        conflicts = []
        
        # Group mods by Minecraft version
        version_groups = {}
        for mod in mods:
            for mc_version in {_normalize_mod_id(v).replace("_", ".") for v in (mod.minecraft_versions or [])}:
                if mc_version not in version_groups:
                    version_groups[mc_version] = []
                version_groups[mc_version].append(mod)
        
        # Check if all mods support a common version
        if len(version_groups) > 1:
            all_mods = {_normalize_mod_id(mod.id) for mod in mods}
            common_versions = []
            
            for version, version_mods in version_groups.items():
                version_mod_ids = {_normalize_mod_id(mod.id) for mod in version_mods}
                if version_mod_ids == all_mods:
                    common_versions.append(version)
            
            if not common_versions:
                conflict = ModConflict(
                    id="version_incompatibility",
                    type=ConflictType.INCOMPATIBLE_VERSIONS,
                    severity=ConflictSeverity.CRITICAL,
                    affected_mods=[_normalize_mod_id(mod.id) for mod in mods],
                    description="No common Minecraft version supported by all mods",
                    suggested_resolution="Update mods to compatible versions or remove incompatible mods",
                    auto_resolvable=False
                )
                conflicts.append(conflict)
        
        return conflicts

    def _check_loader_guardrails(
        self,
        mods: List[ModInfo],
        *,
        pack_manifest: Optional[Dict[str, Any]] = None,
    ) -> List[ModConflict]:
        """Flag loader or Minecraft-version mismatch vs the pack's declared profile."""
        conflicts: List[ModConflict] = []
        # ``javafml`` appears in some Forge ``mods.toml`` / API loader strings; treat as Forge-family.
        forge_aliases = {"forge", "neoforge", "javafml"}
        fabric_aliases = {"fabric", "quilt"}
        pm = pack_manifest if isinstance(pack_manifest, dict) else {}
        exp_mc = str(pm.get("minecraft_version") or "1.20.1").strip()
        exp_loader = _normalize_mod_id(str(pm.get("loader") or "forge").strip())
        if exp_loader in ("", "unknown"):
            exp_loader = "forge"
        # Common manifest spellings
        if exp_loader == "neo_forge":
            exp_loader = "neoforge"
        for mod in mods:
            mod_id = _normalize_mod_id(mod.id)
            versions = {str(v).strip() for v in (mod.minecraft_versions or []) if str(v).strip()}
            loaders = {_normalize_mod_id(loader) for loader in (mod.loaders or []) if str(loader).strip()}
            if versions and exp_mc and exp_mc not in versions:
                conflicts.append(
                    ModConflict(
                        id=f"mc_version_guardrail_{mod_id}",
                        type=ConflictType.INCOMPATIBLE_VERSIONS,
                        severity=ConflictSeverity.HIGH,
                        affected_mods=[mod_id],
                        description=f"'{mod.name}' does not advertise Minecraft {exp_mc} support.",
                        suggested_resolution=f"Choose a {exp_mc}-compatible file or align the pack profile.",
                        auto_resolvable=False,
                    )
                )
            if not loaders:
                continue
            if exp_loader in forge_aliases:
                if not loaders.intersection(forge_aliases):
                    conflicts.append(
                        ModConflict(
                            id=f"loader_guardrail_{mod_id}",
                            type=ConflictType.INCOMPATIBLE_VERSIONS,
                            severity=ConflictSeverity.HIGH,
                            affected_mods=[mod_id],
                            description=f"'{mod.name}' is not marked as Forge/NeoForge compatible.",
                            suggested_resolution="Install a Forge/NeoForge file or use a matching loader instance.",
                            auto_resolvable=False,
                        )
                    )
            elif exp_loader in fabric_aliases:
                if not loaders.intersection(fabric_aliases):
                    conflicts.append(
                        ModConflict(
                            id=f"loader_guardrail_{mod_id}",
                            type=ConflictType.INCOMPATIBLE_VERSIONS,
                            severity=ConflictSeverity.HIGH,
                            affected_mods=[mod_id],
                            description=f"'{mod.name}' is not marked as Fabric/Quilt compatible.",
                            suggested_resolution="Install a Fabric/Quilt build or switch the pack loader profile.",
                            auto_resolvable=False,
                        )
                    )
        return conflicts
    
    def _check_performance_impact(self, mods: List[ModInfo]) -> List[ModConflict]:
        """Check for performance impact issues."""
        conflicts = []
        
        # Check total mod count
        max_mods = self.rules.get("performance_thresholds", {}).get("max_mods", 200)
        if len(mods) > max_mods:
            conflict = ModConflict(
                id="too_many_mods",
                type=ConflictType.PERFORMANCE_IMPACT,
                severity=ConflictSeverity.MEDIUM,
                affected_mods=[mod.id for mod in mods],
                description=f"Too many mods installed ({len(mods)} > {max_mods}). This may impact performance.",
                suggested_resolution="Consider removing some mods or using performance optimization mods",
                auto_resolvable=False
            )
            conflicts.append(conflict)
        
        # Check for known performance-heavy mods
        heavy_mods = []
        for mod in mods:
            if mod.id in self.compatibility_data:
                compat = self.compatibility_data[mod.id]
                if compat.performance_impact == "high":
                    heavy_mods.append(mod)
        
        if len(heavy_mods) > 3:  # Arbitrary threshold
            conflict = ModConflict(
                id="performance_heavy_mods",
                type=ConflictType.PERFORMANCE_IMPACT,
                severity=ConflictSeverity.MEDIUM,
                affected_mods=[mod.id for mod in heavy_mods],
                description=f"Multiple performance-heavy mods detected: {', '.join(mod.name for mod in heavy_mods)}",
                suggested_resolution="Consider using performance optimization settings or removing some heavy mods",
                auto_resolvable=False
            )
            conflicts.append(conflict)
        
        return conflicts
    
    def _check_resource_conflicts(self, mods: List[ModInfo]) -> List[ModConflict]:
        """Check for resource conflicts (textures, models, etc.)."""
        conflicts = []
        
        # This would require analyzing mod contents, which is complex
        # For now, we'll use heuristics based on mod categories
        
        texture_mods = []
        for mod in mods:
            if any(cat in ["texture", "resource", "visual"] for cat in mod.categories):
                texture_mods.append(mod)
        
        if len(texture_mods) > 1:
            conflict = ModConflict(
                id="texture_conflicts",
                type=ConflictType.RESOURCE_CONFLICT,
                severity=ConflictSeverity.LOW,
                affected_mods=[mod.id for mod in texture_mods],
                description=f"Multiple texture/visual mods may conflict: {', '.join(mod.name for mod in texture_mods)}",
                suggested_resolution="Check mod compatibility and load order",
                auto_resolvable=False
            )
            conflicts.append(conflict)
        
        return conflicts
    
    def resolve_conflicts(self, conflicts: List[ModConflict], auto_resolve: bool = False) -> Dict[str, Any]:
        """Resolve conflicts automatically or provide resolution suggestions."""
        resolution_plan = {
            "auto_resolved": [],
            "manual_actions_required": [],
            "suggestions": []
        }
        
        for conflict in conflicts:
            if conflict.auto_resolvable and auto_resolve:
                # Apply automatic resolution
                for action in conflict.resolution_actions:
                    resolution_plan["auto_resolved"].append({
                        "conflict_id": conflict.id,
                        "action": action,
                        "description": conflict.description
                    })
            else:
                # Add to manual actions
                resolution_plan["manual_actions_required"].append({
                    "conflict_id": conflict.id,
                    "type": conflict.type.value,
                    "severity": conflict.severity.value,
                    "description": conflict.description,
                    "suggested_resolution": conflict.suggested_resolution,
                    "affected_mods": conflict.affected_mods
                })
        
        return resolution_plan
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two mod names."""
        # Simple Levenshtein distance-based similarity
        def levenshtein_distance(s1: str, s2: str) -> int:
            if len(s1) < len(s2):
                return levenshtein_distance(s2, s1)
            
            if len(s2) == 0:
                return len(s1)
            
            previous_row = list(range(len(s2) + 1))
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
            
            return previous_row[-1]
        
        max_len = max(len(name1), len(name2))
        if max_len == 0:
            return 1.0
        
        distance = levenshtein_distance(name1, name2)
        return 1.0 - (distance / max_len)
    
    def _select_best_mod(self, mods: List[ModInfo]) -> ModInfo:
        """Select the best mod from a group of similar mods."""
        # Priority: official > popular > recent > stable
        
        # For now, simple heuristic: prefer the one with more downloads (if available)
        # or the first one alphabetically
        return sorted(mods, key=lambda m: m.name)[0]
    
    def _find_circular_dependencies(self, mods: List[ModInfo]) -> List[List[str]]:
        """Find circular dependencies using DFS."""
        # Build dependency graph
        graph = {}
        for mod in mods:
            graph[_normalize_mod_id(mod.id)] = [_normalize_mod_id(dep) for dep in (mod.dependencies or [])]
        
        def dfs(node: str, path: List[str], visited: Set[str]) -> List[List[str]]:
            if node in path:
                # Found cycle
                cycle_start = path.index(node)
                return [path[cycle_start:] + [node]]
            
            if node in visited or node not in graph:
                return []
            
            visited.add(node)
            cycles = []
            
            for neighbor in graph[node]:
                cycles.extend(dfs(neighbor, path + [node], visited))
            
            return cycles
        
        all_cycles = []
        visited = set()
        
        for mod_id in graph:
            if mod_id not in visited:
                cycles = dfs(mod_id, [], visited)
                all_cycles.extend(cycles)
        
        return all_cycles
    
    def update_compatibility_data(self, mod_id: str, compatibility: ModCompatibility):
        """Update compatibility data for a mod."""
        self.compatibility_data[mod_id] = compatibility
        
        # Save to file
        data = {mod_id: asdict(compat) for mod_id, compat in self.compatibility_data.items()}
        with open(self.compatibility_db, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def add_known_conflict(self, conflict: ModConflict):
        """Add a known conflict to the database."""
        self.known_conflicts[conflict.id] = conflict
        
        # Save to file
        data = {}
        for conflict_id, conflict_obj in self.known_conflicts.items():
            conflict_dict = asdict(conflict_obj)
            # Convert enums to strings for JSON serialization
            conflict_dict['type'] = conflict_obj.type.value
            conflict_dict['severity'] = conflict_obj.severity.value
            data[conflict_id] = conflict_dict
        
        with open(self.conflicts_db, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def get_conflict_statistics(self) -> Dict[str, Any]:
        """Get statistics about conflicts."""
        return {
            "total_known_conflicts": len(self.known_conflicts),
            "conflicts_by_type": {
                conflict_type.value: sum(1 for c in self.known_conflicts.values() 
                                       if c.type == conflict_type)
                for conflict_type in ConflictType
            },
            "conflicts_by_severity": {
                severity.value: sum(1 for c in self.known_conflicts.values() 
                                  if c.severity == severity)
                for severity in ConflictSeverity
            },
            "auto_resolvable_conflicts": sum(1 for c in self.known_conflicts.values() 
                                           if c.auto_resolvable),
            "compatibility_entries": len(self.compatibility_data)
        }