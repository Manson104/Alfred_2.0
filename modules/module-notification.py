import logging
import time
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from modules.base_module import BaseModule
from modules.message_bus import MessageBus
from modules.state_manager import StateManager

class NotificationModule(BaseModule):
    """
    Module de gestion des notifications.
    Permet d'envoyer des notifications via différents canaux (push, email, SMS)
    et de gérer les préférences des utilisateurs.
    """
    
    # Priorités de notification
    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"
    
    # Types de notifications
    TYPE_INFO = "info"
    TYPE_WARNING = "warning"
    TYPE_ERROR = "error"
    TYPE_SECURITY = "security"
    TYPE_HOME = "home"
    
    def __init__(self, module_id: str, config: Dict[str, Any], message_bus: MessageBus, state_manager: StateManager):
        """
        Initialise le module de notification.
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration du module
            message_bus: Instance du bus de messages
            state_manager: Instance du gestionnaire d'état
        """
        super().__init__(module_id, "notification", config, message_bus, state_manager)
        
        # Configuration des canaux de notification
        self.channels = config.get("channels", {})
        
        # Configuration des utilisateurs
        self.users = config.get("users", {})
        
        # Configuration des templates
        self.templates = config.get("templates", {})
        
        # Configuration des limitations
        self.rate_limits = config.get("rate_limits", {})
        self.quiet_hours = config.get("quiet_hours", {})
        self.max_notifications_per_hour = self.rate_limits.get("max_per_hour", 10)
        self.max_notifications_per_day = self.rate_limits.get("max_per_day", 50)
        
        # État interne
        self._notification_history = []  # [{timestamp, user_id, channel, message, etc.}, ...]
        self._notification_counts = {}  # user_id -> {"hour": count, "day": count, "last_hour": timestamp, "last_day": timestamp}
        
        self.logger.info(f"Module de notification initialisé avec {len(self.channels)} canaux et {len(self.users)} utilisateurs")
        
        # Enregistrement des gestionnaires de messages
        self._register_handlers()
    
    def _register_handlers(self):
        """Enregistre les gestionnaires de messages pour ce module."""
        self.message_bus.register_handler("notification/send", self._handle_send_notification)
        self.message_bus.register_handler("notification/push", self._handle_push_notification)
        self.message_bus.register_handler("notification/email", self._handle_email_notification)
        self.message_bus.register_handler("notification/sms", self._handle_sms_notification)
        self.message_bus.register_handler("notification/status", self._handle_status_request)
        self.message_bus.register_handler("notification/history", self._handle_history_request)
        self.message_bus.register_handler("notification/preferences", self._handle_preferences_update)
    
    def start(self):
        """Démarre le module."""
        self.logger.info("Démarrage du module de notification")
        
        # Charger l'état précédent si disponible
        self._load_state()
        
        # Définir le statut comme actif
        self.active = True
        
        # Envoyer une notification de démarrage du système
        self._send_system_notification("system_start", {
            "message": "Le système domotique a démarré",
            "timestamp": time.time()
        })
    
    def stop(self):
        """Arrête le module et sauvegarde l'état actuel."""
        self.logger.info("Arrêt du module de notification")
        
        # Envoyer une notification d'arrêt du système
        self._send_system_notification("system_stop", {
            "message": "Le système domotique s'arrête",
            "timestamp": time.time()
        })
        
        # Sauvegarde de l'état
        self._save_state()
        
        # Définir le statut comme inactif
        self.active = False
    
    def _load_state(self):
        """Charge l'état précédent depuis le gestionnaire d'état."""
        state = self.state_manager.get_state(f"{self.module_id}_state")
        if state:
            self.logger.info("Chargement de l'état précédent")
            
            if "notification_history" in state:
                self._notification_history = state["notification_history"]
            
            if "notification_counts" in state:
                self._notification_counts = state["notification_counts"]
    
    def _save_state(self):
        """Sauvegarde l'état actuel dans le gestionnaire d'état."""
        state = {
            "notification_history": self._notification_history[-100:],  # Limiter l'historique
            "notification_counts": self._notification_counts,
            "last_update": time.time()
        }
        self.state_manager.set_state(f"{self.module_id}_state", state)
    
    def _send_notification(self, user_id: str, message: str, title: str = None, 
                         notification_type: str = TYPE_INFO, priority: str = PRIORITY_NORMAL,
                         channel: str = None, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Envoie une notification à un utilisateur.
        
        Args:
            user_id: Identifiant de l'utilisateur
            message: Corps du message
            title: Titre du message (optionnel)
            notification_type: Type de notification (info, warning, error, security, home)
            priority: Priorité du message (low, normal, high, urgent)
            channel: Canal spécifique à utiliser (optionnel)
            data: Données supplémentaires (optionnel)
            
        Returns:
            Dict: Résultat de l'envoi
        """
        if user_id not in self.users:
            self.logger.warning(f"Utilisateur inconnu: {user_id}")
            return {"success": False, "error": "unknown_user"}
        
        # Récupérer la configuration de l'utilisateur
        user_config = self.users[user_id]
        
        # Vérifier si l'utilisateur accepte ce type de notification
        if notification_type not in user_config.get("accepted_types", [notification_type]):
            self.logger.info(f"Type de notification refusé pour {user_id}: {notification_type}")
            return {"success": False, "error": "notification_type_rejected"}
        
        # Vérifier les limites de taux
        if not self._check_rate_limits(user_id, priority):
            self.logger.warning(f"Limite de taux atteinte pour {user_id}")
            return {"success": False, "error": "rate_limit_exceeded"}
        
        # Vérifier les heures de silence
        if not self._check_quiet_hours(user_id, priority):
            self.logger.info(f"Notification non envoyée pendant les heures de silence pour {user_id}")
            return {"success": False, "error": "quiet_hours"}
        
        # Déterminer les canaux à utiliser
        channels_to_use = []
        
        if channel:
            # Canal spécifique demandé
            channels_to_use = [channel]
        else:
            # Utiliser les canaux préférés de l'utilisateur en fonction de la priorité
            if priority == self.PRIORITY_URGENT:
                channels_to_use = user_config.get("urgent_channels", ["push", "sms", "email"])
            elif priority == self.PRIORITY_HIGH:
                channels_to_use = user_config.get("high_channels", ["push", "email"])
            elif priority == self.PRIORITY_NORMAL:
                channels_to_use = user_config.get("normal_channels", ["push"])
            else:  # low
                channels_to_use = user_config.get("low_channels", ["push"])
        
        # Préparer les résultats
        results = {"success": False, "channels": {}}
        
        # Si aucun titre n'est fourni, utiliser un titre par défaut en fonction du type
        if not title:
            if notification_type == self.TYPE_INFO:
                title = "Information"
            elif notification_type == self.TYPE_WARNING:
                title = "Avertissement"
            elif notification_type == self.TYPE_ERROR:
                title = "Erreur"
            elif notification_type == self.TYPE_SECURITY:
                title = "Alerte de sécurité"
            elif notification_type == self.TYPE_HOME:
                title = "Maison connectée"
            else:
                title = "Notification"
        
        # Envoyer la notification via chaque canal
        success_count = 0
        
        for channel_id in channels_to_use:
            if channel_id not in self.channels:
                results["channels"][channel_id] = {"success": False, "error": "unknown_channel"}
                continue
                
            channel_config = self.channels[channel_id]
            
            if not channel_config.get("enabled", True):
                results["channels"][channel_id] = {"success": False, "error": "channel_disabled"}
                continue
            
            # Envoyer la notification via ce canal
            if channel_id == "push":
                result = self._send_push_notification(user_id, message, title, notification_type, priority, data)
            elif channel_id == "email":
                result = self._send_email_notification(user_id, message, title, notification_type, priority, data)
            elif channel_id == "sms":
                result = self._send_sms_notification(user_id, message, notification_type, priority)
            else:
                result = {"success": False, "error": "unsupported_channel"}
            
            results["channels"][channel_id] = result
            
            if result.get("success", False):
                success_count += 1
        
        # Marquer comme succès si au moins un canal a réussi
        results["success"] = success_count > 0
        
        # Mettre à jour l'historique et les compteurs
        if results["success"]:
            self._update_notification_history(user_id, message, title, notification_type, priority, channels_to_use, results, data)
            self._update_notification_counts(user_id)
        
        return results
    
    def _send_push_notification(self, user_id: str, message: str, title: str, 
                              notification_type: str, priority: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Envoie une notification push à un utilisateur.
        
        Args:
            user_id: Identifiant de l'utilisateur
            message: Corps du message
            title: Titre du message
            notification_type: Type de notification
            priority: Priorité du message
            data: Données supplémentaires (optionnel)
            
        Returns:
            Dict: Résultat de l'envoi
        """
        user_config = self.users[user_id]
        push_config = self.channels.get("push", {})
        
        # Vérifier si l'utilisateur a des tokens pour les notifications push
        push_tokens = user_config.get("push_tokens", [])
        if not push_tokens:
            return {"success": False, "error": "no_push_tokens"}
        
        # Déterminer le service à utiliser
        service = push_config.get("service", "fcm")  # Firebase Cloud Messaging par défaut
        
        # Dans une implémentation réelle, nous enverrions la notification via le service approprié
        # Ici, nous simulons simplement l'envoi
        
        self.logger.info(f"Envoi de notification push à {user_id} via {service}: {title}")
        
        # Simuler un succès
        return {"success": True, "service": service, "tokens": len(push_tokens)}
    
    def _send_email_notification(self, user_id: str, message: str, title: str, 
                               notification_type: str, priority: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Envoie une notification par email à un utilisateur.
        
        Args:
            user_id: Identifiant de l'utilisateur
            message: Corps du message
            title: Titre du message
            notification_type: Type de notification
            priority: Priorité du message
            data: Données supplémentaires (optionnel)
            
        Returns:
            Dict: Résultat de l'envoi
        """
        user_config = self.users[user_id]
        email_config = self.channels.get("email", {})
        
        # Vérifier si l'utilisateur a une adresse email
        email = user_config.get("email")
        if not email:
            return {"success": False, "error": "no_email_address"}
        
        # Dans une implémentation réelle, nous enverrions l'email via SMTP
        # Ici, nous simulons simplement l'envoi
        
        self.logger.info(f"Envoi d'email à {user_id} ({email}): {title}")
        
        # Simuler un succès
        return {"success": True, "recipient": email}
    
    def _send_sms_notification(self, user_id: str, message: str, 
                            notification_type: str, priority: str) -> Dict[str, Any]:
        """
        Envoie une notification par SMS à un utilisateur.
        
        Args:
            user_id: Identifiant de l'utilisateur
            message: Corps du message
            notification_type: Type de notification
            priority: Priorité du message
            
        Returns:
            Dict: Résultat de l'envoi
        """
        user_config = self.users[user_id]
        sms_config = self.channels.get("sms", {})
        
        # Vérifier si l'utilisateur a un numéro de téléphone
        phone = user_config.get("phone")
        if not phone:
            return {"success": False, "error": "no_phone_number"}
        
        # Dans une implémentation réelle, nous enverrions le SMS via un service comme Twilio
        # Ici, nous simulons simplement l'envoi
        
        self.logger.info(f"Envoi de SMS à {user_id} ({phone}): {message}")
        
        # Simuler un succès
        return {"success": True, "recipient": phone}
    
    def _send_system_notification(self, event_type: str, data: Dict[str, Any]):
        """
        Envoie une notification système à tous les utilisateurs concernés.
        
        Args:
            event_type: Type d'événement système
            data: Données de l'événement
        """
        # Construire le message en fonction du type d'événement
        message = data.get("message", "Événement système")
        title = None
        notification_type = self.TYPE_INFO
        priority = self.PRIORITY_NORMAL
        
        if event_type == "system_start":
            title = "Système démarré"
        elif event_type == "system_stop":
            title = "Système arrêté"
        elif event_type == "system_error":
            title = "Erreur système"
            notification_type = self.TYPE_ERROR
            priority = self.PRIORITY_HIGH
        elif event_type == "system_update":
            title = "Mise à jour système"
        
        # Envoyer à tous les utilisateurs qui acceptent les notifications système
        for user_id, user_config in self.users.items():
            if self.TYPE_INFO in user_config.get("accepted_types", [self.TYPE_INFO]):
                self._send_notification(
                    user_id=user_id,
                    message=message,
                    title=title,
                    notification_type=notification_type,
                    priority=priority,
                    data=data
                )
    
    def _check_rate_limits(self, user_id: str, priority: str) -> bool:
        """
        Vérifie si les limites de taux sont respectées pour un utilisateur.
        
        Args:
            user_id: Identifiant de l'utilisateur
            priority: Priorité du message
            
        Returns:
            bool: True si les limites sont respectées, False sinon
        """
        # Les notifications urgentes ignorent les limites de taux
        if priority == self.PRIORITY_URGENT:
            return True
        
        current_time = time.time()
        
        # Initialiser les compteurs si nécessaire
        if user_id not in self._notification_counts:
            self._notification_counts[user_id] = {
                "hour": 0,
                "day": 0,
                "last_hour": current_time,
                "last_day": current_time
            }
        
        counts = self._notification_counts[user_id]
        
        # Réinitialiser les compteurs si nécessaire
        hour_elapsed = current_time - counts["last_hour"]
        if hour_elapsed > 3600:  # 1 heure
            counts["hour"] = 0
            counts["last_hour"] = current_time
        
        day_elapsed = current_time - counts["last_day"]
        if day_elapsed > 86400:  # 24 heures
            counts["day"] = 0
            counts["last_day"] = current_time
        
        # Vérifier les limites
        if counts["hour"] >= self.max_notifications_per_hour:
            return False
        
        if counts["day"] >= self.max_notifications_per_day:
            return False
        
        return True
    
    def _check_quiet_hours(self, user_id: str, priority: str) -> bool:
        """
        Vérifie si une notification peut être envoyée pendant les heures de silence.
        
        Args:
            user_id: Identifiant de l'utilisateur
            priority: Priorité du message
            
        Returns:
            bool: True si la notification peut être envoyée, False sinon
        """
        # Les notifications urgentes ignorent les heures de silence
        if priority == self.PRIORITY_URGENT:
            return True
        
        user_config = self.users[user_id]
        
        # Vérifier si les heures de silence sont activées pour cet utilisateur
        if not user_config.get("quiet_hours_enabled", False):
            return True
        
        # Récupérer les heures de silence configurées
        quiet_start = user_config.get("quiet_hours_start", self.quiet_hours.get("start", "22:00"))
        quiet_end = user_config.get("quiet_hours_end", self.quiet_hours.get("end", "07:00"))
        
        # Vérifier l'heure actuelle
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # Convertir en minutes depuis minuit pour faciliter la comparaison
        def time_to_minutes(time_str):
            hours, minutes = map(int, time_str.split(":"))
            return hours * 60 + minutes
        
        current_minutes = time_to_minutes(current_time)
        start_minutes = time_to_minutes(quiet_start)
        end_minutes = time_to_minutes(quiet_end)
        
        # Gérer le cas où la période de silence s'étend sur deux jours
        if start_minutes > end_minutes:
            # La période commence aujourd'hui et se termine demain
            return not (current_minutes >= start_minutes or current_minutes <= end_minutes)
        else:
            # La période commence et se termine le même jour
            return not (start_minutes <= current_minutes <= end_minutes)
    
    def _update_notification_history(self, user_id: str, message: str, title: str, 
                                   notification_type: str, priority: str, channels: List[str],
                                   results: Dict[str, Any], data: Dict[str, Any] = None):
        """
        Met à jour l'historique des notifications.
        
        Args:
            user_id: Identifiant de l'utilisateur
            message: Corps du message
            title: Titre du message
            notification_type: Type de notification
            priority: Priorité du message
            channels: Canaux utilisés
            results: Résultats de l'envoi
            data: Données supplémentaires (optionnel)
        """
        event = {
            "timestamp": time.time(),
            "user_id": user_id,
            "message": message,
            "title": title,
            "type": notification_type,
            "priority": priority,
            "channels": channels,
            "results": results
        }
        
        if data:
            event["data"] = data
        
        # Ajouter l'événement à l'historique
        self._notification_history.insert(0, event)
        
        # Limiter la taille de l'historique
        max_history = 500
        if len(self._notification_history) > max_history:
            self._notification_history = self._notification_history[:max_history]
    
    def _update_notification_counts(self, user_id: str):
        """
        Met à jour les compteurs de notifications pour un utilisateur.
        
        Args:
            user_id: Identifiant de l'utilisateur
        """
        if user_id not in self._notification_counts:
            self._notification_counts[user_id] = {
                "hour": 0,
                "day": 0,
                "last_hour": time.time(),
                "last_day": time.time()
            }
        
        # Incrémenter les compteurs
        self._notification_counts[user_id]["hour"] += 1
        self._notification_counts[user_id]["day"] += 1
    
    def get_status(self) -> Dict[str, Any]:
        """
        Récupère le statut actuel du module de notification.
        
        Returns:
            Dict: Statut du module de notification
        """
        return {
            "active_channels": [channel_id for channel_id, config in self.channels.items() if config.get("enabled", True)],
            "user_count": len(self.users),
            "notification_count": len(self._notification_history),
            "rate_limits": self.rate_limits,
            "quiet_hours": self.quiet_hours
        }
    
    def get_history(self, limit: int = 20, user_id: str = None, notification_type: str = None) -> List[Dict[str, Any]]:
        """
        Récupère l'historique des notifications filtré.
        
        Args:
            limit: Nombre maximum de notifications à retourner
            user_id: Identifiant de l'utilisateur pour filtrer (optionnel)
            notification_type: Type de notification pour filtrer (optionnel)
            
        Returns:
            List: Liste des notifications filtrées
        """
        filtered_history = self._notification_history
        
        if user_id:
            filtered_history = [event for event in filtered_history if event["user_id"] == user_id]
            
        if notification_type:
            filtered_history = [event for event in filtered_history if event["type"] == notification_type]
            
        return filtered_history[:limit]
    
    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        Récupère les préférences de notification d'un utilisateur.
        
        Args:
            user_id: Identifiant de l'utilisateur
            
        Returns:
            Dict: Préférences de l'utilisateur
        """
        if user_id not in self.users:
            return None
            
        user_config = self.users[user_id]
        
        return {
            "accepted_types": user_config.get("accepted_types", []),
            "urgent_channels": user_config.get("urgent_channels", []),
            "high_channels": user_config.get("high_channels", []),
            "normal_channels": user_config.get("normal_channels", []),
            "low_channels": user_config.get("low_channels", []),
            "quiet_hours_enabled": user_config.get("quiet_hours_enabled", False),
            "quiet_hours_start": user_config.get("quiet_hours_start", self.quiet_hours.get("start", "22:00")),
            "quiet_hours_end": user_config.get("quiet_hours_end", self.quiet_hours.get("end", "07:00"))
        }
    
    def update_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> bool:
        """
        Met à jour les préférences de notification d'un utilisateur.
        
        Args:
            user_id: Identifiant de l'utilisateur
            preferences: Nouvelles préférences
            
        Returns:
            bool: True si mis à jour avec succès, False sinon
        """
        if user_id not in self.users:
            return False
            
        user_config = self.users[user_id]
        
        # Mettre à jour les préférences
        if "accepted_types" in preferences:
            user_config["accepted_types"] = preferences["accepted_types"]
            
        if "urgent_channels" in preferences:
            user_config["urgent_channels"] = preferences["urgent_channels"]
            
        if "high_channels" in preferences:
            user_config["high_channels"] = preferences["high_channels"]
            
        if "normal_channels" in preferences:
            user_config["normal_channels"] = preferences["normal_channels"]
            
        if "low_channels" in preferences:
            user_config["low_channels"] = preferences["low_channels"]
            
        if "quiet_hours_enabled" in preferences:
            user_config["quiet_hours_enabled"] = preferences["quiet_hours_enabled"]
            
        if "quiet_hours_start" in preferences:
            user_config["quiet_hours_start"] = preferences["quiet_hours_start"]
            
        if "quiet_hours_end" in preferences:
            user_config["quiet_hours_end"] = preferences["quiet_hours_end"]
        
        # Sauvegarder l'état
        self._save_state()
        
        return True
    
    # Gestionnaires de messages
    
    def _handle_send_notification(self, message: Dict[str, Any]):
        """Gère les demandes d'envoi de notification."""
        user_id = message.get("user_id")
        notification_message = message.get("message")
        title = message.get("title")
        notification_type = message.get("type", self.TYPE_INFO)
        priority = message.get("priority", self.PRIORITY_NORMAL)
        channel = message.get("channel")
        data = message.get("data")
        
        if not user_id or not notification_message:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_parameters"
                })
            return
        
        # Envoyer la notification
        result = self._send_notification(
            user_id=user_id,
            message=notification_message,
            title=title,
            notification_type=notification_type,
            priority=priority,
            channel=channel,
            data=data
        )
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], result)
    
    def _handle_push_notification(self, message: Dict[str, Any]):
        """Gère les demandes d'envoi de notification push."""
        # Convertir en demande générique avec canal forcé à "push"
        message["channel"] = "push"
        self._handle_send_notification(message)
    
    def _handle_email_notification(self, message: Dict[str, Any]):
        """Gère les demandes d'envoi d'email."""
        # Convertir en demande générique avec canal forcé à "email"
        message["channel"] = "email"
        self._handle_send_notification(message)
    
    def _handle_sms_notification(self, message: Dict[str, Any]):
        """Gère les demandes d'envoi de SMS."""
        # Convertir en demande générique avec canal forcé à "sms"
        message["channel"] = "sms"
        self._handle_send_notification(message)
    
    def _handle_status_request(self, message: Dict[str, Any]):
        """Gère les demandes de statut."""
        status = self.get_status()
        
        # Répondre avec le statut
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], status)
    
    def _handle_history_request(self, message: Dict[str, Any]):
        """Gère les demandes d'historique."""
        limit = message.get("limit", 20)
        user_id = message.get("user_id")
        notification_type = message.get("type")
        
        history = self.get_history(limit, user_id, notification_type)
        
        # Répondre avec l'historique
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "history": history,
                "count": len(history)
            })
    
    def _handle_preferences_update(self, message: Dict[str, Any]):
        """Gère les mises à jour de préférences."""
        user_id = message.get("user_id")
        preferences = message.get("preferences")
        
        if not user_id or not preferences:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_parameters"
                })
            return
        
        success = self.update_user_preferences(user_id, preferences)
        
        # Répondre avec le résultat
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": success,
                "user_id": user_id
            })


