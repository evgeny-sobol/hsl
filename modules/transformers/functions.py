class FunctionsMixin:
    def func_call(self, items):
        func_name = str(items[0])

        if len(items) > 1 and items[1] is not None:
            arg = items[1]

            # Reject an arithmetic expression as a direct call argument. The
            # engine does not accept an inline accumulator value-block where a
            # trigger/effect/MTTH key expects a scalar (e.g. factor(1 + x) breaks
            # focus-tree evaluation). Compute it into a variable first.
            # Confirmed in-game on v1.19.2.
            if self._is_expr(arg):
                raise ValueError(
                    f"Arithmetic expression cannot be passed directly to "
                    f"'{func_name}(...)': '{func_name}({self._expr_to_str(arg)})'. "
                    f"HoI4 rejects an inline value-block here. Assign it to a "
                    f"(temp) variable first, e.g.:\n"
                    f"    _tmp <- {self._expr_to_str(arg)}\n"
                    f"    {func_name}(_tmp)"
                )

            # Unwrap a COUNTRY_TAG sentinel to its bare tag.
            if isinstance(arg, tuple) and arg and arg[0] == "COUNTRY_TAG":
                arg = arg[1]
            # Map standard true/false to Clausewitz yes/no. Only strings are
            # touched вЂ” a non-string arg (an int, or an ("ARITH", ...) marker the
            # post-pass will lift) must pass through untouched, NOT be str()'d.
            elif isinstance(arg, str):
                if arg == "true":
                    arg = "yes"
                elif arg == "false":
                    arg = "no"

            return ("ASSIGN", func_name, "=", arg)
        else:
            # If parentheses are empty, default to standard HoI4 trigger behavior ("= yes")
            return ("ASSIGN", func_name, "=", "yes")

    # rand(var) / randf(var,min,max) / randi(var,min,max) -> engine random
    # effects. Also usable as `var = rand*(...)` (see rand_assign), which the
    # compiler rewrites to this same form with no extra temp.
    #
    # temp vs persistent is chosen from var's '_' prefix. The engine range is
    # [min, max); randi makes max INCLUSIVE via max+1 (compile-time for an int
    # literal, else a one-command accumulator temp). randf leaves max as-is.
    # The random block and any max-temp are emitted on one line (RAW_INLINE).
    #
    # rand_call yields a lightweight ("RANDCALL", fname, args) node so the same
    # data can be finalized either as a standalone statement or, via rand_assign,
    # with the assignment's LHS spliced in as the first argument.
    def rand_call(self, items):
        fname = str(items[0])
        args = [a for a in items[1:] if a is not None]
        return ("RANDCALL", fname, args)

    def _finalize_randcall(self, node):
        # node is ("RANDCALL", fname, args); statement context finalizes it.
        return self._build_rand(node[1], node[2])

    # Sugar: `var = rand*(args)` -> prepend var as the first argument.
    # items = [var, EQUAL_OP, ("RANDCALL", fname, args)].
    def rand_assign(self, items):
        var = items[0]
        _, fname, args = items[2]
        return self._build_rand(fname, [var] + args)

    def _build_rand(self, fname, args):
        var = self._unwrap_tag(args[0])
        if fname == "rand":
            if len(args) != 1:
                raise ValueError(f"rand() takes exactly 1 argument, got {len(args)}")
            cmd = "set_temp_variable_to_random" if self._is_temp_ref(var) else "set_variable_to_random"
            return ("ASSIGN", cmd, "=", var)

        if len(args) != 3:
            raise ValueError(f"{fname}() takes exactly 3 arguments (var, min, max), got {len(args)}")
        lo = self._unwrap_tag(args[1])
        hi = self._unwrap_tag(args[2])
        # No argument position accepts an inline arithmetic expression (the
        # engine wants scalars/vars here); reject early with a clear message.
        for role, a in (("var", var), ("min", lo), ("max", hi)):
            if self._is_expr(a):
                raise ValueError(
                    f"{fname}(): {role} cannot be an arithmetic expression; "
                    f"assign it to a variable first, then pass that variable.")
        cmd = "set_temp_variable_to_random" if self._is_temp_ref(var) else "set_variable_to_random"

        pre = []
        # randi makes max INCLUSIVE via max+1; randf leaves it as-is.
        if fname == "randf":
            hi_val = hi
        elif isinstance(hi, int) or (isinstance(hi, str) and self._rand_is_int_literal(hi)):
            hi_val = int(hi) + 1
        else:
            # max is a variable/array ref: compute max+1 in ONE command via an
            # accumulator value-block, rendered inline. Verified in-game
            # (v1.19.2) that set_temp_variable accepts an accumulator block in
            # all contexts, including inside for_loop_effect.
            tmp = f"_hsl_randmax{self._gensym}"
            self._gensym += 1
            acc_body = self._inline_accumulator(self._compile_expr(("MATH", "+", hi, 1)))
            # e.g.  _hsl_randmax0 = { value=_max add=1 }  -- one line, via RAW_INLINE.
            pre.append(("RAW_INLINE", "set_temp_variable", f"{tmp} = {{ {acc_body} }}"))
            hi_val = tmp

        # Compact `key=value` form (no spaces around '='), which these engine
        # effects conventionally use. Rendered on one line via RAW_INLINE.
        parts = [f"var={var}", f"min={lo}", f"max={hi_val}"]
        if fname == "randi":
            parts.append("integer=yes")
        call = ("RAW_INLINE", cmd, " ".join(parts))
        return pre + [call] if pre else call

    def _is_temp_ref(self, name):
        # temp if the segment after any scope prefix ('.') starts with '_'.
        return str(name).rsplit(".", 1)[-1].startswith("_")

    def _inline_accumulator(self, items):
        # Render a list of ("ASSIGN", key, "=", value) accumulator steps as a
        # single-line `key=value key=value` string. A value that is itself a
        # ("BLOCK", [...]) is rendered recursively as `{ ... }`, so nested
        # accumulator blocks collapse to one line too.
        parts = []
        for it in items:
            _, key, _, val = it
            if isinstance(val, tuple) and val and val[0] == "BLOCK":
                parts.append(f"{key} = {{ {self._inline_accumulator(val[1])} }}")
            else:
                parts.append(f"{key}={self._unwrap_tag(val)}")
        return " ".join(parts)

    @staticmethod
    def _rand_is_int_literal(tok):
        try:
            int(str(tok)); return True
        except (TypeError, ValueError):
            return False

    def scoped_func_call(self, items):
        scope = str(items[0])   # "variable"
        func  = str(items[1])   # "can_ROOT_get_wargoal_on_THIS"
        arg   = items[2] if len(items) > 2 else None

        if self._is_expr(arg):
            raise ValueError(
                f"Arithmetic expression cannot be passed directly to "
                f"'{scope}::{func}(...)'. HoI4 rejects an inline value-block "
                f"here. Assign it to a (temp) variable first, e.g.:\n"
                f"    _tmp <- {self._expr_to_str(arg)}\n"
                f"    {scope}::{func}(_tmp)"
            )

        # Preserve non-string args (int / ("ARITH", ...) marker); default the
        # empty case to "yes".
        inner_val = "yes" if arg is None else arg
        return ("ASSIGN", scope, "=", ("BLOCK", [("ASSIGN", func, "=", inner_val)]))

    # One-line prefixed scope + trigger:
    #   var:NAME[i]::func(arg)  ->  var:NAME^i = { func = arg }
    #   var:NAME::func(arg)     ->  var:NAME   = { func = arg }
    # items[0] is the PREFIXED_REF. An optional index `value` may follow (from
    # `[i]`), then the func-name token, then an optional call arg (None if empty).
    # The func name is the sole bare-identifier token; the index and arg are the
    # value nodes around it, so classify by position: index is any value BEFORE
    # the func token, arg is the value AFTER it.
    def prefixed_scoped_call(self, items):
        ref = str(items[0])
        rest = list(items[1:])

        # The func name is a Lark Token of type UNQUOTED_VALUE. Locate it; the
        # value before it (if any) is the index, the value after it is the arg.
        func_pos = None
        for i, it in enumerate(rest):
            if hasattr(it, "type") and it.type == "UNQUOTED_VALUE":
                func_pos = i
                break
        # Fallback: if type info is unavailable, the func is the last string-like
        # token that is not the trailing arg.
        if func_pos is None:
            func_pos = 0

        func = str(rest[func_pos])
        index = rest[func_pos - 1] if func_pos >= 1 else None
        arg   = rest[func_pos + 1] if func_pos + 1 < len(rest) else None

        if index is not None:
            idx = self._unwrap_tag(index)
            name = f"{ref}^{idx}"
        else:
            name = ref

        if self._is_expr(arg):
            raise ValueError(
                f"Arithmetic expression cannot be passed directly to "
                f"'{name}::{func}(...)'. HoI4 rejects an inline value-block "
                f"here. Assign it to a (temp) variable first, e.g.:\n"
                f"    _tmp <- {self._expr_to_str(arg)}\n"
                f"    {name}::{func}(_tmp)"
            )

        inner_val = "yes" if arg is None else arg
        return ("ASSIGN", name, "=", ("BLOCK", [("ASSIGN", func, "=", inner_val)]))
