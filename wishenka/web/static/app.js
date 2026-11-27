/**
 * Global application wiring: CSRF token preparation, HTMX reservation and modal
 * lifecycle hooks, wish card/cabinet refreshes, and delegated modal/preview actions.
 *
 * Classic script (loaded with `defer` after htmx and before `wishlist.js`).
 * Exposes `window.prepareCsrf` for pages (such as `/settings`) that invoke it directly,
 * and `window.swapWishCard` so `wishlist.js` can wrap the card swap.
 */
(() => {
  'use strict';

  const CSRF_TIMEOUT_MS = 10000;
  const DEFAULT_QTY_MIN = 1;
  const DEFAULT_QTY_MAX = 1000;

  let csrfToken = '';
  /** @type {Promise<string> | null} */
  let csrfPending = null;
  let csrfGeneration = 0;
  const pendingGiverControls = new WeakSet();
  const pendingLocks = new WeakMap();

  function refreshReservationBadge() {
    const badge = document.querySelector('.reservations-badge');
    if (!badge) return;
    fetch('/web/reservations/card', { credentials: 'same-origin' })
      .then((response) => response.ok ? response.text() : '')
      .then((markup) => {
        const parsed = new DOMParser().parseFromString(markup, 'text/html');
        const updated = parsed.querySelector('.reservations-badge');
        if (updated) badge.textContent = updated.textContent;
      })
      .catch(() => {});
  }

  window.addEventListener('pageshow', (event) => {
    if (event.persisted) refreshReservationBadge();
  });

  /**
   * Fetch and cache a CSRF token for the current session.
   * Deduplicates concurrent requests and resolves to `''` on timeout or error.
   *
   * @returns {Promise<string>} Resolves with the CSRF token or an empty string.
   */
  function prepareCsrf() {
    if (csrfToken) {
      return Promise.resolve(csrfToken);
    }
    if (csrfPending) {
      return csrfPending;
    }
    const controller = new AbortController();
    const generation = csrfGeneration;
    let timer;
    const deadline = new Promise((resolve) => {
      timer = setTimeout(() => {
        controller.abort();
        resolve('');
      }, CSRF_TIMEOUT_MS);
    });
    const request = fetch('/api/auth/csrf', {
      credentials: 'same-origin',
      signal: controller.signal,
    })
      .then((response) => (response.ok ? response.json() : {}))
      .then((body) => (typeof body.csrf_token === 'string' ? body.csrf_token.trim() : ''))
      .catch(() => '');

    csrfPending = Promise.race([request, deadline]).then((token) => {
      clearTimeout(timer);
      if (generation === csrfGeneration) {
        csrfToken = token;
        window.csrfToken = token;
      }
      csrfPending = null;
      return token;
    });
    return csrfPending;
  }

  /**
   * Display a localized preparation error inside the wish card's busy slot.
   *
   * @param {Element | null} card - The `.item-card` element.
   * @returns {void}
   */
  function giverPreparationError(card) {
    const slot = card && card.querySelector('[data-giver-busy]');
    if (slot) {
      slot.hidden = false;
      slot.textContent =
        document.body.getAttribute('data-i18n-prepare-error') ||
        'Could not prepare the request. Please try again.';
    }
  }

  /**
   * Check whether an element or any ancestor configures HTMX `noHeaders`.
   *
   * @param {Element | null} elt - Starting DOM element.
   * @returns {boolean} True if `noHeaders` is enabled or `hx-request` JSON is invalid.
   */
  function requestSuppressesHeaders(elt) {
    for (let node = elt; node && node.getAttribute; node = node.parentElement) {
      const setting = node.getAttribute('hx-request') || node.getAttribute('data-hx-request');
      if (!setting) {
        continue;
      }
      try {
        if (JSON.parse(setting).noHeaders) {
          return true;
        }
      } catch (_) {
        return true;
      }
    }
    return false;
  }

  /**
   * Check whether request headers already include a non-empty `Authorization: Bearer` header.
   *
   * @param {Record<string, string> | null | undefined} headers - Outgoing request headers.
   * @returns {boolean} True if an explicit Bearer token is present.
   */
  function explicitBearer(headers) {
    return Object.keys(headers || {}).some(
      (name) =>
        name.toLowerCase() === 'authorization' &&
        /^Bearer \S/.test(String(headers[name] || '')),
    );
  }

  /**
   * Generate a unique idempotency key for mutating reservation requests.
   *
   * @returns {string} Idempotency key string.
   */
  function nextIdempotencyKey() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return `idem-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }

  /**
   * Walk up from an element to find an `hx-post` or `hx-patch` reservation path.
   *
   * @param {Element | null} elt - Triggering element.
   * @returns {string} Matching reservation path or `''`.
   */
  function reservationRequestPath(elt) {
    let node = elt;
    while (node && node.getAttribute) {
      const path = node.getAttribute('hx-post') || node.getAttribute('hx-patch');
      if (path && path.indexOf('/reservations') !== -1) {
        return path;
      }
      node = node.parentElement;
    }
    return '';
  }

  /**
   * Replace a wish card in the DOM while preserving its expanded/collapsed state.
   *
   * @param {Element} card - Existing `.item-card` element.
   * @param {string} markup - Server-rendered replacement HTML.
   * @returns {void}
   */
  function swapWishCard(card, markup) {
    const summary = card.querySelector('.item-card-summary');
    const wasExpanded = summary.getAttribute('aria-expanded');
    const cardId = card.id;
    card.outerHTML = markup;
    const nextCard = document.getElementById(cardId);
    if (!nextCard) {
      return;
    }
    if (wasExpanded === 'true') {
      const nextSummary = nextCard.querySelector('.item-card-summary');
      const nextDetails = nextCard.querySelector('.item-card-details');
      if (nextSummary) {
        nextSummary.setAttribute('aria-expanded', 'true');
      }
      if (nextDetails) {
        nextDetails.hidden = false;
      }
    }
  }

  window.swapWishCard = swapWishCard;

  /**
   * Parse an integer attribute with a fallback when missing or non-numeric.
   *
   * @param {string | null} raw - Raw attribute value.
   * @param {number} fallback - Default value when parsing fails.
   * @returns {number} Parsed integer or fallback.
   */
  function parseIntOr(raw, fallback) {
    if (raw === null || raw === '') {
      return fallback;
    }
    const parsed = parseInt(raw, 10);
    return Number.isNaN(parsed) ? fallback : parsed;
  }

  /**
   * Handle delegated clicks for `[data-clear-target]` and `[data-qty-step][data-qty-target]`.
   *
   * @param {MouseEvent} evt - Click event.
   * @returns {void}
   */
  function handleDelegatedClick(evt) {
    const target = evt.target instanceof Element ? evt.target : null;
    if (!target) {
      return;
    }

    const clearTrigger = target.closest('[data-clear-target]');
    if (clearTrigger) {
      const selector = clearTrigger.getAttribute('data-clear-target');
      const container = selector ? document.querySelector(selector) : null;
      if (container) {
        container.innerHTML = '';
      }
      return;
    }

    const qtyTrigger = target.closest('[data-qty-step][data-qty-target]');
    if (qtyTrigger) {
      const step = parseInt(qtyTrigger.getAttribute('data-qty-step') || '', 10);
      const inputSelector = qtyTrigger.getAttribute('data-qty-target');
      const input = inputSelector ? document.querySelector(inputSelector) : null;
      if (!input || !('value' in input) || Number.isNaN(step) || step === 0) {
        return;
      }
      const min = parseIntOr(input.getAttribute('min'), DEFAULT_QTY_MIN);
      const max = parseIntOr(input.getAttribute('max'), DEFAULT_QTY_MAX);
      const current = parseIntOr(String(input.value), min);
      const next = Math.min(max, Math.max(min, current + step));
      input.value = String(next);
    }
  }

  /**
   * Keep `--quick-add-clearance` equal to the real height of the fixed quick-add bar, so the
   * last content stays reachable when the bar wraps or shows a preview card.
   *
   * @returns {void}
   */
  function trackQuickAddClearance() {
    const bar = document.getElementById('quick-add-bar');
    if (!bar || typeof ResizeObserver !== 'function') {
      return;
    }
    const root = document.documentElement;
    const update = () => {
      root.style.setProperty('--quick-add-clearance', `${bar.offsetHeight + 16}px`);
    };
    new ResizeObserver(update).observe(bar);
    update();
  }

  window.prepareCsrf = prepareCsrf;
  document.addEventListener('DOMContentLoaded', trackQuickAddClearance);

  document.addEventListener('DOMContentLoaded', () => {
    if (!document.body.hasAttribute('data-viewer-identified')) {
      return;
    }
    prepareCsrf();

    document.addEventListener('htmx:confirm', (evt) => {
      const detail = evt.detail || {};
      const elt = detail.elt;
      const card = elt && elt.closest && elt.closest('.item-card');
      if (!card || !reservationRequestPath(elt) || !detail.issueRequest) {
        return;
      }
      if (csrfToken) {
        return;
      }
      evt.preventDefault();
      if (pendingGiverControls.has(elt)) {
        return;
      }
      pendingGiverControls.add(elt);
      prepareCsrf().then(() => {
        pendingGiverControls.delete(elt);
        if (elt.isConnected && card.isConnected) {
          detail.issueRequest();
        }
      });
    });

    document.addEventListener('htmx:configRequest', (evt) => {
      const verb = String((evt.detail && evt.detail.verb) || '').toUpperCase();
      if (verb === 'GET' || verb === 'HEAD' || verb === 'OPTIONS') {
        return;
      }
      const elt = evt.detail.elt;
      const card = elt && elt.closest && elt.closest('.item-card');
      const resPath = reservationRequestPath(elt);
      const giver = card && resPath;
      const suppressed = giver && requestSuppressesHeaders(elt);
      if (csrfToken && !suppressed) {
        evt.detail.headers['X-CSRF-Token'] = csrfToken;
      }
      if (resPath && !suppressed && !evt.detail.headers['Idempotency-Key']) {
        let idemKey = elt.dataset && elt.dataset.idempotencyKey;
        if (!idemKey) {
          idemKey = nextIdempotencyKey();
          if (elt.dataset) {
            elt.dataset.idempotencyKey = idemKey;
          }
        }
        evt.detail.headers['Idempotency-Key'] = idemKey;
      }
      if (giver && (suppressed || (!csrfToken && !explicitBearer(evt.detail.headers)))) {
        evt.preventDefault();
        giverPreparationError(card);
      }
    });
  });

  /**
   * Undo `htmx:beforeRequest` locking (busy flag, disabled submit controls) for a request.
   *
   * @param {Element | null} elt - Triggering element.
   * @returns {void}
   */
  function releasePending(elt) {
    const locked = elt && pendingLocks.get(elt);
    if (!locked) {
      return;
    }
    pendingLocks.delete(elt);
    elt.removeAttribute('aria-busy');
    locked.forEach((control) => { control.disabled = false; });
  }

  document.addEventListener('htmx:afterRequest', (evt) => {
    const elt = evt.detail.elt;
    releasePending(elt);
    if (!reservationRequestPath(elt)) {
      return;
    }
    const reqXhr = evt.detail.xhr;
    const reqStatus = reqXhr ? reqXhr.status : 0;
    if (elt.dataset && reqStatus !== 0 && reqStatus !== 503) {
      delete elt.dataset.idempotencyKey;
    }

    const row = elt.closest ? elt.closest('.reservation-row') : null;
    if (row) {
      const rowXhr = evt.detail.xhr;
      const rowStatus = rowXhr ? rowXhr.status : 0;
      const busySlot = row.querySelector('[data-reservation-busy]');
      const busyText =
        document.body.getAttribute('data-i18n-busy-error') ||
        'The wish is busy; the reservation was not changed. Please try again.';
      if (rowStatus === 503) {
        if (busySlot) {
          busySlot.hidden = false;
          busySlot.textContent = busyText;
        }
        return;
      }
      let notice = '';
      if (rowStatus === 409) {
        const detail = rowXhr.responseText || '';
        notice = detail.indexOf('available') === -1 ? 'refused' : 'shortage';
      } else if (rowStatus === 401 || rowStatus === 403 || rowStatus === 404) {
        notice = 'refused';
      } else if (rowStatus !== 200 && rowStatus !== 201) {
        return;
      } else if (reservationRequestPath(elt).endsWith('/complete')) {
        notice = 'completed';
        refreshReservationBadge();
      }
      let listUrl = '/web/reservations/list';
      if (notice) {
        listUrl += `?notice=${notice}`;
        const reservationId = row.getAttribute('data-reservation-id');
        if (notice === 'shortage' && reservationId) {
          listUrl += `&reservation_id=${encodeURIComponent(reservationId)}`;
        }
      }
      fetch(listUrl, {
        credentials: 'same-origin',
        headers: { Accept: 'text/html' },
      })
        .then((response) => response.text())
        .then((markup) => {
          const cabinet = document.getElementById('reservations-cabinet');
          if (!cabinet) {
            return;
          }
          cabinet.outerHTML = markup;
          const next = document.getElementById('reservations-cabinet');
          if (next && window.htmx) {
            window.htmx.process(next);
          }
        });
      return;
    }

    const card = elt.closest ? elt.closest('.item-card') : null;
    if (!card) {
      return;
    }
    const xhr = evt.detail.xhr;
    const status = xhr ? xhr.status : 0;
    if (status === 403) {
      let rejection;
      try {
        rejection = JSON.parse(xhr.responseText);
      } catch (_) {
        giverPreparationError(card);
        return;
      }
      if (!rejection || typeof rejection.detail !== 'string') {
        giverPreparationError(card);
        return;
      }
      if (rejection.detail === 'Invalid CSRF token') {
        csrfToken = '';
        window.csrfToken = '';
        csrfGeneration += 1;
        giverPreparationError(card);
        return;
      }
    }
    if (status === 503) {
      const busy = card.querySelector('[data-giver-busy]');
      if (busy) {
        busy.hidden = false;
        busy.textContent =
          document.body.getAttribute('data-i18n-busy-error') ||
          'The wish is busy; the reservation was not changed. Please try again.';
      }
      return;
    }
    let notice = '';
    if (status === 409) {
      const detail = xhr.responseText || '';
      notice = detail.indexOf('available') === -1 ? 'refused' : 'shortage';
    } else if (status === 401 || status === 403 || status === 404) {
      notice = 'refused';
    } else if (status !== 200 && status !== 201) {
      return;
    }
    const wishlistId = card.getAttribute('data-wishlist-id');
    const itemId = card.getAttribute('data-item-id');
    const isFirst = card.getAttribute('data-is-first') === 'true';
    const isLast = card.getAttribute('data-is-last') === 'true';
    let url =
      `/wishlists/${wishlistId}/items/${itemId}/card` +
      `?is_first=${isFirst ? 'true' : 'false'}` +
      `&is_last=${isLast ? 'true' : 'false'}`;
    if (notice) {
      url += `&notice=${notice}`;
    }
    fetch(url, { credentials: 'same-origin', headers: { Accept: 'text/html' } })
      .then((response) => response.text())
      .then((markup) => {
        window.swapWishCard(card, markup);
      });
  });

  document.addEventListener('htmx:beforeSwap', (evt) => {
    const detail = evt.detail || {};
    if (detail.skipSharedDialog) {
      return;
    }
    const xhr = detail.xhr;
    if (!xhr || xhr.status < 400 || typeof xhr.getResponseHeader !== 'function') {
      return;
    }
    if (xhr.getResponseHeader('X-Reorder-Refusal')) {
      return;
    }
    if (detail.elt && reservationRequestPath(detail.elt)) {
      return;
    }
    const contentType = (xhr.getResponseHeader('Content-Type') || '').toLowerCase();
    if (contentType.indexOf('text/html') === -1) {
      return;
    }
    const target = detail.target;
    const targetId = target && target.id ? target.id : '';
    const isModalTarget =
      targetId === 'item-modal-container' ||
      targetId === 'item-edit-sheet' ||
      targetId === 'item-archive-modal';
    const fromModal = !!(
      detail.elt &&
      detail.elt.closest &&
      detail.elt.closest('#item-modal-container')
    );
    const responseText = xhr.responseText || '';
    const isModalOobToList =
      targetId === 'items-list' &&
      responseText.indexOf('id="item-modal-container"') !== -1 &&
      responseText.indexOf('hx-swap-oob') !== -1;
    if (isModalTarget || fromModal || isModalOobToList) {
      detail.shouldSwap = true;
      detail.isError = false;
    }
  });

  /**
   * Swap a broken external product image (`img[data-img-fallback]`) for its
   * pre-rendered sibling `.item-thumbnail-placeholder`.
   *
   * @param {Event} event - Capture-phase error event.
   * @returns {void}
   */
  function handleImageError(event) {
    const target = event && event.target;
    if (!target || target.tagName !== 'IMG' || !target.hasAttribute('data-img-fallback')) {
      return;
    }
    target.hidden = true;
    const parent = target.parentElement;
    const placeholder = parent && parent.querySelector('.item-thumbnail-placeholder');
    if (placeholder) {
      placeholder.hidden = false;
    }
  }

  /**
   * Whether the shared htmx feedback applies to a request. Reservation requests
   * and any trigger inside `[data-own-feedback]` report their own pending and
   * failure state and are left alone.
   *
   * @param {Element | null} elt - Triggering element.
   * @returns {boolean} True when the shared pending/failure feedback should handle it.
   */
  function sharedFeedbackApplies(elt) {
    return !!elt && !!elt.closest && !reservationRequestPath(elt) &&
      !elt.closest('[data-own-feedback]');
  }

  /**
   * Whether a failure of the request is worth a visible message (not a preview or a modal opener).
   *
   * @param {Element} elt - Triggering element.
   * @param {{requestConfig?: {verb?: string}}} detail - htmx event detail.
   * @returns {boolean} True for mutating requests.
   */
  function reportsFailure(elt, detail) {
    const verb = String((detail.requestConfig && detail.requestConfig.verb) || '').toLowerCase();
    return verb !== 'get' && elt.id !== 'quick-add-input';
  }

  /**
   * Show a localized error in the shared `#feedback` region (`role="alert"`).
   *
   * @returns {void}
   */
  function showRequestFailure() {
    const region = document.getElementById('feedback');
    if (!region) {
      return;
    }
    region.textContent =
      document.body.getAttribute('data-i18n-request-failed') ||
      'The request failed. Check the connection and retry.';
    region.setAttribute('data-kind', 'error');
  }

  document.addEventListener('htmx:beforeRequest', (evt) => {
    const elt = evt.detail && evt.detail.elt;
    if (!sharedFeedbackApplies(elt)) {
      return;
    }
    const region = document.getElementById('feedback');
    if (region && reportsFailure(elt, evt.detail)) {
      region.textContent = '';
      region.removeAttribute('data-kind');
    }
    const locked = [];
    elt.setAttribute('aria-busy', 'true');
    if (reportsFailure(elt, evt.detail)) {
      const controls = elt.tagName === 'FORM'
        ? Array.from(elt.querySelectorAll('button[type="submit"]'))
        : [elt];
      controls.filter((control) => control.tagName === 'BUTTON' && !control.disabled)
        .forEach((control) => {
          control.disabled = true;
          locked.push(control);
        });
    }
    pendingLocks.set(elt, locked);
  });

  ['htmx:sendError', 'htmx:timeout', 'htmx:responseError'].forEach((name) => {
    document.addEventListener(name, (evt) => {
      const detail = evt.detail || {};
      const xhr = detail.xhr;
      const marked = xhr && typeof xhr.getResponseHeader === 'function' &&
        xhr.getResponseHeader('X-Reorder-Refusal');
      if (!marked && sharedFeedbackApplies(detail.elt) && reportsFailure(detail.elt, detail)) {
        showRequestFailure();
      }
    });
  });

  document.addEventListener('error', handleImageError, true);
  document.addEventListener('click', handleDelegatedClick);
})();
