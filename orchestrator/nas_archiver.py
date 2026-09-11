#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Modulo Archiviazione NAS Ugreen (SMB / Windows Share)

Caratteristiche:
- Si collega al NAS Ugreen su IP 192.168.1.11, condivisione 'sentinel-eventi'.
- Credenziali: utente 'jetson', password (configurabile da .env).
- Supporto NTLM esplicito tramite smbclient.ClientConfig per prevenire 'No username or password was specified'.
- Preleva lo snapshot JPEG ad alta risoluzione o la clip video MP4 da Frigate tramite API interna.
- Snapshot: scaricato immediatamente al primo rilevamento.
- Clip MP4: scaricata SOLO alla fine dell'evento con ritardo programmato e retry automatici (risolve HTTP 400).
- Salva l'evidenza sul NAS organizzata per Data e Telecamera:
  `//192.168.1.11/sentinel-eventi/YYYY-MM-DD/<camera>/<id_evento>_<label>.jpg`
- Include buffer di emergenza locale se il NAS è temporaneamente non raggiungibile.
"""

import os
import io
import time
import logging
import threading
from datetime import datetime
import requests
import smbclient
from smbclient import ClientConfig, register_session, makedirs, open_file

logger = logging.getLogger("SentinelNAS")

class UgreenNASArchiver:
    def __init__(
        self,
        nas_ip="192.168.1.11",
        share_name="sentinel-eventi",
        user="jetson",
        password="",
        frigate_host="frigate",
        frigate_port=5000,
        local_backup_dir="/app/storage/local_evidence"
    ):
        self.nas_ip = nas_ip
        self.share_name = share_name
        self.user = user
        self.password = password
        self.frigate_base_url = f"http://{frigate_host}:{frigate_port}"
        self.local_backup_dir = local_backup_dir
        self.unc_base = f"\\\\{self.nas_ip}\\{self.share_name}"
        self._lock = threading.Lock()

        # Configurazione globale e registrazione credenziali SMB (smbprotocol)
        if self.user and self.password:
            try:
                ClientConfig(username=self.user, password=self.password, auth_protocol="ntlm")
                register_session(self.nas_ip, username=self.user, password=self.password)
                logger.info("Configurazione SMB completata per NAS Ugreen %s (utente: %s)", self.nas_ip, self.user)
            except Exception as e:
                logger.warning("Avviso configurazione iniziale sessione SMB per %s: %s", self.nas_ip, e)

    def archive_snapshot(self, event_id: str, camera: str, label: str):
        """
        Scarica immediatamente lo snapshot JPEG dell'evento da Frigate e lo invia al NAS.
        Esegue l'operazione in un thread dedicato per non bloccare l'orchestratore.
        """
        def _snapshot_worker():
            date_folder = datetime.now().strftime("%Y-%m-%d")
            remote_cam_dir = f"{self.unc_base}\\{date_folder}\\{camera}"
            snapshot_url = f"{self.frigate_base_url}/api/events/{event_id}/snapshot.jpg"
            filename = f"{event_id}_{label}.jpg"

            try:
                logger.info("Scaricamento snapshot da Frigate: %s", snapshot_url)
                res = requests.get(snapshot_url, timeout=10.0)
                if res.status_code == 200 and len(res.content) > 0:
                    success = self._write_to_smb(remote_cam_dir, filename, res.content)
                    if not success:
                        self._save_local_fallback(remote_cam_dir, filename, res.content)
                else:
                    logger.warning("Frigate snapshot HTTP %d per %s", res.status_code, snapshot_url)
            except Exception as exc:
                logger.error("Errore durante archiviazione snapshot %s: %s", filename, exc)

        t = threading.Thread(target=_snapshot_worker, daemon=True)
        t.start()

    def archive_clip(self, event_id: str, camera: str, label: str, delay_seconds: float = 3.0, max_retries: int = 3):
        """
        Scarica la clip MP4 dell'evento da Frigate SOLO dopo la conclusione dell'evento.
        Attende delay_seconds e riprova fino a max_retries volte per dare a Frigate il tempo di remuxare l'MP4.
        """
        def _clip_worker():
            if delay_seconds > 0:
                time.sleep(delay_seconds)

            date_folder = datetime.now().strftime("%Y-%m-%d")
            remote_cam_dir = f"{self.unc_base}\\{date_folder}\\{camera}"
            clip_url = f"{self.frigate_base_url}/api/events/{event_id}/clip.mp4"
            filename = f"{event_id}_{label}.mp4"

            for attempt in range(1, max_retries + 1):
                try:
                    logger.info("Scaricamento clip da Frigate (tentativo %d/%d): %s", attempt, max_retries, clip_url)
                    res = requests.get(clip_url, timeout=25.0)
                    if res.status_code == 200 and len(res.content) > 0:
                        success = self._write_to_smb(remote_cam_dir, filename, res.content)
                        if not success:
                            self._save_local_fallback(remote_cam_dir, filename, res.content)
                        return
                    elif res.status_code in (400, 404):
                        logger.info("Clip non ancora finalizzata da Frigate (HTTP %d, tentativo %d/%d). Attendo 3s...", res.status_code, attempt, max_retries)
                        time.sleep(3.0)
                    else:
                        logger.warning("Frigate clip HTTP %d per %s", res.status_code, clip_url)
                        break
                except Exception as exc:
                    logger.error("Errore durante scaricamento clip %s (tentativo %d): %s", filename, attempt, exc)
                    time.sleep(2.0)

            logger.warning("Clip per l'evento %s non disponibile dopo %d tentativi.", event_id, max_retries)

        t = threading.Thread(target=_clip_worker, daemon=True)
        t.start()

    def archive_event(self, event_id: str, camera: str, label: str, has_snapshot: bool = True, has_clip: bool = False):
        """Metodo retrocompatibile per archiviazione cumulativa."""
        if has_snapshot:
            self.archive_snapshot(event_id, camera, label)
        if has_clip:
            self.archive_clip(event_id, camera, label, delay_seconds=3.0)

    def _write_to_smb(self, remote_dir: str, filename: str, data: bytes) -> bool:
        try:
            # Crea ricorsivamente la cartella sul NAS passando sempre credenziali esplicite
            try:
                makedirs(remote_dir, exist_ok=True, username=self.user, password=self.password)
            except Exception as dir_err:
                logger.debug("makedirs su %s: %s", remote_dir, dir_err)

            remote_file_path = f"{remote_dir}\\{filename}"
            with open_file(remote_file_path, mode="wb", username=self.user, password=self.password) as f:
                f.write(data)

            logger.info("Evidenza salvata con successo sul NAS: %s (%d byte)", remote_file_path, len(data))
            return True

        except Exception as smb_err:
            logger.error(
                "Errore scrittura SMB su NAS Ugreen (%s/%s): %s",
                remote_dir, filename, smb_err
            )
            return False

    def _save_local_fallback(self, remote_dir: str, filename: str, data: bytes):
        try:
            os.makedirs(self.local_backup_dir, exist_ok=True)
            local_path = os.path.join(self.local_backup_dir, filename)
            with open(local_path, "wb") as f:
                f.write(data)
            logger.info("Evidenza salvata nel buffer locale di riserva: %s", local_path)
        except Exception as err:
            logger.error("Errore salvataggio buffer locale: %s", err)
