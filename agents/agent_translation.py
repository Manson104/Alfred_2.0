"""
Translation Agent (O2) - Agent de traduction et traitement de fichiers
Version intégrée avec BaseAgent pour une communication uniforme dans Alfred.
"""

import os
import json
import time
import threading
import tempfile
import mimetypes
from typing import Dict, Any, Optional
from base_agent import BaseAgent
import redis
import json

# Connexion à Redis (adapter l'hôte si besoin)
redis_client = redis.Redis(host='localhost', port=6379, db=0)


# Dépendances pour la traduction
try:
    import googletrans
    from googletrans import Translator as GoogleTranslator
    GOOGLE_TRANSLATE_AVAILABLE = True
except ImportError:
    GOOGLE_TRANSLATE_AVAILABLE = False

# Dépendances pour le traitement des sous-titres SRT
try:
    import pysrt
    PYSRT_AVAILABLE = True
except ImportError:
    PYSRT_AVAILABLE = False

# Dépendances pour le traitement des fichiers DOCX
try:
    import docx
    from docx import Document
    PYTHON_DOCX_AVAILABLE = True
except ImportError:
    PYTHON_DOCX_AVAILABLE = False

# Dépendances pour DeepL (optionnel)
try:
    import deepl
    DEEPL_AVAILABLE = True
except ImportError:
    DEEPL_AVAILABLE = False


