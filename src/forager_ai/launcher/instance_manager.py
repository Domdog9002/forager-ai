"""
Minecraft Instance Management
Handles creation, configuration, and management of Minecraft instances.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, asdict, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..fs.safe_writer import write_text_utf8_nobom


@dataclass
class MinecraftInstance:
    """Represents a Minecraft instance configuration."""
    name: str
    minecraft_version: str
    loader: str  # forge, fabric, quilt, vanilla
    loader_version: str
    java_version: str
    memory_min: int  # MB
    memory_max: int  # MB
    instance_path: str
    created_at: str
    last_played: Optional[str] = None
    play_time: int = 0  # minutes
    mods_count: int = 0
    icon: Optional[str] = None
    description: str = ""
    tags: List[str] = None
    linked_source: Optional[str] = None  # curseforge | modrinth when linked from another launcher
    linked_external_id: Optional[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class InstanceManager:
    """Manages Minecraft instances for the launcher."""
    
    def __init__(self, launcher_dir: str):
        self.launcher_dir = Path(launcher_dir)
        self.instances_dir = self.launcher_dir / "instances"
        self.instances_config = self.launcher_dir / "instances.json"
        
        # Ensure directories exist
        self.instances_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing instances
        self.instances: Dict[str, MinecraftInstance] = self._load_instances()
    
    def _load_instances(self) -> Dict[str, MinecraftInstance]:
        """Load instances from configuration file."""
        if not self.instances_config.exists():
            return {}
        
        try:
            with open(self.instances_config, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            instances: Dict[str, MinecraftInstance] = {}
            valid_keys = {f.name for f in fields(MinecraftInstance)}
            for name, config in data.items():
                if not isinstance(config, dict):
                    continue
                clean = {k: v for k, v in config.items() if k in valid_keys}
                try:
                    instances[name] = MinecraftInstance(**clean)
                except TypeError as e:
                    print(f"Skipping instance {name!r}: {e}")
            return instances
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"Error loading instances config: {e}")
            return {}
    
    def _save_instances(self) -> None:
        """Save instances to configuration file."""
        data = {}
        for name, instance in self.instances.items():
            data[name] = asdict(instance)
        
        write_text_utf8_nobom(
            str(self.instances_config),
            json.dumps(data, indent=2, ensure_ascii=False)
        )
    
    def create_instance(
        self,
        name: str,
        minecraft_version: str,
        loader: str = "forge",
        loader_version: str = "latest",
        java_version: str = "17",
        memory_min: int = 2048,
        memory_max: int = 4096,
        description: str = "",
        tags: List[str] = None
    ) -> MinecraftInstance:
        """Create a new Minecraft instance."""
        if name in self.instances:
            raise ValueError(f"Instance '{name}' already exists")
        
        # Create instance directory structure
        instance_path = self.instances_dir / name
        instance_path.mkdir(exist_ok=True)
        
        # Create standard Minecraft directories
        (instance_path / "mods").mkdir(exist_ok=True)
        (instance_path / "config").mkdir(exist_ok=True)
        (instance_path / "resourcepacks").mkdir(exist_ok=True)
        (instance_path / "shaderpacks").mkdir(exist_ok=True)
        (instance_path / "datapacks").mkdir(exist_ok=True)
        (instance_path / "saves").mkdir(exist_ok=True)
        (instance_path / "screenshots").mkdir(exist_ok=True)
        (instance_path / "logs").mkdir(exist_ok=True)
        
        # Create instance object
        instance = MinecraftInstance(
            name=name,
            minecraft_version=minecraft_version,
            loader=loader,
            loader_version=loader_version,
            java_version=java_version,
            memory_min=memory_min,
            memory_max=memory_max,
            instance_path=str(instance_path),
            created_at=datetime.now(timezone.utc).isoformat(),
            description=description,
            tags=tags or []
        )
        
        # Add to instances and save
        self.instances[name] = instance
        self._save_instances()
        
        return instance
    
    def delete_instance(self, name: str, delete_files: bool = True) -> bool:
        """Delete an instance."""
        if name not in self.instances:
            return False
        
        instance = self.instances[name]

        linked = bool(getattr(instance, "linked_source", None))
        if delete_files and not linked:
            instance_path = Path(instance.instance_path)
            if instance_path.exists():
                shutil.rmtree(instance_path)
        
        # Remove from instances
        del self.instances[name]
        self._save_instances()
        
        return True
    
    def get_instance(self, name: str) -> Optional[MinecraftInstance]:
        """Get an instance by name."""
        return self.instances.get(name)
    
    def list_instances(self) -> List[MinecraftInstance]:
        """Get all instances."""
        return list(self.instances.values())

    @staticmethod
    def _norm_game_path(path: str) -> str:
        try:
            return os.path.normcase(os.path.normpath(os.path.expanduser(str(path))))
        except OSError:
            return ""

    def find_instance_covering_path(self, game_root: str) -> Optional[str]:
        """Instance name if this game folder is already registered, else None."""
        needle = self._norm_game_path(game_root)
        if not needle:
            return None
        for name, inst in self.instances.items():
            if self._norm_game_path(inst.instance_path) == needle:
                return name
        return None

    def _allocate_import_name(self, display_name: str) -> str:
        base = re.sub(r'[<>:"/\\|?*]+', "", (display_name or "").strip()) or "profile"
        base = re.sub(r"\s+", " ", base)[:56]
        candidate = base
        idx = 2
        while candidate in self.instances:
            suffix = f" ({idx})"
            candidate = (base[: max(1, 56 - len(suffix))] + suffix).strip()
            idx += 1
        return candidate

    def register_linked_external(self, ext: Any) -> MinecraftInstance:
        """Point a Forager instance at an existing CurseForge/Modrinth game folder (no copy)."""
        from .external_instances import ExternalInstanceInfo

        if not isinstance(ext, ExternalInstanceInfo):
            raise TypeError("Expected ExternalInstanceInfo")
        prev = self.find_instance_covering_path(ext.game_root)
        if prev:
            return self.instances[prev]
        gr = os.path.normpath(os.path.expandvars(os.path.expanduser(str(ext.game_root))))
        if not os.path.isdir(gr):
            raise ValueError(f"Not a directory: {gr}")
        name = self._allocate_import_name(ext.display_name)
        mv = (ext.minecraft_version or "").strip() or "1.20.1"
        if mv.lower() == "unknown":
            mv = "1.20.1"
        ld = (ext.loader or "forge").strip() or "forge"
        if ld.lower() in ("unknown", ""):
            ld = "forge"
        lv = (ext.loader_version or "linked").strip() or "linked"
        if str(lv).lower() == "unknown":
            lv = "linked"
        instance = MinecraftInstance(
            name=name,
            minecraft_version=mv,
            loader=ld,
            loader_version=lv,
            java_version="17",
            memory_min=2048,
            memory_max=4096,
            instance_path=gr,
            created_at=datetime.now(timezone.utc).isoformat(),
            description=f"Linked {ext.source} profile — {ext.display_name}",
            tags=[ext.source, "linked"],
            linked_source=ext.source,
            linked_external_id=ext.stable_id,
        )
        self.instances[name] = instance
        self._save_instances()
        return instance

    def sync_discovered_externals(self, config: Dict[str, Any]) -> Dict[str, int]:
        """Register each discovered CurseForge/Modrinth folder not already in the instance list."""
        from .external_instances import discover_external_instances

        imported = 0
        skipped = 0
        for ext in discover_external_instances(config):
            try:
                gr = os.path.normpath(os.path.expandvars(os.path.expanduser(str(ext.game_root))))
            except Exception:
                skipped += 1
                continue
            if not os.path.isdir(gr):
                skipped += 1
                continue
            if self.find_instance_covering_path(gr):
                skipped += 1
                continue
            try:
                self.register_linked_external(ext)
                imported += 1
            except (TypeError, ValueError):
                skipped += 1
        return {"imported": imported, "skipped": skipped}

    def update_instance(self, name: str, **kwargs) -> bool:
        """Update instance properties."""
        if name not in self.instances:
            return False
        
        instance = self.instances[name]
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        
        self._save_instances()
        return True
    
    def duplicate_instance(self, source_name: str, new_name: str) -> Optional[MinecraftInstance]:
        """Duplicate an existing instance."""
        if source_name not in self.instances or new_name in self.instances:
            return None
        
        source_instance = self.instances[source_name]
        if getattr(source_instance, "linked_source", None):
            return None
        source_path = Path(source_instance.instance_path)

        # Create new instance
        new_instance = self.create_instance(
            name=new_name,
            minecraft_version=source_instance.minecraft_version,
            loader=source_instance.loader,
            loader_version=source_instance.loader_version,
            java_version=source_instance.java_version,
            memory_min=source_instance.memory_min,
            memory_max=source_instance.memory_max,
            description=f"Copy of {source_instance.description}",
            tags=source_instance.tags.copy()
        )
        
        # Copy files (excluding saves and logs)
        new_path = Path(new_instance.instance_path)
        
        for item in ["mods", "config", "resourcepacks", "shaderpacks"]:
            source_item = source_path / item
            new_item = new_path / item
            
            if source_item.exists():
                if source_item.is_dir():
                    shutil.copytree(source_item, new_item, dirs_exist_ok=True)
                else:
                    shutil.copy2(source_item, new_item)
        
        return new_instance
    
    def get_instance_stats(self, name: str) -> Dict[str, Any]:
        """Get statistics for an instance."""
        if name not in self.instances:
            return {}
        
        instance = self.instances[name]
        instance_path = Path(instance.instance_path)
        
        stats = {
            "mods_count": 0,
            "resourcepacks_count": 0,
            "shaderpacks_count": 0,
            "saves_count": 0,
            "total_size_mb": 0,
            "last_modified": None
        }
        
        # Count files in each directory
        for directory, key in [
            ("mods", "mods_count"),
            ("resourcepacks", "resourcepacks_count"), 
            ("shaderpacks", "shaderpacks_count"),
            ("saves", "saves_count")
        ]:
            dir_path = instance_path / directory
            if dir_path.exists():
                stats[key] = len([f for f in dir_path.iterdir() if f.is_file()])
        
        # Calculate total size
        total_size = 0
        if instance_path.exists():
            for root, dirs, files in os.walk(instance_path):
                for file in files:
                    try:
                        total_size += os.path.getsize(os.path.join(root, file))
                    except (OSError, FileNotFoundError):
                        pass
        
        stats["total_size_mb"] = round(total_size / (1024 * 1024), 2)
        
        # Update instance mods count
        if stats["mods_count"] != instance.mods_count:
            self.update_instance(name, mods_count=stats["mods_count"])
        
        return stats