"""AST audit: every ``create*Proto`` builder in ``ib_async/_proto/*.py``
gates each proto-field assignment with the *same* validity check IBKR's
reference client uses in ``ibapi/client_utils.py``.

Why this exists
---------------
The TWS gateway rejects requests when an ``optional int32`` / ``int64``
/ ``double`` / ``string`` field arrives proto3-absent because the
server's default fills the field with IBKR's magic sentinel
(``UNSET_INTEGER = 2**31-1``, ``UNSET_LONG = 2**63-1``,
``UNSET_DOUBLE = float-max``). The visible symptom is
``Error 135: Can't find order with id = 2147483647``.

IBKR's builders all gate writes:

    if isValidIntValue(order.clientId): proto.clientId = order.clientId
    if order.action: proto.action = order.action
    if isValidFloatValue(order.lmtPrice): proto.lmtPrice = order.lmtPrice

So must ours. This script parses both sides as AST, classifies the gate
on every assignment, and flags any pair where ours diverges. Exit 0
iff parity is clean.

Run: ``uv run python scripts/audit_proto_parity.py``
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _twsapi_meta import load as _load_meta  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUR_PROTO_DIR = REPO_ROOT / "ib_async" / "_proto"

# Reference encoder is shipped INSIDE the IBKR TWS API archive
# alongside the .proto schemas, so a cache hit guarantees the audit
# is checking parity against the exact bytes that produced our
# generated bindings. ``scripts/generate_protos.py`` populates the
# cache; if absent, run ``make protos``.
#
# Resolution is module-level (cheap path computation) but existence
# is verified lazily in main() — so the parity test can ``import``
# this module without exploding when the cache hasn't been populated
# yet.
IBKR_CLIENT_UTILS = _load_meta().client_utils_path

# Gate kinds. The first six are the only ones IBKR uses for scalar
# fields; ``none`` marks unconditional assignment (rare, mostly
# compositional like ``proto.x.CopyFrom(y)``).
INT_VALID = "int_valid"
FLOAT_VALID = "float_valid"
LONG_VALID = "long_valid"
DECIMAL_VALID = "decimal_valid"
TRUTHY = "truthy"
IS_NOT_NONE = "is_not_none"
NONE = "none"


def classify_gate(test: ast.expr | None) -> str:
    """Map an ``if <test>:`` AST node to one of the gate kinds above.

    The classifier is intentionally lossy — we only care whether the
    gate semantically matches IBKR's, not the exact source text. Calls
    to ``_isValidInt`` / ``isValidIntValue`` collapse to ``int_valid``,
    etc. Anything we don't recognize falls through to ``TRUTHY`` (the
    safest assumption for a bare ``if x:``).
    """
    if test is None:
        return NONE
    if isinstance(test, ast.Call):
        func = test.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else func.id
            if isinstance(func, ast.Name)
            else None
        )
        if name in {"isValidIntValue", "_isValidInt"}:
            return INT_VALID
        if name in {"isValidFloatValue", "_isValidFloat"}:
            return FLOAT_VALID
        if name in {"isValidLongValue", "_isValidLong"}:
            return LONG_VALID
        if name in {"isValidDecimalValue", "_isValidDecimal"}:
            return DECIMAL_VALID
    if isinstance(test, ast.Compare):
        # ``x != UNSET_INTEGER`` style inline checks.
        if len(test.ops) == 1 and isinstance(test.ops[0], ast.NotEq):
            right = test.comparators[0]
            if isinstance(right, ast.Name):
                if right.id == "UNSET_INTEGER":
                    return INT_VALID
                if right.id == "UNSET_DOUBLE":
                    return FLOAT_VALID
                if right.id == "UNSET_LONG":
                    return LONG_VALID
                if right.id == "UNSET_DECIMAL":
                    return DECIMAL_VALID
        # ``x is not None``
        if (
            len(test.ops) == 1
            and isinstance(test.ops[0], ast.IsNot)
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None
        ):
            return IS_NOT_NONE
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        # ``x is not None and x`` collapses to IS_NOT_NONE — IBKR uses
        # this for list fields where the proto append also needs the
        # list to be non-empty. The proto-write semantics match
        # IS_NOT_NONE for the parity comparison.
        for sub in test.values:
            kind = classify_gate(sub)
            if kind == IS_NOT_NONE:
                return IS_NOT_NONE
        return TRUTHY
    return TRUTHY


def proto_target(target: ast.expr) -> tuple[str, str] | None:
    """If ``target`` is ``<name>.<field>``, return ``(name, field)``.
    Otherwise ``None`` — we only care about flat single-attribute
    assignments to a proto local."""
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        return target.value.id, target.attr
    return None


def collect_assigns(
    func: ast.FunctionDef,
) -> list[tuple[str, str]]:
    """Return ``[(field_name, gate_kind), …]`` for every
    ``<proto>.<field> = …`` assignment inside ``func``. Walks all
    enclosing ``If`` ancestors so the *immediate* enclosing test is
    the one we record (matching IBKR's flat ``if X: assign`` style)."""
    out: list[tuple[str, str]] = []

    def walk(node: ast.AST, gate: str) -> None:
        if isinstance(node, ast.If):
            sub_gate = classify_gate(node.test)
            for body_stmt in node.body:
                walk(body_stmt, sub_gate)
            for else_stmt in node.orelse:
                walk(else_stmt, gate)
            return
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                tf = proto_target(tgt)
                if tf is not None:
                    _, field = tf
                    # Filter compositional sub-message writes like
                    # ``proto.executionFilter.CopyFrom(...)`` which the
                    # AST already excludes (CopyFrom is a Call, not an
                    # Assign). Flat scalar / string / repeated assigns
                    # are what we want.
                    out.append((field, gate))
            return
        for child in ast.iter_child_nodes(node):
            walk(child, gate)

    for stmt in func.body:
        walk(stmt, NONE)
    return out


def collect_functions(path: Path) -> dict[str, list[tuple[str, str]]]:
    """Parse ``path`` and return ``{fn_name: [(field, gate), …]}`` for
    every ``def create*`` function (including ``@staticmethod`` wrapped
    ones, which is how IBKR's reference is structured)."""
    tree = ast.parse(path.read_text())
    result: dict[str, list[tuple[str, str]]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("create"):
            result[node.name] = collect_assigns(node)
    return result


def load_ibkr() -> dict[str, list[tuple[str, str]]]:
    return collect_functions(IBKR_CLIENT_UTILS)


def load_ours() -> dict[str, list[tuple[str, str]]]:
    merged: dict[str, list[tuple[str, str]]] = {}
    for path in sorted(OUR_PROTO_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        for fn, assigns in collect_functions(path).items():
            # Skip *Args / domain decoders — IBKR-side analogue uses
            # different names; we only compare like-named builders.
            merged[fn] = assigns
    return merged


# Acknowledged divergences. Each ``(fn, field)`` entry here is a known
# gap we cannot or deliberately do not fix in the converter — the audit
# treats it as non-divergent. Every entry needs a one-line reason so
# future contributors can re-evaluate.
# Some IBKR builders inline a sub-message that we factor into its own
# converter. To compare gates correctly, treat the IBKR function as
# matching either of the listed ours-side names (the field can live in
# any of them).
EXTRA_OURS_FNS: dict[str, tuple[str, ...]] = {
    "createExecutionRequestProto": ("createExecutionFilterProto",),
    "createPlaceOrderRequestProto": ("createOrderProto", "createContractProto"),
}


ACCEPTED_GAPS: dict[tuple[str, str], str] = {
    # IBKR's ``Order.discretionaryAmt`` is typed ``int`` on their side
    # but the proto field is ``double``; their gate uses
    # ``isValidIntValue`` against a 0.0 default. Our domain types it as
    # ``float`` and we gate with ``_isValidFloat`` — matches the proto
    # type and is semantically equivalent (neither sentinel collides
    # with 0.0).
    (
        "createOrderProto",
        "discretionaryAmt",
    ): "proto field is double; our float gate matches",
    # ``routeMarketableToBbo`` and ``usePriceMgmtAlgo`` are wire-int
    # (0/1/UNSET) but our domain types them as ``bool`` with default
    # ``False`` — there is no representation for "explicit no" distinct
    # from "leave at server default", so we collapse both into the
    # truthy gate. The wire effect is equivalent because proto3-absent
    # ≡ proto3-bool-default = False on the server.
    (
        "createOrderProto",
        "routeMarketableToBbo",
    ): "domain bool collapses None and False; proto3 absent ≡ False default",
    (
        "createOrderProto",
        "usePriceMgmtAlgo",
    ): "domain bool collapses None and False; proto3 absent ≡ False default",
    # IBKR's reference uses a truthy gate on ``bondAccruedInterest``
    # (a ``Decimal``); ours is ``Decimal | None`` so an explicit
    # ``is not None`` check is the semantically-precise gate. Truthy
    # would silently drop ``Decimal("0")`` (a valid zero-accrual
    # bond). Our gate is strictly tighter.
    (
        "createOrderProto",
        "bondAccruedInterest",
    ): "Decimal | None; is_not_none is strictly tighter than IBKR's truthy",
    # IBKR's ``Contract.strike`` defaults to ``UNSET_DOUBLE``, so their
    # ``isValidFloatValue`` gate suppresses the field on every contract
    # that has no strike. OUR domain default is ``0.0``, so the same gate
    # emits ``strike: 0`` for strikeless contracts and the server rejects
    # the request with ``Error 200: No security definition has been found``
    # — it breaks every option-chain sweep, which asks for all strikes of
    # a contract month by sending no strike at all. We suppress both
    # "no strike" spellings; a zero-strike instrument does not exist.
    (
        "createContractProto",
        "strike",
    ): "our domain default is 0.0, IBKR's is UNSET_DOUBLE; both mean unset",
}


def compare(
    ibkr: dict[str, list[tuple[str, str]]],
    ours: dict[str, list[tuple[str, str]]],
) -> tuple[list[str], list[str]]:
    """Return ``(divergences, notes)``. Divergences fail the audit;
    notes are informational only."""
    divergences: list[str] = []
    notes: list[str] = []
    for fn, ibkr_assigns in sorted(ibkr.items()):
        if not any(
            kind
            in {INT_VALID, FLOAT_VALID, LONG_VALID, DECIMAL_VALID, IS_NOT_NONE, TRUTHY}
            for _, kind in ibkr_assigns
        ):
            # No gated field at all — IBKR fn is pure ``proto.x = y``
            # writes (e.g., trivial passthrough composers). Nothing to
            # diverge on.
            continue
        our_fn_names = (fn, *EXTRA_OURS_FNS.get(fn, ()))
        if not any(n in ours for n in our_fn_names):
            notes.append(f"  note: IBKR {fn} has no ours-side match")
            continue
        our_assigns: list[tuple[str, str]] = []
        for n in our_fn_names:
            our_assigns.extend(ours.get(n, []))
        # Build a multi-map: a field can be assigned more than once
        # inside one function (rare but legal, e.g. IBKR's duplicate
        # ``exemptCode`` writes inside createOrderProto). Compare the
        # *set* of gate kinds per field.
        ibkr_map: dict[str, set[str]] = defaultdict(set)
        for f, k in ibkr_assigns:
            ibkr_map[f].add(k)
        our_map: dict[str, set[str]] = defaultdict(set)
        for f, k in our_assigns:
            our_map[f].add(k)

        sentinel_kinds = {INT_VALID, FLOAT_VALID, LONG_VALID, DECIMAL_VALID}
        soft_kinds = {IS_NOT_NONE, TRUTHY}
        for field, kinds in sorted(ibkr_map.items()):
            # Hard pass: IBKR sentinel-aware gates. A mismatch here is
            # the Error-135 class — proto3-absent ↔ IBKR sentinel
            # bleeding onto the wire. Fails the audit.
            if kinds & sentinel_kinds:
                expected = next(iter(kinds & sentinel_kinds))
                if (fn, field) in ACCEPTED_GAPS:
                    notes.append(
                        f"  accepted: {fn}.{field} ({ACCEPTED_GAPS[(fn, field)]})"
                    )
                    continue
                if field not in our_map:
                    divergences.append(f"  {fn}.{field}: IBKR={expected} ours=MISSING")
                    continue
                if expected not in our_map[field]:
                    actual = ", ".join(sorted(our_map[field]))
                    divergences.append(
                        f"  {fn}.{field}: IBKR={expected} ours={{{actual}}}"
                    )
                continue

            # Soft pass: IBKR explicitly chose ``is not None`` (keeps
            # falsy-but-present writes) vs ``truthy`` (collapses None
            # and falsy together). The wire effect of using ``truthy``
            # where IBKR uses ``is not None`` is usually benign because
            # proto3 absent ≡ proto3-default-value, but the intent
            # divergence is still a blind spot: if a future ours-side
            # edit reverses one of these, today's audit wouldn't notice.
            # Reported as ``soft:`` notes only — not failing the audit
            # — so we can ratchet to hard once each is triaged.
            if kinds & soft_kinds:
                expected = next(iter(kinds & soft_kinds))
                if (fn, field) in ACCEPTED_GAPS:
                    continue
                if field not in our_map:
                    notes.append(
                        f"  soft: {fn}.{field}: IBKR={expected} ours=NOT_WRITTEN"
                    )
                    continue
                if expected not in our_map[field] and not (
                    our_map[field] & sentinel_kinds
                ):
                    # ours-using-sentinel-gate is strictly tighter than
                    # IS_NOT_NONE / TRUTHY — don't flag that as a soft
                    # divergence (it's an upgrade, not a drift).
                    actual = ", ".join(sorted(our_map[field]))
                    notes.append(
                        f"  soft: {fn}.{field}: IBKR={expected} ours={{{actual}}}"
                    )
    return divergences, notes


def main() -> int:
    if not IBKR_CLIENT_UTILS.is_file():
        print(
            f"IBKR client_utils.py not found at {IBKR_CLIENT_UTILS}\n"
            f"Run ``make protos`` to populate the version-pinned cache.",
            file=sys.stderr,
        )
        return 1
    ibkr = load_ibkr()
    ours = load_ours()
    divergences, notes = compare(ibkr, ours)

    print(f"audit: {len(ibkr)} IBKR create* fns, {len(ours)} ours create* fns")
    for note in notes:
        print(note)
    if divergences:
        print()
        print(f"DIVERGENCES ({len(divergences)}):")
        for d in divergences:
            print(d)
        return 1
    print()
    print("no divergences — proto send-path gates match IBKR reference.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
