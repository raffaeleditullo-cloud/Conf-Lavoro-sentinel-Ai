/* ══════════════════════════════════════════════════════════════════════════════
 * ORIN — Stanza, finestre e comandi
 *
 * Si carica DOPO app.js e non lo modifica. Si aggancia in tre punti:
 *   - switchView(nome): ridefinita, apre la finestra invece di cambiare pagina.
 *     Anche i pulsanti interni di app.js (es. "Visualizza tutto") la usano.
 *   - applyRole(ruolo): avvolta, chiude la finestra riservata al manutentore
 *     quando si rientra come cliente.
 *   - Funzioni esistenti richiamate dai comandi: openCamModal, closeCamModal,
 *     openLatestIdentikit, triggerFaro, triggerVoice, triggerGate, lockSession.
 *
 * Lo stato arriva leggendo gli elementi che app.js gia' aggiorna (stato di
 * protezione, ultimo identikit): nessuna richiesta in piu' al server.
 * ══════════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const narrowScreen = window.matchMedia('(max-width: 760px)');

  const CAMERA_IDS = { piazzale: 1, magazzino: 2, corridoio: 3 };
  const CAMERA_NAMES = { 1: 'piazzale', 2: 'magazzino', 3: 'corridoio' };

  let ready = false;
  let zTop = 30;
  let pendingConfirm = null;

  // ────────────────────────────────────────────────────────────────────────────
  // 1. RISPOSTA DI ORIN
  // ────────────────────────────────────────────────────────────────────────────
  function say(text, options = {}) {
    const el = $('orinReplyText');
    const actions = $('orinReplyActions');
    if (!el || !actions) return;
    el.textContent = text;
    el.classList.toggle('is-alert', !!options.alert);
    actions.innerHTML = '';
    (options.actions || []).forEach(({ label, command }) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'orin-chip';
      btn.textContent = label;
      btn.addEventListener('click', () => runCommand(command));
      actions.appendChild(btn);
    });
  }

  // ────────────────────────────────────────────────────────────────────────────
  // 2. FINESTRE
  // ────────────────────────────────────────────────────────────────────────────
  const layer = $('orinWindows');
  const windows = Array.from(document.querySelectorAll('.orin-window'));

  function role() {
    try { return currentRole; } catch (e) { return null; }   // let globale di app.js
  }

  function openWindows() {
    return windows.filter((w) => !w.hidden);
  }

  function updateRoom() {
    document.body.classList.toggle('has-windows', openWindows().length > 0);
  }

  function focusWindow(win) {
    win.style.zIndex = String(++zTop);
    windows.forEach((w) => w.classList.toggle('is-focused', w === win));
    eyeState.focus = win;
  }

  function topWindow() {
    return openWindows().sort((a, b) => Number(b.style.zIndex) - Number(a.style.zIndex))[0] || null;
  }

  // Prima apertura: al centro, con un piccolo scalino per ogni finestra gia' aperta
  function placeWindow(win) {
    if (win.dataset.placed) return;
    const area = layer.getBoundingClientRect();
    const w = Math.min(win.offsetWidth, area.width);
    const h = Math.min(win.offsetHeight, area.height);
    const step = (openWindows().length - 1) * 28;
    const left = Math.max(0, Math.min(area.width - w, (area.width - w) / 2 + step));
    const top = Math.max(0, Math.min(area.height - h, (area.height - h) / 2 + step));
    win.style.left = `${left}px`;
    win.style.top = `${top}px`;
    win.dataset.placed = '1';
  }

  function openWindow(key) {
    const win = $(`win-${key}`);
    if (!win) return false;
    if (key === 'diagnostics' && role() !== 'maintainer') {
      say('Lo stato della Jetson è riservato al manutentore. Entra con il suo PIN.');
      return false;
    }
    if (win.hidden) {
      win.hidden = false;
      updateRoom();          // prima si riduce la stanza, poi si centra la finestra
      placeWindow(win);
      // La finestra nasce dalla direzione dell'occhio
      const eyeBox = $('orinEyeStage').getBoundingClientRect();
      const box = win.getBoundingClientRect();
      win.style.setProperty('--orin-origin',
        `${eyeBox.left + eyeBox.width / 2 - box.left}px ${eyeBox.top + eyeBox.height / 2 - box.top}px`);
      if (!reducedMotion.matches) {
        win.classList.add('is-opening');
        requestAnimationFrame(() => requestAnimationFrame(() => win.classList.remove('is-opening')));
      }
    }
    focusWindow(win);
    updateRoom();
    return true;
  }

  function closeWindow(key) {
    const win = $(`win-${key}`);
    if (!win || win.hidden) return false;
    win.hidden = true;
    win.classList.remove('is-focused');
    if (eyeState.focus === win) eyeState.focus = null;
    const next = topWindow();
    if (next) focusWindow(next);
    updateRoom();
    return true;
  }

  function closeEverything() {
    windows.forEach((w) => closeWindow(w.dataset.window));
    if (typeof expandedCamId !== 'undefined' && expandedCamId !== null) closeCamModal();
    const identikit = $('identikitModal');
    if (identikit && identikit.classList.contains('open')) closeIdentikitModal();
  }

  function toggleMaximize(win) {
    const max = !win.classList.contains('is-max');
    win.classList.toggle('is-max', max);
    const btn = win.querySelector('[data-window-action="maximize"]');
    if (btn) {
      btn.setAttribute('aria-pressed', String(max));
      btn.title = max ? 'Riduci' : 'Ingrandisci';
    }
  }

  // Pulsanti della barra, messa a fuoco e trascinamento
  windows.forEach((win) => {
    const key = win.dataset.window;
    const bar = win.querySelector('.orin-window-bar');

    win.addEventListener('pointerdown', () => focusWindow(win));

    win.querySelector('[data-window-action="close"]').addEventListener('click', () => closeWindow(key));
    win.querySelector('[data-window-action="maximize"]').addEventListener('click', () => toggleMaximize(win));
    bar.addEventListener('dblclick', (e) => {
      if (!e.target.closest('button') && !narrowScreen.matches) toggleMaximize(win);
    });

    let drag = null;
    bar.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 || e.target.closest('button') || win.classList.contains('is-max') || narrowScreen.matches) return;
      drag = { x: e.clientX, y: e.clientY, left: win.offsetLeft, top: win.offsetTop };
      bar.setPointerCapture(e.pointerId);
    });
    bar.addEventListener('pointermove', (e) => {
      if (!drag) return;
      const area = layer.getBoundingClientRect();
      // La barra del titolo resta sempre raggiungibile
      const left = Math.max(-win.offsetWidth + 120, Math.min(area.width - 120, drag.left + e.clientX - drag.x));
      const top = Math.max(0, Math.min(area.height - 48, drag.top + e.clientY - drag.y));
      win.style.left = `${left}px`;
      win.style.top = `${top}px`;
    });
    const endDrag = () => { drag = null; };
    bar.addEventListener('pointerup', endDrag);
    bar.addEventListener('pointercancel', endDrag);
  });

  // ────────────────────────────────────────────────────────────────────────────
  // 3. AGGANCI AD APP.JS
  // ────────────────────────────────────────────────────────────────────────────
  // All'avvio app.js apre la parete video: in ORIN la stanza parte vuota, quindi
  // le chiamate arrivate prima che ORIN sia pronto vengono ignorate.
  window.switchView = function (viewName) {
    if (!ready) return;
    openWindow(viewName);
  };

  const originalApplyRole = window.applyRole;
  window.applyRole = function (newRole) {
    originalApplyRole(newRole);
    if (newRole !== 'maintainer') closeWindow('diagnostics');
  };

  // ────────────────────────────────────────────────────────────────────────────
  // 4. COMANDI
  // ────────────────────────────────────────────────────────────────────────────
  const ACTUATOR_LABELS = { faro: 'dockFaroLabel', voce: 'dockSirenLabel', cancello: 'dockGateLabel' };
  const ACTUATOR_BUTTONS = { faro: 'dockFaroBtn', voce: 'dockSirenBtn', cancello: 'dockGateBtn' };
  const ACTUATOR_RUN = { faro: () => triggerFaro(), voce: () => triggerVoice(), cancello: () => triggerGate() };

  function runActuator(key, okText) {
    ACTUATOR_RUN[key]();
    say(okText);
    // app.js segna il pulsante in errore se il server rifiuta: lo si riferisce
    setTimeout(() => {
      const btn = $(ACTUATOR_BUTTONS[key]);
      const label = $(ACTUATOR_LABELS[key]);
      if (btn && btn.classList.contains('is-error')) {
        say(`Non è riuscito: ${label ? label.textContent : 'comando rifiutato'}.`, { alert: true });
      }
    }, 2500);
  }

  function statusSentence() {
    const protection = $('securityStatusLabel');
    const detector = $('vitalityText');
    const p = protection ? protection.textContent.trim() : 'sconosciuto';
    const d = detector ? detector.textContent.trim().toLowerCase() : 'sconosciuto';
    return `Stato: ${p}. Rilevatore: ${d}.`;
  }

  function runCommand(text) {
    const input = $('orinCommandInput');
    if (input) input.value = '';
    pulseThinking();

    if (pendingConfirm) {
      const action = pendingConfirm;
      pendingConfirm = null;
      if (OrinCommands.eConferma(text)) {
        runActuator(action, 'Apro il cancello.');
      } else {
        say('Annullato: il cancello resta chiuso.');
      }
      return;
    }

    const r = OrinCommands.interpreta(text);
    switch (r.tipo) {
      case 'vuoto':
        return;
      case 'apri-finestra':
        if (openWindow(r.finestra)) say(r.risposta);
        return;
      case 'chiudi-finestra':
        say(closeWindow(r.finestra) ? r.risposta : 'Quella finestra non è aperta.');
        return;
      case 'apri-telecamera':
        openCamModal(r.telecamera);
        say(r.risposta);
        return;
      case 'chiudi-telecamera':
        if (typeof expandedCamId !== 'undefined' && expandedCamId !== null) {
          closeCamModal();
          say(r.risposta);
        } else {
          say('Nessuna telecamera è ingrandita.');
        }
        return;
      case 'chiudi-tutto':
        closeEverything();
        say(r.risposta);
        return;
      case 'azione':
        if (r.conferma) {
          pendingConfirm = r.azione;
          say(r.risposta, { actions: [{ label: 'Sì, apri', command: 'si' }, { label: 'Annulla', command: 'no' }] });
        } else {
          runActuator(r.azione, r.risposta);
        }
        return;
      case 'identikit':
        openLatestIdentikit();
        say(r.risposta);
        return;
      case 'blocca':
        closeEverything();
        say(r.risposta);
        lockSession();
        return;
      case 'stato':
        say(statusSentence());
        return;
      case 'sconosciuto':
        say(r.risposta, r.suggerimento
          ? { actions: [{ label: `Sì, ${r.suggerimento}`, command: r.suggerimento }] }
          : {});
        return;
      default:
        say(r.risposta);
    }
  }

  const form = $('orinCommandForm');
  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const value = $('orinCommandInput').value;
      if (value.trim()) runCommand(value);
    });
  }

  document.querySelectorAll('.orin-chip[data-command]').forEach((chip) => {
    chip.addEventListener('click', () => runCommand(chip.dataset.command));
  });

  // Esc: chiude la finestra in primo piano. Si decide in fase di cattura, prima
  // che app.js chiuda la telecamera ingrandita, cosi' un solo Esc chiude una sola cosa.
  window.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const modalOpen = document.querySelector(
      '#camModal.open, #identikitModal.open, #videoModal.open, #plateModal.open, #authModal.open');
    if (modalOpen) return;
    const input = $('orinCommandInput');
    if (document.activeElement === input && input.value) {
      input.value = '';
      return;
    }
    const top = topWindow();
    if (top) closeWindow(top.dataset.window);
  }, true);

  // "/" porta alla barra dei comandi da qualsiasi punto
  window.addEventListener('keydown', (e) => {
    if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if (/INPUT|TEXTAREA|SELECT/.test(tag)) return;
    if ($('authModal') && $('authModal').classList.contains('open')) return;
    e.preventDefault();
    $('orinCommandInput').focus();
  });

  // ────────────────────────────────────────────────────────────────────────────
  // 5. OCCHIO
  // ────────────────────────────────────────────────────────────────────────────
  const eyeState = {
    gazeX: 0, gazeY: 0, mouseX: 0, mouseY: 0,
    think: false, happyUntil: 0, alertUntil: 0,
    focus: null, privacy: false
  };
  let eye = null;

  function pulseThinking() {
    eyeState.think = true;
    clearTimeout(pulseThinking.timer);
    pulseThinking.timer = setTimeout(() => {
      eyeState.think = false;
      eyeState.happyUntil = performance.now() + 700;   // "sorride" dopo aver eseguito
    }, 420);
  }

  function startEye() {
    const stage = $('orinEyeStage');
    if (!stage || !window.OrinEye) return;
    eye = window.OrinEye.create(stage);
    requestAnimationFrame(eyeLoop);
  }

  window.addEventListener('pointermove', (e) => {
    eyeState.mouseX = (e.clientX / window.innerWidth) * 2 - 1;
    eyeState.mouseY = (e.clientY / window.innerHeight) * 2 - 1;
  });

  // La barra ha quasi sempre il focus: l'occhio la guarda solo mentre si scrive
  let lastTyping = 0;
  document.addEventListener('input', (e) => {
    if (e.target && e.target.id === 'orinCommandInput') lastTyping = performance.now();
  });

  let lastFrame = 0;
  function eyeLoop(now) {
    requestAnimationFrame(eyeLoop);
    if (document.hidden) return;
    // Con animazioni ridotte l'occhio vive a pochi fotogrammi al secondo
    if (reducedMotion.matches && now - lastFrame < 250) return;
    lastFrame = now;

    // Dove guarda: la finestra in primo piano, la barra mentre si scrive, il mouse
    let tx = eyeState.mouseX * 0.7;
    let ty = eyeState.mouseY * 0.7;
    if (eyeState.focus && !eyeState.focus.hidden) {
      const stage = $('orinEyeStage').getBoundingClientRect();
      const box = eyeState.focus.getBoundingClientRect();
      tx = ((box.left + box.width / 2) - (stage.left + stage.width / 2)) / (window.innerWidth / 2);
      ty = ((box.top + box.height / 2) - (stage.top + stage.height / 2)) / (window.innerHeight / 2);
    } else if (now - lastTyping < 1500) {
      tx = 0;
      ty = 0.75;
    }
    if (reducedMotion.matches) { tx = 0; ty = 0; }
    eyeState.gazeX = Math.max(-1, Math.min(1, tx));
    eyeState.gazeY = Math.max(-1, Math.min(1, ty));

    // Priorita' degli stati: allarme, pensiero, sorriso, assonnato, riposo
    let mood = 'idle';
    if (now < eyeState.alertUntil) mood = 'alert';
    else if (eyeState.think) mood = 'think';
    else if (now < eyeState.happyUntil) mood = 'happy';
    else if (eyeState.privacy) mood = 'sleepy';
    if (mood === 'think') { eyeState.gazeX = -0.35; eyeState.gazeY = -0.55; }

    eye.frame(now, { gazeX: eyeState.gazeX, gazeY: eyeState.gazeY, mood });
  }

  // ────────────────────────────────────────────────────────────────────────────
  // 6. SEGNALI DA APP.JS: protezione e nuovi passaggi
  // ────────────────────────────────────────────────────────────────────────────
  function watchText(id, onChange) {
    const el = $(id);
    if (!el) return;
    let last = el.textContent.trim();
    new MutationObserver(() => {
      const now = el.textContent.trim();
      if (now !== last) {
        last = now;
        onChange(now);
      }
    }).observe(el, { childList: true, characterData: true, subtree: true });
  }

  function applyProtection(label) {
    eyeState.privacy = /disarmato|pausa/i.test(label);
  }

  // L'identikit viene riscritto ogni 4 secondi anche se non cambia nulla:
  // conta solo un nuovo ID evento. Il primo letto e' la base, non un allarme.
  let lastEventId = null;
  function onIdentikit(text) {
    const match = text.match(/ID:\s*(\S+)/);
    if (!match) return;
    const id = match[1];
    if (lastEventId === null) {
      lastEventId = id;
      return;
    }
    if (id === lastEventId) return;
    lastEventId = id;

    const badge = $('wallIdentikitCamBadge');
    const camera = badge ? badge.textContent.trim().toLowerCase() : '';
    const camId = CAMERA_IDS[camera];
    eyeState.alertUntil = performance.now() + 6000;
    document.body.classList.add('is-alert');
    setTimeout(() => document.body.classList.remove('is-alert'), 6000);
    say(camId ? `Passaggio rilevato al ${CAMERA_NAMES[camId]}.` : 'Passaggio rilevato.', {
      alert: true,
      actions: camId
        ? [{ label: `Mostra ${CAMERA_NAMES[camId]}`, command: CAMERA_NAMES[camId] }, { label: 'Scheda', command: 'identikit' }]
        : [{ label: 'Scheda', command: 'identikit' }]
    });
  }

  // Dopo il PIN la barra dei comandi e' pronta a ricevere
  function watchAuth() {
    const modal = $('authModal');
    if (!modal) return;
    new MutationObserver(() => {
      if (!modal.classList.contains('open')) {
        const input = $('orinCommandInput');
        if (input) input.focus();
      }
    }).observe(modal, { attributes: true, attributeFilter: ['class'] });
  }

  // ────────────────────────────────────────────────────────────────────────────
  // 7. AVVIO (dopo l'inizializzazione di app.js, registrata prima di questa)
  // ────────────────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    ready = true;
    startEye();
    // Si legge lo stato della pianificazione e non l'etichetta in alto: quella e'
    // scritta da due funzioni diverse di app.js e alterna "Protetto" e "Pausa Lavoro"
    const protection = $('securityLiveStateText');
    if (protection) applyProtection(protection.textContent);
    watchText('securityLiveStateText', applyProtection);
    watchText('wallIdentikitTime', onIdentikit);
    watchAuth();
    say('Ciao. Scrivi cosa vuoi vedere, per esempio: piazzale.');
    const auth = $('authModal');
    if (!auth || !auth.classList.contains('open')) $('orinCommandInput').focus();
  });
})();
