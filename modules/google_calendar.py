import os
import json
import logging

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

MODULE_DIR = os.path.dirname(__file__)
CREDENTIALS_FILE = os.path.join(MODULE_DIR, "credentials_calendar.json")  # Identifiants OAuth
TOKEN_FILE = os.path.join(MODULE_DIR, "token_calendar.json")             # Jeton d’authentification

SCOPES = ['https://www.googleapis.com/auth/calendar']

def authenticate_google_calendar():
    """Authentifie l'accès à Google Calendar en utilisant credentials_calendar.json et token_calendar.json."""
    creds = None

    # Si on a déjà un token, on tente de le charger
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # S'il n'y a pas de token ou qu'il n'est pas valide, on lance le flow OAuth
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # On sauvegarde le nouveau token
        with open(TOKEN_FILE, 'w') as token_file:
            token_file.write(creds.to_json())
            logging.info("Nouveau token d'authentification Calendar sauvegardé.")
    
    service = build('calendar', 'v3', credentials=creds)
    logging.info("Authentification Google Calendar réussie.")
    return service
    
    pubsub.subscribe('agent_agenda')

def list_upcoming_events(service, max_results=10):
    """Liste les événements à venir sur Google Agenda."""
    try:
        events_result = service.events().list(
            calendarId='primary',
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
            # timeMin peut être ajouté si besoin, ex: timeMin=datetime.utcnow().isoformat() + 'Z'
        ).execute()

        events = events_result.get('items', [])
        
        if not events:
            logging.info("Aucun événement à venir trouvé.")
        else:
            logging.info(f"Prochains événements (max {max_results}) :")
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'Sans titre')
                logging.info(f"- {start} : {summary}")
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des événements : {e}")

def create_event(service, summary, start_time, end_time):
    """
    Crée un événement sur le Google Agenda principal.
    Exemple de date/heure : "2025-03-10T10:00:00-07:00"
    """
    event_body = {
        'summary': summary,
        'start': {
            'dateTime': start_time
        },
        'end': {
            'dateTime': end_time
        }
    }
    try:
        event = service.events().insert(calendarId='primary', body=event_body).execute()
        logging.info(f"Événement créé : {event.get('htmlLink')}")
    except Exception as e:
        logging.error(f"Erreur lors de la création de l'événement : {e}")

def run():
    """Fonction principale appelée par Alfred pour exécuter le module Google Agenda."""
    logging.info("Exécution du module Google Agenda.")

    # Charger la configuration depuis config.json si besoin
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except Exception as e:
            logging.warning(f"Impossible de charger config.json : {e}")
    
    # Vérifier si le module Google Calendar est activé
    calendar_enabled = config.get("google_calendar", {}).get("enabled", True)
    if not calendar_enabled:
        logging.info("Google Calendar est désactivé dans la configuration.")
        return

    # Authentification
    service = authenticate_google_calendar()

    # Lister les prochains événements (5 dans l'exemple)
    list_upcoming_events(service, max_results=5)

    # Exemple pour créer un événement :
    # create_event(service, "Test Alfred", "2025-03-10T10:00:00-07:00", "2025-03-10T11:00:00-07:00")

    logging.info("Fin du module Google Agenda.")

if __name__ == "__main__":
    # Pour test en standalone
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    run()
