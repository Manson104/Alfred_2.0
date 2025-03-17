            emotional_context: Contexte émotionnel détecté
            
        Returns:
            Contexte pour la génération de réponse
        """
        context = {
            "user": user_info,
            "conversation": [{"role": item["direction"], "message": item["message"]} 
                           for item in conversation_history],
            "emotional_context": emotional_context,
            "current_time": datetime.datetime.now().strftime("%H:%M"),
            "current_date": datetime.datetime.now().strftime("%d/%m/%Y"),
            "day_of_week": datetime.datetime.now().strftime("%A"),
            "general_context": self.conversation_context
        }
        
        # Ajouter des événements à venir si pertinent
        upcoming_events = self._get_upcoming_events(self.current_user, days=1)
        if upcoming_events:
            context["upcoming_events"] = upcoming_events
        
        return context
    
    def _generate_response(self, message: str, context: Dict[str, Any]) -> str:
        """
        Génère une réponse personnalisée à l'aide des services NLP.
        
        Args:
            message: Message de l'utilisateur
            context: Contexte de génération
            
        Returns:
            Réponse générée
        """
        # Valeurs par défaut pour les informations utilisateur
        user_name = context.get("user", {}).get("name", "utilisateur")
        preferred_title = context.get("user", {}).get("preferred_title", "")
        
        # Construire une réponse par défaut si les services NLP ne sont pas disponibles
        if not self.anthropic_client and not self.openai_client:
            emotion = context.get("emotional_context", {}).get("emotion")
            if emotion == "fatigue":
                return f"Je comprends que vous êtes fatigué, {preferred_title}. Puis-je vous aider d'une manière particulière?"
            elif emotion == "stress":
                return f"Je perçois que vous êtes stressé, {preferred_title}. Y a-t-il quelque chose que je puisse faire pour vous aider?"
            elif emotion == "joie":
                return f"Je suis content de vous voir de bonne humeur, {preferred_title}. Comment puis-je contribuer à cette journée positive?"
            else:
                return f"Que puis-je faire pour vous, {preferred_title}?"
        
        try:
            # Construire le prompt pour la personnalisation de la réponse
            conversation_text = ""
            for item in context.get("conversation", [])[-5:]:  # 5 derniers échanges
                role = "Utilisateur" if item["role"] == "user_to_alfred" else "Alfred"
                conversation_text += f"{role}: {item['message']}\n"
            
            # Déterminer si l'utilisateur est dans un état émotionnel particulier
            emotional_hint = ""
            if context.get("emotional_context", {}).get("detected", False):
                emotion = context["emotional_context"]["emotion"]
                emotional_hint = f"L'utilisateur semble être {emotion}. "
                
                if emotion == "fatigue":
                    emotional_hint += "Sois particulièrement attentionné et propose de l'aider à se reposer ou à simplifier sa journée."
                elif emotion == "stress":
                    emotional_hint += "Sois calme, rassurant et propose des solutions concrètes pour réduire ce stress."
                elif emotion == "joie":
                    emotional_hint += "Partage son enthousiasme et renforce cette émotion positive."
                elif emotion == "frustration":
                    emotional_hint += "Sois patient, compréhensif et aide-le à résoudre ce qui le frustre."
            
            # Ajouter des éléments de contexte pertinents
            contextual_hints = []
            if "upcoming_events" in context:
                next_event = context["upcoming_events"][0]
                event_time = datetime.datetime.fromisoformat(next_event["start_date"]).strftime("%H:%M")
                contextual_hints.append(f"Prochain événement aujourd'hui: {next_event['title']} à {event_time}.")
            
            contextual_hints_text = "\n".join(contextual_hints)
            
            # Assembler le système de prompt complet
            system_prompt = f"""Tu es Alfred, un assistant personnel intelligent et attentionné pour la maison.
Tu t'adresses à {user_name} en utilisant "{preferred_title}" comme titre de politesse.
Ton objectif est d'être serviable, précis et de répondre de manière empathique.
{emotional_hint}

Éléments de contexte:
- Heure actuelle: {context.get('current_time')}
- Date: {context.get('current_date')} ({context.get('day_of_week')})
{contextual_hints_text}

Ton style de communication:
- Utilise un ton respectueux et professionnel, tout en restant chaleureux.
- Sois concis mais complet dans tes réponses.
- Propose de l'aide proactive quand c'est pertinent.
- Personnalise tes réponses en utilisant le titre préféré de l'utilisateur.
- Ne mentionne pas que tu es une IA ou un assistant virtuel, agis comme Alfred, le majordome.

Voici l'historique récent de la conversation:
{conversation_text}

Le message de l'utilisateur à répondre est:
"{message}"

