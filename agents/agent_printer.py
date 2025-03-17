"""
Printer Agent - Agent de gestion des imprimantes 3D et des imprimantes papier/scanners
Ce script intègre la logique multi-agents en héritant de BaseAgent.
Il gère à la fois l'état des imprimantes 3D (FDM et résine) et des imprimantes papier standard
avec capacités de numérisation.
"""

import os
import json
import time
import threading
import subprocess
import socket
import re
import uuid
import tempfile
import datetime
from enum import Enum
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union

from base_agent import BaseAgent

# Dépendances pour les imprimantes 3D
try:
    import kasa  # Pour les prises TP-Link
    KASA_AVAILABLE = True
except ImportError:
    KASA_AVAILABLE = False

try:
    from octorest import OctoRest
    OCTOPRINT_AVAILABLE = True
except ImportError:
    OCTOPRINT_AVAILABLE = False

ANYCUBIC_API_AVAILABLE = False  # Placeholder si nécessaire

# Dépendances pour impression/numérisation
try:
    import cups  # Pour l'impression sous Linux/Raspberry Pi
    CUPS_AVAILABLE = True
except ImportError:
    CUPS_AVAILABLE = False

try:
    import win32print  # Pour l'impression sous Windows
    import win32api
    WIN32PRINT_AVAILABLE = True
except ImportError:
    WIN32PRINT_AVAILABLE = False

# Dépendances pour la numérisation
try:
    import pyinsane2  # Pour la numérisation
    PYINSANE_AVAILABLE = True
except ImportError:
    PYINSANE_AVAILABLE = False

# Dépendances pour la gestion des PDF et des documents
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter, A4
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import docx
    PYTHON_DOCX_AVAILABLE = True
except ImportError:
    PYTHON_DOCX_AVAILABLE = False

# Dépendances pour Google Drive
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

# Enum pour les types d'imprimante 3D
class PrinterType(Enum):
    FDM = "fdm"       # Imprimante à filament
    RESIN = "resin"   # Imprimante à résine

# Enum pour le statut de l'imprimante 3D
class PrinterStatus(Enum):
    OFFLINE = "offline"
    IDLE = "idle"
    PRINTING = "printing"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETE = "complete"
    UNKNOWN = "unknown"

# Enum pour les états de l'imprimante papier
class PaperPrinterStatus(Enum):
    OFFLINE = "offline"
    IDLE = "idle"
    PRINTING = "printing"
    SCANNING = "scanning"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"

