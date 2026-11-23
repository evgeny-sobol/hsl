"""Regression tests for compiler bugs that used to produce wrong output
silently: each case either compiles to the expected script or must fail.

Run: python tests/test_regressions.py
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compiler import compile_folder  # noqa: E402
from modules.pruning import GENERATED_MARKER, prune_orphan_txt  # noqa: E402
from modules.splicing import _normalize_flat_aborts  # noqa: E402


def compile_hsl(source):
    """Compile one .hsl source. Returns the output text, or None on error."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "t.hsl").write_text(source, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            ok = compile_folder(tmp, force=True)
        return (Path(tmp) / "t.txt").read_text(encoding="utf-8") if ok else None


def squash(text):
    return " ".join(text.split())


def test_break_inside_while_sets_the_loop_flag():
    out = compile_hsl(
        "effect:\n"
        "  while x < 10:\n"
        "    x += 1\n"
        "    if x == 5:\n"
        "      break\n")
    assert out is not None
    flat = squash(out)
    assert "break = hsl_break0" in flat, out
    assert "set_temp_variable = { hsl_break0 = 1 }" in flat, out


def test_break_in_a_scope_loop_is_an_error():
    assert compile_hsl(
        "effect:\n"
        "  for c in every_country():\n"
        "    break\n") is None


def test_tuple_swap_is_an_error():
    assert compile_hsl("effect:\n  a, b = b, a\n") is None


def test_persistent_tuple_swap_is_an_error():
    assert compile_hsl("effect:\n  &a, &b = b, a\n") is None


def test_flat_abort_with_multiple_conditions_wraps_in_and():
    src = (
        "ROM_communist_ttbe = {\n"
        "\tabort = {\n"
        "\t\tis_subject = yes\n"
        "\t\tOVERLORD = {\n"
        "\t\t\tnot = { has_government = communism }\n"
        "\t\t}\n"
        "\t}\n"
        "}\n"
    )
    out = squash(_normalize_flat_aborts(src))
    assert "abort = { OR = { AND = { is_subject = yes OVERLORD = { not = { has_government = communism } } } } }" in out, out


def test_flat_abort_with_single_condition_stays_direct_in_or():
    src = (
        "ROM_hist = {\n"
        "\tabort = {\n"
        "\t\tis_subject = yes\n"
        "\t}\n"
        "}\n"
    )
    out = squash(_normalize_flat_aborts(src))
    assert "abort = { OR = { is_subject = yes } }" in out, out
    assert "AND" not in out, out


def test_independent_tuple_assign_still_works():
    out = compile_hsl("effect:\n  a, b = 1, 2\n")
    assert out is not None
    assert "set_temp_variable = { a = 1 }" in out
    assert "set_temp_variable = { b = 2 }" in out


def test_ampersand_inside_a_name_is_not_swallowed():
    out = compile_hsl("effect:\n  has_idea(x&y)\n")
    assert out is not None
    flat = squash(out)
    assert "AND = { has_idea = x has_idea = y }" in flat, out
    assert "xy" not in flat, out


def test_persistent_marker_is_still_stripped():
    out = compile_hsl("effect:\n  &a = 1\n  GER.&b = 2\n")
    assert out is not None
    assert "set_variable = { a = 1 }" in out, out
    assert "set_variable = { GER.b = 2 }" in out, out


def test_abs_uses_an_exact_sign_instead_of_a_root():
    out = compile_hsl("effect:\n  g = abs(y)\n")
    assert out is not None
    flat = squash(out)
    assert "root" not in flat and "pow" not in flat, out
    assert "greater_than = 0" in flat, out


def test_underscore_loop_variable_is_rejected():
    assert compile_hsl("effect:\n  for _i in range(3):\n    pass\n") is None


def test_prune_keeps_hand_written_txt():
    with tempfile.TemporaryDirectory() as tmp:
        hand = Path(tmp) / "override.txt"
        orphan = Path(tmp) / "orphan.txt"
        hand.write_text("ideas = {\n}\n", encoding="utf-8")
        orphan.write_text(GENERATED_MARKER + "\nx = 1\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            removed = prune_orphan_txt(tmp)
        assert removed == 1
        assert hand.exists(), "hand-written .txt was deleted"
        assert not orphan.exists(), "generated orphan was kept"


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in globals().items()
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"ok: {name}")
