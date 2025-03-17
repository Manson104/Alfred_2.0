"""
Agent de sécurité fusionné (O3) - Surveille le système, détecte les intrusions et analyse les logs.
"""
import os
import json
import time
import threading
import subprocess
import platform
from typing import Dict, Any
from base_agent import BaseAgent
import redis
import json
import redis
import json

    redis_client = redis.Redis(host='localhost', port=6379, db=0)

    def handle_message(message):
        action = message.get("action")
        if action == "scan_network":
            # ta logique de scan réseau ici
            send_response('orchestrator', {"status": "success", "action": "scan_network"})

    def send_response(channel, message):
        redis_client.publish(channel, json.dumps(message))

    pubsub = redis_client.pubsub()
    pubsub.subscribe('agent_security')

    print("Agent Sécurité en écoute...")
    for message in pubsub.listen():
        if message['type'] == 'message':
            data = json.loads(message['data'].decode('utf-8'))
            handle_message(data)


# Connexion à Redis (adapter l'hôte si besoin)
redis_client = redis.Redis(host='localhost', port=6379, db=0)


class SecurityAgent(BaseAgent):
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379):
        super().__init__("o3", redis_host, redis_port)
        self.capabilities = ["intrusion_detection", "log_analysis", "network_monitoring", "system_integrity"]
        self.monitor_interval = 60  # secondes
        self.monitor_thread = None
        self.running = False
        self.logger.info("Agent de sécurité (O3) initialisé")
    
    def on_start(self) -> None:
        self.broadcast_message("agent_online", {"agent_type": "security", "capabilities": self.capabilities})
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("Agent de sécurité (O3) démarré")
    
    def on_stop(self) -> None:
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        self.broadcast_message("agent_offline", {"agent_type": "security", "shutdown_time": time.time()})
        self.logger.info("Agent de sécurité (O3) arrêté")
    
    def _monitor_loop(self) -> None:
        while self.running:
            self._check_intrusions()
            self._check_logs()
            self._check_network()
            time.sleep(self.monitor_interval)
    
    def _check_intrusions(self) -> None:
        # Exemple : utilisation de netstat pour vérifier les connexions suspectes
        try:
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, shell=True)
            if result.returncode == 0:
                output = result.stdout.lower()
                if "netcat" in output:
                    alert = {"alert": "Processus suspect détecté (netcat)", "timestamp": time.time()}
                    self.broadcast_message("security_alert", alert)
                    self.logger.warning("Intrusion détectée: netcat présent")
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des intrusions: {e}")
    
    def _check_logs(self) -> None:
        # Exemple simplifié : vérifier un fichier log local
        log_file = os.path.join(os.getcwd(), "logs", "alfred.log")
        if os.path.exists(log_file):
            try:
                with open(log_file, "r") as f:
                    errors = [line for line in f if "error" in line.lower()]
                if errors:
                    self.logger.warning(f"Anomalies détectées dans les logs: {len(errors)} erreurs")
                    self.broadcast_message("security_alert", {"alert": "Erreurs dans les logs", "count": len(errors)})
            except Exception as e:
                self.logger.error(f"Erreur lors de la lecture des logs: {e}")
    
    def _check_network(self) -> None:
        # Exemple simplifié : exécuter 'arp -a' et vérifier la présence d'adresses externes
        try:
            output = subprocess.check_output(["arp", "-a"], universal_newlines=True)
            if "external" in output.lower():
                self.logger.warning("Connexions externes suspectes détectées")
                self.broadcast_message("security_alert", {"alert": "Connexions externes suspectes", "timestamp": time.time()})
        except Exception as e:
            self.logger.error(f"Erreur lors du scan réseau: {e}")
    
    # 1. Ajouter ces méthodes à la classe SecurityAgent:

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
        elif msg_type == 'security_check_request':
            # Faire un contrôle de sécurité ponctuel
            check_type = data.get('check_type', 'intrusion')
            reply_to = data.get('reply_to', 'orchestrator')
            
            if check_type == 'intrusion':
                self._check_intrusions()
            elif check_type == 'logs':
                self._check_logs()
            elif check_type == 'network':
                self._check_network()
            
            self.send_redis_message(f"{reply_to}:notifications", 
                                   'security_check_complete', 
                                   {'check_type': check_type, 'timestamp': time.time()})
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
        self.broadcast_message("agent_online", {"agent_type": "security", "capabilities": self.capabilities})
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.setup_redis_listener()
        self.logger.info("Agent de sécurité (O3) démarré")

    # 3. Modifier la méthode on_stop pour fermer proprement l'écoute Redis:
    def on_stop(self) -> None:
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        
        # Arrêter l'écoute Redis
        if hasattr(self, 'redis_pubsub'):
            self.redis_pubsub.unsubscribe()
            
        self.broadcast_message("agent_offline", {"agent_type": "security", "shutdown_time": time.time()})
        self.logger.info("Agent de sécurité (O3) arrêté")


    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        # Pour cet agent, nous pouvons ajouter des commandes spécifiques si nécessaire.
        cmd_type = command.get("type", "unknown")
        self.logger.info(f"Agent de sécurité traite la commande: {cmd_type}")
        # Exemple simple : répondre à une demande de statut
        if cmd_type == "status_request":
            return {
                "status": "ready",
                "capabilities": self.capabilities
            }
        else:
            return {"success": False, "message": f"Commande non supportée: {cmd_type}"}

if __name__ == "__main__":
    agent = SecurityAgent()
    agent.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
