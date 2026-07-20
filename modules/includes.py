"""Include orchestration: turn an .include file + vanilla text into spliced
output. The heavy lifting lives in paradox_text / include_parser / navigation /
splicing; this module wires them together.

Public entry point: transpile_include_source (used by the compiler).
"""
from modules.include_parser import parse_include
from modules.navigation import find_injection_point, _VanillaIndex
from modules.paradox_text import dedent_lines
from modules.splicing import (
    expand_single_line_blocks_multi, _normalize_flat_aborts,
    reindent_fragment, splice_injections, normalize_eof_braces,
)


def _render_local_hsl(items, indent=0):
    """Render a node's *local* content (leaves + created sub-blocks) back into
    HSL source lines, ready to feed to `compile_fragment`.

    Created sub-blocks become plain `name:` headers (the '+' is only meaningful
    at the navigate/create boundary; everything below a create is created).
    Contiguous leaf runs are dedented as a unit so nested HSL (if/for bodies)
    keeps its shape, then re-indented to the current level."""
    out = []
    pad = '  ' * indent
    i = 0
    n = len(items)
    while i < n:
        it = items[i]
        if isinstance(it, tuple):                      # leaf run
            run = []
            while i < n and isinstance(items[i], tuple):
                run.append(items[i][1])
                i += 1
            for dl in dedent_lines(run):
                out.append(pad + dl if dl else '')
        else:                                          # created sub-block
            out.append(f"{pad}{it.name}:")
            out.extend(_render_local_hsl(it.items, indent + 1))
            i += 1
    return out


def _resolve_nav(vanilla_text, nav_path, index):
    """Where to inject for a navigate path.

    Empty path => file scope. File-scope content (e.g. top-level `@CONSTANT = N`
    declarations) is injected at the START of the file, since HoI4 constants read
    best when declared up top. The third return value is a placement flag:
      'leading'  - prepend a newline before the fragment (join onto prior text);
      'trailing' - append a newline after the fragment (separate it from the text
                   that follows, used for the start-of-file case);
      None       - no extra newline needed."""
    if not nav_path:
        # Inject at column 0, before all existing content.
        return 0, '', 'trailing'
    insert_pos, content_indent = find_injection_point(vanilla_text, nav_path, index)
    return insert_pos, content_indent, None


def _collect(node, nav_path, vanilla_text, compile_fragment, injections, index):
    """Walk navigate nodes; at each, inject all local content (direct leaves +
    created sub-blocks) as one fragment, then recurse into navigate children."""
    local = []
    nav_children = []
    for it in node.items:
        if isinstance(it, tuple) or it.create:
            local.append(it)
        else:
            nav_children.append(it)

    if local:
        insert_pos, content_indent, nl = _resolve_nav(vanilla_text, nav_path, index)
        fragment = compile_fragment(_render_local_hsl(local))
        reindented = reindent_fragment(fragment, content_indent)
        if nl == 'leading':
            reindented = '\n' + reindented
        elif nl == 'trailing':
            reindented = reindented + '\n'
        injections.append((insert_pos, reindented))

    for child in nav_children:
        _collect(child, nav_path + [(child.name, child.selector)],
                 vanilla_text, compile_fragment, injections, index)


def _collect_nav_names(node, acc):
    for it in node.items:
        if isinstance(it, tuple):
            continue
        if not it.create:
            acc.add(it.name)
            _collect_nav_names(it, acc)


def transpile_include_source(vanilla_text, include_source, compile_fragment):
    """
    Core, dependency-free transform.

      vanilla_text     - raw text of the original .txt
      include_source   - raw text of the .include file
      compile_fragment - callable(list[str]) -> str
                         (HSL source lines -> HoI4 code, '\\t' indented,
                          starting at column 0, no trailing newline)

    Returns the new .txt text.
    """
    # Some vanilla/mod files omit their final top-level '}' (the engine auto-
    # closes at EOF); restore it so strict brace-matching can splice the delta.
    vanilla_text = normalize_eof_braces(vanilla_text)

    root = parse_include(include_source)

    nav_names = set()
    _collect_nav_names(root, nav_names)
    vanilla_text = expand_single_line_blocks_multi(vanilla_text, nav_names)

    # If the include navigates into an abort block, flat aborts must be wrapped
    # in OR so the abort:/OR: path resolves.
    if "abort" in nav_names:
        vanilla_text = _normalize_flat_aborts(vanilla_text)

    index = _VanillaIndex(vanilla_text)
    injections = []
    _collect(root, [], vanilla_text, compile_fragment, injections, index)
    return splice_injections(vanilla_text, injections)