# Exemple de configuration pour les tests
SAMPLE_CONFIG = {
    "channels": {
        "push": {
            "enabled": True,
            "service": "fcm",
            "api_key": "sample_fcm_api_key"
        },
        "email": {
            "enabled": True,
            "smtp_server": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "notifications@example.com",
            "smtp_password": "sample_password",
            "from_address": "smart-home@example.com",
            "from_name": "Maison Connectée"
        },
        "sms": {
            "enabled": True,
            "service": "twilio",
            "account_sid": "sample_account_sid",
            "auth_token": "sample_auth_token",
            "from_number": "+33612345678"
        }
    },
    "users": {
        "user1": {
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "+33612345678",
            "push_tokens": ["sample_push_token_1"],
            "accepted_types": ["info", "warning", "error", "security", "home"],
            "urgent_channels": ["push", "sms", "email"],
            "high_channels": ["push", "email"],
            "normal_channels": ["push"],
            "low_channels": ["push"],
            "quiet_hours_enabled": True,
            "quiet_hours_start": "22:30",
            "quiet_hours_end": "07:30"
        },
        "user2": {
            "name": "Jane Doe",
            "email": "jane.doe@example.com",
            "phone": "+33687654321",
            "push_tokens": ["sample_push_token_2"],
            "accepted_types": ["info", "warning", "error", "security"],
            "urgent_channels": ["push", "sms"],
            "high_channels": ["push"],
            "normal_channels": ["push"],
            "low_channels": [],
            "quiet_hours_enabled": True,
            "quiet_hours_start": "23:00",
            "quiet_hours_end": "08:00"
        }
    },
    "templates": {
        "welcome": {
            "title": "Bienvenue sur votre maison connectée",
            "message": "Bonjour {name}, votre système domotique est maintenant configuré et prêt à l'emploi."
        },
        "alarm_triggered": {
            "title": "Alerte de sécurité",
            "message": "Une alerte a été détectée par {sensor_name} dans la zone {zone_name} à {time}."
        },
        "low_battery": {
            "title": "Batterie faible",
            "message": "La batterie de {device_name} est faible ({level}%). Veuillez la remplacer dès que possible."
        }
    },
    "rate_limits": {
        "max_per_hour": 10,
        "max_per_day": 50
    },
    "quiet_hours": {
        "start": "22:00",
        "end": "07:00"
    }
}