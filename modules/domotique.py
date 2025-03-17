import os
import json
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_config():
    """
    Charge la configuration spécifique à la domotique depuis config.json.
    Le fichier config.json doit avoir une section 'domotique' pour ce module.
    Exemple de configuration :
    {
        "domotique": {
            "enabled": true,
            "devices": {
                "lumiere_salon": "Lumière du salon",
                "volet_cuisine": "Volet de la cuisine",
                "prise_bureau": "Prise du bureau",
                "camera_entree": "Caméra d'entrée"
            }
        }
    }
    """
    # On suppose que config.json se trouve à la racine du projet (alfred/)
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
    if not os.path.exists(config_path):
        logging.warning("Fichier de configuration non trouvé pour la domotique.")
        return {}
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        return config.get("domotique", {})
    except Exception as e:
        logging.error(f"Erreur de chargement de la configuration domotique: {e}")
        return {}

def control_device(device_name: str, action: str):
    """
    Simule l'exécution d'une action sur un dispositif.
    Dans une implémentation réelle, cette fonction intégrerait l'API de Home Assistant, Tuya, etc.
    """
    logging.info(f"Exécution: {action} sur le dispositif: {device_name}")
    print(f"Action '{action}' sur '{device_name}' effectuée.")

def run():
    """
    Fonction principale appelée par Alfred pour exécuter le module Domotique.
    Propose une interface CLI simple pour contrôler des dispositifs.
    """
    logging.info("Exécution du module Domotique.")
    
    config = load_config()
    if not config.get("enabled", True):
        logging.info("La gestion de la domotique est désactivée dans la configuration.")
        return

    # Liste des dispositifs définis dans la configuration ou valeurs par défaut
    devices = config.get("devices", {
        "lumiere_salon": "Lumière du salon",
        "volet_cuisine": "Volet de la cuisine",
        "prise_bureau": "Prise du bureau",
        "camera_entree": "Caméra d'entrée"
    })
    
    # Menu interactif simple
    while True:
        print("\n--- Module Domotique ---")
        print("Dispositifs disponibles :")
        for ident, name in devices.items():
            print(f"  {ident} : {name}")
        print("\nActions possibles : ON, OFF, STATUS, QUITTER")
        
        device = input("Entrez l'identifiant du dispositif (ou 'quitter' pour sortir) : ").strip()
        if device.lower() == "quitter":
            print("Fin du module Domotique.")
            break
        if device not in devices:
            print("Dispositif inconnu. Réessayez.")
            continue
        
        action = input("Entrez l'action (ON, OFF, STATUS) : ").strip().upper()
        if action not in ["ON", "OFF", "STATUS"]:
            print("Action non reconnue. Veuillez saisir ON, OFF ou STATUS.")
            continue
        
        control_device(devices[device], action)

if __name__ == "__main__":
    run()
