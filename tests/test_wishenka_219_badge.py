"""Browser event wiring for the reservation completion badge."""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.timeout(20)


def test_completion_and_cached_home_refresh_badge() -> None:
    """Completion refreshes a visible badge and browser history refreshes a cached home."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable")
    script = r"""
const fs = require('fs');
const vm = require('vm');
const listeners = {};
const badge = {textContent: '2'};
const row = {querySelector: () => null, getAttribute: () => '1'};
const button = {
  dataset: {},
  getAttribute: (key) => key === 'hx-post' ? '/api/reservations/1/complete' : null,
  closest: (selector) => selector === '.reservation-row' ? row : null,
};
const requests = [];
global.window = {addEventListener: (name, fn) => { listeners[name] = fn; }};
global.document = {
  addEventListener: (name, fn) => { listeners[name] = fn; },
  querySelector: () => badge,
  getElementById: () => null,
  body: {getAttribute: () => null},
};
global.DOMParser = class {
  parseFromString(markup) {
    return {querySelector: () => ({textContent: markup})};
  }
};
global.fetch = async (url) => {
  requests.push(url);
  return {ok: true, text: async () => url.includes('/card') ? '1' : ''};
};
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
(async () => {
  listeners['htmx:afterRequest']({detail: {elt: button, xhr: {status: 200}}});
  await new Promise(resolve => setImmediate(resolve));
  if (badge.textContent !== '1' || !requests.includes('/web/reservations/card')) process.exit(1);
  badge.textContent = '2';
  requests.length = 0;
  listeners.pageshow({persisted: true});
  await new Promise(resolve => setImmediate(resolve));
  if (badge.textContent !== '1' || !requests.includes('/web/reservations/card')) process.exit(2);
})().catch(() => process.exit(3));
"""
    path = Path(__file__).resolve().parents[1] / "wishenka/web/static/app.js"
    result = subprocess.run(
        [node, "-e", script, str(path)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
