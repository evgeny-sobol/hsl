import os
import re
import sys
from lark import Lark
from lark.indenter import Indenter
from modules.transformer import HslTransformer
from modules import includes
from modules.codegen import generate_hoi4_code
from modules.freshness import _macro_floor, _mtime, _is_fresh
from modules.pruning import prune_orphan_txt


class HslIndenter(Indenter):
    NL_type = '_NL'
    OPEN_PAREN_types = ['_LPAR', '_LSQB']
    CLOSE_PAREN_types = ['_RPAR', '_RSQB']
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 2


def _strip_trailing_comment(line):
    """Drop a trailing `# ...` comment from a code line.

    A line that is *only* a comment is left alone: those are real statements
    (the `comment` rule) and survive into the generated script. A '#' inside a
    double-quoted string is not a comment.
    """
    if line.lstrip().startswith('#'):
        return line
    in_str = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"' and (i == 0 or line[i - 1] != '\\'):
            in_str = not in_str
        elif c == '#' and not in_str:
            return line[:i].rstrip()
        i += 1
    return line


# ---------------------------------------------------------------------------
# Line continuations
# ---------------------------------------------------------------------------
# Join physical lines into one logical line BEFORE HslIndenter runs, so a
# trailing operator (or explicit backslash) does not produce a spurious _NL
# that ends the statement. Longer suffixes first so '**' wins over '*', etc.
_CONTINUATION_SUFFIXES = (
    '**=', '+=', '-=', '*=', '/=',
    '**', '==', '!=', '<=', '>=',
    '->',
    '+', '-', '*', '/', '%',
    '=', '<', '>',
    ',',
    'and', 'or',
)


def _ends_inside_string(s):
    """True if `s` ends while still inside a double-quoted string."""
    in_str = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '"' and (i == 0 or s[i - 1] != '\\'):
            in_str = not in_str
        i += 1
    return in_str


def _code_ends_with_continuation(code):
    """True if `code` (comment already stripped) ends with a joinable operator."""
    s = code.rstrip()
    if not s:
        return False
    # Do not treat an unterminated string as a continuation carrier.
    if _ends_inside_string(s):
        return False
    for suf in _CONTINUATION_SUFFIXES:
        if not s.endswith(suf):
            continue
        # '++' / '--' are complete inc/dec statements, not a trailing + or -.
        # Without this guard, `&x++\n&y--` is wrongly glued into one line.
        if suf in ('+', '-') and len(s) >= 2 and s[-2] == suf:
            continue
        if suf.isalpha():
            # Word boundary: 'standard' must not match suffix 'and'.
            before = s[:-len(suf)]
            if before and (before[-1].isalnum() or before[-1] == '_'):
                continue
            return True
        return True
    return False


def join_line_continuations(source_code):
    """Merge physical lines that continue an expression into one logical line.

    Two forms (both Python-flavoured):
      1. Explicit backslash: `expr \\` + newline
      2. Trailing operator:  `expr /`  + newline  (the common HSL case)

    Runs before empty-line markers and before HslIndenter, so the indenter
    never sees a fake indent on the continuation line and never emits _NL
    in the middle of the expression.
    """
    lines = source_code.splitlines()
    if not lines:
        return source_code

    out = []
    buf = lines[0]

    for nxt in lines[1:]:
        # Full-line comments are real statements — never glue onto them.
        if buf.lstrip().startswith('#'):
            out.append(buf)
            buf = nxt
            continue

        code = _strip_trailing_comment(buf).rstrip()

        # 1) backslash-continuation (ignore if the '\\' sits inside a string)
        if code.endswith('\\') and not _ends_inside_string(code[:-1]):
            buf = code[:-1].rstrip() + ' ' + nxt.lstrip()
            continue

        # 2) operator-continuation
        if _code_ends_with_continuation(code):
            buf = code + ' ' + nxt.lstrip()
            continue

        out.append(buf)
        buf = nxt

    out.append(buf)
    return '\n'.join(out)


