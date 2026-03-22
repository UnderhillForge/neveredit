import os
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def _extract_shader(source_text, symbol_name):
    pattern = r"%s\s*=\s*'''(.*?)'''" % re.escape(symbol_name)
    m = re.search(pattern, source_text, re.S)
    assert m, "missing shader symbol %s" % symbol_name
    return m.group(1)


def _load_core_model_shaders():
    src_path = Path(__file__).resolve().parents[2] / "ui" / "GLWindow.py"
    source = src_path.read_text(encoding="utf-8")
    vertex = _extract_shader(source, "CORE_MODEL_VERTEX_SHADER")
    fragment = _extract_shader(source, "CORE_MODEL_FRAGMENT_SHADER")
    return vertex, fragment


def _render_core_model_reference(moderngl, ctx, vertex, fragment, size=(64, 64)):
    prog = ctx.program(vertex_shader=vertex, fragment_shader=fragment)

    positions = np.array([
        -0.75, -0.70, 0.00,
         0.80, -0.55, 0.00,
         0.00,  0.82, 0.00,
    ], dtype="f4")
    normals = np.array([
        0.0, 0.0, 1.0,
        0.0, 0.0, 1.0,
        0.0, 0.0, 1.0,
    ], dtype="f4")
    texcoords = np.array([
        0.0, 0.0,
        1.0, 0.0,
        0.5, 1.0,
    ], dtype="f4")
    instance_cols = np.array([
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ], dtype="f4")

    vbo_pos = ctx.buffer(positions.tobytes())
    vbo_norm = ctx.buffer(normals.tobytes())
    vbo_uv = ctx.buffer(texcoords.tobytes())
    vbo_inst = ctx.buffer(instance_cols.tobytes())

    vao = ctx.vertex_array(prog, [
        (vbo_pos, "3f", "aPosition"),
        (vbo_norm, "3f", "aNormal"),
        (vbo_uv, "2f", "aTexCoord"),
        (vbo_inst, "4f 4f 4f 4f /i", "aInstanceCol0", "aInstanceCol1", "aInstanceCol2", "aInstanceCol3"),
    ])

    tex = ctx.texture((1, 1), 4, b"\xff\xff\xff\xff")
    tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
    tex.use(location=0)

    fbo = ctx.simple_framebuffer(size, components=4)
    fbo.use()
    ctx.viewport = (0, 0, size[0], size[1])
    ctx.clear(0.08, 0.09, 0.11, 1.0)

    identity = np.identity(4, dtype="f4")
    prog["uViewProj"].write(identity.tobytes())
    prog["uModel"].write(identity.tobytes())
    prog["uUseInstancing"].value = 0
    prog["uBaseColor"].value = (0.92, 0.82, 0.72, 1.0)
    prog["uLightDir"].value = (0.0, 0.0, -1.0)
    prog["uCameraPos"].value = (0.0, 0.0, 2.0)
    prog["uTexture0"].value = 0
    prog["uUseTexture"].value = 0
    prog["uAmbientColor"].value = (0.24, 0.28, 0.35)
    prog["uDiffuseColor"].value = (0.84, 0.70, 0.54)
    prog["uFogColor"].value = (0.44, 0.52, 0.60)
    prog["uFogNear"].value = 1.0
    prog["uFogFar"].value = 3.0
    prog["uDistanceDesatStrength"].value = 0.18
    prog["uUseFog"].value = 1
    prog["uUseToon"].value = 1
    prog["uToonBands"].value = 5.0
    prog["uToonRimStrength"].value = 0.35
    prog["uTwoSidedLighting"].value = 0

    vao.render(mode=moderngl.TRIANGLES)
    image = Image.frombytes("RGBA", size, fbo.read(components=4, alignment=1))
    return image.transpose(Image.FLIP_TOP_BOTTOM)


def _assert_matches_golden(image, golden_path, tmp_path):
    golden = Image.open(golden_path).convert("RGBA")
    assert image.size == golden.size

    actual = np.asarray(image, dtype=np.int16)
    expected = np.asarray(golden, dtype=np.int16)
    diff = np.abs(actual - expected)
    max_delta = int(diff.max())
    mean_delta = float(diff.mean())
    if max_delta <= 2 and mean_delta <= 0.25:
        return

    actual_path = tmp_path / "core_shader_actual.png"
    diff_path = tmp_path / "core_shader_diff.png"
    image.save(actual_path)
    Image.fromarray(diff.astype("u1"), mode="RGBA").save(diff_path)
    pytest.fail(
        "golden render mismatch: max_delta=%d mean_delta=%.4f actual=%s diff=%s"
        % (max_delta, mean_delta, actual_path, diff_path)
    )


@pytest.mark.render
def test_headless_shader_compile_smoke():
    moderngl = pytest.importorskip("moderngl")

    vertex, fragment = _load_core_model_shaders()

    try:
        ctx = moderngl.create_standalone_context(require=330)
    except Exception as exc:
        pytest.skip("No standalone OpenGL context available: %s" % exc)

    prog = ctx.program(vertex_shader=vertex, fragment_shader=fragment)
    assert "uUseToon" in prog
    assert "uDistanceDesatStrength" in prog


@pytest.mark.render
def test_headless_shader_image_diff(tmp_path):
    if os.environ.get("NEVEREDIT_RENDER_IMAGE_DIFF", "").lower() not in ("1", "true", "yes", "on"):
        pytest.skip("Set NEVEREDIT_RENDER_IMAGE_DIFF=1 to enable golden image comparison")

    moderngl = pytest.importorskip("moderngl")
    vertex, fragment = _load_core_model_shaders()

    try:
        ctx = moderngl.create_standalone_context(require=330)
    except Exception as exc:
        pytest.skip("No standalone OpenGL context available: %s" % exc)

    image = _render_core_model_reference(moderngl, ctx, vertex, fragment)
    golden_path = Path(__file__).resolve().parent / "golden" / "core_shader_reference.png"
    _assert_matches_golden(image, golden_path, tmp_path)
