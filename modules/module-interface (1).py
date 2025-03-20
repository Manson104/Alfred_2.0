"""
module_interface.py: Définit l'interface standard pour tous les modules du système Alfred
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from utils.logger import get_logger

class ModuleMetadata:
    """Métadonnées décrivant un module."""
    
    def __init__(self, 
                 name: str, 
                 version: str, 
                 description: str, 
                 author: str,
                 dependencies: List[str] = None,
                 provides: List[str] = None):
        self.name = name
        self.version = version
        self.description = description
        self.author = author
        self.dependencies = dependencies or []
        self.provides = provides or []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit les métadonnées en dictionnaire."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "dependencies": self.dependencies,
            "provides": self.provides
        }

class ModuleInterface(ABC):
    """Interface abstraite pour tous les modules du système."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.logger = get_logger(self.__class__.__name__)
        self.config = config or {}
        self.is_initialized = False
        self.logger.info(f"Module {self.get_metadata().name} v{self.get_metadata().version} instancié")
    
    @classmethod
    @abstractmethod
    def get_metadata(cls) -> ModuleMetadata:
        """Retourne les métadonnées du module."""
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialise le module avec ses ressources nécessaires."""
        self.is_initialized = True