def preserve_empty_lines(source_code):
    """
    Finds all empty lines and inserts a hidden comment into each one,
    copying the indentation level from the next non-empty line.
    This prevents HslIndenter from breaking the block structure.
    """
    # Flatten expression continuations first so Indenter never sees a
    # mid-expression newline (or a bogus indent on the next physical line).
    source_code = join_line_continuations(source_code)

    lines = source_code.splitlines()
    # Trailing comments are stripped before parsing: the grammar only allows a
    # comment as its own statement, and threading an optional comment through
    # every statement rule is far more fragile than removing it here.
    lines = [_strip_trailing_comment(l) for l in lines]
    for i in range(len(lines)):
        if lines[i].strip() == '':
            indent = ""
            for j in range(i + 1, len(lines)):
                if lines[j].strip() != '':
                    match = re.match(r'^[ \t]*', lines[j])
                    if match:
                        indent = match.group(0)
                    break
            lines[i] = indent + '#___EMPTY_LINE___'

    # Two empty lines at zero indentation at the end:
    # the first gives HslIndenter a trigger to emit _DEDENT,
    # the second gives the parser a _NL token after _DEDENT
    lines.append('')
    lines.append('')

    return '\n'.join(lines)


def compile_fragment(lines, parser, transformer, cache=None):
    """
    Compile a snippet of HSL source lines into HoI4 code.

    Returns tab-indented code starting at column 0, with no trailing newline.
    This is the exact per-file pipeline used by compile_folder, minus the file
    I/O, so .include payloads compile identically to standalone .hsl files
    (macros included, since the shared transformer is passed in).

    `cache` (optional dict) memoizes results by payload text. Since macros are
    fixed for the duration of a run, identical payloads — common when many
    focuses get the same ai_will_do override — are parsed only once.
    """
    src = "\n".join(lines)
    if cache is not None and src in cache:
        return cache[src]

    prepared = preserve_empty_lines(src + "\n")
    tree = parser.parse(prepared)
    ast_data = transformer.transform(tree)
    code = generate_hoi4_code(ast_data)
    code = re.sub(r'^[ \t]*#___EMPTY_LINE___$', '', code, flags=re.MULTILINE)
    code = code.rstrip("\n")

    if cache is not None:
        cache[src] = code
    return code


def process_include_file(include_path, target_folder, vanilla_root, parser, transformer,
                         macros_mtime=0.0, force=False, fragment_cache=None):
    """
    Splice an .include delta into its vanilla counterpart and write the
    resulting .txt next to the .include file.

    The .include mirrors the vanilla directory layout: an .include at
    <mod>/common/on_actions/foo.include targets <vanilla>/common/on_actions/foo.txt.

    Returns one of: 'built', 'skipped' (output already up to date), or
    'missing' (vanilla source not found). Rebuild is skipped when the output
    exists and is newer than all three ingredients: the .include, the vanilla
    .txt, and the newest .hml macro library (macros_mtime). `force` bypasses
    the freshness check.
    """
    rel = os.path.relpath(include_path, target_folder)
    rel_txt = rel.rsplit('.', 1)[0] + ".txt"
    vanilla_path = os.path.join(vanilla_root, rel_txt)
    out_path = os.path.splitext(include_path)[0] + ".txt"

    if not os.path.exists(vanilla_path):
        print(f"  Vanilla source not found: {vanilla_path}")
        return 'missing'

    if not force and _is_fresh(out_path, [include_path, vanilla_path], macros_mtime):
        return 'skipped'

    with open(vanilla_path, "r", encoding="utf-8-sig") as f:
        vanilla_text = f.read()
    with open(include_path, "r", encoding="utf-8-sig") as f:
        include_src = f.read()

    result = includes.transpile_include_source(
        vanilla_text,
        include_src,
        lambda payload: compile_fragment(payload, parser, transformer, fragment_cache),
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)
    return 'built'


