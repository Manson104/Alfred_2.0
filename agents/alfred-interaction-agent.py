"""
alfred-interaction-agent.py
---------------------------
Agent d'interaction pour Alfred, offrant deux modes de communication :
- Mode "Majordome" (formel)
- Mode "Familier" (décontracté)

Ce module gère également la planification proactive des tâches et l'anticipation des besoins.
À placer dans le dossier 'alfred/agents/' de ton projet Alfred.
"""

import os
import time
import datetime
import threading
import logging
import json
from enum import Enum

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("alfred_interaction.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("InteractionAgent")

# ----- Définition des Modes d'Interaction -----
class InteractionMode(Enum):
    MAJORDOME = "majordome"
    FAMILIER = "familier"

# ----- Classe Task pour la planification des tâches -----
class Task:
    def __init__(self, task_id, description, execution_time, action, parameters=None, recurring=False, interval=None):
        """
        Initialise une nouvelle tâche.

        Args:
            task_id (str): Identifiant unique de la tâche.
            description (str): Description de la tâche.
            execution_time (datetime): Moment d'exécution de la tâche.
            action (callable): Fonction à exécuter.
            parameters (dict, optional): Paramètres pour l'action.
            recurring (bool, optional): Si la tâche est récurrente.
            interval (int, optional): Intervalle en secondes pour les tâches récurrentes.
        """
        self.task_id = task_id
        self.description = description
        self.execution_time = execution_time
        self.action = action
        self.parameters = parameters or {}
        self.recurring = recurring
        self.interval = interval
        self.completed = False

    def is_due(self):
        """Vérifie si la tâche doit être exécutée maintenant."""
        return datetime.datetime.now() >= self.execution_time and not self.completed

    def execute(self):
        """Exécute la tâche."""
        try:
            logger.info(f"Exécution de la tâche : {self.description}")
            self.action(**self.parameters)
            self.completed = True
            if self.recurring and self.interval:
                self.execution_time = datetime.datetime.now() + datetime.timedelta(seconds=self.interval)
                self.completed = False
                logger.info(f"Tâche récurrente reprogrammée pour : {self.execution_time}")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'exécution de la tâche {self.task_id} : {str(e)}")
            return False

    def to_dict(self):
        """Convertit la tâche en dictionnaire pour la sérialisation."""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "execution_time": self.execution_time.isoformat(),
            "recurring": self.recurring,
            "interval": self.interval,
            "completed": self.completed
        }

    @classmethod
    def from_dict(cls, data, action_registry):
        """Crée une tâche à partir d'un dictionnaire sérialisé."""
        task = cls(
            task_id=data["task_id"],
            description=data["description"],
            execution_time=datetime.datetime.fromisoformat(data["execution_time"]),
            action=action_registry.get(data["task_id"]),
            recurring=data.get("recurring", False),
            interval=data.get("interval", None)
        )
        task.completed = data.get("completed", False)
        return task

