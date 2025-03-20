import logging
import time
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta

from modules.base_module import BaseModule
from modules.message_bus import MessageBus
from modules.state_manager import StateManager

class PresenceModule(BaseModule):
    """
    Module de gestion de la présence et des occupants.
    Permet de suivre qui est présent dans la maison, de gérer les arrivées et départs,
    et de servir de base pour l'automatisation personnalisée.
    """
    
    # États de présence
    HOME = "home"
    AWAY = "away"
    EXTENDED_AWAY = "extended_away"
    JUST_ARRIVED = "just_arrived"
    JUST_LEFT = "just_left"
    
    # Modes de la maison
    MODE_HOME = "home"
    MODE_AWAY = "away"
    MODE_NIGHT = "night"
    MODE_VACATION = "vacation"
    
    def __init__(self, module_id: str, config: Dict[str, Any], message_bus: MessageBus, state_manager: StateManager):
        """
        Initialise le module de présence.
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration du module
            message_bus: Instance du bus de messages
            state_manager: Instance du gestionnaire d'état
        """
        super().__init__(module_id, "presence", config, message_bus, state_manager)
        
        # Configuration des personnes
        self.persons = config.get("persons", {})
        
        # Configuration des appareils
        self.devices = config.get("devices", {})
        
        # Configuration des zones
        self.zones = config.get("zones", {})
        
        # Configuration des règles de présence
        self.rules = config.get("rules", {})
        
        # Configuration des délais
        self.away_timeout = config.get("away_timeout", 600)  # 10 minutes
        self.extended_away_timeout = config.get("extended_away_timeout", 86400)  # 24 heures
        self.presence_update_interval = config.get("presence_update_interval", 60)  # 1 minute
        
        # Configuration des notifications
        self.notifications_enabled = config.get("notifications_enabled", True)
        
        # État interne
        self._person_states = {}  # person_id -> {state, last_seen, location, etc.}
        self._device_states = {}  # device_id -> {state, last_seen, owner, etc.}
        self._home_occupancy = {}  # person_id -> timestamp
        self._current_mode = self.MODE_HOME
        self._last_mode_change = time.time()
        self._last_presence_update = 0
        self._presence_history = []  # [{timestamp, event, person, etc.}, ...]
        
        self.logger.info(f"Module de présence initialisé avec {len(self.persons)} personnes et {len(self.devices)} appareils")
        
        # Enregistrement des gestionnaires de messages
        self._register_handlers()
    
    def _register_handlers(self):
        """Enregistre les gestionnaires de messages pour ce module."""
        self.message_bus.register_handler("presence/update", self._handle_presence_update)
        self.message_bus.register_handler("presence/manual_update", self._handle_manual_update)
        self.message_bus.register_handler("presence/status", self._handle_status_request)
        self.message_bus.register_handler("device/connected", self._handle_device_connected)
        self.message_bus.register_handler("device/disconnected", self._handle_device_disconnected)
        self.message_bus.register_handler("sensor/motion", self._handle_motion_detected)
        self.message_bus.register_handler("sensor/door", self._handle_door_event)
        self.message_bus.register_handler("security/system_armed", self._handle_security_armed)
        self.message_bus.register_handler("security/system_disarmed", self._handle_security_disarmed)
        self.message_bus.register_handler("location/update", self._handle_location_update)
        self.message_bus.register_handler("home/mode/set", self._handle_mode_set)
    
    def start(self):
        """Démarre le module."""
        self.logger.info("Démarrage du module de présence")
        
        # Charger l'état précédent si disponible
        self._load_state()
        
        # Initialiser les états des personnes et appareils
        self._initialize_states()
        
        # Définir le statut comme actif
        self.active = True
    
    def stop(self):
        """Arrête le module et sauvegarde l'état actuel."""
        self.logger.info("Arrêt du module de présence")
        
        # Sauvegarde de l'état
        self._save_state()
        
        # Définir le statut comme inactif
        self.active = False
    
    def _load_state(self):
        """Charge l'état précédent depuis le gestionnaire d'état."""
        state = self.state_manager.get_state(f"{self.module_id}_state")
        if state:
            self.logger.info("Chargement de l'état précédent")
            
            if "person_states" in state:
                self._person_states = state["person_states"]
            
            if "device_states" in state:
                self._device_states = state["device_states"]
            
            if "home_occupancy" in state:
                self._home_occupancy = state["home_occupancy"]
            
            if "current_mode" in state:
                self._current_mode = state["current_mode"]
            
            if "last_mode_change" in state:
                self._last_mode_change = state["last_mode_change"]
            
            if "presence_history" in state:
                self._presence_history = state["presence_history"]
    
    def _save_state(self):
        """Sauvegarde l'état actuel dans le gestionnaire d'état."""
        state = {
            "person_states": self._person_states,
            "device_states": self._device_states,
            "home_occupancy": self._home_occupancy,
            "current_mode": self._current_mode,
            "last_mode_change": self._last_mode_change,
            "presence_history": self._presence_history[:100],  # Limiter l'historique
            "last_update": time.time()
        }
        self.state_manager.set_state(f"{self.module_id}_state", state)
    
    def _initialize_states(self):
        """Initialise les états des personnes et appareils."""
        # Initialiser les états des personnes
        for person_id, person_config in self.persons.items():
            if person_id not in self._person_states:
                self._person_states[person_id] = {
                    "state": self.AWAY,
                    "last_seen": 0,
                    "location": None,
                    "devices": []
                }
        
        # Initialiser les états des appareils
        for device_id, device_config in self.devices.items():
            if device_id not in self._device_states:
                owner = device_config.get("owner")
                self._device_states[device_id] = {
                    "state": "disconnected",
                    "last_seen": 0,
                    "owner": owner
                }
        
        # Mettre à jour le mode de la maison en fonction de l'occupation
        self._update_home_mode()
    
    def _update_presence(self):
        """Met à jour les états de présence en fonction des dernières activités."""
        current_time = time.time()
        
        # Ne pas mettre à jour trop fréquemment
        if current_time - self._last_presence_update < self.presence_update_interval:
            return
        
        self._last_presence_update = current_time
        changes_detected = False
        
        # Mettre à jour les états des personnes
        for person_id, person_state in self._person_states.items():
            previous_state = person_state["state"]
            
            # Vérifier l'activité récente des appareils de cette personne
            person_devices = [device_id for device_id, device_config in self.devices.items() 
                             if device_config.get("owner") == person_id]
            
            latest_device_activity = 0
            active_devices = []
            
            for device_id in person_devices:
                if device_id in self._device_states:
                    device_state = self._device_states[device_id]
                    if device_state["state"] == "connected":
                        latest_device_activity = max(latest_device_activity, device_state["last_seen"])
                        active_devices.append(device_id)
            
            # Mettre à jour l'état en fonction de l'activité
            if active_devices:
                if previous_state == self.AWAY or previous_state == self.EXTENDED_AWAY:
                    new_state = self.JUST_ARRIVED
                    self._add_history_event("arrival", person_id)
                    changes_detected = True
                elif previous_state == self.JUST_ARRIVED:
                    new_state = self.HOME
                    changes_detected = True
                else:
                    new_state = self.HOME
                
                # Mettre à jour l'occupation
                self._home_occupancy[person_id] = current_time
                
            else:
                # Vérifier les délais d'absence
                last_seen = person_state["last_seen"]
                if last_seen > 0:
                    time_away = current_time - last_seen
                    
                    if previous_state == self.HOME:
                        if time_away > self.away_timeout:
                            new_state = self.JUST_LEFT
                            self._add_history_event("departure", person_id)
                            changes_detected = True
                            # Supprimer de l'occupation
                            if person_id in self._home_occupancy:
                                del self._home_occupancy[person_id]
                        else:
                            new_state = self.HOME
                    elif previous_state == self.JUST_LEFT:
                        if time_away > self.away_timeout * 2:
                            new_state = self.AWAY
                            changes_detected = True
                        else:
                            new_state = self.JUST_LEFT
                    elif previous_state == self.AWAY:
                        if time_away > self.extended_away_timeout:
                            new_state = self.EXTENDED_AWAY
                            changes_detected = True
                        else:
                            new_state = self.AWAY
                    else:
                        new_state = previous_state
                else:
                    new_state = self.AWAY
            
            # Mettre à jour l'état
            if new_state != previous_state:
                person_state["state"] = new_state
                
                # Publier un événement de changement d'état
                self.message_bus.publish("presence/state_changed", {
                    "person_id": person_id,
                    "previous_state": previous_state,
                    "new_state": new_state,
                    "timestamp": current_time
                })
            
            # Mettre à jour les appareils associés
            person_state["devices"] = active_devices
        
        # Si des changements ont été détectés, mettre à jour le mode de la maison
        if changes_detected:
            self._update_home_mode()
            self._save_state()
    
    def _update_home_mode(self):
        """Met à jour le mode de la maison en fonction de l'occupation."""
        current_time = time.time()
        previous_mode = self._current_mode
        
        # Compter les personnes présentes
        home_persons = [person_id for person_id, person_state in self._person_states.items() 
                       if person_state["state"] in [self.HOME, self.JUST_ARRIVED]]
        
        # Déterminer le nouveau mode
        new_mode = previous_mode
        
        if not home_persons:
            # Personne à la maison
            if previous_mode == self.MODE_HOME or previous_mode == self.MODE_NIGHT:
                new_mode = self.MODE_AWAY
            # Conserver le mode vacances si déjà activé
        else:
            # Au moins une personne à la maison
            if previous_mode == self.MODE_AWAY or previous_mode == self.MODE_VACATION:
                new_mode = self.MODE_HOME
            # Conserver le mode nuit si déjà activé
        
        # Appliquer le changement si nécessaire
        if new_mode != previous_mode:
            self._current_mode = new_mode
            self._last_mode_change = current_time
            
            # Publier un événement de changement de mode
            self.message_bus.publish("home/mode", {
                "mode": new_mode,
                "previous_mode": previous_mode,
                "timestamp": current_time
            })
            
            # Notifier le changement si les notifications sont activées
            if self.notifications_enabled:
                self._send_mode_notification(new_mode, previous_mode)
    
    def _add_history_event(self, event_type: str, person_id: str, details: Dict[str, Any] = None):
        """
        Ajoute un événement à l'historique de présence.
        
        Args:
            event_type: Type d'événement ("arrival", "departure", etc.)
            person_id: Identifiant de la personne concernée
            details: Détails supplémentaires (optionnel)
        """
        if not details:
            details = {}
            
        event = {
            "timestamp": time.time(),
            "type": event_type,
            "person_id": person_id,
            "details": details
        }
        
        # Ajouter l'événement à l'historique
        self._presence_history.insert(0, event)
        
        # Limiter la taille de l'historique
        max_events = 500
        if len(self._presence_history) > max_events:
            self._presence_history = self._presence_history[:max_events]
    
    def _send_mode_notification(self, new_mode: str, previous_mode: str):
        """
        Envoie une notification de changement de mode.
        
        Args:
            new_mode: Nouveau mode de la maison
            previous_mode: Ancien mode de la maison
        """
        mode_names = {
            self.MODE_HOME: "Présence",
            self.MODE_AWAY: "Absence",
            self.MODE_NIGHT: "Nuit",
            self.MODE_VACATION: "Vacances"
        }
        
        message = f"Mode de la maison changé de {mode_names.get(previous_mode, previous_mode)} à {mode_names.get(new_mode, new_mode)}"
        
        self.message_bus.publish("notification/push", {
            "title": "Changement de mode",
            "message": message,
            "priority": "normal"
        })
    
    def get_status(self) -> Dict[str, Any]:
        """
        Récupère le statut actuel du module de présence.
        
        Returns:
            Dict: Statut du module de présence
        """
        # Mettre à jour les états de présence
        self._update_presence()
        
        # Compter les personnes par état
        person_counts = {
            self.HOME: 0,
            self.AWAY: 0,
            self.EXTENDED_AWAY: 0,
            self.JUST_ARRIVED: 0,
            self.JUST_LEFT: 0
        }
        
        for person_state in self._person_states.values():
            state = person_state["state"]
            if state in person_counts:
                person_counts[state] += 1
        
        # Liste des personnes à la maison
        home_persons = [person_id for person_id, person_state in self._person_states.items() 
                       if person_state["state"] in [self.HOME, self.JUST_ARRIVED]]
        
        return {
            "mode": self._current_mode,
            "last_mode_change": self._last_mode_change,
            "person_counts": person_counts,
            "home_persons": home_persons,
            "total_persons": len(self._person_states),
            "last_events": self._presence_history[:5]
        }
    
    def get_person_status(self, person_id: str) -> Dict[str, Any]:
        """
        Récupère le statut d'une personne spécifique.
        
        Args:
            person_id: Identifiant de la personne
            
        Returns:
            Dict: Statut de la personne
        """
        if person_id not in self._person_states:
            return None
            
        person_state = self._person_states[person_id]
        person_config = self.persons.get(person_id, {})
        
        # Récupérer les événements récents de cette personne
        recent_events = [event for event in self._presence_history[:20] 
                        if event["person_id"] == person_id]
        
        return {
            "id": person_id,
            "name": person_config.get("name", person_id),
            "state": person_state["state"],
            "last_seen": person_state["last_seen"],
            "location": person_state["location"],
            "devices": person_state["devices"],
            "recent_events": recent_events
        }
    
    def get_history(self, limit: int = 20, person_id: str = None, event_type: str = None) -> List[Dict[str, Any]]:
        """
        Récupère l'historique de présence filtré.
        
        Args:
            limit: Nombre maximum d'événements à retourner
            person_id: Identifiant de la personne pour filtrer (optionnel)
            event_type: Type d'événement pour filtrer (optionnel)
            
        Returns:
            List: Liste des événements filtrés
        """
        filtered_events = self._presence_history
        
        if person_id:
            filtered_events = [event for event in filtered_events if event["person_id"] == person_id]
            
        if event_type:
            filtered_events = [event for event in filtered_events if event["type"] == event_type]
            
        return filtered_events[:limit]
    
    # Gestionnaires de messages
    
    def _handle_presence_update(self, message: Dict[str, Any]):
        """Gère les demandes de mise à jour de présence."""
        # Forcer une mise à jour des états de présence
        self._update_presence()
        
        # Répondre avec le statut
        if "reply_topic" in message:
            status = self.get_status()
            self.message_bus.publish(message["reply_topic"], status)
    
    def _handle_manual_update(self, message: Dict[str, Any]):
        """Gère les mises à jour manuelles de présence."""
        person_id = message.get("person_id")
        state = message.get("state")
        
        if not person_id or not state or person_id not in self._person_states:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "invalid_mode"
                })
            return
        
        current_time = time.time()
        previous_mode = self._current_mode
        
        # Mettre à jour le mode
        self._current_mode = mode
        self._last_mode_change = current_time
        
        # Publier un événement de changement de mode
        self.message_bus.publish("home/mode", {
            "mode": mode,
            "previous_mode": previous_mode,
            "timestamp": current_time,
            "source": "manual"
        })
        
        # Notifier le changement si les notifications sont activées
        if self.notifications_enabled:
            self._send_mode_notification(mode, previous_mode)
        
        # Sauvegarder l'état
        self._save_state()
        
        # Répondre avec succès
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "previous_mode": previous_mode,
                "new_mode": mode
            })
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calcule la distance approximative entre deux points GPS en mètres.
        Utilise la formule de Haversine.
        
        Args:
            lat1: Latitude du premier point
            lon1: Longitude du premier point
            lat2: Latitude du deuxième point
            lon2: Longitude du deuxième point
            
        Returns:
            float: Distance en mètres
        """
        from math import sin, cos, sqrt, atan2, radians
        
        # Rayon approximatif de la Terre en mètres
        R = 6371000.0
        
        # Convertir les degrés en radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Différence de latitude et longitude
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        # Formule de Haversine
        a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance = R * c
        
        return distance


# Exemple de configuration pour les tests
SAMPLE_CONFIG = {
    "persons": {
        "person1": {
            "name": "John Doe",
            "zones": ["living_room", "kitchen", "bedroom_master"],
            "notifications": True
        },
        "person2": {
            "name": "Jane Doe",
            "zones": ["living_room", "kitchen", "bedroom_master"],
            "notifications": True
        },
        "person3": {
            "name": "Kid Doe",
            "zones": ["living_room", "bedroom_kids"],
            "notifications": False
        }
    },
    "devices": {
        "phone1": {
            "name": "John's Phone",
            "owner": "person1",
            "type": "mobile"
        },
        "phone2": {
            "name": "Jane's Phone",
            "owner": "person2",
            "type": "mobile"
        },
        "tablet1": {
            "name": "Family Tablet",
            "owner": "person3",
            "type": "tablet"
        },
        "laptop1": {
            "name": "John's Laptop",
            "owner": "person1",
            "type": "laptop"
        },
        "laptop2": {
            "name": "Jane's Laptop",
            "owner": "person2",
            "type": "laptop"
        }
    },
    "zones": {
        "entrance": {
            "name": "Entrée"
        },
        "living_room": {
            "name": "Salon"
        },
        "kitchen": {
            "name": "Cuisine"
        },
        "bedroom_master": {
            "name": "Chambre principale"
        },
        "bedroom_kids": {
            "name": "Chambre enfants"
        },
        "bathroom": {
            "name": "Salle de bain"
        },
        "garage": {
            "name": "Garage"
        }
    },
    "rules": {
        "home_location": {
            "latitude": 48.8566,
            "longitude": 2.3522,
            "radius": 100  # mètres
        },
        "work_locations": {
            "person1": {
                "latitude": 48.8484,
                "longitude": 2.3725,
                "radius": 200
            },
            "person2": {
                "latitude": 48.8331,
                "longitude": 2.3264,
                "radius": 200
            }
        }
    },
    "away_timeout": 600,  # 10 minutes
    "extended_away_timeout": 86400,  # 24 heures
    "presence_update_interval": 60,  # 1 minute
    "notifications_enabled": True
} {
                    "success": False,
                    "error": "invalid_parameters"
                })
            return
        
        # Vérifier que l'état est valide
        valid_states = [self.HOME, self.AWAY, self.EXTENDED_AWAY]
        if state not in valid_states:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "invalid_state"
                })
            return
        
        # Récupérer l'état précédent
        previous_state = self._person_states[person_id]["state"]
        
        # Mettre à jour l'état
        self._person_states[person_id]["state"] = state
        self._person_states[person_id]["last_seen"] = time.time()
        
        # Gérer l'occupation
        if state == self.HOME:
            self._home_occupancy[person_id] = time.time()
            if previous_state == self.AWAY or previous_state == self.EXTENDED_AWAY:
                self._add_history_event("manual_arrival", person_id, {"source": "manual"})
        else:
            if person_id in self._home_occupancy:
                del self._home_occupancy[person_id]
            if previous_state == self.HOME or previous_state == self.JUST_ARRIVED:
                self._add_history_event("manual_departure", person_id, {"source": "manual"})
        
        # Publier un événement de changement d'état
        self.message_bus.publish("presence/state_changed", {
            "person_id": person_id,
            "previous_state": previous_state,
            "new_state": state,
            "timestamp": time.time(),
            "source": "manual"
        })
        
        # Mettre à jour le mode de la maison
        self._update_home_mode()
        
        # Sauvegarder l'état
        self._save_state()
        
        # Répondre avec succès
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "person_id": person_id,
                "previous_state": previous_state,
                "new_state": state
            })
    
    def _handle_status_request(self, message: Dict[str, Any]):
        """Gère les demandes de statut."""
        person_id = message.get("person_id")
        
        if person_id:
            # Statut d'une personne spécifique
            status = self.get_person_status(person_id)
        else:
            # Statut global
            status = self.get_status()
        
        # Répondre avec le statut
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], status)
    
    def _handle_device_connected(self, message: Dict[str, Any]):
        """Gère les connexions d'appareils."""
        device_id = message.get("device_id")
        
        if not device_id or device_id not in self.devices:
            return
            
        current_time = time.time()
        
        # Mettre à jour l'état de l'appareil
        if device_id in self._device_states:
            self._device_states[device_id]["state"] = "connected"
            self._device_states[device_id]["last_seen"] = current_time
        else:
            owner = self.devices[device_id].get("owner")
            self._device_states[device_id] = {
                "state": "connected",
                "last_seen": current_time,
                "owner": owner
            }
        
        # Mettre à jour l'état de la personne associée
        owner = self.devices[device_id].get("owner")
        if owner and owner in self._person_states:
            self._person_states[owner]["last_seen"] = current_time
            
            # Si la personne était absente, marquer comme arrivant
            current_state = self._person_states[owner]["state"]
            if current_state == self.AWAY or current_state == self.EXTENDED_AWAY:
                self._person_states[owner]["state"] = self.JUST_ARRIVED
                self._add_history_event("device_arrival", owner, {"device_id": device_id})
                self._home_occupancy[owner] = current_time
                
                # Publier un événement de changement d'état
                self.message_bus.publish("presence/state_changed", {
                    "person_id": owner,
                    "previous_state": current_state,
                    "new_state": self.JUST_ARRIVED,
                    "timestamp": current_time,
                    "device_id": device_id
                })
                
                # Mettre à jour le mode de la maison
                self._update_home_mode()
        
        # Sauvegarder l'état
        self._save_state()
    
    def _handle_device_disconnected(self, message: Dict[str, Any]):
        """Gère les déconnexions d'appareils."""
        device_id = message.get("device_id")
        
        if not device_id or device_id not in self.devices:
            return
            
        current_time = time.time()
        
        # Mettre à jour l'état de l'appareil
        if device_id in self._device_states:
            self._device_states[device_id]["state"] = "disconnected"
            
        # Ne pas modifier l'état de la personne immédiatement
        # Le processus de mise à jour périodique gérera les transitions d'état
        
        # Sauvegarder l'état
        self._save_state()
    
    def _handle_motion_detected(self, message: Dict[str, Any]):
        """Gère les détections de mouvement."""
        sensor_id = message.get("sensor_id")
        motion = message.get("state", False)
        
        if not sensor_id or not motion:
            return
            
        # Vérifier si le capteur est associé à une zone
        sensor_info = self.state_manager.get_state(f"sensor_{sensor_id}")
        if not sensor_info or "zone" not in sensor_info:
            return
            
        zone_id = sensor_info["zone"]
        
        # Vérifier si des personnes sont associées à cette zone
        zone_persons = []
        for person_id, person_config in self.persons.items():
            if "zones" in person_config and zone_id in person_config["zones"]:
                zone_persons.append(person_id)
        
        if not zone_persons:
            return
            
        current_time = time.time()
        
        # Mettre à jour les personnes associées à cette zone
        for person_id in zone_persons:
            if person_id in self._person_states:
                self._person_states[person_id]["last_seen"] = current_time
                
                # Si la personne n'était pas déjà à la maison, marquer comme présente
                current_state = self._person_states[person_id]["state"]
                if current_state != self.HOME and current_state != self.JUST_ARRIVED:
                    previous_state = current_state
                    self._person_states[person_id]["state"] = self.HOME
                    self._add_history_event("motion_detection", person_id, {"zone": zone_id, "sensor_id": sensor_id})
                    self._home_occupancy[person_id] = current_time
                    
                    # Publier un événement de changement d'état
                    self.message_bus.publish("presence/state_changed", {
                        "person_id": person_id,
                        "previous_state": previous_state,
                        "new_state": self.HOME,
                        "timestamp": current_time,
                        "zone": zone_id
                    })
        
        # Mettre à jour le mode de la maison
        self._update_home_mode()
        
        # Sauvegarder l'état
        self._save_state()
    
    def _handle_door_event(self, message: Dict[str, Any]):
        """Gère les événements de porte."""
        sensor_id = message.get("sensor_id")
        state = message.get("state")  # "open" ou "closed"
        
        if not sensor_id or not state:
            return
            
        # Nous ne faisons rien de spécial ici pour l'instant
        # Dans une implémentation plus avancée, nous pourrions utiliser les événements
        # de porte pour améliorer la détection de présence
        pass
    
    def _handle_security_armed(self, message: Dict[str, Any]):
        """Gère les événements d'armement du système de sécurité."""
        state = message.get("state")
        
        if state == "armed_away":
            # Si le système est armé en mode absence, marquer toutes les personnes comme absentes
            current_time = time.time()
            
            for person_id, person_state in self._person_states.items():
                if person_state["state"] != self.AWAY and person_state["state"] != self.EXTENDED_AWAY:
                    previous_state = person_state["state"]
                    person_state["state"] = self.AWAY
                    self._add_history_event("security_departure", person_id, {"source": "security_armed"})
                    
                    # Supprimer de l'occupation
                    if person_id in self._home_occupancy:
                        del self._home_occupancy[person_id]
                    
                    # Publier un événement de changement d'état
                    self.message_bus.publish("presence/state_changed", {
                        "person_id": person_id,
                        "previous_state": previous_state,
                        "new_state": self.AWAY,
                        "timestamp": current_time,
                        "source": "security_armed"
                    })
            
            # Forcer le mode absence
            if self._current_mode != self.MODE_AWAY:
                previous_mode = self._current_mode
                self._current_mode = self.MODE_AWAY
                self._last_mode_change = current_time
                
                # Publier un événement de changement de mode
                self.message_bus.publish("home/mode", {
                    "mode": self.MODE_AWAY,
                    "previous_mode": previous_mode,
                    "timestamp": current_time,
                    "source": "security_armed"
                })
            
            # Sauvegarder l'état
            self._save_state()
    
    def _handle_security_disarmed(self, message: Dict[str, Any]):
        """Gère les événements de désarmement du système de sécurité."""
        # Forcer une mise à jour des états de présence
        self._update_presence()
    
    def _handle_location_update(self, message: Dict[str, Any]):
        """Gère les mises à jour de localisation."""
        person_id = message.get("person_id")
        latitude = message.get("latitude")
        longitude = message.get("longitude")
        accuracy = message.get("accuracy", 0)
        
        if not person_id or person_id not in self._person_states or latitude is None or longitude is None:
            return
            
        current_time = time.time()
        
        # Mettre à jour la localisation
        self._person_states[person_id]["last_seen"] = current_time
        self._person_states[person_id]["location"] = {
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
            "timestamp": current_time
        }
        
        # Vérifier si la personne est près de la maison
        home_location = self.rules.get("home_location", {})
        if home_location:
            home_lat = home_location.get("latitude")
            home_lon = home_location.get("longitude")
            home_radius = home_location.get("radius", 100)  # mètres
            
            if home_lat is not None and home_lon is not None:
                distance = self._calculate_distance(latitude, longitude, home_lat, home_lon)
                
                # Si la personne est dans le rayon de la maison
                if distance <= home_radius and accuracy <= home_radius * 2:
                    current_state = self._person_states[person_id]["state"]
                    
                    # Si la personne n'était pas déjà à la maison, marquer comme arrivant
                    if current_state != self.HOME and current_state != self.JUST_ARRIVED:
                        previous_state = current_state
                        self._person_states[person_id]["state"] = self.JUST_ARRIVED
                        self._add_history_event("location_arrival", person_id, {"distance": distance})
                        self._home_occupancy[person_id] = current_time
                        
                        # Publier un événement de changement d'état
                        self.message_bus.publish("presence/state_changed", {
                            "person_id": person_id,
                            "previous_state": previous_state,
                            "new_state": self.JUST_ARRIVED,
                            "timestamp": current_time,
                            "source": "location"
                        })
                        
                        # Mettre à jour le mode de la maison
                        self._update_home_mode()
                
                # Si la personne est loin de la maison
                elif distance > home_radius * 2:
                    current_state = self._person_states[person_id]["state"]
                    
                    # Si la personne était à la maison, marquer comme partant
                    if current_state == self.HOME or current_state == self.JUST_ARRIVED:
                        previous_state = current_state
                        self._person_states[person_id]["state"] = self.JUST_LEFT
                        self._add_history_event("location_departure", person_id, {"distance": distance})
                        
                        # Supprimer de l'occupation
                        if person_id in self._home_occupancy:
                            del self._home_occupancy[person_id]
                        
                        # Publier un événement de changement d'état
                        self.message_bus.publish("presence/state_changed", {
                            "person_id": person_id,
                            "previous_state": previous_state,
                            "new_state": self.JUST_LEFT,
                            "timestamp": current_time,
                            "source": "location"
                        })
                        
                        # Mettre à jour le mode de la maison
                        self._update_home_mode()
        
        # Sauvegarder l'état
        self._save_state()
    
    def _handle_mode_set(self, message: Dict[str, Any]):
        """Gère les demandes de changement de mode."""
        mode = message.get("mode")
        
        if not mode or mode not in [self.MODE_HOME, self.MODE_AWAY, self.MODE_NIGHT, self.MODE_VACATION]:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"],