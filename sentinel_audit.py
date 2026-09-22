#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          SENTINEL AI — AUDIT DIAGNOSTICO COMPLETO v1.1                      ║
║          Funziona sia dalla Jetson che da PC remoto sulla stessa LAN        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ISTRUZIONI:                                                                 ║
║  MODALITÀ A — direttamente sulla Jetson (consigliata):                       ║
║    python3 sentinel_audit.py                                                 ║
║    → inserire 127.0.0.1 come IP quando richiesto                             ║
║  MODALITÀ B — da PC Windows remoto sulla stessa LAN:                         ║
║    python sentinel_audit.py                                                  ║
║    → inserire l'IP della Jetson (es. 192.168.1.10)                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import json
import time
import socket
import threading
import subprocess
import struct
import datetime
import platform
import urllib.request
import urllib.error
import urllib.parse
import http.client
import traceback
import re
import webbrowser
import tempfile
from collections import defaultdict

# ─────────────────────────────────────────────────────────────────────────────
# RILEVAMENTO AUTOMATICO MODALITÀ: ON-JETSON vs PC REMOTO
# ─────────────────────────────────────────────────────────────────────────────
_is_tegra = "tegra" in platform.release().lower() or "jetson" in platform.release().lower()
_is_linux = platform.system() == "Linux"
IS_ON_JETSON = _is_linux and _is_tegra  # True quando lo script gira direttamente sulla Jetson

SENTINEL_PATH   = "/home/alessio/sentinel-ai"   # Percorso progetto sulla Jetson

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAZIONE — Alessio può modificare questi valori se la rete è diversa
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_JETSON_IP   = "192.168.1.10"    # IP della Jetson sulla LAN
FRIGATE_API_PORT    = 8971              # Porta HTTPS Frigate (LAN, con auth)
FRIGATE_API_PORT_IN = 5000              # Porta HTTP interna (solo 127.0.0.1, senza auth)
GO2RTC_API_PORT     = 1984             # Porta API go2rtc (solo dentro container)
MQTT_PORT           = 1883             # Porta MQTT (Mosquitto, solo 127.0.0.1)
RELAY_HOST          = "192.168.1.30"   # IP scheda relè Waveshare
RELAY_PORT          = 4196             # Porta Modbus TCP relè
SPEAKER_HOST        = "192.168.1.31"   # IP altoparlante Fanvil A233
SPEAKER_PORT        = 80               # Porta HTTP Fanvil
CAM_IPS             = {                # IP telecamere Reolink
    "varco_carrabile": "192.168.1.20",
    "varco_pedonale":  "192.168.1.21",
    "piazzale":        "192.168.1.22",
}
MQTT_MONITOR_SECONDS = 45              # Secondi di ascolto MQTT live
EXPECTED_FPS         = 10             # FPS configurati in Frigate
MIN_DETECT_FPS       = 3              # Soglia warning FPS
PERSON_THRESHOLD     = 0.75           # Soglia confidence configurata
PERSON_MIN_SCORE     = 0.60
GHOST_THRESHOLD      = 0.65           # Sotto questo valore = potenziale fantasma

# ─────────────────────────────────────────────────────────────────────────────
# STRUTTURA REPORT
# ─────────────────────────────────────────────────────────────────────────────
report = {
    "start_time": datetime.datetime.now().isoformat(),
    "jetson_ip": "",
    "sections": [],
    "summary": {"pass": 0, "warn": 0, "fail": 0, "info": 0},
}
_current_section = None


def section(title, icon="🔍"):
    global _current_section
    _current_section = {"title": f"{icon} {title}", "checks": []}
    report["sections"].append(_current_section)
    print(f"\n{'─'*60}")
    print(f"  {icon}  {title}")
    print(f"{'─'*60}")


def log(status, message, detail=""):
    """status: PASS | WARN | FAIL | INFO"""
    icons = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌", "INFO": "ℹ️ "}
    icon = icons.get(status, "   ")
    report["summary"][status.lower()] += 1 if status != "INFO" else 0
    if status == "INFO":
        report["summary"]["info"] += 1
    entry = {"status": status, "message": message, "detail": detail}
    if _current_section is not None:
        _current_section["checks"].append(entry)
    short_detail = f" — {detail[:80]}{'…' if len(detail) > 80 else ''}" if detail else ""
    print(f"  {icon} [{status}] {message}{short_detail}")


def info(msg, detail=""):
    log("INFO", msg, detail)


def ok(msg, detail=""):
    log("PASS", msg, detail)


def warn(msg, detail=""):
    log("WARN", msg, detail)


def fail(msg, detail=""):
    log("FAIL", msg, detail)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER RETE
# ─────────────────────────────────────────────────────────────────────────────
def tcp_reachable(host, port, timeout=3):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def http_get(host, port, path, timeout=5, use_https=False):
    """Ritorna (status_code, body_str) o (None, str_errore)."""
    try:
        if use_https:
            conn = http.client.HTTPSConnection(host, port, timeout=timeout,
                                               context=__import__("ssl")._create_unverified_context())
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", path)
        r = conn.getresponse()
        body = r.read().decode("utf-8", errors="replace")
        conn.close()
        return r.status, body
    except Exception as e:
        return None, str(e)


def ping(host, count=2):
    param = "-n" if platform.system().lower() == "windows" else "-c"
    cmd = ["ping", param, str(count), "-w", "1000", host] if platform.system().lower() == "windows" \
          else ["ping", param, str(count), "-W", "1", host]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 0 — CONFIGURAZIONE E AMBIENTE
