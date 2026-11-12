/* Wishlist management in the Telegram Mini App. */
const root = document.getElementById('app');
let bridge = window.Telegram?.WebApp;
let csrf = '';

function node(tag, text = '', attributes = {}) {
  const el = document.createElement(tag);
  el.textContent = text;
  Object.entries(attributes).forEach(([name, value]) => el.setAttribute(name, value));
  return el;
}
function button(text, handler) {
  const el = node('button', text, {type: 'button'});
  el.addEventListener('click', handler);
  return el;
}
function status(message) {
  document.getElementById('status').textContent = message;
}
async function api(path, options = {}) {
  const method = options.method || 'GET';
  const headers = {...options.headers};
  if (!['GET', 'HEAD'].includes(method)) headers['X-CSRF-Token'] = csrf;
  if (options.body) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {...options, headers, credentials: 'same-origin'});
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}
function linkFor(prefix, token) {
  const bot = root.dataset.bot;
  const app = root.dataset.miniapp;
  if (!/^[A-Za-z0-9_]{1,64}$/.test(bot) || !/^[A-Za-z0-9_]{1,64}$/.test(app) ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(token || '')) throw new Error('Sharing is not configured');
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
  panel.append(button('Copy link', async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(url);
      status('Link copied');
    } catch (_) { field.select(); status('Copy failed. Select the link and copy it manually.'); }
  }));
  panel.append(button('Share via Telegram', () => {
    try {
      if (!bridge?.openTelegramLink) throw new Error('Telegram unavailable');
      bridge.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}`);
      status('Telegram chooser opened');
    } catch (_) { status('Telegram sharing is unavailable'); }
  }));
  return panel;
}
function roleLabel(role) {
  switch (role) {
    case 'owner': return 'Владелец';
    case 'admin': return 'Администратор';
    case 'member': return 'Соавтор';
    case 'favorite': return 'Избранное';
    default: return role;
  }
}
function renderBadge(role) {
  return node('span', roleLabel(role), {class: `badge badge-${role}`});
}
function wishlistCard(list, onClick) {
  const card = node('div', '', {class: 'wishlist-card'});
  const titleBtn = button(list.name || 'Untitled wishlist', onClick);
  card.append(titleBtn);
  if (list.role) {
    card.append(renderBadge(list.role));
  }
  return card;
}
async function showHistory() {
  root.replaceChildren(
    button('Back', showHome),
    node('h1', 'Viewing history')
  );
  status('Loading');
  try {
    const history = await api('/api/history');
    if (history.length > 0) {
      root.append(button('Clear history', async () => {
        try {
          await api('/api/history', {method: 'DELETE'});
          await showHistory();
          status('History cleared');
        } catch (_) { status('Could not clear history'); }
      }));
    }
    const historySection = node('section', '', {'aria-label': 'Viewing history', role: 'region'});
    if (history.length === 0) {
      historySection.append(node('p', 'No viewing history yet'));
    } else {
      history.forEach(item => {
        const row = node('div', '', {class: 'history-item'});
        row.append(button(item.name || 'Untitled wishlist', () => showList(item.id)));
        if (item.viewed_at) {
          const dateStr = new Date(item.viewed_at).toLocaleString();
          row.append(node('span', ` Viewed: ${dateStr} `, {class: 'history-time'}));
        }
        if (item.role) {
          row.append(renderBadge(item.role));
        }
        historySection.append(row);
      });
    }
    root.append(historySection);
    status('');
  } catch (_) { status('Could not load history'); }
}
async function showHome() {
  root.replaceChildren(node('h1', 'Wishlists'));
  const nav = node('nav', '', {class: 'top-nav'});
  nav.append(
    button('Create wishlist', async () => {
      try {
        const list = await api('/api/wishlists', {method: 'POST', body: '{}'});
        await showList(list.id);
      } catch (_) { status('Could not create wishlist. Try again.'); }
    }),
    button('Viewing history', showHistory)
  );
  root.append(nav);
  status('Loading');
  try {
    const [lists, favs] = await Promise.all([
      api('/api/wishlists'),
      api('/api/favorites').catch(() => [])
    ]);

    const myLists = lists.filter(l => l.role === 'owner');
    const collabLists = lists.filter(l => ['admin', 'member'].includes(l.role));

    // My wishlists section
    const mySection = node('section', '', {
      'aria-label': 'My wishlists',
      role: 'region',
      class: 'wishlist-section'
    });
    mySection.append(node('h2', 'My wishlists'));
    if (myLists.length === 0) {
      mySection.append(node('p', 'No personal wishlists yet', {class: 'empty-notice'}));
    } else {
      myLists.forEach(l => mySection.append(wishlistCard(l, () => showList(l.id))));
    }
    root.append(mySection);

    // Collaborating section
    const collabSection = node('section', '', {
      'aria-label': 'Collaborating',
      role: 'region',
      class: 'wishlist-section'
    });
    collabSection.append(node('h2', 'Collaborating'));
    if (collabLists.length === 0) {
      collabSection.append(node('p', 'No collaborative wishlists yet', {class: 'empty-notice'}));
    } else {
      collabLists.forEach(l => collabSection.append(wishlistCard(l, () => showList(l.id))));
    }
    root.append(collabSection);

    // Favorites section
    const favSection = node('section', '', {
      'aria-label': 'Favorites',
      role: 'region',
      class: 'wishlist-section'
    });
    favSection.append(node('h2', 'Favorites'));
    if (favs.length === 0) {
      favSection.append(node('p', 'No favorites yet', {class: 'empty-notice'}));
    } else {
      favs.forEach(l => {
        const card = wishlistCard(l, () => showList(l.id));
        card.append(button('Remove', async () => {
          try {
            await api(`/api/favorites/${l.id}`, {method: 'DELETE'});
            await showHome();
            status('Removed from favorites');
          } catch (_) { status('Could not remove from favorites'); }
        }));
        favSection.append(card);
      });
    }
    root.append(favSection);
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
  } catch (_) { status('Could not load wishlists. Check your session and try again.'); }
}
function settingsForm(list) {
  const form = node('form');
  const inputs = {};
  for (const [name, label, type] of [
    ['name', 'Title', 'text'], ['description', 'Description', 'text'],
    ['event_title', 'Event', 'text'], ['event_date', 'Date', 'datetime-local']
  ]) {
    const wrap = node('label', label);
    const input = node('input', '', {name, type});
    const raw = list[name] || '';
    input.value = name === 'event_date' && raw ? new Date(raw).toISOString().slice(0, 16) : raw;
    inputs[name] = input;
    wrap.append(input);
    form.append(wrap);
  }
  const save = node('button', 'Save settings', {type: 'submit'});
  form.append(save, button('Cancel', () => showList(list.id)));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const date = inputs.event_date.value;
      const data = {name: inputs.name.value, description: inputs.description.value || null,
        event_title: inputs.event_title.value || null,
        event_date: date ? new Date(`${date}Z`).toISOString() : null};
      await api(`/api/wishlists/${list.id}`, {method: 'PATCH', body: JSON.stringify(data)});
      status('Settings saved');
      await showList(list.id);
    } catch (_) { status('Could not save settings. Your changes are still here.'); }
  });
  return form;
}
function memberControls(list) {
  const section = node('section');
  section.append(node('h2', 'Manage members'));
  for (const member of list.members || []) {
    const row = node('div', `${member.display_name} (${member.role}) `);
    if (member.role === 'member') row.append(button('Remove member', async () => {
      try { await api(`/api/wishlists/${list.id}/members/${member.user_id}`, {method: 'DELETE'});
        await showList(list.id); status('Member removed');
      } catch (_) { status('Could not remove member'); }
    }));
    if (list.role === 'owner' && member.role !== 'owner') {
      const next = member.role === 'admin' ? 'member' : 'admin';
      row.append(button(next === 'admin' ? 'Make admin' : 'Remove admin', async () => {
        try { await api(`/api/wishlists/${list.id}/members/${member.user_id}/role`,
          {method: 'PATCH', body: JSON.stringify({role: next})}); await showList(list.id);
        } catch (_) { status('Could not change role'); }
      }));
    }
    section.append(row);
  }
  section.append(sharePanel(list.invite_token, 'i', 'Collaborator invitation'));
  section.append(button('Revoke invitation', async () => {
    try { await api(`/api/wishlists/${list.id}/invite/reset`, {method: 'POST'});
      await showList(list.id); status('Old invitation revoked');
    } catch (_) { status('Could not revoke invitation'); }
  }));
  return section;
}
async function showList(id) {
  status('Loading');
  try {
    api(`/api/history/${id}`, {method: 'POST'}).catch(() => {});
    const list = await api(`/api/wishlists/${id}`);
    root.replaceChildren(button('Back', showHome), node('h1', list.name || 'Untitled wishlist'));
    if (list.role) {
      root.append(renderBadge(list.role));
    }
    if (list.role !== 'owner') {
      const isFav = Boolean(list.is_favorite);
      root.append(button(isFav ? 'Remove from favorites' : 'Add to favorites', async () => {
        try {
          if (isFav) {
            await api(`/api/favorites/${list.id}`, {method: 'DELETE'});
            status('Removed from favorites');
          } else {
            await api(`/api/favorites/${list.id}`, {method: 'POST'});
            status('Added to favorites');
          }
          await showList(list.id);
        } catch (_) { status('Could not update favorites'); }
      }));
    }
    root.append(node('p', list.description || ''), node('h2', 'Wishes'));
    for (const item of list.items || []) root.append(node('p', item.title));
    root.append(node('p', 'Adding wishes will be available in a future update.'));
    const manager = ['owner', 'admin'].includes(list.role);
    if (manager && list.status === 'active') {
      root.append(node('h2', 'Settings'), settingsForm(list));
      root.append(sharePanel(list.share_token || '', 'p', 'Public gift-selection link'));
      root.append(button('Replace public link', async () => {
        try { await api(`/api/wishlists/${list.id}/share/reset`, {method: 'POST'});
          await showList(list.id); status('Old public link no longer works');
        } catch (_) { status('Could not replace the public link'); }
      }));
      root.append(memberControls(list));
    } else if (list.status === 'archived') {
      root.append(node('p', 'This wishlist is archived and read-only.'));
      if (manager) root.append(button('Restore wishlist', async () => {
        try {
          await api(`/api/wishlists/${list.id}/restore`, {method: 'POST'});
          await showList(id);
        } catch (_) { status('Could not restore wishlist'); }
      }));
    }
    status('');
  } catch (_) { status('Could not load this wishlist'); }
}
async function publicView(token) {
  root.replaceChildren(node('h1', 'Loading wishlist'));
  try {
    const list = await api(`/api/public/wishlists/${encodeURIComponent(token)}`);
    root.replaceChildren(
      node('h1', list.name || 'Untitled wishlist'),
      node('p', list.description || ''),
    );
    for (const item of list.items || []) root.append(node('p', item.title));
    root.append(sharePanel(token, 'p', 'Public gift-selection link'));
    status('');
  } catch (_) { status('This public link is unavailable'); }
}
async function invitationView(token) {
  root.replaceChildren(node('h1', 'Collaborator invitation'));
  try {
    const invite = await api('/api/invitations/preview', {headers: {'X-Invite-Token': token}});
    root.append(node('p', `Join ${invite.name || 'wishlist'} as a member?`));
    root.append(button('Confirm joining', async () => {
      try {
        await bootstrap();
        const result = await api('/api/invitations/accept', {method: 'POST', body: '{}',
          headers: {'X-Invite-Token': token}});
        await showList(result.wishlist_id);
      } catch (_) { status('Could not join. Check your Telegram session or invitation.'); }
    }));
    status('');
  } catch (_) { status('This invitation is unavailable'); }
}
async function bootstrap() {
  try { await api('/api/auth/me'); }
  catch (_) {
    if (!bridge?.initData) throw new Error('Telegram authentication required');
    await api('/api/auth/telegram', {
      method: 'POST',
      body: JSON.stringify({init_data: bridge.initData}),
    });
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
  try { await bootstrap(); await showHome(); }
  catch (_) { status('Open this app in Telegram to sign in.'); }
}
start();
