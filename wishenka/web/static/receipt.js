/**
 * Receipt dialog behaviour (WISHENKA-24): quantity summary, dismissal, focus handling.
 *
 * Classic script (loaded with `defer` after htmx and `wishlist.js`); everything lives inside an
 * IIFE and uses delegated listeners on `document`, so it also works for dialogs that htmx swaps
 * in later. All texts are set with `textContent`; nothing here writes server markup.
 */
(() => {
  'use strict';

  const MODAL_SELECTOR = '#item-receipt-modal';
  const CONTAINER_ID = 'item-modal-container';
  const OPENER_SELECTOR = '.btn-receipt-item';
  const CARD_SELECTOR = '.item-card';
  const CARD_SUMMARY_SELECTOR = '.item-card-summary';
  const FEEDBACK_ID = 'receipt-feedback';
  const REFUSAL_HEADER = 'X-Receipt-Refusal';
  const DEFAULT_GENERIC_FAILURE = 'Could not save the receipt. Please try again.';
  const DEFAULT_SUMMARY_TEMPLATE = 'Will mark as received: {chosen} pcs. of {remaining} remaining';
  /** Closed set of refusal reasons the server marks (mirrors the JSON route table plus busy). */
  const REFUSAL_REASONS = new Set([
    'quantity_invalid',
    'quantity_above_remaining',
    'wish_archived',
    'wishlist_not_active',
    'nothing_remaining',
    'forbidden',
    'not_found',
    'busy',
  ]);

  /** Id of the card whose «Получено» button opened the dialog, or an empty string. */
  let openerCardId = '';

  /**
   * Closest ancestor (or the node itself) matching a selector.
   * @param {EventTarget | null} node Event target.
   * @param {string} selector CSS selector.
   * @returns {Element | null} The match or null.
   */
  const closest = (node, selector) => (node && node.closest ? node.closest(selector) : null);

  /**
   * Remove the dialog without a request and return focus to the card that opened it.
   * @returns {void}
   */
  const closeDialog = () => {
    const container = document.getElementById(CONTAINER_ID);
    if (container) {
      container.replaceChildren();
    }
    const card = openerCardId ? document.getElementById(openerCardId) : null;
    const summary = card ? card.querySelector(CARD_SUMMARY_SELECTOR) : null;
    openerCardId = '';
    if (summary) {
      summary.focus();
    }
  };

  /**
   * Show the chosen quantity in the summary line of the dialog.
   * @param {HTMLSelectElement} select The `[data-receipt-quantity]` control.
   * @returns {void}
   */
  const updateSummary = (select) => {
    const remaining = Number.parseInt(select.getAttribute('data-remaining') || '', 10);
    const chosen = Number.parseInt(select.value, 10);
    const modal = closest(select, MODAL_SELECTOR);
    const line = modal ? modal.querySelector('[data-receipt-summary]') : null;
    if (!line || !Number.isInteger(remaining) || !Number.isInteger(chosen)) {
      return;
    }
    const quantity = Math.min(Math.max(chosen, 1), remaining);
    select.value = String(quantity);
    const tpl = (document.body && document.body.getAttribute('data-i18n-receipt-summary'))
      || DEFAULT_SUMMARY_TEMPLATE;
    line.textContent = tpl
      .replace('{chosen}', String(quantity))
      .replace('{remaining}', String(remaining));
  };

  document.addEventListener('change', (event) => {
    const select = closest(event.target, '[data-receipt-quantity]');
    if (select) {
      updateSummary(select);
    }
  });

  document.addEventListener('click', (event) => {
    const opener = closest(event.target, OPENER_SELECTOR);
    if (opener) {
      const card = closest(opener, CARD_SELECTOR);
      openerCardId = card ? card.id : '';
      return;
    }
    const modal = closest(event.target, MODAL_SELECTOR);
    if (modal && (event.target === modal || closest(event.target, '[data-modal-close]'))) {
      closeDialog();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && document.querySelector(MODAL_SELECTOR)) {
      closeDialog();
    }
  });

  /**
   * Leave the busy state and, when no answer of this attempt reached the page, say so.
   * The feedback region was emptied when the attempt started, so an empty region means that
   * neither a refusal sentence nor a list update arrived. A form that left the document was
   * replaced by the response (closed or re-rendered dialog) and needs nothing.
   * @param {HTMLFormElement} form The submitted form.
   * @returns {void}
   */
  const finishAttempt = (form) => {
    if (!document.contains(form)) {
      return;
    }
    form.dataset.pending = 'false';
    form.removeAttribute('aria-busy');
    const button = form.querySelector('.btn-receipt-confirm');
    if (button) {
      button.disabled = false;
    }
    const feedback = document.getElementById(FEEDBACK_ID);
    if (feedback && feedback.textContent.trim() === '') {
      feedback.textContent = (document.body && document.body.getAttribute('data-i18n-receipt-failure'))
        || DEFAULT_GENERIC_FAILURE;
    }
  };

  /**
   * Send the chosen quantity (the only field) once; further submits wait for the answer.
   * This is the only place of this script that calls `htmx.ajax`; htmx adds the CSRF header.
   * @param {HTMLFormElement} form The `form[data-receipt-form]`.
   * @returns {void}
   */
  const submitReceipt = (form) => {
    if (form.dataset.pending === 'true') {
      return;
    }
    form.dataset.pending = 'true';
    form.setAttribute('aria-busy', 'true');
    const button = form.querySelector('.btn-receipt-confirm');
    if (button) {
      button.disabled = true;
    }
    const feedback = document.getElementById(FEEDBACK_ID);
    if (feedback) {
      feedback.textContent = '';
    }
    const field = form.elements.namedItem('quantity');
    const qty = field ? field.value : '';
    let idemKey = form.dataset.idempotencyKey;
    if (!idemKey || form.dataset.idempotencyQty !== qty) {
      idemKey =
        window.crypto && typeof window.crypto.randomUUID === 'function'
          ? window.crypto.randomUUID()
          : `idem-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
      form.dataset.idempotencyKey = idemKey;
      form.dataset.idempotencyQty = qty;
    }
    const done = () => finishAttempt(form);
    new Promise((resolve) => {
      resolve(
        window.htmx.ajax('POST', form.getAttribute('action'), {
          target: `#${FEEDBACK_ID}`,
          swap: 'none',
          values: { quantity: qty },
          headers: { 'Idempotency-Key': idemKey },
        }),
      );
    }).then(done, done);
  };

  document.addEventListener('htmx:afterRequest', (event) => {
    const detail = event.detail;
    const form = detail && closest(detail.elt, 'form[data-receipt-form]');
    if (!form) {
      return;
    }
    const status = detail.xhr ? detail.xhr.status : 0;
    if (status !== 0 && status !== 503) {
      delete form.dataset.idempotencyKey;
      delete form.dataset.idempotencyQty;
    }
  });

  document.addEventListener('submit', (event) => {
    const form = closest(event.target, 'form[data-receipt-form]');
    if (form) {
      event.preventDefault();
      submitReceipt(form);
    }
  });

  document.addEventListener('htmx:beforeSwap', (event) => {
    const detail = event.detail;
    if (!detail || !detail.xhr || typeof detail.xhr.getResponseHeader !== 'function') {
      return;
    }
    if (REFUSAL_REASONS.has(detail.xhr.getResponseHeader(REFUSAL_HEADER))) {
      detail.shouldSwap = true;
      detail.isError = false;
    }
  });

  document.addEventListener('htmx:afterSwap', (event) => {
    const target = event.detail && event.detail.target;
    if (!target || target.id !== CONTAINER_ID) {
      return;
    }
    const first = target.querySelector(
      '[data-receipt-modal] [data-receipt-quantity], .btn-receipt-confirm, [data-modal-close]',
    );
    if (first) {
      first.focus();
    }
  });
})();
