"""Browser repro for WISHENKA-307: settings switches must look and behave like switches.

The five switches of the personal settings page (birthday reminder plus four notification
categories) are native checkboxes that look like default browser controls. These tests assert
the desired design (switch role, skinned track and thumb, distinct pending / unknown / disabled
looks, forced-colors and reduced-motion support). Pseudo-element reads run under emulated
``prefers-reduced-motion: reduce`` so a transition never leaves a half-moved thumb.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Literal

import pytest

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_helpers import Seeded, scroll_to
from tests.browser_screens import provision_user
from tests.conftest import OWNER_TELEGRAM_ID, BrowserServer
from tests.test_personal_settings_browser import _api, _click, _intercept, _open
from wishenka.i18n import t

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

GLOBAL_PATH = "/api/profile/notifications/global"
SWITCH = "input[data-global-category]"
REMINDERS = 'input[data-global-category="reminders"]'
CATEGORIES = ["wishlist_changes", "reservation_changes", "gift_received", "reminders"]
CASES = [("en", 320), ("en", 375), ("ru", 320), ("ru", 375)]
STATE_CASES = [("en", 375), ("ru", 320)]
LONG_RU_LABEL = (
    "Очень длинное название категории уведомлений для проверки переноса текста "
    "в строке переключателя на узком экране"
)
TRACK_BORDER_MIN_CONTRAST = 3.0

OpenSettings = Callable[..., CdpPage]

# JS library: reads everything the assertions need from one switch (or any probe checkbox).
_JS_LIB = """
const PSEUDO = (el, kind) => {
  const s = getComputedStyle(el, kind);
  return {
    content: s.content, width: s.width, height: s.height, left: s.left,
    radius: s.borderTopLeftRadius, bg: s.backgroundColor, color: s.color,
    bStyle: s.borderTopStyle, bColor: s.borderTopColor,
    td: s.transitionDuration, tp: s.transitionProperty,
  };
};
const readSwitch = (el) => {
  const s = getComputedStyle(el);
  return {
    cat: el.dataset.globalCategory || '', role: el.getAttribute('role'),
    appearance: s.appearance, ariaBusy: el.getAttribute('aria-busy'),
    disabled: el.disabled, unknown: el.dataset.unknown || null, checked: el.checked,
    boxW: el.offsetWidth, boxH: el.offsetHeight, opacity: s.opacity, cursor: s.cursor,
    before: PSEUDO(el, '::before'), after: PSEUDO(el, '::after'),
  };
};
const token = (name) => {
  const probe = document.createElement('i');
  probe.style.color = `var(--${name})`;
  document.body.append(probe);
  const value = getComputedStyle(probe).color;
  probe.remove();
  return value;
};
const TOKENS = Object.fromEntries(
  ['accent', 'surface', 'surface-subtle', 'muted', 'danger', 'focus'].map(n => [n, token(n)]));
