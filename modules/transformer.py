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
        # Lift inline arithmetic (("ARITH", ...)) into temp-variable steps.
        self._arith_counter = 0
        return self._lift_seq(items)

    # ---- inline-arithmetic lifting -----------------------------------------
    # `a OP b` in a value position is emitted by the transformer as an
    # ("ARITH", op, left, right) marker. HoI4 has no inline math, so each marker
    # is expanded here into a fresh temp variable plus its update, and the marker
    # is replaced by the temp's name. Placement:
    #   * marker directly in a statement's value slot (a call argument) -> the
    #     steps go BEFORE that statement (jump out of the enclosing param block);
    #   * marker inside a statement's block (an assignment RHS) -> the steps go
    #     BEFORE that statement too, i.e. in place, one level up.
    # Deeper nesting is handled by recursion so each marker lands one block up.
    #
    # A statement sequence (top level or a block body) may contain nested lists:
    # an operator-macro call splices in a *list* of statements, and condition
    # folding does the same. generate_hoi4_code flattens those at render time, so
    # we flatten here first — otherwise markers hiding inside a spliced list are
    # never visited.
    _ARITH_CMD = {
        "+": "add_to_temp_variable",
        "-": "subtract_from_temp_variable",
        "*": "multiply_temp_variable",
        "/": "divide_temp_variable",
    }

    def _new_temp(self):
        name = f"__t{self._arith_counter}"
        self._arith_counter += 1
        return name

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

    def _expand_arith(self, arith):
        _, op, left, right = arith
        left  = self._unwrap_tag(left)
        right = self._unwrap_tag(right)
        tmp = self._new_temp()
        cmd = self._ARITH_CMD.get(op, "unknown_arith_op")
        steps = [
            ("ASSIGN", "set_temp_variable", "=", ("BLOCK", [("ASSIGN", tmp, "=", left)])),
            ("ASSIGN", cmd,                 "=", ("BLOCK", [("ASSIGN", tmp, "=", right)])),
        ]
        return steps, tmp

    def _lift_seq(self, stmts):
        out = []
        for s in self._flatten(stmts):
            pre, s2 = self._lift_stmt(s)
            out.extend(pre)
            out.append(s2)
        return out

    def _lift_stmt(self, s):
        # Returns (steps_to_place_before_s, rewritten_s).
        if not (isinstance(s, tuple) and s and s[0] == "ASSIGN" and len(s) == 4):
            return [], s
        _, L, OP, R = s

        # Call-argument arithmetic: the value slot IS the marker.
        if isinstance(R, tuple) and R and R[0] == "ARITH":
            steps, tmp = self._expand_arith(R)
            return steps, ("ASSIGN", L, OP, tmp)

        # A nested block: arithmetic in its *immediate* children lifts to before
        # this statement; anything deeper recurses and stays one level down.
        if isinstance(R, tuple) and R and R[0] == "BLOCK":
            inner = self._flatten(R[1])
            scope_var = R[2] if len(R) > 2 else None
            pre = []
            new_inner = []
            for ist in inner:
                if (isinstance(ist, tuple) and ist and ist[0] == "ASSIGN" and len(ist) == 4
                        and isinstance(ist[3], tuple) and ist[3] and ist[3][0] == "ARITH"):
                    steps, tmp = self._expand_arith(ist[3])
                    pre.extend(steps)
                    new_inner.append(("ASSIGN", ist[1], ist[2], tmp))
                else:
                    ipre, ist2 = self._lift_stmt(ist)
                    new_inner.extend(ipre)
                    new_inner.append(ist2)
            return pre, ("ASSIGN", L, OP, ("BLOCK", new_inner, scope_var))

        return [], s
