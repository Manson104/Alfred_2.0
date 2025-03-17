import time
import logging
from alfred_domotique import AlfredDomotique

logger = logging.getLogger("DomotiqueAgent")

class DomotiqueAgent:
    """
    Agent pour la gestion domotique d'Alfred (distributeurs de croquettes, arrosage connecté).
    Cet agent utilise le module AlfredDomotique pour interagir avec les appareils IoT.
    """
    def __init__(self, config_file: str = "alfred_domotique_config.json"):
        self.domotique = AlfredDomotique(config_file)
    
    def start(self):
        logger.info("Démarrage du DomotiqueAgent...")
        self.domotique.initialize()
        # Ici, tu pourrais lancer un thread pour surveiller les commandes programmées
    
    def stop(self):
        logger.info("Arrêt du DomotiqueAgent...")
        self.domotique.shutdown()

    def process_command(self, command: dict) -> dict:
        """
        Traite une commande liée à la domotique.
        Exemples de commandes :
          - {"type": "start_irrigation", "system_name": "ArrosageJardin", "zone": "Pelouse", "duration": 600}
          - {"type": "dispense_food", "feeder_name": "DistributeurChien", "amount": 50.0}
        """
        cmd_type = command.get("type")
        if cmd_type == "start_irrigation":
            system_name = command.get("system_name")
            zone = command.get("zone")
            duration = command.get("duration", 600)
            result = self.domotique.start_irrigation(system_name, zone, duration)
            return result
        elif cmd_type == "stop_irrigation":
            system_name = command.get("system_name")
            result = self.domotique.stop_irrigation(system_name)
            return result
        elif cmd_type == "dispense_food":
            feeder_name = command.get("feeder_name")
            amount = command.get("amount", 50.0)
            result = self.domotique.dispense_food(feeder_name, amount)
            return result
        elif cmd_type == "schedule_feeding":
            feeder_name = command.get("feeder_name")
            time_str = command.get("time")
            amount = command.get("amount")
            days = command.get("days")
            result = self.domotique.schedule_feeding(feeder_name, time_str, amount, days)
            return result
        elif cmd_type == "schedule_irrigation":
            system_name = command.get("system_name")
            zone = command.get("zone")
            time_str = command.get("time")
            duration = command.get("duration", 600)
            days = command.get("days")
            weather_adjustment = command.get("weather_adjustment", False)
            result = self.domotique.schedule_irrigation(system_name, zone, time_str, duration, days, weather_adjustment)
            return result
        else:
            return {"error": f"Commande non supportée: {cmd_type}"}

# Exemple d'utilisation autonome
if __name__ == "__main__":
    agent = DomotiqueAgent()
    agent.start()
    # Exemple : démarrer l'arrosage pour tester
    command = {
        "type": "start_irrigation",
        "system_name": "ArrosageJardin",
        "zone": "Pelouse",
        "duration": 300
    }
    result = agent.process_command(command)
    print("Résultat de la commande:", result)
    time.sleep(5)
    agent.stop()
