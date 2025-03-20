"""
modules/module_interface.py
--------------------------
Définit les interfaces de base pour créer des modules compatibles avec Alfred.
Tous les nouveaux modules doivent implémenter l'une de ces interfaces.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, Tuple, Callable

class BaseModule(ABC):
    """Interface de base pour tous les modules Alfred."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nom unique du module."""
        pass
    
    @property
    def version(self) -> str:
        """Version du module."""
        return "1.0.0"
    
    @property
    def dependencies(self) -> List[str]:
        """Liste des noms des modules dont dépend ce module."""
        return []
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialise le module.
        
        Returns:
            True si l'initialisation réussit, False sinon
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> bool:
        """
        Arrête proprement le module.
        
        Returns:
            True si l'arrêt réussit, False sinon
        """
        pass
    
    def get_capabilities(self) -> List[str]:
        """
        Retourne la liste des capacités offertes par le module.
        
        Returns:
            Liste des capacités
        """
        return []

class WeatherModule(BaseModule):
    """Interface pour les modules météo."""
    
    @abstractmethod
    def get_current_weather(self, location: str) -> Dict[str, Any]:
        """
        Récupère les conditions météo actuelles pour une localisation donnée.
        
        Args:
            location: Localisation (ville, coordonnées, etc.)
            
        Returns:
            Dictionnaire contenant les infos météo
        """
        pass
    
    @abstractmethod
    def get_forecast(self, location: str, days: int = 5) -> List[Dict[str, Any]]:
        """
        Récupère les prévisions météo pour une localisation donnée.
        
        Args:
            location: Localisation (ville, coordonnées, etc.)
            days: Nombre de jours de prévision
            
        Returns:
            Liste de dictionnaires contenant les prévisions
        """
        pass
    
    def check_rain_forecast(self, location: str, hours: int = 24) -> bool:
        """
        Vérifie s'il va pleuvoir dans les prochaines heures.
        
        Args:
            location: Localisation (ville, coordonnées, etc.)
            hours: Nombre d'heures à vérifier
            
        Returns:
            True s'il va pleuvoir, False sinon
        """
        pass
    
    def get_capabilities(self) -> List[str]:
        return ["weather_current", "weather_forecast", "rain_forecast"]

class IrrigationModule(BaseModule):
    """Interface pour les modules d'irrigation."""
    
    @abstractmethod
    def start_irrigation(self, zone: str, duration: int) -> bool:
        """
        Démarre l'irrigation d'une zone pour une durée donnée.
        
        Args:
            zone: Nom de la zone à irriguer
            duration: Durée d'irrigation en secondes
            
        Returns:
            True si l'irrigation a démarré, False sinon
        """
        pass
    
    @abstractmethod
    def stop_irrigation(self, zone: str) -> bool:
        """
        Arrête l'irrigation d'une zone.
        
        Args:
            zone: Nom de la zone à arrêter
            
        Returns:
            True si l'irrigation a été arrêtée, False sinon
        """
        pass
    
    @abstractmethod
    def get_irrigation_status(self, zone: Optional[str] = None) -> Dict[str, Any]:
        """
        Récupère le statut actuel de l'irrigation.
        
        Args:
            zone: Nom de la zone à vérifier (toutes les zones si None)
            
        Returns:
            Dictionnaire contenant le statut
        """
        pass
    
    @abstractmethod
    def schedule_irrigation(self, zone: str, time: str, duration: int, 
                          days: List[str], weather_adjustment: bool = True) -> bool:
        """
        Planifie une irrigation régulière.
        
        Args:
            zone: Nom de la zone
            time: Heure au format HH:MM
            duration: Durée en secondes
            days: Jours de la semaine (Mo, Tu, We, Th, Fr, Sa, Su)
            weather_adjustment: Ajuster en fonction de la météo
            
        Returns:
            True si la planification a réussi, False sinon
        """
        pass
    
    def get_capabilities(self) -> List[str]:
        return ["irrigation_control", "irrigation_scheduling"]

