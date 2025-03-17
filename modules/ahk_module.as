import os
import subprocess
import datetime
import json
import re
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional, Tuple

# Import de la couche d'abstraction pour l'exécution des scripts
from automation_executor import get_executor

# Répertoire de base pour ce module (dans alfred/modules)
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# Répertoires pour les scripts, templates et logs AHK
AHK_SCRIPTS_DIR = os.path.join(MODULE_DIR, "ahk_scripts")
AHK_TEMPLATES_DIR = os.path.join(MODULE_DIR, "ahk_templates")
AHK_LOGS_DIR = os.path.join(MODULE_DIR, "ahk_logs")

# Création des répertoires s'ils n'existent pas
for directory in [AHK_SCRIPTS_DIR, AHK_TEMPLATES_DIR, AHK_LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Configuration du logging avec RotatingFileHandler
log_file = os.path.join(AHK_LOGS_DIR, f"alfred_ahk_{datetime.datetime.now().strftime('%Y%m%d')}.log")
logger = logging.getLogger("Alfred-AHK")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
formatter = logging.Formatter("%(asctime)s [%(levelname)s] - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.addHandler(logging.StreamHandler())


# --- AHKTemplates ---
class AHKTemplates:
    """Gère les templates de scripts AutoHotkey."""
    TEMPLATES = {
        "hotkey": """
; Script AutoHotkey généré par Alfred
; Date: {date}
; Description: {description}

#SingleInstance Force
SetWorkingDir %A_ScriptDir%

{hotkey}::
    {action}
    return
""",
        "text_macro": """
; Script AutoHotkey généré par Alfred
; Date: {date}
; Description: {description}

#SingleInstance Force
SetWorkingDir %A_ScriptDir%

::{trigger}::
    SendInput {text}
    return
""",
        "window_automation": """
; Script AutoHotkey généré par Alfred
; Date: {date}
; Description: {description}

#SingleInstance Force
SetWorkingDir %A_ScriptDir%

{trigger_condition}
    WinActivate, {window_title}
    {actions}
    return
""",
        "translation_tool": """
; Script AutoHotkey généré par Alfred pour la traduction de texte
; Date: {date}
; Description: {description}

#SingleInstance Force
SetWorkingDir %A_ScriptDir%

{hotkey}::
    ClipSaved := ClipboardAll
    Clipboard := ""
    Send ^c
    ClipWait, 2
    if ErrorLevel {
        MsgBox, Aucun texte n'a été sélectionné.
        return
    }
    TextToTranslate := Clipboard
    Run, {translation_url}
    WinWaitActive, {translation_window_title}
    Sleep, 1000
    Send ^v
    Sleep, 500
    {additional_actions}
    Clipboard := ClipSaved
    ClipSaved := ""
    return
""",
        "custom": """
; Script AutoHotkey personnalisé généré par Alfred
; Date: {date}
; Description: {description}

#SingleInstance Force
SetWorkingDir %A_ScriptDir%

{script_content}
"""
    }
    
    @classmethod
    def get_template(cls, template_type: str) -> str:
        return cls.TEMPLATES.get(template_type, cls.TEMPLATES["custom"])
    
    @classmethod
    def save_custom_template(cls, name: str, content: str) -> bool:
        try:
            template_path = os.path.join(AHK_TEMPLATES_DIR, f"{name}.ahk")
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Template personnalisé sauvegardé : {name}")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du template '{name}' : {e}")
            return False
    
    @classmethod
    def load_custom_template(cls, name: str) -> Optional[str]:
        template_path = os.path.join(AHK_TEMPLATES_DIR, f"{name}.ahk")
        if os.path.exists(template_path):
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Erreur lors du chargement du template '{name}' : {e}")
        return None


# --- AHKScriptGenerator ---
class AHKScriptGenerator:
    """Génère des scripts AHK à partir de commandes textuelles."""
    
    # Compilation unique des regex utilisées pour analyser les commandes
    _HOTKEY_REGEX = re.compile(r"^hotkey\s+([^:]+):\s*(.*?)$")
    _TEXT_MACRO_REGEX = re.compile(r"^(?:texte|text)\s+macro\s+([^:]+)::\s*(.*?)$")
    _WINDOW_REGEX = re.compile(r"^(?:fen[êe]tre|window)\s+([^:]+):\s*(.*?)$")
    _TRANSLATION_REGEX = re.compile(r"^(?:traduction|translate)\s+([^:]+):\s*(.*?)$")
    _CUSTOM_REGEX = re.compile(r"^(?:personnalis[ée]|custom)\s+([^:]+):\s*(.*?)$")
    
    def __init__(self):
        self.script_catalog = self._load_script_catalog()
        self.catalog_dirty = False  # Indique si le catalogue a été modifié
    
    def _load_script_catalog(self) -> Dict:
        catalog_path = os.path.join(AHK_SCRIPTS_DIR, "catalog.json")
        if os.path.exists(catalog_path):
            try:
                with open(catalog_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Erreur lors du chargement du catalogue de scripts : {e}")
        return {"scripts": {}}
    
    def _save_script_catalog(self) -> bool:
        if not self.catalog_dirty:
            return True
        catalog_path = os.path.join(AHK_SCRIPTS_DIR, "catalog.json")
        try:
            with open(catalog_path, 'w', encoding='utf-8') as f:
                json.dump(self.script_catalog, f, indent=4)
            self.catalog_dirty = False
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du catalogue de scripts : {e}")
            return False
    
    def generate_script_from_command(self, command: str, description: str = "") -> Tuple[bool, str, str]:
        script_type, params = self._parse_command(command)
        if not script_type:
            return False, "", f"Impossible d'analyser la commande : {command}"
        script_name = self._generate_script_name(description or command)
        script_path = os.path.join(AHK_SCRIPTS_DIR, f"{script_name}.ahk")
        script_content = self._generate_script_content(script_type, params, description)
        if not script_content:
            return False, "", f"Échec de la génération du contenu pour le type : {script_type}"
        try:
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            self.script_catalog["scripts"][script_name] = {
                "path": script_path,
                "type": script_type,
                "description": description or command,
                "created": datetime.datetime.now().isoformat(),
                "params": params
            }
            self.catalog_dirty = True
            self._save_script_catalog()
            logger.info(f"Script AHK généré avec succès : {script_name}")
            return True, script_path, f"Script '{script_name}' généré avec succès."
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du script '{script_name}' : {e}")
            return False, "", f"Erreur lors de la sauvegarde du script : {e}"
    
    def _parse_command(self, command: str) -> Tuple[Optional[str], Dict]:
        command = command.strip().lower()
        params = {}
        match = self._HOTKEY_REGEX.match(command)
        if match:
            hotkey, action = match.groups()
            return "hotkey", {"hotkey": self._format_hotkey(hotkey), "action": action}
        match = self._TEXT_MACRO_REGEX.match(command)
        if match:
            trigger, text = match.groups()
            return "text_macro", {"trigger": trigger.strip(), "text": text}
        match = self._WINDOW_REGEX.match(command)
        if match:
            window, actions = match.groups()
            return "window_automation", {"window_title": window.strip(), "actions": self._parse_actions(actions), "trigger_condition": "#t::  ; Déclenché par Win+T"}
        match = self._TRANSLATION_REGEX.match(command)
        if match:
            hotkey, params_str = match.groups()
            translation_params = self._parse_translation_params(params_str)
            translation_params["hotkey"] = self._format_hotkey(hotkey)
            return "translation_tool", translation_params
        match = self._CUSTOM_REGEX.match(command)
        if match:
            name, content = match.groups()
            return "custom", {"name": name.strip(), "script_content": content}
        return "custom", {"script_content": command}
    
    def _format_hotkey(self, hotkey_str: str) -> str:
        replacements = {
            "ctrl": "^",
            "alt": "!",
            "shift": "+",
            "win": "#",
            "windows": "#",
            "super": "#",
            "espace": "Space",
            "space": "Space",
            "entrée": "Enter",
            "entree": "Enter",
            "enter": "Enter",
            "tab": "Tab",
            "tabulation": "Tab",
            "échap": "Escape",
            "echap": "Escape",
            "escape": "Escape",
            "flèche": "Arrow",
            "fleche": "Arrow"
        }
        hotkey = hotkey_str.strip().lower()
        for key, value in replacements.items():
            hotkey = re.sub(r'\b' + key + r'\b', value, hotkey)
        hotkey = hotkey.replace(" ", "")
        return hotkey
    
    def _parse_actions(self, actions_str: str) -> str:
        actions = actions_str.lower().strip()
        if "taper" in actions or "type" in actions:
            match = re.search(r"(?:taper|type)\s+[\"']?(.*?)[\"']?$", actions)
            if match:
                text = match.group(1)
                return f'SendInput {{{text}}}'
        elif "cliquer" in actions or "click" in actions:
            if "droit" in actions or "right" in actions:
                return "Click, right"
            elif "gauche" in actions or "left" in actions:
                return "Click"
            else:
                return "Click"
        elif "attendre" in actions or "wait" in actions:
            match = re.search(r"(?:attendre|wait)\s+(\d+)", actions)
            if match:
                ms = int(match.group(1)) * 1000
                return f"Sleep, {ms}"
        return f'SendInput {{{actions}}}'
    
    def _parse_translation_params(self, params_str: str) -> Dict:
        params = {
            "translation_url": "https://www.deepl.com/translator",
            "translation_window_title": "DeepL Translate",
            "additional_actions": "Sleep, 1000"
        }
        if "google" in params_str.lower():
            params["translation_url"] = "https://translate.google.com/"
            params["translation_window_title"] = "Google Translate"
        elif "bing" in params_str.lower():
            params["translation_url"] = "https://www.bing.com/translator"
            params["translation_window_title"] = "Bing Microsoft Translator"
        if "français" in params_str.lower() and "anglais" in params_str.lower():
            if "vers" in params_str.lower():
                if params_str.lower().index("français") < params_str.lower().index("vers"):
                    if "google" in params_str.lower():
                        params["additional_actions"] = """
                        Sleep, 1000
                        Click, 150 200
                        Sleep, 500
                        Send, français
                        Sleep, 500
                        Send, {Enter}
                        Sleep, 500
                        Click, 450 200
                        Sleep, 500
                        Send, anglais
                        Sleep, 500
                        Send, {Enter}
                        Sleep, 1000
                        """
                else:
                    if "google" in params_str.lower():
                        params["additional_actions"] = """
                        Sleep, 1000
                        Click, 150 200
                        Sleep, 500
                        Send, anglais
                        Sleep, 500
                        Send, {Enter}
                        Sleep, 500
                        Click, 450 200
                        Sleep, 500
                        Send, français
                        Sleep, 500
                        Send, {Enter}
                        Sleep, 1000
                        """
        return params
    
    def _generate_script_name(self, description: str) -> str:
        name_base = re.sub(r'[^a-zA-Z0-9_]', '_', description.lower())
        name_base = re.sub(r'_+', '_', name_base)[:30]
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{name_base}_{timestamp}"
    
    def _generate_script_content(self, script_type: str, params: Dict, description: str) -> Optional[str]:
        template = AHKTemplates.get_template(script_type)
        if not template:
            logger.error(f"Template introuvable pour le type : {script_type}")
            return None
        base_params = {
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "description": description
        }
        format_params = {**base_params, **params}
        try:
            return template.format(**format_params)
        except KeyError as e:
            logger.error(f"Paramètre manquant lors de la génération du script : {e}")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la génération du contenu du script : {e}")
            return None


# --- AHKScriptManager ---
class AHKScriptManager:
    """Gère l'exécution et le stockage des scripts AutoHotkey."""
    
    def __init__(self, ahk_executable_path: Optional[str] = None):
        self.ahk_executable = None  # Nous utilisons désormais l'exécuteur via get_executor()
        self.generator = AHKScriptGenerator()
        self.running_scripts = {}
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """Démarre un thread pour nettoyer périodiquement les processus terminés."""
        def cleanup():
            while True:
                time.sleep(10)
                to_remove = []
                for script, pid in self.running_scripts.items():
                    try:
                        proc = subprocess.Popen(["tasklist", "/FI", f"PID eq {pid}"], stdout=subprocess.PIPE, text=True)
                        output = proc.communicate()[0]
                        if str(pid) not in output:
                            to_remove.append(script)
                    except Exception as e:
                        logger.error(f"Erreur lors du nettoyage du PID {pid} : {e}")
                for script in to_remove:
                    logger.info(f"Nettoyage : Le script {script} n'est plus en cours d'exécution.")
                    del self.running_scripts[script]
        thread = threading.Thread(target=cleanup, daemon=True)
        thread.start()
    
    def generate_script(self, command_or_text: str, description: str = "") -> Tuple[bool, str, str]:
        return self.generator.generate_script_from_command(command_or_text, description)
    
    def execute_script(self, script_path: str) -> Tuple[bool, str]:
        if not os.path.exists(script_path):
            return False, f"Script introuvable : {script_path}"
        try:
            # Utilisation de la couche d'exécution adaptée (Windows ou Linux)
            executor = get_executor()
            success, message = executor.execute_script(script_path)
            if success:
                script_name = os.path.basename(script_path)
                self.running_scripts[script_name] = message.split("PID: ")[-1].strip(").")
            return success, message
        except Exception as e:
            logger.error(f"Erreur lors de l'exécution du script '{script_path}' : {e}")
            return False, f"Erreur lors de l'exécution du script : {e}"
    
    def stop_script(self, script_name_or_path: str) -> Tuple[bool, str]:
        script_name = os.path.basename(script_name_or_path)
        if script_name in self.running_scripts:
            pid = self.running_scripts[script_name]
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
                del self.running_scripts[script_name]
                logger.info(f"Script AHK arrêté : {script_name} (PID: {pid})")
                return True, f"Script '{script_name}' arrêté avec succès."
            except Exception as e:
                logger.error(f"Erreur lors de l'arrêt du script '{script_name}' : {e}")
                return False, f"Erreur lors de l'arrêt du script : {e}"
        else:
            return False, f"Script '{script_name}' non trouvé dans la liste des scripts en cours d'exécution."
    
    def get_script_list(self) -> List[Dict]:
        scripts = []
        for name, info in self.generator.script_catalog.get("scripts", {}).items():
            script_path = info.get("path", "")
            if os.path.exists(script_path):
                scripts.append({
                    "name": name,
                    "path": script_path,
                    "type": info.get("type", "unknown"),
                    "description": info.get("description", ""),
                    "created": info.get("created", ""),
                    "is_running": name in self.running_scripts
                })
        return scripts
    
    def get_script_by_name_or_description(self, query: str) -> Optional[Dict]:
        query = query.lower()
        for name, info in self.generator.script_catalog.get("scripts", {}).items():
            if query in name.lower() or query in info.get("description", "").lower():
                script_path = info.get("path", "")
                if os.path.exists(script_path):
                    return {
                        "name": name,
                        "path": script_path,
                        "type": info.get("type", "unknown"),
                        "description": info.get("description", ""),
                        "created": info.get("created", ""),
                        "is_running": name in self.running_scripts
                    }
        return None


# --- AlfredAHKModule ---
class AlfredAHKModule:
    """Interface principale pour intégrer AutoHotkey dans Alfred."""
    
    def __init__(self, ahk_executable_path: Optional[str] = None):
        logger.info("Initialisation du module AutoHotkey d'Alfred...")
        self.script_manager = AHKScriptManager(ahk_executable_path)
    
    def get_scripts(self) -> List[Dict]:
        return self.script_manager.get_script_list()
    
    def search_script(self, query: str) -> Optional[Dict]:
        return self.script_manager.get_script_by_name_or_description(query)
    
    def execute_script(self, script_name_or_path: str) -> Dict:
        if os.path.exists(script_name_or_path):
            script_path = script_name_or_path
        else:
            script_info = self.script_manager.get_script_by_name_or_description(script_name_or_path)
            if script_info:
                script_path = script_info["path"]
            else:
                return {"success": False, "action": "execute", "message": f"Script '{script_name_or_path}' introuvable."}
        success, message = self.script_manager.execute_script(script_path)
        return {
            "success": success,
            "action": "execute",
            "script_path": script_path,
            "script_name": os.path.basename(script_path),
            "message": message
        }
    
    def stop_script(self, script_name_or_path: str) -> Dict:
        success, message = self.script_manager.stop_script(script_name_or_path)
        return {
            "success": success,
            "action": "stop",
            "script_name": os.path.basename(script_name_or_path),
            "message": message
        }
    
    def process_command(self, command: str, description: str = "") -> Dict:
        existing_script = self.script_manager.get_script_by_name_or_description(command)
        if existing_script and "exécute" in command.lower():
            success, message = self.script_manager.execute_script(existing_script["path"])
            return {
                "success": success,
                "action": "execute",
                "script_name": existing_script["name"],
                "script_path": existing_script["path"],
                "message": message
            }
        else:
            success, script_path, message = self.script_manager.generate_script(command, description)
            if success:
                exec_success, exec_message = self.script_manager.execute_script(script_path)
                return {
                    "success": success,
                    "action": "generate_and_execute",
                    "script_path": script_path,
                    "script_name": os.path.basename(script_path),
                    "execution_success": exec_success,
                    "execution_message": exec_message,
                    "message": message
                }
            else:
                return {
                    "success": False,
                    "action": "generate",
                    "message": message
                }

def run():
    """
    Fonction principale appelée par Alfred pour exécuter le module AutoHotkey.
    Propose un menu interactif pour générer, lister et exécuter des scripts AHK.
    """
    logger.info("Exécution du module AutoHotkey d'Alfred.")
    ahk_module = AlfredAHKModule()
    
    while True:
        print("\n--- Module AutoHotkey d'Alfred ---")
        print("1. Générer et exécuter un script à partir d'une commande")
        print("2. Lister les scripts générés")
        print("3. Arrêter un script en cours")
        print("4. Quitter")
        choice = input("Choisissez une option : ")
        
        if choice == "1":
            command = input("Entrez la commande ou description du script AHK : ")
            description = input("Entrez une description (optionnel) : ")
            result = ahk_module.process_command(command, description)
            print(result["message"])
        elif choice == "2":
            scripts = ahk_module.get_scripts()
            if not scripts:
                print("Aucun script généré.")
            else:
                for script in scripts:
                    running = " (en cours)" if script.get("is_running") else ""
                    print(f"- {script['name']}{running}: {script['description']}")
        elif choice == "3":
            script_name = input("Entrez le nom ou chemin du script à arrêter : ")
            result = ahk_module.stop_script(script_name)
            print(result["message"])
        elif choice == "4":
            print("Fin du module AutoHotkey.")
            break
        else:
            print("Option invalide. Veuillez réessayer.")

if __name__ == "__main__":
    run()
