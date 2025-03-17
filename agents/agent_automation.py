"""
Automation Agent (O1) - Agent de gestion des commandes CMD et AutoHotkey
"""
import os
import json
import time
import subprocess
import threading
from typing import Dict, Any, Tuple, Optional
import redis
import json

# Connexion à Redis (adapter l'hôte si besoin)
redis_client = redis.Redis(host='localhost', port=6379, db=0)


from base_agent import BaseAgent  # Assure-toi que base_agent.py est dans le même dossier

class AutomationAgent(BaseAgent):
    """Agent spécialisé dans l'exécution de commandes système et scripts AutoHotkey"""
    
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379):
        super().__init__("o1", redis_host, redis_port)
        
        # Capacités de l'agent
        self.capabilities = [
            "cmd_execution",     # Exécution de commandes CMD/PowerShell
            "autohotkey_script",  # Exécution de scripts AutoHotkey
            "system_automation",  # Automatisation du système
            "keyboard_mouse",     # Automatisation du clavier et de la souris
            "batch_processing"    # Traitement par lots
        ]
        
        # Répertoire pour les scripts AutoHotkey
        self.ahk_script_dir = os.path.join(os.getcwd(), "scripts", "autohotkey")
        if not os.path.exists(self.ahk_script_dir):
            os.makedirs(self.ahk_script_dir, exist_ok=True)
        
        # Chemin vers l'exécutable AutoHotkey
        self.ahk_exe_path = self._find_autohotkey_executable()
        
        # Garde une trace des processus lancés
        self.running_processes = {}
        self.process_lock = threading.Lock()
        
        self.logger.info(f"Agent d'automatisation (O1) initialisé. AutoHotkey trouvé : {self.ahk_exe_path is not None}")
    
    def _find_autohotkey_executable(self) -> Optional[str]:
        """
        Recherche l'exécutable AutoHotkey dans les emplacements standard
        """
        possible_paths = [
            "C:\\Program Files\\AutoHotkey\\AutoHotkey.exe",
            "C:\\Program Files (x86)\\AutoHotkey\\AutoHotkey.exe",
            "/usr/bin/autohotkey",
            "/usr/local/bin/autohotkey"
        ]
        
        try:
            result = subprocess.run(["where", "autohotkey"], capture_output=True, text=True, shell=True)
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                if os.path.exists(path):
                    return path
        except Exception:
            pass
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        self.logger.warning("Impossible de trouver l'exécutable AutoHotkey")
        return None
    
    def on_start(self) -> None:
        """Démarrage de l'agent"""
        self.broadcast_message("agent_online", {
            "agent_type": "automation",
            "capabilities": self.capabilities
        })
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities,
            "autohotkey_available": self.ahk_exe_path is not None
        })
        self.logger.info("Agent d'automatisation (O1) démarré")
    
    def on_stop(self) -> None:
        """Arrêt de l'agent"""
        with self.process_lock:
            for process_id, process_info in list(self.running_processes.items()):
                try:
                    process = process_info.get('process')
                    if process and process.poll() is None:
                        process.terminate()
                        process.wait(timeout=2)
                        self.logger.info(f"Processus {process_id} terminé lors de l'arrêt")
                except Exception as e:
                    self.logger.error(f"Erreur lors de la terminaison du processus {process_id}: {str(e)}")
        self.broadcast_message("agent_offline", {
            "agent_type": "automation",
            "shutdown_time": time.time()
        })
        self.logger.info("Agent d'automatisation (O1) arrêté")
    
    def execute_cmd(self, command: str, working_dir: Optional[str] = None, 
                    timeout: Optional[int] = None, shell: bool = True) -> Tuple[str, str, int]:
        """
        Exécute une commande système via CMD ou PowerShell
        """
        self.logger.info(f"Exécution de la commande: {command}")
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=shell,
                cwd=working_dir,
                text=True
            )
            process_id = str(process.pid)
            with self.process_lock:
                self.running_processes[process_id] = {
                    'process': process,
                    'command': command,
                    'start_time': time.time()
                }
            stdout, stderr = process.communicate(timeout=timeout)
            return_code = process.returncode
            with self.process_lock:
                if process_id in self.running_processes:
                    del self.running_processes[process_id]
            self.log_activity("cmd_executed", {
                'command': command,
                'return_code': return_code,
                'execution_time': time.time() - self.running_processes.get(process_id, {}).get('start_time', time.time())
            })
            return stdout, stderr, return_code
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout lors de l'exécution de la commande: {command}")
            return "", "Timeout expired", -1
        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution de la commande: {str(e)}")
            return "", str(e), -1
    
    def run_autohotkey_script(self, script_content: str, script_name: Optional[str] = None, 
                                timeout: Optional[int] = None) -> Tuple[bool, str]:
        """
        Exécute un script AutoHotkey
        """
        if not self.ahk_exe_path:
            return False, "AutoHotkey n'est pas disponible sur ce système"
        if not script_name:
            script_name = f"script_{int(time.time())}_{hash(script_content) % 10000}.ahk"
        if not script_name.endswith('.ahk'):
            script_name += '.ahk'
        script_path = os.path.join(self.ahk_script_dir, script_name)
        try:
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            self.logger.info(f"Script AutoHotkey créé: {script_path}")
            command = f"\"{self.ahk_exe_path}\" \"{script_path}\""
            stdout, stderr, return_code = self.execute_cmd(command, timeout=timeout)
            self.log_activity("autohotkey_executed", {
                'script_name': script_name,
                'return_code': return_code
            })
            if return_code == 0:
                return True, "Script exécuté avec succès"
            else:
                return False, f"Erreur lors de l'exécution du script: {stderr}"
        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution du script AutoHotkey: {str(e)}")
            return False, str(e)
    
    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite une commande reçue
        """
        command_type = command.get('type', 'unknown')
        data = command.get('data', {})
        self.logger.info(f"Traitement de la commande: {command_type}")
        if command_type in ['cmd_execution', 'cmd_execution_o1']:
            cmd = data.get('command', '')
            working_dir = data.get('working_dir')
            timeout = data.get('timeout')
            stdout, stderr, return_code = self.execute_cmd(cmd, working_dir, timeout)
            return {
                'success': return_code == 0,
                'stdout': stdout,
                'stderr': stderr,
                'return_code': return_code
            }
        elif command_type in ['autohotkey_script', 'autohotkey_script_o1']:
            script_content = data.get('script_content', '')
            script_name = data.get('script_name')
            timeout = data.get('timeout')
            success, message = self.run_autohotkey_script(script_content, script_name, timeout)
            return {
                'success': success,
                'message': message
            }
        elif command_type == 'status_request':
            return {
                'status': 'ready',
                'type': 'status_response',
                'capabilities': self.capabilities,
                'autohotkey_available': self.ahk_exe_path is not None,
                'running_processes': len(self.running_processes)
            }
        elif command_type == 'terminate_process':
            process_id = data.get('process_id')
            with self.process_lock:
                if process_id in self.running_processes:
                    process = self.running_processes[process_id].get('process')
                    if process and process.poll() is None:
                        try:
                            process.terminate()
                            process.wait(timeout=2)
                            del self.running_processes[process_id]
                            return {'success': True, 'message': f"Processus {process_id} terminé"}
                        except Exception as e:
                            return {'success': False, 'message': f"Erreur lors de la terminaison: {str(e)}"}
            return {'success': False, 'message': f"Processus {process_id} non trouvé"}
        else:
            self.logger.warning(f"Commande inconnue reçue: {command_type}")
            return {
                'success': False,
                'message': f"Commande non supportée: {command_type}"
            }
    
    # 1. Ajouter ces méthodes à la classe AutomationAgent:

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
        elif msg_type == 'cmd_execution_request':
            # Exécuter directement une commande système
            cmd = data.get('command', '')
            working_dir = data.get('working_dir')
            timeout = data.get('timeout')
            if cmd:
                stdout, stderr, return_code = self.execute_cmd(cmd, working_dir, timeout)
                self.send_redis_message(f"{data.get('reply_to', 'orchestrator')}:notifications", 
                                       'cmd_execution_response', 
                                       {'stdout': stdout, 'stderr': stderr, 'return_code': return_code})
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
        """Démarrage de l'agent"""
        self.broadcast_message("agent_online", {
            "agent_type": "automation",
            "capabilities": self.capabilities
        })
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities,
            "autohotkey_available": self.ahk_exe_path is not None
        })
        self.setup_redis_listener()
        self.logger.info("Agent d'automatisation (O1) démarré")

    # 3. Modifier la méthode on_stop pour fermer proprement l'écoute Redis:
    def on_stop(self) -> None:
        """Arrêt de l'agent"""
        with self.process_lock:
            for process_id, process_info in list(self.running_processes.items()):
                try:
                    process = process_info.get('process')
                    if process and process.poll() is None:
                        process.terminate()
                        process.wait(timeout=2)
                        self.logger.info(f"Processus {process_id} terminé lors de l'arrêt")
                except Exception as e:
                    self.logger.error(f"Erreur lors de la terminaison du processus {process_id}: {str(e)}")
        
        # Arrêter l'écoute Redis
        if hasattr(self, 'redis_pubsub'):
            self.redis_pubsub.unsubscribe()
        
        self.broadcast_message("agent_offline", {
            "agent_type": "automation",
            "shutdown_time": time.time()
        })
        self.logger.info("Agent d'automatisation (O1) arrêté")


    def process_broadcast(self, message: Dict[str, Any]) -> None:
        """
        Traite un message broadcast
        """
        msg_type = message.get('type', 'unknown')
        if msg_type == 'status_request':
            self.send_command("orchestrator", "status_update", {
                'status': 'ready',
                'capabilities': self.capabilities,
                'autohotkey_available': self.ahk_exe_path is not None,
                'running_processes': len(self.running_processes)
            })
        elif msg_type == 'system_shutdown':
            self.logger.info("Demande d'arrêt du système reçue, nettoyage des processus")
            with self.process_lock:
                for process_id, process_info in list(self.running_processes.items()):
                    try:
                        process = process_info.get('process')
                        if process and process.poll() is None:
                            process.terminate()
                    except Exception:
                        pass
        else:
            self.logger.info(f"Broadcast reçu : {msg_type}")
    
    def log_activity(self, activity_type: str, details: Dict[str, Any]) -> None:
        self.logger.info(f"Activité enregistrée [{activity_type}]: {details}")

if __name__ == "__main__":
    # Test en standalone
    agent = AutomationAgent()
    agent.on_start()
    test_command = {
        "type": "cmd_execution",
        "data": {
            "command": "echo Hello from AutomationAgent",
            "timeout": 5
        }
    }
    response = agent.process_command(test_command)
    print(response)
    agent.on_stop()
