import logging
import time
from typing import Dict, Any, List, Optional
import json

from base_agent import BaseAgent

class SmartHomeAgent(BaseAgent):
    """
    Agent domotique principal qui intègre toutes les fonctionnalités
    de maison intelligente en utilisant l'architecture modulaire.
    
    Cet agent fusionne les fonctionnalités de l'ancien SmartHomeAgent et
    AdvancedSmartHomeAgent en utilisant le système modulaire.
    """
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        """
        Initialise l'agent domotique.
        
        Args:
            agent_id: Identifiant unique de l'agent
            config: Configuration de l'agent
        """
        super().__init__(agent_id, config)
        
        # Configuration spécifique
        self.enable_voice_control = config.get("enable_voice_control", False)
        self.enable_ai_learning = config.get("enable_ai_learning", False)
        self.ai_preferences = config.get("ai_preferences", {})
        
        self.logger.info("Agent domotique initialisé")
        
        # Enregistrer les gestionnaires de messages spécifiques
        self._register_specific_handlers()
    
    def _register_specific_handlers(self):
        """Enregistre les gestionnaires de messages spécifiques à l'agent domotique."""
        self.message_bus.register_handler("home/command", self._handle_home_command)
        self.message_bus.register_handler("voice/command", self._handle_voice_command)
        self.message_bus.register_handler("scene/activate", self._handle_scene_activation)
        self.message_bus.register_handler("mode/set", self._handle_mode_set)
    
    def start(self):
        """Démarre l'agent domotique et initialise les modules nécessaires."""
        super().start()
        
        self.logger.info("Démarrage de l'agent domotique")
        
        # Vérifier et démarrer les modules requis
        self._ensure_required_modules()
        
        # Charger les scènes et les modes
        self._load_scenes_and_modes()
        
        # Initialiser l'apprentissage IA si activé
        if self.enable_ai_learning:
            self._initialize_ai_learning()
        
        # Publier un événement d'initialisation complète
        self.message_bus.publish("home/initialized", {
            "agent_id": self.agent_id,
            "timestamp": time.time()
        })
    
    def _ensure_required_modules(self):
        """S'assure que tous les modules requis sont démarrés."""
        required_modules = [
            "weather",
            "lighting",
            "security",
            "presence",
            "notification",
            "scheduler"
        ]
        
        # Vérifier que tous les modules requis sont présents et actifs
        for module_type in required_modules:
            modules = self.module_manager.get_modules_by_type(module_type)
            
            if not modules:
                self.logger.warning(f"Module requis non trouvé: {module_type}")
                
                # Essayer de démarrer le module avec la configuration par défaut
                try:
                    default_config = self.config.get("default_modules", {}).get(module_type, {})
                    self.module_manager.create_module(module_type, f"{module_type}_default", default_config)
                except Exception as e:
                    self.logger.error(f"Erreur lors de la création du module {module_type}: {e}")
    
    def _load_scenes_and_modes(self):
        """Charge les scènes d'éclairage et les modes de la maison."""
        # Charger les scènes d'éclairage
        lighting_modules = self.module_manager.get_modules_by_type("lighting")
        if lighting_modules:
            # Utiliser le premier module d'éclairage disponible
            lighting_module = lighting_modules[0]
            
            # Ajouter les scènes depuis la configuration
            scenes = self.config.get("scenes", {})
            for scene_id, scene_config in scenes.items():
                if scene_id and scene_config:
                    self.message_bus.publish("lighting/scene/add", {
                        "scene_id": scene_id,
                        "config": scene_config
                    })
        
        # Initialiser le mode de la maison
        default_mode = self.config.get("default_mode", "home")
        self.message_bus.publish("home/mode/set", {
            "mode": default_mode
        })
    
    def _initialize_ai_learning(self):
        """Initialise les capacités d'apprentissage IA."""
        self.logger.info("Initialisation de l'apprentissage IA")
        
        # Charger les préférences d'apprentissage
        learning_preferences = self.ai_preferences.get("learning", {})
        
        # Configurer les sources de données pour l'apprentissage
        data_sources = []
        
        if learning_preferences.get("learn_from_presence", True):
            data_sources.append("presence")
        
        if learning_preferences.get("learn_from_lighting", True):
            data_sources.append("lighting")
        
        if learning_preferences.get("learn_from_climate", True):
            data_sources.append("climate")
        
        # Dans une implémentation réelle, nous initialiserions ici un système d'apprentissage
        # qui collecterait des données et ajusterait les automatisations
        
        self.logger.debug(f"Sources de données pour l'apprentissage: {data_sources}")
    
    def _handle_home_command(self, message: Dict[str, Any]):
        """Gère les commandes générales pour la maison."""
        command = message.get("command")
        parameters = message.get("parameters", {})
        
        if not command:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_command"
                })
            return
        
        # Traiter la commande
        result = self._process_command(command, parameters)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], result)
    
    def _handle_voice_command(self, message: Dict[str, Any]):
        """Gère les commandes vocales."""
        if not self.enable_voice_control:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "voice_control_disabled"
                })
            return
        
        text = message.get("text")
        
        if not text:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_text"
                })
            return
        
        # Traiter la commande vocale
        # Dans une implémentation réelle, nous utiliserions un système NLU
        # pour extraire l'intention et les entités de la commande
        # Ici, nous simulons simplement une correspondance basique
        
        command = None
        parameters = {}
        
        # Exemples de correspondances simples
        if "allume" in text.lower() and "lumière" in text.lower():
            command = "light_on"
            if "salon" in text.lower():
                parameters["room"] = "living_room"
            elif "cuisine" in text.lower():
                parameters["room"] = "kitchen"
            elif "chambre" in text.lower():
                parameters["room"] = "bedroom"
        
        elif "éteins" in text.lower() and "lumière" in text.lower():
            command = "light_off"
            if "salon" in text.lower():
                parameters["room"] = "living_room"
            elif "cuisine" in text.lower():
                parameters["room"] = "kitchen"
            elif "chambre" in text.lower():
                parameters["room"] = "bedroom"
        
        elif "température" in text.lower():
            command = "get_temperature"
            if "salon" in text.lower():
                parameters["room"] = "living_room"
            elif "cuisine" in text.lower():
                parameters["room"] = "kitchen"
            elif "chambre" in text.lower():
                parameters["room"] = "bedroom"
        
        elif "active" in text.lower() and "alarme" in text.lower():
            command = "security_arm"
            if "présence" in text.lower():
                parameters["mode"] = "home"
            else:
                parameters["mode"] = "away"
        
        elif "désactive" in text.lower() and "alarme" in text.lower():
            command = "security_disarm"
        
        # Traiter la commande extraite
        result = {}
        if command:
            result = self._process_command(command, parameters)
            result["command"] = command
            result["parameters"] = parameters
        else:
            result = {
                "success": False,
                "error": "unknown_command",
                "text": text
            }
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], result)
    
    def _handle_scene_activation(self, message: Dict[str, Any]):
        """Gère les demandes d'activation de scène."""
        scene_id = message.get("scene_id")
        
        if not scene_id:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_scene_id"
                })
            return
        
        # Activer la scène via le module d'éclairage
        self.message_bus.publish("lighting/scene", {
            "scene_id": scene_id
        })
        
        # Répondre avec succès
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "scene_id": scene_id
            })
    
    def _handle_mode_set(self, message: Dict[str, Any]):
        """Gère les demandes de changement de mode."""
        mode = message.get("mode")
        
        if not mode:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_mode"
                })
            return
        
        # Changer le mode via le module approprié
        self.message_bus.publish("home/mode/set", {
            "mode": mode
        })
        
        # Actions supplémentaires en fonction du mode
        if mode == "away":
            # Armer le système de sécurité
            self.message_bus.publish("security/arm", {
                "mode": "away"
            })
            
            # Éteindre les lumières non essentielles
            self.message_bus.publish("lighting/scene", {
                "scene_id": "away"
            })
        
        elif mode == "home":
            # Désarmer le système de sécurité
            self.message_bus.publish("security/disarm", {
                "code": self.config.get("security", {}).get("default_code")
            })
            
            # Activer la scène de bienvenue
            self.message_bus.publish("lighting/scene", {
                "scene_id": "welcome"
            })
        
        elif mode == "night":
            # Armer le système de sécurité en mode présence
            self.message_bus.publish("security/arm", {
                "mode": "home"
            })
            
            # Activer la scène nocturne
            self.message_bus.publish("lighting/scene", {
                "scene_id": "night"
            })
        
        elif mode == "vacation":
            # Armer le système de sécurité
            self.message_bus.publish("security/arm", {
                "mode": "away"
            })
            
            # Activer le mode vacances pour l'éclairage simulé
            self.message_bus.publish("lighting/vacation_mode", {
                "enabled": True
            })
        
        # Répondre avec succès
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "mode": mode
            })
    
    def _process_command(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite une commande et ses paramètres.
        
        Args:
            command: Commande à exécuter
            parameters: Paramètres de la commande
            
        Returns:
            Dict: Résultat de l'exécution
        """
        # Commandes liées à l'éclairage
        if command == "light_on":
            room = parameters.get("room")
            if room:
                # Récupérer les lumières de cette pièce
                light_ids = self._get_room_lights(room)
                
                # Allumer chaque lumière
                for light_id in light_ids:
                    self.message_bus.publish("lighting/set", {
                        "light_id": light_id,
                        "state": True
                    })
                
                return {
                    "success": True,
                    "lights": light_ids
                }
            else:
                return {
                    "success": False,
                    "error": "missing_room"
                }
        
        elif command == "light_off":
            room = parameters.get("room")
            if room:
                # Récupérer les lumières de cette pièce
                light_ids = self._get_room_lights(room)
                
                # Éteindre chaque lumière
                for light_id in light_ids:
                    self.message_bus.publish("lighting/set", {
                        "light_id": light_id,
                        "state": False
                    })
                
                return {
                    "success": True,
                    "lights": light_ids
                }
            else:
                return {
                    "success": False,
                    "error": "missing_room"
                }
        
        # Commandes liées à la sécurité
        elif command == "security_arm":
            mode = parameters.get("mode", "away")
            code = parameters.get("code", self.config.get("security", {}).get("default_code"))
            
            self.message_bus.publish("security/arm", {
                "mode": mode,
                "code": code
            })
            
            return {
                "success": True,
                "mode": mode
            }
        
        elif command == "security_disarm":
            code = parameters.get("code", self.config.get("security", {}).get("default_code"))
            
            self.message_bus.publish("security/disarm", {
                "code": code
            })
            
            return {
                "success": True
            }
        
        # Commandes liées à la météo
        elif command == "get_weather":
            # Demander le statut météo
            weather_status = {}
            weather_modules = self.module_manager.get_modules_by_type("weather")
            if weather_modules:
                weather_module = weather_modules[0]
                weather_status = weather_module.get_status()
            
            return {
                "success": True,
                "weather": weather_status
            }
        
        # Commandes liées à la température
        elif command == "get_temperature":
            room = parameters.get("room")
            if room:
                # Récupérer les capteurs de température de cette pièce
                sensor_ids = self._get_room_temperature_sensors(room)
                
                # Récupérer les données de température
                temperatures = {}
                for sensor_id in sensor_ids:
                    sensor_state = self.state_manager.get_state(f"sensor_{sensor_id}")
                    if sensor_state and "temperature" in sensor_state:
                        temperatures[sensor_id] = sensor_state["temperature"]
                
                return {
                    "success": True,
                    "room": room,
                    "temperatures": temperatures
                }
            else:
                return {
                    "success": False,
                    "error": "missing_room"
                }
        
        # Commande inconnue
        else:
            return {
                "success": False,
                "error": "unknown_command",
                "command": command
            }
    
    def _get_room_lights(self, room: str) -> List[str]:
        """
        Récupère les identifiants des lumières d'une pièce.
        
        Args:
            room: Identifiant de la pièce
            
        Returns:
            List[str]: Liste des identifiants de lumières
        """
        # Cette méthode devrait récupérer les lumières depuis la configuration ou l'état
        # Pour simplifier, nous utilisons des identifiants génériques
        if room == "living_room":
            return ["light1", "light2"]
        elif room == "kitchen":
            return ["light3"]
        elif room == "bedroom":
            return ["light4", "light5"]
        else:
            return []
    
    def _get_room_temperature_sensors(self, room: str) -> List[str]:
        """
        Récupère les identifiants des capteurs de température d'une pièce.
        
        Args:
            room: Identifiant de la pièce
            
        Returns:
            List[str]: Liste des identifiants de capteurs
        """
        # Cette méthode devrait récupérer les capteurs depuis la configuration ou l'état
        # Pour simplifier, nous utilisons des identifiants génériques
        if room == "living_room":
            return ["temp1"]
        elif room == "kitchen":
            return ["temp2"]
        elif room == "bedroom":
            return ["temp3"]
        else:
            return []
