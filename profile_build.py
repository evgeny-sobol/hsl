"""Profile a --force build and show where time actually goes.

Usage:
    python profile_build.py <target_dir> [vanilla_root]

Writes full output to profile.txt and prints a focused summary: the top
functions overall, plus the include-pipeline functions specifically
(expand_single_line_blocks / normalize_eof_braces / _VanillaIndex / splice /
transpile), so you can see whether they dominate on YOUR real mod.
"""
import sys, cProfile, pstats
from compiler import compile_folder

target  = sys.argv[1] if len(sys.argv) > 1 else "."
vanilla = sys.argv[2] if len(sys.argv) > 2 else None

pr = cProfile.Profile()
pr.enable()
compile_folder(target, vanilla, force=True)
pr.disable()

with open("profile.txt", "w") as fh:
    st = pstats.Stats(pr, stream=fh)
    st.sort_stats("cumulative").print_stats(60)
    st.sort_stats("tottime").print_stats(60)

st = pstats.Stats(pr)

print("\n" + "=" * 72)
print("TOP 15 BY OWN TIME")
print("=" * 72)
st.sort_stats("tottime").print_stats(15)

# Match include-pipeline functions by name, regardless of path formatting.
INCLUDE_FUNCS = ("expand_single_line_blocks", "normalize_eof_braces",
                 "_eof_brace_deficit", "transpile_include_source",
                 "splice_injections", "_VanillaIndex", "_match_closing_brace",
                 "_normalize_flat_aborts", "parse_include")
print("\n" + "=" * 72)
print("INCLUDE PIPELINE (by cumulative time)")
print("=" * 72)
st.sort_stats("cumulative").print_stats("|".join(INCLUDE_FUNCS))

print("Full report written to profile.txt")
