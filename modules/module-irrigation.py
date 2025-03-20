import logging
import time
from typing import Dict, Any, List, Optional

from modules.base_module import BaseModule
from modules.message_bus import MessageBus
from modules.state_manager import StateManager

class IrrigationModule(BaseModule):
    """
    Module de gestion de l'irrigation intelligente.
    Permet de contrôler les zones d'arrosage en fonction des conditions météo,
    de l'humidité du sol et des planifications.
    """
    
    def __init__(self, module_id: str, config: Dict[str, Any], message_bus: MessageBus, state_manager: StateManager):
        """
        Initialise le module d'irrigation.
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration du module
            message_bus: Instance du bus de messages
            state_manager: Instance du gestionnaire d'état
        """
        super().__init__(module_id, "irrigation", config, message_bus, state_manager)
        
        # Configuration des zones d'irrigation
        self.zones = config.get("zones", {})
        
        # Configuration des planifications
        self.schedules = config.get("schedules", {})
        
        # Seuils d'humidité et de pluie pour prendre des décisions
        self.moisture_threshold = config.get("moisture_threshold", 30)  # %
        self.rain_threshold = config.get("rain_threshold", 5)  # mm dans les dernières 24h
        self.rain_forecast_threshold = config.get("rain_forecast_threshold", 30)  # % de probabilité de pluie
        
        # État interne
        self._active_zones = set()
        
        self.logger.info(f"Module d'irrigation initialisé avec {len(self.zones)} zones")
        
        # Enregistrement des gestionnaires de messages
        self._register_handlers()
    
    def _register_handlers(self):
        """Enregistre les gestionnaires de messages pour ce module."""
        self.message_bus.register_handler("irrigation/start", self._handle_start_zone)
        self.message_bus.register_handler("irrigation/stop", self._handle_stop_zone)
        self.message_bus.register_handler("irrigation/status", self._handle_status_request)
        self.message_bus.register_handler("weather/rain_detected", self._handle_rain_detected)
        self.message_bus.register_handler("weather/forecast_updated", self._handle_forecast_updated)
        self.message_bus.register_handler("sensor/soil_moisture", self._handle_soil_moisture)
    
    def start(self):
        """Démarre le module et initialise les planifications."""
        self.logger.info("Démarrage du module d'irrigation")
        
        # Charger l'état précédent si disponible
        self._load_state()
        
        # Initialiser les planifications
        self._setup_schedules()
        
        # Définir le statut comme actif
        self.active = True
    
    def stop(self):
        """Arrête le module et sauvegarde l'état actuel."""
        self.logger.info("Arrêt du module d'irrigation")
        
        # Arrêter toutes les zones actives
        for zone_id in list(self._active_zones):
            self._stop_zone(zone_id)
        
        # Sauvegarder l'état
        self._save_state()
        
        # Définir le statut comme inactif
        self.active = False
    
    def _load_state(self):
        """Charge l'état précédent depuis le gestionnaire d'état."""
        state = self.state_manager.get_state(f"{self.module_id}_state")
        if state:
            self.logger.info("Chargement de l'état précédent")
            if "active_zones" in state:
                # Vérifier si les zones sont toujours valides dans la configuration
                valid_zones = {zone_id for zone_id in state["active_zones"] if zone_id in self.zones}
                self._active_zones = valid_zones
    
    def _save_state(self):
        """Sauvegarde l'état actuel dans le gestionnaire d'état."""
        state = {
            "active_zones": list(self._active_zones),
            "last_update": time.time()
        }
        self.state_manager.set_state(f"{self.module_id}_state", state)
    
    def _setup_schedules(self):
        """Configure les planifications d'irrigation."""
        self.logger.info("Configuration des planifications d'irrigation")
        
        # Ici, nous pourrions ajouter des tâches planifiées
        # Pour cet exemple, nous simulons simplement la configuration
        for schedule_id, schedule in self.schedules.items():
            self.logger.info(f"Planification configurée: {schedule_id}")
            
            # Dans une implémentation réelle, nous utiliserions un scheduler
            # comme APScheduler pour configurer les tâches
    
    def _start_zone(self, zone_id: str, duration: int = None) -> bool:
        """
        Démarre l'irrigation d'une zone spécifique.
        
        Args:
            zone_id: Identifiant de la zone
            duration: Durée d'irrigation en minutes (optionnel)
            
        Returns:
            bool: True si démarré avec succès, False sinon
        """
        if zone_id not in self.zones:
            self.logger.warning(f"Zone {zone_id} inconnue")
            return False
        
        # Vérifier si la zone est déjà active
        if zone_id in self._active_zones:
            self.logger.info(f"Zone {zone_id} déjà active")
            return True
        
        # Vérifier les conditions météorologiques si disponibles
        weather_state = self.state_manager.get_state("weather")
        if weather_state:
            recent_rain = weather_state.get("recent_rain", 0)
            rain_forecast = weather_state.get("rain_forecast", 0)
            
            if recent_rain > self.rain_threshold:
                self.logger.info(f"Irrigation annulée pour la zone {zone_id}: pluie récente ({recent_rain}mm)")
                return False
                
            if rain_forecast > self.rain_forecast_threshold:
                self.logger.info(f"Irrigation annulée pour la zone {zone_id}: prévision de pluie ({rain_forecast}%)")
                return False
        
        # Ajuster la durée si nécessaire
        if duration is None:
            duration = self.zones[zone_id].get("default_duration", 15)
        
        # Dans une implémentation réelle, nous enverrions des commandes aux dispositifs physiques
        # Ici, nous simulons simplement l'activation
        self.logger.info(f"Démarrage de l'irrigation pour la zone {zone_id} pendant {duration} minutes")
        
        # Ajouter à la liste des zones actives
        self._active_zones.add(zone_id)
        
        # Publier un événement
        self.message_bus.publish("irrigation/zone_started", {
            "zone_id": zone_id,
            "duration": duration,
            "start_time": time.time()
        })
        
        # Programmer l'arrêt automatique après la durée spécifiée
        # Dans une implémentation réelle, nous utiliserions un scheduler
        
        # Mettre à jour l'état
        self._save_state()
        
        return True
    
    def _stop_zone(self, zone_id: str) -> bool:
        """
        Arrête l'irrigation d'une zone spécifique.
        
        Args:
            zone_id: Identifiant de la zone
            
        Returns:
            bool: True si arrêté avec succès, False sinon
        """
        if zone_id not in self.zones:
            self.logger.warning(f"Zone {zone_id} inconnue")
            return False
        
        # Vérifier si la zone est active
        if zone_id not in self._active_zones:
            self.logger.info(f"Zone {zone_id} déjà inactive")
            return True
        
        # Dans une implémentation réelle, nous enverrions des commandes aux dispositifs physiques
        # Ici, nous simulons simplement la désactivation
        self.logger.info(f"Arrêt de l'irrigation pour la zone {zone_id}")
        
        # Retirer de la liste des zones actives
        self._active_zones.remove(zone_id)
        
        # Publier un événement
        self.message_bus.publish("irrigation/zone_stopped", {
            "zone_id": zone_id,
            "stop_time": time.time()
        })
        
        # Mettre à jour l'état
        self._save_state()
        
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """
        Récupère le statut actuel du système d'irrigation.
        
        Returns:
            Dict: Statut du système d'irrigation
        """
        # Récupérer l'état d'humidité des zones si disponible
        moisture_data = {}
        for zone_id in self.zones:
            sensor_id = self.zones[zone_id].get("moisture_sensor")
            if sensor_id:
                moisture_state = self.state_manager.get_state(f"sensor_{sensor_id}")
                if moisture_state:
                    moisture_data[zone_id] = moisture_state.get("value", 0)
        
        return {
            "active_zones": list(self._active_zones),
            "zone_count": len(self.zones),
            "moisture_data": moisture_data,
            "moisture_threshold": self.moisture_threshold,
            "rain_threshold": self.rain_threshold,
            "rain_forecast_threshold": self.rain_forecast_threshold
        }
    
    # Gestionnaires de messages
    
    def _handle_start_zone(self, message: Dict[str, Any]):
        """Gère les demandes de démarrage d'irrigation."""
        zone_id = message.get("zone_id")
        duration = message.get("duration")
        
        if not zone_id:
            self.logger.warning("Demande de démarrage sans zone_id")
            return
        
        success = self._start_zone(zone_id, duration)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": success,
                "zone_id": zone_id,
                "action": "start"
            })
    
    def _handle_stop_zone(self, message: Dict[str, Any]):
        """Gère les demandes d'arrêt d'irrigation."""
        zone_id = message.get("zone_id")
        
        if not zone_id:
            self.logger.warning("Demande d'arrêt sans zone_id")
            return
        
        success = self._stop_zone(zone_id)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": success,
                "zone_id": zone_id,
                "action": "stop"
            })
    
    def _handle_status_request(self, message: Dict[str, Any]):
        """Gère les demandes de statut."""
        status = self.get_status()
        
        # Répondre avec le statut
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], status)
    
    def _handle_rain_detected(self, message: Dict[str, Any]):
        """Gère les notifications de pluie."""
        amount = message.get("amount", 0)
        
        self.logger.info(f"Notification de pluie reçue: {amount}mm")
        
        # Si la quantité de pluie dépasse le seuil, arrêter toutes les zones actives
        if amount > self.rain_threshold:
            self.logger.info(f"Arrêt de toutes les zones d'irrigation en raison de pluie ({amount}mm)")
            for zone_id in list(self._active_zones):
                self._stop_zone(zone_id)
    
    def _handle_forecast_updated(self, message: Dict[str, Any]):
        """Gère les mises à jour des prévisions météo."""
        rain_probability = message.get("rain_probability", 0)
        
        self.logger.info(f"Prévision de pluie mise à jour: {rain_probability}%")
        
        # Pour l'instant, nous ne faisons rien de proactif avec cette information
        # Elle sera utilisée lors des prochaines demandes de démarrage d'irrigation
    
    def _handle_soil_moisture(self, message: Dict[str, Any]):
        """Gère les mises à jour d'humidité du sol."""
        sensor_id = message.get("sensor_id")
        moisture = message.get("value", 0)
        
        if not sensor_id:
            return
        
        # Trouver la zone associée à ce capteur
        zone_id = None
        for z_id, zone in self.zones.items():
            if zone.get("moisture_sensor") == sensor_id:
                zone_id = z_id
                break
        
        if not zone_id:
            return
        
        self.logger.debug(f"Humidité du sol pour la zone {zone_id}: {moisture}%")
        
        # Vérifier si l'irrigation est nécessaire en fonction de l'humidité
        if moisture < self.moisture_threshold and zone_id not in self._active_zones:
            # Vérifier si l'irrigation automatique est activée pour cette zone
            if self.zones[zone_id].get("auto_irrigation", False):
                self.logger.info(f"Démarrage automatique de l'irrigation pour la zone {zone_id} (humidité: {moisture}%)")
                self._start_zone(zone_id)
        
        # Vérifier si l'irrigation doit être arrêtée
        elif moisture > self.moisture_threshold + 10 and zone_id in self._active_zones:
            if self.zones[zone_id].get("auto_irrigation", False):
                self.logger.info(f"Arrêt automatique de l'irrigation pour la zone {zone_id} (humidité: {moisture}%)")
                self._stop_zone(zone_id)

# Exemple de configuration pour les tests
SAMPLE_CONFIG = {
    "zones": {
        "zone1": {
            "name": "Jardin avant",
            "moisture_sensor": "moisture1",
            "default_duration": 15,
            "auto_irrigation": True
        },
        "zone2": {
            "name": "Jardin arrière",
            "moisture_sensor": "moisture2",
            "default_duration": 20,
            "auto_irrigation": True
        },
        "zone3": {
            "name": "Potager",
            "moisture_sensor": "moisture3",
            "default_duration": 10,
            "auto_irrigation": False
        }
    },
    "schedules": {
        "morning": {
            "zones": ["zone1", "zone2"],
            "time": "07:00",
            "days": ["mon", "wed", "fri"],
            "duration": 15
        },
        "evening": {
            "zones": ["zone3"],
            "time": "19:00",
            "days": ["tue", "thu", "sat"],
            "duration": 10
        }
    },
    "moisture_threshold": 30,
    "rain_threshold": 5,
    "rain_forecast_threshold": 30
}
