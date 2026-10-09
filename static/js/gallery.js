/* Gallery page: browsable card grid of every item, including non-georeferenced ones. */

const state = { catalog: null, activeCollections: new Set(), query: '', geoOnly: false };

const grid = document.getElementById('grid');
const dialog = document.getElementById('item-dialog');
const dialogBody = document.getElementById('dialog-body');

function thumbUrl(item) { return `/thumb/${item.collection}/${item.id}.jpg`; }

function matches(item) {
  if (state.activeCollections.size && !state.activeCollections.has(item.collection)) return false;
  if (state.geoOnly && !item.georeferenced) return false;
  if (state.query) {
    const hay = `${item.frame} ${item.town} ${item.date} ${item.coverage}`.toLowerCase();
    if (!hay.includes(state.query)) return false;
  }
  return true;
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
  render();
});
document.getElementById('geo-only').addEventListener('change', (e) => {
  state.geoOnly = e.target.checked;
  render();
});

fetch('/api/catalog').then(r => r.json()).then((catalog) => {
  state.catalog = catalog;
  buildFilters();
  render();
});
