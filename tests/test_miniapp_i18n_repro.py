"""Failing repro tests for WISHENKA-73: centralized Mini App i18n and full RU/EN UI."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from tests.test_i18n_sync import _has_cyrillic, _make_settings
from wishenka.i18n import CATALOG
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(20)

_SCRIPT_TAG_RE = re.compile(
    r'<script\s+id=["\']miniapp-i18n["\']\s+type=["\']application/json["\']\s*>(.*?)</script>',
    re.DOTALL,
)

_NODE_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const { jsSource, i18nJson, scenario } = payload;

function makeEl(tag) {
  const el = {
    tagName: String(tag || '').toUpperCase(),
    textContent: '',
    value: '',
    dataset: {},
    attributes: {},
    children: [],
    listeners: {},
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name] ?? null; },
    append(...nodes) {
      for (const n of nodes) {
        if (typeof n === 'string') {
          this.children.push({ tagName: '#TEXT', textContent: n, children: [], attributes: {} });
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
      if (sel === 'button') return this.children.find(c => c.tagName === 'BUTTON') || null;
      if (sel === '.wishlist-section') {
        return (
          this.children.find(c => (c.attributes?.class || '').includes('wishlist-section')) || null
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
    focus() {},
  };
  return el;
}

function collectText(node) {
  if (!node) return '';
  let out = node.textContent ? [String(node.textContent)] : [];
  if (node.attributes && node.attributes['aria-label']) {
    out.push(String(node.attributes['aria-label']));
  }
  for (const child of (node.children || [])) {
    const t = collectText(child);
    if (t) out.push(t);
  }
  return out.join(' | ');
}

function findButtons(node, acc = []) {
  if (!node) return acc;
  if (node.tagName === 'BUTTON') acc.push(node);
  for (const child of (node.children || [])) findButtons(child, acc);
  return acc;
}

const rootEl = makeEl('main');
rootEl.dataset = {
  locale: scenario.datasetLocale ?? 'en',
  bot: 'wishenka_bot',
  miniapp: 'app',
};
const statusEl = makeEl('p');
const i18nEl = makeEl('script');
i18nEl.textContent = i18nJson;
const htmlEl = { lang: scenario.htmlLang ?? scenario.datasetLocale ?? 'en' };
const headEl = { append() {} };

const resolvedLocale = scenario.profileLocale || scenario.datasetLocale || 'en';
const apiResponses = {
  '/api/auth/me': { ok: !scenario.authMeFails, data: { locale: resolvedLocale } },
  '/api/auth/telegram': { ok: !scenario.authTgFails, data: { locale: resolvedLocale } },
  '/api/auth/csrf': { ok: true, data: { csrf_token: 'csrf-123' } },
  '/api/wishlists': { ok: true, data: scenario.wishlists || [] },
  '/api/favorites': { ok: true, data: [] },
  '/api/history': { ok: true, data: scenario.history || [] },
  '/api/wishlists/1': { ok: true, data: scenario.wishlistDetail || {} },
  '/api/public/wishlists/tok/view': { ok: true, data: scenario.publicWishlist || {} },
  '/api/invitations/preview': { ok: true, data: { name: 'Birthday' } },
};

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
  URLSearchParams,
  encodeURIComponent,
  setTimeout: (fn, _ms) => { if (typeof fn === 'function') fn(); return 0; },
  navigator: {
    language: scenario.navigatorLanguage || 'en-US',
    clipboard: { writeText: async () => {} },
  },
  location: { search: scenario.search || '' },
  DOMParser: class {
    parseFromString() { return { querySelector: () => null }; }
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
  fetch: async (url, _opts) => {
    if (url === '/web/reservations/card') {
      return { ok: false, text: async () => '' };
    }
    const entry = apiResponses[url];
    if (!entry || !entry.ok) {
      return { ok: false, status: 401, json: async () => ({}) };
    }
    return { ok: true, status: 200, json: async () => entry.data };
  },
  window: {
    crypto: { randomUUID: () => 'uuid-test-1' },
    Telegram: {
      WebApp: {
        initData: scenario.initData !== undefined ? scenario.initData : 'signed_init_data',
        initDataUnsafe: {
          start_param: scenario.startParam || '',
          user: scenario.tgLanguageCode ? { language_code: scenario.tgLanguageCode } : {},
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
  // Let initial start() settle.
  await new Promise(r => setImmediate(r));
  await new Promise(r => setImmediate(r));

  const out = {};
  if (scenario.action === 'roles') {
    out.roles = {
      owner: sandbox.roleLabel('owner'),
      admin: sandbox.roleLabel('admin'),
      member: sandbox.roleLabel('member'),
      favorite: sandbox.roleLabel('favorite'),
      unknown: sandbox.roleLabel('custom_role'),
    };
  } else if (scenario.action === 'home') {
    await sandbox.showHome();
    out.rootText = collectText(rootEl);
    out.statusText = statusEl.textContent;
  } else if (scenario.action === 'history') {
    await sandbox.showHistory();
    out.rootText = collectText(rootEl);
    out.statusText = statusEl.textContent;
  } else if (scenario.action === 'list') {
    await sandbox.showList(1);
    out.rootText = collectText(rootEl);
    out.statusText = statusEl.textContent;
  } else if (scenario.action === 'public') {
    await sandbox.publicView('tok');
    out.rootText = collectText(rootEl);
    out.statusText = statusEl.textContent;
  } else if (scenario.action === 'invitation') {
    await sandbox.invitationView('tok');
    out.rootText = collectText(rootEl);
    out.statusText = statusEl.textContent;
  } else if (scenario.action === 'unavailable_guest') {
    sandbox.unavailableLink();
    out.rootText = collectText(rootEl);
    const btns = findButtons(rootEl);
    if (btns.length > 0) {
      await btns[0].click();
    }
    out.statusAfterClick = statusEl.textContent;
  }
  process.stdout.write(JSON.stringify(out));
})().catch(err => {
  process.stderr.write(String(err && err.stack ? err.stack : err));
  process.exit(1);
});
"""


