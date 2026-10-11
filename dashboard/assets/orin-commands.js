/* ══════════════════════════════════════════════════════════════════════════════
 * ORIN — Interprete dei comandi scritti
 *
 * Trasforma una frase in italiano ("fammi vedere il piazzale", "chiudi tutto")
 * in un'azione strutturata. E' DETERMINISTICO: nessuna AI, risposta immediata e
 * sempre uguale per la stessa frase. Quando arrivera' la voce, la trascrizione
 * passera' da qui senza cambiare nulla.
 *
 * Per aggiungere un sinonimo, una telecamera o una finestra si modifica solo il
 * blocco VOCABOLARIO qui sotto. I test sono in test/orin-commands.test.js
 * (node test/orin-commands.test.js).
 *
 * Tolleranza: maiuscole, accenti, punteggiatura, parole di cortesia e piccoli
 * errori di battitura ("piazale", "magazino") vengono assorbiti.
 * ══════════════════════════════════════════════════════════════════════════════ */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.OrinCommands = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ────────────────────────────────────────────────────────────────────────────
  // VOCABOLARIO
  // ────────────────────────────────────────────────────────────────────────────
  const VOCABOLARIO = {
    // id = numero usato da openCamModal(n) nella dashboard
    telecamere: [
      { id: 1, nome: 'il piazzale', parole: ['piazzale', 'esterno', 'parcheggio', 'ingresso', 'cortile', 'carrabile'] },
      { id: 2, nome: 'il magazzino', parole: ['magazzino', 'capannone', 'interno', 'scaffali', 'deposito', 'pedonale'] },
      { id: 3, nome: 'il corridoio', parole: ['corridoio', 'passaggio', 'transito'] }
    ],
    numeri: {
      1: ['1', 'uno', 'prima', 'primo'],
      2: ['2', 'due', 'seconda', 'secondo'],
      3: ['3', 'tre', 'terza', 'terzo']
    },
    nomiTelecamera: ['telecamera', 'camera', 'cam', 'videocamera'],
    finestre: {
      wall: { titolo: 'le telecamere', parole: ['telecamere', 'camere', 'videocamere', 'video', 'diretta', 'live', 'monitor'] },
      events: { titolo: 'gli eventi', parole: ['eventi', 'evento', 'allarmi', 'archivio', 'registro', 'storico', 'evidenze', 'registrazioni', 'rilevamenti'] },
      plates: { titolo: 'le targhe', parole: ['targhe', 'targa', 'whitelist', 'veicoli'] },
      diagnostics: { titolo: 'lo stato della Jetson', parole: ['diagnostica', 'telemetria', 'jetson', 'hardware', 'temperatura', 'salute'] },
      settings: { titolo: 'le impostazioni', parole: ['impostazioni', 'impostazione', 'configurazione', 'audio', 'volume', 'voce', 'voci', 'orari', 'orario', 'pin', 'sorveglianza'] },
      connectors: { titolo: 'i connettori cloud', parole: ['connettori', 'connettore', 'cloud', 'google', 'drive', 'integrazioni', 'collegamenti', 'nodi'] },
      ptt: { titolo: "l'interfono vocale", parole: ['microfono', 'interfono', 'registratore', 'citofono', 'voce live'] }
    },
    identikit: ['identikit', 'scheda', 'dossier'],
    azioni: {
      faro: ['faro', 'fari', 'luce', 'luci', 'faretto', 'faretti', 'illumina'],
      voce: [
        'dissuasione', 'dissuadi', 'avviso', 'avvisa', 'sirena', 'annuncio', 'annuncia',
        'altoparlante', 'diffusore', 'audio', 'riproduci', 'riprodurre', 'riproduzione',
        'trasmetti', 'trasmettere', 'trasmissione', 'diffondi', 'diffondere', 'suona', 'suonare',
        'parla', 'parlare', 'comunica', 'comunicare'
      ],
      cancello: ['cancello', 'portone', 'sbarra']
    },
    blocca: ['blocca', 'esci', 'logout', 'disconnetti'],
    aiuto: ['aiuto', 'comandi', 'help', 'istruzioni', 'sai'],
    saluto: ['ciao', 'buongiorno', 'buonasera', 'salve', 'ehi'],
    stato: ['stato', 'situazione', 'protetto', 'armato', 'armata', 'sicuro'],
    chiudi: ['chiudi', 'nascondi', 'togli', 'rimuovi', 'basta'],
    tutto: ['tutto', 'tutte', 'tutti', 'finestre'],
    conferma: ['si', 'confermo', 'conferma', 'ok', 'procedi', 'vai'],
    modalita: {
      assente: ['assente', 'totale'],
      notte: ['notte', 'notturno', 'notturna', 'perimetrale'],
      casa: ['casa', 'disarma', 'disarmare', 'disarmo', 'presidio'],
      manutenzione: ['manutenzione']
    },
    // Parole che non cambiano il significato del comando
    vuote: [
      'il', 'lo', 'la', 'l', 'i', 'gli', 'le', 'un', 'una', 'uno', 'di', 'del', 'dello', 'della', 'dei', 'degli', 'delle',
      'al', 'allo', 'alla', 'ai', 'agli', 'alle', 'sul', 'sulla', 'nel', 'nella', 'da', 'dal', 'dalla',
      'per', 'favore', 'piacere', 'mi', 'me', 'ti', 'ci', 'fammi', 'fai', 'puoi', 'potresti', 'vorrei',
      'voglio', 'apri', 'aprimi', 'mostra', 'mostrami', 'vedere', 'vedi', 'visualizza', 'guarda',
      'inquadra', 'dammi', 'metti', 'su', 'e', 'a', 'in', 'con', 'ora', 'adesso', 'subito', 'orin',
      'ehi', 'ciao', 'grazie', 'accendi', 'attiva', 'lancia', 'manda', 'fai', 'partire', 'quella',
      'quello', 'questa', 'questo', 'che', 'cosa', 'come', 'va', 'sei', 'tutto', 'ok',
      'solo', 'soltanto', 'solamente', 'varco', 'varchi', 'modalita', 'profilo', 'siamo', 'sono'
    ]
  };

  // ────────────────────────────────────────────────────────────────────────────
  // NORMALIZZAZIONE E CONFRONTO TOLLERANTE
  // ────────────────────────────────────────────────────────────────────────────
  function normalizza(testo) {
    return String(testo || '')
      .toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '')   // accenti
      .replace(/[^a-z0-9\s]/g, ' ')                        // punteggiatura e apostrofi
      .split(/\s+/)
      .filter(Boolean);
  }

  function distanza(a, b) {
    if (a === b) return 0;
    const m = a.length, n = b.length;
    if (Math.abs(m - n) > 2) return 3;
    let prev = Array.from({ length: n + 1 }, (_, j) => j);
    for (let i = 1; i <= m; i++) {
      const cur = [i];
      for (let j = 1; j <= n; j++) {
        cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      }
      prev = cur;
    }
    return prev[n];
  }

  // Errori ammessi in base alla lunghezza: le parole corte devono essere esatte,
  // altrimenti "cam" diventerebbe "can" e "tre" diventerebbe "te".
  function somiglia(parola, voce) {
    if (parola === voce) return true;
    const ammessi = voce.length >= 8 ? 2 : voce.length >= 5 ? 1 : 0;
    return ammessi > 0 && distanza(parola, voce) <= ammessi;
  }

  function contiene(token, elenco) {
    return token.some((t) => elenco.some((v) => somiglia(t, v)));
  }

  // ────────────────────────────────────────────────────────────────────────────
  // RICONOSCIMENTO DEGLI OGGETTI
  // ────────────────────────────────────────────────────────────────────────────
  function trovaNumero(token) {
    for (const [n, parole] of Object.entries(VOCABOLARIO.numeri)) {
      if (token.some((t) => parole.includes(t))) return Number(n);
    }
    return null;
  }

  function trovaTelecamera(token) {
    for (const cam of VOCABOLARIO.telecamere) {
      if (contiene(token, cam.parole)) return cam;
    }
    // "telecamera 2", "la seconda telecamera", oppure solo "2"
    const numero = trovaNumero(token);
    if (numero !== null) {
      const conNome = contiene(token, VOCABOLARIO.nomiTelecamera);
      const solo = token.length === 1;
      if (conNome || solo) return VOCABOLARIO.telecamere.find((c) => c.id === numero) || null;
    }
    return null;
  }

  function trovaFinestra(token) {
    for (const [chiave, f] of Object.entries(VOCABOLARIO.finestre)) {
      if (contiene(token, f.parole)) return chiave;
    }
    return null;
  }

  function trovaAzione(token) {
    for (const [chiave, parole] of Object.entries(VOCABOLARIO.azioni)) {
      if (contiene(token, parole)) return chiave;
    }
    return null;
  }

  // ────────────────────────────────────────────────────────────────────────────
  // RISPOSTE DI ORIN
  // ────────────────────────────────────────────────────────────────────────────
  const AIUTO =
    'Puoi scrivere per esempio: telecamere, piazzale, magazzino, eventi, targhe, ' +
    'impostazioni, accendi i fari, chiudi tutto.';

  function titolo(view) {
    return VOCABOLARIO.finestre[view].titolo;
  }

  // Suggerimento per le frasi non capite: la parola del vocabolario piu' vicina
  function suggerisci(tokenGrezzi) {
    const candidati = [];
    VOCABOLARIO.telecamere.forEach((c) => c.parole.forEach((p) => candidati.push([p, c.parole[0]])));
    Object.values(VOCABOLARIO.finestre).forEach((f) => f.parole.forEach((p) => candidati.push([p, f.parole[0]])));
    Object.values(VOCABOLARIO.azioni).forEach((a) => a.forEach((p) => candidati.push([p, a[0]])));
    let migliore = null;
    tokenGrezzi.forEach((t) => {
      if (t.length < 4) return;
      const soglia = Math.max(1, Math.floor(t.length / 3));
      candidati.forEach(([parola, comando]) => {
        const d = distanza(t, parola);
        if (d <= soglia && (!migliore || d < migliore.d)) migliore = { d, comando };
      });
    });
    return migliore ? migliore.comando : null;
  }

  // ────────────────────────────────────────────────────────────────────────────
  // INTERPRETAZIONE
  //
  // L'ordine delle regole conta: prima le intenzioni esplicite (chiudere,
  // cancello, fari, avviso), poi gli oggetti (telecamera, finestra).
  // ────────────────────────────────────────────────────────────────────────────
  function interpreta(testo) {
    const grezzi = normalizza(testo);
    if (grezzi.length === 0) return { tipo: 'vuoto', risposta: '' };

    // Le parole di chiusura e i numeri si valutano prima di togliere le "vuote"
    const chiudere = contiene(grezzi, VOCABOLARIO.chiudi);
    const tutto = contiene(grezzi, VOCABOLARIO.tutto);
    // Restano solo le parole che dicono COSA si vuole: via la cortesia e le parole
    // di chiusura, gia' registrate sopra (cosi' "chiudi 2" trova la telecamera 2)
    const token = grezzi.filter((t) =>
      /^\d+$/.test(t) || (!VOCABOLARIO.vuote.includes(t) && !VOCABOLARIO.chiudi.includes(t)));

    const telecamera = trovaTelecamera(token.length ? token : grezzi);
    const finestra = trovaFinestra(token);
    const azione = trovaAzione(token);

    // Sintesi vocale diretta o dettatura da diffondere ("parla: ...", "dì: ...", "annuncia: ...")
    const matchParla = String(testo || '').match(/^(?:parla|di|dì|annuncia)\s*[:]\s*(.+)$/i) ||
                       String(testo || '').match(/^(?:parla|di|dì|annuncia)\s+(?:a\s+tutti\s+|sul\s+fanvil\s+)?(?:che|di)\s+(.+)$/i);
    if (matchParla && matchParla[1].trim()) {
      const msg = matchParla[1].trim();
      return {
        tipo: 'parla-testo',
        testo: msg,
        risposta: `Trasmetto l'annuncio vocale: "${msg}"`
      };
    }

    if (chiudere) {
      if (azione === 'cancello') {
        return { tipo: 'risposta', risposta: 'Il cancello si richiude da solo dopo l\'impulso.' };
      }
      if (telecamera) {
        return { tipo: 'chiudi-telecamera', telecamera: telecamera.id, risposta: `Chiudo ${telecamera.nome}.` };
      }
      if (finestra && !tutto) {
        return { tipo: 'chiudi-finestra', finestra, risposta: `Chiudo ${titolo(finestra)}.` };
      }
      return { tipo: 'chiudi-tutto', risposta: 'Chiudo tutto.' };
    }

    if (azione === 'cancello') {
      return {
        tipo: 'azione', azione: 'cancello', conferma: true,
        risposta: 'Vuoi aprire il cancello? Scrivi sì per confermare.'
      };
    }
    if (azione === 'faro') {
      if (telecamera) {
        return {
          tipo: 'azione',
          azione: 'faro',
          telecamera: telecamera.id,
          targetNome: telecamera.nome,
          risposta: `Accendo i fari per ${telecamera.nome}.`
        };
      }
      return { tipo: 'azione', azione: 'faro', risposta: 'Accendo i fari del piazzale.' };
    }
    if (azione === 'voce') {
      if (telecamera) {
        return {
          tipo: 'azione',
          azione: 'voce',
          telecamera: telecamera.id,
          targetNome: telecamera.nome,
          risposta: `Mando l'avviso vocale per ${telecamera.nome}.`
        };
      }
      if (!telecamera && contiene(token, VOCABOLARIO.nomiTelecamera)) {
        return {
          tipo: 'scelta-varco',
          azione: 'voce',
          risposta: 'Su quale telecamera vuoi trasmettere? Scegli Piazzale, Magazzino o Corridoio.',
          azioni: [
            { label: 'Piazzale', command: 'riproduci al piazzale' },
            { label: 'Magazzino', command: 'riproduci al magazzino' },
            { label: 'Corridoio', command: 'riproduci al corridoio' },
            { label: 'Tutti i varchi', command: 'manda l\'avviso' }
          ]
        };
      }
      return { tipo: 'azione', azione: 'voce', risposta: 'Mando l\'avviso sull\'altoparlante.' };
    }

    if (contiene(token, VOCABOLARIO.blocca)) {
      return { tipo: 'blocca', risposta: 'Blocco la sessione.' };
    }
    if (contiene(token, VOCABOLARIO.aiuto)) {
      return { tipo: 'aiuto', risposta: AIUTO };
    }
    if (contiene(token, VOCABOLARIO.identikit)) {
      return { tipo: 'identikit', risposta: 'Ecco la scheda dell\'ultimo passaggio.' };
    }

    // "tutte le telecamere" e il plurale aprono la parete video, non una telecamera
    if (telecamera && !(tutto && finestra === 'wall')) {
      return { tipo: 'apri-telecamera', telecamera: telecamera.id, risposta: `Ecco ${telecamera.nome}.` };
    }
    if (finestra) {
      return { tipo: 'apri-finestra', finestra, risposta: `Apro ${titolo(finestra)}.` };
    }
    if (tutto) {
      return { tipo: 'apri-finestra', finestra: 'wall', risposta: `Apro ${titolo('wall')}.` };
    }
    if (contiene(token.length ? token : grezzi, VOCABOLARIO.stato)) {
      return { tipo: 'stato', risposta: '' };
    }
    if (contiene(token, VOCABOLARIO.modalita.assente)) {
      return { tipo: 'imposta-modalita', modalita: 'assente', risposta: 'Imposto la modalità Assente: massima protezione perimetro e interno attiva 24/7.' };
    }
    if (contiene(token, VOCABOLARIO.modalita.notte)) {
      return { tipo: 'imposta-modalita', modalita: 'notte', risposta: 'Imposto la modalità Notte: perimetro del piazzale armato, aree interne silenziose.' };
    }
    if (contiene(token, VOCABOLARIO.modalita.casa)) {
      return { tipo: 'imposta-modalita', modalita: 'casa', risposta: 'Imposto la modalità Casa: presidio attivo con monitoraggio silenzioso.' };
    }
    if (contiene(token, VOCABOLARIO.modalita.manutenzione)) {
      return { tipo: 'imposta-modalita', modalita: 'manutenzione', durata: 30, risposta: 'Attivo la modalità Manutenzione per 30 minuti con ripristino automatico.' };
    }
    if (contiene(grezzi, VOCABOLARIO.saluto)) {
      return { tipo: 'saluto', risposta: 'Ciao. Dimmi cosa vuoi vedere.' };
    }

    const suggerimento = suggerisci(grezzi);
    return {
      tipo: 'sconosciuto',
      suggerimento,
      risposta: suggerimento
        ? `Non ho capito. Intendi "${suggerimento}"?`
        : 'Non ho capito. Scrivi aiuto per vedere i comandi.'
    };
  }

  function eConferma(testo) {
    const t = normalizza(testo);
    return t.length > 0 && t.length <= 3 && t.some((p) => VOCABOLARIO.conferma.includes(p));
  }

  return { interpreta, eConferma, normalizza, VOCABOLARIO, AIUTO };
});
