/* Map page: survey footprints + dynamic mosaic tile overlays. */

const map = L.map('map', { zoomControl: true, preferCanvas: true }).setView([40.85, -72.9], 10);

L.tileLayer('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', {
  maxZoom: 20,
  attribution: '&copy; Google',
}).addTo(map);

const state = {
  catalog: null,
  items: new Map(),          // "COLL/id" -> item record
  footprintLayers: {},       // collection -> L.geoJSON
  tileLayers: {},            // collection -> L.tileLayer
  visible: {},               // collection -> bool (footprints)
  imagery: {},               // collection -> bool (tiles)
};

const opacitySlider = document.getElementById('opacity');

function popupHtml(item) {
  const thumb = `/thumb/${item.collection}/${item.id}.jpg`;
  const rows = [
    ['Date', item.date], ['Town', item.town], ['Coverage', item.coverage],
    ['Author', item.author],
  ].filter(([, v]) => v);
  return `
    <div class="frame-popup">
      <img src="${thumb}" alt="${item.frame}" onerror="this.style.display='none'">
      <h3>${item.frame}</h3>
      <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
      ${item.item_url ? `<a href="${item.item_url}" target="_blank">View on Academic Commons</a><br>` : ''}
      ${item.links.native ? `<a href="${item.links.native}" target="_blank">Download native scan</a>` : ''}
    </div>`;
}

function buildLayers(footprints) {
  const colls = state.catalog.collections;
  for (const [cid, coll] of Object.entries(colls)) {
    const feats = footprints.features.filter(f => f.properties.collection === cid);
    if (!feats.length) continue;

    // Frames stay clickable for metadata popups, but never draw.
    state.footprintLayers[cid] = L.geoJSON({ type: 'FeatureCollection', features: feats }, {
      style: { stroke: false, fill: true, fillOpacity: 0 },
      onEachFeature: (feature, layer) => {
        const item = state.items.get(`${cid}/${feature.properties.id}`);
        layer.bindPopup(() => popupHtml(item), { maxWidth: 280 });
      },
    });

    state.tileLayers[cid] = L.tileLayer(`/tiles/${cid}/{z}/{x}/{y}.png`, {
      maxZoom: 20,
      maxNativeZoom: 18,     // beyond scan resolution: upscale client-side, don't re-request
      updateWhenIdle: true,  // wait until pan/zoom settles before fetching
      updateWhenZooming: false,
      keepBuffer: 4,         // keep off-screen tiles so panning back is instant
      opacity: opacitySlider.value / 100,
    });

    state.visible[cid] = true;
    state.tileLayers[cid].addTo(map);
    state.footprintLayers[cid].addTo(map);
  }
}

function renderLayerList() {
  const ul = document.getElementById('layer-list');
  const colls = state.catalog.collections;
  const stats = state.catalog.stats;
  ul.innerHTML = '';
  for (const cid of Object.keys(state.footprintLayers)) {
    const li = document.createElement('li');
    li.className = 'layer-item';
    li.innerHTML = `
      <span class="layer-swatch" style="background:${colls[cid].color}"></span>
      <span class="layer-name">${colls[cid].name}</span>
      <span class="layer-count">${stats[cid].georeferenced}</span>
      <label title="Mosaic imagery"><input type="checkbox" data-role="img" data-cid="${cid}" checked> imagery</label>`;
    ul.appendChild(li);
  }
  ul.addEventListener('change', (e) => {
    const cid = e.target.dataset.cid;
    if (cid) setCollectionVisible(cid, e.target.checked);
  });
}

// Imagery and its invisible click targets toggle together; the sidebar
// checkbox is kept in sync for programmatic calls.
function setCollectionVisible(cid, on) {
  if (!state.tileLayers[cid]) return;
  if (on) {
    state.tileLayers[cid].addTo(map);
    state.footprintLayers[cid].addTo(map);
  } else {
    map.removeLayer(state.tileLayers[cid]);
    map.removeLayer(state.footprintLayers[cid]);
  }
  const box = document.querySelector(`#layer-list input[data-cid="${cid}"]`);
  if (box) box.checked = on;
}

opacitySlider.addEventListener('input', () => {
  for (const tl of Object.values(state.tileLayers)) tl.setOpacity(opacitySlider.value / 100);
});

