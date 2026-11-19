/**
 * Profile settings page controller: birthdate form, notification preferences,
 * and account deletion confirmation flow.
 *
 * Classic script (loaded with `defer` after `/static/app.js`).
 */
(() => {
  'use strict';

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
   * Extract an error detail string from a failed JSON response.
   *
   * @param {Response} resp - Fetch response object.
   * @param {string} fallback - Fallback error message.
   * @returns {Promise<string>} Resolved error detail message.
   */
  async function readErrorDetail(resp, fallback) {
    const err = await resp.json().catch(() => ({}));
    return err.detail || fallback;
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
   * Submit the birthdate form and update feedback/source labels.
   *
   * @param {SubmitEvent} evt - Form submit event.
   * @param {Element} page - The `.settings-page` root element.
   * @returns {Promise<void>}
   */
  async function saveBirthdate(evt, page) {
    evt.preventDefault();
    const dayInput = /** @type {HTMLInputElement | null} */ (document.getElementById('birth-day'));
    const monthInput = /** @type {HTMLInputElement | null} */ (
      document.getElementById('birth-month')
    );
    const yearInput = /** @type {HTMLInputElement | null} */ (
      document.getElementById('birth-year')
    );
    const feedback = document.getElementById('birthdate-feedback');
    const sourceLabel = document.getElementById('birthdate-source-label');
    if (!dayInput || !monthInput || !yearInput || !feedback) {
      return;
    }
    const dayVal = parseInt(dayInput.value, 10);
    const monthVal = parseInt(monthInput.value, 10);
    const yearRaw = yearInput.value.trim();
    const yearVal = yearRaw ? parseInt(yearRaw, 10) : null;
    const resp = await settingsFetch('/api/profile/birthdate', 'PATCH', {
      day: dayVal,
      month: monthVal,
      year: yearVal,
    });
    if (resp.ok) {
      feedback.textContent = getI18n(page, 'saved', 'Saved');
      if (sourceLabel) {
        sourceLabel.textContent = getI18n(page, 'birthdate-source-explicit', '');
      }
    } else {
      feedback.textContent = await readErrorDetail(
        resp,
        getI18n(page, 'invalid-birthdate', 'Invalid birthdate')
      );
    }
  }

  /**
   * Clear the user's stored birthdate via PATCH and reset form fields.
   *
   * @param {Element} page - The `.settings-page` root element.
   * @returns {Promise<void>}
   */
  async function clearBirthdate(page) {
    const feedback = document.getElementById('birthdate-feedback');
    const resp = await settingsFetch('/api/profile/birthdate', 'PATCH', { clear: true });
    if (!resp.ok) {
      return;
    }
    const dayInput = /** @type {HTMLInputElement | null} */ (document.getElementById('birth-day'));
    const monthInput = /** @type {HTMLInputElement | null} */ (
      document.getElementById('birth-month')
    );
    const yearInput = /** @type {HTMLInputElement | null} */ (
      document.getElementById('birth-year')
    );
    const sourceLabel = document.getElementById('birthdate-source-label');
    if (dayInput) {
      dayInput.value = '';
    }
    if (monthInput) {
      monthInput.value = '';
    }
    if (yearInput) {
      yearInput.value = '';
    }
    if (sourceLabel) {
      sourceLabel.textContent = getI18n(page, 'birthdate-source-explicit', '');
    }
    if (feedback) {
      feedback.textContent = getI18n(page, 'saved', 'Saved');
    }
  }

  /**
   * Persist a global notification toggle change.
   *
   * @param {string} category - Notification category key.
   * @param {boolean} enabled - New toggle state.
   * @param {string} feedbackId - ID of the status element to update.
   * @param {Element} page - The `.settings-page` root element.
   * @returns {Promise<void>}
   */
  async function updateGlobalNotification(category, enabled, feedbackId, page) {
    const feedback = document.getElementById(feedbackId);
    const payload = { settings: { [category]: enabled } };
    const resp = await settingsFetch('/api/profile/notifications/global', 'PUT', payload);
    if (!feedback) {
      return;
    }
    if (resp.ok) {
      feedback.textContent = getI18n(page, 'saved', 'Saved');
    } else {
      feedback.textContent = await readErrorDetail(
        resp,
        getI18n(page, 'invalid-notification', 'Invalid notification setting')
      );
    }
  }

  /**
   * Persist a per-wishlist notification override and refresh its effective badge.
   *
   * @param {string} wishlistId - Target wishlist identifier.
   * @param {string} category - Notification category key.
   * @param {string} rawVal - Selected value (`inherit`, `true`, or `false`).
   * @param {Element} page - The `.settings-page` root element.
   * @returns {Promise<void>}
   */
  async function updateWishlistOverride(wishlistId, category, rawVal, page) {
    const feedback = document.getElementById('wishlist-notifications-feedback');
    const val = rawVal === 'inherit' ? null : rawVal === 'true';
    const payload = { overrides: { [category]: val } };
    const resp = await settingsFetch(
      `/api/profile/notifications/wishlists/${wishlistId}`,
      'PUT',
      payload
    );
    if (resp.ok) {
      const data = await resp.json();
      const badge = page.querySelector(`[data-effective-for="${wishlistId}-${category}"] strong`);
      if (badge && data.effective && data.effective[category]) {
        badge.textContent = data.effective[category].enabled
          ? getI18n(page, 'state-enabled', 'Enabled')
          : getI18n(page, 'state-disabled', 'Disabled');
      }
      if (feedback) {
        feedback.textContent = getI18n(page, 'saved', 'Saved');
      }
    } else if (feedback) {
      feedback.textContent = await readErrorDetail(
        resp,
        getI18n(page, 'invalid-notification', 'Invalid notification setting')
      );
    }
  }

  /**
   * Fetch account deletion impact counts and reveal the confirmation panel.
   *
   * @param {Element} page - The `.settings-page` root element.
   * @returns {Promise<void>}
   */
  async function openDeletionPreview(page) {
    const feedback = document.getElementById('delete-account-feedback');
    if (feedback) {
      feedback.textContent = '';
    }
    const resp = await fetch('/api/profile/deletion-preview', { credentials: 'same-origin' });
    if (!resp.ok) {
      if (feedback) {
        feedback.textContent = getI18n(page, 'delete-failed', 'Account deletion failed');
      }
      return;
    }
    const data = await resp.json();
    const counts = [
      ['impact-personal', data.personal_lists_count],
      ['impact-transferred', data.collaborative_transferred_count],
      ['impact-collab-deleted', data.collaborative_deleted_count],
      ['impact-reservations', data.reservations_count],
    ];
    for (const [id, count] of counts) {
      const el = document.getElementById(id);
      if (el) {
        el.textContent = String(count || 0);
      }
    }
    const panel = document.getElementById('delete-account-confirm-panel');
    if (panel) {
      panel.hidden = false;
    }
  }

  /**
   * Hide the account deletion confirmation panel and clear feedback.
   *
   * @returns {void}
   */
  function cancelDeletionPreview() {
    const panel = document.getElementById('delete-account-confirm-panel');
    if (panel) {
      panel.hidden = true;
    }
    const feedback = document.getElementById('delete-account-feedback');
    if (feedback) {
      feedback.textContent = '';
    }
  }

  /**
   * Execute irreversible account deletion after user confirmation.
   *
   * @param {Element} page - The `.settings-page` root element.
   * @returns {Promise<void>}
   */
  async function confirmAccountDeletion(page) {
    const feedback = document.getElementById('delete-account-feedback');
    const resp = await settingsFetch('/api/profile/delete', 'POST', { confirm: true });
    if (resp.ok) {
      const panel = document.getElementById('delete-account-confirm-panel');
      const entry = document.getElementById('delete-account-entry');
      if (panel) {
        panel.hidden = true;
      }
      if (entry) {
        entry.hidden = true;
      }
      if (feedback) {
        feedback.textContent = getI18n(page, 'delete-completed', 'Account deleted');
      }
    } else if (feedback) {
      feedback.textContent = await readErrorDetail(
        resp,
        getI18n(page, 'delete-failed', 'Account deletion failed')
      );
    }
  }

  /**
   * Attach DOM event listeners for the settings page.
   *
   * @returns {void}
   */
  function initSettingsPage() {
    const page = document.querySelector('.settings-page');
    if (!page) {
      return;
    }
    const birthdateForm = document.getElementById('birthdate-form');
    if (birthdateForm) {
      birthdateForm.addEventListener('submit', (evt) => {
        saveBirthdate(evt, page);
      });
    }
    const clearBtn = document.getElementById('birthdate-clear-btn');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        clearBirthdate(page);
      });
    }
    const startDeleteBtn = document.getElementById('delete-account-start-btn');
    if (startDeleteBtn) {
      startDeleteBtn.addEventListener('click', () => {
        openDeletionPreview(page);
      });
    }
    const confirmDeleteBtn = document.getElementById('delete-account-confirm-btn');
    if (confirmDeleteBtn) {
      confirmDeleteBtn.addEventListener('click', () => {
        confirmAccountDeletion(page);
      });
    }
    const cancelDeleteBtn = document.getElementById('delete-account-cancel-btn');
    if (cancelDeleteBtn) {
      cancelDeleteBtn.addEventListener('click', cancelDeletionPreview);
    }
    page.addEventListener('change', (evt) => {
      const target = evt.target;
      if (!(target instanceof Element)) {
        return;
      }
      if (target instanceof HTMLInputElement && target.hasAttribute('data-global-category')) {
        const category = target.getAttribute('data-global-category');
        const feedbackId =
          target.getAttribute('data-feedback-target') || 'global-notifications-feedback';
        if (category) {
          updateGlobalNotification(category, target.checked, feedbackId, page);
        }
        return;
      }
      if (target instanceof HTMLSelectElement && target.hasAttribute('data-wishlist-override')) {
        const wishlistId = target.getAttribute('data-wishlist-id');
        const category = target.getAttribute('data-category');
        if (wishlistId && category) {
          updateWishlistOverride(wishlistId, category, target.value, page);
        }
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSettingsPage);
  } else {
    initSettingsPage();
  }
})();
