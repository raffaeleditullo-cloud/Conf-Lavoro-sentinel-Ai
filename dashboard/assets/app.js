/* ══════════════════════════════════════════════════════════════════════════════
 * CONF-LAVORO Sentinel AI — Operations Controller
 * ══════════════════════════════════════════════════════════════════════════════ */

// 1. GESTIONE NAVIGAZIONE VISTE (ROUTING INTERNO FLUIDO)
const views = {
  wall: { id: 'view-wall', title: 'OPERATIONS // LIVE VIDEO WALL' },
  events: { id: 'view-events', title: 'ARCHIVIO EVIDENZE // REGISTRO EVENTI' },
  plates: { id: 'view-plates', title: 'CONTROLLO ACCESSI // WHITELIST LPR' },
  diagnostics: { id: 'view-diagnostics', title: 'SYSTEM HEALTH // TELEMETRIA EDGE' },
  settings: { id: 'view-settings', title: 'CONFIGURAZIONE // SINTESI VOCALE AI & AUDIO' }
};

function switchView(viewName) {
  const target = views[viewName];
  if (!target) return;

  // Aggiorna stato bottoni nav (sia sidebar desktop/tablet che bottom nav mobile)
  document.querySelectorAll('.nav-btn, .bottom-nav-btn').forEach(btn => {
    if (btn.getAttribute('data-view') === viewName) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  // Nascondi tutte le viste e mostra quella attiva
  Object.keys(views).forEach(k => {
    const el = document.getElementById(views[k].id);
    if (el) {
      el.style.display = (k === viewName) ? 'block' : 'none';
    }
  });

  // Aggiorna titolo nel top HUD
  const hudTitle = document.getElementById('hudTitleText');
  if (hudTitle) hudTitle.textContent = target.title;
}

// Collega i click sui pulsanti della barra laterale e bottom nav mobile
document.querySelectorAll('.nav-btn[data-view], .bottom-nav-btn[data-view]').forEach(btn => {
  btn.addEventListener('click', () => {
    const v = btn.getAttribute('data-view');
    switchView(v);
  });
});

// ──────────────────────────────────────────────────────────────────────────────
// 2. TEMA SCURO / CHIARO CON LOGO VETTORIALE ED ICONA SOLE/LUNA
// ──────────────────────────────────────────────────────────────────────────────
const themeToggleBtn = document.getElementById('themeToggle');
const mobileThemeToggle = document.getElementById('mobileThemeToggle');
const themeSvg = document.getElementById('themeSvg');
const brandLogo = document.getElementById('brandLogo');
const mobileBrandLogo = document.getElementById('mobileBrandLogo');

const SUN_ICON = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
const MOON_ICON = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('sentinel_theme', theme);

  const isLight = (theme === 'light');
  if (themeToggleBtn) themeToggleBtn.title = isLight ? 'Passa a Tema Scuro' : 'Passa a Tema Chiaro';
  if (themeSvg) themeSvg.innerHTML = isLight ? MOON_ICON : SUN_ICON;
  if (mobileThemeToggle) {
    const mSvg = mobileThemeToggle.querySelector('svg');
    if (mSvg) mSvg.innerHTML = isLight ? MOON_ICON : SUN_ICON;
  }
  if (brandLogo) brandLogo.src = isLight ? 'assets/img/icona-ai-acqua-su-scuro.svg' : 'assets/img/icona-ai-viola-su-scuro.svg';
  if (mobileBrandLogo) mobileBrandLogo.src = isLight ? 'assets/img/icona-ai-acqua-su-scuro.svg' : 'assets/img/icona-ai-viola-su-scuro.svg';
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  applyTheme(current === 'light' ? 'dark' : 'light');
}

if (themeToggleBtn) themeToggleBtn.addEventListener('click', toggleTheme);
if (mobileThemeToggle) mobileThemeToggle.addEventListener('click', toggleTheme);

const savedTheme = localStorage.getItem('sentinel_theme') || 'dark';
applyTheme(savedTheme);

// ──────────────────────────────────────────────────────────────────────────────
// 3. COLLAPSE / EXPAND SIDEBAR (BUSINESS CALL COMPRESSIONE DESKTOP)
// ──────────────────────────────────────────────────────────────────────────────
const sidebar = document.querySelector('.soc-nav');
const collapseBtn = document.getElementById('sidebarCollapseBtn');
const collapseSvg = document.getElementById('collapseSvg');

const ICON_EXPAND = '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/><path d="m11 9 3 3-3 3"/>';
const ICON_COLLAPSE = '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/><path d="m14 9-3 3 3 3"/>';

function setSidebarCollapsed(collapsed) {
  if (!sidebar) return;
  if (collapsed) {
    sidebar.classList.add('collapsed');
    if (collapseSvg) collapseSvg.innerHTML = ICON_EXPAND;
    if (collapseBtn) collapseBtn.title = 'Espandi Barra Laterale';
    localStorage.setItem('sentinel_sidebar_collapsed', '1');
  } else {
    sidebar.classList.remove('collapsed');
    if (collapseSvg) collapseSvg.innerHTML = ICON_COLLAPSE;
    if (collapseBtn) collapseBtn.title = 'Comprimi Barra Laterale';
    localStorage.setItem('sentinel_sidebar_collapsed', '0');
  }
}

if (collapseBtn) {
  collapseBtn.addEventListener('click', () => {
    const isCollapsed = sidebar && sidebar.classList.contains('collapsed');
    setSidebarCollapsed(!isCollapsed);
  });
}

// Ripristina preferenza barra salvata
if (localStorage.getItem('sentinel_sidebar_collapsed') === '1') {
  setSidebarCollapsed(true);
}

// ──────────────────────────────────────────────────────────────────────────────
// 3. COMANDI ATTUATORI FLOATING DOCK (FARI, CANCELLO, VOCE)
// ──────────────────────────────────────────────────────────────────────────────
let faroTimer = null;
function triggerFaro() {
  const btn = document.getElementById('dockFaroBtn');
  const label = document.getElementById('dockFaroLabel');
  const bar = document.getElementById('dockFaroProgress');

  label.textContent = 'FARI ATTIVI // 30s';
  btn.style.borderColor = 'var(--cai-gold)';
  bar.style.transition = 'none';
  bar.style.width = '100%';

  setTimeout(() => {
    bar.style.transition = 'width 30s linear';
    bar.style.width = '0%';
  }, 50);

  if (faroTimer) clearTimeout(faroTimer);
  faroTimer = setTimeout(() => {
    label.textContent = 'Fari Piazzale // 30s';
    btn.style.borderColor = 'transparent';
  }, 30000);

  fetch('/api/relay/faretto', { method: 'POST' }).catch(() => {});
}

let gateTimer = null;
function triggerGate() {
  const btn = document.getElementById('dockGateBtn');
  const label = document.getElementById('dockGateLabel');
  const bar = document.getElementById('dockGateProgress');

  label.textContent = 'Apertura Relè 2 (3s)...';
  btn.style.borderColor = 'var(--cai-violet)';
  bar.style.transition = 'none';
  bar.style.width = '100%';

  setTimeout(() => {
    bar.style.transition = 'width 3s linear';
    bar.style.width = '0%';
  }, 50);

  if (gateTimer) clearTimeout(gateTimer);
  gateTimer = setTimeout(() => {
    label.textContent = 'Apri Cancello // 3s';
    btn.style.borderColor = 'transparent';
  }, 3500);

  fetch('/api/relay/cancello', { method: 'POST' }).catch(() => {});
}

function triggerVoice() {
  const label = document.getElementById('dockSirenLabel');
  label.textContent = 'Broadcasting Audio...';
  label.style.color = 'var(--accent-red)';

  setTimeout(() => {
    label.textContent = 'Dissuasione Audio IP';
    label.style.color = 'var(--text-main)';
  }, 4000);

  fetch('/api/speaker/voice', { method: 'POST' }).catch(() => {});
}

// ──────────────────────────────────────────────────────────────────────────────
// 4. GESTIONE WHITELIST TARGHE (LPR)
// ──────────────────────────────────────────────────────────────────────────────
const defaultPlates = [
  { plate: 'FG492KS', owner: 'Rocco Di Tolla', role: 'Direzione Generale', active: true },
  { plate: 'DA812LL', owner: 'Alessio Russo', role: 'Responsabile Impianti', active: true },
  { plate: 'CB551AA', owner: 'Corriere Logistica', role: 'Fornitore Accreditato', active: true },
  { plate: 'EZ902BK', owner: 'Dipendente Ufficio', role: 'Amministrazione', active: true }
];

function getPlates() {
  const stored = localStorage.getItem('sentinel_plates');
  return stored ? JSON.parse(stored) : defaultPlates;
}

function savePlates(plates) {
  localStorage.setItem('sentinel_plates', JSON.stringify(plates));
  renderPlates();
}

function renderPlates() {
  const tbodyFull = document.getElementById('platesFullTbody');
  if (!tbodyFull) return;

  const plates = getPlates();
  tbodyFull.innerHTML = '';

  plates.forEach((p, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="plate-pill">${p.plate}</span></td>
      <td><strong style="font-size:13px;">${p.owner}</strong></td>
      <td style="color:var(--text-muted);">${p.role}</td>
      <td><span class="status-beacon">Autorizzata</span></td>
      <td style="text-align:right;">
        <button class="icon-action-btn" title="Rimuovi" onclick="deletePlate(${idx})">
          <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </td>
    `;
    tbodyFull.appendChild(tr);
  });
}

function deletePlate(idx) {
  const plates = getPlates();
  if (confirm(`Rimuovere autorizzazione per ${plates[idx].plate}?`)) {
    plates.splice(idx, 1);
    savePlates(plates);
  }
}

function openAddPlateModal() {
  document.getElementById('plateModal').classList.add('open');
}

function closeAddPlateModal() {
  document.getElementById('plateModal').classList.remove('open');
}

function handleSavePlate(e) {
  e.preventDefault();
  const plate = document.getElementById('inPlate').value.trim().toUpperCase();
  const owner = document.getElementById('inOwner').value.trim();
  const role = document.getElementById('inRole').value.trim();

  if (!plate || !owner) return;

  const plates = getPlates();
  plates.unshift({ plate, owner, role, active: true });
  savePlates(plates);
  closeAddPlateModal();
  e.target.reset();
}

// ──────────────────────────────────────────────────────────────────────────────
// 5. ATTIVITÀ IN TEMPO REALE & MODALE VIDEO
// ──────────────────────────────────────────────────────────────────────────────
const mockEvents = [
  { time: '16:38:12', cam: 'Varco Carrabile', subj: 'Targa: FG492KS', conf: '94%', thumb: 'https://images.unsplash.com/photo-1590674899484-d5640e854abe?auto=format&fit=crop&w=160&q=80', video: 'https://www.w3schools.com/html/mov_bbb.mp4' },
  { time: '16:21:05', cam: 'Varco Pedonale', subj: 'Persona Rilevata', conf: '88%', thumb: 'https://images.unsplash.com/photo-1541888946425-d0fbb186c5f3?auto=format&fit=crop&w=160&q=80', video: 'https://www.w3schools.com/html/mov_bbb.mp4' },
  { time: '15:45:50', cam: 'Piazzale', subj: 'Persona Rilevata', conf: '91%', thumb: 'https://images.unsplash.com/photo-1506521781263-d8422e82f27a?auto=format&fit=crop&w=160&q=80', video: 'https://www.w3schools.com/html/mov_bbb.mp4' },
  { time: '14:12:00', cam: 'Varco Carrabile', subj: 'Veicolo in Transito', conf: '96%', thumb: 'https://images.unsplash.com/photo-1590674899484-d5640e854abe?auto=format&fit=crop&w=160&q=80', video: 'https://www.w3schools.com/html/mov_bbb.mp4' }
];

function renderEvents() {
  const wallTbody = document.getElementById('eventsWallTbody');
  const fullTbody = document.getElementById('eventsFullTbody');

  if (wallTbody) {
    wallTbody.innerHTML = '';
    mockEvents.slice(0, 3).forEach(ev => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-family:var(--font-mono); font-size:11px; color:var(--text-muted);">${ev.time}</td>
        <td style="font-weight:600; font-size:11px;">${ev.cam}</td>
        <td>
          <span class="status-beacon" style="color:var(--text-main); font-weight:500;">${ev.subj}</span>
          <span style="font-family:var(--font-mono); font-size:10px; color:var(--cai-gold);">(${ev.conf})</span>
        </td>
        <td>
          <div class="event-thumb-wrap">
            <img src="${ev.thumb}" alt="Snapshot">
          </div>
        </td>
        <td>
          <button class="play-video-link" onclick="openVideoModal('${ev.cam} // ${ev.time}', '${ev.video}')">
            <svg style="width:12px; height:12px; fill:currentColor;" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span>Play MP4</span>
          </button>
        </td>
      `;
      wallTbody.appendChild(tr);
    });
  }

  if (fullTbody) {
    fullTbody.innerHTML = '';
    mockEvents.forEach(ev => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-family:var(--font-mono); font-size:12px; color:var(--text-muted);">${ev.time}</td>
        <td><strong>${ev.cam}</strong></td>
        <td>${ev.subj}</td>
        <td><span style="font-family:var(--font-mono); color:var(--cai-gold); font-weight:600;">${ev.conf}</span></td>
        <td>
          <div class="event-thumb-wrap" style="width:60px; height:38px;">
            <img src="${ev.thumb}" alt="Snapshot">
          </div>
        </td>
        <td>
          <button class="play-video-link" onclick="openVideoModal('${ev.cam} // ${ev.time}', '${ev.video}')">
            <svg style="width:12px; height:12px; fill:currentColor;" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span>Riproduci Video NAS</span>
          </button>
        </td>
      `;
      fullTbody.appendChild(tr);
    });
  }
}

function openVideoModal(title, url) {
  document.getElementById('videoTitle').textContent = title;
  document.getElementById('videoMeta').textContent = `Evidenza archiviata: ${title}`;
  const video = document.getElementById('videoPlayer');
  video.src = url;
  video.play().catch(() => {});
  document.getElementById('videoModal').classList.add('open');
}

function closeVideoModal() {
  const video = document.getElementById('videoPlayer');
  video.pause();
  video.src = '';
  document.getElementById('videoModal').classList.remove('open');
}

// ──────────────────────────────────────────────────────────────────────────────
// 6. GESTIONE PACCHETTI AUDIO UFFICIALI (CARMELO & SAMI) & HARDWARE
// ──────────────────────────────────────────────────────────────────────────────
let currentAudioPlayer = null;

let currentSettings = {
  voice_pack: 'carmelo',
  active_track: '03_avviso_dissuasione',
  voice_volume: 85,
  siren_enabled: true,
  faro_sec: 30,
  gate_sec: 3
};

function handleVoiceChange(pack) {
  currentSettings.voice_pack = pack;
  const cardCarmelo = document.getElementById('cardVoiceCarmelo');
  const cardSami = document.getElementById('cardVoiceSami');

  if (pack === 'carmelo') {
    if (cardCarmelo) cardCarmelo.classList.add('active');
    if (cardSami) cardSami.classList.remove('active');
  } else {
    if (cardSami) cardSami.classList.add('active');
    if (cardCarmelo) cardCarmelo.classList.remove('active');
  }

  updateTrackLabel();
  if (currentAudioPlayer) {
    currentAudioPlayer.pause();
    resetPlayBtn();
  }
}

function handleTrackChange() {
  const sel = document.getElementById('selAudioTrack');
  if (sel) {
    currentSettings.active_track = sel.value;
  }
  updateTrackLabel();
  if (currentAudioPlayer) {
    currentAudioPlayer.pause();
    resetPlayBtn();
  }
}

function updateTrackLabel() {
  const lbl = document.getElementById('playingTrackLabel');
  if (lbl) {
    lbl.textContent = `audio/${currentSettings.voice_pack}/${currentSettings.active_track}.mp3`;
  }
}

function resetPlayBtn() {
  const btnText = document.getElementById('playBtnText');
  const indicator = document.getElementById('audioPlayingIndicator');
  if (btnText) btnText.textContent = 'Ascolta Traccia Reale';
  if (indicator) indicator.style.display = 'none';
}

function playRealAudioTrack() {
  const audioPath = `audio/${currentSettings.voice_pack}/${currentSettings.active_track}.mp3`;
  const btnText = document.getElementById('playBtnText');
  const indicator = document.getElementById('audioPlayingIndicator');

  if (currentAudioPlayer && !currentAudioPlayer.paused) {
    currentAudioPlayer.pause();
    resetPlayBtn();
    return;
  }

  if (currentAudioPlayer) {
    currentAudioPlayer.pause();
  }

  currentAudioPlayer = new Audio(audioPath);
  currentAudioPlayer.volume = (currentSettings.voice_volume || 85) / 100;

  if (btnText) btnText.textContent = 'Ferma Riproduzione';
  if (indicator) indicator.style.display = 'inline-flex';

  currentAudioPlayer.play().catch(err => {
    console.warn("Autoplay error or missing audio file:", err);
    resetPlayBtn();
  });

  currentAudioPlayer.onended = () => {
    resetPlayBtn();
  };
}

function updateVolumeLabel(val) {
  const lbl = document.getElementById('valVolume');
  if (lbl) lbl.textContent = `${val}%`;
  currentSettings.voice_volume = parseInt(val, 10);
  if (currentAudioPlayer) {
    currentAudioPlayer.volume = currentSettings.voice_volume / 100;
  }
}

function saveSettings() {
  const rngVol = document.getElementById('rngVolume');
  const chkSiren = document.getElementById('chkSiren');
  const numFaro = document.getElementById('numFaroSec');
  const numGate = document.getElementById('numGateSec');
  const selTrack = document.getElementById('selAudioTrack');

  const payload = {
    voice_pack: currentSettings.voice_pack,
    voice_gender: currentSettings.voice_pack,
    active_track: selTrack ? selTrack.value : '03_avviso_dissuasione',
    voice_volume: rngVol ? parseInt(rngVol.value, 10) : 85,
    siren_enabled: chkSiren ? chkSiren.checked : true,
    faro_sec: numFaro ? parseInt(numFaro.value, 10) : 30,
    gate_sec: numGate ? parseInt(numGate.value, 10) : 3
  };

  localStorage.setItem('sentinel_settings', JSON.stringify(payload));

  fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).catch(() => {});

  const statusLbl = document.getElementById('saveStatus');
  if (statusLbl) {
    statusLbl.style.display = 'inline';
    setTimeout(() => {
      statusLbl.style.display = 'none';
    }, 3000);
  }
}

function loadSettings() {
  const stored = localStorage.getItem('sentinel_settings');
  let data = stored ? JSON.parse(stored) : currentSettings;

  currentSettings = Object.assign(currentSettings, data);
  if (currentSettings.voice_gender && !currentSettings.voice_pack) {
    currentSettings.voice_pack = (currentSettings.voice_gender === 'female' || currentSettings.voice_gender === 'sami') ? 'sami' : 'carmelo';
  }

  handleVoiceChange(currentSettings.voice_pack);

  const radio = document.querySelector(`input[name="voicePack"][value="${currentSettings.voice_pack}"]`);
  if (radio) radio.checked = true;

  const selTrack = document.getElementById('selAudioTrack');
  if (selTrack && currentSettings.active_track) selTrack.value = currentSettings.active_track;

  const rngVol = document.getElementById('rngVolume');
  if (rngVol) {
    rngVol.value = currentSettings.voice_volume;
    updateVolumeLabel(currentSettings.voice_volume);
  }

  const chkSiren = document.getElementById('chkSiren');
  if (chkSiren) chkSiren.checked = currentSettings.siren_enabled;

  const numFaro = document.getElementById('numFaroSec');
  if (numFaro) numFaro.value = currentSettings.faro_sec;

  const numGate = document.getElementById('numGateSec');
  if (numGate) numGate.value = currentSettings.gate_sec;

  updateTrackLabel();
}

// Inizializzazione iniziale
document.addEventListener('DOMContentLoaded', () => {
  renderPlates();
  renderEvents();
  loadSettings();
  switchView('wall');
});
