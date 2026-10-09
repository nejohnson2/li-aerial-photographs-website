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
    if (!cid) return;
    // Imagery and its invisible click targets toggle together.
    if (e.target.checked) {
      state.tileLayers[cid].addTo(map);
      state.footprintLayers[cid].addTo(map);
    } else {
      map.removeLayer(state.tileLayers[cid]);
      map.removeLayer(state.footprintLayers[cid]);
    }
  });
}

opacitySlider.addEventListener('input', () => {
  for (const tl of Object.values(state.tileLayers)) tl.setOpacity(opacitySlider.value / 100);
});

/* search: match frame / town / date across georeferenced items, fly to result */
const searchBox = document.getElementById('search');
const resultsEl = document.getElementById('search-results');
searchBox.addEventListener('input', () => {
  const q = searchBox.value.trim().toLowerCase();
  resultsEl.innerHTML = '';
  if (q.length < 2) return;
  const hits = [...state.items.values()]
    .filter(it => it.georeferenced &&
      (`${it.frame} ${it.town} ${it.date} ${it.coverage}`.toLowerCase().includes(q)))
    .slice(0, 20);
  for (const it of hits) {
    const div = document.createElement('div');
    div.className = 'search-result';
    div.innerHTML = `<strong>${it.frame}</strong><span class="muted">${it.town || it.coverage || ''} · ${it.date || it.year}</span>`;
    div.onclick = () => flyToItem(it);
    resultsEl.appendChild(div);
  }
});

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
  for (const cid of Object.keys(state.footprintLayers)) {
    const on = cid === keep;
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
}

init();
