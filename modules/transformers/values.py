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
            # If it turned out to be a plain string/variable (e.g. current_year) — return the original
            return val

    # Ensure strings retain their quotation marks in the final code
    def string(self, items):
        val = str(items[0])

        # If for some reason the quotes were stripped, we force them back on
        if not val.startswith('"'):
            val = f'"{val}"'

        return val

    def country_tag(self, items):
        return ("COUNTRY_TAG", str(items[0])[1:]) # e.g. ("COUNTRY_TAG", "USA")

    # var:NAME / token:NAME arrives as one token (e.g. "var:ROOT.rival_ideology")
    # -> returned verbatim as a plain string so it flows through assignment RHS,
    # call args and check_variable/has_government like any other scalar.
    def prefixed_value(self, items):
        return str(items[0])

    # Inline arithmetic `left OP right` -> a marker the post-pass lifts into a
    # temp variable. No work happens here beyond recording op and operands.
    def arith_expr(self, items):
        left  = items[0]
        op    = str(items[1])
        right = items[2]
        return ("ARITH", op, left, right)


