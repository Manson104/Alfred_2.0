import os
import time
import json
import logging
from base_agent import BaseAgent
from json_stories_extractor import load_local_stories, fetch_rss_stories, get_story_by_keyword
import redis
import json

    redis_client = redis.Redis(host='localhost', port=6379, db=0)

    def handle_message(message):
        action = message.get("action")
        if action == "tell_story":
            # ta logique pour raconter ou générer une histoire
            send_response('orchestrator', {"status": "success", "action": "tell_story"})

    def send_response(channel, message):
        redis_client.publish(channel, json.dumps(message))

    pubsub = redis_client.pubsub()
    pubsub.subscribe('agent_koba')

    print("Agent Koba en écoute...")
    for message in pubsub.listen():
        if message['type'] == 'message':
            data = json.loads(message['data'].decode('utf-8'))
            handle_message(data)


# Connexion à Redis (adapter l'hôte si besoin)
redis_client = redis.Redis(host='localhost', port=6379, db=0)


# Pour l'exemple, nous utiliserons une fonction fictive pour GPT
def generate_story_with_gpt(prompt: str) -> str:
    """
    Génère une histoire via GPT (fonction fictive pour l'exemple).
    
    Args:
        prompt: Prompt de génération.
    
    Returns:
        Une histoire générée en texte.
    """
    # Ici, vous appelleriez votre API GPT (par exemple OpenAI)
    # Pour l'exemple, nous retournons un texte statique.
    return f"Histoire générée à partir du prompt '{prompt}': Il était une fois..."

