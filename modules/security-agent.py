                    "success": False,
                    "error": "unknown_action",
                    "action": action
                })
    
    def _handle_alert_verification(self, message: Dict[str, Any]):
        """Gère les demandes de vérification d'alerte."""
        alert_id = message.get("alert_id")
        verified = message.get("verified", False)
        false_alarm = message.get("false_alarm", False)
        notes = message.get("notes", "")
        
        if not alert_id or alert_id not in self.current_alerts:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "invalid_alert_id",
                    "alert_id": alert_id
                })
            return
        
        # Mettre à jour l'alerte
        alert = self.current_alerts[alert_id]
        alert["verified"] = verified
        alert["false_alarm"] = false_alarm
        
        if notes:
            alert["notes"] = notes
        
        # Si c'est une fausse alerte, désactiver l'alarme
        if false_alarm:
            # Désactiver l'alarme
            self.message_bus.publish("security/alarm", {
                "action": "deactivate",
                "reason": f"false_alarm_{alert_id}"
            })
            
            # Mettre à jour le statut de l'alerte
            alert["status"] = "resolved"
        else:
            # Mettre à jour le statut de l'alerte
            alert["status"] = "verified"
        
        # Ajouter à l'historique des événements
        self._add_security_event("alert_verification", {
            "alert_id": alert_id,
            "verified": verified,
            "false_alarm": false_alarm,
            "notes": notes,
            "timestamp": time.time()
        })
        
        # Répondre avec succès
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "alert_id": alert_id,
                "status": alert["status"]
            })
    
    def _handle_emergency_request(self, message: Dict[str, Any]):
        """Gère les demandes d'urgence."""
        emergency_type = message.get("type")
        location = message.get("location")
        user_id = message.get("user_id")
        details = message.get("details", {})
        
        if not emergency_type:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_emergency_type"
                })
            return
        
        # Générer un identifiant unique pour la demande d'urgence
        emergency_id = f"emergency_{int(time.time())}_{emergency_type}"
        
        # Ajouter à l'historique des événements
        self._add_security_event("emergency_request", {
            "id": emergency_id,
            "type": emergency_type,
            "location": location,
            "user_id": user_id,
            "details": details,
            "timestamp": time.time()
        })
        
        # Traiter la demande d'urgence en fonction du type
        if emergency_type == "police":
            # Appel à la police
            self._initiate_emergency_call(emergency_id, "police")
        
        elif emergency_type == "fire":
            # Appel aux pompiers
            self._initiate_emergency_call(emergency_id, "fire")
        
        elif emergency_type == "medical":
            # Appel médical d'urgence
            self._initiate_emergency_call(emergency_id, "medical")
        
        elif emergency_type == "panic":
            # Bouton panique - actions multiples
            
            # 1. Activer l'alarme
            self.message_bus.publish("security/alarm", {
                "action": "activate",
                "reason": f"panic_button_{emergency_id}"
            })
            
            # 2. Enregistrer toutes les caméras
            for camera_id in self.config.get("cameras", []):
                recording_id = f"rec_{int(time.time())}_{camera_id}"
                self.message_bus.publish("camera/record", {
                    "camera_id": camera_id,
                    "duration": 300,
                    "recording_id": recording_id
                })
            
            # 3. Envoyer des notifications
            notification_modules = self.module_manager.get_modules_by_type("notification")
            if notification_modules:
                for contact in self.emergency_contacts:
                    self.message_bus.publish("notification/send", {
                        "user_id": contact,
                        "title": "ALERTE PANIQUE",
                        "message": f"Bouton panique activé par {user_id or 'un utilisateur inconnu'} à {location or 'emplacement inconnu'}.",
                        "priority": "urgent",
                        "type": "security"
                    })
            
            # 4. Appel d'urgence si configuré
            if self.enable_emergency_calls:
                self._initiate_emergency_call(emergency_id, "police")
        
        else:
            # Type d'urgence inconnu
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "unknown_emergency_type",
                    "type": emergency_type
                })
            return
        
        # Répondre avec succès
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "emergency_id": emergency_id,
                "type": emergency_type
            })
    
    def get_status(self) -> Dict[str, Any]:
        """
        Récupère le statut de l'agent de sécurité.
        
        Returns:
            Dict: Statut de l'agent
        """
        # Récupérer le statut de base
        status = super().get_status()
        
        # Ajouter des informations spécifiques à la sécurité
        security_modules = self.module_manager.get_modules_by_type("security")
        security_status = {}
        
        if security_modules:
            security_module = security_modules[0]
            security_status = security_module.get_status()
        
        # Compter les alertes actives
        active_alerts = len([alert_id for alert_id, alert in self.current_alerts.items() 
                           if alert["status"] in ["new", "processing", "active", "verified"]])
        
        status.update({
            "security_status": security_status,
            "active_alerts": active_alerts,
            "monitoring_service": self.monitoring_service.get("enabled", False),
            "emergency_calls": self.enable_emergency_calls,
            "recent_events": self.security_events[:5]  # 5 événements les plus récents
        })
        
        return status
    
    def get_security_events(self, limit: int = 20, event_type: str = None) -> List[Dict[str, Any]]:
        """
        Récupère les événements de sécurité récents.
        
        Args:
            limit: Nombre maximum d'événements à retourner
            event_type: Type d'événement pour filtrer (optionnel)
            
        Returns:
            List: Liste des événements
        """
        if event_type:
            filtered_events = [event for event in self.security_events if event["type"] == event_type]
            return filtered_events[:limit]
        else:
            return self.security_events[:limit]
    
    def get_alerts(self, status: str = None) -> Dict[str, Dict[str, Any]]:
        """
        Récupère les alertes de sécurité.
        
        Args:
            status: Statut des alertes à filtrer (optionnel)
            
        Returns:
            Dict: Dictionnaire des alertes
        """
        if status:
            return {alert_id: alert for alert_id, alert in self.current_alerts.items()
                   if alert["status"] == status}
        else:
            return self.current_alerts


