try:
                    module_import = importlib.import_module(module_name)
                    
                    # Rechercher les classes qui implémentent ModuleInterface
                    for name, obj in module_import.__dict__.items():
                        if (inspect.isclass(obj) and issubclass(obj, ModuleInterface) and 
                            obj != ModuleInterface):
                            try:
                                # Instancier temporairement pour obtenir le nom
                                temp_instance = obj()
                                module_actual_name = temp_instance.name
                                discovered[module_actual_name] = obj
                                logger.info(f"Module découvert: {module_actual_name} ({module_name}.{name})")
                            except Exception as e:
                                logger.warning(f"Erreur lors de l'instanciation de {module_name}.{name}: {e}")
                
                except Exception as e:
                    logger.error(f"Erreur lors de la découverte du module {module_name}: {e}")
        
        self.module_classes.update(discovered)
        return discovered
    
    def load_module(self, module_name: str) -> Optional[ModuleInterface]:
        """
        Charge un module spécifique.
        
        Args:
            module_name: Nom du module à charger
            
        Returns:
            Instance du module ou None si le chargement échoue
        """
        # Vérifier si le module est déjà chargé
        if module_name in self.modules:
            logger.warning(f"Module {module_name} déjà chargé")
            return self.modules[module_name]
        
        # Rechercher la classe du module si elle n'est pas déjà connue
        if module_name not in self.module_classes:
            self.discover_modules()
            
            if module_name not in self.module_classes:
                logger.error(f"Module {module_name} introuvable")
                return None
        
        try:
            # Instancier le module
            module_class = self.module_classes[module_name]
            module = module_class()
            
            # Charger la configuration du module
            module_config = self.config.get("modules", {}).get(module_name, {})
            
            # Stocker l'instance
            self.modules[module_name] = module
            logger.info(f"Module {module_name} chargé")
            
            return module
        except Exception as e:
            logger.error(f"Erreur lors du chargement du module {module_name}: {e}")
            return None
    
    def activate_module(self, module_name: str) -> bool:
        """
        Active un module et ses dépendances.
        
        Args:
            module_name: Nom du module à activer
            
        Returns:
            True si l'activation réussit, False sinon
        """
        # Vérifier si le module est déjà actif
        if module_name in self.active_modules:
            logger.warning(f"Module {module_name} déjà actif")
            return True
        
        # Charger le module s'il n'est pas déjà chargé
        if module_name not in self.modules:
            module = self.load_module(module_name)
            if not module:
                logger.error(f"Module {module_name} introuvable")
                return False
        else:
            module = self.modules[module_name]
        
        # Activer les dépendances
        for dependency in module.dependencies:
            if not self.activate_module(dependency):
                logger.error(f"Erreur lors de l'activation de la dépendance {dependency} pour {module_name}")
                return False
        
        # Initialiser le module
        if not module.initialize():
            logger.error(f"Erreur lors de l'initialisation du module {module_name}")
            return False
        
        # Marquer le module comme actif
        self.active_modules.add(module_name)
        logger.info(f"Module {module_name} activé")
        
        return True
    
    def deactivate_module(self, module_name: str) -> bool:
        """
        Désactive un module.
        
        Args:
            module_name: Nom du module à désactiver
            
        Returns:
            True si la désactivation réussit, False sinon
        """
        # Vérifier si le module est actif
        if module_name not in self.active_modules:
            logger.warning(f"Module {module_name} déjà inactif")
            return True
        
        # Vérifier si le module est une dépendance d'autres modules actifs
        dependent_modules = [m for m in self.active_modules if 
                            module_name in self.modules[m].dependencies]
        
        if dependent_modules:
            logger.error(f"Module {module_name} ne peut pas être désactivé car il est utilisé par: {dependent_modules}")
            return False
        
        # Désactiver le module
        module = self.modules[module_name]
        if not module.shutdown():
            logger.error(f"Erreur lors de l'arrêt du module {module_name}")
            return False
        
        # Retirer le module des modules actifs
        self.active_modules.remove(module_name)
        logger.info(f"Module {module_name} désactivé")
        
        return True
    
    def reload_module(self, module_name: str) -> bool:
        """
        Recharge un module.
        
        Args:
            module_name: Nom du module à recharger
            
        Returns:
            True si le rechargement réussit, False sinon
        """
        # Vérifier si le module est actif
        was_active = module_name in self.active_modules
        
        # Désactiver le module s'il est actif
        if was_active and not self.deactivate_module(module_name):
            logger.error(f"Erreur lors de la désactivation du module {module_name} pour rechargement")
            return False
        
        # Réinitialiser le module
        if module_name in self.modules:
            del self.modules[module_name]
        
        # Recharger le module
        module = self.load_module(module_name)
        if not module:
            logger.error(f"Erreur lors du rechargement du module {module_name}")
            return False
        
        # Réactiver le module s'il était actif
        if was_active and not self.activate_module(module_name):
            logger.error(f"Erreur lors de la réactivation du module {module_name} après rechargement")
            return False
        
        logger.info(f"Module {module_name} rechargé avec succès")
        return True
    
    def get_module(self, module_name: str) -> Optional[ModuleInterface]:
        """
        Récupère une instance de module.
        
        Args:
            module_name: Nom du module
            
        Returns:
            Instance du module ou None si le module n'est pas chargé
        """
        if module_name not in self.modules:
            logger.warning(f"Module {module_name} non chargé")
            return None
        
        return self.modules[module_name]
    
    def is_module_active(self, module_name: str) -> bool:
        """
        Vérifie si un module est actif.
        
        Args:
            module_name: Nom du module
            
        Returns:
            True si le module est actif, False sinon
        """
        return module_name in self.active_modules
    
    def get_module_status(self, module_name: str) -> Dict[str, Any]:
        """
        Récupère le statut d'un module.
        
        Args:
            module_name: Nom du module
            
        Returns:
            Dictionnaire contenant le statut du module
        """
        if module_name not in self.module_classes:
            return {"name": module_name, "available": False, "loaded": False, "active": False}
        
        loaded = module_name in self.modules
        active = module_name in self.active_modules
        
        status = {
            "name": module_name,
            "available": True,
            "loaded": loaded,
            "active": active
        }
        
        if loaded:
            module = self.modules[module_name]
            status.update({
                "version": module.version,
                "dependencies": module.dependencies,
                "capabilities": module.get_capabilities()
            })
        
        return status
    
    def start_all_modules(self) -> Tuple[int, int]:
        """
        Charge et active tous les modules disponibles.
        
        Returns:
            Tuple (modules chargés, modules activés)
        """
        # Découvrir les modules disponibles
        self.discover_modules()
        
        loaded_count = 0
        activated_count = 0
        
        # Charger et activer chaque module
        for module_name in self.module_classes:
            if module_name not in self.modules:
                if self.load_module(module_name):
                    loaded_count += 1
            
            if module_name not in self.active_modules:
                if self.activate_module(module_name):
                    activated_count += 1
        
        logger.info(f"{loaded_count} modules chargés, {activated_count} modules activés")
        return loaded_count, activated_count
    
    def stop_all_modules(self) -> int:
        """
        Désactive tous les modules actifs.
        
        Returns:
            Nombre de modules désactivés
        """
        deactivated_count = 0
        
        # Désactiver chaque module dans l'ordre inverse des dépendances
        while self.active_modules:
            # Trouver un module sans dépendants
            independent_module = None
            for module_name in list(self.active_modules):
                dependent_modules = [m for m in self.active_modules if 
                                    module_name in self.modules[m].dependencies]
                if not dependent_modules:
                    independent_module = module_name
                    break
            
            if not independent_module:
                # En cas de dépendances circulaires, prendre le premier module
                independent_module = next(iter(self.active_modules))
            
            # Désactiver le module
            if self.deactivate_module(independent_module):
                deactivated_count += 1
            else:
                # Skip to next module if we can't deactivate this one
                self.active_modules.remove(independent_module)
        
        logger.info(f"{deactivated_count} modules désactivés")
        return deactivated_count
    
    def get_all_modules_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Récupère le statut de tous les modules.
        
        Returns:
            Dictionnaire des statuts (nom du module -> statut)
        """
        # Découvrir les modules disponibles
        self.discover_modules()
        
        statuses = {}
        for module_name in self.module_classes:
            statuses[module_name] = self.get_module_status(module_name)
        
        return statuses
