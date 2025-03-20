"""
modules/ui_module.py
------------------
Module d'interface utilisateur pour Alfred.
Fournit différentes interfaces (web, CLI, API) pour interagir avec le système.
"""

import logging
import json
import threading
import time
from typing import Dict, Any, List, Optional, Callable
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver
from urllib.parse import parse_qs, urlparse

from modules.module_interface import ModuleInterface

class UIModule(ModuleInterface):
    """
    Module d'interface utilisateur fournissant différentes méthodes d'accès au système Alfred.
    Prend en charge une API REST, une interface web simple et une interface CLI.
    """
    
    def __init__(self, module_id: str, config: Dict[str, Any] = None):
        """
        Initialise le module d'interface utilisateur.
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration du module (optionnelle)
        """
        super().__init__(module_id, config)
        self.logger = logging.getLogger(f"ui.{module_id}")
        
        # Configuration par défaut
        self.default_config = {
            "http_enabled": True,
            "http_port": 8080,
            "http_host": "0.0.0.0",
            "cli_enabled": True,
            "web_enabled": True,
            "api_enabled": True
        }
        
        # Fusionner avec la configuration fournie
        self.config = {**self.default_config, **(config or {})}
        
        # État interne
        self.http_server = None
        self.http_thread = None
        self.cli_thread = None
        self.running = False
        self.routes = {}
        self.message_bus = None
        self.state_manager = None
    
    def initialize(self) -> bool:
        """
        Initialise le module d'interface utilisateur.
        
        Returns:
            True si l'initialisation est réussie, False sinon
        """
        self.logger.info("Initialisation du module d'interface utilisateur")
        
        # Récupérer les dépendances (message_bus et state_manager)
        self.message_bus = self.get_dependency("message_bus")
        self.state_manager = self.get_dependency("state_manager")
        
        if not self.message_bus or not self.state_manager:
            self.logger.error("MessageBus ou StateManager non disponible")
            return False
        
        # Enregistrer les routes de base
        self._register_default_routes()
        
        # Démarrer les interfaces activées
        if self.config["http_enabled"]:
            self._start_http_server()
        
        if self.config["cli_enabled"]:
            self._start_cli()
        
        self.running = True
        self.initialized = True
        return True
    
    def cleanup(self) -> bool:
        """
        Nettoie les ressources utilisées par le module.
        
        Returns:
            True si le nettoyage est réussi, False sinon
        """
        self.logger.info("Nettoyage du module d'interface utilisateur")
        self.running = False
        
        if self.http_server:
            self.http_server.shutdown()
            if self.http_thread and self.http_thread.is_alive():
                self.http_thread.join(timeout=3.0)
        
        return True
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Renvoie les capacités du module.
        
        Returns:
            Dictionnaire des capacités
        """
        return {
            "http_api": self.config["http_enabled"] and self.config["api_enabled"],
            "web_interface": self.config["http_enabled"] and self.config["web_enabled"],
            "cli": self.config["cli_enabled"]
        }
    
    def register_route(self, path: str, method: str, handler: Callable) -> None:
        """
        Enregistre une route HTTP pour l'API REST.
        
        Args:
            path: Chemin de la route (ex: "/api/status")
            method: Méthode HTTP (GET, POST, etc.)
            handler: Fonction de traitement de la requête
        """
        key = f"{method.upper()}:{path}"
        self.routes[key] = handler
        self.logger.debug(f"Route enregistrée: {key}")
    
    def _register_default_routes(self) -> None:
        """Enregistre les routes par défaut pour l'API."""
        # Route d'état du système
        self.register_route("/api/status", "GET", self._handle_status)
        
        # Route pour les commandes
        self.register_route("/api/command", "POST", self._handle_command)
        
        # Route pour les états
        self.register_route("/api/state", "GET", self._handle_get_state)
        self.register_route("/api/state", "POST", self._handle_set_state)
    
    def _start_http_server(self) -> None:
        """Démarre le serveur HTTP dans un thread séparé."""
        try:
            # Créer une classe de gestionnaire pour notre serveur HTTP
            ui_module = self  # Référence au module pour la classe interne
            
            class RequestHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self._handle_request("GET")
                
                def do_POST(self):
                    self._handle_request("POST")
                
                def _handle_request(self, method):
                    # Analyser le chemin et les paramètres
                    parsed_url = urlparse(self.path)
                    path = parsed_url.path
                    
                    # Rechercher la route correspondante
                    route_key = f"{method}:{path}"
                    
                    # Servir des fichiers statiques pour l'interface web
                    if method == "GET" and ui_module.config["web_enabled"] and path.startswith("/web/"):
                        self._serve_static_file(path[4:])  # Enlever '/web'
                        return
                    
                    # Vérifier si la route existe
                    if route_key in ui_module.routes:
                        handler = ui_module.routes[route_key]
                        
                        # Lire le corps de la requête pour les requêtes POST
                        body = None
                        if method == "POST":
                            content_length = int(self.headers.get('Content-Length', 0))
                            if content_length > 0:
                                body_bytes = self.rfile.read(content_length)
                                body = body_bytes.decode('utf-8')
                                try:
                                    body = json.loads(body)
                                except json.JSONDecodeError:
                                    # Si ce n'est pas du JSON, utiliser le corps tel quel
                                    pass
                        
                        # Préparer les paramètres pour le gestionnaire
                        params = {
                            'query': parse_qs(parsed_url.query),
                            'body': body,
                            'headers': dict(self.headers),
                            'method': method
                        }
                        
                        # Appeler le gestionnaire
                        try:
                            result = handler(params)
                            self.send_response(200)
                            self.send_header('Content-Type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps(result).encode('utf-8'))
                        except Exception as e:
                            ui_module.logger.error(f"Erreur dans le gestionnaire de route {path}: {str(e)}")
                            self.send_response(500)
                            self.send_header('Content-Type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                    else:
                        # Route non trouvée
                        self.send_response(404)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Route not found"}).encode('utf-8'))
                
                def _serve_static_file(self, path):
                    # Servir un fichier statique
                    # Dans une implémentation réelle, on servirait des fichiers depuis un répertoire
                    if path == "/" or path == "":
                        content = "<html><body><h1>Alfred Web Interface</h1><p>Welcome to Alfred!</p></body></html>"
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/html')
                        self.end_headers()
                        self.wfile.write(content.encode('utf-8'))
                    else:
                        self.send_response(404)
                        self.send_header('Content-Type', 'text/html')
                        self.end_headers()
                        self.wfile.write(b"<html><body><h1>404 Not Found</h1></body></html>")
                
                def log_message(self, format, *args):
                    ui_module.logger.debug(format % args)
            
            # Créer et démarrer le serveur HTTP dans un thread séparé
            server_address = (self.config["http_host"], self.config["http_port"])
            self.http_server = HTTPServer(server_address, RequestHandler)
            
            self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
            self.http_thread.start()
            
            self.logger.info(f"Serveur HTTP démarré sur {server_address[0]}:{server_address[1]}")
        
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage du serveur HTTP: {str(e)}")
    
    def _start_cli(self) -> None:
        """Démarre l'interface en ligne de commande dans un thread séparé."""
        self.cli_thread = threading.Thread(target=self._cli_loop, daemon=True)
        self.cli_thread.start()
        self.logger.info("Interface CLI démarrée")
    
    def _cli_loop(self) -> None:
        """Boucle principale de l'interface en ligne de commande."""
        self.logger.info("Entrez 'help' pour afficher les commandes disponibles")
        
        while self.running:
            try:
                command = input("Alfred> ")
                
                if not command:
                    continue
                
                if command.lower() == "exit" or command.lower() == "quit":
                    self.logger.info("Sortie de l'interface CLI")
                    break
                
                elif command.lower() == "help":
                    print("Commandes disponibles:")
                    print("  status  - Affiche l'état du système")
                    print("  send    - Envoie une commande (format: send topic message)")
                    print("  get     - Récupère un état (format: get state_path)")
                    print("  set     - Définit un état (format: set state_path value)")
                    print("  help    - Affiche cette aide")
                    print("  exit    - Quitte l'interface CLI")
                
                elif command.lower().startswith("status"):
                    # Obtenir l'état général du système
                    status = self._handle_status({})
                    print(json.dumps(status, indent=2))
                
                elif command.lower().startswith("send "):
                    # Format: send topic message
                    parts = command.split(" ", 2)
                    if len(parts) < 3:
                        print("Format incorrect. Utilisez: send topic message")
                        continue
                    
                    topic = parts[1]
                    message = parts[2]
                    
                    try:
                        # Essayer de parser le message comme du JSON
                        message_data = json.loads(message)
                    except json.JSONDecodeError:
                        # Sinon, utiliser le message comme une chaîne
                        message_data = {"text": message}
                    
                    self.message_bus.publish(topic, message_data)
                    print(f"Message envoyé sur le topic '{topic}'")
                
                elif command.lower().startswith("get "):
                    # Format: get state_path
                    parts = command.split(" ", 1)
                    if len(parts) < 2:
                        print("Format incorrect. Utilisez: get state_path")
                        continue
                    
                    state_path = parts[1]
                    state = self.state_manager.get(state_path)
                    print(json.dumps(state, indent=2))
                
                elif command.lower().startswith("set "):
                    # Format: set state_path value
                    parts = command.split(" ", 2)
                    if len(parts) < 3:
                        print("Format incorrect. Utilisez: set state_path value")
                        continue
                    
                    state_path = parts[1]
                    value = parts[2]
                    
                    try:
                        # Essayer de parser la valeur comme du JSON
                        value_data = json.loads(value)
                    except json.JSONDecodeError:
                        # Sinon, utiliser la valeur comme une chaîne
                        value_data = value
                    
                    self.state_manager.set(state_path, value_data)
                    print(f"État défini: {state_path} = {value}")
                
                else:
                    print(f"Commande inconnue: {command}")
                    print("Tapez 'help' pour voir les commandes disponibles")
            
            except KeyboardInterrupt:
                self.logger.info("Interruption clavier, sortie de l'interface CLI")
                break
            except Exception as e:
                self.logger.error(f"Erreur dans l'interface CLI: {str(e)}")
    
    # Gestionnaires de routes par défaut
    
    def _handle_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Gestionnaire pour la route /api/status"""
        return {
            "status": "ok",
            "uptime": time.time(),  # Dans une implémentation réelle, on calculerait le temps écoulé depuis le démarrage
            "modules": {
                # Obtenir la liste des modules et leur état
                # Ce serait normalement fourni par un ModuleManager
                "example_module": {
                    "status": "running",
                    "uptime": 3600
                }
            }
        }
    
    def _handle_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Gestionnaire pour la route /api/command"""
        if not params.get("body"):
            return {"error": "Missing command data"}
        
        body = params["body"]
        if not isinstance(body, dict):
            return {"error": "Invalid command format"}
        
        topic = body.get("topic")
        message = body.get("message")
        
        if not topic or not message:
            return {"error": "Missing topic or message"}
        
        # Publier sur le bus de messages
        self.message_bus.publish(topic, message)
        
        return {"success": True, "topic": topic}
    
    def _handle_get_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Gestionnaire pour la route /api/state (GET)"""
        query = params.get("query", {})
        path = query.get("path", [""])[0]
        
        state = self.state_manager.get(path)
        
        return {"path": path, "state": state}
    
    def _handle_set_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Gestionnaire pour la route /api/state (POST)"""
        if not params.get("body"):
            return {"error": "Missing state data"}
        
        body = params["body"]
        if not isinstance(body, dict):
            return {"error": "Invalid state format"}
        
        path = body.get("path")
        value = body.get("value")
        
        if not path:
            return {"error": "Missing path"}
        
        # Définir l'état
        self.state_manager.set(path, value)
        
        return {"success": True, "path": path}


def create_module(module_id: str, config: Dict[str, Any] = None) -> UIModule:
    """
    Crée une instance du module d'interface utilisateur.
    
    Args:
        module_id: Identifiant unique du module
        config: Configuration du module
    
    Returns:
        Instance du module d'interface utilisateur
    """
    return UIModule(module_id, config)