def _extract_miniapp_i18n_json(html: str) -> str:
    match = _SCRIPT_TAG_RE.search(html)
    return match.group(1) if match else ""


def _run_node_scenario(js_source: str, i18n_json: str, scenario: dict[str, Any]) -> dict[str, Any]:
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


def test_miniapp_shell_embeds_i18n_catalog_json(tmp_path: Path) -> None:
    """GET / embeds centralized EN+RU catalog JSON in #miniapp-i18n without unsafe-inline CSP."""
    app = create_app(_make_settings(tmp_path / "shell_i18n.db"))
    with TestClient(app) as client:
        resp = client.get("/", headers={"Accept-Language": "ru"})
        assert resp.status_code == 200
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "'unsafe-inline'" not in csp

        raw_json = _extract_miniapp_i18n_json(resp.text)
        assert raw_json, "GET / must embed <script id='miniapp-i18n' type='application/json'>"
        payload = json.loads(raw_json)
        assert set(payload.keys()) == {"en", "ru"}
        for locale in ("en", "ru"):
            expected_keys = {k for k in CATALOG[locale] if k.startswith(("nav.", "miniapp."))}
            assert expected_keys <= set(payload[locale].keys())
            assert any(k.startswith("miniapp.") for k in payload[locale]), (
                "Centralized catalog must include miniapp.* keys"
            )
            for key in expected_keys:
                assert payload[locale][key] == CATALOG[locale][key]


def test_miniapp_js_has_no_hardcoded_home_i18n_or_russian_role_labels(tmp_path: Path) -> None:
    """miniapp.js must not duplicate translations in HOME_I18N or hardcode Russian role labels."""
    app = create_app(_make_settings(tmp_path / "js_static.db"))
    with TestClient(app) as client:
        resp = client.get("/static/miniapp.js")
        assert resp.status_code == 200
        source = resp.text

        assert "HOME_I18N" not in source, "miniapp.js must remove duplicate HOME_I18N dictionary"
        assert "homeText" not in source, "miniapp.js must use centralized t() instead of homeText()"
        for hardcoded_ru in ("'Владелец'", "'Администратор'", "'Соавтор'", "'Избранное'"):
            assert hardcoded_ru not in source, (
                f"miniapp.js must not hardcode Russian role label {hardcoded_ru}"
            )


