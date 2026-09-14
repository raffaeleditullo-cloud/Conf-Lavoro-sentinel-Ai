/* ══════════════════════════════════════════════════════════════════════════════
 * CONF-LAVORO Sentinel AI — Dashboard Logic & Client Controller
 * ══════════════════════════════════════════════════════════════════════════════ */

// 1. TEMA (SCURO / CHIARO) CON CAMBIO LOGO SVG UFFICIALE
const themeToggleBtn = document.getElementById('themeToggle');
const themeLabel = document.getElementById('themeLabel');
const themeIcon = document.getElementById('themeIcon');
const brandLogo = document.getElementById('brandLogo');

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('sentinel_theme', theme);

  if (theme === 'light') {
    themeLabel.textContent = 'Tema Scuro';
    themeIcon.textContent = '🌙';
    brandLogo.src = 'assets/img/conflavoro-ai-acqua-su-scuro.svg';
  } else {
    themeLabel.textContent = 'Tema Chiaro';
    themeIcon.textContent = '☀️';
    brandLogo.src = 'assets/img/conflavoro-ai-viola-su-scuro.svg';
  }
}

themeToggleBtn.addEventListener('click', () => {
  const currentTheme = document.documentElement.getAttribute('data-theme');
  const newTheme = currentTheme === 'light' ? 'dark' : 'light';
  applyTheme(newTheme);
});

// Inizializzazione tema
const savedTheme = localStorage.getItem('sentinel_theme') || 'dark';
applyTheme(savedTheme);

// ──────────────────────────────────────────────────────────────────────────────
// 2. NAVIGAZIONE TAB LATERALE
// ──────────────────────────────────────────────────────────────────────────────
const navItems = document.querySelectorAll('.nav-item');
const tabContents = {
  live: document.getElementById('tab-live'),
  actions: document.getElementById('tab-actions'),
  events: document.getElementById('tab-events'),
  plates: document.getElementById('tab-plates'),
  diagnostics: document.getElementById('tab-diagnostics')
};

const tabTitles = {
  live: { title: 'Live Monitor', subtitle: 'Sorveglianza perimetrale 4K attiva sui 3 varchi' },
  actions: { title: 'Comandi Rapidi', subtitle: 'Controllo manuale immediato relè fari, cancello e audio' },
  events: { title: 'Registro Eventi', subtitle: 'Storico intrusioni con evidenze e registrazioni del NAS Ugreen' },
  plates: { title: 'Gestione Targhe LPR', subtitle: 'Elenco autorizzazioni varco carrabile automatico' },
  diagnostics: { title: 'Diagnostica Sistema', subtitle: 'Monitoraggio hardware, temperatura Jetson e bus Modbus' }
};

navItems.forEach(item => {
  item.addEventListener('click', () => {
    const tab = item.getAttribute('data-tab');
    
    navItems.forEach(i => i.classList.remove('active'));
    item.classList.add('active');

    Object.keys(tabContents).forEach(key => {
      if (key === tab) {
        tabContents[key].style.display = 'block';
      } else {
        tabContents[key].style.display = 'none';
      }
    });

    // Aggiorna titolo pagina
    if (tabTitles[tab]) {
      document.getElementById('pageTitle').textContent = tabTitles[tab].title;
      document.getElementById('pageSubtitle').textContent = tabTitles[tab].subtitle;
    }
  });
});

// ──────────────────────────────────────────────────────────────────────────────
// 3. GESTIONE ATTUATORI RAPIDI (FARI, CANCELLO, VOCE)
// ──────────────────────────────────────────────────────────────────────────────
let faroTimer = null;
function triggerFaro() {
  const btn = document.getElementById('btnFaro');
  const status = document.getElementById('faroStatus');
  const bar = document.getElementById('faroPulseBar');

  status.textContent = 'ACCESO (30s rimanenti)';
  status.style.color = 'var(--oro)';
  btn.style.borderColor = 'var(--oro)';
  bar.style.transition = 'none';
  bar.style.width = '100%';

  setTimeout(() => {
    bar.style.transition = 'width 30s linear';
    bar.style.width = '0%';
  }, 50);

  if (faroTimer) clearTimeout(faroTimer);
  faroTimer = setTimeout(() => {
    status.textContent = 'Impulso dissuasione 30 sec';
    status.style.color = 'var(--ink-500)';
    btn.style.borderColor = 'var(--sidebar-border)';
  }, 30000);

  // Invia comando all'API locale se disponibile
  fetch('/api/relay/faretto', { method: 'POST' }).catch(() => {});
}

let gateTimer = null;
function triggerGate() {
  const btn = document.getElementById('btnGate');
  const status = document.getElementById('gateStatus');
  const bar = document.getElementById('gatePulseBar');

  status.textContent = 'IN APERTURA (Impulso 3s)...';
  status.style.color = 'var(--primary)';
  btn.style.borderColor = 'var(--primary)';
  bar.style.transition = 'none';
  bar.style.width = '100%';

  setTimeout(() => {
    bar.style.transition = 'width 3s linear';
    bar.style.width = '0%';
  }, 50);

  if (gateTimer) clearTimeout(gateTimer);
  gateTimer = setTimeout(() => {
    status.textContent = 'Impulso varco 3 sec';
    status.style.color = 'var(--ink-500)';
    btn.style.borderColor = 'var(--sidebar-border)';
  }, 3500);

  fetch('/api/relay/cancello', { method: 'POST' }).catch(() => {});
}

