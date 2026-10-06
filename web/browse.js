const $ = (id) => document.getElementById(id);

// Theme (shared with index page).
const root = document.documentElement;
const themeBtn = $("theme");
function setTheme(t) {
  root.setAttribute("data-theme", t);
  themeBtn.textContent = t === "dark" ? "☀️" : "🌙";
  try { localStorage.setItem("mm-theme", t); } catch (_) {}
}
setTheme((() => { try { return localStorage.getItem("mm-theme") || "dark"; } catch (_) { return "dark"; } })());
themeBtn.onclick = () => setTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");

let offset = 0;

async function init() {
  const cols = await (await fetch("/api/collections")).json();
  const sel = $("col");
  sel.innerHTML = "";
  (cols.collections || []).forEach((c) => {
    const o = document.createElement("option");
    o.value = c.name;
    o.textContent = `${c.name} (${c.count.toLocaleString()})`;
    sel.appendChild(o);
  });
  sel.onchange = () => { offset = 0; loadStats(); browse(); };
  await loadStats();
  await browse();
}

async function loadStats() {
  const s = await (await fetch(`/api/chroma-stats?collection=${encodeURIComponent($("col").value)}`)).json();
  $("bstat-count").textContent = s.count.toLocaleString();
  const cards = $("stat-cards");
  cards.innerHTML = "";
  const total = s.count || 1;
  const nParks = Object.keys(s.branches || {}).length;
  const pos = (parseInt((s.ratings || {})["5"] || 0, 10) + parseInt((s.ratings || {})["4"] || 0, 10));
  [
    ["Total records", s.count.toLocaleString()],
    ["Parks", String(nParks)],
    ["4–5 star share", `${Math.round((pos / total) * 100)}%`],
  ].forEach(([label, val]) => {
    const d = document.createElement("div");
    d.className = "stat-card";
    d.innerHTML = `<div class="stat-val"></div><div class="stat-label"></div>`;
    d.querySelector(".stat-val").textContent = val;
    d.querySelector(".stat-label").textContent = label;
    cards.appendChild(d);
  });
  bar($("d-branch"), s.branches, total);
  bar($("d-rating"), s.ratings, total, (k) => `${k}★`);
  bar($("d-loc"), s.top_locations, total);
  $("stats").classList.remove("hidden");
}

function bar(el, obj, total, fmt) {
  el.innerHTML = "";
  Object.entries(obj || {}).forEach(([k, v]) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    const pct = Math.round((v / (total || 1)) * 100);
    row.innerHTML = `<span class="bar-label"></span><div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div><span class="bar-val"></span>`;
    row.querySelector(".bar-label").textContent = fmt ? fmt(k) : k.replace("Disneyland_", "");
    row.querySelector(".bar-val").textContent = `${v.toLocaleString()} · ${pct}%`;
    el.appendChild(row);
  });
}

function params() {
  return new URLSearchParams({
    collection: $("col").value,
    limit: $("limit").value,
    offset: String(offset),
    ...( $("branch").value ? { branch: $("branch").value } : {}),
    ...( $("rating").value ? { rating: $("rating").value } : {}),
    ...( $("q").value.trim() ? { q: $("q").value.trim() } : {}),
  });
}

