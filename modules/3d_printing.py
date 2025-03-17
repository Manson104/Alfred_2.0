import os
import json
import logging
import requests
import time
import threading
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def handle_message(message):
    action = message.get('action')
    file = message.get('file', '')

    if action == "start_print":
        # Ta logique pour démarrer une impression 3D
        send_response('orchestrator', {"status": "success", "action": "start_3d_print", "file": file})

def send_response(channel, message):
    redis_client.publish(channel, json.dumps(message))

pubsub = redis_client.pubsub()
pubsub.subscribe('agent_3d_printing')

print("Agent Impression 3D en écoute...")
for message in pubsub.listen():
    if message['type'] == 'message':
        data = json.loads(message['data'].decode('utf-8'))
        handle_message(data)


# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("3DPrinting")

def load_config():
    """
    Charge la configuration spécifique au module 3D Printing depuis config.json.
    Le fichier config.json doit inclure une section "3d_printing", par exemple :
    
    "3d_printing": {
      "enabled": true,
      "octoprint_url": "http://192.168.1.100",
      "api_key": "YOUR_API_KEY",
      "status_interval": 10  // intervalle en secondes pour surveiller l'état
    }
    """
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
    if not os.path.exists(config_path):
        logger.warning("Fichier de configuration non trouvé pour le module 3D Printing.")
        return {}
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        return config.get("3d_printing", {})
    except Exception as e:
        logger.error(f"Erreur lors du chargement de la configuration 3D Printing : {e}")
        return {}

class OctoPrintClient:
    def __init__(self, url, api_key, status_interval=10):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.headers = {"X-Api-Key": self.api_key, "Content-Type": "application/json"}
        self.status_interval = status_interval
        self.current_state = None
        self.monitor_thread = None
        self.monitor_running = False

    def get_printer_status(self):
        """
        Récupère le statut de l'imprimante via l'API OctoPrint.
        Retourne un dictionnaire ou None en cas d'erreur.
        """
        try:
            response = requests.get(f"{self.url}/api/printer", headers=self.headers, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Erreur lors de la récupération du statut: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Exception lors de la récupération du statut: {e}")
            return None

    def start_print_job(self, file_name):
        """
        Démarre une impression.
        Ici, nous simulons le démarrage d'une impression.
        Dans une implémentation réelle, le fichier à imprimer doit être uploadé et sélectionné.
        """
        payload = {"command": "start"}
        try:
            response = requests.post(f"{self.url}/api/job", headers=self.headers, json=payload, timeout=5)
            if response.status_code == 204:
                logger.info("Impression démarrée avec succès.")
                return True
            else:
                logger.error(f"Erreur lors du démarrage de l'impression: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Exception lors du démarrage de l'impression: {e}")
            return False

    def cancel_print_job(self):
        """
        Annule l'impression en cours.
        """
        payload = {"command": "cancel"}
        try:
            response = requests.post(f"{self.url}/api/job", headers=self.headers, json=payload, timeout=5)
            if response.status_code == 204:
                logger.info("Impression annulée avec succès.")
                return True
            else:
                logger.error(f"Erreur lors de l'annulation de l'impression: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Exception lors de l'annulation de l'impression: {e}")
            return False

    def monitor_print_status(self):
        """
        Surveille l'état de l'impression en temps réel.
        Si l'état change (par exemple, fin d'impression ou erreur), envoie une notification.
        """
        logger.info("Début de la surveillance de l'état d'impression.")
        while self.monitor_running:
            status = self.get_printer_status()
            if status:
                # Par exemple, on suppose que le statut d'impression se trouve dans status['state']
                new_state = status.get("state", "unknown")
                if new_state != self.current_state:
                    logger.info(f"Changement d'état détecté: {self.current_state} -> {new_state}")
                    self.current_state = new_state
                    self.notify_status_change(new_state)
            time.sleep(self.status_interval)
        logger.info("Surveillance de l'état d'impression terminée.")

    def start_monitoring(self):
        """
        Lance le thread de surveillance de l'état d'impression.
        """
        if not self.monitor_running:
            self.monitor_running = True
            self.monitor_thread = threading.Thread(target=self.monitor_print_status, daemon=True)
            self.monitor_thread.start()

    def stop_monitoring(self):
        """
        Arrête le thread de surveillance.
        """
        self.monitor_running = False
        if self.monitor_thread:
            self.monitor_thread.join()

    def notify_status_change(self, new_state):
        """
        Envoie une notification (simulée ici par un log) lors d'un changement d'état.
        Cette fonction peut être étendue pour envoyer un email, SMS ou notification push.
        """
        logger.info(f"Notification: l'état de l'imprimante est maintenant '{new_state}'.")


def run():
    """
    Fonction principale appelée par Alfred pour exécuter le module 3D Printing.
    Propose une interface CLI pour vérifier le statut, démarrer, annuler une impression,
    et surveiller l'état en temps réel.
    """
    logger.info("Exécution du module 3D Printing.")
    config = load_config()
    if not config.get("enabled", True):
        logger.info("Module 3D Printing désactivé dans la configuration.")
        return

    octoprint_url = config.get("octoprint_url", "")
    api_key = config.get("api_key", "")
    status_interval = config.get("status_interval", 10)

    if not octoprint_url or not api_key:
        logger.error("Configuration invalide pour 3D Printing: octoprint_url et api_key sont requis.")
        return

    client = OctoPrintClient(octoprint_url, api_key, status_interval)
    client.start_monitoring()  # Démarrage de la surveillance en temps réel

    try:
        while True:
            print("\n--- Module 3D Printing ---")
            print("1. Vérifier le statut de l'imprimante")
            print("2. Démarrer une impression")
            print("3. Annuler l'impression en cours")
            print("4. Quitter")
            choice = input("Choisissez une option : ").strip()

            if choice == "1":
                status = client.get_printer_status()
                if status:
                    print("Statut de l'imprimante :")
                    print(json.dumps(status, indent=4))
                else:
                    print("Impossible de récupérer le statut de l'imprimante.")
            elif choice == "2":
                file_name = input("Entrez le nom du fichier à imprimer : ").strip()
                success = client.start_print_job(file_name)
                if success:
                    print("Impression démarrée.")
                else:
                    print("Échec du démarrage de l'impression.")
            elif choice == "3":
                success = client.cancel_print_job()
                if success:
                    print("Impression annulée.")
                else:
                    print("Échec de l'annulation de l'impression.")
            elif choice == "4":
                print("Fin du module 3D Printing.")
                break
            else:
                print("Option invalide. Veuillez réessayer.")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Arrêt demandé par l'utilisateur.")
    finally:
        client.stop_monitoring()

if __name__ == "__main__":
    run()
