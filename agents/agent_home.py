"""
Agent domotique fusionné (O4) - Gère la domotique et le médiacenter.
"""
import os
import json
import time
import threading
import requests
from typing import Dict, Any, Optional
from base_agent import BaseAgent
import redis
import json

# Connexion à Redis (adapter l'hôte si besoin)
redis_client = redis.Redis(host='localhost', port=6379, db=0)


class HomeAgent(BaseAgent):
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379,
                 home_assistant_url: Optional[str] = None, home_assistant_token: Optional[str] = None):
        super().__init__("o4", redis_host, redis_port)
        self.capabilities = ["home_automation", "media_control", "device_monitoring"]
        self.home_assistant_url = home_assistant_url or "http://localhost:8123"
        self.home_assistant_token = home_assistant_token or "YOUR_HOME_ASSISTANT_TOKEN"
        self.ha_headers = {"Authorization": f"Bearer {self.home_assistant_token}"} if self.home_assistant_token else None
        self.logger.info("Agent domotique (O4) initialisé")
    
    def on_start(self) -> None:
        self.broadcast_message("agent_online", {"agent_type": "home_automation", "capabilities": self.capabilities})
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities,
            "home_assistant_available": self.ha_headers is not None
        })
        self.logger.info("Agent domotique (O4) démarré")
    
    def on_stop(self) -> None:
        self.broadcast_message("agent_offline", {"agent_type": "home_automation", "shutdown_time": time.time()})
        self.logger.info("Agent domotique (O4) arrêté")
    
    def control_device(self, entity_id: str, service: str, service_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.ha_headers or not self.home_assistant_url:
            return {"success": False, "error": "Home Assistant non configuré"}
        data = service_data or {}
        data["entity_id"] = entity_id
        try:
            response = requests.post(
                f"{self.home_assistant_url}/api/services/{entity_id.split('.')[0]}/{service}",
                headers=self.ha_headers,
                json=data,
                timeout=5
            )
            if response.status_code in (200, 201):
                self.logger.info(f"Commande {service} envoyée à {entity_id}")
                return {"success": True, "response": response.json()}
            else:
                self.logger.error(f"Erreur {response.status_code} lors du contrôle de {entity_id}")
                return {"success": False, "error": response.text}
        except Exception as e:
            self.logger.error(f"Exception lors du contrôle de {entity_id}: {e}")
            return {"success": False, "error": str(e)}

    # 1. Ajouter ces méthodes à la classe HomeAgent:

    def setup_redis_listener(self):
        """Configure et démarre l'écoute des messages Redis pour l'agent."""
        self.redis_pubsub = self.redis_client.pubsub()
        self.redis_pubsub.subscribe(f"{self.agent_id}:notifications")
        self.redis_listener_thread = threading.Thread(target=self._redis_listener_loop, daemon=True)
        self.redis_listener_thread.start()
        self.logger.info(f"Agent {self.agent_id} en écoute sur le canal {self.agent_id}:notifications")

    def _redis_listener_loop(self):
        """Boucle d'écoute infinie pour les messages Redis."""
        if not self.redis_client:
            self.logger.error("Redis non connecté, impossible de démarrer l'écoute")
            return
        
        self.logger.info(f"Démarrage de la boucle d'écoute Redis pour {self.agent_id}")
        
        try:
            for message in self.redis_pubsub.listen():
                if not self.running:
                    break
                    
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        self.logger.info(f"Message Redis reçu: {data.get('type', 'unknown')}")
                        self._handle_redis_message(data)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Erreur décodage JSON du message Redis: {e}")
                    except Exception as e:
                        self.logger.error(f"Erreur traitement message Redis: {e}")
        except Exception as e:
            self.logger.error(f"Erreur dans la boucle d'écoute Redis: {e}")
        finally:
            self.logger.info("Arrêt de la boucle d'écoute Redis")

    def _handle_redis_message(self, message):
        """Traite un message reçu via Redis."""
        msg_type = message.get('type', 'unknown')
        data = message.get('data', {})
        
        self.logger.info(f"Traitement message Redis: {msg_type}")
        
        # Actions spécifiques selon le type de message
        if msg_type == 'direct_command':
            # Traiter les commandes directes
            if 'command' in data:
                command = data['command']
                self.process_command(command)
        elif msg_type == 'device_control_request':
            # Contrôler un appareil domotique
            entity_id = data.get('entity_id')
            service = data.get('service')
            service_data = data.get('service_data')
            
            if entity_id and service:
                result = self.control_device(entity_id, service, service_data)
                reply_to = data.get('reply_to', 'orchestrator')
                self.send_redis_message(f"{reply_to}:notifications", 'device_control_result', result)
        elif msg_type == 'notification':
            # Traiter les notifications
            self.log_activity('redis_notification', data)
        else:
            self.logger.warning(f"Type de message Redis non reconnu: {msg_type}")

    def send_redis_message(self, channel, message_type, data):
        """Envoie un message via Redis sur un canal spécifique."""
        if not self.redis_client:
            self.logger.warning("Redis non connecté, message non envoyé")
            return False
        
        message = {
            'type': message_type,
            'sender': self.agent_id,
            'timestamp': time.time(),
            'data': data
        }
        
        try:
            self.redis_client.publish(channel, json.dumps(message))
            self.logger.info(f"Message Redis envoyé sur {channel}: {message_type}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur envoi message Redis: {e}")
            return False

    # 2. Modifier la méthode on_start pour ajouter l'appel à setup_redis_listener:
    def on_start(self) -> None:
        self.broadcast_message("agent_online", {"agent_type": "home_automation", "capabilities": self.capabilities})
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities,
            "home_assistant_available": self.ha_headers is not None
        })
        self.setup_redis_listener()
        self.logger.info("Agent domotique (O4) démarré")

    # 3. Modifier la méthode on_stop pour fermer proprement l'écoute Redis:
    def on_stop(self) -> None:
        # Arrêter l'écoute Redis
        if hasattr(self, 'redis_pubsub'):
            self.redis_pubsub.unsubscribe()
            
        self.broadcast_message("agent_offline", {"agent_type": "home_automation", "shutdown_time": time.time()})
        self.logger.info("Agent domotique (O4) arrêté")

    pubsub.subscribe('agent_domotique')
    
    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        cmd_type = command.get("type", "unknown")
        self.logger.info(f"Agent domotique reçoit commande: {cmd_type}")
        if cmd_type == "device_control":
            data = command.get("data", {})
            entity_id = data.get("entity_id")
            service = data.get("service")
            service_data = data.get("service_data")
            return self.control_device(entity_id, service, service_data)
        elif cmd_type == "status_request":
            return {"status": "ready", "capabilities": self.capabilities}
        else:
            return {"success": False, "message": f"Commande non supportée: {cmd_type}"}

if __name__ == "__main__":
    agent = HomeAgent(home_assistant_url="http://192.168.1.X:8123", home_assistant_token="YOUR_HOME_ASSISTANT_TOKEN")
    agent.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