class KobaAgent(BaseAgent):
    """
    Agent Koba pour la gestion des histoires destinées aux enfants.
    Il recherche dans la base locale, dans les flux RSS, puis génère via GPT si nécessaire.
    """
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379, config: dict = None):
        super().__init__("koba", redis_host, redis_port)
        self.capabilities = [
            "story_retrieval",
            "story_generation",
            "favorites_management"
        ]
        # Chemins pour les ressources (à adapter)
        self.local_stories_dir = "data/stories"  # dossier contenant des fichiers JSON d'histoires
        self.rss_urls = [
            "https://www.ebookids.com/feed.xml", 
            "https://www.culturecheznous.gouv.fr/plus-de-1-000-livres-jeunesse-gratuits-litterature-jeunesse-libre"
        ]
        self.config = config or {}
        self.favorites_file = "data/koba_favorites.json"
        # Charger les histoires locales dès le démarrage
        self.local_stories = load_local_stories(self.local_stories_dir)
        self.logger.info("Agent Koba initialisé")

    def on_start(self) -> None:
        self.broadcast_message("agent_online", {
            "agent_type": "koba",
            "capabilities": self.capabilities
        })
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities
        })
        self.logger.info("Agent Koba démarré")

    def on_stop(self) -> None:
        self.broadcast_message("agent_offline", {
            "agent_type": "koba",
            "shutdown_time": time.time()
        })
        self.logger.info("Agent Koba arrêté")

    def get_story(self, keyword: str) -> dict:
        """
        Cherche une histoire basée sur un mot-clé.
        Priorité : recherche locale > flux RSS > génération via GPT
        
        Args:
            keyword: Mot-clé pour la recherche.
        
        Returns:
            Dictionnaire contenant l'histoire.
        """
        # 1. Recherche dans la base locale
        story = get_story_by_keyword(self.local_stories, keyword)
        if story:
            self.logger.info("Histoire trouvée dans la base locale")
            return {"source": "local", "story": story}

        # 2. Recherche dans les flux RSS
        for rss_url in self.rss_urls:
            rss_stories = fetch_rss_stories(rss_url)
            story = get_story_by_keyword(rss_stories, keyword)
            if story:
                self.logger.info(f"Histoire trouvée via RSS {rss_url}")
                return {"source": "rss", "story": story}

        # 3. Génération via GPT
        self.logger.info("Aucune histoire trouvée, génération via GPT")
        generated_text = generate_story_with_gpt(f"Raconte une histoire pour enfants avec le thème {keyword}")
        story = {
            "title": f"Histoire sur {keyword}",
            "content": generated_text,
            "generated_at": time.time()
        }
        return {"source": "gpt", "story": story}

    def add_to_favorites(self, story: dict) -> bool:
        """
        Ajoute une histoire aux favoris.
        
        Args:
            story: Dictionnaire de l'histoire.
        
        Returns:
            bool: Succès de l'opération.
        """
        favorites = []
        if os.path.exists(self.favorites_file):
            with open(self.favorites_file, "r", encoding="utf-8") as f:
                try:
                    favorites = json.load(f)
                except json.JSONDecodeError:
                    favorites = []

        favorites.append(story)
        try:
            with open(self.favorites_file, "w", encoding="utf-8") as f:
                json.dump(favorites, f, indent=4, ensure_ascii=False)
            self.logger.info("Histoire ajoutée aux favoris")
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de l'ajout aux favoris: {e}")
            return False

    def get_favorites(self) -> List[dict]:
        """
        Récupère la liste des histoires favorites.
        
        Returns:
            Liste de dictionnaires.
        """
        if os.path.exists(self.favorites_file):
            try:
                with open(self.favorites_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Erreur lors du chargement des favoris: {e}")
        return []

    def process_command(self, command: dict) -> dict:
        """
        Traite une commande spécifique à Koba.
        Les commandes possibles incluent :
         - get_story: recherche une histoire avec un mot-clé.
         - add_favorite: ajoute une histoire aux favoris.
         - get_favorites: récupère la liste des favoris.
        
        Args:
            command: Commande à traiter.
        
        Returns:
            Dictionnaire de résultat.
        """
        command_type = command.get("type", "")
        data = command.get("data", {})

        if command_type in ["get_story", "get_story_koba"]:
            keyword = data.get("keyword", "")
            if not keyword:
                return {"success": False, "error": "Mot-clé manquant"}
            story_info = self.get_story(keyword)
            return {"success": True, "result": story_info}

        elif command_type in ["add_favorite", "add_favorite_koba"]:
            story = data.get("story")
            if not story:
                return {"success": False, "error": "Aucune histoire fournie"}
            success = self.add_to_favorites(story)
            return {"success": success}

        elif command_type in ["get_favorites", "get_favorites_koba"]:
            favorites = self.get_favorites()
            return {"success": True, "result": favorites}

        else:
            self.logger.warning(f"Commande inconnue pour Koba: {command_type}")
            return {"success": False, "error": f"Commande inconnue: {command_type}"}

    def process_broadcast(self, message: dict) -> None:
        """
        Traite un message broadcast.
        Pour l'instant, nous répondons uniquement aux demandes de statut.
        """
        msg_type = message.get("type", "")
        if msg_type == "status_request":
            self.send_command("orchestrator", "status_update", {
                "status": "ready",
                "capabilities": self.capabilities
            })

# 1. Ajouter ces méthodes à la classe KobaAgent:

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
    elif msg_type == 'story_request':
        # Rechercher une histoire
        keyword = data.get('keyword', '')
        reply_to = data.get('reply_to', 'orchestrator')
        
        if keyword:
            result = self.process_command({
                "type": "get_story", 
                "data": {"keyword": keyword}
            })
        else:
            result = {'success': False, 'error': 'Mot-clé manquant'}
            
        self.send_redis_message(f"{reply_to}:notifications", 'story_result', result)
    elif msg_type == 'favorites_request':
        # Récupérer les histoires favorites
        reply_to = data.get('reply_to', 'orchestrator')
        result = self.process_command({"type": "get_favorites", "data": {}})
        self.send_redis_message(f"{reply_to}:notifications", 'favorites_result', result)
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

# 2. Modifier la méthode on_start pour ajouter l'appel à setup_redis_listener:
def on_start(self) -> None:
    self.broadcast_message("agent_online", {
        "agent_type": "koba",
        "capabilities": self.capabilities
    })
    self.send_command("orchestrator", "status_update", {
        "status": "ready",
        "capabilities": self.capabilities
    })
    self.setup_redis_listener()
    self.logger.info("Agent Koba démarré")

# 3. Modifier la méthode on_stop pour fermer proprement l'écoute Redis:
def on_stop(self) -> None:
    # Arrêter l'écoute Redis
    if hasattr(self, 'redis_pubsub'):
        self.redis_pubsub.unsubscribe()
        
    self.broadcast_message("agent_offline", {
        "agent_type": "koba",
        "shutdown_time": time.time()
    })
    self.logger.info("Agent Koba arrêté")


# Pour les tests, vous pouvez ajouter un main local
if __name__ == "__main__":
    # Exemple de test en mode CLI
    koba = KobaAgent()
    koba.on_start()
    
    # Simulation d'une commande pour obtenir une histoire sur "cuisine indienne"
    cmd = {"type": "get_story_koba", "data": {"keyword": "cuisine indienne"}}
    result = koba.process_command(cmd)
    print("Résultat de get_story_koba:")
    print(json.dumps(result, indent=4, ensure_ascii=False))
    
    # Simulation d'ajout aux favoris
    if result["success"]:
        story = result["result"]["story"]
        add_result = koba.process_command({"type": "add_favorite_koba", "data": {"story": story}})
        print("Ajout aux favoris:", add_result)
    
    # Simulation de récupération des favoris
    fav_result = koba.process_command({"type": "get_favorites_koba", "data": {}})
    print("Favoris:", json.dumps(fav_result, indent=4, ensure_ascii=False))
    
    koba.on_stop()