"""


def _run(page: CdpPage, body: str) -> Any:
    """Evaluate ``body`` (a JS function body) with the reading library in scope."""
    return page.evaluate("(() => {" + _JS_LIB + body + "})()")


def _emulate(page: CdpPage, motion: str = "reduce", colors: str = "none") -> None:
    """Emulate ``prefers-reduced-motion`` and ``forced-colors`` (replaces earlier emulation)."""
    page._send(  # noqa: SLF001 -- shared CDP transport; no public media-emulation wrapper
        "Emulation.setEmulatedMedia",
        {
            "features": [
                {"name": "prefers-reduced-motion", "value": motion},
                {"name": "forced-colors", "value": colors},
            ]
        },
    )


def _switches(page: CdpPage) -> list[dict[str, Any]]:
    result = _run(
        page, f"return [...document.querySelectorAll({json.dumps(SWITCH)})].map(readSwitch);"
    )
    assert isinstance(result, list) and len(result) == 5, f"expected 5 switches, got {result!r}"
    return result


def _tokens(page: CdpPage) -> dict[str, str]:
    result: dict[str, str] = _run(page, "return TOKENS;")
    return result


def _px(value: str | None) -> float | None:
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)px", (value or "").strip())
    return float(match.group(1)) if match else None


def _is_pill(radius: str, height: float | None) -> bool:
    if radius.endswith("%"):
        return float(radius[:-1]) >= 50
    px = _px(radius)
    return px is not None and height is not None and px >= height / 2


def _rgb(value: str) -> tuple[float, float, float] | None:
    match = re.fullmatch(r"rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)", value.strip())
    if not match or (match.group(4) is not None and float(match.group(4)) == 0):
        return None
    return float(match.group(1)), float(match.group(2)), float(match.group(3))


def _luminance(color: tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(first: str, second: str) -> float | None:
    a, b = _rgb(first), _rgb(second)
    if a is None or b is None:
        return None
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _label(sw: dict[str, Any]) -> str:
    return f"switch {sw['cat']} (checked={sw['checked']})"


def _expected(problems: list[str], page: CdpPage, what: str) -> None:
    assert not problems, f"{what}:\n" + "\n".join(problems) + f"\n{page.snapshot()}"


@pytest.fixture
def open_settings(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> OpenSettings:
    """Open /settings for a fresh owner; ``reminders`` presets the stored category value."""

    def open_page(
        locale: Literal["en", "ru"] = "en",
        width: int = 375,
        reminders: bool | None = None,
    ) -> CdpPage:
        seeded = seed_wishlist(["Camera"])
        provision_user(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", locale)
        if reminders is not None:
            _api(
                wishlist_server,
                seeded,
                "PUT",
                GLOBAL_PATH,
                json={"settings": {"reminders": reminders}},
            )
        return _open(chromium_browser, _browser_pages, wishlist_server, seeded, width)

    return open_page


def _settle(page: CdpPage, selector: str) -> None:
    page.wait_for("save finished", f"!document.querySelector({json.dumps(selector)}).disabled")


# --- harness controls -------------------------------------------------------------------------


def test_harness_reads_known_element_and_emulation_works(open_settings: OpenSettings) -> None:
    """Positive control: the readers see a known pseudo-element and the AX tree and emulation."""
    page = open_settings()
    _emulate(page, "reduce", "active")
    assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
    assert page.evaluate("matchMedia('(forced-colors: active)').matches")
    _emulate(page, "no-preference", "none")
    assert not page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
    probe = _run(
        page,
        """
        const style = document.createElement('style');
        style.textContent = '#probe{position:relative;width:52px;height:44px}' +
          '#probe::before{content:"?";position:absolute;width:30px;height:20px;' +
          'border:2px dashed rgb(1, 2, 3);border-radius:999px;background:rgb(9, 8, 7)}';
        const box = document.createElement('input');
        box.type = 'checkbox'; box.id = 'probe';
        document.head.append(style); document.body.append(box);
        return readSwitch(box);
        """,
    )
    before = probe["before"]
    assert (before["content"], before["width"], before["bStyle"]) == ('"?"', "30px", "dashed")
    assert (before["bColor"], before["bg"]) == ("rgb(1, 2, 3)", "rgb(9, 8, 7)")
    tokens = _tokens(page)
    assert all(_rgb(value) for value in tokens.values()), f"tokens must resolve: {tokens}"
    switches = _switches(page)
    assert [sw["cat"] for sw in switches] == ["birthday_reminders", *CATEGORIES]
    nodes = page._send("Accessibility.getFullAXTree")["nodes"]  # noqa: SLF001
    controls = [
        n
        for n in nodes
        if not n.get("ignored") and n.get("role", {}).get("value") in {"checkbox", "switch"}
    ]
    assert len(controls) >= 5, "AX tree must expose the five settings controls"
    checked = [p for n in controls for p in n.get("properties", []) if p.get("name") == "checked"]
    assert len(checked) >= 5, "AX tree controls must carry the checked property"


# --- R1, R2 -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("locale", "width"), CASES)
def test_switches_have_switch_role(
    locale: Literal["en", "ru"], width: int, open_settings: OpenSettings
) -> None:
    page = open_settings(locale, width)
    problems = [
        f"{_label(sw)}: role={sw['role']!r}, expected 'switch'"
        for sw in _switches(page)
        if sw["role"] != "switch"
    ]
    _expected(problems, page, "R1 every settings switch must have role=switch")


@pytest.mark.parametrize(("locale", "width"), CASES)
def test_switches_are_not_native_looking(
    locale: Literal["en", "ru"], width: int, open_settings: OpenSettings
) -> None:
    page = open_settings(locale, width)
    problems = [
        f"{_label(sw)}: appearance={sw['appearance']!r}, expected 'none'"
        for sw in _switches(page)
        if sw["appearance"] != "none"
    ]
    _expected(problems, page, "R2 switches must not use the native checkbox look")


# --- R3, R4 -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("locale", "width"), STATE_CASES)
def test_track_and_thumb_geometry(
    locale: Literal["en", "ru"], width: int, open_settings: OpenSettings
) -> None:
    page = open_settings(locale, width)
    _emulate(page)
    problems: list[str] = []
    for sw in _switches(page):
        name, track, thumb = _label(sw), sw["before"], sw["after"]
        t_w, t_h = _px(track["width"]), _px(track["height"])
        if t_w is None or t_h is None:
            problems.append(f"{name}: no track box (::before width={track['width']!r})")
            continue
        if not 44 <= t_w <= 64 or not 24 <= t_h <= 36:
            problems.append(f"{name}: track {t_w}x{t_h}px outside 44-64 x 24-36")
        if not _is_pill(track["radius"], t_h):
            problems.append(f"{name}: track radius {track['radius']!r} is not a pill")
        d_w, d_h = _px(thumb["width"]), _px(thumb["height"])
        if d_w is None or d_h is None:
            problems.append(f"{name}: no thumb box (::after width={thumb['width']!r})")
            continue
        if d_w != d_h or not _is_pill(thumb["radius"], d_h):
            problems.append(f"{name}: thumb {d_w}x{d_h}px radius {thumb['radius']!r} not a circle")
        if d_w < 18 or d_w >= t_h:
            problems.append(f"{name}: thumb {d_w}px must be >= 18 and below track height {t_h}")
    _expected(problems, page, "R3 switch must draw a pill track and a round thumb")


@pytest.mark.parametrize(("locale", "width"), STATE_CASES)
def test_state_shown_by_thumb_position_and_colour(
    locale: Literal["en", "ru"], width: int, open_settings: OpenSettings
) -> None:
    page = open_settings(locale, width)
    _emulate(page)
    tokens = _tokens(page)
    problems: list[str] = []
    for index in range(5):
        reads = {}
        for value in (False, True):
            reads[value] = _run(
                page,
                f"""
                const el = document.querySelectorAll({json.dumps(SWITCH)})[{index}];
                el.checked = {json.dumps(value)};
                return readSwitch(el);
                """,
            )
        off, on = reads[False], reads[True]
        name = f"switch {off['cat']}"
        centres: dict[bool, float | None] = {}
        for value, sw in ((False, off), (True, on)):
            left, width_px = _px(sw["after"]["left"]), _px(sw["after"]["width"])
            centres[value] = None if left is None or width_px is None else left + width_px / 2
        if centres[False] is None or centres[True] is None:
            problems.append(f"{name}: thumb has no measurable position")
        else:
            middle = off["boxW"] / 2
            if not centres[False] < middle < centres[True]:
                problems.append(
                    f"{name}: thumb centres off={centres[False]} on={centres[True]}, "
                    f"expected left / right of {middle}"
                )
        if off["before"]["bg"] == on["before"]["bg"]:
            problems.append(f"{name}: track colour does not change ({on['before']['bg']})")
        if on["before"]["bg"] != tokens["accent"]:
            problems.append(f"{name}: checked track {on['before']['bg']} != accent")
        pairs = [
            ("off thumb/track", off["after"]["bg"], off["before"]["bg"]),
            ("on thumb/track", on["after"]["bg"], on["before"]["bg"]),
            ("off track border/surface", off["before"]["bColor"], tokens["surface"]),
            ("on track border/surface", on["before"]["bColor"], tokens["surface"]),
        ]
        for what, first, second in pairs:
            ratio = _contrast(first, second)
            if ratio is None or ratio < TRACK_BORDER_MIN_CONTRAST:
                problems.append(f"{name}: {what} contrast {ratio} < 3:1 ({first} vs {second})")
    _expected(problems, page, "R4 state must show by thumb position, colour and 3:1 contrast")


# --- R5, R6 (regression guards) ---------------------------------------------------------------


@pytest.mark.parametrize(("locale", "width"), CASES)
def test_switch_target_is_large_and_label_text_toggles(
    locale: Literal["en", "ru"], width: int, open_settings: OpenSettings
) -> None:
    page = open_settings(locale, width)
    problems = [
        f"{_label(sw)}: input box {sw['boxW']}x{sw['boxH']}px below 44"
        for sw in _switches(page)
        if sw["boxW"] < 44 or sw["boxH"] < 44
    ]
    rows = page.evaluate(
        """[...document.querySelectorAll('label.toggle-row')].map(l => {
          const r = l.getBoundingClientRect();
          return {h: r.height, left: r.left, right: r.right, vw: innerWidth};
        })"""
    )
    problems += [
        f"row {i}: {row}"
        for i, row in enumerate(rows)
        if row["h"] < 44 or row["left"] < 0 or row["right"] > row["vw"] + 0.5
    ]
    assert len(rows) == 5, f"expected 5 toggle rows, got {len(rows)}"
    label = f"label.toggle-row:has({REMINDERS}) .toggle-label"
    before = page.evaluate(
        f"[...document.querySelectorAll({json.dumps(SWITCH)})].map(e => e.checked)"
    )
    scroll_to(page, label)
    page.click(label)
    page.wait_for(
        "label text click toggled reminders",
        f"document.querySelector({json.dumps(REMINDERS)}).checked !== "
        f"{json.dumps(before[CATEGORIES.index('reminders') + 1])}",
    )
    after = page.evaluate(
        f"[...document.querySelectorAll({json.dumps(SWITCH)})].map(e => e.checked)"
    )
    changed = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
    if changed != [CATEGORIES.index("reminders") + 1]:
        problems.append(f"label click changed switches {changed}, expected only the reminders")
    _settle(page, REMINDERS)
    _expected(problems, page, "R5 target size, row fit and label-text click")


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_switch_focus_ring_and_space_toggle(
    locale: Literal["en", "ru"], open_settings: OpenSettings
) -> None:
    page = open_settings(locale)
    for _ in range(40):
        page.press_key("Tab")
        if page.evaluate(f"document.activeElement.matches({json.dumps(SWITCH)})"):
            break
    else:
        pytest.fail("Tab never reached a settings switch within 40 presses")
    tokens = _tokens(page)
    ring = _run(
        page,
        """
        const s = getComputedStyle(document.activeElement);
        return {style: s.outlineStyle, width: s.outlineWidth, color: s.outlineColor,
                offset: s.outlineOffset, id: document.activeElement.dataset.globalCategory};
        """,
    )
    problems = []
    if ring["style"] == "none" or (_px(ring["width"]) or 0) < 2:
        problems.append(f"focus outline {ring['style']} {ring['width']} is not visible")
    if ring["color"] != tokens["focus"]:
        problems.append(f"outline colour {ring['color']} != --focus {tokens['focus']}")
    if ring["offset"] != "3px":
        problems.append(f"outline offset {ring['offset']!r}, expected the global '3px'")
    selector = f'input[data-global-category="{ring["id"]}"]'
    was = page.evaluate(f"document.querySelector({json.dumps(selector)}).checked")
    page.press_key("Space")
    now = page.evaluate(f"document.querySelector({json.dumps(selector)}).checked")
    if now == was:
        problems.append("Space did not toggle the focused switch")
    _settle(page, selector)
    _expected(problems, page, "R6 keyboard focus ring and Space toggle")


# --- R7 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(("locale", "width"), CASES)
def test_switch_announced_once_with_name_of_what_it_controls(
    locale: Literal["en", "ru"], width: int, open_settings: OpenSettings
) -> None:
    page = open_settings(locale, width)
    dom = page.evaluate(
        f"""[...document.querySelectorAll({json.dumps(SWITCH)})].map(el => {{
          const state = el.closest('label').querySelector('.toggle-state');
          return {{cat: el.dataset.globalCategory, checked: el.checked,
                   hidden: state.getAttribute('aria-hidden'),
                   stateText: state.textContent.trim()}};
        }})"""
    )
    nodes = page._send("Accessibility.getFullAXTree")["nodes"]  # noqa: SLF001
    found = [
        n
        for n in nodes
        if n.get("role", {}).get("value") == "switch" and not n.get("ignored", False)
    ]
    problems: list[str] = []
    if len(found) != 5:
        roles = sorted(
            {n.get("role", {}).get("value") for n in nodes if not n.get("ignored", False)},
            key=str,
        )
        problems.append(f"AX tree has {len(found)} switch nodes, expected 5 (roles: {roles})")
    for item, node in zip(dom, found, strict=False):
        key = (
            "settings.birthday_reminders_label"
            if item["cat"] == "birthday_reminders"
            else f"settings.category.{item['cat']}"
        )
        name = node.get("name", {}).get("value")
        if name != t(key, locale):
            problems.append(f"{item['cat']}: AX name {name!r} != {t(key, locale)!r}")
        props = {
            p.get("name"): (p.get("value") or {}).get("value") for p in node.get("properties", [])
        }
        if props.get("checked") != str(item["checked"]).lower():
            problems.append(f"{item['cat']}: AX checked {props.get('checked')!r} != DOM")
    for item in dom:
        expected = t(
            "settings.state.enabled" if item["checked"] else "settings.state.disabled", locale
        )
        if item["hidden"] != "true":
            problems.append(f"{item['cat']}: state text aria-hidden={item['hidden']!r}")
        if item["stateText"] != expected:
            problems.append(f"{item['cat']}: state text {item['stateText']!r} != {expected!r}")
    _expected(problems, page, "R7 accessible name, switch role, state announced once")


# --- R8 ---------------------------------------------------------------------------------------

_SIGNATURE = """
const el = document.querySelector(%s);
return {sw: readSwitch(el), tokens: TOKENS};
"""

_PENDING_OVERRIDE = """(() => {
  const real = window.fetch.bind(window); window.globalPending = false;
  window.fetch = async (input, options = {}) => {
    if (new URL(input, location.href).pathname === '/api/profile/notifications/global') {
      window.globalPending = true;
      await new Promise(resolve => { window.releaseGlobal = resolve; });
    }
    return real(input, options);
  };
})()"""


def _signature(page: CdpPage, selector: str = REMINDERS) -> dict[str, Any]:
    result: dict[str, Any] = _run(page, _SIGNATURE % json.dumps(selector))
    return result


def _reach_pending(page: CdpPage) -> dict[str, Any]:
    """Start a held global save; the caller must call ``window.releaseGlobal()`` afterwards."""
    _emulate(page)
    page.evaluate(_PENDING_OVERRIDE)
    _click(page, REMINDERS)
    page.wait_for(
        "pending request held",
        f"window.globalPending && document.querySelector({json.dumps(REMINDERS)}).disabled",
    )
    return _signature(page)


def _release(page: CdpPage) -> None:
    page.evaluate("window.releaseGlobal && window.releaseGlobal()")


def _reach_unknown(page: CdpPage) -> dict[str, Any]:
    _emulate(page)
    _intercept(page, GLOBAL_PATH, "commit", fail_read=True)
    _click(page, REMINDERS)
    page.wait_for(
        "unknown state settled",
        f"""(() => {{
          const el = document.querySelector({json.dumps(REMINDERS)});
          const note = document.getElementById('global-notifications-feedback-pending');
          return el.dataset.unknown === '1' && !el.hasAttribute('aria-busy') && el.disabled &&
            !!note && note.hidden;
        }})()""",
    )
    return _signature(page)


def _make_disabled(page: CdpPage) -> dict[str, Any]:
    _emulate(page)
    page.evaluate(f"document.querySelector({json.dumps(REMINDERS)}).disabled = true")
    return _signature(page)


def _glyph(sw: dict[str, Any]) -> str:
    return str(sw["after"]["content"])


def _centred(sw: dict[str, Any]) -> bool:
    left, width = _px(sw["after"]["left"]), _px(sw["after"]["width"])
    return left is not None and width is not None and abs(left + width / 2 - sw["boxW"] / 2) <= 1


@pytest.mark.parametrize("initial", [True, False])
def test_pending_switch_look(initial: bool, open_settings: OpenSettings) -> None:
    page = open_settings("en", 375, reminders=initial)
    sig = _reach_pending(page)
    try:
        sw, tokens = sig["sw"], sig["tokens"]
        assert sw["checked"] is (not initial), "control: the click must flip the switch"
        problems = []
        if sw["ariaBusy"] != "true":
            problems.append(f"aria-busy={sw['ariaBusy']!r}, expected 'true'")
        if not sw["disabled"]:
            problems.append("pending switch must be disabled")
        if sw["before"]["bStyle"] != "dashed":
            problems.append(f"track border style {sw['before']['bStyle']!r}, expected dashed")
        if sw["before"]["bColor"] != tokens["accent"]:
            problems.append(f"track border {sw['before']['bColor']} != accent")
        if sw["before"]["bg"] != tokens["surface-subtle"] or sw["before"]["bg"] == tokens["accent"]:
            problems.append(f"track bg {sw['before']['bg']} must be surface-subtle, not accent")
        if sw["opacity"] != "1":
            problems.append(f"opacity {sw['opacity']!r}, expected '1'")
        if sw["cursor"] != "progress":
            problems.append(f"cursor {sw['cursor']!r}, expected 'progress'")
        if "…" not in _glyph(sw):
            problems.append(f"thumb glyph {_glyph(sw)!r} lacks the ellipsis")
        _expected(problems, page, f"R8 pending look (checked={sw['checked']})")
    finally:
        _release(page)


def test_unknown_switch_look(open_settings: OpenSettings) -> None:
    page = open_settings("en", 375, reminders=False)
    sig = _reach_unknown(page)
    sw, tokens = sig["sw"], sig["tokens"]
    problems = []
    if not sw["disabled"] or sw["unknown"] != "1":
        problems.append(f"control: disabled={sw['disabled']} unknown={sw['unknown']!r}")
    if sw["before"]["bStyle"] != "solid":
        problems.append(f"track border style {sw['before']['bStyle']!r}, expected solid")
    if sw["before"]["bColor"] != tokens["danger"]:
        problems.append(f"track border {sw['before']['bColor']} != danger")
    if sw["before"]["bg"] != tokens["surface-subtle"] or sw["before"]["bg"] == tokens["accent"]:
        problems.append(f"track bg {sw['before']['bg']} must be surface-subtle, not accent")
    if sw["opacity"] != "1":
        problems.append(f"opacity {sw['opacity']!r}, expected '1'")
    if sw["cursor"] != "not-allowed":
        problems.append(f"cursor {sw['cursor']!r}, expected 'not-allowed'")
    if "?" not in _glyph(sw):
        problems.append(f"thumb glyph {_glyph(sw)!r} lacks '?'")
    if not _centred(sw):
        problems.append(f"thumb not centred: left={sw['after']['left']} box={sw['boxW']}")
    _expected(problems, page, "R8 unknown look")
    page.evaluate(
        f"document.querySelector({json.dumps(REMINDERS)}).setAttribute('aria-busy', 'true')"
    )
    busy = _signature(page)["sw"]
    problems = []
    if not _centred(busy):
        problems.append("unknown+busy thumb must stay centred")
    if busy["before"]["bStyle"] != "dashed":
        problems.append(f"unknown+busy border {busy['before']['bStyle']!r}, expected dashed")
    if "…" not in _glyph(busy):
        problems.append(f"unknown+busy glyph {_glyph(busy)!r} must be the ellipsis")
    _expected(problems, page, "R8 unknown plus busy (retry) look")


def test_plain_disabled_switch_look(open_settings: OpenSettings) -> None:
    page = open_settings("en", 375, reminders=False)
    sw = _make_disabled(page)["sw"]
    control = [f"control: {k}={sw[k]!r}" for k in ("ariaBusy", "unknown") if sw[k] is not None] + (
        ["control: not disabled or checked"] if not sw["disabled"] or sw["checked"] else []
    )
    problems = control
    if float(sw["opacity"]) >= 1:
        problems.append(f"opacity {sw['opacity']!r}, expected below 1")
    if sw["cursor"] != "not-allowed":
        problems.append(f"cursor {sw['cursor']!r}, expected 'not-allowed'")
    if _glyph(sw) != '""':
        problems.append(f"thumb content {_glyph(sw)!r}, expected the empty string '\"\"'")
    _expected(problems, page, "R8 plain disabled look")


def test_pending_unknown_and_disabled_are_distinguishable(open_settings: OpenSettings) -> None:
    pending_page = open_settings("en", 375, reminders=False)
    try:
        pending = _reach_pending(pending_page)
    finally:
        _release(pending_page)
    unknown = _reach_unknown(open_settings("en", 375, reminders=False))
    disabled = _make_disabled(open_settings("en", 375, reminders=False))
    tokens = disabled["tokens"]
    p, u, d = pending["sw"], unknown["sw"], disabled["sw"]
    problems = []
    for other, name in ((u, "unknown"), (d, "disabled")):
        if p["before"]["bStyle"] == other["before"]["bStyle"]:
            problems.append(f"pending and {name} share border style {p['before']['bStyle']!r}")
        if _glyph(p) == _glyph(other):
            problems.append(f"pending and {name} share glyph {_glyph(p)!r}")
        if p["cursor"] == other["cursor"]:
            problems.append(f"pending and {name} share cursor {p['cursor']!r}")
    if _glyph(u) == _glyph(d):
        problems.append(f"unknown and disabled share glyph {_glyph(u)!r}")
    if u["opacity"] == d["opacity"]:
        problems.append(f"unknown and disabled share opacity {u['opacity']!r}")
    if u["before"]["bColor"] != tokens["danger"] or d["before"]["bColor"] != tokens["muted"]:
        problems.append(
            f"track borders unknown={u['before']['bColor']} disabled={d['before']['bColor']}, "
            f"expected danger {tokens['danger']} / muted {tokens['muted']}"
        )
    _expected(problems, pending_page, "R8 states must differ from each other")


# --- R9 (regression guard) --------------------------------------------------------------------


@pytest.mark.parametrize("width", [320, 360, 375])
def test_switch_rows_do_not_overflow_with_long_label(
    width: int, open_settings: OpenSettings
) -> None:
    page = open_settings("ru", width)
    page.evaluate(
        f"document.querySelector('label.toggle-row:has({REMINDERS}) .toggle-label')"
        f".textContent = {json.dumps(LONG_RU_LABEL)}"
    )
    result = page.evaluate(
        """(() => {
          const rows = [...document.querySelectorAll('label.toggle-row')].map(row => {
            const box = row.getBoundingClientRect();
            const bad = ['input', '.toggle-label', '.toggle-state'].filter(sel => {
              const r = row.querySelector(sel).getBoundingClientRect();
              return r.right > box.right + 0.5 || r.left < box.left - 0.5;
            });
            return {h: box.height, bad};
          });
          return {scroll: document.documentElement.scrollWidth, vw: innerWidth, rows};
        })()"""
    )
    problems = []
    if result["scroll"] > result["vw"]:
        problems.append(f"page scrolls sideways {result['scroll']} > {result['vw']}")
    if len(result["rows"]) != 5:
        problems.append(f"expected 5 rows, got {len(result['rows'])}")
    for index, row in enumerate(result["rows"]):
        if row["h"] < 44 or row["bad"]:
            problems.append(f"row {index}: height {row['h']}, children outside row {row['bad']}")
    _expected(problems, page, "R9 rows must fit and wrap at narrow widths")


# --- R10 --------------------------------------------------------------------------------------


def _durations(value: str) -> list[float]:
    return [float(part.strip().removesuffix("s")) for part in value.split(",") if part.strip()]


def test_transition_declared_and_off_under_reduced_motion(open_settings: OpenSettings) -> None:
    # Part (b) (0s under reduce) is vacuous on current code; it guards an unconditional
    # transition after the fix.
    page = open_settings()
    problems: list[str] = []
    _emulate(page, "no-preference")
    assert not page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
    for sw in _switches(page):
        for part in ("before", "after"):
            style = sw[part]
            if not any(_durations(style["td"])):
                problems.append(f"{sw['cat']} {part}: no transition ({style['td']!r})")
            if "inset-inline-start" not in style["tp"]:
                problems.append(f"{sw['cat']} {part}: transition-property {style['tp']!r}")
    _emulate(page, "reduce")
    for sw in _switches(page):
        for part in ("before", "after"):
            if any(_durations(sw[part]["td"])):
                problems.append(f"{sw['cat']} {part}: reduce still animates {sw[part]['td']!r}")
    _expected(problems, page, "R10 transition declared, disabled under reduced motion")


def test_forced_colors_use_system_colours(open_settings: OpenSettings) -> None:
    page = open_settings()
    _emulate(page, "reduce", "active")
    assert page.evaluate("matchMedia('(forced-colors: active)').matches")
    probes = _run(
        page,
        """
        const read = (prop, value) => {
          const el = document.createElement('i');
          el.style[prop] = value; document.body.append(el);
          const s = getComputedStyle(el);
          const out = prop === 'backgroundColor' ? s.backgroundColor : s.borderTopColor;
          el.remove(); return out;
        };
        return {highlight: read('backgroundColor', 'Highlight'),
                text: read('backgroundColor', 'HighlightText'),
                button: read('borderColor', 'ButtonText')};
        """,
    )
    problems = []
    for index in range(5):
        off, on = (
            _run(
                page,
                f"""
                const el = document.querySelectorAll({json.dumps(SWITCH)})[{index}];
                el.checked = {json.dumps(value)};
                return readSwitch(el);
                """,
            )
            for value in (False, True)
        )
        name = off["cat"]
        if on["before"]["bg"] != probes["highlight"]:
            problems.append(f"{name}: checked track {on['before']['bg']} != Highlight")
        if off["before"]["bColor"] != probes["button"]:
            problems.append(f"{name}: unchecked border {off['before']['bColor']} != ButtonText")
        if on["after"]["bg"] != probes["text"]:
            problems.append(f"{name}: checked thumb {on['after']['bg']} != HighlightText")
    _expected(problems, page, "R10 forced-colors must use system colours")
