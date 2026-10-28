// Minimal vanilla-JS front-end. Polls /api/status for live console + job log.
let source = "modrinth";

function pickSource(s) {
  source = s;
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.src === s));
  document.getElementById("uploadExt").textContent =
    s === "modrinth" ? ".mrpack" : ".zip";
}

async function post(url, body) {
  const opts = { method: "POST" };
  if (body instanceof FormData) opts.body = body;
  const r = await fetch(url, opts);
  let data = {};
  try { data = await r.json(); } catch (e) {}
  if (!r.ok || data.ok === false) {
    alert("Error: " + (data.error || r.status));
    return null;
  }
  return data;
}

async function control(action) {
  await post(`/api/server/${action}`);
  refresh();
}

async function sendCmd() {
  const el = document.getElementById("cmd");
  if (!el.value.trim()) return;
  const fd = new FormData();
  fd.append("command", el.value);
  await post("/api/command", fd);
  el.value = "";
}

async function installLink() {
  const link = document.getElementById("packLink").value.trim();
  if (!link) { alert("Enter a link or ID first."); return; }
  const fd = new FormData();
  fd.append("source", source);
  fd.append("link", link);
  await post("/api/install/link", fd);
}

async function installUpload() {
  const f = document.getElementById("packFile").files[0];
  if (!f) { alert("Choose a file first."); return; }
  const fd = new FormData();
  fd.append("source", source);
  fd.append("file", f);
  await post("/api/install/upload", fd);
}

async function loadMods() {
  try {
    const r = await fetch("/api/mods");
    if (!r.ok) return;
    const d = await r.json();
    const ul = document.getElementById("modList");
    if (!d.extra_mods.length) {
      ul.innerHTML = '<li class="empty">No extra mods yet.</li>';
      return;
    }
    ul.innerHTML = d.extra_mods.map(m =>
      `<li><span class="dot ${m.active ? 'on' : ''}"></span>${m.name}` +
      `<button class="link" onclick="deleteMod('${m.name.replace(/'/g, "")}')">remove</button></li>`
    ).join("");
  } catch (e) {}
}

async function uploadMod() {
  const f = document.getElementById("modFile").files[0];
  if (!f) { alert("Choose a .jar first."); return; }
  const fd = new FormData();
  fd.append("file", f);
  const ok = await post("/api/mods/upload", fd);
  if (ok) {
    flash("Mod added.");
    document.getElementById("modFile").value = "";
    loadMods();
  }
}

async function deleteMod(name) {
  if (!confirm("Remove " + name + "?")) return;
  const fd = new FormData();
  fd.append("name", name);
  const ok = await post("/api/mods/delete", fd);
  if (ok) loadMods();
}

// ---- Players -------------------------------------------------------------
function playerRow(name, removeCall) {
  return `<li>${name}<button class="link" onclick="${removeCall}">remove</button></li>`;
}