# Exemple de configuration pour les tests
SAMPLE_CONFIG = {
    "emergency_contacts": ["user1", "user2"],
    "alarm_settings": {
        "initial_state": "disarmed",
        "default_code": "1234",
        "entry_delay": 30,
        "exit_delay": 60,
        "siren_duration": 300
    },
    "monitoring_service": {
        "enabled": False,
        "account_id": "SAMPLE123",
        "intrusion_monitoring": True,
        "fire_monitoring": True,
        "gas_monitoring": True,
        "medical_monitoring": True
    },
    "enable_emergency_calls": False,
    "users": ["user1", "user2", "user3"],
    "emergency_numbers": {
        "police": "17",
        "fire": "18",
        "medical": "15",
        "default": "112"
    },
    "camera_zones": {
        "entrance": ["cam1"],
        "living_room": ["cam2"],
        "kitchen": ["cam3"],
        "backyard": ["cam4"]
    },
    "camera_motion_alerts": True,
    "camera_motion_triggers_alarm": True,
    "auto_water_shutoff": True,
    "auto_gas_shutoff": True,
    "emergency_call_on_fire": True,
    "emergency_call_on_gas": True,
    "emergency_call_on_intrusion": False,
    "emergency_call_on_medical": True,
    "cameras": ["cam1", "cam2", "cam3", "cam4"]
}
"""Vérifie l'état initial des capteurs."""
        # Récupérer l'état de tous les capteurs de sécurité
        security_modules = self.module_manager.get_modules_by_type("security")
        if security_modules:
            security_module = security_modules[0]
            
            # Vérifier l'état des capteurs (portes, fenêtres, mouvement)
            status = security_module.get_status()
            
            # Journaliser les capteurs ouverts ou actifs
            if "open_doors" in status and status["open_doors"]:
                self.logger.warning(f"Portes ouvertes: {status['open_doors']}")
                
            if "open_windows" in status and status["open_windows"]:
                self.logger.warning(f"Fenêtres ouvertes: {status['open_windows']}")
            
            # Ajouter à l'historique des événements
            if "open_doors" in status and status["open_doors"]:
                self._add_security_event("initial_state", {
                    "type": "open_doors",
                    "sensors": status["open_doors"]
                })
                
            if "open_windows" in status and status["open_windows"]:
                self._add_security_event("initial_state", {
                    "type": "open_windows",
                    "sensors": status["open_windows"]
                })
    
    def _add_security_event(self, event_type: str, data: Dict[str, Any]):
        """
        Ajoute un événement de sécurité à l'historique.
        
        Args:
            event_type: Type d'événement
            data: Données de l'événement
        """
        event = {
            "timestamp": time.time(),
            "type": event_type,
            "data": data
        }
        
        # Ajouter à l'historique des événements
        self.security_events.insert(0, event)
        
        # Limiter la taille de l'historique
        max_events = 1000
        if len(self.security_events) > max_events:
            self.security_events = self.security_events[:max_events]
    
    def _handle_security_alert(self, message: Dict[str, Any]):
        """Gère les alertes de sécurité provenant des modules de sécurité."""
        alert_type = message.get("type")
        sensor_id = message.get("sensor_id")
        zone = message.get("zone")
        severity = message.get("severity", "high")
        
        if not alert_type or not sensor_id:
            return
            
        # Générer un identifiant unique pour l'alerte
        alert_id = f"alert_{int(time.time())}_{sensor_id}"
        
        # Stocker l'alerte dans l'état courant
        self.current_alerts[alert_id] = {
            "id": alert_id,
            "type": alert_type,
            "sensor_id": sensor_id,
            "zone": zone,
            "severity": severity,
            "timestamp": time.time(),
            "status": "new",
            "verified": False
        }
        
        # Ajouter à l'historique des événements
        self._add_security_event("alert", {
            "alert_id": alert_id,
            "type": alert_type,
            "sensor_id": sensor_id,
            "zone": zone,
            "severity": severity
        })
        
        # Déterminer la réponse appropriée en fonction du type et de la sévérité
        self._process_security_alert(alert_id)
        
        # Répondre avec confirmation
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "alert_id": alert_id
            })
    
    def _process_security_alert(self, alert_id: str):
        """
        Traite une alerte de sécurité et détermine la réponse appropriée.
        
        Args:
            alert_id: Identifiant de l'alerte
        """
        if alert_id not in self.current_alerts:
            return
            
        alert = self.current_alerts[alert_id]
        alert_type = alert["type"]
        severity = alert["severity"]
        
        # Mettre à jour le statut de l'alerte
        alert["status"] = "processing"
        
        # Déclencher des actions en fonction du type d'alerte
        if alert_type == "intrusion":
            # Alerte d'intrusion (porte/fenêtre forcée, détection de mouvement)
            self._handle_intrusion_alert(alert_id)
        
        elif alert_type == "fire":
            # Alerte incendie
            self._handle_fire_alert(alert_id)
        
        elif alert_type == "water":
            # Alerte fuite d'eau
            self._handle_water_alert(alert_id)
        
        elif alert_type == "gas":
            # Alerte fuite de gaz
            self._handle_gas_alert(alert_id)
        
        elif alert_type == "medical":
            # Alerte médicale
            self._handle_medical_alert(alert_id)
        
        else:
            # Autre type d'alerte
            self._handle_generic_alert(alert_id)
    
    def _handle_intrusion_alert(self, alert_id: str):
        """
        Gère une alerte d'intrusion.
        
        Args:
            alert_id: Identifiant de l'alerte
        """
        alert = self.current_alerts[alert_id]
        
        # Vérifier si quelqu'un est à la maison
        presence_modules = self.module_manager.get_modules_by_type("presence")
        someone_home = False
        
        if presence_modules:
            presence_module = presence_modules[0]
            status = presence_module.get_status()
            someone_home = len(status.get("home_persons", [])) > 0
        
        # Actions à entreprendre
        
        # 1. Activer l'alarme si pas déjà active
        self.message_bus.publish("security/alarm", {
            "action": "activate",
            "reason": f"intrusion_alert_{alert_id}"
        })
        
        # 2. Enregistrer des caméras dans la zone concernée
        if "zone" in alert:
            self._start_camera_recording(alert["zone"])
        
        # 3. Envoyer des notifications
        notification_modules = self.module_manager.get_modules_by_type("notification")
        if notification_modules:
            notification_module = notification_modules[0]
            
            # Notification à tous les utilisateurs avec niveau d'urgence élevé
            for user_id in self.config.get("users", []):
                self.message_bus.publish("notification/send", {
                    "user_id": user_id,
                    "title": "Alerte intrusion",
                    "message": f"Intrusion détectée par le capteur {alert['sensor_id']} dans la zone {alert.get('zone', 'inconnue')}.",
                    "priority": "urgent",
                    "type": "security"
                })
        
        # 4. Contacter le service de surveillance si configuré
        if self.monitoring_service.get("enabled", False) and self.monitoring_service.get("intrusion_monitoring", False):
            self._contact_monitoring_service(alert_id, "intrusion")
        
        # 5. Appel d'urgence automatique si configuré et personne n'est à la maison
        if self.enable_emergency_calls and not someone_home and self.config.get("emergency_call_on_intrusion", False):
            self._initiate_emergency_call(alert_id, "police")
        
        # Mettre à jour le statut de l'alerte
        alert["status"] = "active"
    
    def _handle_fire_alert(self, alert_id: str):
        """
        Gère une alerte incendie.
        
        Args:
            alert_id: Identifiant de l'alerte
        """
        alert = self.current_alerts[alert_id]
        
        # Vérifier si quelqu'un est à la maison
        presence_modules = self.module_manager.get_modules_by_type("presence")
        someone_home = False
        
        if presence_modules:
            presence_module = presence_modules[0]
            status = presence_module.get_status()
            someone_home = len(status.get("home_persons", [])) > 0
        
        # Actions à entreprendre
        
        # 1. Activer l'alarme incendie
        self.message_bus.publish("security/alarm", {
            "action": "activate",
            "type": "fire",
            "reason": f"fire_alert_{alert_id}"
        })
        
        # 2. Allumer toutes les lumières pour faciliter l'évacuation
        self.message_bus.publish("lighting/scene", {
            "scene_id": "emergency"
        })
        
        # 3. Envoyer des notifications
        notification_modules = self.module_manager.get_modules_by_type("notification")
        if notification_modules:
            notification_module = notification_modules[0]
            
            # Notification à tous les utilisateurs avec niveau d'urgence maximale
            for user_id in self.config.get("users", []):
                self.message_bus.publish("notification/send", {
                    "user_id": user_id,
                    "title": "ALERTE INCENDIE",
                    "message": f"Détection d'incendie par le capteur {alert['sensor_id']} dans la zone {alert.get('zone', 'inconnue')}. Évacuez immédiatement !",
                    "priority": "urgent",
                    "type": "security"
                })
        
        # 4. Contacter le service de surveillance si configuré
        if self.monitoring_service.get("enabled", False) and self.monitoring_service.get("fire_monitoring", False):
            self._contact_monitoring_service(alert_id, "fire")
        
        # 5. Appel d'urgence automatique si configuré
        if self.enable_emergency_calls and self.config.get("emergency_call_on_fire", True):
            self._initiate_emergency_call(alert_id, "fire")
        
        # Mettre à jour le statut de l'alerte
        alert["status"] = "active"
    
    def _handle_water_alert(self, alert_id: str):
        """
        Gère une alerte de fuite d'eau.
        
        Args:
            alert_id: Identifiant de l'alerte
        """
        alert = self.current_alerts[alert_id]
        
        # Actions à entreprendre
        
        # 1. Envoyer des notifications
        notification_modules = self.module_manager.get_modules_by_type("notification")
        if notification_modules:
            notification_module = notification_modules[0]
            
            # Notification à tous les utilisateurs
            for user_id in self.config.get("users", []):
                self.message_bus.publish("notification/send", {
                    "user_id": user_id,
                    "title": "Alerte fuite d'eau",
                    "message": f"Fuite d'eau détectée par le capteur {alert['sensor_id']} dans la zone {alert.get('zone', 'inconnue')}.",
                    "priority": "high",
                    "type": "security"
                })
        
        # 2. Tenter de fermer automatiquement la vanne d'eau si disponible
        if self.config.get("auto_water_shutoff", False):
            self.message_bus.publish("device/water_valve", {
                "action": "close",
                "reason": f"water_alert_{alert_id}"
            })
        
        # Mettre à jour le statut de l'alerte
        alert["status"] = "active"
    
    def _handle_gas_alert(self, alert_id: str):
        """
        Gère une alerte de fuite de gaz.
        
        Args:
            alert_id: Identifiant de l'alerte
        """
        alert = self.current_alerts[alert_id]
        
        # Vérifier si quelqu'un est à la maison
        presence_modules = self.module_manager.get_modules_by_type("presence")
        someone_home = False
        
        if presence_modules:
            presence_module = presence_modules[0]
            status = presence_module.get_status()
            someone_home = len(status.get("home_persons", [])) > 0
        
        # Actions à entreprendre
        
        # 1. Activer l'alarme
        self.message_bus.publish("security/alarm", {
            "action": "activate",
            "type": "gas",
            "reason": f"gas_alert_{alert_id}"
        })
        
        # 2. Allumer toutes les lumières pour faciliter l'évacuation (si sans danger)
        self.message_bus.publish("lighting/scene", {
            "scene_id": "emergency"
        })
        
        # 3. Tenter de fermer automatiquement la vanne de gaz si disponible
        if self.config.get("auto_gas_shutoff", False):
            self.message_bus.publish("device/gas_valve", {
                "action": "close",
                "reason": f"gas_alert_{alert_id}"
            })
        
        # 4. Envoyer des notifications
        notification_modules = self.module_manager.get_modules_by_type("notification")
        if notification_modules:
            notification_module = notification_modules[0]
            
            # Notification à tous les utilisateurs avec niveau d'urgence maximale
            for user_id in self.config.get("users", []):
                self.message_bus.publish("notification/send", {
                    "user_id": user_id,
                    "title": "ALERTE FUITE DE GAZ",
                    "message": f"Fuite de gaz détectée par le capteur {alert['sensor_id']} dans la zone {alert.get('zone', 'inconnue')}. Évacuez immédiatement !",
                    "priority": "urgent",
                    "type": "security"
                })
        
        # 5. Contacter le service de surveillance si configuré
        if self.monitoring_service.get("enabled", False) and self.monitoring_service.get("gas_monitoring", False):
            self._contact_monitoring_service(alert_id, "gas")
        
        # 6. Appel d'urgence automatique si configuré
        if self.enable_emergency_calls and self.config.get("emergency_call_on_gas", True):
            self._initiate_emergency_call(alert_id, "fire")  # Souvent traité comme urgence incendie
        
        # Mettre à jour le statut de l'alerte
        alert["status"] = "active"
    
    def _handle_medical_alert(self, alert_id: str):
        """
        Gère une alerte médicale.
        
        Args:
            alert_id: Identifiant de l'alerte
        """
        alert = self.current_alerts[alert_id]
        
        # Actions à entreprendre
        
        # 1. Envoyer des notifications
        notification_modules = self.module_manager.get_modules_by_type("notification")
        if notification_modules:
            notification_module = notification_modules[0]
            
            # Notification à tous les utilisateurs avec niveau d'urgence élevé
            for user_id in self.config.get("users", []):
                self.message_bus.publish("notification/send", {
                    "user_id": user_id,
                    "title": "Alerte médicale",
                    "message": f"Alerte médicale déclenchée par le capteur {alert['sensor_id']} dans la zone {alert.get('zone', 'inconnue')}.",
                    "priority": "urgent",
                    "type": "security"
                })
        
        # 2. Contacter le service de surveillance si configuré
        if self.monitoring_service.get("enabled", False) and self.monitoring_service.get("medical_monitoring", False):
            self._contact_monitoring_service(alert_id, "medical")
        
        # 3. Appel d'urgence automatique si configuré
        if self.enable_emergency_calls and self.config.get("emergency_call_on_medical", True):
            self._initiate_emergency_call(alert_id, "medical")
        
        # Mettre à jour le statut de l'alerte
        alert["status"] = "active"
    
    def _handle_generic_alert(self, alert_id: str):
        """
        Gère une alerte générique.
        
        Args:
            alert_id: Identifiant de l'alerte
        """
        alert = self.current_alerts[alert_id]
        
        # Actions à entreprendre
        
        # 1. Envoyer des notifications
        notification_modules = self.module_manager.get_modules_by_type("notification")
        if notification_modules:
            notification_module = notification_modules[0]
            
            # Notification à tous les utilisateurs
            for user_id in self.config.get("users", []):
                self.message_bus.publish("notification/send", {
                    "user_id": user_id,
                    "title": "Alerte de sécurité",
                    "message": f"Alerte de type {alert['type']} déclenchée par le capteur {alert['sensor_id']} dans la zone {alert.get('zone', 'inconnue')}.",
                    "priority": "high",
                    "type": "security"
                })
        
        # Mettre à jour le statut de l'alerte
        alert["status"] = "active"
    
    def _start_camera_recording(self, zone: str):
        """
        Démarre l'enregistrement des caméras dans une zone spécifique.
        
        Args:
            zone: Identifiant de la zone
        """
        # Récupérer les caméras de la zone
        cameras = self._get_zone_cameras(zone)
        
        if not cameras:
            self.logger.warning(f"Aucune caméra trouvée dans la zone {zone}")
            return
        
        # Démarrer l'enregistrement de chaque caméra
        for camera_id in cameras:
            recording_id = f"rec_{int(time.time())}_{camera_id}"
            
            # Enregistrer pendant 5 minutes (300 secondes)
            self.message_bus.publish("camera/record", {
                "camera_id": camera_id,
                "duration": 300,
                "recording_id": recording_id
            })
            
            # Stocker l'information d'enregistrement
            self.video_recordings[recording_id] = {
                "id": recording_id,
                "camera_id": camera_id,
                "start_time": time.time(),
                "duration": 300,
                "zone": zone,
                "reason": f"security_alert_{zone}"
            }
            
            self.logger.info(f"Démarrage de l'enregistrement {recording_id} pour la caméra {camera_id}")
    
    def _get_zone_cameras(self, zone: str) -> List[str]:
        """
        Récupère les identifiants des caméras d'une zone.
        
        Args:
            zone: Identifiant de la zone
            
        Returns:
            List[str]: Liste des identifiants de caméras
        """
        # Cette méthode devrait récupérer les caméras depuis la configuration ou l'état
        # Pour simplifier, nous utilisons des identifiants génériques
        camera_zones = self.config.get("camera_zones", {})
        return camera_zones.get(zone, [])
    
    def _contact_monitoring_service(self, alert_id: str, alert_type: str):
        """
        Contacte le service de surveillance externe.
        
        Args:
            alert_id: Identifiant de l'alerte
            alert_type: Type d'alerte
        """
        # Dans une implémentation réelle, nous contacterions un service externe
        # par API ou autre moyen de communication
        self.logger.info(f"Contacter le service de surveillance pour l'alerte {alert_id} de type {alert_type}")
        
        # Simuler l'appel au service
        monitoring_config = self.monitoring_service
        account_id = monitoring_config.get("account_id", "UNKNOWN")
        
        # Ajouter à l'historique des événements
        self._add_security_event("monitoring_contact", {
            "alert_id": alert_id,
            "alert_type": alert_type,
            "account_id": account_id,
            "timestamp": time.time()
        })
    
    def _initiate_emergency_call(self, alert_id: str, service_type: str):
        """
        Initie un appel d'urgence automatique.
        
        Args:
            alert_id: Identifiant de l'alerte
            service_type: Type de service d'urgence (police, fire, medical)
        """
        if not self.enable_emergency_calls:
            self.logger.warning("Les appels d'urgence automatiques sont désactivés")
            return
            
        # Dans une implémentation réelle, nous pourrions utiliser une API
        # pour initier un appel téléphonique via un service tiers
        self.logger.info(f"Initier un appel d'urgence pour l'alerte {alert_id} - service: {service_type}")
        
        # Déterminer le numéro à appeler en fonction du type de service
        emergency_numbers = self.config.get("emergency_numbers", {})
        number = emergency_numbers.get(service_type, emergency_numbers.get("default", "112"))
        
        # Ajouter à l'historique des événements
        self._add_security_event("emergency_call", {
            "alert_id": alert_id,
            "service_type": service_type,
            "number": number,
            "timestamp": time.time()
        })
    
    def _handle_security_event(self, message: Dict[str, Any]):
        """Gère les événements de sécurité génériques."""
        event_type = message.get("type")
        data = message.get("data", {})
        
        if not event_type:
            return
            
        # Ajouter à l'historique des événements
        self._add_security_event(event_type, data)
        
        # Répondre avec confirmation
        if "reply_topic" in message:
            self.message_bus.publish(message["reply_topic"], {
                "success": True,
                "event_type": event_type
            })
    
    def _handle_camera_motion(self, message: Dict[str, Any]):
        """Gère les détections de mouvement par caméra."""
        camera_id = message.get("camera_id")
        motion = message.get("motion", False)
        zone = message.get("zone")
        
        if not camera_id or not motion:
            return
            
        # Vérifier l'état du système de sécurité
        security_modules = self.module_manager.get_modules_by_type("security")
        system_armed = False
        
        if security_modules:
            security_module = security_modules[0]
            status = security_module.get_status()
            system_armed = status.get("state") in ["armed_away", "armed_home"]
        
        # Si le système est armé, traiter comme une alerte potentielle
        if system_armed:
            # Ajouter à l'historique des événements
            self._add_security_event("camera_motion", {
                "camera_id": camera_id,
                "zone": zone,
                "timestamp": time.time()
            })
            
            # Démarrer l'enregistrement
            recording_id = f"rec_{int(time.time())}_{camera_id}"
            
            # Enregistrer pendant 2 minutes (120 secondes)
            self.message_bus.publish("camera/record", {
                "camera_id": camera_id,
                "duration": 120,
                "recording_id": recording_id
            })
            
            # Stocker l'information d'enregistrement
            self.video_recordings[recording_id] = {
                "id": recording_id,
                "camera_id": camera_id,
                "start_time": time.time(),
                "duration": 120,
                "zone": zone,
                "reason": "motion_detection"
            }
            
            # Si configuré pour générer des alertes sur mouvement caméra
            if self.config.get("camera_motion_alerts", True):
                # Créer une alerte
                alert_id = f"alert_{int(time.time())}_{camera_id}"
                
                # Stocker l'alerte
                self.current_alerts[alert_id] = {
                    "id": alert_id,
                    "type": "camera_motion",
                    "camera_id": camera_id,
                    "zone": zone,
                    "severity": "medium",
                    "timestamp": time.time(),
                    "status": "new",
                    "verified": False
                }
                
                # Traiter l'alerte
                self._handle_camera_motion_alert(alert_id)
    
    def _handle_camera_motion_alert(self, alert_id: str):
        """
        Gère une alerte de mouvement détecté par caméra.
        
        Args:
            alert_id: Identifiant de l'alerte
        """
        alert = self.current_alerts[alert_id]
        camera_id = alert.get("camera_id")
        zone = alert.get("zone", "inconnue")
        
        # Vérifier la présence pour éviter les faux positifs
        presence_modules = self.module_manager.get_modules_by_type("presence")
        someone_home = False
        
        if presence_modules:
            presence_module = presence_modules[0]
            status = presence_module.get_status()
            someone_home = len(status.get("home_persons", [])) > 0
        
        # Définir la sévérité en fonction de la présence
        security_modules = self.module_manager.get_modules_by_type("security")
        if security_modules:
            security_module = security_modules[0]
            status = security_module.get_status()
            
            # Si personne n'est à la maison et le système est armé en mode absence
            if not someone_home and status.get("state") == "armed_away":
                alert["severity"] = "high"
                
                # Envoyer des notifications
                notification_modules = self.module_manager.get_modules_by_type("notification")
                if notification_modules:
                    for user_id in self.config.get("users", []):
                        self.message_bus.publish("notification/send", {
                            "user_id": user_id,
                            "title": "Alerte mouvement caméra",
                            "message": f"Mouvement détecté par la caméra {camera_id} dans la zone {zone} alors que personne n'est à la maison.",
                            "priority": "high",
                            "type": "security"
                        })
                
                # Si configuré pour déclencher l'alarme sur mouvement caméra
                if self.config.get("camera_motion_triggers_alarm", True):
                    self.message_bus.publish("security/alarm", {
                        "action": "activate",
                        "reason": f"camera_motion_alert_{alert_id}"
                    })
            
            # Si quelqu'un est à la maison ou le système est armé en mode présence
            elif someone_home or status.get("state") == "armed_home":
                alert["severity"] = "low"
                
                # Envoyer des notifications d'information
                notification_modules = self.module_manager.get_modules_by_type("notification")
                if notification_modules:
                    for user_id in self.config.get("users", []):
                        self.message_bus.publish("notification/send", {
                            "user_id": user_id,
                            "title": "Mouvement détecté",
                            "message": f"Mouvement détecté par la caméra {camera_id} dans la zone {zone}.",
                            "priority": "normal",
                            "type": "security"
                        })
        
        # Mettre à jour le statut de l'alerte
        alert["status"] = "active"
    
    def _handle_alarm_control(self, message: Dict[str, Any]):
        """Gère les demandes de contrôle de l'alarme."""
        action = message.get("action")
        
        if not action:
            # Répondre avec une erreur
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "missing_action"
                })
            return
        
        if action == "activate":
            # Activer l'alarme
            reason = message.get("reason", "manual")
            alarm_type = message.get("type", "intrusion")
            
            # Transmettre au module de sécurité
            security_modules = self.module_manager.get_modules_by_type("security")
            if security_modules:
                # Activer la sirène et autres dispositifs d'alarme
                pass
            
            # Ajouter à l'historique des événements
            self._add_security_event("alarm_activated", {
                "reason": reason,
                "type": alarm_type,
                "timestamp": time.time()
            })
            
            # Répondre avec succès
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": True,
                    "action": action
                })
                
        elif action == "deactivate":
            # Désactiver l'alarme
            reason = message.get("reason", "manual")
            
            # Transmettre au module de sécurité
            security_modules = self.module_manager.get_modules_by_type("security")
            if security_modules:
                # Désactiver la sirène et autres dispositifs d'alarme
                pass
            
            # Ajouter à l'historique des événements
            self._add_security_event("alarm_deactivated", {
                "reason": reason,
                "timestamp": time.time()
            })
            
            # Répondre avec succès
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": True,
                    "action": action
                })
        
        else:
            # Action inconnue
            if "reply_topic" in message:
                self.message_bus.publish(message["reply_topic"], {
                    "success": False,
                    "error": "unknown_action",
                    "action": actionimport logging
import time
from typing import Dict, Any, List, Optional
import json

from base_agent import BaseAgent

class SecurityAgent(BaseAgent):
    """
    Agent spécialisé dans la sécurité de la maison.
    Gère le système d'alarme, la surveillance par caméra, la détection d'intrusion,
    et la coordination des notifications et réponses en cas d'alerte.
    """
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        """
        Initialise l'agent de sécurité.
        
        Args:
            agent_id: Identifiant unique de l'agent
            config: Configuration de l'agent
        """
        super().__init__(agent_id, config)
        
        # Configuration spécifique à la sécurité
        self.emergency_contacts = config.get("emergency_contacts", [])
        self.alarm_settings = config.get("alarm_settings", {})
        self.monitoring_service = config.get("monitoring_service", {})
        self.enable_emergency_calls = config.get("enable_emergency_calls", False)
        
        # État interne
        self.security_events = []
        self.current_alerts = {}
        self.video_recordings = {}
        
        self.logger.info("Agent de sécurité initialisé")
        
        # Enregistrer les gestionnaires de messages spécifiques
        self._register_specific_handlers()
    
    def _register_specific_handlers(self):
        """Enregistre les gestionnaires de messages spécifiques à l'agent de sécurité."""
        self.message_bus.register_handler("security/alert", self._handle_security_alert)
        self.message_bus.register_handler("security/event", self._handle_security_event)
        self.message_bus.register_handler("camera/motion", self._handle_camera_motion)
        self.message_bus.register_handler("security/alarm", self._handle_alarm_control)
        self.message_bus.register_handler("security/verify", self._handle_alert_verification)
        self.message_bus.register_handler("security/emergency", self._handle_emergency_request)
    
    def start(self):
        """Démarre l'agent de sécurité et initialise les modules nécessaires."""
        super().start()
        
        self.logger.info("Démarrage de l'agent de sécurité")
        
        # Vérifier et démarrer les modules requis
        self._ensure_required_modules()
        
        # Initialiser le système de sécurité
        self._initialize_security_system()
        
        # Vérifier l'état initial des capteurs
        self._check_initial_sensors()
        
        # Publier un événement d'initialisation complète
        self.message_bus.publish("security/initialized", {
            "agent_id": self.agent_id,
            "timestamp": time.time()
        })
    
    def _ensure_required_modules(self):
        """S'assure que tous les modules requis sont démarrés."""
        required_modules = [
            "security",
            "presence",
            "notification"
        ]
        
        # Vérifier que tous les modules requis sont présents et actifs
        for module_type in required_modules:
            modules = self.module_manager.get_modules_by_type(module_type)
            
            if not modules:
                self.logger.warning(f"Module requis non trouvé: {module_type}")
                
                # Essayer de démarrer le module avec la configuration par défaut
                try:
                    default_config = self.config.get("default_modules", {}).get(module_type, {})
                    self.module_manager.create_module(module_type, f"{module_type}_default", default_config)
                except Exception as e:
                    self.logger.error(f"Erreur lors de la création du module {module_type}: {e}")
    
    def _initialize_security_system(self):
        """Initialise le système de sécurité avec les paramètres configurés."""
        # Configurer le système en fonction des paramètres
        security_modules = self.module_manager.get_modules_by_type("security")
        if security_modules:
            # Utiliser le premier module de sécurité disponible
            security_module = security_modules[0]
            
            # Récupérer et appliquer la configuration initiale
            initial_state = self.alarm_settings.get("initial_state", "disarmed")
            
            if initial_state == "armed_home":
                self.message_bus.publish("security/arm", {
                    "mode": "home",
                    "code": self.alarm_settings.get("default_code")
                })
            elif initial_state == "armed_away":
                self.message_bus.publish("security/arm", {
                    "mode": "away",
                    "code": self.alarm_settings.get("default_code")
                })
            
            # Configurer le service de surveillance si activé
            if self.monitoring_service.get("enabled", False):
                # Dans une implémentation réelle, nous configurerions ici
                # la connexion avec un service de surveillance externe
                pass
    
    def _check_initial_sensors(self):
        """Vérifie l'état initial des capt