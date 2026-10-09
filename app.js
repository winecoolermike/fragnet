/* FragNet v4.2 - 2007-portal skin. Hash-routed, renders ONLY data.json (written
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
    cs2: { name: "Counter-Strike 2", short: "CS2", sub: "ESEA League", tabs: [["standings", "cs2", "Standings"], ["results", "cs2/results", "Results"], ["players", "cs2/players", "Top Players"], ["today", "cs2/today", "Matches Today", "Today"]] },
    valorant: { name: "Valorant", short: "Valorant", sub: "Challengers / Game Changers", tabs: [["events", "valorant/events", "Events"], ["results", "valorant/results", "Results"], ["players", "valorant/players", "Top Players"]] },
    wow: { name: "World of Warcraft", short: "WoW", sub: "Mythic raid race", tabs: [["us", "wow/us", "US Rankings"], ["eu", "wow/eu", "EU Rankings"]] }
  };
  var KEEP_SCROLL = false, CRUMB = null, CUR_SEC = "", LAST_SEC = (location.hash || "#home").split("/")[0];
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
      return '<a href="#' + t[1] + '"' + (on ? ' class="on" aria-current="page"' : "") + ">" + (t[3] ? '<span class="lg">' + esc(t[2]) + '</span><span class="sh">' + esc(t[3]) + "</span>" : esc(t[2])) + "</a>";
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
    function done(ok) { TX_STATE = ok && window.FRAGNET_TEAMS ? "ok" : "fail"; if (/^#((team|player)\/cs2\/|search|cs2(\/(?!results|players|today)|$))/.test(location.hash)) { KEEP_SCROLL = true; route(); } }
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
    function done(ok) { VX_STATE = ok && window.FRAGNET_VAL ? "ok" : "fail"; if (/^#(team\/val|player\/val|valorant\/players|search)/.test(location.hash)) route(); }
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
    return '<td class="n hide-sm">' + num(p.rnd) + '</td><td class="n">' + valPc(p) + '</td><td class="n">' + Math.round(num(p.acs)) + '</td><td class="n">' + (p.kd == null ? "&ndash;" : num(p.kd).toFixed(2)) +
      '</td><td class="n hide-sm">' + Math.round(num(p.kast)) + '%</td><td class="n hide-sm">' + num(p.adr).toFixed(1) + '</td><td class="n hide-sm">' + Math.round(num(p.hs)) + "%</td>";
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
  function csEmpty(what) {
    var s = csMatchSrc();
    if (!s || s.status === "MISS") return soon(/upcoming/.test(what) ? "Upcoming matches coming soon." : "Match results coming soon.");
    return '<div class="empty">No ' + what + " in the matches FragNet tracks.</div>";
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
          '<td class="n tm ' + (w1 ? "win" : "lose") + '">' + csSide(m.t1) + '</td><td class="score">' + (ru ? '<a href="' + esc(safeUrl(ru)) + '" target="_blank" rel="noopener" title="match room on FACEIT">' + sc + "</a>" : sc) + "</td>" +
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
      ". Dates in Pacific Time. Click a score for the FACEIT match room, a map for the scoreboard. Byes are not listed.</div>";
  }
  function vMatchCS(id) {
    var m = null;
    ((D.cs && D.cs.matches) || []).forEach(function (x) { if (x.id === id) m = x; });
    if (!m) return notFound("Match not tracked", "No finished ESEA match with this id in FragNet's data.", '<a href="#cs2/results">ESEA results</a>');
    var ru = roomUrl(m);
    var info = kv([
      ["Division", ilink("cs2/" + divOf(m), m.region + " " + m.division) + (m.conf ? " &middot; conference " + esc(m.conf) : "") + " &middot; round " + num(m.round) + " &middot; best of " + num(m.bo || 1)],
      ["Finished", m.t ? fmt(m.t) : "?"],
      ["Result", csSide(m.t1) + ' <b><span class="' + (m.winner === 1 ? "w" : "") + '">' + num(m.s1) + '</span>:<span class="' + (m.winner === 2 ? "w" : "") + '">' + num(m.s2) + "</span></b> " + csSide(m.t2)],
      ["FACEIT", ru ? ext(ru, "Match room on FACEIT") : "-"]
    ]);
    function board(lines, side) {
      return '<div class="rankbox"><table class="tbl sb"><thead><tr><th class="first">' + esc(side.name) + '</th><th class="n" title="kills">K</th><th class="n" title="deaths">D</th><th class="n" title="kills per death">K/D</th><th class="n" title="average damage per round">ADR</th><th class="n hide-sm" title="headshot kill percentage">HS%</th></tr></thead><tbody>' +
        (lines || []).map(function (p) {
          var kd = num(p[2]) ? num(p[1]) / num(p[2]) : num(p[1]);
          return '<tr><td class="team">' + ilink(playerHash(p[0]), p[0]) + '</td><td class="n">' + num(p[1]) + '</td><td class="n">' + num(p[2]) + '</td><td class="n"><b>' + kd.toFixed(2) + '</b></td><td class="n">' + num(p[3]).toFixed(1) + '</td><td class="n hide-sm">' + num(p[4]) + "%</td></tr>";
        }).join("") + "</tbody></table></div>";
    }
    var maps = (m.maps || []).map(function (x, i) {
      return '<h2 class="subhead">' + (m.maps.length > 1 ? "Map " + (i + 1) + ": " : "") + esc(x.map) + " <small>" + num(x.s1) + ":" + num(x.s2) + "</small></h2>" + board(x.p1, m.t1) + board(x.p2, m.t2);
    }).join("");
    setCrumbs([["CS2", "cs2"], ["Results", "cs2/results"], [m.t1.name + " vs " + m.t2.name]]);
    return std(esc(m.t1.name) + " vs " + esc(m.t2.name), "CS2 &middot; ESEA match", info) +
      (maps || '<div class="empty">' + (m.nostats ? "FACEIT published no match stats for this match (e.g. forfeit or technical result)." : "Match stats not fetched yet; they are added on a later refresh.") + "</div>") +
      '<div class="note">Scoreboard from the official FACEIT Data API; stats as published by FACEIT.</div>';
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

  /* ---------- forums: read-only for launch ----------
     Posting stays off until shared accounts + moderation exist. ForumBackend is the
     single seam for a future server API: implement topics(forumId) / topic(id) and,
     once FORUM_POSTING_ENABLED is true, add create/reply/remove plus the posting UI
     (see renderPostingUI). Nothing is read from or written to browser storage. */
  var FORUM_POSTING_ENABLED = false;
  var FORUM_NOTICE = "Forums coming soon. Posting opens once shared accounts and moderation are in place.";
  var ForumBackend = {
    postingEnabled: FORUM_POSTING_ENABLED,
    topics: function (forumId) { return []; },   // -> [{id, forum, subject, views, posts:[{author, body, at}]}]
    topic: function (id) { return null; }
  };
  var FORUMS = [
    { cat: "Counter-Strike 2 Forums", items: [{ id: "cs2", name: "ESEA League Discussion", desc: "Divisions, standings and teams in the ESEA League on FACEIT." }] },
    { cat: "Valorant Forums", items: [{ id: "valorant", name: "Challengers & Game Changers", desc: "Tier-2 circuits, Game Changers events and results." }] },
    { cat: "World of Warcraft Forums", items: [{ id: "wow", name: "Mythic Raid Progression", desc: "Guild progression, raid rankings and boss kills." }] },
    { cat: "General Forums", items: [{ id: "general", name: "General Discussion & Site Feedback", desc: "Anything else, plus feedback about FragNet." }] }
  ];
  function forumById(id) { for (var i = 0; i < FORUMS.length; i++) for (var j = 0; j < FORUMS[i].items.length; j++) if (FORUMS[i].items[j].id === id) return FORUMS[i].items[j]; return null; }
  function lastPost(t) { return t.posts[t.posts.length - 1]; }
  function byLast(a, b) { return String(lastPost(b).at).localeCompare(String(lastPost(a).at)); }
  function forumTopics(fid) {
    var ts = [];
    try { ts = ForumBackend.topics(fid) || []; } catch (e) { ts = []; }
    return ts.filter(function (t) { return t && t.id && t.posts && t.posts.length; });
  }

  /* ---------- reusable blocks ---------- */
  function resultsTable(rows, offset, compact, noKeys) {
    if (!rows.length) return '<div class="empty">no results</div>';
    return '<div class="rankbox"><table class="tbl res' + (compact ? " compact" : "") + '"><colgroup>' + (compact ? "" : '<col class="c-date hide-sm">') + '<col class="c-team"><col class="c-score"><col class="c-team">' + (compact ? "" : '<col class="c-ev hide-sm">') + '</colgroup><thead><tr>' + (compact ? "" : '<th class="first hide-sm" title="match start, Pacific Time">Date</th>') + '<th class="n">Team 1</th><th class="c">Score</th><th>Team 2</th>' + (compact ? "" : '<th class="hide-sm">Event</th>') + "</tr></thead><tbody>" +
      rows.map(function (m, j) {
        var w1 = m.winner === 0, w2 = m.winner === 1;
        return "<tr" + (noKeys ? "" : ' data-k="vr:' + (offset + j) + '"') + ">" + (compact ? "" : '<td class="hide-sm dim" title="' + esc(m.ts ? fmt(m.ts) : (m.date + " " + m.time + " (US Central, as listed on vlr.gg)")) + '">' + resDate(m) + "</td>") +
          '<td class="n ' + (w1 ? "win" : "lose") + '">' + ilink(valHash(m.team1), m.team1) + '</td><td class="score"><a href="' + esc(safeUrl(m.url)) + '" target="_blank" rel="noopener" title="match page on vlr.gg">' +
          '<span class="' + (w1 ? "w" : "") + '">' + esc(m.score1) + '</span>:<span class="' + (w2 ? "w" : "") + '">' + esc(m.score2) + "</span></a></td>" +
          '<td class="' + (w2 ? "win" : "lose") + '">' + ilink(valHash(m.team2), m.team2) + "</td>" +
          (compact ? "" : '<td class="hide-sm" title="' + esc(m.event + (m.series ? " - " + m.series : "")) + '">' + esc(shortEv(m.event)) + '<span class="cc">' + esc(m.series) + "</span></td>") + "</tr>";
      }).join("") + "</tbody></table></div>";
  }


  /* ---------- Matches today (v3.5): CS2 (FACEIT) + Valorant (vlr.gg) on today's Pacific date ---------- */
  function dayKey(d) { var p = ptParts(d); return p.y + "-" + p.m + "-" + p.d; }
  function hhmm(iso) { var p = ptParts(new Date(iso)); return pad(p.h) + ":" + pad(p.mi); }
  function todayRows() {
    var key = dayKey(new Date()), rows = [];
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
  function todayBoard(preview) {
    var all = todayRows(), p = ptParts(new Date()), N = 12;
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
    var upd = (D.cs && D.cs.matches_meta && D.cs.matches_meta.fetched_at) || D.fetched_at;
    var meta = upd ? "updated " + fmt(upd, "short") : "";
    if (preview) meta = all.length ? '<a href="#cs2/today">see all ' + all.length + " &raquo;</a>" : "";
    if (!rows.length) return std(esc(title), meta, '<div class="empty today-empty">No matches scheduled today.</div>', "today-board");
    var body = '<div class="rankbox"><table class="tbl res today"><colgroup><col class="c-when"><col class="c-team"><col class="c-score"><col class="c-team"><col class="c-div hide-sm"><col class="c-map hide-sm"></colgroup><thead><tr>' +
      '<th class="first" title="Pacific Time: start time for upcoming and live matches, finish time for finished CS2 matches">Time (PT)</th><th class="n">Team 1</th><th class="c">Score</th><th>Team 2</th><th class="hide-sm">Division / Event</th><th class="hide-sm">Map</th></tr></thead><tbody>' +
      rows.map(function (r) {
        var m = r.m;
        if (r.g === "val" && r.st !== "done") {
          var vt = function (nm) { return nm && nm !== "TBD" ? ilink(valHash(nm), nm) : '<span class="dim">TBD</span>'; };
          return '<tr class="g-val st-' + r.st + '"><td class="dim" title="' + esc("scheduled " + fmt(m.ts)) + '">' + hhmm(m.ts) + '</td><td class="n tm">' + vt(m.team1) + '</td><td class="score"><a href="' + esc(safeUrl(m.url)) + '" target="_blank" rel="noopener" title="match page on vlr.gg">' +
            (r.st === "live" ? '<span class="live-b">LIVE</span>' : "vs") + '</a></td><td class="tm">' + vt(m.team2) + '</td><td class="hide-sm div" title="' + esc(m.event + (m.series ? " - " + m.series : "")) + '"><span class="gtag">VAL</span>' + esc(shortEv(m.event)) + '</td><td class="hide-sm dim">&ndash;</td></tr>';
        }
        if (r.g === "val") {
          var v1 = m.winner === 0, v2 = m.winner === 1;
          return '<tr class="g-val"><td class="dim" title="' + esc(fmt(m.ts)) + '">' + hhmm(m.ts) + '</td><td class="n tm ' + (v1 ? "win" : "lose") + '">' + ilink(valHash(m.team1), m.team1) +
            '</td><td class="score"><a href="' + esc(safeUrl(m.url)) + '" target="_blank" rel="noopener" title="match page on vlr.gg"><span class="' + (v1 ? "w" : "") + '">' + esc(m.score1) + '</span>:<span class="' + (v2 ? "w" : "") + '">' + esc(m.score2) + "</span></a></td>" +
            '<td class="tm ' + (v2 ? "win" : "lose") + '">' + ilink(valHash(m.team2), m.team2) + '</td><td class="hide-sm div" title="' + esc(m.event + (m.series ? " - " + m.series : "")) + '"><span class="gtag">VAL</span>' + esc(shortEv(m.event)) +
            '</td><td class="hide-sm dim">&ndash;</td></tr>';
        }
        var ru = roomUrl(m), w1 = r.st === "done" && m.winner === 1, w2 = r.st === "done" && m.winner === 2, mid;
        if (r.st === "done") mid = '<span class="' + (w1 ? "w" : "") + '">' + num(m.s1) + '</span>:<span class="' + (w2 ? "w" : "") + '">' + num(m.s2) + "</span>";
        else if (r.st === "live") mid = '<span class="live-b">LIVE</span>';
        else mid = "vs";
        var tip = r.st === "done" ? "match room on FACEIT" : r.st === "live" ? "live now (as of the last update) - match room on FACEIT" : "match room on FACEIT";
        return '<tr class="g-cs st-' + r.st + '"><td class="dim" title="' + esc((r.st === "done" ? "finished " : r.st === "live" ? "started " : "scheduled ") + (m.t ? fmt(m.t) : "")) + '">' + (m.t ? hhmm(m.t) : "TBD") + "</td>" +
          '<td class="n tm ' + (r.st === "done" ? (w1 ? "win" : "lose") : "") + '">' + csSide(m.t1) + '</td><td class="score">' + (ru ? '<a href="' + esc(safeUrl(ru)) + '" target="_blank" rel="noopener" title="' + tip + '">' + mid + "</a>" : mid) + "</td>" +
          '<td class="tm ' + (r.st === "done" ? (w2 ? "win" : "lose") : "") + '">' + csSide(m.t2) + '</td><td class="hide-sm div" title="' + esc(m.region + " " + m.division + (m.conf ? " - conference " + m.conf : "") + " - round " + m.round) + '"><span class="gtag">CS2</span>' +
          ilink("cs2/" + divOf(m), m.region + " " + m.division) + '</td><td class="hide-sm">' + (r.st === "done" ? mapCell(m) : '<span class="dim">&ndash;</span>') + "</td></tr>";
      }).join("") + "</tbody></table></div>" +
      (preview ? '<div class="note see-all">' + all.length + " match" + (all.length === 1 ? "" : "es") + ' today &middot; <a href="#cs2/today">see all matches today &raquo;</a></div>' :
      '<div class="note">' + all.length + " match" + (all.length === 1 ? "" : "es") + " today" + (cut ? " &middot; showing " + [live.length ? "live matches" : "", done.length ? "the latest " + Math.min(N, done.length) + " result" + (Math.min(N, done.length) === 1 ? "" : "s") : "", up.length ? "the next " + Math.min(N, up.length) + " start" + (Math.min(N, up.length) === 1 ? "" : "s") : ""].filter(Boolean).join(", ") + ' (<a href="#cs2/results">all results &raquo;</a>)' : "") +
      ". Times in Pacific Time. Click a score for the match room, a map for the scoreboard. LIVE = in progress at the last update.</div>");
    return std(esc(title), meta, body, "today-board");
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
      card("cs2", csT, [["Standings", "cs2"], ["Results", "cs2/results"], ["Top Players", "cs2/players"], ["Matches Today", "cs2/today"]]) +
      card("valorant", vT, [["Events", "valorant/events"], ["Results", "valorant/results"], ["Top Players", "valorant/players"]]) +
      card("wow", wT, [["US Rankings", "wow/us"], ["EU Rankings", "wow/eu"]]) + "</div>";
    var news = newsItems().slice(0, 5);
    var newsHtml = news.length ? '<div class="newsbox">' + news.map(function (n) {
      return '<div class="item">' + ext(n.url, n.title) + '<span class="src">(' + esc(n.source) + ")</span></div>";
    }).join("") + '<div class="item more"><a href="#news">More news &raquo;</a></div></div>' : '<div class="empty">No headlines right now.</div>';
    var intro = '<div class="infobox hub-intro">Amateur &amp; semi-pro esports: ESEA League CS2, Valorant Challengers and the WoW Mythic raid race. Pick a game to start. All times Pacific.</div>';
    return std("FragNet Front Page", "updated " + fmt(D.fetched_at, "short"), intro) + cards + todayBoard(true) +
      std("Latest Esports News", '<a href="#news">more news &raquo;</a>', newsHtml, "home-news");
  }

  function vCS2(parts) {
    var sub = parts[0];
    var cs = D.cs || {}, divs = csDivs(), ids = divs.map(divId);
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
    } else setCrumbs([["CS2", "cs2"], [section === "players" ? "Top Players" : section === "results" ? "Results" : "Matches Today"]]);
    var s = cs.season;
    var info = s ? '<div class="infobox">' + ext(cs.page, cs.league) + " &raquo; <b>" + esc(s.name) + "</b> &middot; " + fmt(s.start, "md") + " &ndash; " + fmt(s.end, "md") + " (PT)" +
      " &middot; " + num(s.team_count).toLocaleString("en-US") + " teams (all regions) &middot; $" + num(s.prize_pool).toLocaleString("en-US") + ' prize pool<br><span class="dim">Map pool: ' + esc((s.maps || []).join(", ")) + "</span></div>" + staleNote(s) : "";
    var body = "", title = "";
    if (sub === "today") {
      return gameHead("cs2", "today", "Counter-Strike 2 :: ESEA League") + todayBoard();
    } else if (sub === "players") {
      title = "Top Fraggers :: EU + NA";
      var ps = cs.top_players || [], pm = cs.top_players_meta || {};
      body = ps.length ? staleNote(pm) + '<div class="rankbox"><table class="tbl"><thead><tr><th class="first c">#</th><th>Player</th><th class="hide-sm">Division</th><th class="n hide-sm" title="matches played">Matches</th><th class="n hide-sm" title="rounds played">Rnds</th><th class="n" title="kills">K</th><th class="n" title="deaths">D</th><th class="n" title="kills per death">K/D</th><th class="n" title="average damage per round">ADR</th><th class="n hide-sm" title="headshot kill percentage">HS%</th></tr></thead><tbody>' +
        ps.map(function (p, i) {
          return '<tr class="' + medal(i + 1) + '" data-k="' + esc("csp:" + p.nick) + '">' + rk(i + 1) + '<td class="team">' + ilink(playerHash(p.nick), p.nick) + '</td><td class="hide-sm">' + esc(p.region + " " + p.division) +
            '</td><td class="n hide-sm">' + num(p.matches) + '</td><td class="n hide-sm">' + num(p.rounds) + '</td><td class="n">' + num(p.kills) + '</td><td class="n">' + num(p.deaths) + '</td><td class="n">' + csPc(p, "kd") + '</td><td class="n">' + csPc(p, "adr") + '</td><td class="n hide-sm">' + Math.round(num(p.hs)) + "%</td></tr>";
        }).join("") + '</tbody></table></div><div class="note">Season to date, top ' + ps.length + (pm.pool ? " of " + num(pm.pool) : "") + " players with at least " + num(pm.min_rounds || 20) + " rounds, sorted by K/D (ADR breaks ties). Early-season samples are small. Stats as published on FACEIT." + "</div>" : '<div class="empty">Player stats coming soon.</div>';
      var tbd = cs.top_by_div || {};
      csDivs().forEach(function (d) {
        var k = d.region + " " + d.division, list = tbd[k] || [];
        if (d.division === "Advanced" && ps.length) return;      // already ranked above
        body += '<h2 class="subhead" id="tf-' + esc(divId(d)) + '">Top Fraggers :: ' + esc(k) + "</h2>" + (list.length ? '<div class="rankbox"><table class="tbl tf-div"><thead><tr><th class="first c">#</th><th>Player</th><th class="hide-sm">Team</th><th class="n hide-sm">Rnds</th><th class="n">K/D</th><th class="n">ADR</th><th class="n hide-sm">HS%</th></tr></thead><tbody>' +
          list.map(function (p, i) {
            return '<tr class="' + medal(i + 1) + '">' + rk(i + 1) + '<td class="team">' + ilink(playerHash(p.nick), p.nick) + '</td><td class="hide-sm">' + (p.team ? (p.team_id ? ilink("team/cs2/" + encodeURIComponent(p.team_id), p.team) : esc(p.team)) : "") +
              '</td><td class="n hide-sm">' + num(p.rounds) + '</td><td class="n">' + csPc(p, "kd") + '</td><td class="n">' + csPc(p, "adr") + '</td><td class="n hide-sm">' + Math.round(num(p.hs)) + "%</td></tr>";
          }).join("") + "</tbody></table></div>" + '<div class="note">Top ' + list.length + (((cs.top_players_meta || {}).per_div || {})[k] ? " of " + num(cs.top_players_meta.per_div[k]) : "") + " players with at least " + MINR() + " rounds in " + esc(k) + ", by K/D.</div>"
          : '<div class="empty">No player in ' + esc(k) + " has " + MINR() + " rounds yet.</div>");
      });
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
          return '<tr class="' + medal(t.rank) + '" data-k="' + esc("cs:" + divId(d) + ":" + t.name) + '">' + rk(t.rank) + '<td class="team">' + csTeamLink(t) + '<span class="cc" title="' + esc(countryName(t.country)) + '">' + esc(t.country || "") + "</span>" + (t.dq ? '<span class="cc dq" title="disqualified">DQ</span>' : "") +
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
      '<h2 class="subhead">' + esc(title) + "</h2>" + body;
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
      body = staleNote(rm) + '<div class="note">' + r.length + " results from " + evNames.length + " events: " + esc(evNames.join(", ")) + ". Winner highlighted; click a score for the vlr.gg match page. Dates in Pacific Time." +
        (rm.scanned ? " Scanned the latest " + num(rm.scanned) + " vlr.gg results; excluded " + num(rm.excluded_international) + " from international events (Champions/Masters) and " + num(rm.excluded_partner) + " from tier-1 VCT partner leagues" + (excl.length ? " (" + esc(excl.join(", ")) + ")" : "") + "." : "") + "</div>" +
        pager(r.length, page, "valorant/results") + resultsTable(slicePage(r, page), (page - 1) * PER_PAGE, false) + pager(r.length, page, "valorant/results");
    } else if (sub === "players") {
      title = "Top Players :: Challengers / Game Changers";
      var tp = v.top_players || [], tm = v.top_players_meta || {}, x = window.FRAGNET_VAL ? valX() : null;
      var pgP = page, npP = Math.max(1, Math.ceil(tp.length / PER_PAGE)); if (pgP > npP) pgP = npP;
      body = tp.length ? staleNote(tm) + pager(tp.length, pgP, "valorant/players") + '<div class="rankbox"><table class="tbl val-pl"><thead><tr><th class="first c">#</th><th>Player</th><th class="hide-sm">Team</th><th class="hide-sm agc">Agents</th>' + VAL_TH + "</tr></thead><tbody>" +
        slicePage(tp, pgP).map(function (p) {
          var tn = p.team_name || (x && x.teams[p.team] && x.teams[p.team].name);
          return '<tr class="' + medal(p.rank) + '">' + rk(p.rank) + '<td class="team">' + ilink(valPHash(p.name), p.name) + (p.cc ? '<span class="cc">' + esc(p.cc) + "</span>" : "") + '</td><td class="hide-sm">' + (tn ? ilink(valHash(tn), tn) : p.tag ? '<span class="dim" title="team tag at the event">' + esc(p.tag) + "</span>" : '<span class="dim">&ndash;</span>') +
            '</td><td class="hide-sm dim agc">' + agentsCell(p.agents) + "</td>" + valStatCells(p) + "</tr>";
        }).join("") + "</tbody></table></div>" + pager(tp.length, pgP, "valorant/players") +
        '<div class="note">Top ' + tp.length + (tm.pool ? " of " + num(tm.pool) : "") + " players with at least " + num(tm.min_rnd || 100) + " rounds across the " + num(tm.events || evs.length) + " events FragNet tracks (latest completed event per Challengers / Game Changers circuit), by vlr.gg rating; per-event numbers are round-weighted. Stats as published on vlr.gg.</div>"
        : '<div class="empty">Player stats coming soon.</div>';
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
          return '<tr class="' + medal(t.place) + '" data-k="' + esc("vs:" + i + ":" + t.team) + '">' + rk(t.place) + '<td class="team">' + ilink(valHash(t.team), t.team) + '<span class="cc">' + esc(t.country) +
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
    return std("FragNet News Wire", shown.length + " headlines", toolbar(tabs, sub) + srcLine("news")) + body;
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
    var body = !ql ? '<div class="empty">Type in the SEARCH FRAGNET box (top right) &mdash; teams, players, guilds, headlines &mdash; and press GO.</div>' :
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
      if (anyM.length) return std(esc(nm), "CS2 &middot; ESEA League team", '<div class="empty">' + esc(nm) + " is not in the current ESEA standings FragNet shows, so there is no standings line or roster here." +
        (known.length ? "<br>Ranked players from this team: " + known.map(function (p) { return ilink(playerHash(p.nick), p.nick); }).join(", ") + "." : "") + "</div>") + teamMatchesHtml(id) +
        '<div class="note">' + (UUID_RE.test(id) ? ext("https://www.faceit.com/en/teams/" + id, "Team page on FACEIT") + " &middot; " : "") + '<a href="#cs2">ESEA standings</a></div>';
      return notFound(nm || "Team not tracked", (nm ? "<b>" + esc(nm) + "</b> is" : "This team is") + " not in the standings FragNet shows (EU and NA Advanced, Main and Intermediate). No standings or roster data for it in the current data." +
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
    return std(esc(t.name), "CS2 &middot; ESEA League team", tl + info) + '<h2 class="subhead">Roster</h2>' + roster + teamMatchesHtml(t.id || csTeamId(t)) +
      '<div class="note">' + ext(teamFaceitUrl(t), "Team page on FACEIT") + " &middot; " + ext(d.link, "Standings on FACEIT") + "</div>";
  }

  function vPlayerCS(nick) {
    var p = findCsPlayer(nick), spot = findRosterSpot(nick);
    if (!p) loadTeams();                                   // Main/Intermediate stats + rosters are in teams.js
    if (!p && TX_STATE === "loading") return std(esc(nick), "CS2 &middot; ESEA League player", '<div class="empty loading">Loading player&hellip;</div>');
    p = p || findCsPlayer(nick); spot = spot || findRosterSpot(nick);
    if (!p && !spot) return notFound("Player not tracked", "No player named &ldquo;" + esc(nick) + "&rdquo; in FragNet's data (rosters and season stats of the ESEA teams shown).", '<a href="#cs2/players">Top fraggers</a>');
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
      ["Recent series", v.results.length ? '<span class="w">' + w + 'W</span> <span class="l">' + l + "L</span> in the " + v.results.length + " tier-2 results FragNet tracks" : '<span class="dim">none in the tracked results</span>'],
      ["Form", formHtml(valForm(v.name))],
      ["vlr.gg", v.url ? ext(v.url, "Team page on vlr.gg") : '<span class="dim">no team link in the scraped data</span> &middot; ' + ext("https://www.vlr.gg/search/?q=" + encodeURIComponent(v.name), "search vlr.gg")]
    ]);
    var pl = v.placings.length ? '<div class="rankbox"><table class="tbl"><thead><tr><th class="first c">Place</th><th>Event</th><th class="n">Prize</th><th class="hide-sm">Qualified / Points</th></tr></thead><tbody>' +
      v.placings.map(function (x) {
        return '<tr class="' + medal(x.t.place) + '">' + rk(x.t.place) + '<td class="team">' + ilink("valorant/" + evId(x.i), x.ev.title) + '<span class="cc">' + esc(x.ev.dates) + '</span></td><td class="n">' + esc(x.t.prize) + '</td><td class="hide-sm">' + esc([x.t.points, x.t.note].filter(Boolean).join(" ")) + "</td></tr>";
      }).join("") + "</tbody></table></div>" : '<div class="empty">No final placings in the events FragNet tracks.</div>';
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
      ["Recent series", v.results.length ? '<span class="w">' + w + 'W</span> <span class="l">' + l + "L</span> in the " + v.results.length + " tier-2 results FragNet tracks" : '<span class="dim">none in the tracked results</span>'],
      ["Form", formHtml(valForm(v.name))],
      ["vlr.gg", ext(tm.url || v.url, "Team page on vlr.gg")]]);
    var vsk = streak(valForm(v.name));
    var tl = tiles([v.results.length ? ["Recent series", '<span class="w">' + w + '</span>-<span class="l">' + l + "</span>"] : null, vsk ? ["Streak", '<span class="' + (vsk[0] === "W" ? "w" : "l") + '">' + vsk + "</span>"] : null, tm && tm.roster ? ["Roster", tm.roster.filter(function (m) { return !/coach|manager|analyst/.test(m[2] || ""); }).length] : null, tm && (tm.tag || v.country || tm.country) ? [tm.tag ? "Tag" : "Region", esc(tm.tag || tm.country || v.country)] : null]);
    setCrumbs([["Valorant", "valorant"], ["Events", "valorant/events"], [v.name]]);
    return std(esc(v.name), "Valorant &middot; team", tl + info) + '<h2 class="subhead">Roster</h2>' + ros + '<h2 class="subhead">Event Placings</h2>' + pl +
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
    if (!cands.length && !onRoster) return notFound("Player not tracked", "No Valorant player named &ldquo;" + esc(name) + "&rdquo; in the events FragNet tracks.", '<a href="#valorant/players">Top players</a>');
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
      (num(p.rnd) < 100 ? '<div class="note few-rounds">Few rounds so far (' + num(p.rnd) + "): too small a sample to rank (min. 100 rounds).</div>" : "") : '<div class="empty">No stats yet: ' + esc(nm) + " has not played in the events FragNet tracks.</div>";
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

  /* ----- forums (board index / topic list / topic view) ----- */
  function forumNote() {
    return '<div class="local-note forum-note" role="status"><span class="lbl">COMING SOON</span><span>' + esc(FORUM_NOTICE) + "</span></div>";
  }
  function renderPostingUI() {
    // New topic / reply / delete forms plug in here once a real backend exists
    // (only when FORUM_POSTING_ENABLED and ForumBackend implement posting).
    return "";
  }
  function vForums(parts) {
    var mode = parts[0] || "", id = parts[1] || "";
    if (mode === "t") return vTopic(id);
    if (mode === "f" && forumById(id)) return vForum(id);
    var total = 0;
    var rows = FORUMS.map(function (c) {
      return '<tr class="row-header"><td><span class="ic"></span>' + esc(c.cat) + '</td><td class="c">Topics</td><td class="c">Posts</td><td class="lastc">Last Post</td></tr>' + c.items.map(function (fo) {
        var ts = forumTopics(fo.id).sort(byLast);
        var posts = ts.reduce(function (n, t) { return n + t.posts.length; }, 0);
        var lp = ts[0] && lastPost(ts[0]);
        total += ts.length;
        return '<tr class="row-item"><td class="title"><a class="name" href="#forums/f/' + fo.id + '">' + esc(fo.name) + '</a><div class="description">' + esc(fo.desc) +
          '</div></td><td class="num">' + ts.length + '</td><td class="num">' + posts + '</td><td class="lastpost">' + (lp ? '<a href="#forums/t/' + esc(ts[0].id) + '">' + esc(lp.author) + '</a><div class="time">' + fmt(lp.at, "short") + "</div>" : '<span class="time">No posts yet</span>') + "</td></tr>";
      }).join("");
    }).join("");
    return std("FragNet eSports Forums", total + " topics", "") + forumNote() +
      '<div class="crumbs"><a href="#forums">Board Index</a></div><table class="forum-table">' + rows + "</table>";
  }
  function vForum(fid) {
    var fo = forumById(fid);
    var ts = forumTopics(fid).sort(byLast);
    var rows = ts.length ? ts.map(function (t) {
      var lp = lastPost(t);
      return '<tr class="row-item"><td class="title"><a class="name" href="#forums/t/' + esc(t.id) + '">' + esc(t.subject) + '</a><div class="description">by ' + esc(t.posts[0].author) + " &middot; " + fmt(t.posts[0].at, "short") +
        '</div></td><td class="num">' + (t.posts.length - 1) + '</td><td class="num">' + num(t.views) + '</td><td class="lastpost">' + esc(lp.author) + '<div class="time">' + fmt(lp.at, "short") + "</div></td></tr>";
    }).join("") : '<tr class="row-item"><td colspan="4" class="emptyrow">No topics yet.</td></tr>';
    return std(esc(fo.name), ts.length + " topics", "") + forumNote() +
      '<div class="crumbs"><a href="#forums">Board Index</a> &raquo; <span>' + esc(fo.name) + "</span></div>" +
      '<table class="forum-table"><tr class="row-header"><td><span class="ic"></span>Topics</td><td class="c">Replies</td><td class="c">Views</td><td class="lastc">Last Post</td></tr>' + rows + "</table>" + renderPostingUI();
  }
  function vTopic(tid) {
    var t = null;
    try { t = ForumBackend.topic(tid); } catch (e) { t = null; }
    if (!t || !t.posts || !t.posts.length) return std("Topic not available", "", "") + forumNote() + '<div class="empty">There are no forum topics yet. <a href="#forums">Back to the board index</a></div>';
    var fo = forumById(t.forum) || { name: "General", id: "general" };
    var posts = t.posts.map(function (p, i) {
      return '<div class="post"><div class="ubox"><div class="av" aria-hidden="true">' + esc(String(p.author || "?").charAt(0).toUpperCase()) + '</div><div><div class="uname">' + esc(p.author) + '</div><div class="urank">' + (i === 0 ? "Topic Starter" : "Member") +
        '</div></div></div><div class="pc"><div class="phead"><b>#' + (i + 1) + "</b> &middot; " + (i === 0 ? "<b>" + esc(t.subject) + "</b>" : "Re: " + esc(t.subject)) + " &middot; posted " + fmt(p.at) +
        '</div><div class="pbody">' + esc(p.body) + "</div></div></div>";
    }).join("");
    return std(esc(t.subject), (t.posts.length - 1) + " replies", "") + forumNote() +
      '<div class="crumbs"><a href="#forums">Board Index</a> &raquo; <a href="#forums/f/' + fo.id + '">' + esc(fo.name) + '</a> &raquo; <span class="subj">' + esc(t.subject) + "</span></div>" + posts + renderPostingUI();
  }

  /* ----- about (static text lives in index.html <template id="about-tpl">) ----- */
  function vAbout() {
    var tpl = $("#about-tpl");
    var live = "The data currently shown was updated " + fmt(D.fetched_at) + ".";
    return tpl ? tpl.innerHTML.replace("{{fetched}}", esc(live)) : std("About FragNet", "", soon());
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
    return std("Site status", "data sources", html) + '<div class="note"><a href="#about">About FragNet</a> &middot; <a href="#home">Front page</a></div>';
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
  function renderSideForum() {
    var ts = [];
    FORUMS.forEach(function (c) { c.items.forEach(function (fo) { ts = ts.concat(forumTopics(fo.id)); }); });
    ts = ts.sort(byLast).slice(0, 8);
    $("#side-forum").innerHTML = (ts.length ? ts.map(function (t) {
      return '<li title="' + esc(t.subject) + '"><a href="#forums/t/' + esc(t.id) + '">' + esc(t.subject) + '</a><span class="cnt" title="replies">' + (t.posts.length - 1) + "</span></li>";
    }).join("") : '<li class="empty">No topics yet.</li>') + '<li class="note">' + esc(FORUM_NOTICE) + "</li>";
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
    var h = (location.hash || "").replace(/^#/, "");
    try { h = decodeURIComponent(h); } catch (e) {}
    var parts = h.split("/");
    return { top: parts[0] || "home", parts: parts.slice(1) };
  }
  var TITLES = { home: "Front Page", cs2: "Counter-Strike 2 :: ESEA League", valorant: "Valorant :: Challengers / Game Changers", wow: "World of Warcraft :: Mythic Raid Progression", news: "News", forums: "Forums", search: "Search", about: "About", team: "Team", player: "Player", guild: "Guild", match: "Match", status: "Site status" };
  function route() {
    var r = parseHash(), html;
    CRUMB = null; CUR_SEC = "";
    try {
      switch (r.top) {
        case "cs2": html = vCS2(r.parts); break;
        case "valorant": html = vValorant(r.parts); break;
        case "wow": html = vWow(r.parts); break;
        case "news": html = vNews(r.parts); break;
        case "forums": html = vForums(r.parts); break;
        case "about": html = vAbout(); break;
        case "team": html = r.parts[0] === "val" ? vTeamVal(r.parts.slice(1).join("/")) : vTeamCS(r.parts.slice(1).join("/")); break;
        case "player": html = r.parts[0] === "val" ? vPlayerVal(r.parts.slice(1).join("/")) : vPlayerCS(r.parts.slice(1).join("/")); break;
        case "match": html = vMatchCS(r.parts.slice(1).join("/")); break;
        case "guild": html = vGuild(r.parts[0] || "", r.parts[1] || "", r.parts.slice(2).join("/")); break;
        case "search": html = vSearch(r.parts.join("/")); break;
        case "status": html = vStatus(); break;
        case "status-box": r.top = "status"; html = vStatus(); break;
        default: r.top = "home"; html = vHome();
      }
    } catch (e) {
      if (window.console) console.warn("FragNet: could not render view", e);
      html = std("Page unavailable", "", soon("This page could not be displayed right now.")) + '<div class="empty"><a href="#home">Back to the front page</a></div>';
    }
    if (r.top !== "home") {
      var tmp = document.createElement("div"); tmp.innerHTML = html;
      var th = tmp.querySelector(".std-header h1"), gm = { player: 1, team: 1, guild: 1, match: 1 };
      html = crumbHtml(CRUMB || [[gm[r.top] && th ? th.textContent : TITLES[r.top] || (th ? th.textContent : "Page")]]) + html;
    }
    $("#view").innerHTML = html;
    var h1 = $("#view .std-header h1");
    document.title = (r.top === "home" ? "" : (h1 ? h1.textContent + " :: " : TITLES[r.top] ? TITLES[r.top] + " :: " : "")) + "FragNet eSports League Tracker";
    var navTop = r.top === "search" ? "" : (r.top === "player" && r.parts[0] !== "val") || r.top === "match" || (r.top === "team" && r.parts[0] !== "val") ? "cs2" : r.top === "team" || r.top === "player" ? "valorant" : r.top === "guild" ? "wow" : r.top;
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
    function stored() { try { return localStorage.getItem("fragnet-theme"); } catch (e) { return null; } }
    function paint() {
      var night = root.getAttribute("data-theme") === "night";
      if (b) { b.textContent = night ? "\u00bb Classic" : "\u00bb Night"; b.setAttribute("aria-pressed", night ? "true" : "false"); b.title = night ? "Switch to the classic light theme" : "Switch to the Night theme"; }
      var tc = document.querySelector('meta[name="theme-color"]'); if (tc) tc.setAttribute("content", night ? "#14171B" : "#0B0D10");
    }
    if (b) b.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "night" ? "classic" : "night";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("fragnet-theme", next); } catch (e) {}
      paint();
    });
    if (mq && mq.addEventListener) mq.addEventListener("change", function (e) { if (!stored()) { root.setAttribute("data-theme", e.matches ? "night" : "classic"); paint(); } });
    paint();
  }
  function boot(data) {
    D = data || {};
    buildIndex();
    $("#hdr-upd").textContent = "updated " + fmt(D.fetched_at, "short");
    initTheme();
    $("#foot-fetched").textContent = "updated " + fmt(D.fetched_at);
    var ql = $("#ql-rio"); if (ql && D.wow && D.wow.raid) ql.href = rioPage(D.wow.raid, "world");
    [renderGameNav, renderStatus, renderSideNews, renderSideForum, renderTicker].forEach(function (fn) { try { fn(); } catch (e) { if (window.console) console.warn("FragNet: sidebar render failed", e); } });
    window.addEventListener("hashchange", function () {
      clearTimeout(tmr); route(); renderSideForum();
      // optional visitor counter (only present when the build sets GOATCOUNTER_CODE): section only, no ids
      var sec = (location.hash || "#home").split("/")[0];
      if (window.goatcounter && window.goatcounter.count && sec !== LAST_SEC) { LAST_SEC = sec; window.goatcounter.count({ path: location.pathname + sec }); }
    });
    var rt; window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(autoTitles, 200); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(autoTitles);
    window.addEventListener("load", autoTitles);
    document.addEventListener("click", function (e) {
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
    v.innerHTML = soon("FragNet's data could not be loaded right now. Please try again later."); }
  /* data.js (same content as data.json) is used on file:// where fetch() is not allowed */
  function loadDataJs() {
    if (window.FRAGNET_DATA) return boot(window.FRAGNET_DATA);
    var s = document.createElement("script");
    s.src = "data.js";
    s.onload = function () { if (window.FRAGNET_DATA) boot(window.FRAGNET_DATA); else fail(); };
    s.onerror = fail;
    document.body.appendChild(s);
  }

  today(); setInterval(today, 30000);
  if (location.protocol === "file:" || !window.fetch) loadDataJs();
  else fetch("data.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(boot, loadDataJs);
})();
