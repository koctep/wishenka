"""Structure pins for the WISHENKA-112 cleanup (red before Step 4, green after).

These tests pin NAMES and CODE SHAPE, not behaviour, and are kept deliberately minimal
(three tests, one per acceptance criterion). Behaviour is protected separately by
``tests/test_items_ui_error_mapping.py``, which is green both before and after the refactor.
A refactoring has no failing behaviour to reproduce, so these checks exist only to stop the
cleanup from being silently reverted; they prove nothing about correctness on their own.
"""

from __future__ import annotations

import ast
import typing
from collections.abc import Callable
from pathlib import Path

import pytest

from wishenka.web.routes import items_ui
from wishenka.wishlists.exceptions import (
    ItemNotFoundError,
    PermissionDeniedError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)

pytestmark = pytest.mark.timeout(30)

_ROOT = Path(__file__).resolve().parents[1] / "wishenka" / "wishlists"
_FORBIDDEN_COLUMNS = {"warn_on_delete_reserved", "display_order"}


def test_domain_errors_group_replaces_not_found_errors() -> None:
    """The misnamed ``_NOT_FOUND_ERRORS`` is gone; ``_DOMAIN_ERRORS`` holds the five classes."""
    assert not hasattr(items_ui, "_NOT_FOUND_ERRORS")
    group: tuple[type[Exception], ...] = getattr(items_ui, "_DOMAIN_ERRORS", ())
    assert set(group) == {
        WishlistNotFoundError,
        WishlistDeletedError,
        ItemNotFoundError,
        PermissionDeniedError,
        WishlistArchivedError,
    }
    assert len(group) == 5


def test_reorder_callback_takes_only_current_ids() -> None:
    """``reorder`` is ``Callable[[list[int]], list[int]]`` (no unused service argument)."""
    hint = typing.get_type_hints(items_ui._reordered_response)["reorder"]
    assert typing.get_origin(hint) is Callable
    assert typing.get_args(hint) == ([list[int]], list[int])


def test_no_column_presence_checks_for_guaranteed_columns() -> None:
    """No ``hasattr``/``getattr`` probes for columns that the schema guarantees."""
    offenders: list[str] = []
    for module in ("store.py", "repository.py"):
        tree = ast.parse((_ROOT / module).read_text(encoding="utf-8"))
        offenders.extend(
            f"{module}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"hasattr", "getattr"}
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in _FORBIDDEN_COLUMNS
        )
    assert offenders == []
