"""
Cooking Agent (O6) - Agent cuisinier personnalisé pour Alfred
Gère les recettes, enregistre les préférences, et propose des suggestions personnalisées
en tenant compte des ingrédients disponibles dans l'inventaire (sans filtrer strictement).
"""

import os
import json
import time
import threading
import logging
from typing import Dict, Any, List, Optional
from base_agent import BaseAgent
import redis
import json

# Connexion à Redis (adapter l'hôte si besoin)
redis_client = redis.Redis(host='localhost', port=6379, db=0)


logger = logging.getLogger("CookingAgent")

class CookingAgent(BaseAgent):
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379,
                 recipes_file: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__("o6", redis_host, redis_port)
        self.capabilities = [
            "recipe_management",        # Gestion des recettes
            "personalized_suggestions", # Suggestions personnalisées
            "preferences_storage"       # Stockage des préférences culinaires
        ]
        
        # Charger la configuration spécifique à l'agent cuisinier
        self.config = config or {}
        
        # Fichier de recettes (JSON)
        self.recipes_file = recipes_file or os.path.join("alfred", "config", "recipes.json")
        self.recipes: List[Dict[str, Any]] = self._load_recipes()
        
        # Charger l'inventaire depuis la configuration ou initialiser une liste vide
        # Cet inventaire représente les ingrédients disponibles dans votre frigo ou placard
        self.inventory: List[str] = self.config.get("inventory", [])
        
        # Préférences utilisateur (allergies, goûts, etc.)
        self.user_preferences: Dict[str, Any] = {}
        self.pref_lock = threading.Lock()
        
        logger.info(f"CookingAgent initialisé avec {len(self.recipes)} recettes et un inventaire de {len(self.inventory)} ingrédients.")
    
    def _load_recipes(self) -> List[Dict[str, Any]]:
        """Charge les recettes depuis un fichier JSON. Si le fichier n'existe pas, retourne une liste vide."""
        if os.path.exists(self.recipes_file):
            try:
                with open(self.recipes_file, "r", encoding="utf-8") as f:
                    recipes = json.load(f)
                logger.info(f"{len(recipes)} recettes chargées depuis {self.recipes_file}")
                return recipes
            except Exception as e:
                logger.error(f"Erreur lors du chargement des recettes : {e}")
        else:
            logger.warning(f"Fichier de recettes non trouvé : {self.recipes_file}")
        return []
    
    def _save_recipes(self) -> None:
        """Sauvegarde les recettes dans le fichier JSON."""
        try:
            os.makedirs(os.path.dirname(self.recipes_file), exist_ok=True)
            with open(self.recipes_file, "w", encoding="utf-8") as f:
                json.dump(self.recipes, f, indent=4, ensure_ascii=False)
            logger.info(f"Recettes sauvegardées dans {self.recipes_file}")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des recettes : {e}")
    
    def update_inventory(self, new_inventory: List[str]) -> Dict[str, Any]:
        """Met à jour l'inventaire des ingrédients disponibles."""
        with self.pref_lock:
            self.inventory = new_inventory
        return {"success": True, "message": "Inventaire mis à jour", "inventory": self.inventory}
    
    def _suggest_recipes(self) -> List[Dict[str, Any]]:
        """
        Propose des recettes en fonction de l'inventaire disponible.
        Au lieu de filtrer strictement, on calcule un score (match_score) pour chaque recette,
        correspondant au pourcentage d'ingrédients présents dans l'inventaire.
        """
        suggestions = []
        # Normaliser l'inventaire en minuscules
        inv = [item.lower() for item in self.inventory]
        for recipe in self.recipes:
            # On s'attend à ce que chaque recette contienne une liste d'ingrédients.
            recipe_ing = [ing.lower() for ing in recipe.get("ingredients", [])]
            if recipe_ing:
                # Compter le nombre d'ingrédients présents dans l'inventaire
                available = sum(1 for ing in recipe_ing if any(inv_item in ing for inv_item in inv))
                match_score = available / len(recipe_ing)
            else:
                match_score = 0.0
            # Ajouter le score à la recette
            recipe_with_score = recipe.copy()
            recipe_with_score["match_score"] = match_score
            suggestions.append(recipe_with_score)
        
        # Trier les recettes par score décroissant (les recettes avec un score élevé en premier)
        suggestions.sort(key=lambda r: r.get("match_score", 0), reverse=True)
        return suggestions
    
    def _search_recipes(self, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Recherche des recettes en fonction de critères.
        Exemple de critères : {"ingredient": "poulet", "type": "plat principal"}
        """
        results = []
        for recipe in self.recipes:
            match = True
            for key, value in criteria.items():
                # Pour les critères sur la liste d'ingrédients, on fait une recherche partielle
                if key == "ingredients" and isinstance(value, list):
                    recipe_ingredients = [ing.lower() for ing in recipe.get("ingredients", [])]
                    for ingredient in value:
                        if ingredient.lower() not in recipe_ingredients:
                            match = False
                            break
                    if not match:
                        break
                else:
                    recipe_value = recipe.get(key, "")
                    if isinstance(recipe_value, list):
                        if not any(value.lower() in item.lower() for item in recipe_value):
                            match = False
                            break
                    else:
                        if value.lower() not in str(recipe_value).lower():
                            match = False
                            break
            if match:
                results.append(recipe)
        return results
    
    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite une commande reçue par l'agent cuisinier.
        Commandes supportées :
          - add_recipe : Ajouter une recette
          - get_recipe : Rechercher des recettes selon des critères
          - suggest_recipe : Proposer des recettes en fonction des ingrédients disponibles et préférences
          - update_preferences : Mettre à jour les préférences (allergies, goûts, etc.)
          - update_inventory : Mettre à jour l'inventaire des ingrédients disponibles
          - status_request : Retourner le statut de l'agent
        """
        cmd_type = command.get("type", "unknown")
        data = command.get("data", {})
        logger.info(f"CookingAgent traite la commande: {cmd_type}")
        
        if cmd_type in ["add_recipe", "add_recipe_o6"]:
            recipe = data.get("recipe")
            if not recipe:
                return {"success": False, "error": "Aucune recette fournie"}
            self.recipes.append(recipe)
            self._save_recipes()
            return {"success": True, "message": "Recette ajoutée"}
        
        elif cmd_type in ["get_recipe", "get_recipe_o6"]:
            criteria = data.get("criteria", {})
            matching_recipes = self._search_recipes(criteria)
            return {"success": True, "recipes": matching_recipes}
        
        elif cmd_type in ["suggest_recipe", "suggest_recipe_o6"]:
            suggestions = self._suggest_recipes()
            return {"success": True, "suggestions": suggestions}
        
        elif cmd_type in ["update_preferences", "update_preferences_o6"]:
            preferences = data.get("preferences", {})
            with self.pref_lock:
                self.user_preferences.update(preferences)
            return {"success": True, "message": "Préférences mises à jour", "preferences": self.user_preferences}
        
        elif cmd_type in ["update_inventory", "update_inventory_o6"]:
            inventory = data.get("inventory", [])
            return self.update_inventory(inventory)
        
        elif cmd_type == "status_request":
            return {"status": "ready", "capabilities": self.capabilities, "recipes_count": len(self.recipes), "inventory": self.inventory}
        
        else:
            logger.warning(f"Commande non supportée: {cmd_type}")
            return {"success": False, "message": f"Commande non supportée: {cmd_type}"}

if __name__ == "__main__":
    # Exemple de test en standalone de l'agent cuisinier
    # Charger la configuration pour le module cuisinier depuis config.json
    import os
    config_path = os.path.join("alfred", "config", "config.json")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            global_config = json.load(f)
            config = global_config.get("cooking", {})
    
    agent = CookingAgent(config=config)
    agent.start()
    
    # 1. Ajouter ces méthodes à la classe CookingAgent:

    def setup_redis_listener(self):
        """Configure et démarre l'écoute des messages Redis pour l'agent."""
        self.redis_pubsub = self.redis_client.pubsub()
        self.redis_pubsub.subscribe(f"{self.agent_id}:notifications")
        self.redis_listener_thread = threading.Thread(target=self._redis_listener_loop, daemon=True)
        self.redis_listener_thread.start()
        self.logger.info(f"Agent {self.agent_id} en écoute sur le canal {self.agent_id}:notifications")

    def _redis_listener_loop(self):
        """Boucle d'écoute infinie pour les messages Redis."""
        if not self.redis_client:
            self.logger.error("Redis non connecté, impossible de démarrer l'écoute")
            return
        
        self.logger.info(f"Démarrage de la boucle d'écoute Redis pour {self.agent_id}")
        
        try:
            for message in self.redis_pubsub.listen():
                if not self.running:
                    break
                    
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        self.logger.info(f"Message Redis reçu: {data.get('type', 'unknown')}")
                        self._handle_redis_message(data)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Erreur décodage JSON du message Redis: {e}")
                    except Exception as e:
                        self.logger.error(f"Erreur traitement message Redis: {e}")
        except Exception as e:
            self.logger.error(f"Erreur dans la boucle d'écoute Redis: {e}")
        finally:
            self.logger.info("Arrêt de la boucle d'écoute Redis")

    def _handle_redis_message(self, message):
        """Traite un message reçu via Redis."""
        msg_type = message.get('type', 'unknown')
        data = message.get('data', {})
        
        self.logger.info(f"Traitement message Redis: {msg_type}")
        
        # Actions spécifiques selon le type de message
        if msg_type == 'direct_command':
            # Traiter les commandes directes
            if 'command' in data:
                command = data['command']
                self.process_command(command)
        elif msg_type == 'recipe_request':
            # Rechercher des recettes
            criteria = data.get('criteria', {})
            reply_to = data.get('reply_to', 'orchestrator')
            result = self.process_command({"type": "get_recipe", "data": {"criteria": criteria}})
            self.send_redis_message(f"{reply_to}:notifications", 'recipe_result', result)
        elif msg_type == 'inventory_update':
            # Mettre à jour l'inventaire
            new_inventory = data.get('inventory', [])
            if new_inventory:
                result = self.update_inventory(new_inventory)
                reply_to = data.get('reply_to', 'orchestrator')
                self.send_redis_message(f"{reply_to}:notifications", 'inventory_updated', result)
        elif msg_type == 'notification':
            # Traiter les notifications
            self.log_activity('redis_notification', data)
        else:
            self.logger.warning(f"Type de message Redis non reconnu: {msg_type}")

    def send_redis_message(self, channel, message_type, data):
        """Envoie un message via Redis sur un canal spécifique."""
        if not self.redis_client:
            self.logger.warning("Redis non connecté, message non envoyé")
            return False
        
        message = {
            'type': message_type,
            'sender': self.agent_id,
            'timestamp': time.time(),
            'data': data
        }
        
        try:
            self.redis_client.publish(channel, json.dumps(message))
            self.logger.info(f"Message Redis envoyé sur {channel}: {message_type}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur envoi message Redis: {e}")
            return False

    # 2. Ajouter une méthode on_start:
    def on_start(self) -> None:
        """Actions à effectuer lors du démarrage de l'agent."""
        self.broadcast_message("agent_online", {
            "agent_type": "cooking",
            "capabilities": self.capabilities
        })
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities,
            "recipes_count": len(self.recipes)
        })
        self.setup_redis_listener()
        self.logger.info("Agent cuisinier (O6) démarré")

    # 3. Ajouter une méthode on_stop:
    def on_stop(self) -> None:
        """Actions à effectuer lors de l'arrêt de l'agent."""
        # Arrêter l'écoute Redis
        if hasattr(self, 'redis_pubsub'):
            self.redis_pubsub.unsubscribe()
            
        self.broadcast_message("agent_offline", {
            "agent_type": "cooking",
            "shutdown_time": time.time()
        })
        self.logger.info("Agent cuisinier (O6) arrêté")


    # Mise à jour de l'inventaire pour refléter vos ingrédients disponibles
    update_inv_cmd = {
        "type": "update_inventory",
        "data": {
            "inventory": ["saké", "sauce teriyaki", "poulet", "riz", "lait de coco"]
        }
    }
    print("Mise à jour de l'inventaire :", agent.process_command(update_inv_cmd))
    
    # Ajout d'une recette qui utilise des ingrédients spécifiques (recette asiatique)
    add_recipe_cmd = {
        "type": "add_recipe",
        "data": {
            "recipe": {
                "id": "recette_asiatique_1",
                "name": "Poulet Teriyaki",
                "ingredients": ["poulet", "sauce teriyaki", "saké", "miel", "ail", "gingembre"],
                "instructions": "Faire mariner le poulet dans la sauce teriyaki, le saké, le miel, l'ail et le gingembre. Puis cuire au four.",
                "type": "plat principal",
                "allergy_info": []
            }
        }
    }
    print("Ajout d'une recette :", agent.process_command(add_recipe_cmd))
    
    # Suggestion de recettes en tenant compte des ingrédients disponibles
    suggest_cmd = {
        "type": "suggest_recipe",
        "data": {}
    }
    print("Suggestions de recettes :", agent.process_command(suggest_cmd))
    
    agent.stop()
