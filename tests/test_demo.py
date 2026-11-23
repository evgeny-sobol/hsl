"""Golden test: demo.hsl, which exercises every language construct, must
compile to exactly the committed demo.txt.

Run:    python tests/test_demo.py
Update: python tests/test_demo.py --update   (after an intended output change)
"""
import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compiler import compile_folder  # noqa: E402


def compile_demo():
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(ROOT / "demo.hsl", tmp)
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            ok = compile_folder(tmp, force=True)
        assert ok, f"demo.hsl failed to compile:\n{log.getvalue()}"
        return (Path(tmp) / "demo.txt").read_text(encoding="utf-8")


def test_demo_matches_golden_output():
    expected = (ROOT / "demo.txt").read_text(encoding="utf-8")
    assert compile_demo() == expected, \
        "demo.hsl output differs from demo.txt (run with --update if intended)"


if __name__ == "__main__":
    if "--update" in sys.argv:
        (ROOT / "demo.txt").write_text(compile_demo(), encoding="utf-8")
        print("updated: demo.txt")
    else:
        test_demo_matches_golden_output()
        print("ok: demo")