async function loadPlayers() {
  try {
    const r = await fetch("/api/players");
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById("wlToggle").checked = d.whitelist_enabled;
    const esc = s => s.replace(/'/g, "");
    document.getElementById("wlList").innerHTML = d.whitelist.length
      ? d.whitelist.map(n => playerRow(n, `playerRemove('whitelist/remove','${esc(n)}')`)).join("")
      : '<li class="empty">empty</li>';
    document.getElementById("opList").innerHTML = d.ops.length
      ? d.ops.map(n => playerRow(n, `playerRemove('ops/remove','${esc(n)}')`)).join("")
      : '<li class="empty">empty</li>';
    document.getElementById("banList").innerHTML = d.banned.length
      ? d.banned.map(n => playerRow(n, `playerRemove('unban','${esc(n)}')`)).join("")
      : '<li class="empty">empty</li>';
    document.getElementById("playersHint").textContent = d.server_running
      ? "" : "Server stopped: whitelist edits work offline; ops/bans need the server running.";
  } catch (e) {}
}

async function toggleWhitelist() {
  const fd = new FormData();
  fd.append("enabled", document.getElementById("wlToggle").checked);
  await post("/api/whitelist/toggle", fd);
  loadPlayers();
}

async function playerAdd(endpoint, inputId) {
  const el = document.getElementById(inputId);
  const name = el.value.trim();
  if (!name) return;
  const fd = new FormData();
  fd.append("name", name);
  const ok = await post("/api/" + endpoint, fd);
  if (ok) { el.value = ""; loadPlayers(); }
}

async function playerRemove(endpoint, name) {
  const fd = new FormData();
  fd.append("name", name);
  const ok = await post("/api/" + endpoint, fd);
  if (ok) loadPlayers();
}

// ---- Backups -------------------------------------------------------------
async function loadBackups() {
  try {
    const r = await fetch("/api/backups");
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById("backupState").textContent =
      (d.enabled ? `auto: every ${d.interval_hours}h, keep ${d.keep}` : "auto off") +
      (d.state.last_result ? " · " + d.state.last_result : "");
    const ul = document.getElementById("backupList");
    ul.innerHTML = d.backups.length
      ? d.backups.map(b =>
          `<li><span>${b.name}</span><span class="meta">${b.size_mb} MB</span>` +
          `<button class="link" onclick="restoreBackup('${b.name}')">restore</button>` +
          `<button class="link" onclick="deleteBackup('${b.name}')">delete</button></li>`
        ).join("")
      : '<li class="empty">No backups yet.</li>';
  } catch (e) {}
}

async function backupNow() {
  const ok = await post("/api/backups/create", new FormData());
  if (ok) { flash("Backup created."); loadBackups(); }
}

async function deleteBackup(name) {
  if (!confirm("Delete " + name + "?")) return;
  const fd = new FormData(); fd.append("name", name);
  const ok = await post("/api/backups/delete", fd);
  if (ok) loadBackups();
}

async function restoreBackup(name) {
  if (!confirm("Restore " + name + "? The server will be stopped and the current world replaced.")) return;
  const fd = new FormData(); fd.append("name", name);
  const d = await post("/api/backups/restore", fd);
  if (d) { flash("Restored. Start the server when ready."); loadBackups(); }
}

async function saveSettings(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  // checkboxes: ensure explicit booleans
  fd.set("auto_restart", ev.target.auto_restart.checked);
  fd.set("eula_accepted", ev.target.eula_accepted.checked);
  fd.set("backup_enabled", ev.target.backup_enabled.checked);
  fd.set("map_enabled", ev.target.map_enabled.checked);
  fd.set("restart_enabled", ev.target.restart_enabled.checked);
  fd.set("discord_enabled", ev.target.discord_enabled.checked);
  fd.set("use_rcon", ev.target.use_rcon.checked);
  const ok = await post("/api/settings", fd);
  if (ok) { flash("Settings saved."); loadBackups(); }
}

async function saveProps() {
  const fd = new FormData();
  fd.append("text", document.getElementById("props").value);
  const ok = await post("/api/properties", fd);
  if (ok) flash("server.properties saved.");
}

function flash(msg) {
  const pill = document.getElementById("statusPill");
  const old = pill.textContent;
  pill.textContent = "✓ " + msg;
  setTimeout(() => (pill.textContent = old), 1500);
}

// ---- Live stats ----------------------------------------------------------
function fmtUptime(s) {
  if (!s) return "—";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}
async function refreshStats() {
  try {
    const r = await fetch("/api/stats");
    if (!r.ok) return;
    const d = await r.json();
    const run = d.status === "running";
    document.getElementById("tileRam").textContent =
      run ? `${d.rss_mb} / ${d.max_mb} MB` : "—";
    document.getElementById("tileCpu").textContent = run ? `${d.cpu_pct}%` : "—";
    document.getElementById("tileUptime").textContent =
      run ? fmtUptime(d.uptime_s) : "—";
  } catch (e) {}
}

// ---- Mod browser (Modrinth search) ---------------------------------------
async function searchMods() {
  const q = document.getElementById("modSearch").value.trim();
  const fd = new FormData();
  fd.append("q", q);
  const d = await post("/api/mods/search", fd);
  const ul = document.getElementById("searchResults");
  if (!d) return;
  if (!d.hits.length) { ul.innerHTML = '<li class="empty">No results.</li>'; return; }
  ul.innerHTML = d.hits.map(h =>
    `<li><span title="${(h.description || '').replace(/"/g, '')}">${h.title}` +
    ` <span class="meta">${h.downloads.toLocaleString()} dl</span></span>` +
    `<button class="link add" onclick="addMod('${h.project_id}')">add</button></li>`
  ).join("");
}
async function addMod(projectId) {
  const fd = new FormData();
  fd.append("project_id", projectId);
  const d = await post("/api/mods/add_modrinth", fd);
  if (d) { flash("Added " + d.name); loadMods(); }
}

// ---- World & icon --------------------------------------------------------
async function importWorld() {
  const f = document.getElementById("worldFile").files[0];
  if (!f) { alert("Choose a world .zip first."); return; }
  if (!confirm("Import world? The server stops and the current world is replaced.")) return;
  const fd = new FormData(); fd.append("file", f);
  const d = await post("/api/world/import", fd);
  if (d) { flash("World imported."); document.getElementById("worldFile").value = ""; }
}
async function uploadIcon() {
  const f = document.getElementById("iconFile").files[0];
  if (!f) { alert("Choose a .png first."); return; }
  const fd = new FormData(); fd.append("file", f);
  const d = await post("/api/icon", fd);
  if (d) { flash("Icon saved."); document.getElementById("iconFile").value = ""; }
}

// ---- Config files --------------------------------------------------------
async function loadFileList() {
  try {
    const r = await fetch("/api/files");
    if (!r.ok) return;
    const d = await r.json();
    const sel = document.getElementById("fileSelect");
    sel.innerHTML = d.files.map(f => `<option value="${f}">${f}</option>`).join("")
      || '<option value="">(no config files yet)</option>';
  } catch (e) {}
}
async function loadFile() {
  const path = document.getElementById("fileSelect").value;
  if (!path) return;
  const fd = new FormData(); fd.append("path", path);
  const d = await post("/api/files/read", fd);
  if (d) document.getElementById("fileText").value = d.text;
}
async function saveFile() {
  const path = document.getElementById("fileSelect").value;
  if (!path) { alert("Open a file first."); return; }
  const fd = new FormData();
  fd.append("path", path);
  fd.append("text", document.getElementById("fileText").value);
  const d = await post("/api/files/write", fd);
  if (d) flash("File saved.");
}

// ---- Performance ---------------------------------------------------------
async function applyAikar() {
  const d = await post("/api/performance/aikar", new FormData());
  if (d) { document.getElementById("jvmArgs").value = d.flags; flash("Aikar flags set — Save settings to keep."); }
}

// ---- Playtime ------------------------------------------------------------
function fmtDur(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}
async function loadPlaytime() {
  try {
    const r = await fetch("/api/playtime");
    if (!r.ok) return;
    const d = await r.json();
    const ul = document.getElementById("playtimeList");
    ul.innerHTML = d.players.length
      ? d.players.map(p =>
          `<li><span class="dot ${p.online ? 'on' : ''}"></span>${p.name}` +
          `<span class="meta">${fmtDur(p.seconds)}</span></li>`
        ).join("")
      : '<li class="empty">no data yet</li>';
  } catch (e) {}
}

// ---- World pre-generation (Chunky) ---------------------------------------
async function addChunky() {
  if (!confirm("Download Chunky for your loader/MC version?")) return;
  const d = await post("/api/mods/add_chunky", new FormData());
  if (d) { flash("Chunky added: " + d.name); loadMods(); }
}
async function pregen(action) {
  const fd = new FormData();
  if (action === "start") fd.append("radius", document.getElementById("pregenRadius").value || "1000");
  const d = await post("/api/pregen/" + action, fd);
  if (d) flash(action === "start" ? "Pre-gen started (see Console)." : "Pre-gen cancelled.");
}

// ---- BlueMap one-click ---------------------------------------------------
async function addBluemap() {
  if (!confirm("Download BlueMap for your loader/MC version and enable the live map?")) return;
  const d = await post("/api/mods/add_bluemap", new FormData());
  if (d) { flash("BlueMap added: " + d.name); loadMods(); }
}

// ---- Scheduled commands --------------------------------------------------
async function loadSchedule() {
  try {
    const r = await fetch("/api/schedule");
    if (!r.ok) return;
    const d = await r.json();
    const ul = document.getElementById("scheduleList");
    ul.innerHTML = d.commands.length
      ? d.commands.map((c, i) =>
          `<li><span class="meta" style="margin:0 10px 0 0">${c.time}</span>${c.command}` +
          `<button class="link" onclick="deleteSchedule(${i})">remove</button></li>`
        ).join("")
      : '<li class="empty">none</li>';
  } catch (e) {}
}
async function addSchedule() {
  const time = document.getElementById("schedTime").value.trim();
  const cmd = document.getElementById("schedCmd").value.trim();
  if (!time || !cmd) { alert("Enter time and command."); return; }
  const fd = new FormData(); fd.append("time", time); fd.append("command", cmd);
  const ok = await post("/api/schedule/add", fd);
  if (ok) { document.getElementById("schedTime").value = ""; document.getElementById("schedCmd").value = ""; loadSchedule(); }
}
async function deleteSchedule(i) {
  const fd = new FormData(); fd.append("index", i);
  const ok = await post("/api/schedule/delete", fd);
  if (ok) loadSchedule();
}

// ---- Tunnel --------------------------------------------------------------
async function tunnelCtl(action) {
  await post("/api/tunnel/" + action, new FormData());
  refreshTunnel();
}
async function refreshTunnel() {
  try {
    const r = await fetch("/api/tunnel");
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById("tunState").textContent = d.running ? "running" : "stopped";
    const el = document.getElementById("tunnelLog");
    el.textContent = d.output;
    el.scrollTop = el.scrollHeight;
  } catch (e) {}
}

// ---- Crash reports -------------------------------------------------------
async function loadCrashList() {
  try {
    const r = await fetch("/api/crashreports");
    if (!r.ok) return;
    const d = await r.json();
    const sel = document.getElementById("crashSelect");
    sel.innerHTML = d.reports.map(c => `<option value="${c.name}">${c.name} (${c.size_kb} KB)</option>`).join("")
      || '<option value="">(no crash reports or logs yet)</option>';
  } catch (e) {}
}
async function loadCrash() {
  const name = document.getElementById("crashSelect").value;
  if (!name) return;
  const fd = new FormData(); fd.append("name", name);
  const d = await post("/api/crashreports/read", fd);
  if (d) {
    const el = document.getElementById("crashText");
    el.textContent = d.text;
    el.scrollTop = el.scrollHeight;
  }
}

// ---- Live map ------------------------------------------------------------
let mapSrc = "";
function updateMap(enabled, port) {
  const card = document.getElementById("mapCard");
  if (!enabled) { card.style.display = "none"; return; }
  card.style.display = "";
  // Same host the panel is served from, just a different port -> works on
  // LAN and over Tailscale without any extra config.
  const url = `${location.protocol}//${location.hostname}:${port}/`;
  document.getElementById("mapOpen").href = url;
  document.getElementById("mapHint").textContent =
    `Map served at ${url} — needs a map mod (e.g. BlueMap) installed and the server running.`;
  if (url !== mapSrc) {              // set src only once to avoid reloading
    document.getElementById("mapFrame").src = url;
    mapSrc = url;
  }
}

let lastConsole = "";
async function refresh() {
  try {
    const r = await fetch("/api/status");
    if (!r.ok) return;
    const d = await r.json();

    const pill = document.getElementById("statusPill");
    pill.textContent = "● " + d.server_status;
    pill.className = "status-pill " + d.server_status;

    document.getElementById("packMeta").textContent = d.pack
      ? `${d.pack} — ${d.loader} ${d.mc_version}`
      : "No modpack installed yet.";

    updateMap(d.map_enabled, d.map_port);

    if (d.console !== lastConsole) {
      const c = document.getElementById("console");
      const atBottom = c.scrollTop + c.clientHeight >= c.scrollHeight - 30;
      c.textContent = d.console;
      if (atBottom) c.scrollTop = c.scrollHeight;
      lastConsole = d.console;
    }

    const jl = document.getElementById("jobLog");
    jl.textContent = d.job.log.join("\n");
    if (d.job.log.length) jl.scrollTop = jl.scrollHeight;
  } catch (e) {}
}

async function loadProps() {
  const r = await fetch("/api/properties");
  if (r.ok) document.getElementById("props").value = (await r.json()).text;
}

async function refreshOnline() {
  try {
    const r = await fetch("/api/players/online");
    if (!r.ok) return;
    const txt = (await r.json()).online;
    document.getElementById("onlineNow").textContent = "online: " + txt;
    const m = txt.match(/(\d+)\s+of\s+(\d+)/);
    document.getElementById("tilePlayers").textContent = m ? `${m[1]} / ${m[2]}` : "—";
  } catch (e) {}
}

// Register the service worker so the panel is installable as a PWA.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

loadProps();
loadMods();
loadPlayers();
loadBackups();
loadFileList();
loadSchedule();
loadCrashList();
loadPlaytime();
refresh();
refreshStats();
refreshOnline();
refreshTunnel();
setInterval(refresh, 2000);
setInterval(refreshStats, 5000);
setInterval(() => { loadPlayers(); refreshOnline(); loadPlaytime(); }, 15000);
setInterval(loadBackups, 30000);
setInterval(refreshTunnel, 5000);
