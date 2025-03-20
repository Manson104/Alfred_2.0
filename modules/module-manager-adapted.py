"""
Module Manager pour Alfred - Version adaptée pour la nouvelle architecture

Ce composant est responsable de:
- Découvrir les modules, agents et providers disponibles sur GitHub
- Télécharger et installer les composants à la demande
- Gérer le cache local et les sauvegardes
- Gérer les dépendances entre composants
- Fournir des mécanismes de fallback quand le réseau est indisponible
"""

import os
import sys
import json
import hashlib
import shutil
import tempfile
import time
from datetime import datetime
import threading
import schedule
import requests
import importlib.util
from typing import Dict, List, Optional, Tuple, Any, Union, Set

from utils.logger import get_logger, log_execution_time

# Configuration du logger
logger = get_logger("ModuleManager")

class ModuleManager:
    """Gère la découverte, le téléchargement, et le cycle de vie des composants Alfred"""
    
    def __init__(self, 
                 github_org: str = "alfred-project", 
                 base_path: str = "~/.alfred",
                 sync_time: str = "03:00"):
        """
        Initialise le Module Manager
        
        Args:
            github_org: Organisation ou utilisateur GitHub hébergeant les composants
            base_path: Répertoire de base pour les données Alfred
            sync_time: Heure de synchronisation nocturne (format 24h)
        """
        self.github_org = github_org
        self.base_path = os.path.expanduser(base_path)
        self.sync_time = sync_time
        
        # Créer la structure de répertoires si elle n'existe pas
        self.cache_dir = os.path.join(self.base_path, "cache")
        self.backup_dir = os.path.join(self.base_path, "backups")
        self.config_file = os.path.join(self.base_path, "components.json")
        
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Registre des composants: stocke les métadonnées de tous les composants disponibles
        self.registry = self._load_registry()
        
        # Composants actuellement chargés: nom -> objet module
        self.loaded_components = {}
        
        # Objets d'instance pour les agents et modules actifs
        self.component_instances = {}
        
        # Démarrer le planificateur pour les synchronisations nocturnes
        self._setup_scheduler()
        
        logger.info(f"ModuleManager initialisé avec chemin de base: {self.base_path}")

    def _load_registry(self) -> Dict:
        """Charge le registre des composants depuis le disque ou en crée un nouveau"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Fichier de registre corrompu: {self.config_file}")
                # Sauvegarder le fichier corrompu
                backup_name = f"components.json.corrupted.{int(time.time())}"
                shutil.copy(self.config_file, os.path.join(self.base_path, backup_name))
        
        # Retourner un registre vide si le fichier n'existe pas ou est corrompu
        return {
            "components": {},
            "last_sync": None,
            "github_org": self.github_org
        }

    def _save_registry(self) -> None:
        """Sauvegarde le registre des composants sur le disque"""
        with open(self.config_file, 'w') as f:
            json.dump(self.registry, f, indent=2)
        logger.debug("Registre sauvegardé sur le disque")

    def _setup_scheduler(self) -> None:
        """Configure le planificateur pour la synchronisation nocturne"""
        schedule.every().day.at(self.sync_time).do(self.sync_all_components)
        
        # Démarrer le planificateur dans un thread en arrière-plan
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)  # Vérifier chaque minute
                
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info(f"Planificateur démarré, synchronisation nocturne programmée pour {self.sync_time}")

    @log_execution_time
    def discover_available_components(self, force_refresh: bool = False) -> Dict:
        """
        Découvre les composants disponibles sur GitHub
        
        Args:
            force_refresh: Si True, ignore le cache et vérifie GitHub même si récemment vérifié
            
        Returns:
            Dictionnaire des composants disponibles avec métadonnées
        """
        # Vérifier si la synchronisation est récente (dernière heure) sauf si force_refresh est True
        last_sync = self.registry.get("last_sync")
        if last_sync and not force_refresh:
            last_sync_time = datetime.fromisoformat(last_sync)
            if (datetime.now() - last_sync_time).total_seconds() < 3600:  # 1 heure
                logger.info("Utilisation de la liste de composants en cache (synchronisée dans la dernière heure)")
                return self.registry["components"]
        
        try:
            # Lister les dépôts dans l'organisation GitHub
            # Dans une implémentation réelle, cela utiliserait l'API GitHub
            response = requests.get(f"https://api.github.com/orgs/{self.github_org}/repos")
            
            if response.status_code != 200:
                logger.error(f"Échec de récupération des dépôts: {response.status_code}")
                # Revenir aux données en cache
                return self.registry["components"]
                
            repos = response.json()
            
            # Traiter chaque dépôt pour voir s'il s'agit d'un composant Alfred
            for repo in repos:
                repo_name = repo["name"]
                
                # Traiter uniquement les dépôts suivant la convention de nommage
                if (repo_name.startswith("alfred-module-") or 
                    repo_name.startswith("alfred-agent-") or 
                    repo_name.startswith("alfred-provider-")):
                    
                    # Déterminer le type de composant
                    if repo_name.startswith("alfred-module-"):
                        component_type = "module"
                    elif repo_name.startswith("alfred-agent-"):
                        component_type = "agent"
                    else:
                        component_type = "provider"
                    
                    # Extraire l'ID du composant
                    component_id = repo_name.split("-", 2)[2] if len(repo_name.split("-")) > 2 else repo_name
                    
                    # Obtenir les métadonnées du composant (généralement depuis un fichier metadata.json)
                    try:
                        metadata_url = f"https://raw.githubusercontent.com/{self.github_org}/{repo_name}/main/metadata.json"
                        metadata_response = requests.get(metadata_url)
                        
                        if metadata_response.status_code == 200:
                            metadata = metadata_response.json()
                            
                            # Ajouter au registre avec infos additionnelles
                            self.registry["components"][component_id] = {
                                "name": metadata.get("name", repo_name),
                                "description": metadata.get("description", ""),
                                "version": metadata.get("version", "0.1.0"),
                                "repo_url": repo["html_url"],
                                "component_type": component_type,
                                "dependencies": metadata.get("dependencies", []),
                                "provides": metadata.get("provides", []),
                                "category": metadata.get("category", "general"),
                                "last_updated": repo["updated_at"]
                            }
                            logger.info(f"Découvert {component_type}: {component_id}")
                    except Exception as e:
                        logger.error(f"Erreur lors du traitement du dépôt {repo_name}: {str(e)}")
            
            # Mettre à jour l'heure de dernière synchronisation
            self.registry["last_sync"] = datetime.now().isoformat()
            self._save_registry()
            
            return self.registry["components"]
            
        except Exception as e:
            logger.error(f"Erreur lors de la découverte des composants: {str(e)}", exc_info=True)
            return self.registry["components"]  # Retourner les données en cache
            
    @log_execution_time
    def download_component(self, component_id: str, version: Optional[str] = None) -> bool:
        """
        Télécharge un composant spécifique depuis GitHub
        
        Args:
            component_id: ID du composant à télécharger
            version: Version spécifique à télécharger, ou dernière si None
            
        Returns:
            True si succès, False sinon
        """
        if component_id not in self.registry["components"]:
            # Tenter de découvrir si le composant est inconnu
            self.discover_available_components()
            
            if component_id not in self.registry["components"]:
                logger.error(f"Composant inconnu: {component_id}")
                return False
        
        component_info = self.registry["components"][component_id]
        component_type = component_info["component_type"]
        
        # Déterminer la version à télécharger
        target_version = version or component_info["version"]
        
        try:
            # Créer un répertoire temporaire pour le téléchargement
            with tempfile.TemporaryDirectory() as temp_dir:
                # Dans une implémentation réelle, cela téléchargerait un zip depuis une release GitHub ou un tag spécifique
                # Pour simplifier, cet exemple utilise un téléchargement direct depuis la branche main
                
                # Déterminer l'URL de téléchargement (simplifié)
                repo_name = f"alfred-{component_type}-{component_id}"
                download_url = f"https://github.com/{self.github_org}/{repo_name}/archive/refs/heads/main.zip"
                
                # Télécharger le fichier zip
                zip_path = os.path.join(temp_dir, f"{component_id}.zip")
                response = requests.get(download_url, stream=True)
                
                if response.status_code != 200:
                    logger.error(f"Échec du téléchargement du composant {component_id}: {response.status_code}")
                    return False
                    
                with open(zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Extraire le fichier zip
                import zipfile
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Déplacer vers le répertoire cache
                component_cache_dir = os.path.join(self.cache_dir, component_id)
                if os.path.exists(component_cache_dir):
                    shutil.rmtree(component_cache_dir)
                
                # Trouver le répertoire extrait
                extracted_dir = None
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isdir(item_path) and item != "__MACOSX":  # Ignorer les métadonnées macOS
                        extracted_dir = item_path
                        break
                
                if not extracted_dir:
                    logger.error(f"Impossible de trouver le contenu extrait pour {component_id}")
                    return False
                
                shutil.move(extracted_dir, component_cache_dir)
                
                # Mettre à jour le registre local avec les infos de téléchargement
                self.registry["components"][component_id]["locally_available"] = True
                self.registry["components"][component_id]["local_path"] = component_cache_dir
                self.registry["components"][component_id]["download_time"] = datetime.now().isoformat()
                self._save_registry()
                
                logger.info(f"Téléchargement réussi du composant {component_id} version {target_version}")
                
                # Vérifier et télécharger les dépendances
                dependencies = component_info.get("dependencies", [])
                if dependencies:
                    logger.info(f"Résolution des dépendances pour {component_id}: {dependencies}")
                    for dep_id in dependencies:
                        if dep_id not in self.registry["components"] or not self.registry["components"][dep_id].get("locally_available", False):
                            logger.info(f"Téléchargement de la dépendance: {dep_id}")
                            self.download_component(dep_id)
                
                return True
                
        except Exception as e:
            logger.error(f"Erreur lors du téléchargement du composant {component_id}: {str(e)}", exc_info=True)
            return False

    @log_execution_time
    def load_component(self, component_id: str, **kwargs) -> Any:
        """
        Charge un composant en mémoire pour pouvoir l'utiliser
        
        Args:
            component_id: ID du composant à charger
            **kwargs: Arguments supplémentaires à passer au composant
            
        Returns:
            L'objet du composant chargé, ou None si échec
        """
        # Vérifier si déjà chargé
        if component_id in self.loaded_components:
            logger.debug(f"Composant {component_id} déjà chargé")
            return self.loaded_components[component_id]
            
        # Vérifier si le composant est dans le registre et disponible localement
        if component_id not in self.registry["components"]:
            logger.error(f"Composant inconnu: {component_id}")
            return None
            
        component_info = self.registry["components"][component_id]
        
        if not component_info.get("locally_available", False):
            # Tenter de télécharger le composant
            if not self.download_component(component_id):
                logger.error(f"Le composant {component_id} n'est pas disponible localement et le téléchargement a échoué")
                return None
                
        # Vérifier les dépendances
        dependencies = self._resolve_dependencies(component_id)
        if dependencies is None:
            logger.error(f"Impossible de résoudre les dépendances pour {component_id}")
            return None
            
        # Charger toutes les dépendances d'abord
        for dep_id in dependencies:
            if not self.is_component_loaded(dep_id):
                if not self.load_component(dep_id):
                    logger.error(f"Échec du chargement de la dépendance {dep_id} pour le composant {component_id}")
                    return None
        
        try:
            # Déterminer le fichier principal du module
            module_path = component_info["local_path"]
            main_file = os.path.join(module_path, "main.py")
            
            if not os.path.exists(main_file):
                # Chercher un autre fichier principal
                for filename in os.listdir(module_path):
                    if filename.endswith(".py") and filename != "__init__.py":
                        main_file = os.path.join(module_path, filename)
                        break
            
            if not os.path.exists(main_file):
                logger.error(f"Impossible de trouver le fichier principal pour le composant {component_id}")
                return None
                
            # Charger le module
            spec = importlib.util.spec_from_file_location(component_id, main_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[component_id] = module
            spec.loader.exec_module(module)
            
            # Stocker dans les composants chargés
            self.loaded_components[component_id] = module
            
            # Créer une instance si c'est un agent ou un module
            component_type = component_info["component_type"]
            if component_type in ["agent", "module"]:
                # Vérifier la fonction d'initialisation appropriée
                if component_type == "agent" and hasattr(module, "start_agent"):
                    # Les agents ont normalement besoin de message_bus et state_manager
                    if "message_bus" in kwargs and "state_manager" in kwargs:
                        instance = module.start_agent(
                            message_bus=kwargs["message_bus"],
                            state_manager=kwargs["state_manager"],
                            agent_config=kwargs.get("config", {})
                        )
                        if instance:
                            self.component_instances[component_id] = instance
                    else:
                        logger.warning(f"Agent {component_id} chargé mais non instancié (message_bus ou state_manager manquant)")
                
                elif component_type == "module" and hasattr(module, "initialize_module"):
                    instance = module.initialize_module(
                        module_id=component_id,
                        config=kwargs.get("config", {})
                    )
                    if instance:
                        self.component_instances[component_id] = instance
            
            # Initialiser le module s'il a une fonction init
            elif hasattr(module, "init"):
                module.init()
                
            logger.info(f"Composant {component_id} chargé avec succès")
            return module
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement du composant {component_id}: {str(e)}", exc_info=True)
            return None

    def unload_component(self, component_id: str) -> bool:
        """
        Décharge un composant de la mémoire
        
        Args:
            component_id: ID du composant à décharger
            
        Returns:
            True si succès, False sinon
        """
        if component_id not in self.loaded_components:
            logger.warning(f"Composant {component_id} non chargé")
            return False
            
        try:
            # Récupérer les informations sur le composant
            component_info = self.registry["components"].get(component_id, {})
            component_type = component_info.get("component_type", "unknown")
            
            # Nettoyer l'instance si c'est un agent ou un module
            if component_id in self.component_instances:
                instance = self.component_instances[component_id]
                
                if component_type == "agent" and hasattr(self.loaded_components[component_id], "stop_agent"):
                    # Arrêter l'agent
                    self.loaded_components[component_id].stop_agent(instance)
                
                elif component_type == "module" and hasattr(self.loaded_components[component_id], "cleanup_module"):
                    # Nettoyer le module
                    self.loaded_components[component_id].cleanup_module(instance)
                
                # Supprimer l'instance
                del self.component_instances[component_id]
            
            # Appeler la fonction de nettoyage si elle existe
            module = self.loaded_components[component_id]
            if hasattr(module, "cleanup"):
                module.cleanup()
                
            # Supprimer des composants chargés et de sys.modules
            del self.loaded_components[component_id]
            if component_id in sys.modules:
                del sys.modules[component_id]
                
            logger.info(f"Composant {component_id} déchargé avec succès")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors du déchargement du composant {component_id}: {str(e)}", exc_info=True)
            return False

    def is_component_loaded(self, component_id: str) -> bool:
        """Vérifie si un composant est actuellement chargé"""
        return component_id in self.loaded_components

    def get_component_instance(self, component_id: str) -> Any:
        """
        Récupère l'instance d'un composant
        
        Args:
            component_id: ID du composant
            
        Returns:
            L'instance du composant ou None si non disponible
        """
        return self.component_instances.get(component_id)

    def _resolve_dependencies(self, component_id: str) -> Optional[List[str]]:
        """
        Résout les dépendances d'un composant dans l'ordre correct
        
        Args:
            component_id: ID du composant
            
        Returns:
            Liste ordonnée des dépendances à charger, ou None si impossible à résoudre
        """
        if component_id not in self.registry["components"]:
            logger.error(f"Composant inconnu: {component_id}")
            return None
            
        # Récupérer les dépendances directes
        direct_deps = self.registry["components"][component_id].get("dependencies", [])
        
        if not direct_deps:
            return []
            
        # Résoudre l'ordre de chargement (tri topologique)
        resolved = []
        visited = set()
        temp_marked = set()
        
        def visit(cid):
            if cid in temp_marked:
                logger.error(f"Dépendance circulaire détectée pour {cid}")
                return False
                
            if cid not in visited:
                temp_marked.add(cid)
                
                # Visiter toutes les dépendances de ce composant
                if cid in self.registry["components"]:
                    deps = self.registry["components"][cid].get("dependencies", [])
                    for dep in deps:
                        if not visit(dep):
                            return False
                            
                temp_marked.remove(cid)
                visited.add(cid)
                resolved.append(cid)
                
            return True
            
        # Visiter chaque dépendance
        for dep in direct_deps:
            if not visit(dep):
                return None
                
        return resolved

    @log_execution_time
    def sync_all_components(self) -> bool:
        """
        Effectue la synchronisation nocturne de tous les composants
        
        Returns:
            True si succès, False si une partie a échoué
        """
        logger.info("Début de la synchronisation nocturne des composants")
        
        try:
            # Découvrir les composants disponibles
            self.discover_available_components(force_refresh=True)
            
            # Créer un répertoire de sauvegarde daté
            backup_date = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(self.backup_dir, f"backup_{backup_date}")
            os.makedirs(backup_path, exist_ok=True)
            
            # Télécharger tous les composants qui ne sont pas déjà téléchargés ou qui ont besoin d'une mise à jour
            for component_id, component_info in self.registry["components"].items():
                # Ignorer si disponible localement et à jour
                if component_info.get("locally_available", False):
                    local_version = component_info.get("version", "0.0.0")
                    remote_version = component_info.get("version", "0.0.0")
                    
                    # Si les versions correspondent, ignorer le téléchargement
                    if local_version == remote_version:
                        logger.debug(f"Composant {component_id} à jour, téléchargement ignoré")
                        
                        # Copier quand même dans la sauvegarde
                        local_path = component_info.get("local_path")
                        if local_path and os.path.exists(local_path):
                            backup_component_path = os.path.join(backup_path, component_id)
                            shutil.copytree(local_path, backup_component_path)
                        
                        continue
                
                # Télécharger ou mettre à jour le composant
                if self.download_component(component_id):
                    # Copier dans la sauvegarde
                    local_path = self.registry["components"][component_id].get("local_path")
                    if local_path and os.path.exists(local_path):
                        backup_component_path = os.path.join(backup_path, component_id)
                        shutil.copytree(local_path, backup_component_path)
            
            # Sauvegarder le registre
            shutil.copy(self.config_file, os.path.join(backup_path, "components.json"))
            
            # Gérer la rotation des sauvegardes (conserver les 7 dernières)
            self._rotate_backups(max_backups=7)
            
            logger.info(f"Synchronisation des composants terminée, sauvegarde créée à {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur durant la synchronisation des composants: {str(e)}", exc_info=True)
            return False

    def _rotate_backups(self, max_backups: int = 7) -> None:
        """
        Effectue une rotation des sauvegardes, ne gardant que les plus récentes
        
        Args:
            max_backups: Nombre maximum de sauvegardes à conserver
        """
        backups = []
        for item in os.listdir(self.backup_dir):
            item_path = os.path.join(self.backup_dir, item)
            if os.path.isdir(item_path) and item.startswith("backup_"):
                backups.append((item_path, os.path.getctime(item_path)))
        
        # Trier par date de création (plus récentes d'abord)
        backups.sort(key=lambda x: x[1], reverse=True)
        
        # Supprimer les sauvegardes les plus anciennes au-delà de la limite
        for backup_path, _ in backups[max_backups:]:
            try:
                shutil.rmtree(backup_path)
                logger.debug(f"Ancienne sauvegarde supprimée: {backup_path}")
            except Exception as e:
                logger.error(f"Échec de la suppression de l'ancienne sauvegarde {backup_path}: {str(e)}")

    def use_fallback(self, component_id: str) -> bool:
        """
        Utilise une sauvegarde si la source en ligne est indisponible
        
        Args:
            component_id: ID du composant à restaurer depuis la sauvegarde
            
        Returns:
            True si succès, False sinon
        """
        if component_id in self.registry["components"] and self.registry["components"][component_id].get("locally_available", False):
            # Déjà disponible localement
            return True
            
        try:
            # Trouver la sauvegarde la plus récente contenant ce composant
            latest_backup = None
            latest_time = 0
            
            for item in os.listdir(self.backup_dir):
                item_path = os.path.join(self.backup_dir, item)
                
                if os.path.isdir(item_path) and item.startswith("backup_"):
                    component_backup_path = os.path.join(item_path, component_id)
                    
                    if os.path.exists(component_backup_path):
                        backup_time = os.path.getctime(item_path)
                        if backup_time > latest_time:
                            latest_time = backup_time
                            latest_backup = component_backup_path
            
            if not latest_backup:
                logger.error(f"Aucune sauvegarde trouvée pour le composant {component_id}")
                return False
                
            # Copier depuis la sauvegarde vers le cache
            component_cache_dir = os.path.join(self.cache_dir, component_id)
            if os.path.exists(component_cache_dir):
                shutil.rmtree(component_cache_dir)
                
            shutil.copytree(latest_backup, component_cache_dir)
            
            # Mettre à jour le registre
            # Si le composant n'a jamais été dans le registre, ajouter une entrée minimale
            if component_id not in self.registry["components"]:
                self.registry["components"][component_id] = {
                    "name": component_id,
                    "description": "Restauré depuis une sauvegarde",
                    "version": "unknown",
                    "component_type": "unknown",
                    "from_backup": True
                }
                
            self.registry["components"][component_id]["locally_available"] = True
            self.registry["components"][component_id]["local_path"] = component_cache_dir
            self.registry["components"][component_id]["fallback_used"] = True
            self.registry["components"][component_id]["fallback_time"] = datetime.now().isoformat()
            self._save_registry()
            
            logger.info(f"Composant {component_id} restauré avec succès depuis la sauvegarde")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de l'utilisation du fallback pour le composant {component_id}: {str(e)}", exc_info=True)
            return False

    def get_component_info(self, component_id: str) -> Dict:
        """Récupère les informations détaillées sur un composant"""
        if component_id not in self.registry["components"]:
            return {"error": "Composant non trouvé"}
            
        return self.registry["components"][component_id]

    def list_available_components(self, component_type: Optional[str] = None, category: Optional[str] = None) -> List[Dict]:
        """
        Liste tous les composants disponibles
        
        Args:
            component_type: Filtrer par type ('agent', 'module', 'provider') si spécifié
            category: Filtrer par catégorie si spécifiée
            
        Returns:
            Liste des dictionnaires d'informations sur les composants
        """
        components = []
        
        for component_id, info in self.registry["components"].items():
            if component_type and info.get("component_type") != component_type:
                continue
                
            if category and info.get("category") != category:
                continue
                
            components.append({
                "id": component_id,
                "name": info.get("name", component_id),
                "description": info.get("description", ""),
                "version": info.get("version", "unknown"),
                "type": info.get("component_type", "unknown"),
                "category": info.get("category", "general"),
                "locally_available": info.get("locally_available", False),
                "dependencies": info.get("dependencies", [])
            })
            
        return components

    def get_component_dependencies(self, component_id: str) -> Dict:
        """
        Obtient les informations complètes sur les dépendances d'un composant
        
        Args:
            component_id: ID du composant
            
        Returns:
            Dictionnaire avec les dépendances et leur statut
        """
        if component_id not in self.registry["components"]:
            return {"error": "Composant non trouvé"}
            
        component_info = self.registry["components"][component_id]
        dependencies = component_info.get("dependencies", [])
        
        # Construire l'arbre de dépendances
        dependency_tree = {}
        for dep_id in dependencies:
            dependency_tree[dep_id] = {
                "available": dep_id in self.registry["components"],
                "locally_available": dep_id in self.registry["components"] and 
                                    self.registry["components"][dep_id].get("locally_available", False),
                "loaded": dep_id in self.loaded_components,
                "resolved": True,  # Par défaut, supposé résolu
                "sub_dependencies": []
            }
            
            # Récursion pour les sous-dépendances (un niveau seulement pour éviter les boucles)
            if dep_id in self.registry["components"]:
                sub_deps = self.registry["components"][dep_id].get("dependencies", [])
                dependency_tree[dep_id]["sub_dependencies"] = sub_deps
                
                # Vérifier si cette dépendance a des problèmes de résolution
                if any(sd not in self.registry["components"] for sd in sub_deps):
                    dependency_tree[dep_id]["resolved"] = False
        
        return {
            "component_id": component_id,
            "total_dependencies": len(dependencies),
            "all_resolved": all(info["resolved"] for info in dependency_tree.values()),
            "dependencies": dependency_tree
        }

    def create_component_metadata(self, component_id: str, component_type: str, 
                                 name: str, description: str, version: str = "0.1.0",
                                 category: str = "general", dependencies: List[str] = None) -> Dict:
        """
        Crée un fichier de métadonnées pour un nouveau composant
        
        Args:
            component_id: ID unique du composant
            component_type: Type du composant ('agent', 'module', 'provider')
            name: Nom lisible du composant
            description: Description du composant
            version: Version du composant
            category: Catégorie du composant
            dependencies: Liste des IDs de dépendances
            
        Returns:
            Dictionnaire des métadonnées créées
        """
        if dependencies is None:
            dependencies = []
            
        metadata = {
            "id": component_id,
            "name": name,
            "description": description,
            "version": version,
            "component_type": component_type,
            "category": category,
            "dependencies": dependencies,
            "creation_time": datetime.now().isoformat(),
            "last_update": datetime.now().isoformat()
        }
        
        # Structure du répertoire recommandée pour ce type de composant
        if component_type == "agent":
            metadata["structure"] = [
                "main.py",
                "README.md",
                "metadata.json",
                "requirements.txt"
            ]
        elif component_type == "module":
            metadata["structure"] = [
                "main.py",
                "README.md", 
                "metadata.json",
                "requirements.txt",
                "tests/"
            ]
        
        return metadata

# Exemple d'utilisation
if __name__ == "__main__":
    # Créer le gestionnaire de modules
    manager = ModuleManager()
    
    # Découvrir les composants disponibles
    components = manager.discover_available_components()
    print(f"Trouvé {len(components)} composants")
    
    # Lister les composants
    print("\nModules disponibles:")
    for component in manager.list_available_components(component_type="module"):
        print(f"- {component['id']} ({component['version']}): {component['description']}")
        
    print("\nAgents disponibles:")
    for component in manager.list_available_components(component_type="agent"):
        print(f"- {component['id']} ({component['version']}): {component['description']}")
        
    print("\nProviders disponibles:")
    for component in manager.list_available_components(component_type="provider"):
        print(f"- {component['id']} ({component['version']}): {component['description']}")
