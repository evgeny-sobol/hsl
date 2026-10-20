"""Regression test for the `.include` `-name:` removal operator.

The operator deletes an existing child block from the addressed parent without
touching siblings. It guards the Rt56 GXC fix, where a bare character scope is
removed and re-scoped.

Run: python tests/test_include_removal.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.includes import transpile_include_source  # noqa: E402

VANILLA = (
    "ideas = {\n"
    "    GXC_jihad = {\n"
    "        available = {\n"
    "            OR = {\n"
    "                AND = {\n"
    "                    NOT = { original_tag = GXC }\n"
    "                }\n"
    "                GXC_bai_chongxi = { is_hired_as_advisor = yes }\n"
    "            }\n"
    "            NOT = { has_government = communism }\n"
    "        }\n"
    "    }\n"
    "    GXC_other = {\n"
    "        available = { always = yes }\n"
    "    }\n"
    "}\n"
)

INCLUDE = (
    "ideas:\n"
    "  GXC_jihad:\n"
    "    available:\n"
    "      OR:\n"
    "        -GXC_bai_chongxi:\n"
)


def test_removal_drops_the_block_and_keeps_siblings():
    out = transpile_include_source(VANILLA, INCLUDE, None)
    assert "GXC_bai_chongxi" not in out, "target block was not removed"
    assert "GXC_other" in out, "sibling block was lost"
    assert "original_tag = GXC" in out, "sibling branch was lost"
    assert "has_government = communism" in out, "parent tail was lost"


if __name__ == "__main__":
    test_removal_drops_the_block_and_keeps_siblings()
    print("ok: include removal")
