"use strict";

// --- config ---------------------------------------------------------------
const DATA_URL = "data/campgrounds.json";
const GEOCODE_URL = "https://api.zippopotam.us/us/";  // keyless, CORS-open
const REC_GOV = "https://www.recreation.gov/camping/campgrounds/";
const AVAIL_URL = "https://www.recreation.gov/api/camps/availability/campground/";
const MAX_RESULTS = 200;   // cap the rendered nearby list
const MAX_CHECK = 40;      // cap how many campgrounds we hit for availability
const FETCH_DELAY_MS = 200; // politeness pause between availability requests

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
  availForm: document.getElementById("avail-form"),
  weeks: document.getElementById("weeks"),
  nights: document.getElementById("nights"),
  weekends: document.getElementById("weekends"),
  check: document.getElementById("check"),
  availStatus: document.getElementById("avail-status"),
  availMatrix: document.getElementById("avail-matrix"),
};

let campgrounds = [];        // loaded once
let lastNearby = [];         // most recent search results (with .miles)
const geoCache = new Map();  // zip -> {lat,lng,label}
const monthCache = new Map();// `${id}-${y}-${m}` -> parsed month
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

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
        `${data.count.toLocaleString()} campgrounds, list updated ${d.toLocaleDateString()}`;
    }
  } catch (err) {
    setStatus(els.status, `Could not load campground data (${err.message}).`, "error");
  }
}

