import re
from lark import Transformer

class HslTransformer(Transformer):
    # Explicitly define external_macros as a keyword argument with a default value of None
    def __init__(self, external_macros=None):
        # Initialize the base Lark Transformer class WITHOUT passing our custom argument
        super().__init__()
        # Store the macros dictionary in the transformer instance
        # If external_macros was passed, we use it; otherwise, we start with an empty dict
        self.macros = external_macros if external_macros is not None else {}

    def unquoted_value(self, items):
        val = str(items[0])

        # If this is a number (contains digits and possibly underscores, dots, or a minus sign),
        # create a clean copy of the string without '_' characters for conversion attempt.
        clean_val = val.replace('_', '')

        # Check if the cleaned string is an integer.
        # Use lstrip('-') to correctly handle negative numbers like -1_000
        if clean_val.lstrip('-').isdigit():
            return int(clean_val)

        try:
            return float(clean_val)
        except ValueError:
            # If it turned out to be a plain string/variable (e.g. current_year) — return the original
            return val

    # Ensure strings retain their quotation marks in the final code
    def string(self, items):
        val = str(items[0])

        # If for some reason the quotes were stripped, we force them back on
        if not val.startswith('"'):
            val = f'"{val}"'

        return val

    def operator(self, items):
        return str(items[0])

    def assignment(self, items):
        left, op, right = items
        return ("ASSIGN", left, str(op), right)

    # Array methods (clear, add, remove)
    def array_method(self, items):
        arr_name = str(items[0])
        method = str(items[1]) # Method name (e.g., clear, add, remove)

        # If there's an argument in parentheses, it will be in items[2]
        val = items[2] if len(items) > 2 else None

        if method == "clear":
            return ("ASSIGN", "clear_array", "=", arr_name)
        elif method == "add":
            return ("ASSIGN", "add_to_array", "=", ("BLOCK", [("ASSIGN", arr_name, "=", val)]))
        elif method == "remove":
            return ("ASSIGN", "remove_from_array", "=", ("BLOCK", [("ASSIGN", arr_name, "=", val)]))
        else:
            raise ValueError(f"Compilation Error: Unknown array method '.{method}()'")

    # Writing a value by index: arr_name[i] << val
    def array_assign(self, items):
        arr_name = str(items[0])
        index = items[1]
        val = items[3] # items[2] is the "<<" token, so the value is in items[3]

        target = f"{arr_name}^{index}"
        return ("ASSIGN", "set_variable", "=", ("BLOCK", [("ASSIGN", target, "=", val)]))

    # Reading array size: arr_name[].size()
    def array_size(self, items):
        arr_name = str(items[0])
        return f"{arr_name}^num"

    # Reading a value by index: arr_name[i]
    def array_access(self, items):
        arr_name = str(items[0])
        index = items[1]
        return f"{arr_name}^{index}"

    # Transform: x <- 10  ==>  set_variable = { x = 10 }
    def short_assign(self, items):
        var_name = str(items[0])
        var_value = items[2]

        # If the name starts with an underscore, it is a temporary variable
        if var_name.startswith("_"):
            return ("ASSIGN", "set_temp_variable", "=", ("BLOCK", [("ASSIGN", var_name, "=", var_value)]))

        # For regular variables, keep the old logic
        return ("ASSIGN", "set_variable", "=", ("BLOCK", [("ASSIGN", var_name, "=", var_value)]))

    def math_assign(self, items):
        var_name = str(items[0])
        op = str(items[1])
        value = items[2]

        # Check if it is a temporary variable
        is_temp = var_name.startswith("_")

        # Select the correct command based on the operator
        if op == "+=":
            hoi_command = "add_to_temp_variable" if is_temp else "add_to_variable"
        elif op == "-=":
            hoi_command = "subtract_from_temp_variable" if is_temp else "subtract_from_variable"
        elif op == "*=":
            hoi_command = "multiply_temp_variable" if is_temp else "multiply_variable"
        elif op == "/=":
            hoi_command = "divide_temp_variable" if is_temp else "divide_variable"
        else:
            hoi_command = "unknown_variable_command"

        return ("ASSIGN", hoi_command, "=", ("BLOCK", [("ASSIGN", var_name, "=", value)]))

    # VARIABLE CHECK TRANSFORMATION
    def var_check(self, items):
        left, op, right = items
        op_str = str(op)

        # Convert our "==" into the game-friendly "=" inside check_variable
        if op_str == "==":
            op_str = "="

        return ("ASSIGN", "check_variable", "=", ("BLOCK", [("ASSIGN", left, op_str, right)]))

    # Check if a value exists in an array: val in arr_name[]
    def array_check(self, items):
        val = items[0]
        arr_name = str(items[1]) # The array name (Lark drops the brackets automatically)

        # Generates: is_in_array = { arr_name = val }
        return ("ASSIGN", "is_in_array", "=", ("BLOCK", [("ASSIGN", arr_name, "=", val)]))

    # Check if a value DOES NOT exist in an array: val not in arr_name[]
    def array_not_check(self, items):
        val = items[0]
        # items[1] is the NOT_OP token ("not") passed by Lark. We just ignore it.
        arr_name = str(items[2])

        # Create the standard 'is_in_array' block
        in_array_block = ("ASSIGN", "is_in_array", "=", ("BLOCK", [("ASSIGN", arr_name, "=", val)]))

        # Wrap it inside a 'NOT = { ... }' block for the Clausewitz engine
        return ("ASSIGN", "NOT", "=", ("BLOCK", [in_array_block]))

    def inc_dec(self, items):
        var_name = str(items[0])
        op = str(items[1])

        # Check if it is a temporary variable
        is_temp = var_name.startswith("_")

        # Choose the command depending on ++ or --
        if op == "++":
            hoi_command = "add_to_temp_variable" if is_temp else "add_to_variable"
        elif op == "--":
            hoi_command = "subtract_from_temp_variable" if is_temp else "subtract_from_variable"
        else:
            hoi_command = "unknown_inc_dec"

        # Expand into standard HoI4 structure for changing value by 1
        return ("ASSIGN", hoi_command, "=", ("BLOCK", [("ASSIGN", var_name, "=", 1)]))

    # PROCESSING OR (||) CHAIN AND CONDITION ROOT
    def condition(self, items):
        # Remove "||" operator tokens from the list
        pure_items = [x for x in items if x != "or"]

        # If there is only one || block, just pass its structure further
        if len(pure_items) == 1:
            return pure_items[0]

        # If there are multiple blocks, wrap them into the game's OR = { ... }
        return ("ASSIGN", "OR", "=", ("BLOCK", pure_items))

    # PROCESSING AND (&&) CHAIN
    def conj_element(self, items):
        pure_items = [x for x in items if x != "and"]

        # If the condition is singular
        if len(pure_items) == 1:
            return pure_items[0]

        # If there are multiple conditions, wrap them into the game's AND = { ... }
        return ("ASSIGN", "AND", "=", ("BLOCK", pure_items))

    # Method for intercepting the ! sign at the base level
    def logical_not(self, items):
        # items[1] is the condition itself that comes after the ! sign
        condition_ast = items[1]

        # If there is a single word inside the ! sign (e.g., "is_major")
        if isinstance(condition_ast, str):
            # Explicitly turn it into the "is_major = yes" structure
            condition_ast = ("ASSIGN", condition_ast, "=", "yes")

        # Wrap the result into the game's NOT = { ... } block
        return ("ASSIGN", "NOT", "=", ("BLOCK", [condition_ast]))

    def if_statement(self, items):
        condition = items[0]
        block_ast = items[-1] # Block is always the last element

        # Automatically build the vanilla limit = { ... } block for HoI4
        limit_block = ("ASSIGN", "limit", "=", ("BLOCK", [condition]))

        # Extract commands from the original block
        original_commands = block_ast[1]
        scope_var = block_ast[2] if len(block_ast) > 2 else None

        # Concatenate: limit block first, then the actual commands
        new_block_items = [limit_block] + original_commands

        return ("ASSIGN", "if", "=", ("BLOCK", new_block_items, scope_var))

    def elif_statement(self, items):
        condition = items[0]
        block_ast = items[-1]

        limit_block = ("ASSIGN", "limit", "=", ("BLOCK", [condition]))
        original_commands = block_ast[1]
        scope_var = block_ast[2] if len(block_ast) > 2 else None

        new_block_items = [limit_block] + original_commands

        # HoI4 uses "else_if" as the keyword
        return ("ASSIGN", "else_if", "=", ("BLOCK", new_block_items, scope_var))

    def else_statement(self, items):
        block_ast = items[-1]
        # The else block does not need a limit — return the block as-is
        return ("ASSIGN", "else", "=", block_ast)

    # Preserve comments in our AST
    def comment(self, items):
        # items[0] contains the actual text of the comment, e.g., "# My comment"
        comment_text = str(items[0])
        return ("COMMENT", comment_text)

    # Context declaration interceptor: c ->
    def scope_def(self, items):
        # Return a special tuple containing the variable name
        return ("SCOPE_DEF", str(items[1]))

    def block(self, items):
        processed_items = []
        scope_var = None

        for item in items:
            # If a context declaration is encountered, store it for future reference
            if isinstance(item, tuple) and item[0] == "SCOPE_DEF":
                scope_var = item[1]
            elif isinstance(item, str):
                processed_items.append(("ASSIGN", item, "=", "yes"))
            else:
                processed_items.append(item)
        return ("BLOCK", processed_items, scope_var)

    # Recursive AST Replacer
    def _replace_args_in_ast(self, node, param_map):
        if isinstance(node, str):
            new_str = node
            # Loop through all parameters and replace them with passed arguments
            for param, arg in param_map.items():
                # \b matches word boundaries, so 'var' won't replace 'my_var'
                pattern = r'\b' + re.escape(str(param)) + r'\b'
                new_str = re.sub(pattern, str(arg), new_str)
            return new_str

        elif isinstance(node, list):
            # Recursively process lists
            return [self._replace_args_in_ast(child, param_map) for child in node]

        elif isinstance(node, tuple):
            # Recursively process tuples
            return tuple(self._replace_args_in_ast(child, param_map) for child in node)

        else:
            return node

    # Helper to unpack parameters
    def macro_params(self, items):
        return [str(item) for item in items]

    # Helper to unpack arguments
    def macro_args(self, items):
        return items

    # Macro Definition
    def macro_def(self, items):
        macro_name = str(items[0])

        # Check if parameters were provided
        if len(items) == 3:
            params = items[1]
            block_ast = items[2]
        else:
            params = []
            block_ast = items[1]

        # Store both parameters and the body block
        self.macros[macro_name] = {
            "params": params,
            "body": block_ast[1]
        }
        return None

    def func_call(self, items):
        func_name = str(items[0])

        if len(items) > 1 and items[1] is not None:
            # Convert argument to string for easier manipulation
            arg = str(items[1])

            # REPLACEMENT MAGIC
            # Map standard true/false values to Clausewitz yes/no primitives
            if arg == "true":
                arg = "yes"
            elif arg == "false":
                arg = "no"

            return ("ASSIGN", func_name, "=", arg)
        else:
            # If parentheses are empty, default to standard HoI4 trigger behavior ("= yes")
            return ("ASSIGN", func_name, "=", "yes")

    # Macro Call
    def macro_call(self, items):
        # Extract the name and strip the leading '@' prefix character
        macro_name = str(items[0])[1:]

        # Check if arguments were provided
        if len(items) == 2:
            args = items[1]
        else:
            args = []

        macro_data = self.macros.get(macro_name)
        if not macro_data:
            raise ValueError(f"Error: Macro '{macro_name}' is not found in the library!")

        params = macro_data["params"]
        body = macro_data["body"]

        # Validation
        if len(args) != len(params):
            raise ValueError(f"Error: Macro '{macro_name}' expects {len(params)} arguments, but got {len(args)}!")

        # Create a mapping dictionary: {'country': 'SWE', 'amount': '50'}
        param_map = dict(zip(params, args))

        # Return a deep-copied AST with all variables replaced!
        return self._replace_args_in_ast(body, param_map)

    # Process chain calls: scope().filter(condition) = { block }
    def linq_statement(self, items):
        scope_name = str(items[0])
        condition = items[1]

        scope_var = None
        block_ast = None

        # Logic: if items[2] is a ("SCOPE_DEF", name) tuple,
        # it means the scope arrow (->) was used
        if isinstance(items[2], tuple) and items[2][0] == "SCOPE_DEF":
            scope_var = items[2][1]
            block_ast = items[3]
        else:
            block_ast = items[2]

        # Generate a classic Clausewitz 'limit = { ... }' block
        # Wrap condition into a list since BLOCK nodes expect an iterable
        limit_block = ("ASSIGN", "limit", "=", ("BLOCK", [condition]))

        # Extract commands from the original HSL block
        original_commands = block_ast[1]

        # Extract the context variable name if it was passed via 'c >>'
        # scope_var = block_ast[2] if len(block_ast) > 2 else None

        # Concatenate elements: prepend the limit_block before execution effects
        new_block_items = [limit_block] + original_commands

        # Return as a standard block assignment tuple, passing scope_var along
        return ("ASSIGN", scope_name, "=", ("BLOCK", new_block_items, scope_var))

    # Handle generic named blocks like effect:, trigger:, option:
    def generic_block(self, items):
        block_name = str(items[0])
        block_ast = items[-1]

        return ("ASSIGN", block_name, "=", block_ast)

    def start(self, items):
        # Filter out None values (which are left by macro definitions)
        return [item for item in items if item is not None]
