import re
from lark import Transformer

class HslTransformer(Transformer):
    # Explicitly define external_macros as a keyword argument with a default value of None
    def __init__(self, external_macros=None):
        # 1. Initialize the base Lark Transformer class WITHOUT passing our custom argument
        super().__init__()
        # 2. Store the macros dictionary in the transformer instance
        # If external_macros was passed, we use it; otherwise, we start with an empty dict
        self.macros = external_macros if external_macros is not None else {}
    
    def unquoted_value(self, items):
        val = str(items[0])
        if val.isdigit(): return int(val)
        try: return float(val)
        except ValueError: return val

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

    # Reading array length: arr_name[].length()
    def array_length(self, items):
        arr_name = str(items[0])
        return f"{arr_name}^num"

    # Reading a value by index: arr_name[i]
    def array_access(self, items):
        arr_name = str(items[0])
        index = items[1]
        return f"{arr_name}^{index}"

    # Transform: x << 10  ==>  set_variable = { x = 10 }
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
        
        # 1. Check if it is a temporary variable
        is_temp = var_name.startswith("_")
        
        # 2. Select the correct command based on the operator
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
        
        # 1. Create the standard 'is_in_array' block
        in_array_block = ("ASSIGN", "is_in_array", "=", ("BLOCK", [("ASSIGN", arr_name, "=", val)]))
        
        # 2. Wrap it inside a 'NOT = { ... }' block for the Clausewitz engine
        return ("ASSIGN", "NOT", "=", ("BLOCK", [in_array_block]))
    
    def inc_dec(self, items):
        var_name = str(items[0])
        op = str(items[1])
        
        # 1. Check if it is a temporary variable
        is_temp = var_name.startswith("_")
        
        # 2. Choose the command depending on ++ or --
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

    # 1. Method for intercepting the ! sign at the base level
    def logical_not(self, items):
        # items[1] is the condition itself that comes after the ! sign
        condition_ast = items[1]
        
        # If there is a single word inside the ! sign (e.g., "is_major")
        if isinstance(condition_ast, str):
            # Explicitly turn it into the "is_major = yes" structure
            condition_ast = ("ASSIGN", condition_ast, "=", "yes")
            
        # Wrap the result into the game's NOT = { ... } block
        return ("ASSIGN", "NOT", "=", ("BLOCK", [condition_ast]))

    # 2. Updated modern_if that can fix single words across the entire logical structure
    def modern_if(self, items):
        condition_ast, block_ast = items
        effects = block_ast[1]
        
        # Recursive function for deep conversion of single strings in condition chains
        def fix_conditions(ast):
            # If it is a single string in nested AND/OR blocks (e.g., "has_same_ideology")
            if isinstance(ast, str):
                return ("ASSIGN", ast, "=", "yes")
            
            if isinstance(ast, tuple) and ast[0] == "ASSIGN":
                node_type = ast[1] # "AND", "OR", "NOT", "check_variable", etc.
                
                # If it is an AND or OR logical block
                if node_type in ["AND", "OR"]:
                    inner_items = ast[3][1]
                    fixed_items = [fix_conditions(item) for item in inner_items]
                    return ("ASSIGN", node_type, "=", ("BLOCK", fixed_items))
                
                # If it is a NOT block (which might have been created by logical_not method earlier)
                if node_type == "NOT":
                    inner_items = ast[3][1]
                    # NOT contains a list of conditions inside, process them too
                    fixed_items = [fix_conditions(item) for item in inner_items]
                    return ("ASSIGN", "NOT", "=", ("BLOCK", fixed_items))
            
            return ast

        # Fix all single words in our if condition tree
        fixed_condition = fix_conditions(condition_ast)
        
        limit_ast = ("ASSIGN", "limit", "=", ("BLOCK", [fixed_condition]))
        if_body = [limit_ast] + effects
        return ("ASSIGN", "if", "=", ("BLOCK", if_body))
    
    # Handle 'elif' identically to 'if', but output 'else_if' for the Clausewitz engine
    def elif_statement(self, items):
        condition_ast = items[0]
        block_ast = items[1] # This is a tuple: ("BLOCK", [list of items])
        
        # Extract the internal list of commands from the block
        block_items = block_ast[1]
        
        # Create the standard limit block required by HoI4
        limit_block = ("ASSIGN", "limit", "=", ("BLOCK", [condition_ast]))
        
        # Insert the limit block at the very beginning of the else_if block
        new_block_items = [limit_block] + block_items
        
        # Return as a standard HoI4 assignment: else_if = { ... }
        return ("ASSIGN", "else_if", "=", ("BLOCK", new_block_items))
    
    # PROCESSING OLD GAME IF: if = { ... }
    def vanilla_if(self, items):
        # items[0] contains EQUAL (=) token, items[1] contains BLOCK block
        block_ast = items[1]
        # We just return it in the standard AST format for the game
        return ("ASSIGN", "if", "=", block_ast)
    
    # Convert print("text") to log = "text"
    def print_statement(self, items):
        val = items[0] # The value inside the parentheses
        
        # Return as a standard HoI4 assignment: log = val
        return ("ASSIGN", "log", "=", val)
    
    # Preserve comments in our AST
    def comment(self, items):
        # items[0] contains the actual text of the comment, e.g., "# My comment"
        comment_text = str(items[0])
        return ("COMMENT", comment_text)
    
    def block(self, items):
        processed_items = []
        for item in items:
            if isinstance(item, str):
                processed_items.append(("ASSIGN", item, "=", "yes"))
            else:
                processed_items.append(item)
        return ("BLOCK", processed_items)
    
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

    # Macro Call
    def macro_call(self, items):
        macro_name = str(items[0])
        
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
    
    def start(self, items):
        # Filter out None values (which are left by macro definitions)
        return [item for item in items if item is not None]
