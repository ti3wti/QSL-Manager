const API = "";
let allCards = [];
let map, markersLayer, mapTileLayer;
let appConfig = {};

const MAP_TILES = {
  voyager: {
    url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
  },
  positron: {
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
  },
  dark: {
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
  },
  osm: {
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenStreetMap contributors",
  },
};

const galleryView = document.getElementById("galleryView");
const mapView = document.getElementById("mapView");
const importStatus = document.getElementById("importStatus");
const countryFilter = document.getElementById("countryFilter");
const modeFilter = document.getElementById("modeFilter");
const callsignSearch = document.getElementById("callsignSearch");
const sortOrder = document.getElementById("sortOrder");

document.getElementById("importBtn").onclick = () => document.getElementById("fileInput").click();
document.getElementById("fileInput").onchange = handleImport;
document.getElementById("closeModal").onclick = closeModal;

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && document.getElementById("cardModal").style.display === "flex") {
    closeModal();
  }
});

document.getElementById("cardModal").addEventListener("click", (e) => {
  // Cierra solo si el click fue en el fondo oscuro, no dentro de la tarjeta
  if (e.target.id === "cardModal") closeModal();
});

countryFilter.onchange = applyFilters;
modeFilter.onchange = applyFilters;
callsignSearch.oninput = () => {
  document.getElementById("clearSearch").style.display = callsignSearch.value ? "block" : "none";
  applyFilters();
};
document.getElementById("clearSearch").onclick = () => {
  callsignSearch.value = "";
  document.getElementById("clearSearch").style.display = "none";
  applyFilters();
  callsignSearch.focus();
};
sortOrder.onchange = applyFilters;

function applyTheme(theme) {
  let resolved = theme;
  if (theme === "system") {
    resolved = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", resolved);
}

async function loadAppConfig() {
  const res = await fetch("/api/settings");
  appConfig = await res.json();
  applyTheme(appConfig.theme || "system");
  applyTranslations(appConfig.ui_language || "es");
  updateOwnerBanner();
  return appConfig;
}

async function setLanguage(lang) {
  applyTranslations(lang);
  appConfig.ui_language = lang;
  await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ui_language: lang }),
  });
  // Re-renderizar lo que ya está armado con texto embebido (galería, stats, países, modos)
  await loadCountries();
  loadModes();
  applyFilters();
  updateStatsLine();
}

function updateOwnerBanner() {
  const banner = document.getElementById("ownerCallsignBanner");
  const callsign = (appConfig.owner_callsign || "").trim();
  if (callsign) {
    banner.textContent = callsign;
    banner.style.display = "inline";
  } else {
    banner.style.display = "none";
  }
}

document.getElementById("galleryTab").onclick = () => switchView("gallery");
document.getElementById("mapTab").onclick = () => switchView("map");

function switchView(view) {
  document.getElementById("galleryTab").classList.toggle("active", view === "gallery");
  document.getElementById("mapTab").classList.toggle("active", view === "map");
  document.getElementById("slideshowTab").classList.toggle("active", view === "slideshow");
  galleryView.style.display = view === "gallery" ? "grid" : "none";
  mapView.style.display = view === "map" ? "block" : "none";
  document.getElementById("slideshowView").style.display = view === "slideshow" ? "block" : "none";
  if (view === "map") {
    initMapIfNeeded();
    renderMapMarkers(getFilteredCards());
    // El mapa se crea/oculta mientras el contenedor puede medir 0px todavía
    // (justo se acaba de volver visible) -- sin esto, Leaflet a veces
    // queda con mosaicos grises hasta que el usuario mueve la ventana.
    setTimeout(() => map.invalidateSize(), 0);
  } else if (view === "slideshow") {
    initSlideshow();
  } else {
    stopSlideshowTimer();
  }
}

document.getElementById("slideshowTab").onclick = () => switchView("slideshow");

async function handleImport(e) {
  const files = Array.from(e.target.files);
  await handleImportFiles(files);
  e.target.value = "";
}

