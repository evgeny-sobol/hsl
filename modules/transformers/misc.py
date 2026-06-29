class MiscMixin:
    # Preserve comments in our AST
    def comment(self, items):
        # items[0] contains the actual text of the comment, e.g., "# My comment"
        comment_text = str(items[0])
        return ("COMMENT", comment_text)

    def operator(self, items):
        return str(items[0])
