from forager_ai.diagnostics.jvm_hints import java_args_preset, jvm_heap_preset_mb


def test_java_args_presets_order() -> None:
    m = java_args_preset("minimal")
    b = java_args_preset("balanced")
    e = java_args_preset("extended")
    assert len(m) <= len(b) <= len(e)
    assert "-XX:+UseG1GC" in m
    assert "MaxGCPauseMillis" in " ".join(b)
    assert "AlwaysPreTouch" in " ".join(e)


def test_jvm_heap_preset_light_heavy() -> None:
    mn, mx = jvm_heap_preset_mb("light", balanced_max_mb=4096)
    assert mn < mx
    assert mx == 3072
    mn2, mx2 = jvm_heap_preset_mb("heavy", balanced_max_mb=4096)
    assert mn2 < mx2
    assert mx2 >= 8192


def test_jvm_heap_preset_balanced() -> None:
    mn, mx = jvm_heap_preset_mb("balanced", balanced_max_mb=6000)
    assert mn < mx
    assert mx == 6000