async function handleImportFiles(files) {
  if (!files.length) return;
  const valid = files.filter(f => /\.(jpg|jpeg|png|bmp|tiff|webp|pdf)$/i.test(f.name));
  if (!valid.length) {
    importStatus.textContent = t("import.unsupported");
    return;
  }
  importStatus.textContent = t("import.processing", { count: valid.length });

  let errors = 0;
  for (let i = 0; i < valid.length; i++) {
    const formData = new FormData();
    formData.append("file", valid[i]);
    importStatus.textContent = t("import.processing_file", { i: i + 1, count: valid.length, name: valid[i].name });
    try {
      const res = await fetch("/api/import", { method: "POST", body: formData });
      const card = await res.json();
      if (ocrFailed(card)) errors++;
      allCards.push(card);
      await loadCountries();
      loadModes();
      applyFilters();
      updateStatsLine();
    } catch (err) {
      errors++;
      console.error("Error importando", valid[i].name, err);
    }
  }
  importStatus.textContent = errors
    ? t("import.done_errors", { count: valid.length, errors })
    : t("import.done", { count: valid.length });
}

const dropOverlay = document.getElementById("dropOverlay");
let dragCounter = 0;
document.addEventListener("dragenter", (e) => {
  e.preventDefault();
  dragCounter++;
  dropOverlay.style.display = "flex";
});
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("dragleave", (e) => {
  e.preventDefault();
  dragCounter--;
  if (dragCounter <= 0) { dragCounter = 0; dropOverlay.style.display = "none"; }
});
document.addEventListener("drop", async (e) => {
  e.preventDefault();
  dragCounter = 0;
  dropOverlay.style.display = "none";
  const files = Array.from(e.dataTransfer.files || []);
  await handleImportFiles(files);
});

async function loadCards() {
  const res = await fetch("/api/cards");
  allCards = await res.json();
  await loadCountries();
  loadModes();
  applyFilters();
  updateStatsLine();
}

function loadModes() {
  const current = modeFilter.value;
  const counts = {};
  allCards.forEach(c => {
    if (!c.mode) return;
    const mode = c.mode.trim().toUpperCase();
    counts[mode] = (counts[mode] || 0) + 1;
  });
  const modes = Object.keys(counts).sort();
  modeFilter.innerHTML = `<option value="">${t("header.all_modes")}</option>` +
    modes.map(m => `<option value="${m}">${m} (${counts[m]})</option>`).join("");
  modeFilter.value = current;
}

async function loadCountries() {
  const res = await fetch("/api/countries");
  const countries = await res.json();
  const current = countryFilter.value;
  countryFilter.innerHTML = `<option value="">${t("header.all_countries")}</option>` +
    countries.map(c => `<option value="${c.country}">${c.country} (${c.total})</option>`).join("");
  countryFilter.value = current;
}

function getFilteredCards() {
  const country = countryFilter.value;
  const mode = modeFilter.value;
  const search = callsignSearch.value.trim().toUpperCase();
  const filtered = allCards.filter(c => {
    if (country && c.country !== country) return false;
    if (mode && (c.mode || "").trim().toUpperCase() !== mode) return false;
    if (search && !(c.callsign || "").toUpperCase().includes(search)) return false;
    return true;
  });
  const order = sortOrder.value;
  if (order === "country_asc") {
    filtered.sort((a, b) => {
      if (!a.country && !b.country) return 0;
      if (!a.country) return 1;
      if (!b.country) return -1;
      return a.country.localeCompare(b.country, "es");
    });
  } else {
    filtered.sort((a, b) => {
      // Las fechas desconocidas (null) siempre al final, sin importar el orden elegido
      if (!a.qso_date && !b.qso_date) return 0;
      if (!a.qso_date) return 1;
      if (!b.qso_date) return -1;
      return order === "date_asc"
        ? a.qso_date.localeCompare(b.qso_date)
        : b.qso_date.localeCompare(a.qso_date);
    });
  }
  return filtered;
}

function applyFilters() {
  const filtered = getFilteredCards();
  renderGallery(filtered);
  if (mapView.style.display !== "none") renderMapMarkers(filtered);
}

