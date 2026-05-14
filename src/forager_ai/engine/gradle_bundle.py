"""
Bundled Gradle wrapper files for Forge scaffolds (Apache-licensed Gradle scripts + wrapper jar).

Data lives under ``forager_ai/engine/data/`` (scripts, jar, ``gradle-wrapper.properties``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

_DATA = Path(__file__).resolve().parent / "data"


def wrapper_properties_text() -> str:
    p = _DATA / "gradle-wrapper.properties"
    if p.is_file():
        return p.read_text(encoding="utf-8").replace("\r\n", "\n")
    return (
        "distributionBase=GRADLE_USER_HOME\n"
        "distributionPath=wrapper/dists\n"
        "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.4-bin.zip\n"
        "zipStoreBase=GRADLE_USER_HOME\n"
        "zipStorePath=wrapper/dists\n"
    )


def gradlew_bat_text() -> str:
    p = _DATA / "gradlew.bat"
    if p.is_file():
        return p.read_text(encoding="utf-8").replace("\r\n", "\n")
    raise FileNotFoundError("Bundled gradlew.bat missing — reinstall Forager or restore engine/data.")


def gradlew_sh_text() -> str:
    p = _DATA / "gradlew"
    if p.is_file():
        return p.read_text(encoding="utf-8").replace("\r\n", "\n")
    raise FileNotFoundError("Bundled gradlew missing — reinstall Forager or restore engine/data.")


def gradle_wrapper_jar_bytes() -> Optional[bytes]:
    p = _DATA / "gradle-wrapper-8.4.jar"
    if not p.is_file():
        return None
    return p.read_bytes()


def copy_wrapper_into_directory(dest_root: str | Path) -> dict:
    """
    Write ``gradle/wrapper/*``, ``gradlew``, ``gradlew.bat`` under ``dest_root``.

    Returns a small report dict (paths written, whether jar was present).
    """
    root = Path(dest_root)
    gw = root / "gradle" / "wrapper"
    gw.mkdir(parents=True, exist_ok=True)
    (gw / "gradle-wrapper.properties").write_text(wrapper_properties_text(), encoding="utf-8", newline="\n")
    jar = gradle_wrapper_jar_bytes()
    jar_path = gw / "gradle-wrapper.jar"
    if jar:
        jar_path.write_bytes(jar)
    (root / "gradlew.bat").write_text(gradlew_bat_text(), encoding="utf-8", newline="\n")
    (root / "gradlew").write_text(gradlew_sh_text(), encoding="utf-8", newline="\n")
    try:
        import os

        os.chmod(root / "gradlew", 0o755)
    except OSError:
        pass
    return {
        "gradle_wrapper_properties": str(gw / "gradle-wrapper.properties"),
        "gradle_wrapper_jar": str(jar_path) if jar else None,
        "gradlew_bat": str(root / "gradlew.bat"),
        "gradlew": str(root / "gradlew"),
    }
