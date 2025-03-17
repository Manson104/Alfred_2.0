import json
import time
import uuid
import redis
import threading
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("alfred_agents.log"), logging.StreamHandler()]
)

class BaseAgent(ABC):
    def __init__(self, agent_id: str, redis_host: str = 'localhost', redis_port: int = 6379):
        self.agent_id = agent_id
        self.logger = logging.getLogger(f"Agent:{agent_id}")
        try:
            self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
            self.redis_client.ping()
            self.logger.info(f"Agent {agent_id} connecté à Redis sur {redis_host}:{redis_port}")
        except Exception as e:
            self.logger.error(f"Erreur de connexion Redis pour l'agent {agent_id}: {e}")
            self.redis_client = None

        self.command_channel = f"{agent_id}:commands"
        self.response_channel = f"{agent_id}:responses"
        self.broadcast_channel = "alfred:broadcast"
        self.running = False
        self.listener_thread = None

    def start(self) -> None:
        if self.running:
            self.logger.warning("L'agent est déjà en cours d'exécution")
            return
        self.running = True
        self.listener_thread = threading.Thread(target=self._listen_for_messages, daemon=True)
        self.listener_thread.start()
        self.logger.info(f"Agent {self.agent_id} démarré")
        self.on_start()

    def stop(self) -> None:
        self.running = False
        if self.listener_thread:
            self.listener_thread.join(timeout=2.0)
        self.logger.info(f"Agent {self.agent_id} arrêté")
        self.on_stop()

    def _listen_for_messages(self) -> None:
        if not self.redis_client:
            return
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe(self.command_channel, self.broadcast_channel)
        self.logger.info(f"Écoute sur {self.command_channel} et {self.broadcast_channel}")
        for message in pubsub.listen():
            if not self.running:
                break
            if message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    if message['channel'] == self.command_channel:
                        self._handle_command(data)
                    elif message['channel'] == self.broadcast_channel:
                        self._handle_broadcast(data)
                except Exception as e:
                    self.logger.error(f"Erreur lors du traitement d'un message: {e}")

    def _handle_command(self, command: Dict[str, Any]) -> None:
        task_id = command.get('task_id', str(uuid.uuid4()))
        self.logger.info(f"Commande reçue: {command.get('type', 'unknown')}, task_id: {task_id}")
        result = self.process_command(command)
        self.send_response(task_id, result)

    def _handle_broadcast(self, message: Dict[str, Any]) -> None:
        sender = message.get('sender', 'unknown')
        if sender == self.agent_id:
            return
        self.logger.info(f"Broadcast reçu de {sender}: {message.get('type', 'unknown')}")
        self.process_broadcast(message)

    def send_command(self, target_agent: str, command_type: str, data: Dict[str, Any]) -> None:
        if not self.redis_client:
            self.logger.warning("Redis non connecté, commande non envoyée")
            return
        command = {
            'task_id': str(uuid.uuid4()),
            'type': command_type,
            'sender': self.agent_id,
            'timestamp': time.time(),
            'data': data
        }
        target_channel = f"{target_agent}:commands"
        self.redis_client.publish(target_channel, json.dumps(command))
        self.logger.info(f"Commande envoyée à {target_agent}: {command_type}")

    def send_response(self, task_id: str, result: Dict[str, Any]) -> None:
        if not self.redis_client:
            return
        response = {
            'task_id': task_id,
            'sender': self.agent_id,
            'timestamp': time.time(),
            'success': True,
            'result': result
        }
        self.redis_client.publish(self.response_channel, json.dumps(response))
        self.logger.info(f"Réponse envoyée pour task_id: {task_id}")

    @abstractmethod
    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        pass

    def process_broadcast(self, message: Dict[str, Any]) -> None:
        self.logger.info(f"BaseAgent reçoit un broadcast: {message.get('type', 'unknown')}")

    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
        pass

    def log_activity(self, activity_type: str, details: Dict[str, Any]) -> None:
        self.logger.info(f"Activité [{activity_type}]: {details}")
