const $ = (id) => document.getElementById(id);
const q = $("q"), go = $("go"), k = $("k"), kval = $("kval");

// Theme: remembered across visits, defaults to dark.
const root = document.documentElement;
const themeBtn = $("theme");
function setTheme(t) {
  root.setAttribute("data-theme", t);
  themeBtn.textContent = t === "dark" ? "☀️" : "🌙";
  try { localStorage.setItem("mm-theme", t); } catch (_) {}
}
setTheme((() => { try { return localStorage.getItem("mm-theme") || "dark"; } catch (_) { return "dark"; } })());
themeBtn.onclick = () => setTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");

kval.textContent = k.value;
k.oninput = () => (kval.textContent = k.value);

document.querySelectorAll(".chip").forEach((c) => {
  c.onclick = () => { q.value = c.textContent; ask(); };
});
q.addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
go.onclick = ask;

fetch("/api/stats").then((r) => r.json()).then((s) => {
  if (s.reviews) $("stat-count").textContent = s.reviews.toLocaleString();
  const b = $("llm-badge");
  if (s.llm_configured) { b.textContent = "LLM ready ✔"; b.className = "badge ok"; }
  else { b.textContent = "LLM not configured — snippets only"; b.className = "badge bad"; }
}).catch(() => {});

function stars(n) {
  n = Math.max(0, Math.min(5, n || 0));
  return "★".repeat(n) + "☆".repeat(5 - n);
}
function branchShort(b) {
  return (b || "").replace("Disneyland_", "");
}

async function ask() {
  const question = q.value.trim();
  if (question.length < 2) return;
  go.disabled = true;
  $("err").classList.add("hidden");
  $("loading").classList.remove("hidden");
  $("answer").classList.add("hidden");
  $("points").classList.add("hidden");
  $("results").classList.add("hidden");
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, k: parseInt(k.value, 10), model: $("model").value || null }),
    });
    if (!res.ok) throw new Error("server " + res.status);
    const d = await res.json();
    renderFilters(d.filters);
    renderAnswer(d.answer, !!d.llm_failed);
    const m = d.metrics || {};
    const perf = $("perf");
    if (m.llm_used && m.tok_per_sec) {
      perf.innerHTML = "";
      const b = document.createElement("b");
      b.textContent = `⚡ ${m.tok_per_sec} tok/s`;
      perf.appendChild(b);
      perf.append(` · ${m.completion_tokens} tokens in ${m.seconds}s · ${m.model}`);
    } else {
      perf.textContent = "";
    }
    $("answer").classList.remove("hidden");
    const cards = $("cards");
    cards.innerHTML = "";
    (d.hits || []).forEach((h) => {
      const el = document.createElement("div");
      el.className = "card";
      const pct = h.distance == null ? null : Math.max(0, (1 - h.distance) * 100);
      el.innerHTML =
        `<div class="meta"><span class="branch">${branchShort(h.branch)}</span>` +
        `<span class="stars">${stars(h.rating)}</span><span>${h.rating ?? "? "}/5</span>` +
        (pct == null ? "" : `<span class="match">◎ ${pct.toFixed(1)}% match</span>`) +
        `</div>` +
        `<div class="meta"><span>${h.reviewer_location || "?"}</span><span>·</span><span>${h.year_month || ""}</span></div>` +
        `<div class="snip clamped"></div>` +
        `<button class="more hidden">Show more ↓</button>` +
        `<div class="rid">Review ID: ${h.review_id ?? "?"}</div>`;
      const snip = el.querySelector(".snip");
      snip.textContent = h.snippet || "";
      const more = el.querySelector(".more");
      if ((h.snippet || "").length > 350) {
        more.classList.remove("hidden");
        more.onclick = () => {
          const open = snip.classList.toggle("clamped");
          more.textContent = open ? "Show more ↓" : "Show less ↑";
        };
      }
      cards.appendChild(el);
    });
    $("rcount").textContent = `· ${d.count} reviews`;
    $("results").classList.remove("hidden");
  } catch (e) {
    const el = $("err");
    el.textContent = "Something went wrong: " + e.message;
    el.classList.remove("hidden");
  } finally {
    $("loading").classList.add("hidden");
    go.disabled = false;
  }
}

function renderAnswer(text, isFallback) {
  const ab = $("answer-body");
  const pb = $("points-body");
  ab.innerHTML = "";
  pb.innerHTML = "";
  ab.classList.toggle("fallback", isFallback);
  // Normalize numbering: the small local model sometimes emits "1 Text"
  // (missing period) or runs "2. ..." mid-paragraph. Fix both so every
  // point becomes its own block.
  const norm = text
    .replace(/^\s*(\d+)\s+(?=[A-Z“"])/, "$1. ")
    .replace(/([.!?"])\s+(\d+)\.\s+(?=[A-Z“"])/g, "$1\n$2. ");
  let first = true;
  let nPoints = 0;
  const blocks = [];
  norm.split(/\n\s*\n/).forEach((para) => {
    para.split(/\n(?=\d+\.\s)/).forEach((b) => blocks.push(b));
  });
  blocks.forEach((block) => {
    block = block.trim();
    if (!block) return;
    const m = block.match(/^\d+\.\s+([\s\S]*)$/);
    if (m) {
      const d = document.createElement("div");
      d.className = "point";
      d.textContent = m[1];
      pb.appendChild(d);
      nPoints++;
    } else {
      const p = document.createElement("p");
      p.textContent = block;
      if (first) p.className = "lead";
      ab.appendChild(p);
    }
    first = false;
  });
  $("answer").classList.remove("hidden");
  $("points").classList.toggle("hidden", nPoints === 0);
}

function renderFilters(f) {
  const box = $("filters");
  box.innerHTML = "";
  const pill = (label, val) => {
    const s = document.createElement("span");
    s.className = "pill";
    s.innerHTML = `${label}: <b></b>`;
    s.querySelector("b").textContent = val ?? "any";
    box.appendChild(s);
  };
  pill("Park", f.branch ? branchShort(f.branch) : null);
  pill("From", f.reviewer_location);
  pill("Months", f.months ? f.months.join(", ") : null);
  pill("Years", f.years ? f.years.join(", ") : null);
  (f.relaxations || []).forEach((r) => {
    const s = document.createElement("span");
    s.className = "pill warn";
    s.textContent = "↩ " + r;
    box.appendChild(s);
  });
  box.classList.remove("hidden");
}
