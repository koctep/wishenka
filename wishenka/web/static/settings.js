/**
 * Profile settings page controller: language, birthdate, notification preferences,
 * and account deletion confirmation flow.
 *
 * The server is authoritative. Every mutation shows pending feedback, a confirmed result, or an
 * error. Only validation/authorization rejections (which happen before any write) restore the
 * previous value; transport errors, 5xx and malformed responses may hide a committed change, so
 * they are reconciled with a read, or reported as unknown and the affected controls stay disabled.
 *
 * Classic script (loaded with `defer` after `/static/app.js`).
 */
(() => {
  'use strict';

  /** HTTP statuses that the endpoints guarantee are returned before any mutation. */
  const DEFINITE_REJECTIONS = new Set([401, 403, 404, 422]);

  /**
   * Read a localized string from `data-i18n-*` attributes on `.settings-page`.
   *
   * @param {Element} page - The `.settings-page` root element.
   * @param {string} key - Attribute suffix after `data-i18n-`.
   * @param {string} fallback - Fallback text if attribute is missing.
   * @returns {string} Localized string or fallback.
   */
  function getI18n(page, key, fallback) {
    return page.getAttribute(`data-i18n-${key}`) || fallback;
  }

  /**
   * Read a JSON body, resolving to `null` when it is missing or malformed.
   *
   * @param {Response} resp - Fetch response object.
   * @returns {Promise<any>} Parsed body or null.
   */
  async function readJson(resp) {
    try {
      return await resp.json();
    } catch (_err) {
      return null;
    }
  }

  /**
   * Pick a safe message for a rejected request: the server's localized validation detail for
   * 422 responses, otherwise the localized fallback (never raw server text).
   *
   * @param {Response} resp - Failed response.
   * @param {string} fallback - Localized fallback message.
   * @returns {Promise<string>} Message to display.
   */
  async function readErrorDetail(resp, fallback) {
    if (resp.status === 422) {
      const body = await readJson(resp);
      if (body && typeof body.detail === 'string' && body.detail.trim()) {
        return body.detail;
      }
    }
    return fallback;
  }

  /**
   * Send an authenticated JSON request with a CSRF token header.
   *
   * @param {string} url - Target API endpoint.
   * @param {string} method - HTTP method.
   * @param {Record<string, unknown>} body - JSON-serializable request payload.
   * @returns {Promise<Response>} Fetch response promise.
   */
  async function settingsFetch(url, method, body) {
    const token = typeof window.prepareCsrf === 'function' ? await window.prepareCsrf() : '';
    const headers = { 'Content-Type': 'application/json' };
    if (token) {
      headers['X-CSRF-Token'] = token;
    }
    return fetch(url, {
      method,
      credentials: 'same-origin',
      headers,
      body: JSON.stringify(body),
    });
  }

  /**
   * Send a request, resolving to `null` on a transport failure.
   *
   * @param {string} url - Target API endpoint.
   * @param {string} method - HTTP method.
   * @param {Record<string, unknown>} body - Request payload.
   * @returns {Promise<Response | null>} Response, or null if the request was lost.
   */
  async function trySend(url, method, body) {
    try {
      return await settingsFetch(url, method, body);
    } catch (_err) {
      return null;
    }
  }

  /**
   * Fetch authoritative JSON with a GET request; resolves to `null` if unavailable.
   *
   * @param {string} url - Endpoint to read.
   * @returns {Promise<any>} Parsed body or null.
   */
  async function readState(url) {
    try {
      const resp = await fetch(url, { credentials: 'same-origin' });
      return resp.ok ? await readJson(resp) : null;
    } catch (_err) {
      return null;
    }
  }

  /**
   * Whether a failed response is guaranteed to have happened before any change.
   *
   * @param {Response | null} resp - Response, or null on transport failure.
   * @returns {boolean} True for a definite pre-mutation rejection.
   */
  function isDefiniteRejection(resp) {
    return resp !== null && DEFINITE_REJECTIONS.has(resp.status);
  }

  /**
   * Create the settings controller bound to one page root.
   *
   * @param {Element} page - The `.settings-page` root element.
   * @returns {void}
   */
  function initController(page) {
    const text = (key, fallback) => getI18n(page, key, fallback);
    const byId = (id) => document.getElementById(id);

    /**
     * Show a result message in a live feedback region, optionally with a retry button.
     *
     * @param {string} id - Feedback element id.
     * @param {string} message - Message text.
     * @param {'success' | 'error' | ''} kind - Visual/semantic kind.
     * @param {{label: string, action: () => void} | null} [action] - Optional action button.
     * @returns {void}
     */
    function setFeedback(id, message, kind, action = null) {
      const el = byId(id);
      if (!el) {
        return;
      }
      el.textContent = message;
      el.classList.toggle('is-error', kind === 'error');
      el.classList.toggle('is-success', kind === 'success');
      page.querySelectorAll(`[data-retry-for="${id}"]`).forEach((node) => node.remove());
      if (action) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'retry-btn';
        btn.dataset.retryFor = id;
        btn.textContent = action.label;
        btn.addEventListener('click', action.action);
        el.after(btn);
      }
    }

    /**
     * Show or hide the "saving" note for a feedback region (kept separate from the result).
     *
     * @param {string} id - Feedback element id the note belongs to.
     * @param {boolean} on - Whether work is pending.
     * @param {string} [label] - Pending message text.
     * @returns {void}
     */
    function setPending(id, on, label = text('saving', 'Saving…')) {
      const feedback = byId(id);
      if (!feedback) {
        return;
      }
      let note = byId(`${id}-pending`);
      if (!note) {
        note = document.createElement('p');
        note.id = `${id}-pending`;
        note.className = 'pending-note';
        note.setAttribute('role', 'status');
        feedback.after(note);
      }
      note.hidden = !on;
      note.textContent = on ? label : '';
      feedback.closest('section')?.setAttribute('aria-busy', on ? 'true' : 'false');
    }

    const reloadAction = () => ({
      label: text('reload', 'Reload page'),
      action: () => window.location.reload(),
    });
    const retryAction = (fn) => ({ label: text('retry', 'Retry'), action: fn });

    // ---- Notification preferences ------------------------------------------------------------

    /** @type {Map<string, number>} */
    const busy = new Map();
    /** @type {Map<string, Promise<unknown>>} */
    const queues = new Map();

    /**
     * Controls that carry a category's effective value (global toggle and list overrides).
     *
     * @param {string} category - Notification category.
     * @returns {Element[]} Matching controls.
     */
    function categoryControls(category) {
      return Array.from(
        page.querySelectorAll(
          `[data-global-category="${category}"], ` +
            `[data-wishlist-override][data-category="${category}"]`
        )
      );
    }

    function refreshDisabled(category) {
      const locked = (busy.get(category) || 0) > 0;
      for (const el of categoryControls(category)) {
        el.disabled = locked || el.dataset.unknown === '1';
        if (el.matches('[data-global-category]')) {
          if (locked) el.setAttribute('aria-busy', 'true'); else el.removeAttribute('aria-busy');
        }
      }
    }

    function changeBusy(category, delta) {
      busy.set(category, Math.max(0, (busy.get(category) || 0) + delta));
      refreshDisabled(category);
    }

    /**
     * Serialize mutations per category so an older response cannot overwrite a newer value.
     *
     * @param {string} category - Notification category.
     * @param {() => Promise<void>} task - Work to run after earlier tasks finish.
     * @returns {Promise<void>}
     */
    function exclusive(category, task) {
      const previous = queues.get(category) || Promise.resolve();
      const next = previous.then(task, task);
      queues.set(
        category,
        next.catch(() => undefined)
      );
      return next;
    }

    function stateLabel(enabled) {
      return enabled ? text('state-enabled', 'Enabled') : text('state-disabled', 'Disabled');
    }

    function syncGlobalText(input) {
      const category = input.getAttribute('data-global-category');
      const label = byId(`state-${category}`);
      if (label) {
        label.textContent = stateLabel(input.checked);
      }
    }

    function setGlobalValue(input, enabled) {
      input.checked = enabled;
      input.dataset.confirmed = String(enabled);
      syncGlobalText(input);
    }

    function setOverrideValue(select, override) {
      const value = override === null || override === undefined ? 'inherit' : String(override);
      select.value = value;
      select.dataset.confirmed = value;
    }

    function setBadge(wishlistId, category, enabled) {
      const badge = page.querySelector(`[data-effective-for="${wishlistId}-${category}"] strong`);
      if (badge) {
        badge.textContent = stateLabel(Boolean(enabled));
      }
    }

    /** Apply a wishlist summary (overrides + effective) for one category. */
    function applyWishlistSummary(summary, category) {
      const select = page.querySelector(
        `[data-wishlist-override][data-wishlist-id="${summary.id}"][data-category="${category}"]`
      );
      if (select && summary.overrides) {
        setOverrideValue(select, summary.overrides[category]);
      }
      if (summary.effective && summary.effective[category]) {
        setBadge(summary.id, category, summary.effective[category].enabled);
      }
    }

    /** Apply a full preferences response for one category; clears its unknown flags. */
    function applyCategoryFromPreferences(data, category) {
      const input = page.querySelector(`input[data-global-category="${category}"]`);
      const value = data.global_notifications && data.global_notifications[category];
      if (input && typeof value === 'boolean') {
        setGlobalValue(input, value);
      }
      for (const summary of data.wishlists || []) {
        applyWishlistSummary(summary, category);
      }
      for (const el of categoryControls(category)) {
        delete el.dataset.unknown;
      }
    }

    /** Derive inherited badges from confirmed global and override values. */
    function deriveInheritedBadges(category, globalEnabled) {
      for (const select of page.querySelectorAll(
        `[data-wishlist-override][data-category="${category}"]`
      )) {
        if (select.dataset.confirmed === 'inherit') {
          setBadge(select.getAttribute('data-wishlist-id'), category, globalEnabled);
        }
      }
    }

    function markUnknown(controls) {
      for (const el of controls) {
        el.dataset.unknown = '1';
      }
    }

    /**
     * Run one global preference change with pending, confirmation and reconciliation.
     *
     * @param {HTMLInputElement} input - Toggle that changed.
     * @returns {Promise<void>}
     */
    function updateGlobalNotification(input) {
      const category = input.getAttribute('data-global-category') || '';
      const feedbackId =
        input.getAttribute('data-feedback-target') || 'global-notifications-feedback';
      const desired = input.checked;
      syncGlobalText(input);
      return exclusive(category, async () => {
        changeBusy(category, 1);
        setFeedback(feedbackId, '', '');
        setPending(feedbackId, true);
        try {
          const resp = await trySend('/api/profile/notifications/global', 'PUT', {
            settings: { [category]: desired },
          });
          if (resp && resp.ok) {
            const body = await readJson(resp);
            const saved = body && body.global_notifications && body.global_notifications[category];
            if (typeof saved === 'boolean') {
              setGlobalValue(input, saved);
              deriveInheritedBadges(category, saved);
              setFeedback(feedbackId, text('saved', 'Saved'), 'success');
              return;
            }
          } else if (isDefiniteRejection(resp)) {
            setGlobalValue(input, input.dataset.confirmed === 'true');
            const detail = await readErrorDetail(resp, text('rejected', 'Not saved.'));
            setFeedback(feedbackId, detail, 'error');
            return;
          }
          await reconcileGlobal(category, feedbackId, desired);
        } finally {
          setPending(feedbackId, false);
          changeBusy(category, -1);
        }
      });
    }

    /** Re-read preferences after an ambiguous outcome and report what is actually stored. */
    async function reconcileGlobal(category, feedbackId, desired) {
      const data = await readState('/api/profile/preferences');
      const stored = data && data.global_notifications && data.global_notifications[category];
      if (typeof stored !== 'boolean') {
        markUnknown(categoryControls(category));
        setFeedback(
          feedbackId,
          text('unknown-state', 'Could not confirm the current value.'),
          'error',
          retryAction(() => retryGlobal(category, feedbackId, desired))
        );
        return;
      }
      applyCategoryFromPreferences(data, category);
      const same = desired === null || stored === desired;
      setFeedback(
        feedbackId,
        same
          ? text('confirmed-after-error', 'The new value was checked and is in effect.')
          : text('not-saved-after-error', 'Not saved. The value is unchanged.'),
        same ? 'success' : 'error'
      );
    }

    function retryGlobal(category, feedbackId, desired) {
      return exclusive(category, async () => {
        changeBusy(category, 1);
        setPending(feedbackId, true);
        try {
          await reconcileGlobal(category, feedbackId, desired);
        } finally {
          setPending(feedbackId, false);
          changeBusy(category, -1);
        }
      });
    }

    /**
     * Run one per-wishlist override change.
     *
     * @param {HTMLSelectElement} select - Override select that changed.
     * @returns {Promise<void>}
     */
    function updateWishlistOverride(select) {
      const wishlistId = select.getAttribute('data-wishlist-id') || '';
      const category = select.getAttribute('data-category') || '';
      const feedbackId = 'wishlist-notifications-feedback';
      const desired = select.value;
      const url = `/api/profile/notifications/wishlists/${wishlistId}`;
      const value = desired === 'inherit' ? null : desired === 'true';
      return exclusive(category, async () => {
        changeBusy(category, 1);
        setFeedback(feedbackId, '', '');
        setPending(feedbackId, true);
        try {
          const resp = await trySend(url, 'PUT', { overrides: { [category]: value } });
          if (resp && resp.ok) {
            const summary = await readJson(resp);
            if (summary && summary.overrides && summary.overrides[category] !== undefined) {
              applyWishlistSummary({ ...summary, id: wishlistId }, category);
              setFeedback(feedbackId, text('saved', 'Saved'), 'success');
              return;
            }
          } else if (isDefiniteRejection(resp)) {
            select.value = select.dataset.confirmed || 'inherit';
            const detail = await readErrorDetail(resp, text('rejected', 'Not saved.'));
            setFeedback(feedbackId, detail, 'error');
            return;
          }
          await reconcileOverride(select, wishlistId, category, desired);
        } finally {
          setPending(feedbackId, false);
          changeBusy(category, -1);
        }
      });
    }

    async function reconcileOverride(select, wishlistId, category, desired) {
      const feedbackId = 'wishlist-notifications-feedback';
      const summary = await readState(`/api/profile/notifications/wishlists/${wishlistId}`);
      if (!summary || !summary.overrides || summary.overrides[category] === undefined) {
        markUnknown([select]);
        setFeedback(
          feedbackId,
          text('unknown-state', 'Could not confirm the current value.'),
          'error',
          retryAction(() => retryOverride(select, wishlistId, category, desired))
        );
        return;
      }
      applyWishlistSummary({ ...summary, id: wishlistId }, category);
      delete select.dataset.unknown;
      const same = select.dataset.confirmed === desired;
      setFeedback(
        feedbackId,
        same
          ? text('confirmed-after-error', 'The new value was checked and is in effect.')
          : text('not-saved-after-error', 'Not saved. The value is unchanged.'),
        same ? 'success' : 'error'
      );
    }

    function retryOverride(select, wishlistId, category, desired) {
      return exclusive(category, async () => {
        changeBusy(category, 1);
        setPending('wishlist-notifications-feedback', true);
        try {
          await reconcileOverride(select, wishlistId, category, desired);
        } finally {
          setPending('wishlist-notifications-feedback', false);
          changeBusy(category, -1);
        }
      });
    }

    // ---- Birthdate ---------------------------------------------------------------------------

    const dayInput = /** @type {HTMLInputElement | null} */ (byId('birth-day'));
    const monthInput = /** @type {HTMLInputElement | null} */ (byId('birth-month'));
    const yearInput = /** @type {HTMLInputElement | null} */ (byId('birth-year'));
    const saveBirthBtn = /** @type {HTMLButtonElement | null} */ (
      document.querySelector('#birthdate-form button[type="submit"]')
    );
    const clearBirthBtn = /** @type {HTMLButtonElement | null} */ (byId('birthdate-clear-btn'));
    let birthdateBusy = false;

    function setBirthdateDisabled(disabled) {
      for (const btn of [saveBirthBtn, clearBirthBtn]) {
        if (btn) {
          btn.disabled = disabled;
        }
      }
    }

    function formatBirthdate(date) {
      if (!date || !date.day || !date.month) {
        return text('birthdate-empty', 'Not set');
      }
      const base = `${String(date.day).padStart(2, '0')}.${String(date.month).padStart(2, '0')}`;
      return date.year ? `${base}.${date.year}` : base;
    }

    /** Show the confirmed birthdate; fill the form only when `fillForm` is set. */
    function applyBirthdate(date, fillForm) {
      const current = byId('birthdate-current');
      if (current) {
        current.textContent = formatBirthdate(date);
      }
      const source = byId('birthdate-source-label');
      if (source && date.source) {
        source.textContent =
          date.source === 'explicit'
            ? text('birthdate-source-explicit', '')
            : text('birthdate-source-auto', '');
      }
      if (fillForm && dayInput && monthInput && yearInput) {
        dayInput.value = date.day ? String(date.day) : '';
        monthInput.value = date.month ? String(date.month) : '';
        yearInput.value = date.year ? String(date.year) : '';
      }
    }

    function sameBirthdate(stored, desired) {
      if (desired.clear) {
        return !stored.day && !stored.month && !stored.year;
      }
      return (
        stored.day === desired.day &&
        stored.month === desired.month &&
        (stored.year || null) === (desired.year || null)
      );
    }

    /**
     * Send a birthdate save or clear request and report a confirmed result.
     *
     * @param {Record<string, unknown>} desired - Request payload (`{clear: true}` or date).
     * @returns {Promise<void>}
     */
    async function sendBirthdate(desired) {
      if (birthdateBusy) {
        return;
      }
      birthdateBusy = true;
      setBirthdateDisabled(true);
      setFeedback('birthdate-feedback', '', '');
      setPending('birthdate-feedback', true);
      try {
        const resp = await trySend('/api/profile/birthdate', 'PATCH', desired);
        if (resp && resp.ok) {
          const date = await readJson(resp);
          if (date && typeof date === 'object' && 'day' in date) {
            applyBirthdate(date, Boolean(desired.clear));
            setFeedback('birthdate-feedback', text('saved', 'Saved'), 'success');
            setBirthdateDisabled(false);
            return;
          }
        } else if (isDefiniteRejection(resp)) {
          // Show the localized fallback at once, then upgrade to the server's detail.
          const fallback = text('invalid-birthdate', 'Invalid birthdate');
          setFeedback('birthdate-feedback', fallback, 'error');
          setBirthdateDisabled(false);
          setFeedback('birthdate-feedback', await readErrorDetail(resp, fallback), 'error');
          return;
        }
        await reconcileBirthdate(desired);
      } finally {
        setPending('birthdate-feedback', false);
        birthdateBusy = false;
      }
    }

    async function reconcileBirthdate(desired) {
      const data = await readState('/api/profile/preferences');
      if (!data || !data.birthdate) {
        setBirthdateDisabled(true);
        setFeedback(
          'birthdate-feedback',
          text('unknown-state', 'Could not confirm the current value.'),
          'error',
          retryAction(async () => {
            if (birthdateBusy) {
              return;
            }
            birthdateBusy = true;
            setPending('birthdate-feedback', true);
            try {
              await reconcileBirthdate(desired);
            } finally {
              setPending('birthdate-feedback', false);
              birthdateBusy = false;
            }
          })
        );
        return;
      }
      const same = sameBirthdate(data.birthdate, desired);
      applyBirthdate(data.birthdate, same);
      setBirthdateDisabled(false);
      setFeedback(
        'birthdate-feedback',
        same
          ? text('confirmed-after-error', 'The new value was checked and is in effect.')
          : text('not-saved-after-error', 'Not saved. The value is unchanged.'),
        same ? 'success' : 'error'
      );
    }

    function submitBirthdate(evt) {
      evt.preventDefault();
      if (!dayInput || !monthInput || !yearInput) {
        return;
      }
      const yearRaw = yearInput.value.trim();
      sendBirthdate({
        day: parseInt(dayInput.value, 10),
        month: parseInt(monthInput.value, 10),
        year: yearRaw ? parseInt(yearRaw, 10) : null,
      });
    }

    // ---- Locale ------------------------------------------------------------------------------

    const localeButtons = Array.from(page.querySelectorAll('.locale-option'));
    const pageLocale = document.documentElement.lang;
    let localeBusy = false;

    function setLocaleDisabled(disabled) {
      for (const btn of localeButtons) {
        btn.disabled = disabled;
      }
    }

    function showPressedLocale(locale) {
      for (const btn of localeButtons) {
        const active = btn.getAttribute('data-locale') === locale;
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        btn.classList.toggle('is-active', active);
      }
    }

    /** Re-read the stored locale; reload when it differs and a reload was requested. */
    async function reconcileLocale(target, reloadOnChange) {
      const data = await readState('/api/profile/preferences');
      if (!data || !data.locale) {
        setLocaleDisabled(true);
        setFeedback(
          'locale-feedback',
          text('unknown-state', 'Could not confirm the current value.'),
          'error',
          retryAction(() => runLocaleReconcile(target, true))
        );
        return;
      }
      if (reloadOnChange && data.locale !== pageLocale) {
        window.location.reload();
        return;
      }
      setLocaleDisabled(false);
      showPressedLocale(data.locale);
      if (data.locale !== pageLocale) {
        setFeedback(
          'locale-feedback',
          text('locale-reload-needed', 'Reload the page to apply the language.'),
          'success',
          reloadAction()
        );
      } else {
        const same = data.locale === target;
        setFeedback(
          'locale-feedback',
          same
            ? text('refreshed', 'The current value was checked.')
            : text('not-saved-after-error', 'Not saved. The value is unchanged.'),
          same ? 'success' : 'error'
        );
      }
    }

    async function runLocaleReconcile(target, reloadOnChange) {
      if (localeBusy) {
        return;
      }
      localeBusy = true;
      setPending('locale-feedback', true);
      try {
        await reconcileLocale(target, reloadOnChange);
      } finally {
        setPending('locale-feedback', false);
        localeBusy = false;
      }
    }

    async function changeLocale(target) {
      if (localeBusy) {
        return;
      }
      localeBusy = true;
      setLocaleDisabled(true);
      setFeedback('locale-feedback', '', '');
      setPending('locale-feedback', true);
      try {
        const resp = await trySend(
          page.querySelector('[data-locale-endpoint]')?.getAttribute('data-locale-endpoint') ||
            '/api/profile/locale',
          'PATCH',
          { locale: target }
        );
        if (resp && resp.ok) {
          window.location.reload();
          return;
        }
        if (isDefiniteRejection(resp)) {
          setLocaleDisabled(false);
          const detail = await readErrorDetail(resp, text('locale-error', 'Not saved.'));
          setFeedback('locale-feedback', detail, 'error');
          return;
        }
        await reconcileLocale(target, false);
      } finally {
        setPending('locale-feedback', false);
        localeBusy = false;
      }
    }

    // ---- Account deletion --------------------------------------------------------------------

    const startDeleteBtn = /** @type {HTMLButtonElement | null} */ (
      byId('delete-account-start-btn')
    );
    const confirmDeleteBtn = /** @type {HTMLButtonElement | null} */ (
      byId('delete-account-confirm-btn')
    );
    const cancelDeleteBtn = /** @type {HTMLButtonElement | null} */ (
      byId('delete-account-cancel-btn')
    );
    const deletePanel = byId('delete-account-confirm-panel');
    let deletionBusy = false;

    async function openDeletionPreview() {
      if (deletionBusy || !startDeleteBtn || !deletePanel) {
        return;
      }
      deletionBusy = true;
      startDeleteBtn.disabled = true;
      setFeedback('delete-account-feedback', '', '');
      setPending('delete-account-feedback', true);
      try {
        const data = await readState('/api/profile/deletion-preview');
        if (!data) {
          startDeleteBtn.disabled = false;
          setFeedback(
            'delete-account-feedback',
            text('delete-preview-failed', 'Could not load the deletion summary.'),
            'error'
          );
          return;
        }
        const counts = [
          ['impact-personal', data.personal_lists_count],
          ['impact-transferred', data.collaborative_transferred_count],
          ['impact-collab-deleted', data.collaborative_deleted_count],
          ['impact-reservations', data.reservations_count],
        ];
        for (const [id, count] of counts) {
          const el = byId(id);
          if (el) {
            el.textContent = String(count || 0);
          }
        }
        deletePanel.hidden = false;
        if (cancelDeleteBtn) {
          cancelDeleteBtn.focus();
        }
      } finally {
        setPending('delete-account-feedback', false);
        deletionBusy = false;
      }
    }

    function cancelDeletionPreview() {
      if (deletionBusy) {
        return;
      }
      if (deletePanel) {
        deletePanel.hidden = true;
      }
      if (startDeleteBtn) {
        startDeleteBtn.disabled = false;
        startDeleteBtn.focus();
      }
      setFeedback('delete-account-feedback', '', '');
    }

    async function confirmAccountDeletion() {
      if (deletionBusy || !confirmDeleteBtn || !cancelDeleteBtn) {
        return;
      }
      deletionBusy = true;
      confirmDeleteBtn.disabled = true;
      cancelDeleteBtn.disabled = true;
      setFeedback('delete-account-feedback', '', '');
      setPending('delete-account-feedback', true, text('deleting', 'Deleting…'));
      try {
        // Never retried automatically: the person must explicitly confirm again.
        const resp = await trySend('/api/profile/delete', 'POST', { confirm: true });
        if (resp && resp.ok) {
          const entry = byId('delete-account-entry');
          if (deletePanel) {
            deletePanel.hidden = true;
          }
          if (entry) {
            entry.hidden = true;
          }
          setFeedback(
            'delete-account-feedback',
            text('delete-completed', 'Account deleted'),
            'success'
          );
        } else if (isDefiniteRejection(resp)) {
          confirmDeleteBtn.disabled = false;
          cancelDeleteBtn.disabled = false;
          const detail = await readErrorDetail(
            resp,
            text('delete-failed', 'Account deletion failed')
          );
          setFeedback('delete-account-feedback', detail, 'error');
        } else {
          setFeedback(
            'delete-account-feedback',
            text('delete-unknown', 'The result of deletion is unknown. Reload the page.'),
            'error',
            reloadAction()
          );
        }
      } finally {
        setPending('delete-account-feedback', false);
        deletionBusy = false;
      }
    }

    // ---- Wiring ------------------------------------------------------------------------------

    for (const input of page.querySelectorAll('input[data-global-category]')) {
      input.dataset.confirmed = String(input.checked);
      syncGlobalText(input);
    }
    for (const select of page.querySelectorAll('select[data-wishlist-override]')) {
      select.dataset.confirmed = select.value;
    }
    const birthdateForm = byId('birthdate-form');
    if (birthdateForm) {
      birthdateForm.addEventListener('submit', submitBirthdate);
    }
    if (clearBirthBtn) {
      clearBirthBtn.addEventListener('click', () => {
        sendBirthdate({ clear: true });
      });
    }
    for (const btn of localeButtons) {
      btn.addEventListener('click', () => {
        const target = btn.getAttribute('data-locale');
        if (target) {
          changeLocale(target);
        }
      });
    }
    if (startDeleteBtn) {
      startDeleteBtn.addEventListener('click', openDeletionPreview);
    }
    if (confirmDeleteBtn) {
      confirmDeleteBtn.addEventListener('click', confirmAccountDeletion);
    }
    if (cancelDeleteBtn) {
      cancelDeleteBtn.addEventListener('click', cancelDeletionPreview);
    }
    page.addEventListener('change', (evt) => {
      const target = evt.target;
      if (target instanceof HTMLInputElement && target.hasAttribute('data-global-category')) {
        updateGlobalNotification(target);
      } else if (
        target instanceof HTMLSelectElement &&
        target.hasAttribute('data-wishlist-override')
      ) {
        updateWishlistOverride(target);
      }
    });
  }

  /**
   * Attach DOM event listeners for the settings page.
   *
   * @returns {void}
   */
  function initSettingsPage() {
    const page = document.querySelector('.settings-page');
    if (page) {
      initController(page);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSettingsPage);
  } else {
    initSettingsPage();
  }
})();
