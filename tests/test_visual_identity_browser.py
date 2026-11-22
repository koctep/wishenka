"""Shared visual action hierarchy across Mini App and server-rendered settings."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_helpers import Seeded, focus, js_str, open_receipt_dialog, settle
from tests.conftest import BrowserServer

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]


def _open(
    browser: CdpBrowser,
    pages: list[CdpPage],
    server: BrowserServer,
    token: str | None,
    path: str,
) -> CdpPage:
    """Open ``path`` in a mobile viewport with an optional session cookie."""
    page = browser.new_page((412, 800))
    pages.append(page)
    if token is not None:
        page.set_cookie("session_id", token, server.base_url)
    page.navigate(f"{server.base_url}{path}")
    return page


def test_both_shells_use_coherent_light_canvas_and_surfaces(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Both entry points retain a light canvas and a legible, distinct surface."""
    seeded = seed_wishlist(["Camera"])
    samples = []
    for path, selector in (("/", ".wishlist-section"), ("/settings", "#language-heading")):
        page = _open(chromium_browser, _browser_pages, wishlist_server, seeded.owner_token, path)
        page.wait_for(
            "representative surface",
            f"document.querySelector({js_str(selector)}) !== null",
        )
        samples.append(
            page.evaluate(
                """(selector => {
                  const color = el => getComputedStyle(el).backgroundColor;
                  const surface = document.querySelector(selector).closest('section');
                  const body = color(document.body);
                  return {canvas: body === 'rgba(0, 0, 0, 0)'
                    ? color(document.documentElement) : body, surface: color(surface)};
                })("""
                + js_str(selector)
                + ")"
            )
        )

    def rgb(color: str) -> tuple[int, int, int]:
        assert color.startswith("rgb("), f"Expected an opaque background, got {color}"
        channels = tuple(int(channel.strip()) for channel in color[4:-1].split(","))
        assert len(channels) == 3, color
        return channels[0], channels[1], channels[2]

    for sample in samples:
        canvas, surface = rgb(sample["canvas"]), rgb(sample["surface"])
        assert min(canvas) >= 225 and min(surface) >= 225, sample
        assert canvas != surface, f"Surface is indistinguishable from the canvas: {sample}"
    for role in ("canvas", "surface"):
        first, second = (rgb(sample[role]) for sample in samples)
        assert max(abs(a - b) for a, b in zip(first, second, strict=True)) <= 16, samples


def test_home_primary_action_is_visually_distinct_from_history(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """The create action is distinguishable from the secondary history action."""
    seeded = seed_wishlist(["Camera"])
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded.owner_token, "/")
    page.wait_for("home actions", "document.querySelectorAll('.top-nav button').length === 2")
    styles = page.evaluate(
        """Array.from(document.querySelectorAll('.top-nav button'), el => {
          const css = getComputedStyle(el);
          return {background: css.backgroundColor, color: css.color};
        })"""
    )
    assert styles[0] != styles[1], "Create and history have identical visual treatment"