Ta réponse (en tant qu'Alfred):"""
            
            if self.anthropic_client:
                response = self.anthropic_client.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=1000,
                    temperature=0.7,
                    system=system_prompt,
                    messages=[{"role": "user", "content": message}]
                )
                return response.content[0].text.strip()
            
            elif self.openai_client:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message}
                    ],
                    temperature=0.7,
                    max_tokens=500
                )
                return response.choices[0].message.content.strip()
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la génération de réponse avec NLP: {e}")
            return f"Je vous prie de m'excuser, {preferred_title}, mais je n'ai pas pu traiter votre demande correctement. Pourriez-vous reformuler ou me donner plus de détails?"
    
    def _update_last_interaction(self, user_id: str) -> None:
        """
        Met à jour le timestamp de la dernière interaction avec l'utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
        """
        try:
            now = datetime.datetime.now().isoformat()
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                UPDATE users SET last_interaction = ? WHERE id = ?
                """, (now, user_id))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Erreur lors de la mise à jour de la dernière interaction: {e}")
    
    def _extract_and_store_personal_info(self, user_id: str, user_message: str, ai_response: str) -> None:
        """
        Extrait et stocke de nouvelles informations personnelles à partir de la conversation.
        
        Args:
            user_id: ID de l'utilisateur
            user_message: Message de l'utilisateur
            ai_response: Réponse de l'assistant
        """
        if not self.anthropic_client and not self.openai_client:
            return
        
        # Nous n'analysons que périodiquement pour économiser les appels API
        should_analyze = random.random() < 0.2  # 20% de chance d'analyser
        if not should_analyze:
            return
        
        try:
            prompt = f"""
            Analyse la conversation ci-dessous entre un utilisateur et Alfred (assistant personnel).
            Identifie les informations personnelles importantes que l'utilisateur révèle et qui devraient être mémorisées pour personnaliser les futures interactions.
            
            Utilisateur: {user_message}
            Alfred: {ai_response}
            
            Réponds strictement au format JSON comme ceci:
            {{
                "info_found": true|false,
                "info_type": "preference|date|personal_detail|contact|health",
                "key": "nom_de_l_information",
                "value": "valeur_de_l_information",
                "confidence": 0.8
            }}
            
            Si aucune information à mémoriser n'est présente, renvoie "info_found": false.
            N'inclue pas d'autre texte dans ta réponse, seulement le JSON.
            """
            
            if self.anthropic_client:
                response = self.anthropic_client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=300,
                    temperature=0,
                    system="Tu es un assistant qui analyse des conversations pour extraire des informations personnelles importantes à mémoriser. Tu réponds uniquement au format JSON strict.",
                    messages=[{"role": "user", "content": prompt}]
                )
                
                response_text = response.content[0].text.strip()
                
            elif self.openai_client:
                response = self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Tu es un assistant qui analyse des conversations pour extraire des informations personnelles importantes à mémoriser. Tu réponds uniquement au format JSON strict."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0,
                    max_tokens=300
                )
                
                response_text = response.choices[0].message.content.strip()
            
            # Extraire le JSON de la réponse
            try:
                extracted_data = json.loads(response_text)
                
                if extracted_data.get("info_found", False) and all(key in extracted_data for key in ["info_type", "key", "value"]):
                    # Déterminer si l'information doit être chiffrée
                    should_encrypt = extracted_data["info_type"] in ["health", "contact"]
                    confidence = extracted_data.get("confidence", 0.5)
                    
                    # Ne stocker que si la confiance est suffisante
                    if confidence >= 0.7:
                        self.store_user_info(
                            user_id, 
                            extracted_data["info_type"],
                            extracted_data["key"],
                            extracted_data["value"],
                            should_encrypt
                        )
                        self.logger.info(f"Information personnelle extraite et mémorisée: {extracted_data['key']}")
            
            except json.JSONDecodeError:
                self.logger.error(f"Erreur de décodage JSON dans la réponse d'extraction: {response_text[:100]}...")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de l'extraction d'informations personnelles: {e}")
    
    def _save_conversation_message(self, user_id: str, direction: str, message: str) -> None:
        """
        Enregistre un message dans l'historique de conversation.
        
        Args:
            user_id: ID de l'utilisateur
            direction: "user_to_alfred" ou "alfred_to_user"
            message: Contenu du message
        """
        try:
            sentiment = None
            if direction == "user_to_alfred" and (self.anthropic_client or self.openai_client):
                # Nous pourrions analyser le sentiment, mais ce serait coûteux en appels API
                # pour chaque message. Ici, nous utilisons simplement l'analyse émotionnelle
                # déjà effectuée si disponible.
                if self.current_user in self.emotional_state:
                    sentiment = self.emotional_state[self.current_user].get("emotion")
            
            context_data = json.dumps(self.conversation_context) if self.conversation_context else None
            
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO conversation_history (user_id, direction, message, detected_sentiment, context_data)
                VALUES (?, ?, ?, ?, ?)
                """, (user_id, direction, message, sentiment, context_data))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Erreur lors de l'enregistrement du message: {e}")
    
    def handle_event_notification(self, user_id: str, event_type: str, event_data: Dict[str, Any]) -> None:
        """
        Traite une notification d'événement externe.
        
        Args:
            user_id: ID de l'utilisateur
            event_type: Type d'événement
            event_data: Données de l'événement
        """
        self.logger.info(f"Notification d'événement reçue: {event_type} pour l'utilisateur {user_id}")
        
        # Mettre à jour le contexte de conversation
        if event_type not in self.conversation_context:
            self.conversation_context[event_type] = {}
        
        self.conversation_context[event_type].update(event_data)
        
        # Générer une notification proactive si nécessaire
        if event_type == "print_complete":
            # Une impression 3D est terminée
            printer_name = event_data.get("printer_name", "")
            job_name = event_data.get("job_name", "")
            
            user_info = self._get_basic_user_info(user_id)
            preferred_title = user_info.get("preferred_title", "")
            
            message = f"{preferred_title}, votre impression 3D"
            if job_name:
                message += f" \"{job_name}\""
            if printer_name:
                message += f" sur {printer_name}"
            message += " est maintenant terminée. Souhaitez-vous lancer une autre impression ?"
            
            # Ajouter aux interactions proactives en attente
            self.pending_reminders.append({
                'user_id': user_id,
                'message': message,
                'type': 'event_notification',
                'event_type': event_type,
                'priority': 8  # Priorité élevée pour les notifications d'événements
            })
        
        elif event_type == "home_arrival":
            # L'utilisateur vient d'arriver chez lui
            now = datetime.datetime.now()
            hour = now.hour
            
            user_info = self._get_basic_user_info(user_id)
            preferred_title = user_info.get("preferred_title", "")
            
            # Message différent selon l'heure
            if 5 <= hour < 12:
                message = f"Bonjour {preferred_title}, bienvenue à la maison. Puis-je faire quelque chose pour vous ?"
            elif 12 <= hour < 18:
                message = f"Bon retour chez vous {preferred_title}. Comment s'est passée votre journée ?"
            else:
                message = f"Bonsoir {preferred_title}, heureux de vous revoir à la maison. Souhaitez-vous que je prépare quelque chose pour vous ?"
            
            # Ajouter aux interactions proactives en attente
            self.pending_reminders.append({
                'user_id': user_id,
                'message': message,
                'type': 'event_notification',
                'event_type': event_type,
                'priority': 7
            })
        
        elif event_type == "weather_alert":
            # Alerte météo importante
            alert_type = event_data.get("alert_type", "")
            alert_message = event_data.get("alert_message", "")
            
            user_info = self._get_basic_user_info(user_id)
            preferred_title = user_info.get("preferred_title", "")
            
            message = f"{preferred_title}, une alerte météo a été émise : {alert_message}"
            
            # Ajouter aux interactions proactives en attente
            self.pending_reminders.append({
                'user_id': user_id,
                'message': message,
                'type': 'event_notification',
                'event_type': event_type,
                'priority': 9  # Haute priorité pour les alertes météo
            })
    
    def update_user_context(self, user_id: str, context_update: Dict[str, Any]) -> None:
        """
        Met à jour le contexte d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            context_update: Nouvelles données de contexte
        """
        self.logger.info(f"Mise à jour du contexte pour l'utilisateur {user_id}")
        
        # Mettre à jour le contexte de conversation
        self.conversation_context.update(context_update)
        
        # Si le contexte contient de nouvelles informations sur l'utilisateur,
        # nous pourrions vouloir les stocker durablement
        for context_type, context_data in context_update.items():
            if context_type == "location" and isinstance(context_data, dict):
                # Stocker la localisation actuelle
                location_name = context_data.get("name")
                if location_name:
                    self.store_user_info(user_id, "context", "current_location", location_name, False)
            
            elif context_type == "weather" and isinstance(context_data, dict):
                # Stocker les conditions météo actuelles
                condition = context_data.get("condition")
                if condition:
                    self.store_user_info(user_id, "context", "weather_condition", condition, False)
            
            elif context_type == "home_status" and isinstance(context_data, dict):
                # Stocker l'état de la maison
                for device, status in context_data.items():
                    self.store_user_info(user_id, "home_status", device, str(status), False)
    
    def handle_calendar_event(self, user_id: str, event_data: Dict[str, Any]) -> None:
        """
        Traite un événement de calendrier.
        
        Args:
            user_id: ID de l'utilisateur
            event_data: Données de l'événement
        """
        self.logger.info(f"Événement de calendrier reçu pour l'utilisateur {user_id}")
        
        event_id = event_data.get("id")
        event_title = event_data.get("title", "Événement sans titre")
        event_start = event_data.get("start")
        event_end = event_data.get("end")
        event_description = event_data.get("description", "")
        
        # Vérifier si l'événement existe déjà
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT id FROM events 
                WHERE user_id = ? AND title = ? AND start_date = ?
                """, (user_id, event_title, event_start))
                
                existing_event = cursor.fetchone()
                
                if not existing_event:
                    # Créer un nouvel événement
                    reminder_time = 30  # 30 minutes par défaut
                    event_type = "appointment"  # Type par défaut
                    
                    # Déterminer le type d'événement
                    lower_title = event_title.lower()
                    if "anniversaire" in lower_title or "birthday" in lower_title:
                        event_type = "birthday"
                    elif "réunion" in lower_title or "meeting" in lower_title:
                        event_type = "meeting"
                    elif "rappel" in lower_title or "reminder" in lower_title:
                        event_type = "reminder"
                    
                    cursor.execute("""
                    INSERT INTO events (user_id, event_type, title, description, start_date, end_date, reminder_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, event_type, event_title, event_description, event_start, event_end, reminder_time))
                    
                    conn.commit()
                    self.logger.info(f"Nouvel événement ajouté pour l'utilisateur {user_id} : {event_title}")
        
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement de l'événement de calendrier: {e}")
    
    def create_user(self, name: str, preferred_title: str = None, preferred_tone: str = None) -> Dict[str, Any]:
        """
        Crée un nouvel utilisateur.
        
        Args:
            name: Nom de l'utilisateur
            preferred_title: Titre préféré (M., Madame, etc.)
            preferred_tone: Ton préféré
            
        Returns:
            Informations sur l'utilisateur créé
        """
        try:
            user_id = str(uuid.uuid4())
            now = datetime.datetime.now().isoformat()
            
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO users (id, name, created_at, preferred_title, preferred_tone)
                VALUES (?, ?, ?, ?, ?)
                """, (user_id, name, now, preferred_title, preferred_tone))
                conn.commit()
            
            self.logger.info(f"Nouvel utilisateur créé: {name} (ID: {user_id})")
            
            return {
                "success": True,
                "user_id": user_id,
                "name": name,
                "created_at": now
            }
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la création de l'utilisateur: {e}")
            return {"success": False, "error": str(e)}
    
    def store_user_info(self, user_id: str, info_type: str, key: str, value: str, encrypt: bool = False) -> Dict[str, Any]:
        """
        Stocke une information utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            info_type: Type d'information (preference, date, contact, etc.)
            key: Clé de l'information
            value: Valeur de l'information
            encrypt: Si True, la valeur sera chiffrée
            
        Returns:
            Statut de l'opération
        """
        try:
            # Vérifier si l'utilisateur existe
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
                if not cursor.fetchone():
                    return {"success": False, "error": f"Utilisateur avec ID {user_id} non trouvé"}
                
                # Chiffrer la valeur si nécessaire
                stored_value = self._encrypt_data(value) if encrypt else value
                now = datetime.datetime.now().isoformat()
                
                # Vérifier si l'information existe déjà
                cursor.execute("""
                SELECT id FROM personal_info 
                WHERE user_id = ? AND info_type = ? AND key = ?
                """, (user_id, info_type, key))
                
                existing_info = cursor.fetchone()
                
                if existing_info:
                    # Mettre à jour l'information existante
                    cursor.execute("""
                    UPDATE personal_info 
                    SET value = ?, is_encrypted = ?, updated_at = ?
                    WHERE user_id = ? AND info_type = ? AND key = ?
                    """, (stored_value, 1 if encrypt else 0, now, user_id, info_type, key))
                else:
                    # Insérer une nouvelle information
                    cursor.execute("""
                    INSERT INTO personal_info (user_id, info_type, key, value, is_encrypted, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, info_type, key, stored_value, 1 if encrypt else 0, now, now))
                
                conn.commit()
            
            self.logger.info(f"Information utilisateur stockée: {info_type}.{key} pour l'utilisateur {user_id}")
            
            return {"success": True, "info_type": info_type, "key": key}
        
        except Exception as e:
            self.logger.error(f"Erreur lors du stockage de l'information utilisateur: {e}")
            return {"success": False, "error": str(e)}
    
    def get_user_info(self, user_id: str, info_type: str = None) -> Dict[str, Any]:
        """
        Récupère les informations d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            info_type: Type d'information à récupérer (facultatif)
            
        Returns:
            Informations récupérées
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                if info_type:
                    # Récupérer les informations d'un type spécifique
                    cursor.execute("""
                    SELECT info_type, key, value, is_encrypted
                    FROM personal_info 
                    WHERE user_id = ? AND info_type = ?
                    """, (user_id, info_type))
                else:
                    # Récupérer toutes les informations
                    cursor.execute("""
                    SELECT info_type, key, value, is_encrypted
                    FROM personal_info 
                    WHERE user_id = ?
                    """, (user_id,))
                
                results = {}
                for row in cursor.fetchall():
                    info_type_key = row["info_type"]
                    if info_type_key not in results:
                        results[info_type_key] = {}
                    
                    value = row["value"]
                    if row["is_encrypted"]:
                        try:
                            value = self._decrypt_data(value)
                        except Exception:
                            value = "<données chiffrées>"
                    
                    results[info_type_key][row["key"]] = value
                
                return {"success": True, "user_id": user_id, "info": results}
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des informations utilisateur: {e}")
            return {"success": False, "error": str(e)}
    
    def create_event(self, user_id: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un nouvel événement pour un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            event_data: Données de l'événement
            
        Returns:
            Statut de l'opération
        """
        try:
            event_type = event_data.get("event_type", "appointment")
            title = event_data.get("title")
            description = event_data.get("description", "")
            start_date = event_data.get("start_date")
            end_date = event_data.get("end_date")
            reminder_time = event_data.get("reminder_time", 30)  # 30 minutes par défaut
            
            if not title or not start_date:
                return {"success": False, "error": "Titre et date de début requis"}
            
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO events (user_id, event_type, title, description, start_date, end_date, reminder_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, event_type, title, description, start_date, end_date, reminder_time))
                
                event_id = cursor.lastrowid
                conn.commit()
            
            self.logger.info(f"Nouvel événement créé pour l'utilisateur {user_id}: {title}")
            
            return {
                "success": True,
                "event_id": event_id,
                "title": title,
                "start_date": start_date
            }
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la création de l'événement: {e}")
            return {"success": False, "error": str(e)}
    
    def create_proactive_reminder(self, user_id: str, reminder_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un rappel proactif.
        
        Args:
            user_id: ID de l'utilisateur
            reminder_data: Données du rappel
            
        Returns:
            Statut de l'opération
        """
        try:
            trigger_type = reminder_data.get("trigger_type")  # time, context, etc.
            message_template = reminder_data.get("message_template")
            trigger_data = reminder_data.get("trigger_data", {})
            
            if not trigger_type or not message_template:
                return {"success": False, "error": "Type de déclencheur et modèle de message requis"}
            
            trigger_data_json = json.dumps(trigger_data)
            
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO proactive_reminders (user_id, trigger_type, message_template, trigger_data, active)
                VALUES (?, ?, ?, ?, 1)
                """, (user_id, trigger_type, message_template, trigger_data_json))
                
                reminder_id = cursor.lastrowid
                conn.commit()
            
            self.logger.info(f"Nouveau rappel proactif créé pour l'utilisateur {user_id}")
            
            return {
                "success": True,
                "reminder_id": reminder_id,
                "trigger_type": trigger_type
            }
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la création du rappel proactif: {e}")
            return {"success": False, "error": str(e)}
    
    def get_conversation_history(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Récupère l'historique de conversation d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            limit: Nombre maximum de messages à récupérer
            
        Returns:
            Liste des messages de l'historique de conversation
        """
        history = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT direction, message, timestamp, detected_sentiment, context_data
                FROM conversation_history 
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """, (user_id, limit))
                
                for row in cursor.fetchall():
                    entry = dict(row)
                    # Convertir le contexte JSON si présent
                    if entry["context_data"]:
                        try:
                            entry["context_data"] = json.loads(entry["context_data"])
                        except:
                            entry["context_data"] = {}
                    
                    history.append(entry)
                
                # Remettre dans l'ordre chronologique
                history.reverse()
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération de l'historique de conversation: {e}")
        
        return history