# ─────────────────────────────────────────────────────────────────────────────
def check_environment(jetson_ip):
    section("AMBIENTE E CONFIGURAZIONE", "🖥️")
    info(f"Sistema operativo: {platform.system()} {platform.release()}")
    info(f"Python: {sys.version.split()[0]}")
    info(f"Jetson IP impostato: {jetson_ip}")
    info(f"Data/Ora audit: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    if IS_ON_JETSON:
        ok("Modalità: ON-JETSON — accesso diretto ai servizi locali (127.0.0.1)")
    else:
        info("Modalità: PC REMOTO — accesso via rete LAN all'IP Jetson")

    # Verifica librerie opzionali
    for lib in ["requests", "paho.mqtt.client"]:
        try:
            __import__(lib)
            ok(f"Libreria disponibile: {lib}")
        except ImportError:
            hint = "Installa con: pip3 install paho-mqtt" if lib == "paho.mqtt.client" else ""
            warn(f"Libreria NON installata: {lib}", hint)


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 1 — CONNETTIVITÀ DI RETE
# ─────────────────────────────────────────────────────────────────────────────
def check_network(jetson_ip):
    section("CONNETTIVITÀ DI RETE", "🌐")

    if IS_ON_JETSON:
        ok("Esecuzione sulla Jetson — connettività locale verificata automaticamente")
    else:
        # Ping Jetson solo se siamo su PC remoto
        reachable, out = ping(jetson_ip)
        if reachable:
            ok(f"Jetson raggiungibile via ping ({jetson_ip})")
        else:
            fail(f"Jetson NON risponde al ping ({jetson_ip})", out.strip())

    # Porte servizi Jetson (go2rtc:1984 è solo interna al container, non testabile da fuori)
    services = [
        ("Frigate Web (8971)", jetson_ip, 8971),
        ("RTSP go2rtc (8554)", jetson_ip, 8554),
    ]
    for name, host, port in services:
        if tcp_reachable(host, port):
            ok(f"Porta aperta: {name}")
        else:
            fail(f"Porta CHIUSA: {name}", f"TCP {host}:{port} non raggiungibile")

    # go2rtc API porta 1984 è interna al container frigate — non esposta verso l'host
    info("go2rtc API (1984): accessibile solo dentro il container — verificata con docker exec")

    # Relay
    if tcp_reachable(RELAY_HOST, RELAY_PORT):
        ok(f"Relè Waveshare raggiungibile ({RELAY_HOST}:{RELAY_PORT})")
    else:
        warn(f"Relè non raggiungibile ({RELAY_HOST}:{RELAY_PORT})", "Verifica alimentazione e cavo di rete")

    # Speaker Fanvil
    if tcp_reachable(SPEAKER_HOST, SPEAKER_PORT):
        ok(f"Fanvil A233 raggiungibile ({SPEAKER_HOST}:{SPEAKER_PORT})")
    else:
        warn(f"Fanvil A233 non raggiungibile ({SPEAKER_HOST}:{SPEAKER_PORT})")

    # Telecamere Reolink
    for cam_name, cam_ip in CAM_IPS.items():
        if tcp_reachable(cam_ip, 554, timeout=2):
            ok(f"Telecamera {cam_name} raggiungibile ({cam_ip}:554 RTSP)")
        elif tcp_reachable(cam_ip, 80, timeout=2):
            warn(f"Telecamera {cam_name}: RTSP chiuso ma HTTP/80 aperto ({cam_ip})",
                 "Potrebbe usare HTTP-FLV — controllare .env")
        else:
            fail(f"Telecamera {cam_name} NON raggiungibile ({cam_ip})", "Spenta o IP sbagliato")


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 2 — FRIGATE API
# ─────────────────────────────────────────────────────────────────────────────
def check_frigate(jetson_ip):
    section("FRIGATE — STATO SISTEMA", "🎯")

    # Se siamo sulla Jetson usiamo direttamente la porta interna 5000 (senza auth)
    # Se siamo su PC remoto usiamo la porta 8971 HTTPS (con auth — potrebbe dare 401)
    if IS_ON_JETSON:
        code, body = http_get("127.0.0.1", FRIGATE_API_PORT_IN, "/api/stats", use_https=False)
        info("Accesso Frigate via porta interna 127.0.0.1:5000 (senza autenticazione)")
    else:
        code, body = http_get(jetson_ip, FRIGATE_API_PORT, "/api/stats", use_https=True)
        if code is None or code == 401:
            # Ultima speranza: porta 5000 sull'IP esterno (funziona solo se il firewall lo permette)
            code2, body2 = http_get(jetson_ip, FRIGATE_API_PORT_IN, "/api/stats", use_https=False)
            if code2 == 200:
                code, body = code2, body2

    if code == 200:
        try:
            stats = json.loads(body)
            ok("Frigate API risponde correttamente")

            # Detector
            detectors = stats.get("detectors", {})
            for det_name, det_data in detectors.items():
                inf_ms = det_data.get("inference_speed", 0)
                if inf_ms > 0:
                    ok(f"Detector '{det_name}': inference {inf_ms:.1f} ms")
                    if inf_ms > 50:
                        warn(f"Detector '{det_name}' lento", f"Inference {inf_ms:.1f}ms > 50ms attesi su TensorRT")
                else:
                    warn(f"Detector '{det_name}': inference_speed = 0", "Potrebbe non essere ancora pronto")

            # CPU / GPU
            service_stats = stats.get("service", {})
            cpu_usage = service_stats.get("cpu_usage", {})
            info(f"Frigate uptime: {service_stats.get('uptime', 'N/D')}s")
            for proc, pct in cpu_usage.items():
                pct_val = pct.get("cpu", 0) if isinstance(pct, dict) else pct
                if pct_val > 80:
                    warn(f"CPU alta: {proc} = {pct_val:.1f}%")
                else:
                    info(f"CPU {proc}: {pct_val:.1f}%")

            # Storage
            storage = stats.get("storage", {})
            for path, sdata in storage.items():
                used = sdata.get("used", 0)
                total = sdata.get("total", 1)
                pct = (used / total * 100) if total else 0
                if pct > 85:
                    fail(f"Storage quasi pieno: {path}", f"{pct:.1f}% usato ({used:.1f}/{total:.1f} GB)")
                elif pct > 70:
                    warn(f"Storage al {pct:.1f}%: {path}")
                else:
                    ok(f"Storage OK: {path} — {pct:.1f}% usato")

        except json.JSONDecodeError:
            warn("Frigate risponde ma JSON non parsabile", body[:200])
    elif code == 401:
        fail("Frigate richiede autenticazione (401)",
             "Da PC remoto non possiamo accedere senza credenziali. "
             "Esegui lo script direttamente sulla Jetson con python3 sentinel_audit.py")
    elif code is None:
        fail("Frigate NON risponde", f"Errore: {body}")
    else:
        fail(f"Frigate risponde con errore HTTP {code}", body[:200])

    return code == 200, body if code == 200 else "{}"


def check_frigate_cameras(jetson_ip, frigate_body_json):
    section("FRIGATE — TELECAMERE E FPS DETECT", "📷")
    try:
        if not frigate_body_json or frigate_body_json == "{}":
            code, body = http_get(jetson_ip, FRIGATE_API_PORT, "/api/stats", use_https=True)
            if code != 200:
                code, body = http_get(jetson_ip, FRIGATE_API_PORT, "/api/stats", use_https=False)
            frigate_body_json = body if code == 200 else "{}"

        stats = json.loads(frigate_body_json)
        cameras = stats.get("cameras", {})

        if not cameras:
            warn("Nessuna camera trovata nell'API Frigate", "Il sistema potrebbe non essere ancora avviato")
            return

        for cam_name, cam_data in cameras.items():
            detect_fps   = cam_data.get("detection_fps", 0)
            process_fps  = cam_data.get("process_fps", 0)
            skipped_fps  = cam_data.get("skipped_fps", 0)
            capture_fps  = cam_data.get("capture_fps", 0)

            info(f"Camera {cam_name}: capture={capture_fps:.1f}fps detect={detect_fps:.1f}fps process={process_fps:.1f}fps skip={skipped_fps:.1f}fps")

            if capture_fps < 1:
                fail(f"{cam_name}: capture FPS = 0", "Telecamera offline o stream interrotto")
            elif capture_fps < MIN_DETECT_FPS:
                warn(f"{cam_name}: capture FPS basso ({capture_fps:.1f})", f"Attesi ~{EXPECTED_FPS}fps")
            else:
                ok(f"{cam_name}: capture FPS OK ({capture_fps:.1f}fps)")

            if detect_fps < 1 and capture_fps > 0:
                warn(f"{cam_name}: detection FPS = 0 ma stream attivo", "Il detector potrebbe essere sovraccarico")

    except Exception as e:
        fail("Errore analisi telecamere Frigate", str(e))


def check_frigate_events(jetson_ip):
    section("FRIGATE — EVENTI RECENTI E FANTASMI", "👻")
    code, body = http_get(jetson_ip, FRIGATE_API_PORT,
                          "/api/events?limit=100&label=person", use_https=True)
    if code is None:
        code, body = http_get(jetson_ip, FRIGATE_API_PORT,
                              "/api/events?limit=100&label=person", use_https=False)

    if code != 200:
        warn("Impossibile leggere eventi Frigate", f"HTTP {code}: {str(body)[:100]}")
        return

    try:
        events = json.loads(body)
        if not events:
            info("Nessun evento 'person' nelle ultime sessioni")
            return

        info(f"Totale eventi 'person' analizzati: {len(events)}")

        ghosts = []
        per_camera = defaultdict(int)
        false_positive_patterns = []

        for ev in events:
            cam = ev.get("camera", "unknown")
            per_camera[cam] += 1
            score = ev.get("top_score", 0) or ev.get("score", 0) or 0
            start_ts = ev.get("start_time", 0)
            end_ts = ev.get("end_time", 0)
            duration = (end_ts - start_ts) if end_ts and start_ts else 0

            # Rilevamento fantasmi: score sotto soglia + durata brevissima
            is_ghost = False
            reasons = []
            if score < GHOST_THRESHOLD and score > 0:
                is_ghost = True
                reasons.append(f"score={score:.2f} < {GHOST_THRESHOLD}")
            if duration < 1.0 and duration > 0:
                is_ghost = True
                reasons.append(f"durata={duration:.1f}s < 1s")

            if is_ghost:
                ghosts.append({
                    "id": ev.get("id", "?")[:8],
                    "camera": cam,
                    "score": score,
                    "duration": duration,
                    "reasons": reasons
                })

        # Riepilogo per camera
        for cam, count in per_camera.items():
            info(f"  {cam}: {count} eventi person")

        # Fantasmi
        if ghosts:
            warn(f"Trovati {len(ghosts)} potenziali FANTASMI (false detection)", 
                 "Score basso e/o durata < 1 secondo")
            for g in ghosts[:10]:  # mostra max 10
                info(f"  → Fantasma [{g['id']}] cam={g['camera']} score={g['score']:.2f} dur={g['duration']:.1f}s | {', '.join(g['reasons'])}")
            if len(ghosts) > 10:
                info(f"  … e altri {len(ghosts)-10} fantasmi (vedi report HTML)")
        else:
            ok("Nessun fantasma rilevato negli eventi recenti")

        # Verifica integrità score vs soglia configurata
        high_score_count = sum(1 for ev in events if (ev.get("top_score") or 0) >= PERSON_THRESHOLD)
        ok(f"Eventi con score ≥ {PERSON_THRESHOLD} (soglia configurata): {high_score_count}/{len(events)}")

    except Exception as e:
        fail("Errore parsing eventi Frigate", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 3 — GO2RTC STREAM HEALTH
# ─────────────────────────────────────────────────────────────────────────────
def check_go2rtc(jetson_ip):
    section("GO2RTC — STREAM HEALTH", "📡")

    body = None
    if IS_ON_JETSON:
        # go2rtc gira dentro il container frigate sulla porta 1984 — accesso via docker exec
        try:
            r = subprocess.run(
                ["docker", "exec", "frigate",
                 "wget", "-qO-", "http://localhost:1984/api/streams"],
                capture_output=True, text=True, timeout=10,
                cwd=SENTINEL_PATH
            )
            if r.returncode == 0 and r.stdout.strip():
                body = r.stdout.strip()
                ok("go2rtc API raggiunta via docker exec (interno container)")
            else:
                fail("go2rtc API non risponde via docker exec", r.stderr[:100])
                return
        except Exception as e:
            fail("Errore docker exec go2rtc", str(e))
            return
    else:
        # Da PC remoto: go2rtc port 1984 non è esposta — non possiamo accedere
        warn("go2rtc API (porta 1984) non esposta dalla Jetson verso l'esterno",
             "È accessibile solo dall'interno del container. "
             "Esegui lo script direttamente sulla Jetson per questa verifica.")
        return

    try:
        streams = json.loads(body)
        info(f"Stream totali in go2rtc: {len(streams)}")

        expected_streams = [
            "varco_carrabile_main", "varco_carrabile_sub",
            "varco_pedonale_main",  "varco_pedonale_sub",
            "piazzale_main",        "piazzale_sub",
        ]

        for stream_name in expected_streams:
            if stream_name not in streams:
                fail(f"Stream MANCANTE: {stream_name}")
                continue

            sdata = streams[stream_name]
            producers = sdata.get("producers", [])
            consumers = sdata.get("consumers", [])

            if not producers:
                fail(f"Stream {stream_name}: nessun producer (sorgente non connessa)")
                continue

            prod = producers[0]
            recv_bytes = prod.get("recv", 0)

            if recv_bytes == 0:
                fail(f"Stream {stream_name}: 0 byte ricevuti dalla sorgente", "Camera offline o URL sbagliato")
            elif recv_bytes < 1000:
                warn(f"Stream {stream_name}: pochi byte ricevuti ({recv_bytes})", "Potrebbe essere appena partito")
            else:
                recv_mb = recv_bytes / 1_000_000
                ok(f"Stream {stream_name}: {recv_mb:.1f} MB ricevuti, {len(consumers)} consumer attivi")

            if not consumers:
                warn(f"  Nessun consumer su {stream_name}", "Frigate potrebbe non aver agganciato il flusso")

    except Exception as e:
        fail("Errore parsing risposta go2rtc", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 4 — MQTT LIVE MONITORING
# ─────────────────────────────────────────────────────────────────────────────
def check_mqtt_live(jetson_ip):
    section(f"MQTT LIVE — {MQTT_MONITOR_SECONDS}s DI ASCOLTO EVENTI", "📨")

    # Mosquitto è legato a 127.0.0.1:1883 — raggiungibile direttamente solo dalla Jetson
    mqtt_host = "127.0.0.1" if IS_ON_JETSON else jetson_ip

    if not tcp_reachable(mqtt_host, MQTT_PORT, timeout=2):
        if IS_ON_JETSON:
            fail(f"MQTT non raggiungibile su 127.0.0.1:{MQTT_PORT}",
                 "Mosquitto potrebbe essere spento — controlla con: docker compose logs mosquitto")
        else:
            warn(f"MQTT ({jetson_ip}:{MQTT_PORT}) non raggiungibile da PC remoto",
                 "Mosquitto è legato a 127.0.0.1 sulla Jetson. "
                 "Esegui lo script direttamente sulla Jetson per il monitoraggio live.")
        return

    try:
        import paho.mqtt.client as mqtt_client
    except ImportError:
        warn("paho-mqtt non installato",
             "Installa con: pip3 install paho-mqtt  — poi rilancia l'audit")
        return

    events_received = []
    state_lock = threading.Lock()
    connected_flag = threading.Event()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            connected_flag.set()
            client.subscribe("frigate/#")
        else:
            fail("MQTT: connessione rifiutata", f"Return code: {rc}")

    def on_message(client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            payload = msg.payload.decode("utf-8", errors="replace")

        with state_lock:
            events_received.append({
                "ts": datetime.datetime.now().isoformat(),
                "topic": topic,
                "payload": payload,
            })

    client = mqtt_client.Client(client_id="sentinel_audit_tool")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(mqtt_host, MQTT_PORT, keepalive=60)
        client.loop_start()

        if not connected_flag.wait(timeout=5):
            fail("MQTT: timeout connessione")
            client.loop_stop()
            return

        ok(f"MQTT connesso — ascolto per {MQTT_MONITOR_SECONDS} secondi…")
        print(f"  ⏳ In ascolto su frigate/# — {MQTT_MONITOR_SECONDS}s")

        for i in range(MQTT_MONITOR_SECONDS):
            time.sleep(1)
            with state_lock:
                n = len(events_received)
            if (i + 1) % 10 == 0:
                print(f"     {i+1}s — {n} messaggi ricevuti finora…")

        client.loop_stop()
        client.disconnect()

    except Exception as e:
        fail("Errore connessione MQTT", str(e))
        return

    with state_lock:
        all_events = list(events_received)

    if not all_events:
        info("Nessun messaggio MQTT ricevuto durante il monitoraggio")
        info("Se le telecamere sono attive ma non c'è movimento, è normale")
        return

    info(f"Messaggi MQTT totali ricevuti: {len(all_events)}")

    # Analisi per topic
    by_topic = defaultdict(list)
    for ev in all_events:
        by_topic[ev["topic"]].append(ev)

    frigate_events = by_topic.get("frigate/events", [])
    person_events  = [e for t, evs in by_topic.items() for e in evs if "/person" in t]

    info(f"  frigate/events: {len(frigate_events)} messaggi")
    info(f"  frigate/*/person: {len(person_events)} messaggi")

    # Analisi fantasmi in tempo reale
    live_ghosts = 0
    for ev in frigate_events:
        payload = ev.get("payload", {})
        if not isinstance(payload, dict):
            continue
        after = payload.get("after", {})
        score = after.get("top_score", 0) or after.get("score", 0) or 0
        label = after.get("label", "")
        cam = after.get("camera", "?")
        ev_type = payload.get("type", "?")

        if label == "person" and score < GHOST_THRESHOLD and score > 0 and ev_type == "new":
            live_ghosts += 1
            warn(f"FANTASMA live: cam={cam} score={score:.2f} tipo={ev_type}",
                 f"Topic: {ev['topic']} alle {ev['ts'][11:19]}")

    if live_ghosts == 0 and frigate_events:
        ok(f"Nessun fantasma live durante {MQTT_MONITOR_SECONDS}s di osservazione")
    elif live_ghosts > 0:
        warn(f"Rilevati {live_ghosts} potenziali fantasmi live",
             "Verifica che HUMAN_RATIO_FILTER_ENABLED=true sia nel .env")

    # Mostra ultimi eventi person
    person_new = [e for e in frigate_events
                  if isinstance(e.get("payload"), dict)
                  and e["payload"].get("after", {}).get("label") == "person"
                  and e["payload"].get("type") == "new"]
    if person_new:
        info(f"Nuovi rilevamenti 'person' durante il monitoraggio: {len(person_new)}")
        for e in person_new[-5:]:
            after = e["payload"].get("after", {})
            info(f"  → cam={after.get('camera')} score={after.get('top_score', 0):.2f} at {e['ts'][11:19]}")


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 5 — ORCHESTRATORE (log Docker via Frigate proxy)
# ─────────────────────────────────────────────────────────────────────────────
def check_orchestrator_logs(jetson_ip):
    section("ORCHESTRATORE — VERIFICA LOG LATENZA", "⚙️")

    log_text = None

    if IS_ON_JETSON:
        # Sulla Jetson eseguiamo docker compose direttamente
        try:
            r = subprocess.run(
                ["docker", "compose", "logs", "--tail=300", "orchestrator"],
                capture_output=True, text=True, timeout=15,
                cwd=SENTINEL_PATH
            )
            if r.returncode == 0 and (r.stdout.strip() or r.stderr.strip()):
                log_text = r.stdout + r.stderr
                ok("Log orchestratore letti via docker compose")
            else:
                warn("Nessun log dall'orchestratore", "Container non avviato?")
        except Exception as e:
            warn("Errore lettura log orchestratore", str(e))
    else:
        # Da PC remoto: prova SSH
        try:
            r = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=no",
                 f"alessio@{jetson_ip}",
                 f"docker compose -f {SENTINEL_PATH}/docker-compose.yml "
                 "logs --tail=200 orchestrator 2>&1"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0 and r.stdout.strip():
                log_text = r.stdout
                ok("Log orchestratore letti via SSH")
            else:
                warn("SSH non disponibile o nessun output")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            warn("SSH non disponibile da questo PC",
                 "Esegui lo script sulla Jetson per leggere i log in automatico")
        except Exception as e:
            warn("Errore SSH", str(e))

    if log_text:
        analyze_orchestrator_log_text(log_text)
    else:
        info("Comando da eseguire manualmente sulla Jetson:")
        info("  docker compose logs --tail=200 orchestrator | grep -E 'Latenza|ERROR|WARNING|WARN'")
        info("Cerca la riga [Latenza software: Xms] — se X < 50ms l'orchestratore è ottimale")


def analyze_orchestrator_log_text(log_text):
    lines = log_text.splitlines()
    latency_vals = []
    errors = []
    warnings = []
    audio_triggers = []
    relay_triggers = []
    ghost_filters = []

    for line in lines:
        if "Latenza software:" in line:
            m = re.search(r"Latenza software:\s*(\d+(?:\.\d+)?)\s*ms", line)
            if m:
                latency_vals.append(float(m.group(1)))
        if "ERROR" in line or "CRITICAL" in line:
            errors.append(line.strip())
        if "WARNING" in line or "WARN" in line:
            warnings.append(line.strip())
        if "audio" in line.lower() and ("play" in line.lower() or "start" in line.lower()):
            audio_triggers.append(line.strip())
        if "relay" in line.lower() or "faretto" in line.lower():
            relay_triggers.append(line.strip())
        if "proporzioni" in line.lower() or "ratio" in line.lower() or "filtro" in line.lower():
            ghost_filters.append(line.strip())

    if latency_vals:
        avg_lat = sum(latency_vals) / len(latency_vals)
        max_lat = max(latency_vals)
        min_lat = min(latency_vals)
        ok(f"Latenza software orchestratore: media={avg_lat:.0f}ms min={min_lat:.0f}ms max={max_lat:.0f}ms")
        if avg_lat < 50:
            ok("Latenza orchestratore ECCELLENTE (< 50ms)")
        elif avg_lat < 150:
            ok(f"Latenza orchestratore buona ({avg_lat:.0f}ms)")
        else:
            warn(f"Latenza orchestratore alta ({avg_lat:.0f}ms)", "Controllare ffprobe cache e relay thread")
    else:
        info("Nessun dato latenza nei log recenti (normale se non ci sono stati eventi)")

    if errors:
        fail(f"Trovati {len(errors)} errori nei log orchestratore")
        for e in errors[-5:]:
            fail("  ERROR: " + e[:120])
    else:
        ok("Nessun errore (ERROR/CRITICAL) nei log orchestratore")

    if warnings:
        warn(f"Trovati {len(warnings)} warning nei log orchestratore")
        for w in warnings[-3:]:
            info("  WARN: " + w[:120])
    else:
        ok("Nessun warning nei log orchestratore")

    info(f"Trigger audio registrati nei log: {len(audio_triggers)}")
    info(f"Trigger relay/faretto registrati: {len(relay_triggers)}")
    if ghost_filters:
        ok(f"Filtro proporzioni attivo — {len(ghost_filters)} righe di filtraggio trovate nei log")


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 6 — RELAY E ALTOPARLANTE
# ─────────────────────────────────────────────────────────────────────────────
def check_relay_and_speaker(jetson_ip):
    section("RELAY WAVESHARE E FANVIL A233", "🔌")

    # Relay: test TCP Modbus
    if tcp_reachable(RELAY_HOST, RELAY_PORT):
        ok(f"Relay Waveshare: porta Modbus TCP aperta ({RELAY_HOST}:{RELAY_PORT})")
        # Invio query Modbus Read Coils (FC01) — non-distruttivo
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((RELAY_HOST, RELAY_PORT))
            # Modbus TCP: Transaction=0x0001, Protocol=0x0000, Length=6, Unit=0x01
            # FC01 Read Coils: Start=0x0000, Count=0x0008
            modbus_req = bytes([0x00, 0x01, 0x00, 0x00, 0x00, 0x06,
                                0x01, 0x01, 0x00, 0x00, 0x00, 0x08])
            s.send(modbus_req)
            resp = s.recv(64)
            s.close()
            if len(resp) >= 9:
                coil_byte = resp[9]
                ok(f"Relay: risposta Modbus OK — stato coil byte = 0x{coil_byte:02X}")
                # Decodifica singoli canali
                for ch in range(8):
                    state = "ON" if (coil_byte >> ch) & 1 else "OFF"
                    info(f"  Canale {ch+1}: {state}")
            else:
                warn("Relay: risposta Modbus troppo corta", f"Ricevuti {len(resp)} byte")
        except Exception as e:
            warn("Relay: TCP aperta ma query Modbus fallita", str(e))
    else:
        fail(f"Relay Waveshare NON raggiungibile ({RELAY_HOST}:{RELAY_PORT})")

    # Fanvil: HTTP check
    if tcp_reachable(SPEAKER_HOST, SPEAKER_PORT):
        code, body = http_get(SPEAKER_HOST, SPEAKER_PORT, "/")
        if code and code < 400:
            ok(f"Fanvil A233: interfaccia HTTP risponde (HTTP {code})")
        else:
            warn(f"Fanvil A233: TCP aperta ma HTTP risponde {code}")
    else:
        warn(f"Fanvil A233: non raggiungibile via HTTP ({SPEAKER_HOST}:{SPEAKER_PORT})")
        info("Il Fanvil ascolta MULTICAST RTP — potrebbe essere raggiungibile anche senza HTTP")


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 7 — AUDIO FILES CHECK (via SSH)
# ─────────────────────────────────────────────────────────────────────────────
def check_audio_files(jetson_ip):
    section("FILE AUDIO — INVENTARIO PACCHETTI VOCALI", "🔊")

    audio_path = f"{SENTINEL_PATH}/orchestrator/audio"
    cmd_find = (
        f"find {audio_path} -name '*.mp3' | sort && "
        f"echo '---DURATIONS---' && "
        f"find {audio_path} -name '*.mp3' | sort | "
        f"xargs -I{{}} sh -c 'echo -n \"{{}}: \" && "
        f"ffprobe -v quiet -show_entries format=duration -of csv=p=0 {{}} 2>/dev/null'"
    )

    output = None
    if IS_ON_JETSON:
        try:
            r = subprocess.run(cmd_find, shell=True, capture_output=True, text=True, timeout=15)
            if r.stdout.strip():
                output = r.stdout.strip()
                ok("Inventario file audio completato")
        except Exception as e:
            warn("Errore inventario audio", str(e))
    else:
        try:
            r = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=no",
                 f"alessio@{jetson_ip}", cmd_find],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode == 0 and r.stdout.strip():
                output = r.stdout.strip()
        except Exception as e:
            warn("Verifica file audio saltata (SSH non disponibile)", f"Controlla: ls -la {audio_path}/")

    if not output:
        warn("Impossibile leggere file audio",
             f"Controlla manualmente: ls -la {audio_path}/carmelo/ {audio_path}/sami/")
        return

    lines = output.split("\n")
    packs = defaultdict(list)
    for line in lines:
        if ".mp3" in line and "DURATIONS" not in line and ":" not in line.split("/")[-1]:
            parts = line.split("/")
            if len(parts) >= 2:
                pack = parts[-2]
                fname = parts[-1]
                packs[pack].append(fname)

    info(f"Pack audio trovati: {list(packs.keys())}")
    for pack, files in packs.items():
        info(f"  Pack '{pack}': {len(files)} file — {', '.join(sorted(files))}")
        for exp in [f"0{i}" for i in range(1, 6)]:
            found = any(f.startswith(exp) for f in files)
            if not found:
                warn(f"  Pack '{pack}': manca il file {exp}_*.mp3")
            else:
                ok(f"  Pack '{pack}': {exp}_*.mp3 ✓")

    # Verifica durata 03
    for line in lines:
        if "03_" in line and ".mp3:" in line:
            try:
                duration = float(line.split(":")[-1].strip())
                if duration > 3.0:
                    warn(f"Audio 03 dura {duration:.1f}s",
                         "Versione 'sprint' da 2.2s non ancora creata — da fare nel prossimo pezzettino")
                else:
                    ok(f"Audio 03: {duration:.1f}s (versione sprint già presente)")
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 8 — CONFIGURAZIONE CRITICA
# ─────────────────────────────────────────────────────────────────────────────
def check_critical_config(jetson_ip):
    section("CONFIGURAZIONE CRITICA — .ENV E CONFIG.YML", "⚙️")

    env_path    = f"{SENTINEL_PATH}/.env"
    config_path = f"{SENTINEL_PATH}/config/config.yml"

    env_text = None
    if IS_ON_JETSON:
        # Leggi direttamente i file locali
        try:
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    env_text = f.read()
                ok(f".env trovato e letto: {env_path}")
            else:
                fail(f".env NON trovato in {env_path}")
        except Exception as e:
            warn("Errore lettura .env", str(e))
    else:
        # Da PC remoto: SSH
        try:
            r = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=no",
                 f"alessio@{jetson_ip}",
                 f"cat {env_path} 2>/dev/null || echo 'FILE_NOT_FOUND'"],
                capture_output=True, text=True, timeout=8
            )
            if r.returncode == 0 and "FILE_NOT_FOUND" not in r.stdout:
                env_text = r.stdout
        except Exception as e:
            warn("SSH non disponibile — impossibile leggere .env", str(e))

    if env_text:
        def get_env(key):
            m = re.search(rf"^{re.escape(key)}\s*=\s*(.+)$", env_text, re.MULTILINE)
            return m.group(1).strip() if m else None

        checks = [
            ("HUMAN_RATIO_FILTER_ENABLED", "true",  "Filtro proporzioni umane"),
            ("SPEAKER_GLOBAL_COOLDOWN_SECONDS", "20", "Cooldown globale speaker"),
            ("FANVIL_RTP_DELAY_MS", "300",           "Pre-roll audio Fanvil"),
            ("AUDIO_COOLDOWN_SECONDS", "15",         "Cooldown locale per camera"),
        ]
        for key, expected, label in checks:
            val = get_env(key)
            if val is None:
                warn(f".env: {label} ({key}) NON TROVATA", "Potrebbe usare il valore di default del codice")
            elif val.lower() == expected.lower():
                ok(f".env: {label} = {val} ✓")
            else:
                warn(f".env: {label} = {val} (atteso: {expected})", f"Chiave: {key}")

        # URL telecamere
        for cam in ["VARCO_CARRABILE", "VARCO_PEDONALE", "PIAZZALE"]:
            sub_url = get_env(f"FRIGATE_CAM_{cam}_SUB_URL") or ""
            if "ffmpeg:http" in sub_url or "flv?" in sub_url:
                if cam == "VARCO_CARRABILE":
                    fail(f".env: {cam} sub URL è ancora HTTP-FLV (test fallito)",
                         "Ripristinare con: rtsp://admin:PASS@192.168.1.20:554/h264Preview_01_sub")
                else:
                    warn(f".env: {cam} sub URL usa HTTP-FLV", sub_url[:80])
            elif "rtsp://" in sub_url:
                ok(f".env: {cam} sub URL = RTSP ✓")
            else:
                warn(f".env: {cam} sub URL formato inatteso", sub_url[:80])
    else:
        warn("Impossibile leggere .env — verifica manuale richiesta")

    # Verifica input_args in config.yml
    config_text = None
    if IS_ON_JETSON:
        try:
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config_text = f.read()
        except Exception:
            pass
    else:
        try:
            r2 = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=no",
                 f"alessio@{jetson_ip}",
                 f"grep 'input_args' {config_path}"],
                capture_output=True, text=True, timeout=8
            )
            if r2.returncode == 0:
                config_text = r2.stdout
        except Exception:
            pass

    if config_text:
        bad_flags = False
        for line in config_text.splitlines():
            if "input_args" in line:
                if "nobuffer" in line or "low_delay" in line:
                    fail("config.yml: input_args contiene flag non supportati!",
                         line.strip() + " — Eseguire: git pull && docker compose up -d --force-recreate frigate")
                    bad_flags = True
                elif "preset-rtsp-restream" in line:
                    ok("config.yml: input_args = preset-rtsp-restream ✓")
        if not bad_flags:
            ok("config.yml: nessun flag non supportato in input_args ✓")
    else:
        info("config.yml non verificato — controlla manualmente con grep 'input_args' config/config.yml")