def test_settings_actions_and_selection_have_distinct_visual_states(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Primary, secondary, destructive and selected settings actions are recognizable."""
    seeded = seed_wishlist(["Camera"])
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded.owner_token, "/settings")
    page.wait_for("settings controls", "document.querySelector('#birthdate-form button') !== null")
    styles = page.evaluate(
        """(() => {
          const style = (selector) => {
            const css = getComputedStyle(document.querySelector(selector));
            return {background: css.backgroundColor, color: css.color,
                    border: css.borderColor};
          };
          const clear = document.querySelector('#birthdate-clear-btn');
          const enabled = style('#birthdate-clear-btn');
          clear.disabled = true;
          const disabled = style('#birthdate-clear-btn');
          clear.disabled = false;
          return {
            enabled, disabled,
            save: style('#birthdate-form button[type=submit]'),
            clear: style('#birthdate-clear-btn'),
            danger: style('#delete-account-start-btn'),
            selected: style('.locale-option[aria-pressed=true]'),
            unselected: style('.locale-option[aria-pressed=false]')
          };
        })()"""
    )
    page.press_key("Tab")
    _assert_focus_visible(page)
    problems = []
    if styles["save"] == styles["clear"]:
        problems.append("save and clear look identical")
    if styles["danger"] == styles["clear"]:
        problems.append("delete and ordinary secondary actions look identical")
    if styles["selected"] == styles["unselected"]:
        problems.append("selected locale has no visual distinction")
    if styles["enabled"] == styles["disabled"]:
        problems.append("disabled action has no visual distinction")
    assert not problems, problems


_CONTRAST_JS = """
const rgb = (value) => value.match(/[\\d.]+/g).map(Number);
const luminance = (color) => color.slice(0, 3).map((v) => {
  v /= 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
const contrastRatio = (fgColor, bgColor) => {
  const fg = luminance(rgb(fgColor));
  const bg = luminance(rgb(bgColor));
  return (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
};
"""


def _assert_focus_visible(
    page: CdpPage,
    *,
    expected_selector: str | None = None,
    sheet_selector: str | None = None,
    min_contrast: float | None = None,
) -> None:
    """Assert the active element exposes a visible keyboard focus outline."""
    expected_js = js_str(expected_selector) if expected_selector is not None else "null"
    sheet_js = js_str(sheet_selector) if sheet_selector is not None else "null"
    state = page.evaluate(
        f"""(() => {{
          {_CONTRAST_JS}
          const active = document.activeElement;
          const css = active ? getComputedStyle(active) : null;
          const expectedSelector = {expected_js};
          const sheetSelector = {sheet_js};
          const expected = expectedSelector ? document.querySelector(expectedSelector) : null;
          const sheet = sheetSelector ? document.querySelector(sheetSelector) : null;
          return {{
            matchesExpected:
              expectedSelector === null || (expected !== null && active === expected),
            inSheet: sheetSelector === null || (sheet !== null && sheet.contains(active)),
            visible: !!active && active.matches(':focus-visible'),
            outlineStyle: css ? css.outlineStyle : 'none',
            outlineWidth: css ? parseFloat(css.outlineWidth) : 0,
            contrast: sheet && css
              ? contrastRatio(css.outlineColor, getComputedStyle(sheet).backgroundColor)
              : null,
          }};
        }})()"""
    )
    assert state["matchesExpected"] is True, state
    assert state["inSheet"] is True, state
    assert state["visible"] is True, state
    assert state["outlineStyle"] != "none" and state["outlineWidth"] > 0, state
    if min_contrast is not None:
        assert state["contrast"] is not None and state["contrast"] >= min_contrast, state


def _assert_sheet_heading_and_focus(
    page: CdpPage, sheet_selector: str, heading_selector: str, prefocus_selector: str
) -> None:
    """Assert readable heading and keyboard :focus-visible outline contrast in a modal sheet."""
    heading = page.evaluate(
        f"""(() => {{
          {_CONTRAST_JS}
          const sheet = document.querySelector({js_str(sheet_selector)});
          const title = document.querySelector({js_str(heading_selector)});
          const rect = title.getBoundingClientRect();
          return {{
            visible: rect.width > 0 && rect.height > 0,
            contrast: contrastRatio(getComputedStyle(title).color,
                                    getComputedStyle(sheet).backgroundColor),
          }};
        }})()"""
    )
    assert heading["visible"] and heading["contrast"] >= 4.5, heading

    focus(page, prefocus_selector)
    page.press_key("Tab")
    _assert_focus_visible(page, sheet_selector=sheet_selector, min_contrast=4.5)


def test_dark_theme_modal_heading_and_focus_outline_contrast(
    seed_wishlist: Callable[..., Seeded],
    wishlist_page: Callable[..., CdpPage],
) -> None:
    """Modal and receipt headings and :focus-visible outlines stay legible in light and dark."""
    seeded = seed_wishlist(["Kettle"], quantities=[2])
    for background, foreground in ((None, None), ("#202020", "#f5f5f5")):
        page = wishlist_page(seeded)
        if background is not None and foreground is not None:
            page.evaluate(
                "document.documentElement.style.setProperty("
                f"'--tg-theme-bg-color', '{background}');"
                "document.documentElement.style.setProperty("
                f"'--tg-theme-text-color', '{foreground}');"
            )

        archive_url = (
            f"/web/wishlists/{seeded.wishlist_id}/items/{seeded.item_ids[0]}/archive-confirm"
        )
        page.evaluate(
            f"void window.htmx.ajax('GET', {js_str(archive_url)},"
            " {target: '#item-modal-container', swap: 'innerHTML'})"
        )
        settle(page)
        page.wait_for(
            "archive modal opened",
            "!!document.querySelector('#item-archive-modal .modal-sheet h2')",
        )
        _assert_sheet_heading_and_focus(
            page,
            "#item-archive-modal .modal-sheet",
            "#item-archive-modal .modal-sheet h2",
            "#item-archive-modal input[type='checkbox']",
        )

        page.click("#item-archive-modal .btn-modal-close")
        page.wait_for("archive modal closed", "!document.querySelector('#item-archive-modal')")

        open_receipt_dialog(page, seeded, seeded.item_ids[0])
        _assert_sheet_heading_and_focus(
            page,
            "#item-receipt-modal .receipt-sheet",
            "#item-receipt-modal .receipt-sheet h2",
            "#receipt-quantity",
        )


def test_invite_preview_primary_link_has_button_geometry_and_touch_target(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Anchor .btn.btn-primary on invite_preview renders as a 44px+ button without underline."""
    page = _open(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        None,
        "/invite/nonexistent-invite-token",
    )
    page.wait_for("invite error link", "document.querySelector('a.btn.btn-primary') !== null")

    metrics = page.evaluate(
        f"""(() => {{
          {_CONTRAST_JS}
          const link = document.querySelector('a.btn.btn-primary');
          const rect = link.getBoundingClientRect();
          const css = getComputedStyle(link);
          return {{
            width: rect.width,
            height: rect.height,
            display: css.display,
            alignItems: css.alignItems,
            justifyContent: css.justifyContent,
            boxSizing: css.boxSizing,
            textDecorationLine: css.textDecorationLine,
            paddingTop: parseFloat(css.paddingTop),
            paddingBottom: parseFloat(css.paddingBottom),
            paddingLeft: parseFloat(css.paddingLeft),
            paddingRight: parseFloat(css.paddingRight),
            borderWidth: parseFloat(css.borderTopWidth),
            borderStyle: css.borderTopStyle,
            borderRadius: parseFloat(css.borderTopLeftRadius),
            fontWeight: Number(css.fontWeight),
            contrast: contrastRatio(css.color, css.backgroundColor),
          }};
        }})()"""
    )
    assert metrics["height"] >= 44 and metrics["width"] >= 44, metrics
    assert metrics["display"] == "inline-flex", metrics
    assert metrics["alignItems"] == "center" and metrics["justifyContent"] == "center", metrics
    assert metrics["boxSizing"] == "border-box", metrics
    assert metrics["textDecorationLine"] == "none", metrics
    assert metrics["paddingTop"] > 0 and metrics["paddingBottom"] > 0, metrics
    assert metrics["paddingLeft"] > 0 and metrics["paddingRight"] > 0, metrics
    assert metrics["borderWidth"] >= 1 and metrics["borderStyle"] == "solid", metrics
    assert metrics["borderRadius"] > 0, metrics
    assert metrics["fontWeight"] >= 600, metrics
    assert metrics["contrast"] >= 4.5, metrics

    page.press_key("Tab")
    _assert_focus_visible(page, expected_selector="a.btn.btn-primary")
