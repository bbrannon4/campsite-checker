"use strict";

// --- config ---------------------------------------------------------------
const DATA_URL = "data/campgrounds.json";
const GEOCODE_URL = "https://api.zippopotam.us/us/";  // keyless, CORS-open
const REC_GOV = "https://www.recreation.gov/camping/campgrounds/";
const MAX_RESULTS = 200;  // cap the rendered list for sanity/performance

// --- element refs ----------------------------------------------------------
const els = {
  form: document.getElementById("search-form"),
  zip: document.getElementById("zip"),
  radius: document.getElementById("radius"),
  radiusOut: document.getElementById("radius-out"),
  status: document.getElementById("status"),
  results: document.getElementById("results"),
  head: document.getElementById("results-head"),
  list: document.getElementById("results-list"),
  dataDate: document.getElementById("data-date"),
};

let campgrounds = [];   // loaded once
const geoCache = new Map();  // zip -> {lat,lng,label}

// --- data load -------------------------------------------------------------
async function loadData() {
  try {
    const res = await fetch(DATA_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    campgrounds = data.campgrounds || [];
    if (data.generated) {
      const d = new Date(data.generated);
      els.dataDate.textContent =
        `${data.count.toLocaleString()} campgrounds, updated ${d.toLocaleDateString()}`;
    }
  } catch (err) {
    setStatus(`Could not load campground data (${err.message}).`, "error");
  }
}

// --- geo helpers -----------------------------------------------------------
function haversineMiles(lat1, lng1, lat2, lng2) {
  const R = 3958.8; // Earth radius in miles
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

async function geocodeZip(zip) {
  if (geoCache.has(zip)) return geoCache.get(zip);
  const res = await fetch(GEOCODE_URL + zip);
  if (!res.ok) throw new Error("ZIP not found");
  const data = await res.json();
  const place = (data.places || [])[0];
  if (!place) throw new Error("ZIP not found");
  const point = {
    lat: parseFloat(place.latitude),
    lng: parseFloat(place.longitude),
    label: `${place["place name"]}, ${place["state abbreviation"]}`,
  };
  geoCache.set(zip, point);
  return point;
}

// --- search ----------------------------------------------------------------
async function runSearch(evt) {
  evt.preventDefault();
  const zip = els.zip.value.trim();
  const radius = Number(els.radius.value);
  if (!/^\d{5}$/.test(zip)) {
    setStatus("Enter a valid 5-digit ZIP code.", "error");
    return;
  }
  if (!campgrounds.length) {
    setStatus("Campground data still loading — try again in a moment.", "error");
    return;
  }

  setStatus("Locating ZIP…", "");
  let origin;
  try {
    origin = await geocodeZip(zip);
  } catch (err) {
    setStatus(`Couldn't locate ZIP ${zip} (${err.message}).`, "error");
    return;
  }

  const nearby = [];
  for (const c of campgrounds) {
    const miles = haversineMiles(origin.lat, origin.lng, c.lat, c.lng);
    if (miles <= radius) nearby.push({ ...c, miles });
  }
  nearby.sort((a, b) => a.miles - b.miles);
  render(origin, radius, nearby);
}

function render(origin, radius, nearby) {
  els.head.textContent =
    `${nearby.length} campground${nearby.length === 1 ? "" : "s"} within ` +
    `${radius} mi (straight-line) of ${origin.label}`;
  els.list.innerHTML = "";

  if (!nearby.length) {
    setStatus("No campgrounds in range. Try a larger distance.", "");
    els.results.hidden = false;
    return;
  }
  setStatus("", "");

  const shown = nearby.slice(0, MAX_RESULTS);
  const frag = document.createDocumentFragment();
  for (const c of shown) {
    const li = document.createElement("li");
    li.className = "card";
    li.innerHTML = `
      <div class="card-main">
        <a class="card-name" href="${REC_GOV}${c.id}" target="_blank" rel="noopener">
          ${escapeHtml(c.name)}</a>
        ${c.parent ? `<div class="card-sub">${escapeHtml(c.parent)}</div>` : ""}
      </div>
      <div class="card-meta">
        <span class="miles" title="straight-line distance, not driving">${c.miles.toFixed(0)} mi</span>
        <span class="sites">${c.sites} sites</span>
        ${c.reservable ? `<span class="badge">reservable</span>` : ""}
      </div>`;
    frag.appendChild(li);
  }
  els.list.appendChild(frag);
  els.results.hidden = false;

  if (nearby.length > MAX_RESULTS) {
    setStatus(`Showing the nearest ${MAX_RESULTS}. Narrow the distance to see fewer.`, "");
  }
}

// --- utilities -------------------------------------------------------------
function setStatus(msg, kind) {
  els.status.textContent = msg;
  els.status.className = "status" + (kind ? " " + kind : "");
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

// --- wire up ---------------------------------------------------------------
els.radius.addEventListener("input", () => {
  els.radiusOut.textContent = els.radius.value;
});
els.form.addEventListener("submit", runSearch);
loadData();
