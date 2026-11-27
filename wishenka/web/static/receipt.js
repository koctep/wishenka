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
  const OPENER_SELECTOR = '.btn-receipt-item, .btn-receipt-edit, .btn-receipt-cancel';
  const CARD_SELECTOR = '.item-card';
  const CARD_SUMMARY_SELECTOR = '.item-card-summary';
  const GIFTED_ITEM_SELECTOR = '.gifted-item';
  const LIST_NOTICE_SELECTOR = '#list-notice';
  const GIFTED_DETAILS_SELECTOR = '#gifted-items-section details.gifted-items-details';
  const GIFTED_SUMMARY_SELECTOR = `${GIFTED_DETAILS_SELECTOR} > summary`;
  const FEEDBACK_ID = 'receipt-feedback';
  const REFUSAL_HEADER = 'X-Receipt-Refusal';
  const INERT_MARKER = 'data-receipt-inert';
  const HIDDEN_MARKER = 'data-receipt-hidden';
  const FOCUSABLE_SELECTOR = [
    'a[href]',
    'button:not(:disabled)',
    'input:not([type="hidden"]):not(:disabled)',
    'select:not(:disabled)',
    'textarea:not(:disabled)',
    '[tabindex]:not([tabindex="-1"])',
  ].join(', ');
  const PRIMARY_CONTROL_SELECTOR = [
    '[data-receipt-modal] [data-receipt-quantity]',
    '[data-receipt-modal] #receipt-edit-quantity',
    '[data-receipt-modal] .btn-receipt-confirm',
    '[data-receipt-modal] [data-modal-close]',
  ].join(', ');
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
    'receipt_not_found',
    'busy',
  ]);

  /** Id of the card whose «Получено» button opened the dialog, or an empty string. */
  let openerCardId = '';
  /** Id of the `.gifted-item` whose edit/cancel button opened the dialog, or an empty string. */
  let openerGiftedItemId = '';
  /** Element that opened the dialog when no item card owns it (e.g. gifted list actions). */
  let openerElement = null;

  /**
   * Closest ancestor (or the node itself) matching a selector.
   * @param {EventTarget | null} node Event target.
   * @param {string} selector CSS selector.
   * @returns {Element | null} The match or null.
   */
  const closest = (node, selector) => (node && node.closest ? node.closest(selector) : null);

  /**
   * Toggle `inert` and `aria-hidden` on all non-ancestor siblings of `#item-modal-container`
   * up to `document.body`, so keyboard and assistive technology stay inside the open dialog.
   * @param {boolean} active True to isolate background content, false to restore.
   * @returns {void}
   */
  const setBackgroundInert = (active) => {
    if (!active) {
      for (const el of document.querySelectorAll(`[${INERT_MARKER}]`)) {
        el.inert = false;
        el.removeAttribute(INERT_MARKER);
      }
      for (const el of document.querySelectorAll(`[${HIDDEN_MARKER}]`)) {
        el.removeAttribute('aria-hidden');
        el.removeAttribute(HIDDEN_MARKER);
      }
      return;
    }
    let current = document.getElementById(CONTAINER_ID);
    while (current && current !== document.body) {
      const parent = current.parentElement;
      if (!parent) {
        break;
      }
      for (const sibling of parent.children) {
        if (sibling === current) {
          continue;
        }
        const tag = sibling.tagName;
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'TEMPLATE') {
          continue;
        }
        if (!sibling.inert) {
          sibling.inert = true;
          sibling.setAttribute(INERT_MARKER, 'true');
        }
        if (!sibling.hasAttribute('aria-hidden')) {
          sibling.setAttribute('aria-hidden', 'true');
          sibling.setAttribute(HIDDEN_MARKER, 'true');
        }
      }
      current = parent;
    }
  };

  /**
   * Visible, enabled focusable descendants inside the open modal.
   * @param {Element} modal The `#item-receipt-modal` element.
   * @returns {HTMLElement[]} Ordered focusable elements.
   */
  const getFocusable = (modal) =>
    Array.from(modal.querySelectorAll(FOCUSABLE_SELECTOR)).filter(
      (el) => el instanceof HTMLElement && el.getClientRects().length > 0,
    );

  /**
   * Focus the feedback banner when non-empty, otherwise the primary interactive control.
   * @returns {void}
   */
  const focusDialog = () => {
    const feedback = document.getElementById(FEEDBACK_ID);
    if (feedback && feedback.textContent.trim() !== '') {
      if (!feedback.hasAttribute('tabindex')) {
        feedback.setAttribute('tabindex', '-1');
      }
      feedback.focus();
      return;
    }
    const first = document.querySelector(PRIMARY_CONTROL_SELECTOR);
    if (first && typeof first.focus === 'function') {
      first.focus();
    }
  };

  /**
   * Return focus to the originating wish card, gifted item/summary, opener control, or list notice.
   * @returns {void}
   */
  const restoreFocusToPage = () => {
    const card = openerCardId ? document.getElementById(openerCardId) : null;
    const cardSummary = card ? card.querySelector(CARD_SUMMARY_SELECTOR) : null;
    const fallbackOpener = openerElement && openerElement.isConnected ? openerElement : null;
    const giftedItem = openerGiftedItemId ? document.getElementById(openerGiftedItemId) : null;
    const giftedSummary = openerGiftedItemId
      ? document.querySelector(GIFTED_SUMMARY_SELECTOR)
      : null;
    const notice = document.querySelector(LIST_NOTICE_SELECTOR);
    const target = openerGiftedItemId
      ? fallbackOpener || giftedItem || giftedSummary || notice
      : cardSummary || fallbackOpener || notice;
    openerCardId = '';
    openerGiftedItemId = '';
    openerElement = null;
    if (target && typeof target.focus === 'function') {
      if ((target === notice || target === giftedItem) && !target.hasAttribute('tabindex')) {
        target.setAttribute('tabindex', '-1');
      }
      target.focus();
    }
  };

  /**
   * Remove the dialog without a request and return focus to the card that opened it.
   * @returns {void}
   */
  const closeDialog = () => {
    const container = document.getElementById(CONTAINER_ID);
    if (container) {
      container.replaceChildren();
    }
    setBackgroundInert(false);
    restoreFocusToPage();
  };

  /**
   * Clamp quantity when requested and update the summary line if present in the dialog.
   * @param {HTMLSelectElement | HTMLInputElement} field The `[data-receipt-quantity]` control.
   * @param {boolean} clampValue Whether to clamp out-of-range values back into the field.
   * @returns {void}
   */
  const updateSummary = (field, clampValue) => {
    const remaining = Number.parseInt(field.getAttribute('data-remaining') || '', 10);
    const chosen = Number.parseInt(field.value, 10);
    if (!Number.isInteger(remaining) || remaining < 1 || !Number.isInteger(chosen)) {
      return;
    }
    if (!clampValue && (chosen < 1 || chosen > remaining)) {
      return;
    }
    const quantity = Math.min(Math.max(chosen, 1), remaining);
    if (clampValue) {
      field.value = String(quantity);
    }
    const modal = closest(field, MODAL_SELECTOR);
    const line = modal ? modal.querySelector('[data-receipt-summary]') : null;
    if (!line) {
      return;
    }
    const tpl = (document.body && document.body.getAttribute('data-i18n-receipt-summary'))
      || DEFAULT_SUMMARY_TEMPLATE;
    line.textContent = tpl
      .replace('{chosen}', String(quantity))
      .replace('{remaining}', String(remaining));
  };

  /**
   * Increment or decrement `[data-receipt-quantity]` within `[1, remaining]` on stepper click.
   * @param {Element} stepBtn The clicked `[data-receipt-step]` button.
   * @returns {void}
   */
  const handleStepClick = (stepBtn) => {
    const modal = closest(stepBtn, MODAL_SELECTOR);
    const field = modal ? modal.querySelector('[data-receipt-quantity]') : null;
    if (!field) {
      return;
    }
    const delta = Number.parseInt(stepBtn.getAttribute('data-receipt-step') || '0', 10);
    const remaining = Number.parseInt(field.getAttribute('data-remaining') || '', 10);
    const current = Number.parseInt(field.value || '1', 10);
    if (Number.isInteger(remaining) && remaining > 0) {
      const base = Number.isInteger(current) ? current : 1;
      const next = Math.min(Math.max(base + delta, 1), remaining);
      field.value = String(next);
      updateSummary(field, true);
    }
  };

  document.addEventListener('input', (event) => {
    const field = closest(event.target, '[data-receipt-quantity]');
    if (field) {
      updateSummary(field, false);
    }
  });

  document.addEventListener('change', (event) => {
    const field = closest(event.target, '[data-receipt-quantity]');
    if (field) {
      updateSummary(field, true);
    }
  });

  document.addEventListener('click', (event) => {
    const opener = closest(event.target, OPENER_SELECTOR);
    if (opener) {
      const card = closest(opener, CARD_SELECTOR);
      const giftedItem = closest(opener, GIFTED_ITEM_SELECTOR);
      openerCardId = card ? card.id : '';
      openerGiftedItemId = giftedItem ? giftedItem.id : '';
      openerElement = opener;
      return;
    }
    const stepBtn = closest(event.target, '[data-receipt-step]');
    if (stepBtn) {
      handleStepClick(stepBtn);
      return;
    }
    const modal = closest(event.target, MODAL_SELECTOR);
    if (modal && (event.target === modal || closest(event.target, '[data-modal-close]'))) {
      closeDialog();
    }
  });

  document.addEventListener('keydown', (event) => {
    const modal = document.querySelector(MODAL_SELECTOR);
    if (!modal) {
      return;
    }
    if (event.key === 'Escape') {
      closeDialog();
      return;
    }
    if (event.key === 'Tab') {
      const focusable = getFocusable(modal);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey) {
        if (active === first || !modal.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || !modal.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  /**
   * Leave the busy state, restore «Подаренные» open state, and manage focus after submit.
   * @param {HTMLFormElement} form The submitted form.
   * @param {boolean} giftedWasOpen Whether `details.gifted-items-details` was open before submit.
   * @returns {void}
   */
  const finishAttempt = (form, giftedWasOpen) => {
    if (giftedWasOpen) {
      const details = document.querySelector(GIFTED_DETAILS_SELECTOR);
      if (details) {
        details.open = true;
      }
    }
    const modal = document.querySelector(MODAL_SELECTOR);
    if (!modal) {
      setBackgroundInert(false);
      restoreFocusToPage();
      return;
    }
    setBackgroundInert(true);
    if (document.contains(form)) {
      form.dataset.pending = 'false';
      form.removeAttribute('aria-busy');
      const button = form.querySelector('.btn-receipt-confirm');
      if (button) {
        button.disabled = false;
      }
      const feedback = document.getElementById(FEEDBACK_ID);
      if (feedback && feedback.textContent.trim() === '') {
        const genericFailure =
          document.body && document.body.getAttribute('data-i18n-receipt-failure');
        feedback.textContent = genericFailure || DEFAULT_GENERIC_FAILURE;
      }
    }
    focusDialog();
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
    const field = form.elements.namedItem('quantity');
    if (
      field &&
      field.type === 'number' &&
      typeof field.checkValidity === 'function' &&
      !field.checkValidity()
    ) {
      field.reportValidity();
      return;
    }
    const giftedDetails = document.querySelector(GIFTED_DETAILS_SELECTOR);
    const giftedWasOpen = Boolean(giftedDetails && giftedDetails.open);
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
    const qty = field ? field.value : 'cancel';
    const values = field ? { quantity: field.value } : {};
    let idemKey = form.dataset.idempotencyKey;
    if (!idemKey || form.dataset.idempotencyQty !== qty) {
      idemKey =
        window.crypto && typeof window.crypto.randomUUID === 'function'
          ? window.crypto.randomUUID()
          : `idem-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
      form.dataset.idempotencyKey = idemKey;
      form.dataset.idempotencyQty = qty;
    }
    const done = () => finishAttempt(form, giftedWasOpen);
    new Promise((resolve) => {
      resolve(
        window.htmx.ajax('POST', form.getAttribute('action'), {
          target: `#${FEEDBACK_ID}`,
          swap: 'none',
          values,
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

  /**
   * Capture runs before the shared bubble listener, which is registered earlier.
   * The flag is neutral so that listener can step aside without naming this flow.
   * Propagation stays intact so a list swap can still cancel an in-progress touch reorder.
   */
  document.addEventListener('htmx:beforeSwap', (event) => {
    const detail = event.detail;
    if (!detail || !detail.xhr || typeof detail.xhr.getResponseHeader !== 'function') {
      return;
    }
    const refusal = detail.xhr.getResponseHeader(REFUSAL_HEADER);
    if (typeof refusal !== 'string') {
      return;
    }
    detail.skipSharedDialog = true;
    if (REFUSAL_REASONS.has(refusal)) {
      detail.shouldSwap = true;
      detail.isError = false;
    }
  }, true);

  document.addEventListener('htmx:responseError', (event) => {
    const detail = event.detail;
    if (!detail || !detail.xhr || typeof detail.xhr.getResponseHeader !== 'function') {
      return;
    }
    if (typeof detail.xhr.getResponseHeader(REFUSAL_HEADER) === 'string') {
      event.stopPropagation();
    }
  }, true);

  document.addEventListener('htmx:afterSwap', (event) => {
    const target = event.detail && event.detail.target;
    if (!target || target.id !== CONTAINER_ID) {
      return;
    }
    if (document.querySelector(MODAL_SELECTOR)) {
      setBackgroundInert(true);
      focusDialog();
    }
  });
})();
