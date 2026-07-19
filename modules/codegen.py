"""HSL code generation: AST -> Hearts of Iron IV (Clausewitz) script text.

Pure rendering layer, the counterpart to the transformer (which does text->AST).
Depends only on `re`; imported by the compiler orchestrator.
"""
import re


def resolve_scopes(text, scope_stack):
    if not isinstance(text, str):
        return text

    # Strip the persistent-variable marker '&' (compiler-only) from every
    # emitted name. It may sit at the start (`&foo`) or after a scope prefix
    # (`global.&foo`); a regex removes it wherever it directly precedes an
    # identifier. Runs regardless of scope_stack so reads are cleaned too.
    if "&" in text:
        text = re.sub(r'&(?=[A-Za-z_])', '', text)

    if not scope_stack:
        return text

    # Traverse the stack backwards
    # Index 0 = last added item (THIS)
    # Index 1 = second to last item (PREV), and so on
    for index, var_name in enumerate(reversed(scope_stack)):
        pointer = "THIS" if index == 0 else ".".join(["PREV"] * index)

        # Match whole words only (\b) to avoid breaking partial matches
        text = re.sub(rf'\b{re.escape(var_name)}\b', pointer, text)

    return text


def generate_hoi4_code(ast, indent_level=0, scope_stack=None):
    """
    Recursively converts the AST back into Hearts of Iron IV source code.
    """
    if scope_stack is None:
        scope_stack = []

    strings = []
    spacing = "\t" * indent_level

    if isinstance(ast, list):
        for item in ast:
            strings.append(generate_hoi4_code(item, indent_level, scope_stack))
        return "".join(strings)

    if isinstance(ast, tuple):
        node_type = ast[0]

        if node_type == "COMMENT":
            comment_text = ast[1]
            if comment_text == "#___EMPTY_LINE___":
                return "\n"
            return f"{spacing}{comment_text}\n"

        if node_type == "RAW_INLINE":
            # Verbatim single-line block: `name = { body }`. body is emitted as
            # given (already normalized), only scope vars resolved to THIS/PREV.
            _, name, body = ast
            name = resolve_scopes(name, scope_stack)
            body = resolve_scopes(body, scope_stack)
            return f"{spacing}{name} = {{ {body} }}\n"

        if node_type == "RAW_BARE":
            # A single verbatim token on its own line (e.g. a focus id in an
            # ai_national_focuses list). No "= yes", just the token.
            val = resolve_scopes(ast[1], scope_stack)
            return f"{spacing}{val}\n"

        if node_type == "RAW_ASSIGN":
            # Verbatim trigger line `left op right`, no sugar (e.g. date < 1939.1.1).
            _, left, op, right = ast
            left  = resolve_scopes(left, scope_stack) if isinstance(left, str) else left
            right = resolve_scopes(right, scope_stack) if isinstance(right, str) else right
            return f"{spacing}{left} {op} {right}\n"

        if node_type == "ASSIGN":
            _, left, op, right = ast

            left = resolve_scopes(left, scope_stack)

            if isinstance(right, tuple) and right[0] == "BLOCK":
                block_items = right[1]
                scope_var = right[2] if len(right) > 2 else None

                if scope_var:
                    scope_stack.append(scope_var)

                if len(block_items) == 1 and isinstance(block_items[0], tuple) and block_items[0][0] == "ASSIGN":
                    inner_left  = block_items[0][1]
                    inner_op    = block_items[0][2]
                    inner_right = block_items[0][3]

                    if not isinstance(inner_right, (tuple, list)):
                        inner_left = resolve_scopes(inner_left, scope_stack)
                        if isinstance(inner_right, str) and not inner_right.startswith('"'):
                            inner_right = resolve_scopes(inner_right, scope_stack)

                        if scope_var:
                            scope_stack.pop()

                        return f"{spacing}{left} {op} {{ {inner_left} {inner_op} {inner_right} }}\n"

                block_content = generate_hoi4_code(block_items, indent_level + 1, scope_stack)

                if scope_var:
                    scope_stack.pop()

                return f"{spacing}{left} {op} {{\n{block_content}{spacing}}}\n"

            else:
                if isinstance(right, str) and not right.startswith('"'):
                    right = resolve_scopes(right, scope_stack)
                return f"{spacing}{left} {op} {right}\n"

    if isinstance(ast, (str, int, float)):
        return f"{spacing}{ast}\n"

    return ""

# A macro call is `$name(` where name starts lowercase (COUNTRY_TAG is `$` +
# uppercase, so `$GER(` never matches). Used to decide whether a changed .hml
