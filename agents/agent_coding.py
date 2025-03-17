    
    def _process_pending_notifications(self) -> None:
        """Traite les notifications en attente pour les envoyer aux utilisateurs."""
        if not self.pending_notifications:
            return
        
        try:
            # Grouper les notifications par utilisateur
            notifications_by_user = {}
            for notification in self.pending_notifications:
                user_id = notification['user_id']
                if user_id not in notifications_by_user:
                    notifications_by_user[user_id] = []
                notifications_by_user[user_id].append(notification)
            
            # Envoyer les notifications à chaque utilisateur
            for user_id, notifications in notifications_by_user.items():
                # Limiter à 3 notifications à la fois pour ne pas surcharger
                for notification in notifications[:3]:
                    news_id = notification['news_id']
                    title = notification['title']
                    
                    # Récupérer les détails complets de l'actualité
                    news_details = self.get_news_details(news_id)
                    
                    # Créer un message personnalisé
                    message = self._create_news_notification(user_id, title, news_details)
                    
                    # Envoyer la notification via Redis
                    self.send_redis_message("orchestrator:notifications", 
                                          'tech_news_notification', 
                                          {'user_id': user_id, 'message': message, 'news_id': news_id})
                    
                    # Marquer comme envoyé
                    with self._get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                        UPDATE tech_news
                        SET notification_sent = 1
                        WHERE id = ?
                        ''', (news_id,))
                        
                        cursor.execute('''
                        INSERT INTO news_notifications (user_id, news_id)
                        VALUES (?, ?)
                        ''', (user_id, news_id))
                        
                        conn.commit()
            
            # Vider la liste des notifications en attente
            self.pending_notifications = []
        
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement des notifications: {e}")
    
    def _create_news_notification(self, user_id: str, title: str, news_details: Dict[str, Any]) -> str:
        """
        Crée un message de notification personnalisé pour une actualité.
        
        Args:
            user_id: ID de l'utilisateur
            title: Titre de l'actualité
            news_details: Détails complets de l'actualité
            
        Returns:
            Message formaté
        """
        try:
            # Récupérer le nom de l'utilisateur
            user_name = "Flo"  # Valeur par défaut
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT name FROM users WHERE id = ?', (user_id,))
                user = cursor.fetchone()
                if user:
                    user_name = user['name']
            
            # Déterminer le type de contenu
            source_category = news_details.get('category', 'general')
            content_type = "actualité"
            if "framework" in source_category:
                content_type = "framework"
            elif "language" in source_category:
                content_type = "langage"
            elif "library" in source_category:
                content_type = "librairie"
            elif "tool" in source_category:
                content_type = "outil"
            
            # Extraire les mots-clés importants
            tags = news_details.get('tags', [])
            tag_str = ", ".join(tags[:3]) if tags else ""
            
            # Construire le message
            source_name = news_details.get('source_name', 'une source tech')
            url = news_details.get('url', '')
            
            templates = [
                f"{user_name}, j'ai trouvé une {content_type} intéressante : \"{title}\". Souhaites-tu en savoir plus ?",
                f"Nouvelle {content_type} tech détectée : \"{title}\". Cela pourrait t'intéresser, {user_name}.",
                f"{user_name}, selon {source_name}, il y a du nouveau concernant {tag_str} : \"{title}\"."
            ]
            
            message = random.choice(templates)
            
            # Ajouter l'URL si disponible
            if url:
                message += f"\nLien : {url}"
            
            return message
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la création du message de notification: {e}")
            return f"Nouvelle actualité tech : {title}"
    
    def get_news_details(self, news_id: int) -> Dict[str, Any]:
        """
        Récupère les détails complets d'une actualité.
        
        Args:
            news_id: ID de l'actualité
            
        Returns:
            Détails de l'actualité
        """
        news_details = {}
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT n.*, s.name as source_name, s.category, s.tags
                FROM tech_news n
                JOIN tech_sources s ON n.source_id = s.id
                WHERE n.id = ?
                ''', (news_id,))
                
                news = cursor.fetchone()
                if news:
                    news_details = dict(news)
                    # Convertir les tags en liste si présent
                    if news_details.get('tags'):
                        news_details['tags'] = json.loads(news_details['tags'])
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des détails de l'actualité {news_id}: {e}")
        
        return news_details
    
    def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite une commande reçue.
        
        Args:
            command: Commande à traiter
            
        Returns:
            Résultat du traitement
        """
        cmd_type = command.get("type", "unknown")
        data = command.get("data", {})
        
        self.logger.info(f"Traitement de la commande: {cmd_type}")
        
        if cmd_type in ["search_tech_news", "search_tech_news_coding"]:
            query = data.get("query")
            limit = data.get("limit", 10)
            
            if not query:
                return {"success": False, "error": "Requête de recherche non spécifiée"}
            
            results = self.search_tech_news(query, limit)
            return {"success": True, "results": results}
        
        elif cmd_type in ["add_user_preference", "add_user_preference_coding"]:
            user_id = data.get("user_id")
            category = data.get("category")
            item = data.get("item")
            value = data.get("value", 1.0)
            
            if not all([user_id, category, item]):
                return {"success": False, "error": "Paramètres incomplets"}
            
            return self.add_user_preference(user_id, category, item, value)
        
        elif cmd_type in ["add_project", "add_project_coding"]:
            user_id = data.get("user_id")
            project_data = data.get("project_data", {})
            
            if not user_id or not project_data:
                return {"success": False, "error": "Paramètres incomplets"}
            
            return self.add_project(user_id, project_data)
        
        elif cmd_type in ["get_package_updates", "get_package_updates_coding"]:
            project_id = data.get("project_id")
            
            if not project_id:
                return {"success": False, "error": "ID de projet non spécifié"}
            
            updates = self.check_package_updates(project_id)
            return {"success": True, "updates": updates}
        
        elif cmd_type in ["add_tech_source", "add_tech_source_coding"]:
            source_data = data.get("source_data", {})
            
            if not source_data:
                return {"success": False, "error": "Données de source non spécifiées"}
            
            return self.add_tech_source(source_data)
        
        elif cmd_type in ["create_user", "create_user_coding"]:
            name = data.get("name")
            
            if not name:
                return {"success": False, "error": "Nom d'utilisateur non spécifié"}
            
            return self.create_user(name)
        
        elif cmd_type == "status_request":
            # Récupérer quelques statistiques
            stats = self.get_agent_stats()
            
            return {
                "status": "ready",
                "capabilities": self.capabilities,
                "stats": stats
            }
        
        else:
            self.logger.warning(f"Commande non supportée: {cmd_type}")
            return {"success": False, "message": f"Commande non supportée: {cmd_type}"}
    
    def search_tech_news(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Recherche des actualités technologiques correspondant à une requête.
        
        Args:
            query: Termes de recherche
            limit: Nombre maximal de résultats
            
        Returns:
            Liste des actualités correspondantes
        """
        results = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Recherche dans le titre et le contenu
                cursor.execute('''
                SELECT n.id, n.title, n.content, n.url, n.published_at, s.name as source_name, s.category
                FROM tech_news n
                JOIN tech_sources s ON n.source_id = s.id
                WHERE n.title LIKE ? OR n.content LIKE ?
                ORDER BY n.published_at DESC
                LIMIT ?
                ''', (f'%{query}%', f'%{query}%', limit))
                
                news_items = cursor.fetchall()
                
                for item in news_items:
                    results.append({
                        "id": item['id'],
                        "title": item['title'],
                        "url": item['url'],
                        "source": item['source_name'],
                        "category": item['category'],
                        "published_at": item['published_at']
                    })
            
            # Enregistrer la recherche dans l'historique
            self.log_search_query(query)
            
            self.logger.info(f"Recherche d'actualités pour '{query}' : {len(results)} résultats")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche d'actualités: {e}")
        
        return results
    
    def log_search_query(self, query: str, user_id: str = None) -> None:
        """
        Enregistre une requête de recherche dans l'historique.
        
        Args:
            query: Termes de recherche
            user_id: ID de l'utilisateur (facultatif)
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO search_history (user_id, query)
                VALUES (?, ?)
                ''', (user_id, query))
                
                conn.commit()
        except Exception as e:
            self.logger.error(f"Erreur lors de l'enregistrement de la requête: {e}")
    
    def add_user_preference(self, user_id: str, category: str, 
                          item: str, value: float = 1.0) -> Dict[str, Any]:
        """
        Ajoute ou met à jour une préférence utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            category: Catégorie de préférence (language, framework, tool, etc.)
            item: Élément spécifique (python, react, vscode, etc.)
            value: Score de préférence (0 à 1)
            
        Returns:
            Statut de l'opération
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Vérifier si l'utilisateur existe
                cursor.execute('SELECT id FROM users WHERE id = ?', (user_id,))
                user = cursor.fetchone()
                
                if not user:
                    return {"success": False, "error": f"Utilisateur {user_id} non trouvé"}
                
                # Normaliser la valeur
                value = max(0.0, min(1.0, value))
                
                # Vérifier si la préférence existe déjà
                cursor.execute('''
                SELECT id FROM dev_preferences
                WHERE user_id = ? AND category = ? AND item = ?
                ''', (user_id, category, item))
                
                preference = cursor.fetchone()
                
                if preference:
                    # Mettre à jour la préférence existante
                    cursor.execute('''
                    UPDATE dev_preferences
                    SET value = ?, updated_at = ?
                    WHERE user_id = ? AND category = ? AND item = ?
                    ''', (value, datetime.datetime.now(), user_id, category, item))
                else:
                    # Créer une nouvelle préférence
                    cursor.execute('''
                    INSERT INTO dev_preferences (user_id, category, item, value)
                    VALUES (?, ?, ?, ?)
                    ''', (user_id, category, item, value))
                
                conn.commit()
                
                self.logger.info(f"Préférence {category}.{item} définie pour l'utilisateur {user_id}")
                
                return {"success": True, "user_id": user_id, "category": category, "item": item, "value": value}
        
        except Exception as e:
            self.logger.error(f"Erreur lors de l'ajout de la préférence: {e}")
            return {"success": False, "error": str(e)}
    
    def add_project(self, user_id: str, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ajoute ou met à jour un projet.
        
        Args:
            user_id: ID de l'utilisateur
            project_data: Données du projet
            
        Returns:
            Statut de l'opération
        """
        try:
            name = project_data.get("name")
            path = project_data.get("path")
            git_repo = project_data.get("git_repo")
            description = project_data.get("description", "")
            tech_stack = project_data.get("tech_stack", {})
            
            if not name:
                return {"success": False, "error": "Nom du projet requis"}
            
            # Convertir tech_stack en JSON si nécessaire
            if isinstance(tech_stack, dict):
                tech_stack = json.dumps(tech_stack)
            
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Vérifier si le projet existe déjà
                cursor.execute('''
                SELECT id FROM projects
                WHERE user_id = ? AND name = ?
                ''', (user_id, name))
                
                project = cursor.fetchone()
                
                if project:
                    # Mettre à jour le projet existant
                    project_id = project['id']
                    cursor.execute('''
                    UPDATE projects
                    SET path = ?, git_repo = ?, description = ?, tech_stack = ?, updated_at = ?
                    WHERE id = ?
                    ''', (path, git_repo, description, tech_stack, datetime.datetime.now(), project_id))
                else:
                    # Créer un nouveau projet
                    cursor.execute('''
                    INSERT INTO projects (user_id, name, path, git_repo, description, tech_stack)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''', (user_id, name, path, git_repo, description, tech_stack))
                    
                    project_id = cursor.lastrowid
                
                conn.commit()
                
                # Traiter les packages si fournis
                packages = project_data.get("packages", [])
                if packages and project_id:
                    self._add_project_packages(project_id, packages)
                
                self.logger.info(f"Projet {name} ajouté/mis à jour pour l'utilisateur {user_id}")
                
                return {
                    "success": True,
                    "project_id": project_id,
                    "name": name,
                    "message": "Projet ajouté avec succès"
                }
        
        except Exception as e:
            self.logger.error(f"Erreur lors de l'ajout du projet: {e}")
            return {"success": False, "error": str(e)}
    
    def _add_project_packages(self, project_id: int, packages: List[Dict[str, Any]]) -> None:
        """
        Ajoute ou met à jour les packages d'un projet.
        
        Args:
            project_id: ID du projet
            packages: Liste des packages avec leur version
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                for package in packages:
                    name = package.get("name")
                    version = package.get("version")
                    ecosystem = package.get("ecosystem", "unknown")
                    
                    if name and version:
                        # Vérifier si le package existe déjà
                        cursor.execute('''
                        SELECT id FROM packages
                        WHERE project_id = ? AND name = ?
                        ''', (project_id, name))
                        
                        pkg = cursor.fetchone()
                        
                        if pkg:
                            # Mettre à jour le package existant
                            cursor.execute('''
                            UPDATE packages
                            SET current_version = ?, ecosystem = ?
                            WHERE id = ?
                            ''', (version, ecosystem, pkg['id']))
                        else:
                            # Ajouter un nouveau package
                            cursor.execute('''
                            INSERT INTO packages (project_id, name, current_version, ecosystem)
                            VALUES (?, ?, ?, ?)
                            ''', (project_id, name, version, ecosystem))
                
                conn.commit()
                
                self.logger.info(f"Ajout/mise à jour de {len(packages)} packages pour le projet {project_id}")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de l'ajout des packages: {e}")
    
    def check_package_updates(self, project_id: int) -> List[Dict[str, Any]]:
        """
        Vérifie les mises à jour disponibles pour les packages d'un projet.
        
        Args:
            project_id: ID du projet
            
        Returns:
            Liste des packages avec mises à jour disponibles
        """
        updates = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT id, name, current_version, ecosystem
                FROM packages
                WHERE project_id = ?
                ''', (project_id,))
                
                packages = cursor.fetchall()
                
                for package in packages:
                    pkg_id = package['id']
                    pkg_name = package['name']
                    current_version = package['current_version']
                    ecosystem = package['ecosystem']
                    
                    # Vérifier les mises à jour selon l'écosystème
                    latest_version = self._check_latest_version(pkg_name, ecosystem)
                    
                    if latest_version and latest_version != current_version:
                        # Mise à jour le package avec la dernière version
                        cursor.execute('''
                        UPDATE packages
                        SET latest_version = ?, last_checked = ?
                        WHERE id = ?
                        ''', (latest_version, datetime.datetime.now(), pkg_id))
                        
                        updates.append({
                            "name": pkg_name,
                            "current_version": current_version,
                            "latest_version": latest_version,
                            "ecosystem": ecosystem
                        })
                
                conn.commit()
                
                self.logger.info(f"Vérification des mises à jour terminée pour le projet {project_id}: {len(updates)} mises à jour trouvées")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des mises à jour: {e}")
        
        return updates
    
    def _check_latest_version(self, package_name: str, ecosystem: str) -> Optional[str]:
        """
        Vérifie la dernière version disponible d'un package.
        
        Args:
            package_name: Nom du package
            ecosystem: Écosystème du package (npm, pypi, etc.)
            
        Returns:
            Dernière version disponible ou None en cas d'erreur
        """
        try:
            if ecosystem == "npm":
                # Vérifier la dernière version sur npm
                url = f"https://registry.npmjs.org/{package_name}"
                response = requests.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("dist-tags", {}).get("latest")
            
            elif ecosystem == "pypi":
                # Vérifier la dernière version sur PyPI
                url = f"https://pypi.org/pypi/{package_name}/json"
                response = requests.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("info", {}).get("version")
            
            # Ajouter d'autres écosystèmes au besoin
            
            return None
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification de la version de {package_name}: {e}")
            return None
    
    def add_tech_source(self, source_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ajoute une nouvelle source de veille technologique.
        
        Args:
            source_data: Données de la source
            
        Returns:
            Statut de l'opération
        """
        try:
            source_type = source_data.get("source_type")
            name = source_data.get("name")
            url = source_data.get("url")
            category = source_data.get("category", "general")
            tags = source_data.get("tags", [])
            
            if not all([source_type, name, url]):
                return {"success": False, "error": "Type, nom et URL requis"}
            
            # Convertir tags en JSON si nécessaire
            if isinstance(tags, list):
                tags = json.dumps(tags)
            
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO tech_sources (source_type, name, url, category, tags)
                VALUES (?, ?, ?, ?, ?)
                ''', (source_type, name, url, category, tags))
                
                source_id = cursor.lastrowid
                conn.commit()
                
                # Recharger les sources
                self.tech_sources = self._load_tech_sources()
                
                self.logger.info(f"Nouvelle source de veille ajoutée: {name}")
                
                return {"success": True, "source_id": source_id, "name": name}
        
        except Exception as e:
            self.logger.error(f"Erreur lors de l'ajout de la source: {e}")
            return {"success": False, "error": str(e)}
    
    def create_user(self, name: str) -> Dict[str, Any]:
        """
        Crée un nouvel utilisateur.
        
        Args:
            name: Nom de l'utilisateur
            
        Returns:
            Informations sur l'utilisateur créé
        """
        try:
            user_id = str(uuid.uuid4())
            
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO users (id, name)
                VALUES (?, ?)
                ''', (user_id, name))
                
                conn.commit()
                
                self.logger.info(f"Nouvel utilisateur créé: {name} (ID: {user_id})")
                
                return {"success": True, "user_id": user_id, "name": name}
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la création de l'utilisateur: {e}")
            return {"success": False, "error": str(e)}
    
    def get_agent_stats(self) -> Dict[str, Any]:
        """
        Récupère des statistiques sur l'agent.
        
        Returns:
            Statistiques diverses
        """
        stats = {
            "tech_sources_count": 0,
            "tech_news_count": 0,
            "projects_count": 0,
            "users_count": 0,
            "last_tech_watch": datetime.datetime.fromtimestamp(self.last_tech_watch_check).isoformat() if self.last_tech_watch_check else None
        }
        
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Compter les sources
                cursor.execute('SELECT COUNT(*) as count FROM tech_sources')
                result = cursor.fetchone()
                stats["tech_sources_count"] = result['count'] if result else 0
                
                # Compter les actualités
                cursor.execute('SELECT COUNT(*) as count FROM tech_news')
                result = cursor.fetchone()
                stats["tech_news_count"] = result['count'] if result else 0
                
                # Compter les projets
                cursor.execute('SELECT COUNT(*) as count FROM projects')
                result = cursor.fetchone()
                stats["projects_count"] = result['count'] if result else 0
                
                # Compter les utilisateurs
                cursor.execute('SELECT COUNT(*) as count FROM users')
                result = cursor.fetchone()
                stats["users_count"] = result['count'] if result else 0
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des statistiques: {e}")
        
        return stats
    
    def process_user_query(self, user_id: str, query: str, context: Dict[str, Any] = None) -> str:
        """
        Traite une requête utilisateur et génère une réponse.
        
        Args:
            user_id: ID de l'utilisateur
            query: Requête de l'utilisateur
            context: Contexte supplémentaire
            
        Returns:
            Réponse à l'utilisateur
        """
        # Enregistrer la requête
        self.log_search_query(query, user_id)
        
        # Analyser la requête pour déterminer l'intention
        query_lower = query.lower()
        
        # Recherche de nouvelles techs
        if re.search(r"(nouvelles?|actualités?|quoi de neuf|nouveautés?)", query_lower):
            # Extraire les mots-clés pertinents
            keywords = self._extract_tech_keywords(query_lower)
            
            if keywords:
                # Rechercher des actualités pour ces mots-clés
                results = self.search_tech_news(" ".join(keywords), limit=3)
                
                if results:
                    # Formater les résultats
                    response = f"Voici les dernières actualités sur {', '.join(keywords)} :\n\n"
                    
                    for i, result in enumerate(results, 1):
                        date_str = self._format_date(result.get('published_at', ''))
                        response += f"{i}. {result['title']}\n"
                        response += f"   Source: {result.get('source', 'Non spécifiée')} ({date_str})\n"
                        if result.get('url'):
                            response += f"   Lien: {result['url']}\n"
                        response += "\n"
                    
                    return response
                else:
                    return f"Je n'ai pas trouvé d'actualités récentes sur {', '.join(keywords)}. Souhaites-tu que je cherche autre chose ?"
            else:
                # Récupérer les actualités générales récentes
                results = self._get_recent_news(limit=3)
                
                if results:
                    response = "Voici les dernières actualités tech :\n\n"
                    
                    for i, result in enumerate(results, 1):
                        date_str = self._format_date(result.get('published_at', ''))
                        response += f"{i}. {result['title']}\n"
                        response += f"   Source: {result.get('source', 'Non spécifiée')} ({date_str})\n"
                        if result.get('url'):
                            response += f"   Lien: {result['url']}\n"
                        response += "\n"
                    
                    return response
                else:
                    return "Je n'ai pas trouvé d'actualités récentes. La veille technologique sera mise à jour prochainement."
        
        # Vérification des mises à jour de packages
        elif re.search(r"(mises? à jour|updates?|packages?|dépendances)", query_lower):
            # Récupérer les projets de l'utilisateur
            projects = self._get_user_projects(user_id)
            
            if projects:
                # Rechercher des mises à jour pour le premier projet
                project_id = projects[0]['id']
                updates = self.check_package_updates(project_id)
                
                if updates:
                    response = f"J'ai trouvé {len(updates)} mise(s) à jour pour le projet '{projects[0]['name']}' :\n\n"
                    
                    for update in updates:
                        response += f"• {update['name']}: {update['current_version']} → {update['latest_version']}\n"
                    
                    response += "\nSouhaites-tu que je mette à jour ces packages ?"
                    return response
                else:
                    return f"Tous les packages du projet '{projects[0]['name']}' sont à jour."
            else:
                return "Je n'ai pas trouvé de projets enregistrés. Souhaites-tu en ajouter un ?"
        
        # Demande d'informations sur les préférences
        elif re.search(r"(préférences|favoris|langages? préférés|frameworks? préférés)", query_lower):
            # Récupérer les préférences de l'utilisateur
            preferences = self._get_user_preferences(user_id)
            
            if preferences:
                response = "Voici tes préférences de développement :\n\n"
                
                # Grouper par catégorie
                by_category = {}
                for pref in preferences:
                    category = pref['category']
                    if category not in by_category:
                        by_category[category] = []
                    by_category[category].append(pref)
                
                for category, prefs in by_category.items():
                    response += f"• {category.capitalize()} :\n"
                    # Trier par valeur décroissante
                    prefs.sort(key=lambda x: x['value'], reverse=True)
                    
                    for pref in prefs:
                        # Convertir la valeur en pourcentage
                        value_percent = int(pref['value'] * 100)
                        response += f"  - {pref['item']}: {value_percent}%\n"
                    
                    response += "\n"
                
                return response
            else:
                return "Je n'ai pas encore enregistré tes préférences de développement. Tu peux me dire quels sont tes langages, frameworks et outils préférés."
        
        # Répondre aux autres types de requêtes
        else:
            # Recherche générale dans les actualités
            results = self.search_tech_news(query, limit=5)
            
            if results:
                response = f"Voici quelques résultats pour '{query}' :\n\n"
                
                for i, result in enumerate(results, 1):
                    date_str = self._format_date(result.get('published_at', ''))
                    response += f"{i}. {result['title']}\n"
                    response += f"   Source: {result.get('source', 'Non spécifiée')} ({date_str})\n"
                    if result.get('url'):
                        response += f"   Lien: {result['url']}\n"
                    response += "\n"
                
                return response
            else:
                return f"Je n'ai pas trouvé d'informations sur '{query}'. Est-ce que tu peux préciser ta demande ?"
    
    def _extract_tech_keywords(self, query: str) -> List[str]:
        """
        Extrait les mots-clés technologiques d'une requête.
        
        Args:
            query: Requête à analyser
            
        Returns:
            Liste des mots-clés extraits
        """
        # Liste de mots-clés technologiques courants à rechercher
        common_tech_keywords = [
            "python", "javascript", "typescript", "java", "c#", "php", "ruby", "go", "rust", "swift",
            "react", "angular", "vue", "svelte", "nextjs", "gatsby", "nuxt",
            "node", "django", "flask", "spring", "laravel", "rails",
            "docker", "kubernetes", "aws", "azure", "gcp", "devops", "git",
            "webpack", "vite", "npm", "yarn", "pnpm", "pip", "composer",
            "ai", "machine learning", "deep learning", "data science", "big data",
            "blockchain", "nft", "web3", "frontend", "backend", "fullstack"
        ]
        
        keywords = []
        query_words = query.lower().split()
        
        # Vérifier les mots-clés simples
        for keyword in common_tech_keywords:
            if keyword in query.lower():
                keywords.append(keyword)
        
        # Rechercher d'autres termes pertinents
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT DISTINCT item FROM dev_preferences
            WHERE category IN ('language', 'framework', 'library', 'tool')
            ''')
            
            db_keywords = [row['item'] for row in cursor.fetchall()]
            
            for keyword in db_keywords:
                if keyword.lower() in query.lower() and keyword not in keywords:
                    keywords.append(keyword)
        
        return keywords
    
    def _get_recent_news(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Récupère les actualités récentes.
        
        Args:
            limit: Nombre de résultats à retourner
            
        Returns:
            Liste des actualités récentes
        """
        results = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT n.id, n.title, n.url, n.published_at, s.name as source_name, s.category
                FROM tech_news n
                JOIN tech_sources s ON n.source_id = s.id
                ORDER BY n.published_at DESC
                LIMIT ?
                ''', (limit,))
                
                news_items = cursor.fetchall()
                
                for item in news_items:
                    results.append({
                        "id": item['id'],
                        "title": item['title'],
                        "url": item['url'],
                        "source": item['source_name'],
                        "category": item['category'],
                        "published_at": item['published_at']
                    })
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des actualités récentes: {e}")
        
        return results
    
    def _get_user_projects(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les projets d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            Liste des projets
        """
        projects = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT id, name, path, git_repo, tech_stack, description
                FROM projects
                WHERE user_id = ?
                ORDER BY updated_at DESC
                ''', (user_id,))
                
                rows = cursor.fetchall()
                
                for row in rows:
                    project = dict(row)
                    
                    # Convertir tech_stack en dictionnaire si c'est un JSON
                    if project.get('tech_stack'):
                        try:
                            project['tech_stack'] = json.loads(project['tech_stack'])
                        except:
                            pass
                    
                    projects.append(project)
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des projets: {e}")
        
        return projects
    
    def _get_user_preferences(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les préférences d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            Liste des préférences
        """
        preferences = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT category, item, value, note
                FROM dev_preferences
                WHERE user_id = ?
                ORDER BY category, value DESC
                ''', (user_id,))
                
                rows = cursor.fetchall()
                
                for row in rows:
                    preferences.append(dict(row))
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des préférences: {e}")
        
        return preferences
    
    def _format_date(self, date_str: str) -> str:
        """
        Formate une date ISO en format lisible.
        
        Args:
            date_str: Date au format ISO
            
        Returns:
            Date formatée
        """
        try:
            if not date_str:
                return "Date inconnue"
            
            date = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            now = datetime.datetime.now()
            diff = now - date
            
            if diff.days == 0:
                if diff.seconds < 3600:
                    minutes = diff.seconds // 60
                    return f"il y a {minutes} minute{'s' if minutes > 1 else ''}"
                else:
                    hours = diff.seconds // 3600
                    return f"il y a {hours} heure{'s' if hours > 1 else ''}"
            elif diff.days == 1:
                return "hier"
            elif diff.days < 7:
                return f"il y a {diff.days} jour{'s' if diff.days > 1 else ''}"
            else:
                return date.strftime("%d/%m/%Y")
        
        except Exception:
            return "Date inconnue"
    
    def update_project_info(self, user_id: str, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Met à jour les informations d'un projet.
        
        Args:
            user_id: ID de l'utilisateur
            project_data: Données du projet
            
        Returns:
            Statut de l'opération
        """
        # Cette méthode est similaire à add_project, mais elle est dédiée aux 
        # mises à jour automatiques via des notifications (ex: hooks git)
        return self.add_project(user_id, project_data)
    
    def learn_from_user_code(self, user_id: str, code_content: str, 
                           language: str = None) -> Dict[str, Any]:
        """
        Apprend les préférences de l'utilisateur à partir de son code.
        
        Args:
            user_id: ID de l'utilisateur
            code_content: Contenu du code
            language: Langage du code (facultatif)
            
        Returns:
            Résultats de l'apprentissage
        """
        results = {"learned": False, "preferences": []}
        
        # Si le langage n'est pas spécifié, essayer de le détecter
        if not language:
            language = self._detect_language(code_content)
        
        if not language:
            return results
        
        try:
            # Ajouter le langage comme préférence
            self.add_user_preference(user_id, "language", language, 0.8)
            results["preferences"].append({"category": "language", "item": language, "value": 0.8})
            
            # Analyser le code selon le langage
            if language.lower() == "javascript" or language.lower() == "typescript":
                # Détecter les frameworks/librairies JS
                frameworks = self._detect_js_frameworks(code_content)
                
                for framework, confidence in frameworks.items():
                    self.add_user_preference(user_id, "framework", framework, confidence)
                    results["preferences"].append({"category": "framework", "item": framework, "value": confidence})
            
            elif language.lower() == "python":
                # Détecter les frameworks/librairies Python
                frameworks = self._detect_python_frameworks(code_content)
                
                for framework, confidence in frameworks.items():
                    self.add_user_preference(user_id, "framework", framework, confidence)
                    results["preferences"].append({"category": "framework", "item": framework, "value": confidence})
            
            # Ajouter d'autres langages au besoin
            
            results["learned"] = len(results["preferences"]) > 0
            
            self.logger.info(f"Apprentissage à partir du code pour l'utilisateur {user_id} terminé")
            
            return results
        
        except Exception as e:
            self.logger.error(f"Erreur lors de l'apprentissage à partir du code: {e}")
            return results
    
    def _detect_language(self, code_content: str) -> Optional[str]:
        """
        Détecte le langage d'un code source.
        
        Args:
            code_content: Contenu du code
            
        Returns:
            Langage détecté ou None
        """
        # Méthode très simple de détection, à améliorer
        if re.search(r"function\s+\w+\s*\(|const\s+\w+\s*=|let\s+\w+|var\s+\w+|=>", code_content):
            if re.search(r"interface\s+\w+|type\s+\w+\s*=|\w+\s*:\s*\w+[]?", code_content):
                return "typescript"
            return "javascript"
        
        if re.search(r"def\s+\w+\s*\(|import\s+\w+|from\s+\w+\s+import", code_content):
            return "python"
        
        if re.search(r"public\s+class|private\s+\w+|protected\s+\w+", code_content):
            return "java"
        
        if re.search(r"#include|int\s+main\s*\(", code_content):
            return "c++"
        
        return None
    
    def _detect_js_frameworks(self, code_content: str) -> Dict[str, float]:
        """
        Détecte les frameworks JavaScript utilisés dans le code.
        
        Args:
            code_content: Contenu du code
            
        Returns:
            Dictionnaire des frameworks et leur score de confiance
        """
        frameworks = {}
        
        # Motifs pour détecter les frameworks
        patterns = {
            "react": (r"import\s+React|from\s+['\"]react['\"]|React\.\w+|useState|useEffect", 0.9),
            "vue": (r"import\s+Vue|from\s+['\"]vue['\"]|new\s+Vue|createApp", 0.9),
            "angular": (r"import\s+{.*}\s+from\s+['\"]@angular|NgModule|Component", 0.9),
            "svelte": (r"import\s+Svelte|from\s+['\"]svelte['\"]", 0.9),
            "next": (r"import\s+.*\s+from\s+['\"]next|NextPage|GetServerSideProps", 0.8),
            "nuxt": (r"import\s+.*\s+from\s+['\"]nuxt|useNuxt", 0.8),
            "jquery": (r"\$\(|jQuery\(", 0.7),
        }
        
        for framework, (pattern, confidence) in patterns.items():
            if re.search(pattern, code_content):
                frameworks[framework] = confidence
        
        return frameworks
    
    def _detect_python_frameworks(self, code_content: str) -> Dict[str, float]:
        """
        Détecte les frameworks Python utilisés dans le code.
        
        Args:
            code_content: Contenu du code
            
        Returns:
            Dictionnaire des frameworks et leur score de confiance
        """
        frameworks = {}
        
        # Motifs pour détecter les frameworks
        patterns = {
            "django": (r"from\s+django|import\s+django|settings\.py", 0.9),
            "flask": (r"from\s+flask\s+import|import\s+flask|Flask\s*\(", 0.9),
            "fastapi": (r"from\s+fastapi\s+import|import\s+fastapi|FastAPI\s*\(", 0.9),
            "pytorch": (r"import\s+torch|from\s+torch", 0.9),
            "tensorflow": (r"import\s+tensorflow|from\s+tensorflow", 0.9),
            "pandas": (r"import\s+pandas|from\s+pandas", 0.8),
            "numpy": (r"import\s+numpy|from\s+numpy|np\.", 0.8),
            "matplotlib": (r"import\s+matplotlib|from\s+matplotlib", 0.7),
        }
        
        for framework, (pattern, confidence) in patterns.items():
            if re.search(pattern, code_content):
                frameworks[framework] = confidence
        
        return frameworks


if __name__ == "__main__":
    # Configuration pour le développement/test
    github_token = os.environ.get("GITHUB_TOKEN")
    
    # Créer l'agent
    coding_agent = CodingAgent(
        redis_host='localhost',
        redis_port=6379,
        db_path='alfred_coding.db',
        github_token=github_token
    )
    
    # Démarrer l'agent
    coding_agent.start()
    
    try:
        # En mode test, créer un utilisateur s'il n'existe pas déjà
        test_user_id = "flo_123"
        existing_user = False
        
        try:
            with coding_agent._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE id = ?", (test_user_id,))
                if cursor.fetchone():
                    existing_user = True
        except:
            pass
        
        if not existing_user:
            coding_agent.create_user("Flo")
            
            # Ajouter quelques préférences de base
            coding_agent.add_user_preference(test_user_id, "language", "python", 0.9)
            coding_agent.add_user_preference(test_user_id, "language", "javascript", 0.8)
            coding_agent.add_user_preference(test_user_id, "framework", "react", 0.9)
            coding_agent.add_user_preference(test_user_id, "framework", "django", 0.7)
            coding_agent.add_user_preference(test_user_id, "tool", "vscode", 0.9)
            coding_agent.add_user_preference(test_user_id, "tool", "git", 0.8)
            
            # Ajouter un projet exemple
            coding_agent.add_project(
                test_user_id,
                {
                    "name": "MonProjetReact",
                    "path": "/home/flo/projects/monprojetreact",
                    "git_repo": "https://github.com/flo/monprojetreact",
                    "description": "Application web React avec backend Django",
                    "tech_stack": {
                        "frontend": ["react", "typescript", "tailwindcss"],
                        "backend": ["django", "python"],
                        "database": ["postgresql"]
                    },
                    "packages": [
                        {"name": "react", "version": "18.2.0", "ecosystem": "npm"},
                        {"name": "typescript", "version": "4.9.5", "ecosystem": "npm"},
                        {"name": "tailwindcss", "version": "3.2.4", "ecosystem": "npm"},
                        {"name": "django", "version": "4.1.5", "ecosystem": "pypi"},
                        {"name": "psycopg2", "version": "2.9.5", "ecosystem": "pypi"}
                    ]
                }
            )
        
        # Boucle principale pour le test
        print("Agent de codage démarré. Appuyez sur Ctrl+C pour quitter.")
        print("Vous pouvez interagir avec l'agent en utilisant le canal Redis.")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        coding_agent.stop()
        print("Agent de codage arrêté.")
"""
Agent Codage - Assistant de développement logiciel personnalisé pour Alfred
Ce script implémente un agent capable de suivre les actualités technologiques,
d'apprendre les préférences de développement et de fournir une assistance proactive.
"""

import os
import json
import time
import threading
import logging
import sqlite3
import feedparser
import requests
import re
import uuid
import datetime
import hashlib
from typing import Dict, Any, List, Optional, Tuple, Union
from contextlib import contextmanager

# Importation de l'agent de base
from base_agent import BaseAgent

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("alfred_coding.log"), logging.StreamHandler()]
)

class CodingAgent(BaseAgent):
    """
    Agent de codage pour Alfred, conçu pour aider Flo dans ses tâches de développement.
    Cet agent surveille les tendances technologiques et fournit des recommandations
    personnalisées basées sur les préférences de l'utilisateur.
    """
    
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379,
                 db_path: str = 'alfred_coding.db', github_token: str = None):
        """
        Initialise l'agent de codage.
        
        Args:
            redis_host: Hôte Redis
            redis_port: Port Redis
            db_path: Chemin vers la base de données SQLite
            github_token: Token d'API GitHub pour les requêtes avec limite plus élevée
        """
        super().__init__("coding", redis_host, redis_port)
        self.capabilities = [
            "tech_watch",
            "code_assistance",
            "preference_learning",
            "project_management",
            "package_updates"
        ]
        
        # Configuration
        self.db_path = db_path
        self.github_token = github_token
        self.github_headers = {'Authorization': f'token {github_token}'} if github_token else {}
        
        # Initialisation de la base de données
        self._init_database()
        
        # Sources de veille technologique
        self.tech_sources = self._load_tech_sources()
        
        # État de l'agent
        self.running = False
        self.last_tech_watch_check = 0
        self.tech_watch_interval = 3600  # 1 heure par défaut
        self.pending_notifications = []
        
        # Configuration des threads pour les vérifications périodiques
        self.tech_watch_thread = None
        
        self.logger.info("Agent Codage initialisé")
    
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
        """Initialise la base de données avec les tables nécessaires."""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Table utilisateurs
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_interaction TIMESTAMP
                )
                ''')
                
                # Table des préférences de développement
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS dev_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    category TEXT NOT NULL,
                    item TEXT NOT NULL,
                    value REAL DEFAULT 1.0,  -- score de préférence entre 0 et 1
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE(user_id, category, item)
                )
                ''')
                
                # Table des projets suivis
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    name TEXT NOT NULL,
                    path TEXT,
                    git_repo TEXT,
                    description TEXT,
                    tech_stack TEXT,  -- JSON avec langages, frameworks, etc.
                    last_scan TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                ''')
                
                # Table des packages/dépendances suivies
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER,
                    name TEXT NOT NULL,
                    current_version TEXT,
                    latest_version TEXT,
                    ecosystem TEXT,  -- npm, pypi, etc.
                    last_checked TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
                ''')
                
                # Table des sources de veille technologique
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS tech_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,  -- rss, github, twitter, etc.
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    category TEXT,  -- language, framework, tool, etc.
                    tags TEXT,  -- JSON avec tags pour classement
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                # Table des actualités technologiques
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS tech_news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER,
                    title TEXT NOT NULL,
                    content TEXT,
                    url TEXT,
                    published_at TIMESTAMP,
                    retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    relevance_score REAL DEFAULT 0.0,
                    notification_sent INTEGER DEFAULT 0,
                    item_hash TEXT UNIQUE,
                    FOREIGN KEY (source_id) REFERENCES tech_sources(id)
                )
                ''')
                
                # Table des notifications d'actualités envoyées
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS news_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    news_id INTEGER,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    interaction TEXT,  -- liked, dismissed, saved, etc.
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (news_id) REFERENCES tech_news(id)
                )
                ''')
                
                # Table des historiques de recherche
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    query TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                ''')
                
                conn.commit()
                self.logger.info("Base de données initialisée")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation de la base de données: {e}")
    
    def _load_tech_sources(self) -> List[Dict[str, Any]]:
        """Charge les sources de veille technologique depuis la base de données."""
        sources = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM tech_sources WHERE active = 1')
                rows = cursor.fetchall()
                
                for row in rows:
                    sources.append(dict(row))
                
                # Si aucune source n'est définie, ajouter des sources par défaut
                if not sources:
                    self._add_default_tech_sources()
                    # Recharger les sources
                    cursor.execute('SELECT * FROM tech_sources WHERE active = 1')
                    rows = cursor.fetchall()
                    for row in rows:
                        sources.append(dict(row))
            
            self.logger.info(f"Chargement de {len(sources)} sources de veille technologique")
        except Exception as e:
            self.logger.error(f"Erreur lors du chargement des sources de veille: {e}")
        
        return sources
    
    def _add_default_tech_sources(self) -> None:
        """Ajoute des sources de veille technologique par défaut."""
        default_sources = [
            # RSS feeds pour les actualités technologiques
            ("rss", "Python Blog", "https://blog.python.org/feeds/posts/default", "language", json.dumps(["python", "language"])),
            ("rss", "React Blog", "https://reactjs.org/feed.xml", "framework", json.dumps(["javascript", "react", "frontend"])),
            ("rss", "Vue.js News", "https://news.vuejs.org/feed.xml", "framework", json.dumps(["javascript", "vue", "frontend"])),
            ("rss", "Angular Blog", "https://blog.angular.io/feed", "framework", json.dumps(["javascript", "angular", "frontend"])),
            ("rss", "Node.js Blog", "https://nodejs.org/en/feed/blog.xml", "language", json.dumps(["javascript", "nodejs", "backend"])),
            ("rss", "TypeScript Blog", "https://devblogs.microsoft.com/typescript/feed/", "language", json.dumps(["typescript", "language"])),
            ("rss", "CSS-Tricks", "https://css-tricks.com/feed/", "frontend", json.dumps(["css", "web", "frontend"])),
            ("rss", "Hacker News", "https://news.ycombinator.com/rss", "general", json.dumps(["tech", "general"])),
            
            # GitHub API endpoints pour les tendances
            ("github", "GitHub Trending Python", "https://api.github.com/search/repositories?q=language:python&sort=stars&order=desc", "language", json.dumps(["python", "github"])),
            ("github", "GitHub Trending JavaScript", "https://api.github.com/search/repositories?q=language:javascript&sort=stars&order=desc", "language", json.dumps(["javascript", "github"])),
            ("github", "GitHub Trending TypeScript", "https://api.github.com/search/repositories?q=language:typescript&sort=stars&order=desc", "language", json.dumps(["typescript", "github"])),
            ("github", "GitHub Trending React", "https://api.github.com/search/repositories?q=topic:react&sort=stars&order=desc", "framework", json.dumps(["react", "github"])),
            ("github", "GitHub Trending Vue", "https://api.github.com/search/repositories?q=topic:vue&sort=stars&order=desc", "framework", json.dumps(["vue", "github"])),
            
            # Sites tech populaires avec des flux RSS
            ("rss", "Dev.to", "https://dev.to/feed", "general", json.dumps(["tech", "community"])),
            ("rss", "InfoQ", "https://feed.infoq.com", "general", json.dumps(["tech", "enterprise"])),
            ("rss", "TechCrunch", "https://techcrunch.com/feed/", "news", json.dumps(["tech", "business"])),
            ("rss", "Medium - JavaScript", "https://medium.com/feed/tag/javascript", "language", json.dumps(["javascript", "articles"])),
            ("rss", "Medium - Python", "https://medium.com/feed/tag/python", "language", json.dumps(["python", "articles"])),
        ]
        
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                for source in default_sources:
                    cursor.execute('''
                    INSERT INTO tech_sources (source_type, name, url, category, tags)
                    VALUES (?, ?, ?, ?, ?)
                    ''', source)
                
                conn.commit()
                self.logger.info(f"Ajout de {len(default_sources)} sources de veille par défaut")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'ajout des sources par défaut: {e}")
    
    def on_start(self) -> None:
        """Actions à effectuer lors du démarrage de l'agent."""
        self.broadcast_message("agent_online", {
            "agent_type": "coding",
            "capabilities": self.capabilities
        })
        
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities
        })
        
        # Démarrer le thread de veille technologique
        self.running = True
        self.tech_watch_thread = threading.Thread(target=self._tech_watch_loop, daemon=True)
        self.tech_watch_thread.start()
        
        # Configuration de l'écoute Redis
        self.setup_redis_listener()
        
        self.logger.info("Agent Codage démarré")
    
    def on_stop(self) -> None:
        """Actions à effectuer lors de l'arrêt de l'agent."""
        self.running = False
        if self.tech_watch_thread:
            self.tech_watch_thread.join(timeout=2)
        
        # Arrêter l'écoute Redis
        if hasattr(self, 'redis_pubsub'):
            self.redis_pubsub.unsubscribe()
        
        self.broadcast_message("agent_offline", {
            "agent_type": "coding",
            "shutdown_time": time.time()
        })
        
        self.logger.info("Agent Codage arrêté")
    
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
                response = self.process_user_query(user_id, message_text, context)
                self.send_redis_message(f"orchestrator:notifications", 
                                      'response_to_user', 
                                      {'user_id': user_id, 'message': response})
        
        elif msg_type == 'tech_watch_request':
            # Demande spécifique de veille technologique
            user_id = data.get('user_id')
            query = data.get('query')
            
            if user_id and query:
                results = self.search_tech_news(query)
                self.send_redis_message(f"orchestrator:notifications", 
                                      'tech_watch_results', 
                                      {'user_id': user_id, 'query': query, 'results': results})
        
        elif msg_type == 'project_update':
            # Notification de mise à jour de projet
            user_id = data.get('user_id')
            project_data = data.get('project_data', {})
            
            if user_id and project_data:
                self.update_project_info(user_id, project_data)
        
        elif msg_type == 'package_check_request':
            # Demande de vérification des mises à jour de packages
            user_id = data.get('user_id')
            project_id = data.get('project_id')
            
            if user_id and project_id:
                updates = self.check_package_updates(project_id)
                self.send_redis_message(f"orchestrator:notifications", 
                                      'package_updates', 
                                      {'user_id': user_id, 'project_id': project_id, 'updates': updates})
        
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
    
    def _tech_watch_loop(self) -> None:
        """Boucle principale pour la veille technologique."""
        while self.running:
            current_time = time.time()
            
            # Vérifier les nouvelles actualités selon l'intervalle défini
            if current_time - self.last_tech_watch_check >= self.tech_watch_interval:
                self.last_tech_watch_check = current_time
                self.perform_tech_watch()
                
                # Traiter les notifications en attente
                self._process_pending_notifications()
            
            # Petite pause pour éviter de surcharger le CPU
            time.sleep(10)
    
    def perform_tech_watch(self) -> None:
        """Effectue une veille technologique complète."""
        self.logger.info("Début de la veille technologique...")
        
        try:
            for source in self.tech_sources:
                source_type = source.get('source_type')
                source_id = source.get('id')
                source_url = source.get('url')
                
                if source_type == 'rss':
                    self._process_rss_feed(source_id, source_url)
                elif source_type == 'github':
                    self._process_github_api(source_id, source_url)
                # Ajouter d'autres types de sources au besoin
                
                # Petite pause entre les sources pour éviter les limitations d'API
                time.sleep(1)
            
            # Analyser la pertinence des nouvelles actualités
            self._analyze_news_relevance()
            
            self.logger.info("Veille technologique terminée")
        except Exception as e:
            self.logger.error(f"Erreur lors de la veille technologique: {e}")
    
    def _process_rss_feed(self, source_id: int, feed_url: str) -> None:
        """Traite un flux RSS pour extraire les actualités."""
        try:
            feed = feedparser.parse(feed_url)
            
            # Parcourir les entrées du flux
            for entry in feed.entries[:10]:  # Limiter aux 10 entrées les plus récentes
                title = entry.get('title', '')
                link = entry.get('link', '')
                
                # Récupérer le contenu
                content = ''
                if 'content' in entry:
                    content = entry.content[0].value
                elif 'summary' in entry:
                    content = entry.summary
                
                # Date de publication
                published = entry.get('published_parsed')
                published_date = datetime.datetime(*published[:6]) if published else datetime.datetime.now()
                
                # Créer un hash unique pour éviter les doublons
                item_hash = hashlib.md5((title + link).encode()).hexdigest()
                
                # Vérifier si cette actualité existe déjà
                with self._get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT id FROM tech_news WHERE item_hash = ?', (item_hash,))
                    
                    if not cursor.fetchone():
                        # Ajouter la nouvelle actualité
                        cursor.execute('''
                        INSERT INTO tech_news (source_id, title, content, url, published_at, item_hash)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ''', (source_id, title, content, link, published_date, item_hash))
                        
                        conn.commit()
            
            self.logger.info(f"Traitement du flux RSS {feed_url} terminé")
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du flux RSS {feed_url}: {e}")
    
    def _process_github_api(self, source_id: int, api_url: str) -> None:
        """Traite une requête à l'API GitHub pour extraire les tendances."""
        try:
            response = requests.get(api_url, headers=self.github_headers)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                for item in items[:10]:  # Limiter aux 10 premiers résultats
                    title = item.get('full_name', '')
                    url = item.get('html_url', '')
                    description = item.get('description', '')
                    stars = item.get('stargazers_count', 0)
                    
                    # Créer un contenu enrichi avec plus d'informations
                    content = f"Description: {description}\nÉtoiles: {stars}\nLanguage: {item.get('language', 'Non spécifié')}"
                    
                    # Date de mise à jour du dépôt
                    updated_at = item.get('updated_at')
                    published_date = datetime.datetime.fromisoformat(updated_at.replace('Z', '+00:00')) if updated_at else datetime.datetime.now()
                    
                    # Créer un hash unique
                    item_hash = hashlib.md5((title + url).encode()).hexdigest()
                    
                    # Vérifier si cette actualité existe déjà
                    with self._get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT id FROM tech_news WHERE item_hash = ?', (item_hash,))
                        
                        if not cursor.fetchone():
                            # Ajouter la nouvelle actualité
                            cursor.execute('''
                            INSERT INTO tech_news (source_id, title, content, url, published_at, item_hash)
                            VALUES (?, ?, ?, ?, ?, ?)
                            ''', (source_id, title, content, url, published_date, item_hash))
                            
                            conn.commit()
                
                self.logger.info(f"Traitement de l'API GitHub {api_url} terminé")
            else:
                self.logger.warning(f"Erreur {response.status_code} lors de l'accès à l'API GitHub {api_url}")
        
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement de l'API GitHub {api_url}: {e}")
    
    def _analyze_news_relevance(self) -> None:
        """Analyse la pertinence des actualités par rapport aux préférences des utilisateurs."""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Récupérer les actualités non traitées
                cursor.execute('''
                SELECT n.id, n.title, n.content, s.category, s.tags
                FROM tech_news n
                JOIN tech_sources s ON n.source_id = s.id
                WHERE n.relevance_score = 0.0 AND n.notification_sent = 0
                ''')
                
                news_items = cursor.fetchall()
                
                for news in news_items:
                    news_id = news['id']
                    title = news['title']
                    content = news['content']
                    category = news['category']
                    tags = json.loads(news['tags']) if news['tags'] else []
                    
                    # Récupérer tous les utilisateurs
                    cursor.execute('SELECT id FROM users')
                    users = cursor.fetchall()
                    
                    for user in users:
                        user_id = user['id']
                        
                        # Calculer un score de pertinence pour cet utilisateur
                        relevance_score = self._calculate_relevance_score(user_id, title, content, category, tags)
                        
                        # Si le score est suffisamment élevé, préparer une notification
                        if relevance_score > 0.7:  # Seuil de pertinence à ajuster
                            self.pending_notifications.append({
                                'user_id': user_id,
                                'news_id': news_id,
                                'title': title,
                                'relevance': relevance_score
                            })
                    
                    # Mettre à jour le score de pertinence moyen
                    cursor.execute('''
                    UPDATE tech_news
                    SET relevance_score = ?
                    WHERE id = ?
                    ''', (0.5, news_id))  # Score par défaut, pourrait être plus sophistiqué
                    
                    conn.commit()
            
            self.logger.info(f"Analyse de pertinence terminée pour {len(news_items)} actualités")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'analyse de pertinence: {e}")
    
    def _calculate_relevance_score(self, user_id: str, title: str, content: str, 
                                 category: str, tags: List[str]) -> float:
        """
        Calcule un score de pertinence pour une actualité en fonction des préférences de l'utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            title: Titre de l'actualité
            content: Contenu de l'actualité
            category: Catégorie de la source
            tags: Liste des tags associés
            
        Returns:
            Score de pertinence entre 0 et 1
        """
        try:
            # Récupérer les préférences de l'utilisateur
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT category, item, value FROM dev_preferences
                WHERE user_id = ?
                ''', (user_id,))
                
                preferences = cursor.fetchall()
                
                if not preferences:
                    return 0.5  # Score neutre si pas de préférences
                
                # Convertir en texte unique pour la recherche
                text = (title + " " + content).lower()
                
                # Score initial
                score = 0.5
                matches = 0
                
                # Vérifier si des éléments préférés sont mentionnés
                for pref in preferences:
                    pref_category = pref['category']
                    pref_item = pref['item'].lower()
                    pref_value = pref['value']
                    
                    # Vérifier si la préférence apparaît dans le texte
                    if pref_item in text:
                        score += 0.1 * pref_value
                        matches += 1
                    
                    # Boost si la catégorie correspond
                    if pref_category == category:
                        score += 0.05
                    
                    # Vérifier les tags
                    for tag in tags:
                        if pref_item == tag.lower():
                            score += 0.05 * pref_value
                            matches += 1
                
                # Normaliser le score
                if matches > 0:
                    score = min(score, 1.0)
                
                return score
        
        except Exception as e:
            self.logger.error(f"Erreur lors du calcul du score de pertinence: {e}")
            return 0.5
    
    