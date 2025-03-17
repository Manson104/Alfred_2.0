import os
import json
import logging
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def send_response(channel, message):
    redis_client.publish(channel, json.dumps(message))

def handle_message(message):
    print(f"Commande Google Drive reçue : {message}")
    action = message.get('action')
    filename = message.get('filename', '')

    if action == "upload":
        # Ta logique upload ici
        send_response('orchestrator', {"status": "success", "action": "upload", "file": filename})

    elif action == "download":
        # Ta logique download ici
        send_response('orchestrator', {"status": "success", "action": "download", "file": filename})

    else:
        send_response('orchestrator', {"status": "error", "message": "Action inconnue"})

pubsub = redis_client.pubsub()
pubsub.subscribe('agent_drive')

print("Agent Google Drive en écoute...")
for message in pubsub.listen():
    if message['type'] == 'message':
        data = json.loads(message['data'].decode('utf-8'))
        handle_message(data)


# On définit des constantes pour pointer vers les fichiers JSON dans le même dossier que ce script
MODULE_DIR = os.path.dirname(__file__)
CREDENTIALS_FILE = os.path.join(MODULE_DIR, "credentials_drive.json")  # Identifiants OAuth (client secret)
TOKEN_FILE = os.path.join(MODULE_DIR, "token_drive.json")             # Jeton OAuth stocké localement

def authenticate_google_drive():
    """Authentifie l'accès à Google Drive via PyDrive en utilisant des fichiers séparés pour credentials et token."""
    gauth = GoogleAuth()

    # Charge la config client depuis credentials_drive.json
    gauth.LoadClientConfigFile(CREDENTIALS_FILE)

    # Vérifie si un token Drive existe déjà (token_drive.json). Si oui, on peut l'utiliser directement.
    if os.path.exists(TOKEN_FILE):
        gauth.LoadCredentialsFile(TOKEN_FILE)
        if gauth.credentials is None or gauth.access_token_expired:
            # Si le token est expiré ou invalide, on tente de le rafraîchir
            if gauth.refresh_token is None:
                # Pas de refresh token, on doit réauthentifier
                gauth.LocalWebserverAuth()
            else:
                gauth.Refresh()
    else:
        # Pas de token local, on lance le flow OAuth dans un navigateur local
        gauth.LocalWebserverAuth()

    # Sauvegarde le token (même si on l'a rafraîchi)
    gauth.SaveCredentialsFile(TOKEN_FILE)
    logging.info("Authentification à Google Drive réussie.")

    return GoogleDrive(gauth)

def upload_file(drive, file_path, folder_id=""):
    """Upload un fichier vers Google Drive dans le dossier spécifié."""
    if not os.path.exists(file_path):
        logging.error(f"Fichier introuvable : {file_path}")
        return
    file_name = os.path.basename(file_path)
    file_metadata = {"title": file_name}
    if folder_id:
        file_metadata["parents"] = [{"id": folder_id}]
    file = drive.CreateFile(file_metadata)
    file.SetContentFile(file_path)
    file.Upload()
    logging.info(f"Fichier uploadé : {file_name}")

def list_drive_files(drive, folder_id=""):
    """Liste les fichiers présents sur Google Drive dans le dossier donné (ou racine si non spécifié)."""
    query = f"'{folder_id}' in parents and trashed=false" if folder_id else "trashed=false"
    file_list = drive.ListFile({"q": query}).GetList()
    logging.info("Liste des fichiers sur Google Drive :")
    for file in file_list:
        logging.info(f"{file['title']} (ID: {file['id']})")
    return file_list

def auto_upload(drive, folder_id=""):
    """Upload automatique des fichiers présents dans le dossier backups/."""
    backup_folder = "backups/"
    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)
        logging.info(f"Création du dossier backups : {backup_folder}")
    for file_name in os.listdir(backup_folder):
        file_path = os.path.join(backup_folder, file_name)
        if os.path.isfile(file_path):
            upload_file(drive, file_path, folder_id)

def rotate_backups():
    """
    Rotation des sauvegardes : conserve uniquement les 10 dernières sauvegardes.
    Cette fonctionnalité peut être affinée en fonction des critères souhaités (date, taille, etc.).
    """
    backup_folder = "backups/"
    if not os.path.exists(backup_folder):
        return
    files = [os.path.join(backup_folder, f) for f in os.listdir(backup_folder) if os.path.isfile(os.path.join(backup_folder, f))]
    # Tri des fichiers par date de modification décroissante
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    # Suppression des fichiers au-delà des 10 plus récents
    for file_path in files[10:]:
        try:
            os.remove(file_path)
            logging.info(f"Fichier supprimé lors de la rotation : {os.path.basename(file_path)}")
        except Exception as e:
            logging.error(f"Erreur lors de la suppression de {file_path} : {e}")

def run():
    """
    Fonction principale appelée par Alfred pour exécuter le module Google Drive.
    Elle charge la configuration, authentifie l'accès, liste les fichiers, 
    effectue l'upload automatique et procède à la rotation des sauvegardes.
    """
    logging.info("Exécution du module Google Drive.")

    # Charger la configuration depuis config.json si besoin
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
    # Ajuste le chemin si tu as mis config.json ailleurs
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except Exception as e:
            logging.warning(f"Impossible de charger config.json : {e}")

    # Vérifier si le module Google Drive est activé
    drive_enabled = config.get("google_drive", {}).get("enabled", True)
    folder_id = config.get("google_drive", {}).get("folder_id", "")
    if not drive_enabled:
        logging.info("Google Drive est désactivé dans la configuration.")
        return

    # Authentification
    try:
        drive = authenticate_google_drive()
    except Exception as e:
        logging.error(f"Erreur d'authentification Google Drive : {e}")
        return

    # Lister les fichiers présents sur Google Drive
    list_drive_files(drive, folder_id)
    # Upload automatique des fichiers du dossier backups/
    auto_upload(drive, folder_id)
    # Rotation des sauvegardes
    rotate_backups()

    logging.info("Fin du module Google Drive.")

if __name__ == "__main__":
    # Pour test en standalone
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    run()