function renderGallery(cards) {
  if (!cards.length) {
    galleryView.innerHTML = `<p style="color:#888">${t("gallery.no_cards")}</p>`;
    return;
  }

  const cardHtml = c => `
    <div class="qsl-card" onclick="openCard(${c.id})">
      ${renderThumb(c)}
      <div class="info">
        <div class="callsign">${c.callsign || "??"}</div>
        <div class="meta country-highlight">${c.country || t("gallery.unknown_country")}</div>
        <div class="meta">${c.qso_date || t("gallery.unknown_date")} · ${c.band || ""} ${c.mode || ""}</div>
        ${ocrFailed(c) ? `<span class="badge-error">${t("gallery.badge_error")}</span>` : (c.verified ? "" : `<span class="badge-unverified">${t("gallery.badge_review")}</span>`)}
      </div>
    </div>
  `;

  if (sortOrder.value === "country_asc") {
    // Agrupado: un encabezado de país cada vez que cambia, en vez de solo orden alfabético plano
    let html = "";
    let lastCountry = null;
    cards.forEach(c => {
      const country = c.country || t("gallery.unknown_country");
      if (country !== lastCountry) {
        html += `<div class="country-group-header">${country}</div>`;
        lastCountry = country;
      }
      html += cardHtml(c);
    });
    galleryView.innerHTML = html;
  } else {
    galleryView.innerHTML = cards.map(cardHtml).join("");
  }
}

function ocrFailed(card) {
  return (card.ocr_text || "").startsWith("[Error de reconocimiento");
}

function renderThumb(c) {
  const isPdf = c.stored_path.toLowerCase().endsWith(".pdf");
  const src = isPdf ? `/api/cards/${c.id}/preview` : `/api/cards/${c.id}/file`;
  return `<img src="${src}" loading="lazy">`;
}

function initMapIfNeeded() {
  if (map) return;
  map = L.map("map").setView([10, -70], 3);
  setMapTileLayer(appConfig.map_style || "voyager");
  markersLayer = L.layerGroup().addTo(map);
  document.getElementById("mapStyleQuick").value = appConfig.map_style || "voyager";
}

document.getElementById("mapStyleQuick").onchange = async (e) => {
  setMapTileLayer(e.target.value);
  appConfig.map_style = e.target.value;
  await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ map_style: e.target.value }),
  });
};

function setMapTileLayer(styleKey) {
  const style = MAP_TILES[styleKey] || MAP_TILES.voyager;
  if (mapTileLayer) map.removeLayer(mapTileLayer);
  mapTileLayer = L.tileLayer(style.url, { attribution: style.attribution, maxZoom: 19 }).addTo(map);
}

// --- Presentación (slideshow) ------------------------------------------
let slideshowCards = [];
let slideIndex = 0;
let slideTimer = null;
let slidePlaying = false;

function initSlideshow() {
  slideshowCards = getFilteredCards();
  slideIndex = 0;
  slidePlaying = false;
  document.getElementById("slidePlayBtn").textContent = "▶";
  renderSlide();
}

function renderSlide() {
  const img = document.getElementById("slideImg");
  const caption = document.getElementById("slideCaption");
  const counter = document.getElementById("slideCounter");

  if (!slideshowCards.length) {
    img.style.display = "none";
    caption.textContent = t("slideshow.empty");
    counter.textContent = "";
    return;
  }
  const card = slideshowCards[slideIndex];
  img.style.display = "block";
  img.src = `/api/cards/${card.id}/preview`;
  caption.innerHTML = `
    <div class="callsign">${card.callsign || "??"}</div>
    <div class="meta"><span class="country-highlight">${card.country || t("gallery.unknown_country")}</span> · ${card.qso_date || t("gallery.unknown_date")} · ${card.band || ""} ${card.mode || ""}</div>
  `;
  counter.textContent = t("slideshow.counter", { current: slideIndex + 1, total: slideshowCards.length });
}

function nextSlide() {
  if (!slideshowCards.length) return;
  slideIndex = (slideIndex + 1) % slideshowCards.length;
  renderSlide();
}

function prevSlide() {
  if (!slideshowCards.length) return;
  slideIndex = (slideIndex - 1 + slideshowCards.length) % slideshowCards.length;
  renderSlide();
}

function stopSlideshowTimer() {
  if (slideTimer) {
    clearInterval(slideTimer);
    slideTimer = null;
  }
  slidePlaying = false;
  const btn = document.getElementById("slidePlayBtn");
  if (btn) {
    btn.textContent = "▶";
    btn.title = t("slideshow.play");
  }
}

function startSlideshowTimer() {
  stopSlideshowTimer();
  const seconds = Math.max(1, parseInt(document.getElementById("slideInterval").value, 10) || 4);
  slideTimer = setInterval(nextSlide, seconds * 1000);
  slidePlaying = true;
  const btn = document.getElementById("slidePlayBtn");
  btn.textContent = "⏸";
  btn.title = t("slideshow.pause");
}

function toggleSlideshowPlay() {
  if (slidePlaying) {
    stopSlideshowTimer();
  } else {
    startSlideshowTimer();
  }
}