# ----- Classe InteractionAgent -----
class InteractionAgent:
    def __init__(self, default_mode=InteractionMode.MAJORDOME):
        """
        Initialise l'agent d'interaction.

        Args:
            default_mode (InteractionMode): Mode d'interaction par défaut.
        """
        self.current_mode = default_mode
        self.tasks = {}  # Dictionnaire de tâches indexées par leur ID
        self.action_registry = {}  # Registre des actions pour la planification
        self.stop_event = threading.Event()
        self.task_thread = None

        # Modèles de réponses pour chaque mode
        self.response_templates = {
            InteractionMode.MAJORDOME: {
                "greeting_morning": "Bonjour Monsieur/Madame. J'espère que vous avez passé une agréable nuit. Que puis-je faire pour vous assister ce matin ?",
                "greeting_afternoon": "Bonjour Monsieur/Madame. Puis-je vous être d'une quelconque assistance cet après-midi ?",
                "greeting_evening": "Bonsoir Monsieur/Madame. Permettez-moi de vous souhaiter une excellente soirée. En quoi puis-je vous être utile ?",
                "task_confirmation": "Bien entendu, je vais m'occuper de {task} immédiatement.",
                "task_completed": "J'ai le plaisir de vous informer que la tâche {task} a été accomplie avec succès.",
                "task_scheduled": "J'ai pris la liberté de planifier {task} pour {time}, comme vous me l'avez demandé.",
                "suggestion": "Si je puis me permettre, il serait peut-être opportun de {suggestion}.",
                "farewell": "Je vous souhaite une excellente journée. N'hésitez pas à me solliciter si vous avez besoin de quoi que ce soit."
            },
            InteractionMode.FAMILIER: {
                "greeting_morning": "Salut ! Bien dormi ? Qu'est-ce que je peux faire pour toi ce matin ?",
                "greeting_afternoon": "Hey ! Comment se passe ta journée ? Je peux t'aider ?",
                "greeting_evening": "Bonsoir ! Prêt pour la soirée ? Besoin d'un coup de main ?",
                "task_confirmation": "OK, je m'en charge direct pour {task} !",
                "task_completed": "Super, j'ai terminé avec {task} !",
                "task_scheduled": "C'est noté ! J'ai programmé {task} pour {time}.",
                "suggestion": "Dis, tu devrais peut-être {suggestion}, non ?",
                "farewell": "À plus tard ! N'hésite pas si tu as besoin de quelque chose !"
            }
        }

        # Charger les tâches sauvegardées (depuis alfred_tasks.json)
        self.load_tasks()
        # Configurer les actions proactives et planifier les tâches récurrentes
        self._setup_proactive_actions()

    def _setup_proactive_actions(self):
        """Configure les actions proactives basées sur le contexte."""
        self.register_action("lunch_suggestion", self.suggest_lunch)
        self.register_action("dinner_suggestion", self.suggest_dinner)
        self.register_action("remind_break", self.remind_break)
        self.register_action("morning_briefing", self.morning_briefing)
        self.register_action("evening_summary", self.evening_summary)
        self._schedule_anticipation_tasks()

    def _schedule_anticipation_tasks(self):
        """Planifie des tâches d'anticipation selon l'heure de la journée."""
        now = datetime.datetime.now()
        lunch_time = datetime.datetime(now.year, now.month, now.day, 11, 30)
        if now > lunch_time:
            lunch_time += datetime.timedelta(days=1)
        dinner_time = datetime.datetime(now.year, now.month, now.day, 18, 30)
        if now > dinner_time:
            dinner_time += datetime.timedelta(days=1)
        morning_time = datetime.datetime(now.year, now.month, now.day, 8, 0)
        if now > morning_time:
            morning_time += datetime.timedelta(days=1)
        evening_time = datetime.datetime(now.year, now.month, now.day, 21, 0)
        if now > evening_time:
            evening_time += datetime.timedelta(days=1)
        
        self.add_task(
            "lunch_suggestion",
            "Suggérer l'heure du déjeuner",
            lunch_time,
            self.suggest_lunch,
            recurring=True,
            interval=86400
        )
        self.add_task(
            "dinner_suggestion",
            "Suggérer l'heure du dîner",
            dinner_time,
            self.suggest_dinner,
            recurring=True,
            interval=86400
        )
        self.add_task(
            "morning_briefing",
            "Briefing matinal",
            morning_time,
            self.morning_briefing,
            recurring=True,
            interval=86400
        )
        self.add_task(
            "evening_summary",
            "Résumé de la journée",
            evening_time,
            self.evening_summary,
            recurring=True,
            interval=86400
        )
        # Rappel de pause toutes les 2 heures pendant la journée
        work_start = 9
        work_end = 18
        for hour in range(work_start, work_end, 2):
            break_time = datetime.datetime(now.year, now.month, now.day, hour, 0)
            if now > break_time:
                break_time += datetime.timedelta(days=1)
            self.add_task(
                f"break_reminder_{hour}",
                f"Rappel de pause à {hour}h",
                break_time,
                self.remind_break,
                recurring=True,
                interval=86400
            )

    def register_action(self, action_id, action_func):
        """
        Enregistre une fonction d'action dans le registre.
        
        Args:
            action_id (str): Identifiant de l'action.
            action_func (callable): Fonction à exécuter.
        """
        self.action_registry[action_id] = action_func

    def set_mode(self, mode):
        """
        Change le mode d'interaction actuel.

        Args:
            mode (InteractionMode or str): Nouveau mode d'interaction.

        Returns:
            str: Message de confirmation.
        """
        if not isinstance(mode, InteractionMode):
            try:
                mode = InteractionMode(mode.lower())
            except Exception:
                return f"Mode non reconnu. Les modes disponibles sont : {[m.value for m in InteractionMode]}"
        self.current_mode = mode
        if mode == InteractionMode.MAJORDOME:
            return "Je suis désormais à votre service en mode Majordome, Monsieur/Madame."
        else:
            return "Cool, je passe en mode familier ! Comment je peux t'aider ?"

    def get_response(self, template_key, **kwargs):
        """
        Génère une réponse formatée selon le mode d'interaction actuel.
        
        Args:
            template_key (str): Clé du modèle de réponse.
            **kwargs: Variables à insérer dans le modèle.
        
        Returns:
            str: Réponse générée.
        """
        template = self.response_templates[self.current_mode].get(template_key, "")
        return template.format(**kwargs)

    def get_greeting(self):
        """Retourne une salutation adaptée en fonction de l'heure."""
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12:
            return self.get_response("greeting_morning")
        elif 12 <= hour < 18:
            return self.get_response("greeting_afternoon")
        else:
            return self.get_response("greeting_evening")

    def respond_to(self, query):
        """
        Génère une réponse à une requête utilisateur.
        
        Args:
            query (str): Requête de l'utilisateur.
        
        Returns:
            str: Réponse appropriée.
        """
        query = query.lower()
        if any(greet in query for greet in ["bonjour", "salut", "hello", "coucou"]):
            return self.get_greeting()
        if "au revoir" in query or "à plus" in query:
            return self.get_response("farewell")
        if "réunion" in query and any(word in query for word in ["organiser", "planifier", "programmer"]):
            return self.get_response("task_confirmation", task="l'organisation de cette réunion")
        # Réponse par défaut
        if self.current_mode == InteractionMode.MAJORDOME:
            return "Je vous prie de m'excuser, mais je n'ai pas bien saisi votre demande. Pourriez-vous la reformuler, s'il vous plaît ?"
        else:
            return "Désolé, je n'ai pas bien compris. Tu peux reformuler ?"

    def add_task(self, task_id, description, execution_time, action, parameters=None, recurring=False, interval=None):
        """
        Ajoute une tâche planifiée.

        Args:
            task_id (str): Identifiant unique de la tâche.
            description (str): Description de la tâche.
            execution_time (datetime): Heure d'exécution.
            action (callable): Fonction à exécuter.
            parameters (dict, optional): Paramètres pour l'action.
            recurring (bool, optional): Tâche récurrente.
            interval (int, optional): Intervalle en secondes.
        
        Returns:
            str: Message de confirmation.
        """
        if task_id in self.tasks:
            logger.warning(f"Une tâche avec l'ID {task_id} existe déjà. Mise à jour de la tâche.")
        self.register_action(task_id, action)
        task = Task(task_id, description, execution_time, action, parameters, recurring, interval)
        self.tasks[task_id] = task
        self.save_tasks()
        formatted_time = execution_time.strftime("%H:%M le %d/%m/%Y")
        logger.info(f"Tâche ajoutée : {description} prévue pour {formatted_time}")
        return self.get_response("task_scheduled", task=description, time=formatted_time)

    def remove_task(self, task_id):
        """
        Supprime une tâche planifiée.

        Args:
            task_id (str): Identifiant de la tâche.
        
        Returns:
            bool: True si supprimée, False sinon.
        """
        if task_id not in self.tasks:
            logger.warning(f"Tâche {task_id} inexistante.")
            return False
        del self.tasks[task_id]
        self.save_tasks()
        logger.info(f"Tâche {task_id} supprimée.")
        return True

    def start_task_manager(self):
        """Démarre le gestionnaire de tâches en arrière-plan."""
        if self.task_thread and self.task_thread.is_alive():
            logger.warning("Gestionnaire de tâches déjà actif.")
            return
        self.stop_event.clear()
        self.task_thread = threading.Thread(target=self._task_manager_loop, daemon=True)
        self.task_thread.start()
        logger.info("Gestionnaire de tâches démarré.")

    def stop_task_manager(self):
        """Arrête le gestionnaire de tâches."""
        if not self.task_thread or not self.task_thread.is_alive():
            logger.warning("Aucun gestionnaire de tâches actif.")
            return
        self.stop_event.set()
        self.task_thread.join(timeout=5)
        logger.info("Gestionnaire de tâches arrêté.")

    def _task_manager_loop(self):
        """Boucle principale du gestionnaire de tâches."""
        logger.info("Démarrage de la boucle des tâches.")
        while not self.stop_event.is_set():
            try:
                tasks_to_run = [task for task in self.tasks.values() if task.is_due()]
                for task in tasks_to_run:
                    task.execute()
                if tasks_to_run:
                    self.save_tasks()
                time.sleep(1)
            except Exception as e:
                logger.error(f"Erreur dans le gestionnaire de tâches : {str(e)}")
                time.sleep(5)

    def load_tasks(self):
        """Charge les tâches sauvegardées depuis 'alfred_tasks.json'."""
        tasks_file = "alfred_tasks.json"
        if not os.path.exists(tasks_file):
            logger.info("Aucun fichier de tâches trouvé, démarrage avec liste vide.")
            return
        try:
            with open(tasks_file, 'r', encoding='utf-8') as f:
                tasks_data = json.load(f)
            self.tasks = {}
            for data in tasks_data:
                task = Task.from_dict(data, self.action_registry)
                self.tasks[task.task_id] = task
            logger.info(f"{len(self.tasks)} tâches chargées depuis {tasks_file}")
        except Exception as e:
            logger.error(f"Erreur lors du chargement des tâches : {str(e)}")

    def save_tasks(self):
        """Sauvegarde les tâches dans 'alfred_tasks.json'."""
        tasks_file = "alfred_tasks.json"
        try:
            tasks_data = [task.to_dict() for task in self.tasks.values()]
            with open(tasks_file, 'w', encoding='utf-8') as f:
                json.dump(tasks_data, f, ensure_ascii=False, indent=2)
            logger.info(f"{len(self.tasks)} tâches sauvegardées dans {tasks_file}")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des tâches : {str(e)}")

    # ----- Fonctions proactives -----
    def suggest_lunch(self, **kwargs):
        suggestion = "prendre une pause déjeuner"
        message = self.get_response("suggestion", suggestion=suggestion)
        logger.info(f"Suggestion déjeuner : {message}")
        return message

    def suggest_dinner(self, **kwargs):
        suggestion = "commencer à préparer le dîner"
        message = self.get_response("suggestion", suggestion=suggestion)
        logger.info(f"Suggestion dîner : {message}")
        return message

    def remind_break(self, **kwargs):
        suggestion = "faire une courte pause pour vous détendre et vous étirer"
        message = self.get_response("suggestion", suggestion=suggestion)
        logger.info(f"Rappel pause : {message}")
        return message

    def morning_briefing(self, **kwargs):
        if self.current_mode == InteractionMode.MAJORDOME:
            message = ("Bonjour Monsieur/Madame. Voici votre briefing matinal : vous avez plusieurs rendez-vous aujourd'hui. "
                       "Souhaitez-vous que je vous les détaille ?")
        else:
            message = "Salut ! Voici ton briefing du matin. Tu as quelques trucs importants aujourd'hui. On y va ?"
        logger.info("Briefing matinal fourni.")
        return message

    def evening_summary(self, **kwargs):
        if self.current_mode == InteractionMode.MAJORDOME:
            message = ("Bonsoir Monsieur/Madame. Voici le résumé de votre journée. Vous avez accompli plusieurs tâches importantes. "
                       "Souhaitez-vous que je vous prépare le planning de demain ?")
        else:
            message = "Hey ! Voilà un petit résumé de ta journée. Plutôt cool, non ?"
        logger.info("Résumé de soirée fourni.")
        return message

# ----- Exemple d'utilisation -----
if __name__ == "__main__":
    agent = InteractionAgent(default_mode=InteractionMode.MAJORDOME)
    agent.start_task_manager()
    print("Agent démarré. Tapez 'exit' pour quitter.")
    print(agent.get_greeting())
    try:
        while True:
            user_input = input("> ")
            if user_input.lower() == "exit":
                break
            if user_input.lower() in ["mode majordome", "mode familier"]:
                new_mode = user_input.lower().split()[1]
                print(agent.set_mode(new_mode))
                continue
            response = agent.respond_to(user_input)
            print(response)
    except KeyboardInterrupt:
        pass
    finally:
        agent.stop_task_manager()
        print("Agent arrêté.")