def _load_macro_libraries(target_folder, parser):
    """Collect and compile every .hml macro library from the compiler's own dir
    (the standard library) and the target folder, into a shared macro dict.

    Returns (global_macros, macros_mtime) on success, or None on error (a
    duplicate macro name or an unreadable library), after printing the reason.
    macros_mtime is the newest library timestamp — an implicit dependency of
    every output, since all files compile through the macro-aware transformer.
    """
    global_macros = {}  # This dictionary will store all processed macros

    # Recursively collect every .hml macro library. Two sources:
    #   1. the compiler's own directory (the macro "standard library"), and
    #   2. the target folder (project-local macros).
    # Deduped by real path so a target inside the compiler dir isn't scanned twice.
    # Stdlib loads first so project .hml files can call $stdlib macros; each
    # source is sorted on its own for a deterministic order within that source.
    stdlib_dir = os.path.dirname(os.path.abspath(__file__))
    seen_hml = set()
    hml_paths = []
    for base in (stdlib_dir, target_folder):
        batch = []
        for root, _dirs, files in os.walk(base):
            for f in files:
                if not f.endswith('.hml'):
                    continue
                p = os.path.realpath(os.path.join(root, f))
                if p not in seen_hml:
                    seen_hml.add(p)
                    batch.append(p)
        batch.sort()
        hml_paths.extend(batch)

    # Newest macro-library timestamp: an implicit dependency of EVERY output,
    # since both .hsl files and .include payloads compile through the macro-aware
    # transformer. If any .hml changes, dependent outputs must be rebuilt.
    macros_mtime = 0.0
    for p in hml_paths:
        m = _mtime(p)
        if m is not None and m > macros_mtime:
            macros_mtime = m

    if hml_paths:
        print(f"Found macro libraries: {len(hml_paths)}. Loading...")

    # A single transformer fills the shared global_macros dict across all files
    hml_transformer = HslTransformer(external_macros=global_macros)

    macro_origin = {}  # macro name -> file that first defined it

    for hml_path in hml_paths:
        relative_path = os.path.relpath(hml_path, target_folder)
        try:
            with open(hml_path, "r", encoding="utf-8-sig") as f:
                hml_code = f.read()

            hml_code = preserve_empty_lines(hml_code)
            # Parse the HML code into an AST tree using our grammar
            hml_tree = parser.parse(hml_code)

            # Snapshot before transforming, so we can report what this file
            # contributes and detect duplicate macro names across files.
            before = dict(global_macros)
            hml_transformer.transform(hml_tree)

            added = [k for k in global_macros if k not in before]
            overridden = [k for k in global_macros
                          if k in before and global_macros[k] is not before[k]]

            # Duplicate macro definitions are a hard error: the standard
            # library and project macros share one namespace.
            if overridden:
                print("Error: duplicate macro definition(s):")
                for name in sorted(overridden):
                    first = os.path.relpath(macro_origin.get(name, '?'), target_folder)
                    print(f"  - '{name}' redefined in {relative_path} "
                          f"(first defined in {first})")
                return None

            for name in added:
                macro_origin[name] = hml_path

            print(f"  - {relative_path}: +{len(added)} macro(s)")

        except Exception as e:
            print(f"Error while reading macro library '{relative_path}': {e}")
            return None

    print(f"Successfully loaded macros: {len(global_macros)}")

    return global_macros, macros_mtime

def _compile_hsl_file(hsl_path, root, target_folder, parser, transformer,
                      macros_mtime, force):
    """Compile one standalone .hsl file into its sibling .txt.

    Returns 'skipped' (up to date), 'built' (compiled), or 'error'.
    """
    filename = os.path.basename(hsl_path)
    txt_path = os.path.join(root, filename.rsplit('.', 1)[0] + ".txt")
    relative_path = os.path.relpath(hsl_path, target_folder)

    # Incremental build: skip if the .txt is newer than the .hsl. A changed
    # .hml only forces a rebuild when this file actually calls a macro.
    floor = _macro_floor(hsl_path, txt_path, macros_mtime)
    if not force and _is_fresh(txt_path, [hsl_path], floor):
        return 'skipped'

    print(f"Compiling: {relative_path}...")
    try:
        with open(hsl_path, "r", encoding="utf-8-sig") as f:
            source_code = f.read() + "\n"

        source_code = preserve_empty_lines(source_code)
        tree = parser.parse(source_code)
        ast_data = transformer.transform(tree)
        final_code = generate_hoi4_code(ast_data)

        # Turn indent-marker lines back into real empty lines.
        final_code = re.sub(r'^[ \t]*#___EMPTY_LINE___$', '',
                            final_code, flags=re.MULTILINE)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(final_code)
        return 'built'
    except Exception as e:
        print(f"Error in file {filename}: {e}")
        return 'error'