document.getElementById("slidePrevBtn").onclick = () => { prevSlide(); if (slidePlaying) startSlideshowTimer(); };
document.getElementById("slideNextBtn").onclick = () => { nextSlide(); if (slidePlaying) startSlideshowTimer(); };
document.getElementById("slidePlayBtn").onclick = toggleSlideshowPlay;
document.getElementById("slideInterval").onchange = () => { if (slidePlaying) startSlideshowTimer(); };

document.addEventListener("keydown", (e) => {
  if (document.getElementById("slideshowView").style.display !== "block") return;
  if (e.key === "ArrowRight") { nextSlide(); if (slidePlaying) startSlideshowTimer(); }
  if (e.key === "ArrowLeft") { prevSlide(); if (slidePlaying) startSlideshowTimer(); }
  if (e.key === " ") { e.preventDefault(); toggleSlideshowPlay(); }
});

function renderMapMarkers(cards) {
  if (!markersLayer) return;
  markersLayer.clearLayers();
  const withCoords = cards.filter(c => c.lat && c.lon);
  withCoords.forEach(c => {
    const marker = L.marker([c.lat, c.lon]);
    marker.bindPopup(`<b>${c.callsign || "??"}</b><br>${c.country || ""}<br>${c.qso_date || ""}`);
    marker.addTo(markersLayer);
  });
  if (withCoords.length) {
    const bounds = L.latLngBounds(withCoords.map(c => [c.lat, c.lon]));
    map.fitBounds(bounds, { padding: [30, 30] });
  }
}

function openCard(id) {
  const card = allCards.find(c => c.id === id);
  if (!card) return;
  const isPdf = card.stored_path.toLowerCase().endsWith(".pdf");
  const modal = document.getElementById("cardModal");
  const body = modal.querySelector(".modal-body");

  const preview = `<img src="/api/cards/${card.id}/preview" class="preview-img">` +
    (isPdf ? `<div class="pdf-original-link"><a href="/api/cards/${card.id}/file" target="_blank">${t("card.view_pdf")}</a></div>` : "");

  body.innerHTML = `
    ${preview}
    ${renderEngineBadge(card)}
    <div class="field-row"><label>${t("card.callsign_label")}</label><input id="f_callsign" value="${card.callsign || ""}"></div>
    <div class="field-row"><label>${t("card.country_label")}</label><input id="f_country" value="${card.country || ""}"></div>
    <div class="field-row"><label>${t("card.date_label")}</label><input id="f_qso_date" value="${card.qso_date || ""}" placeholder="YYYY-MM-DD" maxlength="10"></div>
    <div class="field-row"><label>${t("card.band_label")}</label><input id="f_band" value="${card.band || ""}"></div>
    <div class="field-row"><label>${t("card.mode_label")}</label><input id="f_mode" value="${card.mode || ""}"></div>
    <div class="field-row"><label>${t("card.rst_label")}</label><input id="f_rst" value="${card.rst || ""}"></div>
    <div class="field-row"><label>${t("card.locator_label")}</label><input id="f_locator" value="${card.locator || ""}"></div>
    <div id="ocrStatus" class="ocr-status"></div>
    <div class="modal-actions">
      <button onclick="saveCard(${card.id})">${t("card.save_btn")}</button>
      <button class="btn-secondary" onclick="reprocessOcr(${card.id}, 'tesseract')">${t("card.local_btn")}</button>
      <button class="btn-secondary" onclick="reprocessOcr(${card.id}, 'ai')">${t("card.ai_btn")}</button>
      <button class="btn-secondary" onclick="closeModal()">${t("card.close_btn")}</button>
      <button class="btn-danger" onclick="removeCard(${card.id})">${t("card.delete_btn")}</button>
    </div>
  `;
  modal.style.display = "flex";
  updateEngineBadge(card.recognized_by);

  setupCallsignAutoCountry();
  setupDateMask();
  setupEnterToSave(card.id);
  document.getElementById("f_callsign").focus();

  const statusEl = document.getElementById("ocrStatus");
  if (ocrFailed(card)) {
    statusEl.textContent = card.ocr_text.replace("[Error de reconocimiento: ", "Falló el reconocimiento al importar: ").replace(/\]$/, "");
    statusEl.classList.add("ocr-error");
  }
}

function renderEngineBadge(card) {
  return `<div class="badge-engine" id="engineBadge" style="display:none;"></div>`;
}

