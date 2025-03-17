import platform
import subprocess
import logging
from typing import Tuple

logger = logging.getLogger("AutomationExecutor")
logger.setLevel(logging.INFO)

class AutomationExecutor:
    def execute_script(self, script_path: str) -> Tuple[bool, str]:
        raise NotImplementedError("Cette méthode doit être implémentée par une sous-classe.")

class WindowsAutomationExecutor(AutomationExecutor):
    def execute_script(self, script_path: str) -> Tuple[bool, str]:
        try:
            process = subprocess.Popen(["AutoHotkey.exe", script_path])
            return True, f"Script lancé avec AutoHotkey (PID: {process.pid})"
        except Exception as e:
            logger.error(f"Erreur d'exécution du script sous Windows: {e}")
            return False, f"Erreur d'exécution du script sous Windows: {e}"

class LinuxAutomationExecutor(AutomationExecutor):
    def execute_script(self, script_path: str) -> Tuple[bool, str]:
        try:
            # Ici, nous utilisons "autokey-run" comme exemple.
            # Adapte cette commande selon la solution d'automatisation choisie sur Linux (AutoKey, PyAutoGUI, etc.)
            process = subprocess.Popen(["autokey-run", script_path])
            return True, f"Script lancé avec AutoKey (PID: {process.pid})"
        except Exception as e:
            logger.error(f"Erreur d'exécution du script sous Linux: {e}")
            return False, f"Erreur d'exécution du script sous Linux: {e}"

def get_executor() -> AutomationExecutor:
    system = platform.system()
    if system == "Windows":
        logger.info("Détection de Windows : utilisation de WindowsAutomationExecutor")
        return WindowsAutomationExecutor()
    else:
        logger.info(f"Détection de {system} : utilisation de LinuxAutomationExecutor")
        return LinuxAutomationExecutor()

if __name__ == "__main__":
    # Exemple d'utilisation :
    executor = get_executor()
    # Remplacez ce chemin par celui d'un script réel pour tester
    script_path = "chemin/vers/votre_script.ahk"
    success, message = executor.execute_script(script_path)
    print(message)
