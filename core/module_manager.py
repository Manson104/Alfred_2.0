"""
Module Manager for Alfred

This component is responsible for:
- Discovering available modules and agents on GitHub
- Downloading and installing modules on demand
- Managing local cache and backups
- Handling dependencies between modules
- Providing fallback mechanisms when network is unavailable
"""

import os
import sys
import json
import logging
import hashlib
import shutil
import tempfile
import time
from datetime import datetime
import threading
import schedule
import requests
import importlib.util
from typing import Dict, List, Optional, Tuple, Any, Union

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("alfred_module_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ModuleManager")

class ModuleManager:
    """Manages the discovery, download, and lifecycle of Alfred modules and agents"""
    
    def __init__(self, 
                 github_org: str = "alfred-project", 
                 base_path: str = "~/.alfred",
                 sync_time: str = "03:00"):
        """
        Initialize the Module Manager
        
        Args:
            github_org: GitHub organization or user where modules are hosted
            base_path: Base directory for Alfred data
            sync_time: Time for nightly synchronization (24h format)
        """
        self.github_org = github_org
        self.base_path = os.path.expanduser(base_path)
        self.sync_time = sync_time
        
        # Create directory structure if it doesn't exist
        self.cache_dir = os.path.join(self.base_path, "cache")
        self.backup_dir = os.path.join(self.base_path, "backups")
        self.config_file = os.path.join(self.base_path, "modules.json")
        
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Module registry: stores metadata about all available modules
        self.registry = self._load_registry()
        
        # Currently loaded modules: name -> module object
        self.loaded_modules = {}
        
        # Start the scheduler for nightly syncs
        self._setup_scheduler()
        
        logger.info(f"ModuleManager initialized with base path: {self.base_path}")

    def _load_registry(self) -> Dict:
        """Load the module registry from disk or create a new one"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Corrupted registry file: {self.config_file}")
                # Backup the corrupted file
                backup_name = f"modules.json.corrupted.{int(time.time())}"
                shutil.copy(self.config_file, os.path.join(self.base_path, backup_name))
        
        # Return empty registry if file doesn't exist or is corrupted
        return {
            "modules": {},
            "last_sync": None,
            "github_org": self.github_org
        }

    def _save_registry(self) -> None:
        """Save the module registry to disk"""
        with open(self.config_file, 'w') as f:
            json.dump(self.registry, f, indent=2)
        logger.debug("Registry saved to disk")

    def _setup_scheduler(self) -> None:
        """Set up the scheduler for nightly sync"""
        schedule.every().day.at(self.sync_time).do(self.sync_all_modules)
        
        # Start the scheduler in a background thread
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
                
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info(f"Scheduler started, nightly sync set for {self.sync_time}")

    def discover_available_modules(self, force_refresh: bool = False) -> Dict:
        """
        Discover available modules on GitHub
        
        Args:
            force_refresh: If True, bypass cache and check GitHub even if recently checked
            
        Returns:
            Dictionary of available modules with metadata
        """
        # Check if we've synced recently (within 1 hour) unless force_refresh is True
        last_sync = self.registry.get("last_sync")
        if last_sync and not force_refresh:
            last_sync_time = datetime.fromisoformat(last_sync)
            if (datetime.now() - last_sync_time).total_seconds() < 3600:  # 1 hour
                logger.info("Using cached module list (synced within the last hour)")
                return self.registry["modules"]
        
        try:
            # List repositories in the GitHub organization
            # In a real implementation, this would use GitHub API
            # Here's a simplified version showing the concept
            response = requests.get(f"https://api.github.com/orgs/{self.github_org}/repos")
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch repos: {response.status_code}")
                # Fall back to cached data
                return self.registry["modules"]
                
            repos = response.json()
            
            # Process each repository to see if it's an Alfred module
            for repo in repos:
                repo_name = repo["name"]
                
                # Only process repos that follow naming convention (alfred-module-* or alfred-agent-*)
                if repo_name.startswith("alfred-module-") or repo_name.startswith("alfred-agent-"):
                    # Get module metadata from the repo (typically from a module.json file)
                    try:
                        metadata_url = f"https://raw.githubusercontent.com/{self.github_org}/{repo_name}/main/module.json"
                        metadata_response = requests.get(metadata_url)
                        
                        if metadata_response.status_code == 200:
                            metadata = metadata_response.json()
                            
                            # Add to registry with additional info
                            module_id = metadata.get("id", repo_name)
                            self.registry["modules"][module_id] = {
                                "name": metadata.get("name", repo_name),
                                "description": metadata.get("description", ""),
                                "version": metadata.get("version", "0.1.0"),
                                "repo_url": repo["html_url"],
                                "dependencies": metadata.get("dependencies", []),
                                "type": "agent" if repo_name.startswith("alfred-agent-") else "module",
                                "last_updated": repo["updated_at"]
                            }
                    except Exception as e:
                        logger.error(f"Error processing repo {repo_name}: {str(e)}")
            
            # Update last sync time
            self.registry["last_sync"] = datetime.now().isoformat()
            self._save_registry()
            
            return self.registry["modules"]
            
        except Exception as e:
            logger.error(f"Error discovering modules: {str(e)}")
            return self.registry["modules"]  # Return cached data

    def download_module(self, module_id: str, version: Optional[str] = None) -> bool:
        """
        Download a specific module from GitHub
        
        Args:
            module_id: ID of the module to download
            version: Specific version to download, or latest if None
            
        Returns:
            True if successful, False otherwise
        """
        if module_id not in self.registry["modules"]:
            # Try to discover if we don't know about this module
            self.discover_available_modules()
            
            if module_id not in self.registry["modules"]:
                logger.error(f"Unknown module: {module_id}")
                return False
        
        module_info = self.registry["modules"][module_id]
        
        # Determine version to download
        target_version = version or module_info["version"]
        
        try:
            # Create a temp directory for download
            with tempfile.TemporaryDirectory() as temp_dir:
                # In real implementation, this would download a zip from GitHub release or a specific tag
                # For simplicity, this example uses a direct download from main branch
                
                # Determine download URL (this is simplified)
                repo_name = module_info["repo_url"].split("/")[-1]
                download_url = f"https://github.com/{self.github_org}/{repo_name}/archive/refs/heads/main.zip"
                
                # Download the zip file
                zip_path = os.path.join(temp_dir, f"{module_id}.zip")
                response = requests.get(download_url, stream=True)
                
                if response.status_code != 200:
                    logger.error(f"Failed to download module {module_id}: {response.status_code}")
                    return False
                    
                with open(zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Extract the zip file
                import zipfile
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Move to cache directory
                module_cache_dir = os.path.join(self.cache_dir, module_id)
                if os.path.exists(module_cache_dir):
                    shutil.rmtree(module_cache_dir)
                
                # Find the extracted directory (usually named with the repo name and branch)
                extracted_dir = None
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isdir(item_path) and item != "__MACOSX":  # Skip macOS metadata
                        extracted_dir = item_path
                        break
                
                if not extracted_dir:
                    logger.error(f"Failed to find extracted module content for {module_id}")
                    return False
                
                shutil.move(extracted_dir, module_cache_dir)
                
                # Update local registry with download information
                self.registry["modules"][module_id]["locally_available"] = True
                self.registry["modules"][module_id]["local_path"] = module_cache_dir
                self.registry["modules"][module_id]["download_time"] = datetime.now().isoformat()
                self._save_registry()
                
                logger.info(f"Successfully downloaded module {module_id} version {target_version}")
                return True
                
        except Exception as e:
            logger.error(f"Error downloading module {module_id}: {str(e)}")
            return False

    def load_module(self, module_id: str) -> Any:
        """
        Load a module into memory so it can be used
        
        Args:
            module_id: ID of the module to load
            
        Returns:
            The loaded module object, or None if loading failed
        """
        # Check if already loaded
        if module_id in self.loaded_modules:
            return self.loaded_modules[module_id]
            
        # Check if module is in registry and locally available
        if module_id not in self.registry["modules"]:
            logger.error(f"Unknown module: {module_id}")
            return None
            
        module_info = self.registry["modules"][module_id]
        
        if not module_info.get("locally_available", False):
            # Try to download the module
            if not self.download_module(module_id):
                logger.error(f"Module {module_id} is not locally available and download failed")
                return None
                
        # Check dependencies
        for dep in module_info.get("dependencies", []):
            if not self.is_module_loaded(dep):
                # Try to load dependency
                if not self.load_module(dep):
                    logger.error(f"Failed to load dependency {dep} for module {module_id}")
                    return None
        
        try:
            # Determine the main module file
            module_path = module_info["local_path"]
            main_file = os.path.join(module_path, "main.py")
            
            if not os.path.exists(main_file):
                # Try finding another main file
                for filename in os.listdir(module_path):
                    if filename.endswith(".py") and filename != "__init__.py":
                        main_file = os.path.join(module_path, filename)
                        break
            
            if not os.path.exists(main_file):
                logger.error(f"Could not find main file for module {module_id}")
                return None
                
            # Load the module
            spec = importlib.util.spec_from_file_location(module_id, main_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_id] = module
            spec.loader.exec_module(module)
            
            # Store in loaded modules
            self.loaded_modules[module_id] = module
            
            # Initialize the module if it has an init function
            if hasattr(module, "init"):
                module.init()
                
            logger.info(f"Successfully loaded module {module_id}")
            return module
            
        except Exception as e:
            logger.error(f"Error loading module {module_id}: {str(e)}")
            return None

    def unload_module(self, module_id: str) -> bool:
        """
        Unload a module from memory
        
        Args:
            module_id: ID of the module to unload
            
        Returns:
            True if successful, False otherwise
        """
        if module_id not in self.loaded_modules:
            logger.warning(f"Module {module_id} not loaded")
            return False
            
        try:
            # Call cleanup function if it exists
            module = self.loaded_modules[module_id]
            if hasattr(module, "cleanup"):
                module.cleanup()
                
            # Remove from loaded modules and sys.modules
            del self.loaded_modules[module_id]
            if module_id in sys.modules:
                del sys.modules[module_id]
                
            logger.info(f"Successfully unloaded module {module_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error unloading module {module_id}: {str(e)}")
            return False

    def is_module_loaded(self, module_id: str) -> bool:
        """Check if a module is currently loaded"""
        return module_id in self.loaded_modules

    def sync_all_modules(self) -> bool:
        """
        Perform nightly synchronization of all modules
        
        Returns:
            True if successful, False if any part failed
        """
        logger.info("Starting nightly module synchronization")
        
        try:
            # Discover available modules
            self.discover_available_modules(force_refresh=True)
            
            # Create a dated backup directory
            backup_date = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(self.backup_dir, f"backup_{backup_date}")
            os.makedirs(backup_path, exist_ok=True)
            
            # Download all modules that aren't already downloaded or need updating
            for module_id, module_info in self.registry["modules"].items():
                # Skip if locally available and up-to-date
                if module_info.get("locally_available", False):
                    local_version = module_info.get("version", "0.0.0")
                    remote_version = module_info.get("version", "0.0.0")
                    
                    # If versions match, skip download
                    if local_version == remote_version:
                        logger.debug(f"Module {module_id} is up-to-date, skipping download")
                        
                        # Still copy to backup
                        local_path = module_info.get("local_path")
                        if local_path and os.path.exists(local_path):
                            backup_module_path = os.path.join(backup_path, module_id)
                            shutil.copytree(local_path, backup_module_path)
                        
                        continue
                
                # Download or update the module
                if self.download_module(module_id):
                    # Copy to backup
                    local_path = self.registry["modules"][module_id].get("local_path")
                    if local_path and os.path.exists(local_path):
                        backup_module_path = os.path.join(backup_path, module_id)
                        shutil.copytree(local_path, backup_module_path)
            
            # Backup the registry
            shutil.copy(self.config_file, os.path.join(backup_path, "modules.json"))
            
            # Manage backup rotation (keep last 7 backups)
            self._rotate_backups(max_backups=7)
            
            logger.info(f"Module synchronization complete, backup created at {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error during module synchronization: {str(e)}")
            return False

    def _rotate_backups(self, max_backups: int = 7) -> None:
        """
        Rotate backups, keeping only the most recent ones
        
        Args:
            max_backups: Maximum number of backups to keep
        """
        backups = []
        for item in os.listdir(self.backup_dir):
            item_path = os.path.join(self.backup_dir, item)
            if os.path.isdir(item_path) and item.startswith("backup_"):
                backups.append((item_path, os.path.getctime(item_path)))
        
        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x[1], reverse=True)
        
        # Remove oldest backups beyond the limit
        for backup_path, _ in backups[max_backups:]:
            try:
                shutil.rmtree(backup_path)
                logger.debug(f"Removed old backup: {backup_path}")
            except Exception as e:
                logger.error(f"Failed to remove old backup {backup_path}: {str(e)}")

    def use_fallback(self, module_id: str) -> bool:
        """
        Use fallback from backups if online source is unavailable
        
        Args:
            module_id: ID of the module to restore from backup
            
        Returns:
            True if successful, False otherwise
        """
        if module_id in self.registry["modules"] and self.registry["modules"][module_id].get("locally_available", False):
            # Already available locally
            return True
            
        try:
            # Find the latest backup containing this module
            latest_backup = None
            latest_time = 0
            
            for item in os.listdir(self.backup_dir):
                item_path = os.path.join(self.backup_dir, item)
                
                if os.path.isdir(item_path) and item.startswith("backup_"):
                    module_backup_path = os.path.join(item_path, module_id)
                    
                    if os.path.exists(module_backup_path):
                        backup_time = os.path.getctime(item_path)
                        if backup_time > latest_time:
                            latest_time = backup_time
                            latest_backup = module_backup_path
            
            if not latest_backup:
                logger.error(f"No backup found for module {module_id}")
                return False
                
            # Copy from backup to cache
            module_cache_dir = os.path.join(self.cache_dir, module_id)
            if os.path.exists(module_cache_dir):
                shutil.rmtree(module_cache_dir)
                
            shutil.copytree(latest_backup, module_cache_dir)
            
            # Update registry
            # If module was never in registry, add minimal entry
            if module_id not in self.registry["modules"]:
                self.registry["modules"][module_id] = {
                    "name": module_id,
                    "description": "Restored from backup",
                    "version": "unknown",
                    "from_backup": True
                }
                
            self.registry["modules"][module_id]["locally_available"] = True
            self.registry["modules"][module_id]["local_path"] = module_cache_dir
            self.registry["modules"][module_id]["fallback_used"] = True
            self.registry["modules"][module_id]["fallback_time"] = datetime.now().isoformat()
            self._save_registry()
            
            logger.info(f"Successfully restored module {module_id} from backup")
            return True
            
        except Exception as e:
            logger.error(f"Error using fallback for module {module_id}: {str(e)}")
            return False

    def get_module_info(self, module_id: str) -> Dict:
        """Get detailed information about a module"""
        if module_id not in self.registry["modules"]:
            return {"error": "Module not found"}
            
        return self.registry["modules"][module_id]

    def list_available_modules(self, module_type: Optional[str] = None) -> List[Dict]:
        """
        List all available modules
        
        Args:
            module_type: Filter by type ("agent" or "module") if specified
            
        Returns:
            List of module information dictionaries
        """
        modules = []
        
        for module_id, info in self.registry["modules"].items():
            if module_type and info.get("type") != module_type:
                continue
                
            modules.append({
                "id": module_id,
                "name": info.get("name", module_id),
                "description": info.get("description", ""),
                "version": info.get("version", "unknown"),
                "type": info.get("type", "unknown"),
                "locally_available": info.get("locally_available", False)
            })
            
        return modules

# Example usage
if __name__ == "__main__":
    # Create module manager
    manager = ModuleManager()
    
    # Discover available modules
    modules = manager.discover_available_modules()
    print(f"Found {len(modules)} modules")
    
    # List modules
    for module in manager.list_available_modules():
        print(f"{module['id']} - {module['name']} ({module['version']})")
