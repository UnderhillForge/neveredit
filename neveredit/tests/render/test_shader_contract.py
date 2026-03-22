from pathlib import Path


def test_core_shader_contains_distance_and_toon_controls():
    glwindow = Path(__file__).resolve().parents[2] / "ui" / "GLWindow.py"
    text = glwindow.read_text(encoding="utf-8")

    assert "uniform float uDistanceDesatStrength;" in text
    assert "uniform int uUseToon;" in text
    assert "uniform float uToonBands;" in text
    assert "uniform float uToonRimStrength;" in text
    assert "shaded = mix(shaded, vec3(luma), fogFactor * uDistanceDesatStrength);" in text
