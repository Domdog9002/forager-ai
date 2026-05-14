from __future__ import annotations

from forager_ai.ui.sound_waveform_preview import build_sound_waveform_html, downsample_peaks


def test_downsample_peaks_short() -> None:
    xs = [0.1, -0.4, 0.2, 0.0, -0.9]
    assert downsample_peaks(xs, max_points=100) == [abs(x) for x in xs]


def test_downsample_peaks_long() -> None:
    xs = [((i % 17) - 8) / 10.0 for i in range(5000)]
    out = downsample_peaks(xs, max_points=200)
    assert len(out) <= 200
    assert len(out) >= 32
    assert all(isinstance(x, float) for x in out)


def test_build_sound_waveform_html() -> None:
    html = build_sound_waveform_html(dom_id="w1", samples=[0.0, 0.5, -0.25, 0.1] * 200, sample_rate=44100, width=400, height=100)
    assert "wf-w1" in html
    assert "peaks" in html


def test_downsample_single_sample() -> None:
    assert downsample_peaks([0.42], max_points=100) == [0.42]
