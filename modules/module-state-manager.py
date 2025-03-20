"""
core/state_manager.py
--------------------
Gestionnaire d'état centralisé pour Alfred.
Permet aux agents d'accéder et de modifier un état partagé.
Implémente le pattern Observer pour notifier les changements.
"""

import json
import time
import threading
import logging
from typing import Dict, Any, List, Optional, Callable, Set, Tuple, Union

# Configuration du logger
logger = logging.getLogger("StateManager")

class StateChange:
    """Représente un changement d'état pour observer les modifications."""
    
    def __init__(self, path: str, old_value: Any, new_value: Any, timestamp: float = None):
        """
        Initialise un changement d'état.
        
        Args:
            path: Chemin de la donnée modifiée (notation point)
            old_value: Ancienne valeur
            new_value: Nouvelle valeur
            timestamp: Horodatage du changement
        """
        self.path = path
        self.old_value = old_value
        self.new_value = new_value
        self.timestamp = timestamp or time.time()

class StateManager:
    """
    Gestionnaire d'état centralisé pour le système Alfred.
    Maintient un état partagé et notifie les changements aux observateurs.
    """
    
    def __init__(self, persistence_file: Optional[str] = None):
        """
        Initialise le gestionnaire d'état.
        
        Args:
            persistence_file: Fichier pour la persistance (si None, état en mémoire uniquement)
        """
        self.state: Dict[str, Any] = {}
        self.persistence_file = persistence_file
        self.observers: Dict[str, List[Callable[[StateChange], None]]] = {}
        self.lock = threading.RLock()
        
        # Charger l'état initial depuis le fichier de persistence si spécifié
        if persistence_file:
            self._load_state()
    
    def _load_state(self) -> None:
        """Charge l'état depuis le fichier de persistence."""
        try:
            import os
            if os.path.exists(self.persistence_file):
                with open(self.persistence_file, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
                logger.info(f"État chargé depuis {self.persistence_file}")
        except Exception as e:
            logger.error(f"Erreur lors du chargement de l'état: {e}")
    
    def _save_state(self) -> None:
        """Sauvegarde l'état dans le fichier de persistence."""
        if not self.persistence_file:
            return
            
        try:
            with open(self.persistence_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
            logger.debug(f"État sauvegardé dans {self.persistence_file}")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de l'état: {e}")
    
    def get(self, path: str, default: Any = None) -> Any:
        """
        Récupère une valeur de l'état.
        
        Args:
            path: Chemin de la donnée (notation point)
            default: Valeur par défaut si le chemin n'existe pas
            
        Returns:
            Valeur à l'emplacement spécifié ou valeur par défaut
        """
        with self.lock:
            try:
                parts = path.split(".")
                current = self.state
                
                for part in parts:
                    if part not in current:
                        return default
                    current = current[part]
                    
                return current
            except Exception as e:
                logger.error(f"Erreur lors de la récupération de {path}: {e}")
                return default
    
    def set(self, path: str, value: Any, save: bool = True) -> bool:
        """
        Définit une valeur dans l'état.
        
        Args:
            path: Chemin de la donnée (notation point)
            value: Valeur à définir
            save: Si True, sauvegarde l'état après modification
            
        Returns:
            True si la valeur a été définie, False sinon
        """
        with self.lock:
            try:
                parts = path.split(".")
                current = self.state
                
                # Naviguer jusqu'au parent du dernier élément
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                
                # Récupérer l'ancienne valeur pour notifier le changement
                old_value = current.get(parts[-1])
                current[parts[-1]] = value
                
                # Notifier les observateurs
                change = StateChange(path, old_value, value)
                self._notify_observers(change)
                
                # Sauvegarder si demandé
                if save and self.persistence_file:
                    self._save_state()
                    
                return True
            except Exception as e:
                logger.error(f"Erreur lors de la définition de {path}: {e}")
                return False
    
    def update(self, data: Dict[str, Any], base_path: str = "", save: bool = True) -> bool:
        """
        Met à jour plusieurs valeurs en une seule opération.
        
        Args:
            data: Dictionnaire des valeurs à mettre à jour
            base_path: Chemin de base pour les données
            save: Si True, sauvegarde l'état après modification
            
        Returns:
            True si toutes les valeurs ont été mises à jour, False sinon
        """
        success = True
        with self.lock:
            try:
                for key, value in data.items():
                    path = f"{base_path}.{key}" if base_path else key
                    
                    if isinstance(value, dict):
                        # Récursivité pour les valeurs imbriquées
                        success = success and self.update(value, path, False)
                    else:
                        # Définir directement les valeurs non-dictionnaires
                        success = success and self.set(path, value, False)
                
                # Sauvegarder une seule fois à la fin si demandé
                if save and self.persistence_file and success:
                    self._save_state()
                    
                return success
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour de données: {e}")
                return False
    
    def delete(self, path: str, save: bool = True) -> bool:
        """
        Supprime une valeur de l'état.
        
        Args:
            path: Chemin de la donnée à supprimer
            save: Si True, sauvegarde l'état après suppression
            
        Returns:
            True si la valeur a été supprimée, False sinon
        """
        with self.lock:
            try:
                parts = path.split(".")
                current = self.state
                
                # Naviguer jusqu'au parent du dernier élément
                for part in parts[:-1]:
                    if part not in current:
                        return False
                    current = current[part]
                
                # Vérifier que le dernier élément existe
                if parts[-1] not in current:
                    return False
                
                # Récupérer l'ancienne valeur pour notifier le changement
                old_value = current[parts[-1]]
                
                # Supprimer l'élément
                del current[parts[-1]]
                
                # Notifier les observateurs
                change = StateChange(path, old_value, None)
                self._notify_observers(change)
                
                # Sauvegarder si demandé
                if save and self.persistence_file:
                    self._save_state()
                    
                return True
            except Exception as e:
                logger.error(f"Erreur lors de la suppression de {path}: {e}")
                return False
    
    def add_observer(self, path: str, callback: Callable[[StateChange], None]) -> None:
        """
        Ajoute un observateur pour les changements à un chemin spécifique.
        
        Args:
            path: Chemin à observer (ou "" pour tous les chemins)
            callback: Fonction à appeler lors d'un changement
        """
        with self.lock:
            if path not in self.observers:
                self.observers[path] = []
            self.observers[path].append(callback)
            logger.debug(f"Observateur ajouté pour {path}")
    
    def remove_observer(self, path: str, callback: Callable[[StateChange], None]) -> None:
        """
        Supprime un observateur spécifique.
        
        Args:
            path: Chemin observé
            callback: Fonction à supprimer
        """
        with self.lock:
            if path in self.observers and callback in self.observers[path]:
                self.observers[path].remove(callback)
                if not self.observers[path]:
                    del self.observers[path]
                logger.debug(f"Observateur supprimé pour {path}")
    
    def _notify_observers(self, change: StateChange) -> None:
        """
        Notifie les observateurs d'un changement.
        
        Args:
            change: Changement d'état
        """
        to_notify = []
        
        # Trouver tous les observateurs applicables
        with self.lock:
            # Observateurs du chemin exact
            if change.path in self.observers:
                to_notify.extend(self.observers[change.path])
            
            # Observateurs des chemins parents
            parts = change.path.split(".")
            for i in range(1, len(parts)):
                parent_path = ".".join(parts[:-i])
                if parent_path in self.observers:
                    to_notify.extend(self.observers[parent_path])
            
            # Observateurs globaux
            if "" in self.observers:
                to_notify.extend(self.observers[""])
        
        # Notifier sans le verrou pour éviter les deadlocks
        for callback in to_notify:
            try:
                callback(change)
            except Exception as e:
                logger.error(f"Erreur dans un callback d'observateur: {e}")
    
    def get_full_state(self) -> Dict[str, Any]:
        """
        Récupère une copie complète de l'état.
        
        Returns:
            Copie de l'état complet
        """
        with self.lock:
            import copy
            return copy.deepcopy(self.state)
    
    def get_state_branch(self, base_path: str) -> Dict[str, Any]:
        """
        Récupère une branche spécifique de l'état.
        
        Args:
            base_path: Chemin de base
            
        Returns:
            Sous-arbre de l'état
        """
        result = self.get(base_path)
        if isinstance(result, dict):
            import copy
            return copy.deepcopy(result)
        return {}
    
    def clear(self, save: bool = True) -> None:
        """
        Efface tout l'état.
        
        Args:
            save: Si True, sauvegarde l'état après effacement
        """
        with self.lock:
            old_state = self.state
            self.state = {}
            
            # Notifier pour chaque élément racine
            for key in old_state:
                change = StateChange(key, old_state[key], None)
                self._notify_observers(change)
            
            # Sauvegarder si demandé
            if save and self.persistence_file:
                self._save_state()
