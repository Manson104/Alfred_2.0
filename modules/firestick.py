import os
import json
import logging
import subprocess
import time

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FireStickModule")

def load_config():
    """
    Charge la configuration spécifique au module Fire Stick TV depuis config.json.
    Le fichier config.json doit inclure une section "firestick", par exemple :
    
    "firestick": {
         "enabled": true,
         "ip": "192.168.x.x",
         "port": "5555"
    }
    """
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
    if not os.path.exists(config_path):
        logger.warning("Fichier config.json non trouvé pour le module Fire Stick.")
        return {}
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        return config.get("firestick", {})
    except Exception as e:
        logger.error("Erreur lors du chargement de la configuration Fire Stick: " + str(e))
        return {}

def adb_command(command):
    """
    Exécute une commande ADB et retourne la sortie.
    """
    try:
        result = subprocess.check_output(["adb"] + command, stderr=subprocess.STDOUT, text=True)
        return result.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Erreur adb: {e.output}")
        return None

class FireStickController:
    def __init__(self, ip, port="5555"):
        self.ip = ip
        self.port = port
        self.address = f"{ip}:{port}"
    
    def connect(self):
        logger.info(f"Connexion à Fire Stick à {self.address}")
        output = adb_command(["connect", self.address])
        if output and "connected" in output.lower():
            logger.info("Connexion établie avec succès.")
            return True
        else:
            logger.error("Échec de la connexion au Fire Stick.")
            return False
    
    def disconnect(self):
        logger.info(f"Déconnexion de Fire Stick à {self.address}")
        output = adb_command(["disconnect", self.address])
        if output and "disconnected" in output.lower():
            logger.info("Déconnexion réussie.")
            return True
        else:
            logger.error("Échec de la déconnexion.")
            return False
    
    def send_key_event(self, key_code):
        """
        Envoie un key event au Fire Stick.
        Par exemple : 3 = HOME, 19 = UP, 20 = DOWN, 21 = LEFT, 22 = RIGHT, 66 = ENTER.
        """
        logger.info(f"Envoi du key event: {key_code}")
        output = adb_command(["shell", "input", "keyevent", str(key_code)])
        return output
    
    def launch_app(self, package_name):
        """
        Lance une application sur le Fire Stick.
        """
        logger.info(f"Lancement de l'application: {package_name}")
        output = adb_command(["shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"])
        return output
    
    def stop_app(self, package_name):
        """
        Arrête une application sur le Fire Stick.
        """
        logger.info(f"Arrêt de l'application: {package_name}")
        output = adb_command(["shell", "am", "force-stop", package_name])
        return output

def run():
    """
    Fonction principale appelée par Alfred pour exécuter le module Fire Stick TV et Multimédia.
    Propose une interface CLI pour envoyer des key events, lancer ou arrêter une application, puis se déconnecter.
    """
    logger.info("Exécution du module Fire Stick TV et Multimédia.")
    config = load_config()
    if not config.get("enabled", True):
        logger.info("Module Fire Stick désactivé dans la configuration.")
        return
    
    ip = config.get("ip", "")
    port = config.get("port", "5555")
    if not ip:
        logger.error("Adresse IP du Fire Stick non configurée.")
        return
    
    controller = FireStickController(ip, port)
    if not controller.connect():
        logger.error("Connexion au Fire Stick échouée.")
        return

    pubsub.subscribe('agent_multimedia')

    try:
        while True:
            print("\n--- Module Fire Stick TV et Multimédia ---")
            print("1. Envoyer un key event (ex: HOME=3, UP=19, DOWN=20, LEFT=21, RIGHT=22, ENTER=66)")
            print("2. Lancer une application (ex: com.netflix.ninja)")
            print("3. Arrêter une application (ex: com.netflix.ninja)")
            print("4. Déconnecter et quitter")
            choice = input("Choisissez une option : ").strip()
            
            if choice == "1":
                key = input("Entrez le key code à envoyer : ").strip()
                controller.send_key_event(key)
            elif choice == "2":
                package = input("Entrez le nom du package à lancer : ").strip()
                controller.launch_app(package)
            elif choice == "3":
                package = input("Entrez le nom du package à arrêter : ").strip()
                controller.stop_app(package)
            elif choice == "4":
                controller.disconnect()
                print("Déconnexion et fin du module.")
                break
            else:
                print("Option invalide.")
            time.sleep(1)
    except KeyboardInterrupt:
        controller.disconnect()
        print("Arrêt demandé par l'utilisateur.")

if __name__ == "__main__":
    run()