async function browse() {
  $("err").classList.add("hidden");
  $("loading").classList.remove("hidden");
  try {
    const d = await (await fetch(`/api/browse?${params()}`)).json();
    const tb = $("rows");
    tb.innerHTML = "";
    d.items.forEach((h) => {
      const m = h.metadata || {};
      const tr = document.createElement("tr");
      tr.className = "brow";
      tr.innerHTML =
        `<td class="exp"><button title="Expand record + embedding">＋</button></td>` +
        `<td class="mono"></td>` +
        `<td></td>` +
        `<td class="stars"></td>` +
        `<td></td><td class="nowrap"></td>` +
        `<td class="rev"></td>`;
      tr.children[1].textContent = h.id;
      tr.children[2].textContent = (m.branch || "").replace("Disneyland_", "");
      tr.children[3].textContent = "★".repeat(m.rating || 0) + "☆".repeat(5 - (m.rating || 0));
      tr.children[4].textContent = m.reviewer_location || "?";
      tr.children[5].textContent = m.year_month || "";
      tr.children[6].textContent = (h.snippet || "").slice(0, 220) + ((h.snippet || "").length > 220 ? "…" : "");
      const det = document.createElement("tr");
      det.className = "detail hidden";
      det.innerHTML = `<td colspan="7"><div class="detail-box"><div class="full"></div><div class="emb"><div class="emb-head">loading vector…</div><div class="emb-bars"></div><div class="emb-vals"></div></div></div></td>`;
      det.querySelector(".full").textContent = h.snippet;
      tr.querySelector(".exp button").onclick = () => toggleDetail(det, h.id);
      tb.append(tr, det);
    });
    $("rcount").textContent = `· showing ${d.offset + 1}–${d.offset + d.items.length}`;
    $("pageinfo").textContent = `offset ${d.offset}`;
    $("prev").disabled = d.offset === 0;
    $("next").disabled = d.items.length < d.limit;
    $("results").classList.remove("hidden");
  } catch (e) {
    const el = $("err");
    el.textContent = "Something went wrong: " + e.message;
    el.classList.remove("hidden");
  } finally {
    $("loading").classList.add("hidden");
  }
}

async function toggleDetail(det, id) {
  const box = det.querySelector(".detail-box");
  const nowHidden = det.classList.toggle("hidden");
  if (nowHidden) return; // just closed
  if (!box.dataset.loaded) {
    box.dataset.loaded = "1";
    try {
      const r = await (await fetch(`/api/record?collection=${encodeURIComponent($("col").value)}&id=${encodeURIComponent(id)}&vectors=true`)).json();
      if (r.found) {
        det.querySelector(".full").textContent = r.document;
        renderEmbedding(det, r);
      } else {
        det.querySelector(".emb-head").textContent = "record not found";
      }
    } catch (e) {
      det.querySelector(".emb-head").textContent = "vector load failed: " + e.message;
    }
  }
}

function renderEmbedding(det, r) {
  const v = r.embedding || [];
  const head = det.querySelector(".emb-head");
  const bars = det.querySelector(".emb-bars");
  const vals = det.querySelector(".emb-vals");
  if (!v.length) { head.textContent = "no vector stored"; return; }
  head.textContent = `embedding · dim ${r.dim} · L2 norm ${r.norm}`;
  // Downsample to 64 buckets for the bar view.
  const N = 64, per = Math.max(1, Math.floor(v.length / N));
  let max = 0;
  const buckets = [];
  for (let i = 0; i < N; i++) {
    let s = 0, n = 0;
    for (let j = i * per; j < Math.min(v.length, (i + 1) * per); j++) { s += Math.abs(v[j]); n++; }
    const a = n ? s / n : 0;
    buckets.push(a);
    if (a > max) max = a;
  }
  bars.innerHTML = "";
  buckets.forEach((a) => {
    const b = document.createElement("i");
    b.style.height = `${Math.max(4, Math.round((a / (max || 1)) * 100))}%`;
    b.title = a.toFixed(4);
    bars.appendChild(b);
  });
  vals.textContent = "first 16 dims: " + v.slice(0, 16).map((x) => x.toFixed(4)).join("  ");
}

$("go").onclick = () => { offset = 0; browse(); };
$("q").addEventListener("keydown", (e) => { if (e.key === "Enter") { offset = 0; browse(); } });
$("prev").onclick = () => { offset = Math.max(0, offset - parseInt($("limit").value, 10)); browse(); };
$("next").onclick = () => { offset += parseInt($("limit").value, 10); browse(); };

init().catch((e) => {
  const el = $("err");
  el.textContent = "Failed to load: " + e.message;
  el.classList.remove("hidden");
});
