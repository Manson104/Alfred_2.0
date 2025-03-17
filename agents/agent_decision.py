"""
Agent décisionnel fusionné (O5) - Analyse proactive des demandes et prise de décisions.
"""
import os
import json
import time
import threading
import hashlib
import re
from typing import Dict, Any, List, Optional
from base_agent import BaseAgent
import redis
import json

# Connexion à Redis (adapter l'hôte si besoin)
redis_client = redis.Redis(host='localhost', port=6379, db=0)


try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

class DecisionAgent(BaseAgent):
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379, openai_api_key: Optional[str] = None):
        super().__init__("o5", redis_host, redis_port)
        self.capabilities = ["proactive_suggestions", "task_optimization", "decision_making", "pattern_recognition"]
        self.openai_api_key = openai_api_key
        if OPENAI_AVAILABLE and openai_api_key:
            openai.api_key = openai_api_key
            self.openai_available = True
        else:
            self.openai_available = False
        
        self.decision_cache = {}
        self.cache_lock = threading.Lock()
        self.logger.info(f"Agent décisionnel (O5) initialisé. OpenAI disponible: {self.openai_available}")
    
    def on_start(self) -> None:
        self.broadcast_message("agent_online", {"agent_type": "decision", "capabilities": self.capabilities})
        self.send_command("orchestrator", "status_update", {"status": "ready", "capabilities": self.capabilities})
        self.logger.info("Agent décisionnel (O5) démarré")
    
    def on_stop(self) -> None:
        self.broadcast_message("agent_offline", {"agent_type": "decision", "shutdown_time": time.time()})
        self.logger.info("Agent décisionnel (O5) arrêté")
    
    def _preprocess_text(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
        
    # 1. Ajouter ces méthodes à la classe DecisionAgent:

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
        elif msg_type == 'analyze_user_request':
            # Analyser une demande utilisateur
            request_text = data.get('request', '')
            if request_text:
                result = self.process_command({"type": "analyze_request", "data": {"request": request_text}})
                reply_to = data.get('reply_to', 'orchestrator')
                self.send_redis_message(f"{reply_to}:notifications", 'request_analysis_result', result)
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
        self.broadcast_message("agent_online", {"agent_type": "decision", "capabilities": self.capabilities})
        self.send_command("orchestrator", "status_update", {"status": "ready", "capabilities": self.capabilities})
        self.setup_redis_listener()
        self.logger.info("Agent décisionnel (O5) démarré")

    # 3. Modifier la méthode on_stop pour fermer proprement l'écoute Redis:
    def on_stop(self) -> None:
        # Arrêter l'écoute Redis
        if hasattr(self, 'redis_pubsub'):
            self.redis_pubsub.unsubscribe()
            
        self.broadcast_message("agent_offline", {"agent_type": "decision", "shutdown_time": time.time()})
        self.logger.info("Agent décisionnel (O5) arrêté")
    
    
    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        cmd_type = command.get("type", "unknown")
        self.logger.info(f"Agent décisionnel traite commande: {cmd_type}")
        if cmd_type == "analyze_request":
            request_text = command.get("data", {}).get("request", "")
            processed = self._preprocess_text(request_text)
            # Vérification simple : s'il contient "urgent", on renvoie priorité élevée
            priority = 8 if "urgent" in processed else 5
            result = {
                "agents": ["o1", "o4"] if "domotique" in processed else ["o1"],
                "priority": priority,
                "analysis": f"Texte analysé: {processed}"
            }
            # Mettre en cache le résultat
            cache_key = hashlib.md5(processed.encode()).hexdigest()
            with self.cache_lock:
                self.decision_cache[cache_key] = result
            return result
        elif cmd_type == "status_request":
            return {"status": "ready", "capabilities": self.capabilities}
        else:
            return {"success": False, "message": f"Commande non supportée: {cmd_type}"}

if __name__ == "__main__":
    agent = DecisionAgent(openai_api_key="YOUR_OPENAI_API_KEY")
    agent.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
