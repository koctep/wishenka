/**
 * Wishlist page behaviour: expandable wish cards and drag-and-drop reordering
 * (native HTML5 DnD for mouse, Pointer Events for touch).
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
  const HANDLE_SELECTOR = '.item-drag-handle';
  const CARD_SELECTOR = '.item-card';
  const DRAG_START_THRESHOLD_PX = 4;
  const AUTOSCROLL_EDGE_PX = 64;
  const AUTOSCROLL_MAX_PX = 14;
  const CLICK_SUPPRESS_MS = 400;
  const SWIPES_MIN_VERSION = '7.7';
  const HAPTIC_MIN_VERSION = '6.1';
  const REORDER_REFUSAL_HEADER = 'X-Reorder-Refusal';
  const STALE_RELOAD_DELAY_MS = 800;

  /** @type {Element | null} Card currently being dragged with the mouse. */
  let dragged = null;

  /**
   * Active touch gesture.
   * @typedef {object} TouchDrag
   * @property {'armed' | 'active'} state Armed until the movement threshold is passed.
   * @property {number} pointerId Pointer that started the gesture.
   * @property {Element} handle Handle that captured the pointer.
   * @property {Element} card Card being dragged.
   * @property {number} startX Pointer X at pointerdown.
   * @property {number} startY Pointer Y at pointerdown.
   * @property {number} startScrollY Page scroll offset at pointerdown.
   * @property {number} lastX Latest pointer X.
   * @property {number} lastY Latest pointer Y.
   * @property {Element | null} target Current drop target card.
   * @property {boolean} after True when dropping after the target.
   * @property {number} rafId Pending animation frame id, or 0.
   * @property {boolean} swipesWereEnabled True when this gesture disabled Telegram swipes.
   */

  /** @type {TouchDrag | null} Touch gesture in progress, or null when idle. */
  let touchDrag = null;

  /** True while the click that ends a drag must be swallowed. */
  let suppressNextClick = false;

  /** @type {number} Pending timer id that clears `suppressNextClick`, or 0. */
  let suppressTimer = 0;

  /** True once a Telegram SDK failure was reported (warn only once). */
  let sdkWarned = false;

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
   * Decide whether a pointer is in the lower half of a card.
   * @param {number} clientY Pointer Y coordinate.
   * @param {{top: number, height: number}} rect Target card rectangle.
   * @returns {boolean} True when the dragged card goes after the target.
   */
  const isAfterMidpoint = (clientY, rect) => clientY > rect.top + rect.height / 2;

  /**
   * Move a card next to a target and send the full new order to the server.
   * This is the only place that calls `htmx.ajax`.
   * @param {Element} list The `#items-list` element.
   * @param {Element} card Card being moved.
   * @param {Element} target Card the moved card is dropped next to.
   * @param {boolean} after True to insert after the target, false before.
   * @returns {boolean} True when a request was sent.
   */
  const submitReorder = (list, card, target, after) => {
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
      return false;
    }
    list.insertBefore(card, after ? target.nextSibling : target);
    const ids = Array.from(list.querySelectorAll(CARD_SELECTOR), (item) =>
      item.getAttribute('data-item-id'),
    );
    window.htmx.ajax('POST', `/web/wishlists/${wishlistId}/items/reorder`, {
      target: '#items-list',
      swap: 'innerHTML',
      values: { item_ids: ids },
    });
    return true;
  };

  /**
   * Telegram WebApp object, if the SDK is loaded.
   * @returns {object | null} `window.Telegram.WebApp` or null.
   */
  const telegramWebApp = () => {
    try {
      return window.Telegram?.WebApp ?? null;
    } catch (error) {
      return null;
    }
  };

  /**
   * Warn once about a failing Telegram SDK call.
   * @param {string} call Name of the failing SDK call, for the message.
   * @param {unknown} error Caught error.
   * @returns {void}
   */
  const warnSdk = (call, error) => {
    if (!sdkWarned) {
      sdkWarned = true;
      console.warn(`wishlist.js: Telegram SDK call failed (${call}); later failures are not reported`, error);
    }
  };

  /**
   * Disable Telegram vertical swipes (Bot API 7.7+) for the gesture.
   * @returns {boolean} True when swipes were enabled and are now disabled by us.
   */
  const disableSwipes = () => {
    try {
      const webApp = telegramWebApp();
      if (
        webApp &&
        webApp.isVersionAtLeast(SWIPES_MIN_VERSION) &&
        webApp.isVerticalSwipesEnabled === true
      ) {
        webApp.disableVerticalSwipes();
        return true;
      }
    } catch (error) {
      warnSdk('disableVerticalSwipes', error);
    }
    return false;
  };

  /**
   * Re-enable Telegram vertical swipes that this script disabled.
   * @returns {void}
   */
  const restoreSwipes = () => {
    try {
      const webApp = telegramWebApp();
      if (webApp) {
        webApp.enableVerticalSwipes();
      }
    } catch (error) {
      warnSdk('enableVerticalSwipes', error);
    }
  };

  /**
   * Trigger Telegram haptic feedback when supported.
   * @param {'impact' | 'selection'} kind Feedback kind.
   * @returns {void}
   */
  const haptic = (kind) => {
    try {
      const webApp = telegramWebApp();
      if (!webApp || !webApp.isVersionAtLeast(HAPTIC_MIN_VERSION) || !webApp.HapticFeedback) {
        return;
      }
      if (kind === 'impact') {
        webApp.HapticFeedback.impactOccurred('light');
      } else {
        webApp.HapticFeedback.selectionChanged();
      }
    } catch (error) {
      warnSdk(kind === 'impact' ? 'HapticFeedback.impactOccurred' : 'HapticFeedback.selectionChanged', error);
    }
  };

  /**
   * Remove drop indicator classes from every card.
   * @returns {void}
   */
  const clearDropIndicators = () => {
    document.querySelectorAll('.drop-before, .drop-after').forEach((node) => {
      node.classList.remove('drop-before', 'drop-after');
    });
  };

  /**
   * Swallow the click that the browser fires after a drag ends.
   * The flag stays armed for up to CLICK_SUPPRESS_MS when no click follows
   * (a later genuine tap inside that window would be swallowed too); re-arming
   * restarts the window so an earlier timer cannot clear the flag early.
   * @returns {void}
   */
  const armClickSuppression = () => {
    suppressNextClick = true;
    window.clearTimeout(suppressTimer);
    suppressTimer = window.setTimeout(() => {
      suppressNextClick = false;
      suppressTimer = 0;
    }, CLICK_SUPPRESS_MS);
  };

  /**
   * Finish a touch gesture: reset all state and visual feedback.
   * Runs on every exit path (drop, cancel, early exits).
   * @returns {void}
   */
  const endTouchDrag = () => {
    const drag = touchDrag;
    if (!drag) {
      return;
    }
    touchDrag = null;
    if (drag.rafId) {
      window.cancelAnimationFrame(drag.rafId);
    }
    clearDropIndicators();
    drag.card.style.transform = '';
    drag.card.classList.remove('is-touch-dragging');
    document.body.classList.remove('is-touch-reordering');
    document.documentElement.classList.remove('is-touch-reordering');
    try {
      if (drag.handle.hasPointerCapture(drag.pointerId)) {
        drag.handle.releasePointerCapture(drag.pointerId);
      }
    } catch (error) {
      // The pointer is already gone; nothing to release.
    }
    if (drag.swipesWereEnabled) {
      restoreSwipes();
    }
  };

  /**
   * Abort the gesture without sending anything; the DOM order was never changed.
   * @returns {void}
   */
  const cancelTouchDrag = () => {
    if (!touchDrag) {
      return;
    }
    if (touchDrag.state === 'active') {
      armClickSuppression();
    }
    endTouchDrag();
  };

  /**
   * Find the drop target under the pointer and mark it.
   * @param {TouchDrag} drag Active gesture.
   * @returns {void}
   */
  const updateDropTarget = (drag) => {
    const hit = document.elementFromPoint(drag.lastX, drag.lastY);
    let target = hit && hit.closest ? hit.closest(CARD_SELECTOR) : null;
    if (!target || target === drag.card || !target.closest('#items-list')) {
      target = null;
    }
    const after = target ? isAfterMidpoint(drag.lastY, target.getBoundingClientRect()) : false;
    if (target && target !== drag.target) {
      haptic('selection');
    }
    if (target !== drag.target || after !== drag.after) {
      clearDropIndicators();
      if (target) {
        target.classList.add(after ? 'drop-after' : 'drop-before');
      }
    }
    drag.target = target;
    drag.after = after;
  };

  /**
   * Move the dragged card with the finger, accounting for page scroll.
   * @param {TouchDrag} drag Active gesture.
   * @returns {void}
   */
  const moveDraggedCard = (drag) => {
    const dy = drag.lastY - drag.startY + (window.scrollY - drag.startScrollY);
    drag.card.style.transform = `translateY(${dy}px)`;
  };

  /**
   * Scroll the page while the pointer is near a window edge (one frame).
   * @returns {void}
   */
  const autoScrollTick = () => {
    const drag = touchDrag;
    if (!drag || drag.state !== 'active') {
      return;
    }
    const bottomEdge = window.innerHeight - AUTOSCROLL_EDGE_PX;
    let speed = 0;
    if (drag.lastY < AUTOSCROLL_EDGE_PX) {
      const depth = (AUTOSCROLL_EDGE_PX - drag.lastY) / AUTOSCROLL_EDGE_PX;
      speed = -AUTOSCROLL_MAX_PX * Math.min(1, depth);
    } else if (drag.lastY > bottomEdge) {
      const depth = (drag.lastY - bottomEdge) / AUTOSCROLL_EDGE_PX;
      speed = AUTOSCROLL_MAX_PX * Math.min(1, depth);
    }
    if (speed !== 0) {
      window.scrollBy(0, speed);
      moveDraggedCard(drag);
      updateDropTarget(drag);
    }
    drag.rafId = window.requestAnimationFrame(autoScrollTick);
  };

  /**
   * Switch an armed gesture to active once the movement threshold is passed.
   * @param {TouchDrag} drag Armed gesture.
   * @returns {void}
   */
  const activateTouchDrag = (drag) => {
    drag.state = 'active';
    drag.card.classList.add('is-touch-dragging');
    document.body.classList.add('is-touch-reordering');
    document.documentElement.classList.add('is-touch-reordering');
    haptic('impact');
    drag.rafId = window.requestAnimationFrame(autoScrollTick);
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
    if (touchDrag) {
      event.preventDefault();
      return;
    }
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
    const target = event.target.closest ? event.target.closest(CARD_SELECTOR) : null;
    if (!list || !target || target === dragged) {
      dragged = null;
      return;
    }
    event.preventDefault();
    const after = isAfterMidpoint(event.clientY, target.getBoundingClientRect());
    const card = dragged;
    dragged = null;
    submitReorder(list, card, target, after);
  });

  document.addEventListener('dragend', () => {
    dragged = null;
  });

  document.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'touch') {
      return;
    }
    if (touchDrag) {
      if (event.pointerId !== touchDrag.pointerId) {
        cancelTouchDrag();
      }
      return;
    }
    const handle = event.target.closest ? event.target.closest(HANDLE_SELECTOR) : null;
    const card = handle ? handle.closest('.item-card[draggable="true"]') : null;
    if (!handle || !card || !card.closest('#items-list')) {
      return;
    }
    touchDrag = {
      state: 'armed',
      pointerId: event.pointerId,
      handle,
      card,
      startX: event.clientX,
      startY: event.clientY,
      startScrollY: window.scrollY,
      lastX: event.clientX,
      lastY: event.clientY,
      target: null,
      after: false,
      rafId: 0,
      swipesWereEnabled: false,
    };
    try {
      handle.setPointerCapture(event.pointerId);
    } catch (error) {
      // Capture is best effort; document-level listeners still receive events.
    }
    touchDrag.swipesWereEnabled = disableSwipes();
  });

  document.addEventListener('pointermove', (event) => {
    const drag = touchDrag;
    if (!drag || event.pointerId !== drag.pointerId) {
      return;
    }
    drag.lastX = event.clientX;
    drag.lastY = event.clientY;
    if (drag.state === 'armed') {
      const moved = Math.hypot(drag.lastX - drag.startX, drag.lastY - drag.startY);
      if (moved < DRAG_START_THRESHOLD_PX) {
        return;
      }
      activateTouchDrag(drag);
    }
    moveDraggedCard(drag);
    updateDropTarget(drag);
  });

  document.addEventListener('pointerup', (event) => {
    const drag = touchDrag;
    if (!drag || event.pointerId !== drag.pointerId) {
      return;
    }
    const { card, target, after, state } = drag;
    const list = document.getElementById('items-list');
    endTouchDrag();
    if (state !== 'active') {
      return;
    }
    armClickSuppression();
    if (target && list && document.contains(card) && card.parentElement === list) {
      submitReorder(list, card, target, after);
    }
  });

  document.addEventListener('pointercancel', (event) => {
    if (touchDrag && event.pointerId === touchDrag.pointerId) {
      cancelTouchDrag();
    }
  });

  document.addEventListener('lostpointercapture', (event) => {
    if (touchDrag && event.pointerId === touchDrag.pointerId) {
      cancelTouchDrag();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      cancelTouchDrag();
    }
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      cancelTouchDrag();
    }
  });

  window.addEventListener('blur', cancelTouchDrag);

  document.addEventListener('contextmenu', (event) => {
    if (touchDrag) {
      event.preventDefault();
    }
  });

  document.addEventListener('htmx:beforeSwap', (event) => {
    const swapTarget = event.detail && event.detail.target;
    if (touchDrag && swapTarget && swapTarget.id === 'items-list') {
      cancelTouchDrag();
    }
  });

  /*
   * A refresh of a card that is gone or changed (for example a fully received wish) answers with
   * something other than the same card; the neutral text replaces it instead of the raw answer.
   * The inline script of base.html defines `swapWishCard`; it is wrapped, not edited.
   */
  const originalSwapWishCard = window.swapWishCard;
  if (typeof originalSwapWishCard === 'function') {
    window.swapWishCard = (card, markup) => {
      const holder = document.createElement('template');
      holder.innerHTML = String(markup);
      const root = holder.content.firstElementChild;
      if (root && root.id === card.id && root.classList.contains('item-card')) {
        originalSwapWishCard(card, markup);
        return;
      }
      const gone = document.createElement('p');
      gone.className = 'item-card-unavailable';
      gone.setAttribute('role', 'status');
      gone.textContent = (document.body && document.body.getAttribute('data-i18n-item-unavailable'))
        || 'This wish is no longer available. Please refresh the page.';
      card.replaceWith(gone);
    };
  }

  // A stale reorder answers 400 with a marker header (not swapped by htmx): show a neutral
  // notice and reload so the list matches the server again.
  document.addEventListener('htmx:responseError', (event) => {
    const detail = event.detail;
    if (!detail || !detail.xhr || typeof detail.xhr.getResponseHeader !== 'function') {
      return;
    }
    if (detail.xhr.getResponseHeader(REORDER_REFUSAL_HEADER) !== 'stale_order') {
      return;
    }
    const notice = document.getElementById('list-notice');
    if (notice) {
      notice.textContent = (document.body && document.body.getAttribute('data-i18n-list-changed'))
        || 'The list has changed. Refreshing.';
    }
    window.setTimeout(() => window.location.reload(), STALE_RELOAD_DELAY_MS);
  });

  document.addEventListener(
    'click',
    (event) => {
      if (suppressNextClick) {
        suppressNextClick = false;
        event.preventDefault();
        event.stopPropagation();
      }
    },
    true,
  );
})();