def test_miniapp_js_renders_all_screens_in_ru_and_en_via_node(tmp_path: Path) -> None:
    """Running miniapp.js in isolated Node VM renders roles and all screens in RU and EN."""
    app = create_app(_make_settings(tmp_path / "js_vm.db"))
    with TestClient(app) as client:
        html_resp = client.get("/", headers={"Accept-Language": "en"})
        js_resp = client.get("/static/miniapp.js")
        assert html_resp.status_code == 200
        assert js_resp.status_code == 200
        i18n_json = _extract_miniapp_i18n_json(html_resp.text)
        js_source = js_resp.text

    # 1. roleLabel in EN must not return Russian strings, and in RU must return Russian strings.
    roles_en = _run_node_scenario(
        js_source, i18n_json, {"action": "roles", "datasetLocale": "en", "profileLocale": "en"}
    )["roles"]
    assert not _has_cyrillic(roles_en["owner"]), f"EN owner role leaked Cyrillic: {roles_en}"
    assert roles_en["owner"] == "Owner"
    assert roles_en["admin"] == "Admin"
    assert roles_en["member"] == "Collaborator"
    assert roles_en["favorite"] == "Favorite"
    assert roles_en["unknown"] == "custom_role"

    roles_ru = _run_node_scenario(
        js_source, i18n_json, {"action": "roles", "datasetLocale": "ru", "profileLocale": "ru"}
    )["roles"]
    assert _has_cyrillic(roles_ru["owner"])
    assert _has_cyrillic(roles_ru["admin"])
    assert _has_cyrillic(roles_ru["member"])
    assert _has_cyrillic(roles_ru["favorite"])

    # 2. showHistory in RU must not render hardcoded English strings.
    history_ru = _run_node_scenario(
        js_source,
        i18n_json,
        {
            "action": "history",
            "datasetLocale": "ru",
            "profileLocale": "ru",
            "history": [
                {
                    "id": 1,
                    "name": "ДР",
                    "viewed_at": "2026-05-01T12:00:00Z",
                    "role": "member",
                }
            ],
        },
    )
    for forbidden_en in ("Viewing history", "Clear history", "Back", "Viewed:"):
        assert forbidden_en not in history_ru["rootText"], (
            f"RU history screen leaked English '{forbidden_en}': {history_ru['rootText']}"
        )
    assert _has_cyrillic(history_ru["rootText"])

    # 3. showList in RU must translate settings form, member controls, share panel, and wishes stub.
    list_ru = _run_node_scenario(
        js_source,
        i18n_json,
        {
            "action": "list",
            "datasetLocale": "ru",
            "profileLocale": "ru",
            "wishlistDetail": {
                "id": 1,
                "name": "Праздник",
                "description": "",
                "status": "active",
                "role": "owner",
                "share_token": "share_tok",
                "invite_token": "inv_tok",
                "members": [{"user_id": 2, "display_name": "Alex", "role": "member"}],
                "items": [],
            },
        },
    )
    for forbidden_en in (
        "Back",
        "Wishes",
        "Save settings",
        "Manage members",
        "Copy link",
        "Share via Telegram",
        "Public gift-selection link",
        "Replace public link",
        "Collaborator invitation",
        "Revoke invitation",
    ):
        assert forbidden_en not in list_ru["rootText"], (
            f"RU list screen leaked English '{forbidden_en}': {list_ru['rootText']}"
        )

    # 4. publicView in RU must translate Reserve button and share panel.
    public_ru = _run_node_scenario(
        js_source,
        i18n_json,
        {
            "action": "public",
            "datasetLocale": "ru",
            "profileLocale": "ru",
            "publicWishlist": {
                "title": "Список",
                "description": "",
                "identified": True,
                "status": "active",
                "items": [
                    {
                        "id": 10,
                        "title": "Книга",
                        "is_recipient": False,
                        "is_archived": False,
                        "is_fully_received": False,
                        "is_reserved_by_me": False,
                        "available_quantity": 1,
                    }
                ],
            },
        },
    )
    for forbidden_en in ("Reserve", "Public gift-selection link", "Copy link"):
        assert forbidden_en not in public_ru["rootText"], (
            f"RU public view leaked English '{forbidden_en}': {public_ru['rootText']}"
        )

    # 5. invitationView in RU must translate heading, prompt with wishlist name, and confirm button.
    invite_ru = _run_node_scenario(
        js_source,
        i18n_json,
        {"action": "invitation", "datasetLocale": "ru", "profileLocale": "ru"},
    )
    for forbidden_en in ("Collaborator invitation", "Confirm joining", "as a member?"):
        assert forbidden_en not in invite_ru["rootText"], (
            f"RU invitation view leaked English '{forbidden_en}': {invite_ru['rootText']}"
        )
    assert "Birthday" in invite_ru["rootText"]

    # 6. unavailableLink in guest mode (Telegram user language_code=ru) must localize auth error.
    guest_ru = _run_node_scenario(
        js_source,
        i18n_json,
        {
            "action": "unavailable_guest",
            "datasetLocale": "en",
            "htmlLang": "en",
            "tgLanguageCode": "ru",
            "initData": "",
            "authMeFails": True,
            "authTgFails": True,
        },
    )
    assert _has_cyrillic(guest_ru["rootText"])
    assert "Open this app in Telegram to sign in." not in guest_ru["statusAfterClick"]
    assert _has_cyrillic(guest_ru["statusAfterClick"])

    # 7. Unsupported locale falls back safely to EN without Cyrillic.
    fallback_fr = _run_node_scenario(
        js_source,
        i18n_json,
        {
            "action": "home",
            "datasetLocale": "fr",
            "htmlLang": "fr",
            "profileLocale": "fr",
        },
    )
    assert not _has_cyrillic(fallback_fr["rootText"])
    assert "Wishlists" in fallback_fr["rootText"]
