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
import gc
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
        Scarica lo snapshot JPEG da Frigate in streaming (senza allocare grandi buffer in RAM)
        e lo trasferisce al NAS Ugreen.
        """
        def _snapshot_worker():
            date_folder = datetime.now().strftime("%Y-%m-%d")
            remote_cam_dir = f"{self.unc_base}\\{date_folder}\\{camera}"
            snapshot_url = f"{self.frigate_base_url}/api/events/{event_id}/snapshot.jpg"
            filename = f"{event_id}_{label}.jpg"

            try:
                logger.info("Scaricamento snapshot in streaming da Frigate: %s", snapshot_url)
                with requests.get(snapshot_url, stream=True, timeout=15.0) as res:
                    if res.status_code == 200:
                        success = self._stream_to_smb(remote_cam_dir, filename, res)
                        if not success:
                            self._stream_to_local_fallback(filename, res)
                    else:
                        logger.warning("Frigate snapshot HTTP %d per %s", res.status_code, snapshot_url)
            except Exception as exc:
                logger.error("Errore durante archiviazione snapshot %s: %s", filename, exc)

        t = threading.Thread(target=_snapshot_worker, daemon=True)
        t.start()

    def archive_clip(self, event_id: str, camera: str, label: str, delay_seconds: float = 3.0, max_retries: int = 3):
        """
        Scarica la clip MP4 dell'evento da Frigate SOLO dopo la conclusione dell'evento.
        Usa streaming a blocchi da 64 KB per mantenere il consumo di memoria a ZERO assoluto,
        evitando che il kernel Linux spinga memoria nello swap NVMe.
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
                    logger.info("Scaricamento clip in streaming (tentativo %d/%d): %s", attempt, max_retries, clip_url)
                    with requests.get(clip_url, stream=True, timeout=30.0) as res:
                        if res.status_code == 200:
                            success = self._stream_to_smb(remote_cam_dir, filename, res)
                            if not success:
                                self._stream_to_local_fallback(filename, res)
                            return
                        elif res.status_code in (400, 404):
                            logger.info("Clip non ancora pronta su Frigate (HTTP %d, tentativo %d/%d). Attendo 3s...", res.status_code, attempt, max_retries)
                            time.sleep(3.0)
                        else:
                            logger.warning("Frigate clip HTTP %d per %s", res.status_code, clip_url)
                            break
                except Exception as exc:
                    logger.error("Errore durante streaming clip %s (tentativo %d): %s", filename, attempt, exc)
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

    def _stream_to_smb(self, remote_dir: str, filename: str, response: requests.Response) -> bool:
        """Scrive lo stream HTTP direttamente sul NAS in blocchi da 64 KB (zero buffer in RAM)."""
        try:
            try:
                makedirs(remote_dir, exist_ok=True, username=self.user, password=self.password)
            except Exception as dir_err:
                logger.debug("makedirs su %s: %s", remote_dir, dir_err)

            remote_file_path = f"{remote_dir}\\{filename}"
            bytes_written = 0
            with open_file(remote_file_path, mode="wb", username=self.user, password=self.password) as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        bytes_written += len(chunk)

            if bytes_written > 0:
                logger.info("Evidenza salvata in streaming sul NAS: %s (%d byte)", remote_file_path, bytes_written)
                return True
            else:
                logger.warning("File evidenza vuoto (0 byte) durante streaming verso %s", remote_file_path)
                return False

        except Exception as smb_err:
            logger.error(
                "Errore scrittura streaming SMB su NAS Ugreen (%s/%s): %s",
                remote_dir, filename, smb_err
            )
            return False

    def _stream_to_local_fallback(self, filename: str, response: requests.Response):
        """Salvataggio di emergenza locale in streaming se il NAS è temporaneamente non raggiungibile."""
        try:
            os.makedirs(self.local_backup_dir, exist_ok=True)
            local_path = os.path.join(self.local_backup_dir, filename)
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            logger.info("Evidenza salvata in streaming nel buffer locale: %s", local_path)
        except Exception as err:
            logger.error("Errore salvataggio buffer locale: %s", err)
