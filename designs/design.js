/* Esports Scoreboard redesign preview: small shell helpers shared by the three directions.
   - html.rt-<section> class for per-section layout (home, cs2, predictions, ...)
   - phone tab bar (Home, CS2, Picks, Search, More) for directions that use one (data-d="a" and "c")
   No data, no tracking, no storage; app.js keeps doing all routing and rendering. */
(function () {
  var H = document.documentElement, D = H.getAttribute("data-d") || "";
  function top() {
    var h = (location.hash || "").replace(/^#/, "");
    if (!h) { var m = document.querySelector('meta[name="fragnet-route"]'); h = m ? m.getAttribute("content") || "" : ""; }
    var t = (h.split("/")[0] || "home").toLowerCase();
    if (t === "team" || t === "player" || t === "match") { var p = h.split("/")[1]; t = p === "val" ? "valorant" : "cs2"; }
    if (t === "guild") t = "wow";
    return t;
  }
  var TABS = [["home", "Home", "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"],
              ["cs2", "CS2", "M4 5h16v4H4zM4 11h10v4H4zM4 17h13v3H4z"],
              ["predictions", "Picks", "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 4v5l4 2"],
              ["search", "Search", "M10.5 4a6.5 6.5 0 1 0 4.1 11.5l4.7 4.7 1.4-1.4-4.7-4.7A6.5 6.5 0 0 0 10.5 4z"],
              ["more", "More", "M4 7h16M4 12h16M4 17h16"]];
  var MORE = [["valorant", "Valorant"], ["wow", "WoW Retail"], ["wow-forever", "WoW Forever"], ["news", "News"],
              ["roundup", "Weekly roundups"], ["forums", "Forums"], ["about", "About"]];
  var bar, sheet;
  function build() {
    if (D !== "a" && D !== "a2" && D !== "c") return;
    bar = document.createElement("nav");
    bar.id = "dz-tabbar"; bar.setAttribute("aria-label", "Main sections");
    bar.innerHTML = TABS.map(function (t) {
      var ic = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + t[2] + '"/></svg>';
      return t[0] === "more" ? '<button type="button" data-tab="more" aria-expanded="false">' + ic + "<span>" + t[1] + "</span></button>"
        : '<a href="#' + t[0] + '" data-tab="' + t[0] + '">' + ic + "<span>" + t[1] + "</span></a>";
    }).join("");
    sheet = document.createElement("div");
    sheet.id = "dz-more"; sheet.hidden = true;
    sheet.innerHTML = '<div class="dz-more-in"><div class="dz-more-h">More sections</div>' +
      MORE.map(function (m) { return '<a href="#' + m[0] + '">' + m[1] + "</a>"; }).join("") + "</div>";
    document.body.appendChild(sheet); document.body.appendChild(bar);
    bar.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("button[data-tab=more]");
      if (b) { sheet.hidden = !sheet.hidden; b.setAttribute("aria-expanded", String(!sheet.hidden)); }
      else if (!sheet.hidden) { sheet.hidden = true; }
    });
    sheet.addEventListener("click", function (e) { if (e.target === sheet || (e.target.closest && e.target.closest("a"))) sheet.hidden = true; });
  }
  function mark() {
    var t = top();
    H.className = H.className.replace(/\brt-[a-z0-9-]+\b/g, "").replace(/\s+/g, " ").trim() + " rt-" + t;
    if (bar) {
      var inMore = MORE.some(function (m) { return m[0] === t; });
      Array.prototype.forEach.call(bar.querySelectorAll("[data-tab]"), function (a) {
        var k = a.getAttribute("data-tab"); a.classList.toggle("on", k === t || (k === "more" && inMore));
      });
    }
  }

  /* ---------- a2 only: team initial badges + friendlier empty states (data from the already-loaded site data) ---------- */
  var HUES = ["#2F5E8C", "#7A4E9A", "#2F7D6B", "#A35A2C", "#8A3F55", "#4F6B2E", "#3D5BA8", "#8C6A1F"];
  function initials(n) {
    var w = String(n || "").replace(/[^A-Za-z0-9 ]+/g, " ").trim().split(/\s+/).filter(Boolean);
    if (!w.length) return "?";
    return (w.length > 1 ? w[0][0] + w[1][0] : w[0].slice(0, 2)).toUpperCase();
  }
  function hue(n) { var h = 0; String(n).split("").forEach(function (c) { h = (h * 31 + c.charCodeAt(0)) >>> 0; }); return HUES[h % HUES.length]; }
  function badge(n, cls) {
    var b = document.createElement("span");
    b.className = "dz-bd" + (cls ? " " + cls : ""); b.setAttribute("aria-hidden", "true");
    b.style.setProperty("--bd", hue(n)); b.textContent = initials(n);
    return b;
  }
  function nameOf(el) { var t = ""; el.childNodes.forEach(function (c) { if (c.nodeType === 3) t += c.textContent; }); return t.trim(); }
  var FACTS = null, FACTS_BUSY = false;   // last NA match day + season end, read once from data.json (browser cache) when an empty state needs them
  function fmtDay(t, o) { return new Date(t).toLocaleDateString("en-US", Object.assign({ timeZone: "America/Los_Angeles" }, o)); }
  function facts() {
    if (FACTS || FACTS_BUSY || !window.fetch) return FACTS;
    FACTS_BUSY = true;
    fetch("data.json").then(function (r) { return r.json(); }).then(function (d) {
      var cs = (d || {}).cs || {}, last = "";
      (cs.matches || []).forEach(function (x) { if (x.region === "NA" && x.t && x.t > last) last = x.t; });
      FACTS = { last: last ? fmtDay(last, { weekday: "short", month: "short", day: "numeric" }) : "",
                end: (cs.season || {}).end ? fmtDay(cs.season.end, { month: "short", day: "numeric" }) : "" };
      Array.prototype.forEach.call(document.querySelectorAll(".dz-empty"), function (e) { e.parentNode && e.parentNode.removeChild(e); });
      Array.prototype.forEach.call(document.querySelectorAll(".dz-empty-row"), function (e) { e.classList.remove("dz-empty-row"); });
      var b = document.getElementById("dz-picks"); if (b) b.parentNode.removeChild(b);
      decorate();
    }).catch(function () { FACTS = { last: "", end: "" }; });
    return null;
  }
  function lastNA() { var f = facts(); return f ? f.last : ""; }
  function seasonEnd() { var f = facts(); return f ? f.end : ""; }
  function emptyCard(title) {
    var last = lastNA(), end = seasonEnd();
    return '<div class="dz-empty"><div class="dz-empty-ic" aria-hidden="true"></div><div><div class="dz-empty-t">' + title + "</div>" +
      '<p>Picks show up here as soon as the next NA round is posted.' + (last ? " The last NA matches were played <b>" + last + "</b>." : "") +
      (end ? " The regular season runs through <b>" + end + "</b>." : "") + "</p>" +
      '<p class="dz-empty-a"><a href="#cs2/results">Latest NA results &raquo;</a> <a href="#cs2/na-main">NA standings &raquo;</a></p></div></div>';
  }
  /* a2: last safety net for source names in text written by build-time files (rank.js, spot.js); news headlines are left alone */
  var SRC_RX = [[/FACEIT (?=(?:match )?(?:stats|scoreboards)\b)/g, ""], [/ (?:on|from|by) (?:FACEIT|vlr\.gg|Raider\.IO)\b/g, ""], [/\s*\((?:FACEIT|vlr\.gg|Raider\.IO)[^)]*\)/g, ""]];
  function scrub(v) {
    var w = document.createTreeWalker(v, NodeFilter.SHOW_TEXT, { acceptNode: function (n) {
      return n.parentNode.closest(".listbox, .newsbox, #home-news") || !/FACEIT|vlr\.gg|Raider\.IO/.test(n.nodeValue) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT; } });
    var list = [], n; while ((n = w.nextNode())) list.push(n);
    list.forEach(function (t) { var x = t.nodeValue; SRC_RX.forEach(function (r) { x = x.replace(r[0], r[1]); }); if (x !== t.nodeValue) t.nodeValue = x; });
  }
  function decorate() {
    if (D !== "a2") return;
    var v = document.getElementById("view"); if (!v) return;
    scrub(v);
    Array.prototype.forEach.call(v.querySelectorAll(".pc-tm:not([data-bd])"), function (el) {
      el.setAttribute("data-bd", "1"); el.insertBefore(badge(nameOf(el)), el.firstChild);
    });
    var t = top(), h = (location.hash || "").replace(/^#/, "");
    var hm = document.querySelector('meta[name="fragnet-route"]'); if (!h && hm) h = hm.getAttribute("content") || "";
    if (/^team\//.test(h)) {
      var h1 = v.querySelector(".std-header h1");
      if (h1 && !h1.querySelector(".dz-bd") && !v.querySelector(".team-logo")) h1.insertBefore(badge(h1.textContent, "dz-bd-lg"), h1.firstChild);
    }
    if (t === "home" && !v.querySelector("#na-picks") && !v.querySelector("#dz-picks")) {
      var g = v.querySelector(".home-gcards");
      if (g && window.ESB_PREDS) {
        var box = document.createElement("div");
        box.id = "dz-picks"; box.className = "std";
        box.innerHTML = '<div class="std-header"><h2>This Week&rsquo;s NA Picks</h2><span class="meta"><a href="#predictions">all predictions &raquo;</a></span></div>' + emptyCard("No NA matches scheduled this week");
        g.insertBefore(box, g.firstChild);
      }
    }
    var predEmpty = t === "predictions" && window.ESB_PREDS && !(window.ESB_PREDS.matches || []).length;
    if (predEmpty && !v.querySelector(".dz-empty")) {
      var intro = v.querySelector(".pred-intro") || v.querySelector(".infobox");
      if (intro) { var d = document.createElement("div"); d.innerHTML = emptyCard("No NA matches scheduled this week"); intro.parentNode.insertBefore(d.firstChild, intro.nextSibling); }
    }
    H.classList.toggle("dz-pred-empty", !!(predEmpty && v.querySelector(".dz-empty")));
    var tb = v.querySelector("#today-board");
    if (tb && !tb.querySelector(".tbl") && !tb.querySelector(".dz-empty-row")) {
      var note = tb.querySelector(".note"), last = lastNA();
      if (note) { var nn = note.cloneNode(false); note.parentNode.replaceChild(nn, note); note = nn; note.className = "note dz-empty-row"; note.innerHTML = "<b>No NA matches today.</b>" + (last ? " Last NA matches: " + last + "." : "") + ' <a href="#cs2/results">All NA results &raquo;</a>'; }
    }
  }
  if (D === "a2") {
    var obs = new MutationObserver(function () { obs.disconnect(); try { decorate(); } finally { var v = document.getElementById("view"); if (v) obs.observe(v, { childList: true, subtree: true }); } });
    var start = function () { var v = document.getElementById("view"); decorate(); if (v) obs.observe(v, { childList: true, subtree: true }); };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
  }
  function init() { build(); mark(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
  window.addEventListener("hashchange", mark);
  window.addEventListener("hashchange", function () { if (top() === "search" && window.innerWidth <= 600) { var q = document.getElementById("q"); if (q) setTimeout(function () { q.focus(); }, 60); } });
})();
