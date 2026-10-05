/* Test dell'interprete dei comandi di ORIN.
 * Esecuzione: node test/orin-commands.test.js
 * Ogni riga: frase scritta -> risultato atteso. Aggiungere qui ogni nuovo
 * sinonimo, cosi' si vede subito se rompe un comando che funzionava.
 */
const { interpreta, eConferma } = require('../assets/orin-commands.js');

const CASI = [
  // Telecamere per nome, numero, sinonimo ed errore di battitura
  ['mostra piazzale', { tipo: 'apri-telecamera', telecamera: 1 }],
  ['fammi vedere il magazzino per favore', { tipo: 'apri-telecamera', telecamera: 2 }],
  ['Apri il CORRIDOIO!', { tipo: 'apri-telecamera', telecamera: 3 }],
  ['telecamera 1', { tipo: 'apri-telecamera', telecamera: 1 }],
  ['la seconda telecamera', { tipo: 'apri-telecamera', telecamera: 2 }],
  ['cam 3', { tipo: 'apri-telecamera', telecamera: 3 }],
  ['3', { tipo: 'apri-telecamera', telecamera: 3 }],
  ['piazale', { tipo: 'apri-telecamera', telecamera: 1 }],
  ['magazino', { tipo: 'apri-telecamera', telecamera: 2 }],
  ['inquadra il parcheggio', { tipo: 'apri-telecamera', telecamera: 1 }],
  ['capannone', { tipo: 'apri-telecamera', telecamera: 2 }],

  // Finestre
  ['telecamere', { tipo: 'apri-finestra', finestra: 'wall' }],
  ['tutte le telecamere', { tipo: 'apri-finestra', finestra: 'wall' }],
  ['mostra tutto', { tipo: 'apri-finestra', finestra: 'wall' }],
  ['eventi', { tipo: 'apri-finestra', finestra: 'events' }],
  ['mostrami gli allarmi', { tipo: 'apri-finestra', finestra: 'events' }],
  ['archivio registrazioni', { tipo: 'apri-finestra', finestra: 'events' }],
  ['targhe', { tipo: 'apri-finestra', finestra: 'plates' }],
  ['apri la whitelist', { tipo: 'apri-finestra', finestra: 'plates' }],
  ['impostazioni', { tipo: 'apri-finestra', finestra: 'settings' }],
  ['volume', { tipo: 'apri-finestra', finestra: 'settings' }],
  ['impostazoni', { tipo: 'apri-finestra', finestra: 'settings' }],
  ['stato jetson', { tipo: 'apri-finestra', finestra: 'diagnostics' }],
  ['telemetria', { tipo: 'apri-finestra', finestra: 'diagnostics' }],

  // Chiusura
  ['chiudi tutto', { tipo: 'chiudi-tutto' }],
  ['chiudi', { tipo: 'chiudi-tutto' }],
  ['chiudi il piazzale', { tipo: 'chiudi-telecamera', telecamera: 1 }],
  ['chiudi 2', { tipo: 'chiudi-telecamera', telecamera: 2 }],
  ['chiudi gli eventi', { tipo: 'chiudi-finestra', finestra: 'events' }],
  ['chiudi tutte le finestre', { tipo: 'chiudi-tutto' }],
  ['chiudi il cancello', { tipo: 'risposta' }],

  // Azioni sugli attuatori
  ['accendi i fari', { tipo: 'azione', azione: 'faro' }],
  ['accendi la luce del piazzale', { tipo: 'azione', azione: 'faro' }],
  ['manda l\'avviso', { tipo: 'azione', azione: 'voce' }],
  ['dissuasione', { tipo: 'azione', azione: 'voce' }],
  ['apri il cancello', { tipo: 'azione', azione: 'cancello', conferma: true }],

  // Altro
  ['identikit', { tipo: 'identikit' }],
  ['ultima scheda', { tipo: 'identikit' }],
  ['blocca', { tipo: 'blocca' }],
  ['aiuto', { tipo: 'aiuto' }],
  ['cosa sai fare?', { tipo: 'aiuto' }],
  ['sei armato?', { tipo: 'stato' }],
  ['ciao orin', { tipo: 'saluto' }],
  ['', { tipo: 'vuoto' }],

  // Frasi non capite: suggerimento o invito all'aiuto
  ['magazzzzino', { tipo: 'apri-telecamera', telecamera: 2 }],
  ['tarhge', { tipo: 'sconosciuto', suggerimento: 'targhe' }],
  ['fai il caffè', { tipo: 'sconosciuto', suggerimento: null }]
];

let falliti = 0;
for (const [frase, atteso] of CASI) {
  const r = interpreta(frase);
  const ok = Object.entries(atteso).every(([k, v]) => r[k] === v);
  if (!ok) {
    falliti++;
    console.log(`FALLITO  "${frase}"\n   atteso:  ${JSON.stringify(atteso)}\n   ottenuto: ${JSON.stringify(r)}`);
  }
}

const conferme = [['sì', true], ['si', true], ['ok confermo', true], ['no', false], ['apri il piazzale', false]];
for (const [frase, atteso] of conferme) {
  if (eConferma(frase) !== atteso) {
    falliti++;
    console.log(`FALLITO conferma "${frase}": atteso ${atteso}`);
  }
}

const totale = CASI.length + conferme.length;
console.log(`\n${totale - falliti}/${totale} superati`);
process.exit(falliti ? 1 : 0);
