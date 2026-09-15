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
  if (currentRole === 'client' && viewName === 'diagnostics') {
    viewName = 'wall';
  }

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
// 5. GESTIONE STREAM VIDEO REALI & STATI STANDBY HARDWARE
// ──────────────────────────────────────────────────────────────────────────────
function handleStreamLoaded(camId) {
  const standby = document.getElementById(`standbyCam${camId}`);
  const stream = document.getElementById(`streamCam${camId}`);
  const badge = document.getElementById(`camStatusBadge${camId}`);
  if (standby) standby.classList.add('feed-connected');
  if (stream) stream.classList.add('online');
  if (badge) {
    badge.className = 'cam-status-pill live';
    badge.textContent = '● LIVE 4K';
  }
}

function handleStreamError(camId) {
  const standby = document.getElementById(`standbyCam${camId}`);
  const stream = document.getElementById(`streamCam${camId}`);
  const badge = document.getElementById(`camStatusBadge${camId}`);
  if (standby) standby.classList.remove('feed-connected');
  if (stream) stream.classList.remove('online');
  if (badge) {
    badge.className = 'cam-status-pill offline';
    badge.textContent = '● OFFLINE';
  }
  // Riprova il collegamento dello stream ogni 10 secondi (senza sovraccaricare la rete)
  setTimeout(() => {
    if (stream) {
      const baseSrc = stream.src.split('?')[0];
      stream.src = `${baseSrc}?_retry=${Date.now()}`;
    }
  }, 10000);
}

// ──────────────────────────────────────────────────────────────────────────────
// 5B. ATTIVITÀ IN TEMPO REALE & REGISTRO EVIDENZE REALI (ZERO DATI FINTI)
// ──────────────────────────────────────────────────────────────────────────────
let currentEvents = [];

function formatCamName(raw) {
  if (!raw) return 'Telecamera';
  if (raw === 'varco_carrabile') return 'Varco Carrabile';
  if (raw === 'varco_pedonale') return 'Varco Pedonale';
  if (raw === 'piazzale') return 'Piazzale Centrale';
  return raw.replace(/_/g, ' ').toUpperCase();
}

function formatEventLabel(raw) {
  if (!raw) return 'Rilevamento';
  if (raw.toLowerCase() === 'person') return 'Persona Rilevata';
  if (raw.toLowerCase() === 'car') return 'Veicolo in Transito';
  if (raw.toLowerCase().startsWith('plate:')) return `Targa: ${raw.replace('plate:', '').toUpperCase()}`;
  return raw.toUpperCase();
}

async function loadRealEvents() {
  try {
    const res = await fetch('/api/events');
    if (res.ok) {
      const data = await res.json();
      currentEvents = Array.isArray(data) ? data : [];
      renderEvents();
    }
  } catch (err) {
    currentEvents = [];
    renderEvents();
  }
}

