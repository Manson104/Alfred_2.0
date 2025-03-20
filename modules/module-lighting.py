import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from modules.base_module import BaseModule
from modules.message_bus import MessageBus
from modules.state_manager import StateManager

class LightingModule(BaseModule):
    """
    Module de gestion de l'éclairage intelligent.
    Permet de contrôler différents systèmes d'éclairage en fonction de la présence,
    la luminosité ambiante, l'heure de la journée et des planifications.
    """
    
    def __init__(self, module_id: str, config: Dict[str, Any], message_bus: MessageBus, state_manager: StateManager):
        """
        Initialise le module d'éclairage.
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration du module
            message_bus: Instance du bus de messages
            state_manager: Instance du gestionnaire d'état
        """
        super().__init__(module_id, "lighting", config, message_bus, state_manager)
        
        # Configuration des lumières
        self.lights = config.get("lights", {})
        
        # Configuration des scènes d'éclairage
        self.scenes = config.get("scenes", {})
        
        # Configuration des planifications
        self.schedules = config.get("schedules", {})
        
        # Configuration des modes
        self.auto_mode_enabled = config.get("auto_mode_enabled", True)
        self.presence_based_lighting = config.get("presence_based_lighting", True)
        self.light_sensor_threshold = config.get("light_sensor_threshold", 200)  # lux
        self.nightlight_mode = config.get("nightlight_mode", False)
        self.nightlight_brightness = config.get("nightlight_brightness", 10)  # %
        
        # État interne
        self._active_lights = {}  # light_id -> {brightness, color, etc.}
        self._active_scene = None
        self._last_motion = {}  # room_id -> timestamp
        self._ambient_light_levels = {}  # sensor_id -> lux
        
        self.logger.info(f"Module d'éclairage initialisé avec {len(self.lights)} lumières et {len(self.scenes)} scènes")
        
        # Enregistrement des gestionnaires de messages
        self._register_handlers()
    
    def _register_handlers(self):
        """Enregistre les gestionnaires de messages pour ce module."""
        self.message_bus.register_handler("lighting/set", self._handle_set_light)
        self.message_bus.register_handler("lighting/toggle", self._handle_toggle_light)
        self.message_bus.register_handler("lighting/scene", self._handle_set_scene)
        self.message_bus.register_handler("lighting/status", self._handle_status_request)
        self.message_bus.register_handler("sensor/motion", self._handle_motion_detected)
        self.message_bus.register_handler("sensor/light", self._handle_light_sensor)
        self.message_bus.register_handler("home/mode", self._handle_home_mode_changed)
    
    def start(self):
        """Démarre le module et initialise les planifications."""
        self.logger.info("Démarrage du module d'éclairage")
        
        # Charger l'état précédent si disponible
        self._load_state()
        
        # Initialiser les planifications
        self._setup_schedules()
        
        # Définir le statut comme actif
        self.active = True
    
    def stop(self):
        """Arrête le module et sauvegarde l'état actuel."""
        self.logger.info("Arrêt du module d'éclairage")
        
        # Sauvegarde de l'état
        self._save_state()
        
        # Définir le statut comme inactif
        self.active = False
    
    def _load_state(self):
        """Charge l'état précédent depuis le gestionnaire d'état."""
        state = self.state_manager.get_state(f"{self.module_id}_state")
        if state:
            self.logger.info("Chargement de l'état précédent")
            if "active_lights" in state:
                # Vérifier si les lumières sont toujours valides dans la configuration
                valid_lights = {light_id: settings 
                              for light_id, settings in state["active_lights"].items() 
                              if light_id in self.lights}
                self._active_lights = valid_lights
            
            if "active_scene" in state and state["active_scene"] in self.scenes:
                self._active_scene = state["active_scene"]
    
    def _save_state(self):
        """Sauvegarde l'état actuel dans le gestionnaire d'état."""
        state = {
            "active_lights": self._active_lights,
            "active_scene": self._active_scene,
            "last_update": time.time()
        }
        self.state_manager.set_state(f"{self.module_id}_state", state)
    
    def _setup_schedules(self):
        """Configure les planifications d'éclairage."""
        self.logger.info("Configuration des planifications d'éclairage")
        
        # Ici, nous pourrions ajouter des tâches planifiées
        # Pour cet exemple, nous simulons simplement la configuration
        for schedule_id, schedule in self.schedules.items():
            self.logger.info(f"Planification configurée: {schedule_id}")
            
            # Dans une implémentation réelle, nous utiliserions un scheduler
            # comme APScheduler pour configurer les tâches
    
    def _set_light(self, light_id: str, state: bool, brightness: Optional[int] = None, 
                   color: Optional[str] = None, transition: Optional[int] = None) -> bool:
        """
        Définit l'état d'une lumière.
        
        Args:
            light_id: Identifiant de la lumière
            state: État (True = allumé, False = éteint)
            brightness: Luminosité (0-100, optionnel)
            color: Couleur en format hex ou nom (optionnel)
            transition: Durée de transition en secondes (optionnel)
            
        Returns:
            bool: True si réussi, False sinon
        """
        if light_id not in self.lights:
            self.logger.warning(f"Lumière {light_id} inconnue")
            return False
        
        light_config = self.lights[light_id]
        
        # Vérifier les capacités de la lumière
        if brightness is not None and not light_config.get("dimmable", False):
            self.logger.warning(f"Lumière {light_id} ne supporte pas la gradation")
            brightness = None
        
        if color is not None and not light_config.get("color", False):
            self.logger.warning(f"Lumière {light_id} ne supporte pas les couleurs")
            color = None
        
        # Construire les paramètres de commande
        params = {
            "state": state
        }
        
        if brightness is not None:
            params["brightness"] = max(0, min(100, brightness))
        
        if color is not None:
            params["color"] = color
            
        if transition is not None:
            params["transition"] = transition
        
        # Dans une implémentation réelle, nous enverrions des commandes aux dispositifs physiques
        # Ici, nous simulons simplement le changement d'état
        
        if state:
            self.logger.info(f"Allumage de la lumière {light_id} avec paramètres: {params}")
            
            # Mettre à jour l'état interne
            self._active_lights[light_id] = params
        else:
            self.logger.info(f"Extinction de la lumière {light_id}")
            
            # Supprimer de l'état interne si éteint
            if light_id in self._active_lights:
                del self._active_lights[light_id]
        
        # Publier un événement
        self.message_bus.publish("lighting/light_changed", {
            "light_id": light_id,
            "params": params,
            "timestamp": time.time()
        })
        
        # Mettre à jour l'état
        self._save_state()
        
        return True
    
    def _toggle_light(self, light_id: str) -> bool:
        """
        Bascule l'état d'une lumière (allumé/éteint).
        
        Args:
            light_id: Identifiant de la lumière
            
        Returns:
            bool: Nouvel état (True = allumé, False = éteint)
        """
        if light_id not in self.lights:
            self.logger.warning(f"Lumière {light_id} inconnue")
            return False
        
        # Déterminer l'état actuel
        current_state = light_id in self._active_lights
        
        # Basculer l'état
        if current_state:
            return self._set_light(light_id, False)
        else:
            return self._set_light(light_id, True)
    
    def _set_scene(self, scene_id: str) -> bool:
        """
        Active une scène d'éclairage prédéfinie.
        
        Args:
            scene_id: Identifiant de la scène
            
        Returns:
            bool: True si activé avec succès, False sinon
        """
        if scene_id not in self.scenes:
            self.logger.warning(f"Scène {scene_id} inconnue")
            return False
        
        scene = self.scenes[scene_id]
        
        self.logger.info(f"Activation de la scène {scene_id}")
        
        # Appliquer les paramètres de lumière pour cette scène
        for light_setting in scene.get("lights", []):
            light_id = light_setting.get("id")
            state = light_setting.get("state", True)
            brightness = light_setting.get("brightness")
            color = light_setting.get("color")
            transition = light_setting.get("transition", 1)
            
            self._set_light(light_id, state, brightness, color, transition)
        
        # Mettre à jour la scène active
        self._active_scene = scene_id
        
        # Publier un événement
        self.message_bus.publish("lighting/scene_activated", {
            "scene_id": scene_id,
            "timestamp": time.time()
        })
        
        # Mettre à jour l'état
        self._save_state()
        
        return True
    
    def _handle_motion_based_lighting(self, room_id: str, motion: bool):
        """
        Gère l'éclairage basé sur la détection de mouvement.
        
        Args:
            room_id: Identifiant de la pièce
            motion: État de détection (True = mouvement détecté)
        """
        if not self.auto_mode_enabled or not self.presence_based_lighting:
            return
        
        # Mettre à jour le timestamp du dernier mouvement
        if motion:
            self._last_motion[room_id] = time.time()
        
        # Trouver les lumières dans cette pièce
        room_lights = [light_id for light_id, config in self.lights.items() 
                      if config.get("room") == room_id]
        
        if not room_lights:
            return
        
        # Vérifier les niveaux de luminosité si des capteurs sont disponibles
        light_level = None
        for sensor_id, lux in self._ambient_light_levels.items():
            sensor_room = self.state_manager.get_state(f"sensor_{sensor_id}")
            if sensor_room and sensor_room.get("room") == room_id:
                light_level = lux
                break
        
        # Déterminer si nous devons allumer les lumières
        should_turn_on = (
            motion and 
            (light_level is None or light_level < self.light_sensor_threshold)
        )
        
        now = datetime.now()
        is_night = 22 <= now.hour or now.hour < 6
        
        for light_id in room_lights:
            if should_turn_on:
                brightness = self.nightlight_brightness if is_night and self.nightlight_mode else None
                self._set_light(light_id, True, brightness)
            elif not motion and light_id in self._active_lights:
                # Vérifier si le mouvement s'est arrêté depuis un certain temps
                timeout = self.lights[light_id].get("motion_timeout", 300)  # 5 minutes par défaut
                last_motion_time = self._last_motion.get(room_id, 0)
                if time.time() - last_motion_time > timeout:
                    self._set_light(light_id, False)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Récupère le statut actuel du système d'éclairage.
        
        Returns:
            Dict: Statut du système d'éclairage
        """
        return {
            "active_lights": self._active_lights,
            "active_scene": self._active_scene,
            "light_count": len(self.lights),
            "scene_count": len(self.scenes),
            "auto_mode": self.auto_mode_enabled,
            "presence_based": self.presence_based_lighting,
            "nightlight_mode": self.nightlight_mode
        }
    
    # Gestionnaires de messages
    
    def _handle_set_light(self, message: Dict[str, Any]):
        """Gère les demandes de changement d'état de lumière."""
        light_id = message.get("light_id")
        state = message.get("state")
        brightness = message.get("brightness")
        color = message.get("color")
        transition = message.get("transition")
        
        if not light_id or state is None:
            self.logger.warning("Demande de changement d'état de lumière sans identifiant ou état")
            return
        
        success = self._set_light(light_id, state, brightness, color, transition)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": success,
                "light_id": light_id,
                "action": "set"
            })
    
    def _handle_toggle_light(self, message: Dict[str, Any]):
        """Gère les demandes de bascule d'état de lumière."""
        light_id = message.get("light_id")
        
        if not light_id:
            self.logger.warning("Demande de bascule d'état de lumière sans identifiant")
            return
        
        new_state = self._toggle_light(light_id)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "light_id": light_id,
                "action": "toggle",
                "new_state": new_state
            })
    
    def _handle_set_scene(self, message: Dict[str, Any]):
        """Gère les demandes d'activation de scène."""
        scene_id = message.get("scene_id")
        
        if not scene_id:
            self.logger.warning("Demande d'activation de scène sans identifiant")
            return
        
        success = self._set_scene(scene_id)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": success,
                "scene_id": scene_id,
                "action": "set_scene"
            })
    
    def _handle_status_request(self, message: Dict[str, Any]):
        """Gère les demandes de statut."""
        status = self.get_status()
        
        # Répondre avec le statut
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], status)
    
    def _handle_motion_detected(self, message: Dict[str, Any]):
        """Gère les détections de mouvement."""
        sensor_id = message.get("sensor_id")
        motion = message.get("state", False)
        
        if not sensor_id:
            return
        
        # Récupérer les informations sur le capteur
        sensor_info = self.state_manager.get_state(f"sensor_{sensor_id}")
        if not sensor_info or "room" not in sensor_info:
            return
        
        room_id = sensor_info["room"]
        
        # Traiter l'éclairage basé sur le mouvement
        self._handle_motion_based_lighting(room_id, motion)
    
    def _handle_light_sensor(self, message: Dict[str, Any]):
        """Gère les mises à jour des capteurs de luminosité."""
        sensor_id = message.get("sensor_id")
        lux = message.get("value", 0)
        
        if not sensor_id:
            return
        
        # Mettre à jour les niveaux de luminosité ambiante
        self._ambient_light_levels[sensor_id] = lux
        
        # Si en mode automatique, vérifier si nous devons ajuster les lumières
        if self.auto_mode_enabled:
            # Récupérer les informations sur le capteur
            sensor_info = self.state_manager.get_state(f"sensor_{sensor_id}")
            if not sensor_info or "room" not in sensor_info:
                return
            
            room_id = sensor_info["room"]
            
            # Vérifier s'il y a eu un mouvement récent dans cette pièce
            has_recent_motion = False
            if room_id in self._last_motion:
                timeout = 300  # 5 minutes par défaut
                has_recent_motion = (time.time() - self._last_motion[room_id]) < timeout
            
            # Trouver les lumières dans cette pièce
            room_lights = [light_id for light_id, config in self.lights.items() 
                          if config.get("room") == room_id]
            
            # Ajuster les lumières en fonction du niveau de luminosité
            for light_id in room_lights:
                if has_recent_motion:
                    if lux < self.light_sensor_threshold and light_id not in self._active_lights:
                        self._set_light(light_id, True)
                    elif lux > self.light_sensor_threshold + 50 and light_id in self._active_lights:
                        self._set_light(light_id, False)
    
    def _handle_home_mode_changed(self, message: Dict[str, Any]):
        """Gère les changements de mode de la maison."""
        mode = message.get("mode")
        
        if not mode:
            return
        
        self.logger.info(f"Mode de la maison changé: {mode}")
        
        # Ajuster les paramètres en fonction du mode
        if mode == "away":
            # Éteindre toutes les lumières sauf celles marquées pour la sécurité
            for light_id in list(self._active_lights.keys()):
                if not self.lights.get(light_id, {}).get("security", False):
                    self._set_light(light_id, False)
            
            # Désactiver le mode automatique basé sur la présence
            self.presence_based_lighting = False
            
        elif mode == "home":
            # Réactiver le mode automatique basé sur la présence
            self.presence_based_lighting = True
            
        elif mode == "night":
            # Activer le mode veilleuse
            self.nightlight_mode = True
            
            # Ajuster les lumières actuellement allumées
            for light_id in self._active_lights:
                if self.lights.get(light_id, {}).get("dimmable", False):
                    self._set_light(light_id, True, self.nightlight_brightness)
            
        elif mode == "day":
            # Désactiver le mode veilleuse
            self.nightlight_mode = False