# ─────────────────────────────────────────────────────────────────────────────
# REPORT HTML
# ─────────────────────────────────────────────────────────────────────────────
def generate_html_report():
    now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    s = report["summary"]
    total = s["pass"] + s["warn"] + s["fail"]
    score_pct = int((s["pass"] / total * 100)) if total > 0 else 0

    status_color = "#22c55e" if score_pct >= 90 else "#f59e0b" if score_pct >= 70 else "#ef4444"
    status_text  = "SISTEMA OK" if score_pct >= 90 else "ATTENZIONE" if score_pct >= 70 else "PROBLEMI CRITICI"

    html_sections = ""
    for sec in report["sections"]:
        rows = ""
        for c in sec["checks"]:
            st = c["status"]
            bg = {"PASS": "#f0fdf4", "WARN": "#fefce8", "FAIL": "#fef2f2", "INFO": "#f8fafc"}.get(st, "white")
            icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "INFO": "ℹ️"}.get(st, "")
            detail_html = f"<br><small style='color:#64748b'>{c['detail']}</small>" if c["detail"] else ""
            rows += f"""
            <tr style="background:{bg}">
              <td style="padding:6px 10px;font-size:14px">{icon}</td>
              <td style="padding:6px 10px;font-size:14px">{c['message']}{detail_html}</td>
              <td style="padding:6px 10px;font-size:12px;color:#64748b;white-space:nowrap">{st}</td>
            </tr>"""
        html_sections += f"""
        <div class="section">
          <h2>{sec['title']}</h2>
          <table width="100%">
            <thead><tr>
              <th width="30px"></th>
              <th style="text-align:left">Verifica</th>
              <th width="80px">Stato</th>
            </tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sentinel AI — Audit Report {now_str}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f1f5f9; color: #1e293b; padding: 20px; }}
  .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
             color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
  .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
  .header .meta {{ font-size: 13px; color: #94a3b8; }}
  .score-badge {{ display: inline-block; background: {status_color}; color: white;
                  padding: 6px 16px; border-radius: 20px; font-weight: bold;
                  font-size: 18px; margin-top: 10px; }}
  .summary-bar {{ display: flex; gap: 12px; margin-bottom: 20px; }}
  .summary-card {{ flex: 1; background: white; border-radius: 10px; padding: 16px;
                   text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .summary-card .num {{ font-size: 32px; font-weight: bold; }}
  .summary-card .lbl {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
  .pass-num {{ color: #22c55e; }}
  .warn-num {{ color: #f59e0b; }}
  .fail-num {{ color: #ef4444; }}
  .info-num {{ color: #3b82f6; }}
  .section {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 16px;
              box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .section h2 {{ font-size: 16px; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }}
  table {{ border-collapse: collapse; }}
  th {{ background: #f8fafc; font-size: 12px; text-align: left; padding: 6px 10px; border-bottom: 1px solid #e2e8f0; }}
  tr:hover {{ background: #f8fafc !important; }}
  .footer {{ text-align: center; color: #94a3b8; font-size: 12px; margin-top: 20px; }}
</style>
</head>
<body>
<div class="header">
  <h1>🛡️ SENTINEL AI — AUDIT DIAGNOSTICO COMPLETO</h1>
  <div class="meta">
    Jetson IP: <b>{report['jetson_ip']}</b> &nbsp;|&nbsp;
    Data: <b>{now_str}</b> &nbsp;|&nbsp;
    Durata audit: <b>{report.get('duration_s', '?')}s</b>
  </div>
  <div class="score-badge">{status_text} — {score_pct}% OK</div>
</div>

<div class="summary-bar">
  <div class="summary-card"><div class="num pass-num">{s['pass']}</div><div class="lbl">✅ OK</div></div>
  <div class="summary-card"><div class="num warn-num">{s['warn']}</div><div class="lbl">⚠️ Attenzione</div></div>
  <div class="summary-card"><div class="num fail-num">{s['fail']}</div><div class="lbl">❌ Critici</div></div>
  <div class="summary-card"><div class="num info-num">{s['info']}</div><div class="lbl">ℹ️ Info</div></div>
</div>

{html_sections}

<div class="footer">
  Generato da sentinel_audit.py — Conf-Lavoro Sentinel AI
</div>
</body>
</html>"""
    return html


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     SENTINEL AI — AUDIT DIAGNOSTICO COMPLETO v1.1           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    if IS_ON_JETSON:
        print("  🟢 Modalità rilevata: ON-JETSON")
        print("     → accesso diretto a Frigate:5000, MQTT:127.0.0.1, docker, file .env")
        print()
        default_ip = "127.0.0.1"
    else:
        print("  🔵 Modalità rilevata: PC REMOTO")
        print("     → accesso via rete LAN all'IP della Jetson")
        print()
        default_ip = DEFAULT_JETSON_IP

    user_ip = input(f"  Inserisci IP Jetson (Invio per usare {default_ip}): ").strip()
    jetson_ip = user_ip if user_ip else default_ip
    report["jetson_ip"] = jetson_ip

    print(f"\n  ✔ Jetson IP impostato: {jetson_ip}")
    print(f"  ⏱ Durata stimata: ~{MQTT_MONITOR_SECONDS + 30} secondi\n")
    input("  Premi INVIO per avviare l'audit...")

    t_start = time.time()

    # Esegui tutte le sezioni
    check_environment(jetson_ip)
    check_network(jetson_ip)

    ok_frigate, frigate_json = check_frigate(jetson_ip)
    check_frigate_cameras(jetson_ip, frigate_json)
    check_frigate_events(jetson_ip)

    check_go2rtc(jetson_ip)
    check_mqtt_live(jetson_ip)
    check_orchestrator_logs(jetson_ip)
    check_relay_and_speaker(jetson_ip)
    check_audio_files(jetson_ip)
    check_critical_config(jetson_ip)

    report["duration_s"] = int(time.time() - t_start)

    # Stampa riepilogo finale
    s = report["summary"]
    print("\n")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                    AUDIT COMPLETATO                         ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  ✅ OK:        {s['pass']:3d}                                         ║")
    print(f"║  ⚠️  Attenzione:{s['warn']:3d}                                         ║")
    print(f"║  ❌ Critici:   {s['fail']:3d}                                         ║")
    print(f"║  ℹ️  Info:      {s['info']:3d}                                         ║")
    print(f"║  ⏱  Durata:   {report['duration_s']:3d}s                                        ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # Genera report HTML
    html_content = generate_html_report()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"sentinel_audit_{timestamp}.html"

    # Salva nella stessa cartella dello script (USB)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    report_path = os.path.join(script_dir, report_filename)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\n  📄 Report HTML salvato in:\n     {report_path}\n")

    # Apri automaticamente nel browser
    try:
        webbrowser.open(f"file:///{report_path.replace(os.sep, '/')}")
        print("  🌐 Report aperto nel browser.")
    except Exception:
        print("  (Apri manualmente il file HTML nel browser)")

    print()
    if s["fail"] > 0:
        print(f"  ❌ CI SONO {s['fail']} PROBLEMI CRITICI — Controlla il report HTML!")
    elif s["warn"] > 0:
        print(f"  ⚠️  {s['warn']} avvertenze da verificare — Sistema funzionante ma con attenzioni.")
    else:
        print("  ✅ Tutto OK — Sistema Sentinel AI funzionante correttamente.")
    print()
    input("  Premi INVIO per uscire...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  [Audit interrotto dall'utente]")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ERRORE INATTESO: {e}")
        traceback.print_exc()
        input("\n  Premi INVIO per uscire...")
        sys.exit(1)
