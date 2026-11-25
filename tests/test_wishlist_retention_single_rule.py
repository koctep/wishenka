"""WISHENKA-316: one shared restorability rule for a deleted wishlist.

The test imports ``wishenka.wishlists.retention.is_retention_expired``. Until
that module exists, the import is the red signal. After it exists, a list
deleted inside the configured window stays restorable until the shared rule is
forced to report that the window has ended. Delete, recently deleted, and
restore must all follow that answer.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from tests.test_wishlist_delete_api import OWNER_ID, _create, _delete, _open_app

pytestmark = pytest.mark.timeout(30)


def _rule_says_expired(*_args: object, **_kwargs: object) -> bool:
    return True


def _force_shared_rule_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the single rule so every call site sees an ended window.

    Call sites must read ``is_retention_expired`` from
    ``wishenka.wishlists.retention`` at call time. The import is uncaught: a
    missing module fails the test before any later assertion can hide it.
    """
    from wishenka.wishlists.retention import is_retention_expired

    assert callable(is_retention_expired)
    monkeypatch.setattr(
        "wishenka.wishlists.retention.is_retention_expired",
        _rule_says_expired,
    )


def _detail_code(response: Any) -> str | None:
    body = response.json()
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        code = detail.get("code")
        return str(code) if code is not None else None
    return None


def _events(records: list[logging.LogRecord]) -> list[str]:
    names: list[str] = []
    for record in records:
        event = getattr(record, "event", None)
        if isinstance(event, str):
            names.append(event)
    return names


def _shared_rule_gaps(
    wishlist_id: int,
    repeated: Any,
    listed: Any,
    restored: Any,
    delete_records: list[logging.LogRecord],
) -> list[str]:
    """Describe where delete, list, and restore ignored the shared rule."""
    gaps: list[str] = []
    if repeated.status_code != 410 or _detail_code(repeated) != "retention_expired":
        gaps.append(
            f"DELETE stayed {repeated.status_code} code={_detail_code(repeated)!r}; "
            "expected 410 retention_expired"
        )
    events = _events(delete_records)
    expired = [
        record
        for record in delete_records
        if getattr(record, "event", None) == "wishlist_retention_expired"
    ]
    operation = getattr(expired[0], "operation", None) if len(expired) == 1 else None
    if operation != "delete_wishlist":
        gaps.append(
            "DELETE did not log wishlist_retention_expired with operation "
            f"delete_wishlist; events={events}"
        )
    if "wishlist_deleted_by_owner" in events or "wishlist_status_changed" in events:
        gaps.append(
            "DELETE still logged wishlist_deleted_by_owner or "
            f"wishlist_status_changed; events={events}"
        )
    if listed.status_code != 200:
        gaps.append(f"GET /api/wishlists/deleted stayed {listed.status_code}")
    else:
        ids = [int(row["id"]) for row in listed.json()]
        if wishlist_id in ids:
            gaps.append(f"GET /api/wishlists/deleted still includes {wishlist_id}")
    if restored.status_code != 410 or _detail_code(restored) != "retention_expired":
        gaps.append(
            f"POST restore-deleted stayed {restored.status_code} "
            f"code={_detail_code(restored)!r}; expected 410 retention_expired"
        )
    return gaps


def test_shared_rule_expires_delete_list_and_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Expiry from the shared rule is the answer for delete, list, and restore."""
    with _open_app(tmp_path / "retention-rule.db") as env:
        wishlist_id = int(_create(env)["id"])
        first = _delete(env, wishlist_id)
        assert first.status_code == 200, first.text

        _force_shared_rule_expired(monkeypatch)
        with caplog.at_level(logging.INFO, logger="wishenka"):
            caplog.clear()
            repeated = _delete(env, wishlist_id)
        delete_records = list(caplog.records)
        listed = env.client.get("/api/wishlists/deleted", headers=env.headers(OWNER_ID))
        restored = env.client.post(
            f"/api/wishlists/{wishlist_id}/restore-deleted",
            headers=env.headers(OWNER_ID),
        )

    gaps = _shared_rule_gaps(wishlist_id, repeated, listed, restored, delete_records)
    assert not gaps, "shared retention rule was not applied:\n" + "\n".join(gaps)
