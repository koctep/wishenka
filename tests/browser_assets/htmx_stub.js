/**
 * Offline stand-in for htmx used by the wishlist browser tests (WISHENKA-110).
 *
 * Own code, nothing vendored. It implements only `htmx.ajax(verb, url, {target, swap, values})`:
 * the call is recorded in `window.__ajaxCalls`, forwarded to the real server with `fetch`
 * (form-encoded body, arrays as repeated fields like htmx does), and the response HTML is put
 * into the target with an `innerHTML` swap. It does NOT process `hx-*` attributes, CSRF headers
 * (`htmx:configRequest`), other swap strategies or extensions.
 */
(() => {
  'use strict';

  window.__ajaxCalls = [];
  window.__ajaxPending = 0;

  const resolveTarget = (target) =>
    typeof target === 'string' ? document.querySelector(target) : target || null;

  const encodeValues = (values) => {
    const body = new URLSearchParams();
    Object.entries(values || {}).forEach(([name, value]) => {
      (Array.isArray(value) ? value : [value]).forEach((item) => body.append(name, String(item)));
    });
    return body;
  };

  const ajax = (verb, url, options) => {
    const opts = options || {};
    const values = JSON.parse(JSON.stringify(opts.values || {}));
    window.__ajaxCalls.push({
      verb,
      url,
      target: typeof opts.target === 'string' ? opts.target : null,
      swap: opts.swap || null,
      values,
    });
    window.__ajaxPending += 1;
    const init = {
      method: verb,
      headers: { 'HX-Request': 'true' },
    };
    if (verb !== 'GET') {
      init.headers['Content-Type'] = 'application/x-www-form-urlencoded';
      init.body = encodeValues(values).toString();
    }
    return fetch(url, init)
      .then((response) => response.text())
      .then((html) => {
        const target = resolveTarget(opts.target);
        if (!target) {
          return;
        }
        target.dispatchEvent(
          new CustomEvent('htmx:beforeSwap', { bubbles: true, cancelable: true, detail: { target } }),
        );
        target.innerHTML = html;
        target.dispatchEvent(new CustomEvent('htmx:afterSwap', { bubbles: true, detail: { target } }));
      })
      .catch((error) => {
        console.error('htmx stub: request failed', error);
      })
      .finally(() => {
        window.__ajaxPending -= 1;
      });
  };

  // A plain assignment keeps the property configurable, so tests can `delete window.htmx`.
  window.htmx = { version: 'stub', ajax };
})();
