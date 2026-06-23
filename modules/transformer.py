from lark import Transformer

class HslTransformer(Transformer):
    def unquoted_value(self, items):
        val = str(items[0])
        if val.isdigit(): return int(val)
        try: return float(val)
        except ValueError: return val

    def escaped_string(self, items):
        return str(items[0]).strip('"')

    def operator(self, items):
        return str(items[0])

    def assignment(self, items):
        left, op, right = items
        return ("ASSIGN", left, str(op), right)

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
        pure_items = [x for x in items if x != "||"]

        # If there is only one || block, just pass its structure further
        if len(pure_items) == 1:
            return pure_items[0]

        # If there are multiple blocks, wrap them into the game's OR = { ... }
        return ("ASSIGN", "OR", "=", ("BLOCK", pure_items))

    # PROCESSING AND (&&) CHAIN
    def conj_element(self, items):
        pure_items = [x for x in items if x != "&&"]

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

    # PROCESSING OLD GAME IF: if = { ... }
    def vanilla_if(self, items):
        # items[0] contains EQUAL (=) token, items[1] contains BLOCK block
        block_ast = items[1]
        # We just return it in the standard AST format for the game
        return ("ASSIGN", "if", "=", block_ast)

    def block(self, items):
        processed_items = []
        for item in items:
            if isinstance(item, str):
                processed_items.append(("ASSIGN", item, "=", "yes"))
            else:
                processed_items.append(item)
        return ("BLOCK", processed_items)

    def start(self, items):
        return items
