class AssignmentsMixin:
    def assignment(self, items):
        left, op, right = items
        return ("ASSIGN", left, str(op), right)

    # x = 10  ==>  set_[temp_]variable = { x = 10 }
    # Temp is the default; a leading '&' (e.g. &x) marks a persistent variable.
    # The '&' marker is stripped from the emitted name.
    def short_assign(self, items):
        var_name = self._check_var_name(str(items[0]))
        # A country tag reaches the RHS as ("COUNTRY_TAG", tag); emit the bare tag.
        var_value = self._unwrap_tag(items[2])
        cmd = "set_temp_variable" if self._var_is_temp(var_name) else "set_variable"
        name = self._strip_persist(var_name)
        return ("ASSIGN", cmd, "=", ("BLOCK", [("ASSIGN", name, "=", var_value)]))

    # a, b, c = 1, 2, 3  ->  three separate set_[temp_]variable statements, each
    # by its own '&' marker. The EQUAL_OP token splits targets from values.
    def tuple_assign(self, items):
        split = next(i for i, it in enumerate(items)
                     if hasattr(it, "type") and it.type == "EQUAL_OP")
        targets = items[:split]
        values  = items[split + 1:]
        if len(targets) != len(values):
            raise ValueError(
                f"Tuple assignment mismatch: {len(targets)} targets but "
                f"{len(values)} values.")
        out = []
        for tgt, val in zip(targets, values):
            val = self._unwrap_tag(val)
            name = self._check_var_name(str(tgt))
            cmd = "set_temp_variable" if self._var_is_temp(name) else "set_variable"
            out.append(("ASSIGN", cmd, "=",
                        ("BLOCK", [("ASSIGN", self._strip_persist(name), "=", val)])))
        return out

    # x = null  ==>  clear_variable = x
    # HoI4 has no clear_temp_variable, so clearing a temp (the default) is an
    # error; only a persistent '&'-marked variable can be cleared.
    def clear_var(self, items):
        var_name = self._check_var_name(str(items[0]))
        if self._var_is_temp(var_name):
            raise ValueError(
                f"Cannot clear temp variable '{var_name}': "
                f"HoI4 has no 'clear_temp_variable' command, and variables are "
                f"temp by default. Temp variables drop automatically at the end "
                f"of their effect scope. (Mark it persistent with '&' if needed.)"
            )
        return ("ASSIGN", "clear_variable", "=", self._strip_persist(var_name))

    def math_assign(self, items):
        var_name = self._check_var_name(str(items[0]))
        op = str(items[1])
        value = self._unwrap_tag(items[2])
        is_temp = self._var_is_temp(var_name)
        name = self._strip_persist(var_name)

        if op == "+=":
            cmd = "add_to_temp_variable" if is_temp else "add_to_variable"
        elif op == "-=":
            cmd = "subtract_from_temp_variable" if is_temp else "subtract_from_variable"
        elif op == "*=":
            cmd = "multiply_temp_variable" if is_temp else "multiply_variable"
        elif op == "/=":
            cmd = "divide_temp_variable" if is_temp else "divide_variable"
        else:
            cmd = "unknown_variable_command"

        return ("ASSIGN", cmd, "=", ("BLOCK", [("ASSIGN", name, "=", value)]))

    def inc_dec(self, items):
        var_name = self._check_var_name(str(items[0]))
        op = str(items[1])
        is_temp = self._var_is_temp(var_name)
        name = self._strip_persist(var_name)

        if op == "++":
            cmd = "add_to_temp_variable" if is_temp else "add_to_variable"
        elif op == "--":
            cmd = "subtract_from_temp_variable" if is_temp else "subtract_from_variable"
        else:
            cmd = "unknown_inc_dec"

        return ("ASSIGN", cmd, "=", ("BLOCK", [("ASSIGN", name, "=", 1)]))
