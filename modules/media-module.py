"""
modules/media_module.py
------------------
Module de gestion des médias pour Alfred.
Gère la lecture et le contrôle des différents systèmes multimédias de la maison.
"""

import logging
import json
import time
import threading
import subprocess
import requests
import os
from typing import Dict, Any, List, Optional, Union

from modules.module_interface import ModuleInterface

class MediaModule(ModuleInterface):
    """
    Module de gestion des médias pour la maison intelligente.
    Permet de contrôler différents appareils multimédias comme les téléviseurs,
    systèmes audio, lecteurs de streaming, etc.
    """
    
    def __init__(self, module_id: str, config: Dict[str, Any] = None):
        """
        Initialise le module de gestion des médias.
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration du module (optionnelle)
        """
        super().__init__(module_id, config)
        self.logger = logging.getLogger(f"media.{module_id}")
        
        # Configuration par défaut
        self.default_config = {
            "devices": {},
            "default_device": None,
            "volume_step": 5,
            "polling_interval": 30
        }
        
        # Fusionner avec la configuration fournie
        self.config = {**self.default_config, **(config or {})}
        
        # État interne
        self.devices = {}
        self.active_devices = {}
        self.status_thread = None
        self.running = False
        self.message_bus = None
        self.state_manager = None
    
    def initialize(self) -> bool:
        """
        Initialise le module de gestion des médias.
        
        Returns:
            True si l'initialisation est réussie, False sinon
        """
        self.logger.info("Initialisation du module de gestion des médias")
        
        # Récupérer les dépendances
        self.message_bus = self.get_dependency("message_bus")
        self.state_manager = self.get_dependency("state_manager")
        
        if not self.message_bus or not self.state_manager:
            self.logger.error("MessageBus ou StateManager non disponible")
            return False
        
        # Initialiser les périphériques configurés
        self._initialize_devices()
        
        # Démarrer le thread de surveillance de l'état des périphériques
        self.running = True
        self.status_thread = threading.Thread(target=self._status_thread_func, daemon=True)
        self.status_thread.start()
        
        # Enregistrer les gestionnaires de messages
        self._register_message_handlers()
        
        self.initialized = True
        return True
    
    def cleanup(self) -> bool:
        """
        Nettoie les ressources utilisées par le module.
        
        Returns:
            True si le nettoyage est réussi, False sinon
        """
        self.logger.info("Nettoyage du module de gestion des médias")
        self.running = False
        
        if self.status_thread and self.status_thread.is_alive():
            self.status_thread.join(timeout=3.0)
        
        # Arrêter tous les médias en cours de lecture
        for device_id in list(self.active_devices.keys()):
            self.stop_playback(device_id)
        
        return True
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Renvoie les capacités du module.
        
        Returns:
            Dictionnaire des capacités
        """
        capabilities = {
            "playback_control": True,
            "volume_control": True,
            "device_discovery": True,
            "devices": {}
        }
        
        # Ajouter les capacités spécifiques à chaque appareil
        for device_id, device in self.devices.items():
            capabilities["devices"][device_id] = {
                "type": device.get("type", "unknown"),
                "name": device.get("name", device_id),
                "capabilities": device.get("capabilities", [])
            }
        
        return capabilities
        
    def _get_kodi_status(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """Récupère l'état d'un système Kodi."""
        # Dans une implémentation réelle, on utiliserait l'API JSON-RPC de Kodi
        config = device["config"]
        ip = config.get("ip", "localhost")
        port = config.get("port", 8080)
        
        try:
            # Simulation d'une requête à l'API Kodi
            # response = requests.post(f"http://{ip}:{port}/jsonrpc", json={
            #    "jsonrpc": "2.0",
            #    "method": "Player.GetActivePlayers",
            #    "id": 1
            # })
            # players = response.json().get("result", [])
            
            # Pour la simulation, on suppose qu'un lecteur est actif
            players = [{"playerid": 1, "type": "video"}]
            
            if players:
                # Un média est en cours de lecture
                return {
                    "online": True,
                    "playing": True,
                    "volume": 60,
                    "muted": False,
                    "current_media": {
                        "title": "Film d'exemple",
                        "type": "movie",
                        "thumbnail": "http://example.com/poster.jpg"
                    },
                    "position": 1200,  # 20 minutes
                    "duration": 5400   # 1h30
                }
            else:
                # Aucun média en cours de lecture
                return {
                    "online": True,
                    "playing": False,
                    "volume": 60,
                    "muted": False,
                    "current_media": None
                }
        except Exception as e:
            self.logger.error(f"Erreur lors de la connexion à Kodi ({ip}:{port}): {str(e)}")
            return {
                "online": False,
                "playing": False,
                "error": str(e)
            }
    
    def _initialize_devices(self) -> None:
        """Initialise les périphériques configurés."""
        devices_config = self.config.get("devices", {})
        
        for device_id, device_config in devices_config.items():
            device_type = device_config.get("type", "unknown")
            device_info = self._create_device(device_id, device_type, device_config)
            
            if device_info:
                self.devices[device_id] = device_info
                self.logger.info(f"Périphérique initialisé: {device_id} ({device_type})")
            else:
                self.logger.warning(f"Échec de l'initialisation du périphérique: {device_id}")
    
    def _create_device(self, device_id: str, device_type: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Crée un objet de périphérique en fonction de son type.
        
        Args:
            device_id: Identifiant du périphérique
            device_type: Type de périphérique
            config: Configuration du périphérique
            
        Returns:
            Objet de périphérique ou None en cas d'échec
        """
        device_info = {
            "id": device_id,
            "type": device_type,
            "name": config.get("name", device_id),
            "config": config,
            "status": {
                "online": False,
                "playing": False,
                "volume": 0,
                "muted": False,
                "current_media": None
            }
        }
        
        # Ajouter des capacités spécifiques au type de périphérique
        if device_type == "tv":
            device_info["capabilities"] = ["on_off", "volume", "input_selection", "channel"]
            # Connexion HDMI-CEC, configuration de la télécommande, etc.
        
        elif device_type == "speaker":
            device_info["capabilities"] = ["volume", "playback"]
            # Configuration du système audio, protocole de communication, etc.
        
        elif device_type == "media_player":
            device_info["capabilities"] = ["volume", "playback", "playlist"]
            # Configuration du lecteur multimédia, applications supportées, etc.
        
        elif device_type == "cast":
            device_info["capabilities"] = ["volume", "playback", "apps"]
            # Configuration pour Google Cast, Chromecast, etc.
        
        elif device_type == "kodi":
            device_info["capabilities"] = ["volume", "playback", "library", "addons"]
            # Configuration pour Kodi, adresse IP, port, etc.
        
        else:
            self.logger.warning(f"Type de périphérique inconnu: {device_type}")
            device_info["capabilities"] = []
        
        return device_info
    
    def _register_message_handlers(self) -> None:
        """Enregistre les gestionnaires de messages pour le bus de messages."""
        handlers = {
            "media/play": self._handle_play,
            "media/pause": self._handle_pause,
            "media/stop": self._handle_stop,
            "media/next": self._handle_next,
            "media/previous": self._handle_previous,
            "media/volume": self._handle_volume,
            "media/mute": self._handle_mute,
            "media/status": self._handle_status_request
        }
        
        for topic, handler in handlers.items():
            self.message_bus.subscribe(topic, handler)
            self.logger.debug(f"Gestionnaire enregistré pour le topic: {topic}")
    
    # Gestionnaires de messages
    
    def _handle_play(self, message: Dict[str, Any]) -> None:
        """Gère les demandes de lecture."""
        device_id = message.get("device_id", self.config["default_device"])
        media_uri = message.get("uri")
        media_type = message.get("type")
        
        if not device_id:
            self.logger.warning("Aucun périphérique spécifié et aucun périphérique par défaut configuré")
            return
        
        if media_uri:
            # Lecture d'un média spécifique
            self.play_media(device_id, media_uri, media_type)
        else:
            # Reprise de la lecture
            self.resume_playback(device_id)
        
        # Répondre si un topic de réponse est spécifié
        reply_topic = message.get("reply_topic")
        if reply_topic:
            self.message_bus.publish(reply_topic, {
                "success": True,
                "device_id": device_id,
                "action": "play"
            })
    
    def _handle_pause(self, message: Dict[str, Any]) -> None:
        """Gère les demandes de pause."""
        device_id = message.get("device_id", self.config["default_device"])
        
        if not device_id:
            self.logger.warning("Aucun périphérique spécifié et aucun périphérique par défaut configuré")
            return
        
        self.pause_playback(device_id)
        
        # Répondre si un topic de réponse est spécifié
        reply_topic = message.get("reply_topic")
        if reply_topic:
            self.message_bus.publish(reply_topic, {
                "success": True,
                "device_id": device_id,
                "action": "pause"
            })
    
    def _handle_stop(self, message: Dict[str, Any]) -> None:
        """Gère les demandes d'arrêt."""
        device_id = message.get("device_id", self.config["default_device"])
        
        if not device_id:
            self.logger.warning("Aucun périphérique spécifié et aucun périphérique par défaut configuré")
            return
        
        self.stop_playback(device_id)
        
        # Répondre si un topic de réponse est spécifié
        reply_topic = message.get("reply_topic")
        if reply_topic:
            self.message_bus.publish(reply_topic, {
                "success": True,
                "device_id": device_id,
                "action": "stop"
            })
    
    def _handle_next(self, message: Dict[str, Any]) -> None:
        """Gère les demandes de passage au média suivant."""
        device_id = message.get("device_id", self.config["default_device"])
        
        if not device_id:
            self.logger.warning("Aucun périphérique spécifié et aucun périphérique par défaut configuré")
            return
        
        self.next_track(device_id)
        
        # Répondre si un topic de réponse est spécifié
        reply_topic = message.get("reply_topic")
        if reply_topic:
            self.message_bus.publish(reply_topic, {
                "success": True,
                "device_id": device_id,
                "action": "next"
            })
    
    def _handle_previous(self, message: Dict[str, Any]) -> None:
        """Gère les demandes de passage au média précédent."""
        device_id = message.get("device_id", self.config["default_device"])
        
        if not device_id:
            self.logger.warning("Aucun périphérique spécifié et aucun périphérique par défaut configuré")
            return
        
        self.previous_track(device_id)
        
        # Répondre si un topic de réponse est spécifié
        reply_topic = message.get("reply_topic")
        if reply_topic:
            self.message_bus.publish(reply_topic, {
                "success": True,
                "device_id": device_id,
                "action": "previous"
            })
    
    def _handle_volume(self, message: Dict[str, Any]) -> None:
        """Gère les demandes de changement de volume."""
        device_id = message.get("device_id", self.config["default_device"])
        volume = message.get("volume")
        
        if not device_id:
            self.logger.warning("Aucun périphérique spécifié et aucun périphérique par défaut configuré")
            return
        
        if volume is not None:
            self.set_volume(device_id, volume)
        
        # Répondre si un topic de réponse est spécifié
        reply_topic = message.get("reply_topic")
        if reply_topic:
            device = self.devices.get(device_id, {})
            current_volume = device.get("status", {}).get("volume", 0)
            
            self.message_bus.publish(reply_topic, {
                "success": True,
                "device_id": device_id,
                "action": "volume",
                "volume": current_volume
            })
    
    def _handle_mute(self, message: Dict[str, Any]) -> None:
        """Gère les demandes de mise en sourdine."""
        device_id = message.get("device_id", self.config["default_device"])
        mute = message.get("mute")
        
        if not device_id:
            self.logger.warning("Aucun périphérique spécifié et aucun périphérique par défaut configuré")
            return
        
        if mute is not None:
            self.set_mute(device_id, mute)
        else:
            # Basculer l'état de sourdine
            device = self.devices.get(device_id, {})
            current_mute = device.get("status", {}).get("muted", False)
            self.set_mute(device_id, not current_mute)
        
        # Répondre si un topic de réponse est spécifié
        reply_topic = message.get("reply_topic")
        if reply_topic:
            device = self.devices.get(device_id, {})
            current_mute = device.get("status", {}).get("muted", False)
            
            self.message_bus.publish(reply_topic, {
                "success": True,
                "device_id": device_id,
                "action": "mute",
                "muted": current_mute
            })
    
    def _handle_status_request(self, message: Dict[str, Any]) -> None:
        """Gère les demandes de statut."""
        device_id = message.get("device_id")
        
        reply_topic = message.get("reply_topic")
        if not reply_topic:
            return
        
        if device_id:
            # Statut d'un périphérique spécifique
            device = self.devices.get(device_id)
            if device:
                self.message_bus.publish(reply_topic, {
                    "success": True,
                    "device_id": device_id,
                    "status": device.get("status", {})
                })
            else:
                self.message_bus.publish(reply_topic, {
                    "success": False,
                    "error": f"Périphérique inconnu: {device_id}"
                })
        else:
            # Statut de tous les périphériques
            statuses = {}
            for dev_id, device in self.devices.items():
                statuses[dev_id] = device.get("status", {})
            
            self.message_bus.publish(reply_topic, {
                "success": True,
                "devices": statuses
            })
    
    def _status_thread_func(self) -> None:
        """Thread de surveillance de l'état des périphériques."""
        while self.running:
            for device_id, device in self.devices.items():
                try:
                    status = self._get_device_status(device_id)
                    
                    if status:
                        # Mettre à jour l'état du périphérique
                        old_status = device["status"].copy()
                        device["status"].update(status)
                        
                        # Si l'état a changé, publier un événement
                        if old_status != device["status"]:
                            self.message_bus.publish("media/status_changed", {
                                "device_id": device_id,
                                "old_status": old_status,
                                "new_status": device["status"]
                            })
                            
                            # Mettre à jour le gestionnaire d'état
                            self.state_manager.set(f"media.devices.{device_id}.status", device["status"])
                except Exception as e:
                    self.logger.error(f"Erreur lors de la mise à jour du statut du périphérique {device_id}: {str(e)}")
            
            # Attendre avant la prochaine vérification
            time.sleep(self.config["polling_interval"])
    
    def _get_device_status(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère l'état actuel d'un périphérique.
        
        Args:
            device_id: Identifiant du périphérique
            
        Returns:
            État du périphérique ou None en cas d'échec
        """
        if device_id not in self.devices:
            return None
        
        device = self.devices[device_id]
        device_type = device["type"]
        
        try:
            # Implémentation spécifique pour chaque type de périphérique
            if device_type == "tv":
                return self._get_tv_status(device)
            elif device_type == "speaker":
                return self._get_speaker_status(device)
            elif device_type == "media_player":
                return self._get_media_player_status(device)
            elif device_type == "cast":
                return self._get_cast_status(device)
            elif device_type == "kodi":
                return self._get_kodi_status(device)
            else:
                return None
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération de l'état du périphérique {device_id}: {str(e)}")
            return None
    
    # Méthodes de contrôle de la lecture
    
    def play_media(self, device_id: str, media_uri: str, media_type: Optional[str] = None) -> bool:
        """
        Démarre la lecture d'un média sur un périphérique.
        
        Args:
            device_id: Identifiant du périphérique
            media_uri: URI du média à lire
            media_type: Type de média (video, audio, image)
            
        Returns:
            True si la lecture a démarré, False sinon
        """
        if device_id not in self.devices:
            self.logger.warning(f"Périphérique inconnu: {device_id}")
            return False
        
        device = self.devices[device_id]
        device_type = device["type"]
        
        try:
            # Implémentation spécifique pour chaque type de périphérique
            if device_type == "tv":
                # Simuler la lecture sur un téléviseur
                pass
            elif device_type == "speaker":
                # Simuler la lecture sur un système audio
                pass
            elif device_type == "media_player":
                # Simuler la lecture sur un lecteur multimédia
                pass
            elif device_type == "cast":
                # Simuler la lecture sur un appareil Cast
                pass
            elif device_type == "kodi":
                # Simuler la lecture sur Kodi
                # Dans une implémentation réelle, on utiliserait l'API JSON-RPC de Kodi
                pass
            else:
                return False
            
            # Mettre à jour l'état du périphérique
            device["status"]["playing"] = True
            device["status"]["current_media"] = {
                "uri": media_uri,
                "type": media_type or "unknown",
                "title": os.path.basename(media_uri) if media_uri else "Unknown"
            }
            
            # Ajouter aux périphériques actifs
            self.active_devices[device_id] = {
                "media_uri": media_uri,
                "start_time": time.time()
            }
            
            # Publier un événement
            self.message_bus.publish("media/playback_started", {
                "device_id": device_id,
                "media_uri": media_uri,
                "media_type": media_type
            })
            
            self.logger.info(f"Lecture démarrée sur {device_id}: {media_uri}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage de la lecture sur {device_id}: {str(e)}")
            return False
    
    def resume_playback(self, device_id: str) -> bool:
        """
        Reprend la lecture sur un périphérique.
        
        Args:
            device_id: Identifiant du périphérique
            
        Returns:
            True si la lecture a repris, False sinon
        """
        if device_id not in self.devices:
            self.logger.warning(f"Périphérique inconnu: {device_id}")
            return False
        
        device = self.devices[device_id]
        
        try:
            # Mettre à jour l'état du périphérique
            device["status"]["playing"] = True
            
            # Publier un événement
            self.message_bus.publish("media/playback_resumed", {
                "device_id": device_id
            })
            
            self.logger.info(f"Lecture reprise sur {device_id}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de la reprise de la lecture sur {device_id}: {str(e)}")
            return False
    
    def pause_playback(self, device_id: str) -> bool:
        """
        Met en pause la lecture sur un périphérique.
        
        Args:
            device_id: Identifiant du périphérique
            
        Returns:
            True si la lecture a été mise en pause, False sinon
        """
        if device_id not in self.devices:
            self.logger.warning(f"Périphérique inconnu: {device_id}")
            return False
        
        device = self.devices[device_id]
        
        try:
            # Mettre à jour l'état du périphérique
            device["status"]["playing"] = False
            
            # Publier un événement
            self.message_bus.publish("media/playback_paused", {
                "device_id": device_id
            })
            
            self.logger.info(f"Lecture mise en pause sur {device_id}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de la mise en pause sur {device_id}: {str(e)}")
            return False
    
    def stop_playback(self, device_id: str) -> bool:
        """
        Arrête la lecture sur un périphérique.
        
        Args:
            device_id: Identifiant du périphérique
            
        Returns:
            True si la lecture a été arrêtée, False sinon
        """
        if device_id not in self.devices:
            self.logger.warning(f"Périphérique inconnu: {device_id}")
            return False
        
        device = self.devices[device_id]
        
        try:
            # Mettre à jour l'état du périphérique
            device["status"]["playing"] = False
            device["status"]["current_media"] = None
            
            # Retirer des périphériques actifs
            if device_id in self.active_devices:
                del self.active_devices[device_id]
            
            # Publier un événement
            self.message_bus.publish("media/playback_stopped", {
                "device_id": device_id
            })
            
            self.logger.info(f"Lecture arrêtée sur {device_id}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de l'arrêt de la lecture sur {device_id}: {str(e)}")
            return False
    
    def next_track(self, device_id: str) -> bool:
        """
        Passe au média suivant.
        
        Args:
            device_id: Identifiant du périphérique
            
        Returns:
            True si le passage au média suivant a réussi, False sinon
        """
        if device_id not in self.devices:
            self.logger.warning(f"Périphérique inconnu: {device_id}")
            return False
        
        try:
            # Publier un événement
            self.message_bus.publish("media/next_track", {
                "device_id": device_id
            })
            
            self.logger.info(f"Passage au média suivant sur {device_id}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors du passage au média suivant sur {device_id}: {str(e)}")
            return False
    
    def previous_track(self, device_id: str) -> bool:
        """
        Passe au média précédent.
        
        Args:
            device_id: Identifiant du périphérique
            
        Returns:
            True si le passage au média précédent a réussi, False sinon
        """
        if device_id not in self.devices:
            self.logger.warning(f"Périphérique inconnu: {device_id}")
            return False
        
        try:
            # Publier un événement
            self.message_bus.publish("media/previous_track", {
                "device_id": device_id
            })
            
            self.logger.info(f"Passage au média précédent sur {device_id}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors du passage au média précédent sur {device_id}: {str(e)}")
            return False
    
    def set_volume(self, device_id: str, volume: int) -> bool:
        """
        Définit le volume d'un périphérique.
        
        Args:
            device_id: Identifiant du périphérique
            volume: Niveau de volume (0-100)
            
        Returns:
            True si le volume a été défini, False sinon
        """
        if device_id not in self.devices:
            self.logger.warning(f"Périphérique inconnu: {device_id}")
            return False
        
        device = self.devices[device_id]
        
        try:
            # Limiter le volume entre 0 et 100
            volume = max(0, min(100, volume))
            
            # Mettre à jour l'état du périphérique
            device["status"]["volume"] = volume
            
            # Publier un événement
            self.message_bus.publish("media/volume_changed", {
                "device_id": device_id,
                "volume": volume
            })
            
            self.logger.info(f"Volume défini à {volume} sur {device_id}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de la définition du volume sur {device_id}: {str(e)}")
            return False
    
    def set_mute(self, device_id: str, mute: bool) -> bool:
        """
        Active ou désactive la sourdine d'un périphérique.
        
        Args:
            device_id: Identifiant du périphérique
            mute: True pour activer la sourdine, False pour la désactiver
            
        Returns:
            True si la sourdine a été définie, False sinon
        """
        if device_id not in self.devices:
            self.logger.warning(f"Périphérique inconnu: {device_id}")
            return False
        
        device = self.devices[device_id]
        
        try:
            # Mettre à jour l'état du périphérique
            device["status"]["muted"] = mute
            
            # Publier un événement
            self.message_bus.publish("media/mute_changed", {
                "device_id": device_id,
                "muted": mute
            })
            
            self.logger.info(f"Sourdine {'activée' if mute else 'désactivée'} sur {device_id}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de la définition de la sourdine sur {device_id}: {str(e)}")
            return False
    
    # Méthodes de gestion des périphériques spécifiques
    
    def _get_tv_status(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """Récupère l'état d'un téléviseur."""
        # Dans une implémentation réelle, on pourrait utiliser HDMI-CEC, API Smart TV, etc.
        return {
            "online": True,
            "power": True,
            "volume": 50,
            "muted": False,
            "input": "hdmi1",
            "channel": "N/A"
        }
    
    def _get_speaker_status(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """Récupère l'état d'un système audio."""
        return {
            "online": True,
            "playing": False,
            "volume": 40,
            "muted": False
        }
    
    def _get_media_player_status(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """Récupère l'état d'un lecteur multimédia."""
        return {
            "online": True,
            "playing": device["status"].get("playing", False),
            "volume": device["status"].get("volume", 50),
            "muted": False,
            "current_media": device["status"].get("current_media"),
            "position": device["status"].get("position", 0),
            "duration": device["status"].get("duration", 0)
        }
    
    def _get_cast_status(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """Récupère l'état d'un appareil Cast."""
        # Dans une implémentation réelle, on utiliserait pychromecast
        return {
            "online": True,
            "playing": False,
            "volume": 30,
            "muted": False,
            "current_app": "Netflix",
            "current_media": None
        }