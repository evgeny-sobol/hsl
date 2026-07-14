from lark import Transformer
from modules.transformers.arrays       import ArraysMixin
from modules.transformers.assignments  import AssignmentsMixin
from modules.transformers.blocks       import BlocksMixin
from modules.transformers.conditions   import ConditionsMixin
from modules.transformers.control_flow import ControlFlowMixin
from modules.transformers.functions    import FunctionsMixin
from modules.transformers.linq         import LinqMixin
from modules.transformers.macros       import MacrosMixin
from modules.transformers.misc         import MiscMixin
from modules.transformers.values       import ValuesMixin

class HslTransformer(
    ArraysMixin,
    AssignmentsMixin,
    BlocksMixin,
    ConditionsMixin,
    ControlFlowMixin,
    FunctionsMixin,
    LinqMixin,
    MacrosMixin,
    MiscMixin,
    ValuesMixin,
    Transformer
):
    # Explicitly define external_macros as a keyword argument with a default value of None
    def __init__(self, external_macros=None):
        # Initialize the base Lark Transformer class WITHOUT passing our custom argument
        super().__init__()
        # Store the macros dictionary in the transformer instance
        # If external_macros was passed, we use it; otherwise, we start with an empty dict
        self.macros = external_macros if external_macros is not None else {}

    def start(self, items):
        # Filter out None values (which are left by macro definitions)
        items = [item for item in items if item is not None]
        # Compile arithmetic expression trees into accumulator value-blocks.
        return self._lift_seq(items)

    # ---- arithmetic -> accumulator value-blocks -----------------------------
    # An arithmetic expression is parsed into a tree:
    #   ("MATH", op, left, right)   binary op, op in + - * / % **
    #   ("MATHFN", name, [args])    builtin: sqrt / round / clamp
    # HoI4 has no inline math, but it *does* have accumulator "value = { ... }"
    # blocks (see script_math_functions docs): a block starts from `value = X`
    # and applies a sequence of ops (add/subtract/multiply/divide/modulo/pow/
    # root/round/clamp) left to right. We compile a whole tree into ONE such
    # nested block, so `(1 + 2) * 3` becomes
    #   value = { value = { value = 1  add = 2 }  multiply = 3 }
    # No temp variables are generated. Operator precedence and associativity are
    # already baked into the tree by the grammar cascade, so compilation is a
    # straight structural walk.
    #
    # A statement sequence may contain nested lists (operator-macro expansions,
    # folded conditions); generate_hoi4_code flattens those at render time, so we
    # flatten here first — otherwise MATH nodes hiding inside a spliced list are
    # never visited.
    _MATH_CMD = {
        "+":  "add",
        "-":  "subtract",
        "*":  "multiply",
        "/":  "divide",
        "%":  "mod",
        "**": "pow",
    }

    @staticmethod
    def _unwrap_tag(v):
        if isinstance(v, tuple) and v and v[0] == "COUNTRY_TAG":
            return v[1]
        return v

    def _flatten(self, items):
        # Splice nested lists (macro expansions / folded conditions) into one level.
        out = []
        for it in items:
            if isinstance(it, list):
                out.extend(self._flatten(it))
            else:
                out.append(it)
        return out

    def _is_expr(self, v):
        return isinstance(v, tuple) and v and v[0] in ("MATH", "MATHFN")

    def _expr_to_str(self, v):
        # Best-effort source-like rendering of an expression tree, for error
        # messages. Not a full round-trip — just enough to point the user at the
        # offending expression.
        if isinstance(v, tuple) and v and v[0] == "MATH":
            return f"{self._expr_to_str(v[2])} {v[1]} {self._expr_to_str(v[3])}"
        if isinstance(v, tuple) and v and v[0] == "MATHFN":
            inner = ", ".join(self._expr_to_str(a) for a in v[2])
            return f"{v[1]}({inner})"
        if isinstance(v, tuple) and v and v[0] == "COUNTRY_TAG":
            return f"${v[1]}"
        return str(v)

    def _acc_operand(self, v):
        # Value that goes on the right of an accumulator op (value=/add=/...).
        # A sub-expression becomes a nested ("BLOCK", <accumulator steps>);
        # a scalar is emitted verbatim (tags unwrapped to bare identifiers).
        if self._is_expr(v):
            return ("BLOCK", self._compile_expr(v))
        return self._unwrap_tag(v)

    def _compile_expr(self, node):
        # Returns a list of accumulator ASSIGN steps for one expression node,
        # suitable as the body of a ("BLOCK", ...). The list always begins with
        # a `value = ...` seed.
        if node[0] == "MATH":
            _, op, left, right = node
            cmd = self._MATH_CMD.get(op, "unknown_math_op")
            return [
                ("ASSIGN", "value", "=", self._acc_operand(left)),
                ("ASSIGN", cmd,     "=", self._acc_operand(right)),
            ]

        # MATHFN
        _, name, args = node
        seed = ("ASSIGN", "value", "=", self._acc_operand(args[0]))
        if name == "sqrt":
            # root of degree 2; second arg would be the degree if we ever add it.
            return [seed, ("ASSIGN", "root", "=", 2)]
        if name == "round":
            return [seed, ("ASSIGN", "round", "=", "yes")]
        if name == "clamp":
            lo = self._acc_operand(args[1])
            hi = self._acc_operand(args[2])
            return [seed, ("ASSIGN", "clamp", "=",
                           ("BLOCK", [("ASSIGN", "min", "=", lo),
                                      ("ASSIGN", "max", "=", hi)]))]
        return [seed, ("ASSIGN", "unknown_math_func", "=", name)]

    def _lift_seq(self, stmts):
        return [self._lift_stmt(s) for s in self._flatten(stmts)]

    def _lift_value(self, v):
        # Rewrite a value slot: expression -> accumulator BLOCK; BLOCK -> recurse
        # into its children; scalar -> unchanged.
        if self._is_expr(v):
            return ("BLOCK", self._compile_expr(v))
        if isinstance(v, tuple) and v and v[0] == "BLOCK":
            inner = self._flatten(v[1])
            scope_var = v[2] if len(v) > 2 else None
            new_inner = [self._lift_stmt(ist) for ist in inner]
            if scope_var is not None:
                return ("BLOCK", new_inner, scope_var)
            return ("BLOCK", new_inner)
        return v

    def _lift_stmt(self, s):
        # Rewrite any arithmetic trees inside a statement's value slot in place.
        if not (isinstance(s, tuple) and s and s[0] == "ASSIGN" and len(s) == 4):
            return s
        _, L, OP, R = s
        return ("ASSIGN", L, OP, self._lift_value(R))
