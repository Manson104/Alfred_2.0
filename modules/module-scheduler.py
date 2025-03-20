            return None
    
    def add_task(self, task_config: Dict[str, Any]) -> str:
        """
        Ajoute une nouvelle tâche planifiée.
        
        Args:
            task_config: Configuration de la tâche
            
        Returns:
            str: Identifiant de la tâche ajoutée
        """
        with self._lock:
            # Générer un nouvel identifiant
            task_id = f"task_{int(time.time())}_{len(self._tasks)}"
            
            # Créer la configuration de la tâche
            self._tasks[task_id] = {
                "id": task_id,
                "enabled": task_config.get("enabled", True),
                "schedule_type": task_config.get("schedule_type", self.ONCE),
                "time": task_config.get("time"),
                "days": task_config.get("days"),
                "date": task_config.get("date"),
                "interval": task_config.get("interval"),
                "offset": task_config.get("offset", 0),
                "conditions": task_config.get("conditions", []),
                "actions": task_config.get("actions", []),
                "last_run": 0,
                "next_run": 0  # Sera calculé
            }
            
            # Calculer la prochaine exécution
            self._recalculate_next_run(task_id)
            
            # Mettre à jour la file d'attente
            if self._tasks[task_id]["next_run"] < float('inf'):
                heapq.heappush(self._task_queue, (self._tasks[task_id]["next_run"], task_id))
            
            # Sauvegarder l'état
            self._save_state()
            
            return task_id
    
    def remove_task(self, task_id: str) -> bool:
        """
        Supprime une tâche planifiée.
        
        Args:
            task_id: Identifiant de la tâche
            
        Returns:
            bool: True si supprimé avec succès, False sinon
        """
        with self._lock:
            if task_id not in self._tasks:
                return False
                
            # Supprimer la tâche
            del self._tasks[task_id]
            
            # Reconstruire la file d'attente
            self._update_task_queue()
            
            # Supprimer des dernières exécutions
            if task_id in self._last_run_times:
                del self._last_run_times[task_id]
            
            # Sauvegarder l'état
            self._save_state()
            
            return True
    
    def update_task(self, task_id: str, task_config: Dict[str, Any]) -> bool:
        """
        Met à jour une tâche planifiée.
        
        Args:
            task_id: Identifiant de la tâche
            task_config: Nouvelle configuration
            
        Returns:
            bool: True si mis à jour avec succès, False sinon
        """
        with self._lock:
            if task_id not in self._tasks:
                return False
                
            task = self._tasks[task_id]
            
            # Mettre à jour les paramètres
            if "enabled" in task_config:
                task["enabled"] = task_config["enabled"]
                
            if "schedule_type" in task_config:
                task["schedule_type"] = task_config["schedule_type"]
                
            if "time" in task_config:
                task["time"] = task_config["time"]
                
            if "days" in task_config:
                task["days"] = task_config["days"]
                
            if "date" in task_config:
                task["date"] = task_config["date"]
                
            if "interval" in task_config:
                task["interval"] = task_config["interval"]
                
            if "offset" in task_config:
                task["offset"] = task_config["offset"]
                
            if "conditions" in task_config:
                task["conditions"] = task_config["conditions"]
                
            if "actions" in task_config:
                task["actions"] = task_config["actions"]
            
            # Recalculer la prochaine exécution
            self._recalculate_next_run(task_id)
            
            # Mettre à jour la file d'attente
            self._update_task_queue()
            
            # Sauvegarder l'état
            self._save_state()
            
            return True
    
    def get_task(self, task_id: str) -> Dict[str, Any]:
        """
        Récupère les détails d'une tâche planifiée.
        
        Args:
            task_id: Identifiant de la tâche
            
        Returns:
            Dict: Détails de la tâche, ou None si non trouvée
        """
        return self._tasks.get(task_id)
    
    def list_tasks(self) -> Dict[str, Dict[str, Any]]:
        """
        Liste toutes les tâches planifiées.
        
        Returns:
            Dict: Dictionnaire des tâches
        """
        return self._tasks
    
    def run_task_now(self, task_id: str) -> bool:
        """
        Exécute immédiatement une tâche planifiée.
        
        Args:
            task_id: Identifiant de la tâche
            
        Returns:
            bool: True si exécuté avec succès, False sinon
        """
        if task_id not in self._tasks:
            return False
            
        # Exécuter la tâche
        self._execute_task(task_id)
        
        # Mettre à jour le temps d'exécution
        now = time.time()
        self._tasks[task_id]["last_run"] = now
        self._last_run_times[task_id] = now
        
        # Recalculer la prochaine exécution
        self._recalculate_next_run(task_id)
        
        # Mettre à jour la file d'attente
        self._update_task_queue()
        
        # Sauvegarder l'état
        self._save_state()
        
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """
        Récupère le statut du module de planification.
        
        Returns:
            Dict: Statut du module
        """
        with self._lock:
            # Compter les tâches actives
            active_tasks = len([task_id for task_id, task in self._tasks.items() if task.get("enabled", True)])
            
            # Trouver la prochaine tâche à exécuter
            next_task = None
            next_time = float('inf')
            
            if self._task_queue:
                next_time, next_task_id = self._task_queue[0]
                next_task = self._tasks.get(next_task_id)
            
            return {
                "total_tasks": len(self._tasks),
                "active_tasks": active_tasks,
                "next_task": next_task["id"] if next_task else None,
                "next_time": next_time,
                "sun_times": self._sun_times
            }
    
    # Gestionnaires de messages
    
    def _handle_add_task(self, message: Dict[str, Any]):
        """Gère les demandes d'ajout de tâche."""
        task_config = message.get("task")
        
        if not task_config:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_task_config"
                })
            return
        
        task_id = self.add_task(task_config)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "task_id": task_id
            })
    
    def _handle_remove_task(self, message: Dict[str, Any]):
        """Gère les demandes de suppression de tâche."""
        task_id = message.get("task_id")
        
        if not task_id:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_task_id"
                })
            return
        
        success = self.remove_task(task_id)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": success,
                "task_id": task_id
            })
    
    def _handle_update_task(self, message: Dict[str, Any]):
        """Gère les demandes de mise à jour de tâche."""
        task_id = message.get("task_id")
        task_config = message.get("task")
        
        if not task_id or not task_config:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_parameters"
                })
            return
        
        success = self.update_task(task_id, task_config)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": success,
                "task_id": task_id
            })
    
    def _handle_status_request(self, message: Dict[str, Any]):
        """Gère les demandes de statut."""
        status = self.get_status()
        
        # Répondre avec le statut
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], status)
    
    def _handle_list_tasks(self, message: Dict[str, Any]):
        """Gère les demandes de liste des tâches."""
        tasks = self.list_tasks()
        
        # Répondre avec la liste des tâches
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "tasks": tasks
            })
    
    def _handle_run_now(self, message: Dict[str, Any]):
        """Gère les demandes d'exécution immédiate."""
        task_id = message.get("task_id")
        
        if not task_id:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_task_id"
                })
            return
        
        success = self.run_task_now(task_id)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": success,
                "task_id": task_id
            })
    
    def _handle_sun_times_update(self, message: Dict[str, Any]):
        """Gère les mises à jour des heures de lever/coucher du soleil."""
        sunrise = message.get("sunrise")
        sunset = message.get("sunset")
        
        if sunrise:
            self._sun_times["sunrise"] = sunrise
            
        if sunset:
            self._sun_times["sunset"] = sunset
            
        # Recalculer les prochaines exécutions des tâches basées sur le soleil
        with self._lock:
            for task_id, task in self._tasks.items():
                if task.get("schedule_type") in [self.SUNRISE, self.SUNSET]:
                    self._recalculate_next_run(task_id)
            
            # Mettre à jour la file d'attente
            self._update_task_queue()


