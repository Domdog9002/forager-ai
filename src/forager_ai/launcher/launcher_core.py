"""
Launcher Core
Main launcher class that coordinates all components.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

from .instance_manager import InstanceManager, MinecraftInstance
from .mod_downloader import ModDownloader, ModInfo
from .version_manager import VersionManager, MinecraftVersion, LoaderVersion, JavaVersion
from ..ai.openrouter_client import generate_feature_payload
from ..ai.council import load_recent_lessons
from ..ai.model_resolve import resolve_ai_model
from ..pack.manifest import init_pack_manifest, load_pack_manifest
from ..backend.conflict_resolver import ConflictResolver
from ..backend.conflict_scan import build_install_preflight_report

# Main / balanced path: strong general model. Fast tier stays cheaper for quick passes.
DEFAULT_AI_ROUTER_CHAT_MODEL = "openai/gpt-4o"
DEFAULT_AI_ROUTER_FAST_MODEL = "openai/gpt-4o-mini"
# Quality + default Council fallback: flagship OpenRouter slug (change in Settings if needed).
DEFAULT_AI_ROUTER_QUALITY_MODEL = "anthropic/claude-3.5-sonnet"
FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY = "_forager_launcher_router_defaults_rev1"
FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY_REV2 = "_forager_launcher_router_defaults_rev2"


def apply_legacy_router_model_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    """One-shot upgrade away from unset routing (`openrouter/auto`) toward stronger tier defaults."""
    if config.get(FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY):
        return config
    out = dict(config)
    out[FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY] = True
    balanced = str(out.get("ai_model_balanced") or "").strip()
    main = str(out.get("ai_model") or "").strip()
    if not balanced and main in ("openrouter/auto", ""):
        out["ai_model"] = DEFAULT_AI_ROUTER_CHAT_MODEL
        out["ai_model_balanced"] = DEFAULT_AI_ROUTER_CHAT_MODEL
    if str(out.get("ai_model_fast") or "").strip() == "openrouter/auto":
        out["ai_model_fast"] = DEFAULT_AI_ROUTER_FAST_MODEL
    if str(out.get("ai_model_quality") or "").strip() == "openrouter/auto":
        out["ai_model_quality"] = DEFAULT_AI_ROUTER_QUALITY_MODEL
    return out


def apply_frontier_router_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    """Second-stage upgrade: mini→4o main path, GPT-4o→Sonnet quality, optional preset→quality."""
    if config.get(FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY_REV2):
        return config
    out = dict(config)
    out[FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY_REV2] = True
    _mini = "openai/gpt-4o-mini"
    _prev_quality = "openai/gpt-4o"

    main = str(out.get("ai_model") or "").strip()
    balanced_slot = str(out.get("ai_model_balanced") or "").strip()
    if main == _mini and not balanced_slot:
        out["ai_model"] = DEFAULT_AI_ROUTER_CHAT_MODEL

    if str(out.get("ai_model_quality") or "").strip() == _prev_quality:
        out["ai_model_quality"] = DEFAULT_AI_ROUTER_QUALITY_MODEL

    preset = str(out.get("ai_model_preset") or "").strip().lower()
    main2 = str(out.get("ai_model") or "").strip()
    bal2 = str(out.get("ai_model_balanced") or "").strip()
    _no_balanced_override = (not bal2) or (bal2 == main2)
    if preset == "balanced" and main2 == DEFAULT_AI_ROUTER_CHAT_MODEL and _no_balanced_override:
        out["ai_model_preset"] = "quality"
    return out


@dataclass
class LaunchConfig:
    """Configuration for launching Minecraft."""
    instance_name: str
    java_path: str
    memory_min: int
    memory_max: int
    additional_args: List[str] = None
    
    def __post_init__(self):
        if self.additional_args is None:
            self.additional_args = []


class LauncherCore:
    """Main launcher class that coordinates all functionality."""
    
    def __init__(self, launcher_dir: str = None):
        if launcher_dir is None:
            launcher_dir = os.path.join(os.path.expanduser("~"), ".forager_ai")
        
        self.launcher_dir = Path(launcher_dir)
        self.launcher_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.instance_manager = InstanceManager(str(self.launcher_dir))
        self.mod_downloader = ModDownloader(str(self.launcher_dir / "cache"))
        self.version_manager = VersionManager(str(self.launcher_dir / "cache"))
        self.conflict_resolver = ConflictResolver(str(self.launcher_dir / "conflicts"))
        
        # Configuration
        self.config_file = self.launcher_dir / "launcher_config.json"
        self.config = self._load_config()
        self.mod_downloader.set_curseforge_api_key(self.config.get("curseforge_api_key", ""))
        self._config_mtime_loaded: Optional[float] = self._config_file_mtime()

        # Launch tracking
        self.running_instances: Dict[str, subprocess.Popen] = {}
    
    def _load_config(self) -> Dict[str, Any]:
        """Load launcher configuration."""
        default_config = {
            "theme": "dark",
            "auto_update_mods": True,
            "show_snapshots": False,
            "default_memory": 4096,
            "java_args": ["-XX:+UseG1GC", "-XX:+UnlockExperimentalVMOptions"],
            "openrouter_api_key": "",
            "curseforge_api_key": "",
            "ai_model": DEFAULT_AI_ROUTER_CHAT_MODEL,
            "ai_model_preset": "quality",
            "ai_model_fast": DEFAULT_AI_ROUTER_FAST_MODEL,
            "ai_model_balanced": "",
            "ai_model_quality": DEFAULT_AI_ROUTER_QUALITY_MODEL,
            "ai_model_council": "",
            FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY: True,
            FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY_REV2: True,
            "embedding_rag": True,
            "embedding_model": "openai/text-embedding-3-small",
            "launch_mode": "embedded_only",
            "content_atlas_auto_council_on_rebuild": False,
            "content_atlas_prompt_recurring_review": True,
            "curseforge_instances_root": "",
            "modrinth_profiles_root": "",
            "forge_mdk_root": "",
            "devkit_bindings": {},
            "catalog_pins": [],
            "ai_apply_blocked": False,
            "ai_writes_require_preview": False,
            "catalog_offline_mode": False,
            "catalog_pin_drift_auto": False,
            # Forager Hub assistant: persisted chat transcript (.forager/hub_chat_tape.json) + optional auto Council.
            "hub_chat_turn_limit": 260,
            "hub_auto_council_validation": False,
            # Local-only preflight telemetry queue (see ``preflight_telemetry.py``); no network upload.
            "preflight_telemetry_enabled": False,
            "preflight_telemetry_include_paths": False,
            "home_pinned_widgets": [],
        }
        
        if not self.config_file.exists():
            self._save_config(default_config)
            return dict(default_config)

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            had_r1 = FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY in config
            had_r2 = FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY_REV2 in config
            # Merge defaults (migration markers excluded — migrations own these)
            for key, value in default_config.items():
                if key in (FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY, FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY_REV2):
                    continue
                if key not in config:
                    config[key] = value
            config = apply_legacy_router_model_defaults(config)
            config = apply_frontier_router_defaults(config)
            if not had_r1 or not had_r2:
                self._save_config(config)
            return config
        except (json.JSONDecodeError, IOError):
            return dict(default_config)

    def _config_file_mtime(self) -> Optional[float]:
        try:
            return float(self.config_file.stat().st_mtime)
        except OSError:
            return None

    def reload_config_from_disk_if_changed(self) -> bool:
        """If ``launcher_config.json`` changed since last load, merge into ``self.config`` and refresh CurseForge client.

        Streamlit keeps a long-lived ``LauncherCore`` in ``@st.cache_resource``; this lets saved API keys apply on the
        next rerun without restarting the process.
        """
        mt = self._config_file_mtime()
        if mt is None:
            return False
        prev = getattr(self, "_config_mtime_loaded", None)
        if prev is not None and mt == prev:
            return False
        self.config = self._load_config()
        self.mod_downloader.set_curseforge_api_key(self.config.get("curseforge_api_key", ""))
        self._config_mtime_loaded = mt
        return True

    def _save_config(self, config: Dict[str, Any] = None):
        """Save launcher configuration."""
        if config is None:
            config = self.config
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
    
    def update_config(self, **kwargs):
        """Update launcher configuration."""
        self.config.update(kwargs)
        self._save_config()
        if "curseforge_api_key" in kwargs:
            self.mod_downloader.set_curseforge_api_key(self.config.get("curseforge_api_key", ""))
        mt = self._config_file_mtime()
        if mt is not None:
            self._config_mtime_loaded = mt
    
    # Instance Management
    def create_instance(
        self,
        name: str,
        minecraft_version: str,
        loader: str = "forge",
        loader_version: str = "latest",
        description: str = "",
        tags: List[str] = None,
        install_ai_features: bool = True
    ) -> MinecraftInstance:
        """Create a new Minecraft instance with AI integration."""
        # Find compatible Java version
        java = self.version_manager.find_compatible_java(minecraft_version)
        if not java:
            raise RuntimeError(f"No compatible Java installation found for Minecraft {minecraft_version}")
        
        # Create the instance
        instance = self.instance_manager.create_instance(
            name=name,
            minecraft_version=minecraft_version,
            loader=loader,
            loader_version=loader_version,
            java_version=str(java.major_version),
            memory_min=2048,
            memory_max=self.config.get("default_memory", 4096),
            description=description,
            tags=tags or []
        )
        
        # Initialize pack manifest for AI features
        if install_ai_features:
            init_pack_manifest(
                instance.instance_path,
                pack_id=name,
                minecraft_version=minecraft_version,
                loader=loader
            )
        
        return instance
    
    def launch_instance(
        self,
        instance_name: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """Launch a Minecraft instance."""
        instance = self.instance_manager.get_instance(instance_name)
        if not instance:
            return False
        
        if progress_callback:
            progress_callback("Preparing launch...")
        
        # Find Java installation
        java = self.version_manager.find_compatible_java(instance.minecraft_version)
        if not java:
            if progress_callback:
                progress_callback("Error: No compatible Java found")
            return False
        
        # Build launch command
        java_exe = os.path.join(java.path, "bin", "java.exe" if os.name == "nt" else "java")
        
        launch_args = [
            java_exe,
            f"-Xms{instance.memory_min}M",
            f"-Xmx{instance.memory_max}M",
            f"-Djava.library.path={instance.instance_path}/natives",
            f"-Dminecraft.launcher.brand=ForagerAI",
            f"-Dminecraft.launcher.version=1.0.0",
        ]
        
        # Add custom Java args
        launch_args.extend(self.config.get("java_args", []))
        
        # Add classpath and main class (simplified - would need proper Minecraft launcher logic)
        launch_args.extend([
            "-cp", f"{instance.instance_path}/libraries/*:{instance.instance_path}/minecraft.jar",
            "net.minecraft.client.main.Main",
            "--username", "Player",
            "--version", instance.minecraft_version,
            "--gameDir", instance.instance_path,
            "--assetsDir", f"{instance.instance_path}/assets",
            "--assetIndex", instance.minecraft_version,
        ])
        
        try:
            if progress_callback:
                progress_callback("Starting Minecraft...")
            
            # Launch the process
            process = subprocess.Popen(
                launch_args,
                cwd=instance.instance_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.running_instances[instance_name] = process
            
            # Update instance stats
            self.instance_manager.update_instance(
                instance_name,
                last_played=time.strftime("%Y-%m-%d %H:%M:%S")
            )
            
            if progress_callback:
                progress_callback("Minecraft launched successfully!")
            
            return True
            
        except Exception as e:
            if progress_callback:
                progress_callback(f"Launch failed: {e}")
            return False
    
    def stop_instance(self, instance_name: str) -> bool:
        """Stop a running Minecraft instance."""
        if instance_name not in self.running_instances:
            return False
        
        process = self.running_instances[instance_name]
        try:
            process.terminate()
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        
        del self.running_instances[instance_name]
        return True
    
    def is_instance_running(self, instance_name: str) -> bool:
        """Check if an instance is currently running."""
        if instance_name not in self.running_instances:
            return False
        
        process = self.running_instances[instance_name]
        return process.poll() is None
    
    # Mod Management with AI
    def search_mods(
        self,
        query: str,
        minecraft_version: str = None,
        loader: str = None,
        limit: int = 20,
        sources: List[str] = None,
        curseforge_sort_field: int = 6,
        page: int = 1,
        modrinth_index: str = "relevance",
        catalog_kind: str = "mods",
    ) -> List[ModInfo]:
        """Search for mods and other Minecraft catalog kinds across Modrinth and/or CurseForge."""
        return self.mod_downloader.search_all_sources(
            query=query,
            minecraft_version=minecraft_version,
            loader=loader,
            limit=limit,
            sources=sources,
            curseforge_sort_field=curseforge_sort_field,
            page=page,
            modrinth_index=modrinth_index,
            catalog_kind=catalog_kind,
        )

    @staticmethod
    def _catalog_subdir_for_kind(kind: str) -> str:
        k = (kind or "mods").strip().lower()
        return {
            "mods": "mods",
            "resourcepack": "resourcepacks",
            "shader": "shaderpacks",
            "datapack": "datapacks",
            "modpack": "modpack_downloads",
        }.get(k, "mods")

    def preflight_catalog_install(
        self,
        pack_root: str,
        mod_info: ModInfo,
        *,
        pack_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Simulate adding a mod to a pack/instance and return compatibility risk."""
        root = Path(pack_root).resolve()
        try:
            manifest = load_pack_manifest(str(root))
        except FileNotFoundError:
            manifest = init_pack_manifest(
                str(root),
                pack_id=pack_name or root.name,
                minecraft_version=(mod_info.minecraft_versions or ["1.20.1"])[0],
                loader=(mod_info.loaders or ["forge"])[0],
            )
        return build_install_preflight_report(
            resolver=self.conflict_resolver,
            manifest=manifest,
            pack_root=str(root),
            pack_name=pack_name or root.name,
            candidate=mod_info,
        )

    def preflight_instance_install(self, instance_name: str, mod_info: ModInfo) -> Dict[str, Any]:
        """Simulate adding a mod to a managed instance."""
        instance = self.instance_manager.get_instance(instance_name)
        if not instance:
            return {
                "decision": "block",
                "message": "Instance not found.",
                "summary": {},
                "conflicts": [],
                "resolution_plan": {},
            }
        return self.preflight_catalog_install(
            instance.instance_path,
            mod_info,
            pack_name=instance.name,
        )

    def install_catalog_item(
        self,
        instance_name: str,
        mod_info: ModInfo,
        catalog_kind: str = "mods",
        install_dependencies: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """Download a catalog item into the correct folder under an instance (mods, resourcepacks, …)."""
        instance = self.instance_manager.get_instance(instance_name)
        if not instance:
            return False

        sub = self._catalog_subdir_for_kind(catalog_kind)
        dest_dir = os.path.join(instance.instance_path, sub)
        os.makedirs(dest_dir, exist_ok=True)

        result = self.mod_downloader.download_mod(
            mod_info,
            dest_dir,
            progress_callback,
        )
        if not result:
            return False

        k = (catalog_kind or "mods").strip().lower()
        if install_dependencies and k == "mods":
            dependencies = self.mod_downloader.get_mod_dependencies(mod_info)
            for dep in dependencies:
                self.mod_downloader.download_mod(dep, dest_dir)

        return True

    def install_catalog_into_pack(
        self,
        pack_root: str,
        mod_info: ModInfo,
        catalog_kind: str = "mods",
        install_dependencies: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """Download into ``pack_root/<subdir>/`` (e.g. ``packs/MyPack/resourcepacks``)."""
        root = Path(pack_root).resolve()
        sub = self._catalog_subdir_for_kind(catalog_kind)
        dest_dir = root / sub
        dest_dir.mkdir(parents=True, exist_ok=True)

        result = self.mod_downloader.download_mod(
            mod_info,
            str(dest_dir),
            progress_callback,
        )
        if not result:
            return False

        k = (catalog_kind or "mods").strip().lower()
        if install_dependencies and k == "mods":
            dependencies = self.mod_downloader.get_mod_dependencies(mod_info)
            for dep in dependencies:
                self.mod_downloader.download_mod(dep, str(dest_dir))

        return True

    def install_mod(
        self,
        instance_name: str,
        mod_info: ModInfo,
        install_dependencies: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """Install a mod jar into the instance ``mods/`` folder."""
        return self.install_catalog_item(
            instance_name,
            mod_info,
            catalog_kind="mods",
            install_dependencies=install_dependencies,
            progress_callback=progress_callback,
        )

    def install_mod_into_mods_dir(
        self,
        mods_dir: str,
        mod_info: ModInfo,
        install_dependencies: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """Download a mod into an explicit ``mods`` folder (e.g. under ``packs/MyPack/mods``)."""
        path = Path(mods_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)

        result = self.mod_downloader.download_mod(
            mod_info,
            str(path),
            progress_callback,
        )
        if not result:
            return False

        if install_dependencies:
            dependencies = self.mod_downloader.get_mod_dependencies(mod_info)
            for dep in dependencies:
                self.mod_downloader.download_mod(dep, str(path))

        return True
    
    def ai_suggest_mods(
        self,
        instance_name: str,
        request: str,
        api_key: str = None
    ) -> Dict[str, Any]:
        """Use AI to suggest mods for an instance."""
        instance = self.instance_manager.get_instance(instance_name)
        if not instance:
            return {"error": "Instance not found"}
        
        # Load pack manifest for context
        try:
            manifest = load_pack_manifest(instance.instance_path)
        except FileNotFoundError:
            # Initialize manifest if it doesn't exist
            manifest = init_pack_manifest(
                instance.instance_path,
                pack_id=instance.name,
                minecraft_version=instance.minecraft_version,
                loader=instance.loader
            )
        
        # Use AI to generate suggestions
        if not api_key:
            api_key = self.config.get("openrouter_api_key", "")
        
        if not api_key:
            return {"error": "OpenRouter API key not configured"}
        
        try:
            ai_response = generate_feature_payload(
                api_key=api_key,
                model=resolve_ai_model(self.config),
                user_request=f"Suggest mods for: {request}",
                pack_context=manifest,
                prior_lessons=load_recent_lessons(),
            )
            
            # Parse AI suggestions and search for actual mods
            suggestions = []
            explanation = ai_response.get("explanation", "")
            
            # Extract mod names from the AI response (simplified)
            # In a real implementation, you'd parse the feature_plan more thoroughly
            feature_plan = ai_response.get("feature_plan", {})
            
            return {
                "explanation": explanation,
                "feature_plan": feature_plan,
                "suggestions": suggestions
            }
            
        except Exception as e:
            return {"error": f"AI suggestion failed: {e}"}
    
    def ai_create_feature(
        self,
        instance_name: str,
        feature_request: str,
        api_key: str = None
    ) -> Dict[str, Any]:
        """Use AI to create a custom feature for an instance."""
        instance = self.instance_manager.get_instance(instance_name)
        if not instance:
            return {"error": "Instance not found"}
        
        # Load pack manifest
        try:
            manifest = load_pack_manifest(instance.instance_path)
        except FileNotFoundError:
            manifest = init_pack_manifest(
                instance.instance_path,
                pack_id=instance.name,
                minecraft_version=instance.minecraft_version,
                loader=instance.loader
            )
        
        if not api_key:
            api_key = self.config.get("openrouter_api_key", "")
        
        if not api_key:
            return {"error": "OpenRouter API key not configured"}
        
        try:
            return generate_feature_payload(
                api_key=api_key,
                model=resolve_ai_model(self.config),
                user_request=feature_request,
                pack_context=manifest,
                prior_lessons=load_recent_lessons(),
            )
        except Exception as e:
            return {"error": f"Feature creation failed: {e}"}
    
    # Content Management
    def install_resource_pack(
        self,
        instance_name: str,
        resource_pack_path: str
    ) -> bool:
        """Install a resource pack to an instance."""
        instance = self.instance_manager.get_instance(instance_name)
        if not instance:
            return False
        
        resourcepacks_dir = os.path.join(instance.instance_path, "resourcepacks")
        destination = os.path.join(resourcepacks_dir, os.path.basename(resource_pack_path))
        
        try:
            if os.path.isfile(resource_pack_path):
                # Copy file
                import shutil
                shutil.copy2(resource_pack_path, destination)
            elif os.path.isdir(resource_pack_path):
                # Copy directory
                import shutil
                shutil.copytree(resource_pack_path, destination, dirs_exist_ok=True)
            else:
                return False
            
            return True
        except (OSError, IOError):
            return False
    
    def install_shader_pack(
        self,
        instance_name: str,
        shader_pack_path: str
    ) -> bool:
        """Install a shader pack to an instance."""
        instance = self.instance_manager.get_instance(instance_name)
        if not instance:
            return False
        
        shaderpacks_dir = os.path.join(instance.instance_path, "shaderpacks")
        destination = os.path.join(shaderpacks_dir, os.path.basename(shader_pack_path))
        
        try:
            import shutil
            shutil.copy2(shader_pack_path, destination)
            return True
        except (OSError, IOError):
            return False
    
    # System Information
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information for diagnostics."""
        java_installations = self.version_manager.scan_java_installations()
        
        return {
            "launcher_version": "1.0.0",
            "launcher_dir": str(self.launcher_dir),
            "java_installations": [
                {
                    "version": j.version,
                    "path": j.path,
                    "vendor": j.vendor,
                    "architecture": j.architecture
                }
                for j in java_installations
            ],
            "instances_count": len(self.instance_manager.list_instances()),
            "running_instances": list(self.running_instances.keys()),
            "config": self.config
        }
    
    def cleanup(self):
        """Cleanup launcher resources."""
        # Stop all running instances
        for instance_name in list(self.running_instances.keys()):
            self.stop_instance(instance_name)
        
        # Save configuration
        self._save_config()