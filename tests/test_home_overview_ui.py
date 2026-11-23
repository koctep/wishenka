"""Failing repro tests for WISHENKA-289: Home overview UI contracts and i18n."""

from __future__ import annotations

import json
import re
import shutil
import string
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from tests import test_reservations_cabinet_ui
from tests.test_i18n_sync import _has_cyrillic, _make_settings
from wishenka.i18n import CATALOG, SupportedLocale, miniapp_catalog, t
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(20)

_SCRIPT_TAG_RE = re.compile(
    r'<script\s+id=["\']miniapp-i18n["\']\s+type=["\']application/json["\']\s*>(.*?)</script>',
    re.DOTALL,
)

_NEW_HOME_KEYS = (
    "miniapp.home.lead",
    "miniapp.home.reservations_hint",
    "miniapp.home.my_wishlists_sub",
    "miniapp.home.collaborating_sub",
    "miniapp.home.favorites_sub",
    "miniapp.home.deleted_sub",
    "miniapp.home.my_wishlists_empty_hint",
    "miniapp.home.collaborating_empty_hint",
    "miniapp.home.favorites_empty_hint",
    "miniapp.home.open_wishlist",
    "miniapp.home.open_wishlist_named",
    "miniapp.home.remove_favorite",
    "miniapp.home.remove_favorite_named",
)

_PRESERVED_KEYS = (
    "nav.settings",
    "miniapp.home.title",
    "miniapp.home.create_wishlist",
    "miniapp.home.viewing_history",
    "miniapp.home.my_wishlists",
    "miniapp.home.collaborating",
    "miniapp.home.favorites",
    "miniapp.home.remove",
    "miniapp.deleted.heading",
    "miniapp.deleted.restore",
    "miniapp.common.untitled_wishlist",
)

_NODE_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const { jsSource, i18nJson, scenario } = payload;

const state = {
  wishlists: scenario.wishlists || [],
  favorites: scenario.favorites || [],
  deleted: scenario.deleted || [],
  history: scenario.history || [],
  wishlistDetail: scenario.wishlistDetail || {},
  requests: [],
  focusedEl: null,
};

function makeEl(tag) {
  const el = {
    tagName: String(tag || '').toUpperCase(),
    textContent: '',
    value: '',
    disabled: false,
    dataset: {},
    attributes: {},
    children: [],
    listeners: {},
    get className() {
      return this.attributes.class || '';
    },
    set className(val) {
      this.attributes.class = String(val || '');
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this.attributes, name)
        ? this.attributes[name]
        : null;
    },
    append(...nodes) {
      for (const n of nodes) {
        if (typeof n === 'string') {
          this.children.push({
            tagName: '#TEXT',
            textContent: n,
            children: [],
            attributes: {},
            disabled: false,
          });
        } else if (n) {
          this.children.push(n);
        }
      }
    },
    replaceChildren(...nodes) {
      this.children = [];
      this.append(...nodes);
    },
    insertBefore(newNode, refNode) {
      const idx = this.children.indexOf(refNode);
      if (idx === -1) this.children.push(newNode);
      else this.children.splice(idx, 0, newNode);
    },
    querySelector(sel) {
      if (sel === 'button') {
        return this.children.find(c => c.tagName === 'BUTTON') || findFirstButton(this);
      }
      if (sel === '.wishlist-section') {
        return (
          this.children.find(
            c => String(c.attributes?.class || '').split(/\s+/).includes('wishlist-section')
          ) || null
        );
      }
      return null;
    },
    addEventListener(evt, fn) {
      this.listeners[evt] = this.listeners[evt] || [];
      this.listeners[evt].push(fn);
    },
    async click() {
      for (const fn of (this.listeners.click || [])) {
        await fn({ preventDefault() {} });
      }
    },
    select() {},
    focus() {
      state.focusedEl = serializeEl(this);
    },
  };
  return el;
}

function findFirstButton(node) {
  for (const child of (node.children || [])) {
    if (child.tagName === 'BUTTON') return child;
    const nested = findFirstButton(child);
    if (nested) return nested;
  }
  return null;
}

function serializeEl(node) {
  if (!node) return null;
  return {
    tag: node.tagName,
    text: node.textContent || '',
    attrs: { ...(node.attributes || {}) },
    disabled: Boolean(node.disabled),
    children: (node.children || []).map(serializeEl),
  };
}

