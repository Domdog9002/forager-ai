from __future__ import annotations

import hashlib
import json
import math
import random
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


SAMPLE_RATE = 44_100
MAX_DURATION_MS = 12_000


@dataclass
class SoundForgeResult:
    samples: List[float]
    sample_rate: int
    metadata: Dict[str, Any]
    quality: Dict[str, Any]


def normalize_sound_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(spec.get("sound_kind") or spec.get("kind") or "magic_chime").strip().lower().replace(" ", "_")
    try:
        duration_ms = int(spec.get("duration_ms") or spec.get("duration") or 700)
    except (TypeError, ValueError):
        duration_ms = 700
    duration_ms = max(80, min(duration_ms, MAX_DURATION_MS))
    try:
        pitch = float(spec.get("pitch") or 1.0)
    except (TypeError, ValueError):
        pitch = 1.0
    try:
        volume = float(spec.get("volume") or 0.7)
    except (TypeError, ValueError):
        volume = 0.7
    return {
        "sound_kind": kind,
        "duration_ms": duration_ms,
        "pitch": max(0.25, min(pitch, 3.0)),
        "volume": max(0.05, min(volume, 1.0)),
        "loop": bool(spec.get("loop", False)),
        "generation_mode": str(spec.get("generation_mode") or "local_procedural"),
        "ai_audio_prompt": str(spec.get("ai_audio_prompt") or spec.get("prompt") or "").strip(),
    }


def render_sound_effect(spec: Dict[str, Any], *, index: int = 0) -> SoundForgeResult:
    normalized = normalize_sound_spec(spec)
    seed = _seed_for(spec, index)
    rng = random.Random(seed)
    total = max(1, int(SAMPLE_RATE * normalized["duration_ms"] / 1000))
    kind = normalized["sound_kind"]
    pitch = normalized["pitch"]
    volume = normalized["volume"]
    samples: List[float] = []
    base_freq = _base_frequency(kind, pitch, rng)
    for i in range(total):
        t = i / SAMPLE_RATE
        progress = i / max(1, total - 1)
        env = _envelope(kind, progress, loop=normalized["loop"])
        value = _waveform(kind, t, progress, base_freq, rng)
        samples.append(max(-1.0, min(1.0, value * env * volume)))
    quality = score_sound(samples, sample_rate=SAMPLE_RATE, spec=normalized)
    return SoundForgeResult(
        samples=samples,
        sample_rate=SAMPLE_RATE,
        metadata={
            "engine": "sound_forge_local",
            "seed": seed,
            "kind": kind,
            "duration_ms": normalized["duration_ms"],
            "pitch": pitch,
            "volume": volume,
            "loop": normalized["loop"],
            "generation_mode": normalized["generation_mode"],
            "ai_audio_prompt": normalized["ai_audio_prompt"],
            "format": "wav_preview",
        },
        quality=quality,
    )


def write_wav(path: str | Path, result: SoundForgeResult) -> str:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(result.sample_rate)
        frames = bytearray()
        for value in result.samples:
            clamped = max(-1.0, min(1.0, value))
            frames.extend(int(clamped * 32767).to_bytes(2, byteorder="little", signed=True))
        fh.writeframes(bytes(frames))
    return str(dest)


def score_sound(samples: List[float], *, sample_rate: int = SAMPLE_RATE, spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
    warnings: List[str] = []
    if not samples:
        return {"score": 10, "warnings": ["sound has no samples"], "peak": 0, "rms": 0}
    peak = max(abs(s) for s in samples)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    duration_ms = int(len(samples) / sample_rate * 1000)
    if peak < 0.05:
        warnings.append("sound is very quiet")
    if peak > 0.98:
        warnings.append("sound may clip")
    if rms < 0.015:
        warnings.append("sound energy is very low")
    if duration_ms > MAX_DURATION_MS:
        warnings.append("sound is longer than the local safety limit")
    if spec and spec.get("generation_mode") == "external_ai_optional":
        warnings.append("external AI audio hook requested; local procedural preview was generated")
    score = 100 - len(warnings) * 14
    if 0.08 <= peak <= 0.9:
        score += 4
    return {
        "score": max(0, min(100, score)),
        "warnings": warnings,
        "peak": round(peak, 4),
        "rms": round(rms, 4),
        "duration_ms": duration_ms,
        "sample_rate": sample_rate,
    }


def sound_report_json(result: SoundForgeResult) -> str:
    return json.dumps({"metadata": result.metadata, "quality": result.quality}, indent=2, ensure_ascii=False)


def _seed_for(spec: Dict[str, Any], index: int) -> int:
    raw = json.dumps({"spec": spec, "index": index}, sort_keys=True, ensure_ascii=True)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12], 16)


def _base_frequency(kind: str, pitch: float, rng: random.Random) -> float:
    bases = {
        "click": 880,
        "ui_blip": 660,
        "magic_chime": 520,
        "spell_cast": 330,
        "hit": 150,
        "impact": 110,
        "pickup": 740,
        "machine_hum": 95,
        "ambient_loop": 140,
    }
    return (bases.get(kind, 440) + rng.uniform(-18, 18)) * pitch


def _envelope(kind: str, progress: float, *, loop: bool) -> float:
    if loop or kind in {"ambient_loop", "machine_hum"}:
        return 0.55 + 0.25 * math.sin(progress * math.tau)
    attack = min(1.0, progress / 0.08)
    release = max(0.0, 1.0 - progress)
    if kind in {"hit", "impact", "click"}:
        return attack * (release ** 3)
    if kind in {"magic_chime", "spell_cast", "pickup"}:
        return attack * (release ** 1.4)
    return attack * release


def _waveform(kind: str, t: float, progress: float, freq: float, rng: random.Random) -> float:
    noise = rng.uniform(-1.0, 1.0)
    if kind in {"hit", "impact"}:
        return 0.65 * noise + 0.35 * math.sin(math.tau * freq * (1.0 - progress * 0.35) * t)
    if kind == "click":
        return math.sin(math.tau * freq * t) if progress < 0.18 else 0.18 * noise
    if kind == "machine_hum":
        return 0.7 * math.sin(math.tau * freq * t) + 0.25 * math.sin(math.tau * freq * 2.01 * t) + 0.05 * noise
    if kind == "ambient_loop":
        return 0.45 * math.sin(math.tau * freq * t) + 0.25 * math.sin(math.tau * freq * 1.5 * t) + 0.2 * noise
    if kind in {"magic_chime", "spell_cast", "pickup", "ui_blip"}:
        sweep = 1.0 + progress * (0.85 if kind == "pickup" else 0.25)
        return 0.62 * math.sin(math.tau * freq * sweep * t) + 0.28 * math.sin(math.tau * freq * 2.0 * t)
    return math.sin(math.tau * freq * t)
