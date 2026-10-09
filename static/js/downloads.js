/* Downloads page: multi-select items or collections, export Academic Commons links. */

const state = { catalog: null, activeCollections: new Set(), query: '', selected: new Set() };

const tbody = document.querySelector('#dl-table tbody');

function matches(item) {
  if (state.activeCollections.size && !state.activeCollections.has(item.collection)) return false;
  if (state.query) {
    const hay = `${item.frame} ${item.town} ${item.date} ${item.coverage}`.toLowerCase();
    if (!hay.includes(state.query)) return false;
  }
  return true;
}

function key(item) { return `${item.collection}/${item.id}`; }

function visibleItems() { return state.catalog.items.filter(matches); }

function render() {
  tbody.innerHTML = '';
  const frag = document.createDocumentFragment();
  for (const item of visibleItems()) {
    const tr = document.createElement('tr');
    const k = key(item);
    tr.innerHTML = `
      <td><input type="checkbox" data-key="${k}" ${state.selected.has(k) ? 'checked' : ''}></td>
      <td>${item.frame}</td>
      <td>${item.collection}</td>
      <td>${item.date || item.year}</td>
      <td>${item.town || item.coverage || ''}</td>
      <td class="${item.georeferenced ? 'geo-yes' : 'geo-no'}">${item.georeferenced ? '✓' : '—'}</td>
      <td>
        ${item.item_url ? `<a href="${item.item_url}" target="_blank">page</a>` : ''}
        ${item.links.native ? ` · <a href="${item.links.native}" target="_blank">native</a>` : ''}
      </td>`;
    frag.appendChild(tr);
  }
  tbody.appendChild(frag);
  updateActions();
}

function updateActions() {
  const n = state.selected.size;
  document.getElementById('selection-count').textContent = `${n} selected`;
  document.getElementById('dl-manifest').disabled = n === 0;
  document.getElementById('dl-script').disabled = n === 0;
}

tbody.addEventListener('change', (e) => {
  const k = e.target.dataset.key;
  if (!k) return;
  e.target.checked ? state.selected.add(k) : state.selected.delete(k);
  updateActions();
});

function selectedItems() {
  return state.catalog.items.filter(it => state.selected.has(key(it)));
}

function saveFile(name, text) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

document.getElementById('select-visible').onclick = () => {
  for (const it of visibleItems()) state.selected.add(key(it));
  render();
};
document.getElementById('clear-selection').onclick = () => {
  state.selected.clear();
  render();
};
document.getElementById('dl-manifest').onclick = () => {
  const lines = selectedItems()
    .filter(it => it.links.native)
    .map(it => `${it.collection}/${it.frame}\t${it.links.native}`);
  saveFile('li-aerial-download-manifest.txt', lines.join('\n') + '\n');
};
document.getElementById('dl-script').onclick = () => {
  const items = selectedItems().filter(it => it.links.native);
  const lines = [
    '#!/bin/sh',
    '# Fetch selected LI aerial photographs from SBU Academic Commons at native resolution.',
    'set -e',
    '# -OJ uses the filename provided by Academic Commons for each item.',
    ...items.map(it =>
      `echo "${it.collection}/${it.frame}" && curl -L -OJ "${it.links.native}"`),
  ];
  saveFile('fetch-li-aerials.sh', lines.join('\n') + '\n');
};

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

fetch('/api/catalog').then(r => r.json()).then((catalog) => {
  state.catalog = catalog;
  buildFilters();
  render();
});
