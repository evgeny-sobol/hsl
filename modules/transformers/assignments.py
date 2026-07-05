class AssignmentsMixin:
    def assignment(self, items):
        left, op, right = items
        return ("ASSIGN", left, str(op), right)

    # Transform: x <- 10  ==>  set_variable = { x = 10 }
    def short_assign(self, items):
        var_name = str(items[0])
        var_value = items[2]

        # If the name starts with an underscore, it is a temporary variable
        if var_name.startswith("_"):
            return ("ASSIGN", "set_temp_variable", "=", ("BLOCK", [("ASSIGN", var_name, "=", var_value)]))

        # For regular variables, keep the old logic
        return ("ASSIGN", "set_variable", "=", ("BLOCK", [("ASSIGN", var_name, "=", var_value)]))

    # Transform: x <- null  ==>  clear_variable = x
    # HoI4 has no clear_temp_variable, so clearing a temp (leading '_') is an error.
    def clear_var(self, items):
        var_name = str(items[0])
        if var_name.startswith("_"):
            raise ValueError(
                f"Cannot clear temp variable '{var_name}': "
                f"HoI4 has no 'clear_temp_variable' command. "
                f"Temp variables are dropped automatically at the end of their effect scope."
            )
        return ("ASSIGN", "clear_variable", "=", var_name)

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
