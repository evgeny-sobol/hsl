class ConditionsMixin:
    # Spread a top-level conjunction into bare sibling triggers.
    # In Clausewitz scripting, triggers listed side by side inside a block
    # (limit, root effect, etc.) are already implicitly AND-ed, so the
    # outermost AND = { ... } wrapper is redundant. A nested AND inside an OR
    # must stay, otherwise its children would become OR siblings — so we only
    # ever unwrap ONE outermost level, and only at the point a condition is
    # placed into such a block (the limit builders below).
    def unwrap_top_and(self, condition):
        if (isinstance(condition, tuple)
                and condition[0] == "ASSIGN"
                and condition[1] == "AND"
                and isinstance(condition[3], tuple)
                and condition[3][0] == "BLOCK"):
            return list(condition[3][1])
        return [condition]

    # PROCESSING OR (||) CHAIN AND CONDITION ROOT
    def condition(self, items):
        # Remove "||" operator tokens from the list; fold any macro expansion
        # (a list of statements) used as an OR branch into a single node.
        pure_items = [self._fold_macro(x) for x in items if x != "or"]

        # If there is only one || block, just pass its structure further
        if len(pure_items) == 1:
            return pure_items[0]

        # If there are multiple blocks, wrap them into the game's OR = { ... }
        return ("ASSIGN", "OR", "=", ("BLOCK", pure_items))

    # PROCESSING AND (&&) CHAIN
    def conj_element(self, items):
        pure_items = []
        for x in items:
            if x == "and":
                continue
            # A macro call expands to a list of statements; inside an AND chain
            # its statements are spliced in as plain sibling triggers.
            if isinstance(x, list):
                pure_items.extend(x)
            else:
                pure_items.append(x)

        # If the condition is singular
        if len(pure_items) == 1:
            return pure_items[0]

        # If there are multiple conditions, wrap them into the game's AND = { ... }
        return ("ASSIGN", "AND", "=", ("BLOCK", pure_items))

    # A macro call expands to a LIST of statements. Used as one condition atom
    # it means "all of them hold" → fold into an implicit AND (or the bare
    # statement when the macro body is a single line). Non-macro nodes pass through.
    def _fold_macro(self, node):
        if isinstance(node, list):
            if len(node) == 1:
                return node[0]
            return ("ASSIGN", "AND", "=", ("BLOCK", list(node)))
        return node

    # Method for intercepting the ! sign at the base level
    def logical_not(self, items):
        # items[1] is the condition itself that comes after the ! sign.
        # Fold a macro expansion first, so 'not @macro()' becomes NOT of the
        # whole conjunction rather than a NOR over its statements.
        condition_ast = self._fold_macro(items[1])

        # If there is a single word inside the ! sign (e.g., "is_major")
        if isinstance(condition_ast, str):
            # Explicitly turn it into the "is_major = yes" structure
            condition_ast = ("ASSIGN", condition_ast, "=", "yes")

        # Wrap the result into the game's NOT = { ... } block
        return ("ASSIGN", "NOT", "=", ("BLOCK", [condition_ast]))

    # VARIABLE CHECK TRANSFORMATION
    def var_check(self, items):
        left, op, right = items
        op_str = str(op)

        # Country tag on the right side → plain Clausewitz trigger, no check_variable
        if isinstance(right, tuple) and right[0] == "COUNTRY_TAG":
            return ("ASSIGN", left, "=", right[1])

        if op_str == "==":
            op_str = "="

        return ("ASSIGN", "check_variable", "=", ("BLOCK", [("ASSIGN", left, op_str, right)]))

    # Check if a value exists in an array: val in arr_name[]
    def array_check(self, items):
        val = items[0]
        arr_name = str(items[1]) # The array name (Lark drops the brackets automatically)

        # Unwrap COUNTRY_TAG sentinel
        if isinstance(val, tuple) and val[0] == "COUNTRY_TAG":
            val = val[1]

        # Generates: is_in_array = { arr_name = val }
        return ("ASSIGN", "is_in_array", "=", ("BLOCK", [("ASSIGN", arr_name, "=", val)]))

    # Check if a value DOES NOT exist in an array: val not in arr_name[]
    def array_not_check(self, items):
        val = items[0]
        # items[1] is the NOT_OP token ("not") passed by Lark. We just ignore it.
        arr_name = str(items[2])

        # Unwrap COUNTRY_TAG sentinel
        if isinstance(val, tuple) and val[0] == "COUNTRY_TAG":
            val = val[1]

        # Create the standard 'is_in_array' block
        in_array_block = ("ASSIGN", "is_in_array", "=", ("BLOCK", [("ASSIGN", arr_name, "=", val)]))

        # Wrap it inside a 'NOT = { ... }' block for the Clausewitz engine
        return ("ASSIGN", "NOT", "=", ("BLOCK", [in_array_block]))
