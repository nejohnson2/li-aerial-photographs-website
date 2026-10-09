/* Gallery page: browsable card grid of every item, including non-georeferenced ones. */

const state = { catalog: null, activeCollections: new Set(), query: '', geoOnly: false, addressHits: null };

const grid = document.getElementById('grid');
const dialog = document.getElementById('item-dialog');
const dialogBody = document.getElementById('dialog-body');

function thumbUrl(item) { return `/thumb/${item.collection}/${item.id}.jpg`; }

function matches(item) {
  if (state.activeCollections.size && !state.activeCollections.has(item.collection)) return false;
  if (state.geoOnly && !item.georeferenced) return false;
  // While an address filter is active it replaces the text match (the query
  // text is the address itself).
  if (state.addressHits) return state.addressHits.has(`${item.collection}/${item.id}`);
  if (state.query) {
    const hay = `${item.frame} ${item.town} ${item.date} ${item.coverage}`.toLowerCase();
    if (!hay.includes(state.query)) return false;
  }
  return true;
}

async function searchAddress(q) {
  const status = document.getElementById('addr-status');
  status.textContent = 'Looking up address…';
  const geo = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
  if (!geo.ok) {
    const err = await geo.json().catch(() => ({}));
    status.textContent = err.error || 'Address lookup failed.';
    return;
  }
  const { lon, lat, matched_address } = await geo.json();
  const loc = await fetch(`/api/locate?lon=${lon}&lat=${lat}`).then(r => r.json());
  state.addressHits = new Set(
    loc.surveys.filter(s => s.covered).flatMap(s => s.frames.map(fr => `${s.collection}/${fr.id}`)));
  status.innerHTML = `<span class="addr-chip">📍 ${matched_address}
    <button type="button" title="Clear address filter">×</button></span>`;
  status.querySelector('button').onclick = () => {
    state.addressHits = null;
    status.textContent = '';
    render();
  };
  render();
}

function wireAddressSearch() {
  const input = document.getElementById('search');
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn';
  btn.textContent = '📍 Address';
  btn.title = 'Find images covering a street address';
  btn.onclick = () => input.value.trim().length >= 4 && searchAddress(input.value.trim());
  input.insertAdjacentElement('afterend', btn);
  const status = document.createElement('span');
  status.id = 'addr-status';
  status.className = 'muted';
  btn.insertAdjacentElement('afterend', status);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && input.value.trim().length >= 4) searchAddress(input.value.trim());
  });
}

function render() {
  const colls = state.catalog.collections;
  const items = state.catalog.items.filter(matches);
  document.getElementById('gallery-count').textContent =
    `${items.length} of ${state.catalog.items.length} items`;
  grid.innerHTML = '';
  const frag = document.createDocumentFragment();
  for (const item of items) {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <img loading="lazy" src="${thumbUrl(item)}" alt="${item.frame}"
           onerror="this.style.visibility='hidden'">
      <div class="card-body">
        <div class="card-title">${item.frame}</div>
        <div class="card-sub">
          <span>${item.date || item.year}</span>
          <span class="badge" style="background:${colls[item.collection].color}">${item.collection}</span>
        </div>
      </div>`;
    card.onclick = () => openDialog(item);
    frag.appendChild(card);
  }
  grid.appendChild(frag);
}

function openDialog(item) {
  const rows = [
    ['Collection', state.catalog.collections[item.collection].name],
    ['Date', item.date], ['Town', item.town], ['Coverage', item.coverage],
    ['Author', item.author], ['Description', item.description],
    ['Georeferenced', item.georeferenced ? 'Yes' : 'No'],
    ['Local file', item.preview_file],
  ].filter(([, v]) => v);
  dialogBody.innerHTML = `
    <img src="${thumbUrl(item)}" alt="${item.frame}" onerror="this.style.display='none'">
    <h3>${item.frame}</h3>
    <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
    <p>
      ${item.item_url ? `<a href="${item.item_url}" target="_blank">Academic Commons page</a> · ` : ''}
      ${item.links.native ? `<a href="${item.links.native}" target="_blank">Native download</a>` : ''}
      ${item.georeferenced ? ` · <a href="/?frame=${encodeURIComponent(item.frame)}">Show on map</a>` : ''}
    </p>`;
  dialog.showModal();
}

function buildFilters() {
  const wrap = document.getElementById('collection-filters');
  for (const [cid, coll] of Object.entries(state.catalog.collections)) {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.innerHTML = `<span class="dot" style="background:${coll.color}"></span>${coll.name}`;
    chip.onclick = () => {
      chip.classList.toggle('on');
      chip.classList.contains('on') ? state.activeCollections.add(cid) : state.activeCollections.delete(cid);
      render();
    };
    wrap.appendChild(chip);
  }
}

document.getElementById('search').addEventListener('input', (e) => {
  state.query = e.target.value.trim().toLowerCase();
  if (state.addressHits) {  // editing the query drops the address filter
    state.addressHits = null;
    const status = document.getElementById('addr-status');
    if (status) status.textContent = '';
  }
  render();
});
document.getElementById('geo-only').addEventListener('change', (e) => {
  state.geoOnly = e.target.checked;
  render();
});

fetch('/api/catalog').then(r => r.json()).then((catalog) => {
  state.catalog = catalog;
  buildFilters();
  wireAddressSearch();
  render();
});