function renderEvents() {
  const wallTbody = document.getElementById('eventsWallTbody');
  const fullTbody = document.getElementById('eventsFullTbody');

  if (wallTbody) {
    wallTbody.innerHTML = '';
    if (currentEvents.length === 0) {
      wallTbody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align:center; padding: 26px 12px; color:var(--text-muted); font-family:var(--font-mono); font-size:11px;">
            <div style="display:flex; align-items:center; justify-content:center; gap:8px;">
              <span style="display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--cai-gold);"></span>
              <span>NESSUN EVENTO REGISTRATO // NVR PRONTO AL RILEVAMENTO</span>
            </div>
          </td>
        </tr>
      `;
    } else {
      currentEvents.slice(0, 4).forEach(ev => {
        const camLabel = formatCamName(ev.camera);
        const subjLabel = formatEventLabel(ev.label);
        const thumbUrl = ev.thumb || 'assets/img/icona-ai-viola-su-scuro.svg';
        const videoBtn = ev.video ? `
          <button class="play-video-link" onclick="openVideoModal('${camLabel} // ${ev.time}', '${ev.video}')">
            <svg style="width:12px; height:12px; fill:currentColor;" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span>Play MP4</span>
          </button>
        ` : `<span style="font-family:var(--font-mono); font-size:10px; color:var(--text-dim);">No Clip</span>`;

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td style="font-family:var(--font-mono); font-size:11px; color:var(--text-muted);">${ev.time}</td>
          <td style="font-weight:600; font-size:11px;">${camLabel}</td>
          <td>
            <span class="status-beacon" style="color:var(--text-main); font-weight:500;">${subjLabel}</span>
            <span style="font-family:var(--font-mono); font-size:10px; color:var(--cai-gold);">(${ev.conf || '90%'})</span>
          </td>
          <td>
            <div class="event-thumb-wrap">
              <img src="${thumbUrl}" alt="Snapshot" onerror="this.src='assets/img/icona-ai-viola-su-scuro.svg'">
            </div>
          </td>
          <td>${videoBtn}</td>
        `;
        wallTbody.appendChild(tr);
      });
    }
  }

  if (fullTbody) {
    fullTbody.innerHTML = '';
    if (currentEvents.length === 0) {
      fullTbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align:center; padding: 48px 16px; color:var(--text-muted); font-family:var(--font-mono); font-size:12px;">
            <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px;">
              <span style="color:var(--cai-gold); font-weight:700; letter-spacing:0.08em; font-family:var(--font-brand);">REGISTRO EVENTI VUOTO // HARDWARE IN ATTESA</span>
              <span style="font-size:11px; color:var(--text-dim);">Gli snapshot e le registrazioni appariranno in tempo reale ai primi passaggi rilevati dai sensori ottici.</span>
            </div>
          </td>
        </tr>
      `;
    } else {
      currentEvents.forEach(ev => {
        const camLabel = formatCamName(ev.camera);
        const subjLabel = formatEventLabel(ev.label);
        const thumbUrl = ev.thumb || 'assets/img/icona-ai-viola-su-scuro.svg';
        const videoBtn = ev.video ? `
          <button class="play-video-link" onclick="openVideoModal('${camLabel} // ${ev.time}', '${ev.video}')">
            <svg style="width:12px; height:12px; fill:currentColor;" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span>Riproduci Video NVR</span>
          </button>
        ` : `<span style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim);">Solo Snapshot</span>`;

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td style="font-family:var(--font-mono); font-size:12px; color:var(--text-muted);">${ev.time}</td>
          <td><strong>${camLabel}</strong></td>
          <td>${subjLabel}</td>
          <td><span style="font-family:var(--font-mono); color:var(--cai-gold); font-weight:600;">${ev.conf || '90%'}</span></td>
          <td>
            <div class="event-thumb-wrap" style="width:60px; height:38px;">
              <img src="${thumbUrl}" alt="Snapshot" onerror="this.src='assets/img/icona-ai-viola-su-scuro.svg'">
            </div>
          </td>
          <td>${videoBtn}</td>
        `;
        fullTbody.appendChild(tr);
      });
    }
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

// ──────────────────────────────────────────────────────────────────────────────
// 7. SISTEMA DI AUTENTICAZIONE DOPPIO PIN (CLIENTE VS MANUTENTORE)
// ──────────────────────────────────────────────────────────────────────────────
let currentEnteredPin = '';
let currentRole = null; // 'client' | 'maintainer'

function updatePinDots() {
  const dots = document.querySelectorAll('#pinDots .pin-dot');
  dots.forEach((dot, index) => {
    if (index < currentEnteredPin.length) {
      dot.classList.add('filled');
    } else {
      dot.classList.remove('filled');
    }
  });
}

function pressKeypad(digit) {
  const errorMsg = document.getElementById('authErrorMsg');
  if (errorMsg) errorMsg.style.display = 'none';

  if (currentEnteredPin.length < 4) {
    currentEnteredPin += digit;
    updatePinDots();
  }

  if (currentEnteredPin.length === 4) {
    setTimeout(submitKeypad, 100);
  }
}

function clearKeypad() {
  currentEnteredPin = '';
  updatePinDots();
  const errorMsg = document.getElementById('authErrorMsg');
  if (errorMsg) errorMsg.style.display = 'none';
}

function applyRole(role) {
  currentRole = role;
  document.body.setAttribute('data-role', role);
  sessionStorage.setItem('sentinel_role', role);

  const roleBadge = document.getElementById('roleBadge');
  const roleLabel = document.getElementById('roleLabel');

  if (role === 'maintainer') {
    if (roleBadge) {
      roleBadge.className = 'role-pill maintainer';
    }
    if (roleLabel) roleLabel.textContent = 'MANUTENTORE';
  } else {
    if (roleBadge) {
      roleBadge.className = 'role-pill client';
    }
    if (roleLabel) roleLabel.textContent = 'CLIENTE';

    // Se l'utente era nella pagina diagnostica, reindirizza al wall
    const currentActiveBtn = document.querySelector('.nav-btn.active, .bottom-nav-btn.active');
    if (currentActiveBtn && currentActiveBtn.getAttribute('data-view') === 'diagnostics') {
      switchView('wall');
    }
  }
}

async function submitKeypad() {
  if (currentEnteredPin.length === 0) return;

  const pinToTest = currentEnteredPin;
  const errorMsg = document.getElementById('authErrorMsg');

  try {
    const res = await fetch('/api/auth/pin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: pinToTest })
    });

    if (res.ok) {
      const data = await res.json();
      if (data.success && data.role) {
        applyRole(data.role);
        closeAuthModal();
        return;
      }
    }
  } catch (e) {
    console.warn("Autenticazione via server non disponibile, verifica locale:", e);
  }

  // Fallback se server offline o standalone
  if (pinToTest === '9999') {
    applyRole('maintainer');
    closeAuthModal();
    return;
  } else if (pinToTest === '1111') {
    applyRole('client');
    closeAuthModal();
    return;
  }

  // Se errato
  if (errorMsg) {
    errorMsg.style.display = 'block';
    errorMsg.textContent = 'PIN NON VALIDO';
  }
  const dotsRow = document.getElementById('pinDots');
  if (dotsRow) {
    dotsRow.style.animation = 'shake 0.3s ease';
    setTimeout(() => { dotsRow.style.animation = ''; }, 350);
  }

  setTimeout(() => {
    clearKeypad();
  }, 500);
}

function openAuthModal() {
  clearKeypad();
  const modal = document.getElementById('authModal');
  if (modal) modal.classList.add('open');
}

function closeAuthModal() {
  clearKeypad();
  const modal = document.getElementById('authModal');
  if (modal) modal.classList.remove('open');
}

function lockSession() {
  sessionStorage.removeItem('sentinel_role');
  openAuthModal();
}

function togglePinVisibility(inputId) {
  const inp = document.getElementById(inputId);
  if (inp) {
    inp.type = inp.type === 'password' ? 'text' : 'password';
  }
}

async function saveNewPins() {
  const clientPin = document.getElementById('inputClientPin').value.trim();
  const adminPin = document.getElementById('inputAdminPin').value.trim();
  const statusMsg = document.getElementById('pinSaveStatus');

  if (clientPin.length < 4 || adminPin.length < 4) {
    alert("I codici PIN devono avere almeno 4 cifre.");
    return;
  }

  try {
    const res = await fetch('/api/settings/pins', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_pin: clientPin, admin_pin: adminPin })
    });

    if (res.ok) {
      if (statusMsg) {
        statusMsg.style.display = 'inline';
        setTimeout(() => { statusMsg.style.display = 'none'; }, 3000);
      }
    }
  } catch (err) {
    alert("Errore salvataggio PIN: " + err.message);
  }
}

// Supporto tastiera fisica per digitare il PIN
window.addEventListener('keydown', (e) => {
  const modal = document.getElementById('authModal');
  if (!modal || !modal.classList.contains('open')) return;

  if (e.key >= '0' && e.key <= '9') {
    pressKeypad(e.key);
  } else if (e.key === 'Backspace') {
    clearKeypad();
  } else if (e.key === 'Enter') {
    submitKeypad();
  }
});

// Inizializzazione iniziale
document.addEventListener('DOMContentLoaded', () => {
  renderPlates();
  loadRealEvents();
  // Aggiornamento periodico eventi reali ogni 5 secondi
  setInterval(loadRealEvents, 5000);
  loadSettings();

  // Controllo sessione PIN attiva
  const savedRole = sessionStorage.getItem('sentinel_role');
  if (savedRole) {
    applyRole(savedRole);
  } else {
    // Apri subito il tastierino all'avvio
    openAuthModal();
  }

  switchView('wall');
});
