"""
Agent Cours - Assistant pédagogique spécialisé pour les professeurs d'économie-gestion
Ce script implémente un agent capable de suivre les actualités économiques, juridiques et commerciales,
d'aider à la conception de cours et de s'adapter aux besoins d'un enseignant.
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
import html2text
import tempfile
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional, Tuple, Union
from contextlib import contextmanager

# Import for PDF generation
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    
# Importation de l'agent de base
from base_agent import BaseAgent

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("alfred_cours.log"), logging.StreamHandler()]
)

class CoursAgent(BaseAgent):
    """
    Agent Cours pour Alfred, conçu pour aider les professeurs d'économie-gestion
    dans leur veille pédagogique et la conception de leurs cours.
    """
    
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379,
                 db_path: str = 'alfred_cours.db', api_keys: Dict[str, str] = None):
        """
        Initialise l'agent de cours.
        
        Args:
            redis_host: Hôte Redis
            redis_port: Port Redis
            db_path: Chemin vers la base de données SQLite
            api_keys: Clés API pour les services externes (Google News, etc.)
        """
        super().__init__("cours", redis_host, redis_port)
        self.capabilities = [
            "veille_pedagogique",
            "assistance_conception_cours",
            "suivi_actualite",
            "generation_supports",
            "recherche_ressources"
        ]
        
        # Configuration
        self.db_path = db_path
        self.api_keys = api_keys or {}
        
        # Initialisation de la base de données
        self._init_database()
        
        # Sources de veille
        self.veille_sources = self._load_veille_sources()
        
        # État de l'agent
        self.running = False
        self.last_veille_check = 0
        self.veille_check_interval = 14400  # 4 heures par défaut
        self.pending_notifications = []
        
        # Configuration des threads pour les vérifications périodiques
        self.veille_thread = None
        
        # Thèmes et matières suivis
        self.followed_themes = self._load_followed_themes()
        
        self.logger.info("Agent Cours initialisé")
    
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
                    last_interaction TIMESTAMP,
                    preferences TEXT  -- JSON avec les préférences
                )
                ''')
                
                # Table des thèmes et matières suivis
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS themes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    name TEXT NOT NULL,
                    description TEXT,
                    keywords TEXT,  -- JSON avec mots-clés liés
                    importance REAL DEFAULT 1.0,  -- Importance de 0 à 1
                    level TEXT,  -- Niveau scolaire associé
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE(user_id, name)
                )
                ''')
                
                # Table des sources de veille
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS veille_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,  -- rss, api, website
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    category TEXT,  -- juridique, économique, commercial, etc.
                    tags TEXT,  -- JSON avec tags pour classement
                    refresh_interval INTEGER DEFAULT 14400,  -- en secondes (4h par défaut)
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                # Table des actualités récupérées
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS actu_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER,
                    title: Titre du rapport
            articles: Liste des articles à inclure
            theme: Thème du rapport (facultatif)
            
        Returns:
            Chemin vers le fichier Markdown généré
        """
        # Créer un nom de fichier unique
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"veille_{timestamp}.md"
        
        # Créer le chemin du fichier
        report_dir = os.path.join(os.getcwd(), "reports")
        os.makedirs(report_dir, exist_ok=True)
        file_path = os.path.join(report_dir, filename)
        
        # Construire le contenu Markdown
        markdown_content = [f"# {title}\n\n"]
        
        # Introduction
        intro_text = "Ce rapport présente une synthèse des actualités récentes"
        if theme:
            intro_text += f" sur le thème \"{theme}\""
        intro_text += ".\n\n"
        
        markdown_content.append(intro_text)
        
        # Sommaire
        markdown_content.append("## Sommaire\n\n")
        for i, article in enumerate(articles, 1):
            markdown_content.append(f"{i}. [{article['title']}](#{i}-{article['title'].lower().replace(' ', '-').replace(':', '').replace('?', '').replace('!', '').replace('.', '').replace(',', '')})\n")
        
        markdown_content.append("\n\n")
        
        # Contenu principal avec les articles
        markdown_content.append("## Articles\n\n")
        
        # Grouper les articles par catégorie
        articles_by_category = {}
        for article in articles:
            category = article.get('category', 'Divers')
            if category not in articles_by_category:
                articles_by_category[category] = []
            articles_by_category[category].append(article)
        
        # Ajouter les articles par catégorie
        for category, category_articles in articles_by_category.items():
            markdown_content.append(f"### {category.capitalize()}\n\n")
            
            for i, article in enumerate(category_articles, 1):
                anchor = f"{i}-{article['title'].lower().replace(' ', '-').replace(':', '').replace('?', '').replace('!', '').replace('.', '').replace(',', '')}"
                markdown_content.append(f"#### <a id='{anchor}'></a>{article['title']}\n\n")
                markdown_content.append(f"**Source**: {article['source']} - {self._format_date(article.get('published_at', ''))}\n\n")
                
                if article.get('summary'):
                    markdown_content.append(f"{article['summary']}\n\n")
                
                if article.get('url'):
                    markdown_content.append(f"[Lien vers l'article complet]({article['url']})\n\n")
                
                markdown_content.append("---\n\n")
        
        # Écrire dans le fichier
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(''.join(markdown_content))
        
        return file_path
    
    def _format_date(self, date_str: str) -> str:
        """
        Formate une date pour l'affichage.
        
        Args:
            date_str: Date au format ISO ou timestamp
            
        Returns:
            Date formatée pour l'affichage
        """
        try:
            if isinstance(date_str, str):
                date = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            elif isinstance(date_str, (int, float)):
                date = datetime.datetime.fromtimestamp(date_str)
            else:
                date = date_str
                
            return date.strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            return date_str
    
    def assist_course_creation(self, user_id: str, course_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assiste à la création d'un cours en suggérant du contenu et des ressources.
        
        Args:
            user_id: ID de l'utilisateur
            course_data: Données sur le cours à créer
            
        Returns:
            Suggestions et assistance pour le cours
        """
        result = {
            "success": True,
            "suggestions": [],
            "resources": [],
            "veille": []
        }
        
        try:
            # Extraire les informations du cours
            theme = course_data.get('theme', '')
            level = course_data.get('level', '')
            objectives = course_data.get('objectives', [])
            keywords = course_data.get('keywords', [])
            
            # Rechercher des articles de veille pertinents
            relevant_articles = self.get_veille_by_theme(theme, limit=5)
            result['veille'] = relevant_articles
            
            # Rechercher des ressources existantes
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Trouver des thèmes correspondants
                cursor.execute('''
                SELECT id FROM themes 
                WHERE user_id = ? AND (name LIKE ? OR keywords LIKE ?)
                ''', (user_id, f'%{theme}%', f'%{",".join(keywords)}%'))
                
                theme_ids = [row['id'] for row in cursor.fetchall()]
                
                # Rechercher des ressources pour ces thèmes
                if theme_ids:
                    placeholders = ','.join(['?' for _ in theme_ids])
                    query = f'''
                    SELECT * FROM ressources 
                    WHERE user_id = ? AND theme_id IN ({placeholders})
                    '''
                    cursor.execute(query, [user_id] + theme_ids)
                    
                    resources = cursor.fetchall()
                    for resource in resources:
                        result['resources'].append({
                            'id': resource['id'],
                            'title': resource['title'],
                            'description': resource['description'],
                            'url': resource['url'],
                            'type': resource['resource_type']
                        })
                
                # Rechercher des supports de cours existants
                if theme_ids:
                    placeholders = ','.join(['?' for _ in theme_ids])
                    query = f'''
                    SELECT * FROM cours_supports 
                    WHERE user_id = ? AND theme_id IN ({placeholders})
                    '''
                    cursor.execute(query, [user_id] + theme_ids)
                    
                    supports = cursor.fetchall()
                    for support in supports:
                        result['suggestions'].append({
                            'type': 'existing_support',
                            'id': support['id'],
                            'title': support['title'],
                            'description': support['description'],
                            'message': f"J'ai trouvé un support existant sur '{support['title']}' qui pourrait vous être utile."
                        })
            
            # Générer des suggestions basées sur les mots-clés et objectifs
            for keyword in keywords:
                result['suggestions'].append({
                    'type': 'keyword_suggestion',
                    'keyword': keyword,
                    'message': f"Pensez à inclure du contenu sur '{keyword}' qui est un élément clé pour ce cours."
                })
            
            # Suggestions basées sur les articles récents
            if relevant_articles:
                result['suggestions'].append({
                    'type': 'actualite_suggestion',
                    'articles': [article['title'] for article in relevant_articles[:3]],
                    'message': f"J'ai trouvé {len(relevant_articles)} actualités récentes qui pourraient enrichir votre cours."
                })
            
            # Suggestion de structure
            if objectives:
                suggested_structure = [
                    "Introduction - Présentation du thème et des objectifs",
                ]
                for i, objective in enumerate(objectives, 1):
                    suggested_structure.append(f"Partie {i} - {objective}")
                
                suggested_structure.append("Conclusion - Synthèse et ouverture")
                suggested_structure.append("Évaluation - Exercices et activités")
                
                result['suggestions'].append({
                    'type': 'structure_suggestion',
                    'structure': suggested_structure,
                    'message': "Voici une proposition de structure pour votre cours, basée sur vos objectifs."
                })
            
            # Enregistrer cette requête dans l'historique
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO requetes_historique (user_id, query, query_type)
                VALUES (?, ?, ?)
                ''', (user_id, json.dumps(course_data), 'aide_cours'))
                
                conn.commit()
            
            self.logger.info(f"Assistance à la création de cours générée pour l'utilisateur {user_id}")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de l'assistance à la création de cours: {e}")
            result['success'] = False
            result['error'] = str(e)
        
        return result
    
    def add_theme(self, user_id: str, theme_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ajoute un nouveau thème à suivre.
        
        Args:
            user_id: ID de l'utilisateur
            theme_data: Données du thème à ajouter
            
        Returns:
            Résultat de l'opération
        """
        try:
            name = theme_data.get('name')
            description = theme_data.get('description', '')
            keywords = theme_data.get('keywords', [])
            importance = theme_data.get('importance', 1.0)
            level = theme_data.get('level', '')
            
            if not name:
                return {"success": False, "error": "Nom du thème requis"}
            
            # Convertir les mots-clés en JSON
            keywords_json = json.dumps(keywords)
            
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                try:
                    cursor.execute('''
                    INSERT INTO themes (user_id, name, description, keywords, importance, level)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''', (user_id, name, description, keywords_json, importance, level))
                    
                    theme_id = cursor.lastrowid
                    conn.commit()
                
                except sqlite3.IntegrityError:
                    # Le thème existe déjà, le mettre à jour
                    cursor.execute('''
                    UPDATE themes
                    SET description = ?, keywords = ?, importance = ?, level = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND name = ?
                    ''', (description, keywords_json, importance, level, user_id, name))
                    
                    # Récupérer l'ID du thème
                    cursor.execute('SELECT id FROM themes WHERE user_id = ? AND name = ?', (user_id, name))
                    theme_id = cursor.fetchone()['id']
                    
                    conn.commit()
            
            # Recharger les thèmes
            self.followed_themes = self._load_followed_themes()
            
            self.logger.info(f"Thème '{name}' ajouté ou mis à jour pour l'utilisateur {user_id}")
            
            return {
                "success": True,
                "theme_id": theme_id,
                "message": f"Thème '{name}' ajouté avec succès."
            }
        
        except Exception as e:
            self.logger.error(f"Erreur lors de l'ajout du thème: {e}")
            return {"success": False, "error": str(e)}
    
    def add_resource(self, user_id: str, resource_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ajoute une nouvelle ressource pédagogique.
        
        Args:
            user_id: ID de l'utilisateur
            resource_data: Données de la ressource à ajouter
            
        Returns:
            Résultat de l'opération
        """
        try:
            title = resource_data.get('title')
            description = resource_data.get('description', '')
            url = resource_data.get('url', '')
            file_path = resource_data.get('file_path', '')
            resource_type = resource_data.get('type', 'document')
            theme_id = resource_data.get('theme_id')
            level = resource_data.get('level', '')
            
            if not title:
                return {"success": False, "error": "Titre de la ressource requis"}
            
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO ressources (user_id, title, description, url, file_path, resource_type, theme_id, level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, title, description, url, file_path, resource_type, theme_id, level))
                
                resource_id = cursor.lastrowid
                conn.commit()
            
            self.logger.info(f"Ressource '{title}' ajoutée pour l'utilisateur {user_id}")
            
            return {
                "success": True,
                "resource_id": resource_id,
                "message": f"Ressource '{title}' ajoutée avec succès."
            }
        
        except Exception as e:
            self.logger.error(f"Erreur lors de l'ajout de la ressource: {e}")
            return {"success": False, "error": str(e)}
    
    def create_user(self, name: str, preferences: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Crée un nouvel utilisateur.
        
        Args:
            name: Nom de l'utilisateur
            preferences: Préférences de l'utilisateur (facultatif)
            
        Returns:
            Résultat de l'opération
        """
        try:
            # Générer un ID unique
            user_id = str(uuid.uuid4())
            
            # Enregistrer les préférences en JSON
            preferences_json = json.dumps(preferences or {})
            
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO users (id, name, preferences, last_interaction)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, name, preferences_json))
                
                conn.commit()
            
            # Ajouter des thèmes par défaut pour l'économie-gestion
            default_themes = [
                {
                    "name": "Droit commercial",
                    "description": "Droit des affaires et des sociétés",
                    "keywords": ["contrat commercial", "société", "fonds de commerce", "bail commercial", "concurrence", "propriété intellectuelle"]
                },
                {
                    "name": "Droit du travail",
                    "description": "Relations employeur-employé, contrats de travail",
                    "keywords": ["contrat de travail", "licenciement", "convention collective", "représentation du personnel", "négociation sociale"]
                },
                {
                    "name": "Économie générale",
                    "description": "Principes économiques et analyse macroéconomique",
                    "keywords": ["marché", "offre", "demande", "PIB", "croissance", "inflation", "politique économique"]
                },
                {
                    "name": "Management",
                    "description": "Principes et techniques de management des organisations",
                    "keywords": ["leadership", "organisation", "motivation", "décision", "stratégie", "communication"]
                },
                {
                    "name": "Marketing",
                    "description": "Étude du comportement des consommateurs et stratégies marketing",
                    "keywords": ["étude de marché", "segmentation", "positionnement", "mix marketing", "marketing digital"]
                },
                {
                    "name": "Comptabilité",
                    "description": "Principes comptables et analyse financière",
                    "keywords": ["bilan", "compte de résultat", "comptabilité générale", "analyse financière", "coûts"]
                }
            ]
            
            for theme in default_themes:
                self.add_theme(user_id, theme)
            
            self.logger.info(f"Utilisateur '{name}' créé avec ID {user_id}")
            
            return {
                "success": True,
                "user_id": user_id,
                "message": f"Utilisateur '{name}' créé avec succès."
            }
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la création de l'utilisateur: {e}")
            return {"success": False, "error": str(e)}
    
    def get_resources(self, user_id: str, theme_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Récupère les ressources pédagogiques d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            theme_id: ID du thème (facultatif)
            
        Returns:
            Liste des ressources
        """
        resources = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                if theme_id:
                    cursor.execute('''
                    SELECT r.*, t.name as theme_name 
                    FROM ressources r
                    LEFT JOIN themes t ON r.theme_id = t.id
                    WHERE r.user_id = ? AND r.theme_id = ?
                    ORDER BY r.created_at DESC
                    ''', (user_id, theme_id))
                else:
                    cursor.execute('''
                    SELECT r.*, t.name as theme_name 
                    FROM ressources r
                    LEFT JOIN themes t ON r.theme_id = t.id
                    WHERE r.user_id = ?
                    ORDER BY r.created_at DESC
                    ''', (user_id,))
                
                rows = cursor.fetchall()
                
                for row in rows:
                    resources.append({
                        "id": row['id'],
                        "title": row['title'],
                        "description": row['description'],
                        "url": row['url'],
                        "file_path": row['file_path'],
                        "type": row['resource_type'],
                        "theme_id": row['theme_id'],
                        "theme_name": row.get('theme_name', ''),
                        "level": row['level'],
                        "created_at": row['created_at']
                    })
            
            self.logger.info(f"Récupération de {len(resources)} ressources pour l'utilisateur {user_id}")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des ressources: {e}")
        
        return resources
    
    def get_themes(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les thèmes suivis par un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            Liste des thèmes
        """
        themes = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM themes WHERE user_id = ? ORDER BY name', (user_id,))
                
                rows = cursor.fetchall()
                
                for row in rows:
                    theme = {
                        "id": row['id'],
                        "name": row['name'],
                        "description": row['description'],
                        "keywords": json.loads(row['keywords']) if row['keywords'] else [],
                        "importance": row['importance'],
                        "level": row['level']
                    }
                    themes.append(theme)
            
            self.logger.info(f"Récupération de {len(themes)} thèmes pour l'utilisateur {user_id}")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des thèmes: {e}")
        
        return themes
    
    def get_agent_stats(self) -> Dict[str, Any]:
        """
        Récupère des statistiques sur l'agent.
        
        Returns:
            Statistiques diverses
        """
        stats = {
            "veille_sources_count": 0,
            "articles_count": 0,
            "themes_count": 0,
            "users_count": 0,
            "last_veille_check": self._format_date(self.last_veille_check),
            "recent_articles": []
        }
        
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Nombre de sources de veille
                cursor.execute('SELECT COUNT(*) FROM veille_sources WHERE active = 1')
                stats["veille_sources_count"] = cursor.fetchone()[0]
                
                # Nombre d'articles
                cursor.execute('SELECT COUNT(*) FROM actu_articles')
                stats["articles_count"] = cursor.fetchone()[0]
                
                # Nombre de thèmes
                cursor.execute('SELECT COUNT(*) FROM themes')
                stats["themes_count"] = cursor.fetchone()[0]
                
                # Nombre d'utilisateurs
                cursor.execute('SELECT COUNT(*) FROM users')
                stats["users_count"] = cursor.fetchone()[0]
                
                # Articles récents
                cursor.execute('''
                SELECT aa.title, aa.published_at, vs.name as source_name
                FROM actu_articles aa
                JOIN veille_sources vs ON aa.source_id = vs.id
                ORDER BY aa.published_at DESC
                LIMIT 5
                ''')
                
                recent_articles = cursor.fetchall()
                for article in recent_articles:
                    stats["recent_articles"].append({
                        "title": article['title'],
                        "source": article['source_name'],
                        "published_at": self._format_date(article.get('published_at', ''))
                    })
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des statistiques: {e}")
        
        return stats
    
    def process_user_query(self, user_id: str, query: str, context: Dict[str, Any] = None) -> str:
        """
        Traite une requête textuelle d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            query: Texte de la requête
            context: Contexte supplémentaire (facultatif)
            
        Returns:
            Réponse textuelle à l'utilisateur
        """
        # Enregistrer la requête
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO requetes_historique (user_id, query, query_type)
            VALUES (?, ?, ?)
            ''', (user_id, query, 'query_texte'))
            
            # Mettre à jour la dernière interaction
            cursor.execute('UPDATE users SET last_interaction = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
            
            conn.commit()
        
        # Analyser la requête pour déterminer l'intention
        query_lower = query.lower()
        
        # Recherche de veille
        if any(keyword in query_lower for keyword in ['actu', 'actualité', 'veille', 'news', 'article']):
            # Rechercher un thème dans la requête
            theme = None
            for potential_theme in self.followed_themes:
                if potential_theme['name'].lower() in query_lower:
                    theme = potential_theme['name']
                    break
            
            # Si un thème est mentionné, effectuer une recherche spécifique
            if theme:
                articles = self.get_veille_by_theme(theme, limit=5)
                if articles:
                    response = f"Voici les actualités récentes sur {theme}:\n\n"
                    for i, article in enumerate(articles, 1):
                        response += f"{i}. {article['title']} ({article['source']})\n"
                        if article.get('url'):
                            response += f"   {article['url']}\n"
                        response += "\n"
                    
                    response += "Souhaitez-vous un rapport complet sur ce thème?"
                else:
                    response = f"Je n'ai pas trouvé d'actualités récentes sur {theme}. Souhaitez-vous élargir la recherche?"
            else:
                # Recherche générale
                articles = self.get_recent_veille(limit=5)
                if articles:
                    response = "Voici les actualités récentes :\n\n"
                    for i, article in enumerate(articles, 1):
                        response += f"{i}. {article['title']} ({article['source']})\n"
                        if article.get('summary'):
                            summary = article['summary']
                            if len(summary) > 100:
                                summary = summary[:100] + "..."
                            response += f"   {summary}\n"
                        response += "\n"
                else:
                    response = "Je n'ai pas trouvé d'actualités récentes. La veille sera mise à jour prochainement."
        
        # Aide à la création de cours
        elif any(keyword in query_lower for keyword in ['cours', 'leçon', 'séance', 'séquence', 'préparer']):
            # Extraire les potentiels thèmes ou sujets
            themes = self.get_themes(user_id)
            theme_names = [theme['name'].lower() for theme in themes]
            
            selected_theme = None
            for theme in theme_names:
                if theme in query_lower:
                    selected_theme = theme
                    break
            
            if selected_theme:
                response = f"Je vais vous aider à préparer un cours sur {selected_theme}. "
                response += "Pouvez-vous me préciser :\n"
                response += "1. Le niveau des élèves\n"
                response += "2. La durée du cours\n"
                response += "3. Les objectifs pédagogiques principaux\n"
                response += "\nJe pourrai alors vous proposer une structure et des ressources adaptées."
            else:
                response = "Je serai ravi de vous aider à préparer un cours. "
                response += "Pouvez-vous me préciser le thème et le niveau concernés?"
        
        # Recherche de ressources
        elif any(keyword in query_lower for keyword in ['ressource', 'document', 'exercice', 'support']):
            # Extraire les potentiels thèmes
            themes = self.get_themes(user_id)
            selected_theme_id = None
            
            for theme in themes:
                if theme['name'].lower() in query_lower:
                    selected_theme_id = theme['id']
                    break
            
            resources = self.get_resources(user_id, selected_theme_id)
            
            if resources:
                response = f"J'ai trouvé {len(resources)} ressources"
                if selected_theme_id:
                    theme_name = next((t['name'] for t in themes if t['id'] == selected_theme_id), "")
                    response += f" sur le thème '{theme_name}'"
                
                response += ":\n\n"
                
                for i, resource in enumerate(resources[:5], 1):
                    response += f"{i}. {resource['title']}"
                    if resource.get('theme_name'):
                        response += f" ({resource['theme_name']})"
                    response += "\n"
                    
                    if resource.get('description'):
                        response += f"   {resource['description']}\n"
                    
                    if resource.get('url'):
                        response += f"   URL: {resource['url']}\n"
                    
                    response += "\n"
                
                if len(resources) > 5:
                    response += f"... et {len(resources) - 5} autres ressources. Souhaitez-vous voir les autres?"
            else:
                response = "Je n'ai pas trouvé de ressources correspondant à votre demande. "
                response += "Souhaitez-vous en ajouter de nouvelles?"
        
        # Réponse par défaut
        else:
            response = "Bonjour! Je suis votre assistant pédagogique. Je peux vous aider pour :\n"
            response += "- La veille pédagogique et l'actualité économique, juridique et commerciale\n"
            response += "- La préparation et la conception de cours\n"
            response += "- La recherche de ressources pédagogiques\n"
            response += "- La génération de rapports de veille\n\n"
            response += "Comment puis-je vous être utile aujourd'hui?"
        
        self.logger.info(f"Réponse générée pour la requête: {query[:50]}...")
        return response
    
    def run(self):
        """Point d'entrée pour démarrer l'agent."""
        self.on_start()
        
        try:
            # Boucle principale - reste en vie tant que l'agent est en cours d'exécution
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Interruption clavier, arrêt de l'agent...")
        finally:
            self.on_stop()


if __name__ == "__main__":
    # Configuration des paramètres via des variables d'environnement ou des valeurs par défaut
    redis_host = os.environ.get('REDIS_HOST', 'localhost')
    redis_port = int(os.environ.get('REDIS_PORT', 6379))
    db_path = os.environ.get('DB_PATH', 'alfred_cours.db')
    
    # Clés API (à configurer selon vos besoins)
    api_keys = {
        'google_news': os.environ.get('GOOGLE_NEWS_API_KEY', ''),
        'news_api': os.environ.get('NEWS_API_KEY', '')
    }
    
    # Création et démarrage de l'agent
    agent = CoursAgent(redis_host, redis_port, db_path, api_keys)
    agent.run() TEXT NOT NULL,
                    content TEXT,
                    summary TEXT,
                    url TEXT,
                    published_at TIMESTAMP,
                    retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    themes TEXT,  -- JSON avec les ID des thèmes associés
                    relevance_score REAL DEFAULT 0.0,
                    notification_sent INTEGER DEFAULT 0,
                    viewed INTEGER DEFAULT 0,
                    saved INTEGER DEFAULT 0,
                    item_hash TEXT UNIQUE,
                    FOREIGN KEY (source_id) REFERENCES veille_sources(id)
                )
                ''')
                
                # Table des supports de cours
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS cours_supports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    content TEXT,  -- Contenu ou chemin vers le fichier
                    format TEXT,  -- markdown, pdf, docx, etc.
                    theme_id INTEGER,
                    level TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (theme_id) REFERENCES themes(id)
                )
                ''')
                
                # Table des ressources pédagogiques
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS ressources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    url TEXT,
                    file_path TEXT,
                    resource_type TEXT,  -- document, image, video, exercice, etc.
                    theme_id INTEGER,
                    level TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (theme_id) REFERENCES themes(id)
                )
                ''')
                
                # Table des préférences pédagogiques de l'utilisateur
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS preferences_pedagogiques (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    category TEXT NOT NULL,  -- format_cours, methode_evaluation, etc.
                    preference TEXT NOT NULL,
                    value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE(user_id, category, preference)
                )
                ''')
                
                # Table des rapports de veille générés
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS veille_rapports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    file_path TEXT,
                    format TEXT,  -- pdf, markdown, etc.
                    articles TEXT,  -- JSON avec les ID des articles inclus
                    themes TEXT,  -- JSON avec les ID des thèmes concernés
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                ''')
                
                # Table historique des requêtes
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS requetes_historique (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    query TEXT NOT NULL,
                    query_type TEXT,  -- recherche, aide_cours, etc.
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                ''')
                
                conn.commit()
                self.logger.info("Base de données initialisée")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation de la base de données: {e}")
    
    def _load_veille_sources(self) -> List[Dict[str, Any]]:
        """Charge les sources de veille depuis la base de données."""
        sources = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM veille_sources WHERE active = 1')
                rows = cursor.fetchall()
                
                for row in rows:
                    sources.append(dict(row))
                
                # Si aucune source n'est définie, ajouter des sources par défaut
                if not sources:
                    self._add_default_veille_sources()
                    # Recharger les sources
                    cursor.execute('SELECT * FROM veille_sources WHERE active = 1')
                    rows = cursor.fetchall()
                    for row in rows:
                        sources.append(dict(row))
            
            self.logger.info(f"Chargement de {len(sources)} sources de veille")
        except Exception as e:
            self.logger.error(f"Erreur lors du chargement des sources de veille: {e}")
        
        return sources
    
    def _add_default_veille_sources(self) -> None:
        """Ajoute des sources de veille par défaut pour l'économie-gestion."""
        default_sources = [
            # Sources d'actualité économique
            ("rss", "Les Echos", "https://services.lesechos.fr/rss/les-echos-economie.xml", "économique", json.dumps(["économie", "finance", "entreprise"])),
            ("rss", "La Tribune", "https://www.latribune.fr/rss/home.xml", "économique", json.dumps(["économie", "finance", "entreprise"])),
            ("rss", "Le Monde Économie", "https://www.lemonde.fr/economie/rss_full.xml", "économique", json.dumps(["économie", "international"])),
            ("rss", "Challenges", "https://www.challenges.fr/rss.xml", "économique", json.dumps(["économie", "entreprise", "management"])),
            
            # Sources d'actualité juridique
            ("rss", "Dalloz Actualité", "https://www.dalloz-actualite.fr/rss.xml", "juridique", json.dumps(["droit", "jurisprudence", "loi"])),
            ("rss", "Le Monde du Droit", "https://www.lemondedudroit.fr/rss.xml", "juridique", json.dumps(["droit", "profession", "réglementation"])),
            ("rss", "Légifrance", "https://www.legifrance.gouv.fr/rss.xml", "juridique", json.dumps(["loi", "réglementation", "textes officiels"])),
            
            # Sources d'actualité commerciale et marketing
            ("rss", "E-marketing", "https://www.e-marketing.fr/rss/actualites.xml", "commercial", json.dumps(["marketing", "digital", "commerce"])),
            ("rss", "Marketing Professionnel", "https://www.marketing-professionnel.fr/feed", "commercial", json.dumps(["marketing", "communication"])),
            ("rss", "LSA", "https://www.lsa-conso.fr/rss.xml", "commercial", json.dumps(["distribution", "consommation", "retail"])),
            
            # Sources pour l'enseignement et la pédagogie
            ("rss", "Café Pédagogique", "http://www.cafepedagogique.net/rss.aspx", "pédagogique", json.dumps(["éducation", "pédagogie", "enseignement"])),
            ("rss", "Éduscol", "https://eduscol.education.fr/flux/rss.xml", "pédagogique", json.dumps(["éducation nationale", "programmes", "réforme"])),
            
            # Sources spécifiques à l'économie-gestion
            ("rss", "Apeg", "http://www.apeg.info/feed", "économie-gestion", json.dumps(["économie-gestion", "enseignement", "ressources"])),
            ("rss", "Crcom", "https://crcom.ac-versailles.fr/feed/", "économie-gestion", json.dumps(["économie-gestion", "communication", "ressources"])),
            
            # Sources institutionnelles
            ("rss", "INSEE", "https://www.insee.fr/fr/statistiques/rss", "institutionnel", json.dumps(["statistiques", "économie", "démographie"])),
            ("rss", "Banque de France", "https://publications.banque-france.fr/rss.xml", "institutionnel", json.dumps(["finance", "économie", "monétaire"])),
            ("rss", "Ministère de l'Économie", "https://www.economie.gouv.fr/rss.xml", "institutionnel", json.dumps(["économie", "politique", "réglementation"])),
        ]
        
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                for source in default_sources:
                    cursor.execute('''
                    INSERT INTO veille_sources (source_type, name, url, category, tags)
                    VALUES (?, ?, ?, ?, ?)
                    ''', source)
                
                conn.commit()
                self.logger.info(f"Ajout de {len(default_sources)} sources de veille par défaut")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'ajout des sources par défaut: {e}")
    
    def _load_followed_themes(self) -> List[Dict[str, Any]]:
        """Charge les thèmes suivis depuis la base de données."""
        themes = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM themes')
                rows = cursor.fetchall()
                
                for row in rows:
                    theme = dict(row)
                    # Convertir keywords en liste si présent
                    if theme.get('keywords'):
                        theme['keywords'] = json.loads(theme['keywords'])
                    themes.append(theme)
                
                # Si aucun thème n'est défini, ajouter des thèmes par défaut
                if not themes:
                    # Les thèmes par défaut seront ajoutés lors de la création d'un utilisateur
                    pass
            
            self.logger.info(f"Chargement de {len(themes)} thèmes suivis")
        except Exception as e:
            self.logger.error(f"Erreur lors du chargement des thèmes: {e}")
        
        return themes
    
    def on_start(self) -> None:
        """Actions à effectuer lors du démarrage de l'agent."""
        self.broadcast_message("agent_online", {
            "agent_type": "cours",
            "capabilities": self.capabilities
        })
        
        self.send_command("orchestrator", "status_update", {
            "status": "ready",
            "capabilities": self.capabilities
        })
        
        # Démarrer le thread de veille
        self.running = True
        self.veille_thread = threading.Thread(target=self._veille_loop, daemon=True)
        self.veille_thread.start()
        
        # Configuration de l'écoute Redis
        self.setup_redis_listener()
        
        self.logger.info("Agent Cours démarré")
    
    def on_stop(self) -> None:
        """Actions à effectuer lors de l'arrêt de l'agent."""
        self.running = False
        if self.veille_thread:
            self.veille_thread.join(timeout=2)
        
        # Arrêter l'écoute Redis
        if hasattr(self, 'redis_pubsub'):
            self.redis_pubsub.unsubscribe()
        
        self.broadcast_message("agent_offline", {
            "agent_type": "cours",
            "shutdown_time": time.time()
        })
        
        self.logger.info("Agent Cours arrêté")
    
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
        
        elif msg_type == 'veille_request':
            # Demande spécifique de veille sur un thème
            user_id = data.get('user_id')
            theme = data.get('theme')
            
            if user_id:
                results = self.get_veille_by_theme(theme) if theme else self.get_recent_veille()
                self.send_redis_message(f"orchestrator:notifications", 
                                      'veille_results', 
                                      {'user_id': user_id, 'theme': theme, 'results': results})
        
        elif msg_type == 'generate_report_request':
            # Demande de génération d'un rapport de veille
            user_id = data.get('user_id')
            theme = data.get('theme')
            format = data.get('format', 'pdf')
            
            if user_id:
                report = self.generate_veille_report(user_id, theme, format)
                self.send_redis_message(f"orchestrator:notifications", 
                                      'report_generated', 
                                      {'user_id': user_id, 'report': report})
        
        elif msg_type == 'create_course_request':
            # Demande d'aide à la création d'un cours
            user_id = data.get('user_id')
            course_data = data.get('course_data', {})
            
            if user_id and course_data:
                course_assistance = self.assist_course_creation(user_id, course_data)
                self.send_redis_message(f"orchestrator:notifications", 
                                      'course_assistance', 
                                      {'user_id': user_id, 'assistance': course_assistance})
        
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
    
    def _veille_loop(self) -> None:
        """Boucle principale pour la veille pédagogique."""
        while self.running:
            current_time = time.time()
            
            # Vérifier les nouvelles actualités selon l'intervalle défini
            if current_time - self.last_veille_check >= self.veille_check_interval:
                self.last_veille_check = current_time
                self.perform_veille()
                
                # Traiter les notifications en attente
                self._process_pending_notifications()
            
            # Petite pause pour éviter de surcharger le CPU
            time.sleep(10)
    
    def perform_veille(self) -> None:
        """Effectue une veille complète sur toutes les sources configurées."""
        self.logger.info("Début de la veille pédagogique...")
        
        try:
            for source in self.veille_sources:
                source_type = source.get('source_type')
                source_id = source.get('id')
                source_url = source.get('url')
                
                # Vérifier si cette source doit être mise à jour maintenant
                refresh_interval = source.get('refresh_interval', self.veille_check_interval)
                
                if source_type == 'rss':
                    self._process_rss_feed(source_id, source_url)
                elif source_type == 'website':
                    self._process_website(source_id, source_url)
                # Ajouter d'autres types de sources au besoin
                
                # Petite pause entre les sources pour éviter les limitations d'API
                time.sleep(1)
            
            # Analyser la pertinence des nouvelles actualités
            self._analyze_articles_relevance()
            
            self.logger.info("Veille pédagogique terminée")
        except Exception as e:
            self.logger.error(f"Erreur lors de la veille pédagogique: {e}")
    
    def _process_rss_feed(self, source_id: int, feed_url: str) -> None:
        """Traite un flux RSS pour extraire les actualités."""
        try:
            feed = feedparser.parse(feed_url)
            
            # Parcourir les entrées du flux
            for entry in feed.entries[:20]:  # Limiter aux 20 entrées les plus récentes
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
                
                # Créer un résumé court
                summary = self._create_summary(content)
                
                # Vérifier si cette actualité existe déjà
                with self._get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT id FROM actu_articles WHERE item_hash = ?', (item_hash,))
                    
                    if not cursor.fetchone():
                        # Ajouter la nouvelle actualité
                        cursor.execute('''
                        INSERT INTO actu_articles 
                        (source_id, title, content, summary, url, published_at, item_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (source_id, title, content, summary, link, published_date, item_hash))
                        
                        conn.commit()
            
            self.logger.info(f"Traitement du flux RSS {feed_url} terminé")
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du flux RSS {feed_url}: {e}")
    
    def _process_website(self, source_id: int, website_url: str) -> None:
        """
        Traite un site web pour extraire les actualités (méthode simple de scraping).
        Note: Utilisez cette méthode avec précaution et respectez les conditions des sites.
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(website_url, headers=headers)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Cette partie doit être adaptée selon la structure du site web
                # Exemple simple pour des articles avec des titres et des liens
                articles = []
                
                # Recherche générique d'articles (à adapter selon les sites)
                article_elements = soup.find_all(['article', 'div'], class_=['article', 'post', 'news-item'])
                
                for article in article_elements[:10]:  # Limiter aux 10 premiers
                    title_element = article.find(['h1', 'h2', 'h3', 'h4', 'a'], class_=['title', 'heading'])
                    link_element = article.find('a', href=True)
                    
                    if title_element and link_element:
                        title = title_element.get_text().strip()
                        link = link_element['href']
                        
                        # Construire l'URL complète si nécessaire
                        if not link.startswith(('http://', 'https://')):
                            from urllib.parse import urljoin
                            link = urljoin(website_url, link)
                        
                        content = ""
                        summary = ""
                        
                        # Extraire du contenu si possible
                        content_element = article.find(['div', 'p'], class_=['content', 'summary', 'excerpt'])
                        if content_element:
                            content = content_element.get_text().strip()
                            summary = content[:200] + "..." if len(content) > 200 else content
                        
                        # Date actuelle comme fallback
                        published_date = datetime.datetime.now()
                        
                        # Essayer de trouver une date de publication
                        date_element = article.find(['time', 'span', 'div'], class_=['date', 'published', 'time'])
                        if date_element and date_element.get('datetime'):
                            try:
                                published_date = datetime.datetime.fromisoformat(date_element['datetime'].replace('Z', '+00:00'))
                            except:
                                pass
                        
                        # Créer un hash unique
                        item_hash = hashlib.md5((title + link).encode()).hexdigest()
                        
                        # Vérifier si cette actualité existe déjà
                        with self._get_db_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute('SELECT id FROM actu_articles WHERE item_hash = ?', (item_hash,))
                            
                            if not cursor.fetchone():
                                # Ajouter la nouvelle actualité
                                cursor.execute('''
                                INSERT INTO actu_articles 
                                (source_id, title, content, summary, url, published_at, item_hash)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                ''', (source_id, title, content, summary, link, published_date, item_hash))
                                
                                conn.commit()
                
                self.logger.info(f"Traitement du site web {website_url} terminé")
            else:
                self.logger.warning(f"Erreur {response.status_code} lors de l'accès au site {website_url}")
        
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du site web {website_url}: {e}")
    
    def _create_summary(self, content: str, max_length: int = 200) -> str:
        """
        Crée un résumé court du contenu.
        
        Args:
            content: Contenu à résumer
            max_length: Longueur maximale du résumé
            
        Returns:
            Résumé du contenu
        """
        # Convertir du HTML en texte si nécessaire
        if '<' in content and '>' in content:
            h = html2text.HTML2Text()
            h.ignore_links = True
            h.ignore_images = True
            content = h.handle(content)
        
        # Nettoyer et formater le texte
        content = re.sub(r'\s+', ' ', content).strip()
        
        # Créer un résumé simple
        if len(content) <= max_length:
            return content
        
        # Trouver la dernière phrase complète dans la limite du max_length
        summary = content[:max_length]
        last_sentence_end = max(summary.rfind('.'), summary.rfind('!'), summary.rfind('?'))
        
        if last_sentence_end > 0:
            summary = summary[:last_sentence_end + 1]
        else:
            # Si pas de fin de phrase, on coupe au dernier mot complet
            last_space = summary.rfind(' ')
            if last_space > 0:
                summary = summary[:last_space] + '...'
            else:
                summary += '...'
        
        return summary
    
    def _analyze_articles_relevance(self) -> None:
        """Analyse la pertinence des articles par rapport aux thèmes suivis."""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Récupérer les articles non traités
                cursor.execute('''
                SELECT id, title, content, summary 
                FROM actu_articles 
                WHERE relevance_score = 0.0
                ''')
                
                articles = cursor.fetchall()
                
                for article in articles:
                    article_id = article['id']
                    title = article['title']
                    content = article['content']
                    summary = article['summary']
                    
                    # Analyser la pertinence pour chaque thème
                    relevant_themes = []
                    highest_score = 0.0
                    
                    for theme in self.followed_themes:
                        theme_id = theme['id']
                        theme_name = theme['name']
                        keywords = theme.get('keywords', [])
                        
                        # Calculer un score de pertinence
                        score = self._calculate_theme_relevance(title, content, theme_name, keywords)
                        
                        if score > 0.3:  # Seuil arbitraire de pertinence
                            relevant_themes.append(theme_id)
                            highest_score = max(highest_score, score)
                    
                    # Mettre à jour l'article avec les thèmes pertinents
                    cursor.execute('''
                    UPDATE actu_articles
                    SET themes = ?, relevance_score = ?
                    WHERE id = ?
                    ''', (json.dumps(relevant_themes), highest_score, article_id))
                    
                    # Si l'article est très pertinent, préparer une notification
                    if highest_score > 0.7:  # Seuil de notification
                        # Récupérer le nom de la source
                        cursor.execute('''
                        SELECT vs.name 
                        FROM veille_sources vs
                        JOIN actu_articles aa ON vs.id = aa.source_id
                        WHERE aa.id = ?
                        ''', (article_id,))
                        
                        source = cursor.fetchone()
                        source_name = source['name'] if source else "Source inconnue"
                        
                        # Ajouter à la liste des notifications en attente
                        self.pending_notifications.append({
                            'article_id': article_id,
                            'title': title,
                            'summary': summary,
                            'source': source_name,
                            'relevance': highest_score,
                            'themes': relevant_themes
                        })
                
                conn.commit()
            
            self.logger.info(f"Analyse de pertinence terminée pour {len(articles)} articles")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'analyse de pertinence: {e}")
    
    def _calculate_theme_relevance(self, title: str, content: str, theme_name: str, 
                                  keywords: List[str]) -> float:
        """
        Calcule la pertinence d'un article pour un thème spécifique.
        
        Args:
            title: Titre de l'article
            content: Contenu de l'article
            theme_name: Nom du thème
            keywords: Mots-clés associés au thème
            
        Returns:
            Score de pertinence entre 0 et 1
        """
        # Normaliser le texte
        text = (title + " " + content).lower()
        
        # Score initial
        score = 0.0
        
        # Vérifier si le nom du thème est présent
        if theme_name.lower() in text:
            score += 0.3
        
        # Vérifier les mots-clés
        keyword_matches = 0
        for keyword in keywords:
            if keyword.lower() in text:
                keyword_matches += 1
        
        # Calculer un score basé sur le nombre de mots-clés trouvés
        if keywords:
            score += 0.7 * (keyword_matches / len(keywords))
        
        # Calculer un score de proximité
        # (des mots-clés proches les uns des autres sont plus significatifs)
        if keyword_matches > 1:
            # Logique simplifiée - une implémentation plus avancée 
            # analyserait la distance entre les mots-clés
            score += 0.1
        
        # Donner plus de poids aux mots-clés présents dans le titre
        title_keywords = sum(1 for keyword in keywords if keyword.lower() in title.lower())
        if title_keywords > 0:
            score += 0.2 * (title_keywords / len(keywords) if keywords else 0)
        
        # Limiter le score à 1.0
        return min(score, 1.0)
    
    def _process_pending_notifications(self) -> None:
        """Traite les notifications en attente pour les envoyer aux utilisateurs."""
        if not self.pending_notifications:
            return
        
        try:
            # Récupérer les utilisateurs
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, name FROM users')
                users = cursor.fetchall()
            
            for user in users:
                user_id = user['id']
                user_name = user['name']
                
                # Filtrer les notifications pertinentes pour cet utilisateur
                user_notifications = []
                for notification in self.pending_notifications:
                    # Vérifier si l'utilisateur suit les thèmes de l'article
                    article_themes = notification.get('themes', [])
                    for theme_id in article_themes:
                        # Si l'utilisateur suit au moins un thème pertinent
                        if any(theme['id'] == theme_id and theme['user_id'] == user_id 
                             for theme in self.followed_themes):
                            user_notifications.append(notification)
                            break
                
                # Limiter à 3 notifications à la fois pour ne pas surcharger
                for notification in user_notifications[:3]:
                    article_id = notification['article_id']
                    title = notification['title']
                    source = notification['source']
                    
                    # Créer un message personnalisé
                    message = self._create_article_notification(user_name, title, source, notification['summary'])
                    
                    # Envoyer la notification via Redis
                    self.send_redis_message("orchestrator:notifications", 
                                          'actu_notification', 
                                          {'user_id': user_id, 'message': message, 'article_id': article_id})
                    
                    # Marquer comme envoyé
                    with self._get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                        UPDATE actu_articles
                        SET notification_sent = 1
                        WHERE id = ?
                        ''', (article_id,))
                        
                        conn.commit()
            
            # Vider la liste des notifications en attente
            self.pending_notifications = []
        
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement des notifications: {e}")
    
    def _create_article_notification(self, user_name: str, title: str, 
                                   source: str, summary: str) -> str:
        """
        Crée un message de notification personnalisé pour un article.
        
        Args:
            user_name: Nom de l'utilisateur
            title: Titre de l'article
            source: Nom de la source
            summary: Résumé de l'article
            
        Returns:
            Message formaté
        """
        templates = [
            f"Monsieur, un nouvel article important a été publié : \"{title}\" ({source}). Souhaitez-vous en savoir plus ?",
            f"Une actualité pertinente pour vos cours vient d'être publiée par {source} : \"{title}\". Voulez-vous que je vous la résume ?",
            f"Monsieur, j'ai trouvé un article qui pourrait être utile pour vos cours : \"{title}\". Voici un bref résumé : {summary}"
        ]
        
        return random.choice(templates)
    
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
        
        if cmd_type in ["get_veille", "get_veille_cours"]:
            theme = data.get("theme")
            limit = data.get("limit", 10)
            
            results = self.get_veille_by_theme(theme, limit) if theme else self.get_recent_veille(limit)
            return {"success": True, "results": results}
        
        elif cmd_type in ["generate_report", "generate_report_cours"]:
            user_id = data.get("user_id")
            theme = data.get("theme")
            format = data.get("format", "pdf")
            
            if not user_id:
                return {"success": False, "error": "ID utilisateur requis"}
            
            report = self.generate_veille_report(user_id, theme, format)
            return {"success": True, "report": report}
        
        elif cmd_type in ["assist_course", "assist_course_cours"]:
            user_id = data.get("user_id")
            course_data = data.get("course_data", {})
            
            if not user_id or not course_data:
                return {"success": False, "error": "Paramètres incomplets"}
            
            assistance = self.assist_course_creation(user_id, course_data)
            return {"success": True, "assistance": assistance}
        
        elif cmd_type in ["add_theme", "add_theme_cours"]:
            user_id = data.get("user_id")
            theme_data = data.get("theme_data", {})
            
            if not user_id or not theme_data:
                return {"success": False, "error": "Paramètres incomplets"}
            
            return self.add_theme(user_id, theme_data)
        
        elif cmd_type in ["add_resource", "add_resource_cours"]:
            user_id = data.get("user_id")
            resource_data = data.get("resource_data", {})
            
            if not user_id or not resource_data:
                return {"success": False, "error": "Paramètres incomplets"}
            
            return self.add_resource(user_id, resource_data)
        
        elif cmd_type in ["create_user", "create_user_cours"]:
            name = data.get("name")
            preferences = data.get("preferences", {})
            
            if not name:
                return {"success": False, "error": "Nom d'utilisateur requis"}
            
            return self.create_user(name, preferences)
        
        elif cmd_type in ["get_resources", "get_resources_cours"]:
            user_id = data.get("user_id")
            theme_id = data.get("theme_id")
            
            if not user_id:
                return {"success": False, "error": "ID utilisateur requis"}
            
            resources = self.get_resources(user_id, theme_id)
            return {"success": True, "resources": resources}
        
        elif cmd_type in ["get_themes", "get_themes_cours"]:
            user_id = data.get("user_id")
            
            if not user_id:
                return {"success": False, "error": "ID utilisateur requis"}
            
            themes = self.get_themes(user_id)
            return {"success": True, "themes": themes}
        
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
    
    def get_veille_by_theme(self, theme: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Récupère les actualités de veille par thème.
        
        Args:
            theme: Thème recherché (facultatif)
            limit: Nombre maximal de résultats
            
        Returns:
            Liste des actualités correspondantes
        """
        results = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                if theme:
                    # Trouver l'ID du thème correspondant
                    cursor.execute('SELECT id FROM themes WHERE name LIKE ?', (f'%{theme}%',))
                    theme_ids = [row['id'] for row in cursor.fetchall()]
                    
                    if theme_ids:
                        # Construire une condition pour filtrer par thèmes
                        theme_conditions = []
                        for theme_id in theme_ids:
                            theme_conditions.append(f"json_array_contains(themes, '{theme_id}')")
                        
                        theme_filter = " OR ".join(theme_conditions)
                        
                        # Rechercher les articles correspondant aux thèmes
                        cursor.execute(f'''
                        SELECT aa.id, aa.title, aa.summary, aa.url, aa.published_at, 
                               vs.name as source_name, vs.category
                        FROM actu_articles aa
                        JOIN veille_sources vs ON aa.source_id = vs.id
                        WHERE {theme_filter}
                        ORDER BY aa.published_at DESC
                        LIMIT ?
                        ''', (limit,))
                    else:
                        # Recherche par mots-clés dans le titre et le contenu
                        cursor.execute('''
                        SELECT aa.id, aa.title, aa.summary, aa.url, aa.published_at,
                               vs.name as source_name, vs.category
                        FROM actu_articles aa
                        JOIN veille_sources vs ON aa.source_id = vs.id
                        WHERE aa.title LIKE ? OR aa.content LIKE ?
                        ORDER BY aa.published_at DESC
                        LIMIT ?
                        ''', (f'%{theme}%', f'%{theme}%', limit))
                else:
                    # Récupérer les articles récents avec le meilleur score de pertinence
                    cursor.execute('''
                    SELECT aa.id, aa.title, aa.summary, aa.url, aa.published_at,
                           vs.name as source_name, vs.category
                    FROM actu_articles aa
                    JOIN veille_sources vs ON aa.source_id = vs.id
                    ORDER BY aa.relevance_score DESC, aa.published_at DESC
                    LIMIT ?
                    ''', (limit,))
                
                articles = cursor.fetchall()
                
                for article in articles:
                    results.append({
                        "id": article['id'],
                        "title": article['title'],
                        "summary": article['summary'],
                        "url": article['url'],
                        "source": article['source_name'],
                        "category": article['category'],
                        "published_at": article['published_at']
                    })
            
            self.logger.info(f"Récupération de {len(results)} articles de veille pour le thème '{theme}'")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des articles de veille: {e}")
        
        return results
    
    def generate_veille_report(self, user_id: str, theme: Optional[str] = None, 
                             format: str = "pdf") -> Dict[str, Any]:
        """
        Génère un rapport de veille.
        
        Args:
            user_id: ID de l'utilisateur
            theme: Thème du rapport (facultatif)
            format: Format du rapport (pdf, markdown, etc.)
            
        Returns:
            Informations sur le rapport généré
        """
        # Récupérer les articles pertinents
        articles = self.get_veille_by_theme(theme, limit=20) if theme else self.get_recent_veille(limit=20)
        
        if not articles:
            return {"success": False, "error": "Aucun article trouvé pour générer le rapport"}
        
        # Créer un titre pour le rapport
        report_title = f"Veille pédagogique"
        if theme:
            report_title += f" sur {theme}"
        report_title += f" du {datetime.datetime.now().strftime('%d/%m/%Y')}"
        
        # Chemin du fichier de rapport
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"veille_{timestamp}"
        
        try:
            # Générer le rapport selon le format demandé
            report_path = None
            
            if format.lower() == "pdf" and REPORTLAB_AVAILABLE:
                report_path = self._generate_pdf_report(report_title, articles, theme)
            elif format.lower() == "markdown":
                report_path = self._generate_markdown_report(report_title, articles, theme)
            else:
                # Fallback au markdown si le format demandé n'est pas disponible
                format = "markdown"
                report_path = self._generate_markdown_report(report_title, articles, theme)
            
            # Enregistrer le rapport dans la base de données
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Récupérer les IDs des articles inclus
                article_ids = [article['id'] for article in articles]
                
                # Récupérer les IDs des thèmes concernés
                theme_ids = []
                if theme:
                    cursor.execute('SELECT id FROM themes WHERE name LIKE ?', (f'%{theme}%',))
                    theme_ids = [row['id'] for row in cursor.fetchall()]
                
                cursor.execute('''
                INSERT INTO veille_rapports (user_id, title, description, file_path, format, articles, themes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id, 
                    report_title, 
                    f"Rapport de veille{' sur ' + theme if theme else ''}", 
                    report_path, 
                    format,
                    json.dumps(article_ids),
                    json.dumps(theme_ids)
                ))
                
                report_id = cursor.lastrowid
                conn.commit()
            
            self.logger.info(f"Rapport de veille généré avec succès: {report_path}")
            
            return {
                "success": True,
                "report_id": report_id,
                "title": report_title,
                "file_path": report_path,
                "format": format,
                "article_count": len(articles)
            }
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la génération du rapport de veille: {e}")
            return {"success": False, "error": str(e)}
    
    def _generate_pdf_report(self, title: str, articles: List[Dict[str, Any]], 
                           theme: Optional[str] = None) -> str:
        """
        Génère un rapport de veille au format PDF.
        
        Args:
            title: Titre du rapport
            articles: Liste des articles à inclure
            theme: Thème du rapport (facultatif)
            
        Returns:
            Chemin vers le fichier PDF généré
        """
        # Créer un nom de fichier unique
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"veille_{timestamp}.pdf"
        
        # Créer le chemin du fichier
        report_dir = os.path.join(os.getcwd(), "reports")
        os.makedirs(report_dir, exist_ok=True)
        file_path = os.path.join(report_dir, filename)
        
        # Créer le document PDF
        doc = SimpleDocTemplate(file_path, pagesize=A4)
        styles = getSampleStyleSheet()
        
        # Ajouter des styles personnalisés
        styles.add(ParagraphStyle(name='Title', 
                                 parent=styles['Heading1'], 
                                 fontSize=18, 
                                 alignment=1))  # 1 = center
        
        styles.add(ParagraphStyle(name='ArticleTitle', 
                                 parent=styles['Heading2'], 
                                 fontSize=14))
        
        styles.add(ParagraphStyle(name='ArticleSource', 
                                 parent=styles['Normal'], 
                                 fontSize=10, 
                                 textColor=colors.gray))
        
        # Éléments du document
        elements = []
        
        # Titre du rapport
        elements.append(Paragraph(title, styles['Title']))
        elements.append(Spacer(1, 12))
        
        # Introduction
        intro_text = "Ce rapport présente une synthèse des actualités récentes"
        if theme:
            intro_text += f" sur le thème \"{theme}\""
        intro_text += "."
        
        elements.append(Paragraph(intro_text, styles['Normal']))
        elements.append(Spacer(1, 12))
        
        # Sommaire
        elements.append(Paragraph("Sommaire :", styles['Heading3']))
        for i, article in enumerate(articles, 1):
            elements.append(Paragraph(f"{i}. {article['title']}", styles['BodyText']))
        
        elements.append(Paragraph("\n\n", styles['Normal']))
        elements.append(Spacer(1, 12))
        
        # Contenu principal avec les articles
        elements.append(Paragraph("Articles :", styles['Heading3']))
        elements.append(Spacer(1, 6))
        
        # Grouper les articles par catégorie
        articles_by_category = {}
        for article in articles:
            category = article.get('category', 'Divers')
            if category not in articles_by_category:
                articles_by_category[category] = []
            articles_by_category[category].append(article)
        
        # Ajouter les articles par catégorie
        for category, category_articles in articles_by_category.items():
            elements.append(Paragraph(category.capitalize(), styles['Heading2']))
            elements.append(Spacer(1, 6))
            
            for article in category_articles:
                elements.append(Paragraph(article['title'], styles['ArticleTitle']))
                elements.append(Paragraph(f"Source: {article['source']} - {self._format_date(article.get('published_at', ''))}", 
                                        styles['ArticleSource']))
                elements.append(Spacer(1, 6))
                
                if article.get('summary'):
                    elements.append(Paragraph(article['summary'], styles['Normal']))
                
                if article.get('url'):
                    elements.append(Paragraph(f"Lien: {article['url']}", styles['BodyText']))
                
                elements.append(Spacer(1, 12))
        
        # Construire le document
        doc.build(elements)
        
        return file_path
    
    def _generate_markdown_report(self, title: str, articles: List[Dict[str, Any]], 
                                theme: Optional[str] = None) -> str:
        """
        Génère un rapport de veille au format Markdown.
        
        Args:
            title
    
    def get_recent_veille(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Récupère les actualités de veille les plus récentes.
        
        Args:
            limit: Nombre maximal de résultats
            
        Returns:
            Liste des actualités récentes
        """
        results = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT aa.id, aa.title, aa.summary, aa.url, aa.published_at,
                       vs.name as source_name, vs.category
                FROM actu_articles aa
                JOIN veille_sources vs ON aa.source_id = vs.id
                ORDER BY aa.published_at DESC
                LIMIT ?
                ''', (limit,))
                
                articles = cursor.fetchall()
                
                for article in articles:
                    results.append({
                        "id": article['id'],
                        "title": article['title'],
                        "summary": article['summary'],
                        "url": article['url'],
                        "source": article['source_name'],
                        "category": article['category'],
                        "published_at": article['published_at']
                    })
            
            self.logger.info(f"Récupération de {len(results)} articles de veille récents")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des articles de veille récents: {e}")
        
        return results