/* ══════════════════════════════════════════════════════════════════════════════
 * ORIN — Occhio cartoon (SVG)
 *
 * Un unico occhio grande e lucido, in stile animazione: iride blu con riflessi,
 * palpebre che sbattono e seguono lo sguardo. Disegnato in SVG, quindi nitido a
 * qualsiasi dimensione e senza bisogno di WebGL.
 *
 * Uso:
 *   const eye = OrinEye.create(contenitore);
 *   // a ogni fotogramma:
 *   eye.frame(adesso, { gazeX, gazeY, mood });   // gaze in -1..1
 *   eye.blink();                                  // battito su richiesta
 *
 * Stati d'animo (mood):
 *   idle    sveglio e rilassato
 *   think   sta elaborando: sguardo in alto, occhio un po' socchiuso
 *   happy   comando eseguito: "sorride" alzando la palpebra inferiore
 *   alert   allarme: occhio spalancato, pupilla stretta
 *   sleepy  monitoraggio silenzioso: palpebre a meta'
 * ══════════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  const NS = 'http://www.w3.org/2000/svg';
  const R = 160;            // raggio del bulbo
  const IRIS = 76;          // raggio dell'iride
  const PAD = 40;           // le palpebre debordano oltre il bulbo, poi il ritaglio le rifinisce

  // GEOMETRIA DELLE PALPEBRE
  // Una palpebra e' un guscio che ruota attorno all'asse orizzontale del bulbo:
  // visto di fronte, il suo bordo e' mezza ellisse che passa per gli angoli
  // dell'occhio (±R, 0) e ha il centro all'altezza "edge".
  //   palpebra superiore: edge = -R aperta del tutto ... 0 chiusa (bordo orizzontale)
  //   palpebra inferiore: edge = +R aperta del tutto ... 0 chiusa
  // Nel battito la superiore supera l'equatore e scende fino al bordo inferiore.
  const MOODS = {
    idle:   { upper: -138, lower: 152, pupil: 1.0,  scale: 1.0 },
    think:  { upper: -112, lower: 140, pupil: 1.12, scale: 1.0 },
    happy:  { upper: -128, lower: 92,  pupil: 1.15, scale: 1.02 },   // occhio che "sorride"
    alert:  { upper: -160, lower: 160, pupil: 0.62, scale: 1.06 },   // tondo e spalancato
    sleepy: { upper: -34,  lower: 140, pupil: 0.95, scale: 0.98 }
  };

  // Mezza ellisse da (R,0) a (-R,0) con il centro del bordo a y = edge
  function arc(edge) {
    if (Math.abs(edge) < 0.5) return `L${-R} 0`;
    const sweep = edge > 0 ? 1 : 0;   // sopra l'equatore o sotto
    return `A${R} ${Math.abs(edge).toFixed(1)} 0 0 ${sweep} ${-R} 0`;
  }

  function upperLidPath(edge) {
    return `M${-R - PAD} ${-R - PAD} L${R + PAD} ${-R - PAD} L${R + PAD} 0 L${R} 0 ${arc(edge)} L${-R - PAD} 0 Z`;
  }

  function lowerLidPath(edge) {
    return `M${-R - PAD} ${R + PAD} L${R + PAD} ${R + PAD} L${R + PAD} 0 L${R} 0 ${arc(edge)} L${-R - PAD} 0 Z`;
  }

  function edgePath(edge) {
    return `M${R} 0 ${arc(edge)}`;
  }

  function el(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    if (parent) parent.appendChild(node);
    return node;
  }

  function stop(gradient, offset, color, opacity) {
    el('stop', { offset, 'stop-color': color, 'stop-opacity': opacity === undefined ? 1 : opacity }, gradient);
  }

  function create(container) {
    const uid = 'orinEye' + Math.random().toString(36).slice(2, 7);
    const svg = el('svg', {
      viewBox: '-220 -220 440 460',
      class: 'orin-eye-svg',
      role: 'img',
      'aria-label': 'ORIN'
    }, container);

    // ── Sfumature ────────────────────────────────────────────────────────────
    const defs = el('defs', {}, svg);

    const sclera = el('radialGradient', { id: `${uid}-sclera`, cx: '42%', cy: '36%', r: '70%' }, defs);
    stop(sclera, '0%', '#ffffff');
    stop(sclera, '62%', '#f4f8ff');
    stop(sclera, '100%', '#c9d9f2');

    const iris = el('radialGradient', { id: `${uid}-iris`, cx: '50%', cy: '50%', r: '50%' }, defs);
    stop(iris, '0%', '#c6e6ff');
    stop(iris, '30%', '#5eb0ff');
    stop(iris, '68%', '#1f6fe0');
    stop(iris, '100%', '#0b347e');

    const lid = el('linearGradient', { id: `${uid}-lid`, x1: '0', y1: '0', x2: '0', y2: '1' }, defs);
    stop(lid, '0%', '#2a66d6');
    stop(lid, '100%', '#5a9bf7');

    const lowerLid = el('linearGradient', { id: `${uid}-lower`, x1: '0', y1: '0', x2: '0', y2: '1' }, defs);
    stop(lowerLid, '0%', '#5a9bf7');
    stop(lowerLid, '100%', '#2a66d6');

    const topShade = el('linearGradient', { id: `${uid}-shade`, x1: '0', y1: '0', x2: '0', y2: '1' }, defs);
    stop(topShade, '0%', '#123a7a', 0.28);
    stop(topShade, '38%', '#123a7a', 0);

    const blur = el('filter', { id: `${uid}-blur`, x: '-50%', y: '-50%', width: '200%', height: '200%' }, defs);
    el('feGaussianBlur', { stdDeviation: '9' }, blur);

    const clip = el('clipPath', { id: `${uid}-clip` }, defs);
    el('circle', { r: R - 3 }, clip);

    // ── Ombra a terra ────────────────────────────────────────────────────────
    const shadow = el('ellipse', {
      cx: 0, cy: 212, rx: 116, ry: 15,
      fill: '#06245e', opacity: '0.32', filter: `url(#${uid}-blur)`
    }, svg);

    // ── Occhio ───────────────────────────────────────────────────────────────
    const body = el('g', {}, svg);
    const inner = el('g', { 'clip-path': `url(#${uid}-clip)` }, body);

    el('circle', { r: R, fill: `url(#${uid}-sclera)` }, inner);

    const irisGroup = el('g', {}, inner);
    el('circle', { r: IRIS, fill: `url(#${uid}-iris)` }, irisGroup);
    // Venature dell'iride
    const fibers = el('g', { stroke: '#ffffff', 'stroke-opacity': '0.16', 'stroke-width': '2.2', 'stroke-linecap': 'round' }, irisGroup);
    for (let i = 0; i < 40; i++) {
      const a = (i / 40) * Math.PI * 2;
      const r1 = 34 + (i % 3) * 3;
      const r2 = 66 + (i % 2) * 6;
      el('line', {
        x1: (Math.cos(a) * r1).toFixed(1), y1: (Math.sin(a) * r1).toFixed(1),
        x2: (Math.cos(a) * r2).toFixed(1), y2: (Math.sin(a) * r2).toFixed(1)
      }, fibers);
    }
    el('circle', { r: IRIS, fill: 'none', stroke: '#0a2c6b', 'stroke-width': '5' }, irisGroup);
    const pupil = el('circle', { r: 33, fill: '#06173a' }, irisGroup);
    // Riflessi: danno l'aria viva e "bagnata" tipica dei cartoni
    el('ellipse', { cx: -26, cy: -30, rx: 21, ry: 15, fill: '#ffffff', opacity: '0.95', transform: 'rotate(-32 -26 -30)' }, irisGroup);
    el('circle', { cx: 24, cy: 24, r: 7, fill: '#ffffff', opacity: '0.85' }, irisGroup);

    // Ombra della palpebra sulla parte alta del bulbo e lucido della cornea
    el('rect', { x: -R, y: -R, width: R * 2, height: R * 2, fill: `url(#${uid}-shade)` }, inner);
    el('ellipse', { cx: -72, cy: -92, rx: 36, ry: 20, fill: '#ffffff', opacity: '0.5', transform: 'rotate(-35 -72 -92)' }, inner);

    // Palpebre. La superiore proietta un'ombra morbida sul bianco e ha un filo
    // di luce sul bordo: e' quello che la fa sembrare pelle e non un cappello.
    const lidShadow = el('path', {
      fill: 'none', stroke: '#0b2a63', 'stroke-width': '18', opacity: '0.22', filter: `url(#${uid}-blur)`
    }, inner);
    const lowerLidShape = el('path', { fill: `url(#${uid}-lower)` }, inner);
    const lowerEdge = el('path', { fill: 'none', stroke: '#0f3270', 'stroke-width': '5', 'stroke-linecap': 'round' }, inner);
    const upperLid = el('path', { fill: `url(#${uid}-lid)` }, inner);
    const upperShine = el('path', { fill: 'none', stroke: '#9cc6ff', 'stroke-width': '4', opacity: '0.7' }, inner);
    const upperEdge = el('path', { fill: 'none', stroke: '#0f3270', 'stroke-width': '7', 'stroke-linecap': 'round' }, inner);

    // Contorno da cartone animato
    el('circle', { r: R, fill: 'none', stroke: '#0f3270', 'stroke-width': '8' }, body);

    // ── Stato animato ────────────────────────────────────────────────────────
    const s = {
      gx: 0, gy: 0, upper: MOODS.idle.upper, lower: MOODS.idle.lower,
      pupil: 1, scale: 1, blinkStart: -1, nextBlink: performance.now() + 2500,
      sacX: 0, sacY: 0, nextSaccade: performance.now() + 1200
    };
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');

    function blink() {
      if (s.blinkStart < 0) s.blinkStart = performance.now();
    }

    function frame(now, o) {
      const mood = MOODS[o.mood] || MOODS.idle;

      // Battito spontaneo ogni 3-6 secondi (non mentre e' assonnato)
      if (o.mood !== 'sleepy' && now > s.nextBlink && s.blinkStart < 0) {
        blink();
        s.nextBlink = now + 3000 + Math.random() * 3000;
      }
      let b = 0;
      if (s.blinkStart >= 0) {
        const k = (now - s.blinkStart) / 170;
        b = k < 0.45 ? k / 0.45 : Math.max(0, 1 - (k - 0.45) / 0.55);
        if (k >= 1) s.blinkStart = -1;
      }

      // Piccoli scatti dello sguardo quando e' a riposo: l'occhio sembra pensare
      if (!reduced.matches && now > s.nextSaccade) {
        const calm = o.mood === 'idle' || o.mood === 'sleepy';
        s.sacX = calm ? (Math.random() - 0.5) * 0.14 : 0;
        s.sacY = calm ? (Math.random() - 0.5) * 0.1 : 0;
        s.nextSaccade = now + 900 + Math.random() * 2200;
      }

      const k = 0.16;
      s.gx += ((o.gazeX || 0) + s.sacX - s.gx) * 0.12;
      s.gy += ((o.gazeY || 0) + s.sacY - s.gy) * 0.12;
      s.upper += (mood.upper - s.upper) * k;
      s.lower += (mood.lower - s.lower) * k;
      s.pupil += (mood.pupil - s.pupil) * 0.12;
      s.scale += (mood.scale - s.scale) * 0.12;

      const gx = Math.max(-1, Math.min(1, s.gx));
      const gy = Math.max(-1, Math.min(1, s.gy));

      // Iride: si sposta e si schiaccia leggermente verso il bordo (prospettiva)
      const ix = gx * 62;
      const iy = gy * 52;
      const squash = 1 - Math.min(0.16, Math.hypot(gx, gy) * 0.12);
      const angle = Math.atan2(iy, ix) * 180 / Math.PI;
      irisGroup.setAttribute('transform',
        `translate(${ix.toFixed(1)} ${iy.toFixed(1)}) rotate(${angle.toFixed(1)}) scale(${squash.toFixed(3)} 1) rotate(${(-angle).toFixed(1)})`);
      pupil.setAttribute('r', (33 * s.pupil).toFixed(1));

      // Le palpebre seguono lo sguardo in verticale, come negli occhi veri.
      // Nel battito l'inferiore sale appena e la superiore scende fino a toccarla.
      // Oltre ±R il bordo uscirebbe dal bulbo e coprirebbe gli angoli: si limita
      const upperY = Math.max(-R, s.upper + gy * 22);
      const lowerY = Math.min(R, s.lower + gy * 12);
      const low = lowerY - (lowerY - 40) * b * 0.2;
      const up = Math.min(upperY + (low - upperY) * b, low);

      upperLid.setAttribute('d', upperLidPath(up));
      upperEdge.setAttribute('d', edgePath(up));
      upperShine.setAttribute('d', edgePath(Math.max(-R, up - 6)));
      lidShadow.setAttribute('d', up < -16 ? edgePath(up + 14) : '');
      lowerLidShape.setAttribute('d', lowerLidPath(low));
      lowerEdge.setAttribute('d', edgePath(low));

      // Respiro leggero e "schiacciamento" durante il battito
      const bob = reduced.matches ? 0 : Math.sin(now / 900) * 4;
      const squish = 1 - b * 0.03;
      body.setAttribute('transform',
        `translate(0 ${bob.toFixed(1)}) scale(${s.scale.toFixed(3)} ${(s.scale * squish).toFixed(3)})`);
      shadow.setAttribute('rx', (116 - bob * 2).toFixed(1));
    }

    return { frame, blink, svg };
  }

  window.OrinEye = { create };
})();
