import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json

from modules.base_module import BaseModule
from modules.message_bus import MessageBus
from modules.state_manager import StateManager

class SecurityModule(BaseModule):
    """
    Module de gestion de la sécurité.
    Permet de surveiller et gérer les détecteurs, les caméras, les alarmes 
    et autres équipements de sécurité.
    """
    
    # États du système de sécurité
    STATE_DISARMED = "disarmed"
    STATE_ARMED_HOME = "armed_home"
    STATE_ARMED_AWAY = "armed_away"
    STATE_TRIGGERED = "triggered"
    
    def __init__(self, module_id: str, config: Dict[str, Any], message_bus: MessageBus, state_manager: StateManager):
        """
        Initialise le module de sécurité.
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration du module
            message_bus: Instance du bus de messages
            state_manager: Instance du gestionnaire d'état
        """
        super().__init__(module_id, "security", config, message_bus, state_manager)
        
        # Configuration des capteurs
        self.sensors = config.get("sensors", {})
        
        # Configuration des zones
        self.zones = config.get("zones", {})
        
        # Configuration des codes d'accès
        self._access_codes = config.get("access_codes", {})
        
        # Configuration des notifications
        self.notification_settings = config.get("notifications", {})
        
        # Configuration de l'alarme
        self.alarm_settings = config.get("alarm", {})
        self.alarm_delay = self.alarm_settings.get("entry_delay", 30)  # secondes
        self.exit_delay = self.alarm_settings.get("exit_delay", 60)  # secondes
        self.alarm_duration = self.alarm_settings.get("duration", 300)  # secondes
        
        # Configuration des caméras
        self.cameras = config.get("cameras", {})
        
        # État interne
        self._system_state = self.STATE_DISARMED
        self._triggered_sensors = {}  # sensor_id -> timestamp
        self._alarm_active = False
        self._alarm_trigger_time = None
        self._entry_timer = None
        self._exit_timer = None
        self._last_events = []  # liste des derniers événements
        self._zone_states = {}  # zone_id -> state
        self._door_states = {}  # door_id -> state (open/closed)
        self._window_states = {}  # window_id -> state (open/closed)
        self._motion_states = {}  # sensor_id -> state (active/inactive)
        self._camera_states = {}  # camera_id -> state (active/inactive)
        
        self.logger.info(f"Module de sécurité initialisé avec {len(self.sensors)} capteurs et {len(self.zones)} zones")
        
        # Enregistrement des gestionnaires de messages
        self._register_handlers()
    
    def _register_handlers(self):
        """Enregistre les gestionnaires de messages pour ce module."""
        self.message_bus.register_handler("security/arm", self._handle_arm_system)
        self.message_bus.register_handler("security/disarm", self._handle_disarm_system)
        self.message_bus.register_handler("security/status", self._handle_status_request)
        self.message_bus.register_handler("security/panic", self._handle_panic_button)
        self.message_bus.register_handler("sensor/door", self._handle_door_sensor)
        self.message_bus.register_handler("sensor/window", self._handle_window_sensor)
        self.message_bus.register_handler("sensor/motion", self._handle_motion_sensor)
        self.message_bus.register_handler("sensor/glass_break", self._handle_glass_break_sensor)
        self.message_bus.register_handler("sensor/smoke", self._handle_smoke_sensor)
        self.message_bus.register_handler("camera/motion", self._handle_camera_motion)
        self.message_bus.register_handler("home/mode", self._handle_home_mode_changed)
    
    def start(self):
        """Démarre le module."""
        self.logger.info("Démarrage du module de sécurité")
        
        # Charger l'état précédent si disponible
        self._load_state()
        
        # Vérifier l'état initial des capteurs
        self._check_initial_sensor_states()
        
        # Définir le statut comme actif
        self.active = True
    
    def stop(self):
        """Arrête le module et sauvegarde l'état actuel."""
        self.logger.info("Arrêt du module de sécurité")
        
        # Annuler les timers en cours
        if self._entry_timer:
            # Dans une implémentation réelle, nous annulerions le timer ici
            self._entry_timer = None
            
        if self._exit_timer:
            # Dans une implémentation réelle, nous annulerions le timer ici
            self._exit_timer = None
        
        # Sauvegarde de l'état
        self._save_state()
        
        # Définir le statut comme inactif
        self.active = False
    
    def _load_state(self):
        """Charge l'état précédent depuis le gestionnaire d'état."""
        state = self.state_manager.get_state(f"{self.module_id}_state")
        if state:
            self.logger.info("Chargement de l'état précédent")
            
            # Charger l'état du système
            if "system_state" in state:
                self._system_state = state["system_state"]
            
            # Charger l'état des zones
            if "zone_states" in state:
                self._zone_states = state["zone_states"]
            
            # Charger l'état des capteurs
            if "door_states" in state:
                self._door_states = state["door_states"]
            
            if "window_states" in state:
                self._window_states = state["window_states"]
            
            if "motion_states" in state:
                self._motion_states = state["motion_states"]
            
            # Charger les derniers événements
            if "last_events" in state:
                self._last_events = state["last_events"]
    
    def _save_state(self):
        """Sauvegarde l'état actuel dans le gestionnaire d'état."""
        state = {
            "system_state": self._system_state,
            "zone_states": self._zone_states,
            "door_states": self._door_states,
            "window_states": self._window_states,
            "motion_states": self._motion_states,
            "last_events": self._last_events,
            "last_update": time.time()
        }
        self.state_manager.set_state(f"{self.module_id}_state", state)
    
    def _check_initial_sensor_states(self):
        """Vérifie l'état initial des capteurs au démarrage."""
        for sensor_id, sensor_config in self.sensors.items():
            sensor_type = sensor_config.get("type")
            
            # Récupérer l'état actuel du capteur depuis le gestionnaire d'état
            sensor_state = self.state_manager.get_state(f"sensor_{sensor_id}")
            
            if sensor_state:
                state_value = sensor_state.get("state")
                
                if sensor_type == "door":
                    self._door_states[sensor_id] = state_value
                elif sensor_type == "window":
                    self._window_states[sensor_id] = state_value
                elif sensor_type == "motion":
                    self._motion_states[sensor_id] = state_value
                
                # Mettre à jour l'état de la zone associée
                zone_id = sensor_config.get("zone")
                if zone_id:
                    self._update_zone_state(zone_id)
    
    def _arm_system(self, mode: str, code: str = None) -> bool:
        """
        Arme le système de sécurité.
        
        Args:
            mode: Mode d'armement ('home' ou 'away')
            code: Code d'accès pour l'armement (optionnel)
            
        Returns:
            bool: True si armé avec succès, False sinon
        """
        # Vérifier que le mode est valide
        if mode not in ["home", "away"]:
            self.logger.warning(f"Mode d'armement invalide: {mode}")
            return False
        
        # Vérifier si un code est requis
        if self.alarm_settings.get("require_code_to_arm", False):
            if not code or not self._validate_access_code(code):
                self.logger.warning("Code d'accès invalide pour l'armement")
                return False
        
        # Vérifier si des capteurs sont actifs qui empêcheraient l'armement
        if mode == "away":
            open_doors = [sensor_id for sensor_id, state in self._door_states.items() if state == "open"]
            open_windows = [sensor_id for sensor_id, state in self._window_states.items() if state == "open"]
            
            if open_doors or open_windows:
                sensors = ", ".join(open_doors + open_windows)
                self.logger.warning(f"Armement impossible, capteurs ouverts: {sensors}")
                
                # Publier un message d'erreur
                self.message_bus.publish("security/error", {
                    "type": "arming_failed",
                    "reason": "open_sensors",
                    "sensors": open_doors + open_windows
                })
                
                return False
        
        # Définir l'état en fonction du mode
        new_state = self.STATE_ARMED_HOME if mode == "home" else self.STATE_ARMED_AWAY
        
        # Démarrer le délai de sortie
        self._start_exit_delay(new_state)
        
        # Ajouter un événement
        self._add_event("system_armed", {
            "mode": mode,
            "user": "unknown"  # Dans une implémentation réelle, nous pourrions suivre qui a armé le système
        })
        
        # Publier un message d'armement
        self.message_bus.publish("security/system_arming", {
            "mode": mode,
            "exit_delay": self.exit_delay
        })
        
        return True
    
    def _start_exit_delay(self, target_state: str):
        """
        Démarre le délai de sortie.
        
        Args:
            target_state: État cible après le délai de sortie
        """
        self.logger.info(f"Début du délai de sortie ({self.exit_delay}s)")
        
        # Dans une implémentation réelle, nous utiliserions un timer
        # Ici, nous simulons simplement le début du délai
        self._exit_timer = {
            "target_state": target_state,
            "end_time": time.time() + self.exit_delay
        }
        
        # Publier un message pour le délai de sortie
        self.message_bus.publish("security/exit_delay", {
            "delay": self.exit_delay,
            "end_time": time.time() + self.exit_delay
        })
        
        # Dans une implémentation réelle, nous définirions un callback pour finaliser l'armement
        # après le délai de sortie. Pour cette simulation, nous supposons que l'événement se produit.
        self._system_state = target_state
        self._exit_timer = None
        
        # Publier un message d'armement complet
        self.message_bus.publish("security/system_armed", {
            "state": target_state,
            "timestamp": time.time()
        })
        
        # Mettre à jour l'état
        self._save_state()
    
    def _stop_alarm(self):
        """Arrête l'alarme."""
        if not self._alarm_active:
            return
            
        self.logger.info("Arrêt de l'alarme")
        
        # Mettre à jour l'état
        self._alarm_active = False
        self._alarm_trigger_time = None
        
        # Ajouter un événement
        self._add_event("alarm_stopped", {
            "duration": time.time() - self._alarm_trigger_time if self._alarm_trigger_time else 0,
            "timestamp": time.time()
        })
        
        # Publier un message d'arrêt d'alarme
        self.message_bus.publish("security/alarm_stopped", {
            "timestamp": time.time()
        })
        
        # Désactiver les dispositifs d'alarme
        self._deactivate_alarm_devices()
        
        # Mettre à jour l'état
        self._save_state()
    
    def _activate_alarm_devices(self):
        """Active les dispositifs d'alarme (sirènes, lumières, etc.)."""
        # Activer la sirène
        if self.alarm_settings.get("siren_enabled", True):
            self.message_bus.publish("device/siren/set", {
                "state": True
            })
        
        # Activer les lumières d'alarme
        if self.alarm_settings.get("alarm_lights_enabled", True):
            self.message_bus.publish("lighting/scene", {
                "scene_id": "alarm"  # Scène prédéfinie pour l'alarme
            })
        
        # Activer l'enregistrement des caméras
        for camera_id in self.cameras:
            self.message_bus.publish("camera/record", {
                "camera_id": camera_id,
                "duration": self.alarm_duration
            })
    
    def _deactivate_alarm_devices(self):
        """Désactive les dispositifs d'alarme."""
        # Désactiver la sirène
        self.message_bus.publish("device/siren/set", {
            "state": False
        })
        
        # Restaurer l'éclairage normal
        if self.alarm_settings.get("restore_lights", True):
            self.message_bus.publish("lighting/scene", {
                "scene_id": "normal"  # Scène prédéfinie pour l'éclairage normal
            })
    
    def _send_alarm_notification(self, sensor_id: str, reason: str):
        """
        Envoie des notifications d'alarme.
        
        Args:
            sensor_id: Identifiant du capteur déclencheur
            reason: Raison du déclenchement
        """
        # Récupérer les informations sur le capteur
        sensor_config = self.sensors.get(sensor_id, {})
        sensor_name = sensor_config.get("name", sensor_id)
        sensor_type = sensor_config.get("type", "unknown")
        zone_id = sensor_config.get("zone")
        zone_name = self.zones.get(zone_id, {}).get("name", zone_id) if zone_id else "Inconnue"
        
        # Construire le message de notification
        message = f"ALARME: {sensor_name} ({sensor_type}) dans la zone {zone_name}. Raison: {reason}"
        
        # Envoyer les notifications configurées
        if self.notification_settings.get("push_enabled", False):
            self.message_bus.publish("notification/push", {
                "title": "Alerte de sécurité",
                "message": message,
                "priority": "high"
            })
        
        if self.notification_settings.get("sms_enabled", False):
            recipients = self.notification_settings.get("sms_recipients", [])
            for recipient in recipients:
                self.message_bus.publish("notification/sms", {
                    "to": recipient,
                    "message": message
                })
        
        if self.notification_settings.get("email_enabled", False):
            recipients = self.notification_settings.get("email_recipients", [])
            for recipient in recipients:
                self.message_bus.publish("notification/email", {
                    "to": recipient,
                    "subject": "Alerte de sécurité",
                    "message": message
                })
    
    def _update_zone_state(self, zone_id: str):
        """
        Met à jour l'état d'une zone en fonction de l'état de ses capteurs.
        
        Args:
            zone_id: Identifiant de la zone
        """
        if zone_id not in self.zones:
            return
            
        # Trouver tous les capteurs dans cette zone
        zone_sensors = [sensor_id for sensor_id, config in self.sensors.items() 
                       if config.get("zone") == zone_id]
        
        # Vérifier si un capteur est actif dans la zone
        zone_active = False
        
        for sensor_id in zone_sensors:
            sensor_config = self.sensors[sensor_id]
            sensor_type = sensor_config.get("type")
            
            if sensor_type == "door" and self._door_states.get(sensor_id) == "open":
                zone_active = True
                break
            elif sensor_type == "window" and self._window_states.get(sensor_id) == "open":
                zone_active = True
                break
            elif sensor_type == "motion" and self._motion_states.get(sensor_id) == "active":
                zone_active = True
                break
        
        # Mettre à jour l'état de la zone
        self._zone_states[zone_id] = "active" if zone_active else "inactive"
        
        # Publier un événement de changement d'état de zone
        self.message_bus.publish("security/zone_changed", {
            "zone_id": zone_id,
            "state": self._zone_states[zone_id],
            "timestamp": time.time()
        })
    
    def _add_event(self, event_type: str, data: Dict[str, Any]):
        """
        Ajoute un événement à l'historique.
        
        Args:
            event_type: Type d'événement
            data: Données associées à l'événement
        """
        event = {
            "type": event_type,
            "timestamp": time.time(),
            "data": data
        }
        
        # Ajouter l'événement au début de la liste
        self._last_events.insert(0, event)
        
        # Limiter la taille de l'historique
        max_events = 100
        if len(self._last_events) > max_events:
            self._last_events = self._last_events[:max_events]
    
    def get_status(self) -> Dict[str, Any]:
        """
        Récupère le statut actuel du système de sécurité.
        
        Returns:
            Dict: Statut du système de sécurité
        """
        return {
            "state": self._system_state,
            "alarm_active": self._alarm_active,
            "triggered_sensors": self._triggered_sensors,
            "zone_states": self._zone_states,
            "open_doors": [sensor_id for sensor_id, state in self._door_states.items() if state == "open"],
            "open_windows": [sensor_id for sensor_id, state in self._window_states.items() if state == "open"],
            "active_motion": [sensor_id for sensor_id, state in self._motion_states.items() if state == "active"],
            "last_events": self._last_events[:5]  # Limiter aux 5 derniers événements pour la vue d'ensemble
        }
    
    def get_events(self, limit: int = 20, event_type: str = None) -> List[Dict[str, Any]]:
        """
        Récupère les événements récents.
        
        Args:
            limit: Nombre maximum d'événements à retourner
            event_type: Type d'événement à filtrer (optionnel)
            
        Returns:
            List: Liste des événements
        """
        if event_type:
            filtered_events = [event for event in self._last_events if event["type"] == event_type]
            return filtered_events[:limit]
        else:
            return self._last_events[:limit]
    
    # Gestionnaires de messages
    
    def _handle_arm_system(self, message: Dict[str, Any]):
        """Gère les demandes d'armement du système."""
        mode = message.get("mode", "away")
        code = message.get("code")
        
        success = self._arm_system(mode, code)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": success,
                "mode": mode,
                "action": "arm"
            })
    
    def _handle_disarm_system(self, message: Dict[str, Any]):
        """Gère les demandes de désarmement du système."""
        code = message.get("code")
        
        if not code:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "action": "disarm",
                    "error": "missing_code"
                })
            return
        
        success = self._disarm_system(code)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": success,
                "action": "disarm"
            })
    
    def _handle_status_request(self, message: Dict[str, Any]):
        """Gère les demandes de statut."""
        status = self.get_status()
        
        # Répondre avec le statut
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], status)
    
    def _handle_panic_button(self, message: Dict[str, Any]):
        """Gère les activations du bouton panique."""
        self.logger.info("Bouton panique activé")
        
        # Activer immédiatement l'alarme
        self._activate_alarm("panic_button", "panic")
        
        # Répondre avec confirmation
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "action": "panic"
            })
    
    def _handle_door_sensor(self, message: Dict[str, Any]):
        """Gère les événements des capteurs de porte."""
        sensor_id = message.get("sensor_id")
        state = message.get("state")  # "open" ou "closed"
        
        if not sensor_id or not state:
            return
        
        # Vérifier que c'est bien un capteur de porte
        sensor_config = self.sensors.get(sensor_id, {})
        if sensor_config.get("type") != "door":
            return
        
        # Mettre à jour l'état du capteur
        self._door_states[sensor_id] = state
        
        # Si le système est armé et que la porte s'ouvre, déclencher l'alarme
        if state == "open" and (self._system_state == self.STATE_ARMED_AWAY or 
                               (self._system_state == self.STATE_ARMED_HOME and not sensor_config.get("bypass_in_home_mode", False))):
            self._trigger_alarm(sensor_id, "door_opened")
        
        # Mettre à jour l'état de la zone
        zone_id = sensor_config.get("zone")
        if zone_id:
            self._update_zone_state(zone_id)
    
    def _handle_window_sensor(self, message: Dict[str, Any]):
        """Gère les événements des capteurs de fenêtre."""
        sensor_id = message.get("sensor_id")
        state = message.get("state")  # "open" ou "closed"
        
        if not sensor_id or not state:
            return
        
        # Vérifier que c'est bien un capteur de fenêtre
        sensor_config = self.sensors.get(sensor_id, {})
        if sensor_config.get("type") != "window":
            return
        
        # Mettre à jour l'état du capteur
        self._window_states[sensor_id] = state
        
        # Si le système est armé et que la fenêtre s'ouvre, déclencher l'alarme
        if state == "open" and (self._system_state == self.STATE_ARMED_AWAY or 
                               (self._system_state == self.STATE_ARMED_HOME and not sensor_config.get("bypass_in_home_mode", False))):
            self._trigger_alarm(sensor_id, "window_opened")
        
        # Mettre à jour l'état de la zone
        zone_id = sensor_config.get("zone")
        if zone_id:
            self._update_zone_state(zone_id)
    
    def _handle_motion_sensor(self, message: Dict[str, Any]):
        """Gère les événements des détecteurs de mouvement."""
        sensor_id = message.get("sensor_id")
        state = message.get("state")  # "active" ou "inactive"
        
        if not sensor_id or not state:
            return
        
        # Vérifier que c'est bien un détecteur de mouvement
        sensor_config = self.sensors.get(sensor_id, {})
        if sensor_config.get("type") != "motion":
            return
        
        # Mettre à jour l'état du capteur
        self._motion_states[sensor_id] = state
        
        # Si le système est armé et qu'un mouvement est détecté, déclencher l'alarme
        if state == "active" and (self._system_state == self.STATE_ARMED_AWAY or 
                                 (self._system_state == self.STATE_ARMED_HOME and not sensor_config.get("bypass_in_home_mode", True))):
            self._trigger_alarm(sensor_id, "motion_detected")
        
        # Mettre à jour l'état de la zone
        zone_id = sensor_config.get("zone")
        if zone_id:
            self._update_zone_state(zone_id)
    
    def _handle_glass_break_sensor(self, message: Dict[str, Any]):
        """Gère les événements des détecteurs de bris de verre."""
        sensor_id = message.get("sensor_id")
        state = message.get("state")  # "triggered" ou "normal"
        
        if not sensor_id or not state:
            return
        
        # Vérifier que c'est bien un détecteur de bris de verre
        sensor_config = self.sensors.get(sensor_id, {})
        if sensor_config.get("type") != "glass_break":
            return
        
        # Si le système est armé et qu'un bris de verre est détecté, déclencher l'alarme immédiatement
        if state == "triggered" and (self._system_state == self.STATE_ARMED_AWAY or self._system_state == self.STATE_ARMED_HOME):
            self._trigger_alarm(sensor_id, "glass_break")
    
    def _handle_smoke_sensor(self, message: Dict[str, Any]):
        """Gère les événements des détecteurs de fumée."""
        sensor_id = message.get("sensor_id")
        state = message.get("state")  # "triggered" ou "normal"
        
        if not sensor_id or not state:
            return
        
        # Vérifier que c'est bien un détecteur de fumée
        sensor_config = self.sensors.get(sensor_id, {})
        if sensor_config.get("type") != "smoke":
            return
        
        # Les détecteurs de fumée déclenchent toujours l'alarme, même si le système est désarmé
        if state == "triggered":
            self._activate_alarm(sensor_id, "smoke_detected")
            
            # Envoyer également une notification aux services d'urgence si configuré
            if self.alarm_settings.get("emergency_services_enabled", False):
                self.message_bus.publish("notification/emergency", {
                    "type": "fire",
                    "sensor_id": sensor_id,
                    "location": sensor_config.get("location", "Unknown")
                })
    
    def _handle_camera_motion(self, message: Dict[str, Any]):
        """Gère les détections de mouvement par caméra."""
        camera_id = message.get("camera_id")
        motion = message.get("motion", False)
        
        if not camera_id:
            return
        
        # Vérifier que la caméra est configurée
        if camera_id not in self.cameras:
            return
        
        # Mettre à jour l'état de la caméra
        self._camera_states[camera_id] = "active" if motion else "inactive"
        
        # Si le système est armé en mode absence et qu'un mouvement est détecté, déclencher l'alarme
        if motion and self._system_state == self.STATE_ARMED_AWAY and self.cameras[camera_id].get("trigger_alarm", True):
            self._trigger_alarm(camera_id, "camera_motion")
            
            # Démarrer l'enregistrement
            self.message_bus.publish("camera/record", {
                "camera_id": camera_id,
                "duration": self.alarm_duration
            })
    
    def _handle_home_mode_changed(self, message: Dict[str, Any]):
        """Gère les changements de mode de la maison."""
        mode = message.get("mode")
        
        if not mode:
            return
        
        self.logger.info(f"Mode de la maison changé: {mode}")
        
        # Ajuster le système de sécurité en fonction du mode
        if mode == "away" and self._system_state == self.STATE_DISARMED:
            # Armer automatiquement le système en mode absence si configuré
            if self.alarm_settings.get("auto_arm_when_away", False):
                self._arm_system("away")
        
        elif mode == "home" and self._system_state == self.STATE_ARMED_AWAY:
            # Désarmer automatiquement le système si configuré
            if self.alarm_settings.get("auto_disarm_when_home", False):
                # Utiliser le code par défaut si configuré
                default_code = self.alarm_settings.get("default_code")
                if default_code:
                    self._disarm_system(default_code)
        
        elif mode == "night" and self._system_state == self.STATE_DISARMED:
            # Armer automatiquement le système en mode présence si configuré
            if self.alarm_settings.get("auto_arm_at_night", False):
                self._arm_system("home")


