#!/usr/bin/env python3
"""
CONF-LAVORO SENTINEL AI — Generatore Dossier Tecnico di Presentazione
Genera un PDF multipagina (A4) ad altissima risoluzione grafica con Playwright.
Salva direttamente su Desktop del sistema.
"""

import os
import base64
from playwright.sync_api import sync_playwright
import pypdf

# Percorsi
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DESKTOP_DIR = os.path.expanduser("~/Desktop")
OUTPUT_PDF = os.path.join(DESKTOP_DIR, "CONF_LAVORO_SENTINEL_AI_Presentazione_Tecnica.pdf")
IMG_DIR = os.path.join(WORKSPACE_DIR, "dashboard", "assets", "img")

def get_base64_svg(filename):
    path = os.path.join(IMG_DIR, filename)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""

logo_oro_b64 = get_base64_svg("conflavoro-ai-oro.svg")
logo_viola_chiaro_b64 = get_base64_svg("conflavoro-ai-viola-su-chiaro.svg")
icon_oro_b64 = get_base64_svg("conflavoro-ai-icon-oro.svg")

html_content = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>CONF-LAVORO SENTINEL AI — Dossier Tecnico di Presentazione</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

  @page {{
    size: A4 portrait;
    margin: 0;
  }}

  * {{
    box-sizing: border-box;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}

  body {{
    margin: 0;
    padding: 0;
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #1e293b;
    background-color: #ffffff;
    font-size: 9pt;
    line-height: 1.45;
  }}

  .page {{
    width: 210mm;
    height: 297mm;
    max-height: 297mm;
    position: relative;
    page-break-after: always;
    page-break-inside: avoid;
    overflow: hidden;
    padding: 14mm 16mm 14mm 16mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}

  .page-last {{
    page-break-after: avoid;
  }}

  /* Page 1: Dark Executive Hero */
  .page-cover {{
    background: radial-gradient(circle at 85% 15%, #1e293b 0%, #0b132b 55%, #050814 100%);
    color: #f8fafc;
    padding: 18mm 18mm 16mm 18mm;
  }}

  /* Typography & Utilities */
  .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
  .text-gold {{ color: #d4af37; }}
  .text-emerald {{ color: #10b981; }}
  .text-cyan {{ color: #06b6d4; }}
  .text-muted {{ color: #64748b; }}
  .text-white {{ color: #ffffff; }}

  /* Cover Components */
  .cover-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(212, 175, 55, 0.25);
    padding-bottom: 12px;
  }}

  .cover-badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(212, 175, 55, 0.12);
    border: 1px solid rgba(212, 175, 55, 0.4);
    color: #ffd700;
    font-size: 7.5pt;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 4px 10px;
    border-radius: 999px;
    text-transform: uppercase;
  }}

  .cover-title-area {{
    margin-top: 25px;
    margin-bottom: 20px;
  }}

  .cover-pretitle {{
    font-size: 8.5pt;
    font-weight: 700;
    color: #94a3b8;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    margin-bottom: 8px;
  }}

  .cover-title {{
    font-size: 28pt;
    font-weight: 800;
    letter-spacing: -0.5px;
    line-height: 1.1;
    color: #ffffff;
    margin: 0 0 10px 0;
  }}

  .cover-title span {{
    background: linear-gradient(135deg, #ffd700 0%, #d4af37 60%, #fff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}

  .cover-subtitle {{
    font-size: 11pt;
    font-weight: 400;
    color: #cbd5e1;
    line-height: 1.4;
    max-width: 90%;
  }}

  .cover-metrics {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin: 20px 0;
  }}

  .metric-card {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 12px 10px;
    text-align: center;
  }}

  .metric-value {{
    font-size: 17pt;
    font-weight: 800;
    line-height: 1;
    margin-bottom: 4px;
    color: #ffd700;
    font-family: 'JetBrains Mono', monospace;
  }}

  .metric-label {{
    font-size: 7pt;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}

  .cover-meta-box {{
    background: rgba(15, 23, 42, 0.7);
    border: 1px solid rgba(212, 175, 55, 0.2);
    border-radius: 10px;
    padding: 14px 18px;
    margin-top: 15px;
  }}

  .cover-meta-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }}

  .meta-item-label {{
    font-size: 6.8pt;
    font-weight: 700;
    color: #d4af37;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 2px;
  }}

  .meta-item-val {{
    font-size: 8.8pt;
    font-weight: 600;
    color: #f1f5f9;
  }}

  .meta-item-sub {{
    font-size: 7.2pt;
    color: #94a3b8;
  }}

  .cover-footer {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    padding-top: 12px;
    font-size: 7pt;
    color: #64748b;
  }}

  /* Inner Pages (Light Clean Architectural Layout) */
  .page-inner {{
    background: #ffffff;
  }}

  .page-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1.5px solid #0f172a;
    padding-bottom: 8px;
    margin-bottom: 12px;
  }}

  .page-header-left {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  .page-chapter {{
    font-size: 7.5pt;
    font-weight: 800;
    letter-spacing: 1.2px;
    color: #b45309;
    text-transform: uppercase;
  }}

  .page-title {{
    font-size: 12.5pt;
    font-weight: 800;
    color: #0f172a;
    margin: 0;
  }}

  .page-header-right {{
    text-align: right;
  }}

  .page-doc-tag {{
    font-size: 7pt;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
  }}

  .page-footer {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid #e2e8f0;
    padding-top: 8px;
    margin-top: 10px;
    font-size: 7pt;
    color: #94a3b8;
  }}

  .page-num {{
    font-weight: 700;
    color: #0f172a;
    background: #f1f5f9;
    padding: 2px 7px;
    border-radius: 4px;
  }}

  /* Content Cards & Sections */
  .section-title {{
    font-size: 9.5pt;
    font-weight: 800;
    color: #0f172a;
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 0 0 7px 0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}

  .section-title::before {{
    content: "";
    display: inline-block;
    width: 3.5px;
    height: 12px;
    background: #d4af37;
    border-radius: 2px;
  }}

  .card-grid-2 {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }}

  .card-grid-3 {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }}

  .card {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 9px 11px;
  }}

  .card-highlight {{
    background: #fdfbf4;
    border: 1px solid #fde68a;
  }}

  .card-primary {{
    background: #0f172a;
    color: #ffffff;
    border: 1px solid #1e293b;
  }}

  .card-title {{
    font-size: 8.3pt;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 3px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}

  .card-primary .card-title {{
    color: #ffd700;
  }}

  .badge-small {{
    font-size: 6.5pt;
    font-weight: 700;
    padding: 1.5px 5px;
    border-radius: 3px;
    text-transform: uppercase;
  }}

  .badge-gold {{ background: #fef3c7; color: #92400e; }}
  .badge-blue {{ background: #e0f2fe; color: #0369a1; }}
  .badge-green {{ background: #dcfce7; color: #166534; }}
  .badge-purple {{ background: #f3e8ff; color: #6b21a8; }}

  /* Tables */
  .tech-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 7.5pt;
    margin: 6px 0 10px 0;
  }}

  .tech-table th {{
    background: #0f172a;
    color: #ffffff;
    text-align: left;
    padding: 5px 8px;
    font-weight: 700;
    font-size: 7pt;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}

  .tech-table td {{
    padding: 5px 8px;
    border-bottom: 1px solid #e2e8f0;
    color: #334155;
  }}

  .tech-table tr:nth-child(even) td {{
    background: #f8fafc;
  }}

  .tech-table tr:last-child td {{
    border-bottom: 1.5px solid #cbd5e1;
  }}

  .tech-table .col-highlight {{
    font-weight: 700;
    color: #0f172a;
  }}

  /* Diagram Box */
  .diagram-flow {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 10px 8px;
    margin: 8px 0;
  }}

  .diagram-node {{
    background: #ffffff;
    border: 1px solid #94a3b8;
    border-radius: 5px;
    padding: 6px 8px;
    text-align: center;
    width: 18%;
  }}

  .diagram-node-primary {{
    background: #0f172a;
    border-color: #ffd700;
    color: #ffffff;
  }}

  .node-title {{
    font-size: 7.2pt;
    font-weight: 800;
    line-height: 1.1;
    margin-bottom: 2px;
  }}

  .node-sub {{
    font-size: 6pt;
    color: #64748b;
  }}

  .diagram-node-primary .node-sub {{
    color: #cbd5e1;
  }}

  .diagram-arrow {{
    color: #b45309;
    font-size: 11pt;
    font-weight: 800;
  }}

  /* Callout Quote */
  .callout {{
    border-left: 3px solid #d4af37;
    background: #fefce8;
    padding: 6px 10px;
    border-radius: 0 4px 4px 0;
    font-size: 7.6pt;
    color: #713f12;
    margin: 6px 0;
  }}

  /* Signatures */
  .sign-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 20px;
    margin-top: 15px;
    padding-top: 12px;
    border-top: 1.5px dashed #cbd5e1;
  }}

  .sign-box {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 10px;
  }}

  .sign-role {{
    font-size: 6.8pt;
    font-weight: 700;
    color: #94a3b8;
    text-transform: uppercase;
    margin-bottom: 3px;
  }}

  .sign-name {{
    font-size: 9pt;
    font-weight: 800;
    color: #0f172a;
  }}

  .sign-org {{
    font-size: 7pt;
    color: #475569;
  }}

  .sign-seal {{
    margin-top: 15px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 6.5pt;
    color: #94a3b8;
    border-top: 1px solid #e2e8f0;
    padding-top: 6px;
  }}
</style>
</head>
<body>

  <!-- ══════════════════════════════════════════════════════════════════════════
       PAGINA 1: COPERTINA ESECUTIVA (DARK LUXURY EXECUTIVE DESIGN)
       ══════════════════════════════════════════════════════════════════════════ -->
  <div class="page page-cover">
    
    <div class="cover-header">
      <div>
        <img src="data:image/svg+xml;base64,{logo_oro_b64}" alt="Conflavoro AI" style="height: 38px;">
      </div>
      <div class="cover-badge">
        <span>●</span> Dossier Ufficiale di Prodotto
      </div>
    </div>

    <div class="cover-title-area">
      <div class="cover-pretitle font-mono">CONF-LAVORO SENTINEL AI // PERIMETER & DOMOTICS SYSTEM</div>
      <h1 class="cover-title">Piattaforma Cibernetica di <span>Videosorveglianza IA</span> & Domotica Industriale</h1>
      <p class="cover-subtitle">
        Architettura edge-native on-premise per la protezione perimetrale attiva, dissuasione acustica in tempo reale, 
        riconoscimento targhe LPR ed automazione integrata dei varchi aziendali.
      </p>
    </div>

    <div class="cover-metrics">
      <div class="metric-card">
        <div class="metric-value font-mono">33.9 ms</div>
        <div class="metric-label">Inferenza Neurale TensorRT</div>
      </div>
      <div class="metric-card">
        <div class="metric-value font-mono">&lt; 300 ms</div>
        <div class="metric-label">Reattività Dissuasione RTP</div>
      </div>
      <div class="metric-card">
        <div class="metric-value font-mono">100%</div>
        <div class="metric-label">On-Premise (Zero Cloud)</div>
      </div>
      <div class="metric-card">
        <div class="metric-value font-mono">4K UHD</div>
        <div class="metric-label">Risoluzione & Ottica Forense</div>
      </div>
    </div>

    <div class="cover-meta-box">
      <div class="cover-meta-grid">
        <div>
          <div class="meta-item-label">Destinatario Esecutivo</div>
          <div class="meta-item-val">Dott. Roberto Capobianco</div>
          <div class="meta-item-sub">Presidente Nazionale Conflavoro PMI</div>
        </div>
        <div>
          <div class="meta-item-label">Responsabile Sviluppo & Architettura</div>
          <div class="meta-item-val">Raffaele Di Tullo</div>
          <div class="meta-item-sub">Divisione Tecnologica & IA Conflavoro</div>
        </div>
        <div>
          <div class="meta-item-label">Classificazione Documento</div>
          <div class="meta-item-val">Specifiche Tecniche & Funzionali v2.4</div>
          <div class="meta-item-sub">Riservato ad uso direzionale e commerciale</div>
        </div>
        <div>
          <div class="meta-item-label">Piattaforma di Riferimento</div>
          <div class="meta-item-val">NVIDIA Jetson Orin Nano Super Dev Kit</div>
          <div class="meta-item-sub">Accelerazione Hardware TensorRT & Modbus TCP</div>
        </div>
      </div>
    </div>

    <div class="cover-footer font-mono">
      <div>CONFIDENZIALE © 2026 CONFLAVORO PMI — TUTTI I DIRITTI RISERVATI</div>
      <div>OTTOBRE 2026 // RELEASE STABILE</div>
    </div>

  </div>

  <!-- ══════════════════════════════════════════════════════════════════════════
       PAGINA 2: VISIONE STRATEGICA & ARCHITETTURA HARDWARE EDGE
       ══════════════════════════════════════════════════════════════════════════ -->
  <div class="page page-inner">
    
    <div>
      <div class="page-header">
        <div class="page-header-left">
          <img src="data:image/svg+xml;base64,{icon_oro_b64}" alt="Icon" style="height: 22px;">
          <div>
            <div class="page-chapter">Sezione 01 // Visione Strategica & Hardware</div>
            <h2 class="page-title">Il Salto di Paradigma: Da TVCC Passivo ad Agente Attivo</h2>
          </div>
        </div>
        <div class="page-header-right font-mono">
          <div class="page-doc-tag">SENTINEL AI // ARCHITETTURA</div>
          <div style="font-size: 6.5pt; color: #94a3b8;">SISTEMA DI PRODUZIONE JETSON</div>
        </div>
      </div>

      <div class="section-title">1.1 Il Valore Imprenditoriale per le PMI</div>
      <p style="margin: 0 0 8px 0; text-align: justify;">
        I tradizionali impianti di videosorveglianza aziendali presentano due limiti strutturali: sono <strong>puramente passivi</strong> 
        (registrano l'evento solo per consultarlo a danno già compiuto) oppure <strong>dipendono da cloud proprietari terzi</strong> 
        (con costi di canone mensile ricorrente, saturazione della banda internet e rischi gravi di non conformità GDPR).
        <strong>CONF-LAVORO SENTINEL AI</strong> capovolge questo paradigma: è un sistema <strong>Edge-First</strong> che elabora 
        tutti i flussi video localmente tramite reti neurali su silicio dedicato, rileva e classifica minacce in tempo reale e reagisce 
        in frazioni di secondo attivando contromisure domotiche ed acustiche prima che l'intrusione si compia.
      </p>

      <div class="callout">
        <strong>Vantaggio Competitivo Fondamentale:</strong> Nessun flusso video o metadato biometrico esce dalla rete locale aziendale. 
        Zero canoni mensili per server cloud, reattività garantita anche in totale assenza di connettività internet esterna e 
        totale conformità allo Statuto dei Lavoratori (Art. 4 L. 300/1970) e al Regolamento Europeo GDPR (Reg. UE 2016/679).
      </div>

      <div class="section-title" style="margin-top: 10px;">1.2 Topologia & Flusso Dati di Produzione</div>
      <div class="diagram-flow">
        <div class="diagram-node">
          <div class="node-title">Telecamere 4K</div>
          <div class="node-sub">3x Reolink Ottica UHD<br>Flusso RTSP Low-Latency</div>
        </div>
        <div class="diagram-arrow">➔</div>
        <div class="diagram-node diagram-node-primary">
          <div class="node-title" style="color:#ffd700;">Jetson Orin Nano</div>
          <div class="node-sub">NVDEC + TensorRT IA<br>Inferenza in 33.9 ms</div>
        </div>
        <div class="diagram-arrow">➔</div>
        <div class="diagram-node">
          <div class="node-title">Orchestratore</div>
          <div class="node-sub">Algoritmi Anti-Fantasma<br>Filtri Traiettoria & JEV</div>
        </div>
        <div class="diagram-arrow">➔</div>
        <div class="diagram-node">
          <div class="node-title">Attuazione Relè</div>
          <div class="node-sub">Modbus TCP (.30:4196)<br>Cancelli 3s / Fari 220V</div>
        </div>
        <div class="diagram-arrow">➔</div>
        <div class="diagram-node">
          <div class="node-title">Deterrenza Fanvil</div>
          <div class="node-sub">Multicast RTP (.31)<br>Voce Istantanea &lt;300ms</div>
        </div>
      </div>

      <div class="section-title" style="margin-top: 10px;">1.3 Distinta Base Hardware Certificata (BOM Industriale)</div>
      <table class="tech-table">
        <thead>
          <tr>
            <th>Dispositivo Hardware</th>
            <th>Indirizzo / Bus</th>
            <th>Protocollo</th>
            <th>Specifiche & Ruolo Operativo</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="col-highlight">NVIDIA Jetson Orin Nano Super (8GB)</td>
            <td class="font-mono">192.168.1.10</td>
            <td>TensorRT / Docker</td>
            <td>Supercomputer Edge 40 TOPS INT8, GPU Ampere 1024-core. Gestisce Frigate 0.17.2, modelli IA e broker MQTT.</td>
          </tr>
          <tr>
            <td class="col-highlight">3x Telecamere Reolink RLC-811A 4K</td>
            <td class="font-mono">192.168.1.20-22</td>
            <td>RTSP / HTTP-FLV</td>
            <td>Sensori ottici 8 Megapixel (3840x2160), zoom ottico 5X, visione notturna avanzata e floodlight LED integrati.</td>
          </tr>
          <tr>
            <td class="col-highlight">Scheda Relè Waveshare Modbus TCP</td>
            <td class="font-mono">192.168.1.30:4196</td>
            <td>Modbus TCP (Funz. 0x05)</td>
            <td>Controllo carichi industriali: Ch 1 Faretto 220V (30s con watchdog), Ch 2 Impulso Cancello Carraio (3s).</td>
          </tr>
          <tr>
            <td class="col-highlight">Altoparlante IP Fanvil A233 (30W)</td>
            <td class="font-mono">192.168.1.31</td>
            <td>Multicast RTP :5004</td>
            <td>Diffusore acustico da esterno IP65. Codec G.711 µ-law mono ad emissione immediata senza handshake SIP.</td>
          </tr>
          <tr>
            <td class="col-highlight">Storage NAS Ugreen Ridondato</td>
            <td class="font-mono">192.168.1.11</td>
            <td>SMB / CIFS</td>
            <td>Unità di archiviazione centrale (share <code>sentinel-eventi</code>) per video 4K e snap forensi criptati.</td>
          </tr>
        </tbody>
      </table>

      <div class="card-grid-2" style="margin-top: 4px;">
        <div class="card">
          <div class="card-title"><span>Efficienza Energetica Edge</span> <span class="badge-small badge-green">&lt; 15 Watt</span></div>
          <p style="margin: 0; font-size: 7.2pt; color: #475569;">
            L'intero nodo computazionale consuma meno di una lampadina LED. Consente l'alimentazione continuativa anche 
            sotto gruppo di continuità (UPS) compatto garantendo ore di autonomia in caso di blackout o sabotaggio elettrico.
          </p>
        </div>
        <div class="card">
          <div class="card-title"><span>Isolamento Galvanico Modbus</span> <span class="badge-small badge-gold">Sicurezza CE</span></div>
          <p style="margin: 0; font-size: 7.2pt; color: #475569;">
            La scheda relè Waveshare separa galvanicamente i circuiti di potenza a 220V dalla logica di rete, proteggendo il server Jetson 
            da sovratensioni, fulmini o ritorni di corrente derivanti dai motori dei cancelli o dai fari.
          </p>
        </div>
      </div>
    </div>

    <div class="page-footer font-mono">
      <div>CONF-LAVORO SENTINEL AI // DOSSIER TECNICO DI PRESENTAZIONE</div>
      <div>PAGINA <span class="page-num">02</span> / 05</div>
    </div>

  </div>

  <!-- ══════════════════════════════════════════════════════════════════════════
       PAGINA 3: MOTORE PERCETTIVO IA & FILTRI ANTI-FANTASMA
       ══════════════════════════════════════════════════════════════════════════ -->
  <div class="page page-inner">
    
    <div>
      <div class="page-header">
        <div class="page-header-left">
          <img src="data:image/svg+xml;base64,{icon_oro_b64}" alt="Icon" style="height: 22px;">
          <div>
            <div class="page-chapter">Sezione 02 // Cervello Neurale & Precisione</div>
            <h2 class="page-title">Motore Percettivo IA & Filtri Anti-Fantasma</h2>
          </div>
        </div>
        <div class="page-header-right font-mono">
          <div class="page-doc-tag">INFERENZA IN TEMPO REALE</div>
          <div style="font-size: 6.5pt; color: #94a3b8;">TENSORRT ENGINE V0.17.2</div>
        </div>
      </div>

      <div class="section-title">2.1 Pipeline Neurale ad Altissima Velocità (33.9 ms)</div>
      <p style="margin: 0 0 7px 0; text-align: justify;">
        Il cuore del rilevamento visivo sfrutta acceleratori tensoriali dedicati sulla GPU NVIDIA Jetson. 
        Mentre i software commerciali tradizionali richiedono dai 400 ai 1200 millisecondi per analizzare un fotogramma su CPU, 
        il motore di Sentinel AI esegue l'inferenza in soli <strong>33.9 millisecondi</strong> a 10 frame al secondo per ciascuna delle 3 telecamere, 
        lasciando oltre il 50% di margine di calcolo libero sulla GPU per compiti biometrici e domotici simultanei.
      </p>

      <div class="section-title" style="margin-top: 8px;">2.2 Algoritmi Proprietari Anti-Fantasma (Zero Falsi Allarmi)</div>
      <p style="margin: 0 0 6px 0;">
        Il limite storico degli allarmi è il falso positivo (animali, rami al vento, pioggia, fari). 
        Sentinel AI integra un'architettura decisionale multistadio che filtra le evidenze prima di azionare audio e relè:
      </p>

      <div class="card-grid-3">
        <div class="card card-highlight">
          <div class="card-title"><span>Filtro Anatomico H/W</span> <span class="badge-small badge-gold">Ratio &ge; 1.20</span></div>
          <p style="margin: 0; font-size: 7.1pt; color: #475569;">
            Analizza il rapporto proporzionale altezza/larghezza del bounding box. Un essere umano eretto ha un ratio tipico di 1.8 &divide; 2.8. 
            Scarta automaticamente animali domestici, scatoloni trascinati, ombre a terra e riflessi luminosi sull'asfalto bagnato.
          </p>
        </div>
        <div class="card card-highlight">
          <div class="card-title"><span>Traiettoria Dinamica</span> <span class="badge-small badge-blue">Distanza &gt; 2.5%</span></div>
          <p style="margin: 0; font-size: 7.1pt; color: #475569;">
            Traccia in RAM il centroide euclideo <code>[cx, cy]</code> dell'oggetto. Se la sagoma è statica o compie micro-oscillazioni 
            ripetute (es. telone o ramo che sventola), il trigger audio e l'allarme vengono bloccati prima di qualsiasi attuazione.
          </p>
        </div>
        <div class="card card-highlight">
          <div class="card-title"><span>JEV Adaptive Decider</span> <span class="badge-small badge-purple">Multi-Profilo</span></div>
          <p style="margin: 0; font-size: 7.1pt; color: #475569;">
            Profili geometrici adattivi per ciascuna area specifica: 
            <strong>Piazzale</strong> (soppressione ombre auto parcheggiate), <strong>Magazzino</strong> (filtro muletti e bancali), 
            <strong>Corridoio</strong> (massima sensibilità e reattività sui varchi di accesso).
          </p>
        </div>
      </div>

      <div class="section-title" style="margin-top: 10px;">2.3 Modulo LPR: Riconoscimento Targhe & Varchi Carrai</div>
      <div class="card" style="margin-bottom: 7px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px;">
          <div class="card-title" style="margin: 0;">Riconoscimento Automatico Ottico Targhe (LPR) & Whitelist Veicoli</div>
          <span class="badge-small badge-green">Modello YOLOv9 + OCR Vettoriale</span>
        </div>
        <p style="margin: 0; font-size: 7.2pt; color: #334155; line-height: 1.4;">
          Sulla telecamera del varco carrabile, un sottomodello specializzato si attiva istantaneamente quando un veicolo entra nella zona focale. 
          Estrae la combinazione alfanumerica della targa e la confronta con il registro <strong>Whitelist autorizzati</strong> in memoria locale. 
          Se il veicolo è censito (dipendenti, fornitori abituali, dirigenza), il sistema invia in autonomia l'impulso di apertura al cancello 
          senza richiedere l'uso di telecomandi fisici o badge.
        </p>
      </div>

      <div class="section-title" style="margin-top: 7px;">2.4 Generatore di Identikit Forense Istantaneo</div>
      <div class="card-primary" style="padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px;">
          <div style="font-size: 8.2pt; font-weight: 800; color: #ffd700;">Scheda Evidenza Forense Digitale (Identikit Profiler)</div>
          <span class="badge-small" style="background: rgba(212,175,55,0.2); color: #ffd700; border: 1px solid #ffd700;">NORMATIVA GIUDIZIARIA</span>
        </div>
        <p style="margin: 0; font-size: 7.1pt; color: #e2e8f0; line-height: 1.35;">
          Ad ogni evento confermato, Sentinel AI genera istantaneamente un file forense conforme 
          (<code>identikit_&#123;cam&#125;_&#123;id&#125;.json</code>) con marcatura temporale millesimale, coordinate d'inquadratura, 
          grado di confidenza IA, proporzioni stimate e fermo-immagine ad altissima risoluzione ritagliato sul soggetto. 
          Il fascicolo è immediatamente condivisibile con le forze dell'ordine o gli istituti di vigilanza privata convenzionati.
        </p>
      </div>

      <div class="section-title" style="margin-top: 7px;">2.5 Catena Decisionale a Tre Livelli di Rilevamento</div>
      <div class="card-grid-3">
        <div class="card" style="border-left: 3px solid #0284c7;">
          <div style="font-weight: 800; font-size: 7.2pt; color: #0284c7; margin-bottom: 2px;">LIVELLO 1: PRE-ALLERTA</div>
          <p style="margin: 0; font-size: 6.8pt; color: #475569;">
            Tracciamento sagoma nel piazzale esterno. Calcolo del vettore velocità e classificazione silhouette. Nessun disturbo sonoro se in transito periferico.
          </p>
        </div>
        <div class="card" style="border-left: 3px solid #b45309;">
          <div style="font-weight: 800; font-size: 7.2pt; color: #b45309; margin-bottom: 2px;">LIVELLO 2: VARCO CRITICO</div>
          <p style="margin: 0; font-size: 6.8pt; color: #475569;">
            Avvicinamento al cancello carraio o portone di carico. Scatto lettura targa LPR e verifica whitelist. Se non autorizzato: pre-caricamento audio.
          </p>
        </div>
        <div class="card" style="border-left: 3px solid #dc2626;">
          <div style="font-weight: 800; font-size: 7.2pt; color: #dc2626; margin-bottom: 2px;">LIVELLO 3: EFFRAZIONE IMMINENTE</div>
          <p style="margin: 0; font-size: 6.8pt; color: #475569;">
            Ingresso in area protetta a fabbricato chiuso. Trigger istantaneo altoparlante Fanvil (&lt;300ms) + accensione fari 220V + salvataggio clip MP4 su NAS.
          </p>
        </div>
      </div>

    </div>

    <div class="page-footer font-mono">
      <div>CONF-LAVORO SENTINEL AI // DOSSIER TECNICO DI PRESENTAZIONE</div>
      <div>PAGINA <span class="page-num">03</span> / 05</div>
    </div>

  </div>

  <!-- ══════════════════════════════════════════════════════════════════════════
       PAGINA 4: DOMOTICA, DISSUASIONE ATTIVA & MODULO ORIN
       ══════════════════════════════════════════════════════════════════════════ -->
  <div class="page page-inner">
    
    <div>
      <div class="page-header">
        <div class="page-header-left">
          <img src="data:image/svg+xml;base64,{icon_oro_b64}" alt="Icon" style="height: 22px;">
          <div>
            <div class="page-chapter">Sezione 03 // Domotica & Deterrenza Sonora</div>
            <h2 class="page-title">Automazione Domotica & Cervello Multimodale</h2>
          </div>
        </div>
        <div class="page-header-right font-mono">
          <div class="page-doc-tag">ATTUAZIONE & INTERAZIONE</div>
          <div style="font-size: 6.5pt; color: #94a3b8;">WAVESHARE & FANVIL PROTOCOLS</div>
        </div>
      </div>

      <div class="section-title">3.1 Automazioni Domotiche di Sicurezza (Relè Modbus TCP)</div>
      <p style="margin: 0 0 7px 0; text-align: justify;">
        Sentinel AI non si limita a osservare: interagisce fisicamente con l'edificio tramite la scheda relè Waveshare industriale. 
        Tutti i comandi viaggiano su socket TCP dedicato (porta 4196) con gestione multi-thread asincrona che non rallenta mai il motore video:
      </p>

      <div class="card-grid-2">
        <div class="card">
          <div class="card-title">
            <span>Apertura Intelligente Cancelli (Ch 2)</span>
            <span class="badge-small badge-green">Impulso 3s</span>
          </div>
          <p style="margin: 0 0 4px 0; font-size: 7.1pt; color: #475569;">
            Il Canale 2 del relè Modbus invia un contatto pulito temporizzato di 3 secondi al quadro della motorizzazione cancello. 
            Viene innescato automaticamente da targa riconosciuta in Whitelist, riconoscimento facciale VIP, 
            oppure manualmente con un tocco dal dock operativo della plancia web.
          </p>
          <div style="font-size: 6.7pt; color: #0284c7; font-weight: 600;">Interblocco software anti-doppio-impulso attivo</div>
        </div>

        <div class="card">
          <div class="card-title">
            <span>Illuminazione Tattica Piazzale (Ch 1)</span>
            <span class="badge-small badge-gold">Faro 220V // 30s</span>
          </div>
          <p style="margin: 0 0 4px 0; font-size: 7.1pt; color: #475569;">
            Al rilevamento di un'intrusione perimetrale notturna, il Canale 1 accende istantaneamente i fari a 220V ad alta potenza. 
            Un algoritmo <em>Watchdog Anti-Sfarfallio</em> estende dinamicamente il tempo di accensione qualora l'intruso rimanga nell'area, 
            evitando spegnimenti prematuri o dannosi scatti a raffica del relè.
          </p>
          <div style="font-size: 6.7pt; color: #b45309; font-weight: 600;">Prolungamento timer automatico su permanenza</div>
        </div>
      </div>

      <div class="section-title" style="margin-top: 10px;">3.2 Dissuasione Vocale Sprint su Altoparlante Fanvil A233</div>
      <div class="card card-highlight">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <div class="card-title" style="margin: 0;">Dissuasione Acustica Immediata in Multicast RTP (&lt; 300 ms)</div>
          <span class="badge-small badge-purple">Canale 239.255.1.1:5004</span>
        </div>
        <p style="margin: 0 0 5px 0; font-size: 7.2pt; color: #334155; line-height: 1.4;">
          Il diffusore sonoro IP Fanvil da 30 Watt riceve lo stream audio via <strong>Multicast RTP</strong> (codec pcm_mulaw 8kHz). 
          A differenza dei vecchi sistemi SIP o HTTP con lunghe negoziazioni, l'emissione parte in <strong>meno di 300 millisecondi</strong>. 
          Il messaggio di dissuasione sprint dura appena <strong>2.1 secondi</strong> (<em>"Alt! Area videosorvegliata. Allontanarsi immediatamente!"</em>), 
          inducendo la fuga istantanea prima che l'intruso tenti l'effrazione di porte o finestre.
        </p>
        <div style="display: flex; gap: 12px; font-size: 6.8pt; color: #64748b; border-top: 1px solid #fde68a; padding-top: 4px;">
          <span>• <strong>Cooldown Globale:</strong> 20 secondi anti-eco</span>
          <span>• <strong>Toni di servizio Fanvil:</strong> soppressi (Zero bip di disturbo)</span>
          <span>• <strong>Pre-roll:</strong> 150 ms anti-troncamento</span>
        </div>
      </div>

      <div class="section-title" style="margin-top: 10px;">3.3 Modulo "ORIN Brain": Visione Multimodale & Accoglienza VIP</div>
      <div class="card" style="background: linear-gradient(135deg, #f8fafc 0%, #eff6ff 100%); border-color: #bfdbfe;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px;">
          <div class="card-title" style="color: #1e3a8a; margin: 0;">Intelligenza Contestuale Relazionale & Memoria Visiva</div>
          <span class="badge-small" style="background: #dbeafe; color: #1e40af;">Riconoscimento Presidente</span>
        </div>
        <p style="margin: 0 0 5px 0; font-size: 7.2pt; color: #334155; line-height: 1.35;">
          Oltre alla deterrenza, Sentinel AI include il modulo <strong>ORIN Brain</strong> basato su modelli visivi multimodali di ultima generazione. 
          Il sistema ha in memoria visiva permanente le figure chiave dell'organizzazione (incluso il <strong>Dott. Roberto Capobianco</strong>). 
          Quando il Presidente giunge al varco aziendale, il sistema lo riconosce visivamente e compie contemporaneamente due azioni:
        </p>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 4px;">
          <div style="background: #ffffff; padding: 6px 9px; border-radius: 4px; border: 1px solid #cbd5e1;">
            <div style="font-weight: 700; color: #1e3a8a; font-size: 7pt;">Apertura Varco Direzionale</div>
            <div style="font-size: 6.6pt; color: #64748b;">Invio istantaneo impulso apertura al cancello carraio (Relè 2) senza attese.</div>
          </div>
          <div style="background: #ffffff; padding: 6px 9px; border-radius: 4px; border: 1px solid #cbd5e1;">
            <div style="font-weight: 700; color: #1e3a8a; font-size: 7pt;">Accoglienza Vocale Personalizzata</div>
            <div style="font-size: 6.6pt; color: #64748b;"><em>"Buongiorno Presidente Roberto! È un piacere vederla, cancello in apertura."</em></div>
          </div>
        </div>
      </div>

      <div class="section-title" style="margin-top: 10px;">3.4 Gestione Fail-Safe & Sicurezza di Esercizio</div>
      <div class="card-grid-2">
        <div class="card">
          <div class="card-title"><span>Stato di Riposo Garantito</span> <span class="badge-small badge-green">Normalmente Aperto</span></div>
          <p style="margin: 0; font-size: 6.8pt; color: #475569;">
            In caso di blackout totale o disconnessione accidentale della scheda relè, tutti i contatti tornano istantaneamente in posizione sicura: 
            i fari si spengono e i motori dei cancelli rimangono protetti da azionamenti anomali.
          </p>
        </div>
        <div class="card">
          <div class="card-title"><span>Schedulazione Oraria Automatica</span> <span class="badge-small badge-blue">Giorno / Notte</span></div>
          <p style="margin: 0; font-size: 6.8pt; color: #475569;">
            La dissuasione vocale ad alta potenza si attiva automaticamente solo negli orari di chiusura aziendale (notte, weekend e festivi), 
            mantenendo di giorno la modalità cordiale e la sola apertura varchi per dipendenti e clienti.
          </p>
        </div>
      </div>

    </div>

    <div class="page-footer font-mono">
      <div>CONF-LAVORO SENTINEL AI // DOSSIER TECNICO DI PRESENTAZIONE</div>
      <div>PAGINA <span class="page-num">04</span> / 05</div>
    </div>

  </div>

  <!-- ══════════════════════════════════════════════════════════════════════════
       PAGINA 5: MISSION CONTROL DASHBOARD, BENCHMARK & FIRME
       ══════════════════════════════════════════════════════════════════════════ -->
  <div class="page page-inner page-last">
    
    <div>
      <div class="page-header">
        <div class="page-header-left">
          <img src="data:image/svg+xml;base64,{icon_oro_b64}" alt="Icon" style="height: 22px;">
          <div>
            <div class="page-chapter">Sezione 04 // Piattaforma SOC & Valore d'Impresa</div>
            <h2 class="page-title">Plancia di Comando "Mission Control" & Benchmark</h2>
          </div>
        </div>
        <div class="page-header-right font-mono">
          <div class="page-doc-tag">CRUSCOTTO UNIFICATO</div>
          <div style="font-size: 6.5pt; color: #94a3b8;">LINEAR / VERKADA UI V2.4</div>
        </div>
      </div>

      <div class="section-title">4.1 La Dashboard Operativa Proprietaria (SOC Console)</div>
      <p style="margin: 0 0 7px 0; text-align: justify;">
        L'utente aziendale ed il responsabile della sicurezza dispongono di una console web proprietaria reattiva (sviluppata secondo i pattern 
        di design di Verkada e Linear), accessibile da PC, tablet o smartphone in rete locale o VPN protetta:
      </p>

      <div class="card-grid-3" style="margin-bottom: 7px;">
        <div class="card">
          <div class="card-title"><span>Video Wall 4K Live</span></div>
          <p style="margin: 0; font-size: 7pt; color: #475569;">
            Streaming live sincrono delle telecamere a latenza zero tramite WebRTC e MSE con dock operativo per comandi manuali rapidi.
          </p>
        </div>
        <div class="card">
          <div class="card-title"><span>Registro Evidenze</span></div>
          <p style="margin: 0; font-size: 7pt; color: #475569;">
            Archivio storico perimetrale con filtri per targa, persona o veicolo, visualizzatore istantaneo di clip MP4 e scaricamento identikit forensi.
          </p>
        </div>
        <div class="card">
          <div class="card-title"><span>Telemetria Edge (PIN)</span></div>
          <p style="margin: 0; font-size: 7pt; color: #475569;">
            Area riservata manutentore protetta da PIN: telemetria termica Jetson, frequenze GPU, watchdog MQTT e test singoli relè.
          </p>
        </div>
      </div>

      <div class="section-title" style="margin-top: 7px;">4.2 Benchmark: Sentinel AI vs Sistemi Tradizionali</div>
      <table class="tech-table">
        <thead>
          <tr>
            <th>Caratteristica Funzionale</th>
            <th>TVCC Tradizionale (Dahua/Hikvision)</th>
            <th>Soluzioni Cloud Consumer (Ring/Nest)</th>
            <th style="background:#b45309; color:#fff;">CONF-LAVORO SENTINEL AI</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="col-highlight">Modalità di Protezione</td>
            <td>Passiva (registra e basta)</td>
            <td>Notifica su cellulare con ritardo</td>
            <td class="col-highlight" style="color:#b45309;">Attiva: Dissuasione &lt;300ms + Fari</td>
          </tr>
          <tr>
            <td class="col-highlight">Localizzazione Dati & Privacy</td>
            <td>Archivio NVR spesso vulnerabile</td>
            <td>Video inviati su Cloud esteri (USA/Cina)</td>
            <td class="col-highlight" style="color:#166534;">100% On-Premise (GDPR Compliance)</td>
          </tr>
          <tr>
            <td class="col-highlight">Costi Ricorrenti (Canoni)</td>
            <td>Zero (ma nessun aggiornamento IA)</td>
            <td>Canone mensile fisso per telecamera</td>
            <td class="col-highlight" style="color:#166534;">ZERO CANONI CLOUD OBBLIGATORI</td>
          </tr>
          <tr>
            <td class="col-highlight">Automazione Domotica</td>
            <td>Assente o limitata a uscite NVR grezze</td>
            <td>Non integrabile con cancelli industriali</td>
            <td class="col-highlight" style="color:#b45309;">Modbus TCP Industriale Nativo</td>
          </tr>
          <tr>
            <td class="col-highlight">Accoglienza VIP & LPR</td>
            <td>Non prevista</td>
            <td>Riconoscimento volti limitato a notifica</td>
            <td class="col-highlight" style="color:#b45309;">Apertura Varchi + Voce Saluto Personalizzata</td>
          </tr>
        </tbody>
      </table>

      <div class="section-title" style="margin-top: 7px;">4.3 Opportunità di Business & Scalabilità per le PMI</div>
      <div class="card-grid-2" style="margin-bottom: 8px;">
        <div class="card card-highlight">
          <div class="card-title"><span>Soluzione Pacchettizzata "Plug & Protect"</span></div>
          <p style="margin: 0; font-size: 6.8pt; color: #475569;">
            Il sistema viene pre-configurato in fabbrica su micro-server Jetson. L'installatore deve solo collegare il cavo di rete PoE e l'alimentazione: 
            l'auto-discovery attiva le telecamere, i relè e l'altoparlante in pochi minuti senza complesse configurazioni in loco.
          </p>
        </div>
        <div class="card card-highlight">
          <div class="card-title"><span>Fidelizzazione & Servizi per le Imprese</span></div>
          <p style="margin: 0; font-size: 6.8pt; color: #475569;">
            Conflavoro PMI può offrire la tecnologia alle proprie aziende associate come standard di sicurezza accreditato, 
            generando un canale commerciale ad alta redditività sia sulla vendita dell'hardware che sulla manutenzione evolutiva programmata.
          </p>
        </div>
      </div>

      <div class="sign-grid">
        <div class="sign-box">
          <div class="sign-role">Approvazione & Visione Direzionale</div>
          <div class="sign-name">Dott. Roberto Capobianco</div>
          <div class="sign-org">Presidente Nazionale Conflavoro PMI</div>
          <div class="sign-seal">
            <span>VALIDAZIONE STRATEGICA</span>
            <span>PRESIDENZA NAZIONALE</span>
          </div>
        </div>

        <div class="sign-box">
          <div class="sign-role">Sviluppo Tecnologico & Architettura Sistemi</div>
          <div class="sign-name">Raffaele Di Tullo</div>
          <div class="sign-org">Head of Engineering & AI Solutions</div>
          <div class="sign-seal">
            <span>CERTIFICAZIONE TECNICA</span>
            <span>R&D SENTINEL AI V2.4</span>
          </div>
        </div>
      </div>

    </div>

    <div class="page-footer font-mono">
      <div>CONF-LAVORO SENTINEL AI // DOSSIER TECNICO DI PRESENTAZIONE</div>
      <div>PAGINA <span class="page-num">05</span> / 05</div>
    </div>

  </div>

</body>
</html>
"""

# Scrittura file temporaneo HTML
temp_html = os.path.join(WORKSPACE_DIR, "dossier_temp.html")
with open(temp_html, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"HTML temporaneo generato ({len(html_content)} caratteri). Avvio rendering Playwright...")

# Compilazione PDF con Playwright + Chrome
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    page = browser.new_page()
    page.set_content(html_content, wait_until="networkidle")
    
    # Generazione PDF a pagina intera A4 senza bordi esterni aggiuntivi
    page.pdf(
        path=OUTPUT_PDF,
        format="A4",
        print_background=True,
        prefer_css_page_size=True,
        margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"}
    )
    browser.close()

# Verifica del numero di pagine e dimensioni
if os.path.exists(OUTPUT_PDF):
    reader = pypdf.PdfReader(OUTPUT_PDF)
    print(f"PDF GENERATO CON SUCCESSO!")
    print(f"Percorso: {OUTPUT_PDF}")
    print(f"Numero pagine: {len(reader.pages)}")
    print(f"Dimensione file: {os.path.getsize(OUTPUT_PDF):,} bytes")
else:
    print("ERRORE: PDF non trovato!")

# Pulizia file temporaneo
if os.path.exists(temp_html):
    os.remove(temp_html)
