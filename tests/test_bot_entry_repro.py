"""Reproduce the missing role-aware Mini App public-link entry (WISHENKA-27)."""

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_helpers import Seeded
from tests.conftest import BrowserServer, _open_page
from tests.test_giver_csrf_repro_browser import wishlist_server as wishlist_server

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]


def _open_session_page(
    browser: CdpBrowser, pages: list[CdpPage], server: BrowserServer, token: str, payload: str
) -> CdpPage:
    """Open a Mini App entry with the session cookie used by the CSRF endpoint."""
    browser.ensure_alive()
    page = browser.new_page((412, 800))
    pages.append(page)
    page._send("Network.setCookie", {"name": "session_id", "value": token, "url": server.base_url})
    page.navigate(f"{server.base_url}/?startapp={payload}")
    return page


def test_shared_link_offers_authenticated_giver_reservation(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """A giver arriving from a shared Mini App link can reserve the displayed wish."""
    seeded = seed_wishlist(["A shared gift"])
    page = _open_session_page(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        seeded.viewer_token,
        f"p_{seeded.public_token}",
    )
    page.wait_for("shared gift displayed", "document.body.innerText.includes('A shared gift')")

    text = page.evaluate("document.body.innerText")
    assert "Забронировать" in text or "Reserve" in text, (
        "A signed-in giver following a public Mini App link cannot reserve the wish; "
        f"rendered text: {text!r}"
    )
    page.evaluate(
        "[...document.querySelectorAll('button')].find(b => b.innerText === 'Reserve').click()"
    )
    page.wait_for(
        "reservation completed", "document.getElementById('status').innerText === 'Reserved'"
    )


@pytest.mark.parametrize("kind", ["malformed", "unknown", "revoked"])
def test_invalid_public_links_offer_generic_recovery_without_creating_lists(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    kind: str,
) -> None:
    """Malformed, unknown, and revoked capabilities offer the same safe way home."""
    import httpx

    seeded = seed_wishlist(["Private gift"])
    headers = {"Authorization": f"Bearer {seeded.owner_token}"}
    with httpx.Client(base_url=wishlist_server.base_url, headers=headers, timeout=10) as api:
        before = api.get("/api/wishlists")
        before.raise_for_status()
        reset = api.post(f"/api/wishlists/{seeded.wishlist_id}/share/reset")
        reset.raise_for_status()
        expected_count = len(before.json())
        payload = {
            "malformed": "p_%21invalid",
            "unknown": "p_unknown_token",
            "revoked": f"p_{seeded.public_token}",
        }[kind]
        page = _open_session_page(
            chromium_browser, _browser_pages, wishlist_server, seeded.owner_token, payload
        )
        page.wait_for("entry settled", "document.body.innerText.trim().length > 0")
        page.wait_for(
            "recovery available",
            "[...document.querySelectorAll('button, a')].some(e => "
            "/home|menu|главн|меню/i.test(e.innerText))",
        )
        assert "Private gift" not in page.evaluate("document.body.innerText")
        after = api.get("/api/wishlists")
        after.raise_for_status()
        assert len(after.json()) == expected_count


def test_invitation_link_still_requires_explicit_confirmation(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """A collaborator link previews an invitation without silently granting membership."""
    import httpx

    seeded = seed_wishlist(["A gift"])
    headers = {"Authorization": f"Bearer {seeded.owner_token}"}
    with httpx.Client(base_url=wishlist_server.base_url, headers=headers, timeout=10) as api:
        detail = api.get(f"/api/wishlists/{seeded.wishlist_id}")
        detail.raise_for_status()
        invite_token = detail.json()["invite_token"]
        members_before = detail.json()["members"]
        page = _open_page(
            chromium_browser,
            _browser_pages,
            f"{wishlist_server.base_url}/?startapp=i_{invite_token}",
            seeded.viewer_token,
            (412, 800),
        )
        page.wait_for("invitation preview", "document.body.innerText.includes('Confirm joining')")
        after = api.get(f"/api/wishlists/{seeded.wishlist_id}")
        after.raise_for_status()
        assert after.json()["members"] == members_before


def test_shared_link_hides_reservation_from_recipient(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """A recipient must not learn that another user reserved their wish."""
    import httpx

    seeded = seed_wishlist(["Surprise gift"])
    with httpx.Client(
        base_url=wishlist_server.base_url,
        headers={"Authorization": f"Bearer {seeded.viewer_token}"},
        timeout=10,
    ) as api:
        reservation = api.post(
            f"/api/wishlists/{seeded.wishlist_id}/items/{seeded.item_ids[0]}/reservations",
            json={"quantity": 1},
        )
        reservation.raise_for_status()
    page = _open_session_page(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        seeded.owner_token,
        f"p_{seeded.public_token}",
    )
    page.wait_for("recipient sees wish", "document.body.innerText.includes('Surprise gift')")
    text = page.evaluate("document.body.innerText").lower()
    assert not any(word in text for word in ("reserved", "забронир", "viewer"))


def test_anonymous_public_api_does_not_disclose_reservations(
    seed_wishlist: Callable[..., Seeded], wishlist_server: BrowserServer
) -> None:
    """An unidentified recipient gets the same public response before and after reservation."""
    import httpx

    seeded = seed_wishlist(["Surprise gift"])
    path = f"/api/public/wishlists/{seeded.public_token}/view"
    with httpx.Client(base_url=wishlist_server.base_url, timeout=10) as api:
        before = api.get(path)
        before.raise_for_status()
        reservation = api.post(
            f"/api/wishlists/{seeded.wishlist_id}/items/{seeded.item_ids[0]}/reservations",
            headers={"Authorization": f"Bearer {seeded.viewer_token}"},
            json={"quantity": 1},
        )
        reservation.raise_for_status()
        after = api.get(path)
        after.raise_for_status()
        before_item = before.json()["items"][0]
        after_body = after.json()
        item = after_body["items"][0]
        assert after_body["identified"] is False
        assert item["title"] == "Surprise gift"
        assert item["id"] == before_item["id"]
        assert "reservations" not in item
        assert item["is_reserved_by_me"] is False
        assert item["my_reservation_id"] is None
        assert item["available_quantity"] == before_item["available_quantity"] - 1

        giver = api.get(path, headers={"Authorization": f"Bearer {seeded.viewer_token}"})
        giver.raise_for_status()
        assert giver.json()["items"][0]["is_reserved_by_me"] is True
        recipient = api.get(path, headers={"Authorization": f"Bearer {seeded.owner_token}"})
        recipient.raise_for_status()
        assert "available_quantity" not in recipient.json()["items"][0]


def test_shared_link_retains_sharing_controls(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """A visitor can still copy and share the public link from the shared view."""
    seeded = seed_wishlist(["A shared gift"])
    page = _open_session_page(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        seeded.viewer_token,
        f"p_{seeded.public_token}",
    )
    page.wait_for("shared gift displayed", "document.body.innerText.includes('A shared gift')")
    page.evaluate(
        "document.getElementById('app').dataset.bot='test_bot';"
        "document.getElementById('app').dataset.miniapp='wishlist';"
        f"publicView('{seeded.public_token}')"
    )
    page.wait_for("sharing controls", "document.body.innerText.includes('Share via Telegram')")
    assert (
        page.evaluate(
            "document.querySelector('input[aria-label=\"Public gift-selection link\"]').value"
        )
        == f"https://t.me/test_bot/wishlist?startapp=p_{seeded.public_token}"
    )
    assert "Copy link" in page.evaluate("document.body.innerText")


@pytest.mark.timeout(90)
def test_unavailable_link_recovery_is_indistinguishable(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    tmp_path: Path,
) -> None:
    """Invalid, unknown, rotated and deleted links reveal identical recovery text."""
    import sqlite3

    import httpx

    rotated = seed_wishlist(["Rotated private gift"])
    deleted = seed_wishlist(["Deleted private gift"])
    headers = {"Authorization": f"Bearer {rotated.owner_token}"}
    with httpx.Client(base_url=wishlist_server.base_url, headers=headers, timeout=10) as api:
        reset = api.post(f"/api/wishlists/{rotated.wishlist_id}/share/reset")
        reset.raise_for_status()
        # Set up the same soft-deleted state that the domain deletion service persists.
        with sqlite3.connect(tmp_path / "csrf-browser.db", timeout=5) as db:
            db.execute(
                "UPDATE wl_lists SET status = 'deleted' WHERE id = ?", (deleted.wishlist_id,)
            )
        before = api.get("/api/wishlists")
        before.raise_for_status()
        payloads = (
            "p_%21invalid",
            "p_unknown_token",
            f"p_{rotated.public_token}",
            f"p_{deleted.public_token}",
        )
        messages = []
        for payload in payloads:
            page = _open_session_page(
                chromium_browser, _browser_pages, wishlist_server, rotated.owner_token, payload
            )
            page.wait_for(
                "unavailable link recovery",
                "[...document.querySelectorAll('button, a')].some(e => "
                "/home|menu|главн|меню/i.test(e.innerText))",
            )
            messages.append(page.evaluate("document.body.innerText.trim()"))
        assert len(set(messages)) == 1
        assert all("private gift" not in message.lower() for message in messages)
        after = api.get("/api/wishlists")
        after.raise_for_status()
        assert len(after.json()) == len(before.json())


def test_revoked_capability_cannot_create_a_reservation(
    seed_wishlist: Callable[..., Seeded], wishlist_server: BrowserServer
) -> None:
    """Recheck the public capability in the same operation as the reservation."""
    import httpx

    seeded = seed_wishlist(["A gift"])
    with httpx.Client(base_url=wishlist_server.base_url, timeout=10) as api:
        owner = {"Authorization": f"Bearer {seeded.owner_token}"}
        viewer = {"Authorization": f"Bearer {seeded.viewer_token}"}
        api.post(
            f"/api/wishlists/{seeded.wishlist_id}/share/reset", headers=owner
        ).raise_for_status()
        response = api.post(
            f"/api/public/wishlists/{seeded.public_token}/items/{seeded.item_ids[0]}/reservations",
            headers=viewer,
            json={"quantity": 1},
        )
        assert response.status_code == 404
