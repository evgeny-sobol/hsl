import os
import sys
from lark import Lark
from modules.transformer import HslTransformer

def generate_hoi4_code(ast, indent_level=0):
    """
    Recursively converts the AST back into Hearts of Iron IV source code.
    """
    strings = []
    spacing = "\t" * indent_level

    if isinstance(ast, list):
        for item in ast:
            strings.append(generate_hoi4_code(item, indent_level))
        return "".join(strings)

    if isinstance(ast, tuple):
        node_type = ast[0]

        if node_type == "ASSIGN":
            _, left, op, right = ast

            if isinstance(right, tuple) and right[0] == "BLOCK":
                block_content = generate_hoi4_code(right[1], indent_level + 1)
                return f"{spacing}{left} {op} {{\n{block_content}{spacing}}}\n"
            else:
                if isinstance(right, str):
                    if " " in right or left in ["has_dlc", "title", "desc", "text"]:
                        return f"{spacing}{left} {op} \"{right}\"\n"
                return f"{spacing}{left} {op} {right}\n"

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

    # 1. Initialize Lark
    print(f"Loading grammar from {grammar_path}...")
    parser = Lark.open(grammar_path, start='start', parser='lalr')
    transformer = HslTransformer()

    if not os.path.exists(target_folder):
        print(f"Error: The specified directory '{target_folder}' does not exist!")
        return

    print(f"Scanning directory '{target_folder}' and all subdirectories...")
    print("-" * 50)

    compiled_count = 0

    # 2. Use os.walk to recursively traverse all subdirectories
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
                    source_code = f.read()

                # Parsing, transformation, and code generation
                tree = parser.parse(source_code)
                ast_data = transformer.transform(tree)
                final_code = generate_hoi4_code(ast_data)

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
