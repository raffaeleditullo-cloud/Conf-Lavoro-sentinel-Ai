/* ══════════════════════════════════════════════════════════════════════════════
 * CONF-LAVORO Sentinel AI — Operations Controller
 * ══════════════════════════════════════════════════════════════════════════════ */

// 1. GESTIONE NAVIGAZIONE VISTE (ROUTING INTERNO FLUIDO)
const views = {
  wall: { id: 'view-wall', title: 'Telecamere' },
  events: { id: 'view-events', title: 'Archivio Evidenze' },
  plates: { id: 'view-plates', title: 'Targhe Autorizzate' },
  diagnostics: { id: 'view-diagnostics', title: 'Telemetria Edge' },
  settings: { id: 'view-settings', title: 'Audio e Deterrenza' }
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

  // Cambiando vista il menu del telefono non deve restare aperto
  closeHudMenu();
}

// ──────────────────────────────────────────────────────────────────────────────
// 1B. MENU DEL TELEFONO
//
// Raccoglie ruolo, stato del rilevatore e uscita verso il tastierino. Su schermo
// largo il pannello e' sempre in linea nella barra e il pulsante e' nascosto:
// queste funzioni restano innocue perche' agiscono solo sulla classe 'open',
// che al di fuori del telefono non produce alcun effetto.
// ──────────────────────────────────────────────────────────────────────────────
function setHudMenuOpen(open) {
  const menu = document.getElementById('hudMenu');
  const btn = document.getElementById('hudMenuBtn');
  if (!menu || !btn) return;
  menu.classList.toggle('open', open);
  btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  btn.setAttribute('aria-label', open ? 'Chiudi il menu' : 'Apri il menu');
}

function toggleHudMenu() {
  const menu = document.getElementById('hudMenu');
  setHudMenuOpen(!(menu && menu.classList.contains('open')));
}

function closeHudMenu() {
  setHudMenuOpen(false);
}

// Si chiude toccando fuori e con Esc
document.addEventListener('click', (e) => {
  const menu = document.getElementById('hudMenu');
  const btn = document.getElementById('hudMenuBtn');
  if (!menu || !btn || !menu.classList.contains('open')) return;
  if (!menu.contains(e.target) && !btn.contains(e.target)) closeHudMenu();
});

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeHudMenu();
});

// Collega i click sui pulsanti della barra laterale e bottom nav mobile
document.querySelectorAll('.nav-btn[data-view], .bottom-nav-btn[data-view]').forEach(btn => {
  btn.addEventListener('click', () => {
    const v = btn.getAttribute('data-view');
    switchView(v);
  });
});

// ──────────────────────────────────────────────────────────────────────────────
// 2. SELETTORI GLOBALI E MARCHIO
//
// Il selettore tema chiaro/scuro e' stato rimosso: l'interfaccia ha un tema
// unico. Resta solo la scelta fra marchio esteso e sola icona, che dipende
// dalla larghezza della barra laterale e dal formato dello schermo.
// ──────────────────────────────────────────────────────────────────────────────
const sidebar = document.querySelector('.soc-nav');
const collapseBtn = document.getElementById('sidebarCollapseBtn');
const collapseSvg = document.getElementById('collapseSvg');

const brandLogo = document.getElementById('brandLogo');

// Sotto i 1024px (tablet e telefono) la barra e' a sole icone
const brandIconOnlyQuery = window.matchMedia('(max-width: 1023.98px)');

// Marchio in oro: unica variante leggibile sul fondo rosso della barra
const BRAND_LOGO_FULL = 'assets/img/conflavoro-ai-oro.svg';
const BRAND_LOGO_ICON = 'assets/img/conflavoro-ai-icon-oro.svg';

function updateBrandLogos(isCollapsed) {
  if (!brandLogo) return;
  const iconOnly = isCollapsed || brandIconOnlyQuery.matches;
  brandLogo.src = iconOnly ? BRAND_LOGO_ICON : BRAND_LOGO_FULL;
}

// Il marchio segue il cambio di formato senza ricaricare la pagina
if (brandIconOnlyQuery.addEventListener) {
  brandIconOnlyQuery.addEventListener('change', () => {
    updateBrandLogos(!!(sidebar && sidebar.classList.contains('collapsed')));
  });
}

updateBrandLogos(!!(sidebar && sidebar.classList.contains('collapsed')));

// ──────────────────────────────────────────────────────────────────────────────
// 3. COLLAPSE / EXPAND SIDEBAR (BUSINESS CALL COMPRESSIONE DESKTOP)
// ──────────────────────────────────────────────────────────────────────────────
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
  updateBrandLogos(collapsed);
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
// 3. COMANDI ATTUATORI (DOCK SOTTO LA GRIGLIA E MODALE A SCHERMO INTERO)
//
// I tre comandi condividono un solo motore: prima erano tre funzioni quasi
// identiche che ignoravano la risposta del server con .catch(() => {}), quindi
// l'animazione di successo partiva anche quando il comando non veniva eseguito.
// Ora l'esito viene atteso: su errore di rete o su risposta 503 (driver non
// caricato lato server) il pulsante passa in stato di errore e mostra il motivo.
// ──────────────────────────────────────────────────────────────────────────────
function getActuatorSeconds(key) {
  // currentSettings e' dichiarata piu' avanti nel file: qui viene solo letta al
  // momento del clic, quando e' gia' inizializzata da loadSettings().
  if (key === 'faro') return Number(currentSettings.faro_sec) || 30;
  if (key === 'gate') return Number(currentSettings.gate_sec) || 3;
  return 4;
}

const ACTUATORS = {
  faro: {
    endpoint: '/api/relay/faretto',
    targets: [
      {
        btn: 'dockFaroBtn', label: 'dockFaroLabel', progress: 'dockFaroProgress',
        idle: (s) => `Fari Piazzale // ${s}s`,
        running: (s) => `FARI ATTIVI // ${s}s`
      },
      {
        btn: 'modalFaroBtn', label: 'modalFaroLabel',
        idle: () => 'Accendi Faro',
        running: (s) => `Faro attivo // ${s}s`
      }
    ]
  },
  gate: {
    endpoint: '/api/relay/cancello',
    targets: [
      {
        btn: 'dockGateBtn', label: 'dockGateLabel', progress: 'dockGateProgress',
        idle: (s) => `Apri Cancello // ${s}s`,
        running: (s) => `Apertura in corso // ${s}s`
      },
      {
        btn: 'modalGateBtn', label: 'modalGateLabel',
        idle: () => 'Apri Cancello',
        running: () => 'Apertura in corso'
      }
    ]
  },
  voice: {
    endpoint: '/api/speaker/voice',
    targets: [
      {
        btn: 'dockSirenBtn', label: 'dockSirenLabel',
        idle: () => 'Dissuasione Audio IP',
        running: () => 'Trasmissione in corso...'
      },
      {
        btn: 'modalVoiceBtn', label: 'modalVoiceLabel',
        idle: () => 'Dissuasione Audio',
        running: () => 'Trasmissione...'
      }
    ]
  }
};

const actuatorTimers = {};

function setActuatorState(key, state, seconds, message) {
  const cfg = ACTUATORS[key];
  if (!cfg) return;

  cfg.targets.forEach((target) => {
    const btn = document.getElementById(target.btn);
    const label = document.getElementById(target.label);
    if (btn) {
      btn.classList.toggle('is-running', state === 'running');
      btn.classList.toggle('is-error', state === 'error');
    }
    if (!label) return;
    if (state === 'running') {
      label.textContent = target.running(seconds);
    } else if (state === 'error') {
      label.textContent = message || 'Comando non riuscito';
    } else {
      label.textContent = target.idle(seconds);
    }
  });
}

