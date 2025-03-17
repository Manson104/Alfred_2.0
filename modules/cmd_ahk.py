import subprocess
import logging
import os

# Liste des commandes interdites pour des raisons de sécurité
BLACKLISTED_COMMANDS = ["shutdown", "del", "rd", "rmdir", "format", "erase", "remove", "rm"]

def is_command_dangerous(command):
    """
    Vérifie si la commande contient un mot-clé dangereux.
    La vérification se fait de manière simple, en comparant en minuscule.
    """
    cmd_lower = command.lower()
    for dangerous in BLACKLISTED_COMMANDS:
        if dangerous in cmd_lower:
            return True
    return False

def execute_command(command):
    """
    Exécute une commande CMD ou un script AutoHotkey.
    Si la commande se termine par '.ahk', on suppose qu'il s'agit d'un script AutoHotkey,
    sinon on l'exécute via CMD.
    Avant exécution, on vérifie que la commande n'est pas dangereuse.
    """
    command = command.strip()
    if not command:
        return

    if is_command_dangerous(command):
        logging.warning(f"Commande bloquée pour des raisons de sécurité : {command}")
        return

    # Si c'est un script AutoHotkey
    if command.endswith('.ahk'):
        # On suppose que AutoHotkey.exe est dans le PATH ; sinon, il faudra préciser son chemin complet.
        try:
            result = subprocess.run(["AutoHotkey.exe", command], capture_output=True, text=True, shell=False)
            logging.info(f"Exécution du script AHK '{command}' terminée. Retour : {result.stdout}")
        except Exception as e:
            logging.error(f"Erreur lors de l'exécution du script AHK '{command}': {e}")
    else:
        # Exécution d'une commande CMD classique
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            logging.info(f"Commande exécutée : {command}")
            logging.info(f"Sortie : {result.stdout}")
            if result.stderr:
                logging.error(f"Erreur : {result.stderr}")
        except Exception as e:
            logging.error(f"Erreur lors de l'exécution de la commande '{command}': {e}")

def execute_batch(commands):
    """
    Exécute une séquence de commandes (données dans une liste).
    Chaque commande est traitée individuellement.
    """
    for cmd in commands:
        execute_command(cmd)

def run():
    """
    Fonction principale appelée par Alfred pour exécuter le module CMD et AutoHotkey.
    L'utilisateur peut saisir une ou plusieurs commandes séparées par un point-virgule.
    """
    logging.info("Exécution du module CMD et AutoHotkey.")
    
    user_input = input("Entrez une commande CMD ou le chemin d'un script AHK (pour plusieurs commandes, séparez-les par ';'):\n")
    # Séparation des commandes par ';'
    commands = [cmd.strip() for cmd in user_input.split(';') if cmd.strip()]
    
    if not commands:
        logging.info("Aucune commande fournie.")
        return
    
    execute_batch(commands)
    logging.info("Fin de l'exécution des commandes.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    run()
