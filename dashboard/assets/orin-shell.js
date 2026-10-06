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
  // 2. FINESTRE & WINDOW MANAGER (Stile Windows con Snap Layouts e Resize Handles)
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
    syncDockIndicators();
  }

  function syncDockIndicators() {
    const openKeys = openWindows().filter(w => !w.classList.contains('is-minimized')).map(w => w.dataset.window);
    document.querySelectorAll('.dock-app-btn[data-app]').forEach(btn => {
      const app = btn.dataset.app;
      btn.classList.toggle('is-active', openKeys.includes(app));
    });
  }

  function focusWindow(win) {
    win.style.zIndex = String(++zTop);
    windows.forEach((w) => w.classList.toggle('is-focused', w === win));
    eyeState.focus = win;
    syncDockIndicators();
  }

  function topWindow() {
    return openWindows().filter(w => !w.classList.contains('is-minimized'))
      .sort((a, b) => Number(b.style.zIndex) - Number(a.style.zIndex))[0] || null;
  }

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
      win.classList.remove('is-minimized');
      updateRoom();
      placeWindow(win);
      const eyeBox = $('orinEyeStage').getBoundingClientRect();
      const box = win.getBoundingClientRect();
      win.style.setProperty('--orin-origin',
        `${eyeBox.left + eyeBox.width / 2 - box.left}px ${eyeBox.top + eyeBox.height / 2 - box.top}px`);
      if (!reducedMotion.matches) {
        win.classList.add('is-opening');
        requestAnimationFrame(() => requestAnimationFrame(() => win.classList.remove('is-opening')));
      }
    } else if (win.classList.contains('is-minimized')) {
      win.classList.remove('is-minimized');
    }
    focusWindow(win);
    updateRoom();
    return true;
  }

  function minimizeWindow(key) {
    const win = $(`win-${key}`);
    if (!win || win.hidden) return false;
    win.classList.add('is-minimized');
    win.classList.remove('is-focused');
    if (eyeState.focus === win) eyeState.focus = null;
    const next = topWindow();
    if (next) focusWindow(next);
    syncDockIndicators();
    return true;
  }

  function closeWindow(key) {
    const win = $(`win-${key}`);
    if (!win || win.hidden) return false;
    win.hidden = true;
    win.classList.remove('is-focused');
    win.classList.remove('is-minimized');
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
    syncDockIndicators();
  }

  function toggleMaximize(win) {
    const max = !win.classList.contains('is-max');
    win.classList.toggle('is-max', max);
    win.classList.remove('is-minimized');
    const btn = win.querySelector('[data-window-action="maximize"]');
    if (btn) {
      btn.setAttribute('aria-pressed', String(max));
      btn.title = max ? 'Riduci' : 'Ingrandisci';
    }
  }

  // Snap Window (Suddivisione e aggancio stile Windows Snap Assist)
  function snapWindow(win, layout) {
    win.classList.remove('is-max');
    win.classList.remove('is-minimized');
    const area = layer.getBoundingClientRect();
    const W = area.width;
    const H = area.height;

    switch (layout) {
      case 'half-left':
        win.style.left = '0px';
        win.style.top = '0px';
        win.style.width = `${Math.round(W * 0.5)}px`;
        win.style.height = `${H}px`;
        break;
      case 'half-right':
        win.style.left = `${Math.round(W * 0.5)}px`;
        win.style.top = '0px';
        win.style.width = `${Math.round(W * 0.5)}px`;
        win.style.height = `${H}px`;
        break;
      case 'quad-tl':
        win.style.left = '0px';
        win.style.top = '0px';
        win.style.width = `${Math.round(W * 0.5)}px`;
        win.style.height = `${Math.round(H * 0.5)}px`;
        break;
      case 'quad-tr':
        win.style.left = `${Math.round(W * 0.5)}px`;
        win.style.top = '0px';
        win.style.width = `${Math.round(W * 0.5)}px`;
        win.style.height = `${Math.round(H * 0.5)}px`;
        break;
      case 'quad-bl':
        win.style.left = '0px';
        win.style.top = `${Math.round(H * 0.5)}px`;
        win.style.width = `${Math.round(W * 0.5)}px`;
        win.style.height = `${Math.round(H * 0.5)}px`;
        break;
      case 'quad-br':
        win.style.left = `${Math.round(W * 0.5)}px`;
        win.style.top = `${Math.round(H * 0.5)}px`;
        win.style.width = `${Math.round(W * 0.5)}px`;
        win.style.height = `${Math.round(H * 0.5)}px`;
        break;
      case 'grid-6-1': // Layout 6 finestre (3x2): colonna 1, riga 1
        win.style.left = '0px';
        win.style.top = '0px';
        win.style.width = `${Math.round(W / 3)}px`;
        win.style.height = `${Math.round(H * 0.5)}px`;
        break;
      case 'grid-6-2': // colonna 2, riga 1
        win.style.left = `${Math.round(W / 3)}px`;
        win.style.top = '0px';
        win.style.width = `${Math.round(W / 3)}px`;
        win.style.height = `${Math.round(H * 0.5)}px`;
        break;
      case 'grid-6-3': // colonna 3, riga 1
        win.style.left = `${Math.round((W / 3) * 2)}px`;
        win.style.top = '0px';
        win.style.width = `${Math.round(W - (W / 3) * 2)}px`;
        win.style.height = `${Math.round(H * 0.5)}px`;
        break;
      case 'grid-6-4': // colonna 1, riga 2
        win.style.left = '0px';
        win.style.top = `${Math.round(H * 0.5)}px`;
        win.style.width = `${Math.round(W / 3)}px`;
        win.style.height = `${Math.round(H * 0.5)}px`;
        break;
      case 'grid-6-5': // colonna 2, riga 2
        win.style.left = `${Math.round(W / 3)}px`;
        win.style.top = `${Math.round(H * 0.5)}px`;
        win.style.width = `${Math.round(W / 3)}px`;
        win.style.height = `${Math.round(H * 0.5)}px`;
        break;
      case 'grid-6-6': // colonna 3, riga 2
        win.style.left = `${Math.round((W / 3) * 2)}px`;
        win.style.top = `${Math.round(H * 0.5)}px`;
        win.style.width = `${Math.round(W - (W / 3) * 2)}px`;
        win.style.height = `${Math.round(H * 0.5)}px`;
        break;
      case 'full':
        if (!win.classList.contains('is-max')) toggleMaximize(win);
        return;
    }
    win.dataset.placed = '1';
    focusWindow(win);
  }

  function getLayoutRect(layout) {
    const area = layer.getBoundingClientRect();
    const W = area.width;
    const H = area.height;
    switch (layout) {
      case 'half-left': return { left: 0, top: 0, width: Math.round(W * 0.5), height: H };
      case 'half-right': return { left: Math.round(W * 0.5), top: 0, width: Math.round(W * 0.5), height: H };
      case 'quad-tl': return { left: 0, top: 0, width: Math.round(W * 0.5), height: Math.round(H * 0.5) };
      case 'quad-tr': return { left: Math.round(W * 0.5), top: 0, width: Math.round(W * 0.5), height: Math.round(H * 0.5) };
      case 'quad-bl': return { left: 0, top: Math.round(H * 0.5), width: Math.round(W * 0.5), height: Math.round(H * 0.5) };
      case 'quad-br': return { left: Math.round(W * 0.5), top: Math.round(H * 0.5), width: Math.round(W * 0.5), height: Math.round(H * 0.5) };
      case 'grid-6-1': return { left: 0, top: 0, width: Math.round(W / 3), height: Math.round(H * 0.5) };
      case 'grid-6-2': return { left: Math.round(W / 3), top: 0, width: Math.round(W / 3), height: Math.round(H * 0.5) };
      case 'grid-6-3': return { left: Math.round((W / 3) * 2), top: 0, width: Math.round(W - (W / 3) * 2), height: Math.round(H * 0.5) };
      case 'grid-6-4': return { left: 0, top: Math.round(H * 0.5), width: Math.round(W / 3), height: Math.round(H * 0.5) };
      case 'grid-6-5': return { left: Math.round(W / 3), top: Math.round(H * 0.5), width: Math.round(W / 3), height: Math.round(H * 0.5) };
      case 'grid-6-6': return { left: Math.round((W / 3) * 2), top: Math.round(H * 0.5), width: Math.round(W - (W / 3) * 2), height: Math.round(H * 0.5) };
      case 'full': return { left: 0, top: 0, width: W, height: H };
      default: return null;
    }
  }

  const snapBar = $('orinSnapBar');
  const snapGhost = $('orinSnapGhost');
  let activeSnapTarget = null;

  function showGhost(layout) {
    if (!snapGhost) return;
    const rect = getLayoutRect(layout);
    if (!rect) {
      hideGhost();
      return;
    }
    snapGhost.style.left = `${rect.left}px`;
    snapGhost.style.top = `${rect.top}px`;
    snapGhost.style.width = `${rect.width}px`;
    snapGhost.style.height = `${rect.height}px`;
    snapGhost.classList.add('is-active');
  }

  function hideGhost() {
    if (!snapGhost) return;
    snapGhost.classList.remove('is-active');
  }

  function openSnapBar() {
    if (snapBar && !snapBar.classList.contains('is-visible')) {
      snapBar.classList.add('is-visible');
    }
  }

  function closeSnapBar() {
    if (snapBar) {
      snapBar.classList.remove('is-visible');
      snapBar.querySelectorAll('.snap-slot').forEach(s => s.classList.remove('is-hovered'));
    }
    hideGhost();
    activeSnapTarget = null;
  }

  if (snapBar) {
    snapBar.querySelectorAll('.snap-slot').forEach(slot => {
      slot.addEventListener('click', (e) => {
        e.stopPropagation();
        const topWin = topWindow();
        if (topWin && slot.dataset.snapTarget) {
          snapWindow(topWin, slot.dataset.snapTarget);
          closeSnapBar();
        }
      });
    });
  }

  // Inizializzazione strumenti di ogni finestra: Snap, Riduci, Ingrandisci, Chiudi, Drag e Resize
  windows.forEach((win) => {
    const key = win.dataset.window;
    const bar = win.querySelector('.orin-window-bar');
    const tools = win.querySelector('.orin-window-tools');

    win.addEventListener('pointerdown', () => focusWindow(win));

    // Aggiungi pulsante Riduci a icona se non presente
    if (tools && !tools.querySelector('[data-window-action="minimize"]')) {
      const minBtn = document.createElement('button');
      minBtn.type = 'button';
      minBtn.className = 'orin-window-btn';
      minBtn.dataset.windowAction = 'minimize';
      minBtn.title = 'Riduci a icona';
      minBtn.setAttribute('aria-label', 'Riduci a icona');
      minBtn.innerHTML = '<svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"/></svg>';
      tools.insertBefore(minBtn, tools.firstChild);
    }

    // Aggiungi menu Snap Layout in stile Windows 11
    if (tools && !tools.querySelector('.orin-snap-wrap')) {
      const snapWrap = document.createElement('div');
      snapWrap.className = 'orin-snap-wrap';
      snapWrap.innerHTML = `
        <button type="button" class="orin-window-btn" data-window-action="snap" title="Layout e suddivisione schermo" aria-label="Layout suddivisione">
          <svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="12" y1="3" x2="12" y2="21"/></svg>
        </button>
        <div class="orin-snap-menu" role="menu">
          <div class="orin-snap-title">Layout Schermo (Snap)</div>
          <div class="orin-snap-grid">
            <button type="button" class="snap-option" data-snap="half-left" title="Metà Sinistra">
              <div class="snap-box half-l"><span class="snap-fill active"></span><span class="snap-fill"></span></div>
              <span>Metà SX</span>
            </button>
            <button type="button" class="snap-option" data-snap="half-right" title="Metà Destra">
              <div class="snap-box half-r"><span class="snap-fill"></span><span class="snap-fill active"></span></div>
              <span>Metà DX</span>
            </button>
            <button type="button" class="snap-option" data-snap="quad-tl" title="Griglia a 4 (Quadrante)">
              <div class="snap-box grid-4"><span class="snap-fill active"></span><span class="snap-fill"></span><span class="snap-fill"></span><span class="snap-fill"></span></div>
              <span>4 Riquadri</span>
            </button>
            <button type="button" class="snap-option" data-snap="grid-6-1" title="Griglia a 6 (Fino a 6 finestre)">
              <div class="snap-box grid-6"><span class="snap-fill active"></span><span class="snap-fill"></span><span class="snap-fill"></span><span class="snap-fill"></span><span class="snap-fill"></span><span class="snap-fill"></span></div>
              <span>6 Riquadri</span>
            </button>
            <button type="button" class="snap-option" data-snap="full" title="Tutto Schermo" style="grid-column: 1 / -1;">
              <div class="snap-box full" style="width:100%;"><span class="snap-fill active"></span></div>
              <span>A Tutto Schermo</span>
            </button>
          </div>
        </div>
      `;
      const maxBtn = tools.querySelector('[data-window-action="maximize"]');
      if (maxBtn) tools.insertBefore(snapWrap, maxBtn);
      else tools.appendChild(snapWrap);

      const snapBtn = snapWrap.querySelector('[data-window-action="snap"]');
      if (snapBtn) {
        snapBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          snapWrap.classList.toggle('is-open');
        });
      }
      document.addEventListener('pointerdown', (e) => {
        if (!snapWrap.contains(e.target)) {
          snapWrap.classList.remove('is-open');
        }
      });

      // Listener per le opzioni di snap
      snapWrap.querySelectorAll('.snap-option').forEach(opt => {
        opt.addEventListener('click', (e) => {
          e.stopPropagation();
          snapWrap.classList.remove('is-open');
          const layout = opt.dataset.snap;
          snapWindow(win, layout);
        });
      });
    }

    // Aggiungi 8 maniglie di ridimensionamento (Resize Handles) per bordi e angoli
    const handles = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'];
    handles.forEach(dir => {
      if (!win.querySelector(`.handle-${dir}`)) {
        const h = document.createElement('div');
        h.className = `win-resize-handle handle-${dir}`;
        h.dataset.handle = dir;
        win.appendChild(h);

        // Resize interattivo
        h.addEventListener('pointerdown', (e) => {
          if (e.button !== 0 || win.classList.contains('is-max') || narrowScreen.matches) return;
          e.preventDefault();
          e.stopPropagation();
          focusWindow(win);

          const startX = e.clientX;
          const startY = e.clientY;
          const startW = win.offsetWidth;
          const startH = win.offsetHeight;
          const startL = win.offsetLeft;
          const startT = win.offsetTop;

          h.setPointerCapture(e.pointerId);

          const onPointerMove = (ev) => {
            const dx = ev.clientX - startX;
            const dy = ev.clientY - startY;

            let newW = startW;
            let newH = startH;
            let newL = startL;
            let newT = startT;

            if (dir.includes('e')) newW = Math.max(360, startW + dx);
            if (dir.includes('s')) newH = Math.max(240, startH + dy);
            if (dir.includes('w')) {
              newW = Math.max(360, startW - dx);
              newL = startL + (startW - newW);
            }
            if (dir.includes('n')) {
              newH = Math.max(240, startH - dy);
              newT = startT + (startH - newH);
            }

            win.style.width = `${newW}px`;
            win.style.height = `${newH}px`;
            win.style.left = `${newL}px`;
            win.style.top = `${newT}px`;
          };

          const onPointerUp = (ev) => {
            h.releasePointerCapture(ev.pointerId);
            window.removeEventListener('pointermove', onPointerMove);
            window.removeEventListener('pointerup', onPointerUp);
          };

          window.addEventListener('pointermove', onPointerMove);
          window.addEventListener('pointerup', onPointerUp);
        });
      }
    });

    const closeBtn = win.querySelector('[data-window-action="close"]');
    if (closeBtn) closeBtn.addEventListener('click', () => closeWindow(key));

    const maxBtn = win.querySelector('[data-window-action="maximize"]');
    if (maxBtn) maxBtn.addEventListener('click', () => toggleMaximize(win));

    const minBtn = win.querySelector('[data-window-action="minimize"]');
    if (minBtn) minBtn.addEventListener('click', () => minimizeWindow(key));

    if (bar) {
      bar.addEventListener('dblclick', (e) => {
        if (!e.target.closest('button') && !narrowScreen.matches) toggleMaximize(win);
      });

      // Trascinamento finestra (Drag con Snap Assist stile Windows 11)
      let drag = null;
      bar.addEventListener('pointerdown', (e) => {
        if (e.button !== 0 || e.target.closest('button') || e.target.closest('.orin-snap-wrap') || narrowScreen.matches) return;
        if (win.classList.contains('is-max')) {
          toggleMaximize(win);
          win.style.left = `${Math.max(0, e.clientX - win.offsetWidth / 2)}px`;
          win.style.top = '12px';
        }
        drag = { x: e.clientX, y: e.clientY, left: win.offsetLeft, top: win.offsetTop };
        bar.setPointerCapture(e.pointerId);
      });

      bar.addEventListener('pointermove', (e) => {
        if (!drag) return;
        const area = layer.getBoundingClientRect();
        const left = Math.max(-win.offsetWidth + 120, Math.min(area.width - 120, drag.left + e.clientX - drag.x));
        const top = Math.max(0, Math.min(area.height - 48, drag.top + e.clientY - drag.y));
        win.style.left = `${left}px`;
        win.style.top = `${top}px`;

        // Rilevamento trascinamento verso l'alto (Snap Assist stile Windows 11)
        if (e.clientY < 75 || top < 25) {
          openSnapBar();
        } else if (e.clientY > 160 && activeSnapTarget === null) {
          closeSnapBar();
        }

        // Rileva se il cursore sta sopra uno slot della barra snap in alto
        let hitTarget = null;
        if (snapBar && snapBar.classList.contains('is-visible')) {
          const elUnder = document.elementFromPoint(e.clientX, e.clientY);
          const slot = elUnder ? elUnder.closest('.snap-slot') : null;
          snapBar.querySelectorAll('.snap-slot').forEach(s => s.classList.toggle('is-hovered', s === slot));
          if (slot && slot.dataset.snapTarget) {
            hitTarget = slot.dataset.snapTarget;
          }
        }

        // Edge Snapping (se non siamo sopra uno slot della barra)
        if (!hitTarget) {
          if (e.clientX < 24) {
            hitTarget = 'half-left';
          } else if (e.clientX > window.innerWidth - 24) {
            hitTarget = 'half-right';
          } else if (e.clientY < 8) {
            hitTarget = 'full';
          }
        }

        if (hitTarget) {
          activeSnapTarget = hitTarget;
          showGhost(hitTarget);
        } else {
          const elUnder = document.elementFromPoint(e.clientX, e.clientY);
          if (!snapBar || !snapBar.contains(elUnder)) {
            activeSnapTarget = null;
            hideGhost();
          }
        }
      });

      const endDrag = () => {
        if (!drag) return;
        drag = null;
        if (activeSnapTarget) {
          snapWindow(win, activeSnapTarget);
        }
        closeSnapBar();
      };
      bar.addEventListener('pointerup', endDrag);
      bar.addEventListener('pointercancel', endDrag);
    }
  });

  // Collegamento pulsanti della barra Dock laterale
  document.querySelectorAll('.dock-app-btn[data-app]').forEach(btn => {
    btn.addEventListener('click', () => {
      const app = btn.dataset.app;
      if (app === 'lock') {
        lockSession();
        return;
      }
      const win = $(`win-${app}`);
      if (!win) return;
      if (win.hidden) {
        openWindow(app);
      } else if (win.classList.contains('is-minimized')) {
        win.classList.remove('is-minimized');
        focusWindow(win);
      } else if (win.classList.contains('is-focused')) {
        minimizeWindow(app);
      } else {
        focusWindow(win);
      }
      syncDockIndicators();
    });
  });

  // ────────────────────────────────────────────────────────────────────────────
  // 2B. SYSTEM DRAWER (Cassetto Laterale da Destra per Diagnostica Jetson)
  // ────────────────────────────────────────────────────────────────────────────
  function setSystemDrawerOpen(open) {
    const drawer = $('systemDrawer');
    const backdrop = $('systemDrawerBackdrop');
    if (!drawer || !backdrop) return;
    drawer.classList.toggle('is-open', open);
    backdrop.classList.toggle('is-open', open);
    if (open) {
      pollDrawerTelemetry();
    }
  }

  window.toggleSystemDrawer = function () {
    const drawer = $('systemDrawer');
    setSystemDrawerOpen(!(drawer && drawer.classList.contains('is-open')));
  };
  window.openSystemDrawer = function () { setSystemDrawerOpen(true); };
  window.closeSystemDrawer = function () { setSystemDrawerOpen(false); };

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const drawer = $('systemDrawer');
      if (drawer && drawer.classList.contains('is-open')) closeSystemDrawer();
    }
  });

  async function pollDrawerTelemetry() {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) return;
      const data = await res.json();

      // Temperatura SoC Jetson
      const tempNum = $('drawerTempNum');
      const tempPill = $('drawerTempPill');
      const tempBar = $('drawerTempBar');
      const topbarTempText = $('topbarTempText');
      const topbarChip = $('topbarTempChip');

      if (data.temperature !== undefined) {
        const t = data.temperature;
        const tStr = `${t.toFixed(1)} °C`;
        if (tempNum) tempNum.textContent = tStr;
        if (topbarTempText) topbarTempText.textContent = tStr;

        const isOpt = t < 65;
        const isWarm = t >= 65 && t < 78;
        const isHot = t >= 78;

        const label = isOpt ? 'Ottimale' : (isWarm ? 'Nominale' : 'Attenzione');
        if (tempPill) {
          tempPill.textContent = label;
          tempPill.className = `temp-status-pill ${isOpt ? 'is-optimal' : (isWarm ? 'is-warm' : 'is-hot')}`;
        }
        if (topbarChip) {
          topbarChip.className = `topbar-temp-chip ${isOpt ? 'is-optimal' : (isWarm ? 'is-warm' : 'is-hot')}`;
        }
        if (tempBar) {
          const pct = Math.min(100, Math.max(10, (t / 85) * 100));
          tempBar.style.width = `${pct}%`;
        }
      }

      // TensorRT Detector FPS
      const trtFps = $('drawerTrtFps');
      if (trtFps && data.detection_fps !== undefined) {
        trtFps.textContent = `${data.detection_fps.toFixed(1)} FPS`;
      }

      // RAM
      const ramVal = $('drawerRamVal');
      const ramSub = $('drawerRamSub');
      if (ramVal && data.ram_used_mb !== undefined && data.ram_total_mb !== undefined) {
        ramVal.textContent = `${(data.ram_used_mb / 1024).toFixed(2)} GB / ${(data.ram_total_mb / 1024).toFixed(1)} GB`;
        if (ramSub && data.ram_free_mb !== undefined) {
          ramSub.textContent = `~${(data.ram_free_mb / 1024).toFixed(1)} GB liberi`;
        }
      }

      // Swap
      const swapVal = $('drawerSwapVal');
      if (swapVal && data.swap_used_mb !== undefined && data.swap_total_mb !== undefined) {
        swapVal.textContent = `${data.swap_used_mb} MB / ${(data.swap_total_mb / 1024).toFixed(1)} GB`;
      }

      // Potenza & Uptime
      const pVal = $('drawerPowerVal');
      if (pVal && data.power_watts !== undefined) pVal.textContent = `${data.power_watts.toFixed(1)} W`;
      const upVal = $('drawerUptimeVal');
      if (upVal && data.uptime) upVal.textContent = data.uptime;

      // Aggiornamento Visibilità Ruolo (Admin vs Cliente)
      const isClient = role() === 'client';
      const restrictedBanner = $('drawerAdminRestricted');
      const telemCard = $('drawerTelemetryCard');
      const rolePill = $('drawerRolePill');
      if (rolePill) {
        rolePill.textContent = isClient ? 'Cliente' : 'Manutentore';
        rolePill.className = `role-pill ${isClient ? 'client' : 'maintainer'}`;
      }
      if (restrictedBanner) restrictedBanner.style.display = isClient ? 'flex' : 'none';
      if (telemCard) telemCard.style.display = isClient ? 'none' : 'flex';
      if (topbarChip) topbarChip.style.display = isClient ? 'none' : 'inline-flex';

    } catch (e) {
      // Ignora errori di polling
    }
  }

  // Polling periodico per temperatura ed stato
  setInterval(pollDrawerTelemetry, 3500);

  // ────────────────────────────────────────────────────────────────────────────
  // 2C. INTERFONO LIVE / REGISTRATORE PUSH-TO-TALK (win-ptt)
  // ────────────────────────────────────────────────────────────────────────────
  const pttBtn = $('btnPttMic');
  const pttTimer = $('pttTimerDisplay');
  const pttBeacon = $('pttStatusBeacon');
  const pttLabel = $('pttMicLabel');
  let pttInterval = null;
  let pttSeconds = 0;
  let isPttRecording = false;

  const chatMicBtn = $('btnChatMic');
  const chatInput = $('orinCommandInput');
  let originalPlaceholder = chatInput ? chatInput.placeholder : 'Scrivi cosa vuoi vedere o cosa dire al varco...';

  function startPttRecording() {
    if (isPttRecording) return;
    isPttRecording = true;
    pttSeconds = 0;
    if (pttBtn) pttBtn.classList.add('is-active');
    if (chatMicBtn) chatMicBtn.classList.add('is-recording');

    if (chatInput) {
      originalPlaceholder = chatInput.placeholder;
      chatInput.placeholder = '🔴 In trasmissione audio... Parla pure (rilascia per inviare)';
    }

    if (pttBeacon) {
      pttBeacon.textContent = 'IN TRASMISSIONE DIRETTA';
      pttBeacon.className = 'status-beacon is-alert';
    }
    if (pttLabel) pttLabel.textContent = 'PARLA ORA...';
    if (pttTimer) {
      pttTimer.style.display = 'block';
      pttTimer.textContent = '00:00';
    }

    pttInterval = setInterval(() => {
      pttSeconds++;
      const m = String(Math.floor(pttSeconds / 60)).padStart(2, '0');
      const s = String(pttSeconds % 60).padStart(2, '0');
      if (pttTimer) pttTimer.textContent = `${m}:${s}`;
      if (chatInput) {
        chatInput.placeholder = `🔴 In trasmissione audio (${m}:${s})... Parla pure`;
      }
    }, 1000);
  }

  function stopPttRecording() {
    if (!isPttRecording) return;
    isPttRecording = false;
    if (pttInterval) {
      clearInterval(pttInterval);
      pttInterval = null;
    }
    if (pttBtn) pttBtn.classList.remove('is-active');
    if (chatMicBtn) chatMicBtn.classList.remove('is-recording');

    if (chatInput) {
      chatInput.placeholder = originalPlaceholder;
    }

    if (pttBeacon) {
      pttBeacon.textContent = 'Pronto alla trasmissione';
      pttBeacon.className = 'status-beacon is-accent';
    }
    if (pttLabel) pttLabel.textContent = 'PREMI E PARLA';
    if (pttTimer) pttTimer.style.display = 'none';

    const target = $('selPttTarget') ? $('selPttTarget').value : 'fanvil';
    const targetLabel = target === 'fanvil' ? 'tutti i varchi' : target;
    say(`Messaggio vocale (${pttSeconds}s) trasmesso a ${targetLabel} sull'altoparlante Fanvil.`);
  }

  if (pttBtn) {
    pttBtn.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      startPttRecording();
    });
    pttBtn.addEventListener('pointerup', stopPttRecording);
    pttBtn.addEventListener('pointercancel', stopPttRecording);
    pttBtn.addEventListener('pointerleave', stopPttRecording);
  }

  // Supporto microfono integrato nella barra di ricerca
  if (chatMicBtn) {
    chatMicBtn.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      startPttRecording();
    });
    chatMicBtn.addEventListener('pointerup', stopPttRecording);
    chatMicBtn.addEventListener('pointercancel', stopPttRecording);
    chatMicBtn.addEventListener('pointerleave', stopPttRecording);
  }

  // Supporto Spacebar per Push-to-Talk quando win-ptt è aperto o si tiene premuto
  window.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !e.repeat) {
      const pttWin = $('win-ptt');
      if (pttWin && !pttWin.hidden && pttWin.classList.contains('is-focused') && !$('orinCommandInput')?.matches(':focus')) {
        e.preventDefault();
        startPttRecording();
      }
    }
  });
  window.addEventListener('keyup', (e) => {
    if (e.code === 'Space' && isPttRecording) {
      e.preventDefault();
      stopPttRecording();
    }
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
  window.openWindow = openWindow;
  window.closeWindow = closeWindow;
  window.minimizeWindow = minimizeWindow;
  window.closeEverything = closeEverything;

  const originalApplyRole = window.applyRole;
  window.applyRole = function (newRole) {
    originalApplyRole(newRole);
    if (newRole !== 'maintainer') closeWindow('diagnostics');
    pollDrawerTelemetry();
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
