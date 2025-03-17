import os
import json
import logging
import base64
from email.mime.text import MIMEText

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def handle_message(message):
    action = message.get('action')
    print(f"Commande Gmail reçue : {action}")

    if action == "send_email":
        # Ta logique d'envoi d'e-mail ici
        send_response('orchestrator', {"status": "success", "action": "send_email"})

def send_response(channel, message):
    redis_client.publish(channel, json.dumps(message))

pubsub = redis_client.pubsub()
pubsub.subscribe('agent_gmail')

print("Agent Gmail en écoute...")
for message in pubsub.listen():
    if message['type'] == 'message':
        data = json.loads(message['data'].decode('utf-8'))
        handle_message(data)


# Répertoire du module
MODULE_DIR = os.path.dirname(__file__)
# Chemins vers les fichiers d'identifiants et de token pour Gmail
CREDENTIALS_FILE = os.path.join(MODULE_DIR, "credentials_gmail.json")
TOKEN_FILE = os.path.join(MODULE_DIR, "token_gmail.json")

# Portée d'accès pour Gmail (permet de lire, modifier et envoyer des emails)
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def authenticate_gmail():
    """
    Authentifie l'accès à Gmail via OAuth 2.0.
    Charge les identifiants depuis credentials_gmail.json et le token depuis token_gmail.json.
    """
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token_file:
            token_file.write(creds.to_json())
            logging.info("Nouveau token d'authentification Gmail sauvegardé.")
    
    service = build('gmail', 'v1', credentials=creds)
    logging.info("Authentification Gmail réussie.")
    return service

def list_messages(service, query='in:inbox', max_results=10):
    """
    Liste jusqu'à max_results messages de la boîte de réception correspondant à la requête.
    Par défaut, on récupère les emails présents dans la boîte de réception.
    """
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])
        if not messages:
            logging.info("Aucun email trouvé.")
        else:
            logging.info("Emails récupérés :")
            for message in messages:
                msg = service.users().messages().get(userId='me', id=message['id']).execute()
                snippet = msg.get('snippet', '')
                logging.info(f"ID: {message['id']} - {snippet}")
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des emails: {e}")

def send_email(service, to, subject, body):
    """
    Envoie un email via l'API Gmail.
    Pour tester cette fonction, décommente l'appel dans run() et adapte les paramètres.
    """
    try:
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        message_body = {'raw': raw_message}
        sent_message = service.users().messages().send(userId='me', body=message_body).execute()
        logging.info(f"Email envoyé, ID: {sent_message['id']}")
    except Exception as e:
        logging.error(f"Erreur lors de l'envoi de l'email: {e}")

def run():
    """
    Fonction principale appelée par Alfred pour exécuter le module Gmail.
    Elle charge la configuration, s'authentifie, liste quelques messages et peut envoyer un email de test.
    """
    logging.info("Exécution du module Gmail.")
    
    # Charger la configuration depuis config.json si besoin
    config = {}
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except Exception as e:
            logging.warning(f"Impossible de charger config.json : {e}")
    
    # Vérifier si le module Gmail est activé (par défaut True)
    gmail_enabled = config.get("gmail", {}).get("enabled", True)
    if not gmail_enabled:
        logging.info("Gmail est désactivé dans la configuration.")
        return

    # Authentification et création du service Gmail
    service = authenticate_gmail()
    
    # Lister les messages de la boîte de réception
    list_messages(service, query="in:inbox", max_results=10)

    # Pour tester l'envoi d'un email, décommente et adapte cette ligne :
    # send_email(service, to="destinataire@example.com", subject="Test Alfred", body="Ceci est un test d'envoi d'email via Alfred.")

    logging.info("Fin du module Gmail.")

if __name__ == "__main__":
    # Pour test en standalone
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    run()
