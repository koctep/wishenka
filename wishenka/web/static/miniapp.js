/* Wishlist management in the Telegram Mini App. */
const root = document.getElementById('app');
let bridge = window.Telegram?.WebApp;
let csrf = '';
let profileLocale = '';

function loadI18nCatalog() {
  try {
    const raw = document.getElementById('miniapp-i18n')?.textContent;
    if (!raw) {
      console?.warn?.('miniapp.js: #miniapp-i18n catalog missing or empty');
      return {};
    }
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') return parsed;
    console?.warn?.('miniapp.js: #miniapp-i18n catalog is not an object');
    return {};
  } catch (error) {
    console?.warn?.('miniapp.js: failed to parse #miniapp-i18n catalog', error);
    return {};
  }
}
const I18N_CATALOG = loadI18nCatalog();
const WARNED_MISSING_KEYS = new Set();

function node(tag, text = '', attributes = {}) {
  const el = document.createElement(tag);
  el.textContent = text;
  Object.entries(attributes).forEach(([name, value]) => el.setAttribute(name, value));
  return el;
}
function button(text, handler, className = '') {
  const el = node('button', text, {type: 'button'});
  if (className) el.setAttribute('class', className);
  el.addEventListener('click', handler);
  return el;
}
function normalizeLocale(raw) {
  const value = String(raw || '').trim().toLowerCase();
  if (!value) return '';
  const primary = value.split(/[-_]/)[0];
  return primary === 'ru' ? 'ru' : 'en';
}
function activeLocale() {
  if (profileLocale) return profileLocale;
  const guestRaw =
    bridge?.initDataUnsafe?.user?.language_code ||
    root?.dataset?.locale ||
    document.documentElement.lang ||
    navigator.language ||
    'en';
  return normalizeLocale(guestRaw) || 'en';
}
function t(key, params = {}) {
  const locale = activeLocale();
  const localeTable = I18N_CATALOG[locale] || {};
  const fallbackTable = I18N_CATALOG.en || {};
  const template = localeTable[key] ?? fallbackTable[key];
  if (template === undefined) {
    if (Object.keys(I18N_CATALOG).length > 0 && !WARNED_MISSING_KEYS.has(key)) {
      WARNED_MISSING_KEYS.add(key);
      console?.warn?.(`miniapp.js: missing i18n key "${key}" for locale "${locale}"`);
    }
    return key;
  }
  return String(template).replace(/\{([A-Za-z0-9_]+)\}/g, (match, name) => (
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match
  ));
}
function formatDateTime(iso) {
  const tag = activeLocale() === 'ru' ? 'ru-RU' : 'en-US';
  return new Date(iso).toLocaleString(tag);
}
function status(message) {
  document.getElementById('status').textContent = message;
}
function nextIdempotencyKey() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    return window.crypto.randomUUID();
  }
  return `idem-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
async function api(path, options = {}) {
  const method = options.method || 'GET';
  const headers = {...options.headers};
  if (!['GET', 'HEAD'].includes(method)) headers['X-CSRF-Token'] = csrf;
  if (options.body) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {...options, headers, credentials: 'same-origin'});
  if (!response.ok) {
    const err = new Error(`Request failed (${response.status})`);
    err.status = response.status;
    throw err;
  }
  return response.json();
}
function linkFor(prefix, token) {
  const bot = root.dataset.bot;
  const app = root.dataset.miniapp;
  if (!/^[A-Za-z0-9_]{1,64}$/.test(bot) || !/^[A-Za-z0-9_]{1,64}$/.test(app) ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(token || '')) {
    throw new Error(t('miniapp.share.not_configured'));
  }
  return `https://t.me/${bot}/${app}?startapp=${prefix}_${token}`;
}
function sharePanel(token, prefix, title, options = {}) {
  const panel = node('section', '', {
    class: `list-admin-section share-panel ${options.className || ''}`
  });
  panel.append(node('h2', title));
  if (options.hint) {
    panel.append(node('p', options.hint, {class: 'section-subtitle share-panel-hint'}));
  }
  let url;
  try { url = linkFor(prefix, token); } catch (error) {
    panel.append(node('p', error.message));
    if (options.footerAction) panel.append(options.footerAction);
    return panel;
  }
  const field = node('input', '', {value: url, readonly: '', 'aria-label': title,
    class: 'share-link-input'});
  panel.append(field);
  const actions = node('div', '', {class: 'share-panel-actions'});
  actions.append(button(t('miniapp.share.copy_link'), async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(url);
      status(t('miniapp.share.link_copied'));
    } catch (_) { field.select(); status(t('miniapp.share.copy_failed')); }
  }, 'share-copy-btn'));
  actions.append(button(t('miniapp.share.share_telegram'), () => {
    try {
      if (!bridge?.openTelegramLink) throw new Error('Telegram unavailable');
      bridge.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}`);
      status(t('miniapp.share.telegram_opened'));
    } catch (_) { status(t('miniapp.share.telegram_unavailable')); }
  }, 'btn-primary share-telegram-btn'));
  panel.append(actions);
  if (options.footerAction) {
    const footer = node('div', '', {class: 'share-panel-footer'});
    footer.append(options.footerAction);
    panel.append(footer);
  }
  return panel;
}
const KNOWN_ROLES = new Set(['owner', 'admin', 'member', 'favorite']);
function roleLabel(role) {
  if (KNOWN_ROLES.has(role)) return t(`miniapp.role.${role}`);
  return role ? String(role) : '';
}
function renderBadge(role) {
  return node('span', roleLabel(role), {class: `badge badge-${role}`});
}
function formatDate(iso) {
  if (!iso) return '';
  const parsed = new Date(iso);
  if (isNaN(parsed.getTime())) return String(iso);
  const tag = activeLocale() === 'ru' ? 'ru-RU' : 'en-US';
  return parsed.toLocaleDateString(tag, {day: 'numeric', month: 'short', year: 'numeric'});
}
function renderSectionHeader(section, title, count, subtitle) {
  const header = node('div', '', {class: 'wishlist-section-header'});
  header.append(
    node('h2', title),
    node('span', String(count), {class: 'section-count'})
  );
  section.append(header);
  if (subtitle) {
    section.append(node('p', subtitle, {class: 'section-subtitle'}));
  }
}
function renderEmptyState(noticeKey, hintKey) {
  const box = node('div', '', {class: 'empty-state'});
  box.append(
    node('p', t(noticeKey), {class: 'empty-notice'}),
    node('p', t(hintKey), {class: 'empty-hint'})
  );
  return box;
}
function wishlistCard(list, onClick, options = {}) {
  const title = list.name || t('miniapp.common.untitled_wishlist');
  const card = node('div', '', {class: 'wishlist-card'});
  const header = node('div', '', {class: 'wishlist-card-header'});
  header.append(node('h3', title, {class: 'wishlist-card-title'}));
  if (list.role) {
    header.append(renderBadge(list.role));
  }
  card.append(header);
  const metaParts = [];
  if (list.event_title) metaParts.push(String(list.event_title));
  if (list.event_date) metaParts.push(formatDate(list.event_date));
  if (metaParts.length > 0) {
    card.append(node('p', metaParts.join(' · '), {class: 'wishlist-card-meta'}));
  }
  const actions = node('div', '', {class: 'wishlist-card-actions'});
  const openBtn = button(t('miniapp.home.open_wishlist'), onClick, 'wishlist-card-open');
  openBtn.setAttribute('aria-label', t('miniapp.home.open_wishlist_named', {name: title}));
  actions.append(openBtn);
  if (options.secondaryAction) {
    actions.append(options.secondaryAction);
  }
  card.append(actions);
  return card;
}
let historyRenderToken = 0;
function formatViewedAt(iso) {
  const moment = iso ? new Date(iso) : null;
  if (!moment || isNaN(moment.getTime())) return null;
  const tag = activeLocale() === 'ru' ? 'ru-RU' : 'en-US';
  const absolute = moment.toLocaleString(tag, {dateStyle: 'medium', timeStyle: 'short'});
  const seconds = Math.max(0, (Date.now() - moment.getTime()) / 1000);
  const units = [['minute', 60], ['hour', 3600], ['day', 86400]];
  let text = absolute;
  if (seconds < 60) {
    text = t('miniapp.history.just_now');
  } else if (seconds < 7 * 86400 && typeof Intl.RelativeTimeFormat === 'function') {
    const [unit, size] = units.filter(([, s]) => seconds >= s).pop();
    text = new Intl.RelativeTimeFormat(tag, {numeric: 'auto'})
      .format(-Math.floor(seconds / size), unit);
  }
  return {text, absolute, iso: moment.toISOString()};
}
function renderHistoryCard(item) {
  const name = item.name || t('miniapp.common.untitled_wishlist');
  const card = node('li', '', {class: 'history-card history-item'});
  const main = node('div', '', {class: 'history-card-main'});
  const meta = node('p', '', {class: 'history-meta'});
  const viewed = formatViewedAt(item.viewed_at);
  if (viewed) {
    meta.append(node('time', t('miniapp.history.viewed_at', {date: viewed.text}), {
      class: 'history-time', datetime: viewed.iso, title: viewed.absolute
    }));
  }
  if (item.role) meta.append(renderBadge(item.role));
  main.append(node('h2', name, {class: 'history-title'}), meta);
  const open = button(t('miniapp.home.open_wishlist'), () => showList(item.id), 'history-open');
  open.setAttribute('aria-label', t('miniapp.home.open_wishlist_named', {name}));
  card.append(main, open);
  return card;
}
function renderHistoryEmpty() {
  const box = node('div', '', {class: 'empty-state history-empty'});
  box.append(
    node('p', t('miniapp.history.empty'), {class: 'empty-notice'}),
    node('p', t('miniapp.history.empty_hint'), {class: 'empty-hint'}),
    button(t('miniapp.history.open_home'), showHome, 'history-empty-action')
  );
  return box;
}
function renderHistoryFooter(count) {
  const footer = node('div', '', {class: 'history-footer'});
  let clearing = false;
  const clearBtn = button(t('miniapp.history.clear'), () => openConfirm(), 'history-clear');
  const cancelBtn = button(
    t('miniapp.history.clear_confirm_cancel'), () => closeConfirm(), 'history-confirm-cancel'
  );
  const yesBtn = button(
    t('miniapp.history.clear_confirm_yes'), () => confirmClear(), 'history-confirm-yes btn-danger'
  );
  const failure = node('p', '', {class: 'history-error', role: 'alert'});
  const actions = node('div', '', {class: 'history-confirm-actions'});
  actions.append(cancelBtn, yesBtn);
  const group = node('div', '', {class: 'history-confirm', role: 'group'});
  group.append(
    node('p', t('miniapp.history.clear_confirm_title'), {class: 'history-confirm-title'}),
    node('p', t('miniapp.history.clear_confirm_body', {count}), {class: 'empty-hint'}),
    actions
  );
  group.addEventListener('keydown', ev => { if (ev.key === 'Escape') closeConfirm(); });
  function openConfirm() {
    clearBtn.replaceWith(group);
    cancelBtn.focus();
  }
  function closeConfirm() {
    if (clearing) return;
    failure.remove();
    group.replaceWith(clearBtn);
    clearBtn.focus();
  }
  async function confirmClear() {
    if (clearing) return;
    clearing = true;
    failure.remove();
    cancelBtn.disabled = yesBtn.disabled = true;
    group.setAttribute('aria-busy', 'true');
    status(t('miniapp.history.clearing'));
    try {
      await api('/api/history', {method: 'DELETE'});
    } catch (_) {
      clearing = false;
      cancelBtn.disabled = yesBtn.disabled = false;
      group.removeAttribute('aria-busy');
      status('');
      failure.textContent = t('miniapp.history.clear_failed');
      group.insertBefore(failure, actions);
      return;
    }
    await showHistory();
    status(t('miniapp.history.cleared'));
    root.querySelector('h1')?.focus();
  }
  footer.append(clearBtn);
  return footer;
}
async function showHistory() {
  const token = ++historyRenderToken;
  const historyTitle = t('miniapp.history.title');
  const section = node('section', '', {
    'aria-label': historyTitle, role: 'region', 'aria-busy': 'true'
  });
  root.replaceChildren(
    button(t('nav.back'), showHome),
    node('h1', historyTitle, {tabindex: '-1'}),
    section
  );
  status(t('nav.loading'));
  let history;
  try {
    history = await api('/api/history');
  } catch (_) {
    if (token !== historyRenderToken) return;
    section.removeAttribute('aria-busy');
    status('');
    section.append(
      node('p', t('miniapp.history.load_failed'), {class: 'history-error', role: 'alert'}),
      button(t('miniapp.history.retry'), showHistory, 'history-retry')
    );
    return;
  }
  if (token !== historyRenderToken) return;
  section.setAttribute('aria-busy', 'false');
  if (history.length === 0) {
    section.append(renderHistoryEmpty());
  } else {
    const list = node('ul', '', {class: 'history-list'});
    history.forEach(item => list.append(renderHistoryCard(item)));
    section.append(list, renderHistoryFooter(history.length));
  }
  status('');
}
async function showHome() {
  root.replaceChildren(
    node('h1', t('miniapp.home.title')),
    node('p', t('miniapp.home.lead'), {class: 'home-lead'})
  );
  const nav = node('nav', '', {class: 'top-nav home-top-nav'});
  const settingsLink = node('a', t('nav.settings'), {
    href: '/settings',
    class: 'settings-link home-nav-action',
  });
  nav.append(
    button(t('miniapp.home.create_wishlist'), async () => {
      try {
        const list = await api('/api/wishlists', {method: 'POST', body: '{}'});
        await showList(list.id);
      } catch (_) { status(t('miniapp.home.create_failed')); }
    }, 'btn-primary home-create-btn'),
    button(t('miniapp.home.viewing_history'), showHistory, 'home-nav-action'),
    settingsLink
  );
  root.append(nav);
  status(t('nav.loading'));
  try {
    const [lists, favs, deletedLists] = await Promise.all([
      api('/api/wishlists'),
      api('/api/favorites').catch(() => []),
      api('/api/wishlists/deleted').catch(() => [])
    ]);

    const myLists = lists.filter(l => l.role === 'owner');
    const collabLists = lists.filter(l => ['admin', 'member'].includes(l.role));
    const activeIds = new Set(lists.map(l => l.id));
    const pureFavs = (Array.isArray(favs) ? favs : []).filter(
      l => !activeIds.has(l.id) && !['owner', 'admin', 'member'].includes(l.role)
    );

    // My wishlists section
    const myTitle = t('miniapp.home.my_wishlists');
    const mySection = node('section', '', {
      'aria-label': myTitle,
      role: 'region',
      class: 'wishlist-section wishlist-section--owned'
    });
    renderSectionHeader(
      mySection,
      myTitle,
      myLists.length,
      t('miniapp.home.my_wishlists_sub')
    );
    if (myLists.length === 0) {
      mySection.append(
        renderEmptyState(
          'miniapp.home.my_wishlists_empty',
          'miniapp.home.my_wishlists_empty_hint'
        )
      );
    } else {
      myLists.forEach(l => mySection.append(wishlistCard(l, () => showList(l.id))));
    }
    root.append(mySection);

    // Collaborating section
    const collabTitle = t('miniapp.home.collaborating');
    const collabSection = node('section', '', {
      'aria-label': collabTitle,
      role: 'region',
      class: 'wishlist-section wishlist-section--collab'
    });
    renderSectionHeader(
      collabSection,
      collabTitle,
      collabLists.length,
      t('miniapp.home.collaborating_sub')
    );
    if (collabLists.length === 0) {
      collabSection.append(
        renderEmptyState(
          'miniapp.home.collaborating_empty',
          'miniapp.home.collaborating_empty_hint'
        )
      );
    } else {
      collabLists.forEach(l => collabSection.append(wishlistCard(l, () => showList(l.id))));
    }
    root.append(collabSection);

    // Favorites section
    const favTitle = t('miniapp.home.favorites');
    const favSection = node('section', '', {
      'aria-label': favTitle,
      role: 'region',
      class: 'wishlist-section wishlist-section--favorites'
    });
    renderSectionHeader(
      favSection,
      favTitle,
      pureFavs.length,
      t('miniapp.home.favorites_sub')
    );
    if (pureFavs.length === 0) {
      favSection.append(
        renderEmptyState(
          'miniapp.home.favorites_empty',
          'miniapp.home.favorites_empty_hint'
        )
      );
    } else {
      pureFavs.forEach(l => {
        const itemTitle = l.name || t('miniapp.common.untitled_wishlist');
        const removeBtn = button(t('miniapp.home.remove_favorite'), async () => {
          try {
            await api(`/api/favorites/${l.id}`, {method: 'DELETE'});
            await showHome();
            status(t('miniapp.home.removed_from_favorites'));
          } catch (_) { status(t('miniapp.home.remove_favorite_failed')); }
        }, 'wishlist-card-remove');
        removeBtn.setAttribute(
          'aria-label',
          t('miniapp.home.remove_favorite_named', {name: itemTitle})
        );
        const card = wishlistCard(l, () => showList(l.id), {secondaryAction: removeBtn});
        favSection.append(card);
      });
    }
    root.append(favSection);

    // Recently deleted section (owner-only, within retention window)
    if (Array.isArray(deletedLists) && deletedLists.length > 0) {
      const deletedTitle = t('miniapp.deleted.heading');
      const deletedSection = node('section', '', {
        'aria-label': deletedTitle,
        role: 'region',
        class: 'wishlist-section deleted-section wishlist-section--deleted'
      });
      renderSectionHeader(
        deletedSection,
        deletedTitle,
        deletedLists.length,
        t('miniapp.home.deleted_sub')
      );
      deletedLists.forEach(l => {
        const card = node('div', '', {class: 'wishlist-card deleted-wishlist-card'});
        const header = node('div', '', {class: 'wishlist-card-header'});
        header.append(
          node('h3', l.name || t('miniapp.common.untitled_wishlist'), {
            class: 'wishlist-card-title'
          }),
          node('span', t('miniapp.deleted.days_left', {days: l.days_remaining}), {
            class: 'history-time deleted-meta'
          })
        );
        card.append(header);
        const restoreBtn = button(t('miniapp.deleted.restore'), async () => {
          restoreBtn.disabled = true;
          status(t('miniapp.deleted.restoring'));
          try {
            await api(`/api/wishlists/${l.id}/restore-deleted`, {method: 'POST'});
            await showHome();
            status(t('miniapp.deleted.restored'));
          } catch (err) {
            restoreBtn.disabled = false;
            if (err && err.status === 410) {
              await showHome();
              status(t('miniapp.deleted.expired'));
            } else {
              status(t('miniapp.deleted.restore_failed'));
            }
          }
        }, 'wishlist-card-restore');
        const actions = node('div', '', {class: 'wishlist-card-actions'});
        actions.append(restoreBtn);
        card.append(actions);
        deletedSection.append(card);
      });
      root.append(deletedSection);
    }
    try {
      const cardResponse = await fetch('/web/reservations/card', {
        credentials: 'same-origin',
      });
      if (cardResponse.ok) {
        const parsed = new DOMParser().parseFromString(
          await cardResponse.text(),
          'text/html',
        );
        const sourceLink = parsed.querySelector('a');
        const title = parsed.querySelector('.reservations-title');
        const badge = parsed.querySelector('.reservations-badge');
        if (sourceLink && title && badge) {
          const card = node('a', '', {
            href: sourceLink.getAttribute('href') || '',
            class: 'reservations-card',
          });
          const main = node('span', '', {class: 'reservations-card-main'});
          main.append(
            node('span', title.textContent || '', {class: 'reservations-title'}),
            node('span', t('miniapp.home.reservations_hint'), {
              class: 'reservations-card-hint',
            }),
          );
          card.append(
            main,
            node('span', badge.textContent || '', {class: 'reservations-badge'}),
          );
          const firstSection = root.querySelector('.wishlist-section');
          if (firstSection) root.insertBefore(card, firstSection);
        }
      }
    } catch (_) {
      // A failed card leaves the three sections in place.
    }
    status('');
  } catch (_) { status(t('miniapp.home.load_failed')); }
}
function settingsForm(list) {
  const form = node('form', '', {class: 'wishlist-settings-form'});
  const inputs = {};
  for (const [name, label, type, hint] of [
    ['name', 'title', 'text', 'title'],
    ['description', 'description', 'text', 'description'],
    ['event_title', 'event', 'text', 'event'],
    ['event_date', 'date', 'datetime-local', 'date']
  ]) {
    const wrap = node('label', '', {class: 'settings-field'});
    wrap.append(node('span', t(`miniapp.wishlist_settings.field_${label}`),
      {class: 'settings-field-label'}));
    const input = node('input', '', {name, type});
    const raw = list[name] || '';
    input.value = name === 'event_date' && raw ? new Date(raw).toISOString().slice(0, 16) : raw;
    inputs[name] = input;
    wrap.append(input, node('span', t(`miniapp.wishlist_settings.hint_${hint}`),
      {class: 'settings-field-hint'}));
    form.append(wrap);
  }
  const save = node('button', t('miniapp.wishlist_settings.save'), {
    type: 'submit', class: 'btn-primary settings-save-btn'
  });
  const actions = node('div', '', {class: 'form-actions settings-form-actions'});
  actions.append(save, button(t('miniapp.wishlist_settings.cancel'), async () => {
    if (await showList(list.id)) status(t('miniapp.wishlist_settings.cancelled'));
  }, 'settings-cancel-btn'));
  form.append(actions);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    save.disabled = true;
    try {
      const date = inputs.event_date.value;
      const data = {name: inputs.name.value, description: inputs.description.value || null,
        event_title: inputs.event_title.value || null,
        event_date: date ? new Date(`${date}Z`).toISOString() : null};
      await api(`/api/wishlists/${list.id}`, {method: 'PATCH', body: JSON.stringify(data)});
      const refreshed = await showList(list.id);
      status(t(refreshed ? 'miniapp.wishlist_settings.saved' :
        'miniapp.wishlist_settings.saved_refresh_failed'));
    } catch (_) { status(t('miniapp.wishlist_settings.save_failed')); }
    finally { save.disabled = false; }
  });
  return form;
}
function memberControls(list) {
  const section = node('section', '', {class: 'list-admin-section list-members-section',
    role: 'region', 'aria-label': t('miniapp.members.heading')});
  section.append(node('h2', t('miniapp.members.heading')));
  section.append(node('p', t('miniapp.members.subtitle'), {class: 'section-subtitle'}));
  const members = node('div', '', {class: 'member-list'});
  for (const member of list.members || []) {
    const row = node('div', '', {class: 'member-row'});
    const info = node('div', '', {class: 'member-row-info'});
    info.append(node('span', member.display_name, {class: 'member-name'}),
      renderBadge(member.role));
    const actions = node('div', '', {class: 'member-row-actions'});
    if (member.role === 'member') actions.append(button(t('miniapp.members.remove'), async () => {
      try { await api(`/api/wishlists/${list.id}/members/${member.user_id}`, {method: 'DELETE'});
        await refreshAfterMutation(list.id, 'miniapp.members.removed');
      } catch (_) { status(t('miniapp.members.remove_failed')); }
    }, 'btn-danger member-remove-btn'));
    if (list.role === 'owner' && member.role !== 'owner') {
      const next = member.role === 'admin' ? 'member' : 'admin';
      const roleBtnLabel = next === 'admin'
        ? t('miniapp.members.make_admin')
        : t('miniapp.members.remove_admin');
      actions.append(button(roleBtnLabel, async () => {
        try { await api(`/api/wishlists/${list.id}/members/${member.user_id}/role`,
          {method: 'PATCH', body: JSON.stringify({role: next})});
          await refreshAfterMutation(list.id, 'miniapp.members.role_updated');
        } catch (_) { status(t('miniapp.members.role_change_failed')); }
      }, 'member-role-btn'));
    }
    row.append(info, actions);
    members.append(row);
  }
  section.append(members);
  const revoke = button(t('miniapp.members.revoke_invite'), async () => {
    try { await api(`/api/wishlists/${list.id}/invite/reset`, {method: 'POST'});
      await refreshAfterMutation(list.id, 'miniapp.members.invite_revoked');
    } catch (_) { status(t('miniapp.members.revoke_invite_failed')); }
  }, 'invite-revoke-btn');
  section.append(sharePanel(list.invite_token, 'i', t('miniapp.members.invite_heading'), {
    className: 'share-panel--invite', hint: t('miniapp.members.invite_hint'), footerAction: revoke
  }));
  return section;
}
async function refreshAfterMutation(id, successMessage) {
  root.replaceChildren(node('h1', t('nav.loading')));
  if (await showList(id)) {
    status(t(successMessage));
    return;
  }
  root.replaceChildren(
    node('h1', t('miniapp.list.refresh_unavailable')),
    button(t('miniapp.list.refresh_retry'), () => showList(id), 'list-refresh-retry-btn'),
    button(t('nav.back'), showHome, 'list-back-btn')
  );
  status(t('miniapp.list.changed_refresh_failed'));
}
async function showList(id) {
  status(t('nav.loading'));
  try {
    api(`/api/history/${id}`, {method: 'POST'}).catch(() => {});
    const list = await api(`/api/wishlists/${id}`);
    const listTitle = list.name || t('miniapp.common.untitled_wishlist');
    const header = node('section', '', {class: 'wishlist-detail-header'});
    const nav = node('div', '', {class: 'list-header-nav'});
    nav.append(button(t('nav.back'), showHome, 'list-back-btn'));
    if (list.role !== 'owner') {
      const isFav = Boolean(list.is_favorite);
      const favLabel = isFav
        ? t('miniapp.list.remove_favorite')
        : t('miniapp.list.add_favorite');
      nav.append(button(favLabel, async () => {
        try {
          if (isFav) {
            await api(`/api/favorites/${list.id}`, {method: 'DELETE'});
          } else {
            await api(`/api/favorites/${list.id}`, {method: 'POST'});
          }
          await refreshAfterMutation(list.id,
            isFav ? 'miniapp.list.removed_favorite' : 'miniapp.list.added_favorite');
        } catch (_) { status(t('miniapp.list.favorite_failed')); }
      }, 'list-favorite-btn'));
    }
    const titleRow = node('div', '', {class: 'list-header-title-row'});
    titleRow.append(node('h1', listTitle, {class: 'list-title'}));
    if (list.role) titleRow.append(renderBadge(list.role));
    header.append(nav, titleRow);
    const eventParts = [];
    if (list.event_title) eventParts.push(list.event_title);
    if (list.event_date) eventParts.push(formatDate(list.event_date));
    if (eventParts.length) {
      const eventText = `${t('miniapp.list.occasion_prefix')} ${eventParts.join(' · ')}`;
      header.append(node('p', eventText, {class: 'list-event-meta'}));
    }
    if (list.description) header.append(node('p', list.description, {class: 'list-description'}));
    const wishes = node('section', '', {class: 'wishlist-section list-wishes-section',
      role: 'region', 'aria-label': t('miniapp.list.wishes_heading')});
    const items = list.items || [];
    renderSectionHeader(wishes, t('miniapp.list.wishes_heading'), items.length,
      t('miniapp.list.wishes_subtitle'));
    for (const item of items) {
      const card = node('div', '', {class: 'list-wish-card'});
      card.append(node('p', item.title, {class: 'list-wish-title'}));
      wishes.append(card);
    }
    const note = node('div', '', {class: 'empty-state list-wishes-note'});
    if (!items.length) {
      note.append(node('p', t('miniapp.list.wishes_empty'), {class: 'empty-notice'}));
    }
    note.append(node('p', t('miniapp.list.wishes_future_update'), {class: 'empty-hint'}));
    wishes.append(note);
    root.replaceChildren(header, wishes);
    const manager = ['owner', 'admin'].includes(list.role);
    if (manager && list.status === 'active') {
      const settings = node('section', '', {class: 'list-admin-section list-settings-section',
        role: 'region', 'aria-label': t('miniapp.wishlist_settings.heading')});
      settings.append(node('h2', t('miniapp.wishlist_settings.heading')),
        node('p', t('miniapp.wishlist_settings.subtitle'), {class: 'section-subtitle'}),
        settingsForm(list));
      root.append(settings);
      const reset = button(t('miniapp.share.replace_public'), async () => {
        try { await api(`/api/wishlists/${list.id}/share/reset`, {method: 'POST'});
          await refreshAfterMutation(list.id, 'miniapp.share.public_replaced');
        } catch (_) { status(t('miniapp.share.replace_public_failed')); }
      }, 'share-reset-btn');
      root.append(sharePanel(list.share_token || '', 'p', t('miniapp.share.public_title'), {
        className: 'share-panel--public', hint: t('miniapp.share.public_hint'), footerAction: reset
      }));
      root.append(memberControls(list));
    } else if (list.status === 'archived') {
      const banner = node('section', '', {class: 'list-admin-section list-archived-banner'});
      banner.append(node('p', t('miniapp.list.archived_notice'), {class: 'archived-notice'}));
      if (manager) banner.append(button(t('miniapp.list.restore'), async () => {
        try {
          await api(`/api/wishlists/${list.id}/restore`, {method: 'POST'});
          await refreshAfterMutation(id, 'miniapp.list.restored');
        } catch (_) { status(t('miniapp.list.restore_failed')); }
      }, 'btn-primary list-restore-btn'));
      root.append(banner);
    }
    status('');
    return true;
  } catch (_) { status(t('miniapp.list.load_failed')); return false; }
}
function unavailableLink() {
  root.replaceChildren(
    node('h1', t('miniapp.unavailable.title')),
    node('p', t('miniapp.unavailable.description')),
    button(t('miniapp.unavailable.home_menu'), async () => {
      try { await bootstrap(); await showHome(); }
      catch (_) { status(t('miniapp.auth.open_in_telegram')); }
    })
  );
  status('');
}
async function publicView(token) {
  root.replaceChildren(node('h1', t('miniapp.public.loading')));
  try { await bootstrap(); } catch (_) { /* Guest view remains available. */ }
  try {
    const list = await api(`/api/public/wishlists/${encodeURIComponent(token)}/view`);
    root.replaceChildren(node('h1', list.title || t('miniapp.common.untitled_wishlist')),
      node('p', list.description || ''));
    for (const item of list.items || []) {
      const section = node('section');
      section.append(node('h2', item.title));
      if (list.identified && list.status === 'active' && !item.is_recipient &&
          !item.is_archived && !item.is_fully_received && !item.is_reserved_by_me &&
          item.available_quantity > 0) {
        let pendingKey = '';
        section.append(button(t('miniapp.public.reserve'), async () => {
          if (!pendingKey) pendingKey = nextIdempotencyKey();
          try {
            await api(
              `/api/public/wishlists/${encodeURIComponent(token)}/items/${item.id}/reservations`,
              {
                method: 'POST',
                headers: {'Idempotency-Key': pendingKey},
                body: JSON.stringify({quantity: 1}),
              }
            );
            pendingKey = '';
            await publicView(token);
            status(t('miniapp.public.reserved'));
          } catch (err) {
            if (err && err.status && err.status !== 503) pendingKey = '';
            status(t('miniapp.public.reserve_failed'));
          }
        }, 'btn-primary'));
      }
      root.append(section);
    }
    root.append(sharePanel(token, 'p', t('miniapp.share.public_title')));
    status('');
  } catch (_) { unavailableLink(); }
}
async function invitationView(token) {
  root.replaceChildren(node('h1', t('miniapp.invite.heading')));
  try {
    const invite = await api('/api/invitations/preview', {headers: {'X-Invite-Token': token}});
    const invitePrompt = t('miniapp.invite.prompt', {
      name: invite.name || t('miniapp.invite.default_name'),
    });
    root.append(node('p', invitePrompt));
    root.append(button(t('miniapp.invite.confirm'), async () => {
      try {
        await bootstrap();
        const result = await api('/api/invitations/accept', {method: 'POST', body: '{}',
          headers: {'X-Invite-Token': token}});
        await showList(result.wishlist_id);
      } catch (_) { status(t('miniapp.invite.join_failed')); }
    }, 'btn-primary'));
    status('');
  } catch (_) { status(t('miniapp.invite.unavailable')); }
}
async function bootstrap() {
  let me = null;
  try {
    me = await api('/api/auth/me');
  } catch (_) {
    if (!bridge?.initData) throw new Error('Telegram authentication required');
    const auth = await api('/api/auth/telegram', {
      method: 'POST',
      body: JSON.stringify({init_data: bridge.initData}),
    });
    const authLocale = auth?.locale || auth?.user?.locale;
    if (authLocale) {
      profileLocale = normalizeLocale(authLocale);
      document.documentElement.lang = profileLocale;
      if (root) root.dataset.locale = profileLocale;
    }
  }
  const meLocale = me?.locale || me?.user?.locale;
  if (meLocale) {
    profileLocale = normalizeLocale(meLocale);
    document.documentElement.lang = profileLocale;
    if (root) root.dataset.locale = profileLocale;
  }
  csrf = (await api('/api/auth/csrf')).csrf_token;
}
async function start() {
  if (!bridge) {
    await new Promise(resolve => {
      const script = document.createElement('script');
      script.src = 'https://telegram.org/js/telegram-web-app.js';
      script.onload = resolve;
      script.onerror = resolve;
      document.head.append(script);
      setTimeout(resolve, 3000);
    });
    bridge = window.Telegram?.WebApp;
  }
  bridge?.ready?.();
  bridge?.expand?.();
  const startParam =
    bridge?.initDataUnsafe?.start_param ||
    new URLSearchParams(location.search).get('startapp');
  if (startParam && /^[pi]_[A-Za-z0-9_-]{1,128}$/.test(startParam)) {
    const [prefix, ...rest] = startParam.split('_');
    const token = rest.join('_');
    if (prefix === 'p') return publicView(token);
    return invitationView(token);
  }
  if (startParam && !['home', 'create', 'collection'].includes(startParam)) {
    return unavailableLink();
  }
  try {
    await bootstrap();
    await showHome();
    if (startParam === 'create') {
      root.querySelector('button')?.focus();
    }
  } catch (_) { status(t('miniapp.auth.open_in_telegram')); }
}
start();