/* search: frame / town / date matches, plus address lookup via /api/geocode */
const searchBox = document.getElementById('search');
const resultsEl = document.getElementById('search-results');
searchBox.addEventListener('input', () => {
  const q = searchBox.value.trim();
  resultsEl.innerHTML = '';
  if (q.length < 2) return;
  const ql = q.toLowerCase();
  const hits = [...state.items.values()]
    .filter(it => it.georeferenced &&
      (`${it.frame} ${it.town} ${it.date} ${it.coverage}`.toLowerCase().includes(ql)))
    .slice(0, 12);
  for (const it of hits) {
    const div = document.createElement('div');
    div.className = 'search-result';
    div.innerHTML = `<strong>${it.frame}</strong><span class="muted">${it.town || it.coverage || ''} · ${it.date || it.year}</span>`;
    div.onclick = () => flyToItem(it);
    resultsEl.appendChild(div);
  }
  if (q.length >= 4) {
    const div = document.createElement('div');
    div.className = 'search-result addr-row';
    div.innerHTML = `📍 Search “<strong>${q}</strong>” as a street address`;
    div.onclick = () => searchAddress(q);
    resultsEl.appendChild(div);
  }
});
searchBox.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && searchBox.value.trim().length >= 4) searchAddress(searchBox.value.trim());
});

async function searchAddress(q) {
  resultsEl.innerHTML = '<div class="muted">Looking up address…</div>';
  const geo = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
  if (!geo.ok) {
    const err = await geo.json().catch(() => ({}));
    resultsEl.innerHTML = `<div class="muted">${err.error || 'Address lookup failed.'}</div>`;
    return;
  }
  const { lon, lat, matched_address } = await geo.json();

  if (state.addressMarker) map.removeLayer(state.addressMarker);
  state.addressMarker = L.marker([lat, lon]).addTo(map).bindPopup(matched_address);
  map.setView([lat, lon], 15);

  const loc = await fetch(`/api/locate?lon=${lon}&lat=${lat}`).then(r => r.json());
  const covered = loc.surveys.filter(s => s.covered);

  // "this location through time": enable every survey that covers the address
  for (const s of covered) setCollectionVisible(s.collection, true);

  resultsEl.innerHTML = `<div class="addr-matched">📍 ${matched_address}</div>`;
  if (!covered.length) {
    resultsEl.innerHTML += '<div class="muted">No survey imagery covers this address.</div>';
    return;
  }
  for (const s of covered) {
    const group = document.createElement('div');
    group.className = 'survey-group';
    group.innerHTML = `<div class="survey-group-title">
        <span class="dot" style="background:${state.catalog.collections[s.collection].color}"></span>
        ${s.year} — ${s.name}</div>`;
    for (const fr of s.frames) {
      const item = state.items.get(`${s.collection}/${fr.id}`);
      const row = document.createElement('div');
      row.className = 'search-result';
      row.innerHTML = `<strong>${fr.frame}</strong><span class="muted">frame center ${(fr.distance_m / 1000).toFixed(1)} km away</span>`;
      row.onclick = () => flyToItem(item);
      group.appendChild(row);
    }
    resultsEl.appendChild(group);
  }
}

function flyToItem(item) {
  const layerGroup = state.footprintLayers[item.collection];
  if (!layerGroup) return;
  layerGroup.eachLayer(l => {
    if (l.feature.properties.id === item.id) {
      map.fitBounds(l.getBounds(), { maxZoom: 14 });
      l.openPopup();
    }
  });
}

async function init() {
  const [catalog, footprints] = await Promise.all([
    fetch('/api/catalog').then(r => r.json()),
    fetch('/api/footprints').then(r => r.json()),
  ]);
  state.catalog = catalog;
  for (const item of catalog.items) state.items.set(`${item.collection}/${item.id}`, item);
  buildLayers(footprints);
  renderLayerList();

  const all = L.featureGroup(Object.values(state.footprintLayers));
  if (all.getLayers().length) map.fitBounds(all.getBounds().pad(0.05));

  // deep link from the gallery: /?frame=<frame name> — show only that
  // frame's collection so the linked survey isn't buried under the others
  const wanted = new URLSearchParams(location.search).get('frame');
  if (wanted) {
    const hit = [...state.items.values()].find(it => it.georeferenced && it.frame === wanted);
    if (hit) {
      showOnlyCollection(hit.collection);
      flyToItem(hit);
    }
  }
}

function showOnlyCollection(keep) {
  for (const cid of Object.keys(state.footprintLayers)) setCollectionVisible(cid, cid === keep);
}

init();
