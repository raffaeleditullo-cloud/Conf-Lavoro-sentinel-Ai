/* ══════════════════════════════════════════════════════════════════════════════
 * ORIN — Registro Biometrico (viso + voce) e feed del dialogo al varco
 *
 * Modulo autonomo: usa solo le API /api/biometrics/* e /api/orin/dialogue e
 * l'hook window.onPinUnlocked() invocato da app.js dopo lo sblocco del tastierino.
 * Non tocca il polling delle telecamere ne' la logica del Video Wall.
 * ══════════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const REC_SECONDS = 4;
  const FACE_MAX_PX = 512;
  const WAV_RATE = 16000;

  // Il PIN manutentore resta solo in memoria (mai in storage): serve a firmare enroll/revoca.
  let adminPin = null;
  let profiles = [];
  let firstRun = false;

  const state = { faceB64: null, voiceB64: null, camStream: null, micStream: null, audioCtx: null, raf: 0, busy: false };

  // ── API ──────────────────────────────────────────────────────────────────────
  async function fetchProfiles() {
    const res = await fetch('/api/biometrics/profiles', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    profiles = (await res.json()).profiles || [];
    return profiles;
  }

  function authHeaders() {
    return { 'Content-Type': 'application/json', 'X-Orin-Pin': adminPin || ($('bioPin') && $('bioPin').value.trim()) || '' };
  }

  // ── Registro (finestra) ──────────────────────────────────────────────────────
  function renderList() {
    const list = $('bioList');
    $('bioCountPill').textContent = profiles.length === 1 ? '1 profilo' : `${profiles.length} profili`;
    list.replaceChildren();
    if (!profiles.length) {
      const p = document.createElement('p');
      p.className = 'bio-empty';
      p.textContent = 'Nessuna identità registrata. ORIN non riconoscerà nessuno finché non aggiungi la prima.';
      list.appendChild(p);
      return;
    }
    profiles.forEach((pr) => list.appendChild(profileCard(pr)));
  }

  function profileCard(pr) {
    const card = document.createElement('article');
    card.className = 'bio-profile';

    const img = document.createElement('img');
    img.className = 'bio-avatar';
    img.alt = pr.name;
    img.src = pr.has_face ? `/api/biometrics/faces/${pr.id}` : 'assets/img/conflavoro-ai-icon-oro.svg';
    card.appendChild(img);

    const info = document.createElement('div');
    info.className = 'bio-profile-info';
    const name = document.createElement('strong');
    name.textContent = pr.name;
    const roleBadge = document.createElement('span');
    roleBadge.className = 'bio-badge';
    roleBadge.textContent = pr.role || 'Ruolo non indicato';
    info.append(name, roleBadge);
    if (pr.open_gate) {
      const gate = document.createElement('span');
      gate.className = 'bio-badge is-gate';
      gate.textContent = 'Apre il cancello';
      info.appendChild(gate);
    }
    card.appendChild(info);

    const actions = document.createElement('div');
    actions.className = 'bio-profile-actions';
    if (pr.has_voice) {
      const play = document.createElement('button');
      play.type = 'button';
      play.className = 'bio-btn';
      play.textContent = '▶ Ascolta voce';
      play.addEventListener('click', () => {
        const a = new Audio(`/api/biometrics/voices/${pr.id}`);
        a.play().catch(() => {});
      });
      actions.appendChild(play);
    }
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'bio-btn is-danger';
    del.textContent = 'Revoca';
    del.addEventListener('click', () => revoke(pr));
    actions.appendChild(del);
    card.appendChild(actions);
    return card;
  }

  async function revoke(pr) {
    if (!window.confirm(`Revocare l'identità di ${pr.name}? Viso e voce verranno eliminati.`)) return;
    let pin = adminPin;
    if (!pin) pin = (window.prompt('PIN Manutentore per confermare la revoca:') || '').trim();
    if (!pin) return;
    try {
      const res = await fetch(`/api/biometrics/profiles/${pr.id}`, { method: 'DELETE', headers: { 'X-Orin-Pin': pin } });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || 'HTTP ' + res.status);
      await refresh();
    } catch (e) {
      window.alert('Revoca non riuscita: ' + e.message);
    }
  }

  async function refresh() {
    try { await fetchProfiles(); renderList(); } catch (e) { /* server offline: lascia l'elenco com'è */ }
  }

  // ── Modale enrollment ────────────────────────────────────────────────────────
  function stopCamera() {
    if (state.camStream) state.camStream.getTracks().forEach((t) => t.stop());
    state.camStream = null;
    $('bioVideo').srcObject = null;
  }

  function stopMic() {
    cancelAnimationFrame(state.raf);
    if (state.micStream) state.micStream.getTracks().forEach((t) => t.stop());
    state.micStream = null;
    if (state.audioCtx) { state.audioCtx.close().catch(() => {}); state.audioCtx = null; }
  }

  function mediaSupported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  }

  function insecureMessage() {
    return window.isSecureContext === false
      ? 'Fotocamera e microfono richiedono HTTPS oppure l\'indirizzo localhost: apri la dashboard dal browser del Jetson (http://localhost:8080) o tramite HTTPS.'
      : 'Fotocamera o microfono non disponibili su questo browser.';
  }

  function resetModal(prefill) {
    stopCamera(); stopMic();
    state.faceB64 = null; state.voiceB64 = null;
    $('bioName').value = prefill ? 'Alessio Russo' : '';
    $('bioRole').value = prefill ? 'Responsabile Tecnico & Ingegnere di Sistema' : '';
    $('bioGreeting').value = prefill ? 'Benvenuto Alessio. Sistema operativo e varco sbloccato.' : '';
    $('bioOpenGate').checked = !!prefill;
    $('bioPin').value = '';
    $('bioPinRow').hidden = !!adminPin;
    $('bioError').textContent = '';
    $('bioVideo').hidden = false;
    $('bioFacePreview').hidden = true;
    $('bioFacePreview').removeAttribute('src');
    $('bioReticle').hidden = true;
    $('bioCountdown').hidden = true;
    $('bioFaceStart').hidden = false;
    $('bioFaceCapture').hidden = true;
    $('bioFaceRetake').hidden = true;
    $('bioFaceMsg').textContent = 'Premi «Avvia fotocamera» e allinea occhi e volto al mirino.';
    $('bioVoiceRec').hidden = false;
    $('bioVoiceRetake').hidden = true;
    $('bioVoicePlayer').hidden = true;
    $('bioVoicePlayer').removeAttribute('src');
    $('bioVoiceMsg').textContent = '';
    $('bioRecBar').style.width = '0';
    const g = $('bioWave').getContext('2d');
    g.clearRect(0, 0, $('bioWave').width, $('bioWave').height);
    updatePhrase();
  }

  function updatePhrase() {
    const name = $('bioName').value.trim() || 'Nome Cognome';
    $('bioPhrase').textContent = `Premi Registra e pronuncia con voce naturale: «Sono ${name}, autorizzazione per ORIN»`;
  }

  function openModal(isFirstRun) {
    firstRun = !!isFirstRun;
    resetModal(isFirstRun);
    $('bioModalEyebrow').textContent = isFirstRun ? 'Benvenuto su ORIN' : 'ORIN // Identità Biometrica';
    $('bioModalTitle').textContent = isFirstRun
      ? 'Configurazione Iniziale Identità Biometrica'
      : 'Nuova identità autorizzata';
    $('bioEnrollModal').hidden = false;
    document.body.classList.add('bio-modal-open');
    $('bioName').focus();
  }

  function closeModal() {
    stopCamera(); stopMic();
    $('bioEnrollModal').hidden = true;
    document.body.classList.remove('bio-modal-open');
  }

  // ── Volto ────────────────────────────────────────────────────────────────────
  async function startCamera() {
    if (!mediaSupported()) { $('bioFaceMsg').textContent = insecureMessage(); return; }
    try {
      state.camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
    } catch (e) {
      $('bioFaceMsg').textContent = 'Accesso alla fotocamera negato o non disponibile: ' + (e.name || e.message);
      return;
    }
    const v = $('bioVideo');
    v.srcObject = state.camStream;
    await v.play().catch(() => {});
    $('bioFacePreview').hidden = true;
    v.hidden = false;
    $('bioReticle').hidden = false;
    $('bioFaceStart').hidden = true;
    $('bioFaceRetake').hidden = true;
    $('bioFaceCapture').hidden = false;
    $('bioFaceMsg').textContent = 'Allinea occhi e volto al mirino ovale, luce frontale, poi premi «Cattura Volto».';
  }

  function beep(freq, ms) {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      const ctx = new Ctx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = freq;
      gain.gain.value = 0.08;
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start();
      setTimeout(() => { osc.stop(); ctx.close().catch(() => {}); }, ms);
    } catch (e) { /* audio di cortesia: non essenziale */ }
  }

  async function captureFace() {
    if (state.busy) return;
    state.busy = true;
    $('bioFaceCapture').disabled = true;
    const cd = $('bioCountdown');
    cd.hidden = false;
    for (let n = 3; n >= 1; n--) {
      cd.textContent = String(n);
      beep(660, 90);
      await new Promise((r) => setTimeout(r, 900));
    }
    cd.hidden = true;
    beep(990, 160);

    const v = $('bioVideo');
    const w = v.videoWidth, h = v.videoHeight;
    if (!w || !h) { $('bioFaceMsg').textContent = 'Fotocamera non pronta, riprova.'; state.busy = false; $('bioFaceCapture').disabled = false; return; }
    const scale = Math.min(1, FACE_MAX_PX / Math.max(w, h));
    const c = document.createElement('canvas');
    c.width = Math.round(w * scale);
    c.height = Math.round(h * scale);
    c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
    const dataUrl = c.toDataURL('image/jpeg', 0.85);
    state.faceB64 = dataUrl.split(',')[1];

    stopCamera();
    $('bioFacePreview').src = dataUrl;
    $('bioFacePreview').hidden = false;
    $('bioVideo').hidden = true;
    $('bioReticle').hidden = true;
    $('bioFaceCapture').hidden = true;
    $('bioFaceCapture').disabled = false;
    $('bioFaceRetake').hidden = false;
    $('bioFaceMsg').textContent = 'Volto acquisito. Se è sfocato o decentrato, rifai lo scatto.';
    state.busy = false;
  }

  function retakeFace() {
    state.faceB64 = null;
    $('bioFacePreview').hidden = true;
    $('bioVideo').hidden = false;
    startCamera();
  }

  // ── Voce ─────────────────────────────────────────────────────────────────────
  function drawWave(analyser) {
    const canvas = $('bioWave');
    const g = canvas.getContext('2d');
    const data = new Uint8Array(analyser.fftSize);
    const gold = getComputedStyle(document.documentElement).getPropertyValue('--bio-gold').trim() || '#d4af37';
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      g.clearRect(0, 0, canvas.width, canvas.height);
      g.lineWidth = 2;
      g.strokeStyle = gold;
      g.beginPath();
      const step = canvas.width / data.length;
      for (let i = 0; i < data.length; i++) {
        const y = (data[i] / 255) * canvas.height;
        i ? g.lineTo(i * step, y) : g.moveTo(0, y);
      }
      g.stroke();
      state.raf = requestAnimationFrame(tick);
    };
    tick();
  }

  // Decodifica il blob del MediaRecorder e lo riscrive come WAV PCM 16 bit mono 16 kHz
  async function blobToWav(blob) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    let decoded;
    try { decoded = await ctx.decodeAudioData(await blob.arrayBuffer()); } finally { ctx.close().catch(() => {}); }
    const frames = Math.ceil(decoded.duration * WAV_RATE);
    const off = new OfflineAudioContext(1, frames, WAV_RATE);
    const src = off.createBufferSource();
    src.buffer = decoded;
    src.connect(off.destination);
    src.start();
    const pcm = (await off.startRendering()).getChannelData(0);

    const buf = new ArrayBuffer(44 + pcm.length * 2);
    const dv = new DataView(buf);
    const str = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
    str(0, 'RIFF'); dv.setUint32(4, 36 + pcm.length * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
    dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
    dv.setUint32(24, WAV_RATE, true); dv.setUint32(28, WAV_RATE * 2, true);
    dv.setUint16(32, 2, true); dv.setUint16(34, 16, true); str(36, 'data'); dv.setUint32(40, pcm.length * 2, true);
    for (let i = 0; i < pcm.length; i++) {
      const v = Math.max(-1, Math.min(1, pcm[i]));
      dv.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
    }
    return new Blob([buf], { type: 'audio/wav' });
  }

  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result).split(',')[1]);
      r.onerror = reject;
      r.readAsDataURL(blob);
    });
  }

  async function recordVoice() {
    if (state.busy) return;
    if (!mediaSupported() || typeof MediaRecorder === 'undefined') { $('bioVoiceMsg').textContent = insecureMessage(); return; }
    try {
      state.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      $('bioVoiceMsg').textContent = 'Accesso al microfono negato o non disponibile: ' + (e.name || e.message);
      return;
    }
    state.busy = true;
    $('bioVoiceRec').disabled = true;
    $('bioVoiceRetake').hidden = true;
    $('bioVoicePlayer').hidden = true;
    $('bioVoiceMsg').textContent = 'Registrazione in corso… parla ora.';

    const Ctx = window.AudioContext || window.webkitAudioContext;
    state.audioCtx = new Ctx();
    const analyser = state.audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    state.audioCtx.createMediaStreamSource(state.micStream).connect(analyser);
    drawWave(analyser);

    const chunks = [];
    const rec = new MediaRecorder(state.micStream);
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    const done = new Promise((resolve) => { rec.onstop = resolve; });
    rec.start();

    const t0 = performance.now();
    const bar = $('bioRecBar');
    const prog = setInterval(() => {
      bar.style.width = Math.min(100, ((performance.now() - t0) / (REC_SECONDS * 1000)) * 100) + '%';
    }, 60);
    await new Promise((r) => setTimeout(r, REC_SECONDS * 1000));
    clearInterval(prog);
    rec.stop();
    await done;
    stopMic();

    try {
      const wav = await blobToWav(new Blob(chunks, { type: rec.mimeType || 'audio/webm' }));
      state.voiceB64 = await blobToBase64(wav);
      const player = $('bioVoicePlayer');
      player.src = URL.createObjectURL(wav);
      player.hidden = false;
      $('bioVoiceMsg').textContent = 'Registrazione acquisita. Riascoltala prima di salvare.';
      $('bioVoiceRec').hidden = true;
      $('bioVoiceRetake').hidden = false;
    } catch (e) {
      state.voiceB64 = null;
      $('bioVoiceMsg').textContent = 'Impossibile elaborare l\'audio registrato: ' + (e.message || e.name);
    }
    $('bioVoiceRec').disabled = false;
    state.busy = false;
  }

  // ── Salvataggio ──────────────────────────────────────────────────────────────
  async function save() {
    const err = $('bioError');
    err.textContent = '';
    const name = $('bioName').value.trim();
    if (name.length < 3) { err.textContent = 'Inserisci nome e cognome.'; return; }
    if (!state.faceB64) { err.textContent = 'Cattura prima il volto.'; return; }
    if (!adminPin && !$('bioPin').value.trim()) { err.textContent = 'Inserisci il PIN Manutentore.'; return; }

    $('bioSave').disabled = true;
    try {
      const res = await fetch('/api/biometrics/enroll', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          name,
          role: $('bioRole').value.trim(),
          open_gate: $('bioOpenGate').checked,
          greeting: $('bioGreeting').value.trim(),
          face_b64: state.faceB64,
          audio_b64: state.voiceB64 || '',
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.success) throw new Error(data.error || 'HTTP ' + res.status);
      closeModal();
      await refresh();
      if (typeof window.openWindow === 'function') window.openWindow('biometrics');
    } catch (e) {
      err.textContent = 'Salvataggio non riuscito: ' + e.message;
    } finally {
      $('bioSave').disabled = false;
    }
  }

  // ── Feed dialogo al varco ────────────────────────────────────────────────────
  let lastDialogueKey = '';
  function bubble(kind, text, meta) {
    const b = document.createElement('div');
    b.className = 'bio-bubble is-' + kind;
    const t = document.createElement('span');
    t.textContent = text;
    b.appendChild(t);
    if (meta) {
      const m = document.createElement('small');
      m.textContent = meta;
      b.appendChild(m);
    }
    return b;
  }

  async function pollDialogue() {
    const win = $('win-ptt');
    if (!win || win.hidden) return;
    try {
      const res = await fetch('/api/orin/dialogue?limit=30', { cache: 'no-store' });
      if (!res.ok) return;
      const entries = (await res.json()).entries || [];
      const key = entries.length ? entries[entries.length - 1].ts + entries.length : '';
      if (key === lastDialogueKey) return;
      lastDialogueKey = key;
      const feed = $('orinDialogueFeed');
      feed.replaceChildren();
      $('orinDialogueCount').textContent = String(entries.length);
      if (!entries.length) {
        const p = document.createElement('p');
        p.className = 'bio-empty';
        p.textContent = 'Nessuna conversazione registrata al varco.';
        feed.appendChild(p);
        return;
      }
      entries.forEach((e) => {
        const time = (e.ts || '').slice(11, 19);
        if (e.transcription) feed.appendChild(bubble('user', e.transcription, time + (e.identity_name ? ' · ' + e.identity_name : '')));
        if (e.reply) feed.appendChild(bubble('orin', e.reply, `ORIN · ${e.latency_ms} ms`));
      });
      feed.scrollTop = feed.scrollHeight;
    } catch (e) { /* server offline */ }
  }

  // ── Avvio ────────────────────────────────────────────────────────────────────
  window.onPinUnlocked = async function (role, pin) {
    if (role !== 'maintainer') { adminPin = null; return; }
    adminPin = pin;
    try {
      await fetchProfiles();
      renderList();
      if (!profiles.length) openModal(true);
    } catch (e) { /* server non raggiungibile: nessun onboarding */ }
  };

  document.addEventListener('DOMContentLoaded', () => {
    $('bioAddBtn').addEventListener('click', () => openModal(false));
    $('bioModalClose').addEventListener('click', closeModal);
    $('bioCancel').addEventListener('click', closeModal);
    $('bioSave').addEventListener('click', save);
    $('bioFaceStart').addEventListener('click', startCamera);
    $('bioFaceCapture').addEventListener('click', captureFace);
    $('bioFaceRetake').addEventListener('click', retakeFace);
    $('bioVoiceRec').addEventListener('click', recordVoice);
    $('bioVoiceRetake').addEventListener('click', recordVoice);
    $('bioName').addEventListener('input', updatePhrase);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('bioEnrollModal').hidden) closeModal(); });

    // Aggiorna l'elenco ogni volta che la finestra viene aperta
    const win = $('win-biometrics');
    new MutationObserver(() => { if (!win.hidden) refresh(); }).observe(win, { attributes: true, attributeFilter: ['hidden'] });

    pollDialogue();
    setInterval(pollDialogue, 4000);
  });
})();
