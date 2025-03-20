"""
modules/alexa_integration_module.py
----------------------------------
Module d'intégration pour les appareils Alexa d'Amazon.
Offre des capacités de capture audio, diffusion et récupération d'informations.
"""

import logging
import json
from typing import Dict, Any, List, Optional

# Importer les bibliothèques d'interaction Alexa (à remplacer par la vraie bibliothèque)
import alexaapi  # Bibliothèque hypothétique pour interagir avec Alexa

from modules.module_interface import ModuleInterface

class AlexaIntegrationModule(ModuleInterface):
    """
    Module d'intégration Alexa offrant :
    - Capture audio multi-pièces
    - Diffusion de sons/musique
    - Récupération d'informations système
    """
    
    def __init__(self, module_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialise le module d'intégration Alexa.
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration spécifique du module
        """
        super().__init__(module_id, config)
        
        # Configuration par défaut
        self.default_config = {
            "devices": {},  # Liste des appareils Alexa
            "default_device": None,
            "audio_capture": {
                "enabled": True,
                "rooms": []  # Pièces avec Alexa
            },
            "music_streaming": {
                "enabled": True,
                "services": ["amazon_music", "spotify"]
            },
            "information_retrieval": {
                "weather": True,
                "temperature": True,
                "news": True
            }
        }
        
        # Fusionner la configuration
        self.config = {**self.default_config, **(config or {})}
        
        # État interne
        self.alexa_devices = {}
        self.active_streams = {}
    
    @classmethod
    def get_metadata(cls):
        """
        Renvoie les métadonnées du module.
        
        Returns:
            Métadonnées du module
        """
        return {
            "name": "alexa_integration",
            "version": "1.0.0",
            "description": "Module d'intégration pour les appareils Alexa",
            "dependencies": ["notification", "audio_processing"],
            "provides": [
                "multi_room_audio",
                "audio_capture",
                "information_retrieval",
                "music_streaming"
            ]
        }
    
    def initialize(self) -> bool:
        """
        Initialise le module d'intégration Alexa.
        
        Returns:
            True si l'initialisation est réussie, False sinon
        """
        try:
            # Découvrir et initialiser les appareils Alexa
            self._discover_alexa_devices()
            
            # Enregistrer les gestionnaires de messages
            self._register_message_handlers()
            
            # Configurer les capacités de capture audio
            self._setup_audio_capture()
            
            self.initialized = True
            self.logger.info("Module d'intégration Alexa initialisé avec succès")
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation du module Alexa : {e}")
            return False
    
    def _discover_alexa_devices(self):
        """
        Découvre et initialise les appareils Alexa du réseau local.
        """
        try:
            # Utiliser l'API Alexa pour découvrir les appareils
            discovered_devices = alexaapi.discover_devices()
            
            for device in discovered_devices:
                self.alexa_devices[device['id']] = {
                    'name': device['name'],
                    'room': device.get('room'),
                    'capabilities': device.get('capabilities', [])
                }
            
            # Définir un appareil par défaut si non spécifié
            if not self.config.get('default_device') and self.alexa_devices:
                self.config['default_device'] = list(self.alexa_devices.keys())[0]
            
            self.logger.info(f"{len(self.alexa_devices)} appareils Alexa découverts")
        except Exception as e:
            self.logger.error(f"Erreur lors de la découverte des appareils Alexa : {e}")
    
    def _register_message_handlers(self):
        """
        Enregistre les gestionnaires de messages pour le module.
        """
        handlers = {
            "audio/capture": self._handle_audio_capture,
            "audio/play": self._handle_audio_play,
            "alexa/info/request": self._handle_info_request,
            "alexa/broadcast": self._handle_broadcast,
            "alexa/status": self._handle_status_request
        }
        
        # Enregistrer chaque gestionnaire via le bus de messages
        for topic, handler in handlers.items():
            self.message_bus.subscribe(topic, handler)
    
    def _setup_audio_capture(self):
        """
        Configure les capacités de capture audio multi-pièces.
        """
        # Configuration de la capture audio dans les pièces spécifiées
        for room in self.config['audio_capture'].get('rooms', []):
            # Trouver un appareil Alexa dans cette pièce
            room_devices = [
                device_id for device_id, device in self.alexa_devices.items()
                if device.get('room') == room
            ]
            
            if room_devices:
                # Configurer la capture audio pour le premier appareil de la pièce
                self._configure_audio_capture(room_devices[0])
    
    def _configure_audio_capture(self, device_id: str):
        """
        Configure la capture audio pour un appareil Alexa spécifique.
        
        Args:
            device_id: Identifiant de l'appareil Alexa
        """
        try:
            # Activer la capture audio sur l'appareil
            alexaapi.configure_audio_capture(device_id)
            self.logger.info(f"Capture audio configurée pour l'appareil {device_id}")
        except Exception as e:
            self.logger.error(f"Erreur de configuration audio pour {device_id}: {e}")
    
    def _handle_audio_capture(self, message: Dict[str, Any]):
        """
        Gère les demandes de capture audio multi-pièces.
        
        Args:
            message: Message contenant les détails de capture audio
        """
        rooms = message.get('rooms', self.config['audio_capture'].get('rooms', []))
        duration = message.get('duration', 10)  # 10 secondes par défaut
        
        captured_audio = {}
        for room in rooms:
            # Trouver un appareil Alexa dans la pièce
            room_devices = [
                device_id for device_id, device in self.alexa_devices.items()
                if device.get('room') == room
            ]
            
            if room_devices:
                # Capturer l'audio sur le premier appareil de la pièce
                audio_data = alexaapi.capture_audio(room_devices[0], duration)
                captured_audio[room] = audio_data
        
        # Publier les données audio capturées
        self.message_bus.publish("audio/captured", {
            "source": "alexa_multi_room",
            "audio_data": captured_audio
        })
    
    def _handle_audio_play(self, message: Dict[str, Any]):
        """
        Gère la diffusion audio sur les appareils Alexa.
        
        Args:
            message: Message contenant les détails de lecture audio
        """
        rooms = message.get('rooms')
        audio_source = message.get('source')
        
        # Si aucune pièce n'est spécifiée, utiliser toutes les pièces
        if not rooms:
            rooms = self.config['audio_capture'].get('rooms', list(set(
                device.get('room') for device in self.alexa_devices.values() if device.get('room')
            )))
        
        # Diffuser l'audio dans les pièces spécifiées
        for room in rooms:
            # Trouver un appareil Alexa dans la pièce
            room_devices = [
                device_id for device_id, device in self.alexa_devices.items()
                if device.get('room') == room
            ]
            
            if room_devices:
                # Jouer l'audio sur le premier appareil de la pièce
                alexaapi.play_audio(room_devices[0], audio_source)
                
                # Suivre le flux actif
                self.active_streams[room] = {
                    "device_id": room_devices[0],
                    "source": audio_source,
                    "start_time": time.time()
                }
    
    def _handle_info_request(self, message: Dict[str, Any]):
        """
        Gère les demandes d'informations via Alexa.
        
        Args:
            message: Message contenant les détails de la requête
        """
        info_type = message.get('type')
        room = message.get('room')
        
        # Sélectionner l'appareil Alexa approprié
        device_id = None
        if room:
            room_devices = [
                device_id for device_id, device in self.alexa_devices.items()
                if device.get('room') == room
            ]
            device_id = room_devices[0] if room_devices else None
        else:
            device_id = self.config.get('default_device')
        
        if not device_id:
            self.logger.warning("Aucun appareil Alexa disponible pour la requête")
            return
        
        # Récupérer les informations selon le type
        if info_type == 'weather':
            weather_info = alexaapi.get_weather(device_id)
            self.message_bus.publish("info/weather", weather_info)
        
        elif info_type == 'temperature':
            temp_info = alexaapi.get_temperature(device_id)
            self.message_bus.publish("info/temperature", temp_info)
        
        elif info_type == 'news':
            news_info = alexaapi.get_news(device_id)
            self.message_bus.publish("info/news", news_info)
    
    def _handle_broadcast(self, message: Dict[str, Any]):
        """
        Gère la diffusion de messages vocaux sur les appareils Alexa.
        
        Args:
            message: Message à diffuser
        """
        text = message.get('text')
        rooms = message.get('rooms', self.config['audio_capture'].get('rooms', []))
        
        for room in rooms:
            # Trouver un appareil Alexa dans la pièce
            room_devices = [
                device_id for device_id, device in self.alexa_devices.items()
                if device.get('room') == room
            ]
            
            if room_devices:
                # Diffuser le message sur le premier appareil de la pièce
                alexaapi.broadcast(room_devices[0], text)
    
    def _handle_status_request(self, message: Dict[str, Any]):
        """
        Gère les demandes de statut des appareils Alexa.
        
        Args:
            message: Message de requête de statut
        """
        status = {
            "devices": self.alexa_devices,
            "active_streams": self.active_streams,
            "configuration": {
                "audio_capture": self.config.get('audio_capture'),
                "music_streaming": self.config.get('music_streaming'),
                "information_retrieval": self.config.get('information_retrieval')
            }
        }
        
        reply_topic = message.get('reply_topic')
        if reply_topic:
            self.message_bus.publish(reply_topic, status)
    
    def cleanup(self) -> bool:
        """
        Nettoie les ressources du module Alexa.
        
        Returns:
            True si le nettoyage est réussi
        """
        # Arrêter tous les flux actifs
        for room, stream_info in self.active_streams.items():
            try:
                alexaapi.stop_audio(stream_info['device_id'])
            except Exception as e:
                self.logger.warning(f"Erreur lors de l'arrêt du flux dans {room}: {e}")
        
        self.active_streams.clear()
        return True

def create_module(module_id: str, config: Optional[Dict[str, Any]] = None) -> AlexaIntegrationModule:
    """
    Crée une instance du module d'intégration Alexa.
    
    Args:
        module_id: Identifiant unique du module
        config: Configuration du module
    
    Returns:
        Instance du module d'intégration Alexa
    """
    return AlexaIntegrationModule(module_id, config)