if __name__ == "__main__":
    # Configuration des clés API pour le développement/test
    api_keys = {
        "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY"),
        "openai_api_key": os.environ.get("OPENAI_API_KEY")
    }
    
    # Créer l'agent
    discussion_agent = DiscussionAgent(
        redis_host='localhost',
        redis_port=6379,
        db_path='alfred_memory.db',
        api_keys=api_keys,
        encryption_key=os.environ.get("ALFRED_ENCRYPTION_KEY")
    )
    
    # Démarrer l'agent
    discussion_agent.start()
    
    try:
        # En mode test, créer un utilisateur s'il n'existe pas déjà
        test_user_id = "test_user_123"
        existing_user = False
        
        try:
            with discussion_agent._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE id = ?", (test_user_id,))
                if cursor.fetchone():
                    existing_user = True
        except:
            pass
        
        if not existing_user:
            discussion_agent.create_user(
                "John Doe",
                "Monsieur",
                "formal"
            )
            
            # Stocker quelques informations personnelles
            discussion_agent.store_user_info(test_user_id, "preference", "music", "Jazz et classique")
            discussion_agent.store_user_info(test_user_id, "preference", "temperature", "22°C")
            
            # Créer un événement de test
            now = datetime.datetime.now()
            tomorrow = now + datetime.timedelta(days=1)
            event_time = tomorrow.replace(hour=14, minute=30, second=0).isoformat()
            
            discussion_agent.create_event(
                test_user_id,
                {
                    "event_type": "appointment",
                    "title": "Rendez-vous médical",
                    "description": "Consultation chez Dr. Smith",
                    "start_date": event_time,
                    "reminder_time": 60  # 1 heure avant
                }
            )
        
        # Boucle principale pour le test
        print("Agent de discussion démarré. Appuyez sur Ctrl+C pour quitter.")
        print("Vous pouvez interagir avec l'agent en utilisant le canal Redis.")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        discussion_agent.stop()
        print("Agent de discussion arrêté.")
    def _create_event_reminder(self, user_name: str, preferred_title: str,
                              event_title: str, event_type: str, 
                              start_time: datetime.datetime) -> str:
        """
        Crée un message de rappel personnalisé pour un événement.
        
        Args:
            user_name: Nom de l'utilisateur
            preferred_title: Titre préféré de l'utilisateur (M., Mme, etc.)
            event_title: Titre de l'événement
            event_type: Type d'événement (rendez-vous, anniversaire, etc.)
            start_time: Heure de début de l'événement
            
        Returns:
            Message de rappel personnalisé
        """
        # Formatage de l'heure
        time_str = start_time.strftime("%H:%M")
        
        # Différents modèles de messages selon le type d'événement
        if event_type == "appointment":
            templates = [
                f"{preferred_title}, n'oubliez pas votre rendez-vous \"{event_title}\" à {time_str}.",
                f"{preferred_title}, je vous rappelle que vous avez \"{event_title}\" à {time_str}.",
                f"Rappel : votre rendez-vous \"{event_title}\" est prévu à {time_str}. Avez-vous tout ce qu'il vous faut ?"
            ]
        elif event_type == "birthday":
            templates = [
                f"{preferred_title}, c'est l'anniversaire de {event_title} aujourd'hui.",
                f"N'oubliez pas que c'est l'anniversaire de {event_title} aujourd'hui !",
                f"{preferred_title}, puis-je vous rappeler que c'est l'anniversaire de {event_title} aujourd'hui ?"
            ]
        elif event_type == "reminder":
            templates = [
                f"{preferred_title}, vous m'avez demandé de vous rappeler : \"{event_title}\".",
                f"Rappel : {event_title}",
                f"{preferred_title}, voici le rappel que vous avez programmé : \"{event_title}\"."
            ]
        elif event_type == "meeting":
            templates = [
                f"{preferred_title}, vous avez une réunion \"{event_title}\" prévue à {time_str}.",
                f"Votre réunion \"{event_title}\" commence à {time_str}. Souhaitez-vous que je prépare quelque chose ?",
                f"{preferred_title}, n'oubliez pas la réunion \"{event_title}\" à {time_str}."
            ]
        else:
            templates = [
                f"{preferred_title}, vous avez \"{event_title}\" prévu à {time_str}.",
                f"Rappel pour l'événement \"{event_title}\" à {time_str}.",
                f"{preferred_title}, n'oubliez pas \"{event_title}\" à {time_str}."
            ]
        
        # Sélectionner un message aléatoire pour de la variété
        return random.choice(templates)
    
    def _check_contextual_reminders(self) -> None:
        """Vérifie les rappels basés sur le contexte (heure de la journée, etc.)."""
        try:
            now = datetime.datetime.now()
            hour = now.hour
            
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                # Obtenir les rappels contextuels
                cursor.execute('''
                SELECT r.id, r.user_id, r.message_template, r.trigger_data, 
                       u.name, u.preferred_title
                FROM proactive_reminders r
                JOIN users u ON r.user_id = u.id
                WHERE r.trigger_type = 'context' 
                AND r.active = 1
                AND (r.last_triggered IS NULL OR datetime(r.last_triggered) < datetime(?, '-12 hours'))
                ''', (now,))
                
                reminders = cursor.fetchall()
                
                for reminder in reminders:
                    try:
                        trigger_data = json.loads(reminder['trigger_data'])
                        context_type = trigger_data.get('context_type')
                        context_value = trigger_data.get('context_value')
                        
                        # Vérifier si le contexte actuel correspond
                        trigger_now = False
                        
                        if context_type == 'time_of_day':
                            # Matin (5h-12h), Après-midi (12h-18h), Soir (18h-22h), Nuit (22h-5h)
                            if ((context_value == 'morning' and 5 <= hour < 12) or
                                (context_value == 'afternoon' and 12 <= hour < 18) or
                                (context_value == 'evening' and 18 <= hour < 22) or
                                (context_value == 'night' and (hour >= 22 or hour < 5))):
                                trigger_now = True
                        
                        elif context_type == 'day_of_week':
                            current_day = now.strftime("%A").lower()
                            if context_value == current_day:
                                trigger_now = True
                        
                        elif context_type == 'weather':
                            # Géré par l'agent météo via les updates de contexte
                            current_weather = self.conversation_context.get('weather', {}).get('condition')
                            if current_weather and current_weather == context_value:
                                trigger_now = True
                        
                        if trigger_now:
                            user_id = reminder['user_id']
                            message = self._personalize_message(
                                reminder['message_template'],
                                reminder['name'],
                                reminder['preferred_title']
                            )
                            
                            # Ajouter aux interactions proactives en attente
                            self.pending_reminders.append({
                                'user_id': user_id,
                                'message': message,
                                'type': 'context_reminder',
                                'reminder_id': reminder['id'],
                                'priority': trigger_data.get('priority', 3)
                            })
                            
                            # Mettre à jour le timestamp du dernier déclenchement
                            cursor.execute('''
                            UPDATE proactive_reminders
                            SET last_triggered = ?
                            WHERE id = ?
                            ''', (now, reminder['id']))
                            
                            conn.commit()
                    except Exception as e:
                        self.logger.error(f"Erreur lors du traitement du rappel contextuel {reminder['id']}: {e}")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des rappels contextuels: {e}")
    
    def _personalize_message(self, template: str, user_name: str, preferred_title: str) -> str:
        """
        Personnalise un modèle de message pour un utilisateur spécifique.
        
        Args:
            template: Modèle de message avec placeholders
            user_name: Nom de l'utilisateur
            preferred_title: Titre préféré de l'utilisateur
            
        Returns:
            Message personnalisé
        """
        now = datetime.datetime.now()
        hour = now.hour
        
        # Déterminer la salutation appropriée selon l'heure
        if 5 <= hour < 12:
            greeting = "Bonjour"
        elif 12 <= hour < 18:
            greeting = "Bonjour"
        elif 18 <= hour < 22:
            greeting = "Bonsoir"
        else:
            greeting = "Bonsoir"
        
        # Remplacer les placeholders dans le template
        message = template.replace("{name}", user_name)
        message = message.replace("{title}", preferred_title if preferred_title else "")
        message = message.replace("{greeting}", greeting)
        message = message.replace("{time}", now.strftime("%H:%M"))
        message = message.replace("{date}", now.strftime("%d/%m/%Y"))
        
        return message
    
    def _process_pending_proactive_interactions(self) -> None:
        """Traite les interactions proactives en attente."""
        if not self.pending_reminders:
            return
        
        # Trier par priorité (décroissante)
        self.pending_reminders.sort(key=lambda x: x.get('priority', 0), reverse=True)
        
        # Prendre l'interaction la plus prioritaire
        interaction = self.pending_reminders.pop(0)
        user_id = interaction['user_id']
        message = interaction['message']
        
        # Envoyer le message à l'utilisateur via l'orchestrateur
        self.send_redis_message("orchestrator:notifications", 
                              'proactive_message', 
                              {'user_id': user_id, 'message': message})
        
        # Enregistrer dans l'historique de conversation
        self._save_conversation_message(user_id, "alfred_to_user", message)
        
        self.logger.info(f"Message proactif envoyé à l'utilisateur {user_id}: {message}")
    
    def process_user_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> str:
        """
        Traite un message reçu de l'utilisateur et génère une réponse.
        
        Args:
            user_id: ID de l'utilisateur
            message: Message de l'utilisateur
            context: Contexte supplémentaire (facultatif)
            
        Returns:
            Réponse générée pour l'utilisateur
        """
        # Mettre à jour le contexte de conversation
        self.current_user = user_id
        if context:
            self.conversation_context.update(context)
        
        # Enregistrer le message dans l'historique
        self._save_conversation_message(user_id, "user_to_alfred", message)
        
        # Analyser le sentiment et le contexte émotionnel
        emotional_context = self._analyze_emotional_context(message)
        
        # Vérifier s'il s'agit d'une requête spécifique
        specific_intent = self._detect_specific_intent(message)
        if specific_intent:
            response = self._handle_specific_intent(user_id, specific_intent, message)
            if response:
                self._save_conversation_message(user_id, "alfred_to_user", response)
                return response
        
        # Récupérer des informations sur l'utilisateur pour personnaliser la réponse
        user_info = self._get_basic_user_info(user_id)
        
        # Récupérer l'historique de conversation pour le contexte
        conversation_history = self.get_conversation_history(user_id, limit=5)
        
        # Construire le contexte pour la génération de réponse
        generation_context = self._build_generation_context(
            user_info, conversation_history, emotional_context
        )
        
        # Générer une réponse avec NLP avancé
        response = self._generate_response(message, generation_context)
        
        # Enregistrer la réponse dans l'historique
        self._save_conversation_message(user_id, "alfred_to_user", response)
        
        # Mettre à jour la dernière interaction
        self._update_last_interaction(user_id)
        
        # Extraire et stocker de nouvelles informations personnelles si présentes
        self._extract_and_store_personal_info(user_id, message, response)
        
        return response
    
    def _analyze_emotional_context(self, message: str) -> Dict[str, Any]:
        """
        Analyse le contexte émotionnel d'un message utilisateur.
        
        Args:
            message: Message de l'utilisateur
            
        Returns:
            Informations sur le contexte émotionnel détecté
        """
        emotional_context = {"detected": False, "emotion": None, "confidence": 0.0}
        
        # Recherche simple d'émotions basée sur des mots-clés
        message_lower = message.lower()
        
        for emotion, keywords in self.contextual_triggers.items():
            for keyword in keywords:
                if keyword in message_lower:
                    emotional_context["detected"] = True
                    emotional_context["emotion"] = emotion
                    emotional_context["confidence"] = 0.7  # Valeur arbitraire pour une correspondance simple
                    
                    # Mémoriser cette émotion pour l'utilisateur actuel
                    if self.current_user:
                        self.emotional_state[self.current_user] = {
                            "emotion": emotion,
                            "timestamp": time.time(),
                            "source_message": message
                        }
                    
                    return emotional_context
        
        # Analyse plus sophistiquée avec NLP si disponible
        if self.anthropic_client or self.openai_client:
            try:
                if self.anthropic_client:
                    prompt = f"""
                    Analyse l'émotion dominante dans ce message. Réponds uniquement avec un mot parmi : 
                    joie, tristesse, colère, peur, surprise, dégoût, frustration, confusion, fatigue, stress, 
                    satisfaction, neutre.
                    
                    Message : "{message}"
                    
                    Émotion :
                    """
                    
                    response = self.anthropic_client.messages.create(
                        model="claude-3-haiku-20240307",
                        max_tokens=10,
                        temperature=0,
                        system="Tu es un détecteur d'émotions qui répond par un seul mot.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    
                    emotion = response.content[0].text.strip().lower()
                    
                elif self.openai_client:
                    response = self.openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "Tu es un détecteur d'émotions qui répond par un seul mot."},
                            {"role": "user", "content": f"Analyse l'émotion dominante dans ce message et réponds par un seul mot parmi : joie, tristesse, colère, peur, surprise, dégoût, frustration, confusion, fatigue, stress, satisfaction, neutre.\n\nMessage : \"{message}\"\n\nÉmotion :"}
                        ],
                        max_tokens=10,
                        temperature=0
                    )
                    
                    emotion = response.choices[0].message.content.strip().lower()
                
                # Mettre à jour le contexte émotionnel
                if emotion and emotion != "neutre":
                    emotional_context["detected"] = True
                    emotional_context["emotion"] = emotion
                    emotional_context["confidence"] = 0.9
                    
                    # Mémoriser cette émotion pour l'utilisateur actuel
                    if self.current_user:
                        self.emotional_state[self.current_user] = {
                            "emotion": emotion,
                            "timestamp": time.time(),
                            "source_message": message
                        }
            
            except Exception as e:
                self.logger.error(f"Erreur lors de l'analyse émotionnelle avec NLP: {e}")
        
        return emotional_context
    
    def _detect_specific_intent(self, message: str) -> Optional[str]:
        """
        Détecte si un message contient une intention spécifique.
        
        Args:
            message: Message de l'utilisateur
            
        Returns:
            Type d'intention identifiée ou None
        """
        message_lower = message.lower()
        
        # Détecter les intentions liées à la gestion des données personnelles (RGPD)
        if any(kw in message_lower for kw in ["supprimer mes données", "efface mes infos", "rgpd", "oublie-moi"]):
            return "delete_personal_data"
        
        if any(kw in message_lower for kw in ["quelles données", "mes informations", "mes données"]):
            return "show_personal_data"
        
        # Autres intentions spécifiques
        if any(kw in message_lower for kw in ["ajoute un événement", "crée un rendez-vous", "nouvel événement"]):
            return "create_event"
        
        if any(kw in message_lower for kw in ["rappelle-moi", "n'oublie pas de me rappeler", "alarme"]):
            return "create_reminder"
        
        if any(kw in message_lower for kw in ["mes rendez-vous", "mon agenda", "mes événements"]):
            return "list_events"
        
        return None
    
    def _handle_specific_intent(self, user_id: str, intent: str, message: str) -> Optional[str]:
        """
        Traite une intention spécifique identifiée dans un message.
        
        Args:
            user_id: ID de l'utilisateur
            intent: Type d'intention
            message: Message original
            
        Returns:
            Réponse générée ou None si l'intention n'a pas pu être traitée
        """
        try:
            if intent == "delete_personal_data":
                self._delete_user_data(user_id)
                return "J'ai supprimé toutes vos données personnelles conformément à votre demande. Je ne conserve plus aucune information vous concernant, hormis l'historique minimal nécessaire au fonctionnement du système."
            
            elif intent == "show_personal_data":
                user_data = self._get_all_user_data(user_id)
                data_summary = self._format_user_data_summary(user_data)
                return f"Voici les informations que je conserve à votre sujet :\n\n{data_summary}\n\nVous pouvez à tout moment me demander de supprimer ces données."
            
            elif intent == "create_event":
                # Cette intention nécessite un traitement plus complexe avec NLP
                # Nous allons plutôt engager une conversation pour obtenir plus d'informations
                return "Souhaitez-vous créer un nouvel événement ? Pourriez-vous me préciser la date, l'heure et le titre de cet événement ?"
            
            elif intent == "create_reminder":
                # De même, engager une conversation
                return "Je peux vous créer un rappel. De quoi souhaitez-vous que je vous rappelle, et à quel moment ?"
            
            elif intent == "list_events":
                # Récupérer les événements à venir
                upcoming_events = self._get_upcoming_events(user_id)
                if upcoming_events:
                    events_text = self._format_events_list(upcoming_events)
                    return f"Voici vos prochains événements :\n\n{events_text}"
                else:
                    return "Vous n'avez pas d'événements à venir dans votre agenda."
            
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement de l'intention spécifique '{intent}': {e}")
            return None
    
    def _get_all_user_data(self, user_id: str) -> Dict[str, Any]:
        """
        Récupère toutes les données stockées pour un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            Dictionnaire contenant toutes les données de l'utilisateur
        """
        user_data = {"basic_info": {}, "personal_info": {}, "events": [], "preferences": {}}
        
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Informations de base sur l'utilisateur
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                user = cursor.fetchone()
                if user:
                    user_data["basic_info"] = dict(user)
                
                # Informations personnelles
                cursor.execute("SELECT info_type, key, value, is_encrypted FROM personal_info WHERE user_id = ?", (user_id,))
                personal_info = cursor.fetchall()
                for info in personal_info:
                    info_type = info["info_type"]
                    if info_type not in user_data["personal_info"]:
                        user_data["personal_info"][info_type] = {}
                    
                    value = info["value"]
                    if info["is_encrypted"]:
                        try:
                            value = self._decrypt_data(value)
                        except Exception:
                            value = "<données chiffrées>"
                    
                    user_data["personal_info"][info_type][info["key"]] = value
                
                # Événements
                cursor.execute("""
                SELECT event_type, title, description, start_date, end_date 
                FROM events WHERE user_id = ? ORDER BY start_date
                """, (user_id,))
                events = cursor.fetchall()
                user_data["events"] = [dict(event) for event in events]
                
                # Préférences de communication
                cursor.execute("""
                SELECT category, feature, value FROM communication_preferences 
                WHERE user_id = ?
                """, (user_id,))
                preferences = cursor.fetchall()
                for pref in preferences:
                    category = pref["category"]
                    if category not in user_data["preferences"]:
                        user_data["preferences"][category] = {}
                    
                    user_data["preferences"][category][pref["feature"]] = pref["value"]
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des données utilisateur: {e}")
        
        return user_data
    
    def _format_user_data_summary(self, user_data: Dict[str, Any]) -> str:
        """
        Formate un résumé des données utilisateur.
        
        Args:
            user_data: Dictionnaire contenant les données utilisateur
            
        Returns:
            Chaîne formatée avec un résumé des données
        """
        summary = []
        
        # Informations de base
        if user_data["basic_info"]:
            basic_info = user_data["basic_info"]
            summary.append("Informations de base:")
            summary.append(f"- Nom: {basic_info.get('name', 'Non spécifié')}")
            summary.append(f"- Titre préféré: {basic_info.get('preferred_title', 'Non spécifié')}")
            summary.append(f"- Ton préféré: {basic_info.get('preferred_tone', 'Non spécifié')}")
            summary.append("")
        
        # Informations personnelles
        if user_data["personal_info"]:
            summary.append("Informations personnelles:")
            for info_type, items in user_data["personal_info"].items():
                summary.append(f"- {info_type.capitalize()}:")
                for key, value in items.items():
                    summary.append(f"  - {key}: {value}")
            summary.append("")
        
        # Événements
        if user_data["events"]:
            summary.append("Événements enregistrés:")
            for event in user_data["events"][:5]:  # Limiter pour ne pas surcharger
                event_date = datetime.datetime.fromisoformat(event["start_date"]).strftime("%d/%m/%Y %H:%M")
                summary.append(f"- {event['title']} ({event_date})")
            
            if len(user_data["events"]) > 5:
                summary.append(f"... et {len(user_data['events']) - 5} autres événements")
            summary.append("")
        
        # Préférences
        if user_data["preferences"]:
            summary.append("Préférences de communication:")
            for category, features in user_data["preferences"].items():
                for feature, value in features.items():
                    summary.append(f"- {category}.{feature}: {value}")
        
        return "\n".join(summary)
    
    def _delete_user_data(self, user_id: str) -> None:
        """
        Supprime toutes les données personnelles d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Supprimer les informations personnelles
                cursor.execute("DELETE FROM personal_info WHERE user_id = ?", (user_id,))
                
                # Supprimer les événements
                cursor.execute("DELETE FROM events WHERE user_id = ?", (user_id,))
                
                # Supprimer les préférences
                cursor.execute("DELETE FROM communication_preferences WHERE user_id = ?", (user_id,))
                
                # Supprimer les rappels
                cursor.execute("DELETE FROM proactive_reminders WHERE user_id = ?", (user_id,))
                
                # Supprimer les données d'apprentissage
                cursor.execute("DELETE FROM learning_data WHERE user_id = ?", (user_id,))
                
                # Conserver l'historique minimal et l'utilisateur lui-même pour assurer le fonctionnement du système
                conn.commit()
                
                self.logger.info(f"Données personnelles de l'utilisateur {user_id} supprimées")
        except Exception as e:
            self.logger.error(f"Erreur lors de la suppression des données utilisateur: {e}")
    
    def _get_upcoming_events(self, user_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Récupère les événements à venir pour un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            days: Nombre de jours à considérer
            
        Returns:
            Liste des événements à venir
        """
        now = datetime.datetime.now()
        future = now + datetime.timedelta(days=days)
        
        events = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT id, event_type, title, description, start_date, end_date 
                FROM events 
                WHERE user_id = ? AND datetime(start_date) >= datetime(?) AND datetime(start_date) <= datetime(?)
                ORDER BY start_date
                """, (user_id, now, future))
                
                rows = cursor.fetchall()
                for row in rows:
                    events.append(dict(row))
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des événements à venir: {e}")
        
        return events
    
    def _format_events_list(self, events: List[Dict[str, Any]]) -> str:
        """
        Formate une liste d'événements en texte.
        
        Args:
            events: Liste des événements
            
        Returns:
            Texte formaté
        """
        if not events:
            return "Aucun événement prévu."
        
        now = datetime.datetime.now()
        today = now.date()
        
        by_date = {}
        for event in events:
            start_date = datetime.datetime.fromisoformat(event["start_date"])
            date_key = start_date.date()
            
            if date_key not in by_date:
                by_date[date_key] = []
            
            by_date[date_key].append({
                "time": start_date.strftime("%H:%M"),
                "title": event["title"],
                "type": event["event_type"],
                "description": event["description"]
            })
        
        formatted = []
        for date_key in sorted(by_date.keys()):
            if date_key == today:
                date_str = "Aujourd'hui"
            elif date_key == today + datetime.timedelta(days=1):
                date_str = "Demain"
            else:
                date_str = date_key.strftime("%A %d %B").capitalize()
            
            formatted.append(f"● {date_str} :")
            for event in by_date[date_key]:
                type_emoji = "📅"
                if event["type"] == "appointment":
                    type_emoji = "🕒"
                elif event["type"] == "birthday":
                    type_emoji = "🎂"
                elif event["type"] == "meeting":
                    type_emoji = "👥"
                
                formatted.append(f"  {type_emoji} {event['time']} - {event['title']}")
                if event.get("description"):
                    formatted.append(f"     {event['description']}")
            
            formatted.append("")
        
        return "\n".join(formatted)
    
    def _get_basic_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        Récupère les informations de base sur un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            Informations de base sur l'utilisateur
        """
        user_info = {}
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT name, preferred_title, preferred_tone, last_interaction 
                FROM users WHERE id = ?
                """, (user_id,))
                
                user = cursor.fetchone()
                if user:
                    user_info = dict(user)
                    
                    # Récupérer quelques préférences clés
                    cursor.execute("""
                    SELECT category, feature, value FROM communication_preferences 
                    WHERE user_id = ? AND category IN ('communication', 'notifications')
                    """, (user_id,))
                    
                    preferences = cursor.fetchall()
                    if preferences:
                        user_info["preferences"] = {}
                        for pref in preferences:
                            category = pref["category"]
                            if category not in user_info["preferences"]:
                                user_info["preferences"][category] = {}
                            
                            user_info["preferences"][category][pref["feature"]] = pref["value"]
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des informations utilisateur: {e}")
        
        return user_info
    
    def _build_generation_context(self, user_info: Dict[str, Any], 
                                 conversation_history: List[Dict[str, Any]],
                                 emotional_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Construit le contexte pour la génération de réponse.
        
        Args:
            user_info: Informations sur l'utilisateur
            conversation_history: Historique de conversation récent
            emotional_context: Contexte émotionnel"""
