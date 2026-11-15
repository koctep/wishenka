/**
 * Offline stand-in for htmx used by the wishlist browser tests (WISHENKA-110, extended by
 * WISHENKA-24).
 *
 * Own code, nothing vendored. It implements only `htmx.ajax(verb, url, {target, swap, values})`:
 * the call is recorded in `window.__ajaxCalls`, forwarded to the real server with `fetch`
 * (form-encoded body, arrays as repeated fields like htmx does), and the response HTML is put
 * into the target with an `innerHTML` swap. It does NOT process `hx-*` attributes (except
 * `hx-swap-oob` inside a response), CSRF headers (`htmx:configRequest`), other swap strategies
 * or extensions.
 *
 * WISHENKA-24 additions (all additive, the old contract is kept):
 * - `htmx:beforeSwap` now carries `detail.xhr = {status, responseText, getResponseHeader}`,
 *   `detail.shouldSwap = status < 400` and `detail.isError = status >= 400`. Handlers may change
 *   both; the stub reads them back after the event, as htmx 1.9.12 does.
 * - A response that is not swapped (`shouldSwap === false`) is dropped; when `isError` is still
 *   true afterwards `htmx:responseError` is dispatched on the target (bubbles to `document`).
 * - `swap: 'none'` skips the main swap.
 * - Out-of-band elements (`hx-swap-oob` = `true`, `outerHTML`, `innerHTML`, `beforeend`,
 *   `afterbegin`, `beforebegin`, `afterend`, `delete`, optionally `<style>:<selector>`) are
 *   applied, and removed from the main content, only for an accepted response.
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

  /** Apply every `hx-swap-oob` element of a parsed response and return the remaining markup. */
  const applyOutOfBand = (fragment) => {
    const found = Array.from(fragment.querySelectorAll('[hx-swap-oob]'));
    found.forEach((element) => {
      const raw = (element.getAttribute('hx-swap-oob') || 'true').trim();
      const colon = raw.indexOf(':');
      const style = (colon === -1 ? raw : raw.slice(0, colon)) || 'true';
      const selector = colon === -1 ? '' : raw.slice(colon + 1);
      element.remove();
      const target = selector
        ? document.querySelector(selector)
        : element.id
          ? document.getElementById(element.id)
          : null;
      if (!target) {
        return;
      }
      element.removeAttribute('hx-swap-oob');
      if (style === 'delete') {
        target.remove();
      } else if (style === 'true' || style === 'outerHTML') {
        target.replaceWith(element);
      } else if (style === 'innerHTML') {
        target.replaceChildren(...Array.from(element.childNodes));
      } else if (style === 'beforeend') {
        target.append(...Array.from(element.childNodes));
      } else if (style === 'afterbegin') {
        target.prepend(...Array.from(element.childNodes));
      } else if (style === 'beforebegin') {
        target.before(...Array.from(element.childNodes));
      } else if (style === 'afterend') {
        target.after(...Array.from(element.childNodes));
      }
    });
    const holder = document.createElement('div');
    holder.append(fragment.cloneNode(true));
    return holder.innerHTML;
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
      .then((response) => response.text().then((html) => ({ response, html })))
      .then(({ response, html }) => {
        const target = resolveTarget(opts.target);
        if (!target) {
          return;
        }
        const detail = {
          target,
          xhr: {
            status: response.status,
            responseText: html,
            getResponseHeader: (name) => response.headers.get(name),
          },
          shouldSwap: response.status < 400,
          isError: response.status >= 400,
        };
        target.dispatchEvent(
          new CustomEvent('htmx:beforeSwap', { bubbles: true, cancelable: true, detail }),
        );
        if (!detail.shouldSwap) {
          if (detail.isError) {
            target.dispatchEvent(
              new CustomEvent('htmx:responseError', { bubbles: true, detail }),
            );
          }
          return;
        }
        const template = document.createElement('template');
        template.innerHTML = html;
        const rest = applyOutOfBand(template.content);
        if (opts.swap !== 'none') {
          target.innerHTML = rest;
        }
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
