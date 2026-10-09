/* Esports Scoreboard v4.7 - 2007-portal skin. Hash-routed, renders ONLY data.json (written
   by fetch_data.py; data.js is the identical copy used for file://). Missing
   sources show MISS badges, failed-but-kept sources show STALE. Forums are
   read-only for launch (FORUM_POSTING_ENABLED = false; no browser storage used).
   All times are shown in Pacific Time (America/Los_Angeles). */
(function () {
  "use strict";
  var D = null, IDX = [], pendingHL = null, tmr = null;
  var PER_PAGE = 25, MAX_Q = 100;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- helpers ---------- */
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  // only absolute http(s) URLs without whitespace/control chars are rendered as links
  function safeUrl(u) { u = String(u || "").trim(); return /^https?:\/\/[^\s<>"'\u0000-\u001f]+$/i.test(u) ? u : "#"; }
  function ext(url, text, cls) {
    var u = safeUrl(url);
    if (u === "#") return '<span' + (cls ? ' class="' + cls + '"' : "") + ">" + esc(text) + "</span>";
    return '<a href="' + esc(u) + '" target="_blank" rel="noopener"' + (cls ? ' class="' + cls + '"' : "") + ">" + esc(text) + "</a>";
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  /* Pacific-time parts of a Date (falls back to the browser zone if Intl lacks tz data) */
  var PTF = null;
  try { PTF = new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", hourCycle: "h23", weekday: "short", timeZoneName: "short" }); } catch (e) { PTF = null; }
  function ptParts(d) {
    if (PTF) {
      var o = {};
      PTF.formatToParts(d).forEach(function (p) { o[p.type] = p.value; });
      var wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(o.weekday);
      return { y: +o.year, m: +o.month - 1, d: +o.day, h: +o.hour % 24, mi: +o.minute, wd: wd, tz: o.timeZoneName || "PT" };
    }
    return { y: d.getFullYear(), m: d.getMonth(), d: d.getDate(), h: d.getHours(), mi: d.getMinutes(), wd: d.getDay(), tz: "local" };
  }
  function fmt(iso, mode) { // "dt" default | "d" | "short" | "md" ; "...z" variants append the zone (PDT/PST)
    if (!iso) return "?";
    var dd = new Date(iso);
    if (isNaN(dd)) return esc(iso);
    var p = ptParts(dd), z = /z$/.test(mode || ""), m = (mode || "dt").replace(/z$/, "");
    var t = pad(p.h) + ":" + pad(p.mi), out;
    if (m === "d") out = p.y + "-" + pad(p.m + 1) + "-" + pad(p.d);
    else if (m === "md") out = MON[p.m] + " " + p.d;
    else if (m === "short") out = MON[p.m] + " " + p.d + ", " + t;
    else out = MON[p.m] + " " + p.d + " " + p.y + " " + t;
    return out + (z || m === "dt" || m === "short" ? " " + p.tz : "");
  }
  var REGION_NAMES = null;
  try { REGION_NAMES = new Intl.DisplayNames(["en"], { type: "region" }); } catch (e) { REGION_NAMES = null; }
  function countryName(cc) { try { return cc && REGION_NAMES ? REGION_NAMES.of(cc) : cc || ""; } catch (e) { return cc || ""; } }
  function slug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
  function badge(st) { return st === "OK" ? '<span class="ok">OK</span>' : st === "STALE" ? '<span class="stale-b">STALE</span>' : '<span class="miss-b">MISS</span>'; }
  /* Visitor-facing pages never show fetch plumbing (source states, endpoints, error text):
     missing data -> a short friendly line, kept-old data -> a neutral "Last updated" line.
     The full per-source table lives on the low-key #status page (footer / About only). */
  function soon(msg) { return '<div class="empty soon">' + esc(msg || "Not available yet.") + "</div>"; }
  function missRow() { return soon(); }
  function staleRow(src, reason, ts) { return ts ? '<div class="note upd-note">Last updated ' + fmt(ts, "short") + ".</div>" : ""; }
  var CREDIT = { cs: [["FACEIT", "https://www.faceit.com/en/cs2/league/ESEA%20League/a14b8616-45b9-4581-8637-4dfd0b5f6af8"]],
    valorant: [["vlr.gg", "https://www.vlr.gg/"]], wow: [["Raider.IO", "https://raider.io/"]] };
  function srcLine(sec) {
    var cr = CREDIT[sec];
    if (!cr) {   // news: the publishers whose headlines are shown
      var seen = {};
      cr = [];
      newsItems().forEach(function (n) { if (n.source && !seen[n.source]) { seen[n.source] = 1; try { cr.push([n.source, new URL(n.url).origin + "/"]); } catch (e) { cr.push([n.source, ""]); } } });
    }
    var t = (D[sec] || {}).fetched_at;
    return '<div class="srcline">Data: ' + (cr.length ? cr.map(function (c) { return c[1] ? ext(c[1], c[0]) : esc(c[0]); }).join(", ") : "&ndash;") +
      (t ? " &middot; Updated " + fmt(t, "short") : "") + "</div>";
  }
  function staleNote(meta) { return meta && meta.stale ? '<div class="note upd-note">Last updated ' + fmt(meta.fetched_at, "short") + ".</div>" : ""; }
  function medal(rank) { var n = String(rank).match(/^(\d+)(st|nd|rd|th)?$/); n = n ? +n[1] : 0; return n >= 1 && n <= 3 ? "r" + n : ""; }
  function rk(rank) { return '<td class="rk"><span>' + esc(rank) + "</span></td>"; }
  function std(title, meta, inner, id) {
    return '<div class="std"' + (id ? ' id="' + id + '"' : "") + '><div class="std-header"><h1>' + title + "</h1>" + (meta ? '<span class="meta">' + meta + "</span>" : "") + "</div>" + inner + "</div>";
  }
  /* v4.0 navigation: game -> section tabs, segmented pickers, breadcrumbs */
  var SECTIONS = {
    cs2: { name: "Counter-Strike 2", short: "CS2", sub: "ESEA League", tabs: [["standings", "cs2", "Standings"], ["results", "cs2/results", "Results"], ["players", "cs2/players", "Top Players"], ["today", "cs2/today", "Matches Today", "Today"], ["ranking", "cs2/ranking", "ESB Ranking", "Ranking"], ["top20", "cs2/top20", "Top 20", "Top 20"], ["awards", "cs2/awards", "Awards", "Awards"], ["playoffs", "cs2/playoffs", "Playoffs", "Playoffs"]] },
    valorant: { name: "Valorant", short: "Valorant", sub: "Challengers / Game Changers", tabs: [["events", "valorant/events", "Events"], ["results", "valorant/results", "Results"], ["players", "valorant/players", "Top Players"]] },
    wow: { name: "World of Warcraft", short: "WoW", sub: "Mythic raid race", tabs: [["us", "wow/us", "US Rankings"], ["eu", "wow/eu", "EU Rankings"]] }
  };
  /* v4.5 path pages (e.g. team/cs2/<id>/): the route comes from <meta name="fragnet-route"> until a hash is set.
     Hash links on those pages resolve through <base> to the front page, so navigation stays the plain hash SPA. */
  var PATH_ROUTE = (function () {
    var m = document.querySelector('meta[name="fragnet-route"]'), b = document.querySelector("base[href]");
    if (b) b.setAttribute("href", document.baseURI + (location.protocol === "file:" ? "index.html" : ""));   // freeze it; file:// has no directory index
    return m ? (m.getAttribute("content") || "").replace(/^#/, "") : "";
  })();
  function curHash() { return location.hash || (PATH_ROUTE ? "#" + PATH_ROUTE : ""); }
  var KEEP_SCROLL = false, CRUMB = null, CUR_SEC = "", LAST_SEC = (curHash() || "#home").split("/")[0];
  function setCrumbs(list) { CRUMB = list.filter(Boolean); }
  function crumbHtml(list) {
    return '<nav class="crumbs" aria-label="Breadcrumb"><a href="#home">Home</a>' + list.map(function (c, i) {
      return ' <span class="sep" aria-hidden="true">&rsaquo;</span> ' + (c[1] && i < list.length - 1 ? '<a href="#' + esc(c[1]) + '">' + esc(c[0]) + "</a>" : '<span class="cur" aria-current="page">' + esc(c[0]) + "</span>");
    }).join("") + "</nav>";
  }
  function secTabs(game, active) {
    CUR_SEC = game + ":" + active;
    var g = SECTIONS[game];
    return '<nav class="sectabs" aria-label="' + esc(g.short) + ' sections">' + g.tabs.map(function (t) {
      var on = t[0] === active;
      return '<a href="#' + (game === "cs2" && t[0] === "standings" ? csHome() : t[1]) + '"' + (on ? ' class="on" aria-current="page"' : "") + ">" + (t[3] ? '<span class="lg">' + esc(t[2]) + '</span><span class="sh">' + esc(t[3]) + "</span>" : esc(t[2])) + "</a>";
    }).join("") + "</nav>";
  }
  // game header bar + sticky section tabs (tabs sit outside .std so they can stick while the page scrolls)
  function gameHead(game, active, title, extra) {
    return std(esc(title), "", "", "game-head") + secTabs(game, active) + (extra || "");
  }
  function seg(label, items) { // items: [label, hash, on, shortLabel]
    return '<div class="seg" role="group" aria-label="' + esc(label) + '"><span class="seg-l">' + esc(label) + "</span>" + items.map(function (it) {
      return '<a href="#' + esc(it[1]) + '"' + (it[2] ? ' class="on" aria-current="true"' : "") + ">" + (it[3] ? '<span class="lg">' + esc(it[0]) + '</span><span class="sh">' + esc(it[3]) + "</span>" : esc(it[0])) + "</a>";
    }).join("") + "</div>";
  }
  var TB_FOLD = 6; // groups longer than this fold into a tap-to-open list (keeps phones tidy)
  function toolbar(items, active, cls) {
    function a(it) { return '<a href="#' + esc(it.hash) + '" class="' + (it.id === active ? "on" : "") + '"' + (it.id === active ? ' aria-current="page"' : "") + '><span class="bullet" aria-hidden="true">&rsaquo;</span>' + esc(it.label) + "</a>"; }
    var out = [], grp = null, run = [];
    function flush() {
      if (grp != null && run.length > TB_FOLD) {
        var cur = run.filter(function (it) { return it.id === active; })[0];
        out.push('<details class="tb-fold"><summary><span class="grp">' + esc(grp) + '</span> <span class="tb-cur">' + (cur ? esc(cur.label) : "choose (" + run.length + ")") + '</span><span class="tb-caret" aria-hidden="true">&#9662;</span></summary><div class="tb-list">' + run.map(a).join("") + "</div></details>");
      } else out.push((grp != null ? '<span class="grp">' + esc(grp) + "</span>" : "") + run.map(a).join(""));
      run = [];
    }
    items.forEach(function (it) { if (it.grp) { flush(); grp = it.grp; } else run.push(it); });
    flush();
    return '<div class="' + (cls || "toolbar") + '">' + out.join("") + "</div>";
  }
  function tiles(arr) {
    arr = arr.filter(Boolean);
    return arr.length ? '<div class="tiles">' + arr.map(function (t) { return '<div class="tile' + (t[2] ? " " + t[2] : "") + '"><b>' + t[1] + "</b><span>" + esc(t[0]) + "</span></div>"; }).join("") + "</div>" : "";
  }
  function fold(s) { s = String(s == null ? "" : s); try { s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, ""); } catch (e) {} return s.toLowerCase(); }
  function pageOf(parts) { var m = (parts || []).join("/").match(/(?:^|\/)p(\d+)$/); return m ? Math.max(1, +m[1]) : 1; }
  function pager(total, page, base) {
    var pages = Math.ceil(total / PER_PAGE);
    if (pages <= 1) return "";
    var h = '<nav class="pager" aria-label="Pages"><span class="title">Pages:</span>';
    if (page > 1) h += '<a href="#' + esc(base) + "/p" + (page - 1) + '">&laquo; Prev</a>';
    for (var i = 1; i <= pages; i++) h += i === page ? '<span class="act" aria-current="page">' + i + "</span>" : '<a href="#' + esc(base) + "/p" + i + '">' + i + "</a>";
    if (page < pages) h += '<a href="#' + esc(base) + "/p" + (page + 1) + '">Next &raquo;</a>';
    var a = (page - 1) * PER_PAGE + 1, b = Math.min(total, page * PER_PAGE);
    return h + '<span class="info">showing ' + a + "&ndash;" + b + " of " + total + "</span></nav>";
  }
  function slicePage(arr, page) { return arr.slice((page - 1) * PER_PAGE, page * PER_PAGE); }
  function num(n) { var x = Number(n); return isFinite(x) ? x : 0; }

  /* ---------- data shortcuts ---------- */
  var CSD = null; // North America first everywhere (v4.0); stable within a region
  function csDivs() {
    var src = (D.cs && D.cs.divisions) || [];
    if (CSD && CSD.src === src) return CSD.list;
    var list = src.map(function (d, i) { return { d: d, i: i }; }).sort(function (a, b) { return (a.d.region === "NA" ? 0 : 1) - (b.d.region === "NA" ? 0 : 1) || a.i - b.i; }).map(function (x) { return x.d; });
    CSD = { src: src, list: list };
    return list;
  }
  // Valorant event indices with North America events first (ids stay event-N of the data order)
  function evOrder() {
    return valEvents().map(function (e, i) { return i; }).sort(function (a, b) {
      var na = function (i) { return /north america/i.test(valEvents()[i].title || "") ? 0 : 1; };
      return na(a) - na(b) || a - b;
    });
  }
  function wowRegs(rks) { return Object.keys(rks || {}).sort(function (a, b) { return (a === "us" ? 0 : 1) - (b === "us" ? 0 : 1); }); }
  function divId(d) { return slug(d.region + "-" + d.division); }
  function valEvents() { return (D.valorant && D.valorant.events) || []; }
  function evId(i) { return "event-" + (i + 1); }
  function shortEv(t) { return String(t || "").replace(/^Challengers 20\d\d: /, "VCL ").replace(/^VCL \d\d: /, "VCL ").replace(/^Game Changers 20\d\d: /, "GC "); }
  function newsItems() { return (D.news && D.news.items) || []; }
  function valResults() { return (D.valorant && D.valorant.results) || []; }
  function rioPage(raid, region) { return raid && raid.slug ? "https://raider.io/" + encodeURIComponent(raid.slug) + "/rankings/" + encodeURIComponent(region || "world") + "/mythic" : "https://raider.io/"; }
  /* ---------- detail-page links + lookups (v3.3) ---------- */
  function ilink(hash, text, cls) { return '<a href="#' + esc(hash) + '"' + (cls ? ' class="' + cls + '"' : "") + ">" + esc(text) + "</a>"; }
  function csTeamId(t) { if (!t) return ""; if (t.id) return t.id; var m = String(t.url || "").match(/\/teams\/([0-9a-f-]{36})$/i); return m ? m[1] : ""; }   // older data.json: id only in url
  function teamHash(t) { var id = csTeamId(t); return id ? "team/cs2/" + encodeURIComponent(id) : ""; }
  function playerHash(nick) { return "player/cs2/" + encodeURIComponent(nick); }
  function valHash(name) { return "team/val/" + slug(name); }
  function guildRealm(g) { return g.realm_slug || slug(g.realm); }
  function guildHash(region, g) { return "guild/" + region + "/" + encodeURIComponent(guildRealm(g)) + "/" + encodeURIComponent(g.guild); }
  function csTeamLink(t) { var h = teamHash(t); return h ? ilink(h, t.name) : ext(t.url, t.name); }
  function csPlayers() { return (D.cs && (D.cs.players && D.cs.players.length ? D.cs.players : D.cs.top_players)) || []; }
  /* v3.7.2: Main/Intermediate season stats live in the lazy teams.js ("players", compact rows in player_cols order) */
  var XP = null;
  function xPlayers() {
    var x = window.FRAGNET_TEAMS;
    if (!x || !x.players) return [];
    if (XP && XP.src === x) return XP.list;
    var tName = {}; csDivs().forEach(function (d) { (d.teams || []).forEach(function (t) { if (t.id) tName[t.id] = t.name; }); });
    var cols = x.player_cols || [], list = x.players.map(function (row) {
      var o = {}; cols.forEach(function (c, i) { o[c] = row[i]; });
      o.url = "https://www.faceit.com/en/players/" + encodeURIComponent(o.nick || "");
      if (o.team_id && !o.team) { var tm = tName[o.team_id]; o.team = tm || null; if (!tm) o.team_id = null; }
      return o;
    });
    XP = { src: x, list: list }; return list;
  }
  function allCsPlayers() { return csPlayers().concat(xPlayers()); }
  var MINR = function () { return num(((D.cs || {}).top_players_meta || {}).min_rounds || 20); };
  function findCsTeam(id) {
    var ds = csDivs();
    for (var i = 0; i < ds.length; i++) for (var j = 0; j < (ds[i].teams || []).length; j++) if (csTeamId(ds[i].teams[j]) === id && id) return { t: ds[i].teams[j], d: ds[i] };
    return null;
  }
  /* ----- lazy teams.js (v3.6): rosters + extra match lines for every team outside the top 20 ----- */
  var TX_STATE = "";
  function teamsX() { return window.FRAGNET_TEAMS || null; }
  function loadTeams() {
    if (window.FRAGNET_TEAMS) { TX_STATE = "ok"; return; }
    if (TX_STATE) return;
    TX_STATE = "loading";
    var sc = document.createElement("script");
    sc.src = "teams.js?v=" + encodeURIComponent(D.fetched_at || "");
    function done(ok) { TX_STATE = ok && window.FRAGNET_TEAMS ? "ok" : "fail"; if (/^#((team|player|match)\/cs2\/|search|cs2(\/(?!results)|$)|home|$)/.test(curHash() || "#")) { KEEP_SCROLL = true; route(); } }
    sc.onload = function () { done(true); };
    sc.onerror = function () { done(false); };
    document.head.appendChild(sc);
  }
  /* ----- lazy val.js (v3.8): Valorant event player lines, per-player totals and rosters ----- */
  var VX_STATE = "", VXC = null;
  function loadVal() {
    if (window.FRAGNET_VAL) { VX_STATE = "ok"; return; }
    if (VX_STATE) return;
    VX_STATE = "loading";
    var sc = document.createElement("script");
    sc.src = "val.js?v=" + encodeURIComponent(D.fetched_at || "");
    function done(ok) { VX_STATE = ok && window.FRAGNET_VAL ? "ok" : "fail"; if (/^#(team\/val|player\/val|match\/val|valorant\/players|search)/.test(curHash())) { KEEP_SCROLL = true; route(); } }
    sc.onload = function () { done(true); };
    sc.onerror = function () { done(false); };
    document.head.appendChild(sc);
  }
  function rowsOf(cols, rows) { return (rows || []).map(function (r) { var o = {}; cols.forEach(function (c, i) { o[c] = r[i]; }); return o; }); }
  function valX() {
    var x = window.FRAGNET_VAL;
    if (!x) return null;
    if (VXC && VXC.src === x) return VXC;
    var teams = x.teams || {}, bySlug = {};
    Object.keys(teams).forEach(function (id) { var t = teams[id]; if (t && t.name) bySlug[slug(t.name)] = t; });
    VXC = { src: x, lines: rowsOf(x.player_cols || [], x.players), agg: rowsOf(x.agg_cols || [], x.agg), teams: teams, bySlug: bySlug };
    return VXC;
  }
  function valEvById(eid) {
    var evs = valEvents();
    for (var i = 0; i < evs.length; i++) { var m = String(evs[i].url || "").match(/\/event\/(\d+)\//); if (m && m[1] === String(eid)) return { e: evs[i], i: i }; }
    return null;
  }
  function valPHash(name) { return "player/val/" + encodeURIComponent(name); }
  function agentsCell(a) { var t = agentsHtml(a); return '<span class="ag" title="' + t + '">' + t + "</span>"; }
  function agentsHtml(a) { return esc((a || []).map(function (x) { return x.charAt(0).toUpperCase() + x.slice(1); }).join(", ")); }
  function valStatCells(p) {
    // some regions' vlr.gg stat pages publish no rating/KAST/ADR (shown as 0 there): show a dash, not a fake zero
    var na = !num(p.rating) && !num(p.kast) && !num(p.adr), dash = '<span class="dim" title="not published on vlr.gg for this event">&ndash;</span>';
    return '<td class="n hide-sm">' + num(p.rnd) + '</td><td class="n">' + (na ? dash : valPc(p)) + '</td><td class="n">' + Math.round(num(p.acs)) + '</td><td class="n">' + (p.kd == null ? "&ndash;" : num(p.kd).toFixed(2)) +
      '</td><td class="n hide-sm">' + (na ? dash : Math.round(num(p.kast)) + "%") + '</td><td class="n hide-sm">' + (na ? dash : num(p.adr).toFixed(1)) + '</td><td class="n hide-sm">' + (na && !num(p.hs) ? dash : Math.round(num(p.hs)) + "%") + "</td>";
  }
  var VAL_TH = '<th class="n hide-sm" title="rounds played">Rnd</th><th class="n" title="vlr.gg rating">R</th><th class="n" title="average combat score">ACS</th><th class="n" title="kills per death">K/D</th><th class="n hide-sm" title="kill / assist / trade / survive %">KAST</th><th class="n hide-sm" title="average damage per round">ADR</th><th class="n hide-sm" title="headshot %">HS%</th>';
  function teamFaceitUrl(t) { var id = csTeamId(t); return t.url || (UUID_RE.test(id) ? "https://www.faceit.com/en/teams/" + id : ""); }
  function xMatches(key, id) {
    var x = teamsX();
    return x ? (x[key] || []).filter(function (m) { return involves(m, id); }) : [];
  }
  function findCsPlayer(nick) {
    var n = String(nick || "").toLowerCase(), ps = allCsPlayers();
    for (var i = 0; i < ps.length; i++) if (String(ps[i].nick).toLowerCase() === n) return ps[i];
    return null;
  }
  function findRosterSpot(nick) {
    var n = String(nick || "").toLowerCase(), ds = csDivs();
    for (var i = 0; i < ds.length; i++) for (var j = 0; j < (ds[i].teams || []).length; j++) {
      var t = ds[i].teams[j], r = t.roster || [];
      for (var k = 0; k < r.length; k++) if (String(r[k].nick).toLowerCase() === n) return { t: t, d: ds[i], m: r[k] };
    }
    var x = window.FRAGNET_TEAMS, rs = (x && x.rosters) || {};   // lazy rosters of teams outside the top 20
    for (var tid in rs) {
      if (!Object.prototype.hasOwnProperty.call(rs, tid)) continue;
      var rr = rs[tid].r || [];
      for (var q = 0; q < rr.length; q++) if (String(rr[q][0]).toLowerCase() === n) {
        var f = findCsTeam(tid);
        if (f) return { t: f.t, d: f.d, m: { nick: rr[q][0], country: rr[q][1], sub: !!rr[q][2] } };
      }
    }
    return null;
  }
  function valTeamData(sl) {
    var out = { name: "", url: null, country: "", placings: [], results: [] };
    valEvents().forEach(function (e, i) {
      (e.standings || []).forEach(function (t) {
        if (slug(t.team) !== sl) return;
        out.name = out.name || t.team; out.country = out.country || t.country;
        if (!out.url && safeUrl(t.url) !== "#") out.url = t.url;
        out.placings.push({ ev: e, i: i, t: t });
      });
    });
    valResults().forEach(function (m) {
      if (slug(m.team1) === sl || slug(m.team2) === sl) { out.results.push(m); out.name = out.name || (slug(m.team1) === sl ? m.team1 : m.team2); }
    });
    return out;
  }
  function findGuild(region, realm, name) {
    var rows = ((D.wow && D.wow.rankings) || {})[region] || [], n = String(name || "").toLowerCase();
    for (var i = 0; i < rows.length; i++) if (guildRealm(rows[i]) === realm && String(rows[i].guild).toLowerCase() === n) return rows[i];
    return null;
  }
  function kv(rows) {
    return '<div class="rankbox"><table class="tbl kv"><tbody>' + rows.filter(Boolean).map(function (r) {
      return '<tr><th scope="row">' + esc(r[0]) + "</th><td>" + r[1] + "</td></tr>";
    }).join("") + "</tbody></table></div>";
  }
  function notFound(title, msg, back) {
    return std(esc(title), "", '<div class="empty">' + msg + "</div>") + (back ? '<div class="note">' + back + "</div>" : "");
  }
  var UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  /* ---------- CS2 match results (FACEIT Data API, v3.4) ---------- */
  function csMeta() { return (D.cs && D.cs.matches_meta) || null; }
  function csFinished() { return ((D.cs && D.cs.matches) || []).slice().sort(function (a, b) { return String(b.t || "").localeCompare(String(a.t || "")); }); }
  function csUpcoming() { return ((D.cs && D.cs.upcoming) || []).slice().sort(function (a, b) { return String(a.t || "").localeCompare(String(b.t || "")); }); }
  function csMatchSrc() {
    var s = ((D.cs && D.cs.sources) || []).filter(function (x) { return /match lists/.test(x.source) || /match results/.test(x.source); })[0];
    return s || null;
  }
  function roomUrl(m) { return m.url || (/^[0-9a-z-]+$/i.test(String(m.id || "")) ? "https://www.faceit.com/en/cs2/room/" + m.id : ""); }
  /* v5.6 row extras: current division rank prefix, map chips for series */
  var RANKC = null;
  function rankOf(id) {
    if (!RANKC) { RANKC = {}; csDivs().forEach(function (d) { (d.teams || []).forEach(function (t) { var k = csTeamId(t); if (k && t.rank) RANKC[k] = t.rank; }); }); }
    return RANKC[id] || "";
  }
  function rankPre(sd) { var r = sd && rankOf(sd.id); return r ? '<span class="rk-pre" title="current division standing (at the last update), not the rank when the match was played">#' + esc(r) + "</span> " : ""; }
  function mapChips(m) {
    if (!m.maps || m.maps.length < 2) return "";
    return '<div class="map-chips">' + m.maps.map(function (x) {
      var a = num(x.s1), b = num(x.s2);
      return '<span class="mchip">' + esc(x.map) + " " + (a > b ? "<b>" + a + "</b>-" + b : a + "-<b>" + b + "</b>") + "</span>";
    }).join(" ") + "</div>";
  }
  function csSide(sd) { return sd && sd.id && UUID_RE.test(sd.id) ? ilink("team/cs2/" + encodeURIComponent(sd.id), sd.name) : esc(sd ? sd.name : "TBD"); }
  function divOf(m) { return slug(m.region + "-" + m.division); }
  function involves(m, id) { return (m.t1 && m.t1.id === id) || (m.t2 && m.t2.id === id); }
  /* ----- v4.1 form & streaks: computed only from finished results already in data.json / teams.js ----- */
  function isFF(m) { var a = num(m.s1), b = num(m.s2); return a + b <= 1 && (num(m.bo) === 1 || !!m.nostats); }
  var FORM = null;
  function csForm(id) { // oldest -> newest results for a CS team: {r: W|L|D, ff, opp, score, t}
    var x = teamsX(), a = (D.cs && D.cs.matches) || [], b = (x && x.matches) || [];
    if (!FORM || FORM.a !== a || FORM.b !== b) {
      var seen = {}, map = {};
      a.concat(b).forEach(function (m) {
        if (!m || !m.id || seen[m.id] || !m.t1 || !m.t2 || !m.t1.id || !m.t2.id) return;   // byes / TBD have no opponent
        seen[m.id] = 1;
        [1, 2].forEach(function (side) {
          var me = side === 1 ? m.t1 : m.t2, op = side === 1 ? m.t2 : m.t1, w = num(m.winner);
          (map[me.id] = map[me.id] || []).push({ r: w === side ? "W" : w === 1 || w === 2 ? "L" : "D", ff: isFF(m), opp: op.name, score: side === 1 ? num(m.s1) + ":" + num(m.s2) : num(m.s2) + ":" + num(m.s1), t: m.t });
        });
      });
      Object.keys(map).forEach(function (k) { map[k].sort(function (p, q) { return String(p.t || "").localeCompare(String(q.t || "")); }); });
      FORM = { a: a, b: b, map: map };
    }
    return FORM.map[id] || [];
  }
  function valForm(name) { // Valorant results use winner 0/1 (team1/team2)
    var sl = slug(name), out = [];
    valResults().forEach(function (m) {
      var side = slug(m.team1) === sl ? 0 : slug(m.team2) === sl ? 1 : -1;
      if (side < 0 || (m.winner !== 0 && m.winner !== 1)) return;
      out.push({ r: m.winner === side ? "W" : "L", ff: false, opp: side === 0 ? m.team2 : m.team1, score: side === 0 ? m.score1 + ":" + m.score2 : m.score2 + ":" + m.score1, t: m.ts });
    });
    return out.sort(function (p, q) { return String(p.t || "").localeCompare(String(q.t || "")); });
  }
  function formHtml(list, n) {
    var last = list.slice(-(n || 5));
    if (!last.length) return '<span class="dim form-none" title="no finished matches yet">&ndash;</span>';
    return '<span class="form" aria-label="last ' + last.length + " results, newest right: " + last.map(function (f) { return f.ff ? f.r + " by forfeit" : f.r; }).join(", ") + '">' + last.map(function (f) {
      var tip = (f.r === "W" ? "Won" : f.r === "L" ? "Lost" : "Drew") + (f.ff ? " by forfeit" : "") + " vs " + f.opp + " " + f.score + (f.t ? " (" + fmt(f.t, "md") + ")" : "");
      return '<span class="fq ' + f.r.toLowerCase() + (f.ff ? " ff" : "") + '" title="' + esc(tip) + '">' + (f.ff ? "FF" : f.r) + "</span>";
    }).join("") + "</span>";
  }
  /* ----- v4.2 percentile chips: 5 steps (red -> green) within the same pool (division / tracked events) ----- */
  var PCC = {};
  function pcPool(key, build) {
    var c = PCC[key], t = window.FRAGNET_TEAMS || null, v = window.FRAGNET_VAL || null;
    if (c && c.d === D && c.t === t && c.v === v) return c.a;
    var a = build().map(Number).filter(function (x) { return isFinite(x); }).sort(function (x, y) { return x - y; });
    PCC[key] = { d: D, t: t, v: v, a: a };
    return a;
  }
  function chip(v, txt, pool, who) {
    v = Number(v);
    if (pool.length < 10 || !isFinite(v)) return "<b>" + txt + "</b>";
    var lo = 0, hi = pool.length;
    while (lo < hi) { var mid = (lo + hi) >> 1; if (pool[mid] < v) lo = mid + 1; else hi = mid; }
    var f = lo / pool.length, k = Math.min(5, Math.floor(f * 5) + 1);
    return '<span class="pc pc' + k + '" title="' + esc("better than " + Math.round(f * 100) + "% of " + pool.length + " " + who) + '">' + txt + "</span>";
  }
  function csPc(p, stat) {
    var txt = stat === "kd" ? num(p.kd).toFixed(2) : num(p.adr).toFixed(1);
    if (num(p.rounds) < MINR()) return "<b>" + txt + "</b>";
    var dv = p.region + " " + p.division;
    return chip(p[stat], txt, pcPool("cs:" + dv + ":" + stat, function () {
      return allCsPlayers().filter(function (q) { return q.region === p.region && q.division === p.division && num(q.rounds) >= MINR(); }).map(function (q) { return q[stat]; });
    }), dv + " players (min. " + MINR() + " rounds)");
  }
  function valPc(p) {
    var txt = num(p.rating).toFixed(2);
    if (num(p.rnd) < 100) return "<b>" + txt + "</b>";
    return chip(p.rating, txt, pcPool("val:rating", function () {
      var x = window.FRAGNET_VAL ? valX() : null;
      return (x ? x.agg : ((D.valorant || {}).top_players || [])).filter(function (q) { return num(q.rnd) >= 100; }).map(function (q) { return q.rating; });
    }), "players in the tracked events (min. 100 rounds)");
  }

  /* v4.6 player boards: every player with stats, sortable, min-rounds filter, 25 per page or all.
     State lives in the hash: <base>[/<division>][/s-<sort>][/m-<min rounds>][/p<n>|/all] */
  var MIN_OPTS = [0, 20, 50, 100];
  function boardOpts(parts, sorts, defs, ids) {
    var o = { div: defs.div || "", sort: defs.sort, min: defs.min, page: 1, all: false };
    (parts || []).forEach(function (t) {
      if (ids && ids.indexOf(t) >= 0) o.div = t;
      else if (/^s-/.test(t) && sorts.some(function (x) { return x[0] === t.slice(2); })) o.sort = t.slice(2);
      else if (/^m-\d+$/.test(t) && MIN_OPTS.indexOf(+t.slice(2)) >= 0) o.min = +t.slice(2);
      else if (t === "all") o.all = true;
      else if (/^p\d+$/.test(t)) o.page = Math.max(1, +t.slice(1));
    });
    return o;
  }
  function boardHash(base, o, over, defs) {
    var x = {}, k;
    for (k in o) x[k] = o[k];
    for (k in over || {}) x[k] = over[k];
    var p = [base];
    if (x.div) p.push(x.div);
    if (x.sort !== defs.sort) p.push("s-" + x.sort);
    if (x.min !== defs.min) p.push("m-" + x.min);
    if (x.all) p.push("all"); else if (x.page > 1) p.push("p" + x.page);
    return p.join("/");
  }
  function boardSort(list, key, tie) {
    return list.slice().sort(function (a, b) {
      var d = num(b[key]) - num(a[key]);
      for (var i = 0; !d && i < tie.length; i++) d = num(b[tie[i]]) - num(a[tie[i]]);
      return d || fold(a.nick || a.name).localeCompare(fold(b.nick || b.name));
    });
  }
  function boardTh(base, o, defs, key, label, cls, tip) {
    var on = o.sort === key;
    return '<th class="' + cls + (on ? " sorted" : "") + '"' + (on ? ' aria-sort="descending"' : "") + (tip ? ' title="' + esc(tip) + '"' : "") + '><a class="sortl" href="#' + esc(boardHash(base, o, { sort: key, page: 1 }, defs)) + '">' + label + (on ? ' <span aria-hidden="true">&#9662;</span>' : "") + "</a></th>";
  }
  function boardFrame(base, o, defs, sorts, total, rowsFn, extraSegs) {
    var pages = Math.max(1, Math.ceil(total / PER_PAGE)), pg = Math.min(o.page, pages), shown = o.all ? null : pg;
    var segs = (extraSegs ? '<div class="segs">' + extraSegs + "</div>" : "") + '<div class="segs segs2">' +
      seg("Sort", sorts.map(function (x) { return [x[1], boardHash(base, o, { sort: x[0], page: 1 }, defs), o.sort === x[0]]; })) +
      seg("Min. rounds", MIN_OPTS.map(function (m) { return [String(m), boardHash(base, o, { min: m, page: 1 }, defs), o.min === m]; })) + "</div>";
    var pbase = boardHash(base, o, { page: 1, all: false }, defs);
    var nav = o.all ? '<nav class="pager" aria-label="Pages"><span class="info">showing all ' + total + '</span><a href="#' + esc(pbase) + '">25 per page</a></nav>'
      : (total > PER_PAGE ? boardPager(total, pg, pbase).replace("</nav>", '<a href="#' + esc(boardHash(base, o, { all: true }, defs)) + '">show all ' + total + "</a></nav>") : "");
    return segs + nav + rowsFn(o.all ? 0 : (pg - 1) * PER_PAGE, o.all ? total : PER_PAGE) + nav;
  }
  function boardPager(total, page, base) {   // compact: first, last and two either side of the current page
    var pages = Math.ceil(total / PER_PAGE), h = '<nav class="pager" aria-label="Pages"><span class="title">Pages:</span>', gap = false;
    if (page > 1) h += '<a href="#' + esc(base) + "/p" + (page - 1) + '">&laquo; Prev</a>';
    for (var i = 1; i <= pages; i++) {
      if (i === 1 || i === pages || Math.abs(i - page) <= 2) { gap = false; h += i === page ? '<span class="act" aria-current="page">' + i + "</span>" : '<a href="#' + esc(base) + (i > 1 ? "/p" + i : "") + '">' + i + "</a>"; }
      else if (!gap) { gap = true; h += '<span class="gap" aria-hidden="true">&hellip;</span>'; }
    }
    if (page < pages) h += '<a href="#' + esc(base) + "/p" + (page + 1) + '">Next &raquo;</a>';
    return h + '<span class="info">showing ' + ((page - 1) * PER_PAGE + 1) + "&ndash;" + Math.min(total, page * PER_PAGE) + " of " + total + "</span></nav>";
  }
  /* ---------- v6 ESB Team Ranking + ESB Rating 1.0 (rank.js from ranking.py at deploy; formulas on #cs2/methodology) ---------- */
  var RK_STATE = "";
  function rankX() { return window.ESB_RANK || null; }
  function loadRank() {
    if (RK_STATE || !CFG.rank) return;
    RK_STATE = "loading";
    var s = document.createElement("script");
    function done() { RK_STATE = rankX() ? "ok" : "fail"; RKIDX = null; if (/^#(cs2|team\/cs2|player\/cs2|match\/cs2|home)?/.test(curHash())) { KEEP_SCROLL = true; route(); } }
    s.src = "rank.js"; s.onload = done; s.onerror = done;
    document.body.appendChild(s);
  }
  var RKIDX = null;
  function teamRank(id) {
    var x = rankX(); if (!x) { loadRank(); return null; }
    if (!RKIDX) { RKIDX = {}; (x.teams || []).forEach(function (t) { RKIDX[t.id] = t; }); }
    return RKIDX[id] || null;
  }
  function esbRating(k, d, r, adr, hs, avg) {
    if (!avg || !(r > 0)) return null;
    var kpr = k / r, dpr = Math.max(d, 1) / r, kd = k / Math.max(d, 1);
    var v = 0.30 * kpr / avg.kpr + 0.25 * avg.dpr / dpr + 0.30 * adr / avg.adr + 0.10 * kd / avg.kd + 0.05 * (avg.hs ? hs / avg.hs : 1);
    return Math.round(v * 100) / 100;
  }
  function divAvg(region, division) { var x = rankX(); return x && x.avgs ? x.avgs[region + " " + division] : null; }
  function playerEsbr(p) {
    var x = rankX(); if (!x) { loadRank(); return null; }
    if (num(p.rounds) < (x.min_rounds || 20)) return null;
    return esbRating(num(p.kills), num(p.deaths), num(p.rounds), num(p.adr), num(p.hs), divAvg(p.region, p.division));
  }
  function rtCell(v) { return v == null ? '<span class="dim">&ndash;</span>' : '<span class="esbr' + (v >= 1.15 ? " hi" : v < 0.9 ? " lo" : "") + '">' + v.toFixed(2) + "</span>"; }
  function arrow(t) {
    if (!t.prev) return '<span class="arw new" title="newly ranked this week">new</span>';
    var d = t.prev - t.rank;
    return d > 0 ? '<span class="arw up" title="up ' + d + ' since last week">&#9650;' + d + "</span>" : d < 0 ? '<span class="arw dn" title="down ' + (-d) + ' since last week">&#9660;' + (-d) + "</span>" : '<span class="arw eq" title="no change">&ndash;</span>';
  }
  function vRanking(reg) {
    var x = rankX();
    reg = reg === "eu" ? "EU" : reg === "all" ? "all" : "NA";
    setCrumbs([["CS2", "cs2"], ["ESB Ranking"]]);
    var segs = '<div class="segs"><div class="seg"><span class="seg-l">Region</span>' + [["NA", "na"], ["EU", "eu"], ["All", "all"]].map(function (r) { return '<a href="#cs2/ranking/' + r[1] + '"' + ((reg === r[0] || (reg === "all" && r[1] === "all")) ? ' class="on"' : "") + ">" + r[0] + "</a>"; }).join("") + "</div></div>";
    if (!x) return segs + rankWait("The ranking is");
    var rows = (x.teams || []).filter(function (t) { return reg === "all" || t.region === reg; });
    var intro = '<div class="infobox">One Elo-style ranking across every ESEA division, updated with each site refresh; arrows compare with the ranking at the end of last week. Teams appear after 3 matches. <a href="#cs2/methodology">How it works</a></div>';
    if (!rows.length) return segs + intro + '<div class="empty">No team has played 3 matches yet this season, so nobody is ranked yet. The first ranking appears after round 3.</div>';
    return segs + intro + '<div class="rankbox"><table class="tbl esb-rank"><thead><tr><th class="first c">#</th><th class="c">+/-</th><th>Team</th><th class="hide-sm">Division</th><th class="n">Points</th><th class="n">W-L</th>' + (reg === "all" ? "" : '<th class="n hide-sm" title="rank across all regions">Overall</th>') + "</tr></thead><tbody>" +
      rows.slice(0, 200).map(function (t) {
        var r = reg === "all" ? t.rank : t.rank_region;
        return '<tr class="' + medal(r) + '">' + rk(r) + '<td class="c">' + arrow(t) + '</td><td class="team">' + ilink("team/cs2/" + encodeURIComponent(t.id), t.name) + '</td><td class="hide-sm dim">' + esc(t.region + " " + t.division) + '</td><td class="n"><b>' + Math.round(t.pts) + '</b></td><td class="n">' + t.w + "-" + t.l + "</td>" + (reg === "all" ? "" : '<td class="n hide-sm dim">#' + t.rank + "</td>") + "</tr>";
      }).join("") + "</tbody></table></div>" + '<div class="note">' + rows.length + " ranked teams" + (rows.length > 200 ? ", top 200 shown" : "") + " &middot; as of " + fmt(x.generated, "short") + ". Built only from FACEIT results tracked here.</div>";
  }
  function rankWait(what) { loadRank(); return CFG.rank && RK_STATE !== "fail" ? '<div class="empty loading">Loading&hellip;</div>' : '<div class="empty">' + what + " not available on this copy of the site.</div>"; }
  function vTop20() {
    var x = rankX();
    setCrumbs([["CS2", "cs2"], ["Top 20 players"]]);
    if (!x) return rankWait("The Top 20 is");
    var t = x.top20 || [];
    var intro = '<div class="infobox">Season Top 20 across all ESEA divisions by ESB Rating 1.0 with a division-strength factor (Advanced &times;' + x.div_factor.Advanced.toFixed(2) + ", Main &times;" + x.div_factor.Main.toFixed(2) + ", Intermediate &times;" + x.div_factor.Intermediate.toFixed(2) + '), at least 60 rounds. <a href="#cs2/methodology">Methodology</a></div>';
    if (!t.length) return intro + '<div class="empty">No player has 60 rounds yet this season.</div>';
    return intro + '<div class="rankbox"><table class="tbl top20"><thead><tr><th class="first c">#</th><th>Player</th><th class="hide-sm">Team</th><th>Division</th><th class="n">Rating</th><th class="n" title="rating x division factor">Adjusted</th><th class="n hide-sm">Rounds</th></tr></thead><tbody>' +
      t.map(function (p, i) { return '<tr class="' + medal(i + 1) + '">' + rk(i + 1) + '<td class="team">' + ilink(playerHash(p.nick), p.nick) + '</td><td class="hide-sm">' + (p.team_id && p.team ? ilink("team/cs2/" + encodeURIComponent(p.team_id), p.team) : esc(p.team || "")) + "</td><td>" + esc(p.region + " " + p.division) + '</td><td class="n">' + rtCell(p.rating) + '</td><td class="n"><b>' + p.adj.toFixed(2) + '</b></td><td class="n hide-sm">' + p.rounds + "</td></tr>"; }).join("") + "</tbody></table></div>" +
      (t.length < 20 ? '<div class="note">Only ' + t.length + " players have 60+ rounds so far.</div>" : "");
  }
  function seasonNote(x) {
    var end = x.season && x.season.end ? new Date(x.season.end) : null, over = end && Date.now() > end.getTime();
    return '<div class="infobox">' + (over ? "Season finished " + fmt(x.season.end, "short") + "." : "<b>Season in progress</b>, standings as of " + fmt(x.generated, "short") + (end ? "; the regular season ends " + fmt(x.season.end, "md") + "." : ".")) + ' Awards follow the published formulas (<a href="#cs2/methodology">methodology</a>).</div>';
  }
  function vAwards() {
    var x = rankX();
    setCrumbs([["CS2", "cs2"], ["Season awards"]]);
    if (!x) return rankWait("Awards are");
    var a = x.awards || {}, m = a.mvp, b = a.best_team, k = a.breakout;
    function row(label, html, why) { return "<tr><th>" + label + "</th><td>" + (html || '<span class="dim">no eligible pick yet</span>') + '</td><td class="hide-sm dim">' + why + "</td></tr>"; }
    var tl = function (t) { return ilink("team/cs2/" + encodeURIComponent(t.id), t.name) + " (" + esc(t.region + " " + t.division) + ")"; };
    return seasonNote(x) + '<div class="rankbox"><table class="tbl awards"><tbody>' +
      row("MVP", m && ilink(playerHash(m.nick), m.nick) + " (" + esc(m.region + " " + m.division) + ") &middot; adjusted rating <b>" + m.adj.toFixed(2) + "</b>", "#1 of the Top 20 below") +
      row("Best team", b && tl(b) + " &middot; " + Math.round(b.pts) + " pts", "#1 in the ESB Ranking") +
      row("Breakout team", k && tl(k) + " &middot; +" + k.gain.toFixed(1) + " pts above its division start", "largest gain over its division starting value") +
      "</tbody></table></div>" + '<div class="note">Not awarded: ' + esc((a.omitted || []).join(" ")) + "</div>" + '<h2 class="subhead">All-division Top 20</h2>' + vTop20().replace(/^[\s\S]*?<\/div>/, "") + (setCrumbs([["CS2", "cs2"], ["Season awards"]]), "");
  }
  function vPlayoffs() {
    var x = rankX();
    setCrumbs([["CS2", "cs2"], ["Playoffs"]]);
    if (!x) return rankWait("Playoff pages are");
    var po = x.playoffs || {}, ms = po.matches || [];
    var links = '<ul class="po-links">' + (po.links || []).map(function (d) { return "<li>" + ext(d.link, "ESEA " + d.region + " " + d.division + " on FACEIT") + "</li>"; }).join("") + "</ul>";
    if (!ms.length) return '<div class="infobox"><b>Playoffs have not started.</b> ESEA playoffs follow the regular season' + (x.season && x.season.end ? ", which ends " + fmt(x.season.end, "md") : "") + ". FACEIT has not published playoff brackets in the data this site fetches, so there is no bracket here yet. It will appear automatically once FACEIT lists playoff matches. Follow the divisions on FACEIT:</div>" + links;
    var groups = {};
    ms.forEach(function (m) { var k = m.region + " " + m.division; (groups[k] = groups[k] || {})[m.round || 0] = (groups[k][m.round || 0] || []).concat([m]); });
    var mvp = po.mvp;
    return (mvp ? '<div class="infobox">Event MVP so far: <b>' + ilink(playerHash(mvp.nick), mvp.nick) + "</b> (" + esc(mvp.team) + ") &middot; rating " + Number(mvp.rating).toFixed(2) + " over " + num(mvp.maps) + " maps</div>" : "") +
      Object.keys(groups).sort().map(function (g) {
        return '<h2 class="subhead">' + esc(g) + ' playoffs</h2><div class="bracket">' + Object.keys(groups[g]).sort(function (a, b) { return a - b; }).map(function (r) {
          return '<div class="bcol"><div class="bhead">Round ' + esc(r) + "</div>" + groups[g][r].map(function (m) {
            var w = m.winner;
            return '<div class="bm"><div class="' + (w === 1 ? "w" : "") + '">' + esc(m.t1 ? m.t1.name : "TBD") + "<b>" + (m.s1 != null ? num(m.s1) : "") + '</b></div><div class="' + (w === 2 ? "w" : "") + '">' + esc(m.t2 ? m.t2.name : "TBD") + "<b>" + (m.s2 != null ? num(m.s2) : "") + "</b></div></div>";
          }).join("") + "</div>";
        }).join("") + "</div>";
      }).join("") + links;
  }
  function vMethod() {
    var x = rankX();
    setCrumbs([["CS2", "cs2"], ["Methodology"]]);
    if (!x) return rankWait("The methodology is");
    var ft = x ? x.formula_team : "", fp = x ? x.formula_player : "";
    return '<div class="infobox method"><h3>ESB Team Ranking</h3><p>' + esc(ft || "Loading…") + '</p><p>Map scores come from FACEIT; a Bo1 without map stats counts as one map from the series score; a series without map stats counts as one game without a margin bonus. NA and EU teams never meet, so their relative order comes only from the division starting values. Arrows compare with the ranking replayed up to the start of this week (Monday 00:00 PT); finished weeks are archived in the repo (rankings/).</p>' +
      "<h3>ESB Rating 1.0</h3><p>" + esc(fp) + "</p><p>KPR = kills per round, DPR = deaths per round, ADR = average damage per round, HS% = headshot kill percentage, all as published by FACEIT. Win rate is not included: FACEIT gives team records, not per-player ones. A per-map rating on match scoreboards uses the same formula with that map&rsquo;s rounds. This is an Esports Scoreboard formula, not an official FACEIT or ESEA rating.</p>" +
      "<h3>Player and Team of the Week</h3><p>Player of the Week: highest rounds-weighted per-map rating over the week (Monday-Sunday PT), at least 2 maps with FACEIT scoreboards, multiplied by the division factor. Team of the Week: largest ranking-points gain over the week with at least 2 matches that week, among ranked teams.</p></div>";
  }
  var CS_SORTS = [["esbr", "Rating"], ["kd", "K/D"], ["adr", "ADR"], ["hs", "HS%"], ["kills", "Kills"], ["rounds", "Rounds"], ["matches", "Matches"]];
  function csBoard(parts) {
    var divs = csDivs(), ids = divs.map(divId);
    if (!ids.length) return '<div class="empty">Player stats coming soon.</div>';
    var defs = { div: ids[0], sort: "kd", min: 20 }, o = boardOpts(parts, CS_SORTS, defs, ids), base = "cs2/players";
    var cur = divs[ids.indexOf(o.div)], dn = cur.region + " " + cur.division;
    var regs = ["NA", "EU"].filter(function (rg) { return divs.some(function (d) { return d.region === rg; }); });
    var inReg = function (rg) { return divs.filter(function (d) { return d.region === rg; }); };
    var dsegs = seg("Region", regs.map(function (rg) {
      var same = inReg(rg).filter(function (d) { return d.division === cur.division; })[0] || inReg(rg)[0];
      return [rg, boardHash(base, o, { div: divId(same), page: 1 }, defs), rg === cur.region];
    })) + seg("Division", inReg(cur.region).map(function (d) {
      return [d.division, boardHash(base, o, { div: divId(d), page: 1 }, defs), d === cur, d.division === "Intermediate" ? "Int" : d.division === "Advanced" ? "Adv" : d.division];
    }));
    setCrumbs([["CS2", "cs2"], ["Top Players", "cs2/players"], [dn]]);
    loadTeams();
    if (!teamsX() && TX_STATE === "loading") return '<div class="segs">' + dsegs + '</div><div class="empty loading">Loading players&hellip;</div>';
    var seen = {}, all = allCsPlayers().filter(function (p) {
      var k = fold(p.nick); if (seen[k] || p.region !== cur.region || p.division !== cur.division) return false; seen[k] = 1; return true;
    });
    all.forEach(function (p) { p.esbr = playerEsbr(p); });
    var list = boardSort(all.filter(function (p) { return num(p.rounds) >= o.min && num(p.rounds) > 0; }), o.sort, ["kd", "adr", "rounds"]);
    var tName = {}; (cur.teams || []).forEach(function (t) { if (t.id) tName[t.id] = t.name; });
    var th = function (k, l, c, t) { return boardTh(base, o, defs, k, l, c, t); };
    var note = '<div class="note">' + list.length + " of " + all.length + " " + esc(dn) + " players with season stats" + (o.min ? " (at least " + o.min + " rounds)" : "") + ", sorted by " + esc(CS_SORTS.filter(function (x) { return x[0] === o.sort; })[0][1]) +
      ". Early-season samples are small. Colored K/D and ADR compare with " + esc(dn) + " players with " + MINR() + "+ rounds. Stats as published on FACEIT." + (TX_STATE === "fail" ? " Only the top players could be loaded right now." : "") + "</div>";
    if (!list.length) return '<div class="segs">' + dsegs + '</div><div class="empty">No ' + esc(dn) + " player has " + o.min + " rounds yet.</div>" + note;
    return boardFrame(base, o, defs, CS_SORTS, list.length, function (from, n) {
      return '<div class="rankbox"><table class="tbl board cs-board"><thead><tr><th class="first c">#</th><th>Player</th><th class="hide-sm">Team</th>' +
        th("matches", "Matches", "n hide-sm", "matches played") + th("rounds", "Rnds", "n hide-sm", "rounds played") + th("esbr", "Rating", "n", "ESB Rating 1.0 (division average = 1.00)") + th("kills", "K", "n hide-sm", "kills") + th("kd", "K/D", "n", "kills per death") + th("adr", "ADR", "n", "average damage per round") + th("hs", "HS%", "n hide-sm", "headshot kill percentage") +
        "</tr></thead><tbody>" + list.slice(from, from + n).map(function (p, i) {
          var r = from + i + 1, tn = p.team || tName[p.team_id];
          return '<tr class="' + medal(r) + '" data-k="' + esc("csp:" + p.nick) + '">' + rk(r) + '<td class="team">' + ilink(playerHash(p.nick), p.nick) + '</td><td class="hide-sm">' + (tn ? (p.team_id ? ilink("team/cs2/" + encodeURIComponent(p.team_id), tn) : esc(tn)) : '<span class="dim">&ndash;</span>') +
            '</td><td class="n hide-sm">' + num(p.matches) + '</td><td class="n hide-sm">' + num(p.rounds) + '</td><td class="n">' + rtCell(p.esbr) + '</td><td class="n hide-sm">' + num(p.kills) + '</td><td class="n">' + csPc(p, "kd") + '</td><td class="n">' + csPc(p, "adr") + '</td><td class="n hide-sm">' + Math.round(num(p.hs)) + "%</td></tr>";
        }).join("") + "</tbody></table></div>";
    }, dsegs) + note;
  }
  var VAL_SORTS = [["rating", "Rating"], ["acs", "ACS"], ["kd", "K/D"], ["adr", "ADR"], ["hs", "HS%"], ["rnd", "Rounds"], ["maps", "Maps"]];
  function valBoard(parts) {
    var defs = { sort: "rating", min: 100 }, o = boardOpts(parts, VAL_SORTS, defs, null), base = "valorant/players";
    var tm = (D.valorant || {}).top_players_meta || {};
    loadVal();
    var x = valX();
    if (!x) return VX_STATE === "fail" ? '<div class="empty">Player stats could not be loaded right now.</div>' : '<div class="empty loading">Loading players&hellip;</div>';
    var list = boardSort(x.agg.filter(function (p) { return num(p.rnd) >= o.min && num(p.rnd) > 0; }), o.sort, ["rating", "acs", "rnd"]);
    var th = function (k, l, c, t) { return boardTh(base, o, defs, k, l, c, t); };
    var note = '<div class="note">' + list.length + " of " + x.agg.length + " players" + (o.min ? " with at least " + o.min + " rounds" : "") + " across the " + num(tm.events || valEvents().length) + " events Esports Scoreboard tracks (latest completed event per Challengers / Game Changers circuit), sorted by " +
      esc(VAL_SORTS.filter(function (s) { return s[0] === o.sort; })[0][1]) + "; per-event numbers are round-weighted. Colored ratings compare with players with 100+ rounds. Stats as published on vlr.gg.</div>";
    if (!list.length) return '<div class="empty">No player has ' + o.min + " rounds yet.</div>" + note;
    return staleNote(tm) + boardFrame(base, o, defs, VAL_SORTS, list.length, function (from, n) {
      return '<div class="rankbox"><table class="tbl val-pl board"><thead><tr><th class="first c">#</th><th>Player</th><th class="hide-sm">Team</th><th class="hide-sm agc">Agents</th>' +
        th("rnd", "Rnd", "n hide-sm", "rounds played") + th("rating", "R", "n", "vlr.gg rating") + th("acs", "ACS", "n", "average combat score") + th("kd", "K/D", "n", "kills per death") +
        '<th class="n hide-sm" title="kill / assist / trade / survive %">KAST</th>' + th("adr", "ADR", "n hide-sm", "average damage per round") + th("hs", "HS%", "n hide-sm", "headshot %") + "</tr></thead><tbody>" +
        list.slice(from, from + n).map(function (p, i) {
          var r = from + i + 1, tn = x.teams[p.team] && x.teams[p.team].name;
          return '<tr class="' + medal(r) + '">' + rk(r) + '<td class="team">' + ilink(valPHash(p.name), p.name) + (p.cc ? '<span class="cc">' + esc(p.cc) + "</span>" : "") + '</td><td class="hide-sm">' + (tn ? ilink(valHash(tn), tn) : p.tag ? '<span class="dim" title="team tag at the event">' + esc(p.tag) + "</span>" : '<span class="dim">&ndash;</span>') +
            '</td><td class="hide-sm dim agc">' + agentsCell(p.agents) + "</td>" + valStatCells(p) + "</tr>";
        }).join("") + "</tbody></table></div>";
    }) + note;
  }
  function streak(list) {
    if (!list.length) return "";
    var r = list[list.length - 1].r, n = 0;
    for (var i = list.length - 1; i >= 0 && list[i].r === r; i--) n++;
    return r + n;
  }
  function mapCell(m) {
    if (m.maps && m.maps.length) return ilink("match/cs2/" + encodeURIComponent(m.id), m.maps.map(function (x) { return x.map; }).join(", "));
    if (m.nostats) return '<span class="dim" title="no match stats on FACEIT (e.g. forfeit or technical result)">no stats</span>';
    return '<span class="dim" title="map and scoreboard coming soon">&ndash;</span>';
  }
  /* v4.4: score cells open Esports Scoreboard's match page; a small arrow keeps the source link (FACEIT room / vlr.gg) */
  function vlrId(u) { var m = String(u || "").match(/vlr\.gg\/(\d+)\//); return m ? m[1] : ""; }
  function scoreLink(hash, inner, extUrl, extTitle) {
    var x = extUrl && safeUrl(extUrl) !== "#" ? ' <a class="xl" href="' + esc(safeUrl(extUrl)) + '" target="_blank" rel="noopener" title="' + esc(extTitle) + '" aria-label="' + esc(extTitle) + '">&#8599;</a>' : "";
    return (hash ? '<a class="sc" href="#' + esc(hash) + '" title="match page">' + inner + "</a>" : inner) + x;
  }
  function csMatchHash(m) { return m && m.id && /^[0-9a-z-]+$/i.test(String(m.id)) ? "match/cs2/" + encodeURIComponent(m.id) : ""; }
  function valMatchHash(m) { var id = vlrId(m && m.url); return id ? "match/val/" + id : ""; }
  // winner normalized to 1 (team 1) / 2 (team 2) / 0 for both games: CS stores 1/2, vlr.gg results 0/1
  function win12(m, g) { return g === "val" ? (m.winner === 0 ? 1 : m.winner === 1 ? 2 : 0) : (m.winner === 1 || m.winner === 2 ? m.winner : 0); }
  function csEmpty(what) {
    var s = csMatchSrc();
    if (!s || s.status === "MISS") return soon(/upcoming/.test(what) ? "Upcoming matches coming soon." : "Match results coming soon.");
    return '<div class="empty">No ' + what + " in the matches Esports Scoreboard tracks.</div>";
  }
  function csResultsTable(rows, opts) {
    opts = opts || {};
    if (!rows.length) return csEmpty(opts.what || "finished matches");
    var showDiv = !!opts.showDiv;
    return '<div class="rankbox"><table class="tbl res cs-res' + (opts.compact ? " compact" : "") + '"><colgroup>' + (opts.compact ? "" : '<col class="c-date hide-sm">') + '<col class="c-team"><col class="c-score"><col class="c-team"><col class="c-map' + (opts.compact ? " hide-sm" : "") + '">' + (showDiv ? '<col class="c-div hide-sm">' : "") + "</colgroup><thead><tr>" +
      (opts.compact ? "" : '<th class="first hide-sm" title="match finished, Pacific Time">Date</th>') + '<th class="n">Team 1</th><th class="c">Score</th><th>Team 2</th><th class="' + (opts.compact ? "hide-sm" : "") + '" title="map(s) - click for the scoreboard">Map</th>' + (showDiv ? '<th class="hide-sm">Division</th>' : "") + "</tr></thead><tbody>" +
      rows.map(function (m) {
        var w1 = m.winner === 1, w2 = m.winner === 2, ru = roomUrl(m);
        var sc = '<span class="' + (w1 ? "w" : "") + '">' + num(m.s1) + '</span>:<span class="' + (w2 ? "w" : "") + '">' + num(m.s2) + "</span>";
        return "<tr>" + (opts.compact ? "" : '<td class="hide-sm dim date" title="' + esc(m.t ? fmt(m.t) : "") + '">' + (m.t ? fmt(m.t, "md") : "?") + "</td>") +
          '<td class="n tm ' + (w1 ? "win" : "lose") + '">' + csSide(m.t1) + '</td><td class="score">' + scoreLink(csMatchHash(m), sc, ru, "match room on FACEIT") + "</td>" +
          '<td class="tm ' + (w2 ? "win" : "lose") + '">' + csSide(m.t2) + '</td><td class="' + (opts.compact ? "hide-sm" : "") + '">' + mapCell(m) + "</td>" +
          (showDiv ? '<td class="hide-sm div" title="' + esc(m.region + " " + m.division + (m.conf ? " - conference " + m.conf : "") + " - round " + m.round) + '">' + ilink("cs2/" + divOf(m), m.region + " " + m.division) + '<span class="cc">R' + num(m.round) + "</span></td>" : "") + "</tr>";
      }).join("") + "</tbody></table></div>";
  }
  function csUpcomingTable(rows, opts) {
    opts = opts || {};
    if (!rows.length) return csEmpty("upcoming matches");
    return '<div class="rankbox"><table class="tbl res cs-up"><colgroup><col class="c-when"><col class="c-team"><col class="c-score"><col class="c-team">' + (opts.showDiv ? '<col class="c-div hide-sm">' : '<col class="c-rd hide-sm">') + "</colgroup><thead><tr>" +
      '<th class="first" title="scheduled start, Pacific Time (as listed on FACEIT; may change)">Scheduled (PT)</th><th class="n">Team 1</th><th class="c"></th><th>Team 2</th><th class="hide-sm">' + (opts.showDiv ? "Division" : "Round") + "</th></tr></thead><tbody>" +
      rows.map(function (m) {
        var ru = roomUrl(m);
        return '<tr><td class="dim" title="' + esc(m.t ? fmt(m.t) : "") + '">' + (m.t ? fmt(m.t, "short").replace(/ [A-Z]{3,4}$/, "") : "TBD") + '</td><td class="n tm">' + csSide(m.t1) + '</td><td class="score">' + (ru ? '<a href="' + esc(safeUrl(ru)) + '" target="_blank" rel="noopener" title="match room on FACEIT">vs</a>' : "vs") +
          '</td><td class="tm">' + csSide(m.t2) + '</td><td class="hide-sm rd">' + (opts.showDiv ? ilink("cs2/" + divOf(m), m.region + " " + m.division) + '<span class="cc">R' + num(m.round) + "</span>" : "Round " + num(m.round) + (m.conf ? '<span class="cc">' + esc(m.conf) + "</span>" : "")) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }
  function csMatchNote() {
    var mm = csMeta();
    if (!mm) return "";
    return '<div class="note">Results from FACEIT' + (mm.fetched_at ? ", updated " + fmt(mm.fetched_at, "short") : "") +
      ". Dates in Pacific Time. Click a score for the match page (&#8599; = FACEIT match room). Byes are not listed.</div>";
  }
  /* v4.4 match pages: header, per-map scores (+ scoreboards when published), picked maps, both teams'
     last 5 and earlier meetings this season. Built only from tracked data; bans are never made up. */
  function lastFive(list, upto) {
    var l = upto ? list.filter(function (f) { return String(f.t || "") < String(upto); }) : list;
    return formHtml(l);
  }
  function meetingsHtml(rows, g, cur) {
    if (!rows.length) return '<div class="empty">No other meeting between these teams in the data Esports Scoreboard tracks this season.</div>';
    return '<div class="rankbox"><table class="tbl res meet"><colgroup><col class="c-date"><col class="c-team"><col class="c-score"><col class="c-team"></colgroup><thead><tr><th class="first">Date</th><th class="n">Team 1</th><th class="c">Score</th><th>Team 2</th></tr></thead><tbody>' +
      rows.map(function (m) {
        var w = win12(m, g), t = g === "val" ? m.ts : m.t;
        var sc = g === "val" ? '<span class="' + (w === 1 ? "w" : "") + '">' + esc(m.score1) + '</span>:<span class="' + (w === 2 ? "w" : "") + '">' + esc(m.score2) + "</span>" :
          '<span class="' + (w === 1 ? "w" : "") + '">' + num(m.s1) + '</span>:<span class="' + (w === 2 ? "w" : "") + '">' + num(m.s2) + "</span>";
        var a = g === "val" ? ilink(valHash(m.team1), m.team1) : csSide(m.t1), b = g === "val" ? ilink(valHash(m.team2), m.team2) : csSide(m.t2);
        return '<tr><td class="dim">' + (t ? fmt(t, "md") : "?") + '</td><td class="n tm ' + (w === 1 ? "win" : "lose") + '">' + a + '</td><td class="score">' +
          scoreLink(g === "val" ? valMatchHash(m) : csMatchHash(m), sc, g === "val" ? m.url : roomUrl(m), g === "val" ? "match page on vlr.gg" : "match room on FACEIT") + '</td><td class="tm ' + (w === 2 ? "win" : "lose") + '">' + b + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }
  function matchHead(t1, t2, s1, s2, w, sub) {
    return '<div class="mhead"><div class="mt mt1' + (w === 1 ? " won" : "") + '">' + t1 + '</div><div class="ms"><span class="' + (w === 1 ? "w" : "") + '">' + s1 + '</span><span class="dash">:</span><span class="' + (w === 2 ? "w" : "") + '">' + s2 + "</span>" +
      (sub ? '<div class="msub">' + sub + "</div>" : "") + '</div><div class="mt mt2' + (w === 2 ? " won" : "") + '">' + t2 + "</div></div>";
  }
  function mapsTable(maps, n1, n2, g) {
    if (!maps.length) return "";
    return '<div class="rankbox"><table class="tbl maps-tbl"><thead><tr><th class="first">Map</th><th class="c">' + esc(n1) + '</th><th class="c">' + esc(n2) + '</th><th class="hide-sm">Pick</th></tr></thead><tbody>' +
      maps.map(function (x, i) {
        var w = num(x.s1) > num(x.s2) ? 1 : num(x.s2) > num(x.s1) ? 2 : 0;
        var pick = g === "val" ? (x.pick === 1 ? esc(n1) : x.pick === 2 ? esc(n2) : '<span class="dim">decider</span>') : '<span class="dim">&ndash;</span>';
        return "<tr><td>" + (maps.length > 1 ? '<span class="dim">' + (i + 1) + ".</span> " : "") + "<b>" + esc(x.map) + '</b></td><td class="c ' + (w === 1 ? "w" : "") + '">' + num(x.s1) + '</td><td class="c ' + (w === 2 ? "w" : "") + '">' + num(x.s2) + '</td><td class="hide-sm">' + pick + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }
  function findCsMatch(id) {
    var all = ((D.cs && D.cs.matches) || []).concat((teamsX() && teamsX().matches) || []);
    for (var i = 0; i < all.length; i++) if (all[i].id === id) return all[i];
    return null;
  }
  /* v5.9 pre-match preview for upcoming / live CS2 matches: this season's tracked maps only, no predictions */
  function findCsUpcoming(id) {
    var all = ((D.cs && D.cs.live) || []).concat(csUpcoming(), (teamsX() && teamsX().upcoming) || []);
    for (var i = 0; i < all.length; i++) if (all[i].id === id) return all[i];
    return null;
  }
  function csAllFinished() {
    var seen = {}, out = [];
    ((D.cs && D.cs.matches) || []).concat((teamsX() && teamsX().matches) || []).forEach(function (x) { if (x.id && !seen[x.id] && (x.winner === 1 || x.winner === 2)) { seen[x.id] = 1; out.push(x); } });
    return out;
  }
  function mapRecord(fin, id) {
    var rec = {};
    fin.forEach(function (x) {
      var side = x.t1 && x.t1.id === id ? 1 : x.t2 && x.t2.id === id ? 2 : 0;
      if (!side || isFF(x)) return;
      var list = (x.maps && x.maps.length) ? x.maps.map(function (mp) { return { map: mp.map, a: num(mp.s1), b: num(mp.s2) }; })
        : (num(x.bo) === 1 && x.pick && x.pick[0]) ? [{ map: x.pick[0], a: num(x.s1), b: num(x.s2) }] : [];
      list.forEach(function (mp) {
        if (!mp.map || mp.a === mp.b) return;
        var r = rec[mp.map] || (rec[mp.map] = { w: 0, n: 0, last: [] }), won = side === 1 ? mp.a > mp.b : mp.b > mp.a;
        r.n++; if (won) r.w++; r.last.push({ r: won ? "W" : "L", t: x.t });
      });
    });
    return rec;
  }
  function vPreviewCS(m) {
    var fin = csAllFinished(), a = m.t1 || {}, b = m.t2 || {}, ra = mapRecord(fin, a.id), rb = mapRecord(fin, b.id);
    var maps = Object.keys(ra).concat(Object.keys(rb)).filter(function (x, i, l) { return l.indexOf(x) === i; }).sort();
    function cell(r) {
      if (!r) return '<td class="n dim">&ndash;</td>';
      var pct = Math.round(100 * r.w / r.n), last = r.last.sort(function (p, q) { return String(p.t).localeCompare(String(q.t)); }).slice(-5).map(function (f) { return '<span class="fq ' + (f.r === "W" ? "w" : "l") + '">' + f.r + "</span>"; }).join("");
      return '<td class="n' + (r.n < 2 ? " dim small-n" : "") + '" title="' + r.w + " won of " + r.n + ' maps tracked this season">' + '<span class="wr-bar" style="width:' + pct + '%"></span>' + pct + "% <small>(" + r.w + "-" + (r.n - r.w) + ", n=" + r.n + ")</small> " + last + "</td>";
    }
    var mapTbl = maps.length ? '<div class="rankbox"><table class="tbl prev-maps"><thead><tr><th class="first">Map</th><th class="n">' + esc(a.name) + '</th><th class="n">' + esc(b.name) + "</th></tr></thead><tbody>" +
      maps.map(function (mp) { return "<tr><td>" + esc(mp) + "</td>" + cell(ra[mp]) + cell(rb[mp]) + "</tr>"; }).join("") + "</tbody></table></div>" : '<div class="empty">No maps tracked for these teams yet this season.</div>';
    function involves(x, id) { return (x.t1 && x.t1.id === id) || (x.t2 && x.t2.id === id); }
    var h2h = fin.filter(function (x) { return involves(x, a.id) && involves(x, b.id); }).sort(function (p, q) { return String(q.t).localeCompare(String(p.t)); });
    var oppA = {}, oppB = {};
    fin.forEach(function (x) { [[a.id, oppA], [b.id, oppB]].forEach(function (z) { if (involves(x, z[0])) { var o = x.t1.id === z[0] ? x.t2 : x.t1, won = (x.t1.id === z[0]) === (x.winner === 1); (z[1][o.id] = z[1][o.id] || { name: o.name, r: [] }).r.push(won ? "W" : "L"); } }); });
    var common = Object.keys(oppA).filter(function (k) { return oppB[k] && k !== a.id && k !== b.id; }).map(function (k) { return esc(oppA[k].name) + " (" + esc(a.name) + " " + oppA[k].r.join("") + ", " + esc(b.name) + " " + oppB[k].r.join("") + ")"; });
    var live = ((D.cs && D.cs.live) || []).some(function (x) { return x.id === m.id; }), ru = roomUrl(m);
    var info = kv([["When", m.t ? fmt(m.t) + " " + relSpan(live ? "live" : "up", m.t, "cs") : "TBD"], ["Division", esc(m.region + " " + m.division) + (m.conf ? " &middot; conference " + esc(m.conf) : "") + (m.round ? " &middot; round " + num(m.round) : "")],
      ["Format", "best of " + num(m.bo || 1)], ["Standing now", rankPre(a) + esc(a.name) + " &middot; " + rankPre(b) + esc(b.name)], ["Match room", ru ? ext(ru, live ? "Follow live on FACEIT" : "Match room on FACEIT") : ""]]);
    setCrumbs([["CS2", "cs2"], ["Matches Today", "cs2/today"], [a.name + " vs " + b.name]]);
    return std(esc(a.name) + " vs " + esc(b.name), (live ? '<span class="live-b">LIVE</span> ' : "") + "CS2 &middot; match preview", info) +
      '<h2 class="subhead">Map win rates this season <small>maps tracked here; n&lt;2 greyed</small></h2>' + mapTbl +
      '<h2 class="subhead">Form <small>last 5, newest right</small></h2>' + kv([[a.name, lastFive(csForm(a.id))], [b.name, lastFive(csForm(b.id))]]) +
      '<h2 class="subhead">Head to head this season</h2>' + meetingsHtml(h2h, "cs") +
      '<h2 class="subhead">Common opponents</h2>' + (common.length ? '<div class="spot-line">' + common.join(" &middot; ") + "</div>" : '<div class="empty">No common opponents yet this season.</div>') +
      '<div class="note">Built only from this season&rsquo;s results tracked here (small samples early in the season). No predictions. Times in Pacific Time.</div>';
  }
  function rankLine(id) {
    if (!CFG.rank) return "";
    try { id = decodeURIComponent(id); } catch (e) {}
    var t = teamRank(id);
    if (!rankX()) return "";
    return '<div class="infobox rank-line"><b>ESB Ranking:</b> ' + (t ? "#" + t.rank_region + " " + esc(t.region) + " / #" + t.rank + " overall &middot; " + Math.round(t.pts) + " points " + arrow(t) : "not ranked yet (needs 3 matches)") + ' &middot; <a href="#cs2/ranking/' + (t && t.region === "EU" ? "eu" : "na") + '">full ranking</a></div>';
  }
  function ratingLine(nick) {
    if (!CFG.rank) return "";
    try { nick = decodeURIComponent(nick); } catch (e) {}
    var x = rankX(); if (!x) { loadRank(); return ""; }
    var ps = allCsPlayers().filter(function (p) { return fold(p.nick) === fold(nick); });
    if (!ps.length) return "";
    var p = ps.sort(function (a, b) { return num(b.rounds) - num(a.rounds); })[0], v = playerEsbr(p);
    return '<div class="infobox rank-line"><b>ESB Rating 1.0:</b> ' + (v == null ? "needs " + (x.min_rounds || 20) + " rounds" : rtCell(v) + " (" + esc(p.region + " " + p.division) + " average = 1.00, " + num(p.rounds) + " rounds)") + ' &middot; <a href="#cs2/methodology">formula</a></div>';
  }
  function vMatchCS(id) {
    var m = findCsMatch(id);
    if (!m && TX_STATE !== "ok" && TX_STATE !== "fail") { loadTeams(); if (TX_STATE === "loading") return std("Match", "CS2 &middot; ESEA match", '<div class="empty loading">Loading match&hellip;</div>'); m = findCsMatch(id); }
    if (!m) { var um = findCsUpcoming(id); if (um) return vPreviewCS(um); }
    if (!m) return notFound("Match not tracked", "No finished ESEA match with this id in Esports Scoreboard's data.", '<a href="#cs2/results">ESEA results</a>');
    loadTeams();
    var ru = roomUrl(m), w = win12(m, "cs"), maps = m.maps || [];
    var pick = (m.pick || []).filter(Boolean);
    var info = kv([
      ["Division", ilink("cs2/" + divOf(m), m.region + " " + m.division) + (m.conf ? " &middot; conference " + esc(m.conf) : "") + " &middot; round " + num(m.round) + " &middot; best of " + num(m.bo || 1)],
      ["Finished", m.t ? fmt(m.t) : "?"],
      ["Result", csSide(m.t1) + ' <b><span class="' + (w === 1 ? "w" : "") + '">' + num(m.s1) + '</span>:<span class="' + (w === 2 ? "w" : "") + '">' + num(m.s2) + "</span></b> " + csSide(m.t2) + (isFF(m) ? ' <span class="dim">(forfeit / technical result)</span>' : "")],
      ["Map veto", pick.length ? "Picked: <b>" + pick.map(esc).join(", ") + '</b> <span class="dim">(FACEIT lists the chosen map' + (pick.length > 1 ? "s" : "") + " only)</span>" : '<span class="dim">not published for this match</span>'],
      ["FACEIT", ru ? ext(ru, "Match room on FACEIT") : "-"]
    ]);
    var mAvg = CFG.rank ? (rankX() ? divAvg(m.region, m.division) : (loadRank(), null)) : null;
    function board(lines, side, mr) {
      return '<div class="rankbox"><table class="tbl sb"><thead><tr><th class="first">' + esc(side.name) + '</th>' + (mAvg ? '<th class="n" title="ESB Rating 1.0 on this map (division average = 1.00)">Rtg</th>' : "") + '<th class="n" title="kills">K</th><th class="n" title="deaths">D</th><th class="n" title="kills per death">K/D</th><th class="n" title="average damage per round">ADR</th><th class="n hide-sm" title="headshot kill percentage">HS%</th></tr></thead><tbody>' +
        (lines || []).map(function (p) {
          var kd = num(p[2]) ? num(p[1]) / num(p[2]) : num(p[1]);
          return '<tr><td class="team">' + ilink(playerHash(p[0]), p[0]) + "</td>" + (mAvg ? '<td class="n">' + rtCell(mr >= 13 ? esbRating(num(p[1]), num(p[2]), mr, num(p[3]), num(p[4]), mAvg) : null) + "</td>" : "") + '<td class="n">' + num(p[1]) + '</td><td class="n">' + num(p[2]) + '</td><td class="n"><b>' + kd.toFixed(2) + '</b></td><td class="n">' + num(p[3]).toFixed(1) + '</td><td class="n hide-sm">' + num(p[4]) + "%</td></tr>";
        }).join("") + "</tbody></table></div>";
    }
    var boards = maps.map(function (x, i) {
      return '<h2 class="subhead">' + (maps.length > 1 ? "Map " + (i + 1) + ": " : "") + esc(x.map) + " <small>" + num(x.s1) + ":" + num(x.s2) + "</small></h2>" + board(x.p1, m.t1, num(x.s1) + num(x.s2)) + board(x.p2, m.t2, num(x.s1) + num(x.s2));
    }).join("");
    var other = {}, prior = [];
    ((D.cs && D.cs.matches) || []).concat((teamsX() && teamsX().matches) || []).forEach(function (x) {
      if (!x.id || other[x.id] || x.id === m.id) return; other[x.id] = 1;
      if (involves(x, m.t1.id) && involves(x, m.t2.id)) prior.push(x);
    });
    prior.sort(function (a, b) { return String(b.t || "").localeCompare(String(a.t || "")); });
    var form = kv([[m.t1.name, lastFive(csForm(m.t1.id), m.t)], [m.t2.name, lastFive(csForm(m.t2.id), m.t)]]);
    setCrumbs([["CS2", "cs2"], ["Results", "cs2/results"], [m.t1.name + " vs " + m.t2.name]]);
    return std(esc(m.t1.name) + " vs " + esc(m.t2.name), "CS2 &middot; ESEA match", matchHead(csSide(m.t1), csSide(m.t2), num(m.s1), num(m.s2), w, "best of " + num(m.bo || 1)) + info) +
      (maps.length > 1 || maps.length && pick.length ? '<h2 class="subhead">Maps</h2>' + mapsTable(maps, m.t1.name, m.t2.name, "cs") : "") +
      (boards || '<div class="empty">' + (m.nostats ? "FACEIT published no match stats for this match (e.g. forfeit or technical result)." : "Scoreboard not available for this match yet (Esports Scoreboard adds stats for the newest matches on each refresh).") + "</div>") +
      '<h2 class="subhead">Form before this match <small>last 5, newest right</small></h2>' + form +
      '<h2 class="subhead">Meetings this season</h2>' + meetingsHtml(prior, "cs") +
      '<div class="note">Scoreboard from the official FACEIT Data API; stats as published by FACEIT. Times in Pacific Time.</div>';
  }
  function vMatchVal(id) {
    var m = null;
    valResults().forEach(function (x) { if (!m && vlrId(x.url) === id) m = x; });
    if (!m) return notFound("Match not tracked", "No Valorant result with this id in Esports Scoreboard's data (Esports Scoreboard keeps the latest tier-2 / Game Changers results).", '<a href="#valorant/results">Valorant results</a>');
    loadVal();
    var vx = window.FRAGNET_VAL, det = vx && vx.matches && vx.matches[id], w = win12(m, "val");
    var detail;
    if (!vx && VX_STATE !== "fail") detail = '<div class="empty loading">Loading map details&hellip;</div>';
    else if (!det) detail = '<div class="empty">Map details not fetched yet (Esports Scoreboard reads a few vlr.gg match pages per refresh). ' + ext(m.url, "Full match page on vlr.gg") + "</div>";
    else detail = (det.veto ? '<div class="infobox veto"><b>Map veto</b> <span class="dim">(as listed on vlr.gg)</span><br>' + esc(det.veto) + "</div>" : "") +
      (det.maps && det.maps.length ? mapsTable(det.maps, m.team1, m.team2, "val") : '<div class="empty">No map scores on the vlr.gg match page.</div>') +
      '<div class="note">Player scoreboards: ' + ext(m.url, "match page on vlr.gg") + (det.fetched_at ? " &middot; read " + fmt(det.fetched_at, "short") : "") + ".</div>";
    var info = kv([
      ["Event", esc(m.event) + (m.series ? ' <span class="dim">&middot; ' + esc(m.series) + "</span>" : "")],
      ["Date", m.ts ? fmt(m.ts) : esc(m.date || "?")],
      ["Result", ilink(valHash(m.team1), m.team1) + ' <b><span class="' + (w === 1 ? "w" : "") + '">' + esc(m.score1) + '</span>:<span class="' + (w === 2 ? "w" : "") + '">' + esc(m.score2) + "</span></b> " + ilink(valHash(m.team2), m.team2)],
      ["vlr.gg", ext(m.url, "Match page on vlr.gg")]
    ]);
    var prior = valResults().filter(function (x) { return x !== m && ((slug(x.team1) === slug(m.team1) && slug(x.team2) === slug(m.team2)) || (slug(x.team1) === slug(m.team2) && slug(x.team2) === slug(m.team1))); });
    var form = kv([[m.team1, lastFive(valForm(m.team1), m.ts)], [m.team2, lastFive(valForm(m.team2), m.ts)]]);
    setCrumbs([["Valorant", "valorant"], ["Results", "valorant/results"], [m.team1 + " vs " + m.team2]]);
    return std(esc(m.team1) + " vs " + esc(m.team2), "Valorant &middot; match", matchHead(ilink(valHash(m.team1), m.team1), ilink(valHash(m.team2), m.team2), esc(m.score1), esc(m.score2), w, esc(shortEv(m.event))) + info) +
      '<h2 class="subhead">Maps</h2>' + detail +
      '<h2 class="subhead">Form before this match <small>last 5, newest right</small></h2>' + form +
      '<h2 class="subhead">Meetings this season</h2>' + meetingsHtml(prior, "val") +
      '<div class="note">Results as listed on vlr.gg; dates in Pacific Time.</div>';
  }
  function teamMatchesHtml(id) {
    var seen = {};
    function uniq(m) { if (seen[m.id]) return false; seen[m.id] = 1; return true; }
    var fin = csFinished().filter(function (m) { return involves(m, id); }).concat(xMatches("matches", id)).filter(uniq)
      .sort(function (a, b) { return String(b.t || "").localeCompare(String(a.t || "")); });
    var up = csUpcoming().filter(function (m) { return involves(m, id); }).concat(xMatches("upcoming", id)).filter(uniq)
      .sort(function (a, b) { return String(a.t || "").localeCompare(String(b.t || "")); });
    return '<h2 class="subhead">Recent Results</h2>' + csResultsTable(fin, { what: "finished matches for this team" }) +
      '<h2 class="subhead">Upcoming Matches</h2>' + csUpcomingTable(up) + csMatchNote();
  }
  function playerMatchesHtml(nick) {
    var n = String(nick || "").toLowerCase(), rows = [];
    csFinished().forEach(function (m) {
      (m.maps || []).forEach(function (x) {
        [["p1", m.t1, m.t2], ["p2", m.t2, m.t1]].forEach(function (s) {
          (x[s[0]] || []).forEach(function (p) { if (String(p[0]).toLowerCase() === n) rows.push({ m: m, x: x, p: p, me: s[1], vs: s[2], won: (s[0] === "p1" ? x.s1 > x.s2 : x.s2 > x.s1) }); });
        });
      });
    });
    if (!rows.length) return "";
    return '<h2 class="subhead">Recent Matches</h2><div class="rankbox"><table class="tbl"><thead><tr><th class="first hide-sm">Date</th><th>Opponent</th><th>Map</th><th class="c">Score</th><th class="n">K-D</th><th class="n">ADR</th></tr></thead><tbody>' +
      rows.slice(0, 10).map(function (r) {
        return '<tr><td class="hide-sm dim">' + (r.m.t ? fmt(r.m.t, "md") : "?") + '</td><td class="team">' + csSide(r.vs) + "</td><td>" + ilink("match/cs2/" + encodeURIComponent(r.m.id), r.x.map) + '</td><td class="c ' + (r.won ? "w" : "l") + '">' + (r.won ? "W " : "L ") +
          (r.me === r.m.t1 ? num(r.x.s1) + ":" + num(r.x.s2) : num(r.x.s2) + ":" + num(r.x.s1)) + '</td><td class="n">' + num(r.p[1]) + "-" + num(r.p[2]) + '</td><td class="n">' + num(r.p[3]).toFixed(1) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }
  function resDate(m, withTime) { return m.ts ? fmt(m.ts, withTime ? "short" : "md") : esc(String(m.date || "").replace(/^\w+, /, "").replace(/, \d{4}$/, "").replace(/^(\w{3})\w*/, "$1")); }

  /* ---------- search index ---------- */
  function buildIndex() {
    IDX = [];
    csDivs().forEach(function (d) {
      (d.teams || []).forEach(function (t) {
        IDX.push({ g: "CS2 teams (ESEA)", label: t.name + (t.tag ? " [" + t.tag + "]" : ""), where: d.region + " " + d.division + " #" + t.rank,
          hash: teamHash(t) || "cs2/" + divId(d), key: teamHash(t) ? "" : "cs:" + divId(d) + ":" + t.name, ext: t.url, text: [t.name, t.tag, t.country, countryName(t.country)].join(" ") });
      });
    });
    var seenP = {};
    csPlayers().forEach(function (p) {
      seenP[String(p.nick).toLowerCase()] = 1;
      IDX.push({ g: "CS2 players", label: p.nick, where: (p.team ? p.team + " · " : "") + p.region + " " + p.division + " K/D " + num(p.kd).toFixed(2), hash: playerHash(p.nick), key: "", ext: p.url, text: p.nick + " " + (p.team || "") });
    });
    csDivs().forEach(function (d) {
      (d.teams || []).forEach(function (t) {
        (t.roster || []).forEach(function (m) {
          if (seenP[String(m.nick).toLowerCase()]) return;
          seenP[String(m.nick).toLowerCase()] = 1;
          IDX.push({ g: "CS2 players", label: m.nick, where: t.name + " · " + d.region + " " + d.division, hash: playerHash(m.nick), key: "", ext: "", text: m.nick + " " + t.name });
        });
      });
    });
    valResults().forEach(function (m, i) {
      var pg = Math.floor(i / PER_PAGE) + 1;
      IDX.push({ g: "Valorant results", label: m.team1 + " " + m.score1 + ":" + m.score2 + " " + m.team2, where: shortEv(m.event), hash: "valorant/results" + (pg > 1 ? "/p" + pg : ""), key: "vr:" + i, ext: m.url, text: [m.team1, m.team2, m.event].join(" ") });
    });
    var seenV = {};
    valEvents().forEach(function (e, i) {
      (e.standings || []).forEach(function (t) {
        var sl = slug(t.team); if (!sl || seenV[sl]) return; seenV[sl] = 1;
        IDX.push({ g: "Valorant teams", label: t.team, where: shortEv(e.title) + " " + t.place, hash: valHash(t.team), key: "", ext: t.url, text: [t.team, t.country, e.title].join(" ") });
      });
    });
    valResults().forEach(function (m) {
      [m.team1, m.team2].forEach(function (n) {
        var sl = slug(n); if (!sl || seenV[sl]) return; seenV[sl] = 1;
        IDX.push({ g: "Valorant teams", label: n, where: shortEv(m.event), hash: valHash(n), key: "", ext: "", text: n });
      });
    });
    ((D.valorant && D.valorant.event_list) || []).forEach(function (e, i) {
      IDX.push({ g: "Valorant events", label: e.title, where: e.status + " " + e.dates, hash: "valorant/calendar", key: "vc:" + i, ext: e.url, text: e.title });
    });
    ((D.valorant && D.valorant.top_players) || []).forEach(function (p) {
      IDX.push({ g: "Valorant players", label: p.name, where: (p.team_name ? p.team_name + " · " : "") + "rating " + num(p.rating).toFixed(2), hash: valPHash(p.name), key: "", ext: "", text: p.name + " " + (p.team_name || "") });
    });
    var rks = (D.wow && D.wow.rankings) || {};
    Object.keys(rks).forEach(function (rg) {
      (rks[rg] || []).forEach(function (g, i) {
        var pg = Math.floor(i / PER_PAGE) + 1;
        IDX.push({ g: "WoW guilds", label: g.guild + " - " + g.realm, where: rg.toUpperCase() + " #" + g.rank + " " + g.progress, hash: guildHash(rg, g), key: "", ext: g.url, text: [g.guild, g.realm].join(" ") });
      });
    });
    newsItems().forEach(function (n, i) {
      var pg = Math.floor(i / PER_PAGE) + 1;
      IDX.push({ g: "News", label: n.title, where: n.source + " " + fmt(n.date, "md"), hash: "news/all" + (pg > 1 ? "/p" + pg : ""), key: "n:" + i, ext: n.url, text: [n.title, n.source].join(" ") });
    });
  }

  var LZ = null;
  function lazyIdx() { // players/teams that only live in the lazy teams.js / val.js files
    var tx = window.FRAGNET_TEAMS || null, vx = valX();
    if (LZ && LZ.tx === tx && LZ.vx === vx) return LZ.list;
    var seen = {}, list = [];
    IDX.forEach(function (x) { seen[x.hash] = 1; });
    function add(o) { if (seen[o.hash]) return; seen[o.hash] = 1; list.push(o); }
    xPlayers().forEach(function (p) { add({ g: "CS2 players", label: p.nick, where: (p.team ? p.team + " · " : "") + p.region + " " + p.division + (num(p.rounds) ? " K/D " + num(p.kd).toFixed(2) : ""), hash: playerHash(p.nick), key: "", ext: "", text: p.nick + " " + (p.team || "") }); });
    if (tx && tx.rosters) {
      var tName = {}; csDivs().forEach(function (d) { (d.teams || []).forEach(function (t) { tName[csTeamId(t)] = t.name; }); });
      Object.keys(tx.rosters).forEach(function (id) { (tx.rosters[id].r || []).forEach(function (m) { add({ g: "CS2 players", label: m[0], where: tName[id] || "ESEA roster", hash: playerHash(m[0]), key: "", ext: "", text: m[0] + " " + (tName[id] || "") }); }); });
    }
    if (vx) {
      vx.agg.forEach(function (p) { var t = p.team && vx.teams[p.team]; add({ g: "Valorant players", label: p.name, where: (t ? t.name + " · " : "") + "rating " + num(p.rating).toFixed(2), hash: valPHash(p.name), key: "", ext: "", text: p.name + " " + (t ? t.name : "") }); });
      Object.keys(vx.teams).forEach(function (id) { var t = vx.teams[id]; (t.roster || []).forEach(function (m) { if (!/coach|manager|analyst/.test(m[2] || "")) add({ g: "Valorant players", label: m[0], where: t.name, hash: valPHash(m[0]), key: "", ext: "", text: m[0] + " " + t.name }); }); });
    }
    LZ = { tx: tx, vx: vx, list: list };
    return list;
  }

  /* ---------- v5.0 community: GitHub Discussions + giscus comments ----------
     window.ESB_CONFIG is written at deploy time (discussions.py): {repo, discussions, forum, giscus?, discord?}.
     Nothing third-party loads unless the owner switched it on there. The forum list (forum.js) is
     a build-time snapshot of the latest Discussions; posting happens on GitHub (free account). */
  var CFG = window.ESB_CONFIG || {}, FX_STATE = "";
  var DISC_URL = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/discussions$/.test(CFG.discussions || "") ? CFG.discussions : "https://github.com/winecoolermike/fragnet/discussions";
  function forumX() { return window.ESB_FORUM || null; }
  function loadForum() {
    if (FX_STATE || !CFG.forum) return;
    FX_STATE = "loading";
    var s = document.createElement("script");
    function done() { FX_STATE = forumX() ? "ok" : "fail"; try { renderSideForum(); } catch (e) {} if (/^#forums/.test(curHash())) { KEEP_SCROLL = true; route(); } }
    s.src = "forum.js"; s.onload = done; s.onerror = done;
    document.body.appendChild(s);
  }
  /* v5.2 spotlights + weekly roundups: spot.js is computed at deploy time by spotlight.py */
  var SP_STATE = "";
  function spotX() { return window.ESB_SPOT || null; }
  function loadSpot() {
    if (SP_STATE || !CFG.spot) return;
    SP_STATE = "loading";
    var s = document.createElement("script");
    function done() { SP_STATE = spotX() ? "ok" : "fail"; var h = curHash(); if (/^#(home|roundup)?(\/|$)/.test(h) || h === "" || h === "#") { KEEP_SCROLL = true; route(); } }
    s.src = "spot.js"; s.onload = done; s.onerror = done;
    document.body.appendChild(s);
  }
  function spotHtml(b) {
    var out = "", ups = b.upsets || [], fr = b.fraggers || [], st = b.streaks || [], w = b.wow || {};
    function tl(t) { return /^[0-9a-f-]{36}$/.test(String(t.id)) ? ilink("team/cs2/" + t.id, t.name) : esc(t.name); }
    out += '<h2 class="subhead">Upset of the week</h2>' + (ups.length ? ups.slice(0, 3).map(function (u) {
      return '<div class="spot-line">' + tl(u.winner) + " (#" + u.winner.rank + ") beat " + tl(u.loser) + " (#" + u.loser.rank + ") " + ilink(csMatchHash(u), u.score) + ' <span class="dim">' + esc(u.region + " " + u.division) + "</span></div>";
    }).join("") : '<div class="empty">No upset by this rule in this period.</div>');
    out += '<h2 class="subhead">Top fragger by division</h2>' + (fr.length ? '<div class="rankbox"><table class="tbl spot-fr"><thead><tr><th class="first">Division</th><th>Player</th><th class="n">Kills</th><th class="n">Maps</th></tr></thead><tbody>' + fr.map(function (f) {
      return "<tr><td>" + esc(f.div) + '</td><td class="team">' + ilink(playerHash(f.nick), f.nick) + ' <span class="dim">' + esc(f.team) + '</span></td><td class="n">' + (f.match ? ilink(csMatchHash({ id: f.match }), String(f.kills)) : num(f.kills)) + '</td><td class="n">' + num(f.maps) + "</td></tr>";
    }).join("") + "</tbody></table></div>" : '<div class="empty">No FACEIT scoreboards in this period.</div>');
    out += '<h2 class="subhead">Hottest streak</h2>' + (st.length ? st.slice(0, 3).map(function (x) {
      return '<div class="spot-line">' + tl(x) + ": " + x.n + ' wins in a row <span class="dim">' + esc(x.div) + "</span></div>";
    }).join("") : '<div class="empty">No team is on a 3+ win streak.</div>');
    out += '<h2 class="subhead">WoW Mythic kills</h2>' + ((w.guilds || []).length ? w.guilds.map(function (g) {
      var reg = g.region === "eu" ? "eu" : "us";
      return '<div class="spot-line">' + ilink(guildHash(reg, g), g.guild) + " (" + reg.toUpperCase() + "): " + g.kills + " kill" + (g.kills === 1 ? "" : "s") + " &middot; " + esc((g.bosses || []).join(", ")) + " " + ext(g.url, "Raider.IO") + "</div>";
    }).join("") : '<div class="empty">No Mythic kills by tracked guilds in this period.</div>');
    return out;
  }
  function homeSpot() {
    if (!CFG.spot) return "";
    var sp = spotX();
    if (!sp) { loadSpot(); return SP_STATE === "fail" ? "" : std("This Week", "", '<div class="empty loading-sp">Loading this week&hellip;</div>', "home-spot"); }
    var b = sp.last7 || {};
    return std("This Week", '<a href="#roundup">weekly roundups &raquo;</a>', '<div class="infobox spot-intro">Last 7 days: ' + num(b.cs_matches) + " CS2 results tracked, " + num((b.wow || {}).kills) + " WoW Mythic boss kills. " + esc(sp.upset_rule) + "</div>" + picksHtml((sp.weeks || []).filter(function (w) { return w.current; })[0], true) + spotHtml(b), "home-spot");
  }
  /* v6.2 Player / Team of the Week (computed in spotlight.py via ranking.py; archived with the roundup week) */
  function picksHtml(w, home) {
    if (!w || !("potw" in w)) return "";
    var p = w.potw, t = w.totw, out = '<div class="potw">';
    out += '<div class="pick"><h2 class="subhead">Player of the Week' + (home ? ' <small>(' + esc(w.label) + (w.current ? ", so far" : "") + ")</small>" : "") + "</h2>" + (p ? '<div class="spot-line"><b>' + ilink(playerHash(p.nick), p.nick) + "</b> (" + (/^[0-9a-f-]{36}$/.test(String(p.team_id)) ? ilink("team/cs2/" + p.team_id, p.team) : esc(p.team)) + ", " + esc(p.div) + ") &middot; rating <b>" + Number(p.rating).toFixed(2) + "</b> over " + num(p.maps) + " maps, " + num(p.k) + "-" + num(p.d) + " K-D</div>" + shareBox("roundup/" + w.id + "/potw") : '<div class="empty">No player has 2 maps with FACEIT scoreboards this week yet.</div>') + "</div>";
    out += '<div class="pick"><h2 class="subhead">Team of the Week</h2>' + (t ? '<div class="spot-line"><b>' + ilink("team/cs2/" + t.id, t.name) + "</b> (" + esc(t.region + " " + t.division) + ") &middot; <b>+" + Number(t.gain).toFixed(1) + "</b> ranking points from " + num(t.played) + " matches, now " + Math.round(t.pts) + "</div>" + shareBox("roundup/" + w.id + "/totw") : '<div class="empty">No ranked team has played 2 matches this week yet.</div>') + "</div>";
    return out + '<div class="note">Picks follow the published formula: <a href="#cs2/methodology">methodology</a>.</div></div>';
  }
  function vRoundup(parts) {
    setCrumbs(parts[0] ? [["Weekly Roundups", "roundup"], [parts[0].toUpperCase()]] : [["Weekly Roundups"]]);
    if (!CFG.spot) return std("Weekly Roundups", "", '<div class="empty">Weekly roundups are not available on this copy of the site.</div>');
    var sp = spotX();
    if (!sp) { loadSpot(); return SP_STATE === "fail" ? std("Weekly Roundups", "", '<div class="empty">Roundups could not be loaded.</div>') : std("Weekly Roundups", "", '<div class="empty loading">Loading&hellip;</div>'); }
    var weeks = sp.weeks || [];
    if (parts[0]) {
      var w = weeks.filter(function (x) { return x.id === parts[0]; })[0];
      if (!w) return std("Roundup not found", "", '<div class="empty miss">No roundup for that week. <a href="#roundup">All roundups</a></div>');
      var n = +w.id.slice(-2);
      return std("Weekly Roundup :: " + esc(w.label), "week " + n, picksHtml(w) + '<div class="infobox">Week ' + n + (w.current ? " (so far)" : "") + ": " + num(w.cs_matches) + " CS2 results tracked (" + num(w.cs_with_scoreboards) + " with scoreboards) and " + num((w.wow || {}).kills) + " WoW Mythic boss kills by tracked guilds. " + esc(sp.upset_rule) + "</div>" + spotHtml(w) + '<div class="crumbs"><a href="#roundup">All roundups</a></div>');
    }
    return std("Weekly Roundups", weeks.length + " weeks", weeks.length ? '<div class="rankbox"><table class="tbl"><thead><tr><th class="first">Week</th><th class="n">CS2 results</th><th class="n">WoW kills</th></tr></thead><tbody>' + weeks.map(function (w) {
      return '<tr><td class="team">' + ilink("roundup/" + w.id, w.label + (w.current ? " (so far)" : "")) + '</td><td class="n">' + num(w.cs_matches) + '</td><td class="n">' + num((w.wow || {}).kills) + "</td></tr>";
    }).join("") + '</tbody></table></div><div class="note">Roundups are built from the results this site still tracks; a week is listed once its results are fully covered.</div>' : '<div class="empty">No complete weeks tracked yet.</div>');
  }
  function safeGh(u) { return /^https:\/\/github\.com\//.test(String(u || "")) ? String(u) : DISC_URL; }
  function discordBox(where) {
    if (!CFG.discord || !/^https:\/\/(discord\.gg|discord\.com\/invite)\/[A-Za-z0-9-]{2,32}\/?$/.test(CFG.discord)) return "";
    return '<div class="infobox discord-box ' + where + '"><b>Join the Discord</b> &middot; chat with amateur and semi-pro players, find scrims and talk about this week&rsquo;s matches. ' + ext(CFG.discord, "Join the Esports Scoreboard Discord") + "</div>";
  }
  /* ---------- reusable blocks ---------- */
  function resultsTable(rows, offset, compact, noKeys) {
    if (!rows.length) return '<div class="empty">no results</div>';
    return '<div class="rankbox"><table class="tbl res' + (compact ? " compact" : "") + '"><colgroup>' + (compact ? "" : '<col class="c-date hide-sm">') + '<col class="c-team"><col class="c-score"><col class="c-team">' + (compact ? "" : '<col class="c-ev hide-sm">') + '</colgroup><thead><tr>' + (compact ? "" : '<th class="first hide-sm" title="match start, Pacific Time">Date</th>') + '<th class="n">Team 1</th><th class="c">Score</th><th>Team 2</th>' + (compact ? "" : '<th class="hide-sm">Event</th>') + "</tr></thead><tbody>" +
      rows.map(function (m, j) {
        var w1 = m.winner === 0, w2 = m.winner === 1;
        return "<tr" + (noKeys ? "" : ' data-k="vr:' + (offset + j) + '"') + ">" + (compact ? "" : '<td class="hide-sm dim" title="' + esc(m.ts ? fmt(m.ts) : (m.date + " " + m.time + " (US Central, as listed on vlr.gg)")) + '">' + resDate(m) + "</td>") +
          '<td class="n ' + (w1 ? "win" : "lose") + '">' + ilink(valHash(m.team1), m.team1) + '</td><td class="score">' +
          scoreLink(valMatchHash(m), '<span class="' + (w1 ? "w" : "") + '">' + esc(m.score1) + '</span>:<span class="' + (w2 ? "w" : "") + '">' + esc(m.score2) + "</span>", m.url, "match page on vlr.gg") + "</td>" +
          '<td class="' + (w2 ? "win" : "lose") + '">' + ilink(valHash(m.team2), m.team2) + "</td>" +
          (compact ? "" : '<td class="hide-sm" title="' + esc(m.event + (m.series ? " - " + m.series : "")) + '">' + esc(shortEv(m.event)) + '<span class="cc">' + esc(m.series) + "</span></td>") + "</tr>";
      }).join("") + "</tbody></table></div>";
  }


  /* ---------- Matches today (v3.5): CS2 (FACEIT) + Valorant (vlr.gg) on today's Pacific date ---------- */
  function dayKey(d) { var p = ptParts(d); return p.y + "-" + p.m + "-" + p.d; }
  function hhmm(iso) { var p = ptParts(new Date(iso)); return pad(p.h) + ":" + pad(p.mi); }
  /* v5.8 day strip: TODAY_SEL is a dayKey (y-m0-d, Pacific) chosen via #cs2/today/YYYY-MM-DD; null = today */
  var TODAY_SEL = null;
  function keyFromIso(s) { var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || ""); return m ? +m[1] + "-" + (+m[2] - 1) + "-" + +m[3] : null; }
  function isoFromKey(k) { var a = k.split("-"); return a[0] + "-" + pad(+a[1] + 1) + "-" + pad(+a[2]); }
  function keyDate(k) { var a = k.split("-"); return new Date(Date.UTC(+a[0], +a[1], +a[2], 12)); }
  function shiftKey(k, n) { var d = keyDate(k); d.setUTCDate(d.getUTCDate() + n); return d.getUTCFullYear() + "-" + d.getUTCMonth() + "-" + d.getUTCDate(); }
  function dayCounts() {
    var c = {}, mine = {};
    function add(iso, r) { if (!iso) return; var d = new Date(iso); if (isNaN(d)) return; var k = dayKey(d); c[k] = (c[k] || 0) + 1; if (r && rowMine(r)) mine[k] = 1; }
    ((D.cs && D.cs.live) || []).forEach(function (m) { add(m.t, { g: "cs", m: m }); });
    csFinished().forEach(function (m) { add(m.t, { g: "cs", m: m }); });
    csUpcoming().forEach(function (m) { add(m.t, { g: "cs", m: m }); });
    valResults().forEach(function (m) { add(m.ts, { g: "val", m: m }); });
    ((D.valorant && D.valorant.upcoming) || []).forEach(function (m) { add(m.ts, { g: "val", m: m }); });
    return { c: c, mine: mine };
  }
  function dayStrip(sel) {
    var dc = dayCounts(), keys = Object.keys(dc.c).sort(function (a, b) { return keyDate(a) - keyDate(b); }), tk = dayKey(new Date());
    if (!keys.length) return "";
    var lo = keyDate(keys[0]), hi = keyDate(keys[keys.length - 1]), out = [];
    for (var i = -3; i <= 3; i++) {
      var k = shiftKey(sel, i), d = keyDate(k), inWin = d >= lo && d <= hi, n = dc.c[k] || 0;
      var lbl = DAYS[d.getUTCDay()].slice(0, 3) + " " + d.getUTCDate() + (k === tk ? " (today)" : "");
      var href = "#cs2/today" + (k === tk ? "" : "/" + isoFromKey(k));
      out.push(inWin || k === tk ? '<a class="day' + (k === sel ? " on" : "") + '" href="' + href + '"' + (k === sel ? ' aria-current="date"' : "") + ">" + esc(lbl) + ' <span class="cnt">' + n + "</span>" + (dc.mine[k] ? '<span class="mydot" title="a starred team plays">&#9679;</span>' : "") + "</a>"
        : '<span class="day off" title="not tracked">' + esc(lbl) + "</span>");
    }
    return '<nav class="day-strip" aria-label="Pick a day">' + out.join("") + "</nav>";
  }
  function todayRows() {
    var key = TODAY_SEL || dayKey(new Date()), rows = [];
    function today(iso) { if (!iso) return false; var d = new Date(iso); return !isNaN(d) && dayKey(d) === key; }
    var liveIds = {};
    ((D.cs && D.cs.live) || []).forEach(function (m) { liveIds[m.id] = 1; if (today(m.t)) rows.push({ g: "cs", st: "live", m: m }); });
    csFinished().forEach(function (m) { if (today(m.t) && !liveIds[m.id]) rows.push({ g: "cs", st: "done", m: m }); });
    csUpcoming().forEach(function (m) { if (today(m.t) && !liveIds[m.id]) rows.push({ g: "cs", st: "up", m: m }); });
    valResults().forEach(function (m) { if (today(m.ts)) rows.push({ g: "val", st: "done", m: m }); });
    var vdone = {}; valResults().forEach(function (m) { vdone[m.url] = 1; });
    ((D.valorant && D.valorant.upcoming) || []).forEach(function (m) { if (today(m.ts) && !vdone[m.url]) rows.push({ g: "val", st: m.live ? "live" : "up", m: m }); });
    rows.sort(function (a, b) { return String(a.m.t || a.m.ts || "").localeCompare(String(b.m.t || b.m.ts || "")); });
    return rows;
  }
  /* v5.5 relative times + status tabs (Today board) */
  function relText(st, iso, g) {
    var t = new Date(iso).getTime(); if (isNaN(t)) return "";
    var d = Math.round((Date.now() - t) / 60000), a = Math.abs(d);
    var span = a < 60 ? a + "m" : a < 1440 ? Math.floor(a / 60) + "h" + (a % 60 ? " " + (a % 60) + "m" : "") : Math.floor(a / 1440) + "d";
    if (st === "up") return d < 0 ? "in " + span : "started " + span + " ago &middot; no result yet";
    if (st === "live") return "started " + span + " ago";
    if (g === "as") return d < 0 ? "just now" : span + " ago";
    return d < 0 ? "" : (g === "cs" ? "ended " : "started ") + span + " ago";
  }
  function relSpan(st, iso, g) { return iso ? '<span class="rel" data-st="' + st + '" data-g="' + g + '" data-t="' + esc(iso) + '">' + relText(st, iso, g) + "</span>" : ""; }
  function refreshRel() { Array.prototype.forEach.call(document.querySelectorAll("#view .rel[data-t]"), function (el) { el.innerHTML = relText(el.getAttribute("data-st"), el.getAttribute("data-t"), el.getAttribute("data-g")); }); }
  var TABS = [["all", "All"], ["live", "Live"], ["up", "Upcoming"], ["done", "Finished"], ["mine", "My teams"]];
  function rowMine(r) {
    var m = r.m;
    if (r.g === "cs") return (m.t1 && isFav("cs:" + m.t1.id)) || (m.t2 && isFav("cs:" + m.t2.id));
    return isFav("val:" + slug(m.team1)) || isFav("val:" + slug(m.team2));
  }
  /* C: R6 pinned divisions, R7 filter presets (shareable as #cs2/today/f-na), R9 scoreboard bar */
  function pins() { var p = lsGet("esb-pins", []); var ids = csDivs().map(divId); return Array.isArray(p) ? p.filter(function (x) { return ids.indexOf(x) >= 0; }) : []; }
  function pinBtn(id, label) { var on = pins().indexOf(id) >= 0; return ' <button type="button" class="pin' + (on ? " on" : "") + '" data-pin="' + esc(id) + '" aria-pressed="' + on + '" title="' + (on ? "Unpin " : "Pin ") + esc(label) + ' (kept in this browser)">' + (on ? "&#9873; Pinned" : "&#9872; Pin") + "</button>"; }
  function renderPinned() {
    var box = $("#side-pins"), ul = $("#side-pins-list"); if (!box || !ul) return;
    var ds = csDivs(), p = pins();
    ul.innerHTML = p.map(function (id) { var d = ds.filter(function (x) { return divId(x) === id; })[0]; return d ? '<li><a href="#cs2/' + esc(id) + '">' + esc(d.region + " " + d.division) + "</a></li>" : ""; }).join("");
    box.hidden = !p.length;
  }
  var FILTERS = [["all", "All"], ["na", "NA interest"], ["eu", "EU"], ["adv", "Advanced"], ["bo1", "Bo1"], ["bo3", "Bo3"], ["mine", "My teams + pinned"]];
  var TODAY_F = null, CCC = null;
  function teamCountry(id) { if (!CCC) { CCC = {}; csDivs().forEach(function (d) { (d.teams || []).forEach(function (t) { var k = csTeamId(t); if (k) CCC[k] = t.country; }); }); } return CCC[id] || ""; }
  function todayFilter() { var f = TODAY_F || lsGet("esb-today-filter", "all"); return FILTERS.some(function (x) { return x[0] === f; }) ? f : "all"; }
  function passFilter(r, f) {
    var m = r.m, cs = r.g === "cs";
    if (f === "all") return true;
    if (f === "mine") return rowMine(r) || (cs && pins().indexOf(divOf(m)) >= 0);
    if (f === "bo1" || f === "bo3") return cs && num(m.bo) === +f.slice(2);
    if (f === "adv") return cs && m.division === "Advanced";
    if (f === "eu") return cs ? m.region === "EU" : /EMEA|Europe/i.test(m.event || "");
    if (f === "na") return cs ? (m.region === "NA" || /^(US|CA)$/.test(teamCountry(m.t1 && m.t1.id)) || /^(US|CA)$/.test(teamCountry(m.t2 && m.t2.id)) || rowMine(r)) : (/North America|Americas/i.test(m.event || "") || rowMine(r));
    return true;
  }
  function filterSegs(f, dayIso) {
    return '<div class="segs segs2 f-presets"><div class="seg"><span class="seg-l">Filter</span>' + FILTERS.map(function (x) {
      return '<a href="#cs2/today/' + (dayIso ? dayIso + "/" : "") + "f-" + x[0] + '" class="fpre' + (x[0] === f ? " on" : "") + '" data-f="' + x[0] + '">' + x[1] + "</a>";
    }).join("") + "</div></div>";
  }
  function renderBar() {
    var bar = $("#sb-bar"); if (!bar) return;
    if (!favs().length && !pins().length) { bar.hidden = true; bar.innerHTML = ""; return; }
    var items = [], now = Date.now(), seen = {};
    function push(r) { var k = r.g + (r.m.id || r.m.url); if (seen[k]) return; seen[k] = 1; items.push(r); }
    ((D.cs && D.cs.live) || []).forEach(function (m) { var r = { g: "cs", st: "live", m: m }; if (passFilter(r, "mine")) push(r); });
    csUpcoming().forEach(function (m) { var r = { g: "cs", st: "up", m: m }; if (new Date(m.t).getTime() > now - 3600000 && passFilter(r, "mine")) push(r); });
    items = items.slice(0, 8);
    if (!items.length) { bar.hidden = true; bar.innerHTML = ""; return; }
    var upd = (D.cs && D.cs.matches_meta && D.cs.matches_meta.fetched_at) || D.fetched_at;
    bar.innerHTML = '<span class="sb-l">MY MATCHES</span>' + items.map(function (r) {
      var m = r.m, h = csMatchHash(m);
      return '<a class="sb-i" href="' + (r.st === "live" ? esc(safeUrl(roomUrl(m) || "#" + h)) + '" target="_blank" rel="noopener' : "#" + esc(h)) + '" title="' + (r.st === "live" ? "live as of " + esc(fmt(upd, "short")) : "starts " + esc(fmt(m.t))) + '">' + esc(m.t1.name) + " vs " + esc(m.t2.name) + " <b>" + (r.st === "live" ? "LIVE" : hhmm(m.t)) + "</b> &#9656;</a>";
    }).join("");
    bar.hidden = false;
  }
  function todayTab() { var t = lsGet("esb-today-tab", "all"); return TABS.some(function (x) { return x[0] === t; }) ? t : "all"; }
  function todayBoard(preview) {
    var flt = preview ? "all" : todayFilter(), all = todayRows().filter(function (r) { return passFilter(r, flt); }), p = ptParts(new Date()), N = 12, tab = preview ? "all" : todayTab(), counts = { all: all.length, live: 0, up: 0, done: 0, mine: 0 };
    all.forEach(function (r) { counts[r.st]++; if (rowMine(r)) counts.mine++; });
    var tabsHtml = preview ? "" : '<div class="segs segs2 st-tabs"><div class="seg" role="tablist" aria-label="Match status"><span class="seg-l">Show</span>' + TABS.map(function (x) {
      return '<a href="#cs2/today" role="tab" class="st-tab' + (x[0] === tab ? " on" : "") + '" aria-selected="' + (x[0] === tab) + '" data-tab="' + x[0] + '">' + x[1] + ' <span class="cnt">' + counts[x[0]] + "</span></a>";
    }).join("") + "</div></div>";
    if (tab !== "all") { all = all.filter(function (r) { return tab === "mine" ? rowMine(r) : r.st === tab; }); N = 60; }
    // busy league days have 200+ matches: show every live match, the latest N results and the next N starts
    var done = all.filter(function (r) { return r.st === "done"; }), up = all.filter(function (r) { return r.st === "up"; });
    var live = all.filter(function (r) { return r.st === "live"; });
    var rows = live.concat(done.slice(-N), up.slice(0, N));
    if (preview) { // home: at most 5 rows - live first, then the latest results and the next starts
      var lv = live.slice(0, 5), rem = 5 - lv.length, nu = Math.min(up.length, Math.floor(rem / 2)), nd = Math.min(done.length, rem - nu);
      nu = Math.min(up.length, rem - nd);
      rows = lv.concat(done.slice(done.length - nd), up.slice(0, nu));
    }
    rows.sort(function (a, b) { return String(a.m.t || a.m.ts || "").localeCompare(String(b.m.t || b.m.ts || "")); });
    var cut = rows.length < all.length;
    var title = "Matches Today :: " + DAYS[p.wd].slice(0, 3) + " " + MON[p.m] + " " + p.d;
    if (TODAY_SEL && !preview && TODAY_SEL !== dayKey(new Date())) { var sd = keyDate(TODAY_SEL); title = "Matches :: " + DAYS[sd.getUTCDay()].slice(0, 3) + " " + MON[sd.getUTCMonth()] + " " + sd.getUTCDate(); }
    if (!preview) tabsHtml = dayStrip(TODAY_SEL || dayKey(new Date())) + filterSegs(flt, TODAY_SEL && TODAY_SEL !== dayKey(new Date()) ? isoFromKey(TODAY_SEL) : "") + tabsHtml;
    var upd = (D.cs && D.cs.matches_meta && D.cs.matches_meta.fetched_at) || D.fetched_at;
    var meta = upd ? "updated " + fmt(upd, "short") : "";
    if (preview) meta = all.length ? '<a href="#cs2/today">see all ' + all.length + " &raquo;</a>" : "";
    if (!rows.length) return std(esc(title), meta, tabsHtml + '<div class="empty today-empty">' + (tab === "all" ? "No matches scheduled today." : tab === "mine" ? "None of your starred teams play today." : "No " + { live: "live", up: "upcoming", done: "finished" }[tab] + " matches today.") + "</div>", "today-board");
    var liveN = rows.filter(function (x) { return x.st === "live"; }).length;
    var liveAge = liveN && upd ? '<div class="live-age"><span class="live-b">LIVE</span> status as of ' + fmt(upd, "short") + " (" + relSpan("done", upd, "as") + ") &middot; scores here refresh about every 30 minutes; for the live score use the LIVE button (FACEIT / vlr.gg match room &#8599;).</div>" : "";
    var body = tabsHtml + liveAge + '<div class="rankbox"><table class="tbl res today"><colgroup><col class="c-when"><col class="c-team"><col class="c-score"><col class="c-team"><col class="c-div hide-sm"><col class="c-map hide-sm"></colgroup><thead><tr>' +
      '<th class="first" title="Pacific Time: start time for upcoming and live matches, finish time for finished CS2 matches">Time (PT)</th><th class="n">Team 1</th><th class="c">Score</th><th>Team 2</th><th class="hide-sm">Division / Event</th><th class="hide-sm">Map</th></tr></thead><tbody>' +
      rows.map(function (r) {
        var m = r.m;
        if (r.g === "val" && r.st !== "done") {
          var vt = function (nm) { return nm && nm !== "TBD" ? ilink(valHash(nm), nm) : '<span class="dim">TBD</span>'; };
          return '<tr class="g-val st-' + r.st + '"><td class="dim" title="' + esc("scheduled " + fmt(m.ts)) + '">' + hhmm(m.ts) + relSpan(r.st, m.ts, "val") + '</td><td class="n tm">' + vt(m.team1) + '</td><td class="score"><a href="' + esc(safeUrl(m.url)) + '" target="_blank" rel="noopener" title="match page on vlr.gg">' +
            (r.st === "live" ? '<span class="live-b">LIVE</span>' : "vs") + '</a></td><td class="tm">' + vt(m.team2) + '</td><td class="hide-sm div" title="' + esc(m.event + (m.series ? " - " + m.series : "")) + '"><span class="gtag">VAL</span>' + esc(shortEv(m.event)) + '</td><td class="hide-sm dim">&ndash;</td></tr>';
        }
        if (r.g === "val") {
          var v1 = m.winner === 0, v2 = m.winner === 1;
          return '<tr class="g-val"><td class="dim" title="' + esc(fmt(m.ts)) + '">' + hhmm(m.ts) + relSpan("done", m.ts, "val") + '</td><td class="n tm ' + (v1 ? "win" : "lose") + '">' + ilink(valHash(m.team1), m.team1) +
            '</td><td class="score">' + scoreLink(valMatchHash(m), '<span class="' + (v1 ? "w" : "") + '">' + esc(m.score1) + '</span>:<span class="' + (v2 ? "w" : "") + '">' + esc(m.score2) + "</span>", m.url, "match page on vlr.gg") + "</td>" +
            '<td class="tm ' + (v2 ? "win" : "lose") + '">' + ilink(valHash(m.team2), m.team2) + '</td><td class="hide-sm div" title="' + esc(m.event + (m.series ? " - " + m.series : "")) + '"><span class="gtag">VAL</span>' + esc(shortEv(m.event)) +
            '</td><td class="hide-sm dim">&ndash;</td></tr>';
        }
        var ru = roomUrl(m), w1 = r.st === "done" && m.winner === 1, w2 = r.st === "done" && m.winner === 2, mid;
        if (r.st === "done") mid = '<span class="' + (w1 ? "w" : "") + '">' + num(m.s1) + '</span>:<span class="' + (w2 ? "w" : "") + '">' + num(m.s2) + "</span>";
        else if (r.st === "live") mid = '<span class="live-b">LIVE</span>';
        else mid = "vs";
        var tip = r.st === "done" ? "match room on FACEIT" : r.st === "live" ? "live now (as of the last update) - match room on FACEIT" : "match room on FACEIT";
        return '<tr class="g-cs st-' + r.st + '"><td class="dim" title="' + esc((r.st === "done" ? "finished " : r.st === "live" ? "started " : "scheduled ") + (m.t ? fmt(m.t) : "")) + '">' + (m.t ? hhmm(m.t) + relSpan(r.st, m.t, "cs") : "TBD") + "</td>" +
          '<td class="n tm ' + (r.st === "done" ? (w1 ? "win" : "lose") : "") + '">' + rankPre(m.t1) + csSide(m.t1) + '</td><td class="score">' + (r.st === "done" ? scoreLink(csMatchHash(m), mid, ru, tip) + (isFF(m) ? ' <span class="ff-tag" title="forfeit (FACEIT result with no rounds played)">FF</span>' : "") : (r.st === "up" && csMatchHash(m) ? '<a href="#' + esc(csMatchHash(m)) + '" title="match preview">' + mid + "</a>" : ru ? '<a href="' + esc(safeUrl(ru)) + '" target="_blank" rel="noopener" title="' + tip + '">' + mid + "</a>" : mid)) + (r.st === "done" ? mapChips(m) : "") + "</td>" +
          '<td class="tm ' + (r.st === "done" ? (w2 ? "win" : "lose") : "") + '">' + rankPre(m.t2) + csSide(m.t2) + '</td><td class="hide-sm div" title="' + esc(m.region + " " + m.division + (m.conf ? " - conference " + m.conf : "") + " - round " + m.round) + '"><span class="gtag">CS2</span>' +
          ilink("cs2/" + divOf(m), m.region + " " + m.division) + (m.bo ? ' <span class="bo-tag">Bo' + num(m.bo) + "</span>" : "") + '</td><td class="hide-sm">' + (r.st === "done" ? mapCell(m) : '<span class="dim">&ndash;</span>') + "</td></tr>";
      }).join("") + "</tbody></table></div>" +
      (preview ? '<div class="note see-all">' + all.length + " match" + (all.length === 1 ? "" : "es") + ' today &middot; <a href="#cs2/today">see all matches today &raquo;</a></div>' :
      '<div class="note">' + all.length + " match" + (all.length === 1 ? "" : "es") + " today" + (cut ? " &middot; showing " + [live.length ? "live matches" : "", done.length ? "the latest " + Math.min(N, done.length) + " result" + (Math.min(N, done.length) === 1 ? "" : "s") : "", up.length ? "the next " + Math.min(N, up.length) + " start" + (Math.min(N, up.length) === 1 ? "" : "s") : ""].filter(Boolean).join(", ") + ' (<a href="#cs2/results">all results &raquo;</a>)' : "") +
      ". Times in Pacific Time. Click a final score for the match page (&#8599; = source), vs / LIVE for the match room. LIVE = in progress at the last update.</div>");
    return std(esc(title), meta, body, "today-board");
  }

  /* ----- v4.3 my teams, recently viewed, last CS2 division: kept in this browser only (localStorage) ----- */
  var LS = { fav: "esb-favs", rec: "esb-recent", div: "esb-cs-div" }, FAVC = null;
  function lsGet(k, def) { try { var v = JSON.parse(localStorage.getItem(k)); return v == null ? def : v; } catch (e) { return def; } }
  function lsSet(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } }
  function favs() {
    if (FAVC) return FAVC;
    var f = lsGet(LS.fav, []);
    FAVC = Array.isArray(f) ? f.filter(function (x) { return x && typeof x.k === "string" && /^(cs|val):./.test(x.k) && typeof x.n === "string"; }).slice(0, 50) : [];
    return FAVC;
  }
  function isFav(k) { return favs().some(function (x) { return x.k === k; }); }
  function toggleFav(k, n) {
    var f = favs().slice(), i = -1;
    f.forEach(function (x, j) { if (x.k === k) i = j; });
    if (i >= 0) f.splice(i, 1); else f.push({ k: k, n: String(n || "").slice(0, 80) });
    lsSet(LS.fav, f.length ? f : null); FAVC = null; try { renderBar(); } catch (e) {}
    return i < 0;
  }
  function favHash(k) { return k.indexOf("cs:") === 0 ? "team/cs2/" + encodeURIComponent(k.slice(3)) : "team/val/" + k.slice(4); }
  function star(k, n, big) {
    var on = isFav(k);
    return '<button type="button" class="star' + (big ? " star-lg" : "") + (on ? " on" : "") + '" data-fav="' + esc(k) + '" data-n="' + esc(n) + '" aria-pressed="' + on + '" title="' + (on ? "Remove " + esc(n) + " from" : "Add " + esc(n) + " to") + ' My Teams (saved in this browser)">' +
      '<span aria-hidden="true">' + (on ? "&#9733;" : "&#9734;") + "</span>" + (big ? (on ? " Following" : " Follow") : '<span class="vh">' + (on ? "Unfollow " : "Follow ") + esc(n) + "</span>") + "</button>";
  }
  function csHome() { var v = lsGet(LS.div, ""); return typeof v === "string" && csDivs().some(function (d) { return divId(d) === v; }) ? "cs2/" + v : "cs2"; }
  function myMatches(page) {
    var f = favs(), cs = {}, val = {}, nCs = 0;
    f.forEach(function (x) { if (x.k.indexOf("cs:") === 0) { cs[x.k.slice(3)] = 1; nCs++; } else val[x.k.slice(4)] = 1; });
    if (!f.length) return page === "today" ? "" : '<div class="note my-hint" id="my-matches"><span aria-hidden="true">&#9734;</span> Tip: star a team (on its page or in the standings) to follow its matches here. Saved in this browser only.</div>';
    if (nCs) loadTeams();
    var seen = {}, done = [], up = [], x = teamsX();
    function csIn(m) { return (m.t1 && cs[m.t1.id]) || (m.t2 && cs[m.t2.id]); }
    function add(list, st, g) { list.forEach(function (m) { var k = g + (m.id || m.url); if (seen[k]) return; seen[k] = 1; (st === "done" ? done : up).push({ g: g, st: st === "done" ? "done" : m.live || st === "live" ? "live" : "up", m: m, t: m.t || m.ts || "" }); }); }
    add(((D.cs && D.cs.live) || []).filter(csIn), "live", "cs");
    add(csFinished().concat((x && x.matches) || []).filter(csIn), "done", "cs");
    add(csUpcoming().concat((x && x.upcoming) || []).filter(csIn), "up", "cs");
    function vIn(m) { return val[slug(m.team1)] || val[slug(m.team2)]; }
    add(valResults().filter(vIn), "done", "val");
    add(((D.valorant && D.valorant.upcoming) || []).filter(vIn), "up", "val");
    done.sort(function (a, b) { return String(b.t).localeCompare(String(a.t)); });
    up.sort(function (a, b) { return (a.st === "live" ? 0 : 1) - (b.st === "live" ? 0 : 1) || String(a.t).localeCompare(String(b.t)); });
    function side(r, n) {
      var m = r.m, isMine;
      if (r.g === "cs") { var sd = n === 1 ? m.t1 : m.t2; isMine = sd && cs[sd.id]; return '<span class="' + (isMine ? "mine" : "") + '">' + csSide(sd) + "</span>"; }
      var nm = n === 1 ? m.team1 : m.team2; isMine = val[slug(nm)];
      return '<span class="' + (isMine ? "mine" : "") + '">' + (nm && nm !== "TBD" ? ilink(valHash(nm), nm) : '<span class="dim">TBD</span>') + "</span>";
    }
    function row(r) {
      var m = r.m, w1, w2, mid, url, when;
      if (r.g === "cs") { w1 = r.st === "done" && m.winner === 1; w2 = r.st === "done" && m.winner === 2; url = roomUrl(m); }
      else { w1 = r.st === "done" && m.winner === 0; w2 = r.st === "done" && m.winner === 1; url = m.url; }
      if (r.st === "done") mid = r.g === "cs" ? '<span class="' + (w1 ? "w" : "") + '">' + num(m.s1) + '</span>:<span class="' + (w2 ? "w" : "") + '">' + num(m.s2) + "</span>" : '<span class="' + (w1 ? "w" : "") + '">' + esc(m.score1) + '</span>:<span class="' + (w2 ? "w" : "") + '">' + esc(m.score2) + "</span>";
      else mid = r.st === "live" ? '<span class="live-b">LIVE</span>' : "vs";
      when = r.t ? (r.st === "done" ? fmt(r.t, "md") : fmt(r.t, "short").replace(/ [A-Z]{3,4}$/, "")) : "TBD";
      var src = r.g === "cs" ? "match room on FACEIT" : "match page on vlr.gg";
      var where = r.g === "cs" ? '<span class="gtag">CS2</span>' + ilink("cs2/" + divOf(m), m.region + " " + m.division) : '<span class="gtag">VAL</span>' + esc(shortEv(m.event));
      return '<tr class="st-' + r.st + '"><td class="dim when" title="' + esc(r.t ? fmt(r.t) : "") + '">' + when + '</td><td class="n tm ' + (r.st === "done" ? (w1 ? "win" : "lose") : "") + '">' + side(r, 1) + '</td><td class="score">' +
        (r.st === "done" ? scoreLink(r.g === "cs" ? csMatchHash(m) : valMatchHash(m), mid, url, src) : url && safeUrl(url) !== "#" ? '<a href="' + esc(safeUrl(url)) + '" target="_blank" rel="noopener" title="' + src + '">' + mid + "</a>" : mid) + '</td><td class="tm ' + (r.st === "done" ? (w2 ? "win" : "lose") : "") + '">' + side(r, 2) + '</td><td class="hide-sm div">' + where + "</td></tr>";
    }
    function table(rows, head) {
      return '<div class="my-h">' + head + "</div>" + (rows.length ? '<div class="rankbox"><table class="tbl res my-tbl"><colgroup><col class="c-when"><col class="c-team"><col class="c-score"><col class="c-team"><col class="c-div hide-sm"></colgroup><tbody>' +
        rows.map(row).join("") + "</tbody></table></div>" : '<div class="empty">None in the data Esports Scoreboard tracks.</div>');
    }
    var nUp = up.slice(0, 5), nDone = done.slice(0, 5);
    var body = (nUp.length || nDone.length) ? table(nUp, "Next matches") + table(nDone, "Latest results") :
      '<div class="empty">No recent or upcoming matches for your teams in the data Esports Scoreboard tracks' + (nCs && TX_STATE === "loading" ? " (still loading&hellip;)" : "") + ".</div>";
    var list = '<div class="note my-teams">Following: ' + f.map(function (x) { return ilink(favHash(x.k), x.n) + star(x.k, x.n); }).join(" &middot; ") +
      '<br><span class="dim">Saved in this browser only &mdash; no account. Tap a star to follow or unfollow.</span></div>';
    return std("My Teams", f.length + " followed", body + list, "my-matches");
  }
  function noteRecent(r) {
    if (["team", "player", "guild", "match"].indexOf(r.top) < 0) return;
    var h1 = $("#view .std-header h1"), name = h1 ? h1.textContent.trim() : "";
    if (!name || /not tracked|unavailable/i.test(name) || $("#view .loading")) return;
    var h = curHash().replace(/^#/, ""), kind = { team: "team", player: "player", guild: "guild", match: "match" }[r.top];
    var game = r.top === "guild" ? "WoW" : r.parts[0] === "val" ? "Valorant" : "CS2";
    var rec = lsGet(LS.rec, []); if (!Array.isArray(rec)) rec = [];
    rec = [{ h: h, n: name.slice(0, 80), w: game + " " + kind }].concat(rec.filter(function (x) { return x && x.h !== h; })).slice(0, 8);
    lsSet(LS.rec, rec);
  }
  function recentHtml() {
    var rec = lsGet(LS.rec, []);
    rec = Array.isArray(rec) ? rec.filter(function (x) { return x && typeof x.h === "string" && /^(team|player|guild|match)\//.test(x.h) && typeof x.n === "string"; }) : [];
    if (!rec.length) return "";
    return '<div class="sr-group recent"><div class="sr-h">Recently viewed <button type="button" class="rv-clear" title="Forget the recently viewed list in this browser">clear</button></div><ul class="sr-list">' + rec.map(function (x) {
      return '<li><a href="#' + esc(x.h) + '">' + esc(x.n) + '</a><span class="where">' + esc(x.w || "") + "</span></li>";
    }).join("") + '</ul><div class="note">Kept in this browser only.</div></div>';
  }

  /* ================= VIEWS ================= */
  function vHome() {
    var s = D.cs && D.cs.season, raid = D.wow && D.wow.raid, tr = todayRows();
    function cnt(n, w) { return n + " " + w + (n === 1 ? "" : (w === "match" ? "es" : "s")); }
    function card(game, teaser, btns) {
      var g = SECTIONS[game];
      return '<section class="gcard g-' + game + '" aria-label="' + esc(g.name) + '"><a class="gc-head" href="#' + game + '"><span class="gc-name">' + esc(g.name) + '</span><span class="gc-sub">' + esc(g.sub) + ' &raquo;</span></a>' +
        '<div class="gc-teaser">' + (teaser || '<span class="dim">No data yet.</span>') + '</div><div class="gc-btns">' + btns.map(function (b) { return '<a class="gbtn" href="#' + b[1] + '">' + esc(b[0]) + "</a>"; }).join("") + "</div></section>";
    }
    var csN = tr.filter(function (r) { return r.g === "cs"; }).length, csLive = tr.filter(function (r) { return r.g === "cs" && r.st === "live"; }).length;
    var d0 = csDivs().filter(function (d) { return d.teams && d.teams.length; })[0];
    var csT = [csN ? cnt(csN, "match") + " today" : s ? esc(s.name) : "", csLive ? '<span class="live-b">' + csLive + " LIVE</span>" : "", d0 ? esc(d0.region + " " + d0.division) + " leader <b>" + esc(d0.teams[0].name) + "</b>" : ""].filter(Boolean).join(" &middot; ");
    var vN = tr.filter(function (r) { return r.g === "val"; }).length, tp = ((D.valorant || {}).top_players || [])[0], evs = valEvents();
    var vT = [vN ? cnt(vN, "match") + " today" : "", evs.length ? cnt(evs.length, "event") + " tracked" : "", tp ? "top player <b>" + esc(tp.name) + "</b> (" + num(tp.rating).toFixed(2) + ")" : ""].filter(Boolean).join(" &middot; ");
    var rk = (D.wow && D.wow.rankings) || {}, us = (rk.us || [])[0], eu = (rk.eu || [])[0];
    var wT = [raid ? esc(raid.name) : "", us ? "US #1 <b>" + esc(us.guild) + "</b> " + esc(us.progress) : "", eu ? "EU #1 <b>" + esc(eu.guild) + "</b> " + esc(eu.progress) : ""].filter(Boolean).join(" &middot; ");
    var cards = '<div class="gcards">' +
      card("cs2", csT, [["Standings", csHome()], ["Results", "cs2/results"], ["Top Players", "cs2/players"], ["Matches Today", "cs2/today"]]) +
      card("valorant", vT, [["Events", "valorant/events"], ["Results", "valorant/results"], ["Top Players", "valorant/players"]]) +
      card("wow", wT, [["US Rankings", "wow/us"], ["EU Rankings", "wow/eu"]]) + "</div>";
    var news = newsItems().slice(0, 5);
    var newsHtml = news.length ? '<div class="newsbox">' + news.map(function (n) {
      return '<div class="item">' + ext(n.url, n.title) + '<span class="src">(' + esc(n.source) + ")</span></div>";
    }).join("") + '<div class="item more"><a href="#news">More news &raquo;</a></div></div>' : '<div class="empty">No headlines right now.</div>';
    var intro = '<div class="infobox hub-intro">Amateur &amp; semi-pro esports: ESEA League CS2, Valorant Challengers and the WoW Mythic raid race. Pick a game to start. All times Pacific.</div>';
    return std("Esports Scoreboard Front Page", "updated " + fmt(D.fetched_at, "short"), intro) + discordBox("home") + cards + homeSpot() + myMatches("home") + todayBoard(true) +
      std("Latest Esports News", '<a href="#news">more news &raquo;</a>', newsHtml, "home-news");
  }

  function vCS2(parts) {
    var sub = parts[0];
    var cs = D.cs || {}, divs = csDivs(), ids = divs.map(divId);
    if (/^(ranking|top20|methodology|awards|playoffs)$/.test(sub)) {
      var V6 = { ranking: ["ESB Team Ranking", vRanking], top20: ["Top 20 Players of the Season", vTop20], methodology: ["Ranking &amp; Rating Methodology", vMethod], awards: ["Season Awards", vAwards], playoffs: ["Playoffs", vPlayoffs] };
      var bodyR = V6[sub][1](parts[1]);
      return gameHead("cs2", sub === "methodology" ? "ranking" : sub, "Counter-Strike 2 :: " + V6[sub][0]) + bodyR;
    }
    if (!sub || (ids.indexOf(sub) < 0 && sub !== "players" && sub !== "results" && sub !== "today")) sub = ids[0] || "players";
    var section = sub === "players" || sub === "results" || sub === "today" ? sub : "standings", segs = "";
    if (section === "standings" && ids.length) {
      var cur = divs[ids.indexOf(sub)], regs = ["NA", "EU"].filter(function (rg) { return divs.some(function (d) { return d.region === rg; }); });
      var inReg = function (rg) { return divs.filter(function (d) { return d.region === rg; }); };
      segs = '<div class="segs">' + seg("Region", regs.map(function (rg) {
        var same = inReg(rg).filter(function (d) { return d.division === cur.division; })[0] || inReg(rg)[0];
        return [rg, "cs2/" + divId(same), rg === cur.region];
      })) + seg("Division", inReg(cur.region).map(function (d) {
        return [d.division, "cs2/" + divId(d), d === cur, d.division === "Intermediate" ? "Int" : d.division === "Advanced" ? "Adv" : d.division];
      })) + "</div>";
      setCrumbs([["CS2", "cs2"], [cur.region + " " + cur.division, "cs2/" + divId(cur)], ["Standings"]]);
      if (parts[0] === sub && lsGet(LS.div, "") !== sub) lsSet(LS.div, sub);   // v4.3: remembered for the Standings links
    } else setCrumbs([["CS2", "cs2"], [section === "players" ? "Top Players" : section === "results" ? "Results" : "Matches Today"]]);
    var s = cs.season;
    var info = s ? '<div class="infobox">' + ext(cs.page, cs.league) + " &raquo; <b>" + esc(s.name) + "</b> &middot; " + fmt(s.start, "md") + " &ndash; " + fmt(s.end, "md") + " (PT)" +
      " &middot; " + num(s.team_count).toLocaleString("en-US") + " teams (all regions) &middot; $" + num(s.prize_pool).toLocaleString("en-US") + ' prize pool<br><span class="dim">Map pool: ' + esc((s.maps || []).join(", ")) + "</span></div>" + staleNote(s) : "";
    var body = "", title = "";
    if (sub === "today") {
      TODAY_SEL = null; TODAY_F = null;
      parts.slice(1).forEach(function (x) { if (keyFromIso(x)) TODAY_SEL = keyFromIso(x); var fm = /^f-([a-z0-9]+)$/.exec(x || ""); if (fm) TODAY_F = fm[1]; });
      if (TODAY_F && FILTERS.some(function (x) { return x[0] === TODAY_F; })) lsSet("esb-today-filter", TODAY_F);
      return gameHead("cs2", "today", "Counter-Strike 2 :: ESEA League") + myMatches("today") + todayBoard();
    } else if (sub === "players") {
      title = "Top Fraggers";
      body = csBoard(parts.slice(1));
    } else if (sub === "results") {
      title = "Match Results :: EU + NA";
      var allF = csFinished(), pg = pageOf(parts), npg = Math.max(1, Math.ceil(allF.length / PER_PAGE)); if (pg > npg) pg = npg;
      body = csMatchNote() + pager(allF.length, pg, "cs2/results") + csResultsTable(slicePage(allF, pg), { showDiv: true }) + pager(allF.length, pg, "cs2/results") +
        '<h2 class="subhead">Upcoming Matches</h2>' + csUpcomingTable(csUpcoming().slice(0, PER_PAGE), { showDiv: true }) +
        '<div class="note">Shows the newest finished matches of each tracked division plus the latest matches of every team in the standings; upcoming = next scheduled matches (times as listed on FACEIT).</div>';
    } else {
      var d = divs[ids.indexOf(sub)];
      var multi = (d.conferences || []).length > 1;
      title = d.region + " " + d.division + " :: " + d.stage;
      var showAll = parts[1] === "all", spg = pageOf(parts), base = "cs2/" + divId(d), nT = (d.teams || []).length;
      var npgT = Math.max(1, Math.ceil(nT / PER_PAGE)); if (spg > npgT) spg = npgT;
      var shown = showAll ? d.teams : slicePage(d.teams || [], spg);
      var pnav = nT > PER_PAGE ? '<div class="pager-wrap">' + (showAll ? '<nav class="pager"><span class="title">All ' + nT + ' teams</span><a href="#' + esc(base) + '">show pages</a></nav>' :
        pager(nT, spg, base).replace("</nav>", ' <a class="show-all" href="#' + esc(base) + '/all">show all ' + nT + "</a></nav>")) + "</div>" : "";
      loadTeams();   // more finished matches for the Form column (lazy teams.js)
      if (d.status !== "OK") body = soon("Standings coming soon.");
      else if (!d.teams.length) body = '<div class="empty">no standings yet</div>';
      else body = (d.stale ? staleRow("FACEIT standings", d.stale_reason, d.fetched_at) : "") + pnav + '<div class="rankbox"><table class="tbl"><thead><tr><th class="first c" title="rank across the whole stage (ties shown as ranges)">#</th><th>Team</th>' + (multi ? '<th class="c" title="conference">Conf</th>' : "") + '<th class="hide-sm">Tag</th><th class="n" title="wins">W</th><th class="n" title="losses">L</th><th class="n" title="league points (3 per win)">Pts</th><th class="n hide-sm" title="rounds won-lost">Rounds</th><th class="c form-h" title="last 5 results, newest right (FF = forfeit)">Form</th></tr></thead><tbody>' +
        shown.map(function (t) {
          return '<tr class="' + medal(t.rank) + '" data-k="' + esc("cs:" + divId(d) + ":" + t.name) + '">' + rk(t.rank) + '<td class="team">' + (csTeamId(t) ? star("cs:" + csTeamId(t), t.name) : "") + csTeamLink(t) + '<span class="cc" title="' + esc(countryName(t.country)) + '">' + esc(t.country || "") + "</span>" + (t.dq ? '<span class="cc dq" title="disqualified">DQ</span>' : "") +
            "</td>" + (multi ? '<td class="c">' + esc(t.conf || "?") + "</td>" : "") + '<td class="hide-sm dim">' + esc(t.tag || "") + '</td><td class="n w">' + num(t.w) + '</td><td class="n l">' + num(t.l) + '</td><td class="n"><b>' + num(t.pts) + '</b></td><td class="n hide-sm">' + esc(t.rounds) + '</td><td class="c fcell">' + formHtml(csForm(csTeamId(t))) + "</td></tr>";
        }).join("") + "</tbody></table></div>" + pnav + '<div class="note">All ' + nT + " teams of the " + esc(d.stage) + " stage" + (multi ? ", conferences " + esc(d.conferences.join(" + ")) + " ranked together (FACEIT stage table)" : "") +
        " &middot; tied ranks shown as ranges (e.g. 3-12) &middot; " + ext(d.link, "full table on FACEIT") + "</div>";
    }
    if (sub !== "players" && sub !== "results") {
      var dsel = divs[ids.indexOf(sub)];
      var df = csFinished().filter(function (m) { return divOf(m) === sub; }), du = csUpcoming().filter(function (m) { return divOf(m) === sub; });
      body += '<h2 class="subhead">' + esc(dsel.region + " " + dsel.division) + ' Results <small><a href="#cs2/results">all results &raquo;</a></small></h2>' + csResultsTable(df.slice(0, 10), { what: "finished matches in this division" }) +
        '<h2 class="subhead">Upcoming Matches</h2>' + csUpcomingTable(du.slice(0, 8)) + csMatchNote();
    }
    return gameHead("cs2", section, "Counter-Strike 2 :: ESEA League", segs) + srcLine("cs") + (section === "standings" ? info : "") +
      '<h2 class="subhead">' + esc(title) + (section === "standings" && ids.indexOf(sub) >= 0 ? pinBtn(sub, title) : "") + "</h2>" + body;
  }

  function vValorant(parts) {
    var sub = parts[0], page = pageOf(parts);
    var v = D.valorant || {}, evs = valEvents();
    var ids = ["results", "players", "calendar"].concat(evs.map(function (e, i) { return evId(i); }));
    var ord = evOrder();
    if (sub === "events") sub = "calendar";
    if (ids.indexOf(sub) < 0) sub = ord.length ? evId(ord[0]) : "calendar";   // #valorant opens the North America event
    var section = sub === "results" || sub === "players" ? sub : "events", picker = "";
    var evTabs = [{ grp: "Event" }].concat(ord.map(function (i) { return { id: evId(i), hash: "valorant/" + evId(i), label: shortEv(evs[i].title) }; }));
    if (section === "events" && evs.length) picker = toolbar(evTabs, sub, "toolbar ev-pick");
    setCrumbs([["Valorant", "valorant"], section === "results" ? ["Results"] : section === "players" ? ["Top Players"] : sub === "calendar" ? ["Events"] : ["Events", "valorant/events"],
      ids.indexOf(sub) >= 3 ? [shortEv(evs[ids.indexOf(sub) - 3].title)] : null]);
    var body = "", title = "", r;
    if (sub === "results") {
      r = valResults();
      var pages = Math.max(1, Math.ceil(r.length / PER_PAGE)); if (page > pages) page = pages;
      var evNames = Array.from(new Set(r.map(function (m) { return shortEv(m.event); })));
      var rm = v.results_meta || {};
      var excl = (rm.excluded_events || []).map(shortEv);
      title = "Recent Results (Challengers / Game Changers / tier-2)";
      body = staleNote(rm) + '<div class="note">' + r.length + " results from " + evNames.length + " events: " + esc(evNames.join(", ")) + ". Winner highlighted; click a score for the match page (&#8599; = vlr.gg). Dates in Pacific Time." +
        (rm.scanned ? " Scanned the latest " + num(rm.scanned) + " vlr.gg results; excluded " + num(rm.excluded_international) + " from international events (Champions/Masters) and " + num(rm.excluded_partner) + " from tier-1 VCT partner leagues" + (excl.length ? " (" + esc(excl.join(", ")) + ")" : "") + "." : "") + "</div>" +
        pager(r.length, page, "valorant/results") + resultsTable(slicePage(r, page), (page - 1) * PER_PAGE, false) + pager(r.length, page, "valorant/results");
    } else if (sub === "players") {
      title = "Top Players :: Challengers / Game Changers";
      body = valBoard(parts.slice(1));
    } else if (sub === "calendar") {
      title = "Tracked Events";
      var cal = v.event_list || [];
      body = (evs.length ? '<div class="rankbox"><table class="tbl ev-list"><thead><tr><th class="first">Event</th><th class="hide-sm">Dates</th><th>Winner</th></tr></thead><tbody>' +
        ord.map(function (i) {
          var e = evs[i], w0 = (e.standings || [])[0];
          return '<tr><td class="team">' + ilink("valorant/" + evId(i), shortEv(e.title)) + '</td><td class="hide-sm dim">' + esc(e.dates || "") + "</td><td>" + (w0 && String(w0.place).match(/^1(st)?$/i) ? ilink(valHash(w0.team), w0.team) : '<span class="dim">&ndash;</span>') + "</td></tr>";
        }).join("") + '</tbody></table></div><div class="note">Final standings and top players for each event; pick an event above or in the list.</div>' : '<div class="empty">No tracked events yet.</div>') +
        '<h2 class="subhead">Ongoing &amp; Upcoming Events</h2>' + staleNote(v.event_list_meta) + (cal.length ? '<div class="rankbox"><table class="tbl"><thead><tr><th class="first">Status</th><th>Event</th><th class="hide-sm">Circuit</th><th>Dates</th></tr></thead><tbody>' +
        cal.map(function (e, i) {
          var st = String(e.status || "");
          return '<tr data-k="vc:' + i + '"><td class="' + (st === "ongoing" ? "w" : "") + '">' + esc(st.toUpperCase()) + '</td><td class="team">' + ext(e.url, e.title) + '</td><td class="hide-sm">' + esc(e.circuit) + "</td><td>" + esc(e.dates) + "</td></tr>";
        }).join("") + '</tbody></table></div><div class="note">Dates as listed on vlr.gg.</div>' : '<div class="empty">no ongoing/upcoming events listed</div>');
    } else {
      var i = ids.indexOf(sub) - 3, e = evs[i], rows = e.standings || [];
      title = e.title + " :: Final Standings";
      body = (e.stale ? staleRow("vlr.gg event page", e.status_note, e.fetched_at) : "") + '<div class="note">' + esc(e.dates) + " &middot; " + ext(e.url, "event page on vlr.gg") + "</div>" + (rows.length ? '<div class="rankbox"><table class="tbl"><thead><tr><th class="first c">Place</th><th>Team</th><th class="n">Prize</th><th class="hide-sm">Qualified / Points</th><th class="c form-h" title="last 5 tracked results, newest right">Form</th></tr></thead><tbody>' +
        rows.map(function (t) {
          return '<tr class="' + medal(t.place) + '" data-k="' + esc("vs:" + i + ":" + t.team) + '">' + rk(t.place) + '<td class="team">' + star("val:" + slug(t.team), t.team) + ilink(valHash(t.team), t.team) + '<span class="cc">' + esc(t.country) +
            '</span></td><td class="n">' + esc(t.prize) + '</td><td class="hide-sm">' + esc([t.points, t.note].filter(Boolean).join(" ")) + '</td><td class="c fcell">' + formHtml(valForm(t.team)) + "</td></tr>";
        }).join("") + "</tbody></table></div>" : soon("Standings not available yet."));
      var etp = e.top_players || [];
      if (etp.length) body += '<h2 class="subhead">Top Players at ' + esc(shortEv(e.title)) + '</h2><div class="rankbox"><table class="tbl val-pl"><thead><tr><th class="first c">#</th><th>Player</th><th class="n hide-sm">Rnd</th><th class="n">R</th><th class="n">ACS</th><th class="n">K/D</th><th class="n hide-sm">ADR</th></tr></thead><tbody>' +
        etp.map(function (p, k) {
          return '<tr class="' + medal(k + 1) + '">' + rk(k + 1) + '<td class="team">' + ilink(valPHash(p.name), p.name) + (p.tag ? '<span class="cc">' + esc(p.tag) + "</span>" : "") + '</td><td class="n hide-sm">' + num(p.rnd) + '</td><td class="n">' + valPc(p) + '</td><td class="n">' + Math.round(num(p.acs)) +
            '</td><td class="n">' + num(p.kd).toFixed(2) + '</td><td class="n hide-sm">' + num(p.adr).toFixed(1) + "</td></tr>";
        }).join("") + '</tbody></table></div><div class="note">Best five by vlr.gg rating (min. 40 rounds) &middot; <a href="#valorant/players">all top players</a> &middot; ' + ext(String(e.url || "").replace(/\/event\/(\d+)\/.*/, "/event/stats/$1"), "event stats on vlr.gg") + "</div>";
    }
    return gameHead("valorant", section, "Valorant :: Challengers / Game Changers", picker) + srcLine("valorant") +
      '<h2 class="subhead">' + esc(title) + "</h2>" + body;
  }

  function vWow(parts) {
    var sub = parts[0], page = pageOf(parts);
    var w = D.wow || {}, rks = w.rankings || {}, regs = wowRegs(rks);
    if (regs.indexOf(sub) < 0) sub = regs[0] || "us";
    setCrumbs([["WoW", "wow"], [sub.toUpperCase() + " Rankings"]]);
    var raid = w.raid;
    var info = raid ? '<div class="infobox">Current raid: <b>' + esc(raid.name) + "</b> &middot; " + (raid.bosses || []).length + " bosses &middot; opened " + fmt(raid.starts_us, "md") +
      ' (US)<br><span class="dim">' + esc((raid.bosses || []).join(" / ")) + "</span></div>" : "";
    var rows = rks[sub] || [];
    var pages = Math.max(1, Math.ceil(rows.length / PER_PAGE)); if (page > pages) page = pages;
    var link = rioPage(raid, sub);
    var base = "wow/" + sub;
    var body = rows.length ? staleNote((w.rankings_meta || {})[sub]) + pager(rows.length, page, base) + '<div class="rankbox"><table class="tbl"><thead><tr><th class="first c" title="Raider.IO mythic progress rank">#</th><th>Guild</th><th class="hide-sm">Realm</th><th title="mythic bosses killed">Progress</th><th class="n" title="date of the most recent new Mythic boss kill (PT)">Last New Kill</th></tr></thead><tbody>' +
      slicePage(rows, page).map(function (g) {
        var full = raid && g.kills === (raid.bosses || []).length;
        var fac = g.faction === "alliance" ? "ally" : g.faction === "horde" ? "horde" : "";
        return '<tr class="' + medal(g.rank) + '" data-k="' + esc("w:" + sub + ":" + g.rank) + '">' + rk(g.rank) + '<td class="team ' + fac + '">' + ilink(guildHash(sub, g), g.guild) +
          '</td><td class="hide-sm">' + esc(g.realm) + '</td><td class="' + (full ? "w" : "") + '">' + esc(g.progress) + '</td><td class="n">' + (g.last_first_kill ? fmt(g.last_first_kill, "md") : "&ndash;") + "</td></tr>";
      }).join("") + "</tbody></table></div>" + pager(rows.length, page, base) +
      '<div class="note">Guild names colored by faction (blue Alliance / red Horde). Dates in Pacific Time. ' + ext(link, "Full rankings on Raider.IO") + "</div>" : '<div class="empty">no rankings</div>';
    return gameHead("wow", sub, "World of Warcraft :: Mythic Raid Progression") + srcLine("wow") + info +
      '<h2 class="subhead">' + esc(sub.toUpperCase()) + " Mythic Rankings <small>top " + rows.length + "</small></h2>" + body;
  }

  function vNews(parts) {
    var sub = parts[0], page = pageOf(parts);
    var items = newsItems().map(function (n, i) { n._i = i; return n; });
    var tags = ["all"].concat(Array.from(new Set(items.map(function (i) { return String(i.tag || "").toLowerCase(); }))));
    if (tags.indexOf(sub) < 0) sub = "all";
    var tabs = [{ grp: "Filter" }].concat(tags.map(function (t) { return { id: t, hash: "news/" + t, label: t === "all" ? "All News" : t.toUpperCase() }; }));
    var shown = items.filter(function (n) { return sub === "all" || String(n.tag || "").toLowerCase() === sub; });
    var pages = Math.max(1, Math.ceil(shown.length / PER_PAGE)); if (page > pages) page = pages;
    var base = "news/" + sub;
    var body = shown.length ? pager(shown.length, page, base) + '<div class="listbox">' + slicePage(shown, page).map(function (n) {
      return '<div class="item' + (n.stale ? " is-stale" : "") + '" data-k="n:' + n._i + '"><span class="tag ' + esc(slug(n.tag)) + '">' + esc(n.tag) + '</span><span class="when">' + (n.date ? fmt(n.date, "short") : "") + "</span>" + ext(n.url, n.title, "ttl") +
        '<span class="src">' + esc(n.source) + "</span></div>";
    }).join("") + "</div>" + pager(shown.length, page, base) : '<div class="empty">no headlines</div>';
    return std("Esports Scoreboard News Wire", shown.length + " headlines", toolbar(tabs, sub) + srcLine("news")) + body;
  }

  function vSearch(q) {
    q = (q || "").trim().slice(0, MAX_Q);
    if ($("#q").value.trim() !== q && document.activeElement !== $("#q")) $("#q").value = q;
    var ql = fold(q);
    if (ql) { loadTeams(); loadVal(); }
    var hits = ql ? IDX.concat(lazyIdx()).filter(function (x) { return fold(x.text + " " + x.label).indexOf(ql) >= 0; }) : [];
    var lazyBusy = ql && (TX_STATE === "loading" || VX_STATE === "loading");
    var groups = {};
    hits.forEach(function (h) { (groups[h.g] = groups[h.g] || []).push(h); });
    // highlight on the raw text, escaping each piece (never regex over escaped HTML)
    function hl(s) {
      s = String(s);
      if (!ql) return esc(s);
      var low = Array.prototype.map.call(s, function (c) { var f = fold(c); return f.length === 1 ? f : "\u0000"; }).join(""), out = "", i = 0, j;
      while ((j = low.indexOf(ql, i)) >= 0) { out += esc(s.slice(i, j)) + "<mark>" + esc(s.slice(j, j + ql.length)) + "</mark>"; i = j + ql.length; }
      return out + esc(s.slice(i));
    }
    var body = !ql ? '<div class="empty">Type in the SEARCH FRAGNET box (top right) &mdash; teams, players, guilds, headlines &mdash; and press GO.</div>' + recentHtml() :
      !hits.length ? '<div class="empty' + (lazyBusy ? ' loading">Searching all players&hellip;' : '">No matches for &ldquo;' + esc(q) + "&rdquo;.") + "</div>" :
      Object.keys(groups).map(function (g) {
        return '<div class="sr-group"><div class="sr-h">' + esc(g) + " (" + groups[g].length + ')</div><ul class="sr-list">' + groups[g].slice(0, 40).map(function (h) {
          return '<li><a href="#' + esc(h.hash) + '"' + (h.key ? ' data-hl="' + esc(h.key) + '"' : "") + ">" + hl(h.label) + '</a><span class="where">' + esc(h.where) + (h.ext && safeUrl(h.ext) !== "#" ? " &middot; " + ext(h.ext, "source") : "") + "</span></li>";
        }).join("") + (groups[g].length > 40 ? '<li class="empty">&hellip; ' + (groups[g].length - 40) + " more, refine your search</li>" : "") + "</ul></div>";
      }).join("");
    return std("Search Results", ql ? hits.length + " match" + (hits.length === 1 ? "" : "es") + " for &ldquo;" + esc(q) + "&rdquo;" : "", '<div class="std-cap"></div>') + body;
  }

  /* ----- detail pages: CS2 team / CS2 player / Valorant team / WoW guild ----- */
  function vTeamCS(id) {
    var f = findCsTeam(id), s = (D.cs && D.cs.season) || {};
    loadTeams();
    if (!f) {
      var known = csPlayers().filter(function (p) { return p.team_id && p.team_id === id; });
      var nm = known.length ? known[0].team : "";
      var anyM = csFinished().concat(csUpcoming()).filter(function (m) { return involves(m, id); });
      if (!nm && anyM.length) nm = anyM[0].t1.id === id ? anyM[0].t1.name : anyM[0].t2.name;
      if (anyM.length) return std(esc(nm), "CS2 &middot; ESEA League team", '<div class="empty">' + esc(nm) + " is not in the current ESEA standings Esports Scoreboard shows, so there is no standings line or roster here." +
        (known.length ? "<br>Ranked players from this team: " + known.map(function (p) { return ilink(playerHash(p.nick), p.nick); }).join(", ") + "." : "") + "</div>") + teamMatchesHtml(id) +
        '<div class="note">' + (UUID_RE.test(id) ? ext("https://www.faceit.com/en/teams/" + id, "Team page on FACEIT") + " &middot; " : "") + '<a href="#cs2">ESEA standings</a></div>';
      return notFound(nm || "Team not tracked", (nm ? "<b>" + esc(nm) + "</b> is" : "This team is") + " not in the standings Esports Scoreboard shows (EU and NA Advanced, Main and Intermediate). No standings or roster data for it in the current data." +
        (known.length ? "<br>Ranked players from this team: " + known.map(function (p) { return ilink(playerHash(p.nick), p.nick); }).join(", ") + "." : ""),
        (UUID_RE.test(id) ? ext("https://www.faceit.com/en/teams/" + id, "Team page on FACEIT") + " &middot; " : "") + '<a href="#cs2">ESEA standings</a>');
    }
    var fl = csForm(csTeamId(f.t)), sk = streak(fl);
    var t = f.t, d = f.d, r = t.roster, lead = t.leader, x = teamsX(), xr = x && x.rosters && x.rosters[csTeamId(t)];
    if (!r && xr) { r = (xr.r || []).map(function (a) { return { nick: a[0], country: a[1], sub: !!a[2] }; }); lead = xr.lead; }
    var rosterPending = !r && TX_STATE !== "ok" && TX_STATE !== "fail";
    r = r || [];
    var line = '<b>#' + esc(t.rank) + "</b> in " + esc(d.region + " " + d.division) + " " + esc(d.stage) + " &middot; " + '<span class="w">' + num(t.w) + 'W</span> <span class="l">' + num(t.l) + "L</span>" + (num(t.t) ? " " + num(t.t) + "T" : "") + " &middot; " + num(t.pts) + " pts &middot; rounds " + esc(t.rounds) + (t.dq ? ' &middot; <span class="cc dq">DQ</span>' : "");
    var info = kv([
      ["Tag", esc(t.tag || "-")],
      ["Country", esc(t.country ? countryName(t.country) + " (" + t.country + ")" : "-")],
      ["Division", ilink("cs2/" + divId(d), d.region + " " + d.division) + (t.conf ? " &middot; " + esc(t.conf) + " conference" : (d.conferences || []).length === 1 ? " &middot; " + esc(d.conferences[0]) + " conference" : "")],
      ["Season", esc(s.name || "?") + (s.start ? " (" + fmt(s.start, "md") + " &ndash; " + fmt(s.end, "md") + ")" : "")],
      ["Standings", line],
      ["Form", formHtml(fl) + (fl.length ? ' <span class="dim">last ' + Math.min(5, fl.length) + ", newest right</span>" : "")]
    ]);
    var stats = {}; allCsPlayers().forEach(function (p) { if (p.division === d.division && p.region === d.region || !stats[String(p.nick).toLowerCase()]) stats[String(p.nick).toLowerCase()] = p; });
    var roster = r.length ? '<div class="rankbox"><table class="tbl"><thead><tr><th class="first">Player</th><th>Country</th><th>Role</th><th class="n" title="kills per death, season to date">K/D</th><th class="n hide-sm" title="average damage per round">ADR</th></tr></thead><tbody>' +
      r.map(function (m) {
        var p = stats[String(m.nick).toLowerCase()];
        return "<tr><td class=\"team\">" + ilink(playerHash(m.nick), m.nick) + '</td><td title="' + esc(countryName(m.country)) + '">' + esc(m.country || "") + "</td><td>" + (m.sub ? "Substitute" : "Player") + (lead === m.nick ? " &middot; Captain" : "") +
          '</td><td class="n">' + (p ? csPc(p, "kd") + (num(p.rounds) < MINR() ? '<span class="dim" title="few rounds">*</span>' : "") : '<span class="dim">&ndash;</span>') + '</td><td class="n hide-sm">' + (p ? num(p.adr).toFixed(1) : '<span class="dim">&ndash;</span>') + "</td></tr>";
      }).join("") + '</tbody></table></div><div class="note">League roster as registered on FACEIT for this conference. K/D and ADR season to date (* = fewer than ' + MINR() + " rounds); &ndash; = no matches with stats yet.</div>"
      : rosterPending ? '<div class="empty loading">Loading roster&hellip;</div>' : '<div class="empty">No roster in the public FACEIT league data for this team.</div>';
    var tl = tiles([["Rank in " + d.region + " " + d.division, "#" + esc(t.rank), num(t.rank) <= 3 ? "hi" : ""], ["Record", '<span class="w">' + num(t.w) + '</span>-<span class="l">' + num(t.l) + "</span>" + (num(t.t) ? "-" + num(t.t) : "")], ["Points", num(t.pts)],
      sk ? ["Streak", '<span class="' + (sk[0] === "W" ? "w" : sk[0] === "L" ? "l" : "") + '">' + sk + "</span>"] : ["Rounds", esc(t.rounds || "-")]]);
    setCrumbs([["CS2", "cs2"], [d.region + " " + d.division, "cs2/" + divId(d)], [t.name]]);
    return std(esc(t.name), "CS2 &middot; ESEA League team " + (csTeamId(t) ? star("cs:" + csTeamId(t), t.name, true) : ""), tl + info) + '<h2 class="subhead">Roster</h2>' + roster + teamMatchesHtml(t.id || csTeamId(t)) +
      '<div class="note">' + ext(teamFaceitUrl(t), "Team page on FACEIT") + " &middot; " + ext(d.link, "Standings on FACEIT") + "</div>";
  }

  function vPlayerCS(nick) {
    var p = findCsPlayer(nick), spot = findRosterSpot(nick);
    if (!p) loadTeams();                                   // Main/Intermediate stats + rosters are in teams.js
    if (!p && TX_STATE === "loading") return std(esc(nick), "CS2 &middot; ESEA League player", '<div class="empty loading">Loading player&hellip;</div>');
    p = p || findCsPlayer(nick); spot = spot || findRosterSpot(nick);
    if (!p && !spot) return notFound("Player not tracked", "No player named &ldquo;" + esc(nick) + "&rdquo; in Esports Scoreboard's data (rosters and season stats of the ESEA teams shown).", '<a href="#cs2/players">Top fraggers</a>');
    var name = p ? p.nick : spot.m.nick, pm = (D.cs && D.cs.top_players_meta) || {};
    var teamCell = spot ? csTeamLink(spot.t) + ' <span class="dim">(' + esc(spot.d.region + " " + spot.d.division) + ")</span>" :
      p.team ? (p.team_id ? ilink("team/cs2/" + encodeURIComponent(p.team_id), p.team) : esc(p.team)) : '<span class="dim">not found in the public rosters</span>';
    var info = kv([
      ["Team", teamCell],
      spot ? ["Role", spot.m.sub ? "Substitute" : "Player" + (spot.t.leader === spot.m.nick ? " &middot; Captain" : "")] : null,
      spot && spot.m.country ? ["Country", esc(countryName(spot.m.country) + " (" + spot.m.country + ")")] : null,
      p ? ["Stats group", esc(p.region + " " + p.division)] : null
    ]);
    var few = p && num(p.rounds) < MINR();
    var rankCell = p && p.drank ? "<b>#" + num(p.drank) + '</b><span class="cc">of ' + num(p.dpool) + "</span>" : '<span class="dim" title="fewer than ' + MINR() + ' rounds">&ndash;</span>';
    var st = p ? '<div class="rankbox"><table class="tbl pstats"><thead><tr><th class="first c" title="rank by K/D in the division (min. ' + MINR() + ' rounds)">Rank</th><th class="n">Matches</th><th class="n">Rounds</th><th class="n">K</th><th class="n">D</th><th class="n">K/D</th><th class="n">ADR</th><th class="n">HS%</th></tr></thead><tbody><tr>' +
      '<td class="c">' + rankCell + '</td><td class="n">' + num(p.matches) + '</td><td class="n">' + num(p.rounds) + '</td><td class="n">' + num(p.kills) + '</td><td class="n">' + num(p.deaths) +
      '</td><td class="n">' + csPc(p, "kd") + '</td><td class="n">' + csPc(p, "adr") + '</td><td class="n">' + Math.round(num(p.hs)) + "%</td></tr></tbody></table></div>" +
      (few ? '<div class="note few-rounds">Few rounds so far (' + num(p.rounds) + "): too small a sample to rank (min. " + MINR() + " rounds).</div>" : "") +
      '<div class="note">Season to date in ESEA ' + esc(p.region + " " + p.division) + (p.drank ? ", ranked by K/D among " + num(p.dpool) + " players with at least " + MINR() + " rounds" : "") + ". Stats as published on FACEIT" + (pm.fetched_at ? ", fetched " + fmt(pm.fetched_at, "short") : "") + ".</div>"
      : '<div class="empty">No season stats yet: ' + esc(name) + " has not played an ESEA match with stats this season.</div>";
    var link = (p && p.url) || "https://www.faceit.com/en/players/" + encodeURIComponent(name);
    var tl = p ? tiles([["K/D", num(p.kd).toFixed(2), "hi"], ["ADR", num(p.adr).toFixed(1)], ["HS%", Math.round(num(p.hs)) + "%"], p.drank ? ["Div. rank", "#" + num(p.drank)] : ["Rounds", num(p.rounds)]]) : "";
    setCrumbs([["CS2", "cs2"], spot ? [spot.d.region + " " + spot.d.division, "cs2/" + divId(spot.d)] : ["Top Players", "cs2/players"], spot ? [spot.t.name, teamHash(spot.t) || null] : null, [name]]);
    return std(esc(name), "CS2 &middot; ESEA League player", tl + info) + '<h2 class="subhead">Season Stats</h2>' + st + playerMatchesHtml(name) +
      '<div class="note">' + ext(link, "Profile on FACEIT") + ' &middot; <a href="#cs2/players">Top fraggers</a></div>';
  }

  function vTeamVal(sl) {
    var v = valTeamData(sl);
    if (!v.name) return notFound("Team not tracked", "No Valorant team &ldquo;" + esc(sl) + "&rdquo; in the current results or event standings.", '<a href="#valorant">Valorant</a>');
    var w = 0, l = 0;
    v.results.forEach(function (m) { var me = slug(m.team1) === sl ? 0 : 1; if (m.winner === me) w++; else if (m.winner === 0 || m.winner === 1) l++; });
    var info = kv([
      v.country ? ["Country / region", esc(v.country)] : null,
      ["Recent series", v.results.length ? '<span class="w">' + w + 'W</span> <span class="l">' + l + "L</span> in the " + v.results.length + " tier-2 results Esports Scoreboard tracks" : '<span class="dim">none in the tracked results</span>'],
      ["Form", formHtml(valForm(v.name))],
      ["vlr.gg", v.url ? ext(v.url, "Team page on vlr.gg") : '<span class="dim">no team link in the scraped data</span> &middot; ' + ext("https://www.vlr.gg/search/?q=" + encodeURIComponent(v.name), "search vlr.gg")]
    ]);
    var pl = v.placings.length ? '<div class="rankbox"><table class="tbl"><thead><tr><th class="first c">Place</th><th>Event</th><th class="n">Prize</th><th class="hide-sm">Qualified / Points</th></tr></thead><tbody>' +
      v.placings.map(function (x) {
        return '<tr class="' + medal(x.t.place) + '">' + rk(x.t.place) + '<td class="team">' + ilink("valorant/" + evId(x.i), x.ev.title) + '<span class="cc">' + esc(x.ev.dates) + '</span></td><td class="n">' + esc(x.t.prize) + '</td><td class="hide-sm">' + esc([x.t.points, x.t.note].filter(Boolean).join(" ")) + "</td></tr>";
      }).join("") + "</tbody></table></div>" : '<div class="empty">No final placings in the events Esports Scoreboard tracks.</div>';
    loadVal();
    var vx = valX(), tm = vx && vx.bySlug[sl], ros;
    if (!vx && VX_STATE === "loading") ros = '<div class="empty loading">Loading roster&hellip;</div>';
    else if (tm && (tm.roster || []).length) {
      var st = {}; (vx.agg || []).forEach(function (p) { if (p.pid) st[p.pid] = p; });
      ros = '<div class="rankbox"><table class="tbl val-roster"><thead><tr><th class="first">Player</th><th>Role</th><th class="n" title="vlr.gg rating across the tracked events">R</th><th class="n hide-sm">ACS</th><th class="n hide-sm">Rnd</th></tr></thead><tbody>' +
        tm.roster.map(function (m) {
          var p = st[m[1]], staff = /coach|manager|analyst/.test(m[2] || "");
          return '<tr><td class="team">' + (staff ? esc(m[0]) : ilink(valPHash(m[0]), m[0])) + "</td><td>" + esc(m[2] ? m[2].charAt(0).toUpperCase() + m[2].slice(1) : "Player") + '</td><td class="n">' + (p ? valPc(p) : '<span class="dim">&ndash;</span>') +
            '</td><td class="n hide-sm">' + (p ? Math.round(num(p.acs)) : '<span class="dim">&ndash;</span>') + '</td><td class="n hide-sm">' + (p ? num(p.rnd) : '<span class="dim">&ndash;</span>') + "</td></tr>";
        }).join("") + '</tbody></table></div><div class="note">Current roster from the team page on vlr.gg' + (tm.fetched_at ? " (checked " + fmt(tm.fetched_at, "short") + ")" : "") + "; stats across the tracked events, &ndash; = no tracked event stats.</div>";
      if (!v.url) v.url = tm.url;
    } else ros = '<div class="empty">Roster not available yet.</div>';
    if (tm) info = kv([tm.tag ? ["Tag", esc(tm.tag)] : null, (tm.country || v.country) ? ["Country / region", esc(tm.country || v.country)] : null,
      ["Recent series", v.results.length ? '<span class="w">' + w + 'W</span> <span class="l">' + l + "L</span> in the " + v.results.length + " tier-2 results Esports Scoreboard tracks" : '<span class="dim">none in the tracked results</span>'],
      ["Form", formHtml(valForm(v.name))],
      ["vlr.gg", ext(tm.url || v.url, "Team page on vlr.gg")]]);
    var vsk = streak(valForm(v.name));
    var tl = tiles([v.results.length ? ["Recent series", '<span class="w">' + w + '</span>-<span class="l">' + l + "</span>"] : null, vsk ? ["Streak", '<span class="' + (vsk[0] === "W" ? "w" : "l") + '">' + vsk + "</span>"] : null, tm && tm.roster ? ["Roster", tm.roster.filter(function (m) { return !/coach|manager|analyst/.test(m[2] || ""); }).length] : null, tm && (tm.tag || v.country || tm.country) ? [tm.tag ? "Tag" : "Region", esc(tm.tag || tm.country || v.country)] : null]);
    setCrumbs([["Valorant", "valorant"], ["Events", "valorant/events"], [v.name]]);
    return std(esc(v.name), "Valorant &middot; team " + star("val:" + sl, v.name, true), tl + info) + '<h2 class="subhead">Roster</h2>' + ros + '<h2 class="subhead">Event Placings</h2>' + pl +
      '<h2 class="subhead">Recent Results</h2>' + (v.results.length ? resultsTable(v.results, 0, false, true) : '<div class="empty">No results for this team in the tracked tier-2 results.</div>') +
      '<div class="note">Results and placings as listed on vlr.gg; dates in Pacific Time.</div>';
  }

  function vPlayerVal(name) {
    loadVal();
    var vx = valX();
    if (!vx) return VX_STATE === "fail" ? notFound("Player not tracked", "Valorant player data could not be loaded right now.", '<a href="#valorant/players">Top players</a>')
      : std(esc(name), "Valorant &middot; player", '<div class="empty loading">Loading player&hellip;</div>');
    var n = String(name).toLowerCase(), cands = vx.agg.filter(function (p) { return String(p.name).toLowerCase() === n; });
    var onRoster = null;
    Object.keys(vx.teams).forEach(function (id) { (vx.teams[id].roster || []).forEach(function (m) { if (String(m[0]).toLowerCase() === n && !onRoster) onRoster = { t: vx.teams[id], m: m }; }); });
    if (!cands.length && !onRoster) return notFound("Player not tracked", "No Valorant player named &ldquo;" + esc(name) + "&rdquo; in the events Esports Scoreboard tracks.", '<a href="#valorant/players">Top players</a>');
    cands.sort(function (a, b) { return num(b.rnd) - num(a.rnd); });
    var p = cands[0], team = (p && p.team && vx.teams[p.team]) || (onRoster && onRoster.t);
    var pid = p ? p.pid : onRoster.m[1], nm = p ? p.name : onRoster.m[0];
    var info = kv([
      ["Team", team ? ilink(valHash(team.name), team.name) + (team.tag ? ' <span class="dim">(' + esc(team.tag) + ")</span>" : "") : '<span class="dim">not on a tracked team roster</span>'],
      p && p.cc ? ["Country", esc(countryName(p.cc) + " (" + p.cc + ")")] : null,
      p && (p.agents || []).length ? ["Main agents", agentsHtml(p.agents)] : null,
      p && p.rank ? ["Top players rank", ilink("valorant/players", "#" + p.rank) + " of " + num(((D.valorant || {}).top_players_meta || {}).pool || 0)] : null
    ]);
    var st = p ? '<div class="rankbox"><table class="tbl pstats"><thead><tr><th class="first n">Maps</th>' + VAL_TH + '<th class="n hide-sm">K</th><th class="n hide-sm">D</th></tr></thead><tbody><tr><td class="n">' + num(p.maps) + "</td>" + valStatCells(p) +
      '<td class="n hide-sm">' + num(p.k) + '</td><td class="n hide-sm">' + num(p.d) + "</td></tr></tbody></table></div>" +
      (num(p.rnd) < 100 ? '<div class="note few-rounds">Few rounds so far (' + num(p.rnd) + "): too small a sample to rank (min. 100 rounds).</div>" : "") : '<div class="empty">No stats yet: ' + esc(nm) + " has not played in the events Esports Scoreboard tracks.</div>";
    var lines = vx.lines.filter(function (l) { return pid ? l.pid === pid : String(l.name).toLowerCase() === n; });
    var ev = lines.length ? '<div class="rankbox"><table class="tbl"><thead><tr><th class="first">Event</th><th class="hide-sm">Agents</th>' + VAL_TH + "</tr></thead><tbody>" + lines.map(function (l) {
      var e = valEvById(l.ev);
      return '<tr><td class="team">' + (e ? ilink("valorant/" + evId(e.i), shortEv(e.e.title)) : esc(l.ev)) + (l.tag ? '<span class="cc">' + esc(l.tag) + "</span>" : "") + '</td><td class="hide-sm dim">' + agentsCell(l.agents) + "</td>" + valStatCells(l) + "</tr>";
    }).join("") + "</tbody></table></div>" : "";
    var link = pid ? "https://www.vlr.gg/player/" + encodeURIComponent(pid) : "https://www.vlr.gg/search/?q=" + encodeURIComponent(nm);
    var tl = p ? tiles([["Rating", num(p.rating).toFixed(2), "hi"], ["ACS", Math.round(num(p.acs))], ["K/D", p.kd == null ? "&ndash;" : num(p.kd).toFixed(2)], ["KAST", Math.round(num(p.kast)) + "%"]]) : "";
    setCrumbs([["Valorant", "valorant"], ["Top Players", "valorant/players"], [nm]]);
    return std(esc(nm), "Valorant &middot; player", tl + info) + '<h2 class="subhead">Stats (tracked events)</h2>' + st + (ev ? '<h2 class="subhead">By Event</h2>' + ev : "") +
      '<div class="note">Round-weighted across the tracked Challengers / Game Changers events. Stats as published on vlr.gg &middot; ' + ext(link, "Profile on vlr.gg") + ' &middot; <a href="#valorant/players">Top players</a></div>';
  }

  function vGuild(region, realm, name) {
    var g = findGuild(region, realm, name), raid = (D.wow && D.wow.raid) || {};
    if (!g) return notFound("Guild not tracked", "No guild &ldquo;" + esc(name) + "&rdquo; (" + esc(region.toUpperCase()) + " " + esc(realm) + ") in the current top " + (((D.wow || {}).rankings || {})[region] || []).length + " Mythic rankings.", '<a href="#wow">Raid rankings</a>');
    var fac = g.faction === "alliance" ? "Alliance" : g.faction === "horde" ? "Horde" : "-";
    var full = (raid.bosses || []).length && g.kills === raid.bosses.length;
    var info = kv([
      ["Realm", esc(g.realm)],
      ["Region", esc(region.toUpperCase())],
      ["Faction", '<span class="' + (g.faction === "alliance" ? "ally" : g.faction === "horde" ? "horde" : "") + '">' + esc(fac) + "</span>"],
      ["Progress", '<span class="' + (full ? "w" : "") + '"><b>' + esc(g.progress) + "</b></span> " + esc(raid.name || "")],
      ["Rank", "#" + num(g.rank) + " " + esc(region.toUpperCase()) + " Mythic (" + ilink("wow/" + region + (Math.ceil(num(g.rank) / PER_PAGE) > 1 ? "/p" + Math.ceil(num(g.rank) / PER_PAGE) : ""), "rankings") + ")"],
      ["Last new kill", g.last_first_kill ? fmt(g.last_first_kill) : "&ndash;"]
    ]);
    var kd = g.kill_dates, bosses = raid.bosses || [];
    var tbl = kd && kd.length ? '<div class="rankbox"><table class="tbl"><thead><tr><th class="first c">#</th><th>Boss (Mythic)</th><th class="n" title="first Mythic kill, Pacific Time">First kill</th></tr></thead><tbody>' +
      bosses.map(function (b, i) {
        return '<tr><td class="c">' + (i + 1) + '</td><td class="' + (kd[i] ? "w" : "dim") + '">' + esc(b) + '</td><td class="n">' + (kd[i] ? fmt(kd[i]) : '<span class="dim">not yet</span>') + "</td></tr>";
      }).join("") + "</tbody></table></div>" : '<div class="empty">No boss kill dates in the current data.</div>';
    var tl = tiles([["Progress", esc(g.progress), full ? "hi" : ""], [region.toUpperCase() + " rank", "#" + num(g.rank)], ["Faction", esc(fac)]]);
    setCrumbs([["WoW", "wow"], [region.toUpperCase() + " Rankings", "wow/" + region], [g.guild]]);
    return std(esc(g.guild), "WoW &middot; Mythic raid guild", tl + info) + '<h2 class="subhead">' + esc(raid.name || "Current raid") + " :: Boss Kills</h2>" + tbl +
      '<div class="note">' + ext(g.url, "Guild profile on Raider.IO") + " &middot; kill dates from Raider.IO raid rankings, Pacific Time.</div>";
  }

  /* ----- forums (v5.0): GitHub Discussions index ----- */
  function vForums() {
    setCrumbs([["Forums"]]);
    if (CFG.forum && !forumX() && FX_STATE !== "fail") { loadForum(); return std("Community Forums", "GitHub Discussions", "") + '<div class="empty loading">Loading the forum list&hellip;</div>'; }
    var fx = forumX(), intro = '<div class="infobox forum-intro">The Esports Scoreboard forums live on <b>GitHub Discussions</b>: anyone can read, posting needs a free GitHub account.' +
      (CFG.giscus ? " Match, team and player pages have their own comment threads there too." : "") + '<div class="forum-btns"><a class="gbtn" href="' + esc(DISC_URL) + '" target="_blank" rel="noopener">Open the forums &#8599;</a> <a class="gbtn" href="' + esc(DISC_URL) + '/new/choose" target="_blank" rel="noopener">Start a discussion &#8599;</a></div></div>';
    var body = intro + discordBox("forums");
    if (!fx) return std("Community Forums", "GitHub Discussions", "") + body + '<div class="empty">The latest threads appear here after the next site update.</div>';
    var cats = (fx.categories || []).filter(function (c) { return c && c.name; });
    if (cats.length) body += '<h2 class="subhead">Categories</h2><div class="rankbox"><table class="tbl forum-cats"><thead><tr><th class="first">Category</th><th class="n" title="threads among the 30 most recently active">Recent threads</th></tr></thead><tbody>' + cats.map(function (c) {
      return '<tr><td class="team">' + ext(DISC_URL + "/categories/" + encodeURIComponent(c.slug || ""), c.name) + (c.desc ? '<div class="dim fdesc">' + esc(c.desc) + "</div>" : "") + '</td><td class="n">' + num(c.recent) + "</td></tr>";
    }).join("") + "</tbody></table></div>";
    var lt = (fx.latest || []).slice(0, 30);
    body += '<h2 class="subhead">Latest Threads</h2>' + (lt.length ? '<div class="rankbox"><table class="tbl forum-latest"><thead><tr><th class="first">Thread</th><th class="hide-sm">Category</th><th class="n">Replies</th><th class="hide-sm">Last activity</th></tr></thead><tbody>' + lt.map(function (d) {
      return '<tr><td class="team">' + ext(safeGh(d.url), d.title) + '<div class="dim fdesc">by ' + esc(d.author) + " &middot; " + fmt(d.created, "short") + '</div></td><td class="hide-sm">' + esc(d.cat) + '</td><td class="n">' + num(d.comments) + '</td><td class="hide-sm dim">' + fmt(d.updated, "short") + "</td></tr>";
    }).join("") + "</tbody></table></div>" : '<div class="empty">No threads yet &ndash; <a href="' + esc(DISC_URL) + '/new/choose" target="_blank" rel="noopener">start the first one</a>.</div>');
    return std("Community Forums", num(fx.total) + " threads", "") + body + '<div class="note">Thread list as of ' + fmt(fx.fetched_at, "short") + " (refreshed with every site update).</div>";
  }
  /* giscus comment threads on match, team and player pages (only when switched on in ESB_CONFIG) */
  function commentsBox(term) {
    var g = CFG.giscus;
    if (!g || !g.repo_id || !g.category_id || location.protocol !== "https:") return "";
    return '<h2 class="subhead" id="comments-h">Comments</h2><div class="comments" data-term="' + esc(term) + '"><div class="empty">Comments load when you scroll here (GitHub Discussions; posting needs a free GitHub account).</div></div>';
  }
  /* v5.3 "Share my card": the path page for this route carries the 1200x630 season card as og:image */
  function shareBox(route) {
    if (!/^https?:$/.test(location.protocol)) return "";
    return '<div class="share-card"><button type="button" class="gbtn share-btn" data-route="' + esc(route) + '">Share my card</button> <span class="share-msg" role="status"></span></div>';
  }
  function shareCard(btn) {
    var route = btn.getAttribute("data-route"), msg = btn.parentNode.querySelector(".share-msg");
    var page = new URL(route.split("/").map(function (x) { try { x = decodeURIComponent(x); } catch (e) {} return encodeURIComponent(x); }).join("/") + "/", document.baseURI).href;
    msg.textContent = "Preparing\u2026";
    fetch(page).then(function (r) { if (!r.ok) throw new Error("no page"); return r.text(); }).then(function (t) {
      var img = (t.match(/<meta property="og:image" content="([^"]+)"/) || [])[1], canon = (t.match(/<link rel="canonical" href="([^"]+)"/) || [])[1] || page;
      if (!img) { msg.textContent = "No season card for this page yet."; return; }
      img = img.replace(/&amp;/g, "&");
      var title = document.title;
      if (navigator.share) { navigator.share({ title: title, url: canon }).catch(function () {}); }
      else if (navigator.clipboard) { navigator.clipboard.writeText(canon).catch(function () {}); }
      msg.innerHTML = 'Link ready: <a href="' + esc(canon) + '">' + esc(canon.replace(/^https?:\/\//, "")) + '</a> (previews as your card) &middot; <a href="' + esc(img) + '" target="_blank" rel="noopener">Open card image &#8599;</a>';
    }).catch(function () { msg.textContent = "Card not available here."; });
  }
  document.addEventListener("click", function (ev) { var b = ev.target.closest && ev.target.closest(".share-btn"); if (b) shareCard(b); });
  /* v5.4 team-owned extras: extra.js is the reviewed teams-extra.json, validated at deploy (teams_extra.py) */
  var EX_STATE = "";
  function extraX() { return window.ESB_EXTRA || null; }
  function loadExtra() {
    if (EX_STATE || !CFG.extra) return;
    EX_STATE = "loading";
    var s = document.createElement("script");
    function done() { EX_STATE = extraX() ? "ok" : "fail"; if (/^#(team|recruiting)\//.test(curHash() + "/")) { KEEP_SCROLL = true; route(); } }
    s.src = "extra.js"; s.onload = done; s.onerror = done;
    document.body.appendChild(s);
  }
  var ISSUE_NEW = DISC_URL.replace(/\/discussions$/, "/issues/new");
  function okUrl(u, re) { return typeof u === "string" && re.test(u); }
  var SOC_RE = /^https:\/\/(x\.com|www\.twitch\.tv|www\.youtube\.com|discord\.gg|www\.faceit\.com)\//;
  function socLink(o) { return okUrl(o.url, SOC_RE) ? '<a href="' + esc(o.url) + '" target="_blank" rel="nofollow noopener ugc">' + esc(o.label) + " &#8599;</a>" : ""; }
  function teamExtraKey(parts) { return parts[0] === "cs2" ? "cs2:" + parts[1] : parts[0] === "val" ? "val:" + parts[1] : ""; }
  function teamExtraBox(parts) {
    var key = teamExtraKey(parts);
    if (!key) return "";
    if (CFG.extra && !extraX() && EX_STATE !== "fail") loadExtra();
    var x = extraX() && extraX().teams && extraX().teams[key], out = "";
    if (x) {
      var logo = okUrl(x.logo, /^https:\/\/[a-z0-9.-]+\/[^?#]+\.(png|jpe?g|webp|gif)$/i) ? '<img class="team-logo" src="' + esc(x.logo) + '" alt="" width="64" height="64" loading="lazy" referrerpolicy="no-referrer" decoding="async">' : "";
      var soc = (x.socials || []).map(function (o) { return '<span class="soc soc-' + esc(o.kind) + '">' + esc(o.kind) + " " + socLink(o) + "</span>"; }).join(" ");
      var rec = (x.recruiting || []).map(function (r) { return '<div class="rec-line"><span class="rec-tag">' + esc(r.type) + "</span> <b>" + esc(r.role) + "</b>" + (r.note ? " &middot; " + esc(r.note) : "") + (r.contact ? " &middot; " + socLink(r.contact) : "") + ' <span class="dim">(' + esc(r.updated) + ")</span></div>"; }).join("");
      out = '<h2 class="subhead">Team info</h2><div class="infobox team-extra">' + logo + '<div class="te-body">' + (soc ? '<div class="te-soc">' + soc + "</div>" : "") + rec + '<div class="dim te-note">Provided by the team, reviewed before publishing.</div></div></div>';
    }
    var q = "?template=claim-team.yml&title=" + encodeURIComponent("Claim: " + key) + "&team_url=" + encodeURIComponent(location.href.split("#")[0].replace(/[^/]*$/, "") + "#team/" + parts.join("/"));
    return out + '<div class="claim"><a href="' + esc(ISSUE_NEW + q) + '" target="_blank" rel="noopener">' + (x ? "Update this team&rsquo;s info" : "Claim this team") + ' &#8599;</a> <span class="dim">add a logo, socials or a recruiting note (GitHub account; reviewed by hand)</span></div>';
  }
  function vRecruiting() {
    setCrumbs([["Recruiting"]]);
    var post = '<div class="forum-btns"><a class="gbtn" href="' + esc(ISSUE_NEW) + '?template=recruiting-post.yml" target="_blank" rel="noopener">Post LFT / LFP &#8599;</a></div>';
    var intro = '<div class="infobox">LFP = team looking for a player, LFT = player looking for a team. Posts are sent as a GitHub issue and appear here after review. ' + post + "</div>";
    if (CFG.extra && !extraX() && EX_STATE !== "fail") { loadExtra(); return std("LFP / LFT Recruiting Board", "", intro + '<div class="empty loading">Loading&hellip;</div>'); }
    var x = extraX() || { teams: {}, players: [] }, rows = [];
    Object.keys(x.teams || {}).forEach(function (k) {
      var t = x.teams[k], g = k.split(":")[0], id = k.slice(g.length + 1);
      (t.recruiting || []).forEach(function (r) { rows.push({ r: r, who: ilink("team/" + (g === "cs2" ? "cs2/" + id : "val/" + id), t.name || id) }); });
    });
    (x.players || []).forEach(function (r) { rows.push({ r: r, who: esc(r.nick) }); });
    rows.sort(function (a, b) { return String(b.r.updated).localeCompare(String(a.r.updated)); });
    var tbl = rows.length ? '<div class="rankbox"><table class="tbl rec-board"><thead><tr><th class="first">Type</th><th>Who</th><th>Role</th><th class="hide-sm">Note</th><th>Contact</th><th class="hide-sm">Updated</th></tr></thead><tbody>' + rows.map(function (o) {
      var r = o.r;
      return '<tr><td><span class="rec-tag">' + esc(r.type) + "</span> " + (r.game === "val" ? "VAL" : "CS2") + '</td><td class="team">' + o.who + "</td><td>" + esc(r.role) + (r.region ? ' <span class="dim">' + esc(r.region) + "</span>" : "") + '</td><td class="hide-sm">' + esc(r.note) + "</td><td>" + (r.contact ? socLink(r.contact) : "") + '</td><td class="hide-sm dim">' + esc(r.updated) + "</td></tr>";
    }).join("") + "</tbody></table></div>" : '<div class="empty">No recruiting posts yet. Be the first: use &ldquo;Post LFT / LFP&rdquo; above.</div>';
    return std("LFP / LFT Recruiting Board", rows.length + " posts", intro + tbl);
  }
  function giscusTheme() { return new URL("giscus-" + (document.documentElement.getAttribute("data-theme") === "night" ? "night" : "classic") + ".css", document.baseURI).href; }
  function mountComments() {
    var box = $("#view .comments[data-term]"), g = CFG.giscus;
    if (!box || !g) return;
    function load() {
      if (box.dataset.loaded) return;
      box.dataset.loaded = "1";
      var s = document.createElement("script"), a = { "data-repo": CFG.repo, "data-repo-id": g.repo_id, "data-category": g.category, "data-category-id": g.category_id, "data-mapping": "specific",
        "data-term": box.getAttribute("data-term"), "data-strict": "1", "data-reactions-enabled": "1", "data-emit-metadata": "0", "data-input-position": "top", "data-theme": giscusTheme(), "data-lang": "en", "data-loading": "lazy", crossorigin: "anonymous" };
      s.src = "https://giscus.app/client.js"; s.async = true;
      Object.keys(a).forEach(function (k) { s.setAttribute(k, a[k]); });
      box.innerHTML = ""; box.appendChild(s);
    }
    if (window.IntersectionObserver) { var io = new IntersectionObserver(function (es) { if (es.some(function (x) { return x.isIntersecting; })) { io.disconnect(); load(); } }, { rootMargin: "300px" }); io.observe(box); }
    else load();
  }
  function retintComments() {
    var f = document.querySelector("iframe.giscus-frame");
    if (f && f.contentWindow) f.contentWindow.postMessage({ giscus: { setConfig: { theme: giscusTheme() } } }, "https://giscus.app");
  }

  /* ----- about (static text lives in index.html <template id="about-tpl">) ----- */
  function vAbout() {
    var tpl = $("#about-tpl");
    var live = "The data currently shown was updated " + fmt(D.fetched_at) + ".";
    return tpl ? tpl.innerHTML.replace("{{fetched}}", esc(live)) : std("About Esports Scoreboard", "", soon());
  }

  /* ----- site status (low-key page, linked only from the footer and About) ----- */
  function vStatus() {
    var secs = [["cs", "Counter-Strike 2 / FACEIT"], ["valorant", "Valorant / vlr.gg"], ["wow", "World of Warcraft / Raider.IO"], ["news", "News (RSS)"]];
    var st = D.status || [], c = { OK: 0, STALE: 0, MISS: 0 };
    st.forEach(function (s) { c[s.status] = (c[s.status] || 0) + 1; });
    var html = '<div class="infobox">Technical status of every data source in the latest update (' + fmt(D.fetched_at) + "): <b>" + c.OK + " OK</b>, <b>" + c.STALE + " STALE</b>, <b>" + c.MISS +
      " MISS</b>. The rest of the site only shows the data itself; this page is for anyone curious about where it comes from and how fresh it is.</div>";
    secs.forEach(function (sc) {
      var list = (D[sc[0]] || {}).sources || [];
      if (!list.length) return;
      html += '<h2 class="subhead">' + esc(sc[1]) + ' <small>updated ' + fmt((D[sc[0]] || {}).fetched_at, "short") + "</small></h2>" +
        '<div class="rankbox"><table class="tbl st-tbl"><colgroup><col class="c-st"><col class="c-src"><col class="c-cnt"><col class="c-when hide-sm"><col class="c-why"></colgroup><thead><tr><th class="first c">Status</th><th>Source</th><th class="n">Records</th><th class="hide-sm">Data from</th><th>Notes</th></tr></thead><tbody>' +
        list.map(function (s) {
          var why = s.status === "OK" ? (s.note || "") : (s.reason || "") + (s.note ? " - " + s.note : "");
          return '<tr><td class="c">' + badge(s.status) + "</td><td>" + ext(s.page || s.url, s.source) + '</td><td class="n">' + (s.status === "MISS" ? "&ndash;" : num(s.count)) + '</td><td class="hide-sm dim">' +
            fmt(s.status === "STALE" ? s.data_fetched_at : s.fetched_at, "short") + '</td><td class="dim st-why" title="' + esc(why) + '">' + esc(why) + "</td></tr>";
        }).join("") + "</tbody></table></div>";
    });
    html += '<h2 class="subhead">Status labels</h2><div class="rankbox"><table class="tbl about-st"><tbody>' +
      '<tr><td class="c"><span class="ok">OK</span></td><td>Fetched and read successfully in the latest update.</td></tr>' +
      '<tr><td class="c"><span class="stale-b">STALE</span></td><td>The latest update for this source failed, so the last good data is still shown (pages say &ldquo;Last updated&rdquo; with its date).</td></tr>' +
      '<tr><td class="c"><span class="miss-b">MISS</span></td><td>Not available: the source needs a login or key, blocks automated requests, or returned nothing usable. Pages show &ldquo;Not available yet&rdquo; / &ldquo;coming soon&rdquo; instead of guessing.</td></tr>' +
      "</tbody></table></div>";
    return std("Site status", "data sources", html) + '<div class="note"><a href="#about">About Esports Scoreboard</a> &middot; <a href="#home">Front page</a></div>';
  }

  /* ================= SIDEBARS / HEADER ================= */
  function renderGameNav() {
    var games = ["cs2", "valorant", "wow"].map(function (g) {
      var sc = SECTIONS[g];
      return '<details class="gn-item" data-gn="' + g + '"><summary><a href="#' + g + '">' + esc(sc.name) + '</a><span class="gn-caret" aria-hidden="true"></span></summary><ul class="gn-sub">' +
        sc.tabs.map(function (t) { return '<li><a href="#' + t[1] + '" data-sel="' + g + ":" + t[0] + '">' + esc(t[2]) + "</a></li>"; }).join("") + "</ul></details>";
    });
    var cs = games[0], val = games[1], wow = games[2];
    var news = '<div class="gn-item" data-gn="news"><a href="#news">News</a></div>';
    var forum = '<div class="gn-item" data-gn="forums"><a href="#forums">Forums</a></div>';
    var about = '<div class="gn-item" data-gn="about"><a href="#about">About</a></div>';
    $("#gamenav").innerHTML = cs + val + wow + '<div class="gn-sep"></div>' + news + forum + about;
  }
  function renderStatus() {
    if (!$("#data-status")) return;
    var secs = [["cs", "CS2 / FACEIT"], ["valorant", "Valorant / vlr.gg"], ["wow", "WoW / Raider.IO"], ["news", "News RSS"]];
    var st = D.status || [];
    var c = { OK: 0, STALE: 0, MISS: 0 };
    st.forEach(function (s) { c[s.status] = (c[s.status] || 0) + 1; });
    var html = '<div class="st-upd"><b>' + c.OK + " OK</b>" + (c.STALE ? ' / <b class="t-stale">' + c.STALE + " STALE</b>" : "") + ' / <b class="t-miss">' + c.MISS + " MISS</b> &middot; fetched " + fmt(D.fetched_at, "short") + "</div>";
    secs.forEach(function (sc) {
      var list = (D[sc[0]] || {}).sources || [];
      if (!list.length) return;
      html += '<div class="st-sec">' + esc(sc[1]) + '</div><ul class="side-menu">' + list.map(function (s) {
        var isOk = s.status === "OK";
        var name = s.source.replace(/\s*\((public web JSON|pages 1-\d+, [^)]*)\)/, "").replace(/^FACEIT ESEA /, "ESEA ").replace(/^vlr\.gg /, "vlr ");
        var tip = s.source + " - " + s.status + " - " + (isOk ? s.count + " records" : s.reason || "") + (s.note ? " - " + s.note : "") +
          (s.status === "STALE" ? " - data from " + fmt(s.data_fetched_at) : "") + " - checked " + fmt(s.fetched_at);
        return '<li class="st" title="' + esc(tip) + '">' + badge(s.status) + ext(s.page || s.url, name) + '<span class="cnt">' + (s.status === "MISS" ? "" : num(s.count)) + "</span>" +
          (isOk ? "" : '<span class="st-why">' + esc(s.reason || "") + "</span>") + "</li>";
      }).join("") + '</ul><div class="st-upd">updated ' + fmt((D[sc[0]] || {}).fetched_at, "short") + "</div>";
    });
    $("#data-status").innerHTML = html;
  }
  function renderSideNews() {
    var items = newsItems().slice(0, 8);
    $("#side-news").innerHTML = items.length ? items.map(function (n) {
      return '<li title="' + esc(n.title + " (" + n.source + ")") + '">' + ext(n.url, n.title) + '<span class="cnt">' + (n.date ? fmt(n.date, "md") : "") + "</span></li>";
    }).join("") : '<li class="empty">no headlines</li>';
  }
  function renderDiscordFoot() {
    var li = $("#discord-ft"), box = discordBox("x");
    if (!li || !box) return;
    li.innerHTML = '<a href="' + esc(CFG.discord) + '" target="_blank" rel="noopener"><span class="bullet">&raquo;</span> Discord &#8599;</a>';
    li.hidden = false;
  }
  function renderSideForum() {
    var fx = forumX(), lt = fx ? (fx.latest || []).slice(0, 6) : [];
    if (CFG.forum && !fx) loadForum();
    $("#side-forum").innerHTML = (lt.length ? lt.map(function (d) {
      return '<li title="' + esc(d.title) + '"><a href="' + esc(safeGh(d.url)) + '" target="_blank" rel="noopener">' + esc(d.title) + '</a><span class="cnt" title="replies">' + num(d.comments) + "</span></li>";
    }).join("") : '<li class="empty">No threads yet.</li>') + '<li class="note">Forums run on GitHub Discussions. <a href="' + esc(DISC_URL) + '" target="_blank" rel="noopener">Open the forums &#8599;</a></li>';
  }

  function renderTicker() {
    var bits = [];
    newsItems().slice(0, 10).forEach(function (i) { bits.push('<span class="it"><b>' + esc(i.source) + ":</b> " + ext(i.url, i.title) + "</span>"); });
    valResults().slice(0, 5).forEach(function (m) { bits.push('<span class="it"><b>VAL:</b> ' + esc(m.team1) + " " + esc(m.score1) + "-" + esc(m.score2) + " " + esc(m.team2) + "</span>"); });
    var w = D.wow && D.wow.rankings;
    if (w && w.us && w.us[0]) bits.push('<span class="it"><b>WoW:</b> US #1 ' + esc(w.us[0].guild) + " " + esc(w.us[0].progress) + "</span>");
    if (w && w.eu && w.eu[0]) bits.push('<span class="it"><b>WoW:</b> EU #1 ' + esc(w.eu[0].guild) + " " + esc(w.eu[0].progress) + "</span>");
    csDivs().filter(function (d) { return d.teams && d.teams.length; }).forEach(function (d) {
      bits.push('<span class="it"><b>ESEA ' + esc(d.region + " " + d.division) + ":</b> " + esc(d.teams[0].name) + (d.teams[0].rank === "1" ? " leads" : " tied for the lead") + " (" + num(d.teams[0].w) + "-" + num(d.teams[0].l) + ")</span>");
    });
    var html = bits.length ? bits.join("") : '<span class="it">no live data</span>';
    // second copy only exists for the seamless loop: hide it from screen readers and the tab order
    $("#tk").innerHTML = '<span class="tk-copy">' + html + '</span><span class="tk-copy" aria-hidden="true">' + html.replace(/<a /g, '<a tabindex="-1" ') + "</span>";
  }

  /* add a tooltip to any text that is visibly cut off with an ellipsis */
  var TRUNC = ".tbl td, .tbl td a, .newsbox .item a, .listbox .ttl, .listbox .src, .side-menu li a, .side-menu .st-why, .miss .why, .std-header h1, .sb-upd, .crumbs .subj, .sr-list .where";
  function autoTitles() {
    $$(TRUNC).forEach(function (el) {
      if (el.scrollWidth > el.clientWidth + 1) { if (!el.title) { el.title = el.textContent.trim(); el.dataset.autoTitle = "1"; } }
      else if (el.dataset.autoTitle) { el.removeAttribute("title"); delete el.dataset.autoTitle; }
    });
  }

  /* ================= ROUTER ================= */
  function parseHash() {
    var h = curHash().replace(/^#/, "");
    try { h = decodeURIComponent(h); } catch (e) {}
    var parts = h.split("/");
    return { top: parts[0] || "home", parts: parts.slice(1) };
  }
  var TITLES = { home: "Front Page", cs2: "Counter-Strike 2 :: ESEA League", valorant: "Valorant :: Challengers / Game Changers", wow: "World of Warcraft :: Mythic Raid Progression", news: "News", forums: "Forums", roundup: "Weekly Roundups", recruiting: "Recruiting", search: "Search", about: "About", team: "Team", player: "Player", guild: "Guild", match: "Match", status: "Site status" };
  function route() {
    var r = parseHash(), html;
    CRUMB = null; CUR_SEC = ""; FAVC = null;
    try {
      TODAY_SEL = null; TODAY_F = null;
      switch (r.top) {
        case "cs2": html = vCS2(r.parts); break;
        case "valorant": html = vValorant(r.parts); break;
        case "wow": html = vWow(r.parts); break;
        case "news": html = vNews(r.parts); break;
        case "forums": html = vForums(); break;
        case "roundup": html = vRoundup(r.parts); break;
        case "recruiting": html = vRecruiting(); break;
        case "about": html = vAbout(); break;
        case "team": html = r.parts[0] === "val" ? vTeamVal(r.parts.slice(1).join("/")) : vTeamCS(r.parts.slice(1).join("/")); break;
        case "player": html = r.parts[0] === "val" ? vPlayerVal(r.parts.slice(1).join("/")) : vPlayerCS(r.parts.slice(1).join("/")); break;
        case "match": html = r.parts[0] === "val" ? vMatchVal(r.parts.slice(1).join("/")) : vMatchCS(r.parts.slice(1).join("/")); break;
        case "guild": html = vGuild(r.parts[0] || "", r.parts[1] || "", r.parts.slice(2).join("/")); break;
        case "search": html = vSearch(r.parts.join("/")); break;
        case "status": html = vStatus(); break;
        case "status-box": r.top = "status"; html = vStatus(); break;
        default: r.top = "home"; html = vHome();
      }
    } catch (e) {
      if (window.console) console.warn("Esports Scoreboard: could not render view", e);
      html = std("Page unavailable", "", soon("This page could not be displayed right now.")) + '<div class="empty"><a href="#home">Back to the front page</a></div>';
    }
    if (r.top !== "home") {
      var tmp = document.createElement("div"); tmp.innerHTML = html;
      var th = tmp.querySelector(".std-header h1"), gm = { player: 1, team: 1, guild: 1, match: 1 };
      html = crumbHtml(CRUMB || [[gm[r.top] && th ? th.textContent : TITLES[r.top] || (th ? th.textContent : "Page")]]) + html;
    }
    if ((r.top === "team" || r.top === "player" || r.top === "match") && html.indexOf('class="miss"') < 0 && html.indexOf('class="empty loading"') < 0) html += (r.top === "team" && r.parts[0] === "cs2" ? rankLine(r.parts[1]) : "") + (r.top === "player" && r.parts[0] === "cs2" ? ratingLine(r.parts[1]) : "") + (r.top === "team" ? teamExtraBox(r.parts) : "") + (r.top !== "match" ? shareBox(r.top + "/" + r.parts.join("/")) : "") + commentsBox(r.top + "/" + r.parts.join("/"));
    $("#view").innerHTML = html;
    try { mountComments(); } catch (e) {}
    try { noteRecent(r); } catch (e) {}
    var gs = $('[data-sel="cs2:standings"]'); if (gs) gs.setAttribute("href", "#" + csHome());
    var h1 = $("#view .std-header h1");
    document.title = (r.top === "home" ? "" : (h1 ? h1.textContent + " :: " : TITLES[r.top] ? TITLES[r.top] + " :: " : "")) + (r.top === "home" ? "Esports Scoreboard :: Esports League Tracker" : "Esports Scoreboard");
    try { var nl = todayRows().filter(function (x) { return x.st === "live"; }).length; if (nl) document.title = "(" + nl + " live) " + document.title; } catch (e) {}
    var navTop = r.top === "search" ? "" : (r.top === "player" || r.top === "match" || r.top === "team") && r.parts[0] !== "val" ? "cs2" : r.top === "team" || r.top === "player" || r.top === "match" ? "valorant" : r.top === "guild" ? "wow" : r.top;
    $$("[data-nav]").forEach(function (a) { var on = a.dataset.nav === navTop; a.classList.toggle("on", on); if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    $$("[data-gn]").forEach(function (a) { a.classList.toggle("on", a.dataset.gn === navTop); });
    $$("[data-sel]").forEach(function (a) { a.classList.toggle("on", a.dataset.sel === CUR_SEC); });
    $$("details[data-gn]").forEach(function (d) { if (d.dataset.gn === navTop) d.open = true; });
    autoTitles();
    if (pendingHL) {
      var row = $('[data-k="' + (window.CSS && CSS.escape ? CSS.escape(pendingHL) : pendingHL.replace(/["\\]/g, "\\$&")) + '"]', $("#view"));
      pendingHL = null;
      if (row) { row.classList.add("flash"); row.scrollIntoView({ block: "center" }); return; }
    }
    var keep = KEEP_SCROLL; KEEP_SCROLL = false;
    if (!keep && r.top !== "home" && window.scrollY > $("#mesh").offsetTop) $("#mesh").scrollIntoView();
  }

  function today() {
    var p = ptParts(new Date());
    $("#today").textContent = DAYS[p.wd] + " " + MONTHS[p.m] + " " + p.d + " " + p.y + " " + pad(p.h) + ":" + pad(p.mi) + " " + p.tz;
  }

  /* v4.2 theme: default follows prefers-color-scheme; an explicit choice is kept in this browser */
  function initTheme() {
    var b = $("#theme-tg"), root = document.documentElement, mq = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;
    function stored() { try { return localStorage.getItem("esb-theme"); } catch (e) { return null; } }
    function paint() {
      var night = root.getAttribute("data-theme") === "night";
      if (b) { b.textContent = night ? "\u00bb Classic" : "\u00bb Night"; b.setAttribute("aria-pressed", night ? "true" : "false"); b.title = night ? "Switch to the classic light theme" : "Switch to the Night theme"; }
      var tc = document.querySelector('meta[name="theme-color"]'); if (tc) tc.setAttribute("content", night ? "#14171B" : "#0B0D10");
    }
    if (b) b.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "night" ? "classic" : "night";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("esb-theme", next); } catch (e) {}
      paint();
      try { retintComments(); } catch (e) {}
    });
    if (mq && mq.addEventListener) mq.addEventListener("change", function (e) { if (!stored()) { root.setAttribute("data-theme", e.matches ? "night" : "classic"); paint(); } });
    paint();
  }
  var LAST_FETCH = Date.now();
  function refreshData() {
    if (location.protocol === "file:" || !window.fetch || Date.now() - LAST_FETCH < 300000) return;
    LAST_FETCH = Date.now();
    fetch("data.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(function (nd) {
      if (!nd || !nd.fetched_at || nd.fetched_at === D.fetched_at) return;
      D = nd; RANKC = null; buildIndex();
      $("#hdr-upd").textContent = "updated " + fmt(D.fetched_at, "short");
      $("#foot-fetched").textContent = "updated " + fmt(D.fetched_at);
      KEEP_SCROLL = true; route();
    }).catch(function () {});
  }
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("button[data-pin]");
    if (!b) return;
    var id = b.getAttribute("data-pin"), p = pins(), i = p.indexOf(id);
    if (i >= 0) p.splice(i, 1); else p.push(id);
    lsSet("esb-pins", p.slice(0, 12));
    renderPinned(); renderBar(); KEEP_SCROLL = true; route();
  });
  document.addEventListener("keydown", function (ev) {
    if ((ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") || ev.altKey || ev.ctrlKey || ev.metaKey || /^(INPUT|TEXTAREA|SELECT)$/.test((ev.target || {}).tagName || "")) return;
    var on = document.querySelector("#view .day-strip .on");
    if (!on) return;
    var sib = ev.key === "ArrowLeft" ? on.previousElementSibling : on.nextElementSibling;
    if (sib && sib.tagName === "A") { ev.preventDefault(); location.hash = sib.getAttribute("href"); }
  });
  /* R10 installable app: service worker (http(s) only), footer Install link, honest offline note */
  if ("serviceWorker" in navigator && /^https?:$/.test(location.protocol) && !/^(localhost|127\.)/.test(location.hostname)) {
    window.addEventListener("load", function () { navigator.serviceWorker.register(new URL("sw.js", document.baseURI).href).catch(function () {}); });
  }
  var DEFER_INSTALL = null;
  window.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); DEFER_INSTALL = e; var li = $("#install-ft"); if (li) li.hidden = false; });
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("#install-a");
    if (!a || !DEFER_INSTALL) return;
    ev.preventDefault(); DEFER_INSTALL.prompt(); DEFER_INSTALL = null; $("#install-ft").hidden = true;
  });
  function offlineNote() {
    var n = $("#offline-note");
    if (!n) { n = document.createElement("div"); n.id = "offline-note"; n.className = "offline-note"; n.setAttribute("role", "status"); var v = $("#view"); if (v) v.parentNode.insertBefore(n, v); }
    n.hidden = navigator.onLine !== false;
    n.textContent = "Offline - showing data from " + (D && D.fetched_at ? fmt(D.fetched_at, "short") : "the last visit") + ".";
  }
  window.addEventListener("online", function () { try { offlineNote(); refreshData(); } catch (e) {} });
  window.addEventListener("offline", function () { try { offlineNote(); } catch (e) {} });
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible") refreshData(); });
  function boot(data) {
    D = data || {};
    buildIndex();
    $("#hdr-upd").textContent = "updated " + fmt(D.fetched_at, "short");
    initTheme();
    $("#foot-fetched").textContent = "updated " + fmt(D.fetched_at);
    var ql = $("#ql-rio"); if (ql && D.wow && D.wow.raid) ql.href = rioPage(D.wow.raid, "world");
    [renderGameNav, renderStatus, renderSideNews, renderSideForum, renderTicker, renderDiscordFoot, renderPinned, renderBar, offlineNote].forEach(function (fn) { try { fn(); } catch (e) { if (window.console) console.warn("Esports Scoreboard: sidebar render failed", e); } });
    window.addEventListener("hashchange", function () {
      clearTimeout(tmr); route(); renderSideForum();
      // optional visitor counter (only present when the build sets GOATCOUNTER_CODE): section only, no ids
      var sec = (curHash() || "#home").split("/")[0];
      if (window.goatcounter && window.goatcounter.count && sec !== LAST_SEC) { LAST_SEC = sec; window.goatcounter.count({ path: location.pathname + sec }); }
    });
    var rt; window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(autoTitles, 200); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(autoTitles);
    window.addEventListener("load", autoTitles);
    document.addEventListener("click", function (e) {
      var sb = e.target.closest && e.target.closest("button[data-fav]");
      if (sb) {
        e.preventDefault();
        var k = sb.getAttribute("data-fav"), big = sb.classList.contains("star-lg"), inMy = !!sb.closest("#my-matches");
        toggleFav(k, sb.getAttribute("data-n"));
        KEEP_SCROLL = true; route();
        var again = $$('button[data-fav]').filter(function (b) { return b.getAttribute("data-fav") === k && b.classList.contains("star-lg") === big && !!b.closest("#my-matches") === inMy; })[0];
        if (again) again.focus();
        return;
      }
      var sk = e.target.closest && e.target.closest("a.skip");
      if (sk) { e.preventDefault(); var pm = $("#pane-middle"); if (pm) { pm.focus(); pm.scrollIntoView(); } return; }   // in-page jump, not a route
      if (e.target.closest && e.target.closest("button.rv-clear")) { lsSet(LS.rec, null); KEEP_SCROLL = true; route(); return; }
      var a = e.target.closest && e.target.closest("[data-hl]");
      if (a && a.dataset.hl) pendingHL = a.dataset.hl;
    });
    $("#hsearch").addEventListener("submit", function (e) {
      e.preventDefault(); clearTimeout(tmr);
      location.hash = "#search/" + encodeURIComponent($("#q").value.trim().slice(0, MAX_Q));
      if (parseHash().top === "search") route();
    });
    $("#q").addEventListener("input", function () {
      clearTimeout(tmr);
      tmr = setTimeout(function () {
        var q = $("#q").value.trim().slice(0, MAX_Q);
        if (!q && parseHash().top !== "search") return;
        var target = "#search/" + encodeURIComponent(q);
        if (parseHash().top === "search") { history.replaceState(null, "", target); route(); }
        else if (q.length >= 2) location.hash = target;
      }, 300);
    });
    route();
    var pv = $("#view"); if (pv) pv.removeAttribute("data-prerender");   // static snapshot (prerender.py) has now been replaced
    document.documentElement.classList.remove("deep");
  }

  function fail() {
    var v = $("#view");
    if (v && v.hasAttribute("data-prerender")) { document.documentElement.classList.remove("deep"); return; }   // keep the static snapshot
    v.innerHTML = soon("Esports Scoreboard's data could not be loaded right now. Please try again later."); }
  /* data.js (same content as data.json) is used on file:// where fetch() is not allowed */
  function loadDataJs() {
    if (window.FRAGNET_DATA) return boot(window.FRAGNET_DATA);
    var s = document.createElement("script");
    s.src = "data.js";
    s.onload = function () { if (window.FRAGNET_DATA) boot(window.FRAGNET_DATA); else fail(); };
    s.onerror = fail;
    document.body.appendChild(s);
  }

  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest(".st-tab");
    if (!b) return;
    ev.preventDefault();
    lsSet("esb-today-tab", b.getAttribute("data-tab"));
    KEEP_SCROLL = true; route();
  });
  today(); setInterval(function () { today(); try { refreshRel(); } catch (e) {} }, 30000);
  if (location.protocol === "file:" || !window.fetch) loadDataJs();
  else fetch("data.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(boot, loadDataJs);
})();
