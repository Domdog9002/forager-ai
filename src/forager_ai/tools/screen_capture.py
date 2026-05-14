"""
One-shot primary desktop capture for Windows (best-effort elsewhere).

Used only after explicit user action — never auto-captures.
"""

from __future__ import annotations

import io
import sys
from typing import Tuple

_MAX_LONG_EDGE = 1600
_MAX_BYTES_SOFT = 1_800_000


def capture_primary_screen_png(*, max_long_edge: int = _MAX_LONG_EDGE) -> Tuple[bytes, str]:
    """
    Capture the full virtual screen (all monitors) and return PNG bytes + short note.

    Raises RuntimeError if capture fails.
    """
    try:
        from PIL import Image, ImageGrab
    except ImportError as exc:
        raise RuntimeError("Pillow is required for screen capture.") from exc

    try:
        img = ImageGrab.grab(all_screens=True)
    except TypeError:
        img = ImageGrab.grab()
    except Exception as exc:
        raise RuntimeError(f"Screen grab failed: {exc}") from exc

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    w, h = img.size
    edge = max(w, h)
    if edge > max_long_edge:
        scale = max_long_edge / float(edge)
        nw = max(1, int(w * scale))
        nh = max(1, int(h * scale))
        rs = getattr(getattr(Image, "Resampling", Image), "LANCZOS", getattr(Image, "LANCZOS", Image.BICUBIC))
        img = img.resize((nw, nh), rs)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    raw = buf.getvalue()
    note = f"Captured {w}×{h} → PNG {len(raw) // 1024} KiB (may include all monitors)."
    if len(raw) > _MAX_BYTES_SOFT:
        buf2 = io.BytesIO()
        img2 = img.copy()
        if max(img2.size) > 960:
            edge2 = max(img2.size)
            sc2 = 960 / float(edge2)
            img2 = img2.resize(
                (max(1, int(img2.width * sc2)), max(1, int(img2.height * sc2))),
                getattr(getattr(Image, "Resampling", Image), "LANCZOS", getattr(Image, "LANCZOS", Image.BICUBIC)),
            )
        if img2.mode == "RGBA":
            img2 = img2.convert("RGB")
        elif img2.mode != "RGB":
            img2 = img2.convert("RGB")
        img2.save(buf2, format="JPEG", quality=82, optimize=True)
        raw = buf2.getvalue()
        note = f"Captured {w}×{h} → JPEG (compressed) {len(raw) // 1024} KiB for API size limits."
    return raw, note


def capture_supported() -> bool:
    if sys.platform != "win32":
        return False
    return True
