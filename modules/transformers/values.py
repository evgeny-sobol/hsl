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
