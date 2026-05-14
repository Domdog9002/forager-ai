"""
Content Management System
Comprehensive system for managing texture packs, animations, resource packs, and custom content.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from PIL import Image
import base64
from io import BytesIO

from .blockbench_models import bbmodel_to_json, build_bbmodel_project, validate_bbmodel
from .sound_forge import render_sound_effect, sound_report_json, write_wav
from .texture_forge import model_json_for_spec, render_animation_strip, render_texture_asset
from .texture_workshop import (
    export_blockbench_sources,
    rollback_latest,
    save_export_report,
    validate_texture_forge_export,
)
from ..fs.safe_writer import write_text_utf8_nobom


@dataclass
class ResourcePack:
    """Represents a Minecraft resource pack."""
    name: str
    description: str
    pack_format: int
    path: str
    version: str = "1.0.0"
    author: str = "Unknown"
    icon: Optional[str] = None  # Base64 encoded image
    size_mb: float = 0.0
    created_at: str = ""
    modified_at: str = ""
    compatible_versions: List[str] = None
    tags: List[str] = None
    
    def __post_init__(self):
        if self.compatible_versions is None:
            self.compatible_versions = []
        if self.tags is None:
            self.tags = []


@dataclass
class TextureAsset:
    """Represents a texture asset."""
    name: str
    path: str
    category: str  # blocks, items, entities, gui, etc.
    dimensions: tuple[int, int]
    format: str  # png, jpg, etc.
    animated: bool = False
    frames: int = 1
    frame_time: int = 1
    interpolate: bool = False
    
    @property
    def is_valid_minecraft_texture(self) -> bool:
        """Check if texture dimensions are valid for Minecraft."""
        width, height = self.dimensions
        # Minecraft textures should be power of 2 and square for most cases
        return width == height and (width & (width - 1)) == 0


class ContentManager:
    """Main content management system."""
    
    def __init__(self, content_dir: str):
        self.content_dir = Path(content_dir)
        self.content_dir.mkdir(parents=True, exist_ok=True)
        
        # Content directories
        self.resource_packs_dir = self.content_dir / "resource_packs"
        self.textures_dir = self.content_dir / "textures"
        self.animations_dir = self.content_dir / "animations"
        self.templates_dir = self.content_dir / "templates"
        
        # Create directories
        for directory in [self.resource_packs_dir, self.textures_dir, 
                         self.animations_dir, self.templates_dir]:
            directory.mkdir(exist_ok=True)
        
        # Content registry
        self.registry_file = self.content_dir / "content_registry.json"
        self.registry = self._load_registry()
    
    def _load_registry(self) -> Dict[str, Any]:
        """Load content registry."""
        if not self.registry_file.exists():
            return {
                "resource_packs": {},
                "textures": {},
                "animations": {},
                "templates": {}
            }
        
        try:
            with open(self.registry_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {
                "resource_packs": {},
                "textures": {},
                "animations": {},
                "templates": {}
            }
    
    def _save_registry(self):
        """Save content registry."""
        write_text_utf8_nobom(
            str(self.registry_file),
            json.dumps(self.registry, indent=2, ensure_ascii=False)
        )
    
    def create_resource_pack(
        self,
        name: str,
        description: str,
        pack_format: int = 15,  # 1.20.1 format
        author: str = "ForagerAI User"
    ) -> ResourcePack:
        """Create a new resource pack."""
        pack_dir = self.resource_packs_dir / name
        pack_dir.mkdir(exist_ok=True)
        
        # Create pack.mcmeta
        pack_mcmeta = {
            "pack": {
                "pack_format": pack_format,
                "description": description
            }
        }
        
        mcmeta_path = pack_dir / "pack.mcmeta"
        write_text_utf8_nobom(
            str(mcmeta_path),
            json.dumps(pack_mcmeta, indent=2)
        )
        
        # Create basic directory structure
        (pack_dir / "assets" / "minecraft" / "textures" / "block").mkdir(parents=True, exist_ok=True)
        (pack_dir / "assets" / "minecraft" / "textures" / "item").mkdir(parents=True, exist_ok=True)
        (pack_dir / "assets" / "minecraft" / "textures" / "entity").mkdir(parents=True, exist_ok=True)
        (pack_dir / "assets" / "minecraft" / "textures" / "gui").mkdir(parents=True, exist_ok=True)
        (pack_dir / "assets" / "minecraft" / "models").mkdir(parents=True, exist_ok=True)
        (pack_dir / "assets" / "minecraft" / "blockstates").mkdir(parents=True, exist_ok=True)
        
        # Create resource pack object
        resource_pack = ResourcePack(
            name=name,
            description=description,
            pack_format=pack_format,
            path=str(pack_dir),
            author=author,
            created_at=self._get_timestamp(),
            modified_at=self._get_timestamp()
        )
        
        # Register the pack
        self.registry["resource_packs"][name] = asdict(resource_pack)
        self._save_registry()
        
        return resource_pack
    
    def import_resource_pack(self, pack_path: str) -> Optional[ResourcePack]:
        """Import an existing resource pack."""
        pack_path = Path(pack_path)
        
        if not pack_path.exists():
            return None
        
        # Handle zip files
        if pack_path.suffix.lower() == '.zip':
            return self._import_zip_resource_pack(pack_path)
        
        # Handle directories
        elif pack_path.is_dir():
            return self._import_directory_resource_pack(pack_path)
        
        return None
    
    def _import_zip_resource_pack(self, zip_path: Path) -> Optional[ResourcePack]:
        """Import resource pack from zip file."""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                # Find pack.mcmeta
                mcmeta_content = None
                for file_info in zip_file.filelist:
                    if file_info.filename.endswith('pack.mcmeta'):
                        mcmeta_content = zip_file.read(file_info.filename).decode('utf-8')
                        break
                
                if not mcmeta_content:
                    return None
                
                # Parse pack.mcmeta
                mcmeta = json.loads(mcmeta_content)
                pack_info = mcmeta.get("pack", {})
                
                # Extract to resource packs directory
                pack_name = zip_path.stem
                pack_dir = self.resource_packs_dir / pack_name
                
                # Remove existing if present
                if pack_dir.exists():
                    shutil.rmtree(pack_dir)
                
                zip_file.extractall(pack_dir)
                
                # Create resource pack object
                resource_pack = ResourcePack(
                    name=pack_name,
                    description=pack_info.get("description", "Imported resource pack"),
                    pack_format=pack_info.get("pack_format", 15),
                    path=str(pack_dir),
                    size_mb=round(zip_path.stat().st_size / (1024 * 1024), 2),
                    created_at=self._get_timestamp(),
                    modified_at=self._get_timestamp()
                )
                
                # Register the pack
                self.registry["resource_packs"][pack_name] = asdict(resource_pack)
                self._save_registry()
                
                return resource_pack
                
        except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as e:
            print(f"Error importing zip resource pack: {e}")
            return None
    
    def _import_directory_resource_pack(self, pack_dir: Path) -> Optional[ResourcePack]:
        """Import resource pack from directory."""
        mcmeta_path = pack_dir / "pack.mcmeta"
        if not mcmeta_path.exists():
            return None
        
        try:
            with open(mcmeta_path, 'r', encoding='utf-8') as f:
                mcmeta = json.load(f)
            
            pack_info = mcmeta.get("pack", {})
            
            # Copy to resource packs directory
            pack_name = pack_dir.name
            dest_dir = self.resource_packs_dir / pack_name
            
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            
            shutil.copytree(pack_dir, dest_dir)
            
            # Calculate size
            total_size = sum(
                f.stat().st_size for f in dest_dir.rglob('*') if f.is_file()
            )
            
            # Create resource pack object
            resource_pack = ResourcePack(
                name=pack_name,
                description=pack_info.get("description", "Imported resource pack"),
                pack_format=pack_info.get("pack_format", 15),
                path=str(dest_dir),
                size_mb=round(total_size / (1024 * 1024), 2),
                created_at=self._get_timestamp(),
                modified_at=self._get_timestamp()
            )
            
            # Register the pack
            self.registry["resource_packs"][pack_name] = asdict(resource_pack)
            self._save_registry()
            
            return resource_pack
            
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error importing directory resource pack: {e}")
            return None
    
    def add_texture_to_pack(
        self,
        pack_name: str,
        texture_path: str,
        minecraft_path: str,
        category: str = "block"
    ) -> bool:
        """Add a texture to a resource pack."""
        if pack_name not in self.registry["resource_packs"]:
            return False
        
        pack_info = self.registry["resource_packs"][pack_name]
        pack_dir = Path(pack_info["path"])
        
        # Determine destination path
        dest_path = pack_dir / "assets" / "minecraft" / "textures" / category / minecraft_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Copy and potentially process the texture
            texture_path = Path(texture_path)
            if texture_path.exists():
                # Validate and potentially resize texture
                processed_texture = self._process_texture(texture_path)
                if processed_texture:
                    processed_texture.save(dest_path)
                else:
                    shutil.copy2(texture_path, dest_path)
                
                # Update pack modification time
                pack_info["modified_at"] = self._get_timestamp()
                self.registry["resource_packs"][pack_name] = pack_info
                self._save_registry()
                
                return True
        except (IOError, OSError) as e:
            print(f"Error adding texture to pack: {e}")
        
        return False
    
    def _process_texture(self, texture_path: Path) -> Optional[Image.Image]:
        """Process texture for Minecraft compatibility."""
        try:
            with Image.open(texture_path) as img:
                # Convert to RGBA if not already
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                # Check if dimensions are power of 2
                width, height = img.size
                if width != height or (width & (width - 1)) != 0:
                    # Resize to nearest power of 2
                    new_size = 1
                    while new_size < max(width, height):
                        new_size *= 2
                    
                    if new_size > 1024:  # Cap at 1024x1024
                        new_size = 1024
                    
                    img = img.resize((new_size, new_size), Image.Resampling.LANCZOS)
                
                return img
                
        except Exception as e:
            print(f"Error processing texture: {e}")
            return None
    
    def create_animated_texture(
        self,
        pack_name: str,
        frames: List[str],
        minecraft_path: str,
        category: str = "block",
        frame_time: int = 1,
        interpolate: bool = False
    ) -> bool:
        """Create an animated texture from multiple frames."""
        if pack_name not in self.registry["resource_packs"]:
            return False
        
        pack_info = self.registry["resource_packs"][pack_name]
        pack_dir = Path(pack_info["path"])
        
        try:
            # Load and validate frames
            frame_images = []
            for frame_path in frames:
                img = Image.open(frame_path)
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                frame_images.append(img)
            
            # Ensure all frames are the same size
            if frame_images:
                base_size = frame_images[0].size
                for i, img in enumerate(frame_images):
                    if img.size != base_size:
                        frame_images[i] = img.resize(base_size, Image.Resampling.LANCZOS)
                
                # Create vertical strip (Minecraft animation format)
                strip_height = base_size[1] * len(frame_images)
                strip = Image.new('RGBA', (base_size[0], strip_height))
                
                for i, frame in enumerate(frame_images):
                    strip.paste(frame, (0, i * base_size[1]))
                
                # Save texture
                texture_path = pack_dir / "assets" / "minecraft" / "textures" / category / f"{minecraft_path}.png"
                texture_path.parent.mkdir(parents=True, exist_ok=True)
                strip.save(texture_path)
                
                # Create .mcmeta file for animation
                mcmeta_path = pack_dir / "assets" / "minecraft" / "textures" / category / f"{minecraft_path}.png.mcmeta"
                animation_data = {
                    "animation": {
                        "frametime": frame_time,
                        "interpolate": interpolate
                    }
                }
                
                write_text_utf8_nobom(
                    str(mcmeta_path),
                    json.dumps(animation_data, indent=2)
                )
                
                # Update pack modification time
                pack_info["modified_at"] = self._get_timestamp()
                self.registry["resource_packs"][pack_name] = pack_info
                self._save_registry()
                
                return True
                
        except Exception as e:
            print(f"Error creating animated texture: {e}")
        
        return False
    
    def export_resource_pack(self, pack_name: str, export_path: str) -> bool:
        """Export resource pack as zip file."""
        if pack_name not in self.registry["resource_packs"]:
            return False
        
        pack_info = self.registry["resource_packs"][pack_name]
        pack_dir = Path(pack_info["path"])
        export_path = Path(export_path)
        
        try:
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for file_path in pack_dir.rglob('*'):
                    if file_path.is_file():
                        arc_path = file_path.relative_to(pack_dir)
                        zip_file.write(file_path, arc_path)
            
            return True
        except Exception as e:
            print(f"Error exporting resource pack: {e}")
            return False
    
    def list_resource_packs(self) -> List[ResourcePack]:
        """Get list of all resource packs."""
        packs = []
        for pack_data in self.registry["resource_packs"].values():
            packs.append(ResourcePack(**pack_data))
        return packs
    
    def get_resource_pack(self, pack_name: str) -> Optional[ResourcePack]:
        """Get a specific resource pack."""
        if pack_name in self.registry["resource_packs"]:
            return ResourcePack(**self.registry["resource_packs"][pack_name])
        return None
    
    def delete_resource_pack(self, pack_name: str) -> bool:
        """Delete a resource pack."""
        if pack_name not in self.registry["resource_packs"]:
            return False
        
        pack_info = self.registry["resource_packs"][pack_name]
        pack_dir = Path(pack_info["path"])
        
        try:
            if pack_dir.exists():
                shutil.rmtree(pack_dir)
            
            del self.registry["resource_packs"][pack_name]
            self._save_registry()
            
            return True
        except Exception as e:
            print(f"Error deleting resource pack: {e}")
            return False
    
    def scan_pack_textures(self, pack_name: str) -> List[TextureAsset]:
        """Scan a resource pack for textures."""
        if pack_name not in self.registry["resource_packs"]:
            return []
        
        pack_info = self.registry["resource_packs"][pack_name]
        pack_dir = Path(pack_info["path"])
        textures_dir = pack_dir / "assets" / "minecraft" / "textures"
        
        textures = []
        if textures_dir.exists():
            for texture_file in textures_dir.rglob('*.png'):
                try:
                    with Image.open(texture_file) as img:
                        # Determine category from path
                        relative_path = texture_file.relative_to(textures_dir)
                        category = relative_path.parts[0] if relative_path.parts else "unknown"
                        
                        # Check for animation
                        mcmeta_file = texture_file.with_suffix('.png.mcmeta')
                        animated = mcmeta_file.exists()
                        frames = 1
                        frame_time = 1
                        interpolate = False
                        
                        if animated:
                            try:
                                with open(mcmeta_file, 'r', encoding='utf-8') as f:
                                    mcmeta = json.load(f)
                                    animation = mcmeta.get("animation", {})
                                    frame_time = animation.get("frametime", 1)
                                    interpolate = animation.get("interpolate", False)
                                    
                                    # Calculate frames from image height
                                    if img.height > img.width:
                                        frames = img.height // img.width
                            except (json.JSONDecodeError, IOError):
                                pass
                        
                        texture = TextureAsset(
                            name=texture_file.stem,
                            path=str(texture_file),
                            category=category,
                            dimensions=img.size,
                            format=img.format.lower() if img.format else 'png',
                            animated=animated,
                            frames=frames,
                            frame_time=frame_time,
                            interpolate=interpolate
                        )
                        textures.append(texture)
                        
                except Exception as e:
                    print(f"Error scanning texture {texture_file}: {e}")
        
        return textures
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
    
    def create_texture_template(
        self,
        template_name: str,
        base_texture: str,
        variations: Dict[str, Any]
    ) -> bool:
        """Create a texture template for AI generation."""
        template_data = {
            "name": template_name,
            "base_texture": base_texture,
            "variations": variations,
            "created_at": self._get_timestamp()
        }
        
        template_file = self.templates_dir / f"{template_name}.json"
        write_text_utf8_nobom(
            str(template_file),
            json.dumps(template_data, indent=2)
        )
        
        self.registry["templates"][template_name] = template_data
        self._save_registry()
        
        return True
    
    def get_pack_statistics(self, pack_name: str) -> Dict[str, Any]:
        """Get statistics for a resource pack."""
        if pack_name not in self.registry["resource_packs"]:
            return {}
        
        pack_info = self.registry["resource_packs"][pack_name]
        pack_dir = Path(pack_info["path"])
        
        stats = {
            "total_files": 0,
            "texture_files": 0,
            "model_files": 0,
            "sound_files": 0,
            "animated_textures": 0,
            "categories": {},
            "total_size_mb": 0
        }
        
        if pack_dir.exists():
            for file_path in pack_dir.rglob('*'):
                if file_path.is_file():
                    stats["total_files"] += 1
                    stats["total_size_mb"] += file_path.stat().st_size
                    
                    suffix = file_path.suffix.lower()
                    if suffix == '.png':
                        stats["texture_files"] += 1
                        
                        # Check for animation
                        mcmeta_file = file_path.with_suffix('.png.mcmeta')
                        if mcmeta_file.exists():
                            stats["animated_textures"] += 1
                        
                        # Categorize by directory
                        if 'textures' in file_path.parts:
                            try:
                                textures_idx = file_path.parts.index('textures')
                                if textures_idx + 1 < len(file_path.parts):
                                    category = file_path.parts[textures_idx + 1]
                                    stats["categories"][category] = stats["categories"].get(category, 0) + 1
                            except ValueError:
                                pass
                    
                    elif suffix == '.json':
                        if 'models' in file_path.parts:
                            stats["model_files"] += 1
                    
                    elif suffix in ['.ogg', '.wav']:
                        stats["sound_files"] += 1
        
        stats["total_size_mb"] = round(stats["total_size_mb"] / (1024 * 1024), 2)
        
        return stats

    def index_pack_assets(self, pack_name: str) -> List[Dict[str, Any]]:
        """
        Flat index of assets under assets/<namespace>/... with mod source = namespace folder.
        """
        if pack_name not in self.registry["resource_packs"]:
            return []
        pack_dir = Path(self.registry["resource_packs"][pack_name]["path"])
        assets_root = pack_dir / "assets"
        out: List[Dict[str, Any]] = []
        if not assets_root.is_dir():
            return out
        for ns_dir in sorted(assets_root.iterdir()):
            if not ns_dir.is_dir():
                continue
            ns = ns_dir.name
            for f in ns_dir.rglob("*"):
                if not f.is_file():
                    continue
                try:
                    rel = f.relative_to(ns_dir)
                except ValueError:
                    continue
                parts = rel.parts
                category = "other"
                if parts and parts[0] == "textures":
                    category = "texture"
                elif parts and parts[0] == "models":
                    category = "model"
                elif parts and parts[0] == "sounds":
                    category = "sound"
                elif parts and parts[0] == "lang":
                    category = "lang"
                elif parts and f.name == "sounds.json":
                    category = "sounds_json"
                out.append(
                    {
                        "namespace": ns,
                        "category": category,
                        "rel_from_namespace": str(rel).replace("\\", "/"),
                        "path": f"{ns}/{str(rel).replace(chr(92), '/')}",
                    }
                )
        out.sort(key=lambda x: (x["namespace"], x["path"]))
        return out

    def save_theme_manifest(self, pack_name: str, theme: Dict[str, Any]) -> str:
        if pack_name not in self.registry["resource_packs"]:
            raise ValueError("Unknown resource pack.")
        pack_dir = Path(self.registry["resource_packs"][pack_name]["path"])
        meta_dir = pack_dir / ".forager"
        meta_dir.mkdir(parents=True, exist_ok=True)
        path = meta_dir / "theme.json"
        write_text_utf8_nobom(str(path), json.dumps(theme, indent=2, ensure_ascii=False))
        pack_info = self.registry["resource_packs"][pack_name]
        pack_info["modified_at"] = self._get_timestamp()
        self.registry["resource_packs"][pack_name] = pack_info
        self._save_registry()
        return str(path)

    def load_theme_manifest(self, pack_name: str) -> Optional[Dict[str, Any]]:
        if pack_name not in self.registry["resource_packs"]:
            return None
        pack_dir = Path(self.registry["resource_packs"][pack_name]["path"])
        p = pack_dir / ".forager" / "theme.json"
        if not p.is_file():
            return None
        try:
            with open(p, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _normalize_asset_rel(rel: str) -> str:
        r = rel.replace("\\", "/").strip("/")
        if not r or ".." in r.split("/"):
            raise ValueError(f"Unsafe asset path: {rel!r}")
        return r

    @staticmethod
    def _hex_to_rgba(hex_color: Optional[str], fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        if not hex_color or not isinstance(hex_color, str):
            return fallback
        h = hex_color.strip().lstrip("#")
        if len(h) == 6 and all(c in "0123456789abcdefABCDEF" for c in h):
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
        return fallback

    def _backup_existing_asset(self, pack_dir: Path, dest: Path, result: Dict[str, Any]) -> None:
        if not dest.is_file():
            return
        try:
            rel = dest.relative_to(pack_dir)
        except ValueError:
            return
        backup = pack_dir / ".forager" / "backups" / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, backup)
        result.setdefault("backups", []).append(backup.relative_to(pack_dir).as_posix())

    def apply_ai_resource_plan(self, pack_name: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply an AI blueprint: placeholder PNGs, model JSON, animation metas, sounds.json merges, theme file.
        Binary .ogg must be supplied by the user; sound events are registered in sounds.json only.
        """
        result: Dict[str, Any] = {"created": [], "warnings": [], "backups": [], "quality": []}
        if pack_name not in self.registry["resource_packs"]:
            result["warnings"].append("Unknown pack.")
            return result
        pack_dir = Path(self.registry["resource_packs"][pack_name]["path"]).resolve()
        pack_info = self.registry["resource_packs"][pack_name]

        theme = plan.get("theme")
        if isinstance(theme, dict) and theme:
            self.save_theme_manifest(pack_name, theme)
            result["created"].append(".forager/theme.json")

        # --- textures ---
        for i, tex in enumerate(plan.get("new_textures") or []):
            if not isinstance(tex, dict):
                continue
            ns = str(tex.get("namespace") or "minecraft").strip()
            try:
                rel = self._normalize_asset_rel(str(tex.get("path") or ""))
            except ValueError:
                result["warnings"].append(f"Skip texture (bad path): {tex!r}")
                continue
            dest = (pack_dir / "assets" / ns / "textures" / rel).with_suffix(".png")
            if not str(dest.resolve()).startswith(str(pack_dir)):
                result["warnings"].append(f"Skipped escaping path: {dest}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._backup_existing_asset(pack_dir, dest, result)
            forged = render_texture_asset(tex, theme if isinstance(theme, dict) else {}, index=i)
            forged.image.save(dest, format="PNG")
            rel_created = dest.relative_to(pack_dir).as_posix()
            result["created"].append(rel_created)
            # sidecar label for mod-source filtering in external tools
            label = {
                "inspired_by_mod": tex.get("inspired_by_mod") or ns,
                "namespace": ns,
                "note": tex.get("note"),
                "forge": forged.metadata,
                "quality": forged.quality,
                "source_spec": tex,
            }
            label_path = dest.parent / f"{dest.name}.forager.json"
            write_text_utf8_nobom(
                str(label_path),
                json.dumps(label, indent=2, ensure_ascii=False),
            )
            result["created"].append(label_path.relative_to(pack_dir).as_posix())
            result["quality"].append({"path": rel_created, **forged.quality})

        # --- models ---
        for i, m in enumerate(plan.get("new_models") or []):
            if not isinstance(m, dict):
                continue
            ns = str(m.get("namespace") or "minecraft").strip()
            try:
                rel = self._normalize_asset_rel(str(m.get("path") or ""))
            except ValueError:
                result["warnings"].append(f"Skip model (bad path): {m!r}")
                continue
            parent = str(m.get("parent") or "").strip()
            if parent and ":" not in parent:
                parent = f"minecraft:{parent}"
            tex_key = str(m.get("texture_layer0") or f"{ns}:{rel}")
            model_spec = dict(m)
            if parent:
                model_spec.setdefault("parent", parent)
            model_spec.setdefault("texture_layer0", tex_key)
            body = model_json_for_spec(model_spec, namespace=ns, rel=rel)
            dest = (pack_dir / "assets" / ns / "models" / rel).with_suffix(".json")
            if not str(dest.resolve()).startswith(str(pack_dir)):
                result["warnings"].append(f"Skipped model escaping path: {dest}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._backup_existing_asset(pack_dir, dest, result)
            write_text_utf8_nobom(str(dest), json.dumps(body, indent=2, ensure_ascii=False))
            result["created"].append(dest.relative_to(pack_dir).as_posix())
            meta_path = dest.parent / f"{dest.name}.forager.json"
            write_text_utf8_nobom(
                str(meta_path),
                json.dumps(
                    {
                        "namespace": ns,
                        "inspired_by_mod": m.get("inspired_by_mod") or ns,
                        "model_type": m.get("model_type"),
                        "uv_template": m.get("uv_template"),
                        "source_spec": m,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )
            result["created"].append(meta_path.relative_to(pack_dir).as_posix())

        # --- texture animations (vertical strip PNG + .mcmeta) ---
        for j, anim in enumerate(plan.get("animations") or []):
            if not isinstance(anim, dict):
                continue
            ns = str(anim.get("namespace") or "minecraft").strip()
            try:
                rel = self._normalize_asset_rel(str(anim.get("texture_path") or ""))
            except ValueError:
                result["warnings"].append(f"Skip animation (bad path): {anim!r}")
                continue
            frames = int(anim.get("frames") or 4)
            frames = max(2, min(frames, 64))
            frametime = int(anim.get("frametime") or 2)
            interpolate = bool(anim.get("interpolate", False))
            dest_png = pack_dir / "assets" / ns / "textures" / f"{rel}.png"
            if not str(dest_png.resolve()).startswith(str(pack_dir)):
                continue
            dest_png.parent.mkdir(parents=True, exist_ok=True)
            self._backup_existing_asset(pack_dir, dest_png, result)
            anim_spec = dict(anim)
            anim_spec.setdefault("path", rel)
            anim_spec.setdefault("asset_kind", "animation")
            forged_anim = render_animation_strip(
                anim_spec,
                theme if isinstance(theme, dict) else {},
                frames=frames,
                index=j,
            )
            forged_anim.image.save(dest_png, format="PNG")
            result["created"].append(dest_png.relative_to(pack_dir).as_posix())
            mcmeta_path = dest_png.with_suffix(".png.mcmeta")
            self._backup_existing_asset(pack_dir, mcmeta_path, result)
            write_text_utf8_nobom(
                str(mcmeta_path),
                json.dumps(
                    {"animation": {"frametime": frametime, "interpolate": interpolate}},
                    indent=2,
                    ensure_ascii=False,
                ),
            )
            result["created"].append(mcmeta_path.relative_to(pack_dir).as_posix())
            result["quality"].append({ "path": dest_png.relative_to(pack_dir).as_posix(), **forged_anim.quality })

        # --- sound events (sounds.json per namespace + local procedural WAV previews) ---
        ns_sound_maps: Dict[str, Dict[str, Any]] = {}
        for sound_idx, sd in enumerate(plan.get("sound_events") or []):
            if not isinstance(sd, dict):
                continue
            sns = str(sd.get("namespace") or "minecraft").strip()
            ev = str(sd.get("event") or "").strip()
            sfile = str(sd.get("sound_file") or "").strip().replace("\\", "/")
            if not ev or not sfile or ".." in sfile.split("/"):
                result["warnings"].append(f"Skip sound event: {sd!r}")
                continue
            ns_sound_maps.setdefault(sns, {})
            entry = {
                "sounds": [{"name": f"{sns}:{sfile}", "stream": False}],
            }
            sub = sd.get("subtitle")
            if sub:
                entry["subtitle"] = str(sub)
            ns_sound_maps[sns][ev] = entry
            mode = str(sd.get("generation_mode") or "local_procedural")
            if mode in {"local_procedural", "external_ai_optional"}:
                try:
                    forged_sound = render_sound_effect(sd, index=sound_idx)
                    preview_dest = (pack_dir / ".forager" / "sounds" / sns / sfile).with_suffix(".wav")
                    write_wav(preview_dest, forged_sound)
                    result["created"].append(preview_dest.relative_to(pack_dir).as_posix())
                    meta_dest = preview_dest.with_suffix(".wav.forager.json")
                    write_text_utf8_nobom(str(meta_dest), sound_report_json(forged_sound))
                    result["created"].append(meta_dest.relative_to(pack_dir).as_posix())
                    result.setdefault("quality", []).append({"path": preview_dest.relative_to(pack_dir).as_posix(), **forged_sound.quality})
                    result["warnings"].append(
                        f"Generated WAV preview for `{ev}`. Minecraft runtime still expects an OGG at `assets/{sns}/sounds/{sfile}.ogg`."
                    )
                except Exception as exc:
                    result["warnings"].append(f"Could not generate sound preview for `{ev}`: {exc}")

        for sns, events in ns_sound_maps.items():
            sj_path = pack_dir / "assets" / sns / "sounds.json"
            existing: Dict[str, Any] = {}
            if sj_path.is_file():
                try:
                    with open(sj_path, "r", encoding="utf-8") as fh:
                        existing = json.load(fh)
                    if not isinstance(existing, dict):
                        existing = {}
                except (json.JSONDecodeError, OSError):
                    existing = {}
            existing.update(events)
            sj_path.parent.mkdir(parents=True, exist_ok=True)
            write_text_utf8_nobom(str(sj_path), json.dumps(existing, indent=2, ensure_ascii=False))
            result["created"].append(sj_path.relative_to(pack_dir).as_posix())
        if ns_sound_maps:
            result["warnings"].append(
                "Sound events updated in sounds.json. Local WAV previews may be generated under `.forager/sounds`, but Minecraft requires matching `.ogg` files under each namespace's `sounds/` folder."
            )

        prompts = plan.get("image_prompts")
        if isinstance(prompts, list) and prompts:
            prompt_path = pack_dir / ".forager" / "image_prompts.json"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            write_text_utf8_nobom(str(prompt_path), json.dumps(prompts, indent=2, ensure_ascii=False))
            result["created"].append(prompt_path.relative_to(pack_dir).as_posix())

        pack_info["modified_at"] = self._get_timestamp()
        self.registry["resource_packs"][pack_name] = pack_info
        self._save_registry()
        result["validation"] = validate_texture_forge_export(pack_dir)
        save_export_report(pack_dir, result, label="last_blueprint_apply")
        return result

    def texture_forge_export_report(self, pack_name: str) -> Dict[str, Any]:
        if pack_name not in self.registry["resource_packs"]:
            return {"ok": False, "warnings": ["Unknown pack."]}
        pack_dir = Path(self.registry["resource_packs"][pack_name]["path"]).resolve()
        return validate_texture_forge_export(pack_dir)

    def rollback_last_texture_forge_apply(self, pack_name: str) -> Dict[str, Any]:
        if pack_name not in self.registry["resource_packs"]:
            return {"restored": [], "warnings": ["Unknown pack."]}
        pack_dir = Path(self.registry["resource_packs"][pack_name]["path"]).resolve()
        return rollback_latest(pack_dir)

    def export_blockbench_source_pack(self, pack_name: str, export_path: str) -> bool:
        if pack_name not in self.registry["resource_packs"]:
            return False
        pack_dir = Path(self.registry["resource_packs"][pack_name]["path"]).resolve()
        return export_blockbench_sources(pack_dir, export_path)

    def write_texture_replacement(
        self,
        pack_name: str,
        *,
        target: Dict[str, Any],
        spec: Dict[str, Any],
        create_model: bool = True,
        create_blockbench: bool = True,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {"created": [], "warnings": [], "backups": [], "quality": []}
        if pack_name not in self.registry["resource_packs"]:
            result["warnings"].append("Unknown pack.")
            return result
        pack_dir = Path(self.registry["resource_packs"][pack_name]["path"]).resolve()
        ns = str(spec.get("namespace") or target.get("mod_id") or "minecraft").strip()
        rel = self._normalize_asset_rel(str(spec.get("path") or self._target_texture_path(target)))
        theme = spec.get("theme") if isinstance(spec.get("theme"), dict) else {}
        forged = render_texture_asset(spec, theme)

        texture_dest = (pack_dir / "assets" / ns / "textures" / rel).with_suffix(".png")
        if not str(texture_dest.resolve()).startswith(str(pack_dir)):
            result["warnings"].append(f"Skipped escaping texture path: {texture_dest}")
            return result
        texture_dest.parent.mkdir(parents=True, exist_ok=True)
        self._backup_existing_asset(pack_dir, texture_dest, result)
        forged.image.save(texture_dest, format="PNG")
        result["created"].append(texture_dest.relative_to(pack_dir).as_posix())
        result["quality"].append({"path": texture_dest.relative_to(pack_dir).as_posix(), **forged.quality})

        texture_ref = f"{ns}:textures/{rel}".replace(".png", "")
        model_path = None
        if create_model:
            model_rel = rel
            model_spec = dict(spec)
            model_spec.setdefault("texture_layer0", texture_ref)
            model_body = model_json_for_spec(model_spec, namespace=ns, rel=model_rel)
            model_dest = (pack_dir / "assets" / ns / "models" / model_rel).with_suffix(".json")
            if str(model_dest.resolve()).startswith(str(pack_dir)):
                model_dest.parent.mkdir(parents=True, exist_ok=True)
                self._backup_existing_asset(pack_dir, model_dest, result)
                write_text_utf8_nobom(str(model_dest), json.dumps(model_body, indent=2, ensure_ascii=False))
                model_path = model_dest.relative_to(pack_dir).as_posix()
                result["created"].append(model_path)

        bbmodel_path = None
        if create_blockbench:
            bbmodel = build_bbmodel_project(
                name=str(spec.get("name") or target.get("id") or rel).replace(":", "_"),
                texture=forged.image,
                model_type=str(spec.get("model_type") or spec.get("asset_kind") or "cube"),
                animations=spec.get("blockbench_animations") if isinstance(spec.get("blockbench_animations"), list) else [],
            )
            validation = validate_bbmodel(bbmodel)
            if not validation["ok"]:
                result["warnings"].extend([f"Blockbench: {w}" for w in validation["warnings"]])
            bb_dir = pack_dir / ".forager" / "blockbench"
            bb_dir.mkdir(parents=True, exist_ok=True)
            bb_dest = bb_dir / f"{Path(rel).name}.bbmodel"
            write_text_utf8_nobom(str(bb_dest), bbmodel_to_json(bbmodel))
            bbmodel_path = bb_dest.relative_to(pack_dir).as_posix()
            result["created"].append(bbmodel_path)

        meta = {
            "saved_at": self._get_timestamp(),
            "target": target,
            "spec": spec,
            "texture": texture_dest.relative_to(pack_dir).as_posix(),
            "model": model_path,
            "bbmodel": bbmodel_path,
            "forge": forged.metadata,
            "quality": forged.quality,
            "backups": result.get("backups") or [],
        }
        repl_dir = pack_dir / ".forager" / "replacements"
        repl_dir.mkdir(parents=True, exist_ok=True)
        repl_dest = repl_dir / f"{Path(rel).name}.json"
        write_text_utf8_nobom(str(repl_dest), json.dumps(meta, indent=2, ensure_ascii=False))
        result["created"].append(repl_dest.relative_to(pack_dir).as_posix())

        pack_info = self.registry["resource_packs"][pack_name]
        pack_info["modified_at"] = self._get_timestamp()
        self.registry["resource_packs"][pack_name] = pack_info
        self._save_registry()
        result["validation"] = validate_texture_forge_export(pack_dir)
        save_export_report(pack_dir, result, label="last_replacement_apply")
        return result

    @staticmethod
    def _target_texture_path(target: Dict[str, Any]) -> str:
        target_id = str(target.get("id") or target.get("file") or "generated_asset").lower()
        clean = re.sub(r"[^a-z0-9_/:-]+", "_", target_id).replace(":", "/")
        entry_type = str(target.get("type") or "").lower()
        if "block" in entry_type or "structure" in entry_type:
            return f"block/{Path(clean).name}"
        if "mob" in entry_type or "entity" in entry_type:
            return f"entity/{Path(clean).name}"
        if "gui" in entry_type:
            return f"gui/{Path(clean).name}"
        return f"item/{Path(clean).name}"