# Exemple de configuration pour les tests
SAMPLE_CONFIG = {
    "schedules": {
        "morning_lights": {
            "type": "daily",
            "time": "07:00",
            "enabled": True,
            "actions": [
                {
                    "type": "scene",
                    "scene_id": "morning"
                },
                {
                    "type": "notification",
                    "user_id": "user1",
                    "message": "Bonjour ! Il est l'heure de se lever.",
                    "title": "Réveil"
                }
            ]
        },
        "evening_lights": {
            "type": "sunset",
            "offset": -30,  # 30 minutes avant le coucher du soleil
            "enabled": True,
            "actions": [
                {
                    "type": "scene",
                    "scene_id": "evening"
                }
            ]
        },
        "night_security": {
            "type": "daily",
            "time": "23:00",
            "enabled": True,
            "actions": [
                {
                    "type": "security",
                    "action": "arm_home",
                    "code": "1234"
                },
                {
                    "type": "scene",
                    "scene_id": "night"
                }
            ]
        },
        "weekend_watering": {
            "type": "weekly",
            "time": "08:00",
            "days": ["sat", "sun"],
            "enabled": True,
            "actions": [
                {
                    "type": "irrigation",
                    "zone_id": "zone1",
                    "action": "start",
                    "duration": 15
                }
            ]
        }
    },
    "automations": {
        "presence_lights": {
            "type": "interval",
            "interval": 300,  # 5 minutes
            "enabled": True,
            "conditions": [
                {
                    "type": "time_between",
                    "start_time": "17:00",
                    "end_time": "23:00"
                },
                {
                    "type": "presence",
                    "person_id": "user1",
                    "state": "home"
                }
            ],
            "actions": [
                {
                    "type": "scene",
                    "scene_id": "welcome"
                }
            ]
        },
        "rain_cancel_irrigation": {
            "type": "interval",
            "interval": 3600,  # 1 heure
            "enabled": True,
            "conditions": [
                {
                    "type": "weather",
                    "condition": "rain"
                }
            ],
            "actions": [
                {
                    "type": "irrigation",
                    "zone_id": "all",
                    "action": "stop"
                },
                {
                    "type": "notification",
                    "user_id": "user1",
                    "message": "L'irrigation a été annulée en raison de la pluie.",
                    "title": "Irrigation annulée"
                }
            ]
        },
        "vacation_mode": {
            "type": "daily",
            "time": "20:00",
            "enabled": False,
            "actions": [
                {
                    "type": "light",
                    "light_id": "living_room",
                    "state": True,
                    "brightness": 80
                },
                {
                    "type": "light",
                    "light_id": "living_room",
                    "state": False,
                    "delay": 3600
                }
            ]
        }
    },
    "update_interval": 1,
    "location": {
        "latitude": 48.8566,
        "longitude": 2.3522
    },
    "timezone": "Europe/Paris"
}import logging
import time
import json
import math
import threading
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from queue import PriorityQueue
import heapq