// --- geo helpers -----------------------------------------------------------
function haversineMiles(lat1, lng1, lat2, lng2) {
  const R = 3958.8;
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

// --- nearby search ---------------------------------------------------------
async function runSearch(evt) {
  evt.preventDefault();
  const zip = els.zip.value.trim();
  const radius = Number(els.radius.value);
  if (!/^\d{5}$/.test(zip)) {
    setStatus(els.status, "Enter a valid 5-digit ZIP code.", "error");
    return;
  }
  if (!campgrounds.length) {
    setStatus(els.status, "Campground data still loading — try again in a moment.", "error");
    return;
  }

  setStatus(els.status, "Locating ZIP…", "");
  let origin;
  try {
    origin = await geocodeZip(zip);
  } catch (err) {
    setStatus(els.status, `Couldn't locate ZIP ${zip} (${err.message}).`, "error");
    return;
  }

  const nearby = [];
  for (const c of campgrounds) {
    const miles = haversineMiles(origin.lat, origin.lng, c.lat, c.lng);
    if (miles <= radius) nearby.push({ ...c, miles });
  }
  nearby.sort((a, b) => a.miles - b.miles);
  lastNearby = nearby;
  renderNearby(origin, radius, nearby);
}

function renderNearby(origin, radius, nearby) {
  els.head.textContent =
    `${nearby.length} campground${nearby.length === 1 ? "" : "s"} within ` +
    `${radius} mi (straight-line) of ${origin.label}`;
  els.list.innerHTML = "";
  els.availMatrix.innerHTML = "";
  setStatus(els.availStatus, "", "");

  if (!nearby.length) {
    setStatus(els.status, "No campgrounds in range. Try a larger distance.", "");
    els.results.hidden = false;
    return;
  }
  setStatus(els.status, "", "");

  const frag = document.createDocumentFragment();
  for (const c of nearby.slice(0, MAX_RESULTS)) {
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
}

// --- availability ----------------------------------------------------------
function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function targetCheckins(weeks, weekendsOnly, stay) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const end = new Date(today);
  end.setDate(end.getDate() + weeks * 7);
  const out = [];
  for (const d = new Date(today); d < end; d.setDate(d.getDate() + 1)) {
    let ok = true;
    if (weekendsOnly) {
      for (let i = 0; i < stay; i++) {
        const n = new Date(d);
        n.setDate(n.getDate() + i);
        const w = n.getDay(); // Sun=0 … Fri=5, Sat=6
        if (w !== 5 && w !== 6) { ok = false; break; }
      }
    }
    if (ok) out.push(new Date(d));
  }
  return out;
}

async function fetchMonth(id, year, month) {
  const key = `${id}-${year}-${month}`;
  if (monthCache.has(key)) return monthCache.get(key);
  const start = `${year}-${String(month).padStart(2, "0")}-01T00:00:00.000Z`;
  const url = `${AVAIL_URL}${id}/month?start_date=${encodeURIComponent(start)}`;
  const res = await fetch(url); // simple GET: no custom headers, no preflight
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const sites = {};
  const campsites = (data && data.campsites) || {};
  for (const [sid, raw] of Object.entries(campsites)) {
    const overnight = String(raw.type_of_use || "Overnight").toLowerCase() !== "day";
    const avail = {};
    for (const [dstr, status] of Object.entries(raw.availabilities || {})) {
      avail[dstr.slice(0, 10)] = status === "Available"; // reservable + open only
    }
    sites[sid] = { overnight, avail };
  }
  monthCache.set(key, sites);
  return sites;
}

async function countsForCampground(id, checkins, stay) {
  // Fetch every month any stay touches (a stay can cross a month boundary).
  const need = new Set();
  for (const c of checkins) {
    for (let i = 0; i < stay; i++) {
      const d = new Date(c); d.setDate(d.getDate() + i);
      need.add(`${d.getFullYear()}-${d.getMonth() + 1}`);
    }
  }
  const months = {};
  for (const mk of need) {
    const [y, m] = mk.split("-").map(Number);
    months[mk] = await fetchMonth(id, y, m);
  }

  const counts = {};
  for (const c of checkins) {
    const days = [];
    for (let i = 0; i < stay; i++) {
      const d = new Date(c); d.setDate(d.getDate() + i); days.push(d);
    }
    const firstMonth = months[`${c.getFullYear()}-${c.getMonth() + 1}`] || {};
    let cnt = 0;
    for (const [sid, site] of Object.entries(firstMonth)) {
      if (!site.overnight) continue;
      let ok = true;
      for (const d of days) {
        const mo = months[`${d.getFullYear()}-${d.getMonth() + 1}`];
        if (!mo || !mo[sid] || !mo[sid].avail[fmtDate(d)]) { ok = false; break; }
      }
      if (ok) cnt++;
    }
    counts[fmtDate(c)] = cnt;
  }
  return counts;
}

async function runAvailability(evt) {
  evt.preventDefault();
  const weeks = Math.max(1, Math.min(12, Number(els.weeks.value) || 2));
  const stay = Math.max(1, Math.min(14, Number(els.nights.value) || 2));
  const weekendsOnly = els.weekends.checked;

  const checkins = targetCheckins(weeks, weekendsOnly, stay);
  if (!checkins.length) {
    setStatus(els.availStatus,
      "No check-in dates. A weekends-only stay longer than 2 nights can't fit Fri/Sat — reduce nights or uncheck weekends.",
      "error");
    els.availMatrix.innerHTML = "";
    return;
  }

  const targets = lastNearby.filter((c) => c.reservable).slice(0, MAX_CHECK);
  if (!targets.length) {
    setStatus(els.availStatus, "No reservable campgrounds in range to check.", "error");
    return;
  }

  els.check.disabled = true;
  els.availMatrix.innerHTML = "";
  const rows = [];
  for (let i = 0; i < targets.length; i++) {
    const c = targets[i];
    setStatus(els.availStatus, `Checking ${i + 1}/${targets.length}: ${c.name}…`, "");
    try {
      const counts = await countsForCampground(c.id, checkins, stay);
      rows.push({ c, counts, error: null });
    } catch (err) {
      rows.push({ c, counts: null, error: err.message });
    }
    if (i < targets.length - 1) await sleep(FETCH_DELAY_MS);
  }

  renderMatrix(checkins, stay, weekendsOnly, rows, targets.length, lastNearby.filter((c) => c.reservable).length);
  els.check.disabled = false;
}

function renderMatrix(checkins, stay, weekendsOnly, rows, checked, totalReservable) {
  const hasAny = rows.filter((r) => r.counts && Object.values(r.counts).some((n) => n > 0));
  const errored = rows.filter((r) => r.error);
  const withNone = rows.filter((r) => r.counts && !Object.values(r.counts).some((n) => n > 0)).length;

  const stayLabel = stay === 1 ? "1-night" : `${stay}-night`;
  const mode = weekendsOnly ? "weekend " : "";
  const first = checkins[0];
  const last = checkins[checkins.length - 1];
  const span = checkins.length === 1
    ? `${DOW[first.getDay()]} ${first.getMonth() + 1}/${first.getDate()}`
    : `${first.getMonth() + 1}/${first.getDate()} – ${last.getMonth() + 1}/${last.getDate()}`;

  const notes = [];
  if (totalReservable > checked) notes.push(`Checked the nearest ${checked} reservable of ${totalReservable} in range.`);
  if (errored.length) notes.push(`${errored.length} campground(s) couldn't be reached.`);

  let html = `<div class="matrix-caption">Reservable ${stayLabel} ${mode}stays &mdash; check-in ${span}. Cell = # of sites open for the whole stay.</div>`;

  // No openings anywhere: show a clear message, NOT a table full of blank rows.
  if (!hasAny.length) {
    html += `<div class="no-openings">No open sites for a ${stayLabel} ${mode}stay in this window — all ${checked} reservable campgrounds checked are booked.</div>`;
    if (notes.length) html += `<div class="hint">${notes.join(" ")}</div>`;
    els.availMatrix.innerHTML = html;
    setStatus(els.availStatus, "", "");
    return;
  }

  // Otherwise show only the campgrounds that actually have openings.
  html += `<table class="matrix"><thead><tr><th class="cg">Campground</th>`;
  for (const c of checkins) {
    html += `<th>${DOW[c.getDay()]}<br>${c.getMonth() + 1}/${c.getDate()}</th>`;
  }
  html += `</tr></thead><tbody>`;
  for (const r of hasAny) {
    html += `<tr><td class="cg"><a href="${REC_GOV}${r.c.id}" target="_blank" rel="noopener">${escapeHtml(r.c.name)}</a></td>`;
    for (const c of checkins) {
      const n = r.counts[fmtDate(c)] || 0;
      html += `<td class="${n ? "open" : ""}">${n ? n : ""}</td>`;
    }
    html += `</tr>`;
  }
  html += `</tbody></table>`;

  notes.unshift(`${hasAny.length} campground(s) with openings; ${withNone} fully booked in this window.`);
  html += `<div class="hint">${notes.join(" ")}</div>`;
  els.availMatrix.innerHTML = html;
  setStatus(els.availStatus, "", "");
}

// --- utilities -------------------------------------------------------------
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function setStatus(el, msg, kind) {
  el.textContent = msg;
  el.className = "status" + (kind ? " " + kind : "");
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

// --- wire up ---------------------------------------------------------------
els.radius.addEventListener("input", () => { els.radiusOut.textContent = els.radius.value; });
els.form.addEventListener("submit", runSearch);
els.availForm.addEventListener("submit", runAvailability);
loadData();