function findByClass(node, cls, acc = []) {
  if (!node) return acc;
  const classes = String(node.attributes?.class || '').split(/\s+/).filter(Boolean);
  if (classes.includes(cls)) acc.push(node);
  for (const child of (node.children || [])) findByClass(child, cls, acc);
  return acc;
}

const rootEl = makeEl('main');
rootEl.dataset = {
  locale: scenario.locale || 'en',
  bot: 'wishenka_bot',
  miniapp: 'app',
};
const statusEl = makeEl('p');
const i18nEl = makeEl('script');
i18nEl.textContent = i18nJson;
const htmlEl = { lang: scenario.locale || 'en' };
const headEl = { append() {} };
const resolvedLocale = scenario.locale || 'en';

function jsonRes(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  };
}

const sandbox = {
  console,
  Promise,
  Date,
  JSON,
  Error,
  String,
  Boolean,
  Object,
  Array,
  Math,
  Number,
  Set,
  Map,
  RegExp,
  Intl,
  URLSearchParams,
  encodeURIComponent,
  setTimeout: (fn, _ms) => { if (typeof fn === 'function') fn(); return 0; },
  navigator: {
    language: resolvedLocale === 'ru' ? 'ru-RU' : 'en-US',
    clipboard: { writeText: async () => {} },
  },
  location: { search: scenario.startParam ? `?startapp=${scenario.startParam}` : '' },
  DOMParser: class {
    parseFromString(html) {
      const text = String(html || '');
      const hrefMatch = text.match(/<a[^>]*href=["']([^"']*)["'][^>]*>/i);
      const titleMatch = text.match(
        /class=["'][^"']*reservations-title[^"']*["'][^>]*>([^<]*)</i
      );
      const badgeMatch = text.match(
        /class=["'][^"']*reservations-badge[^"']*["'][^>]*>([^<]*)</i
      );
      const linkEl = hrefMatch ? makeEl('a') : null;
      if (linkEl) linkEl.setAttribute('href', hrefMatch[1]);
      const titleEl = titleMatch ? makeEl('span') : null;
      if (titleEl) titleEl.textContent = titleMatch[1].trim();
      const badgeEl = badgeMatch ? makeEl('span') : null;
      if (badgeEl) badgeEl.textContent = badgeMatch[1].trim();
      return {
        querySelector(sel) {
          if (sel === 'a') return linkEl;
          if (sel === '.reservations-title') return titleEl;
          if (sel === '.reservations-badge') return badgeEl;
          return null;
        },
      };
    }
  },
  document: {
    documentElement: htmlEl,
    head: headEl,
    getElementById(id) {
      if (id === 'app') return rootEl;
      if (id === 'status') return statusEl;
      if (id === 'miniapp-i18n') return i18nJson ? i18nEl : null;
      return null;
    },
    createElement(tag) { return makeEl(tag); },
  },
  fetch: async (url, opts = {}) => {
    const method = (opts.method || 'GET').toUpperCase();
    state.requests.push({ method, url, body: opts.body || null });

    if (url === '/web/reservations/card') {
      const cardStatus = scenario.reservationsCardStatus ?? 200;
      if (cardStatus !== 200) {
        return { ok: false, status: cardStatus, text: async () => '' };
      }
      return {
        ok: true,
        status: 200,
        text: async () => String(scenario.reservationsCardHtml || ''),
      };
    }
    if (url === '/api/auth/me') return jsonRes({ locale: resolvedLocale });
    if (url === '/api/auth/csrf') return jsonRes({ csrf_token: 'csrf-test' });
    if (url === '/api/wishlists' && method === 'GET') return jsonRes(state.wishlists);
    if (url === '/api/wishlists' && method === 'POST') {
      const sent = JSON.parse(opts.body || '{}');
      const created = {
        id: 999, name: sent.name || '', role: 'owner', status: 'active', items: [],
      };
      state.wishlistDetail['999'] = created;
      return jsonRes(created, 201);
    }
    if (url === '/api/favorites' && method === 'GET') return jsonRes(state.favorites);
    if (url.startsWith('/api/favorites/') && method === 'DELETE') {
      const favId = Number(url.split('/').pop());
      state.favorites = state.favorites.filter(f => f.id !== favId);
      return jsonRes({ status: 'removed', wishlist_id: favId });
    }
    if (url === '/api/wishlists/deleted' && method === 'GET') return jsonRes(state.deleted);
    if (url.endsWith('/restore-deleted') && method === 'POST') {
      const restoreStatus = scenario.restoreStatus ?? 200;
      const wlId = Number(url.split('/')[3]);
      if (restoreStatus === 200) {
        state.deleted = state.deleted.filter(d => d.id !== wlId);
        return jsonRes({ id: wlId, status: 'active' });
      }
      return jsonRes({ detail: 'restore failed' }, restoreStatus);
    }
    if (url === '/api/history' && method === 'GET') return jsonRes(state.history);
    if (url.startsWith('/api/history/') && method === 'POST') {
      return jsonRes({ status: 'recorded' });
    }
    if (url.startsWith('/api/wishlists/') && method === 'GET') {
      const wlId = url.split('/').pop();
      return jsonRes(
        state.wishlistDetail[wlId] || { id: Number(wlId), name: 'Detail', role: 'owner', items: [] }
      );
    }
    return jsonRes({ detail: 'not found' }, 404);
  },
  window: {
    crypto: { randomUUID: () => 'uuid-test-1' },
    Telegram: {
      WebApp: {
        initData: 'signed_init_data',
        initDataUnsafe: {
          start_param: scenario.startParam || '',
          user: { language_code: resolvedLocale },
        },
        ready() {},
        expand() {},
        openTelegramLink() {},
      },
    },
  },
};
sandbox.globalThis = sandbox;

(async () => {
  vm.createContext(sandbox);
  vm.runInContext(jsSource, sandbox);
  await new Promise(r => setImmediate(r));
  await new Promise(r => setImmediate(r));

  if (scenario.clickClass) {
    const matches = findByClass(rootEl, scenario.clickClass);
    const idx = scenario.clickIndex ?? 0;
    if (matches[idx]) {
      await matches[idx].click();
      await new Promise(r => setImmediate(r));
    }
  } else if (scenario.clickNavButtonIndex !== undefined) {
    const navs = findByClass(rootEl, 'top-nav');
    const navButtons = (navs[0]?.children || []).filter(c => c.tagName === 'BUTTON');
    if (navButtons[scenario.clickNavButtonIndex]) {
      await navButtons[scenario.clickNavButtonIndex].click();
      await new Promise(r => setImmediate(r));
    }
  } else if (scenario.clickRestore) {
    const delCards = findByClass(rootEl, 'deleted-wishlist-card');
    const btn = delCards[0] ? findFirstButton(delCards[0]) : null;
    if (btn) {
      await btn.click();
      await new Promise(r => setImmediate(r));
    }
  }

  process.stdout.write(JSON.stringify({
    root: serializeEl(rootEl),
    status: statusEl.textContent,
    requests: state.requests,
    focusedEl: state.focusedEl,
  }));
})().catch(err => {
  process.stderr.write(String(err && err.stack ? err.stack : err));
  process.exit(1);
});
"""


def _placeholders(template: str) -> set[str]:
    """Extract format field names from an i18n template string."""
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(template)
        if field_name is not None
    }


def _load_miniapp_assets(tmp_path: Path) -> tuple[str, str]:
    """Fetch Mini App JS source and embedded #miniapp-i18n JSON catalog."""
    app = create_app(_make_settings(tmp_path / "home_overview_ui.db"))
    with TestClient(app) as client:
        html_resp = client.get("/", headers={"Accept-Language": "en"})
        js_resp = client.get("/static/miniapp.js")
        assert html_resp.status_code == 200
        assert js_resp.status_code == 200
        match = _SCRIPT_TAG_RE.search(html_resp.text)
        assert match is not None, "GET / must embed #miniapp-i18n JSON"
        return js_resp.text, match.group(1)


def _run_node(js_source: str, i18n_json: str, scenario: dict[str, Any]) -> dict[str, Any]:
    """Execute miniapp.js in an isolated Node VM sandbox with a bounded timeout."""
    node_bin = shutil.which("node") or "/usr/bin/node"
    assert Path(node_bin).exists(), f"Node binary not found at {node_bin}"
    proc = subprocess.run(
        [node_bin, "-e", _NODE_HARNESS],
        input=json.dumps({"jsSource": js_source, "i18nJson": i18n_json, "scenario": scenario}),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 0, f"Node harness failed ({proc.returncode}): {proc.stderr}"
    return cast(dict[str, Any], json.loads(proc.stdout))


def _classes(node: dict[str, Any]) -> set[str]:
    """Return the whitespace-split CSS classes of a serialized DOM node."""
    raw = str(node.get("attrs", {}).get("class", ""))
    return {part for part in raw.split() if part}


def _find_all(
    node: dict[str, Any], *, tag: str | None = None, cls: str | None = None
) -> list[dict[str, Any]]:
    """Find all matching serialized DOM nodes recursively by tag and/or CSS class."""
    hits: list[dict[str, Any]] = []
    if (tag is None or node.get("tag") == tag.upper()) and (cls is None or cls in _classes(node)):
        hits.append(node)
    for child in node.get("children", []):
        hits.extend(_find_all(child, tag=tag, cls=cls))
    return hits


def _find_one(
    node: dict[str, Any],
    *,
    tag: str | None = None,
    cls: str | None = None,
) -> dict[str, Any] | None:
    """Return the first matching serialized DOM node or None."""
    hits = _find_all(node, tag=tag, cls=cls)
    return hits[0] if hits else None


def _collect_text(node: dict[str, Any]) -> str:
    """Recursively join textContent across a serialized DOM subtree."""
    parts: list[str] = []
    if node.get("text"):
        parts.append(str(node["text"]))
    for child in node.get("children", []):
        text = _collect_text(child)
        if text:
            parts.append(text)
    return " ".join(parts).strip()


def _reservations_card_html(locale: str, count: int) -> str:
    """Build SSR /web/reservations/card partial HTML for the given locale and count."""
    title = t("web.reservations.title", locale)
    return (
        f'<a href="/web/reservations">'
        f'<span class="reservations-title">{title}</span>'
        f'<span class="reservations-badge">{count}</span>'
        f"</a>"
    )


def test_home_overview_i18n_keys_and_bilingual_parity(tmp_path: Path) -> None:
    """CATALOG and embedded #miniapp-i18n define all new RU/EN home keys cleanly."""
    missing_en = [k for k in _NEW_HOME_KEYS if k not in CATALOG["en"]]
    missing_ru = [k for k in _NEW_HOME_KEYS if k not in CATALOG["ru"]]
    assert not missing_en, f"Missing EN home overview i18n keys: {missing_en}"
    assert not missing_ru, f"Missing RU home overview i18n keys: {missing_ru}"

    projected = miniapp_catalog()
    for key in (*_NEW_HOME_KEYS, *_PRESERVED_KEYS):
        en_val = CATALOG["en"][key]
        ru_val = CATALOG["ru"][key]
        assert en_val.strip() and ru_val.strip()
        assert _placeholders(en_val) == _placeholders(ru_val), key
        assert not _has_cyrillic(en_val), f"Cyrillic in EN key {key}: {en_val}"
        assert _has_cyrillic(ru_val), f"Missing Russian copy in RU key {key}: {ru_val}"
        assert projected["en"][key] == en_val
        assert projected["ru"][key] == ru_val

    assert CATALOG["en"]["miniapp.home.open_wishlist"] == "Open"
    assert CATALOG["ru"]["miniapp.home.open_wishlist"] == "Открыть"
    assert CATALOG["en"]["miniapp.home.remove_favorite"] == "Remove from favorites"
    assert CATALOG["ru"]["miniapp.home.remove_favorite"] == "Убрать из избранного"

    locales: tuple[SupportedLocale, ...] = ("en", "ru")
    for locale in locales:
        open_label = CATALOG[locale]["miniapp.home.open_wishlist"]
        open_named = CATALOG[locale]["miniapp.home.open_wishlist_named"]
        assert open_named.startswith(open_label) and "{name}" in open_named
        rm_label = CATALOG[locale]["miniapp.home.remove_favorite"]
        rm_named = CATALOG[locale]["miniapp.home.remove_favorite_named"]
        assert rm_named.startswith(rm_label) and "{name}" in rm_named

    _, i18n_json = _load_miniapp_assets(tmp_path)
    embedded = json.loads(i18n_json)
    for locale in locales:
        for key in _NEW_HOME_KEYS:
            assert embedded[locale][key] == CATALOG[locale][key]


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_home_section_grouping_and_role_precedence_deduplication(
    tmp_path: Path, locale: str
) -> None:
    """Home groups lists into distinct sections and deduplicates collaborator favorites."""
    js_source, i18n_json = _load_miniapp_assets(tmp_path)
    result = _run_node(
        js_source,
        i18n_json,
        {
            "locale": locale,
            "wishlists": [
                {
                    "id": 1,
                    "name": "Owned Birthday",
                    "role": "owner",
                    "is_favorite": False,
                    "event_title": "Birthday Party",
                    "event_date": "2026-08-15T12:00:00Z",
                },
                {
                    "id": 2,
                    "name": "Admin Shared",
                    "role": "admin",
                    "is_favorite": True,
                    "event_title": "Office Party",
                    "event_date": "2026-09-01T00:00:00Z",
                },
                {
                    "id": 3,
                    "name": "Member Collab",
                    "role": "member",
                    "is_favorite": True,
                },
            ],
            "favorites": [
                {"id": 2, "name": "Admin Shared", "role": "admin", "is_favorite": True},
                {"id": 3, "name": "Member Collab", "role": "member", "is_favorite": True},
                {
                    "id": 4,
                    "name": "Pure Favorite",
                    "role": "favorite",
                    "is_favorite": True,
                    "event_title": "Picnic",
                    "event_date": "2026-07-10T00:00:00Z",
                },
                {"id": 5, "name": "", "role": "favorite", "is_favorite": True},
            ],
            "deleted": [],
            "reservationsCardHtml": _reservations_card_html(locale, 2),
        },
    )
    root = result["root"]
    assert result["status"] == ""

    problems: list[str] = []
    h1 = _find_one(root, tag="h1")
    if h1 is None or _collect_text(h1) != t("miniapp.home.title", locale):
        problems.append("missing or mismatched #app h1")
    lead = _find_one(root, cls="home-lead")
    if lead is None or not _collect_text(lead):
        problems.append("missing .home-lead subtitle")

    nav = _find_one(root, cls="home-top-nav")
    if nav is None or "top-nav" not in _classes(nav):
        problems.append("missing .top-nav.home-top-nav")
    else:
        nav_buttons = [c for c in nav["children"] if c["tag"] == "BUTTON"]
        if len(nav_buttons) != 2:
            problems.append(f"expected 2 nav buttons, got {len(nav_buttons)}")
        else:
            if "btn-primary" not in _classes(nav_buttons[0]):
                problems.append("first nav button missing .btn-primary")
            if _collect_text(nav_buttons[0]) != t("miniapp.home.create_wishlist", locale):
                problems.append("first nav button label mismatch")
            if "home-nav-action" not in _classes(nav_buttons[1]):
                problems.append("second nav button missing .home-nav-action")
            if _collect_text(nav_buttons[1]) != t("miniapp.home.viewing_history", locale):
                problems.append("second nav button label mismatch")
        settings_link = _find_one(nav, tag="a", cls="settings-link")
        if settings_link is None or settings_link["attrs"].get("href") != "/settings":
            problems.append("missing a.settings-link[href='/settings'] inside .home-top-nav")
        elif _collect_text(settings_link) != t("nav.settings", locale):
            problems.append("settings link label mismatch")

    direct_sections = [c for c in root["children"] if "wishlist-section" in _classes(c)]
    if len(direct_sections) != 3:
        problems.append(f"expected 3 direct .wishlist-section children, got {len(direct_sections)}")
    if _find_one(root, cls="deleted-section") is not None:
        problems.append("unexpected .deleted-section when deleted lists is empty")

    expected_sections = [
        ("wishlist-section--owned", "1", ["Owned Birthday"], ["badge-owner"]),
        (
            "wishlist-section--collab",
            "2",
            ["Admin Shared", "Member Collab"],
            ["badge-admin", "badge-member"],
        ),
        (
            "wishlist-section--favorites",
            "2",
            ["Pure Favorite", t("miniapp.common.untitled_wishlist", locale)],
            ["badge-favorite", "badge-favorite"],
        ),
    ]
    for section, (modifier, count, titles, badge_classes) in zip(
        direct_sections, expected_sections, strict=True
    ):
        if modifier not in _classes(section):
            problems.append(f"section missing modifier {modifier}")
        header = _find_one(section, cls="wishlist-section-header")
        if header is None:
            problems.append(f"{modifier}: missing .wishlist-section-header")
        else:
            count_el = _find_one(header, cls="section-count")
            if count_el is None or _collect_text(count_el) != count:
                problems.append(f"{modifier}: expected .section-count == {count!r}")
        sub = _find_one(section, cls="section-subtitle")
        if sub is None or not _collect_text(sub):
            problems.append(f"{modifier}: missing .section-subtitle")

        cards = _find_all(section, cls="wishlist-card")
        card_titles = [
            _collect_text(_find_one(card, cls="wishlist-card-title") or {}) for card in cards
        ]
        if card_titles != titles:
            problems.append(f"{modifier}: card titles {card_titles!r} != {titles!r}")
        for card, badge_cls in zip(cards, badge_classes, strict=False):
            if _find_one(card, cls=badge_cls) is None:
                problems.append(f"{modifier}: card missing .{badge_cls}")

    if len(direct_sections) >= 3:
        fav_text = _collect_text(direct_sections[2])
        if "Admin Shared" in fav_text or "Member Collab" in fav_text:
            problems.append("collaborator-favorited wishlist duplicated into Favorites section")

    assert problems == [], problems


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_home_cards_scannability_action_hierarchy_and_favorites_removal(
    tmp_path: Path, locale: str
) -> None:
    """Cards separate title/role/event context from Open and subordinate Remove from favorites."""
    js_source, i18n_json = _load_miniapp_assets(tmp_path)
    scenario: dict[str, Any] = {
        "locale": locale,
        "wishlists": [
            {
                "id": 10,
                "name": "",
                "role": "owner",
                "event_title": "Autumn Dinner",
                "event_date": "2026-10-20T00:00:00Z",
            },
            {"id": 11, "name": "Plain List", "role": "member"},
        ],
        "favorites": [{"id": 42, "name": "Friend List", "role": "favorite", "is_favorite": True}],
        "deleted": [],
        "wishlistDetail": {
            "42": {"id": 42, "name": "Friend List", "role": "favorite", "is_favorite": True}
        },
    }
    res = _run_node(js_source, i18n_json, scenario)
    root = res["root"]
    untitled = t("miniapp.common.untitled_wishlist", locale)
    open_label = "Open" if locale == "en" else "Открыть"
    remove_label = "Remove from favorites" if locale == "en" else "Убрать из избранного"

    owned_sec = _find_one(root, cls="wishlist-section--owned")
    collab_sec = _find_one(root, cls="wishlist-section--collab")
    fav_sec = _find_one(root, cls="wishlist-section--favorites")
    assert owned_sec is not None, "Missing .wishlist-section--owned"
    assert collab_sec is not None, "Missing .wishlist-section--collab"
    assert fav_sec is not None, "Missing .wishlist-section--favorites"

    owned_card = _find_one(owned_sec, cls="wishlist-card")
    assert owned_card is not None
    title_el = _find_one(owned_card, tag="h3", cls="wishlist-card-title")
    assert title_el is not None and _collect_text(title_el) == untitled
    meta_el = _find_one(owned_card, cls="wishlist-card-meta")
    assert meta_el is not None
    meta_text = _collect_text(meta_el)
    assert "Autumn Dinner" in meta_text and "2026" in meta_text

    open_btn = _find_one(owned_card, tag="button", cls="wishlist-card-open")
    assert open_btn is not None
    assert _collect_text(open_btn) == open_label
    aria_open = open_btn["attrs"].get("aria-label", "")
    assert aria_open.startswith(open_label) and untitled in aria_open

    plain_card = _find_one(collab_sec, cls="wishlist-card")
    assert plain_card is not None
    assert _find_one(plain_card, cls="wishlist-card-meta") is None

    fav_card = _find_one(fav_sec, cls="wishlist-card")
    assert fav_card is not None
    fav_actions = _find_one(fav_card, cls="wishlist-card-actions")
    assert fav_actions is not None
    fav_open = _find_one(fav_actions, tag="button", cls="wishlist-card-open")
    fav_remove = _find_one(fav_actions, tag="button", cls="wishlist-card-remove")
    assert fav_open is not None and fav_remove is not None
    assert _collect_text(fav_remove) == remove_label
    assert "btn-danger" not in _classes(fav_remove)
    assert "btn-primary" not in _classes(fav_remove)
    aria_rm = fav_remove["attrs"].get("aria-label", "")
    assert aria_rm.startswith(remove_label) and "Friend List" in aria_rm

    opened = _run_node(
        js_source,
        i18n_json,
        {**scenario, "clickClass": "wishlist-card-open", "clickIndex": 2},
    )
    assert any(r["url"] == "/api/wishlists/42" for r in opened["requests"])

    removed = _run_node(js_source, i18n_json, {**scenario, "clickClass": "wishlist-card-remove"})
    assert any(
        r["method"] == "DELETE" and r["url"] == "/api/favorites/42" for r in removed["requests"]
    )
    assert removed["status"] == t("miniapp.home.removed_from_favorites", locale)
    fav_sec_after = _find_one(removed["root"], cls="wishlist-section--favorites")
    assert fav_sec_after is not None and _find_one(fav_sec_after, cls="empty-state") is not None


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_home_empty_states_two_part_guidance_and_hidden_deleted_section(
    tmp_path: Path, locale: str
) -> None:
    """Empty primary sections show calm two-part reason+hint guidance; empty deleted hides."""
    js_source, i18n_json = _load_miniapp_assets(tmp_path)
    res = _run_node(
        js_source,
        i18n_json,
        {"locale": locale, "wishlists": [], "favorites": [], "deleted": []},
    )
    root = res["root"]
    assert _find_one(root, cls="deleted-section") is None

    for modifier in (
        "wishlist-section--owned",
        "wishlist-section--collab",
        "wishlist-section--favorites",
    ):
        section = _find_one(root, cls=modifier)
        assert section is not None, f"Missing {modifier}"
        count_el = _find_one(section, cls="section-count")
        assert count_el is not None and _collect_text(count_el) == "0"
        empty_state = _find_one(section, cls="empty-state")
        assert empty_state is not None, f"Missing .empty-state in {modifier}"
        notice = _find_one(empty_state, cls="empty-notice")
        hint = _find_one(empty_state, cls="empty-hint")
        assert notice is not None and hint is not None
        notice_text = _collect_text(notice)
        hint_text = _collect_text(hint)
        assert notice_text and hint_text and notice_text != hint_text
        if locale == "ru":
            assert _has_cyrillic(notice_text) and _has_cyrillic(hint_text)
        else:
            assert not _has_cyrillic(notice_text) and not _has_cyrillic(hint_text)


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_home_recently_deleted_section_restore_and_error_states(
    tmp_path: Path, locale: str
) -> None:
    """Conditional Recently deleted section supports restore, 410 expired, and retry on error."""
    js_source, i18n_json = _load_miniapp_assets(tmp_path)
    base_scenario: dict[str, Any] = {
        "locale": locale,
        "wishlists": [],
        "favorites": [],
        "deleted": [{"id": 77, "name": "Deleted Birthday", "days_remaining": 12}],
    }
    res = _run_node(js_source, i18n_json, base_scenario)
    del_section = _find_one(res["root"], cls="deleted-section")
    assert del_section is not None
    assert "wishlist-section--deleted" in _classes(del_section)
    header = _find_one(del_section, cls="wishlist-section-header")
    assert header is not None
    count_el = _find_one(header, cls="section-count")
    assert count_el is not None and _collect_text(count_el) == "1"
    assert _find_one(del_section, cls="section-subtitle") is not None
    del_card = _find_one(del_section, cls="deleted-wishlist-card")
    assert del_card is not None
    card_text = _collect_text(del_card)
    assert "Deleted Birthday" in card_text and "12" in card_text

    ok_res = _run_node(
        js_source, i18n_json, {**base_scenario, "clickRestore": True, "restoreStatus": 200}
    )
    assert any(
        r["method"] == "POST" and r["url"] == "/api/wishlists/77/restore-deleted"
        for r in ok_res["requests"]
    )
    assert ok_res["status"] == t("miniapp.deleted.restored", locale)
    assert _find_one(ok_res["root"], cls="deleted-section") is None

    exp_res = _run_node(
        js_source, i18n_json, {**base_scenario, "clickRestore": True, "restoreStatus": 410}
    )
    assert exp_res["status"] == t("miniapp.deleted.expired", locale)

    err_res = _run_node(
        js_source, i18n_json, {**base_scenario, "clickRestore": True, "restoreStatus": 500}
    )
    assert err_res["status"] == t("miniapp.deleted.restore_failed", locale)
    del_card_err = _find_one(err_res["root"], cls="deleted-wishlist-card")
    restore_btn = _find_one(del_card_err or {}, tag="button")
    assert restore_btn is not None and restore_btn["disabled"] is False


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_home_reservations_card_rendering_and_non_blocking_fallback(
    tmp_path: Path, locale: str
) -> None:
    """Reservations card renders semantic markup before sections and degrades cleanly on 500."""
    js_source, i18n_json = _load_miniapp_assets(tmp_path)
    ok_res = _run_node(
        js_source,
        i18n_json,
        {
            "locale": locale,
            "reservationsCardStatus": 200,
            "reservationsCardHtml": _reservations_card_html(locale, 3),
        },
    )
    root = ok_res["root"]
    assert ok_res["status"] == ""
    card = _find_one(root, tag="a", cls="reservations-card")
    assert card is not None, "Missing a.reservations-card"
    assert card["attrs"].get("href") == "/web/reservations"
    main = _find_one(card, cls="reservations-card-main")
    assert main is not None, "Missing .reservations-card-main"
    title_el = _find_one(main, cls="reservations-title")
    hint_el = _find_one(main, cls="reservations-card-hint")
    badge_el = _find_one(card, cls="reservations-badge")
    assert title_el is not None and _collect_text(title_el) == t("web.reservations.title", locale)
    assert hint_el is not None and _collect_text(hint_el), "Missing .reservations-card-hint"
    assert badge_el is not None and _collect_text(badge_el) == "3"

    card_idx = next(i for i, c in enumerate(root["children"]) if "reservations-card" in _classes(c))
    first_sec_idx = next(
        i for i, c in enumerate(root["children"]) if "wishlist-section" in _classes(c)
    )
    assert card_idx < first_sec_idx

    fail_res = _run_node(
        js_source,
        i18n_json,
        {"locale": locale, "reservationsCardStatus": 500},
    )
    assert fail_res["status"] == ""
    assert _find_one(fail_res["root"], cls="reservations-card") is None
    assert len(_find_all(fail_res["root"], cls="wishlist-section")) == 3


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_home_navigation_startapp_create_focus_and_preserved_script_contracts(
    tmp_path: Path, locale: str
) -> None:
    """startapp=create focuses Create without creating a list; nav transitions and AST hold."""
    js_source, i18n_json = _load_miniapp_assets(tmp_path)
    assert test_reservations_cabinet_ui.home_script_problems(js_source) == []

    create_focus = _run_node(
        js_source,
        i18n_json,
        {"locale": locale, "startParam": "create"},
    )
    assert not any(
        r["method"] == "POST" and r["url"] == "/api/wishlists" for r in create_focus["requests"]
    )
    focused = create_focus["focusedEl"]
    assert focused is not None and focused["tag"] == "BUTTON"
    assert _collect_text(focused) == t("miniapp.home.create_wishlist", locale)

    clicked_create = _run_node(
        js_source,
        i18n_json,
        {"locale": locale, "clickNavButtonIndex": 0},
    )
    assert not any(
        r["method"] == "POST" and r["url"] == "/api/wishlists" for r in clicked_create["requests"]
    ), "WISHENKA-296: Create wishlist opens a form and sends nothing"
    assert _find_one(clicked_create["root"], tag="form") is not None

    clicked_history = _run_node(
        js_source,
        i18n_json,
        {"locale": locale, "clickNavButtonIndex": 1},
    )
    assert any(
        r["method"] == "GET" and r["url"] == "/api/history" for r in clicked_history["requests"]
    )
    hist_h1 = _find_one(clicked_history["root"], tag="h1")
    assert hist_h1 is not None and _collect_text(hist_h1) == t("miniapp.history.title", locale)
