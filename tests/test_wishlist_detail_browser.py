"""Mobile layout of the wishlist detail workspace in both supported locales."""

from collections.abc import Callable
from typing import Literal

import pytest

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_helpers import Seeded
from tests.conftest import OWNER_TELEGRAM_ID, BrowserServer
from tests.test_home_overview_browser import _open_home, _set_user_locale

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("width", [360, 412])
def test_detail_mobile_order_and_touch_targets(
    locale: Literal["en", "ru"],
    width: int,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", locale)
    page = _open_home(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        seeded.owner_token,
        locale,
        viewport=(width, 800),
    )
    _mock_detail(page, seeded.wishlist_id)
    page.evaluate("""(() => {
      window.detail.description = 'Очень длинное описание вишлиста для проверки переноса текста '
        .repeat(3);
      window.detail.members[0].display_name = 'Очень длинное имя участника семейного вишлиста';
    })()""")
    page.click(".wishlist-card-open")
    page.wait_for(
        "wishlist detail", "document.querySelector('#app h1')?.innerText === 'Browser wishlist'"
    )
    result = page.evaluate("""(() => {
      const selectors = ['.wishlist-detail-header', '.list-wishes-section',
        '.list-settings-section', '.share-panel--public', '.list-members-section'];
      const regions = selectors.map(s => {
        const el = document.querySelector(s);
        return el ? el.getBoundingClientRect().top : null;
      });
      const controls = Array.from(document.querySelectorAll(
        '.wishlist-detail-header button, .list-settings-section button, '
        + '.share-panel--public button, .list-members-section button'
      ), el => ({text: el.innerText, height: el.getBoundingClientRect().height}));
      const groups = ['.form-actions', '.share-panel--public .share-panel-actions',
        '.share-panel--invite .share-panel-actions', '.member-row-actions'].map(selector => {
        const group = document.querySelector(selector);
        return group ? Array.from(group.querySelectorAll('button'), el => {
          const r = el.getBoundingClientRect();
          return {left: r.left, right: r.right, top: r.top, bottom: r.bottom};
        }) : null;
      });
      return {regions, controls, scrollWidth: document.documentElement.scrollWidth,
              innerWidth: window.innerWidth, groups};
    })()""")
    assert all(top is not None for top in result["regions"]), result
    assert result["regions"] == sorted(result["regions"]), result
    assert result["scrollWidth"] <= result["innerWidth"], result
    assert all(control["height"] >= 44 for control in result["controls"]), result
    assert all(group is not None and len(group) >= 2 for group in result["groups"]), result
    for group in result["groups"]:
        for index, first in enumerate(group):
            for second in group[index + 1 :]:
                assert (
                    first["right"] <= second["left"]
                    or second["right"] <= first["left"]
                    or first["bottom"] <= second["top"]
                    or second["bottom"] <= first["top"]
                ), (first, second)
    styles = page.evaluate("""(() => {
      const style = selector => {
        const s = getComputedStyle(document.querySelector(selector));
        return [s.color, s.backgroundColor, s.borderColor];
      };
      return {save: style('.settings-save-btn'), cancel: style('.settings-cancel-btn')};
    })()""")
    assert styles["save"] != styles["cancel"]


def _mock_detail(page: CdpPage, wishlist_id: int, *, role: str = "owner") -> None:
    """Intercept detail mutations while keeping Home and authentication on the local server."""
    page.evaluate(
        """(() => {
          const id = DETAIL_ID, role = DETAIL_ROLE, realFetch = window.fetch.bind(window);
          document.getElementById('app').dataset.bot = 'wishenka_bot';
          document.getElementById('app').dataset.miniapp = 'app';
          window.detailCalls = [];
          window.detailFail = false;
          window.detailGetFail = false;
          window.failRefreshAfterMutation = false;
          window.detail = {id, role, name: 'Browser wishlist', description: 'Original',
            event_title: null, event_date: null, status: 'active', is_favorite: false,
            share_token: 'public-token', invite_token: 'invite-token', items: [],
            members: [{user_id: 202, display_name: 'Collaborator', role: 'member'}]};
          window.fetch = async (url, options = {}) => {
            const path = new URL(url, location.href).pathname;
            const method = options.method || 'GET';
            const base = `/api/wishlists/${id}`;
            if (path === `/api/history/${id}`) return new Response('{}', {status: 200});
            if (path === base && method === 'GET' && window.detailGetFail)
              return new Response('{}', {status: 500});
            if (path === base && method === 'GET')
              return new Response(JSON.stringify(window.detail), {status: 200});
            if ((path.startsWith(base) || path === `/api/favorites/${id}`) && method !== 'GET') {
              window.detailCalls.push({path, method, body: options.body || ''});
              if (window.detailFail) return new Response('{}', {status: 500});
              if (path === base && method === 'PATCH') Object.assign(window.detail,
                JSON.parse(options.body));
              if (path.endsWith('/role')) window.detail.members[0].role =
                JSON.parse(options.body).role;
              if (path.endsWith('/members/202') && method === 'DELETE')
                window.detail.members = [];
              if (path.endsWith('/restore')) window.detail.status = 'active';
              if (path.startsWith('/api/favorites/')) window.detail.is_favorite = method === 'POST';
              if (window.failRefreshAfterMutation) window.detailGetFail = true;
              return new Response('{}', {status: 200});
            }
            return realFetch(url, options);
          };
          window.detailCopied = [];
          Object.defineProperty(navigator, 'clipboard', {configurable: true,
            value: {writeText: async text => window.detailCopied.push(text)}});
        })()""".replace("DETAIL_ID", str(wishlist_id)).replace("DETAIL_ROLE", repr(role))
    )


def _open_mock_detail(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    pages: list[CdpPage],
    *,
    role: str = "owner",
    archived: bool = False,
) -> CdpPage:
    seeded = seed_wishlist(["Camera"])
    page = _open_home(
        chromium_browser,
        pages,
        wishlist_server,
        seeded.owner_token,
        "en",
        preload_script="""window.detailShared = [];
          window.Telegram = {WebApp: {initData: '', ready() {}, expand() {},
            openTelegramLink(url) { window.detailShared.push(url); }}};""",
    )
    _mock_detail(page, seeded.wishlist_id, role=role)
    if archived:
        page.evaluate("window.detail.status = 'archived'")
    page.click(".wishlist-card-open")
    page.wait_for(
        "detail loaded", "document.querySelector('#app h1')?.innerText === 'Browser wishlist'"
    )
    return page


def _click_detail(page: CdpPage, selector: str) -> None:
    page.evaluate(f"document.querySelector({selector!r}).scrollIntoView({{block: 'center'}})")
    page.click(selector)


def test_detail_settings_save_cancel_and_error_retains_draft(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    page = _open_mock_detail(seed_wishlist, wishlist_server, chromium_browser, _browser_pages)
    page.wait_for("settings form", "!!document.querySelector('.wishlist-settings-form')")
    page.evaluate("document.querySelector('[name=name]').value = 'Draft'")
    _click_detail(page, ".settings-cancel-btn")
    page.wait_for(
        "cancel confirmation", "document.querySelector('#status').innerText === 'Changes discarded'"
    )
    assert page.evaluate("document.querySelector('[name=name]').value") == "Browser wishlist"
    page.evaluate("window.detailFail = true; document.querySelector('[name=name]').value = 'Draft'")
    _click_detail(page, ".settings-save-btn")
    page.wait_for(
        "save error", "document.querySelector('#status').innerText.startsWith('Could not save')"
    )
    assert page.evaluate("document.querySelector('[name=name]').value") == "Draft"
    page.evaluate("window.detailFail = false")
    _click_detail(page, ".settings-save-btn")
    page.wait_for(
        "save confirmation", "document.querySelector('#status').innerText === 'Settings saved'"
    )
    assert page.evaluate("document.querySelector('#app h1').innerText") == "Draft"
    assert page.evaluate("window.detailCalls.filter(c => c.method === 'PATCH').length") == 2


@pytest.mark.parametrize("action", ["cancel", "save"])
def test_settings_refresh_failure_preserves_draft_and_reports_outcome(
    action: str,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    page = _open_mock_detail(seed_wishlist, wishlist_server, chromium_browser, _browser_pages)
    page.evaluate(
        "window.detailGetFail = true; document.querySelector('[name=name]').value = 'Draft'"
    )
    _click_detail(page, f".settings-{action}-btn")
    expected = (
        "Could not load this wishlist"
        if action == "cancel"
        else "Settings saved, but the wishlist could not be refreshed"
    )
    page.wait_for(
        "refresh failure", f"document.querySelector('#status').innerText === {expected!r}"
    )
    assert page.evaluate("document.querySelector('[name=name]').value") == "Draft"
    assert page.evaluate("document.querySelector('#app h1').innerText") == "Browser wishlist"
    expected_name = "Draft" if action == "save" else "Browser wishlist"
    assert page.evaluate("window.detail.name") == expected_name
    assert page.evaluate("document.querySelector('.settings-save-btn').disabled") is False


def test_detail_links_and_member_actions_are_scoped(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    page = _open_mock_detail(seed_wishlist, wishlist_server, chromium_browser, _browser_pages)
    page.wait_for("sharing panels", "!!document.querySelector('.share-panel--invite')")
    assert page.evaluate("""(() => {
      const style = selector => {
        const s = getComputedStyle(document.querySelector(selector));
        return [s.color, s.backgroundColor, s.borderColor].join(',');
      };
      return style('.member-role-btn') !== style('.member-remove-btn');
    })()""")
    assert page.evaluate("""(() => {
      const pub = document.querySelector('.share-panel--public input');
      const invite = document.querySelector('.share-panel--invite input');
      return pub.readOnly && invite.readOnly && pub.value.includes('public-token') &&
        invite.value.includes('invite-token');
    })()""")
    _click_detail(page, ".share-panel--public .share-copy-btn")
    page.wait_for("public copied", "window.detailCopied.length === 1")
    assert "public-token" in page.evaluate("window.detailCopied[0]")
    _click_detail(page, ".share-panel--public .share-telegram-btn")
    page.wait_for("public shared", "window.detailShared.length === 1")
    assert "public-token" in page.evaluate("decodeURIComponent(window.detailShared[0])")
    _click_detail(page, ".share-panel--invite .share-copy-btn")
    page.wait_for("invitation copied", "window.detailCopied.length === 2")
    assert "invite-token" in page.evaluate("window.detailCopied[1]")
    _click_detail(page, ".share-panel--invite .share-telegram-btn")
    page.wait_for("invitation shared", "window.detailShared.length === 2")
    assert "invite-token" in page.evaluate("decodeURIComponent(window.detailShared[1])")
    _click_detail(page, ".share-reset-btn")
    page.wait_for("public reset", "window.detailCalls.some(c => c.path.endsWith('/share/reset'))")
    page.wait_for(
        "public reset feedback",
        "document.querySelector('#status').innerText === 'Old public link no longer works'",
    )
    page.wait_for("refreshed member row", "!!document.querySelector('.member-role-btn')")
    _click_detail(page, ".member-role-btn")
    page.wait_for("promoted", "window.detail.members[0].role === 'admin'")
    page.wait_for(
        "role feedback", "document.querySelector('#status').innerText === 'Member role updated'"
    )
    _click_detail(page, ".member-role-btn")
    page.wait_for("demoted", "window.detail.members[0].role === 'member'")
    page.wait_for("member restored", "!!document.querySelector('.member-remove-btn')")
    _click_detail(page, ".member-remove-btn")
    page.wait_for("removed", "window.detail.members.length === 0")
    page.wait_for(
        "member removal feedback",
        "document.querySelector('#status').innerText === 'Member removed'",
    )
    page.wait_for("invite panel restored", "!!document.querySelector('.invite-revoke-btn')")
    _click_detail(page, ".invite-revoke-btn")
    page.wait_for(
        "invite revoked", "window.detailCalls.some(c => c.path.endsWith('/invite/reset'))"
    )


def test_detail_non_owner_favorite(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    page = _open_mock_detail(
        seed_wishlist, wishlist_server, chromium_browser, _browser_pages, role="member"
    )
    page.wait_for("favorite", "!!document.querySelector('.list-favorite-btn')")
    assert not page.evaluate("!!document.querySelector('.list-settings-section')")
    _click_detail(page, ".list-favorite-btn")
    page.wait_for("favorite saved", "window.detail.is_favorite")


@pytest.mark.parametrize(
    ("selector", "role", "archived", "mutation_path"),
    [
        (".share-reset-btn", "owner", False, "/share/reset"),
        (".invite-revoke-btn", "owner", False, "/invite/reset"),
        (".member-role-btn", "owner", False, "/members/202/role"),
        (".member-remove-btn", "owner", False, "/members/202"),
        (".list-favorite-btn", "member", False, "/api/favorites/"),
        (".list-restore-btn", "owner", True, "/restore"),
    ],
)
def test_mutation_refresh_failure_hides_stale_controls_and_allows_retry(
    selector: str,
    role: str,
    archived: bool,
    mutation_path: str,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    page = _open_mock_detail(
        seed_wishlist,
        wishlist_server,
        chromium_browser,
        _browser_pages,
        role=role,
        archived=archived,
    )
    page.evaluate("window.failRefreshAfterMutation = true")
    _click_detail(page, selector)
    page.wait_for(
        "saved but refresh failed",
        "document.querySelector('#status').innerText === "
        "'Your change was saved, but the wishlist could not be refreshed'",
    )
    assert page.evaluate(f"window.detailCalls.some(c => c.path.includes({mutation_path!r}))")
    assert page.evaluate("!document.querySelector('.share-panel, .member-row, .list-favorite-btn')")
    assert page.evaluate("!document.querySelector('.list-restore-btn')")
    page.evaluate("window.detailGetFail = false; window.failRefreshAfterMutation = false")
    _click_detail(page, ".list-refresh-retry-btn")
    page.wait_for("reloaded", "document.querySelector('#app h1')?.innerText === 'Browser wishlist'")
    assert page.evaluate("document.querySelector('#status').innerText") == ""


def test_detail_archived_restore(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    page = _open_mock_detail(
        seed_wishlist, wishlist_server, chromium_browser, _browser_pages, archived=True
    )
    page.wait_for("restore control", "!!document.querySelector('.list-restore-btn')")
    assert not page.evaluate("!!document.querySelector('.list-settings-section')")
    _click_detail(page, ".list-restore-btn")
    page.wait_for("restored", "window.detail.status === 'active'")
    page.wait_for(
        "restore feedback", "document.querySelector('#status').innerText === 'Wishlist restored'"
    )