function updateEngineBadge(recognizedBy) {
  const el = document.getElementById("engineBadge");
  if (!el) return;
  if (!recognizedBy) {
    el.style.display = "none";
    return;
  }
  const keys = { ai: "card.engine_ai", tesseract: "card.engine_tesseract", eqsl: "card.engine_eqsl" };
  el.textContent = keys[recognizedBy] ? t(keys[recognizedBy]) : recognizedBy;
  el.style.display = "inline-block";
}

function setupCallsignAutoCountry() {
  const callsignInput = document.getElementById("f_callsign");
  const countryInput = document.getElementById("f_country");
  let debounceTimer;
  callsignInput.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    const value = callsignInput.value.trim();
    if (!value) return;
    debounceTimer = setTimeout(async () => {
      const res = await fetch(`/api/resolve?callsign=${encodeURIComponent(value)}`);
      const data = await res.json();
      if (data.country) countryInput.value = data.country;
    }, 400);
  });
}

function setupDateMask() {
  const dateInput = document.getElementById("f_qso_date");
  dateInput.addEventListener("input", () => {
    let digits = dateInput.value.replace(/\D/g, "").slice(0, 8);
    let formatted = digits;
    if (digits.length > 4) formatted = digits.slice(0, 4) + "-" + digits.slice(4);
    if (digits.length > 6) formatted = digits.slice(0, 4) + "-" + digits.slice(4, 6) + "-" + digits.slice(6);
    dateInput.value = formatted;
  });
}

function setupEnterToSave(cardId) {
  document.querySelectorAll(".modal-body input").forEach(input => {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        saveCard(cardId);
      }
    });
  });
}

