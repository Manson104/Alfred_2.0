"""
core/message_bus.py
------------------
Module de communication centralisé pour Alfred.
Gère les communications entre agents via Redis ou d'autres backends.
"""

import json
import time
import uuid
import logging
import threading
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum, auto

# Configuration du logger
logger = logging.getLogger("MessageBus")

class MessagePriority(Enum):
    """Niveau de priorité des messages."""
    LOW = auto()
    NORMAL = auto()
    HIGH = auto()
    URGENT = auto()

class MessageType(Enum):
    """Types de messages standards."""
    COMMAND = "command"              # Demande d'action
    RESPONSE = "response"            # Réponse à une commande
    EVENT = "event"                  # Notification d'événement
    BROADCAST = "broadcast"          # Message à tous les agents
    STATUS_UPDATE = "status_update"  # Mise à jour de l'état

class MessageBus:
    """
    Bus de messages centralisé pour la communication entre agents.
    Implémente le pattern Observer pour permettre aux agents de s'abonner à des sujets.
    """
    
    def __init__(self, backend_type: str = "redis", 
                 redis_host: str = "localhost", 
                 redis_port: int = 6379):
        """
        Initialise le bus de message avec le backend spécifié.
        
        Args:
            backend_type: Type de backend ("redis", "memory", etc.)
            redis_host: Hôte Redis (si backend redis)
            redis_port: Port Redis (si backend redis)
        """
        self.backend_type = backend_type
        self.backend = None
        self.subscribers = {}  # topic -> [callbacks]
        self.running = False
        self.listener_thread = None
        
        # Initialisation du backend
        if backend_type == "redis":
            self._init_redis_backend(redis_host, redis_port)
        elif backend_type == "memory":
            self._init_memory_backend()
        else:
            raise ValueError(f"Backend non supporté: {backend_type}")
    
    def _init_redis_backend(self, host: str, port: int) -> None:
        """Initialise le backend Redis."""
        try:
            import redis
            self.backend = redis.Redis(host=host, port=port, decode_responses=True)
            self.backend.ping()  # Vérifier la connexion
            logger.info(f"Backend Redis initialisé avec succès sur {host}:{port}")
        except ImportError:
            logger.error("Module Redis non disponible. Installez-le avec: pip install redis")
            raise
        except Exception as e:
            logger.error(f"Erreur d'initialisation du backend Redis: {e}")
            raise
    
    def _init_memory_backend(self) -> None:
        """Initialise un backend en mémoire (pour les tests ou standalone)."""
        self.backend = {"messages": {}}
        logger.info("Backend en mémoire initialisé")
    
    def start(self) -> None:
        """Démarre l'écoute des messages."""
        if self.running:
            logger.warning("Le bus de message est déjà en cours d'exécution")
            return
        
        self.running = True
        
        if self.backend_type == "redis":
            self.listener_thread = threading.Thread(target=self._redis_listener_loop, daemon=True)
            self.listener_thread.start()
        
        logger.info("Bus de message démarré")
    
    def stop(self) -> None:
        """Arrête l'écoute des messages."""
        self.running = False
        if self.listener_thread:
            self.listener_thread.join(timeout=2.0)
        logger.info("Bus de message arrêté")
    
    def _redis_listener_loop(self) -> None:
        """Boucle d'écoute pour Redis."""
        if not self.backend:
            logger.error("Backend Redis non initialisé")
            return
            
        # Créer un pubsub pour chaque topic auquel nous sommes abonnés
        pubsub = self.backend.pubsub()
        topics = list(self.subscribers.keys())
        if topics:
            pubsub.subscribe(*topics)
            logger.info(f"Écoute sur les topics: {topics}")
        
        while self.running:
            try:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                if message:
                    topic = message['channel']
                    data = json.loads(message['data'])
                    self._dispatch_message(topic, data)
            except Exception as e:
                logger.error(f"Erreur lors de l'écoute des messages: {e}")
                time.sleep(1)  # Pause avant de réessayer
    
    def _dispatch_message(self, topic: str, data: Dict[str, Any]) -> None:
        """Dispatche un message aux abonnés d'un topic."""
        if topic in self.subscribers:
            for callback in self.subscribers[topic]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Erreur dans le callback pour le topic {topic}: {e}")
    
    def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Abonne un callback à un topic.
        
        Args:
            topic: Sujet à écouter
            callback: Fonction à appeler lors de la réception d'un message
        """
        if topic not in self.subscribers:
            self.subscribers[topic] = []
            # Si le bus est déjà en cours d'exécution, s'abonner au nouveau topic
            if self.running and self.backend_type == "redis":
                pubsub = self.backend.pubsub()
                pubsub.subscribe(topic)
        
        self.subscribers[topic].append(callback)
        logger.info(f"Abonné au topic: {topic}")
    
    def unsubscribe(self, topic: str, callback: Optional[Callable] = None) -> None:
        """
        Désabonne un callback d'un topic.
        
        Args:
            topic: Sujet à désabonner
            callback: Fonction à désabonner (si None, désabonne tous les callbacks)
        """
        if topic in self.subscribers:
            if callback:
                self.subscribers[topic] = [cb for cb in self.subscribers[topic] if cb != callback]
                if not self.subscribers[topic]:
                    del self.subscribers[topic]
            else:
                del self.subscribers[topic]
            logger.info(f"Désabonnement du topic: {topic}")
    
    def publish(self, topic: str, message_type: Union[str, MessageType], 
                data: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL) -> str:
        """
        Publie un message sur un topic.
        
        Args:
            topic: Sujet de publication
            message_type: Type du message
            data: Données du message
            priority: Priorité du message
            
        Returns:
            ID du message publié
        """
        if isinstance(message_type, MessageType):
            message_type = message_type.value
            
        message_id = str(uuid.uuid4())
        message = {
            "id": message_id,
            "type": message_type,
            "priority": priority.value,
            "timestamp": time.time(),
            "data": data
        }
        
        if self.backend_type == "redis":
            self.backend.publish(topic, json.dumps(message))
        elif self.backend_type == "memory":
            if topic not in self.backend["messages"]:
                self.backend["messages"][topic] = []
            self.backend["messages"][topic].append(message)
            # Dispatche immédiatement en mémoire
            self._dispatch_message(topic, message)
        
        logger.debug(f"Message publié sur {topic}: {message_type}")
        return message_id
    
    def send_command(self, target: str, command_type: str, 
                    data: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL) -> str:
        """
        Envoie une commande à un agent spécifique.
        
        Args:
            target: Agent cible
            command_type: Type de commande
            data: Données de la commande
            priority: Priorité de la commande
            
        Returns:
            ID du message envoyé
        """
        command_topic = f"{target}:commands"
        command_data = {
            "command_type": command_type,
            "data": data
        }
        return self.publish(command_topic, MessageType.COMMAND, command_data, priority)
    
    def broadcast(self, message_type: str, data: Dict[str, Any], 
                 priority: MessagePriority = MessagePriority.NORMAL) -> str:
        """
        Diffuse un message à tous les agents.
        
        Args:
            message_type: Type de message broadcast
            data: Données du message
            priority: Priorité du message
            
        Returns:
            ID du message diffusé
        """
        broadcast_topic = "alfred:broadcast"
        broadcast_data = {
            "broadcast_type": message_type,
            "data": data
        }
        return self.publish(broadcast_topic, MessageType.BROADCAST, broadcast_data, priority)
    
    def request_status(self) -> str:
        """
        Demande le statut de tous les agents.
        
        Returns:
            ID du message de demande
        """
        return self.broadcast("status_request", {"timestamp": time.time()}, MessagePriority.NORMAL)
