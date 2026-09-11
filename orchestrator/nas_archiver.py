#!/usr/bin/env python3
"""
CONF-LAVORO Sentinel AI — Modulo Archiviazione NAS Ugreen (SMB / Windows Share)

Caratteristiche:
- Si collega al NAS Ugreen su IP 192.168.1.11, condivisione 'sentinel-eventi'.
- Credenziali: utente 'jetson', password (configurabile da .env).
- Preleva lo snapshot ad alta risoluzione o la clip video da Frigate tramite API interna (http://frigate:5000/api/events/<event_id>/snapshot.jpg).
- Salva l'evidenza sul NAS organizzata per Data e Telecamera:
  `//192.168.1.11/sentinel-eventi/YYYY-MM-DD/<camera>/<id_evento>_<label>.jpg`
- Include salvataggio di emergenza su disco locale se il NAS è temporaneamente offline.
- Totalmente asincrono: l'invio al NAS non rallenta l'orchestratore.
"""

import os
import io
import time
import logging
import threading
from datetime import datetime
import requests
import smbclient

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

        # Registrazione credenziali di sessione SMB (smbprotocol)
        if self.user and self.password:
            try:
                smbclient.register_session(self.nas_ip, username=self.user, password=self.password)
                logger.info("Credenziali registrate per il NAS Ugreen %s (utente: %s)", self.nas_ip, self.user)
            except Exception as e:
                logger.warning("Impossibile registrare subito la sessione SMB per %s: %s", self.nas_ip, e)

    def archive_event(self, event_id: str, camera: str, label: str, has_snapshot: bool = True, has_clip: bool = False):
        """
        Scarica gli allegati dell'evento da Frigate e li copia nella cartella del NAS.
        Esegue l'operazione in un thread in background.
        """
        def _archive_worker():
            date_folder = datetime.now().strftime("%Y-%m-%d")
            remote_cam_dir = f"{self.unc_base}\\{date_folder}\\{camera}"

            # 1. Archiviazione Snapshot (Immagine JPEG nitida)
            if has_snapshot:
                snapshot_url = f"{self.frigate_base_url}/api/events/{event_id}/snapshot.jpg"
                filename = f"{event_id}_{label}.jpg"
                self._transfer_file_from_frigate(snapshot_url, remote_cam_dir, filename)

            # 2. Archiviazione Clip Video (se disponibile)
            if has_clip:
                clip_url = f"{self.frigate_base_url}/api/events/{event_id}/clip.mp4"
                filename = f"{event_id}_{label}.mp4"
                self._transfer_file_from_frigate(clip_url, remote_cam_dir, filename)

        t = threading.Thread(target=_archive_worker, daemon=True)
        t.start()

    def _transfer_file_from_frigate(self, download_url: str, remote_dir: str, filename: str):
        try:
            # Download contenuto dall'API interna di Frigate (molto veloce)
            logger.info("Scaricamento file evidenza da Frigate: %s", download_url)
            res = requests.get(download_url, timeout=10.0)
            if res.status_code != 200:
                logger.warning("Frigate ha risposto con HTTP %d per %s", res.status_code, download_url)
                return

            data_bytes = res.content

            # Tentativo scrittura su NAS Ugreen via SMB
            success = self._write_to_smb(remote_dir, filename, data_bytes)
            if not success:
                # Fallback di emergenza: se il NAS è spento, salviamo in locale per non perdere l'evento
                self._save_local_fallback(remote_dir, filename, data_bytes)

        except Exception as exc:
            logger.error("Errore durante l'archiviazione di %s: %s", filename, exc)

    def _write_to_smb(self, remote_dir: str, filename: str, data: bytes) -> bool:
        try:
            # Crea ricorsivamente la cartella del giorno e della telecamera sul NAS se non esiste
            try:
                smbclient.makedirs(remote_dir, exist_ok=True)
            except Exception:
                pass

            remote_file_path = f"{remote_dir}\\{filename}"
            with smbclient.open_file(remote_file_path, mode="wb") as f:
                f.write(data)

            logger.info("Evidenza salvata con successo sul NAS: %s (%d byte)", remote_file_path, len(data))
            return True

        except Exception as smb_err:
            logger.warning(
                "Impossibile scrivere su NAS Ugreen (%s). Se il NAS non è ancora acceso sul banco, è previsto: %s",
                remote_dir, smb_err
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
