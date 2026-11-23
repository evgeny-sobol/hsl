class ValuesMixin:
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
            # If it turned out to be a plain string/variable (e.g. current_year) - return the original
            return val

    # ESCAPED_STRING keeps its quotation marks, which the output needs.
    def string(self, items):
        return str(items[0])

    def country_tag(self, items):
        return ("COUNTRY_TAG", str(items[0])[1:]) # e.g. ("COUNTRY_TAG", "USA")

    # var:NAME / token:NAME / mtth:NAME arrives as one token (e.g.
    # "var:ROOT.rival_ideology") -> returned verbatim as a plain string so it
    # flows through assignment RHS, call args and check_variable/has_government
    # like any other scalar.
    def prefixed_value(self, items):
        return str(items[0])

    # Arithmetic expression tree. A binary op node is ("MATH", op, left, right);
    # a math builtin is ("MATHFN", name, [args...]). Operands are either further
    # MATH/MATHFN nodes or plain scalars (simple_value results). The post-pass
    # (_compile_expr) turns a whole tree into one nested accumulator value-block.
    # Precedence and associativity are already encoded by the grammar cascade,
    # so nothing to reorder here.
    def arith_binop(self, items):
        left  = items[0]
        op    = str(items[1])
        right = items[2]
        return ("MATH", op, left, right)

    def math_func(self, items):
        name = str(items[0])
        args = list(items[1:])
        if name == "abs":
            if len(args) != 1:
                raise ValueError(
                    f"abs() takes exactly 1 argument, got {len(args)}: "
                    f"'abs({', '.join(self._expr_to_str(a) for a in args)})'")
        return ("MATHFN", name, args)
