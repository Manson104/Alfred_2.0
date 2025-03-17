import os
import json
import feedparser
import requests
from typing import List, Dict, Optional

def load_local_stories(stories_dir: str) -> List[Dict]:
    """
    Charge les histoires stockées localement sous forme de fichiers JSON.
    
    Args:
        stories_dir: Répertoire contenant les fichiers JSON d'histoires.
    
    Returns:
        Liste de dictionnaires contenant les histoires.
    """
    stories = []
    if not os.path.isdir(stories_dir):
        return stories

    for root, _, files in os.walk(stories_dir):
        for file in files:
            if file.lower().endswith(".json"):
                try:
                    with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                        story = json.load(f)
                        stories.append(story)
                except Exception as e:
                    print(f"Erreur lors du chargement du fichier {file}: {e}")
    return stories

def fetch_rss_stories(rss_url: str, max_items: int = 10) -> List[Dict]:
    """
    Récupère des histoires depuis un flux RSS.
    
    Args:
        rss_url: URL du flux RSS.
        max_items: Nombre maximum d’éléments à récupérer.
    
    Returns:
        Liste de dictionnaires contenant des histoires extraites du flux RSS.
    """
    stories = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:max_items]:
            story = {
                "title": entry.get("title", "Titre inconnu"),
                "link": entry.get("link", ""),
                "description": entry.get("description", ""),
                "published": entry.get("published", "")
            }
            stories.append(story)
    except Exception as e:
        print(f"Erreur lors de la récupération du flux RSS: {e}")
    return stories

def get_story_by_keyword(stories: List[Dict], keyword: str) -> Optional[Dict]:
    """
    Recherche dans la liste d'histoires celle qui correspond à un mot-clé.
    
    Args:
        stories: Liste de dictionnaires d'histoires.
        keyword: Mot-clé de recherche.
    
    Returns:
        Un dictionnaire d'histoire si trouvé, sinon None.
    """
    keyword_lower = keyword.lower()
    for story in stories:
        if keyword_lower in story.get("title", "").lower() or keyword_lower in story.get("description", "").lower():
            return story
    return None
