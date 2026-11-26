"""Failing repro for WISHENKA-296 (Step 3): Mini App creation form in the Node harness.

The real ``showHome`` / ``showCreate`` run in the shared fake-DOM harness of
``test_miniapp_i18n_repro``. Today a tap on "Create wishlist" sends ``POST /api/wishlists`` with
``{}`` at once and there is no form, so every assertion about "no request before confirmation"
and about the form fails. The fake DOM cannot represent inline error nodes, focus or the 422
body mapping; those are asserted in ``test_wishlist_create_form_browser.py`` (design D-3, test
strategy). ``h1.focus()`` is deliberately not asserted here.

Tests marked "guard" are green today and must stay green.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from tests.test_miniapp_i18n_repro import _NODE_HARNESS
from wishenka.i18n import CATALOG, miniapp_catalog

pytestmark = pytest.mark.timeout(20)

SOURCE = Path("wishenka/web/static/miniapp.js")
PREFIX = "miniapp.create."
CREATE_KEYS = (
    "title",
    "lead",
    "field_title",
    "submit",
    "pending",
    "error_title_required",
    "error_title_too_long",
    "error_date_invalid",
)
FIELDS = ("name", "description", "event_title", "event_date")
FIELD_LABEL_KEYS = {
    "description": "miniapp.wishlist_settings.field_description",
    "event_title": "miniapp.wishlist_settings.field_event",
    "event_date": "miniapp.wishlist_settings.field_date",
}
MAX_TITLE = 255

_PATCHES = (
    (
        "sandbox.globalThis = sandbox;",
        "sandbox.globalThis = sandbox;\n"
        "const baseFetch = sandbox.fetch;\n"
        "const fetchCalls = [];\n"
        "const storageWrites = [];\n"
        "const memoryStore = name => ({\n"
        "  getItem() { return null; },\n"
        "  setItem(key, value) { storageWrites.push({name, key, value}); },\n"
        "  removeItem() {},\n"
        "});\n"
        "sandbox.localStorage = memoryStore('localStorage');\n"
        "sandbox.sessionStorage = memoryStore('sessionStorage');\n"
        "sandbox.fetch = async (url, opts = {}) => {\n"
        "  const method = opts.method || 'GET';\n"
        "  if (method !== 'GET') fetchCalls.push({url, method, body: opts.body ?? null,\n"
        "    headers: opts.headers || {}});\n"
        "  if (method === 'POST' && url === '/api/wishlists') {\n"
        "    const reply = scenario.postReply || {};\n"
        "    if (reply.network) throw new Error('network down');\n"
        "    const status = reply.status || 201;\n"
        "    const sent = JSON.parse(opts.body || '{}');\n"
        "    const body = reply.body || {id: 1, name: sent.name || '', role: 'owner',\n"
        "      status: 'active', items: []};\n"
        "    return {ok: status < 400, status, json: async () => body};\n"
        "  }\n"
        "  return baseFetch(url, opts);\n"
        "};\n"
        "function walk(node, test) {\n"
        "  if (!node) return null;\n"
        "  if (test(node)) return node;\n"
        "  for (const child of (node.children || [])) {\n"
        "    const hit = walk(child, test);\n"
        "    if (hit) return hit;\n"
        "  }\n"
        "  return null;\n"
        "}\n"
        "function matcher(step) {\n"
        "  return node => {\n"
        "    const attrs = node.attributes || {};\n"
        "    const classes = (attrs.class || '').split(/\\s+/);\n"
        "    if (step.cls) return classes.includes(step.cls);\n"
        "    if (step.text !== undefined) {\n"
        "      return node.tagName === 'BUTTON' && node.textContent === step.text;\n"
        "    }\n"
        "    if (step.field) return node.tagName === 'INPUT' && attrs.name === step.field;\n"
        "    if (step.tag) return node.tagName === step.tag;\n"
        "    return false;\n"
        "  };\n"
        "}\n"
        "async function runSteps(out) {\n"
        "  out.stepErrors = [];\n"
        "  out.stepExceptions = [];\n"
        "  for (const step of scenario.steps || []) {\n"
        "    try {\n"
        "      if (step.op === 'click') {\n"
        "        const hit = walk(rootEl, matcher(step));\n"
        "        if (!hit) {\n"
        "          out.stepErrors.push('not found: ' + JSON.stringify(step)); continue;\n"
        "        }\n"
        "        await hit.click();\n"
        "      } else if (step.op === 'fill') {\n"
        "        const hit = walk(rootEl, matcher(step));\n"
        "        if (!hit) {\n"
        "          out.stepErrors.push('not found: ' + JSON.stringify(step)); continue;\n"
        "        }\n"
        "        hit.value = step.value;\n"
        "        for (const fn of (hit.listeners.input || [])) {\n"
        "          await fn({target: hit, preventDefault() {}});\n"
        "        }\n"
        "      } else if (step.op === 'submit') {\n"
        "        const form = walk(rootEl, matcher({tag: 'FORM'}));\n"
        "        if (!form) { out.stepErrors.push('no form to submit'); continue; }\n"
        "        const fire = () => Promise.all((form.listeners.submit || []).map(\n"
        "          fn => fn({target: form, preventDefault() {}})));\n"
        "        await Promise.all(Array.from({length: step.times || 1}, fire));\n"
        "      }\n"
        "    } catch (error) {\n"
        "      out.stepExceptions.push(String(error && error.stack ? error.stack : error));\n"
        "    }\n"
        "    await new Promise(r => setImmediate(r));\n"
        "    await new Promise(r => setImmediate(r));\n"
        "  }\n"
        "  out.rootText = collectText(rootEl);\n"
        "  out.tree = rootEl;\n"
        "  out.statusText = statusEl.textContent;\n"
        "  out.statusKind = statusEl.attributes['data-kind'] ?? null;\n"
        "  out.fetchCalls = fetchCalls;\n"
        "  out.storageWrites = storageWrites;\n"
        "}",
    ),
    (
        "  } else if (scenario.action === 'history') {",
        "  } else if (scenario.action === 'create_flow') {\n"
        "    await sandbox.showHome();\n"
        "    await runSteps(out);\n"
        "  } else if (scenario.action === 'history') {",
    ),
)


def _table(locale: str) -> dict[str, str]:
    return CATALOG["ru" if locale == "ru" else "en"]


def _patched_harness() -> str:
    harness = _NODE_HARNESS
    for old, new in _PATCHES:
        assert harness.count(old) == 1, f"harness anchor changed: {old[:50]!r}"
        harness = harness.replace(old, new)
    return harness


HARNESS = _patched_harness()


def _text(locale: str, key: str) -> str:
    """Catalog text of a key; a key Step 4 has not added yet reads as a marker, not an error."""
    return _table(locale).get(key, f"<missing catalog key {key}>")


def _create_text(locale: str, key: str) -> str:
    return _text(locale, PREFIX + key)


def _run(
    locale: str,
    steps: list[dict[str, Any]],
    *,
    reply: dict[str, Any] | None = None,
    allow_step_errors: bool = False,
) -> dict[str, Any]:
    detail = {
        "id": 1,
        "name": "Birthday",
        "description": None,
        "status": "active",
        "role": "owner",
        "share_token": "share_tok",
        "invite_token": "inv_tok",
        "members": [],
        "items": [],
    }
    scenario: dict[str, Any] = {
        "action": "create_flow",
        "datasetLocale": locale,
        "wishlistDetail": detail,
        "wishlists": [],
        "steps": steps,
        "postReply": reply,
    }
    payload = {
        "jsSource": SOURCE.read_text(encoding="utf-8"),
        "i18nJson": json.dumps(CATALOG),
        "scenario": scenario,
    }
    process = subprocess.run(
        [shutil.which("node") or "node", "-e", HARNESS],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    result = cast(dict[str, Any], json.loads(process.stdout))
    assert result["stepExceptions"] == [], f"a handler threw: {result['stepExceptions']}"
    if not allow_step_errors:
        assert result["stepErrors"] == [], (
            f"a step target is not rendered (feature missing): {result['stepErrors']}"
        )
    return result


def _walk(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        node,
        *(descendant for child in node.get("children", []) for descendant in _walk(child)),
    ]


def _tag(tree: dict[str, Any], tag: str) -> list[dict[str, Any]]:
    return [node for node in _walk(tree) if node.get("tagName") == tag]


def _attr(node: dict[str, Any], name: str) -> str | None:
    value = node.get("attributes", {}).get(name)
    return None if value is None else str(value)


def _field(tree: dict[str, Any], name: str) -> dict[str, Any]:
    found = [n for n in _tag(tree, "INPUT") if _attr(n, "name") == name]
    assert len(found) == 1, f"expected one input named {name!r}, found {len(found)}"
    return found[0]


def _h1(tree: dict[str, Any]) -> str:
    headings = _tag(tree, "H1")
    assert headings, "no h1 rendered"
    return str(headings[0]["textContent"])


def _creations(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        call
        for call in result["fetchCalls"]
        if call["method"] == "POST" and call["url"] == "/api/wishlists"
    ]


def _open_form() -> dict[str, Any]:
    return {"op": "click", "cls": "home-create-btn"}


def _fill(field: str, value: str) -> dict[str, Any]:
    return {"op": "fill", "field": field, "value": value}


SUBMIT: dict[str, Any] = {"op": "submit"}


# --- catalog ----------------------------------------------------------------------------------


def test_create_keys_exist_in_both_languages_with_the_same_placeholders() -> None:
    placeholder = re.compile(r"\{(\w+)\}")
    for key in CREATE_KEYS:
        en = CATALOG["en"].get(PREFIX + key)
        ru = CATALOG["ru"].get(PREFIX + key)
        assert en and ru, f"{PREFIX + key} must exist in en and ru"
        assert set(placeholder.findall(en)) == set(placeholder.findall(ru)), key
        assert en != ru, f"{PREFIX + key} must be translated"
    assert "{max}" in CATALOG["en"][PREFIX + "error_title_too_long"]
    assert "{max}" in CATALOG["ru"][PREFIX + "error_title_too_long"]


def test_create_keys_reach_the_embedded_miniapp_catalog() -> None:
    embedded = miniapp_catalog()
    for locale in ("en", "ru"):
        for key in CREATE_KEYS:
            assert PREFIX + key in embedded[locale], (locale, key)


def test_create_texts_never_mention_reservations() -> None:
    """Surprise invariant guard (D-8): the form carries no reservation wording."""
    word = re.compile(r"reserv|резерв|бронир|бронь|gifted|подарен", re.IGNORECASE)
    for locale in ("en", "ru"):
        for key in CREATE_KEYS:
            assert not word.search(_create_text(locale, key)), (locale, key)


def test_create_screen_is_defined_outside_the_home_script_slice() -> None:
    """D-3: ``showCreate`` sits before ``showHome`` so ``home_script_problems`` does not scan it."""
    source = SOURCE.read_text(encoding="utf-8")
    create = source.find("function showCreate(")
    home = source.find("async function showHome(")
    assert create != -1, "miniapp.js must define showCreate() (feature missing)"
    assert create < home, "showCreate must be defined before showHome"
    assert "homeRenderToken" in source, "showHome needs the staleness token (design D-2)"


# --- the home button opens a form and sends nothing -------------------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_home_create_button_opens_the_form_and_sends_no_request(
    locale: Literal["en", "ru"],
) -> None:
    result = _run(locale, [_open_form()])

    assert _creations(result) == [], "tapping Create wishlist must not send POST /api/wishlists"
    assert result["fetchCalls"] == []
    assert _h1(result["tree"]) == _create_text(locale, "title")
    assert _tag(result["tree"], "FORM"), "the creation screen must render a form"


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_form_has_the_four_fields_labelled_from_the_catalog(
    locale: Literal["en", "ru"],
) -> None:
    result = _run(locale, [_open_form()])
    tree = result["tree"]
    text = result["rootText"]

    assert [_attr(n, "name") for n in _tag(tree, "INPUT")] == list(FIELDS)
    assert _attr(_field(tree, "event_date"), "type") == "datetime-local"
    assert _create_text(locale, "field_title") in text
    for field, key in FIELD_LABEL_KEYS.items():
        assert _text(locale, key) in text, field
    assert _create_text(locale, "lead") in text
    assert _attr(_field(tree, "name"), "aria-required") == "true"
    assert _attr(_field(tree, "name"), "autocomplete") == "off"
    for node in _tag(tree, "FORM"):
        assert _attr(node, "novalidate") is not None


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_form_has_a_submit_create_and_a_plain_cancel_button(
    locale: Literal["en", "ru"],
) -> None:
    tree = _run(locale, [_open_form()])["tree"]
    buttons = _tag(tree, "BUTTON")
    submit = [b for b in buttons if b["textContent"] == _create_text(locale, "submit")]
    cancel_text = _text(locale, "miniapp.wishlist_settings.cancel")
    cancel = [b for b in buttons if b["textContent"] == cancel_text]
    assert len(submit) == 1 and _attr(submit[0], "type") == "submit"
    assert "btn-primary" in (_attr(submit[0], "class") or "")
    assert len(cancel) == 1 and _attr(cancel[0], "type") == "button"
    assert buttons.index(submit[0]) < buttons.index(cancel[0]), "Create comes before Cancel"


def test_opening_the_form_writes_no_draft_to_storage() -> None:
    result = _run("en", [_open_form(), _fill("name", "My draft")])
    assert _h1(result["tree"]) == _create_text("en", "title"), "the creation form must be open"
    assert result["storageWrites"] == []


# --- cancel -----------------------------------------------------------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_cancel_returns_home_and_sends_nothing(locale: Literal["en", "ru"]) -> None:
    cancel = _text(locale, "miniapp.wishlist_settings.cancel")
    result = _run(
        locale,
        [_open_form(), _fill("name", "Half typed"), {"op": "click", "text": cancel}],
    )

    assert result["fetchCalls"] == [], "Cancel must not send anything"
    assert _h1(result["tree"]) == _text(locale, "miniapp.home.title")
    assert not _tag(result["tree"], "FORM")
    assert result["storageWrites"] == []


def test_form_reopens_empty_after_cancel() -> None:
    cancel = _text("en", "miniapp.wishlist_settings.cancel")
    result = _run(
        "en",
        [
            _open_form(),
            _fill("name", "draft"),
            _fill("description", "draft text"),
            {"op": "click", "text": cancel},
            _open_form(),
        ],
    )
    assert _field(result["tree"], "name").get("value") == ""
    assert _field(result["tree"], "description").get("value") == ""
    assert result["fetchCalls"] == []


# --- validation before any request ------------------------------------------------------------


@pytest.mark.parametrize("title", ["", "   ", "\t \n", "a" * (MAX_TITLE + 1)])
def test_invalid_title_sends_nothing_and_keeps_the_typed_values(title: str) -> None:
    result = _run(
        "en",
        [
            _open_form(),
            _fill("name", title),
            _fill("description", "keep me"),
            _fill("event_title", "Party"),
            SUBMIT,
        ],
    )

    assert _creations(result) == [], "an invalid title must not be sent"
    tree = result["tree"]
    assert _tag(tree, "FORM"), "the form must stay on screen"
    assert _field(tree, "name")["value"] == title
    assert _field(tree, "description")["value"] == "keep me"
    assert _field(tree, "event_title")["value"] == "Party"
    assert result["statusText"] != _create_text("en", "pending"), "no 'Creating...' flash"


def test_five_digit_year_is_rejected_without_a_request_or_an_exception() -> None:
    result = _run(
        "en",
        [_open_form(), _fill("name", "Birthday"), _fill("event_date", "20000-01-01T00:00"), SUBMIT],
    )
    assert _creations(result) == []
    assert _field(result["tree"], "name")["value"] == "Birthday"
    assert _field(result["tree"], "event_date")["value"] == "20000-01-01T00:00"


# --- confirmed creation -----------------------------------------------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_valid_submit_sends_one_trimmed_post_and_opens_the_list(
    locale: Literal["en", "ru"],
) -> None:
    result = _run(locale, [_open_form(), _fill("name", "  Birthday  "), SUBMIT])

    posts = _creations(result)
    assert len(posts) == 1, f"exactly one POST /api/wishlists expected, got {len(posts)}"
    assert posts[0]["headers"].get("X-CSRF-Token") == "csrf-123"
    body = json.loads(posts[0]["body"])
    assert body.get("name") == "Birthday"
    assert body.get("description") is None
    assert body.get("event_title") is None
    assert body.get("event_date") is None
    # The owner list screen carries its own settings form, so only the creation form is checked.
    creation_forms = [
        form
        for form in _tag(result["tree"], "FORM")
        if "wishlist-create-form" in (_attr(form, "class") or "")
    ]
    assert not creation_forms, "the creation form must be replaced by the list screen"
    assert _create_text(locale, "title") not in result["rootText"]
    assert "Birthday" in result["rootText"]


def test_valid_submit_sends_trimmed_optional_values_and_a_utc_date() -> None:
    result = _run(
        "en",
        [
            _open_form(),
            _fill("name", "Birthday"),
            _fill("description", "  Party at home  "),
            _fill("event_title", "Turns 30"),
            _fill("event_date", "2030-05-01T10:00"),
            SUBMIT,
        ],
    )
    body = json.loads(_creations(result)[0]["body"])
    assert body.get("description") == "Party at home"
    assert body.get("event_title") == "Turns 30"
    assert body.get("event_date") == "2030-05-01T10:00:00.000Z"


def test_title_of_255_code_points_is_sent() -> None:
    title = "\U0001f381" * MAX_TITLE
    result = _run("en", [_open_form(), _fill("name", title), SUBMIT])
    posts = _creations(result)
    assert len(posts) == 1
    assert json.loads(posts[0]["body"]).get("name") == title


def test_submit_burst_sends_exactly_one_post() -> None:
    """Requirement 8: several submits in the same tick (taps and Enter) share one lock."""
    result = _run("en", [_open_form(), _fill("name", "Birthday"), {"op": "submit", "times": 3}])
    posts = _creations(result)
    assert len(posts) == 1, "a burst of submits must send one request"
    assert json.loads(posts[0]["body"]).get("name") == "Birthday", "the request carries the form"


# --- failure ----------------------------------------------------------------------------------


@pytest.mark.parametrize("reply", [{"status": 500}, {"network": True}], ids=["500", "network"])
def test_failed_creation_keeps_the_form_and_announces_the_error(reply: dict[str, Any]) -> None:
    result = _run("en", [_open_form(), _fill("name", "Birthday"), SUBMIT], reply=reply)

    assert len(_creations(result)) == 1
    assert _tag(result["tree"], "FORM"), "the form must stay after a failure"
    assert _field(result["tree"], "name")["value"] == "Birthday"
    assert result["statusText"] == _text("en", "miniapp.home.create_failed")
    assert result["statusKind"] == "error"


def test_retry_after_a_failure_sends_a_second_request_only_on_the_next_submit() -> None:
    result = _run(
        "en",
        [_open_form(), _fill("name", "Birthday"), SUBMIT, SUBMIT],
        reply={"status": 500},
    )
    posts = _creations(result)
    assert [json.loads(p["body"]).get("name") for p in posts] == ["Birthday", "Birthday"], (
        "one request per confirmed submit, none extra"
    )


# --- WISHENKA-320 name contract ---------------------------------------------------------------


INVISIBLE_NAMES = (
    ("zwsp", "\u200b"),
    ("word-joiner", "\u2060"),
    ("bom", "\ufeff"),
    ("lrm", "\u200e"),
    ("rlm", "\u200f"),
    ("marks-and-spaces", " \u200b \u2060 \ufeff \u200e \u200f "),
)


def _too_long_text(locale: str) -> str:
    return _create_text(locale, "error_title_too_long").replace("{max}", str(MAX_TITLE))


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize(("label", "title"), INVISIBLE_NAMES)
def test_invisible_only_name_uses_the_required_message_and_sends_nothing(
    locale: Literal["en", "ru"], label: str, title: str
) -> None:
    result = _run(
        locale,
        [_open_form(), _fill("name", title), _fill("description", "keep me"), SUBMIT],
    )

    assert _creations(result) == [], f"invisible-only name {label} must not be posted"
    assert _create_text(locale, "error_title_required") in result["rootText"]
    assert _field(result["tree"], "name")["value"] == title
    assert _field(result["tree"], "description")["value"] == "keep me"
    assert _tag(result["tree"], "FORM")


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_too_long_error_type_uses_the_too_long_catalog_string(
    locale: Literal["en", "ru"],
) -> None:
    required = _create_text(locale, "error_title_required")
    too_long = _too_long_text(locale)
    result = _run(
        locale,
        [_open_form(), _fill("name", "Birthday"), SUBMIT],
        reply={
            "status": 422,
            "body": {
                "detail": [
                    {
                        "loc": ["body", "name"],
                        "msg": "too long",
                        "type": "wishlist_name_too_long",
                        "ctx": {"max_length": MAX_TITLE},
                    }
                ]
            },
        },
    )

    assert too_long in result["rootText"], (
        "422 type wishlist_name_too_long must use the too-long catalog string; "
        f"required shown={required in result['rootText']}"
    )
    assert required not in result["rootText"]
    assert _field(result["tree"], "name")["value"] == "Birthday"
    assert _tag(result["tree"], "FORM"), "a refused create must not open a list"


def test_edge_bom_stays_in_the_submitted_name() -> None:
    """The POST name is the normalized string, not a second ``String.prototype.trim()``."""
    raw = "  \ufeffHi  "
    result = _run("en", [_open_form(), _fill("name", raw), SUBMIT])
    posts = _creations(result)
    assert len(posts) == 1, "a visible name must be submitted once"
    assert json.loads(posts[0]["body"])["name"] == "\ufeffHi"
