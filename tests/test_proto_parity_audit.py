"""Pin parity between ``ib_async/_proto/*.py`` and IBKR's reference
``client_utils.py`` builders.

The audit script (``scripts/audit_proto_parity.py``) parses both
implementations as AST and flags any ``create*Proto`` field whose
sentinel gate diverges. This test runs that script in-process so any
future regression — a contributor reverting ``_isValidInt`` back to
``truthy`` on a hot field, or adding a new builder without copying the
gate from IBKR — breaks CI immediately.

The script is the source of truth; if it changes, this test
automatically tracks the new behaviour.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def audit_module():
    """Load ``scripts/audit_proto_parity.py`` as a fresh module so we
    can call its ``main()`` without spawning a subprocess.

    The script lives outside the ``ib_async`` package (it's a dev-time
    tool, not shipped to users), so an explicit ``importlib`` load is
    cleaner than path-mangling ``sys.path``."""
    script_path = (
        Path(__file__).resolve().parent.parent / "scripts" / "audit_proto_parity.py"
    )
    spec = importlib.util.spec_from_file_location("audit_proto_parity", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_proto_send_path_matches_ibkr_reference(audit_module, capsys):
    """Every ``create*Proto`` builder must gate proto-field writes with
    the same validity check IBKR's reference uses. A divergence here
    means a TWS server will reject the request because a proto3-absent
    field arrives as the IBKR magic sentinel — the
    ``Error 135: Can't find order with id = 2147483647`` failure mode."""
    exit_code = audit_module.main()
    captured = capsys.readouterr()
    assert exit_code == 0, (
        "proto send-path diverges from IBKR reference — see audit output:\n"
        + captured.out
    )