class TranslationAgent(BaseAgent):
    """Agent spécialisé dans la traduction et le traitement de fichiers."""
    
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379,
                 deepl_api_key: Optional[str] = None):
        super().__init__("o2", redis_host, redis_port)
        
        # Capacités de l'agent
        self.capabilities = [
            "text_translation",    # Traduction de texte
            "file_translation",    # Traduction de fichiers
            "subtitle_processing", # Traitement de sous-titres
            "document_processing", # Traitement de documents
            "language_detection"   # Détection de langue
        ]
        
        # Initialisation des services de traduction
        self.google_translator = None
        self.deepl_translator = None
        self.deepl_api_key = deepl_api_key
        self._init_translation_services()
        
        # Répertoire temporaire pour les fichiers
        self.temp_dir = tempfile.mkdtemp(prefix="alfred_translation_")
        
        # Cache de traduction pour les requêtes fréquentes
        self.translation_cache: Dict[str, Any] = {}
        self.cache_lock = threading.Lock()
        self.max_cache_entries = 1000
        
        self.logger.info(f"Translation Agent (O2) initialisé. Services disponibles: "
                         f"Google Translate: {GOOGLE_TRANSLATE_AVAILABLE}, "
                         f"DeepL: {DEEPL_AVAILABLE and self.deepl_translator is not None}, "
                         f"Pysrt: {PYSRT_AVAILABLE}, "
                         f"Python-docx: {PYTHON_DOCX_AVAILABLE}")
    
    def _init_translation_services(self) -> None:
        """Initialise les services de traduction disponibles."""
        # Initialiser Google Translate
        if GOOGLE_TRANSLATE_AVAILABLE:
            try:
                self.google_translator = GoogleTranslator()
                self.logger.info("Service Google Translate initialisé")
            except Exception as e:
                self.logger.error(f"Erreur lors de l'initialisation de Google Translate: {e}")
        
        # Initialiser DeepL si la clé API est fournie
        if DEEPL_AVAILABLE and self.deepl_api_key:
            try:
                self.deepl_translator = deepl.Translator(self.deepl_api_key)
                self.logger.info("Service DeepL initialisé")
            except Exception as e:
                self.logger.error(f"Erreur lors de l'initialisation de DeepL: {e}")
    
    def on_start(self) -> None:
        """Actions à effectuer lors du démarrage de l'agent."""
        self.broadcast_message("agent_online", {
            "agent_type": "translation",
            "capabilities": self.capabilities
        })
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities,
            "services": {
                "google_translate": GOOGLE_TRANSLATE_AVAILABLE and self.google_translator is not None,
                "deepl": DEEPL_AVAILABLE and self.deepl_translator is not None,
                "srt_support": PYSRT_AVAILABLE,
                "docx_support": PYTHON_DOCX_AVAILABLE
            }
        })
        self.logger.info("Translation Agent (O2) démarré")
    
    def on_stop(self) -> None:
        """Actions à effectuer lors de l'arrêt de l'agent."""
        # Nettoyer le répertoire temporaire
        try:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            self.logger.error(f"Erreur lors du nettoyage des fichiers temporaires: {e}")
        self.broadcast_message("agent_offline", {
            "agent_type": "translation",
            "shutdown_time": time.time()
        })
        self.logger.info("Translation Agent (O2) arrêté")
    
    def detect_language(self, text: str) -> Dict[str, Any]:
        """
        Détecte la langue d'un texte.
        """
        result = {
            'success': False,
            'detected_language': None,
            'confidence': 0.0,
            'service': None
        }
        if self.google_translator:
            try:
                detection = self.google_translator.detect(text)
                result.update({
                    'success': True,
                    'detected_language': detection.lang,
                    'confidence': detection.confidence,
                    'service': 'google'
                })
                return result
            except Exception as e:
                self.logger.error(f"Erreur détecter langue via Google Translate: {e}")
        if self.deepl_translator:
            try:
                detection = self.deepl_translator.detect_language(text)
                result.update({
                    'success': True,
                    'detected_language': detection.language,
                    'confidence': getattr(detection, 'reliability_score', 0.9),
                    'service': 'deepl'
                })
                return result
            except Exception as e:
                self.logger.error(f"Erreur détecter langue via DeepL: {e}")
        return result
    
    def translate_text(self, text: str, target_lang: str, source_lang: Optional[str] = None,
                       service: Optional[str] = None) -> Dict[str, Any]:
        """
        Traduit un texte vers une langue cible.
        """
        result = {
            'success': False,
            'translated_text': None,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'service': None
        }
        # Utilisation d'un cache
        cache_key = f"{source_lang or 'auto'}_{target_lang}_{service or 'auto'}_{hash(text)}"
        with self.cache_lock:
            if cache_key in self.translation_cache:
                self.logger.info(f"Traduction trouvée dans le cache pour {cache_key}")
                return self.translation_cache[cache_key]
        # Choix du service
        if not service:
            service = 'deepl' if self.deepl_translator else 'google' if self.google_translator else None
        if service == 'deepl' and self.deepl_translator:
            try:
                target = target_lang.upper() if len(target_lang) == 2 else target_lang
                source = None if not source_lang else (source_lang.upper() if len(source_lang) == 2 else source_lang)
                translation = self.deepl_translator.translate_text(text, target_lang=target, source_lang=source)
                result.update({
                    'success': True,
                    'translated_text': translation.text,
                    'source_lang': translation.detected_source_lang.lower() if not source_lang else source_lang,
                    'service': 'deepl'
                })
            except Exception as e:
                self.logger.error(f"Erreur DeepL: {e}")
                if self.google_translator:
                    service = 'google'
                else:
                    result['error'] = str(e)
                    return result
        if service == 'google' and self.google_translator:
            try:
                translation = self.google_translator.translate(text, dest=target_lang, src=source_lang or 'auto')
                result.update({
                    'success': True,
                    'translated_text': translation.text,
                    'source_lang': translation.src,
                    'service': 'google'
                })
            except Exception as e:
                self.logger.error(f"Erreur Google Translate: {e}")
                result['error'] = str(e)
                return result
        # Stocker dans le cache si succès
        if result['success']:
            with self.cache_lock:
                self.translation_cache[cache_key] = result
                if len(self.translation_cache) > self.max_cache_entries:
                    # Supprimer des entrées pour limiter la taille du cache
                    keys_to_remove = list(self.translation_cache.keys())[:-self.max_cache_entries]
                    for key in keys_to_remove:
                        del self.translation_cache[key]
        return result
    
    def translate_file(self, file_path: str, target_lang: str, source_lang: Optional[str] = None,
                       service: Optional[str] = None) -> Dict[str, Any]:
        """
        Traduit un fichier (TXT, SRT, DOCX).
        """
        if not os.path.exists(file_path):
            return {'success': False, 'error': f"Le fichier {file_path} n'existe pas"}
        file_type = self._detect_file_type(file_path)
        # Pour simplifier, nous traiterons uniquement les fichiers TXT dans cet exemple.
        if file_type != 'txt':
            return {'success': False, 'error': f"Type de fichier '{file_type}' non supporté dans cet exemple"}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if not source_lang:
                detection = self.detect_language(content[:1000])
                if detection['success']:
                    source_lang = detection['detected_language']
            translation_result = self.translate_text(content, target_lang, source_lang, service)
            if not translation_result['success']:
                return translation_result
            # Sauvegarder la traduction dans un fichier temporaire
            base_name, ext = os.path.splitext(os.path.basename(file_path))
            translated_file = os.path.join(self.temp_dir, f"{base_name}_{target_lang}{ext}")
            with open(translated_file, 'w', encoding='utf-8') as f:
                f.write(translation_result['translated_text'])
            return {
                'success': True,
                'original_file': file_path,
                'translated_file': translated_file,
                'source_lang': translation_result['source_lang'],
                'target_lang': target_lang,
                'service': translation_result['service']
            }
        except Exception as e:
            self.logger.error(f"Erreur lors de la traduction du fichier: {e}")
            return {'success': False, 'error': str(e)}
    
    def _detect_file_type(self, file_path: str) -> str:
        """Détermine le type de fichier (txt, srt, docx). Ici, on traite simplement les .txt."""
        _, ext = os.path.splitext(file_path)
        return ext.lower().strip('.') if ext else 'unknown'
    
    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite une commande reçue.
        Commandes supportées :
          - 'detect_language'
          - 'translate_text'
          - 'translate_file'
          - 'status_request'
        """
        cmd_type = command.get("type", "unknown")
        data = command.get("data", {})
        self.logger.info(f"Traitement de la commande: {cmd_type}")
        if cmd_type in ["detect_language", "detect_language_o2"]:
            text = data.get("text", "")
            if not text:
                return {"success": False, "error": "Texte non spécifié"}
            return self.detect_language(text)
        elif cmd_type in ["translate_text", "translate_text_o2"]:
            text = data.get("text", "")
            target_lang = data.get("target_lang", "en")
            source_lang = data.get("source_lang")
            service = data.get("service")
            if not text:
                return {"success": False, "error": "Texte non spécifié"}
            return self.translate_text(text, target_lang, source_lang, service)
        elif cmd_type in ["translate_file", "translate_file_o2"]:
            file_path = data.get("file_path", "")
            target_lang = data.get("target_lang", "en")
            source_lang = data.get("source_lang")
            service = data.get("service")
            if not file_path:
                return {"success": False, "error": "Chemin de fichier non spécifié"}
            return self.translate_file(file_path, target_lang, source_lang, service)
        elif cmd_type == "status_request":
            return {
                "status": "ready",
                "capabilities": self.capabilities,
                "active_translations": len(self.translation_cache)
            }
        else:
            self.logger.warning(f"Commande non supportée: {cmd_type}")
            return {"success": False, "message": f"Commande non supportée: {cmd_type}"}

    # 1. Ajouter ces méthodes à la classe TranslationAgent:

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
        elif msg_type == 'translate_text_request':
            # Traduire un texte
            text = data.get('text', '')
            target_lang = data.get('target_lang', 'en')
            source_lang = data.get('source_lang')
            service = data.get('service')
            
            if text:
                result = self.translate_text(text, target_lang, source_lang, service)
                reply_to = data.get('reply_to', 'orchestrator')
                self.send_redis_message(f"{reply_to}:notifications", 'translation_result', result)
        elif msg_type == 'detect_language_request':
            # Détecter la langue d'un texte
            text = data.get('text', '')
            if text:
                result = self.detect_language(text)
                reply_to = data.get('reply_to', 'orchestrator')
                self.send_redis_message(f"{reply_to}:notifications", 'language_detection_result', result)
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
        """Actions à effectuer lors du démarrage de l'agent."""
        self.broadcast_message("agent_online", {
            "agent_type": "translation",
            "capabilities": self.capabilities
        })
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities,
            "services": {
                "google_translate": GOOGLE_TRANSLATE_AVAILABLE and self.google_translator is not None,
                "deepl": DEEPL_AVAILABLE and self.deepl_translator is not None,
                "srt_support": PYSRT_AVAILABLE,
                "docx_support": PYTHON_DOCX_AVAILABLE
            }
        })
        self.setup_redis_listener()
        self.logger.info("Translation Agent (O2) démarré")

    # 3. Modifier la méthode on_stop pour fermer proprement l'écoute Redis:
    def on_stop(self) -> None:
        """Actions à effectuer lors de l'arrêt de l'agent."""
        # Nettoyer le répertoire temporaire
        try:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            self.logger.error(f"Erreur lors du nettoyage des fichiers temporaires: {e}")
        
        # Arrêter l'écoute Redis
        if hasattr(self, 'redis_pubsub'):
            self.redis_pubsub.unsubscribe()
            
        self.broadcast_message("agent_offline", {
            "agent_type": "translation",
            "shutdown_time": time.time()
        })
        self.logger.info("Translation Agent (O2) arrêté")
  
  
    def process_broadcast(self, message: Dict[str, Any]) -> None:
        """Traite les messages broadcast (ici, on les loggue simplement)."""
        self.logger.info(f"Broadcast reçu: {message.get('type', 'unknown')}")
    
    def log_activity(self, activity_type: str, details: Dict[str, Any]) -> None:
        """Enregistre une activité dans les logs."""
        self.logger.info(f"Activité [{activity_type}]: {details}")

if __name__ == "__main__":
    agent = TranslationAgent(deepl_api_key="YOUR_DEEPL_API_KEY")
    agent.start()
    # Exemple de test en standalone : traduction de texte
    test_command = {
        "type": "translate_text",
        "data": {
            "text": "Bonjour, comment allez-vous ?",
            "target_lang": "en"
        }
    }
    response = agent.process_command(test_command)
    print(response)
    agent.stop()