# Enum pour les types de documents supportés
class DocumentType(Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    IMAGE = "image"
    UNKNOWN = "unknown"

class PaperPrinterManager:
    """
    Gestionnaire d'imprimantes papier qui s'intègre à l'Agent Printer existant.
    Gère l'impression de documents et la numérisation.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Any, redis_client: Any = None):
        """
        Initialise le gestionnaire d'imprimantes papier.
        
        Args:
            config: Configuration de l'imprimante papier
            logger: Logger de l'agent principal
            redis_client: Client Redis pour l'envoi de messages
        """
        self.config = config
        self.logger = logger
        self.redis_client = redis_client
        
        # Répertoires de travail
        self.scan_dir = config.get("scan_directory", os.path.join(os.getcwd(), "scans"))
        self.temp_dir = config.get("temp_directory", tempfile.gettempdir())
        
        # Créer les répertoires s'ils n'existent pas
        os.makedirs(self.scan_dir, exist_ok=True)
        
        # Paramètres de l'imprimante par défaut
        self.default_printer = config.get("default_printer", None)
        self.default_scanner = config.get("default_scanner", None)
        
        # Connexion aux services de print
        self.cups_conn = None
        self.printer_connection = None
        self.scanner_connection = None
        
        # Tâches en cours
        self.current_print_jobs = {}
        self.current_scan_jobs = {}
        self.job_lock = threading.Lock()
        
        # État de l'imprimante
        self.printer_status = PaperPrinterStatus.UNKNOWN
        
        # Google Drive
        self.google_drive_credentials_path = config.get("google_drive_credentials_path", None)
        self.google_drive_token_path = config.get("google_drive_token_path", None)
        self.google_drive_scopes = ['https://www.googleapis.com/auth/drive.file']
        self.google_drive_service = None
        
        # Planning des tâches automatiques
        self.scheduled_tasks = []
        self.tasks_lock = threading.Lock()
        
        # Initialisation des services
        self._init_printing_service()
        self._init_scanning_service()
        self._init_google_drive()
        
        self.logger.info("Gestionnaire d'imprimantes papier initialisé")
    
    def _init_printing_service(self) -> None:
        """
        Initialise le service d'impression selon la plateforme (Linux/Windows).
        """
        # Tentative de connexion avec CUPS (Linux/Mac)
        if CUPS_AVAILABLE:
            try:
                self.cups_conn = cups.Connection()
                printers = self.cups_conn.getPrinters()
                
                if printers:
                    if not self.default_printer or self.default_printer not in printers:
                        # Utiliser la première imprimante disponible comme imprimante par défaut
                        self.default_printer = list(printers.keys())[0]
                    
                    self.printer_status = PaperPrinterStatus.IDLE
                    self.logger.info(f"Service CUPS connecté. Imprimante par défaut : {self.default_printer}")
                else:
                    self.logger.warning("Aucune imprimante trouvée via CUPS")
                    self.printer_status = PaperPrinterStatus.OFFLINE
            except Exception as e:
                self.logger.error(f"Erreur lors de l'initialisation de CUPS : {e}")
                self.cups_conn = None
                self.printer_status = PaperPrinterStatus.ERROR
        
        # Tentative de connexion avec win32print (Windows)
        elif WIN32PRINT_AVAILABLE:
            try:
                # Obtenir la liste des imprimantes
                printers = [printer[2] for printer in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)]
                
                if printers:
                    if not self.default_printer or self.default_printer not in printers:
                        # Utiliser l'imprimante par défaut de Windows
                        self.default_printer = win32print.GetDefaultPrinter()
                    
                    self.printer_status = PaperPrinterStatus.IDLE
                    self.logger.info(f"Service Windows Print connecté. Imprimante par défaut : {self.default_printer}")
                else:
                    self.logger.warning("Aucune imprimante trouvée via win32print")
                    self.printer_status = PaperPrinterStatus.OFFLINE
            except Exception as e:
                self.logger.error(f"Erreur lors de l'initialisation de win32print : {e}")
                self.printer_status = PaperPrinterStatus.ERROR
        else:
            self.logger.warning("Aucun service d'impression disponible (ni CUPS ni win32print)")
            self.printer_status = PaperPrinterStatus.OFFLINE
    
    def _init_scanning_service(self) -> None:
        """
        Initialise le service de numérisation.
        """
        if PYINSANE_AVAILABLE:
            try:
                # Initialiser pyinsane2
                pyinsane2.init()
                
                # Lister les périphériques de numérisation disponibles
                devices = pyinsane2.get_devices()
                
                if devices:
                    if not self.default_scanner or self.default_scanner not in [dev.name for dev in devices]:
                        # Utiliser le premier scanner disponible
                        self.default_scanner = devices[0].name
                    
                    self.logger.info(f"Service de numérisation connecté. Scanner par défaut : {self.default_scanner}")
                else:
                    self.logger.warning("Aucun scanner trouvé via pyinsane2")
            except Exception as e:
                self.logger.error(f"Erreur lors de l'initialisation de pyinsane2 : {e}")
        else:
            self.logger.warning("pyinsane2 non disponible, la numérisation ne sera pas possible")
    
    def _init_google_drive(self) -> None:
        """
        Initialise la connexion à Google Drive si les informations d'identification sont disponibles.
        """
        if not GOOGLE_API_AVAILABLE:
            self.logger.warning("Les bibliothèques Google API ne sont pas disponibles")
            return
        
        if not self.google_drive_credentials_path or not self.google_drive_token_path:
            self.logger.warning("Informations d'identification Google Drive non configurées")
            return
        
        creds = None
        
        # Charger les jetons existants
        if os.path.exists(self.google_drive_token_path):
            try:
                creds = Credentials.from_authorized_user_info(
                    json.load(open(self.google_drive_token_path, 'r')),
                    self.google_drive_scopes
                )
            except Exception as e:
                self.logger.error(f"Erreur lors du chargement des jetons Google Drive : {e}")
        
        # Si aucun jeton valide n'est disponible, demander à l'utilisateur de se connecter
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    self.logger.error(f"Erreur lors du rafraîchissement des jetons Google Drive : {e}")
                    creds = None
            
            if not creds:
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.google_drive_credentials_path, self.google_drive_scopes)
                    creds = flow.run_local_server(port=0)
                    
                    # Sauvegarder les jetons pour une utilisation future
                    with open(self.google_drive_token_path, 'w') as token:
                        token.write(creds.to_json())
                except Exception as e:
                    self.logger.error(f"Erreur lors de l'authentification Google Drive : {e}")
                    return
        
        try:
            # Créer le service Google Drive
            self.google_drive_service = build('drive', 'v3', credentials=creds)
            self.logger.info("Connexion à Google Drive établie avec succès")
        except Exception as e:
            self.logger.error(f"Erreur lors de la création du service Google Drive : {e}")
    
    def get_printers(self) -> List[Dict[str, Any]]:
        """
        Récupère la liste des imprimantes disponibles.
        
        Returns:
            Liste des imprimantes avec leurs propriétés
        """
        printers = []
        
        if CUPS_AVAILABLE and self.cups_conn:
            try:
                cups_printers = self.cups_conn.getPrinters()
                for name, props in cups_printers.items():
                    printers.append({
                        "name": name,
                        "info": props.get("printer-info", ""),
                        "location": props.get("printer-location", ""),
                        "make_and_model": props.get("printer-make-and-model", ""),
                        "state": props.get("printer-state", 0),
                        "is_default": name == self.default_printer
                    })
            except Exception as e:
                self.logger.error(f"Erreur lors de la récupération des imprimantes CUPS : {e}")
        
        elif WIN32PRINT_AVAILABLE:
            try:
                win_printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
                for _, _, name, _ in win_printers:
                    # Obtenir plus d'informations sur l'imprimante (Windows API limité en infos)
                    is_default = name == win32print.GetDefaultPrinter()
                    printers.append({
                        "name": name,
                        "info": name,
                        "location": "Local",
                        "make_and_model": "Non disponible",
                        "state": 0,  # État inconnu dans l'API simple
                        "is_default": is_default
                    })
            except Exception as e:
                self.logger.error(f"Erreur lors de la récupération des imprimantes Windows : {e}")
        
        return printers
    
    def get_scanners(self) -> List[Dict[str, Any]]:
        """
        Récupère la liste des scanners disponibles.
        
        Returns:
            Liste des scanners avec leurs propriétés
        """
        scanners = []
        
        if PYINSANE_AVAILABLE:
            try:
                devices = pyinsane2.get_devices()
                for device in devices:
                    scanners.append({
                        "name": device.name,
                        "vendor": getattr(device, "vendor", "Unknown"),
                        "model": getattr(device, "model", "Unknown"),
                        "is_default": device.name == self.default_scanner
                    })
            except Exception as e:
                self.logger.error(f"Erreur lors de la récupération des scanners : {e}")
        
        return scanners
    
    def get_paper_printer_status(self) -> Dict[str, Any]:
        """
        Récupère l'état actuel de l'imprimante papier.
        
        Returns:
            État actuel et informations supplémentaires
        """
        status_info = {
            "status": self.printer_status.value,
            "default_printer": self.default_printer,
            "default_scanner": self.default_scanner,
            "print_jobs_count": len(self.current_print_jobs),
            "scan_jobs_count": len(self.current_scan_jobs),
            "cups_available": CUPS_AVAILABLE,
            "win32print_available": WIN32PRINT_AVAILABLE,
            "scanning_available": PYINSANE_AVAILABLE,
            "google_drive_available": self.google_drive_service is not None
        }
        
        # Obtenir des informations supplémentaires selon le service d'impression
        if CUPS_AVAILABLE and self.cups_conn and self.default_printer:
            try:
                # Récupérer l'état de l'imprimante par défaut
                printer_info = self.cups_conn.getPrinterAttributes(self.default_printer)
                status_info["printer_info"] = {
                    "state": printer_info.get("printer-state", 0),
                    "state_message": printer_info.get("printer-state-message", ""),
                    "is_accepting_jobs": printer_info.get("printer-is-accepting-jobs", False)
                }
            except Exception as e:
                self.logger.error(f"Erreur lors de la récupération de l'état de l'imprimante CUPS : {e}")
        
        return status_info
    
    def print_file(self, file_path: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Imprime un fichier.
        
        Args:
            file_path: Chemin vers le fichier à imprimer
            options: Options d'impression (imprimante, copies, etc.)
        
        Returns:
            Informations sur la tâche d'impression
        """
        if not os.path.exists(file_path):
            return {"success": False, "error": f"Le fichier {file_path} n'existe pas"}
        
        # Vérifier si le chemin est autorisé (sécurité)
        if not self._is_path_allowed(file_path):
            return {"success": False, "error": "Accès au fichier non autorisé pour des raisons de sécurité"}
        
        options = options or {}
        printer_name = options.get("printer", self.default_printer)
        copies = options.get("copies", 1)
        
        # Déterminer le type de document
        document_type = self._get_document_type(file_path)
        
        # Créer un ID de tâche unique
        job_id = str(uuid.uuid4())
        timestamp = time.time()
        
        # Mettre à jour l'état de l'imprimante
        self.printer_status = PaperPrinterStatus.PRINTING
        
        # Préparer le document si nécessaire (conversion)
        prepared_file = file_path
        if document_type == DocumentType.DOCX and not self._can_print_directly(document_type):
            prepared_file = self._convert_docx_to_pdf(file_path)
        elif document_type == DocumentType.TXT and not self._can_print_directly(document_type):
            prepared_file = self._convert_txt_to_pdf(file_path)
        elif document_type == DocumentType.IMAGE and not self._can_print_directly(document_type):
            prepared_file = self._convert_image_to_pdf(file_path)
        
        # Enregistrer les informations sur la tâche d'impression
        with self.job_lock:
            self.current_print_jobs[job_id] = {
                "file_path": file_path,
                "prepared_file": prepared_file,
                "printer": printer_name,
                "start_time": timestamp,
                "status": "pending",
                "options": options,
                "document_type": document_type.value
            }
        
        # Démarrer l'impression dans un thread séparé
        thread = threading.Thread(
            target=self._print_job_thread,
            args=(job_id, prepared_file, printer_name, copies, options)
        )
        thread.daemon = True
        thread.start()
        
        # Journaliser l'action
        self.logger.info(f"Tâche d'impression {job_id} démarrée pour {file_path} sur {printer_name}")
        
        return {
            "success": True,
            "job_id": job_id,
            "message": f"Impression de {os.path.basename(file_path)} en cours",
            "start_time": timestamp
        }
    
    def _print_job_thread(self, job_id: str, file_path: str, printer_name: str, 
                          copies: int, options: Dict[str, Any]) -> None:
        """
        Thread d'exécution d'une tâche d'impression.
        
        Args:
            job_id: Identifiant de la tâche
            file_path: Chemin vers le fichier à imprimer
            printer_name: Nom de l'imprimante
            copies: Nombre de copies
            options: Options d'impression
        """
        try:
            with self.job_lock:
                if job_id in self.current_print_jobs:
                    self.current_print_jobs[job_id]["status"] = "processing"
            
            # Imprimer selon le système disponible
            if CUPS_AVAILABLE and self.cups_conn:
                # Impression avec CUPS (Linux)
                cups_options = {
                    "copies": str(copies)
                }
                # Ajouter d'autres options si spécifiées (recto-verso, etc.)
                if "duplex" in options:
                    cups_options["sides"] = "two-sided-long-edge" if options["duplex"] else "one-sided"
                if "media" in options:
                    cups_options["media"] = options["media"]
                
                # Lancer l'impression
                cups_job_id = self.cups_conn.printFile(
                    printer_name,
                    file_path,
                    os.path.basename(file_path),
                    cups_options
                )
                
                # Mettre à jour la tâche avec l'ID CUPS
                with self.job_lock:
                    if job_id in self.current_print_jobs:
                        self.current_print_jobs[job_id]["cups_job_id"] = cups_job_id
                
                # Attendre que la tâche soit terminée (facultatif)
                try:
                    # Boucle pour vérifier l'état de la tâche
                    while True:
                        jobs = self.cups_conn.getJobs()
                        if cups_job_id not in jobs:
                            break
                        time.sleep(1)
                except Exception as e:
                    self.logger.error(f"Erreur lors du suivi de la tâche CUPS {cups_job_id}: {e}")
            
            elif WIN32PRINT_AVAILABLE:
                # Impression avec win32print (Windows)
                try:
                    # Ouvrir l'imprimante
                    handle = win32print.OpenPrinter(printer_name)
                    
                    # Configurer les options d'impression
                    dev_mode = win32print.GetPrinter(handle, 2)["pDevMode"]
                    dev_mode.Copies = copies
                    
                    # Soumettre le document à l'imprimante
                    win32print.StartDocPrinter(handle, 1, (os.path.basename(file_path), None, "RAW"))
                    
                    # Lire et envoyer le fichier
                    with open(file_path, "rb") as f:
                        data = f.read()
                        win32print.StartPagePrinter(handle)
                        win32print.WritePrinter(handle, data)
                        win32print.EndPagePrinter(handle)
                    
                    # Terminer le document
                    win32print.EndDocPrinter(handle)
                    win32print.ClosePrinter(handle)
                except Exception as e:
                    self.logger.error(f"Erreur lors de l'impression Windows : {e}")
                    raise
            
            else:
                # Solution de repli avec une commande système
                if os.name == "posix":  # Linux/Mac
                    cmd = ["lp", "-d", printer_name, "-n", str(copies), file_path]
                    subprocess.run(cmd, check=True)
                else:  # Windows
                    cmd = ["print", "/d:" + printer_name, file_path]
                    subprocess.run(cmd, shell=True, check=True)
            
            # Marquer la tâche comme terminée
            with self.job_lock:
                if job_id in self.current_print_jobs:
                    self.current_print_jobs[job_id]["status"] = "completed"
                    self.current_print_jobs[job_id]["end_time"] = time.time()
            
            self.logger.info(f"Tâche d'impression {job_id} terminée avec succès")
        
        except Exception as e:
            # Marquer la tâche comme échouée
            with self.job_lock:
                if job_id in self.current_print_jobs:
                    self.current_print_jobs[job_id]["status"] = "failed"
                    self.current_print_jobs[job_id]["error"] = str(e)
                    self.current_print_jobs[job_id]["end_time"] = time.time()
            
            self.logger.error(f"Erreur lors de l'impression {job_id}: {e}")
        
        finally:
            # Nettoyer les fichiers temporaires si nécessaire
            original_file = file_path
            with self.job_lock:
                if job_id in self.current_print_jobs:
                    original_file = self.current_print_jobs[job_id]["file_path"]
            
            if file_path != original_file and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    self.logger.warning(f"Impossible de supprimer le fichier temporaire {file_path}: {e}")
            
            # Mettre à jour l'état de l'imprimante si aucune autre tâche n'est en cours
            with self.job_lock:
                active_jobs = sum(1 for job in self.current_print_jobs.values() 
                                if job["status"] in ["pending", "processing"])
                if active_jobs == 0:
                    self.printer_status = PaperPrinterStatus.IDLE
    
    def scan_document(self, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Numérise un document depuis le scanner.
        
        Args:
            options: Options de numérisation (résolution, format, etc.)
        
        Returns:
            Informations sur la tâche de numérisation
        """
        if not PYINSANE_AVAILABLE:
            return {"success": False, "error": "Service de numérisation non disponible"}
        
        options = options or {}
        scanner_name = options.get("scanner", self.default_scanner)
        resolution = options.get("resolution", 300)  # DPI
        mode = options.get("mode", "Color")
        format = options.get("format", "pdf")
        output_path = options.get("output_path")
        upload_to_drive = options.get("upload_to_drive", False)
        drive_folder_id = options.get("drive_folder_id")
        
        # Si aucun chemin de sortie n'est spécifié, en créer un dans le répertoire de scan
        if not output_path:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(self.scan_dir, f"scan_{timestamp}.{format}")
        
        # Créer un ID de tâche unique
        job_id = str(uuid.uuid4())
        timestamp = time.time()
        
        # Mettre à jour l'état du scanner
        self.printer_status = PaperPrinterStatus.SCANNING
        
        # Enregistrer les informations sur la tâche de numérisation
        with self.job_lock:
            self.current_scan_jobs[job_id] = {
                "scanner": scanner_name,
                "start_time": timestamp,
                "status": "pending",
                "options": options,
                "output_path": output_path,
                "upload_to_drive": upload_to_drive,
                "drive_folder_id": drive_folder_id
            }
        
        # Démarrer la numérisation dans un thread séparé
        thread = threading.Thread(
            target=self._scan_job_thread,
            args=(job_id, scanner_name, resolution, mode, format, output_path, upload_to_drive, drive_folder_id)
        )
        thread.daemon = True
        thread.start()
        
        # Journaliser l'action
        self.logger.info(f"Tâche de numérisation {job_id} démarrée avec {scanner_name}")
        
        return {
            "success": True,
            "job_id": job_id,
            "message": "Numérisation en cours",
            "output_path": output_path,
            "start_time": timestamp
        }
    
    def _scan_job_thread(self, job_id: str, scanner_name: str, resolution: int, 
                          mode: str, format: str, output_path: str, 
                          upload_to_drive: bool, drive_folder_id: Optional[str]) -> None:
        """
        Thread d'exécution d'une tâche de numérisation.
        
        Args:
            job_id: Identifiant de la tâche
            scanner_name: Nom du scanner
            resolution: Résolution en DPI
            mode: Mode de numérisation (Couleur, N&B, etc.)
            format: Format de sortie (pdf, jpg, etc.)
            output_path: Chemin du fichier de sortie
            upload_to_drive: Si True, téléverse le fichier sur Google Drive
            drive_folder_id: ID du dossier Google Drive (facultatif)
        """
        try:
            # Mettre à jour le statut de la tâche
            with self.job_lock:
                if job_id in self.current_scan_jobs:
                    self.current_scan_jobs[job_id]["status"] = "processing"
            
            # Obtenir le périphérique de numérisation
            devices = pyinsane2.get_devices()
            device = None
            
            for dev in devices:
                if dev.name == scanner_name:
                    device = dev
                    break
            
            if not device:
                raise ValueError(f"Scanner {scanner_name} non trouvé")
            
            # Configurer les options de numérisation
            device.options['resolution'].value = resolution
            
            # Mode de numérisation
            if 'mode' in device.options:
                if mode in device.options['mode'].constraint:
                    device.options['mode'].value = mode
                else:
                    # Mode par défaut si non disponible
                    self.logger.warning(f"Mode {mode} non disponible, utilisation du mode par défaut")
            
            # Lancer la numérisation
            scan_session = device.scan(multiple=False)
            
            # Récupérer l'image numérisée
            try:
                scan_session.scan.read()
                image = scan_session.images[0]
                
                # Enregistrer l'image dans le format demandé
                if format.lower() == 'pdf':
                    if PIL_AVAILABLE and REPORTLAB_AVAILABLE:
                        # Convertir l'image en PDF
                        pil_image = Image.frombytes(
                            "RGB",
                            (image.width, image.height),
                            image.get_image().tobytes()
                        )
                        pil_image.save(output_path + '.tmp', 'JPEG')
                        
                        # Créer un PDF avec reportlab
                        c = canvas.Canvas(output_path, pagesize=(image.width, image.height))
                        c.drawImage(output_path + '.tmp', 0, 0, image.width, image.height)
                        c.save()
                        
                        # Supprimer l'image temporaire
                        if os.path.exists(output_path + '.tmp'):
                            os.remove(output_path + '.tmp')
                    else:
                        self.logger.error("PIL ou ReportLab non disponibles, impossible de créer un PDF")
                        # Utiliser une commande système comme solution de repli
                        if os.name == "posix":  # Linux/Mac
                            subprocess.run(["convert", output_path + '.tmp', output_path], check=True)
                        else:
                            raise ValueError("Impossible de créer un PDF sans PIL et ReportLab")
                else:
                    # Autres formats (JPEG, PNG, etc.)
                    pil_image = Image.frombytes(
                        "RGB",
                        (image.width, image.height),
                        image.get_image().tobytes()
                    )
                    pil_image.save(output_path, format.upper())
                
                # Mettre à jour le statut de la tâche
                with self.job_lock:
                    if job_id in self.current_scan_jobs:
                        self.current_scan_jobs[job_id]["status"] = "completed"
                        self.current_scan_jobs[job_id]["end_time"] = time.time()
                
                self.logger.info(f"Numérisation terminée avec succès, fichier enregistré dans {output_path}")
                
                # Téléverser sur Google Drive si demandé
                if upload_to_drive and self.google_drive_service:
                    self._upload_to_google_drive(output_path, drive_folder_id, job_id)
            except Exception as e:
                self.logger.error(f"Erreur pendant la numérisation : {e}")
                raise
        
        except Exception as e:
            # Marquer la tâche comme échouée
            with self.job_lock:
                if job_id in self.current_scan_jobs:
                    self.current_scan_jobs[job_id]["status"] = "failed"
                    self.current_scan_jobs[job_id]["error"] = str(e)
                    self.current_scan_jobs[job_id]["end_time"] = time.time()
            
            self.logger.error(f"Erreur lors de la numérisation {job_id}: {e}")
        
        finally:
            # Mettre à jour l'état de l'imprimante si aucune autre tâche n'est en cours
            with self.job_lock:
                active_jobs = sum(1 for job in self.current_scan_jobs.values() 
                                if job["status"] in ["pending", "processing"])
                if active_jobs == 0:
                    self.printer_status = PaperPrinterStatus.IDLE
            
            # Finalisation pour libérer les ressources du scanner
            try:
                pyinsane2.exit()
            except Exception:
                pass
    
    def _upload_to_google_drive(self, file_path: str, folder_id: Optional[str], 
                               job_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Téléverse un fichier sur Google Drive.
        
        Args:
            file_path: Chemin vers le fichier à téléverser
            folder_id: ID du dossier Google Drive (facultatif)
            job_id: ID de la tâche associée (facultatif)
        
        Returns:
            Informations sur le téléversement
        """
        if not self.google_drive_service:
            return {"success": False, "error": "Service Google Drive non disponible"}
        
        try:
            # Mettre à jour le statut de la tâche
            if job_id:
                with self.job_lock:
                    if job_id in self.current_scan_jobs:
                        self.current_scan_jobs[job_id]["drive_upload_status"] = "uploading"
            
            file_metadata = {
                'name': os.path.basename(file_path)
            }
            
            # Spécifier le dossier parent si un ID de dossier est fourni
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            # Obtenir le type MIME en fonction de l'extension du fichier
            mime_type = self._get_mime_type(file_path)
            
            # Créer l'objet MediaFileUpload
            media = MediaFileUpload(
                file_path,
                mimetype=mime_type,
                resumable=True
            )
            
            # Téléverser le fichier
            file = self.google_drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,webViewLink'
            ).execute()
            
            # Mettre à jour le statut de la tâche
            if job_id:
                with self.job_lock:
                    if job_id in self.current_scan_jobs:
                        self.current_scan_jobs[job_id]["drive_upload_status"] = "completed"
                        self.current_scan_jobs[job_id]["drive_file_id"] = file.get('id')
                        self.current_scan_jobs[job_id]["drive_file_link"] = file.get('webViewLink')
            
            self.logger.info(f"Fichier {file_path} téléversé sur Google Drive avec succès, ID: {file.get('id')}")
            
            return {
                "success": True,
                "file_id": file.get('id'),
                "file_name": file.get('name'),
                "web_link": file.get('webViewLink')
            }
        
        except Exception as e:
            # Mettre à jour le statut de la tâche
            if job_id:
                with self.job_lock:
                    if job_id in self.current_scan_jobs:
                        self.current_scan_jobs[job_id]["drive_upload_status"] = "failed"
                        self.current_scan_jobs[job_id]["drive_upload_error"] = str(e)
            
            self.logger.error(f"Erreur lors du téléversement du fichier {file_path} sur Google Drive: {e}")
            
            return {"success": False, "error": str(e)}
    
    def get_job_status(self, job_id: str, job_type: str = "print") -> Dict[str, Any]:
        """
        Vérifie l'état d'une tâche d'impression ou de numérisation.
        
        Args:
            job_id: ID de la tâche
            job_type: Type de tâche ("print" ou "scan")
        
        Returns:
            État actuel de la tâche
        """
        with self.job_lock:
            if job_type.lower() == "print" and job_id in self.current_print_jobs:
                return {
                    "success": True,
                    "job_id": job_id,
                    "job_type": "print",
                    "status": self.current_print_jobs[job_id]["status"],
                    "details": self.current_print_jobs[job_id]
                }
            elif job_type.lower() == "scan" and job_id in self.current_scan_jobs:
                return {
                    "success": True,
                    "job_id": job_id,
                    "job_type": "scan",
                    "status": self.current_scan_jobs[job_id]["status"],
                    "details": self.current_scan_jobs[job_id]
                }
            else:
                return {"success": False, "error": f"Tâche {job_id} non trouvée"}
    
    def download_from_google_drive(self, file_id: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Télécharge un fichier depuis Google Drive.
        
        Args:
            file_id: ID du fichier sur Google Drive
            output_path: Chemin où enregistrer le fichier (facultatif)
        
        Returns:
            Informations sur le téléchargement
        """
        if not self.google_drive_service:
            return {"success": False, "error": "Service Google Drive non disponible"}
        
        try:
            # Obtenir les métadonnées du fichier
            file_metadata = self.google_drive_service.files().get(fileId=file_id).execute()
            file_name = file_metadata.get('name', f"driveFile_{file_id}")
            
            # Si aucun chemin de sortie n'est spécifié, en créer un dans le répertoire temporaire
            if not output_path:
                output_path = os.path.join(self.temp_dir, file_name)
            
            # Télécharger le fichier
            request = self.google_drive_service.files().get_media(fileId=file_id)
            
            with open(output_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            
            self.logger.info(f"Fichier téléchargé depuis Google Drive avec succès, chemin: {output_path}")
            
            return {
                "success": True,
                "file_path": output_path,
                "file_name": file_name
            }
        
        except Exception as e:
            self.logger.error(f"Erreur lors du téléchargement du fichier {file_id} depuis Google Drive: {e}")
            return {"success": False, "error": str(e)}
    
    def schedule_print_job(self, file_path: str, schedule_time: float, 
                           options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Planifie une tâche d'impression pour une exécution ultérieure.
        
        Args:
            file_path: Chemin vers le fichier à imprimer
            schedule_time: Timestamp Unix pour l'exécution
            options: Options d'impression
        
        Returns:
            Informations sur la tâche planifiée
        """
        if not os.path.exists(file_path):
            return {"success": False, "error": f"Le fichier {file_path} n'existe pas"}
        
        options = options or {}
        task_id = str(uuid.uuid4())
        
        with self.tasks_lock:
            self.scheduled_tasks.append({
                "task_id": task_id,
                "task_type": "print",
                "file_path": file_path,
                "options": options,
                "schedule_time": schedule_time,
                "created_at": time.time(),
                "status": "scheduled"
            })
        
        self.logger.info(f"Tâche d'impression planifiée pour le fichier {file_path} à {schedule_time}")
        
        return {
            "success": True,
            "task_id": task_id,
            "schedule_time": schedule_time,
            "message": f"Impression de {os.path.basename(file_path)} planifiée"
        }
    
    def schedule_scan_job(self, schedule_time: float, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Planifie une tâche de numérisation pour une exécution ultérieure.
        
        Args:
            schedule_time: Timestamp Unix pour l'exécution
            options: Options de numérisation
        
        Returns:
            Informations sur la tâche planifiée
        """
        options = options or {}
        task_id = str(uuid.uuid4())
        
        with self.tasks_lock:
            self.scheduled_tasks.append({
                "task_id": task_id,
                "task_type": "scan",
                "options": options,
                "schedule_time": schedule_time,
                "created_at": time.time(),
                "status": "scheduled"
            })
        
        self.logger.info(f"Tâche de numérisation planifiée pour {schedule_time}")
        
        return {
            "success": True,
            "task_id": task_id,
            "schedule_time": schedule_time,
            "message": "Numérisation planifiée"
        }
    
    def check_scheduled_tasks(self) -> None:
        """
        Vérifie et exécute les tâches planifiées qui doivent être exécutées.
        Cette méthode doit être appelée régulièrement depuis l'agent principal.
        """
        current_time = time.time()
        executed_tasks = []
        
        with self.tasks_lock:
            for task in self.scheduled_tasks:
                if task["status"] == "scheduled" and task["schedule_time"] <= current_time:
                    # Exécuter la tâche
                    try:
                        if task["task_type"] == "print":
                            self.logger.info(f"Exécution de la tâche d'impression planifiée {task['task_id']}")
                            result = self.print_file(task["file_path"], task["options"])
                            task["result"] = result
                            task["status"] = "executed"
                        elif task["task_type"] == "scan":
                            self.logger.info(f"Exécution de la tâche de numérisation planifiée {task['task_id']}")
                            result = self.scan_document(task["options"])
                            task["result"] = result
                            task["status"] = "executed"
                        
                        executed_tasks.append(task)
                    except Exception as e:
                        self.logger.error(f"Erreur lors de l'exécution de la tâche planifiée {task['task_id']}: {e}")
                        task["status"] = "failed"
                        task["error"] = str(e)
        
        # Retourner les tâches exécutées pour notification à l'orchestrateur
        return executed_tasks
    
    def cleanup_old_jobs(self, max_age: int = 86400) -> None:
        """
        Nettoie les anciennes tâches terminées des journaux.
        
        Args:
            max_age: Âge maximum en secondes (par défaut 24 heures)
        """
        current_time = time.time()
        
        with self.job_lock:
            # Nettoyer les tâches d'impression
            completed_statuses = ["completed", "failed"]
            for job_id in list(self.current_print_jobs.keys()):
                job = self.current_print_jobs[job_id]
                if (job["status"] in completed_statuses and 
                    "end_time" in job and 
                    current_time - job["end_time"] > max_age):
                    del self.current_print_jobs[job_id]
            
            # Nettoyer les tâches de numérisation
            for job_id in list(self.current_scan_jobs.keys()):
                job = self.current_scan_jobs[job_id]
                if (job["status"] in completed_statuses and 
                    "end_time" in job and 
                    current_time - job["end_time"] > max_age):
                    del self.current_scan_jobs[job_id]
        
        with self.tasks_lock:
            # Nettoyer les tâches planifiées
            for task in list(self.scheduled_tasks):
                if (task["status"] in ["executed", "failed"] and 
                    current_time - task.get("execution_time", task["created_at"]) > max_age):
                    self.scheduled_tasks.remove(task)
    
    # Méthodes utilitaires privées
    
    def _get_document_type(self, file_path: str) -> DocumentType:
        """
        Détermine le type de document en fonction de l'extension du fichier.
        
        Args:
            file_path: Chemin vers le fichier
        
        Returns:
            Type de document (enum DocumentType)
        """
        _, ext = os.path.splitext(file_path)
        ext = ext.lower().strip(".")
        
        if ext == "pdf":
            return DocumentType.PDF
        elif ext == "docx":
            return DocumentType.DOCX
        elif ext == "txt":
            return DocumentType.TXT
        elif ext in ["jpg", "jpeg", "png", "bmp", "tiff", "tif", "gif"]:
            return DocumentType.IMAGE
        else:
            return DocumentType.UNKNOWN
    
    def _can_print_directly(self, document_type: DocumentType) -> bool:
        """
        Vérifie si un type de document peut être imprimé directement sans conversion.
        
        Args:
            document_type: Type de document
        
        Returns:
            True si le document peut être imprimé directement
        """
        # PDF peut toujours être imprimé directement
        if document_type == DocumentType.PDF:
            return True
        
        # Vérifier selon le système d'exploitation et le service d'impression
        if CUPS_AVAILABLE and self.cups_conn:
            # CUPS peut généralement gérer tous les types de documents
            return True
        elif WIN32PRINT_AVAILABLE:
            # Windows peut avoir des limitations pour certains formats
            # Par mesure de précaution, seulement PDF, TXT et DOCX directement
            return document_type in [DocumentType.PDF, DocumentType.TXT]
        
        # Par défaut, convertir en PDF pour plus de sécurité
        return False
    
    def _convert_docx_to_pdf(self, docx_path: str) -> str:
        """
        Convertit un fichier DOCX en PDF pour l'impression.
        
        Args:
            docx_path: Chemin vers le fichier DOCX
        
        Returns:
            Chemin vers le fichier PDF généré
        """
        if not PYTHON_DOCX_AVAILABLE or not REPORTLAB_AVAILABLE:
            raise ValueError("python-docx ou reportlab non disponible pour la conversion DOCX vers PDF")
        
        # Créer un nom de fichier temporaire pour le PDF
        pdf_path = os.path.join(self.temp_dir, f"{os.path.splitext(os.path.basename(docx_path))[0]}_{int(time.time())}.pdf")
        
        try:
            # Ouvrir le document DOCX
            doc = docx.Document(docx_path)
            
            # Créer un PDF avec reportlab
            c = canvas.Canvas(pdf_path, pagesize=letter)
            
            # Position initiale du texte
            y = 750
            
            # Parcourir chaque paragraphe et l'ajouter au PDF
            for para in doc.paragraphs:
                text = para.text
                if text:
                    c.drawString(50, y, text)
                    y -= 12
                    
                    # Vérifier si nous devons créer une nouvelle page
                    if y < 50:
                        c.showPage()
                        y = 750
            
            # Sauvegarder le PDF
            c.save()
            
            self.logger.info(f"Conversion DOCX vers PDF réussie: {docx_path} -> {pdf_path}")
            return pdf_path
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la conversion DOCX vers PDF: {e}")
            raise
    
    def _convert_txt_to_pdf(self, txt_path: str) -> str:
        """
        Convertit un fichier TXT en PDF pour l'impression.
        
        Args:
            txt_path: Chemin vers le fichier TXT
        
        Returns:
            Chemin vers le fichier PDF généré
        """
        if not REPORTLAB_AVAILABLE:
            raise ValueError("reportlab non disponible pour la conversion TXT vers PDF")
        
        # Créer un nom de fichier temporaire pour le PDF
        pdf_path = os.path.join(self.temp_dir, f"{os.path.splitext(os.path.basename(txt_path))[0]}_{int(time.time())}.pdf")
        
        try:
            # Lire le fichier texte
            with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                text_content = f.readlines()
            
            # Créer un PDF avec reportlab
            c = canvas.Canvas(pdf_path, pagesize=letter)
            
            # Position initiale du texte
            y = 750
            
            # Ajouter chaque ligne au PDF
            for line in text_content:
                line = line.rstrip('\n')
                c.drawString(50, y, line)
                y -= 12
                
                # Vérifier si nous devons créer une nouvelle page
                if y < 50:
                    c.showPage()
                    y = 750
            
            # Sauvegarder le PDF
            c.save()
            
            self.logger.info(f"Conversion TXT vers PDF réussie: {txt_path} -> {pdf_path}")
            return pdf_path
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la conversion TXT vers PDF: {e}")
            raise
    
    def _convert_image_to_pdf(self, image_path: str) -> str:
        """
        Convertit une image en PDF pour l'impression.
        
        Args:
            image_path: Chemin vers le fichier image
        
        Returns:
            Chemin vers le fichier PDF généré
        """
        if not PIL_AVAILABLE or not REPORTLAB_AVAILABLE:
            raise ValueError("PIL ou reportlab non disponible pour la conversion Image vers PDF")
        
        # Créer un nom de fichier temporaire pour le PDF
        pdf_path = os.path.join(self.temp_dir, f"{os.path.splitext(os.path.basename(image_path))[0]}_{int(time.time())}.pdf")
        
        try:
            # Ouvrir l'image avec PIL
            img = Image.open(image_path)
            
            # Déterminer les dimensions de l'image
            width, height = img.size
            
            # Créer un PDF avec reportlab
            c = canvas.Canvas(pdf_path, pagesize=(width, height))
            
            # Ajouter l'image au PDF
            c.drawImage(image_path, 0, 0, width, height)
            
            # Sauvegarder le PDF
            c.save()
            
            self.logger.info(f"Conversion Image vers PDF réussie: {image_path} -> {pdf_path}")
            return pdf_path
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la conversion Image vers PDF: {e}")
            raise
    
    def _is_path_allowed(self, file_path: str) -> bool:
        """
        Vérifie si un chemin de fichier est autorisé pour des raisons de sécurité.
        
        Args:
            file_path: Chemin à vérifier
        
        Returns:
            True si le chemin est autorisé
        """
        # Liste des répertoires autorisés
        allowed_directories = self.config.get("allowed_directories", [])
        # Ajouter les répertoires par défaut
        allowed_directories.extend([self.temp_dir, self.scan_dir])
        
        # Vérifier si le chemin est dans un répertoire autorisé
        real_path = os.path.realpath(file_path)
        return any(real_path.startswith(os.path.realpath(allowed_dir)) for allowed_dir in allowed_directories)
    
    def _get_mime_type(self, file_path: str) -> str:
        """
        Détermine le type MIME d'un fichier en fonction de son extension.
        
        Args:
            file_path: Chemin vers le fichier
        
        Returns:
            Type MIME du fichier
        """
        mime_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.txt': 'text/plain',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.bmp': 'image/bmp',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
            '.gif': 'image/gif'
        }
        
        _, ext = os.path.splitext(file_path)
        return mime_types.get(ext.lower(), 'application/octet-stream')


class PrinterAgent(BaseAgent):
    """Agent de gestion des imprimantes 3D et papier, intégrant la communication multi-agents."""
    
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379,
                 config_file: Optional[str] = None):
        super().__init__("printer", redis_host, redis_port)
        self.capabilities = [
            "printer_control",
            "print_job_management",
            "power_management",
            "status_monitoring"
        ]
        # Charger la configuration (vous pouvez préciser un chemin dans config_file)
        self.config = self._load_config(config_file)
        
        # Dictionnaire des imprimantes et travaux
        self.printers: Dict[str, Any] = {}
        self.print_jobs: Dict[str, Any] = {}
        self.printer_lock = threading.Lock()
        self.jobs_lock = threading.Lock()
        
        # Connexions aux API des imprimantes (ex: OctoPrint, Anycubic, etc.)
        self.printer_connections: Dict[str, Any] = {}
        
        # Tâches planifiées
        self.scheduled_tasks = []
        self.tasks_lock = threading.Lock()
        
        self._init_printers()
        
        # Initialiser le gestionnaire d'imprimantes papier
        self._init_paper_printer_manager()
        
        # Pour planifier les vérifications périodiques
        self.scheduler_running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        
        self.logger.info(f"PrinterAgent initialisé avec {len(self.printers)} imprimante(s) 3D et imprimantes papier")
    
    def _init_paper_printer_manager(self):
        """
        Initialise le gestionnaire d'imprimantes papier.
        Cette méthode doit être appelée dans __init__ de PrinterAgent.
        """
        # Configuration pour l'imprimante papier
        paper_printer_config = self.config.get("paper_printer", {})
        
        self.paper_printer_manager = PaperPrinterManager(paper_printer_config, self.logger, self.redis_client)
        self.capabilities.extend([
            "paper_printing",
            "document_scanning",
            "google_drive_integration"
        ])
        
        self.logger.info("Gestionnaire d'imprimantes papier initialisé")
    
    def _load_config(self, config_file: Optional[str]) -> Dict[str, Any]:
        default_config = {
            "printers": [],
            "power_devices": {},
            "auto_shutdown": True,
            "polling_interval": 30,  # en secondes
            "paper_printer": {
                "default_printer": None,
                "default_scanner": None,
                "scan_directory": os.path.join(os.getcwd(), "scans"),
                "temp_directory": tempfile.gettempdir(),
                "allowed_directories": [],
                "google_drive_credentials_path": None,
                "google_drive_token_path": None
            }
        }
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
                self.logger.info(f"Configuration chargée depuis {config_file}")
                return config.get("printing", default_config)
            except Exception as e:
                self.logger.error(f"Erreur lors du chargement de la configuration: {e}")
                return default_config
        else:
            self.logger.warning("Aucun fichier de configuration spécifique trouvé, utilisation des valeurs par défaut")
            return default_config
    
    def _init_printer_connection(self, printer_id: str, config: Dict[str, Any]) -> None:
        """Initialise la connexion à une imprimante 3D en fonction de son type et de sa configuration."""
        printer_type = config.get("type", "").lower()
        connection_type = config.get("connection_type", "").lower()
        if printer_type == PrinterType.FDM.value and connection_type == "octoprint" and OCTOPRINT_AVAILABLE:
            api_url = config.get("api_url", "")
            api_key = config.get("api_key", "")
            if api_url and api_key:
                try:
                    client = OctoRest(url=api_url, apikey=api_key)
                    self.printer_connections[printer_id] = {"client": client, "type": "octoprint"}
                    with self.printer_lock:
                        self.printers[printer_id]["connected"] = True
                        self.printers[printer_id]["status"] = PrinterStatus.IDLE.value
                    self.logger.info(f"Connexion OctoPrint établie pour {printer_id}")
                except Exception as e:
                    self.logger.error(f"Erreur de connexion OctoPrint pour {printer_id}: {e}")
        elif printer_type == PrinterType.RESIN.value and connection_type == "anycubic":
            ip_address = config.get("ip_address", "")
            if ip_address and self._ping_device(ip_address):
                self.printer_connections[printer_id] = {"ip_address": ip_address, "type": "anycubic"}
                with self.printer_lock:
                    self.printers[printer_id]["connected"] = True
                    self.printers[printer_id]["status"] = PrinterStatus.IDLE.value
                self.logger.info(f"Imprimante Anycubic configurée pour {printer_id}")
            else:
                self.logger.error(f"Imprimante {printer_id} non accessible sur le réseau")
    
    def _ping_device(self, ip_address: str, timeout: int = 2) -> bool:
        """Vérifie si un appareil est accessible via un ping."""
        try:
            if os.name == "nt":
                response = subprocess.call(["ping", "-n", "1", "-w", str(timeout * 1000), ip_address],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                response = subprocess.call(["ping", "-c", "1", "-W", str(timeout), ip_address],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return response == 0
        except Exception:
            return False
    
    def on_start(self) -> None:
        """Démarre l'agent d'impression 3D et papier."""
        self.broadcast_message("agent_online", {
            "agent_type": "printer", 
            "capabilities": self.capabilities
        })
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities,
            "printers_count": len(self.printers)
        })
        self.scheduler_running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        self.setup_redis_listener()
        self.logger.info("PrinterAgent démarré")
    
    def on_stop(self) -> None:
        """Arrête l'agent d'impression 3D et papier."""
        self.scheduler_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=2)
        
        # Arrêter l'écoute Redis
        if hasattr(self, 'redis_pubsub'):
            self.redis_pubsub.unsubscribe()
            
        self.broadcast_message("agent_offline", {"agent_type": "printer", "shutdown_time": time.time()})
        self.logger.info("PrinterAgent arrêté")
    
    def _scheduler_loop(self) -> None:
        """Boucle pour exécuter périodiquement les tâches planifiées."""
        polling_interval = self.config.get("polling_interval", 30)
        last_check = 0
        last_cleanup = 0
        
        while self.scheduler_running:
            now = time.time()
            
            # Vérifier l'état des imprimantes 3D
            if now - last_check >= polling_interval:
                self._check_all_printers_status()
                last_check = now
            
            # Vérifier les tâches planifiées (imprimantes 3D)
            with self.tasks_lock:
                for task in list(self.scheduled_tasks):
                    if now >= task.get("execution_time", 0):
                        try:
                            if task["task_type"] == "check_print_complete":
                                self._check_print_completion(task["task_data"].get("printer_id"),
                                                             task["task_data"].get("job_id"))
                        except Exception as e:
                            self.logger.error(f"Erreur lors de l'exécution de la tâche: {e}")
                        self.scheduled_tasks.remove(task)
            
            # Vérifier les tâches planifiées (imprimantes papier)
            executed_tasks = self.paper_printer_manager.check_scheduled_tasks()
            if executed_tasks:
                for task in executed_tasks:
                    task_id = task.get("task_id")
                    task_type = task.get("task_type")
                    self.logger.info(f"Tâche {task_type} planifiée {task_id} exécutée")
            
            # Nettoyer périodiquement les anciennes tâches (toutes les 1h)
            if now - last_cleanup >= 3600:  # 3600 secondes = 1 heure
                self.paper_printer_manager.cleanup_old_jobs()
                last_cleanup = now
            
            time.sleep(1)
    
    def _check_all_printers_status(self) -> None:
        """Vérifie l'état de toutes les imprimantes 3D configurées."""
        for printer_id in list(self.printers.keys()):
            try:
                self.check_printer_status(printer_id)
            except Exception as e:
                self.logger.error(f"Erreur lors de la vérification de {printer_id}: {e}")
    
    def check_printer_status(self, printer_id: str) -> Dict[str, Any]:
        """Vérifie et retourne l'état d'une imprimante 3D."""
        if printer_id not in self.printers:
            return {"success": False, "error": f"Imprimante {printer_id} non trouvée"}
        if printer_id in self.printer_connections:
            connection = self.printer_connections[printer_id]
            if connection.get("type") == "octoprint":
                return self._check_octoprint_status(printer_id, connection)
            elif connection.get("type") == "anycubic":
                # Pour Anycubic, on peut simplement vérifier la connexion via ping
                reachable = self._ping_device(connection.get("ip_address", ""))
                with self.printer_lock:
                    self.printers[printer_id]["status"] = PrinterStatus.IDLE.value if reachable else PrinterStatus.OFFLINE.value
                    self.printers[printer_id]["last_update"] = time.time()
                return {"success": True, "printer_id": printer_id, "status": self.printers[printer_id]["status"]}
        # Si aucune connexion spécifique, on retourne UNKNOWN
        with self.printer_lock:
            self.printers[printer_id]["status"] = PrinterStatus.UNKNOWN.value
        return {"success": True, "printer_id": printer_id, "status": PrinterStatus.UNKNOWN.value}
    
    def _check_octoprint_status(self, printer_id: str, connection: Dict[str, Any]) -> Dict[str, Any]:
        """Vérifie l'état d'une imprimante via OctoPrint."""
        try:
            client = connection.get("client")
            printer_data = client.printer()
            job_data = client.job_info()
            
            if printer_data.get("state", {}).get("flags", {}).get("printing"):
                status = PrinterStatus.PRINTING.value
            elif printer_data.get("state", {}).get("flags", {}).get("paused"):
                status = PrinterStatus.PAUSED.value
            elif printer_data.get("state", {}).get("flags", {}).get("error"):
                status = PrinterStatus.ERROR.value
            elif printer_data.get("state", {}).get("flags", {}).get("operational"):
                status = PrinterStatus.IDLE.value
            else:
                status = PrinterStatus.UNKNOWN.value
            
            with self.printer_lock:
                self.printers[printer_id]["status"] = status
                self.printers[printer_id]["last_update"] = time.time()
                self.printers[printer_id]["connected"] = True
            
            return {"success": True, "printer_id": printer_id, "status": status}
        except Exception as e:
            self.logger.error(f"Erreur OctoPrint pour {printer_id}: {e}")
            with self.printer_lock:
                self.printers[printer_id]["status"] = PrinterStatus.ERROR.value
                self.printers[printer_id]["last_update"] = time.time()
            return {"success": False, "printer_id": printer_id, "error": str(e)}
    
    def _check_print_completion(self, printer_id: str, job_id: str) -> None:
        """Vérifie si une impression 3D est terminée et effectue les actions nécessaires."""
        self.logger.info(f"Vérification de l'achèvement de l'impression {job_id} sur {printer_id}")
        # À implémenter selon les besoins
    
    def _schedule_task(self, task_type: str, task_data: Dict[str, Any], execution_time: float) -> str:
        """Planifie une tâche 3D et retourne son ID."""
        task_id = f"{task_type}_{int(time.time())}_{hash(str(task_data)) % 10000}"
        task = {
            "task_id": task_id, 
            "task_type": task_type, 
            "task_data": task_data, 
            "execution_time": execution_time, 
            "created_at": time.time()
        }
        with self.tasks_lock:
            self.scheduled_tasks.append(task)
        self.logger.info(f"Tâche {task_type} planifiée pour {datetime.fromtimestamp(execution_time)}")
        return task_id
    
    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite une commande reçue par PrinterAgent.
        Les commandes supportées incluent les commandes pour imprimantes 3D et papier.
        """
        cmd_type = command.get("type", "unknown")
        data = command.get("data", {})
        self.logger.info(f"Traitement de la commande: {cmd_type}")
        
        # Vérifier d'abord si c'est une commande pour l'imprimante papier
        paper_printer_result = self.process_paper_printer_command(command)
        if paper_printer_result is not None:
            return paper_printer_result
        
        # Sinon, traiter comme une commande d'imprimante 3D
        if cmd_type in ["get_printer_status", "get_printer_status_printer"]:
            printer_id = data.get("printer_id")
            return self.check_printer_status(printer_id) if printer_id else self._check_all_printers_status()
        
        elif cmd_type in ["start_print", "start_print_printer"]:
            printer_id = data.get("printer_id")
            file_path = data.get("file_path")
            options = data.get("options", {})
            if not printer_id or not file_path:
                return {"success": False, "error": "ID d'imprimante et chemin de fichier requis"}
            return self.start_print(printer_id, file_path, options)
        
        elif cmd_type in ["cancel_print", "cancel_print_printer"]:
            printer_id = data.get("printer_id")
            if not printer_id:
                return {"success": False, "error": "ID d'imprimante requis"}
            return self.cancel_print(printer_id)
        
        elif cmd_type in ["pause_print", "pause_print_printer"]:
            printer_id = data.get("printer_id")
            if not printer_id:
                return {"success": False, "error": "ID d'imprimante requis"}
            return self.pause_print(printer_id)
        
        elif cmd_type in ["resume_print", "resume_print_printer"]:
            printer_id = data.get("printer_id")
            if not printer_id:
                return {"success": False, "error": "ID d'imprimante requis"}
            return self.resume_print(printer_id)
        
        elif cmd_type in ["connect_printer", "connect_printer_printer"]:
            printer_id = data.get("printer_id")
            if not printer_id:
                return {"success": False, "error": "ID d'imprimante requis"}
            return self.connect_printer(printer_id)
        
        elif cmd_type == "status_request":
            return {
                "status": "ready", 
                "capabilities": self.capabilities, 
                "printers_count": len(self.printers),
                "paper_printer_status": self.paper_printer_manager.get_paper_printer_status()
            }
        
        else:
            self.logger.warning(f"Commande non supportée: {cmd_type}")
            return {"success": False, "message": f"Commande non supportée: {cmd_type}"}
    
    def process_paper_printer_command(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Traite une commande spécifique à l'imprimante papier.
        
        Args:
            command: Commande à traiter
        
        Returns:
            Résultat de l'exécution de la commande ou None si la commande n'est pas pour l'imprimante papier
        """
        cmd_type = command.get("type", "unknown")
        data = command.get("data", {})
        
        # Commandes liées à l'impression papier
        if cmd_type in ["print_document", "print_document_printer"]:
            file_path = data.get("file_path")
            options = data.get("options", {})
            
            if not file_path:
                return {"success": False, "error": "Chemin du fichier non spécifié"}
            
            return self.paper_printer_manager.print_file(file_path, options)
        
        # Commandes liées à la numérisation
        elif cmd_type in ["scan_document", "scan_document_printer"]:
            options = data.get("options", {})
            return self.paper_printer_manager.scan_document(options)
        
        # Commandes liées à Google Drive
        elif cmd_type in ["upload_to_drive", "upload_to_drive_printer"]:
            file_path = data.get("file_path")
            folder_id = data.get("folder_id")
            
            if not file_path:
                return {"success": False, "error": "Chemin du fichier non spécifié"}
            
            return self.paper_printer_manager.upload_to_google_drive(file_path, folder_id)
        
        elif cmd_type in ["download_from_drive", "download_from_drive_printer"]:
            file_id = data.get("file_id")
            output_path = data.get("output_path")
            
            if not file_id:
                return {"success": False, "error": "ID de fichier Google Drive non spécifié"}
            
            return self.paper_printer_manager.download_from_google_drive(file_id, output_path)
        
        # Commandes liées à la planification
        elif cmd_type in ["schedule_print", "schedule_print_printer"]:
            file_path = data.get("file_path")
            schedule_time = data.get("schedule_time")
            options = data.get("options", {})
            
            if not file_path or not schedule_time:
                return {"success": False, "error": "Paramètres manquants pour la planification"}
            
            return self.paper_printer_manager.schedule_print_job(file_path, schedule_time, options)
        
        elif cmd_type in ["schedule_scan", "schedule_scan_printer"]:
            schedule_time = data.get("schedule_time")
            options = data.get("options", {})
            
            if not schedule_time:
                return {"success": False, "error": "Heure de planification non spécifiée"}
            
            return self.paper_printer_manager.schedule_scan_job(schedule_time, options)
        
        # Commandes liées à l'état et aux informations
        elif cmd_type in ["get_paper_printer_status", "get_paper_printer_status_printer"]:
            return self.paper_printer_manager.get_paper_printer_status()
        
        elif cmd_type in ["get_printers_list", "get_printers_list_printer"]:
            return {"success": True, "printers": self.paper_printer_manager.get_printers()}
        
        elif cmd_type in ["get_scanners_list", "get_scanners_list_printer"]:
            return {"success": True, "scanners": self.paper_printer_manager.get_scanners()}
        
        elif cmd_type in ["get_job_status", "get_job_status_printer"]:
            job_id = data.get("job_id")
            job_type = data.get("job_type", "print")
            
            if not job_id:
                return {"success": False, "error": "ID de tâche non spécifié"}
            
            return self.paper_printer_manager.get_job_status(job_id, job_type)
        
        else:
            # Cette commande n'est pas reconnue comme une commande d'imprimante papier
            return None
    
    def setup_redis_listener(self):
        """Configure et démarre l'écoute des messages Redis pour l'agent."""
        self.redis_pubsub = self.redis_client.pubsub()
        self.redis_pubsub.subscribe(f"{self.agent_id}:notifications")
        self.redis_listener_thread = threading.Thread(target=self._redis_listener_loop, daemon=True)
        self.redis_listener_thread.start()
        self.logger.info(f"Agent {self.agent_id} en écoute sur le canal {self.agent_id}:notifications")
    
    def _redis_listener_loop(self):
        """Boucle d'écoute infinie pour les messages Redis."""
        if not self.redis_client:
            self.logger.error("Redis non connecté, impossible de démarrer l'écoute")
            return
        
        self.logger.info(f"Démarrage de la boucle d'écoute Redis pour {self.agent_id}")
        
        try:
            for message in self.redis_pubsub.listen():
                if not self.running:
                    break
                    
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        self.logger.info(f"Message Redis reçu: {data.get('type', 'unknown')}")
                        self._handle_redis_message(data)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Erreur décodage JSON du message Redis: {e}")
                    except Exception as e:
                        self.logger.error(f"Erreur traitement message Redis: {e}")
        except Exception as e:
            self.logger.error(f"Erreur dans la boucle d'écoute Redis: {e}")
        finally:
            self.logger.info("Arrêt de la boucle d'écoute Redis")
    
    def _handle_redis_message(self, message):
        """Traite un message reçu via Redis."""
        msg_type = message.get('type', 'unknown')
        data = message.get('data', {})
        
        self.logger.info(f"Traitement message Redis: {msg_type}")
        
        # Traiter d'abord les messages spécifiques à l'imprimante papier
        paper_printer_handled = self._handle_redis_message_paper_printer(message)
        if paper_printer_handled:
            return
        
        # Actions spécifiques selon le type de message pour l'imprimante 3D
        if msg_type == 'direct_command':
            # Traiter les commandes directes
            if 'command' in data:
                command = data['command']
                self.process_command(command)
        elif msg_type == 'printer_status_request':
            # Vérifier l'état d'une imprimante 3D
            printer_id = data.get('printer_id')
            reply_to = data.get('reply_to', 'orchestrator')
            
            if printer_id:
                result = self.check_printer_status(printer_id)
            else:
                result = {'success': False, 'error': 'ID d\'imprimante non spécifié'}
                
            self.send_redis_message(f"{reply_to}:notifications", 'printer_status_result', result)
        elif msg_type == 'start_print_request':
            # Démarrer une impression 3D
            printer_id = data.get('printer_id')
            file_path = data.get('file_path')
            options = data.get('options', {})
            reply_to = data.get('reply_to', 'orchestrator')
            
            if printer_id and file_path:
                result = self.process_command({
                    "type": "start_print", 
                    "data": {
                        "printer_id": printer_id,
                        "file_path": file_path,
                        "options": options
                    }
                })
            else:
                result = {'success': False, 'error': 'ID d\'imprimante ou chemin de fichier manquant'}
                
            self.send_redis_message(f"{reply_to}:notifications", 'print_job_result', result)
        elif msg_type == 'notification':
            # Traiter les notifications
            self.log_activity('redis_notification', data)
        else:
            self.logger.warning(f"Type de message Redis non reconnu: {msg_type}")
    
    def _handle_redis_message_paper_printer(self, message: Dict[str, Any]) -> bool:
        """
        Traite les messages Redis spécifiques à l'imprimante papier.
        
        Args:
            message: Message Redis à traiter
        
        Returns:
            True si le message a été traité, False sinon
        """
        msg_type = message.get('type', 'unknown')
        data = message.get('data', {})
        
        # Messages liés à l'impression papier
        if msg_type == 'print_document_request':
            file_path = data.get('file_path')
            options = data.get('options', {})
            reply_to = data.get('reply_to', 'orchestrator')
            
            if file_path:
                result = self.paper_printer_manager.print_file(file_path, options)
                self.send_redis_message(f"{reply_to}:notifications", 'print_document_result', result)
                return True
        
        # Messages liés à la numérisation
        elif msg_type == 'scan_document_request':
            options = data.get('options', {})
            reply_to = data.get('reply_to', 'orchestrator')
            
            result = self.paper_printer_manager.scan_document(options)
            self.send_redis_message(f"{reply_to}:notifications", 'scan_document_result', result)
            return True
        
        # Messages liés à Google Drive
        elif msg_type == 'upload_to_drive_request':
            file_path = data.get('file_path')
            folder_id = data.get('folder_id')
            reply_to = data.get('reply_to', 'orchestrator')
            
            if file_path:
                result = self.paper_printer_manager.upload_to_google_drive(file_path, folder_id)
                self.send_redis_message(f"{reply_to}:notifications", 'upload_to_drive_result', result)
                return True
        
        elif msg_type == 'download_from_drive_request':
            file_id = data.get('file_id')
            output_path = data.get('output_path')
            reply_to = data.get('reply_to', 'orchestrator')
            
            if file_id:
                result = self.paper_printer_manager.download_from_google_drive(file_id, output_path)
                self.send_redis_message(f"{reply_to}:notifications", 'download_from_drive_result', result)
                return True
        
        # Ce n'est pas un message d'imprimante papier
        return False
    
    def send_redis_message(self, channel, message_type, data):
        """Envoie un message via Redis sur un canal spécifique."""
        if not self.redis_client:
            self.logger.warning("Redis non connecté, message non envoyé")
            return False
        
        message = {
            'type': message_type,
            'sender': self.agent_id,
            'timestamp': time.time(),
            'data': data
        }
        
        try:
            self.redis_client.publish(channel, json.dumps(message))
            self.logger.info(f"Message Redis envoyé sur {channel}: {message_type}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur envoi message Redis: {e}")
            return False
    
    def log_activity(self, activity_type: str, details: Dict[str, Any]) -> None:
        """Enregistre une activité dans les logs via BaseAgent."""
        self.logger.info(f"Activité [{activity_type}]: {details}")

    # Méthodes d'impression 3D (à compléter si nécessaire)
    def start_print(self, printer_id: str, file_path: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Démarre une impression 3D."""
        # Implémentation à compléter
        return {"success": True, "message": f"Impression 3D démarrée sur {printer_id}"}
    
    def cancel_print(self, printer_id: str) -> Dict[str, Any]:
        """Annule une impression 3D en cours."""
        # Implémentation à compléter
        return {"success": True, "message": f"Impression 3D annulée sur {printer_id}"}
    
    def pause_print(self, printer_id: str) -> Dict[str, Any]:
        """Met en pause une impression 3D en cours."""
        # Implémentation à compléter
        return {"success": True, "message": f"Impression 3D mise en pause sur {printer_id}"}
    
    def resume_print(self, printer_id: str) -> Dict[str, Any]:
        """Reprend une impression 3D en pause."""
        # Implémentation à compléter
        return {"success": True, "message": f"Impression 3D reprise sur {printer_id}"}
    
    def connect_printer(self, printer_id: str) -> Dict[str, Any]:
        """Connecte une imprimante 3D."""
        # Implémentation à compléter
        return {"success": True, "message": f"Imprimante 3D {printer_id} connectée"}


if __name__ == "__main__":
    # Test en standalone du PrinterAgent
    agent = PrinterAgent(config_file="alfred/config/config.json")
    agent.start()
    
    # Exemple de commande : obtenir l'état d'une imprimante 3D
    test_command_3d = {
        "type": "get_printer_status",
        "data": {
            "printer_id": "printer1"
        }
    }
    response_3d = agent.process_command(test_command_3d)
    print("Test imprimante 3D:", response_3d)
    
    # Exemple de commande : imprimer un document papier
    test_command_paper = {
        "type": "print_document",
        "data": {
            "file_path": "test_document.pdf",
            "options": {
                "copies": 1
            }
        }
    }
    response_paper = agent.process_command(test_command_paper)
    print("Test imprimante papier:", response_paper)
    
    agent.stop()
s(self) -> None:
        """Initialise les imprimantes 3D à partir de la configuration."""
        for printer_config in self.config.get("printers", []):
            printer_id = printer_config.get("id")
            if not printer_id:
                continue
            with self.printer_lock:
                self.printers[printer_id] = {
                    "config": printer_config,
                    "status": PrinterStatus.UNKNOWN.value,
                    "current_job": None,
                    "last_update": time.time(),
                    "connected": False,
                    "error": None
                }
            # Initialiser la connexion selon le type
            self._init_printer_connection(printer_id, printer_config)
    
    def _init_printer