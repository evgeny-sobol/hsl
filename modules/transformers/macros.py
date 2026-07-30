import re

class MacrosMixin:
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

        # `params` is a list of (name, default) tuples; default is None when the
        # parameter is required. Enforce Python-style ordering: once a parameter
        # has a default, every parameter after it must have one too — otherwise
        # filling missing trailing args from defaults would be ambiguous.
        seen_default = False
        for name, default in params:
            if default is None:
                if seen_default:
                    raise ValueError(
                        f"Error: Macro '{macro_name}': required parameter '{name}' "
                        f"cannot follow a parameter with a default value."
                    )
            else:
                seen_default = True

        # Store both parameters and the body block.
        # A body that is exactly one bare value expression (("EXPR", v)) marks a
        # *value macro*: calling it in a value position substitutes that
        # expression. Anything else is an ordinary *operator macro* whose body is
        # a list of statements spliced in at the call site.
        body_items = block_ast[1]
        if len(body_items) == 1 and isinstance(body_items[0], tuple) and body_items[0][0] == "EXPR":
            self.macros[macro_name] = {
                "params": params,
                "body": body_items[0][1],   # the value expression itself
                "is_value": True,
            }
        else:
            self.macros[macro_name] = {
                "params": params,
                "body": body_items,
                "is_value": False,
            }
        return None

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

        params = macro_data["params"]      # list of (name, default) tuples
        body = macro_data["body"]

        param_names = [p[0] for p in params]
        defaults    = [p[1] for p in params]
        required    = sum(1 for d in defaults if d is None)  # defaults are trailing

        # Validation: allow anywhere from `required` up to len(params) arguments.
        if not (required <= len(args) <= len(params)):
            if required == len(params):
                expected = f"{len(params)}"
            else:
                expected = f"{required} to {len(params)}"
            raise ValueError(
                f"Error: Macro '{macro_name}' expects {expected} arguments, "
                f"but got {len(args)}!"
            )

        # Fill the missing trailing arguments from their defaults.
        effective_args = list(args) + defaults[len(args):]

        # Create a mapping dictionary: {'country': 'SWE', 'amount': '50'}
        param_map = dict(zip(param_names, effective_args))

        # Parameters the CALLER actually supplied (defaults don't count) — this
        # is what `if defined(_p_):` tests at compile time.
        provided = set(param_names[:len(args)])

        # Resolve compile-time `if defined(...)` blocks first, then substitute.
        body = self._resolve_defined(body, provided)
        return self._replace_args_in_ast(body, param_map)

    # Compile-time `if defined(_p_):` — the block is kept (spliced inline,
    # without the `if`) when every parameter it names was supplied at the call
    # site, and dropped entirely otherwise. Nothing survives into the output.
    def _resolve_defined(self, node, provided):
        if isinstance(node, list):
            out = []
            for child in node:
                r = self._resolve_defined(child, provided)
                if r is None:
                    continue
                out.extend(r) if isinstance(r, list) else out.append(r)
            return out

        if not (isinstance(node, tuple) and len(node) == 4
                and node[0] == "ASSIGN" and node[1] == "if"
                and isinstance(node[3], tuple) and node[3][0] == "BLOCK"):
            # Not an `if` — but a nested block may contain one, so recurse into
            # any BLOCK payload (e.g. `add_dynamic_modifier:` wrapping the ifs).
            if (isinstance(node, tuple) and len(node) == 4
                    and isinstance(node[3], tuple) and node[3][0] == "BLOCK"):
                inner = self._resolve_defined(list(node[3][1]), provided)
                return (node[0], node[1], node[2],
                        ("BLOCK", inner) + tuple(node[3][2:]))
            return node

        items = list(node[3][1])
        names = self._defined_names(items)
        if names is None:
            # A normal runtime `if` — just recurse into its body.
            new_items = self._resolve_defined(items, provided)
            return ("ASSIGN", "if", "=", ("BLOCK", new_items) + tuple(node[3][2:]))

        # Drop the limit clause; keep the rest only if every name was provided.
        body_items = [it for it in items
                      if not (isinstance(it, tuple) and len(it) == 4
                              and it[1] == "limit")]
        if not all(n in provided for n in names):
            return None
        return self._resolve_defined(body_items, provided)

    @staticmethod
    def _defined_names(items):
        """Return the parameter names tested by a `defined(...)` limit block,
        or None when this `if` isn't a compile-time defined() test."""
        for it in items:
            if (isinstance(it, tuple) and len(it) == 4 and it[1] == "limit"
                    and isinstance(it[3], tuple) and it[3][0] == "BLOCK"):
                names = []
                for cond in it[3][1]:
                    if (isinstance(cond, tuple) and len(cond) == 4
                            and cond[1] == "defined"):
                        names.append(str(cond[3]))
                    else:
                        return None          # mixed with real conditions
                return names or None
        return None

    # One parameter: name with an optional default value.
    # Returns (name, default) where default is None when absent.
    def macro_param(self, items):
        name = str(items[0])
        # items is [NAME] or [NAME, EQUAL_OP, <default>] — the EQUAL_OP token is
        # kept here, so the default is the LAST element, not items[1].
        default = items[-1] if len(items) > 1 else None
        return (name, default)

    # Helper to unpack parameters — a list of (name, default) tuples.
    def macro_params(self, items):
        return list(items)

    # Helper to unpack arguments
    def macro_args(self, items):
        return items

    # Recursive AST Replacer
    def _replace_args_in_ast(self, node, param_map):
        # Unwrap COUNTRY_TAG sentinels in param_map before substitution
        unwrapped_map = {
            k: (v[1] if isinstance(v, tuple) and v[0] == "COUNTRY_TAG" else v)
            for k, v in param_map.items()
        }

        if isinstance(node, str):
            new_str = node
            # Loop through all parameters and replace them with passed arguments
            for param, arg in unwrapped_map.items():
                # `{param}` interpolates *inside* an identifier and the braces are
                # consumed: LocKey_x_{_c_}_tt -> LocKey_x_ROOT_tt. Needed because
                # the \b form below can't match between underscores.
                new_str = new_str.replace("{" + str(param) + "}", str(arg))
                # \b matches word boundaries, so 'var' won't replace 'my_var'
                pattern = r'\b' + re.escape(str(param)) + r'\b'
                new_str = re.sub(pattern, str(arg), new_str)
            return new_str

        elif isinstance(node, list):
            # Recursively process lists
            return [self._replace_args_in_ast(child, param_map) for child in node]

        elif isinstance(node, tuple):
            # For an ASSIGN, the op slot (index 2) may receive an operator passed
            # as a quoted string (e.g. ">"); strip the surrounding quotes so it
            # lands in the operator position literally. Normal ops ("=", ">") are
            # never quoted, so this is a no-op for them.
            if node[0] == "ASSIGN" and len(node) == 4:
                left  = self._replace_args_in_ast(node[1], param_map)
                op    = self._replace_args_in_ast(node[2], param_map)
                right = self._replace_args_in_ast(node[3], param_map)
                if isinstance(op, str) and len(op) >= 2 and op[0] == '"' and op[-1] == '"':
                    op = op[1:-1]
                return ("ASSIGN", left, op, right)
            # A raw statement trigger (`raw field op val`) is emitted verbatim,
            # and HoI4 wants bare tokens (date < 1939.1.1, not "date" < "1939.1.1").
            # Args must be quoted at the call site so tokens like 1939.1.1 survive
            # parsing; strip the surrounding quotes off every slot here.
            if node[0] == "RAW_ASSIGN" and len(node) == 4:
                parts = [self._replace_args_in_ast(node[i], param_map) for i in (1, 2, 3)]
                parts = [p[1:-1] if isinstance(p, str) and len(p) >= 2
                         and p[0] == '"' and p[-1] == '"' else p
                         for p in parts]
                return ("RAW_ASSIGN", parts[0], parts[1], parts[2])
            # Recursively process other tuples
            return tuple(self._replace_args_in_ast(child, param_map) for child in node)

        else:
            return node
