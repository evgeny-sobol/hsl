"""Incremental-build freshness checks: decide whether an output is up to date
relative to its sources and the macro libraries. Pure filesystem/mtime logic.
"""
import os
import re


_MACRO_CALL_RE = re.compile(r'\$[a-z][a-zA-Z0-9_]*\s*\(')


def _uses_macro(path):
    """True if the source file contains at least one `$macro(` call."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return bool(_MACRO_CALL_RE.search(f.read()))
    except OSError:
        return False


def _macro_floor(path, out_path, macros_mtime):
    """Freshness floor for `path`: the newest-macro timestamp only applies when
    the output is older than it AND the source actually calls a macro. Otherwise
    macro changes are irrelevant to this file, so the floor is 0. The mtime gate
    comes first so unaffected files never get re-read on clean builds."""
    om = _mtime(out_path)
    if om is not None and macros_mtime > om and _uses_macro(path):
        return macros_mtime
    return 0.0


def _mtime(path):
    """Modification time of `path`, or None if it does not exist."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return None

def _is_fresh(out_path, ingredient_paths, floor_mtime=0.0):
    """
    True if `out_path` exists and is at least as new as every ingredient.

    `floor_mtime` is an extra dependency timestamp (e.g. the newest .hml macro
    library) that applies to every output. A missing ingredient is ignored;
    a missing output is never fresh.
    """
    out_m = _mtime(out_path)
    if out_m is None:
        return False
    newest_dep = floor_mtime
    for p in ingredient_paths:
        m = _mtime(p)
        if m is not None and m > newest_dep:
            newest_dep = m
    return out_m >= newest_dep
