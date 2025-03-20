import logging
import time
from typing import Dict, Any, List, Optional
import json

from modules.message_bus import MessageBus
from modules.state_manager import StateManager
from modules.manager import ModuleManager

class BaseAgent:
    """
    Classe de base pour tous les agents dans le système Alfred.
    Fournit les fonctionnalités communes et la gestion des modules.
    """
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        """
        Initialise l'agent de base.
        
        Args:
            agent_id: Identifiant unique de l'agent
            config: Configuration de l'agent
        """
        self.agent_id = agent_id
        self.config = config
        self.logger = logging.getLogger(f"agent.{agent_id}")
        
        # Configuration de base
        self.debug_mode = config.get("debug_mode", False)
        
        # Initialiser le bus de messages
        self.message_bus = MessageBus(agent_id)
        
        # Initialiser le gestionnaire d'état
        self.state_manager = StateManager(agent_id, config.get("state_manager", {}))
        
        # Initialiser le gestionnaire de modules
        self.module_manager = ModuleManager(agent_id, config.get("modules", {}), 
                                            self.message_bus, self.state_manager)
        
        # État de l'agent
        self.active = False
        self.start_time = None
        
        self.logger.info(f"Agent {agent_id} initialisé")
        
        # Enregistrer les gestionnaires de messages de base
        self._register_base_handlers()
    
    def _register_base_handlers(self):
        """Enregistre les gestionnaires de messages de base."""
        self.message_bus.register_handler(f"agent/{self.agent_id}/status", self._handle_status_request)
        self.message_bus.register_handler(f"agent/{self.agent_id}/restart", self._handle_restart_request)
        self.message_bus.register_handler(f"agent/{self.agent_id}/config", self._handle_config_request)
    
    def start(self):
        """Démarre l'agent et ses modules."""
        self.logger.info(f"Démarrage de l'agent {self.agent_id}")
        
        # Démarrer le bus de messages
        self.message_bus.start()
        
        # Démarrer le gestionnaire d'état
        self.state_manager.start()
        
        # Démarrer les modules nécessaires
        self.module_manager.start_all()
        
        # Marquer l'agent comme actif
        self.active = True
        self.start_time = time.time()
        
        # Publier un événement de démarrage
        self.message_bus.publish("agent/started", {
            "agent_id": self.agent_id,
            "timestamp": self.start_time
        })
    
    def stop(self):
        """Arrête l'agent et ses modules."""
        self.logger.info(f"Arrêt de l'agent {self.agent_id}")
        
        # Marquer l'agent comme inactif
        self.active = False
        
        # Arrêter les modules
        self.module_manager.stop_all()
        
        # Arrêter le gestionnaire d'état
        self.state_manager.stop()
        
        # Arrêter le bus de messages
        self.message_bus.stop()
        
        # Publier un événement d'arrêt
        self.message_bus.publish("agent/stopped", {
            "agent_id": self.agent_id,
            "timestamp": time.time()
        })
    
    def restart(self):
        """Redémarre l'agent."""
        self.logger.info(f"Redémarrage de l'agent {self.agent_id}")
        
        # Arrêter l'agent
        self.stop()
        
        # Attendre un peu
        time.sleep(1)
        
        # Redémarrer l'agent
        self.start()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Récupère le statut de l'agent.
        
        Returns:
            Dict: Statut de l'agent
        """
        # Récupérer le statut des modules
        module_statuses = self.module_manager.get_all_statuses()
        
        # Construire le statut global
        return {
            "agent_id": self.agent_id,
            "active": self.active,
            "uptime": time.time() - self.start_time if self.start_time else 0,
            "start_time": self.start_time,
            "modules": module_statuses
        }
    
    def _handle_status_request(self, message: Dict[str, Any]):
        """Gère les demandes de statut."""
        status = self.get_status()
        
        # Répondre avec le statut
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], status)
    
    def _handle_restart_request(self, message: Dict[str, Any]):
        """Gère les demandes de redémarrage."""
        # Redémarrer l'agent
        self.restart()
        
        # Répondre avec confirmation
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "agent_id": self.agent_id,
                "timestamp": time.time()
            })
    
    def _handle_config_request(self, message: Dict[str, Any]):
        """Gère les demandes de configuration."""
        # Retourner la configuration actuelle (sans données sensibles)
        safe_config = {k: v for k, v in self.config.items() if k not in ["api_keys", "passwords", "tokens"]}
        
        # Répondre avec la configuration
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "agent_id": self.agent_id,
                "config": safe_config
            })