from modules.base_module import BaseModule
from modules.message_bus import MessageBus
from modules.state_manager import StateManager

class SchedulerModule(BaseModule):
    """
    Module de planification et d'automatisation temporelle.
    Permet de planifier des tâches récurrentes ou ponctuelles et de gérer
    des automatisations basées sur l'heure.
    """
    
    # Types de planification
    ONCE = "once"          # Une seule fois
    DAILY = "daily"        # Tous les jours
    WEEKLY = "weekly"      # Toutes les semaines
    MONTHLY = "monthly"    # Tous les mois
    INTERVAL = "interval"  # À intervalles réguliers
    CRON = "cron"          # Selon une expression cron
    SUNRISE = "sunrise"    # Au lever du soleil
    SUNSET = "sunset"      # Au coucher du soleil
    
    # Jours de la semaine
    DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    
    def __init__(self, module_id: str, config: Dict[str, Any], message_bus: MessageBus, state_manager: StateManager):
        """
        Initialise le module de planification.
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration du module
            message_bus: Instance du bus de messages
            state_manager: Instance du gestionnaire d'état
        """
        super().__init__(module_id, "scheduler", config, message_bus, state_manager)
        
        # Configuration des tâches planifiées
        self.schedules = config.get("schedules", {})
        
        # Configuration des automatisations temporelles
        self.automations = config.get("automations", {})
        
        # Configuration des paramètres avancés
        self.update_interval = config.get("update_interval", 1)  # Intervalle en secondes
        self.location = config.get("location", {"latitude": 48.8566, "longitude": 2.3522})  # Paris par défaut
        self.timezone = config.get("timezone", "Europe/Paris")
        
        # État interne
        self._tasks = {}  # task_id -> task_config
        self._task_queue = []  # Tas (heap) de tâches à exécuter [(next_run, task_id), ...]
        self._last_run_times = {}  # task_id -> last_run_time
        self._running = False
        self._scheduler_thread = None
        self._sun_times = {"sunrise": None, "sunset": None}
        self._lock = threading.RLock()  # Pour la synchronisation
        
        self.logger.info(f"Module de planification initialisé avec {len(self.schedules)} tâches planifiées")
        
        # Enregistrement des gestionnaires de messages
        self._register_handlers()
    
    def _register_handlers(self):
        """Enregistre les gestionnaires de messages pour ce module."""
        self.message_bus.register_handler("scheduler/add", self._handle_add_task)
        self.message_bus.register_handler("scheduler/remove", self._handle_remove_task)
        self.message_bus.register_handler("scheduler/update", self._handle_update_task)
        self.message_bus.register_handler("scheduler/status", self._handle_status_request)
        self.message_bus.register_handler("scheduler/list", self._handle_list_tasks)
        self.message_bus.register_handler("scheduler/run_now", self._handle_run_now)
        self.message_bus.register_handler("weather/sun_times", self._handle_sun_times_update)
    
    def start(self):
        """Démarre le module et le thread du planificateur."""
        self.logger.info("Démarrage du module de planification")
        
        # Charger l'état précédent si disponible
        self._load_state()
        
        # Initialiser les tâches planifiées
        self._initialize_tasks()
        
        # Calculer les heures de lever/coucher du soleil
        self._calculate_sun_times()
        
        # Démarrer le thread du planificateur
        self._running = True
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        
        # Définir le statut comme actif
        self.active = True
    
    def stop(self):
        """Arrête le module et le thread du planificateur."""
        self.logger.info("Arrêt du module de planification")
        
        # Arrêter le thread du planificateur
        self._running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
            
        # Sauvegarde de l'état
        self._save_state()
        
        # Définir le statut comme inactif
        self.active = False
    
    def _load_state(self):
        """Charge l'état précédent depuis le gestionnaire d'état."""
        state = self.state_manager.get_state(f"{self.module_id}_state")
        if state:
            self.logger.info("Chargement de l'état précédent")
            
            if "tasks" in state:
                self._tasks = state["tasks"]
            
            if "last_run_times" in state:
                self._last_run_times = state["last_run_times"]
    
    def _save_state(self):
        """Sauvegarde l'état actuel dans le gestionnaire d'état."""
        state = {
            "tasks": self._tasks,
            "last_run_times": self._last_run_times,
            "last_update": time.time()
        }
        self.state_manager.set_state(f"{self.module_id}_state", state)
    
    def _initialize_tasks(self):
        """Initialise les tâches planifiées à partir de la configuration."""
        with self._lock:
            # Charger les tâches planifiées depuis la configuration
            for schedule_id, schedule_config in self.schedules.items():
                if schedule_id not in self._tasks:
                    self._tasks[schedule_id] = {
                        "id": schedule_id,
                        "enabled": schedule_config.get("enabled", True),
                        "schedule_type": schedule_config.get("type", self.ONCE),
                        "time": schedule_config.get("time"),
                        "days": schedule_config.get("days"),
                        "date": schedule_config.get("date"),
                        "interval": schedule_config.get("interval"),
                        "offset": schedule_config.get("offset", 0),
                        "actions": schedule_config.get("actions", []),
                        "last_run": self._last_run_times.get(schedule_id, 0),
                        "next_run": 0  # Sera calculé
                    }
            
            # Charger les automatisations temporelles
            for automation_id, automation_config in self.automations.items():
                if automation_id not in self._tasks:
                    self._tasks[automation_id] = {
                        "id": automation_id,
                        "enabled": automation_config.get("enabled", True),
                        "schedule_type": automation_config.get("type", self.ONCE),
                        "time": automation_config.get("time"),
                        "days": automation_config.get("days"),
                        "date": automation_config.get("date"),
                        "interval": automation_config.get("interval"),
                        "offset": automation_config.get("offset", 0),
                        "conditions": automation_config.get("conditions", []),
                        "actions": automation_config.get("actions", []),
                        "last_run": self._last_run_times.get(automation_id, 0),
                        "next_run": 0  # Sera calculé
                    }
            
            # Calculer les prochaines exécutions
            self._recalculate_next_runs()
            
            # Mettre à jour la file d'attente des tâches
            self._update_task_queue()
    
    def _recalculate_next_runs(self):
        """Recalcule les prochaines exécutions pour toutes les tâches."""
        now = time.time()
        
        for task_id, task in self._tasks.items():
            if not task.get("enabled", True):
                task["next_run"] = float('inf')  # Ne pas exécuter
                continue
                
            schedule_type = task.get("schedule_type")
            
            if schedule_type == self.ONCE:
                # Tâche à exécuter une seule fois
                if "date" in task and "time" in task:
                    task_datetime = self._parse_datetime(task["date"], task["time"])
                    if task_datetime:
                        task["next_run"] = task_datetime.timestamp()
                    else:
                        task["next_run"] = float('inf')
                else:
                    task["next_run"] = float('inf')
            
            elif schedule_type == self.DAILY:
                # Tâche quotidienne
                if "time" in task:
                    next_run = self._calculate_next_daily(task["time"], task.get("last_run", 0))
                    task["next_run"] = next_run
                else:
                    task["next_run"] = float('inf')
            
            elif schedule_type == self.WEEKLY:
                # Tâche hebdomadaire
                if "time" in task and "days" in task:
                    next_run = self._calculate_next_weekly(task["time"], task["days"], task.get("last_run", 0))
                    task["next_run"] = next_run
                else:
                    task["next_run"] = float('inf')
            
            elif schedule_type == self.MONTHLY:
                # Tâche mensuelle
                if "time" in task and "date" in task:
                    next_run = self._calculate_next_monthly(task["time"], task["date"], task.get("last_run", 0))
                    task["next_run"] = next_run
                else:
                    task["next_run"] = float('inf')
            
            elif schedule_type == self.INTERVAL:
                # Tâche à intervalle régulier
                if "interval" in task:
                    last_run = task.get("last_run", 0)
                    interval = task["interval"]
                    
                    if last_run > 0:
                        # Prochaine exécution basée sur la dernière exécution
                        task["next_run"] = last_run + interval
                    else:
                        # Première exécution
                        task["next_run"] = now + interval
                else:
                    task["next_run"] = float('inf')
            
            elif schedule_type == self.SUNRISE:
                # Tâche au lever du soleil
                if self._sun_times["sunrise"]:
                    sunrise_time = self._sun_times["sunrise"]
                    offset = task.get("offset", 0)  # Décalage en minutes
                    
                    # Convertir le lever du soleil en timestamp
                    sunrise_dt = self._parse_time(sunrise_time)
                    if sunrise_dt:
                        next_run = sunrise_dt.timestamp() + offset * 60
                        
                        # Si l'heure est déjà passée, programmer pour demain
                        if next_run < now:
                            tomorrow = datetime.now() + timedelta(days=1)
                            tomorrow_date = tomorrow.strftime("%Y-%m-%d")
                            sunrise_dt = self._parse_datetime(tomorrow_date, sunrise_time)
                            if sunrise_dt:
                                next_run = sunrise_dt.timestamp() + offset * 60
                        
                        task["next_run"] = next_run
                    else:
                        task["next_run"] = float('inf')
                else:
                    task["next_run"] = float('inf')
            
            elif schedule_type == self.SUNSET:
                # Tâche au coucher du soleil
                if self._sun_times["sunset"]:
                    sunset_time = self._sun_times["sunset"]
                    offset = task.get("offset", 0)  # Décalage en minutes
                    
                    # Convertir le coucher du soleil en timestamp
                    sunset_dt = self._parse_time(sunset_time)
                    if sunset_dt:
                        next_run = sunset_dt.timestamp() + offset * 60
                        
                        # Si l'heure est déjà passée, programmer pour demain
                        if next_run < now:
                            tomorrow = datetime.now() + timedelta(days=1)
                            tomorrow_date = tomorrow.strftime("%Y-%m-%d")
                            sunset_dt = self._parse_datetime(tomorrow_date, sunset_time)
                            if sunset_dt:
                                next_run = sunset_dt.timestamp() + offset * 60
                        
                        task["next_run"] = next_run
                    else:
                        task["next_run"] = float('inf')
                else:
                    task["next_run"] = float('inf')
            
            elif schedule_type == self.CRON:
                # Tâche selon une expression cron (non implémentée)
                task["next_run"] = float('inf')
            
            else:
                task["next_run"] = float('inf')
    
    def _update_task_queue(self):
        """Met à jour la file d'attente des tâches."""
        with self._lock:
            # Vider la file d'attente
            self._task_queue = []
            
            # Ajouter les tâches activées avec une date d'exécution valide
            for task_id, task in self._tasks.items():
                if task.get("enabled", True) and task["next_run"] < float('inf'):
                    heapq.heappush(self._task_queue, (task["next_run"], task_id))
    
    def _scheduler_loop(self):
        """Boucle principale du planificateur."""
        last_update = 0
        
        while self._running:
            now = time.time()
            
            # Vérifier s'il est temps de mettre à jour les calculs de lever/coucher du soleil
            if now - last_update > 3600:  # Mettre à jour toutes les heures
                self._calculate_sun_times()
                last_update = now
            
            # Exécuter les tâches dues
            with self._lock:
                while self._task_queue and self._task_queue[0][0] <= now:
                    # Récupérer la prochaine tâche
                    next_run, task_id = heapq.heappop(self._task_queue)
                    
                    # Vérifier que la tâche existe toujours et est activée
                    if task_id in self._tasks and self._tasks[task_id].get("enabled", True):
                        self._execute_task(task_id)
                        
                        # Mettre à jour le temps d'exécution
                        self._tasks[task_id]["last_run"] = now
                        self._last_run_times[task_id] = now
                        
                        # Recalculer la prochaine exécution pour cette tâche
                        self._recalculate_next_run(task_id)
                        
                        # Remettre la tâche dans la file si nécessaire
                        if self._tasks[task_id]["next_run"] < float('inf'):
                            heapq.heappush(self._task_queue, (self._tasks[task_id]["next_run"], task_id))
            
            # Attendre avant la prochaine vérification
            time.sleep(self.update_interval)
    
    def _recalculate_next_run(self, task_id: str):
        """
        Recalcule la prochaine exécution pour une tâche spécifique.
        
        Args:
            task_id: Identifiant de la tâche
        """
        task = self._tasks.get(task_id)
        if not task:
            return
            
        schedule_type = task.get("schedule_type")
        last_run = task.get("last_run", 0)
        
        if schedule_type == self.ONCE:
            # Les tâches ponctuelles ne sont pas réexécutées
            task["next_run"] = float('inf')
        
        elif schedule_type == self.DAILY:
            # Tâche quotidienne
            if "time" in task:
                next_run = self._calculate_next_daily(task["time"], last_run)
                task["next_run"] = next_run
        
        elif schedule_type == self.WEEKLY:
            # Tâche hebdomadaire
            if "time" in task and "days" in task:
                next_run = self._calculate_next_weekly(task["time"], task["days"], last_run)
                task["next_run"] = next_run
        
        elif schedule_type == self.MONTHLY:
            # Tâche mensuelle
            if "time" in task and "date" in task:
                next_run = self._calculate_next_monthly(task["time"], task["date"], last_run)
                task["next_run"] = next_run
        
        elif schedule_type == self.INTERVAL:
            # Tâche à intervalle régulier
            if "interval" in task:
                interval = task["interval"]
                task["next_run"] = last_run + interval
        
        elif schedule_type == self.SUNRISE:
            # Tâche au lever du soleil
            if self._sun_times["sunrise"]:
                sunrise_time = self._sun_times["sunrise"]
                offset = task.get("offset", 0)  # Décalage en minutes
                
                # Convertir le lever du soleil en timestamp
                now = time.time()
                sunrise_dt = self._parse_time(sunrise_time)
                if sunrise_dt:
                    next_run = sunrise_dt.timestamp() + offset * 60
                    
                    # Si l'heure est déjà passée, programmer pour demain
                    if next_run <= now:
                        tomorrow = datetime.now() + timedelta(days=1)
                        tomorrow_date = tomorrow.strftime("%Y-%m-%d")
                        sunrise_dt = self._parse_datetime(tomorrow_date, sunrise_time)
                        if sunrise_dt:
                            next_run = sunrise_dt.timestamp() + offset * 60
                    
                    task["next_run"] = next_run
        
        elif schedule_type == self.SUNSET:
            # Tâche au coucher du soleil
            if self._sun_times["sunset"]:
                sunset_time = self._sun_times["sunset"]
                offset = task.get("offset", 0)  # Décalage en minutes
                
                # Convertir le coucher du soleil en timestamp
                now = time.time()
                sunset_dt = self._parse_time(sunset_time)
                if sunset_dt:
                    next_run = sunset_dt.timestamp() + offset * 60
                    
                    # Si l'heure est déjà passée, programmer pour demain
                    if next_run <= now:
                        tomorrow = datetime.now() + timedelta(days=1)
                        tomorrow_date = tomorrow.strftime("%Y-%m-%d")
                        sunset_dt = self._parse_datetime(tomorrow_date, sunset_time)
                        if sunset_dt:
                            next_run = sunset_dt.timestamp() + offset * 60
                    
                    task["next_run"] = next_run
        
        elif schedule_type == self.CRON:
            # Tâche selon une expression cron (non implémentée)
            task["next_run"] = float('inf')
    
    def _execute_task(self, task_id: str):
        """
        Exécute une tâche planifiée.
        
        Args:
            task_id: Identifiant de la tâche
        """
        task = self._tasks.get(task_id)
        if not task:
            return
            
        self.logger.info(f"Exécution de la tâche planifiée: {task_id}")
        
        # Vérifier les conditions pour les automatisations
        if "conditions" in task and task["conditions"]:
            if not self._evaluate_conditions(task["conditions"]):
                self.logger.info(f"Tâche {task_id} non exécutée: conditions non remplies")
                return
        
        # Exécuter les actions
        actions = task.get("actions", [])
        for action in actions:
            self._execute_action(action)
        
        # Publier un événement d'exécution
        self.message_bus.publish("scheduler/task_executed", {
            "task_id": task_id,
            "timestamp": time.time()
        })
    
    def _execute_action(self, action: Dict[str, Any]):
        """
        Exécute une action.
        
        Args:
            action: Description de l'action à exécuter
        """
        action_type = action.get("type")
        
        if not action_type:
            self.logger.warning("Action sans type spécifié")
            return
            
        if action_type == "publish":
            # Publier un message sur le bus
            topic = action.get("topic")
            message = action.get("message", {})
            
            if topic:
                self.message_bus.publish(topic, message)
        
        elif action_type == "scene":
            # Activer une scène d'éclairage
            scene_id = action.get("scene_id")
            
            if scene_id:
                self.message_bus.publish("lighting/scene", {
                    "scene_id": scene_id
                })
        
        elif action_type == "light":
            # Contrôler une lumière
            light_id = action.get("light_id")
            state = action.get("state")
            brightness = action.get("brightness")
            color = action.get("color")
            
            if light_id is not None and state is not None:
                self.message_bus.publish("lighting/set", {
                    "light_id": light_id,
                    "state": state,
                    "brightness": brightness,
                    "color": color
                })
        
        elif action_type == "security":
            # Contrôler le système de sécurité
            action_name = action.get("action")
            code = action.get("code")
            
            if action_name == "arm_home":
                self.message_bus.publish("security/arm", {
                    "mode": "home",
                    "code": code
                })
            elif action_name == "arm_away":
                self.message_bus.publish("security/arm", {
                    "mode": "away",
                    "code": code
                })
            elif action_name == "disarm":
                self.message_bus.publish("security/disarm", {
                    "code": code
                })
        
        elif action_type == "irrigation":
            # Contrôler l'irrigation
            zone_id = action.get("zone_id")
            action_name = action.get("action")
            duration = action.get("duration")
            
            if zone_id and action_name:
                if action_name == "start":
                    self.message_bus.publish("irrigation/start", {
                        "zone_id": zone_id,
                        "duration": duration
                    })
                elif action_name == "stop":
                    self.message_bus.publish("irrigation/stop", {
                        "zone_id": zone_id
                    })
        
        elif action_type == "notification":
            # Envoyer une notification
            user_id = action.get("user_id")
            message = action.get("message")
            title = action.get("title")
            priority = action.get("priority", "normal")
            
            if user_id and message:
                self.message_bus.publish("notification/send", {
                    "user_id": user_id,
                    "message": message,
                    "title": title,
                    "priority": priority
                })
        
        elif action_type == "mode":
            # Changer le mode de la maison
            mode = action.get("mode")
            
            if mode:
                self.message_bus.publish("home/mode/set", {
                    "mode": mode
                })
        
        else:
            self.logger.warning(f"Type d'action inconnu: {action_type}")
    
    def _evaluate_conditions(self, conditions: List[Dict[str, Any]]) -> bool:
        """
        Évalue une liste de conditions.
        
        Args:
            conditions: Liste de conditions à évaluer
            
        Returns:
            bool: True si toutes les conditions sont remplies, False sinon
        """
        if not conditions:
            return True
            
        for condition in conditions:
            condition_type = condition.get("type")
            
            if not condition_type:
                continue
                
            if condition_type == "time_between":
                # Vérifier si l'heure actuelle est entre deux heures
                start_time = condition.get("start_time")
                end_time = condition.get("end_time")
                
                if start_time and end_time:
                    if not self._is_time_between(start_time, end_time):
                        return False
            
            elif condition_type == "day_of_week":
                # Vérifier si le jour actuel est dans la liste
                days = condition.get("days", [])
                
                if days:
                    now = datetime.now()
                    day_index = now.weekday()  # 0 = lundi, 6 = dimanche
                    day_name = self.DAYS[day_index]
                    
                    if day_name not in days:
                        return False
            
            elif condition_type == "home_mode":
                # Vérifier le mode actuel de la maison
                mode = condition.get("mode")
                
                if mode:
                    home_state = self.state_manager.get_state("home")
                    if not home_state or home_state.get("mode") != mode:
                        return False
            
            elif condition_type == "presence":
                # Vérifier la présence d'une personne
                person_id = condition.get("person_id")
                state = condition.get("state")
                
                if person_id and state:
                    presence_state = self.state_manager.get_state(f"presence_{person_id}")
                    if not presence_state or presence_state.get("state") != state:
                        return False
            
            elif condition_type == "weather":
                # Vérifier les conditions météo
                condition_name = condition.get("condition")
                
                if condition_name:
                    weather_state = self.state_manager.get_state("weather")
                    if not weather_state:
                        return False
                        
                    if condition_name == "rain" and not weather_state.get("raining", False):
                        return False
                    elif condition_name == "sunny" and not weather_state.get("sunny", False):
                        return False
            
            elif condition_type == "sensor":
                # Vérifier l'état d'un capteur
                sensor_id = condition.get("sensor_id")
                property_name = condition.get("property")
                operator = condition.get("operator", "eq")
                value = condition.get("value")
                
                if sensor_id and property_name is not None and value is not None:
                    sensor_state = self.state_manager.get_state(f"sensor_{sensor_id}")
                    if not sensor_state:
                        return False
                        
                    sensor_value = sensor_state.get(property_name)
                    if sensor_value is None:
                        return False
                        
                    if operator == "eq" and sensor_value != value:
                        return False
                    elif operator == "ne" and sensor_value == value:
                        return False
                    elif operator == "gt" and sensor_value <= value:
                        return False
                    elif operator == "lt" and sensor_value >= value:
                        return False
                    elif operator == "ge" and sensor_value < value:
                        return False
                    elif operator == "le" and sensor_value > value:
                        return False
        
        # Toutes les conditions sont remplies
        return True
    
    def _is_time_between(self, start_time: str, end_time: str) -> bool:
        """
        Vérifie si l'heure actuelle est entre deux heures.
        
        Args:
            start_time: Heure de début (format "HH:MM")
            end_time: Heure de fin (format "HH:MM")
            
        Returns:
            bool: True si l'heure actuelle est dans l'intervalle, False sinon
        """
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # Convertir en minutes depuis minuit pour faciliter la comparaison
        def time_to_minutes(time_str):
            hours, minutes = map(int, time_str.split(":"))
            return hours * 60 + minutes
        
        current_minutes = time_to_minutes(current_time)
        start_minutes = time_to_minutes(start_time)
        end_minutes = time_to_minutes(end_time)
        
        # Gérer le cas où l'intervalle s'étend sur deux jours
        if start_minutes > end_minutes:
            # L'intervalle commence aujourd'hui et se termine demain
            return current_minutes >= start_minutes or current_minutes <= end_minutes
        else:
            # L'intervalle commence et se termine le même jour
            return start_minutes <= current_minutes <= end_minutes
    
    def _calculate_sun_times(self):
        """Calcule les heures de lever et coucher du soleil."""
        try:
            # Dans une implémentation réelle, nous utiliserions une bibliothèque
            # comme astral pour calculer ces heures en fonction de la position géographique
            # Ici, nous simulons simplement des valeurs
            
            # Obtenir la date du jour
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Simuler le lever du soleil à 7h du matin
            self._sun_times["sunrise"] = "07:00"
            
            # Simuler le coucher du soleil à 19h
            self._sun_times["sunset"] = "19:00"
            
            self.logger.debug(f"Heures calculées - Lever: {self._sun_times['sunrise']}, Coucher: {self._sun_times['sunset']}")
            
            # Publier un événement avec les heures de lever/coucher du soleil
            self.message_bus.publish("weather/sun_times", {
                "date": today,
                "sunrise": self._sun_times["sunrise"],
                "sunset": self._sun_times["sunset"]
            })
        except Exception as e:
            self.logger.error(f"Erreur lors du calcul des heures de lever/coucher du soleil: {e}")
    
    def _calculate_next_daily(self, time_str: str, last_run: float) -> float:
        """
        Calcule la prochaine exécution d'une tâche quotidienne.
        
        Args:
            time_str: Heure d'exécution (format "HH:MM")
            last_run: Timestamp de la dernière exécution
            
        Returns:
            float: Timestamp de la prochaine exécution
        """
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        
        # Convertir l'heure en datetime
        time_dt = self._parse_datetime(today, time_str)
        if not time_dt:
            return float('inf')
            
        next_run = time_dt.timestamp()
        
        # Si l'heure est déjà passée aujourd'hui, programmer pour demain
        if next_run <= time.time():
            tomorrow = now + timedelta(days=1)
            tomorrow_date = tomorrow.strftime("%Y-%m-%d")
            time_dt = self._parse_datetime(tomorrow_date, time_str)
            if time_dt:
                next_run = time_dt.timestamp()
        
        return next_run
    
    def _calculate_next_weekly(self, time_str: str, days: List[str], last_run: float) -> float:
        """
        Calcule la prochaine exécution d'une tâche hebdomadaire.
        
        Args:
            time_str: Heure d'exécution (format "HH:MM")
            days: Liste des jours d'exécution (format ["mon", "tue", ...])
            last_run: Timestamp de la dernière exécution
            
        Returns:
            float: Timestamp de la prochaine exécution
        """
        if not days:
            return float('inf')
            
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        today_weekday = now.weekday()  # 0 = lundi, 6 = dimanche
        
        # Convertir les noms de jours en indices
        day_indices = []
        for day in days:
            if day in self.DAYS:
                day_indices.append(self.DAYS.index(day))
        
        if not day_indices:
            return float('inf')
            
        # Trouver le prochain jour programmé
        next_day_offset = None
        for i in range(7):
            future_day = (today_weekday + i) % 7
            if future_day in day_indices:
                if i == 0:
                    # C'est aujourd'hui, vérifier si l'heure est déjà passée
                    time_dt = self._parse_datetime(today, time_str)
                    if time_dt and time_dt.timestamp() > time.time():
                        next_day_offset = 0
                        break
                else:
                    next_day_offset = i
                    break
        
        if next_day_offset is None:
            return float('inf')
            
        # Calculer la date du prochain jour d'exécution
        next_date = now + timedelta(days=next_day_offset)
        next_date_str = next_date.strftime("%Y-%m-%d")
        
        # Convertir en datetime
        next_dt = self._parse_datetime(next_date_str, time_str)
        if not next_dt:
            return float('inf')
            
        return next_dt.timestamp()
    
    def _calculate_next_monthly(self, time_str: str, date: int, last_run: float) -> float:
        """
        Calcule la prochaine exécution d'une tâche mensuelle.
        
        Args:
            time_str: Heure d'exécution (format "HH:MM")
            date: Jour du mois (1-31)
            last_run: Timestamp de la dernière exécution
            
        Returns:
            float: Timestamp de la prochaine exécution
        """
        if not isinstance(date, int) or date < 1 or date > 31:
            return float('inf')
            
        now = datetime.now()
        current_year = now.year
        current_month = now.month
        
        # Vérifier si la date de ce mois est déjà passée
        if date < now.day or (date == now.day and self._parse_time(time_str).timestamp() <= time.time()):
            # Passer au mois suivant
            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1
        
        # Gérer les jours invalides (ex: 31 février)
        import calendar
        last_day = calendar.monthrange(current_year, current_month)[1]
        if date > last_day:
            date = last_day
        
        # Construire la date
        next_date_str = f"{current_year}-{current_month:02d}-{date:02d}"
        
        # Convertir en datetime
        next_dt = self._parse_datetime(next_date_str, time_str)
        if not next_dt:
            return float('inf')
            
        return next_dt.timestamp()
    
    def _parse_time(self, time_str: str) -> datetime:
        """
        Parse une chaîne d'heure au format "HH:MM".
        
        Args:
            time_str: Chaîne d'heure à parser
            
        Returns:
            datetime: Objet datetime correspondant, ou None si invalide
        """
        try:
            hour, minute = map(int, time_str.split(":"))
            now = datetime.now()
            return datetime(now.year, now.month, now.day, hour, minute)
        except (ValueError, TypeError):
            self.logger.warning(f"Format d'heure invalide: {time_str}")
            return None
    
    def _parse_datetime(self, date_str: str, time_str: str) -> datetime:
        """
        Parse une chaîne de date et une chaîne d'heure.
        
        Args:
            date_str: Chaîne de date au format "YYYY-MM-DD"
            time_str: Chaîne d'heure au format "HH:MM"
            
        Returns:
            datetime: Objet datetime correspondant, ou None si invalide
        """
        try:
            year, month, day = map(int, date_str.split("-"))
            hour, minute = map(int, time_str.split(":"))
            return datetime(year, month, day, hour, minute)
        except (ValueError, TypeError):
            self.logger.warning(f"Format de date/heure invalide: {date_str} {time_str}")
            return None