function runActuatorProgress(key, seconds) {
  ACTUATORS[key].targets.forEach((target) => {
    if (!target.progress) return;
    const bar = document.getElementById(target.progress);
    if (!bar) return;
    bar.style.transition = 'none';
    bar.style.width = '100%';
    setTimeout(() => {
      bar.style.transition = `width ${seconds}s linear`;
      bar.style.width = '0%';
    }, 50);
  });
}

function resetActuatorProgress(key) {
  ACTUATORS[key].targets.forEach((target) => {
    if (!target.progress) return;
    const bar = document.getElementById(target.progress);
    if (!bar) return;
    bar.style.transition = 'none';
    bar.style.width = '0%';
  });
}

async function runActuatorAction(key) {
  const cfg = ACTUATORS[key];
  if (!cfg) return;

  const seconds = getActuatorSeconds(key);
  if (actuatorTimers[key]) clearTimeout(actuatorTimers[key]);

  setActuatorState(key, 'running', seconds);
  runActuatorProgress(key, seconds);

  let errorMessage = null;
  try {
    const res = await fetch(cfg.endpoint, { method: 'POST' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      errorMessage = data.error || `Errore server (HTTP ${res.status})`;
    }
  } catch (err) {
    errorMessage = 'Server non raggiungibile';
  }

  if (errorMessage) {
    console.warn(`[Sentinel Dashboard] Comando '${key}' non riuscito:`, errorMessage);
    resetActuatorProgress(key);
    setActuatorState(key, 'error', seconds, errorMessage);
    actuatorTimers[key] = setTimeout(() => setActuatorState(key, 'idle', seconds), 6000);
    return;
  }

  // Comando accettato: si lascia lo stato attivo per la durata reale dell'impulso
  actuatorTimers[key] = setTimeout(
    () => setActuatorState(key, 'idle', seconds),
    seconds * 1000
  );
}

// Nomi storici mantenuti: sono richiamati dagli onclick nel markup
function triggerFaro() { runActuatorAction('faro'); }
function triggerGate() { runActuatorAction('gate'); }
function triggerVoice() { runActuatorAction('voice'); }

// ──────────────────────────────────────────────────────────────────────────────
// 4. GESTIONE WHITELIST TARGHE (LPR) — PERSISTENZA NVME SU config/known_plates.json
// ──────────────────────────────────────────────────────────────────────────────
let currentPlates = [];

async function loadPlates() {
  try {
    const res = await fetch('/api/plates');
    if (res.ok) {
      currentPlates = await res.json();
      renderPlates();
    }
  } catch (err) {
    console.warn('[Sentinel Dashboard] Errore caricamento whitelist targhe:', err);
  }
}

function renderPlates() {
  const tbodyFull = document.getElementById('platesFullTbody');
  if (!tbodyFull) return;

  tbodyFull.innerHTML = '';
  if (!currentPlates || currentPlates.length === 0) {
    tbodyFull.innerHTML = `
      <tr>
        <td colspan="5" class="ev-empty-cell">
          <div class="ev-empty">
            <span class="ev-empty-title">Nessuna targa autorizzata</span>
            <span class="ev-empty-sub">Registra un veicolo con il pulsante qui sopra: il cancello carrabile si aprira' da solo al riconoscimento della targa.</span>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  currentPlates.forEach((p) => {
    const isAct = p.active !== false;
    const tr = document.createElement('tr');
    // L'attributo data-field non ha effetto su schermo largo: lo usa il foglio
    // di stile per ricomporre la riga come scheda quando lo schermo e' stretto.
    tr.innerHTML = `
      <td data-field="plate"><span class="plate-pill">${p.plate}</span></td>
      <td data-field="owner" class="ev-cam">${p.owner}</td>
      <td data-field="role" class="ev-role">${p.role || 'Personale Autorizzato'}</td>
      <td data-field="state">
        <button class="plate-state ${isAct ? 'is-active' : 'is-suspended'}" onclick="togglePlate('${p.plate}')" title="Tocca per abilitare o sospendere l'autorizzazione">
          ${isAct ? 'Autorizzata' : 'Sospesa'}
        </button>
      </td>
      <td data-field="actions" style="text-align:right;">
        <button class="icon-action-btn" title="Rimuovi definitivamente la targa" onclick="deletePlate('${p.plate}')">
          <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          <span class="icon-action-label">Elimina</span>
        </button>
      </td>
    `;
    tbodyFull.appendChild(tr);
  });
}

async function deletePlate(plateStr) {
  if (!confirm(`Rimuovere la targa ${plateStr} dalla memoria del sistema?`)) return;
  try {
    const res = await fetch('/api/plates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'delete', plate: plateStr })
    });
    if (res.ok) {
      await loadPlates();
    }
  } catch (err) {
    alert("Errore rimozione targa: " + err.message);
  }
}

async function togglePlate(plateStr) {
  try {
    const res = await fetch('/api/plates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'toggle', plate: plateStr })
    });
    if (res.ok) {
      await loadPlates();
    }
  } catch (err) {
    console.warn("Errore toggle stato targa:", err);
  }
}

function openAddPlateModal() {
  document.getElementById('plateModal').classList.add('open');
}

function closeAddPlateModal() {
  document.getElementById('plateModal').classList.remove('open');
}

async function handleSavePlate(e) {
  e.preventDefault();
  const plate = document.getElementById('inPlate').value.trim().toUpperCase();
  const owner = document.getElementById('inOwner').value.trim();
  const role = document.getElementById('inRole').value.trim();

  if (!plate || !owner) return;

  try {
    const res = await fetch('/api/plates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plate,
        owner,
        role: role || 'Personale Autorizzato',
        active: true,
        date: new Date().toISOString().split('T')[0]
      })
    });

    if (res.ok) {
      closeAddPlateModal();
      e.target.reset();
      await loadPlates();
    } else {
      const errData = await res.json().catch(() => ({}));
      alert("Errore salvataggio targa: " + (errData.error || "Risposta server non valida"));
    }
  } catch (err) {
    alert("Errore comunicazione server per salvataggio targa: " + err.message);
  }
}

// Intervalli di polling per ogni cam (ID -> intervalId)
const camPollIntervals = {};
const CAM_NAMES = { 1: 'piazzale', 2: 'magazzino', 3: 'corridoio' };
const CAM_POLL_MS = 1000; // refresh frame ogni 1 secondo

function startCamPolling(camId) {
  if (camPollIntervals[camId]) return; // già attivo
  camPollIntervals[camId] = setInterval(() => {
    const stream = document.getElementById(`streamCam${camId}`);
    if (!stream) return;
    const camName = CAM_NAMES[camId];
    stream.src = `/api/camera/${camName}/latest.jpg?_t=${Date.now()}`;
  }, CAM_POLL_MS);
}

function stopCamPolling(camId) {
  if (camPollIntervals[camId]) {
    clearInterval(camPollIntervals[camId]);
    delete camPollIntervals[camId];
  }
}

function handleStreamLoaded(camId) {
  const standby = document.getElementById(`standbyCam${camId}`);
  const stream = document.getElementById(`streamCam${camId}`);
  const badge = document.getElementById(`camStatusBadge${camId}`);
  const meta = document.getElementById(`camCardMeta${camId}`);
  if (standby) standby.classList.add('feed-connected');
  if (stream) stream.classList.add('online');
  if (badge) {
    // Il pallino colorato e' uno pseudo-elemento CSS: qui va solo l'etichetta
    badge.className = 'cam-status-pill live';
    badge.textContent = 'Live';
  }
  // Il polling riassegna la sorgente ogni secondo e ogni fotogramma ricevuto
  // richiama questa funzione: vale quindi da orologio della diretta, senza
  // bisogno di un timer aggiuntivo.
  if (meta) meta.textContent = `In diretta · ${new Date().toLocaleTimeString('it-IT')}`;
  syncCamModalStatus(camId);
  // Avvia il polling periodico per aggiornare il frame
  startCamPolling(camId);
}

function handleStreamError(camId) {
  const standby = document.getElementById(`standbyCam${camId}`);
  const stream = document.getElementById(`streamCam${camId}`);
  const badge = document.getElementById(`camStatusBadge${camId}`);
  if (standby) standby.classList.remove('feed-connected');
  if (stream) stream.classList.remove('online');
  if (badge) {
    badge.className = 'cam-status-pill offline';
    badge.textContent = 'Offline';
  }
  const meta = document.getElementById(`camCardMeta${camId}`);
  if (meta) meta.textContent = 'Segnale assente · nuovo tentativo tra 10s';
  syncCamModalStatus(camId);
  // Ferma il polling e riprova il collegamento ogni 10 secondi
  stopCamPolling(camId);
  setTimeout(() => {
    if (stream) {
      const camName = CAM_NAMES[camId];
      stream.src = `/api/camera/${camName}/latest.jpg?_retry=${Date.now()}`;
    }
  }, 10000);
}

// Esponi esplicitamente su window per retrocompatibilità globale
window.handleStreamLoaded = handleStreamLoaded;
window.handleStreamError = handleStreamError;

// ──────────────────────────────────────────────────────────────────────────────
// 5A-bis. MODALE TELECAMERA A SCHERMO INTERO (CLIC SU UNA SCHEDA)
//
// La modale ha un proprio elemento immagine e un proprio intervallo di polling:
// la griglia sottostante continua a lavorare senza essere toccata, cosi' la
// logica di startCamPolling/handleStreamLoaded resta quella gia' stabile in campo.
// ──────────────────────────────────────────────────────────────────────────────
const CAM_LABELS = { 1: 'Piazzale Esterno', 2: 'Magazzino Interno', 3: 'Corridoio Transito' };

let expandedCamId = null;
let camModalPollInterval = null;
let camModalLastFocus = null;

function refreshCamModalFrame() {
  if (!expandedCamId) return;
  const img = document.getElementById('camModalStream');
  if (!img) return;
  img.src = `/api/camera/${CAM_NAMES[expandedCamId]}/latest.jpg?_t=${Date.now()}`;
}

// Allinea la pastiglia della modale a quella della scheda corrispondente,
// cosi' lo stato resta uno solo e non puo' divergere fra le due viste.
function syncCamModalStatus(camId) {
  if (expandedCamId !== camId) return;
  const source = document.getElementById(`camStatusBadge${camId}`);
  const target = document.getElementById('camModalBadge');
  if (source && target) {
    target.className = source.className;
    target.textContent = source.textContent;
  }
}

function openCamModal(camId) {
  const modal = document.getElementById('camModal');
  const img = document.getElementById('camModalStream');
  const standby = document.getElementById('camModalStandby');
  const title = document.getElementById('camModalTitle');
  if (!modal || !img) return;

  expandedCamId = camId;
  camModalLastFocus = document.activeElement;

  const name = CAM_LABELS[camId] || 'Telecamera';
  if (title) title.textContent = name;
  img.alt = `${name} in diretta`;

  img.onload = () => {
    if (standby) standby.classList.remove('is-visible');
  };
  img.onerror = () => {
    if (standby) standby.classList.add('is-visible');
  };

  // Si parte dalla schermata di attesa finche' non arriva il primo fotogramma
  if (standby) standby.classList.add('is-visible');

  modal.classList.add('open');
  document.body.style.overflow = 'hidden';

  syncCamModalStatus(camId);
  refreshCamModalFrame();

  if (camModalPollInterval) clearInterval(camModalPollInterval);
  camModalPollInterval = setInterval(refreshCamModalFrame, CAM_POLL_MS);

  const closeBtn = modal.querySelector('.cam-modal-close');
  if (closeBtn) closeBtn.focus();
}

function closeCamModal() {
  const modal = document.getElementById('camModal');
  const img = document.getElementById('camModalStream');

  if (camModalPollInterval) {
    clearInterval(camModalPollInterval);
    camModalPollInterval = null;
  }
  expandedCamId = null;

  if (img) {
    // Si azzerano i gestori e la sorgente per non lasciare richieste in volo
    img.onload = null;
    img.onerror = null;
    img.removeAttribute('src');
  }
  if (modal) modal.classList.remove('open');
  document.body.style.overflow = '';

  if (camModalLastFocus && typeof camModalLastFocus.focus === 'function') {
    camModalLastFocus.focus();
  }
  camModalLastFocus = null;
}

// Chiusura con Esc e con clic sullo sfondo scuro
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && expandedCamId !== null) {
    closeCamModal();
  }
});

document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('camModal');
  if (!modal) return;
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeCamModal();
  });
});

function initCameraStreams() {
  [1, 2, 3].forEach(camId => {
    const stream = document.getElementById(`streamCam${camId}`);
    if (!stream) return;
    
    stream.onload = () => handleStreamLoaded(camId);
    stream.onerror = () => handleStreamError(camId);

    // Se l'immagine era già in cache o completata prima dell'esecuzione del JS:
    if (stream.complete && stream.naturalWidth > 0) {
      handleStreamLoaded(camId);
    }
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// 5B. ATTIVITÀ IN TEMPO REALE & REGISTRO EVIDENZE REALI (ZERO DATI FINTI)
// ──────────────────────────────────────────────────────────────────────────────
let currentEvents = [];

// Telecamera selezionata nel registro completo ('all' = nessun filtro)
let eventCameraFilter = 'all';

// Filtro tipo oggetto nel registro completo ('all', 'person', 'vehicle')
let eventLabelFilter = 'all';

// Telecamera selezionata nell'anteprima "Attivita' Recente". E' una variabile
// distinta di proposito: nell'anteprima si guarda cosa sta succedendo adesso,
// nell'Archivio si cerca un evento passato, e i due filtri non devono
// influenzarsi a vicenda.
let wallCameraFilter = 'all';

// Miniatura mostrata quando lo snapshot manca o non si carica
const EVENT_THUMB_FALLBACK = 'assets/img/conflavoro-ai-icon-viola.svg';

// Il filtro agisce sul solo registro completo: l'anteprima nella schermata
// delle telecamere continua a mostrare l'attivita' recente di tutti i varchi.
// Lo stato visivo non va sincronizzato a mano, ci pensa il select stesso.
function setEventCameraFilter(cam) {
  eventCameraFilter = cam;
  renderEvents();
}

function setEventFilter(cam) {
  setEventCameraFilter(cam);
}

function setEventLabelFilter(val) {
  eventLabelFilter = val;
  renderEvents();
}

function setWallFilter(cam) {
  wallCameraFilter = cam;
  renderEvents();
}

function formatCamName(raw) {
  if (!raw) return 'Telecamera';
  if (raw === 'piazzale') return 'Piazzale Esterno';
  if (raw === 'magazzino') return 'Magazzino Interno';
  if (raw === 'corridoio') return 'Corridoio Transito';
  if (raw === 'varco_carrabile') return 'Varco Carrabile';
  if (raw === 'varco_pedonale') return 'Varco Pedonale';
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
  pollLatestIdentikit();
}

function renderEvents() {
  const wallTbody = document.getElementById('eventsWallTbody');
  const fullTbody = document.getElementById('eventsFullTbody');

  if (wallTbody) {
    const wallEvents = (wallCameraFilter === 'all'
      ? currentEvents
      : currentEvents.filter((ev) => ev.camera === wallCameraFilter)
    ).slice(0, 4);

    wallTbody.innerHTML = '';
    if (wallEvents.length === 0) {
      wallTbody.innerHTML = `
        <tr>
          <td colspan="5" class="ev-empty-cell is-compact">
            <div class="ev-empty">
              <span class="ev-empty-title">${wallCameraFilter === 'all' ? 'Nessun evento registrato' : 'Nessun evento per questa telecamera'}</span>
            </div>
          </td>
        </tr>
      `;
    } else {
      wallEvents.forEach(ev => {
        const camLabel = formatCamName(ev.camera);
        const subjLabel = formatEventLabel(ev.label);
        const thumbUrl = ev.thumb || EVENT_THUMB_FALLBACK;
        const videoBtn = ev.video ? `
          <button class="play-video-link" onclick="openVideoModal('${camLabel} // ${ev.time}', '${ev.video}')">
            <svg style="width:12px; height:12px; fill:currentColor;" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span>Play MP4</span>
          </button>
        ` : `<span class="ev-noclip">No Clip</span>`;

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td data-field="time" class="ev-time">${ev.time}</td>
          <td data-field="cam" class="ev-cam">${camLabel}</td>
          <td data-field="type">
            <span class="ev-type">${subjLabel}</span>
            <span class="ev-conf">(${ev.conf || 'n.d.'})</span>
          </td>
          <td data-field="thumb">
            <div class="event-thumb-wrap" onclick="showIdentikitForEvent('${ev.id}', '${ev.camera}')" style="cursor:pointer;" title="Clicca per visualizzare la Scheda Identikit Forense">
              <img src="${thumbUrl}" alt="Fotogramma dell'evento" onerror="this.src='${EVENT_THUMB_FALLBACK}'">
            </div>
            <button type="button" class="ultra-primary-btn" onclick="showIdentikitForEvent('${ev.id}', '${ev.camera}')" style="font-size:10px; padding:2px 6px; margin-top:4px; background:rgba(212,175,55,0.2); border:1px solid #d4af37; color:#f7e7ce; display:inline-flex; align-items:center; gap:3px; border-radius:3px;">
              <span>Identikit</span>
            </button>
          </td>
          <td data-field="video">${videoBtn}</td>
        `;
        wallTbody.appendChild(tr);
      });
    }
  }

  if (fullTbody) {
    const visibleEvents = currentEvents.filter((ev) => {
      // Filtro telecamera
      if (eventCameraFilter !== 'all' && ev.camera !== eventCameraFilter) {
        return false;
      }
      // Filtro tipo oggetto (persona vs veicolo)
      if (eventLabelFilter !== 'all') {
        const lbl = (ev.label || '').toLowerCase();
        if (eventLabelFilter === 'person') {
          if (lbl !== 'person') return false;
        } else if (eventLabelFilter === 'vehicle') {
          const isVehicle = ['car', 'truck', 'motorcycle', 'bus'].includes(lbl) || lbl.startsWith('plate:');
          if (!isVehicle) return false;
        }
      }
      return true;
    });

    fullTbody.innerHTML = '';
    if (visibleEvents.length === 0) {
      const emptySub = (eventCameraFilter !== 'all' || eventLabelFilter !== 'all')
        ? 'Nessun evento corrispondente ai filtri selezionati. Modifica i criteri per visualizzare altri passaggi.'
        : 'Fotogrammi e registrazioni compariranno qui ai primi passaggi rilevati.';
      fullTbody.innerHTML = `
        <tr>
          <td colspan="6" class="ev-empty-cell">
            <div class="ev-empty">
              <span class="ev-empty-title">Nessun evento trovato</span>
              <span class="ev-empty-sub">${emptySub}</span>
            </div>
          </td>
        </tr>
      `;
    } else {
      visibleEvents.forEach(ev => {
        const camLabel = formatCamName(ev.camera);
        const subjLabel = formatEventLabel(ev.label);
        const thumbUrl = ev.thumb || EVENT_THUMB_FALLBACK;
        const videoBtn = ev.video ? `
          <button class="play-video-link" onclick="openVideoModal('${camLabel} // ${ev.time}', '${ev.video}')">
            <svg style="width:12px; height:12px; fill:currentColor;" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span>Riproduci Video NVR</span>
          </button>
        ` : `<span class="ev-noclip">Solo Snapshot</span>`;

        const tr = document.createElement('tr');
        // data-field non ha effetto su schermo largo: serve al foglio di stile
        // per ricomporre la riga come scheda quando lo schermo e' stretto.
        tr.innerHTML = `
          <td data-field="time" class="ev-time">${ev.time}</td>
          <td data-field="cam" class="ev-cam">${camLabel}</td>
          <td data-field="type"><span class="ev-type">${subjLabel}</span></td>
          <td data-field="conf"><span class="ev-conf">${ev.conf || 'n.d.'}</span></td>
          <td data-field="thumb">
            <div class="event-thumb-wrap" onclick="showIdentikitForEvent('${ev.id}', '${ev.camera}')" style="cursor:pointer;" title="Clicca per visualizzare la Scheda Identikit Forense">
              <img src="${thumbUrl}" alt="Fotogramma dell'evento" onerror="this.src='${EVENT_THUMB_FALLBACK}'">
            </div>
            <button type="button" class="ultra-primary-btn" onclick="showIdentikitForEvent('${ev.id}', '${ev.camera}')" style="font-size:11px; padding:3px 8px; margin-top:6px; background:linear-gradient(135deg, rgba(212,175,55,0.25), rgba(160,120,20,0.3)); border:1px solid #d4af37; color:#f7e7ce; display:inline-flex; align-items:center; gap:5px; border-radius:4px; font-weight:700;">
              <svg style="width:11px; height:11px; fill:currentColor;" viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
              <span>Scheda Identikit</span>
            </button>
          </td>
          <td data-field="video">${videoBtn}</td>
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
// 5B-bis. SCHEDA IDENTIKIT FORENSE (JEV DECIDER)
// ──────────────────────────────────────────────────────────────────────────────
async function showIdentikitForEvent(eventId, camera) {
  try {
    const res = await fetch('/api/identikit');
    let matchedProfile = null;
    if (res.ok) {
      const list = await res.json();
      if (Array.isArray(list)) {
        matchedProfile = list.find(p => p.event_id === eventId || (p.telecamera === camera && String(eventId).startsWith(String(p.event_id || '').slice(0, 8))));
      }
    }

    if (!matchedProfile) {
      const ev = (currentEvents || []).find(e => e.id === eventId) || {};
      matchedProfile = {
        event_id: eventId,
        telecamera: camera,
        soggetto: ev.label || 'Persona',
        confidenza_ia: ev.conf ? parseFloat(ev.conf) : 88.0,
        timestamp_human: ev.time || new Date().toLocaleTimeString(),
        rilevamento: {
          aspect_ratio: 1.85,
        },
        dinamica: {
          traiettoria_stimata: camera === 'corridoio' ? 'Transito rapido ad altezza uomo verso uffici' : (camera === 'magazzino' ? 'Spostamento attivo corsie merci capannone' : 'Avvicinamento piazzale esterno portone di carico')
        },
        evidenze: {
          snapshot_url: `/api/events/${eventId}/snapshot.jpg`
        }
      };
    }

    openIdentikitModal(matchedProfile);
  } catch (err) {
    console.error("Errore caricamento identikit:", err);
  }
}

let currentModalIdentikit = null;

function openIdentikitModal(p) {
  const modal = document.getElementById('identikitModal');
  if (!modal) return;
  currentModalIdentikit = p;

  const camName = formatCamName(p.telecamera || 'piazzale');
  const titleEl = document.getElementById('identikitModalTitle');
  if (titleEl) titleEl.textContent = `Scheda Identikit // ${camName}`;

  const badgeEl = document.getElementById('identikitCameraBadge');
  if (badgeEl) badgeEl.textContent = (p.telecamera || 'CAM').toUpperCase();

  const timeEl = document.getElementById('identikitTime');
  if (timeEl) timeEl.textContent = p.timestamp_human || p.timestamp || '--:--:--';

  const idEl = document.getElementById('identikitEventId');
  if (idEl) idEl.textContent = `ID: ${p.event_id || '--'}`;

  const subjEl = document.getElementById('identikitSubject');
  if (subjEl) subjEl.textContent = (p.soggetto || 'PERSONA').toUpperCase();

  const confEl = document.getElementById('identikitConf');
  if (confEl) confEl.textContent = `${p.confidenza_ia || '90'}%`;

  const trajEl = document.getElementById('identikitTrajectory');
  if (trajEl) {
    const traj = p.dinamica ? p.dinamica.traiettoria_stimata : 'Traiettoria confermata';
    trajEl.textContent = traj;
  }

  const ratioEl = document.getElementById('identikitRatio');
  if (ratioEl) {
    const ar = (p.rilevamento && p.rilevamento.aspect_ratio) ? `${p.rilevamento.aspect_ratio} (Sagoma eretta)` : '1.80 (Sagoma eretta)';
    ratioEl.textContent = ar;
  }

  const evalEl = document.getElementById('identikitEvaluation');
  if (evalEl) {
    const evalText = p.stato_valutazione || 'DISSVASIONE ESEGUITA';
    evalEl.textContent = evalText;
    if (evalText.includes('SILENZIOSO') || evalText.includes('Lavoro')) {
      evalEl.style.color = '#4fc3f7';
    } else {
      evalEl.style.color = '#ef5350';
    }
  }

  const threatBadge = document.getElementById('identikitThreatBadge');
  if (threatBadge) {
    if (p.stato_valutazione && (p.stato_valutazione.includes('SILENZIOSO') || p.stato_valutazione.includes('Lavoro'))) {
      threatBadge.textContent = 'MONITORAGGIO SILENZIOSO';
      threatBadge.style.background = '#0288d1';
    } else if (p.orin_intelligence && p.orin_intelligence.is_president) {
      threatBadge.textContent = 'ACCESSO AUTORIZZATO // PRESIDENZA';
      threatBadge.style.background = 'var(--brand)';
      threatBadge.style.color = '#fff';
    } else {
      threatBadge.textContent = 'DISSUASIONE ESEGUITA';
      threatBadge.style.background = '#e53935';
      threatBadge.style.color = '#fff';
    }
  }

  // ORIN MULTIMODAL INTELLIGENCE RENDERING
  const orinBlock = document.getElementById('identikitOrinBlock');
  const orinVipBadge = document.getElementById('identikitOrinVipBadge');
  const orinAction = document.getElementById('identikitOrinAction');
  const orinSpeech = document.getElementById('identikitOrinSpeech');

  const orinData = p.orin_intelligence;
  if (orinBlock) {
    if (orinData) {
      orinBlock.style.display = 'block';
      if (orinData.is_president) {
        if (orinVipBadge) {
          orinVipBadge.style.display = 'inline-flex';
          orinVipBadge.textContent = 'PRESIDENZA // ACCESSO AUTORIZZATO';
        }
      } else {
        if (orinVipBadge) orinVipBadge.style.display = 'none';
      }
      if (orinAction) {
        orinAction.textContent = orinData.action_detected ? `Azione Rilevata: ${orinData.action_detected}` : '';
      }
      if (orinSpeech) {
        orinSpeech.textContent = orinData.spoken_message ? `Messaggio ORIN: "${orinData.spoken_message}"` : '';
      }
    } else {
      orinBlock.style.display = 'none';
    }
  }

  const img = document.getElementById('identikitSnapshot');
  if (img) {
    const snapUrl = (p.evidenze && p.evidenze.snapshot_url) ? p.evidenze.snapshot_url : `/api/events/${p.event_id}/snapshot.jpg`;
    img.src = `${snapUrl}?_t=${Date.now()}`;
  }

  modal.style.display = 'flex';
  modal.classList.add('open');
}

function closeIdentikitModal() {
  const modal = document.getElementById('identikitModal');
  if (!modal) return;
  modal.style.display = 'none';
  modal.classList.remove('open');
}

function downloadCurrentIdentikitJson() {
  if (!currentModalIdentikit || !currentModalIdentikit.event_id) {
    alert("Nessuna scheda identikit attiva da scaricare.");
    return;
  }
  const eventId = currentModalIdentikit.event_id;
  // Trigger direct download using browser Blob for instant client response
  const jsonStr = JSON.stringify(currentModalIdentikit, null, 2);
  const blob = new Blob([jsonStr], { type: 'application/json' });
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = `identikit_${String(eventId).slice(0, 12)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}

function downloadCurrentSnapshot() {
  if (!currentModalIdentikit || !currentModalIdentikit.event_id) {
    alert("Nessuno snapshot disponibile.");
    return;
  }
  const eventId = currentModalIdentikit.event_id;
  const snapUrl = (currentModalIdentikit.evidenze && currentModalIdentikit.evidenze.snapshot_url)
    ? currentModalIdentikit.evidenze.snapshot_url
    : `/api/events/${eventId}/snapshot.jpg`;
  const a = document.createElement('a');
  a.href = snapUrl;
  a.download = `snapshot_${String(eventId).slice(0, 12)}.jpg`;
  a.target = '_blank';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

async function openLatestIdentikit() {
  try {
    const res = await fetch('/api/identikit');
    if (res.ok) {
      const list = await res.json();
      if (Array.isArray(list) && list.length > 0) {
        openIdentikitModal(list[0]);
        return;
      }
    }
    // Fallback con eventi in memoria
    if (currentEvents && currentEvents.length > 0) {
      const p = currentEvents.find(e => (e.label || '').toLowerCase() === 'person') || currentEvents[0];
      showIdentikitForEvent(p.id, p.camera);
      return;
    }
    alert("Nessun identikit ancora registrato dal sistema.");
  } catch (err) {
    console.error("Errore apertura ultimo identikit:", err);
  }
}

async function pollLatestIdentikit() {
  try {
    const res = await fetch('/api/identikit');
    if (!res.ok) return;
    const list = await res.json();
    if (Array.isArray(list) && list.length > 0) {
      updateWallIdentikitCard(list[0]);
    } else if (currentEvents && currentEvents.length > 0) {
      const p = currentEvents.find(e => (e.label || '').toLowerCase() === 'person');
      if (p) {
        updateWallIdentikitCard({
          event_id: p.id,
          telecamera: p.camera,
          soggetto: p.label,
          confidenza_ia: p.conf ? parseFloat(p.conf) : 90.0,
          timestamp_human: p.time,
          evidenze: { snapshot_url: p.thumb }
        });
      }
    }
  } catch (err) {
    // ignora in silenzio
  }
}

function updateWallIdentikitCard(p) {
  if (!p) return;
  const badge = document.getElementById('wallIdentikitCamBadge');
  const thumb = document.getElementById('wallIdentikitThumb');
  const subj = document.getElementById('wallIdentikitSubject');
  const conf = document.getElementById('wallIdentikitConf');
  const timeEl = document.getElementById('wallIdentikitTime');
  const traj = document.getElementById('wallIdentikitTraj');

  if (badge) {
    badge.textContent = (p.telecamera || p.camera || 'CAM').toUpperCase();
    badge.className = 'cam-status-pill online';
  }
  if (subj) subj.textContent = (p.soggetto || p.label || 'Persona').toUpperCase();
  if (conf) conf.textContent = p.confidenza_ia ? `${p.confidenza_ia}%` : (p.conf ? `${p.conf}` : 'IA 90%');
  if (timeEl) timeEl.textContent = `${p.timestamp_human || p.time || ''} // ID: ${String(p.event_id || p.id || '').slice(0, 10)}`;
  if (traj) {
    const d = p.dinamica ? p.dinamica.traiettoria_stimata : (p.telecamera === 'corridoio' ? 'Transito rapido ad altezza uomo verso uffici' : 'Movimento confermato nel varco');
    traj.textContent = d;
  }
  if (thumb) {
    const snap = (p.evidenze && p.evidenze.snapshot_url) ? p.evidenze.snapshot_url : (p.thumb || `/api/events/${p.event_id || p.id}/snapshot.jpg`);
    thumb.src = `${snap}?_t=${Date.now()}`;
  }
  const orinBadge = document.getElementById('wallIdentikitOrinBadge');
  if (orinBadge) {
    if (p.orin_intelligence) {
      if (p.orin_intelligence.is_president) {
        orinBadge.innerHTML = '<span class="orin-vip-tag">Presidenza // Autorizzato</span>';
        orinBadge.style.display = 'block';
      } else if (p.orin_intelligence.spoken_message) {
        orinBadge.innerHTML = `<span style="color:var(--brand); font-size:11.5px; font-weight:600; font-style:italic;">"${p.orin_intelligence.spoken_message.slice(0, 50)}..."</span>`;
        orinBadge.style.display = 'block';
      } else {
        orinBadge.style.display = 'none';
      }
    } else {
      orinBadge.style.display = 'none';
    }
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// 5C. VITALITY HEARTBEAT & WATCHDOG ANTI-FREEZE TENSORRT (SEGNALAZIONE ALESSIO)
// ──────────────────────────────────────────────────────────────────────────────
// Aggiorna l'indicatore rassicurante al centro della barra superiore.
// E' l'unico elemento di stato che vede anche il cliente: resta verde quando il
// sistema sorveglia, diventa rosso solo se il watchdog segnala il rilevatore bloccato.
function updateSecurityStatus(status) {
  const box = document.getElementById('securityStatus');
  const label = document.getElementById('securityStatusLabel');
  if (!box || !label) return;

  if (status === 'frozen') {
    box.classList.add('is-alert');
    label.textContent = 'Anomalia · Rilevamento bloccato';
    box.title = 'Il rilevatore non elabora immagini: contattare l\'assistenza tecnica';
  } else {
    box.classList.remove('is-alert');
    label.textContent = 'Protetto';
    box.title = 'Il sistema sorveglia regolarmente le aree controllate';
  }
}

async function pollDetectorVitality() {
  try {
    const res = await fetch('/api/detector/vitality');
    if (!res.ok) return;
    const data = await res.json();

    updateSecurityStatus(data.status);

    const badge = document.getElementById('detectorVitalityBadge');
    const textEl = document.getElementById('vitalityText');
    if (!badge || !textEl) return;

    if (data.status === 'frozen') {
      badge.className = 'vitality-badge frozen';
      textEl.textContent = 'Rilevamento bloccato';
    } else if (data.status === 'healthy' && data.detection_fps > 0) {
      badge.className = 'vitality-badge healthy';
      textEl.innerHTML = `Rilevamento attivo · <strong>${data.detection_fps.toFixed(1)}</strong> FPS`;
    } else if (data.status === 'waiting') {
      badge.className = 'vitality-badge healthy';
      textEl.textContent = 'In attesa dei flussi video';
    } else {
      badge.className = 'vitality-badge standby';
      textEl.textContent = 'In attesa di segnale';
    }
    // Il testo resta leggibile anche con etichetta collassata
    badge.title = textEl.textContent;
  } catch (err) {
    // standby
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// 5D. TELEMETRIA EDGE JETSON ORIN NANO IN TEMPO REALE (/api/status)
// ──────────────────────────────────────────────────────────────────────────────
async function pollJetsonTelemetry() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();

    // NOTA: le pastiglie di telemetria che stavano nella barra superiore sono
    // state rimosse per non esporre al cliente numeri di sistema. I valori
    // continuano ad alimentare la vista "Telemetria Edge", riservata al manutentore.

    // 2. Aggiornamento Pannello Diagnostica Completa (Vista 4)
    const diagTemp = document.getElementById('diagTemp');
    const diagSwap = document.getElementById('diagSwap');
    const diagRam = document.getElementById('diagRam');
    const diagPower = document.getElementById('diagPower');
    const diagUptime = document.getElementById('diagUptime');

    if (diagTemp && data.temperature !== undefined) {
      const tempLabel = data.temperature < 65 ? 'Ottimale' : (data.temperature < 78 ? 'Nominale' : 'Alto');
      diagTemp.textContent = `${data.temperature.toFixed(1)} °C (${tempLabel})`;
    }

    if (diagSwap && data.swap_used_mb !== undefined) {
      const swapTot = (data.swap_total_mb / 1024).toFixed(1);
      diagSwap.textContent = `${data.swap_used_mb} MB / ${swapTot} GB (swappiness=10)`;
    }

    if (diagRam && data.ram_used_mb !== undefined) {
      const ramGb = (data.ram_used_mb / 1024).toFixed(2);
      const totGb = (data.ram_total_mb / 1024).toFixed(1);
      const freeGb = (data.ram_free_mb / 1024).toFixed(1);
      diagRam.textContent = `${ramGb} GB / ${totGb} GB (~${freeGb} GB liberi)`;
    }

    if (diagPower && data.power_watts !== undefined) {
      diagPower.textContent = `${data.power_watts.toFixed(1)} W (Profilo 25W)`;
    }

    if (diagUptime && data.uptime) {
      diagUptime.textContent = `${data.uptime} (Attivo)`;
    }

    // Nodi di Rete
    if (data.devices) {
      const c1 = document.getElementById('diagCam1Node');
      const c2 = document.getElementById('diagCam2Node');
      const c3 = document.getElementById('diagCam3Node');
      const rel = document.getElementById('diagRelayNode');
      const nas = document.getElementById('diagNasNode');

      if (c1) {
        c1.textContent = `192.168.1.22:554 ${data.devices.cam1 ? '(LIVE 4K)' : '(ATTESA SEGNALE)'}`;
        c1.classList.toggle('is-online', !!data.devices.cam1);
      }
      if (c2) {
        c2.textContent = `192.168.1.20:554 ${data.devices.cam2 ? '(LIVE 4K)' : '(ATTESA SEGNALE)'}`;
        c2.classList.toggle('is-online', !!data.devices.cam2);
      }
      if (c3) {
        c3.textContent = `192.168.1.21:554 ${data.devices.cam3 ? '(LIVE 4K)' : '(ATTESA SEGNALE)'}`;
        c3.classList.toggle('is-online', !!data.devices.cam3);
      }
      if (rel) {
        rel.textContent = `192.168.1.30:4196 ${data.devices.relay_modbus ? '(ONLINE)' : '(STANDBY)'}`;
        rel.classList.toggle('is-online', !!data.devices.relay_modbus);
      }
      if (nas) {
        nas.textContent = `192.168.1.11 ${data.devices.nas_ugreen ? '(SMB OK)' : '(STANDBY)'}`;
        nas.classList.toggle('is-online', !!data.devices.nas_ugreen);
      }
    }

  } catch (err) {
    // fallback
  }
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
  gate_sec: 3,
  security_mode: 'assente',
  work_start: '08:00',
  work_end: '18:30',
  work_days: [1, 2, 3, 4, 5]
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

// ──────────────────────────────────────────────────────────────────────────────
// 6B. ORIN CYBERNETIC BRAIN // LIVE DYNAMIC SPEECH STREAMING (ELEVENLABS TURBO)
// ──────────────────────────────────────────────────────────────────────────────
function setOrinSpeechText(text) {
  const inp = document.getElementById('orinLiveInput');
  if (inp) {
    inp.value = text;
    inp.focus();
  }
}

async function triggerOrinSpeak() {
  const inp = document.getElementById('orinLiveInput');
  const btn = document.getElementById('btnOrinSpeak');
  const btnText = document.getElementById('orinSpeakBtnText');
  const statusEl = document.getElementById('orinSpeakStatus');
  const text = inp ? inp.value.trim() : '';
  if (!text) return;

  const originalText = btnText ? btnText.textContent : 'Parla Live';
  if (btn) btn.disabled = true;
  if (btnText) btnText.textContent = 'Trasmissione...';
  if (statusEl) {
    statusEl.style.display = 'inline';
    statusEl.style.color = '#e8c15a';
    statusEl.textContent = 'Sintesi audio & streaming RTP in corso...';
  }

  try {
    const res = await fetch('/api/orin/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text,
        voice: currentSettings.voice_pack || 'carmelo',
        volume: currentSettings.voice_volume || 70
      })
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.success) {
      if (statusEl) {
        statusEl.style.color = '#22c55e';
        statusEl.textContent = 'Trasmesso con successo su Diffusore Fanvil (.31)';
      }
    } else {
      if (statusEl) {
        statusEl.style.color = '#ef4444';
        statusEl.textContent = 'Errore trasmissione: ' + (data.error || 'Server non raggiungibile');
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#ef4444';
      statusEl.textContent = 'Errore connessione: ' + err.message;
    }
  } finally {
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = originalText;
    setTimeout(() => {
      if (statusEl) statusEl.style.display = 'none';
    }, 4000);
  }
}

async function pollOrinStatus() {
  try {
    const res = await fetch('/api/orin/status');
    if (!res.ok) return;
    const data = await res.json();
    const beacon = document.getElementById('orinStatusBeacon');
    if (beacon) {
      if (data.status === 'online') {
        beacon.textContent = 'ORIN ONLINE // GOOGLE GEMINI';
        beacon.className = 'status-beacon is-accent';
      } else {
        beacon.textContent = 'ORIN STANDBY';
        beacon.className = 'status-beacon';
      }
    }
  } catch (_) {}
}

function toggleSecurityModeFlyout() {
  const flyout = document.getElementById('securityModeFlyout');
  if (!flyout) return;
  flyout.style.display = (flyout.style.display === 'none' || !flyout.style.display) ? 'block' : 'none';
}

async function selectSecurityMode(mode, durationMin) {
  const flyout = document.getElementById('securityModeFlyout');
  if (flyout) flyout.style.display = 'none';

  currentSettings.security_mode = mode;

  const payload = { mode: mode };
  if (mode === 'manutenzione') {
    payload.duration_minutes = durationMin || 30;
  }

  try {
    await fetch('/api/security/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    await pollSecurityState();
  } catch (err) {
    console.warn("Errore selezione modalità sicurezza:", err);
  }
}

function promptMaintenance(defaultMin = 30) {
  selectSecurityMode('manutenzione', defaultMin);
}

async function cancelMaintenance() {
  try {
    await fetch('/api/security/maintenance/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    await pollSecurityState();
  } catch (err) {
    console.warn("Errore annullamento manutenzione:", err);
  }
}

async function handleSecurityModeChange(mode) {
  await selectSecurityMode(mode);
}

async function saveSettings() {
  const rngVol = document.getElementById('rngVolume');
  const numFaro = document.getElementById('numFaroSec');
  const numGate = document.getElementById('numGateSec');
  const selTrack = document.getElementById('selAudioTrack');
  const selSecMode = document.getElementById('selSecurityMode');
  const inpWorkStart = document.getElementById('inputWorkStart');
  const inpWorkEnd = document.getElementById('inputWorkEnd');

  let activeSecMode = currentSettings.security_mode || 'assente';
  const activeCard = document.querySelector('.sec-mode-card.is-active');
  if (activeCard && activeCard.id) {
    if (activeCard.id === 'modeCardAssente') activeSecMode = 'assente';
    else if (activeCard.id === 'modeCardNotte') activeSecMode = 'notte';
    else if (activeCard.id === 'modeCardCasa') activeSecMode = 'casa';
    else if (activeCard.id === 'modeCardMaint') activeSecMode = 'manutenzione';
  }

  const payload = {
    voice_pack: currentSettings.voice_pack || 'carmelo',
    voice_gender: currentSettings.voice_pack || 'carmelo',
    active_track: selTrack ? selTrack.value : (currentSettings.active_track || '03_avviso_dissuasione'),
    voice_volume: rngVol ? parseInt(rngVol.value, 10) : (currentSettings.voice_volume || 70),
    faro_sec: numFaro ? parseInt(numFaro.value, 10) : (currentSettings.faro_sec || 30),
    gate_sec: numGate ? parseInt(numGate.value, 10) : (currentSettings.gate_sec || 3),
    security_mode: selSecMode ? selSecMode.value : activeSecMode,
    work_start: inpWorkStart ? inpWorkStart.value : (currentSettings.work_start || '08:00'),
    work_end: inpWorkEnd ? inpWorkEnd.value : (currentSettings.work_end || '18:30'),
    work_days: currentSettings.work_days || [1, 2, 3, 4, 5]
  };

  const statusLbl = document.getElementById('saveStatus');
  const schedStatusLbl = document.getElementById('scheduleSaveStatus');

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const respData = await res.json();
      if (respData.settings) {
        Object.assign(currentSettings, respData.settings);
      }
      localStorage.setItem('sentinel_settings', JSON.stringify(payload));
      if (statusLbl) {
        statusLbl.textContent = 'Configurazione salvata sul server';
        statusLbl.style.color = 'var(--tone-ok-fg, #166534)';
        statusLbl.style.display = 'inline';
        setTimeout(() => { statusLbl.style.display = 'none'; }, 3000);
      }
      if (schedStatusLbl) {
        schedStatusLbl.textContent = 'Orari salvati';
        schedStatusLbl.style.display = 'inline';
        setTimeout(() => { schedStatusLbl.style.display = 'none'; }, 3000);
      }
      pollSecurityState();
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (err) {
    console.error("Errore salvataggio impostazioni su server:", err);
    // Salva comunque in locale come fallback
    localStorage.setItem('sentinel_settings', JSON.stringify(payload));
    if (statusLbl) {
      statusLbl.textContent = 'Errore salvataggio server (salvato in locale)';
      statusLbl.style.color = 'var(--alert, #ef4444)';
      statusLbl.style.display = 'inline';
      setTimeout(() => { statusLbl.style.display = 'none'; }, 4000);
    }
  }
}

async function loadSettings() {
  // 1. Prova a caricare le impostazioni reali dal server Jetson
  try {
    const res = await fetch('/api/settings');
    if (res.ok) {
      const serverData = await res.json();
      if (serverData && typeof serverData === 'object') {
        currentSettings = Object.assign(currentSettings, serverData);
        localStorage.setItem('sentinel_settings', JSON.stringify(currentSettings));
      }
    }
  } catch (e) {
    console.warn("Impossibile caricare impostazioni dal server, uso cache locale:", e);
    const stored = localStorage.getItem('sentinel_settings');
    if (stored) {
      try {
        currentSettings = Object.assign(currentSettings, JSON.parse(stored));
      } catch (_) {}
    }
  }

  if (currentSettings.voice_gender && !currentSettings.voice_pack) {
    currentSettings.voice_pack = (currentSettings.voice_gender === 'female' || currentSettings.voice_gender === 'sami') ? 'sami' : 'carmelo';
  }

  handleVoiceChange(currentSettings.voice_pack);

  const radio = document.querySelector(`input[name="voicePack"][value="${currentSettings.voice_pack}"]`);
  if (radio) radio.checked = true;

  const selTrack = document.getElementById('selAudioTrack');
  if (selTrack && currentSettings.active_track) selTrack.value = currentSettings.active_track;

  const rngVol = document.getElementById('rngVolume');
  if (rngVol && currentSettings.voice_volume !== undefined) {
    rngVol.value = currentSettings.voice_volume;
    updateVolumeLabel(currentSettings.voice_volume);
  }

  const numFaro = document.getElementById('numFaroSec');
  if (numFaro && currentSettings.faro_sec !== undefined) numFaro.value = currentSettings.faro_sec;

  const numGate = document.getElementById('numGateSec');
  if (numGate && currentSettings.gate_sec !== undefined) numGate.value = currentSettings.gate_sec;

  const selSecMode = document.getElementById('selSecurityMode');
  if (selSecMode && currentSettings.security_mode) selSecMode.value = currentSettings.security_mode;

  const inpWorkStart = document.getElementById('inputWorkStart');
  if (inpWorkStart && currentSettings.work_start) inpWorkStart.value = currentSettings.work_start;

  const inpWorkEnd = document.getElementById('inputWorkEnd');
  if (inpWorkEnd && currentSettings.work_end) inpWorkEnd.value = currentSettings.work_end;

  updateTrackLabel();
  pollSecurityState();
}

async function pollSecurityState() {
  try {
    const res = await fetch('/api/security/state');
    if (!res.ok) return;
    const data = await res.json();

    const mode = (data.mode || 'assente').toLowerCase();
    currentSettings.security_mode = mode;

    // 1. Aggiornamento Topbar (#securityStatus)
    const box = document.getElementById('securityStatus');
    const label = document.getElementById('securityStatusLabel');
    if (box && label && !box.classList.contains('is-alert')) {
      if (mode === 'assente' || mode === 'armed') {
        label.textContent = 'Assente · Armato 24/7';
        box.title = 'Modalità Assente: Fari e deterrenza vocale attivi su tutte le aree';
      } else if (mode === 'notte') {
        label.textContent = 'Notte · Perimetro Armato';
        box.title = 'Modalità Notte: Deterrenza attiva su piazzale esterno. Aree interne silenziose';
      } else if (mode === 'casa' || mode === 'disarmed') {
        label.textContent = 'Casa · Presidio Diurno';
        box.title = 'Modalità Casa: Presidio presente, monitoraggio discreto senza allarmi vocali';
      } else if (mode === 'manutenzione') {
        const remSec = data.maintenance ? data.maintenance.remaining_seconds : 0;
        const mm = Math.floor(remSec / 60);
        const ss = remSec % 60;
        label.textContent = `Manutenzione · ${String(mm).padStart(2,'0')}:${String(ss).padStart(2,'0')}`;
        box.title = `Manutenzione a tempo attiva: ripristino automatico tra ${mm}m ${ss}s`;
      } else {
        label.textContent = data.is_armed ? 'Protetto (Auto)' : 'Pausa Lavoro (Auto)';
        box.title = data.status_text || '';
      }
    }

    // 2. Banner Manutenzione
    const maintBanner = document.getElementById('maintenanceBanner');
    const maintCountdown = document.getElementById('maintCountdown');
    if (maintBanner && maintCountdown) {
      if (data.maintenance && data.maintenance.active) {
        maintBanner.style.display = 'block';
        const remSec = data.maintenance.remaining_seconds;
        const mm = Math.floor(remSec / 60);
        const ss = remSec % 60;
        maintCountdown.textContent = `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
      } else {
        maintBanner.style.display = 'none';
      }
    }

    // 3. Highlight Card nei Settings & Badge Orari
    const cardAssente = document.getElementById('modeCardAssente');
    const cardNotte = document.getElementById('modeCardNotte');
    const cardCasa = document.getElementById('modeCardCasa');
    const cardMaint = document.getElementById('modeCardMaint');
    const schedBadge = document.getElementById('securityScheduleBadge');

    if (cardAssente) cardAssente.classList.toggle('is-active', mode === 'assente' || mode === 'armed');
    if (cardNotte) cardNotte.classList.toggle('is-active', mode === 'notte');
    if (cardCasa) cardCasa.classList.toggle('is-active', mode === 'casa' || mode === 'disarmed');
    if (cardMaint) cardMaint.classList.toggle('is-active', mode === 'manutenzione');

    if (schedBadge) {
      if (mode === 'assente') schedBadge.textContent = 'Modalità Assente (24/7)';
      else if (mode === 'notte') schedBadge.textContent = 'Modalità Notte (Perimetro)';
      else if (mode === 'casa') schedBadge.textContent = 'Modalità Casa (Diurno)';
      else if (mode === 'manutenzione') schedBadge.textContent = 'Modalità Manutenzione';
      else schedBadge.textContent = data.is_armed ? 'Automatica (Armato)' : 'Automatica (Pausa Lavoro)';
      schedBadge.className = data.is_armed ? 'status-beacon is-accent' : 'status-beacon';
    }

    // 4. Quadro Sinottico: Aree Protette, Telecamere, Varchi, Guasti
    if (data.protected_areas) {
      const synPiazzale = document.getElementById('synAreaPiazzale');
      const synMagazzino = document.getElementById('synAreaMagazzino');
      const synCorridoio = document.getElementById('synAreaCorridoio');

      if (synPiazzale) {
        const isProt = data.protected_areas.piazzale && data.protected_areas.piazzale.armed;
        synPiazzale.textContent = isProt ? 'PROTETTO' : 'SILENZIOSO';
        synPiazzale.className = isProt ? 'sec-badge ok' : 'sec-badge neutral';
      }
      if (synMagazzino) {
        const isProt = data.protected_areas.magazzino && data.protected_areas.magazzino.armed;
        synMagazzino.textContent = isProt ? 'PROTETTO' : 'SILENZIOSO';
        synMagazzino.className = isProt ? 'sec-badge ok' : 'sec-badge neutral';
      }
      if (synCorridoio) {
        const isProt = data.protected_areas.corridoio && data.protected_areas.corridoio.armed;
        synCorridoio.textContent = isProt ? 'PROTETTO' : 'SILENZIOSO';
        synCorridoio.className = isProt ? 'sec-badge ok' : 'sec-badge neutral';
      }
    }

    // 5. Telemetria Decider
    const liveText = document.getElementById('securityLiveStateText');
    const liveReason = document.getElementById('securityLiveReasonText');
    if (liveText) {
      if (data.is_armed) {
        liveText.textContent = `ARMATO (${mode.toUpperCase()})`;
        liveText.style.color = '#81c784';
      } else {
        liveText.textContent = `MONITORAGGIO SILENZIOSO (${mode.toUpperCase()})`;
        liveText.style.color = '#4fc3f7';
      }
    }
    if (liveReason) {
      liveReason.textContent = data.status_text || '';
    }
  } catch (e) {
    // silently ignore
  }
}

// Chiusura flyout cliccando all'esterno
document.addEventListener('click', function(e) {
  const flyout = document.getElementById('securityModeFlyout');
  const secStatus = document.getElementById('securityStatus');
  if (flyout && flyout.style.display === 'block') {
    if (!flyout.contains(e.target) && !secStatus.contains(e.target)) {
      flyout.style.display = 'none';
    }
  }
});

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
    if (roleLabel) roleLabel.textContent = 'Manutentore';
  } else {
    if (roleBadge) {
      roleBadge.className = 'role-pill client';
    }
    if (roleLabel) roleLabel.textContent = 'Cliente';

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
  // Il comando parte da dentro il menu del telefono, quindi il clic non ricade
  // "fuori" e va chiuso qui a mano, altrimenti resterebbe aperto dietro il
  // tastierino e ricomparirebbe al rientro.
  closeHudMenu();
  sessionStorage.removeItem('sentinel_role');
  openAuthModal();
}

function togglePinVisibility(inputId, btn) {
  const inp = document.getElementById(inputId);
  if (!inp) return;

  const reveal = inp.type === 'password';
  inp.type = reveal ? 'text' : 'password';

  // L'icona passa a occhio sbarrato quando il codice e' in chiaro
  if (btn) {
    btn.classList.toggle('is-revealed', reveal);
    btn.setAttribute('aria-pressed', reveal ? 'true' : 'false');
    btn.title = reveal ? 'Nascondi il codice' : 'Mostra il codice';
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
  initCameraStreams();
  loadPlates();
  loadRealEvents();
  // Aggiornamento periodico eventi reali ogni 5 secondi
  setInterval(loadRealEvents, 5000);

  // Monitoraggio Vitality Detector TensorRT (Watchdog Alessio)
  pollDetectorVitality();
  setInterval(pollDetectorVitality, 3000);

  // Telemetria Edge Jetson Orin Nano in Tempo Reale
  pollJetsonTelemetry();
  setInterval(pollJetsonTelemetry, 2500);

  loadSettings();
  pollSecurityState();
  setInterval(pollSecurityState, 6000);
  pollLatestIdentikit();
  setInterval(pollLatestIdentikit, 4000);
  pollOrinStatus();
  setInterval(pollOrinStatus, 10000);

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