async function reprocessOcr(id, engine) {
  const statusEl = document.getElementById("ocrStatus");
  statusEl.textContent = t("common.processing");
  statusEl.classList.remove("ocr-error");
  try {
    const res = await fetch(`/api/cards/${id}/reprocess-ocr?engine=${engine}`, { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      statusEl.textContent = err.detail || `Error del servidor (HTTP ${res.status}).`;
      statusEl.classList.add("ocr-error");
      return;
    }
    const fields = await res.json();
    if (fields.callsign) document.getElementById("f_callsign").value = fields.callsign;
    if (fields.country) document.getElementById("f_country").value = fields.country;
    if (fields.qso_date) document.getElementById("f_qso_date").value = fields.qso_date;
    if (fields.band) document.getElementById("f_band").value = fields.band;
    if (fields.mode) document.getElementById("f_mode").value = fields.mode;
    if (fields.rst) document.getElementById("f_rst").value = fields.rst;
    if (fields.locator) document.getElementById("f_locator").value = fields.locator;
    updateEngineBadge(fields.engine_used);
    // Refrescar la vista previa por si se regeneró (cache-busting)
    const img = document.querySelector(".modal-body .preview-img");
    if (img) img.src = `/api/cards/${id}/preview?t=${Date.now()}`;
    const motor = fields.engine_used === "ai" ? "IA (Gemini)" : "Tesseract";
    if (!fields.callsign && !fields.qso_date && !fields.band) {
      statusEl.textContent = `${motor} no detectó texto reconocible en esta tarjeta. Completa los campos a mano.`;
    } else {
      statusEl.textContent = `Listo (motor: ${motor}). Revisa los campos y guarda si están correctos.`;
    }
  } catch (err) {
    statusEl.textContent = "No se pudo conectar con el servidor para reprocesar.";
    statusEl.classList.add("ocr-error");
    console.error(err);
  }
}

async function saveCard(id) {
  const payload = {
    callsign: document.getElementById("f_callsign").value.toUpperCase() || null,
    country: document.getElementById("f_country").value || null,
    qso_date: document.getElementById("f_qso_date").value || null,
    band: document.getElementById("f_band").value || null,
    mode: document.getElementById("f_mode").value || null,
    rst: document.getElementById("f_rst").value || null,
    locator: document.getElementById("f_locator").value.toUpperCase() || null,
    verified: 1,
    ocr_text: "", // el usuario ya revisó/confirmó -- limpia cualquier "Error de OCR" viejo
  };
  await fetch(`/api/cards/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  closeModal();
  await loadCards();
}

async function removeCard(id) {
  if (!confirm(t("card.delete_confirm2"))) return;
  await fetch(`/api/cards/${id}`, { method: "DELETE" });
  closeModal();
  await loadCards();
}

function closeModal() {
  document.getElementById("cardModal").style.display = "none";
}

document.getElementById("settingsBtn").onclick = openSettings;
document.getElementById("closeSettings").onclick = closeSettingsModal;
document.getElementById("settingsModal").addEventListener("click", (e) => {
  if (e.target.id === "settingsModal") closeSettingsModal();
});

async function detectModels() {
  const statusEl = document.getElementById("modelDetectStatus");
  await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ gemini_api_key: document.getElementById("s_gemini_key").value.trim() }),
  });
  statusEl.textContent = "Consultando modelos disponibles...";
  try {
    const res = await fetch("/api/settings/gemini-models");
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      statusEl.textContent = err.detail || "No se pudo consultar.";
      return;
    }
    const { models } = await res.json();
    const select = document.getElementById("s_gemini_model");
    const current = select.value;
    select.innerHTML = models.map(m => `<option value="${m}">${m}</option>`).join("");
    // Mantener la selección previa si sigue existiendo en la lista, si no, usar la primera (ya viene priorizada)
    select.value = models.includes(current) ? current : models[0];
    statusEl.textContent = `${models.length} modelo(s) encontrado(s). Elegido "${select.value}" (puedes cambiarlo del desplegable).`;
  } catch (err) {
    statusEl.textContent = t("common.conn_error");
    console.error(err);
  }
}

async function openSettings() {
  const res = await fetch("/api/settings");
  const cfg = await res.json();
  document.getElementById("s_owner_callsign").value = cfg.owner_callsign || "";
  document.getElementById("s_telemetry_opt_in").checked = !!cfg.telemetry_opt_in;
  document.getElementById("s_gemini_key").value = cfg.gemini_api_key || "";
  const select = document.getElementById("s_gemini_model");
  const savedModel = cfg.gemini_model || "gemini-flash-lite-latest";
  if (![...select.options].some(o => o.value === savedModel)) {
    select.insertAdjacentHTML("afterbegin", `<option value="${savedModel}">${savedModel}</option>`);
  }
  select.value = savedModel;
  document.getElementById("s_engine").value = cfg.ocr_engine || "auto";
  document.getElementById("s_tesseract_path").value = cfg.tesseract_path || "";
  document.getElementById("s_theme").value = cfg.theme || "system";
  document.getElementById("s_map_style").value = cfg.map_style || "voyager";
  document.getElementById("modelDetectStatus").textContent = "";
  document.getElementById("settingsStatus").textContent = "";
  document.getElementById("settingsModal").style.display = "flex";
}

function closeSettingsModal() {
  document.getElementById("settingsModal").style.display = "none";
}

async function saveSettings() {
  const payload = {
    owner_callsign: document.getElementById("s_owner_callsign").value.trim().toUpperCase(),
    telemetry_opt_in: document.getElementById("s_telemetry_opt_in").checked,
    gemini_api_key: document.getElementById("s_gemini_key").value.trim(),
    gemini_model: document.getElementById("s_gemini_model").value.trim() || "gemini-flash-lite-latest",
    ocr_engine: document.getElementById("s_engine").value,
    tesseract_path: document.getElementById("s_tesseract_path").value.trim(),
    theme: document.getElementById("s_theme").value,
    map_style: document.getElementById("s_map_style").value,
  };
  const res = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  appConfig = await res.json();
  applyTheme(appConfig.theme);
  updateOwnerBanner();
  if (map) setMapTileLayer(appConfig.map_style);
  document.getElementById("mapStyleQuick").value = appConfig.map_style;
  if (payload.owner_callsign) fetch("/api/telemetry/ping", { method: "POST" }).catch(() => {});
  document.getElementById("settingsStatus").textContent = "Guardado.";
}

document.getElementById("importEqslBtn").onclick = openEqslModal;
document.getElementById("closeEqsl").onclick = closeEqslModal;
document.getElementById("eqslModal").addEventListener("click", (e) => {
  if (e.target.id === "eqslModal") closeEqslModal();
});

let eqslPollTimer = null;

async function openEqslModal() {
  await loadAppConfig(); // refrescar por si se guardó desde otra sesión
  document.getElementById("eqsl_user").value = appConfig.eqsl_username || appConfig.owner_callsign || "";
  document.getElementById("eqsl_pass").value = appConfig.eqsl_password || "";
  document.getElementById("eqslProgress").textContent = "";
  document.getElementById("eqslModal").style.display = "flex";
  pollEqslStatus(); // por si ya había una descarga corriendo en segundo plano
}

function closeEqslModal() {
  document.getElementById("eqslModal").style.display = "none";
}

async function startEqslImport() {
  const username = document.getElementById("eqsl_user").value.trim().toUpperCase();
  const password = document.getElementById("eqsl_pass").value;
  if (!username || !password) {
    document.getElementById("eqslProgress").textContent = t("eqsl.required");
    return;
  }
  document.getElementById("eqslProgress").textContent = t("eqsl.connecting");
  document.getElementById("eqslStartBtn").disabled = true;
  try {
    const res = await fetch("/api/eqsl/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      document.getElementById("eqslProgress").textContent = err.detail || "No se pudo iniciar.";
      document.getElementById("eqslStartBtn").disabled = false;
      return;
    }
    setEqslFormMode(true);
    pollEqslStatus();
  } catch (err) {
    document.getElementById("eqslProgress").textContent = t("common.conn_error");
    document.getElementById("eqslStartBtn").disabled = false;
  }
}

async function saveAndCloseEqsl() {
  const payload = {
    eqsl_username: document.getElementById("eqsl_user").value.trim().toUpperCase(),
    eqsl_password: document.getElementById("eqsl_pass").value,
  };
  await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  appConfig.eqsl_username = payload.eqsl_username;
  appConfig.eqsl_password = payload.eqsl_password;
  closeEqslModal();
}

async function stopEqslImport() {
  document.getElementById("eqslStopBtn").disabled = true;
  document.getElementById("eqslProgress").textContent = t("eqsl.stopping");
  try {
    await fetch("/api/eqsl/cancel", { method: "POST" });
  } catch (err) {
    console.error(err);
  }
  pollEqslStatus();
}

function setEqslFormMode(running) {
  document.getElementById("eqsl_user").disabled = running;
  document.getElementById("eqsl_pass").disabled = running;
  document.getElementById("eqslStartBtn").style.display = running ? "none" : "inline-block";
  document.getElementById("eqslStartBtn").disabled = false; // se quedaba deshabilitado tras la primera descarga
  document.getElementById("eqslStopBtn").style.display = running ? "inline-block" : "none";
  document.getElementById("eqslStopBtn").disabled = false;
}

async function pollEqslStatus() {
  if (eqslPollTimer) clearTimeout(eqslPollTimer);
  try {
    const res = await fetch("/api/eqsl/status");
    const status = await res.json();
    const pill = document.getElementById("eqslStatusPill");
    const modalOpen = document.getElementById("eqslModal").style.display === "flex";
    const el = document.getElementById("eqslProgress");

    if (status.running) {
      pill.style.display = "inline-block";
      pill.textContent = status.total
        ? `📥 eQSL: ${status.done}/${status.total}${status.errors ? ` (${status.errors} err)` : ""}`
        : "📥 eQSL: conectando...";
      if (modalOpen) {
        setEqslFormMode(true);
        el.textContent = status.total
          ? `${status.done}/${status.total} tarjetas -- actual: ${status.current || "..."}` +
            (status.errors ? ` (${status.errors} con error)` : "") +
            (status.last_error ? `\nÚltimo error: ${status.last_error}` : "")
          : (status.current || t("eqsl.connecting"));
      }
      eqslPollTimer = setTimeout(pollEqslStatus, 2000);
      // Refrescar galería/mapa con lo que ya se haya bajado, sin esperar a que termine todo
      await loadCards();
    } else {
      pill.style.display = "none";
      if (modalOpen) {
        setEqslFormMode(false);
        el.textContent = status.message || "";
        const startBtn = document.getElementById("eqslStartBtn");
        startBtn.textContent = (status.message || "").startsWith("Detenido")
          ? t("eqsl.resume_btn")
          : t("eqsl.start_btn");
      }
      if (status.total) await loadCards();
    }
  } catch (err) {
    console.error("Error consultando estado de eQSL", err);
    eqslPollTimer = setTimeout(pollEqslStatus, 3000);
  }
}

document.getElementById("eqslStatusPill").onclick = openEqslModal;

function reopenOnboarding() {
  closeSettingsModal();
  document.getElementById("onboard_key").value = "";
  document.getElementById("onboardStatus").textContent = "";
  document.getElementById("onboardingModal").style.display = "flex";
}

async function finishOnboarding(activateAI) {
  const statusEl = document.getElementById("onboardStatus");
  const ownerCallsign = document.getElementById("onboard_callsign").value.trim().toUpperCase();
  const base = { owner_callsign: ownerCallsign, onboarding_done: true };
  if (activateAI) {
    const key = document.getElementById("onboard_key").value.trim();
    if (!key) {
      statusEl.textContent = t("onboarding.need_key");
      return;
    }
    statusEl.textContent = t("onboarding.saving");
    await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...base, gemini_api_key: key, ocr_engine: "auto" }),
    });
  } else {
    await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(base),
    });
  }
  document.getElementById("onboardingModal").style.display = "none";
  await loadAppConfig();
  if (ownerCallsign) fetch("/api/telemetry/ping", { method: "POST" }).catch(() => {});
}

document.getElementById("bulkReprocessBtn").onclick = startBulkReprocess;
let bulkPollTimer = null;

async function startBulkReprocess() {
  try {
    const res = await fetch("/api/cards/reprocess-all", { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      importStatus.textContent = err.detail || "No se pudo iniciar la revisión masiva.";
      return;
    }
    pollBulkStatus();
  } catch (err) {
    importStatus.textContent = t("common.conn_error");
    console.error(err);
  }
}

async function pollBulkStatus() {
  if (bulkPollTimer) clearTimeout(bulkPollTimer);
  try {
    const res = await fetch("/api/cards/reprocess-all/status");
    const status = await res.json();
    const pill = document.getElementById("bulkStatusPill");

    if (status.running) {
      pill.style.display = "inline-block";
      pill.textContent = t("bulk.reviewing", { done: status.done, total: status.total }) + (status.errors ? ` (${status.errors} err)` : "");
      bulkPollTimer = setTimeout(pollBulkStatus, 1500);
      await loadCards();
    } else {
      pill.style.display = "none";
      if (status.message) importStatus.textContent = status.message;
      if (status.total) await loadCards();
    }
  } catch (err) {
    console.error("Error consultando estado de revisión masiva", err);
    bulkPollTimer = setTimeout(pollBulkStatus, 3000);
  }
}

document.getElementById("aboutBtn").onclick = () => {
  document.getElementById("aboutModal").style.display = "flex";
  showCurrentVersion();
};
document.getElementById("closeAbout").onclick = closeAboutModal;
document.getElementById("aboutModal").addEventListener("click", (e) => {
  if (e.target.id === "aboutModal") closeAboutModal();
});
function closeAboutModal() {
  document.getElementById("aboutModal").style.display = "none";
}

let currentAppVersion = "";

async function showCurrentVersion() {
  if (!currentAppVersion) {
    try {
      const res = await fetch("/api/version");
      currentAppVersion = (await res.json()).version;
    } catch (e) { /* ignorar */ }
  }
  document.getElementById("versionLine").textContent = currentAppVersion ? `v. ${currentAppVersion}` : "";
  document.getElementById("updateStatus").textContent = "";
}

async function checkForUpdates(manual) {
  const statusEl = document.getElementById("updateStatus");
  if (manual) statusEl.textContent = t("common.processing");
  try {
    const res = await fetch("/api/check-update");
    const data = await res.json();
    if (data.update_available) {
      document.getElementById("updatePill").style.display = "inline-block";
      document.getElementById("updatePill").href = data.url;
      document.getElementById("updatePill").textContent = `⬆ ${data.latest_version}`;
      if (manual) statusEl.innerHTML = `<a href="${data.url}" target="_blank">${t("about.update_found", { version: data.latest_version })}</a>`;
    } else if (manual) {
      statusEl.textContent = data.note || t("about.up_to_date");
    }
  } catch (e) {
    if (manual) statusEl.textContent = t("common.conn_error");
  }
}

function updateStatsLine() {
  const countries = new Set(allCards.map(c => c.country).filter(Boolean));
  document.getElementById("statsLine").textContent =
    t("gallery.stats", { count: allCards.length, countries: countries.size });
}

(async function init() {
  await loadAppConfig();
  await loadCards();
  pollEqslStatus();
  pollBulkStatus();
  fetch("/api/telemetry/ping", { method: "POST" }).catch(() => {}); // opcional, en silencio si falla
  checkForUpdates(false); // silencioso: solo se nota si SÍ hay algo nuevo
  if (!appConfig.onboarding_done) {
    document.getElementById("onboardingModal").style.display = "flex";
  }
})();
