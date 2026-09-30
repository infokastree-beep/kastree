"""Safe evaluator for pack DSL (includeWhen, appliesWhen, review-rule 'when').
v5.1: accepts pack-authored SQL-style tokens AND/OR/NOT/true/false (normalised
before parsing) — the pack files were previously unparseable/unresolvable.
AST-whitelisted: names resolve against a context dict; comparisons, boolean
ops, arithmetic, %, abs(), string constants. Never bare eval()/exec() of pack
logic (see review: pack .py data files moved to JSON where execution mattered)."""
import ast, builtins, io, operator, re as _re, tokenize

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Mod: operator.mod,
        ast.Eq: operator.eq, ast.NotEq: operator.ne,
        ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
        ast.GtE: operator.ge}
_BOOL = {ast.And: all, ast.Or: any}
_UNARY = {ast.USub: operator.neg, ast.Not: operator.not_, ast.UAdd: operator.pos}

_KEYWORDS = {"AND": "and", "OR": "or", "NOT": "not", "true": "True", "false": "False"}


class Unanswered(Exception):
    """A predicate needed a disclosure answer the user has not given yet."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def _normalise(expr: str) -> str:
    """Rewrite SQL-style keywords in NAME tokens only; string literals such as
    'LAND AND BUILDINGS' are left untouched."""
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(expr).readline))
    except (tokenize.TokenError, IndentationError) as e:
        raise ValueError(f"unparseable predicate: {e}") from None
    out = [(t.type, _KEYWORDS.get(t.string, t.string)) if t.type == tokenize.NAME
           else (t.type, t.string) for t in toks]
    return tokenize.untokenize(out)

MAX_EXPR = 10_000  # C7: pathological pack expressions are rejected before parse

def evaluate(expr: str, ctx: dict) -> bool:
    if not isinstance(expr, str) or len(expr) > MAX_EXPR:
        raise ValueError("predicate expression missing or oversized")
    def walk(node):
        if isinstance(node, ast.Expression): return walk(node.body)
        if isinstance(node, ast.BoolOp):
            # generator => Python short-circuit semantics (all/any stop early)
            return _BOOL[type(node.op)](walk(v) for v in node.values)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = walk(node.left), walk(node.right)
            if isinstance(left, str) or isinstance(right, str):
                raise ValueError("arithmetic on strings is not allowed in pack DSL")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](walk(node.operand))
        if isinstance(node, ast.Compare):
            left = walk(node.left)
            for op, comp in zip(node.ops, node.comparators, strict=True):
                if type(op) not in _OPS:
                    raise ValueError(f"disallowed comparison: {type(op).__name__}")
                right = walk(comp)
                if not _OPS[type(op)](left, right): return False
                left = right
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "abs" and len(node.args) == 1 and not node.keywords:
            return builtins.abs(walk(node.args[0]))
        if isinstance(node, ast.Name):
            if node.id not in ctx: raise KeyError(f"unknown predicate name: {node.id}")
            value = ctx[node.id]
            if value is None:  # tri-state: unanswered disclosure fact
                raise Unanswered(node.id)
            return value
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool, str)):
            return node.value
        raise ValueError(f"disallowed expression element: {ast.dump(node)}")
    try:
        return bool(walk(ast.parse(_normalise(expr), mode="eval")))
    except (SyntaxError, RecursionError) as e:  # one error type for callers
        raise ValueError(f"unparseable predicate: {e}") from None


def declared_names(expr: str) -> set:
    """All variable names an expression reads (for pack-load validation)."""
    tree = ast.parse(_normalise(expr), mode="eval")
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
    return names - {"abs", "True", "False"}