Agent Discussion - Agent de conversation proactive et personnalisée pour Alfred
Ce script implémente un agent capable d'interagir naturellement avec les utilisateurs,
de mémoriser leurs informations personnelles et de générer des interactions proactives.
"""

import os
import json
import time
import threading
import logging
import sqlite3
import uuid
import re
import random
import datetime
import base64
from typing import Dict, Any, List, Optional, Tuple, Union
from contextlib import contextmanager
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Importation de l'agent de base
from base_agent import BaseAgent

# Dépendances pour NLP avancé
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("alfred_discussion.log"), logging.StreamHandler()]
)

class DiscussionAgent(BaseAgent):
    """
    Agent de discussion proactive et personnalisée pour Alfred.
    Capable de mémoriser les informations des utilisateurs, d'interagir de manière
    proactive et d'offrir un dialogue empathique.
    """
    
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379,
                 db_path: str = 'alfred_memory.db', api_keys: Dict[str, str] = None,
                 encryption_key: str = None):
        """
        Initialise l'agent de discussion.
        
        Args:
            redis_host: Hôte Redis
            redis_port: Port Redis
            db_path: Chemin vers la base de données SQLite
            api_keys: Clés API pour les services NLP
            encryption_key: Clé pour le chiffrement des données sensibles
        """
        super().__init__("discussion", redis_host, redis_port)
        self.capabilities = [
            "personalized_conversation",
            "proactive_interaction",
            "memory_retention",
            "empathic_dialogue",
            "context_awareness"
        ]
        
        # Configuration des API
        self.api_keys = api_keys or {}
        self.anthropic_client = None
        self.openai_client = None
        self._init_nlp_clients()
        
        # Initialisation de la base de données
        self.db_path = db_path
        self._init_database()
        
        # Configuration de l'encryption
        self.encryption_key = encryption_key
        if not self.encryption_key:
            self.encryption_key = os.environ.get('ALFRED_ENCRYPTION_KEY', self._generate_encryption_key())
        self.cipher_suite = self._setup_encryption()
        
        # État de la conversation et contexte
        self.current_user = None
        self.conversation_context = {}
        self.pending_reminders = []
        self.emotional_state = {}
        self.contextual_triggers = self._load_contextual_triggers()
        
        # Configuration des threads pour les interactions proactives
        self.proactive_thread = None
        self.running = False
        self.last_proactive_check = 0
        self.proactive_check_interval = 60  # Vérifier toutes les 60 secondes
        
        self.logger.info("Agent Discussion initialisé")
    
    def _init_nlp_clients(self) -> None:
        """Initialise les clients pour les services NLP."""
        # Initialiser Anthropic (Claude)
        if ANTHROPIC_AVAILABLE and 'anthropic_api_key' in self.api_keys:
            try:
                self.anthropic_client = anthropic.Anthropic(api_key=self.api_keys['anthropic_api_key'])
                self.logger.info("Client Anthropic initialisé")
            except Exception as e:
                self.logger.error(f"Erreur lors de l'initialisation du client Anthropic: {e}")
        
        # Initialiser OpenAI
        if OPENAI_AVAILABLE and 'openai_api_key' in self.api_keys:
            try:
                openai.api_key = self.api_keys['openai_api_key']
                self.openai_client = openai
                self.logger.info("Client OpenAI initialisé")
            except Exception as e:
                self.logger.error(f"Erreur lors de l'initialisation du client OpenAI: {e}")
    
    def _generate_encryption_key(self) -> str:
        """Génère une clé d'encryption sécurisée."""
        password = os.urandom(16).hex()
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        # Stocker le sel pour une utilisation future (dans un fichier sécurisé par exemple)
        with open(".alfred_salt", "wb") as f:
            f.write(salt)
        return key.decode()
    
    def _setup_encryption(self) -> Fernet:
        """Configure l'encryption Fernet pour les données sensibles."""
        try:
            return Fernet(self.encryption_key.encode())
        except Exception as e:
            self.logger.error(f"Erreur lors de la configuration de l'encryption: {e}")
            # Fallback à une nouvelle clé si nécessaire
            self.encryption_key = self._generate_encryption_key()
            return Fernet(self.encryption_key.encode())
    
    def _encrypt_data(self, data: str) -> str:
        """Chiffre des données sensibles."""
        return self.cipher_suite.encrypt(data.encode()).decode()
    
    def _decrypt_data(self, encrypted_data: str) -> str:
        """Déchiffre des données sensibles."""
        try:
            return self.cipher_suite.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            self.logger.error(f"Erreur lors du déchiffrement: {e}")
            return ""
    
    @contextmanager
    def _get_db_connection(self):
        """Crée et retourne une connexion à la base de données SQLite."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            conn.close()
    
    def _init_database(self) -> None:
        """Initialise la base de données avec les tables nécessaires si elles n'existent pas."""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Table utilisateurs
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_interaction TIMESTAMP,
                    preferred_title TEXT,
                    preferred_tone TEXT,
                    notes TEXT
                )
                ''')
                
                # Table informations personnelles
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS personal_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    info_type TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    is_encrypted INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                ''')
                
                # Table événements (anniversaires, rendez-vous, etc.)
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    start_date TIMESTAMP NOT NULL,
                    end_date TIMESTAMP,
                    recurrence TEXT,
                    reminder_time INTEGER, -- minutes avant l'événement
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                ''')
                
                # Table historique des conversations
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    direction TEXT NOT NULL, -- "user_to_alfred" ou "alfred_to_user"
                    message TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    detected_sentiment TEXT,
                    context_data TEXT, -- JSON avec le contexte
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                ''')
                
                # Table des rappels proactifs
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS proactive_reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    trigger_type TEXT NOT NULL, -- "time", "event", "context", etc.
                    message_template TEXT NOT NULL,
                    trigger_data TEXT, -- JSON avec les détails du déclencheur
                    active INTEGER DEFAULT 1,
                    last_triggered TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                ''')
                
                # Table des préférences de communication
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS communication_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    category TEXT NOT NULL,
                    feature TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                ''')
                
                # Table des données d'apprentissage
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS learning_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    data_type TEXT NOT NULL,
                    data_key TEXT NOT NULL,
                    data_value TEXT,
                    confidence REAL,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                ''')
                
                conn.commit()
                self.logger.info("Base de données initialisée")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation de la base de données: {e}")
    
    def _load_contextual_triggers(self) -> Dict[str, Any]:
        """
        Charge les déclencheurs contextuels pour les interactions proactives.
        (Ex: expressions qui indiquent de la fatigue, du stress, etc.)
        """
        return {
            "fatigue": ["fatigué", "épuisé", "endormi", "besoin de repos", "épuisant"],
            "stress": ["stressé", "anxieux", "inquiet", "tendu", "sous pression"],
            "joie": ["content", "heureux", "ravi", "joyeux", "super", "génial"],
            "frustration": ["frustré", "irrité", "énervé", "agacé", "contrarié"]
        }
    
    def on_start(self) -> None:
        """Actions à effectuer lors du démarrage de l'agent."""
        self.broadcast_message("agent_online", {
            "agent_type": "discussion",
            "capabilities": self.capabilities
        })
        
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities
        })
        
        # Démarrer le thread de vérification proactive
        self.running = True
        self.proactive_thread = threading.Thread(target=self._proactive_loop, daemon=True)
        self.proactive_thread.start()
        
        # Configuration de l'écoute Redis
        self.setup_redis_listener()
        
        self.logger.info("Agent Discussion démarré")
    
    def on_stop(self) -> None:
        """Actions à effectuer lors de l'arrêt de l'agent."""
        self.running = False
        if self.proactive_thread:
            self.proactive_thread.join(timeout=2)
        
        # Arrêter l'écoute Redis
        if hasattr(self, 'redis_pubsub'):
            self.redis_pubsub.unsubscribe()
        
        self.broadcast_message("agent_offline", {
            "agent_type": "discussion",
            "shutdown_time": time.time()
        })
        
        self.logger.info("Agent Discussion arrêté")
    
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
        
        elif msg_type == 'user_message':
            # Message direct de l'utilisateur à traiter
            user_id = data.get('user_id')
            message_text = data.get('message')
            context = data.get('context', {})
            
            if user_id and message_text:
                response = self.process_user_message(user_id, message_text, context)
                self.send_redis_message(f"orchestrator:notifications", 
                                      'response_to_user', 
                                      {'user_id': user_id, 'message': response})
        
        elif msg_type == 'event_notification':
            # Notification d'un événement (ex: rendez-vous à venir, impression terminée)
            event_type = data.get('event_type')
            user_id = data.get('user_id')
            event_data = data.get('data', {})
            
            if event_type and user_id:
                self.handle_event_notification(user_id, event_type, event_data)
        
        elif msg_type == 'user_context_update':
            # Mise à jour du contexte utilisateur (ex: arrivée à la maison, départ du travail)
            user_id = data.get('user_id')
            context_update = data.get('context', {})
            
            if user_id and context_update:
                self.update_user_context(user_id, context_update)
                
        elif msg_type == 'calendar_event':
            # Événement de calendrier à traiter
            user_id = data.get('user_id')
            event_data = data.get('event_data', {})
            
            if user_id and event_data:
                self.handle_calendar_event(user_id, event_data)
        
        elif msg_type == 'status_request':
            reply_to = data.get('reply_to', 'orchestrator')
            self.send_redis_message(f"{reply_to}:notifications", 
                                   'status_response', 
                                   {'status': 'ready', 'capabilities': self.capabilities})
        
        elif msg_type == 'notification':
            # Traiter les notifications génériques
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
    
    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite une commande reçue.
        
        Args:
            command: Commande à traiter avec 'type' et 'data'
            
        Returns:
            Résultat du traitement de la commande
        """
        cmd_type = command.get("type", "unknown")
        data = command.get("data", {})
        self.logger.info(f"Traitement de la commande: {cmd_type}")
        
        if cmd_type in ["get_user_info", "get_user_info_discussion"]:
            user_id = data.get("user_id")
            info_type = data.get("info_type")
            
            if not user_id:
                return {"success": False, "error": "ID utilisateur requis"}
            
            return self.get_user_info(user_id, info_type)
        
        elif cmd_type in ["store_user_info", "store_user_info_discussion"]:
            user_id = data.get("user_id")
            info_type = data.get("info_type")
            key = data.get("key")
            value = data.get("value")
            encrypt = data.get("encrypt", False)
            
            if not all([user_id, info_type, key, value is not None]):
                return {"success": False, "error": "Paramètres incomplets"}
            
            return self.store_user_info(user_id, info_type, key, value, encrypt)
        
        elif cmd_type in ["create_event", "create_event_discussion"]:
            user_id = data.get("user_id")
            event_data = data.get("event_data", {})
            
            if not user_id or not event_data:
                return {"success": False, "error": "Paramètres incomplets"}
            
            return self.create_event(user_id, event_data)
        
        elif cmd_type in ["create_reminder", "create_reminder_discussion"]:
            user_id = data.get("user_id")
            reminder_data = data.get("reminder_data", {})
            
            if not user_id or not reminder_data:
                return {"success": False, "error": "Paramètres incomplets"}
            
            return self.create_proactive_reminder(user_id, reminder_data)
        
        elif cmd_type in ["process_message", "process_message_discussion"]:
            user_id = data.get("user_id")
            message = data.get("message")
            context = data.get("context", {})
            
            if not user_id or not message:
                return {"success": False, "error": "Paramètres incomplets"}
            
            response = self.process_user_message(user_id, message, context)
            return {"success": True, "response": response}
        
        elif cmd_type in ["create_user", "create_user_discussion"]:
            name = data.get("name")
            preferred_title = data.get("preferred_title")
            preferred_tone = data.get("preferred_tone")
            
            if not name:
                return {"success": False, "error": "Nom d'utilisateur requis"}
            
            return self.create_user(name, preferred_title, preferred_tone)
        
        elif cmd_type in ["get_conversation_history", "get_conversation_history_discussion"]:
            user_id = data.get("user_id")
            limit = data.get("limit", 10)
            
            if not user_id:
                return {"success": False, "error": "ID utilisateur requis"}
            
            history = self.get_conversation_history(user_id, limit)
            return {"success": True, "history": history}
        
        elif cmd_type == "status_request":
            return {
                "status": "ready",
                "capabilities": self.capabilities,
                "nlp_services": {
                    "anthropic": self.anthropic_client is not None,
                    "openai": self.openai_client is not None
                }
            }
        
        else:
            self.logger.warning(f"Commande non supportée: {cmd_type}")
            return {"success": False, "message": f"Commande non supportée: {cmd_type}"}
    
    def _proactive_loop(self) -> None:
        """
        Boucle de vérification pour les interactions proactives.
        Vérifie si des rappels, événements ou interactions contextuelles doivent être déclenchés.
        """
        while self.running:
            try:
                current_time = time.time()
                
                # Ne vérifier que toutes les X secondes pour éviter de surcharger le CPU
                if current_time - self.last_proactive_check >= self.proactive_check_interval:
                    self.last_proactive_check = current_time
                    
                    # Vérifier les rappels basés sur le temps
                    self._check_time_based_reminders()
                    
                    # Vérifier les événements à venir
                    self._check_upcoming_events()
                    
                    # Vérifier les rappels contextuels
                    self._check_contextual_reminders()
                    
                    # Traiter les interactions proactives en attente
                    self._process_pending_proactive_interactions()
            
            except Exception as e:
                self.logger.error(f"Erreur dans la boucle proactive: {e}")
            
            time.sleep(1)
    
    def _check_time_based_reminders(self) -> None:
        """Vérifie et déclenche les rappels basés sur le temps."""
        try:
            now = datetime.datetime.now()
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                # Trouver les rappels basés sur le temps qui doivent être déclenchés maintenant
                cursor.execute('''
                SELECT r.id, r.user_id, r.message_template, r.trigger_data, u.name, u.preferred_title
                FROM proactive_reminders r
                JOIN users u ON r.user_id = u.id
                WHERE r.trigger_type = 'time' 
                AND r.active = 1
                AND (r.last_triggered IS NULL OR datetime(r.last_triggered) < datetime(?))
                ''', (now - datetime.timedelta(minutes=5),))
                
                reminders = cursor.fetchall()
                
                for reminder in reminders:
                    try:
                        trigger_data = json.loads(reminder['trigger_data'])
                        trigger_time = trigger_data.get('time')
                        
                        # Vérifier si c'est l'heure de déclencher ce rappel
                        if self._should_trigger_time_reminder(trigger_time):
                            user_id = reminder['user_id']
                            message = self._personalize_message(
                                reminder['message_template'],
                                reminder['name'],
                                reminder['preferred_title']
                            )
                            
                            # Ajouter aux interactions proactives en attente
                            self.pending_reminders.append({
                                'user_id': user_id,
                                'message': message,
                                'type': 'time_reminder',
                                'reminder_id': reminder['id'],
                                'priority': trigger_data.get('priority', 5)
                            })
                            
                            # Mettre à jour le timestamp du dernier déclenchement
                            cursor.execute('''
                            UPDATE proactive_reminders
                            SET last_triggered = ?
                            WHERE id = ?
                            ''', (now, reminder['id']))
                            
                            conn.commit()
                    except Exception as e:
                        self.logger.error(f"Erreur lors du traitement du rappel {reminder['id']}: {e}")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des rappels basés sur le temps: {e}")
    
    def _should_trigger_time_reminder(self, trigger_time: str) -> bool:
        """
        Détermine si un rappel basé sur le temps doit être déclenché.
        
        Args:
            trigger_time: Heure de déclenchement au format "HH:MM" ou "HH:MM|Mon,Tue,Wed,Thu,Fri,Sat,Sun"
            
        Returns:
            True si le rappel doit être déclenché, False sinon
        """
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.strftime("%a")
        
        # Format simple "HH:MM"
        if "|" not in trigger_time:
            return current_time == trigger_time
        
        # Format avec jours spécifiés "HH:MM|Mon,Tue,..."
        time_part, days_part = trigger_time.split("|")
        allowed_days = [day.strip() for day in days_part.split(",")]
        
        return current_time == time_part and current_day in allowed_days
    
    def _check_upcoming_events(self) -> None:
        """Vérifie et notifie des événements à venir."""
        try:
            now = datetime.datetime.now()
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                # Trouver les événements qui vont se produire dans la fenêtre de rappel
                cursor.execute('''
                SELECT e.id, e.user_id, e.event_type, e.title, e.description, e.start_date, 
                       e.reminder_time, u.name, u.preferred_title
                FROM events e
                JOIN users u ON e.user_id = u.id
                WHERE datetime(e.start_date) > datetime(?)
                AND datetime(e.start_date) <= datetime(?, '+1 day')
                ''', (now, now))
                
                events = cursor.fetchall()
                
                for event in events:
                    start_time = datetime.datetime.fromisoformat(event['start_date'])
                    reminder_minutes = event['reminder_time'] or 30  # Défaut à 30 minutes
                    
                    # Si l'événement est dans la fenêtre de rappel
                    time_until_event = (start_time - now).total_seconds() / 60
                    if 0 <= time_until_event <= reminder_minutes:
                        # Vérifier si on a déjà envoyé un rappel récemment
                        cursor.execute('''
                        SELECT id FROM conversation_history 
                        WHERE user_id = ? 
                        AND direction = 'alfred_to_user'
                        AND message LIKE ? 
                        AND timestamp > datetime(?, '-60 minutes')
                        ''', (
                            event['user_id'], 
                            f"%{event['title']}%",
                            now
                        ))
                        
                        if not cursor.fetchone():  # Aucun rappel récent
                            # Créer un message de rappel personnalisé
                            message = self._create_event_reminder(
                                event['name'],
                                event['preferred_title'],
                                event['title'],
                                event['event_type'],
                                start_time
                            )
                            
                            # Ajouter aux interactions proactives en attente
                            self.pending_reminders.append({
                                'user_id': event['user_id'],
                                'message': message,
                                'type': 'event_reminder',
                                'event_id': event['id'],
                                'priority': 8  # Priorité élevée pour les rappels d'événements
                            })
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des événements à venir: {e}")
    
    def _create_event_reminder(self, user_name: str, preferred_title: str,
                              event_title: str, event_type: str, 
                              start_time: datetime.datetime) -> str:
        """
        Crée un message de rappel personnalisé pour un événement.
        
        Args:
            user_name: Nom de