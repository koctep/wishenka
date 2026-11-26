"""Failing browser repro tests for WISHENKA-289: Home overview UX and mobile ergonomics."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import httpx
import pytest

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_helpers import assert_clean_console, scroll_to
from tests.browser_screens import open_miniapp, provision_user, telegram_init_data
from tests.conftest import OWNER_TELEGRAM_ID, VIEWER_TELEGRAM_ID, BrowserServer
from wishenka.i18n import SupportedLocale, t

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]


# The helpers moved to ``tests/browser_screens.py``; the private names stay for the older tests.
_telegram_init_data = telegram_init_data
_set_user_locale = provision_user
_open_home = open_miniapp


def _seed_rich_overview(server: BrowserServer, locale: SupportedLocale) -> dict[str, Any]:
    """Seed owned, admin/member collab (both favorited), pure favorite, and reservations."""
    _set_user_locale(server, server.owner_token, OWNER_TELEGRAM_ID, "Owner", locale)
    _set_user_locale(server, server.viewer_token, VIEWER_TELEGRAM_ID, "Viewer", locale)

    owner_headers = {"Authorization": f"Bearer {server.owner_token}"}
    viewer_headers = {"Authorization": f"Bearer {server.viewer_token}"}

    long_title = (
        "Очень длинный семейный вишлист для большого праздника и проверки переноса текста"
        if locale == "ru"
        else "Very long family birthday wishlist title to verify mobile card wrapping cleanly"
    )
    event_title = "День рождения" if locale == "ru" else "Birthday Dinner"

    with httpx.Client(base_url=server.base_url, headers=owner_headers, timeout=10) as owner_api:
        owned_main = owner_api.post(
            "/api/wishlists",
            json={
                "name": long_title,
                "event_title": event_title,
                "event_date": "2026-09-15T12:00:00Z",
            },
        )
        owned_main.raise_for_status()
        owned_main_data = owned_main.json()

        owned_item = owner_api.post(
            f"/api/wishlists/{owned_main_data['id']}/items",
            json={"title": "Secret Espresso Machine", "quantity": 1},
        )
        owned_item.raise_for_status()

        # Creation requires a title. A legacy empty title is stored directly, not via PATCH.
        owned_untitled = owner_api.post("/api/wishlists", json={"name": "Temporary"})
        owned_untitled.raise_for_status()
        untitled_id = int(owned_untitled.json()["id"])
        assert server.database_path is not None
        with sqlite3.connect(server.database_path) as connection:
            updated = connection.execute(
                "UPDATE wl_lists SET title = '' WHERE id = ?", (untitled_id,)
            )
            connection.commit()
            assert updated.rowcount == 1
        stored = owner_api.get(f"/api/wishlists/{untitled_id}")
        stored.raise_for_status()
        assert stored.json()["name"] == ""

    with httpx.Client(base_url=server.base_url, headers=viewer_headers, timeout=10) as viewer_api:
        # Viewer reserves an item in owner's list (must NEVER leak on owner's Home screen).
        secret_res = viewer_api.post(
            f"/api/public/wishlists/{owned_main_data['share_token']}"
            f"/items/{owned_item.json()['id']}/reservations",
            json={"quantity": 1},
        )
        secret_res.raise_for_status()

        admin_wl = viewer_api.post("/api/wishlists", json={"name": "Admin Shared List"})
        admin_wl.raise_for_status()
        admin_wl_data = admin_wl.json()

        member_wl = viewer_api.post("/api/wishlists", json={"name": "Member Collab List"})
        member_wl.raise_for_status()
        member_wl_data = member_wl.json()

        fav_wl = viewer_api.post("/api/wishlists", json={"name": "Pure Favorite List"})
        fav_wl.raise_for_status()
        fav_wl_data = fav_wl.json()

        fav_item = viewer_api.post(
            f"/api/wishlists/{fav_wl_data['id']}/items",
            json={"title": "Ceramic Mug", "quantity": 1},
        )
        fav_item.raise_for_status()

    with httpx.Client(base_url=server.base_url, headers=owner_headers, timeout=10) as owner_api:
        for wl_data in (admin_wl_data, member_wl_data):
            join_resp = owner_api.post(
                "/api/invitations/accept",
                headers={"x-invite-token": wl_data["invite_token"]},
            )
            join_resp.raise_for_status()
            fav_join = owner_api.post(f"/api/favorites/{wl_data['id']}")
            fav_join.raise_for_status()

        owner_api.get(f"/api/public/wishlists/{fav_wl_data['share_token']}/view").raise_for_status()
        fav_pure = owner_api.post(f"/api/favorites/{fav_wl_data['id']}")
        fav_pure.raise_for_status()

        # Owner reserves 1 item on viewer's pure favorite list -> badge count must be 1.
        owner_res = owner_api.post(
            f"/api/public/wishlists/{fav_wl_data['share_token']}"
            f"/items/{fav_item.json()['id']}/reservations",
            json={"quantity": 1},
        )
        owner_res.raise_for_status()

    with httpx.Client(base_url=server.base_url, headers=viewer_headers, timeout=10) as viewer_api:
        promote = viewer_api.patch(
            f"/api/wishlists/{admin_wl_data['id']}/members/{OWNER_TELEGRAM_ID}/role",
            json={"role": "admin"},
        )
        promote.raise_for_status()

    return {
        "long_title": long_title,
        "event_title": event_title,
    }


def _collect_layout_metrics(page: CdpPage) -> dict[str, Any]:
    """Inspect Home DOM, section modifiers, visual contrast/distinction, and mobile geometry."""
    script = """(() => {
      const vw = window.innerWidth;
      const app = document.getElementById('app');
      const directSections = Array.from(app.children).filter(
        el => el.classList.contains('wishlist-section')
      );
      const nav = document.querySelector('.top-nav');
      const navButtons = Array.from(document.querySelectorAll('.top-nav button'));
      const settingsLink = document.querySelector('.top-nav a.settings-link');
      const resCard = document.querySelector('#app > a.reservations-card');
      const resRect = resCard ? resCard.getBoundingClientRect() : null;
      const firstSecRect = directSections[0]
        ? directSections[0].getBoundingClientRect()
        : null;

      const touchTargets = Array.from(
        app.querySelectorAll('button, a.settings-link, a.reservations-card')
      ).map(el => {
        const r = el.getBoundingClientRect();
        return {
          text: (el.innerText || '').trim(),
          width: r.width,
          height: r.height,
          left: r.left,
          right: r.right,
          scrollW: el.scrollWidth,
          clientW: el.clientWidth,
        };
      });

      const overlaps = (a, b) => !(
        a.right <= b.left + 0.5 || b.right <= a.left + 0.5 ||
        a.bottom <= b.top + 0.5 || b.bottom <= a.top + 0.5
      );

      const sections = directSections.map(sec => {
        const secCss = getComputedStyle(sec);
        const cards = Array.from(sec.querySelectorAll('.wishlist-card')).map(card => {
          const cRect = card.getBoundingClientRect();
          const titleEl = card.querySelector('h3.wishlist-card-title');
          const badgeEl = card.querySelector('.badge');
          const metaEl = card.querySelector('.wishlist-card-meta');
          const openBtn = card.querySelector('button.wishlist-card-open');
          const removeBtn = card.querySelector('button.wishlist-card-remove');
          const parts = [titleEl, badgeEl, metaEl, openBtn, removeBtn].filter(Boolean);
          const rects = parts.map(el => el.getBoundingClientRect());
          let hasOverlap = false;
          for (let i = 0; i < rects.length; i++) {
            for (let j = i + 1; j < rects.length; j++) {
              if (overlaps(rects[i], rects[j])) hasOverlap = true;
            }
          }
          const outOfCard = rects.some(
            r => r.left < cRect.left - 1 || r.right > cRect.right + 1
          );
          const styleOf = el => {
            if (!el) return null;
            const css = getComputedStyle(el);
            return {
              bg: css.backgroundColor,
              color: css.color,
              border: css.borderColor,
            };
          };
          return {
            text: (card.innerText || '').trim(),
            title: titleEl ? titleEl.innerText.trim() : null,
            titleInButton: Boolean(titleEl && titleEl.closest('button')),
            titleClipped: titleEl ? titleEl.scrollWidth > titleEl.clientWidth + 2 : false,
            badge: badgeEl ? badgeEl.innerText.trim() : null,
            meta: metaEl ? metaEl.innerText.trim() : null,
            openText: openBtn ? openBtn.innerText.trim() : null,
            openAria: openBtn ? openBtn.getAttribute('aria-label') : null,
            openStyle: styleOf(openBtn),
            removeText: removeBtn ? removeBtn.innerText.trim() : null,
            removeAria: removeBtn ? removeBtn.getAttribute('aria-label') : null,
            removeDanger: Boolean(removeBtn && removeBtn.classList.contains('btn-danger')),
            removeStyle: styleOf(removeBtn),
            hasOverlap,
            outOfCard,
          };
        });
        return {
          classes: Array.from(sec.classList),
          text: (sec.innerText || '').trim(),
          borderLeft: secCss.borderLeftColor,
          bg: secCss.backgroundColor,
          hasHeader: Boolean(sec.querySelector('.wishlist-section-header')),
          countText: sec.querySelector('.section-count')?.innerText.trim() || null,
          subtitleText: sec.querySelector('.section-subtitle')?.innerText.trim() || null,
          cards,
        };
      });

      return {
        innerWidth: vw,
        scrollWidth: document.documentElement.scrollWidth,
        leadText: document.querySelector('#app .home-lead')?.innerText.trim() || null,
        navHasHomeClass: Boolean(nav && nav.classList.contains('home-top-nav')),
        navButtonCount: navButtons.length,
        navButtonStyles: navButtons.map(b => {
          const css = getComputedStyle(b);
          return { bg: css.backgroundColor, color: css.color, top: b.getBoundingClientRect().top };
        }),
        settingsHref: settingsLink ? settingsLink.getAttribute('href') : null,
        settingsText: settingsLink ? settingsLink.innerText.trim() : null,
        hasResCard: Boolean(resCard),
        resTitle: resCard?.querySelector('.reservations-title')?.innerText.trim() || null,
        resHint: resCard?.querySelector('.reservations-card-hint')?.innerText.trim() || null,
        resBadge: resCard?.querySelector('.reservations-badge')?.innerText.trim() || null,
        resBeforeSections: Boolean(resRect && firstSecRect && resRect.bottom <= firstSecRect.top),
        sections,
        touchTargets,
        appText: app.innerText,
      };
    })()"""
    result = page.evaluate(script)
    assert isinstance(result, dict)
    return result


@pytest.mark.parametrize(
    ("locale", "viewport"),
    [("en", (412, 800)), ("ru", (412, 800)), ("ru", (360, 800))],
)
def test_home_overview_sections_dedup_cards_nav_and_mobile_geometry(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    locale: SupportedLocale,
    viewport: tuple[int, int],
) -> None:
    """Active Home renders deduplicated sections, scannable cards, and clean mobile geometry."""
    seeded = _seed_rich_overview(wishlist_server, locale)
    page = _open_home(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        wishlist_server.owner_token,
        locale,
        viewport=viewport,
    )
    assert_clean_console(page)
    assert page.external_requests == []

    data = _collect_layout_metrics(page)
    problems: list[str] = []
    if data["scrollWidth"] > data["innerWidth"]:
        problems.append(f"horizontal overflow: {data['scrollWidth']} > {data['innerWidth']}")
    if not data["leadText"]:
        problems.append("missing .home-lead subtitle")
    if data["navHasHomeClass"] is not True:
        problems.append("missing .home-top-nav class on .top-nav")
    if data["navButtonCount"] != 2:
        problems.append(f"expected 2 .top-nav buttons, got {data['navButtonCount']}")
    else:
        btn_styles = data["navButtonStyles"]
        if (btn_styles[0]["bg"], btn_styles[0]["color"]) == (
            btn_styles[1]["bg"],
            btn_styles[1]["color"],
        ):
            problems.append("Create and Viewing history buttons share identical visual style")
        if btn_styles[0]["top"] > btn_styles[1]["top"]:
            problems.append("Create button does not sit on top row above Viewing history")
    if data["settingsHref"] != "/settings" or data["settingsText"] != t("nav.settings", locale):
        problems.append("settings nav link contract mismatch")

    if not data["hasResCard"]:
        problems.append("missing a.reservations-card before wishlist sections")
    else:
        if not data["resBeforeSections"]:
            problems.append(".reservations-card is not placed before first .wishlist-section")
        if data["resTitle"] != t("web.reservations.title", locale):
            problems.append(f"unexpected .reservations-title: {data['resTitle']!r}")
        if not data["resHint"]:
            problems.append("missing .reservations-card-hint")
        if data["resBadge"] != "1":
            problems.append(f"expected reservations badge '1', got {data['resBadge']!r}")

    sections = data["sections"]
    if len(sections) != 3:
        problems.append(f"expected 3 direct .wishlist-section blocks, got {len(sections)}")
    else:
        modifiers = [
            ("wishlist-section--owned", "2"),
            ("wishlist-section--collab", "2"),
            ("wishlist-section--favorites", "1"),
        ]
        for sec, (mod, count) in zip(sections, modifiers, strict=True):
            if mod not in sec["classes"]:
                problems.append(f"missing section modifier {mod}")
            if not sec["hasHeader"]:
                problems.append(f"{mod}: missing .wishlist-section-header")
            if sec["countText"] != count:
                problems.append(f"{mod}: count {sec['countText']!r} != {count!r}")
            if not sec["subtitleText"]:
                problems.append(f"{mod}: missing .section-subtitle")
        if len({sec["borderLeft"] for sec in sections}) < 2:
            problems.append("sections lack distinct left border visual cues")

        owned_cards = sections[0]["cards"]
        collab_cards = sections[1]["cards"]
        fav_cards = sections[2]["cards"]
        role_badges = (
            ("Owner", "Admin", "Collaborator", "Favorite")
            if locale == "en"
            else ("Владелец", "Администратор", "Соавтор", "Избранное")
        )
        owner_badge, admin_badge, member_badge, fav_badge = role_badges
        if [c["title"] for c in owned_cards] != [
            seeded["long_title"],
            t("miniapp.common.untitled_wishlist", locale),
        ]:
            problems.append(f"unexpected owned card titles: {[c['title'] for c in owned_cards]}")
        if [c["badge"] for c in owned_cards] != [owner_badge, owner_badge]:
            problems.append(f"unexpected owned card badges: {[c['badge'] for c in owned_cards]}")
        if (
            not owned_cards
            or not owned_cards[0]["meta"]
            or (seeded["event_title"] not in owned_cards[0]["meta"])
        ):
            problems.append("owned card missing .wishlist-card-meta with event title")
        if [c["title"] for c in collab_cards] != ["Admin Shared List", "Member Collab List"]:
            problems.append(f"unexpected collab card titles: {[c['title'] for c in collab_cards]}")
        if [c["badge"] for c in collab_cards] != [admin_badge, member_badge]:
            problems.append(f"unexpected collab card badges: {[c['badge'] for c in collab_cards]}")
        if [c["title"] for c in fav_cards] != ["Pure Favorite List"]:
            problems.append(f"unexpected favorite card titles: {[c['title'] for c in fav_cards]}")
        if [c["badge"] for c in fav_cards] != [fav_badge]:
            problems.append(f"unexpected favorite card badges: {[c['badge'] for c in fav_cards]}")
        if "Admin Shared List" in sections[2]["text"] or (
            "Member Collab List" in sections[2]["text"]
        ):
            problems.append("collaborator-favorited list duplicated into Favorites")

        open_label = "Open" if locale == "en" else "Открыть"
        rm_label = "Remove from favorites" if locale == "en" else "Убрать из избранного"
        create_style = data["navButtonStyles"][0] if data["navButtonStyles"] else None
        for card in owned_cards + collab_cards + fav_cards:
            if card["titleInButton"]:
                problems.append("card title must not be rendered inside a button")
            if card["titleClipped"]:
                problems.append(f"clipped card title: {card['title']!r}")
            if card["hasOverlap"]:
                problems.append(f"overlapping elements inside card: {card['title']!r}")
            if card["outOfCard"]:
                problems.append(f"card element overflows card box: {card['title']!r}")
            if card["openText"] != open_label:
                problems.append(f"missing/invalid .wishlist-card-open label: {card['openText']!r}")
            if not card["openAria"] or not card["openAria"].startswith(open_label):
                problems.append(f"open aria-label violates Label in Name: {card['openAria']!r}")
            if card["openStyle"] is None or (
                create_style is not None
                and (card["openStyle"]["bg"], card["openStyle"]["color"])
                == (create_style["bg"], create_style["color"])
            ):
                problems.append("card open button should be visually distinct from .btn-primary")

        if fav_cards:
            fav_card = fav_cards[0]
            if fav_card["removeText"] != rm_label:
                problems.append(f"invalid remove label: {fav_card['removeText']!r}")
            if not fav_card["removeAria"] or not fav_card["removeAria"].startswith(rm_label):
                problems.append(f"remove aria-label mismatch: {fav_card['removeAria']!r}")
            if fav_card["removeDanger"]:
                problems.append("favorite removal must not use .btn-danger")
            if fav_card["removeStyle"] == fav_card["openStyle"]:
                problems.append("favorite removal is not visually subordinate to open")

    for forbidden in ("Viewer", "Reserved", "Забронировано", "Куплено", "Purchased"):
        if forbidden in data["appText"]:
            problems.append(f"Surprise invariant leak: {forbidden}")

    for target in data["touchTargets"]:
        if target["height"] < 44 or target["width"] < 44:
            problems.append(f"touch target < 44px: {target}")
        if target["left"] < 0 or target["right"] > data["innerWidth"] + 1:
            problems.append(f"control outside viewport: {target}")
        if target["scrollW"] > target["clientW"] + 2:
            problems.append(f"control text clipped: {target}")

    page.press_key("Tab")
    focus_state = page.evaluate(
        """(() => {
          const active = document.activeElement;
          const css = active ? getComputedStyle(active) : null;
          return {
            visible: Boolean(active && active.matches(':focus-visible')),
            outlineStyle: css ? css.outlineStyle : 'none',
            outlineWidth: css ? parseFloat(css.outlineWidth) : 0,
          };
        })()"""
    )
    if (
        not focus_state["visible"]
        or focus_state["outlineStyle"] == "none"
        or (focus_state["outlineWidth"] <= 0)
    ):
        problems.append(f"keyboard :focus-visible outline missing: {focus_state}")

    assert problems == [], problems


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_home_overview_empty_states_deleted_restore_and_single_step_navigation(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    locale: SupportedLocale,
) -> None:
    """Empty states guide next steps, nav destinations work in 1 step, and deleted restores."""
    _set_user_locale(
        wishlist_server, wishlist_server.owner_token, OWNER_TELEGRAM_ID, "Owner", locale
    )

    page = _open_home(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        wishlist_server.owner_token,
        locale,
        viewport=(412, 800),
    )
    assert_clean_console(page)

    empty_info = page.evaluate(
        """(() => {
          const sections = Array.from(document.querySelectorAll('#app > .wishlist-section'));
          return {
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
            hasDeleted: Boolean(document.querySelector('.deleted-section')),
            resBadge: document.querySelector('.reservations-badge')?.innerText.trim() || null,
            sections: sections.map(sec => {
              const es = sec.querySelector('.empty-state');
              const notice = sec.querySelector('.empty-notice');
              const hint = sec.querySelector('.empty-hint');
              const secBg = getComputedStyle(sec).backgroundColor;
              const esBg = es ? getComputedStyle(es).backgroundColor : null;
              const bg = esBg && esBg !== 'rgba(0, 0, 0, 0)' ? esBg : (es ? secBg : null);
              return {
                classes: Array.from(sec.classList),
                count: sec.querySelector('.section-count')?.innerText.trim() || null,
                hasEmptyState: Boolean(es),
                noticeText: notice ? notice.innerText.trim() : null,
                hintText: hint ? hint.innerText.trim() : null,
                isErrorAlert: Boolean(es && es.classList.contains('alert-error')),
                sectionBg: secBg,
                bg,
              };
            }),
          };
        })()"""
    )
    assert empty_info["scrollWidth"] <= empty_info["innerWidth"]
    assert empty_info["hasDeleted"] is False
    assert empty_info["resBadge"] == "0"
    assert len(empty_info["sections"]) == 3
    for sec in empty_info["sections"]:
        assert sec["count"] == "0"
        assert sec["hasEmptyState"] is True
        assert sec["noticeText"] and sec["hintText"]
        assert sec["isErrorAlert"] is False
        assert sec["sectionBg"] == "rgb(255, 255, 255)"
        bg = sec["bg"]
        assert isinstance(bg, str) and bg.startswith("rgb("), bg
        channels = [int(part.strip()) for part in bg[4:-1].split(",")]
        assert len(channels) == 3 and min(channels) >= 240, bg

    # Single-step nav: Viewing history -> Back -> Settings -> Home -> Reservations.
    page.click(".home-top-nav button.home-nav-action")
    hist_title = json.dumps(t("miniapp.history.title", locale))
    page.wait_for(
        "history screen", f"document.querySelector('#app h1')?.innerText === {hist_title}"
    )
    page.click("#app button")
    home_title = json.dumps(t("miniapp.home.title", locale))
    page.wait_for("back to home", f"document.querySelector('#app h1')?.innerText === {home_title}")

    page.click("a.settings-link")
    page.wait_for("settings page", "document.querySelector('#language-heading') !== null")

    page.navigate(f"{wishlist_server.base_url}/")
    page.wait_for(
        "home reloaded",
        f"document.querySelector('#app h1')?.innerText === {home_title} "
        "&& document.getElementById('status')?.innerText === ''",
    )
    page.click("a.reservations-card")
    page.wait_for(
        "reservations cabinet", "document.querySelector('#reservations-cabinet') !== null"
    )

    # startapp=create focuses Create wishlist without creating a list.
    create_page = _open_home(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        wishlist_server.owner_token,
        locale,
        query="startapp=create",
    )
    create_label = json.dumps(t("miniapp.home.create_wishlist", locale))
    create_page.wait_for(
        "create button focused",
        "document.activeElement?.tagName === 'BUTTON' "
        f"&& document.activeElement?.innerText === {create_label}",
    )
    with httpx.Client(
        base_url=wishlist_server.base_url,
        headers={"Authorization": f"Bearer {wishlist_server.owner_token}"},
        timeout=10,
    ) as api:
        assert api.get("/api/wishlists").json() == []

    # Conditional Recently deleted section + restore + /web/reservations/card 500 fallback.
    deleted_preload = """(() => {
      const origFetch = window.fetch.bind(window);
      let restored = false;
      window.fetch = async (url, opts) => {
        const path = new URL(url, location.href).pathname;
        const method = (opts?.method || 'GET').toUpperCase();
        if (path === '/api/wishlists/deleted') {
          const items = restored
            ? []
            : [{id: 901, name: 'Recoverable List', days_remaining: 5}];
          return new Response(
            JSON.stringify(items),
            {status: 200, headers: {'content-type': 'application/json'}}
          );
        }
        if (path === '/api/wishlists/901/restore-deleted' && method === 'POST') {
          restored = true;
          return new Response(
            JSON.stringify({id: 901, status: 'active'}),
            {status: 200, headers: {'content-type': 'application/json'}}
          );
        }
        if (path === '/api/wishlists' && method === 'GET' && restored) {
          return new Response(
            JSON.stringify([{id: 901, name: 'Recoverable List', role: 'owner'}]),
            {status: 200, headers: {'content-type': 'application/json'}}
          );
        }
        if (path === '/web/reservations/card') {
          return new Response('', {status: 500});
        }
        return origFetch(url, opts);
      };
    })();"""
    del_page = _open_home(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        wishlist_server.owner_token,
        locale,
        preload_script=deleted_preload,
    )
    assert_clean_console(del_page)
    del_state = del_page.evaluate(
        """(() => {
          const delSec = document.querySelector('#app > .deleted-section');
          const delBtn = delSec?.querySelector('.deleted-wishlist-card button');
          const resCard = document.querySelector('#app > a.reservations-card');
          return {
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
            activeSections: document.querySelectorAll('#app > .wishlist-section').length,
            hasResCard: Boolean(resCard),
            hasDeleted: Boolean(delSec && delSec.classList.contains('wishlist-section--deleted')),
            delCount: delSec?.querySelector('.section-count')?.innerText.trim() || null,
            hasSubtitle: Boolean(delSec?.querySelector('.section-subtitle')),
            delText: delSec?.innerText || '',
            restoreBtnHeight: delBtn ? delBtn.getBoundingClientRect().height : 0,
          };
        })()"""
    )
    assert del_state["scrollWidth"] <= del_state["innerWidth"]
    assert del_state["hasResCard"] is False
    assert del_state["activeSections"] == 4
    assert del_state["hasDeleted"] is True
    assert del_state["delCount"] == "1"
    assert del_state["hasSubtitle"] is True
    assert "Recoverable List" in del_state["delText"] and "5" in del_state["delText"]
    assert del_state["restoreBtnHeight"] >= 44

    scroll_to(del_page, ".deleted-wishlist-card button")
    del_page.click(".deleted-wishlist-card button")
    restored_status = json.dumps(t("miniapp.deleted.restored", locale))
    del_page.wait_for(
        "deleted wishlist restored",
        "document.querySelector('.deleted-section') === null "
        f"&& document.getElementById('status')?.innerText === {restored_status} "
        "&& document.querySelectorAll('.wishlist-section--owned .wishlist-card').length === 1",
    )
    assert_clean_console(del_page)


def test_home_overview_favorites_remove_and_open_wishlist_browser(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Remove from favorites drops bookmark only; Open navigates owned list detail."""
    _set_user_locale(wishlist_server, wishlist_server.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    _set_user_locale(
        wishlist_server, wishlist_server.viewer_token, VIEWER_TELEGRAM_ID, "Viewer", "en"
    )
    with httpx.Client(
        base_url=wishlist_server.base_url,
        headers={"Authorization": f"Bearer {wishlist_server.viewer_token}"},
        timeout=10,
    ) as viewer_api:
        wl_one = viewer_api.post("/api/wishlists", json={"name": "Friend Favorite One"})
        wl_one.raise_for_status()
        wl_two = viewer_api.post("/api/wishlists", json={"name": "Friend Favorite Two"})
        wl_two.raise_for_status()

    with httpx.Client(
        base_url=wishlist_server.base_url,
        headers={"Authorization": f"Bearer {wishlist_server.owner_token}"},
        timeout=10,
    ) as owner_api:
        owned_wl = owner_api.post("/api/wishlists", json={"name": "Owner Open Target"})
        owned_wl.raise_for_status()
        owner_api.get(
            f"/api/public/wishlists/{wl_one.json()['share_token']}/view"
        ).raise_for_status()
        owner_api.get(
            f"/api/public/wishlists/{wl_two.json()['share_token']}/view"
        ).raise_for_status()
        owner_api.post(f"/api/favorites/{wl_one.json()['id']}").raise_for_status()
        owner_api.post(f"/api/favorites/{wl_two.json()['id']}").raise_for_status()

    page = _open_home(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        wishlist_server.owner_token,
        "en",
    )
    assert_clean_console(page)

    assert page.evaluate(
        "document.querySelector('.wishlist-section--favorites .wishlist-card-remove') !== null"
    ), "Missing .wishlist-card-remove inside .wishlist-section--favorites"

    titles_before = page.evaluate(
        "Array.from(document.querySelectorAll("
        "'.wishlist-section--favorites .wishlist-card-title'), el => el.innerText.trim())"
    )
    assert set(titles_before) == {"Friend Favorite One", "Friend Favorite Two"}

    scroll_to(page, ".wishlist-section--favorites .wishlist-card-remove")
    page.click(".wishlist-section--favorites .wishlist-card-remove")
    page.wait_for(
        "favorite removed",
        "document.querySelectorAll('.wishlist-section--favorites .wishlist-card').length === 1",
    )
    remaining_title = page.evaluate(
        "document.querySelector('.wishlist-section--favorites .wishlist-card-title')"
        "?.innerText.trim()"
    )
    assert remaining_title in {"Friend Favorite One", "Friend Favorite Two"}
    assert remaining_title != titles_before[0]

    fav_open_btn = page.evaluate(
        """(() => {
          const btn = document.querySelector('.wishlist-section--favorites .wishlist-card-open');
          return btn
            ? {text: btn.innerText.trim(), aria: btn.getAttribute('aria-label') || ''}
            : null;
        })()"""
    )
    assert fav_open_btn is not None and fav_open_btn["text"] == "Open"
    assert fav_open_btn["aria"].startswith("Open") and remaining_title in fav_open_btn["aria"]

    # Confirm the viewer's lists still exist (bookmark removal did not delete the wishlist).
    with httpx.Client(
        base_url=wishlist_server.base_url,
        headers={"Authorization": f"Bearer {wishlist_server.viewer_token}"},
        timeout=10,
    ) as viewer_api:
        viewer_ids = {wl["id"] for wl in viewer_api.get("/api/wishlists").json()}
        assert {wl_one.json()["id"], wl_two.json()["id"]} <= viewer_ids

    scroll_to(page, ".wishlist-section--owned .wishlist-card-open")
    page.click(".wishlist-section--owned .wishlist-card-open")
    page.wait_for(
        "opened owned list detail",
        "document.querySelector('#app h1')?.innerText === 'Owner Open Target' "
        "&& document.getElementById('status')?.innerText === ''",
    )
    assert_clean_console(page)