function triggerVoice() {
  const status = document.getElementById('voiceStatus');
  status.textContent = 'Riproduzione avviso in corso...';
  status.style.color = 'var(--danger)';

  setTimeout(() => {
    status.textContent = 'Riproduci avviso Carmelo';
    status.style.color = 'var(--ink-500)';
  }, 4000);

  fetch('/api/speaker/voice', { method: 'POST' }).catch(() => {});
}

// ──────────────────────────────────────────────────────────────────────────────
// 4. GESTIONE TARGHE (WHITELIST CRUD)
// ──────────────────────────────────────────────────────────────────────────────
let defaultPlates = [
  { plate: 'FG492KS', owner: 'Ing. Rocco Di Tolla', role: 'Direzione Generale', active: true, date: '2026-09-08' },
  { plate: 'DA812LL', owner: 'Alessio Russo', role: 'Responsabile Impianti', active: true, date: '2026-09-09' },
  { plate: 'CB551AA', owner: 'Logistica Conflavoro', role: 'Fornitore Corriere', active: true, date: '2026-09-10' }
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
  const tbody = document.getElementById('platesTableBody');
  const plates = getPlates();
  tbody.innerHTML = '';

  plates.forEach((p, index) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="plate-badge">${p.plate}</span></td>
      <td><strong>${p.owner}</strong></td>
      <td>${p.role}</td>
      <td><span class="status-tag ${p.active ? 'active' : ''}">${p.active ? 'Autorizzata' : 'Sospesa'}</span></td>
      <td>${p.date}</td>
      <td>
        <button class="btn-icon" title="Elimina" onclick="deletePlate(${index})">🗑️</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function deletePlate(index) {
  const plates = getPlates();
  if (confirm(`Rimuovere la targa ${plates[index].plate} dalla whitelist?`)) {
    plates.splice(index, 1);
    savePlates(plates);
  }
}

function openAddPlateModal() {
  document.getElementById('addPlateModal').classList.add('open');
}

function closeAddPlateModal() {
  document.getElementById('addPlateModal').classList.remove('open');
  document.getElementById('plateForm').reset();
}

function handleSavePlate(e) {
  e.preventDefault();
  const plate = document.getElementById('inputPlate').value.trim().toUpperCase();
  const owner = document.getElementById('inputOwner').value.trim();
  const role = document.getElementById('inputRole').value.trim();

  if (!plate || !owner) return;

  const plates = getPlates();
  plates.unshift({
    plate,
    owner,
    role,
    active: true,
    date: new Date().toISOString().split('T')[0]
  });

  savePlates(plates);
  closeAddPlateModal();
}

// ──────────────────────────────────────────────────────────────────────────────
// 5. REGISTRO EVENTI & PLAYER VIDEO NAS
// ──────────────────────────────────────────────────────────────────────────────
const mockEvents = [
  { time: 'Oggi 15:42:10', cam: 'Varco Carrabile', type: 'Targa Riconosciuta', desc: 'FG492KS (Rocco Di Tolla) - Cancello aperto', snapshot: 'https://images.unsplash.com/photo-1590674899484-d5640e854abe?auto=format&fit=crop&w=120&q=80', video: 'https://www.w3schools.com/html/mov_bbb.mp4' },
  { time: 'Oggi 15:35:04', cam: 'Varco Pedonale', type: 'Persona Rilevata', desc: 'Rilevamento perimetrale - Dissuasione avviata', snapshot: 'https://images.unsplash.com/photo-1541888946425-d0fbb186c5f3?auto=format&fit=crop&w=120&q=80', video: 'https://www.w3schools.com/html/mov_bbb.mp4' },
  { time: 'Oggi 14:18:22', cam: 'Piazzale', type: 'Persona Rilevata', desc: 'Faro acceso per 30s - Clip salvata su NAS', snapshot: 'https://images.unsplash.com/photo-1506521781263-d8422e82f27a?auto=format&fit=crop&w=120&q=80', video: 'https://www.w3schools.com/html/mov_bbb.mp4' }
];

function renderEvents() {
  const tbody = document.getElementById('eventsTableBody');
  tbody.innerHTML = '';

  mockEvents.forEach(evt => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${evt.time}</td>
      <td><strong>${evt.cam}</strong></td>
      <td><span class="status-tag ${evt.type.includes('Targa') ? 'active' : ''}">${evt.type}</span></td>
      <td>${evt.desc}</td>
      <td><img src="${evt.snapshot}" style="width:48px; height:28px; border-radius:4px; object-fit:cover;"></td>
      <td>
        <button class="primary-btn" style="padding:4px 10px; font-size:11px;" onclick="playEventVideo('${evt.cam} - ${evt.time}', '${evt.video}')">▶ Guarda Video</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function playEventVideo(meta, videoUrl) {
  document.getElementById('videoModalTitle').textContent = `Video Evento: ${meta}`;
  document.getElementById('videoModalMeta').textContent = meta;
  const player = document.getElementById('playerVideo');
  player.src = videoUrl;
  player.play().catch(() => {});
  document.getElementById('videoModal').classList.add('open');
}

function closeVideoModal() {
  const player = document.getElementById('playerVideo');
  player.pause();
  player.src = '';
  document.getElementById('videoModal').classList.remove('open');
}

function refreshEvents() {
  renderEvents();
}

// Inizializzazione iniziale
document.addEventListener('DOMContentLoaded', () => {
  renderPlates();
  renderEvents();
});
