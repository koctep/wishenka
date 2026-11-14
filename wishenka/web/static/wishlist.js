/**
 * Wishlist page behaviour: expandable wish cards and drag-and-drop reordering.
 *
 * Classic script (loaded with `defer` after htmx); everything lives inside an IIFE
 * so no globals are exposed. The wishlist id for reordering is read from
 * `#items-list[data-wishlist-id]` at drop time.
 */
(() => {
  'use strict';

  const SUMMARY_SELECTOR = '.item-card-summary';
  const TOGGLE_EXCLUSION = 'a, button, input, select, textarea, [data-no-toggle]';
  const WISHLIST_ID_PATTERN = /^\d+$/;

  /** @type {Element | null} Card currently being dragged. */
  let dragged = null;

  /**
   * Toggle a card summary and its details panel.
   * @param {Event} event Click or keydown event that reached the summary.
   * @param {Element} summary The `.item-card-summary` element.
   * @returns {void}
   */
  const toggleWishCard = (event, summary) => {
    if (event.target.closest(TOGGLE_EXCLUSION)) {
      return;
    }
    if (event.type === 'keydown') {
      event.preventDefault();
    }
    const expanded = summary.getAttribute('aria-expanded') === 'true';
    summary.setAttribute('aria-expanded', expanded ? 'false' : 'true');
    const details = summary.parentElement.querySelector('.item-card-details');
    if (details) {
      details.hidden = expanded;
    }
  };

  /**
   * Find the card summary an event originated from.
   * @param {Event} event DOM event.
   * @returns {Element | null} The summary element or null.
   */
  const findSummary = (event) =>
    event.target.closest ? event.target.closest(SUMMARY_SELECTOR) : null;

  document.addEventListener('click', (event) => {
    const summary = findSummary(event);
    if (summary) {
      toggleWishCard(event, summary);
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    const summary = findSummary(event);
    if (summary) {
      toggleWishCard(event, summary);
    }
  });

  document.addEventListener('dragstart', (event) => {
    const card = event.target.closest
      ? event.target.closest('.item-card[draggable="true"]')
      : null;
    if (!card) {
      return;
    }
    dragged = card;
    event.dataTransfer.effectAllowed = 'move';
  });

  document.addEventListener('dragover', (event) => {
    if (dragged && event.target.closest && event.target.closest('#items-list')) {
      event.preventDefault();
    }
  });

  document.addEventListener('drop', (event) => {
    if (!dragged) {
      return;
    }
    const list = document.getElementById('items-list');
    const target = event.target.closest ? event.target.closest('.item-card') : null;
    if (!list || !target || target === dragged) {
      dragged = null;
      return;
    }
    event.preventDefault();
    const wishlistId = list.getAttribute('data-wishlist-id') || '';
    if (!WISHLIST_ID_PATTERN.test(wishlistId) || !window.htmx) {
      const causes = [];
      if (!WISHLIST_ID_PATTERN.test(wishlistId)) {
        causes.push(`#items-list[data-wishlist-id] is not numeric (got "${wishlistId}")`);
      }
      if (!window.htmx) {
        causes.push('window.htmx is not loaded (CDN blocked or script order)');
      }
      console.warn(`wishlist.js: reorder skipped: ${causes.join('; ')}`);
      dragged = null;
      return;
    }
    const rect = target.getBoundingClientRect();
    const after = event.clientY > rect.top + rect.height / 2;
    list.insertBefore(dragged, after ? target.nextSibling : target);
    dragged = null;
    const ids = Array.from(list.querySelectorAll('.item-card'), (card) =>
      card.getAttribute('data-item-id'),
    );
    window.htmx.ajax('POST', `/web/wishlists/${wishlistId}/items/reorder`, {
      target: '#items-list',
      swap: 'innerHTML',
      values: { item_ids: ids },
    });
  });

  document.addEventListener('dragend', () => {
    dragged = null;
  });
})();
