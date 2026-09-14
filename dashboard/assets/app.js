/* ══════════════════════════════════════════════════════════════════════════════
 * CONF-LAVORO Sentinel AI — Operations Controller
 * ══════════════════════════════════════════════════════════════════════════════ */

// 1. TEMA SCURO / CHIARO CON LOGO VETTORIALE UFFICIALE
const themeToggleBtn = document.getElementById('themeToggle');
const themeLabel = document.getElementById('themeLabel');
const brandLogo = document.getElementById('brandLogo');

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('sentinel_theme', theme);

  if (theme === 'light') {
    themeLabel.textContent = 'Tema Scuro';
    brandLogo.src = 'assets/img/icona-ai-acqua-su-scuro.svg';
  } else {
    themeLabel.textContent = 'Tema Chiaro';
    brandLogo.src = 'assets/img/icona-ai-viola-su-scuro.svg';
  }
}

themeToggleBtn.addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme');
  applyTheme(current === 'light' ? 'dark' : 'light');
});

const savedTheme = localStorage.getItem('sentinel_theme') || 'dark';
applyTheme(savedTheme);

// ──────────────────────────────────────────────────────────────────────────────
// 2. COMANDI ATTUATORI FLOATING DOCK (FARI, CANCELLO, VOCE)
// ──────────────────────────────────────────────────────────────────────────────
let faroTimer = null;
function triggerFaro() {
  const btn = document.getElementById('dockFaroBtn');
  const label = document.getElementById('dockFaroLabel');
  const bar = document.getElementById('dockFaroProgress');

  label.textContent = 'Fari ATTIVI (30s)';
  btn.style.borderColor = 'var(--cai-gold)';
  bar.style.transition = 'none';
  bar.style.width = '100%';

  setTimeout(() => {
    bar.style.transition = 'width 30s linear';
    bar.style.width = '0%';
  }, 50);

  if (faroTimer) clearTimeout(faroTimer);
  faroTimer = setTimeout(() => {
    label.textContent = 'Fari Piazzale (30s)';
    btn.style.borderColor = 'transparent';
  }, 30000);

  fetch('/api/relay/faretto', { method: 'POST' }).catch(() => {});
}

let gateTimer = null;
function triggerGate() {
  const btn = document.getElementById('dockGateBtn');
  const label = document.getElementById('dockGateLabel');
  const bar = document.getElementById('dockGateProgress');

  label.textContent = 'Apertura in corso (3s)...';
  btn.style.borderColor = 'var(--cai-violet)';
  bar.style.transition = 'none';
  bar.style.width = '100%';

  setTimeout(() => {
    bar.style.transition = 'width 3s linear';
    bar.style.width = '0%';
  }, 50);

  if (gateTimer) clearTimeout(gateTimer);
  gateTimer = setTimeout(() => {
    label.textContent = 'Apri Cancello (3s)';
    btn.style.borderColor = 'transparent';
  }, 3500);

  fetch('/api/relay/cancello', { method: 'POST' }).catch(() => {});
}

function triggerVoice() {
  const label = document.getElementById('dockSirenLabel');
  label.textContent = 'Voce in riproduzione...';
  label.style.color = 'var(--accent-red)';

  setTimeout(() => {
    label.textContent = 'Dissuasione Vocale';
    label.style.color = 'var(--text-main)';
  }, 4000);

  fetch('/api/speaker/voice', { method: 'POST' }).catch(() => {});
}

// ──────────────────────────────────────────────────────────────────────────────
// 3. GESTIONE WHITELIST TARGHE (LPR)
// ──────────────────────────────────────────────────────────────────────────────
const defaultPlates = [
  { plate: 'FG492KS', owner: 'Rocco Di Tolla', role: 'Direzione Generale', active: true },
  { plate: 'DA812LL', owner: 'Alessio Russo', role: 'Responsabile Impianti', active: true },
  { plate: 'CB551AA', owner: 'Corriere Logistica', role: 'Fornitore Accreditato', active: true }
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
  const tbody = document.getElementById('platesTbody');
  const plates = getPlates();
  tbody.innerHTML = '';

  plates.forEach((p, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="plate-pill">${p.plate}</span></td>
      <td>
        <div style="font-weight:600; font-size:12px;">${p.owner}</div>
        <div style="font-size:10px; color:var(--text-dim);">${p.role}</div>
      </td>
      <td><span class="status-beacon">Autorizzata</span></td>
      <td style="text-align:right;">
        <button class="icon-action-btn" title="Rimuovi" onclick="deletePlate(${idx})">
          <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </td>
    `;
    tbody.appendChild(tr);
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
// 4. ATTIVITÀ IN TEMPO REALE & MODALE VIDEO
// ──────────────────────────────────────────────────────────────────────────────
const mockEvents = [
  { time: '16:38:12', cam: 'Varco Carrabile', subj: 'Targa: FG492KS', conf: '94%', thumb: 'https://images.unsplash.com/photo-1590674899484-d5640e854abe?auto=format&fit=crop&w=120&q=80', video: 'https://www.w3schools.com/html/mov_bbb.mp4' },
  { time: '16:21:05', cam: 'Varco Pedonale', subj: 'Persona Rilevata', conf: '88%', thumb: 'https://images.unsplash.com/photo-1541888946425-d0fbb186c5f3?auto=format&fit=crop&w=120&q=80', video: 'https://www.w3schools.com/html/mov_bbb.mp4' },
  { time: '15:45:50', cam: 'Piazzale', subj: 'Persona Rilevata', conf: '91%', thumb: 'https://images.unsplash.com/photo-1506521781263-d8422e82f27a?auto=format&fit=crop&w=120&q=80', video: 'https://www.w3schools.com/html/mov_bbb.mp4' }
];

function renderEvents() {
  const tbody = document.getElementById('eventsTbody');
  tbody.innerHTML = '';

  mockEvents.forEach(ev => {
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
    tbody.appendChild(tr);
  });
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

// Inizializzazione
document.addEventListener('DOMContentLoaded', () => {
  renderPlates();
  renderEvents();
});
