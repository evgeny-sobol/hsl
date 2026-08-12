# HSL — HoI4 Scripting Language

**A Python-like language that compiles to Hearts of Iron IV (Clausewitz) script.**

Modding HoI4 means writing deeply nested, verbose `key = { ... }` blocks by hand — no arithmetic, no real control flow, no reuse. HSL lets you write compact, readable code with variables, expressions, loops, conditionals, `match`, arrays, and macros, then compiles it down to the exact vanilla script the game expects.

```python
# HSL
modifier:
  f = clamp(1 - opinion@FRA / 100, 0.0, 2.0)
  factor(f)
```

compiles to:

```perl
# HoI4 script
modifier = {
    set_temp_variable = {
        f = {
            value = { value = 1  subtract = { value = opinion@FRA  divide = 100 } }
            clamp = { min = 0.0  max = 2.0 }
        }
    }
    factor = f
}
```

## Features

- **Arithmetic expressions** with full operator precedence and parentheses — `+ - * / % **`, plus `sqrt`, `abs`, `round`, `clamp`. Compiles to nested accumulator value-blocks, no manual temp-variable scaffolding.
- **Line continuations** — a trailing operator (`+ - * / % ** = ==` …) or an explicit `\` joins the next physical line into one logical expression (Python-style). Safe inside strings and full-line comments.
- **Control flow** — `if` / `elif` / `else`, `while`, `break`, and `match` / `case` (with `|` patterns and a `_` default).
- **Loops** — numeric `for x in range(...)`, scope iteration `for c in every_country()`, and indexed array iteration `for value, index in arr[]`.
- **Arrays** — add / erase / remove_at / pop / clear / resize, indexing, size, min/max, `rand` / `rand_idx`, and `in` / `not in` membership tests.
- **Variables** — temp by default; a leading `&` marks persistent. Compound assignment, `++`/`--`, tuple assign (`a, b = 1, 2`), `null` clearing.
- **Scoped calls** — `scope->trigger(arg)`, multi-level chains `A->B->C(x)`, block form `scope->name:`, country-tag heads (`$GER->...`), and `scope->$macro(args)`.
- **Trigger sugar** — `trigger(a | b | c)` → OR, `trigger(a & b & c)` → AND.
- **Macros** — compile-time expansion with default arguments, optional params via `if defined(_p_):`, `{param}` brace-interpolation inside identifiers, and a reusable standard library.
- **LINQ-style filtering** — `every_country().which()`.
- **Scorers** — `get_highest_scored_country`, `get_sorted_scored_countries`.
- **`raw` escape hatch** — pass verbatim Clausewitz through untouched for anything HSL doesn't model natively.
- **`.include` delta system** — inject changes into vanilla HoI4 files without copying them.
- **Editor support** — [`udl_for_notepad++.xml`](udl_for_notepad++.xml) User-Defined Language for Notepad++ (`.hsl` / `.hml` / `.include`).

See [`demo.hsl`](demo.hsl) for a full showcase of every construct.

### Line continuations

Long expressions can span multiple lines. Two forms:

```python
# 1) Trailing operator (most common) — the line ends with an operator
f = 1.5 * (mtth:democracy_factor + mtth:fascism_factor) /
    (2 * mtth:democracy_factor + mtth:communism_factor + mtth:fascism_factor) * 2

# 2) Explicit backslash
g = 10 + 20 + \
    30 + 40
```

Joining runs before the indenter, so the continuation line's indentation is ignored and never produces a spurious statement break. A `#` comment on a continued line is stripped first; full-line comments and content inside `"..."` strings are never treated as continuations.

## Status

HSL is under active development and was built to power [a personal HoI4 AI mod](https://github.com/evgeny-sobol/hoi4-sandbox-mode), but it works for any HoI4 scripting. It targets HoI4 **v1.19.2**; because the compiler emits engine script, some constructs are best verified in-game.

# Running the HSL compiler

Two scripts live in the project root (`hsl/`):

- **`compiler.py`** — the compiler. A single pass: finds every `.hsl`/`.include` file in the target folder, compiles them to HoI4 script (`.txt`) next to the sources, applies `.include` deltas to vanilla files, and removes orphaned `.txt` files. Macros (`.hml`) are picked up both from the compiler's own directory (the standard library) and from the target folder.
- **`watcher.py`** — a background watcher. Monitors `.hsl`/`.hml`/`.include` files in the target folder and re-runs `compiler.py` automatically on every save. On a failed build it beeps and brings the console to the foreground. It is a wrapper around `compiler.py`, not a separate compiler.

> `watcher.py` is **Windows-only** — it uses `ctypes.windll` to control the console window. `compiler.py` is cross-platform.

## Setting up the environment

You need Python 3 and one package — `lark`.

```
# from the project root (where compiler.py and requirements.txt live)
python -m venv venv
venv\Scripts\activate           # Windows
# source venv/bin/activate      # Linux/macOS

pip install -r requirements.txt
```

`requirements.txt` pins `lark==1.3.1` — the version the grammar was verified against. Using a different version is not recommended: LALR parser behavior can differ between Lark releases.

## Running the compiler

```
python compiler.py [target_dir] [vanilla_root] [--force | -f]
```

- **`target_dir`** — folder with your `.hsl`/`.include` sources. Optional, defaults to the current folder (`.`). Scanned recursively.
- **`vanilla_root`** — path to the vanilla HoI4 files (e.g. the game's `common/` tree). Needed only for `.include` deltas; without it, `.include` files are skipped and plain `.hsl` files still compile normally.
- **`--force` / `-f`** — full rebuild, ignoring the incremental mtime check.

The positional argument order is fixed: `target_dir` first, then `vanilla_root`. Surrounding quotes on paths are stripped automatically (handy for Windows paths with spaces).

Exit code: `0` on success, `1` on a compilation error (usable in scripts and CI).

### Examples

```
# compile the current folder, no .include deltas
python compiler.py

# a specific mod folder + vanilla files for .include
python compiler.py "C:\Games\...\mod\_sandbox" "C:\Games\...\Hearts of Iron IV"

# full rebuild
python compiler.py "C:\Games\...\mod\_sandbox" -f
```

> **Important:** after editing the compiler's Python files (grammar, transformers), the incremental build does not track them — run with `--force`, otherwise your changes won't be picked up.

## Running the watcher (Windows)

```
python watcher.py [target_dir] [vanilla_root] [--interval SECONDS] [--force | -f]
```

Same arguments as `compiler.py`, plus:

- **`--interval`** — folder polling period in seconds (default `0.4`).

The watcher snapshots the modification times of all `.hsl`/`.hml`/`.include` files, and whenever something changes it invokes `compiler.py` with the same arguments. Generated `.txt` files won't retrigger a build on the next tick. Stop with `Ctrl+C`.

### Example workflow

```
venv\Scripts\activate
python watcher.py "C:\Games\...\mod\_sandbox" "C:\Games\...\Hearts of Iron IV"
```

Leave the window open and edit `.hsl` in your editor — every save rebuilds the mod. On an error the watcher window pops to the front with a beep and shows what broke.

## Editor support (Notepad++)

Import [`udl_for_notepad++.xml`](udl_for_notepad++.xml) via **Language → User Defined Language → Define your language… → Import**. It covers keywords, builtins, scope prefixes (`var:` / `token:` / `mtth:`), array methods, and country tags for `.hsl`, `.hml`, and `.include` files.
