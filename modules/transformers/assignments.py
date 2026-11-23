_MATH_ASSIGN_CMDS = {
    "+=": ("add_to_temp_variable",        "add_to_variable"),
    "-=": ("subtract_from_temp_variable", "subtract_from_variable"),
    "*=": ("multiply_temp_variable",      "multiply_variable"),
    "/=": ("divide_temp_variable",        "divide_variable"),
}
_INC_DEC_CMDS = {
    "++": _MATH_ASSIGN_CMDS["+="],
    "--": _MATH_ASSIGN_CMDS["-="],
}


def _leaf_names(v):
    """Every string leaf of a value (a scalar or an arithmetic tree)."""
    if isinstance(v, str):
        return {v}
    if isinstance(v, (tuple, list)):
        return set().union(*(_leaf_names(x) for x in v)) if v else set()
    return set()


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
    # The statements run in order, so a value may not read a target assigned
    # earlier in the same line (`a, b = b, a` would set both to b).
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
        assigned = set()
        for tgt, val in zip(targets, values):
            val = self._unwrap_tag(val)
            name = self._check_var_name(str(tgt))
            bare = self._strip_persist(name)
            reused = assigned & {self._strip_persist(n) for n in _leaf_names(val)}
            if reused:
                raise ValueError(
                    f"Tuple assignment reads '{sorted(reused)[0]}' after it was "
                    f"already reassigned in the same line; HSL assigns left to "
                    f"right, so a swap like 'a, b = b, a' does not work. Use a "
                    f"temp variable: 't = a', 'a = b', 'b = t'.")
            assigned.add(bare)
            cmd = "set_temp_variable" if self._var_is_temp(name) else "set_variable"
            out.append(("ASSIGN", cmd, "=",
                        ("BLOCK", [("ASSIGN", bare, "=", val)])))
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

    def _variable_cmd(self, var_name, cmds, value):
        temp_cmd, persistent_cmd = cmds
        cmd = temp_cmd if self._var_is_temp(var_name) else persistent_cmd
        name = self._strip_persist(var_name)
        return ("ASSIGN", cmd, "=", ("BLOCK", [("ASSIGN", name, "=", value)]))

    def math_assign(self, items):
        var_name = self._check_var_name(str(items[0]))
        return self._variable_cmd(var_name, _MATH_ASSIGN_CMDS[str(items[1])],
                                  self._unwrap_tag(items[2]))

    def inc_dec(self, items):
        var_name = self._check_var_name(str(items[0]))
        return self._variable_cmd(var_name, _INC_DEC_CMDS[str(items[1])], 1)
