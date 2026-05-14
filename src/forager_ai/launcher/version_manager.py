"""
Version Management
Handles Minecraft versions, mod loaders, and Java versions.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests


@dataclass
class MinecraftVersion:
    """Represents a Minecraft version."""
    id: str
    type: str  # release, snapshot, old_beta, old_alpha
    url: str
    time: str
    release_time: str
    sha1: str
    compliance_level: int
    
    @property
    def is_release(self) -> bool:
        return self.type == "release"
    
    @property
    def is_snapshot(self) -> bool:
        return self.type == "snapshot"


@dataclass
class LoaderVersion:
    """Represents a mod loader version."""
    version: str
    minecraft_version: str
    loader: str  # forge, fabric, quilt
    stable: bool
    recommended: bool
    latest: bool
    build_number: Optional[int] = None
    installer_url: Optional[str] = None
    
    @property
    def display_name(self) -> str:
        return f"{self.loader.title()} {self.version}"


@dataclass
class JavaVersion:
    """Represents a Java installation."""
    version: str
    path: str
    architecture: str  # x64, x86
    vendor: str
    is_valid: bool = True
    
    @property
    def major_version(self) -> int:
        """Get major Java version number."""
        try:
            # Handle both "1.8.0_XXX" and "17.0.X" formats
            if self.version.startswith("1."):
                return int(self.version.split(".")[1])
            else:
                return int(self.version.split(".")[0])
        except (ValueError, IndexError):
            return 8  # Default fallback


class VersionManager:
    """Manages Minecraft, loader, and Java versions."""
    
    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache files
        self.minecraft_cache = self.cache_dir / "minecraft_versions.json"
        self.forge_cache = self.cache_dir / "forge_versions.json"
        self.fabric_cache = self.cache_dir / "fabric_versions.json"
        self.java_cache = self.cache_dir / "java_installations.json"
        
        # API endpoints
        self.minecraft_api = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
        self.forge_api = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
        self.fabric_api = "https://meta.fabricmc.net/v2/versions"
        
        # Cache expiry (24 hours)
        self.cache_expiry = 24 * 60 * 60
        
        # Load cached data
        self.minecraft_versions: List[MinecraftVersion] = []
        self.forge_versions: Dict[str, List[LoaderVersion]] = {}
        self.fabric_versions: List[LoaderVersion] = []
        self.java_installations: List[JavaVersion] = []
        
        self._load_cached_data()
    
    def _is_cache_valid(self, cache_file: Path) -> bool:
        """Check if cache file is still valid."""
        if not cache_file.exists():
            return False
        
        try:
            stat = cache_file.stat()
            age = time.time() - stat.st_mtime
            return age < self.cache_expiry
        except OSError:
            return False
    
    def _load_minecraft_cache_any_age(self) -> bool:
        """If the live API failed, use the last saved manifest from disk (even if expired)."""
        if not self.minecraft_cache.is_file():
            return False
        try:
            with open(self.minecraft_cache, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list) or not data:
                return False
            self.minecraft_versions = [MinecraftVersion(**v) for v in data]
            return bool(self.minecraft_versions)
        except (OSError, json.JSONDecodeError, TypeError, KeyError):
            return False

    def _seed_minimal_release_fallback(self) -> None:
        """Last resort when offline and no cache — enough for instance create UI + Java routing."""
        ids = (
            "1.21.4",
            "1.21.1",
            "1.20.6",
            "1.20.4",
            "1.20.1",
            "1.19.2",
            "1.18.2",
            "1.16.5",
            "1.12.2",
        )
        self.minecraft_versions = [
            MinecraftVersion(
                id=vid,
                type="release",
                url="",
                time="",
                release_time="",
                sha1="",
                compliance_level=0,
            )
            for vid in ids
        ]

    def _load_cached_data(self):
        """Load cached version data."""
        # Load Minecraft versions
        if self._is_cache_valid(self.minecraft_cache):
            try:
                with open(self.minecraft_cache, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.minecraft_versions = [MinecraftVersion(**v) for v in data]
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
        
        # Load Java installations
        if self._is_cache_valid(self.java_cache):
            try:
                with open(self.java_cache, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.java_installations = [JavaVersion(**j) for j in data]
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
    
    def refresh_minecraft_versions(self) -> bool:
        """Refresh Minecraft version list from Mojang API."""
        try:
            response = requests.get(self.minecraft_api, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            versions = []
            for version_data in data.get("versions", []):
                version = MinecraftVersion(
                    id=version_data["id"],
                    type=version_data["type"],
                    url=version_data["url"],
                    time=version_data["time"],
                    release_time=version_data["releaseTime"],
                    sha1=version_data["sha1"],
                    compliance_level=version_data.get("complianceLevel", 0)
                )
                versions.append(version)
            
            self.minecraft_versions = versions
            
            # Cache the data
            with open(self.minecraft_cache, 'w', encoding='utf-8') as f:
                json.dump([v.__dict__ for v in versions], f, indent=2)
            
            return True
            
        except requests.RequestException as e:
            print(f"Error fetching Minecraft versions: {e}")
            return False
    
    def get_minecraft_versions(
        self,
        include_snapshots: bool = False,
        include_old: bool = False
    ) -> List[MinecraftVersion]:
        """Get filtered list of Minecraft versions."""
        if not self.minecraft_versions:
            self.refresh_minecraft_versions()
        if not self.minecraft_versions:
            self._load_minecraft_cache_any_age()
        if not self.minecraft_versions:
            self._seed_minimal_release_fallback()

        filtered = []
        for version in self.minecraft_versions:
            if version.is_release:
                filtered.append(version)
            elif include_snapshots and version.is_snapshot:
                filtered.append(version)
            elif include_old and version.type in ["old_beta", "old_alpha"]:
                filtered.append(version)

        if not filtered:
            for v in self.minecraft_versions:
                if getattr(v, "id", None):
                    filtered.append(v)
                if len(filtered) >= 60:
                    break
        if not filtered:
            self._seed_minimal_release_fallback()
            filtered = [v for v in self.minecraft_versions if v.is_release]
        
        return filtered
    
    def get_latest_minecraft_version(self, release_only: bool = True) -> Optional[MinecraftVersion]:
        """Get the latest Minecraft version."""
        versions = self.get_minecraft_versions(include_snapshots=not release_only)
        return versions[0] if versions else None
    
    def refresh_forge_versions(self) -> bool:
        """Refresh Forge version list."""
        try:
            # Get promotions (recommended versions)
            response = requests.get(self.forge_api, timeout=30)
            response.raise_for_status()
            promotions = response.json()
            
            # Get full version list
            maven_response = requests.get(
                "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml",
                timeout=30
            )
            maven_response.raise_for_status()
            
            # Parse versions (simplified - would need proper XML parsing)
            forge_versions = {}
            
            # For now, use promotions data to build basic version info
            for key, version in promotions.get("promos", {}).items():
                if "-" in key:
                    mc_version, promo_type = key.rsplit("-", 1)
                    
                    if mc_version not in forge_versions:
                        forge_versions[mc_version] = []
                    
                    loader_version = LoaderVersion(
                        version=version,
                        minecraft_version=mc_version,
                        loader="forge",
                        stable=True,
                        recommended=promo_type == "recommended",
                        latest=promo_type == "latest"
                    )
                    forge_versions[mc_version].append(loader_version)
            
            self.forge_versions = forge_versions
            
            # Cache the data
            with open(self.forge_cache, 'w', encoding='utf-8') as f:
                cache_data = {}
                for mc_ver, loaders in forge_versions.items():
                    cache_data[mc_ver] = [l.__dict__ for l in loaders]
                json.dump(cache_data, f, indent=2)
            
            return True
            
        except requests.RequestException as e:
            print(f"Error fetching Forge versions: {e}")
            return False
    
    def refresh_fabric_versions(self) -> bool:
        """Refresh Fabric version list."""
        try:
            # Get Fabric loader versions
            loader_response = requests.get(f"{self.fabric_api}/loader", timeout=30)
            loader_response.raise_for_status()
            loader_data = loader_response.json()
            
            # Get Fabric game versions
            game_response = requests.get(f"{self.fabric_api}/game", timeout=30)
            game_response.raise_for_status()
            game_data = game_response.json()
            
            versions = []
            stable_loaders = [l for l in loader_data if l.get("stable", False)]
            
            for game_version in game_data:
                if game_version.get("stable", False):
                    for loader in stable_loaders[:3]:  # Top 3 stable loaders
                        version = LoaderVersion(
                            version=loader["version"],
                            minecraft_version=game_version["version"],
                            loader="fabric",
                            stable=loader.get("stable", False),
                            recommended=False,  # Fabric doesn't have recommended versions
                            latest=loader == stable_loaders[0]
                        )
                        versions.append(version)
            
            self.fabric_versions = versions
            
            # Cache the data
            with open(self.fabric_cache, 'w', encoding='utf-8') as f:
                json.dump([v.__dict__ for v in versions], f, indent=2)
            
            return True
            
        except requests.RequestException as e:
            print(f"Error fetching Fabric versions: {e}")
            return False
    
    def get_loader_versions(
        self,
        minecraft_version: str,
        loader: str = "forge"
    ) -> List[LoaderVersion]:
        """Get loader versions for a specific Minecraft version."""
        if loader == "forge":
            if not self.forge_versions:
                self.refresh_forge_versions()
            return self.forge_versions.get(minecraft_version, [])
        
        elif loader == "fabric":
            if not self.fabric_versions:
                self.refresh_fabric_versions()
            return [v for v in self.fabric_versions if v.minecraft_version == minecraft_version]
        
        return []
    
    def scan_java_installations(self) -> List[JavaVersion]:
        """Scan system for Java installations."""
        java_installations = []
        
        # Common Java installation paths
        java_paths = []
        
        if os.name == "nt":  # Windows
            java_paths.extend([
                "C:\\Program Files\\Java",
                "C:\\Program Files (x86)\\Java",
                "C:\\Program Files\\Eclipse Adoptium",
                "C:\\Program Files\\Microsoft\\jdk",
                os.path.expandvars("%JAVA_HOME%") if os.getenv("JAVA_HOME") else ""
            ])
        else:  # Unix-like
            java_paths.extend([
                "/usr/lib/jvm",
                "/usr/java",
                "/opt/java",
                "/Library/Java/JavaVirtualMachines",  # macOS
                os.path.expandvars("$JAVA_HOME") if os.getenv("JAVA_HOME") else ""
            ])
        
        # Scan paths
        for base_path in java_paths:
            if not base_path or not os.path.exists(base_path):
                continue
            
            try:
                if os.path.isfile(os.path.join(base_path, "bin", "java.exe" if os.name == "nt" else "java")):
                    # Direct Java installation
                    java_info = self._get_java_info(base_path)
                    if java_info:
                        java_installations.append(java_info)
                else:
                    # Directory containing Java installations
                    for item in os.listdir(base_path):
                        java_dir = os.path.join(base_path, item)
                        if os.path.isdir(java_dir):
                            java_info = self._get_java_info(java_dir)
                            if java_info:
                                java_installations.append(java_info)
            except (OSError, PermissionError):
                continue
        
        # Check system PATH
        try:
            result = subprocess.run(
                ["java", "-version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                # Parse version from stderr (Java outputs version info to stderr)
                version_output = result.stderr
                java_info = self._parse_java_version_output(version_output, "system")
                if java_info:
                    java_installations.append(java_info)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        # Remove duplicates and sort by version
        unique_installations = {}
        for java in java_installations:
            key = (java.version, java.path)
            if key not in unique_installations:
                unique_installations[key] = java
        
        sorted_installations = sorted(
            unique_installations.values(),
            key=lambda j: j.major_version,
            reverse=True
        )
        
        self.java_installations = sorted_installations
        
        # Cache the data
        with open(self.java_cache, 'w', encoding='utf-8') as f:
            json.dump([j.__dict__ for j in sorted_installations], f, indent=2)
        
        return sorted_installations
    
    def _get_java_info(self, java_path: str) -> Optional[JavaVersion]:
        """Get Java version information from installation path."""
        java_exe = os.path.join(java_path, "bin", "java.exe" if os.name == "nt" else "java")
        
        if not os.path.isfile(java_exe):
            return None
        
        try:
            result = subprocess.run(
                [java_exe, "-version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return self._parse_java_version_output(result.stderr, java_path)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        return None
    
    def _parse_java_version_output(self, output: str, path: str) -> Optional[JavaVersion]:
        """Parse Java version output."""
        lines = output.strip().split('\n')
        if not lines:
            return None
        
        # Parse version line (first line)
        version_line = lines[0]
        
        # Extract version number
        version = "unknown"
        if '"' in version_line:
            version = version_line.split('"')[1]
        
        # Extract vendor
        vendor = "Unknown"
        for line in lines:
            if "OpenJDK" in line:
                vendor = "OpenJDK"
                break
            elif "Oracle" in line:
                vendor = "Oracle"
                break
            elif "Eclipse Adoptium" in line or "Temurin" in line:
                vendor = "Eclipse Adoptium"
                break
            elif "Microsoft" in line:
                vendor = "Microsoft"
                break
        
        # Determine architecture
        architecture = "x64"  # Default assumption
        for line in lines:
            if "32-Bit" in line or "x86" in line:
                architecture = "x86"
                break
        
        return JavaVersion(
            version=version,
            path=path,
            architecture=architecture,
            vendor=vendor,
            is_valid=True
        )
    
    def get_recommended_java_version(self, minecraft_version: str) -> int:
        """Get recommended Java version for a Minecraft version."""
        # Parse Minecraft version to determine Java requirements
        try:
            version_parts = minecraft_version.split('.')
            major = int(version_parts[0])
            minor = int(version_parts[1]) if len(version_parts) > 1 else 0
            
            # Minecraft 1.17+ requires Java 16+
            if major > 1 or (major == 1 and minor >= 17):
                return 17
            # Minecraft 1.12+ works well with Java 8+
            elif major > 1 or (major == 1 and minor >= 12):
                return 8
            # Older versions
            else:
                return 8
                
        except (ValueError, IndexError):
            return 8  # Safe default
    
    def find_compatible_java(self, minecraft_version: str) -> Optional[JavaVersion]:
        """Find a compatible Java installation for a Minecraft version."""
        if not self.java_installations:
            self.scan_java_installations()
        
        recommended_version = self.get_recommended_java_version(minecraft_version)
        
        # First, try to find exact match
        for java in self.java_installations:
            if java.major_version == recommended_version and java.is_valid:
                return java
        
        # Then, try to find compatible version (higher is usually OK)
        for java in self.java_installations:
            if java.major_version >= recommended_version and java.is_valid:
                return java
        
        # Fallback to any valid Java
        for java in self.java_installations:
            if java.is_valid:
                return java
        
        return None