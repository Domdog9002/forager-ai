"""Canvas waveform preview for procedural audio (no WebGL / Three.js)."""

from __future__ import annotations

import html
import json
from typing import List, Sequence


def downsample_peaks(samples: Sequence[float], *, max_points: int = 1200) -> List[float]:
    """Return max-abs envelope points for canvas polyline."""
    if not samples:
        return []
    n = len(samples)
    cap = max(32, min(int(max_points), n))
    if n <= cap:
        return [float(abs(x)) for x in samples]
    step = n / float(cap)
    out: List[float] = []
    j = 0.0
    for i in range(cap):
        j0 = int(j)
        j1 = min(n, int(j + step))
        chunk = samples[j0:j1] or [0.0]
        out.append(max(abs(float(x)) for x in chunk))
        j += step
    return out


def build_sound_waveform_html(
    *,
    dom_id: str,
    samples: Sequence[float],
    sample_rate: int = 44_100,
    width: int = 720,
    height: int = 140,
) -> str:
    peaks = downsample_peaks(samples, max_points=1400)
    safe_id = html.escape(dom_id, quote=True)
    w = max(200, min(int(width), 1200))
    h = max(80, min(int(height), 400))
    sr = max(8000, min(int(sample_rate), 192_000))
    payload = json.dumps({"peaks": peaks, "sr": sr}, separators=(",", ":"))
    esc_payload = html.escape(payload, quote=False)
    return f"""<div style="width:100%;max-width:100%;border-radius:12px;border:1px solid rgba(148,163,184,0.28);overflow:hidden;background:#0b1220;">
<canvas id="wf-{safe_id}" width="{w}" height="{h}" style="width:100%;height:auto;display:block;"></canvas>
<script type="application/json" id="wfdata-{safe_id}">{esc_payload}</script>
<script>
(function() {{
  var HID = "{safe_id}";
  var c = document.getElementById("wf-" + HID);
  var j = document.getElementById("wfdata-" + HID);
  if (!c || !j) return;
  var data = JSON.parse(j.textContent);
  var peaks = data.peaks || [];
  var sr = data.sr || 44100;
  var ctx = c.getContext("2d");
  var W = c.width, H = c.height;
  ctx.fillStyle = "#0f172a";
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = "rgba(56,189,248,0.35)";
  ctx.lineWidth = 1;
  for (var g = 0; g < 5; g++) {{
    var y = H * (0.15 + g * 0.175);
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
  }}
  if (!peaks.length) {{
    ctx.fillStyle = "#94a3b8";
    ctx.font = "600 13px system-ui,sans-serif";
    ctx.fillText("No waveform data", 12, H/2);
    return;
  }}
  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 1.25;
  ctx.beginPath();
  var mid = H * 0.52;
  var amp = H * 0.38;
  var denom = Math.max(1, peaks.length - 1);
  for (var i = 0; i < peaks.length; i++) {{
    var x = (i / denom) * (W - 4) + 2;
    var y = mid - Math.min(1, peaks[i]) * amp;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }}
  ctx.stroke();
  ctx.strokeStyle = "rgba(167,139,250,0.55)";
  ctx.beginPath();
  for (var i2 = 0; i2 < peaks.length; i2++) {{
    var x2 = (i2 / denom) * (W - 4) + 2;
    var y2 = mid + Math.min(1, peaks[i2]) * amp * 0.55;
    if (i2 === 0) ctx.moveTo(x2, y2); else ctx.lineTo(x2, y2);
  }}
  ctx.stroke();
  ctx.fillStyle = "#64748b";
  ctx.font = "600 11px system-ui,sans-serif";
  ctx.fillText("Live waveform · " + peaks.length + " pts · " + sr + " Hz", 8, 14);
}})();
</script>
</div>"""