class EnergyModule(BaseModule):
    """Interface pour les modules d'énergie."""
    
    @abstractmethod
    def log_consumption(self, device: str, consumption: float, unit: str = "kWh") -> bool:
        """
        Enregistre la consommation d'un appareil.
        
        Args:
            device: Nom de l'appareil
            consumption: Consommation
            unit: Unité de mesure
            
        Returns:
            True si l'enregistrement a réussi, False sinon
        """
        pass
    
    @abstractmethod
    def get_device_consumption(self, device: str, period: str = "day") -> Dict[str, Any]:
        """
        Récupère la consommation d'un appareil pour une période donnée.
        
        Args:
            device: Nom de l'appareil
            period: Période (day, week, month, year)
            
        Returns:
            Dictionnaire contenant la consommation
        """
        pass
    
    @abstractmethod
    def get_consumption_report(self, period: str = "day", devices: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Génère un rapport de consommation.
        
        Args:
            period: Période (day, week, month, year)
            devices: Liste des appareils à inclure (tous si None)
            
        Returns:
            Dictionnaire contenant le rapport
        """
        pass
    
    @abstractmethod
    def optimize_consumption(self) -> Dict[str, Any]:
        """
        Propose des optimisations de consommation.
        
        Returns:
            Dictionnaire contenant les recommandations
        """
        pass
    
    def get_capabilities(self) -> List[str]:
        return ["energy_monitoring", "consumption_reporting", "optimization"]

class HabitModule(BaseModule):
    """Interface pour les modules d'analyse d'habitudes."""
    
    @abstractmethod
    def log_activity(self, category: str, timestamp: Optional[str] = None) -> bool:
        """
        Enregistre une activité dans une catégorie.
        
        Args:
            category: Catégorie de l'activité
            timestamp: Horodatage (moment actuel si None)
            
        Returns:
            True si l'enregistrement a réussi, False sinon
        """
        pass
    
    @abstractmethod
    def detect_patterns(self, category: Optional[str] = None, days: int = 30) -> Dict[str, Any]:
        """
        Détecte des modèles d'activité.
        
        Args:
            category: Catégorie à analyser (toutes si None)
            days: Nombre de jours d'historique à analyser
            
        Returns:
            Dictionnaire contenant les modèles détectés
        """
        pass
    
    @abstractmethod
    def predict_next_activity(self, category: str) -> Dict[str, Any]:
        """
        Prédit la prochaine occurrence d'une activité.
        
        Args:
            category: Catégorie de l'activité
            
        Returns:
            Dictionnaire contenant la prédiction
        """
        pass
    
    def get_capabilities(self) -> List[str]:
        return ["habit_tracking", "pattern_detection", "activity_prediction"]

class CommandModule(BaseModule):
    """Interface pour les modules d'exécution de commandes."""
    
    @abstractmethod
    def execute_command(self, command: str, working_dir: Optional[str] = None, 
                       timeout: Optional[int] = None, shell: bool = True) -> Tuple[str, str, int]:
        """
        Exécute une commande système.
        
        Args:
            command: Commande à exécuter
            working_dir: Répertoire de travail
            timeout: Timeout en secondes
            shell: Utiliser un shell pour l'exécution
            
        Returns:
            Tuple (stdout, stderr, code de retour)
        """
        pass
    
    @abstractmethod
    def execute_script(self, script_content: str, script_type: str, 
                      script_name: Optional[str] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Exécute un script.
        
        Args:
            script_content: Contenu du script
            script_type: Type de script (autohotkey, python, batch, etc.)
            script_name: Nom du fichier script (généré si None)
            timeout: Timeout en secondes
            
        Returns:
            Dictionnaire contenant le résultat
        """
        pass
    
    def get_capabilities(self) -> List[str]:
        return ["command_execution", "script_execution"]

class SecurityModule(BaseModule):
    """Interface pour les modules de sécurité."""
    
    @abstractmethod
    def check_intrusions(self) -> List[Dict[str, Any]]:
        """
        Vérifie les intrusions.
        
        Returns:
            Liste des intrusions détectées
        """
        pass
    
    @abstractmethod
    def check_logs(self, log_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Vérifie les logs à la recherche d'anomalies.
        
        Args:
            log_file: Fichier log à vérifier (tous si None)
            
        Returns:
            Dictionnaire contenant les anomalies détectées
        """
        pass
    
    @abstractmethod
    def check_network(self) -> Dict[str, Any]:
        """
        Vérifie le réseau à la recherche d'anomalies.
        
        Returns:
            Dictionnaire contenant les anomalies détectées
        """
        pass
    
    def get_capabilities(self) -> List[str]:
        return ["intrusion_detection", "log_analysis", "network_monitoring"]

class TranslationModule(BaseModule):
    """Interface pour les modules de traduction."""
    
    @abstractmethod
    def detect_language(self, text: str) -> Dict[str, Any]:
        """
        Détecte la langue d'un texte.
        
        Args:
            text: Texte à analyser
            
        Returns:
            Dictionnaire contenant la langue détectée et la confiance
        """
        pass
    
    @abstractmethod
    def translate_text(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict[str, Any]:
        """
        Traduit un texte.
        
        Args:
            text: Texte à traduire
            target_lang: Langue cible
            source_lang: Langue source (automatique si None)
            
        Returns:
            Dictionnaire contenant la traduction
        """
        pass
    
    @abstractmethod
    def translate_file(self, file_path: str, target_lang: str, source_lang: Optional[str] = None) -> Dict[str, Any]:
        """
        Traduit un fichier.
        
        Args:
            file_path: Chemin du fichier
            target_lang: Langue cible
            source_lang: Langue source (automatique si None)
            
        Returns:
            Dictionnaire contenant le chemin du fichier traduit
        """
        pass
    
    def get_capabilities(self) -> List[str]:
        return ["language_detection", "text_translation", "file_translation"]

class EmotionModule(BaseModule):
    """Interface pour les modules d'analyse d'émotions."""
    
    @abstractmethod
    def analyze_emotion(self, audio_path: str) -> Dict[str, Any]:
        """
        Analyse l'émotion dans un fichier audio.
        
        Args:
            audio_path: Chemin du fichier audio
            
        Returns:
            Dictionnaire contenant l'émotion détectée et la confiance
        """
        pass
    
    @abstractmethod
    def text_to_speech(self, text: str, emotion: str = "neutre") -> str:
        """
        Convertit du texte en parole avec une émotion donnée.
        
        Args:
            text: Texte à convertir
            emotion: Émotion à appliquer
            
        Returns:
            Chemin du fichier audio généré
        """
        pass
    
    def get_capabilities(self) -> List[str]:
        return ["emotion_detection", "emotional_tts"]

class NLPModule(BaseModule):
    """Interface pour les modules de traitement du langage naturel."""
    
    @abstractmethod
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyse le sentiment d'un texte.
        
        Args:
            text: Texte à analyser
            
        Returns:
            Dictionnaire contenant le sentiment détecté
        """
        pass
    
    @abstractmethod
    def extract_entities(self, text: str) -> Dict[str, Any]:
        """
        Extrait les entités d'un texte.
        
        Args:
            text: Texte à analyser
            
        Returns:
            Dictionnaire contenant les entités extraites
        """
        pass
    
    @abstractmethod
    def generate_response(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Génère une réponse à un prompt.
        
        Args:
            prompt: Prompt à traiter
            context: Contexte additionnel
            
        Returns:
            Réponse générée
        """
        pass
    
    def get_capabilities(self) -> List[str]:
        return ["sentiment_analysis", "entity_extraction", "response_generation"]

class NotificationModule(BaseModule):
    """Interface pour les modules de notification."""
    
    @abstractmethod
    def send_notification(self, message: str, level: str = "info", 
                        channel: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Envoie une notification.
        
        Args:
            message: Message à envoyer
            level: Niveau de la notification (info, warning, error, etc.)
            channel: Canal de notification (email, sms, etc.)
            metadata: Métadonnées additionnelles
            
        Returns:
            True si la notification a été envoyée, False sinon
        """
        pass
    
    @abstractmethod
    def schedule_notification(self, message: str, schedule_time: Union[str, int], 
                           level: str = "info", channel: Optional[str] = None, 
                           metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Planifie une notification.
        
        Args:
            message: Message à envoyer
            schedule_time: Moment de la notification (timestamp ou format ISO)
            level: Niveau de la notification
            channel: Canal de notification
            metadata: Métadonnées additionnelles
            
        Returns:
            ID de la notification planifiée
        """
        pass
    
    @abstractmethod
    def cancel_notification(self, notification_id: str) -> bool:
        """
        Annule une notification planifiée.
        
        Args:
            notification_id: ID de la notification
            
        Returns:
            True si la notification a été annulée, False sinon
        """
        pass
    
    def get_capabilities(self) -> List[str]:
        return ["notification_sending", "notification_scheduling"]
