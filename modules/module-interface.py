"""
Module Interface - Définit l'interface standard pour tous les modules

Ce module établit le contrat que tous les modules fonctionnels doivent respecter
pour être utilisables par les agents dans le système Alfred.
"""

import abc
from typing import Dict, Any, Optional, List, Union

from utils.logger import get_logger

logger = get_logger("modules.interface")

class ModuleInterface(abc.ABC):
    """
    Interface de base pour tous les modules fonctionnels.
    
    Un module est une bibliothèque de fonctionnalités qui peut être utilisée par plusieurs agents.
    Contrairement aux agents, les modules n'ont pas de logique autonome et répondent uniquement
    aux appels de méthodes.
    """
    
    def __init__(self, module_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialise un module
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration spécifique au module (optionnelle)
        """
        self.module_id = module_id
        self.config = config or {}
        self.logger = get_logger(f"modules.{self.module_id}")
        self.initialized = False
    
    @abc.abstractmethod
    def initialize(self) -> bool:
        """
        Initialise le module avec sa configuration
        
        Returns:
            True si l'initialisation est réussie, False sinon
        """
        pass
    
    @abc.abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Renvoie les capacités du module
        
        Returns:
            Dictionnaire des capacités et fonctionnalités offertes par le module
        """
        pass
    
    def cleanup(self) -> bool:
        """
        Nettoie les ressources utilisées par le module
        
        Returns:
            True si le nettoyage est réussi, False sinon
        """
        # Implémentation par défaut qui ne fait rien
        return True
    
    def get_dependencies(self) -> List[str]:
        """
        Renvoie la liste des dépendances du module
        
        Returns:
            Liste des IDs de modules dont dépend ce module
        """
        # Par défaut, aucune dépendance
        return []
    
    def is_initialized(self) -> bool:
        """
        Vérifie si le module est initialisé
        
        Returns:
            True si le module est initialisé, False sinon
        """
        return self.initialized

    def get_status(self) -> Dict[str, Any]:
        """
        Renvoie l'état actuel du module
        
        Returns:
            Dictionnaire contenant des informations sur l'état du module
        """
        return {
            "module_id": self.module_id,
            "initialized": self.initialized,
            "capabilities": self.get_capabilities() if self.initialized else {},
            "dependencies": self.get_dependencies()
        }


def create_module(module_id: str, config: Optional[Dict[str, Any]] = None) -> ModuleInterface:
    """
    Crée une instance de module avec la configuration donnée
    
    Cette fonction est appelée par le gestionnaire de modules lors du chargement d'un module
    et doit être implémentée par chaque module concret.
    
    Args:
        module_id: Identifiant unique du module
        config: Configuration spécifique au module
        
    Returns:
        Instance de module configurée
    """
    # Cette fonction doit être implémentée par chaque module concret
    # et retourner une instance correctement configurée
    raise NotImplementedError("Cette fonction doit être implémentée par le module concret")


def initialize_module(module_id: str, config: Optional[Dict[str, Any]] = None) -> Union[ModuleInterface, None]:
    """
    Initialise un module
    
    Cette fonction est appelée par le système lors du chargement d'un module.
    
    Args:
        module_id: Identifiant unique du module
        config: Configuration spécifique au module
        
    Returns:
        Instance de module initialisée ou None en cas d'échec
    """
    logger = get_logger("modules.loader")
    
    try:
        # Crée l'instance de module
        module = create_module(module_id, config)
        
        # Initialise le module
        if module.initialize():
            logger.info(f"Module {module_id} initialisé avec succès")
            return module
        else:
            logger.error(f"Échec de l'initialisation du module {module_id}")
            return None
            
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation du module {module_id}: {str(e)}", exc_info=True)
        return None


def cleanup_module(module_instance: ModuleInterface) -> bool:
    """
    Nettoie les ressources utilisées par un module
    
    Cette fonction est appelée par le système lors du déchargement d'un module.
    
    Args:
        module_instance: L'instance de module à nettoyer
        
    Returns:
        True si le nettoyage est réussi, False sinon
    """
    logger = get_logger("modules.loader")
    
    try:
        if module_instance and hasattr(module_instance, 'cleanup'):
            module_id = getattr(module_instance, 'module_id', 'unknown_module')
            if module_instance.cleanup():
                logger.info(f"Module {module_id} nettoyé avec succès")
                return True
            else:
                logger.error(f"Échec du nettoyage du module {module_id}")
                return False
        return True
    except Exception as e:
        logger.error(f"Erreur lors du nettoyage du module: {str(e)}", exc_info=True)
        return False
