"""
Agent orchestrateur (Orchestrator) - Coordonne tous les agents d'Alfred.
"""
import json
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from base_agent import BaseAgent
from agent_discussion import DiscussionAgent
from agent_coding import CodingAgent
from agent_discussion import DiscussionAgent
from agent_coding import CodingAgent
from voiceemotionagent import VoiceEmotionAgent


class OrchestratorAgent(BaseAgent):
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379):
        super().__init__("orchestrator", redis_host, redis_port)
        self.agents_registry = {}
        self.required_agents = ["o1", "o3", "o4", "o5"]
        self.logger.info("Agent orchestrateur initialisé")
        self.initialize_agents()

    def initialize_agents(self):
        """Instancie et enregistre les agents Discussion, Codage et VoiceEmotion."""
        try:
            discussion_agent = DiscussionAgent(redis_host="localhost", redis_port=6379, db_path="alfred_memory.db", api_keys={})
            coding_agent = CodingAgent(redis_host="localhost", redis_port=6379, db_path="alfred_memory.db", api_keys={})
            voiceemotion_agent = VoiceEmotionAgent(redis_host="localhost", redis_port=6379, db_path="alfred_memory.db", api_keys={})
            
            self.agents_registry["discussion"] = discussion_agent
            self.agents_registry["coding"] = coding_agent
            self.agents_registry["voiceemotion"] = voiceemotion_agent
            
            self.logger.info("Agents Discussion, Codage et VoiceEmotion intégrés avec succès dans l'orchestrateur.")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation des agents : {e}")


    def on_start(self) -> None:
        self.broadcast_message("status_request", {"timestamp": time.time()})
        self.logger.info("Agent orchestrateur démarré")
        self.setup_redis_listener()
    
    def on_stop(self) -> None:
        self.broadcast_message("system_shutdown", {"timestamp": time.time()})
        self.logger.info("Agent orchestrateur arrêté")
    
    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        cmd_type = command.get("type", "unknown")
        self.logger.info(f"Orchestrateur traite commande: {cmd_type}")
        if cmd_type == "status_request":
            return {"status": "ready", "agents": list(self.agents_registry.keys())}
        else:
            return {"success": False, "message": f"Commande non supportée: {cmd_type}"}
    
    def setup_redis_listener(self):
        """Configure et démarre l'écoute des messages Redis pour l'agent orchestrateur."""
        self.redis_pubsub = self.redis_client.pubsub()
        self.redis_pubsub.subscribe(f"{self.agent_id}:notifications")
        self.redis_listener_thread = threading.Thread(target=self._redis_listener_loop, daemon=True)
        self.redis_listener_thread.start()
        self.logger.info(f"Orchestrateur en écoute sur le canal {self.agent_id}:notifications")

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
        """Traite un message reçu via Redis pour l'orchestrateur."""
        msg_type = message.get('type', 'unknown')
        data = message.get('data', {})
        
        self.logger.info(f"Orchestrateur traite message Redis: {msg_type}")
        
        if msg_type == 'direct_command':
            if 'command' in data:
                command = data['command']
                self.process_command(command)
        elif msg_type == 'agent_command':
            target_agent = data.get('target_agent')
            command_data = data.get('command')
            
            if target_agent and command_data:
                if target_agent in self.agents_registry:
                    self.send_redis_message(f"{target_agent}:notifications", 
                                              'direct_command', 
                                              {'command': command_data, 'reply_to': self.agent_id})
                else:
                    self.logger.warning(f"Agent cible {target_agent} non enregistré")
        elif msg_type == 'broadcast_message':
            broadcast_type = data.get('broadcast_type')
            broadcast_data = data.get('broadcast_data', {})
            self.logger.info(f"Diffusion du message de type {broadcast_type}")
