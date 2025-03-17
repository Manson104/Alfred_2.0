import os
import logging
import json

class ModuleManager:
    def __init__(self):
        # Chargement de la configuration des modules depuis modules.json
        config_file = os.path.join(os.path.dirname(__file__), "modules.json")
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                self.modules_config = json.load(f)
        else:
            self.modules_config = {}
    
    def install_module(self, module_name):
        """Installe un module en récupérant son dépôt GitHub (simulation)."""
        if module_name in self.modules_config:
            modules_dir = os.path.join(os.path.dirname(__file__), "modules")
            if not os.path.exists(modules_dir):
                os.makedirs(modules_dir)
            module_file = os.path.join(modules_dir, f"{module_name}.py")
            if os.path.exists(module_file):
                logging.info(f"Le module {module_name} est déjà installé.")
            else:
                # Ici, on simule l'installation en créant un fichier de module basique.
                with open(module_file, "w") as f:
                    f.write(
                        f"def run():\n"
                        f"    print('Module {module_name} exécuté.')\n"
                    )
                logging.info(f"✅ Module installé : {module_name}")
        else:
            logging.warning(f"⚠️ Module {module_name} non trouvé dans la configuration.")
    
    def update_modules(self):
        """Met à jour les modules installés (simulation)."""
        logging.info("🔄 Mise à jour des modules...")
        # Implémentation simulée de la mise à jour
        logging.info("✅ Tous les modules ont été mis à jour.")
    
    def uninstall_module(self, module_name):
        """Désinstalle un module en supprimant son fichier dans le dossier modules."""
        modules_dir = os.path.join(os.path.dirname(__file__), "modules")
        module_file = os.path.join(modules_dir, f"{module_name}.py")
        if os.path.exists(module_file):
            try:
                os.remove(module_file)
                logging.info(f"✅ Module désinstallé : {module_name}")
                return True
            except Exception as e:
                logging.error(f"❌ Erreur lors de la désinstallation du module {module_name}: {e}")
                return False
        else:
            logging.warning(f"⚠️ Le module {module_name} n'est pas installé.")
            return False
