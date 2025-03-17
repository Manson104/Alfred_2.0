"""
Agent d'automatisation fusionné - Gère l'exécution de commandes système et de scripts AutoHotkey,
le suivi des processus, et la communication via Redis.
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


from base_agent import BaseAgent  # Assurez-vous que base_agent.py est dans le dossier alfred/agents/

class AutomationAgentMerged(BaseAgent):
    """Agent d'automatisation fusionné qui regroupe l'exécution de commandes et le suivi des processus."""
    
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379):
        super().__init__("o1", redis_host, redis_port)
        
        self.capabilities = [
            "cmd_execution",
            "autohotkey_script",
            "system_automation",
            "keyboard_mouse",
            "batch_processing"
        ]
        
        # Répertoire pour les scripts AutoHotkey
        self.ahk_script_dir = os.path.join(os.getcwd(), "scripts", "autohotkey")
        if not os.path.exists(self.ahk_script_dir):
            os.makedirs(self.ahk_script_dir, exist_ok=True)
        
        self.ahk_exe_path = self._find_autohotkey_executable()
        self.running_processes = {}
        self.process_lock = threading.Lock()
        
        self.logger.info(f"Agent d'automatisation fusionné initialisé. AutoHotkey trouvé : {self.ahk_exe_path is not None}")
    
    def _find_autohotkey_executable(self) -> Optional[str]:
        """Recherche l'exécutable AutoHotkey dans plusieurs emplacements standard."""
        possible_paths = [
            "C:\\Program Files\\AutoHotkey\\AutoHotkey.exe",
            "C:\\Program Files (x86)\\AutoHotkey\\AutoHotkey.exe",
            "/usr/bin/autohotkey",
            "/usr/local/bin/autohotkey"
        ]
        # Essayer de le trouver dans le PATH
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
        self.logger.warning("AutoHotkey introuvable")
        return None
    
    def on_start(self) -> None:
        """Méthode appelée au démarrage de l'agent."""
        self.broadcast_message("agent_online", {
            "agent_type": "automation",
            "capabilities": self.capabilities
        })
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities,
            "autohotkey_available": self.ahk_exe_path is not None
        })
        self.logger.info("Agent d'automatisation fusionné démarré")
    
    def on_stop(self) -> None:
        """Méthode appelée à l'arrêt de l'agent. Termine proprement les processus lancés."""
        with self.process_lock:
            for pid, proc_info in list(self.running_processes.items()):
                try:
                    proc = proc_info.get('process')
                    if proc and proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=2)
                        self.logger.info(f"Processus {pid} terminé lors de l'arrêt")
                except Exception as e:
                    self.logger.error(f"Erreur lors de la terminaison du processus {pid}: {str(e)}")
        self.broadcast_message("agent_offline", {
            "agent_type": "automation",
            "shutdown_time": time.time()
        })
        self.logger.info("Agent d'automatisation fusionné arrêté")
    
    def execute_cmd(self, command: str, working_dir: Optional[str] = None,
                    timeout: Optional[int] = None, shell: bool = True) -> Tuple[str, str, int]:
        """
        Exécute une commande système et retourne (stdout, stderr, code de retour).
        """
        self.logger.info(f"Exécution de la commande: {command}")
        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=shell,
                cwd=working_dir,
                text=True
            )
            pid = str(proc.pid)
            with self.process_lock:
                self.running_processes[pid] = {'process': proc, 'command': command, 'start_time': time.time()}
            stdout, stderr = proc.communicate(timeout=timeout)
            return_code = proc.returncode
            with self.process_lock:
                if pid in self.running_processes:
                    del self.running_processes[pid]
            self.log_activity("cmd_executed", {
                "command": command,
                "return_code": return_code,
                "execution_time": time.time()
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
        Enregistre et exécute un script AutoHotkey, retourne (succès, message).
        """
        if not self.ahk_exe_path:
            return False, "AutoHotkey non disponible"
        if not script_name:
            script_name = f"script_{int(time.time())}_{hash(script_content) % 10000}.ahk"
        if not script_name.endswith(".ahk"):
            script_name += ".ahk"
        script_path = os.path.join(self.ahk_script_dir, script_name)
        try:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script_content)
            self.logger.info(f"Script AutoHotkey créé: {script_path}")
            command = f"\"{self.ahk_exe_path}\" \"{script_path}\""
            stdout, stderr, return_code = self.execute_cmd(command, timeout=timeout)
            self.log_activity("autohotkey_executed", {
                "script_name": script_name,
                "return_code": return_code
            })
            if return_code == 0:
                return True, "Script exécuté avec succès"
            else:
                return False, f"Erreur: {stderr}"
        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution du script AutoHotkey: {str(e)}")
            return False, str(e)
    
    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite une commande reçue et retourne le résultat.
        Les types supportés sont 'cmd_execution' et 'autohotkey_script'.
        """
        cmd_type = command.get("type", "unknown")
        data = command.get("data", {})
        self.logger.info(f"Traitement de la commande: {cmd_type}")
        
        if cmd_type in ["cmd_execution", "cmd_execution_o1"]:
            cmd = data.get("command", "")
            working_dir = data.get("working_dir")
            timeout = data.get("timeout")
            stdout, stderr, return_code = self.execute_cmd(cmd, working_dir, timeout)
            return {
                "success": return_code == 0,
                "stdout": stdout,
                "stderr": stderr,
                "return_code": return_code
            }
        elif cmd_type in ["autohotkey_script", "autohotkey_script_o1"]:
            script_content = data.get("script_content", "")
            script_name = data.get("script_name")
            timeout = data.get("timeout")
            success, message = self.run_autohotkey_script(script_content, script_name, timeout)
            return {
                "success": success,
                "message": message
            }
        else:
            self.logger.warning(f"Commande inconnue: {cmd_type}")
            return {"success": False, "message": f"Commande non supportée: {cmd_type}"}
    
    def process_broadcast(self, message: Dict[str, Any]) -> None:
        """Traite les messages broadcast (ici, on se contente de les logger)."""
        self.logger.info(f"Broadcast reçu: {message.get('type', 'unknown')}")
    
    def log_activity(self, activity_type: str, details: Dict[str, Any]) -> None:
        """Enregistre une activité dans les logs."""
        self.logger.info(f"Activité [{activity_type}]: {details}")

if __name__ == "__main__":
    # Test en standalone
    agent = AutomationAgentMerged()
    agent.on_start()
    test_cmd = {
        "type": "cmd_execution",
        "data": {
            "command": "echo Bonjour depuis AutomationAgentMerged",
            "timeout": 5
        }
    }
    response = agent.process_command(test_cmd)
    print(response)
    agent.on_stop()
