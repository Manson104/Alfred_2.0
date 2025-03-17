"""
Logger - Système de journalisation centralisé pour Alfred

Ce module fournit une configuration unifiée de logging pour tous les composants d'Alfred.
Il permet de configurer facilement la journalisation avec différents niveaux et handlers.
"""

import os
import logging
import logging.handlers
from datetime import datetime
from typing import Dict, Optional, Union, List

class AlfredLogger:
    """
    Gestionnaire centralisé de journalisation pour Alfred
    """
    
    def __init__(self, 
                 log_level: int = logging.INFO,
                 log_dir: str = "~/.alfred/logs",
                 console_output: bool = True,
                 max_file_size: int = 10 * 1024 * 1024,  # 10 MB
                 backup_count: int = 5):
        """
        Initialise le système de journalisation
        
        Args:
            log_level: Niveau de journalisation global
            log_dir: Répertoire pour stocker les fichiers de logs
            console_output: Afficher aussi les logs dans la console
            max_file_size: Taille maximale d'un fichier de log avant rotation
            backup_count: Nombre de fichiers de backup à conserver
        """
        self.log_level = log_level
        self.log_dir = os.path.expanduser(log_dir)
        self.console_output = console_output
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        
        # Dictionnaire pour stocker les niveaux personnalisés par module
        self.module_levels = {}
        
        # Créer le répertoire de logs s'il n'existe pas
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Configurer le logger racine
        self._setup_root_logger()
        
        # Logger pour ce module
        self.logger = logging.getLogger("logger")
        self.logger.info("Système de journalisation Alfred initialisé")
    
    def _setup_root_logger(self):
        """Configure le logger racine avec les handlers appropriés"""
        root_logger = logging.getLogger("")
        root_logger.setLevel(self.log_level)
        
        # Supprimer les handlers existants pour éviter les doublons
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Format de log unifié
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Fichier de log général
        general_log_file = os.path.join(self.log_dir, "alfred.log")
        file_handler = logging.handlers.RotatingFileHandler(
            general_log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # Fichier de log des erreurs (niveau ERROR et plus)
        error_log_file = os.path.join(self.log_dir, "errors.log")
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)
        
        # Sortie console si activée
        if self.console_output:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Obtient un logger spécifique à un module
        
        Args:
            name: Nom du module ou composant
            
        Returns:
            Logger configuré
        """
        logger = logging.getLogger(name)
        
        # Appliquer le niveau personnalisé s'il existe
        if name in self.module_levels:
            logger.setLevel(self.module_levels[name])
            
        return logger
    
    def set_module_level(self, module_name: str, level: Union[int, str]):
        """
        Configurer un niveau de log spécifique pour un module
        
        Args:
            module_name: Nom du module
            level: Niveau de log (peut être un int ou une chaîne comme "DEBUG", "INFO")
        """
        # Convertir le niveau en int si c'est une chaîne
        if isinstance(level, str):
            level = getattr(logging, level.upper())
            
        self.module_levels[module_name] = level
        logging.getLogger(module_name).setLevel(level)
        self.logger.info(f"Niveau de log pour {module_name} configuré à {logging.getLevelName(level)}")
    
    def set_global_level(self, level: Union[int, str]):
        """
        Modifier le niveau de log global
        
        Args:
            level: Nouveau niveau de log
        """
        if isinstance(level, str):
            level = getattr(logging, level.upper())
            
        self.log_level = level
        logging.getLogger("").setLevel(level)
        self.logger.info(f"Niveau de log global configuré à {logging.getLevelName(level)}")
    
    def add_module_file_handler(self, module_name: str):
        """
        Ajouter un handler de fichier spécifique pour un module
        
        Args:
            module_name: Nom du module
        """
        logger = logging.getLogger(module_name)
        
        # Créer un fichier de log spécifique au module
        module_log_file = os.path.join(self.log_dir, f"{module_name}.log")
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        handler = logging.handlers.RotatingFileHandler(
            module_log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        self.logger.info(f"Handler de fichier spécifique ajouté pour {module_name}")

# Créer une instance singleton
_alfred_logger = None

def initialize(config: Optional[Dict] = None) -> AlfredLogger:
    """
    Initialise le système de journalisation avec la configuration donnée
    
    Args:
        config: Configuration optionnelle (niveau de log, répertoire, etc.)
        
    Returns:
        Instance du logger
    """
    global _alfred_logger
    
    if _alfred_logger is None:
        # Paramètres par défaut
        log_level = logging.INFO
        log_dir = "~/.alfred/logs"
        console_output = True
        max_file_size = 10 * 1024 * 1024  # 10 MB
        backup_count = 5
        
        # Appliquer la configuration si fournie
        if config:
            if "log_level" in config:
                level_str = config.get("log_level", "INFO")
                log_level = getattr(logging, level_str.upper()) if isinstance(level_str, str) else level_str
                
            log_dir = config.get("log_dir", log_dir)
            console_output = config.get("console_output", console_output)
            max_file_size = config.get("max_file_size", max_file_size)
            backup_count = config.get("backup_count", backup_count)
        
        _alfred_logger = AlfredLogger(
            log_level=log_level,
            log_dir=log_dir,
            console_output=console_output,
            max_file_size=max_file_size,
            backup_count=backup_count
        )
        
        # Configurer les niveaux par module si dans la config
        if config and "module_levels" in config:
            for module, level in config["module_levels"].items():
                _alfred_logger.set_module_level(module, level)
                
    return _alfred_logger

def get_logger(name: str) -> logging.Logger:
    """
    Fonction utilitaire pour obtenir un logger
    
    Args:
        name: Nom du module ou composant
        
    Returns:
        Logger configuré
    """
    global _alfred_logger
    
    # Initialiser avec les valeurs par défaut si pas encore fait
    if _alfred_logger is None:
        initialize()
        
    return _alfred_logger.get_logger(name)

# Fonctions utilitaires de logging de performances
def log_execution_time(func):
    """
    Décorateur pour mesurer et logger le temps d'exécution d'une fonction
    
    Args:
        func: La fonction à décorer
        
    Returns:
        Fonction décorée
    """
    import time
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Obtenir le nom du module parent
        module_name = func.__module__
        logger = get_logger(f"perf.{module_name}")
        
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        
        logger.info(f"{func.__qualname__} exécuté en {execution_time:.4f} secondes")
        return result
    
    return wrapper