def compile_folder(target_folder, vanilla_root=None, force=False):
    """
    Recursively finds all .hsl and .include files in the specified directory and
    all its subdirectories, then compiles them into the game's .txt files.

    .hsl     - full files, compiled standalone into a sibling .txt.
    .include - delta injections spliced into a mirrored vanilla file; requires
               vanilla_root to locate the original .txt.
    """
    errors = 0
    # Defensive: strip stray surrounding quotes (illegal in paths anyway) so a
    # quoted vanilla root passed programmatically or via a shell quirk still works.
    if vanilla_root:
        vanilla_root = vanilla_root.strip().strip('"')
    grammar_path = "modules/grammar.lark"
    if not os.path.exists(grammar_path):
        print(f"Error: Grammar file '{grammar_path}' not found in the project root!")
        return False
    # Initialize Lark
    print(f"Loading grammar from {grammar_path}...")
    parser = Lark.open(grammar_path, start='start', parser='lalr', postlex=HslIndenter())
    transformer = HslTransformer()

    loaded = _load_macro_libraries(target_folder, parser)
    if loaded is None:
        return False
    global_macros, macros_mtime = loaded
    transformer.macros = global_macros

    if not os.path.exists(target_folder):
        print(f"Error: The specified directory '{target_folder}' does not exist!")
        return False

    print(f"Scanning directory '{target_folder}' and all subdirectories...")
    print("-" * 50)

    compiled_count = 0
    skipped_count = 0

    # Per-run memo for compiled .include payloads (safe: macros are fixed now).
    fragment_cache = {}

    # Use os.walk to recursively traverse all subdirectories
    # root - current directory, dirs - list of subdirectories, files - files within it
    for root, dirs, files in os.walk(target_folder):
        hsl_files = [f for f in files if f.endswith('.hsl')]
        include_files = [f for f in files if f.endswith('.include')]

        # Skip only directories that have neither kind of source file.
        if not hsl_files and not include_files:
            continue

        # ---- Standalone .hsl -> sibling .txt --------------------------------
        for filename in hsl_files:
            hsl_path = os.path.join(root, filename)
            status = _compile_hsl_file(hsl_path, root, target_folder,
                                       parser, transformer, macros_mtime, force)
            if status == 'built':
                compiled_count += 1
            elif status == 'skipped':
                skipped_count += 1
            else:  # 'error'
                errors += 1

        # ---- Delta .include -> spliced .txt ---------------------------------
        for filename in include_files:
            include_path = os.path.join(root, filename)
            relative_path = os.path.relpath(include_path, target_folder)

            if vanilla_root is None:
                print(f"Including: {relative_path}...")
                print("  No vanilla root provided (pass it as the 2nd argument). Skipped.")
                continue

            # A changed .hml only forces an include rebuild when the .include
            # payload calls a macro. out_path mirrors process_include_file.
            inc_out = os.path.splitext(include_path)[0] + ".txt"
            inc_floor = _macro_floor(include_path, inc_out, macros_mtime)

            try:
                status = process_include_file(include_path, target_folder, vanilla_root,
                                              parser, transformer,
                                              macros_mtime=inc_floor, force=force,
                                              fragment_cache=fragment_cache)
            except (KeyError, ValueError) as e:
                # Address resolution / structural errors: report and keep going.
                print(f"Including: {relative_path}...")
                print(f"  {filename}: {e}")
                errors += 1
                continue
            except Exception as e:
                print(f"Including: {relative_path}...")
                print(f"  Error in include {filename}: {e}")
                errors += 1
                continue

            if status == 'built':
                print(f"Including: {relative_path}...")
                compiled_count += 1
            elif status == 'skipped':
                skipped_count += 1
            elif status == 'missing':
                # already reported its own line inside process_include_file
                errors += 1

    print("-" * 50)
    removed_count = prune_orphan_txt(target_folder)
    summary = f"Recursive compilation completed! Total files processed: {compiled_count}"
    if skipped_count:
        summary += f", up to date (skipped): {skipped_count}"
    if removed_count:
        summary += f", orphans removed: {removed_count}"
    if errors:
        summary += f", ERRORS: {errors}"
    print(summary)
    return errors == 0

if __name__ == "__main__":
    # Usage: python compiler.py [target_dir] [vanilla_root] [--force]
    # --force (or -f) rebuilds everything, ignoring the incremental mtime check.
    force = False
    positional = []
    for arg in sys.argv[1:]:
        if arg in ('-f', '--force'):
            force = True
        else:
            # Strip stray quotes: on Windows a trailing '\\' before the closing
            # quote (e.g. "C:\\...\\Hearts of Iron IV\\") escapes the quote, leaving
            # a literal '"' embedded in the argument. Quotes are illegal in paths
            # anyway, so stripping them from the ends is always safe.
            positional.append(arg.strip().strip('"'))

    target_dir = positional[0] if positional else "."
    vanilla_root = positional[1] if len(positional) > 1 else None

    ok = compile_folder(target_dir, vanilla_root, force=force)
    sys.exit(0 if ok else 1)
