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
  if (className) el.className = className;
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
function sharePanel(token, prefix, title) {
  const panel = node('section');
  panel.append(node('h2', title));
  let url;
  try { url = linkFor(prefix, token); } catch (error) {
    panel.append(node('p', error.message));
    return panel;
  }
  const field = node('input', '', {value: url, readonly: '', 'aria-label': title});
  panel.append(field);
  panel.append(button(t('miniapp.share.copy_link'), async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(url);
      status(t('miniapp.share.link_copied'));
    } catch (_) { field.select(); status(t('miniapp.share.copy_failed')); }
  }));
  panel.append(button(t('miniapp.share.share_telegram'), () => {
    try {
      if (!bridge?.openTelegramLink) throw new Error('Telegram unavailable');
      bridge.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}`);
      status(t('miniapp.share.telegram_opened'));
    } catch (_) { status(t('miniapp.share.telegram_unavailable')); }
  }, 'btn-primary'));
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
function wishlistCard(list, onClick) {
  const card = node('div', '', {class: 'wishlist-card'});
  const titleBtn = button(list.name || t('miniapp.common.untitled_wishlist'), onClick);
  card.append(titleBtn);
  if (list.role) {
    card.append(renderBadge(list.role));
  }
  return card;
}
async function showHistory() {
  const historyTitle = t('miniapp.history.title');
  root.replaceChildren(
    button(t('nav.back'), showHome),
    node('h1', historyTitle)
  );
  status(t('nav.loading'));
  try {
    const history = await api('/api/history');
    if (history.length > 0) {
      root.append(button(t('miniapp.history.clear'), async () => {
        try {
          await api('/api/history', {method: 'DELETE'});
          await showHistory();
          status(t('miniapp.history.cleared'));
        } catch (_) { status(t('miniapp.history.clear_failed')); }
      }, 'btn-danger'));
    }
    const historySection = node('section', '', {'aria-label': historyTitle, role: 'region'});
    if (history.length === 0) {
      historySection.append(node('p', t('miniapp.history.empty')));
    } else {
      history.forEach(item => {
        const row = node('div', '', {class: 'history-item'});
        const title = item.name || t('miniapp.common.untitled_wishlist');
        row.append(button(title, () => showList(item.id)));
        if (item.viewed_at) {
          const dateStr = formatDateTime(item.viewed_at);
          const viewedLabel = ` ${t('miniapp.history.viewed_at', {date: dateStr})} `;
          row.append(node('span', viewedLabel, {class: 'history-time'}));
        }
        if (item.role) {
          row.append(renderBadge(item.role));
        }
        historySection.append(row);
      });
    }
    root.append(historySection);
    status('');
  } catch (_) { status(t('miniapp.history.load_failed')); }
}
async function showHome() {
  root.replaceChildren(node('h1', t('miniapp.home.title')));
  const nav = node('nav', '', {class: 'top-nav'});
  const settingsLink = node('a', t('nav.settings'), {
    href: '/settings',
    class: 'settings-link',
  });
  nav.append(
    button(t('miniapp.home.create_wishlist'), async () => {
      try {
        const list = await api('/api/wishlists', {method: 'POST', body: '{}'});
        await showList(list.id);
      } catch (_) { status(t('miniapp.home.create_failed')); }
    }, 'btn-primary'),
    button(t('miniapp.home.viewing_history'), showHistory),
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

    // My wishlists section
    const myTitle = t('miniapp.home.my_wishlists');
    const mySection = node('section', '', {
      'aria-label': myTitle,
      role: 'region',
      class: 'wishlist-section'
    });
    mySection.append(node('h2', myTitle));
    if (myLists.length === 0) {
      mySection.append(node('p', t('miniapp.home.my_wishlists_empty'), {class: 'empty-notice'}));
    } else {
      myLists.forEach(l => mySection.append(wishlistCard(l, () => showList(l.id))));
    }
    root.append(mySection);

    // Collaborating section
    const collabTitle = t('miniapp.home.collaborating');
    const collabSection = node('section', '', {
      'aria-label': collabTitle,
      role: 'region',
      class: 'wishlist-section'
    });
    collabSection.append(node('h2', collabTitle));
    if (collabLists.length === 0) {
      collabSection.append(
        node('p', t('miniapp.home.collaborating_empty'), {class: 'empty-notice'})
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
      class: 'wishlist-section'
    });
    favSection.append(node('h2', favTitle));
    if (favs.length === 0) {
      favSection.append(node('p', t('miniapp.home.favorites_empty'), {class: 'empty-notice'}));
    } else {
      favs.forEach(l => {
        const card = wishlistCard(l, () => showList(l.id));
        card.append(button(t('miniapp.home.remove'), async () => {
          try {
            await api(`/api/favorites/${l.id}`, {method: 'DELETE'});
            await showHome();
            status(t('miniapp.home.removed_from_favorites'));
          } catch (_) { status(t('miniapp.home.remove_favorite_failed')); }
        }));
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
        class: 'wishlist-section deleted-section'
      });
      deletedSection.append(node('h2', deletedTitle));
      deletedLists.forEach(l => {
        const card = node('div', '', {class: 'wishlist-card deleted-wishlist-card'});
        card.append(
          node('span', l.name || t('miniapp.common.untitled_wishlist')),
          node('span', t('miniapp.deleted.days_left', {days: l.days_remaining}), {
            class: 'history-time deleted-meta'
          })
        );
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
        });
        card.append(restoreBtn);
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
          });
          card.append(
            node('span', title.textContent || ''),
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
  const form = node('form');
  const inputs = {};
  for (const [name, label, type] of [
    ['name', t('miniapp.wishlist_settings.field_title'), 'text'],
    ['description', t('miniapp.wishlist_settings.field_description'), 'text'],
    ['event_title', t('miniapp.wishlist_settings.field_event'), 'text'],
    ['event_date', t('miniapp.wishlist_settings.field_date'), 'datetime-local']
  ]) {
    const wrap = node('label', label);
    const input = node('input', '', {name, type});
    const raw = list[name] || '';
    input.value = name === 'event_date' && raw ? new Date(raw).toISOString().slice(0, 16) : raw;
    inputs[name] = input;
    wrap.append(input);
    form.append(wrap);
  }
  const save = node('button', t('miniapp.wishlist_settings.save'), {
    type: 'submit', class: 'btn-primary'
  });
  form.append(save, button(t('miniapp.wishlist_settings.cancel'), () => showList(list.id)));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const date = inputs.event_date.value;
      const data = {name: inputs.name.value, description: inputs.description.value || null,
        event_title: inputs.event_title.value || null,
        event_date: date ? new Date(`${date}Z`).toISOString() : null};
      await api(`/api/wishlists/${list.id}`, {method: 'PATCH', body: JSON.stringify(data)});
      status(t('miniapp.wishlist_settings.saved'));
      await showList(list.id);
    } catch (_) { status(t('miniapp.wishlist_settings.save_failed')); }
  });
  return form;
}
function memberControls(list) {
  const section = node('section');
  section.append(node('h2', t('miniapp.members.heading')));
  for (const member of list.members || []) {
    const row = node('div', `${member.display_name} (${roleLabel(member.role)}) `);
    if (member.role === 'member') row.append(button(t('miniapp.members.remove'), async () => {
      try { await api(`/api/wishlists/${list.id}/members/${member.user_id}`, {method: 'DELETE'});
        await showList(list.id); status(t('miniapp.members.removed'));
      } catch (_) { status(t('miniapp.members.remove_failed')); }
    }, 'btn-danger'));
    if (list.role === 'owner' && member.role !== 'owner') {
      const next = member.role === 'admin' ? 'member' : 'admin';
      const roleBtnLabel = next === 'admin'
        ? t('miniapp.members.make_admin')
        : t('miniapp.members.remove_admin');
      row.append(button(roleBtnLabel, async () => {
        try { await api(`/api/wishlists/${list.id}/members/${member.user_id}/role`,
          {method: 'PATCH', body: JSON.stringify({role: next})}); await showList(list.id);
        } catch (_) { status(t('miniapp.members.role_change_failed')); }
      }));
    }
    section.append(row);
  }
  section.append(sharePanel(list.invite_token, 'i', t('miniapp.members.invite_heading')));
  section.append(button(t('miniapp.members.revoke_invite'), async () => {
    try { await api(`/api/wishlists/${list.id}/invite/reset`, {method: 'POST'});
      await showList(list.id); status(t('miniapp.members.invite_revoked'));
    } catch (_) { status(t('miniapp.members.revoke_invite_failed')); }
  }));
  return section;
}
async function showList(id) {
  status(t('nav.loading'));
  try {
    api(`/api/history/${id}`, {method: 'POST'}).catch(() => {});
    const list = await api(`/api/wishlists/${id}`);
    const listTitle = list.name || t('miniapp.common.untitled_wishlist');
    root.replaceChildren(button(t('nav.back'), showHome), node('h1', listTitle));
    if (list.role) {
      root.append(renderBadge(list.role));
    }
    if (list.role !== 'owner') {
      const isFav = Boolean(list.is_favorite);
      const favLabel = isFav
        ? t('miniapp.list.remove_favorite')
        : t('miniapp.list.add_favorite');
      root.append(button(favLabel, async () => {
        try {
          if (isFav) {
            await api(`/api/favorites/${list.id}`, {method: 'DELETE'});
            status(t('miniapp.list.removed_favorite'));
          } else {
            await api(`/api/favorites/${list.id}`, {method: 'POST'});
            status(t('miniapp.list.added_favorite'));
          }
          await showList(list.id);
        } catch (_) { status(t('miniapp.list.favorite_failed')); }
      }));
    }
    root.append(node('p', list.description || ''), node('h2', t('miniapp.list.wishes_heading')));
    for (const item of list.items || []) root.append(node('p', item.title));
    root.append(node('p', t('miniapp.list.wishes_future_update')));
    const manager = ['owner', 'admin'].includes(list.role);
    if (manager && list.status === 'active') {
      root.append(node('h2', t('miniapp.wishlist_settings.heading')), settingsForm(list));
      root.append(sharePanel(list.share_token || '', 'p', t('miniapp.share.public_title')));
      root.append(button(t('miniapp.share.replace_public'), async () => {
        try { await api(`/api/wishlists/${list.id}/share/reset`, {method: 'POST'});
          await showList(list.id); status(t('miniapp.share.public_replaced'));
        } catch (_) { status(t('miniapp.share.replace_public_failed')); }
      }));
      root.append(memberControls(list));
    } else if (list.status === 'archived') {
      root.append(node('p', t('miniapp.list.archived_notice')));
      if (manager) root.append(button(t('miniapp.list.restore'), async () => {
        try {
          await api(`/api/wishlists/${list.id}/restore`, {method: 'POST'});
          await showList(id);
        } catch (_) { status(t('miniapp.list.restore_failed')); }
      }));
    }
    status('');
  } catch (_) { status(t('miniapp.list.load_failed')); }
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
