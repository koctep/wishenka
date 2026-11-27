"""Failing reproduction for WISHENKA-335: one shared apply procedure.

Wishlist startup and person startup both still call the apply procedure
that lives in the wishlist package. They must call the same procedure
from ``wishenka.db.migrations``.
"""

from __future__ import annotations

import pytest

# Auth loads the wishlist store through a completed import. Importing the
# store first leaves it half-initialized and raises a circular ImportError.
import wishenka.auth.models  # noqa: F401
import wishenka.users.store as user_store
import wishenka.wishlists.store as wishlist_store

pytestmark = pytest.mark.timeout(10)


def test_wishlist_and_person_startup_call_shared_upgrade_to_head() -> None:
    """Both stores use the apply procedure in ``wishenka.db.migrations``."""
    import wishenka.db.migrations as shared

    assert user_store.upgrade_to_head is shared.upgrade_to_head
    assert wishlist_store.upgrade_to_head is shared.upgrade_to_head
