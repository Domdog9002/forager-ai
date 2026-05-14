from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Set, Tuple


COMPARE_DIRS = ["mods", "config", "kubejs", "scripts", "resourcepacks"]


def _file_sha1(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _collect_files(base_root: str, subdir: str) -> Dict[str, str]:
    abs_root = os.path.join(base_root, subdir)
    out: Dict[str, str] = {}
    if not os.path.isdir(abs_root):
        return out
    for root, _, files in os.walk(abs_root):
        for name in files:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, abs_root).replace("\\", "/")
            out[rel] = path
    return out


def compare_pack_roots(client_root: str, server_root: str) -> Dict[str, Any]:
    sections: Dict[str, Any] = {}
    high = 0
    medium = 0

    for subdir in COMPARE_DIRS:
        client = _collect_files(client_root, subdir)
        server = _collect_files(server_root, subdir)
        c_keys = set(client.keys())
        s_keys = set(server.keys())

        client_only = sorted(c_keys - s_keys)
        server_only = sorted(s_keys - c_keys)
        shared = sorted(c_keys & s_keys)
        hash_mismatch: List[str] = []

        for rel in shared:
            try:
                c_hash = _file_sha1(client[rel])
                s_hash = _file_sha1(server[rel])
                if c_hash != s_hash:
                    hash_mismatch.append(rel)
            except OSError:
                hash_mismatch.append(rel)

        severity = "none"
        if client_only or server_only or hash_mismatch:
            severity = "medium"
            if subdir in ("mods", "kubejs", "scripts") and (client_only or server_only or hash_mismatch):
                severity = "high"
        if severity == "high":
            high += 1
        elif severity == "medium":
            medium += 1

        sections[subdir] = {
            "client_only": client_only,
            "server_only": server_only,
            "hash_mismatch": hash_mismatch,
            "severity": severity,
        }

    summary = {
        "high_sections": high,
        "medium_sections": medium,
        "in_sync": (high == 0 and medium == 0),
    }
    return {"summary": summary, "sections": sections}