# Exemple de configuration pour les tests
SAMPLE_CONFIG = {
    "sensors": {
        "door1": {
            "name": "Porte d'entrée",
            "type": "door",
            "zone": "entrance",
            "is_entry_point": True,
            "bypass_in_home_mode": False
        },
        "door2": {
            "name": "Porte arrière",
            "type": "door",
            "zone": "backyard",
            "is_entry_point": True,
            "bypass_in_home_mode": False
        },
        "window1": {
            "name": "Fenêtre salon",
            "type": "window",
            "zone": "living_room",
            "is_entry_point": False,
            "bypass_in_home_mode": False
        },
        "window2": {
            "name": "Fenêtre cuisine",
            "type": "window",
            "zone": "kitchen",
            "is_entry_point": False,
            "bypass_in_home_mode": False
        },
        "motion1": {
            "name": "Mouvement salon",
            "type": "motion",
            "zone": "living_room",
            "bypass_in_home_mode": True
        },
        "motion2": {
            "name": "Mouvement couloir",
            "type": "motion",
            "zone": "hallway",
            "bypass_in_home_mode": True
        },
        "glass1": {
            "name": "Bris de verre salon",
            "type": "glass_break",
            "zone": "living_room",
            "bypass_in_home_mode": False
        },
        "smoke1": {
            "name": "Détecteur de fumée cuisine",
            "type": "smoke",
            "zone": "kitchen",
            "location": "Cuisine"
        }
    },
    "zones": {
        "entrance": {
            "name": "Entrée"
        },
        "backyard": {
            "name": "Jardin arrière"
        },
        "living_room": {
            "name": "Salon"
        },
        "kitchen": {
            "name": "Cuisine"
        },
        "hallway": {
            "name": "Couloir"
        }
    },
    "access_codes": {
        "admin": "1234",
        "user1": "5678",
        "user2": "9012"
    },
    "notifications": {
        "push_enabled": True,
        "sms_enabled": True,
        "sms_recipients": ["+33612345678"],
        "email_enabled": True,
        "email_recipients": ["user@example.com"]
    },
    "alarm": {
        "entry_delay": 30,
        "exit_delay": 60,
        "duration": 300,
        "siren_enabled": True,
        "alarm_lights_enabled": True,
        "require_code_to_arm": False,
        "auto_arm_when_away": True,
        "auto_disarm_when_home": False,
        "auto_arm_at_night": True,
        "default_code": "1234",
        "emergency_services_enabled": False
    },
    "cameras": {
        "cam1": {
            "name": "Caméra entrée",
            "location": "Entrée",
            "trigger_alarm": True
        },
        "cam2": {
            "name": "Caméra jardin",
            "location": "Jardin arrière",
            "trigger_alarm": True
        }
    }
}
    
    def _disarm_system(self, code: str) -> bool:
        """
        Désarme le système de sécurité.
        
        Args:
            code: Code d'accès pour le désarmement
            
        Returns:
            bool: True si désarmé avec succès, False sinon
        """
        # Vérifier le code d'accès
        if not self._validate_access_code(code):
            self.logger.warning("Code d'accès invalide pour le désarmement")
            
            # Ajouter un événement d'échec
            self._add_event("disarm_failed", {
                "reason": "invalid_code"
            })
            
            return False
        
        # Annuler les timers en cours
        if self._entry_timer:
            # Dans une implémentation réelle, nous annulerions le timer ici
            self._entry_timer = None
        
        # Arrêter l'alarme si elle est active
        if self._alarm_active:
            self._stop_alarm()
        
        # Désarmer le système
        previous_state = self._system_state
        self._system_state = self.STATE_DISARMED
        
        # Effacer les capteurs déclenchés
        self._triggered_sensors = {}
        
        # Ajouter un événement
        self._add_event("system_disarmed", {
            "previous_state": previous_state,
            "user": "unknown"  # Dans une implémentation réelle, nous pourrions suivre qui a désarmé le système
        })
        
        # Publier un message de désarmement
        self.message_bus.publish("security/system_disarmed", {
            "timestamp": time.time()
        })
        
        # Mettre à jour l'état
        self._save_state()
        
        return True
    
    def _validate_access_code(self, code: str) -> bool:
        """
        Valide un code d'accès.
        
        Args:
            code: Code d'accès à valider
            
        Returns:
            bool: True si valide, False sinon
        """
        # Vérifier si le code existe dans la liste des codes autorisés
        return code in self._access_codes.values()
    
    def _trigger_alarm(self, sensor_id: str, reason: str):
        """
        Déclenche l'alarme ou le délai d'entrée.
        
        Args:
            sensor_id: Identifiant du capteur déclencheur
            reason: Raison du déclenchement
        """
        # Ne rien faire si le système est désarmé
        if self._system_state == self.STATE_DISARMED:
            return
        
        # Si l'alarme est déjà active, ajouter simplement le capteur à la liste
        if self._alarm_active or self._system_state == self.STATE_TRIGGERED:
            self._triggered_sensors[sensor_id] = time.time()
            return
        
        # Vérifier si c'est un capteur d'entrée qui nécessite un délai
        sensor_config = self.sensors.get(sensor_id, {})
        is_entry_sensor = sensor_config.get("is_entry_point", False)
        
        if is_entry_sensor and self._system_state == self.STATE_ARMED_AWAY:
            # Démarrer le délai d'entrée
            self._start_entry_delay(sensor_id)
        else:
            # Déclencher immédiatement l'alarme
            self._activate_alarm(sensor_id, reason)
    
    def _start_entry_delay(self, sensor_id: str):
        """
        Démarre le délai d'entrée.
        
        Args:
            sensor_id: Identifiant du capteur qui a déclenché le délai
        """
        self.logger.info(f"Début du délai d'entrée ({self.alarm_delay}s) déclenché par {sensor_id}")
        
        # Enregistrer le capteur déclencheur
        self._triggered_sensors[sensor_id] = time.time()
        
        # Dans une implémentation réelle, nous utiliserions un timer
        # Ici, nous simulons simplement le début du délai
        self._entry_timer = {
            "sensor_id": sensor_id,
            "end_time": time.time() + self.alarm_delay
        }
        
        # Publier un message pour le délai d'entrée
        self.message_bus.publish("security/entry_delay", {
            "sensor_id": sensor_id,
            "delay": self.alarm_delay,
            "end_time": time.time() + self.alarm_delay
        })
        
        # Ajouter un événement
        self._add_event("entry_delay", {
            "sensor_id": sensor_id,
            "delay": self.alarm_delay
        })
        
        # Dans une implémentation réelle, nous définirions un callback pour activer l'alarme
        # après le délai d'entrée si le système n'est pas désarmé. Pour cette simulation,
        # nous supposons que l'événement se produit.
        # self._activate_alarm(sensor_id, "entry_timeout")
    
    def _activate_alarm(self, sensor_id: str, reason: str):
        """
        Active l'alarme.
        
        Args:
            sensor_id: Identifiant du capteur déclencheur
            reason: Raison du déclenchement
        """
        self.logger.info(f"Activation de l'alarme, déclenchée par {sensor_id} ({reason})")
        
        # Mettre à jour l'état du système
        self._system_state = self.STATE_TRIGGERED
        self._alarm_active = True
        self._alarm_trigger_time = time.time()
        self._triggered_sensors[sensor_id] = time.time()
        
        # Annuler le délai d'entrée s'il est actif
        if self._entry_timer:
            self._entry_timer = None
        
        # Ajouter un événement
        self._add_event("alarm_triggered", {
            "sensor_id": sensor_id,
            "reason": reason,
            "timestamp": time.time()
        })
        
        # Publier un message d'alarme
        self.message_bus.publish("security/alarm_triggered", {
            "sensor_id": sensor_id,
            "reason": reason,
            "timestamp": time.time()
        })
        
        # Envoyer des notifications
        self._send_alarm_notification(sensor_id, reason)
        
        # Activer les dispositifs d'alarme
        self._activate_alarm_devices()
        
        # Dans une implémentation réelle, nous utiliserions un timer pour arrêter l'alarme
        # après la durée configurée. Pour cette simulation, nous supposons que l'événement se produit.
        # self._schedule_alarm_stop()
        
        # Mettre à jour l'état
        self._save_state()
        