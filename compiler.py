import os
import re
import sys
from lark import Lark
from lark.indenter import Indenter
from modules.transformer import HslTransformer

class HslIndenter(Indenter):
    NL_type = '_NL'
    OPEN_PAREN_types = ['_LPAR', '_LSQB']
    CLOSE_PAREN_types = ['_RPAR', '_RSQB']
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 2

def preserve_empty_lines(source_code):
    """
    Finds all empty lines and inserts a hidden comment into each one,
    copying the indentation level from the next non-empty line.
    This prevents HslIndenter from breaking the block structure.
    """
    lines = source_code.splitlines()
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

def resolve_scopes(text, scope_stack):
    if not isinstance(text, str) or not scope_stack:
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

def compile_folder(target_folder):
    """
    Recursively finds all .hsl files in the specified directory and all
    its subdirectories, then compiles them into the game's .txt files.
    """
    grammar_path = "modules/grammar.lark"
    if not os.path.exists(grammar_path):
        print(f"Error: Grammar file '{grammar_path}' not found in the project root!")
        return
    # Initialize Lark
    print(f"Loading grammar from {grammar_path}...")
    parser = Lark.open(grammar_path, start='start', parser='lalr', postlex=HslIndenter())
    transformer = HslTransformer()

    global_macros = {} # This dictionary will store all processed macros
    hml_path = os.path.join(target_folder, "macros.hml")

    if os.path.exists(hml_path):
        print(f"📖 Found macro library: {hml_path}. Loading...")
        try:
            with open(hml_path, "r", encoding="utf-8-sig") as f:
                hml_code = f.read()

            hml_code = preserve_empty_lines(hml_code)
            # Parse the HML code into an AST tree using our grammar
            hml_tree = parser.parse(hml_code)

            # Pass our global_macros dict to the transformer to fill it
            hml_transformer = HslTransformer(external_macros=global_macros)
            hml_transformer.transform(hml_tree)

            print(f"✅ Successfully loaded macros: {len(global_macros)}")
        except Exception as e:
            print(f"❌ Error while reading macro library: {e}")
            return

    transformer.macros = global_macros

    if not os.path.exists(target_folder):
        print(f"Error: The specified directory '{target_folder}' does not exist!")
        return

    print(f"Scanning directory '{target_folder}' and all subdirectories...")
    print("-" * 50)

    compiled_count = 0

    # Use os.walk to recursively traverse all subdirectories
    # root - current directory, dirs - list of subdirectories, files - files within it
    for root, dirs, files in os.walk(target_folder):
        # Filter only files ending with .hsl
        hsl_files = [f for f in files if f.endswith('.hsl')]

        if not hsl_files:
            continue

        for filename in hsl_files:
            # Build the absolute path to the source .hsl file
            hsl_path = os.path.join(root, filename)

            # Generate the name and path for the output .txt file in the same subdirectory
            txt_filename = filename.rsplit('.', 1)[0] + ".txt"
            txt_path = os.path.join(root, txt_filename)

            # Print the relative path to prettify the console output
            relative_path = os.path.relpath(hsl_path, target_folder)
            print(f"Compiling: {relative_path}...")

            try:
                with open(hsl_path, "r", encoding="utf-8-sig") as f:
                    source_code = f.read() + "\n"

                # Fill empty lines with indent-aware markers
                source_code = preserve_empty_lines(source_code)

                # Parsing, transformation, and code generation
                tree = parser.parse(source_code)
                ast_data = transformer.transform(tree)
                final_code = generate_hoi4_code(ast_data)

                # Strip markers from the final generated code.
                # The regex finds all lines containing only whitespace and our marker,
                # and replaces them with a real empty line.
                final_code = re.sub(r'^[ \t]*#___EMPTY_LINE___$', '', final_code, flags=re.MULTILINE)

                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(final_code)

                compiled_count += 1

            except Exception as e:
                print(f"Error in file {filename}: {e}")

    print("-" * 50)
    print(f"Recursive compilation completed! Total files processed: {compiled_count}")

if __name__ == "__main__":
    # By default, look for files in the current directory where the script is running
    target_dir = "."

    # If a directory path was passed as a command-line argument (e.g., python compiler.py ./my_mod_src)
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]

    compile_folder(target_dir)
