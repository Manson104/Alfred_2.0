"""
Entity Extraction Module - Extraction d'entités à partir de texte

Ce module fournit des fonctionnalités d'extraction d'entités à partir de texte,
comme les dates, lieux, personnes, etc.
"""

import re
import datetime
from typing import Dict, List, Any, Optional, Tuple, Set

from modules.module_interface import ModuleInterface, create_module as base_create_module
from utils.logger import get_logger, log_execution_time

class EntityExtractionModule(ModuleInterface):
    """
    Module d'extraction d'entités à partir de texte
    """
    
    def __init__(self, module_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialise le module d'extraction d'entités
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration spécifique au module
        """
        super().__init__(module_id, config)
        
        # Types d'entités supportés
        self.supported_entities = {
            "date": True,       # Dates et périodes temporelles
            "time": True,       # Heures et durées
            "location": True,   # Lieux (villes, pays, adresses)
            "person": True,     # Noms de personnes
            "organization": True, # Organisations
            "email": True,      # Adresses email
            "phone": True,      # Numéros de téléphone
            "url": True,        # URLs et liens web
            "number": True      # Valeurs numériques
        }
        
        # Règles d'extraction (expressions régulières) pour chaque type d'entité
        self.extraction_rules = {}
        
        # Cache des résultats récents
        self.results_cache = {}
        self.max_cache_size = 100
    
    def initialize(self) -> bool:
        """
        Initialise le module avec sa configuration
        
        Returns:
            True si l'initialisation est réussie, False sinon
        """
        try:
            # Charger la configuration
            if "disabled_entities" in self.config:
                for entity_type in self.config["disabled_entities"]:
                    if entity_type in self.supported_entities:
                        self.supported_entities[entity_type] = False
            
            # Taille du cache
            self.max_cache_size = self.config.get("max_cache_size", self.max_cache_size)
            
            # Initialiser les règles d'extraction
            self._init_extraction_rules()
            
            self.initialized = True
            self.logger.info(f"Module d'extraction d'entités initialisé avec {sum(self.supported_entities.values())} types d'entités activés")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation du module d'extraction d'entités: {str(e)}", exc_info=True)
            return False
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Renvoie les capacités du module
        
        Returns:
            Dictionnaire des capacités
        """
        return {
            "extract_entities": True,
            "supported_entity_types": {k: v for k, v in self.supported_entities.items() if v},
            "uses_regex": True,
            "supports_multilingual": False,  # Pour l'instant, seulement français et anglais
            "supported_languages": ["fr", "en"]
        }
    
    def cleanup(self) -> bool:
        """
        Nettoie les ressources utilisées par le module
        
        Returns:
            True si le nettoyage est réussi, False sinon
        """
        # Vider le cache
        self.results_cache.clear()
        return True
    
    def _init_extraction_rules(self):
        """
        Initialise les règles d'extraction pour chaque type d'entité
        """
        # Règles pour les dates (format français et anglais)
        date_patterns = [
            r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b',  # 01/01/2023, 1-1-23
            r'\b(\d{1,2}) (janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre) (\d{2,4})\b',  # 1 janvier 2023
            r'\b(\d{1,2}) (jan|fév|mar|avr|mai|juin|juil|août|sept|oct|nov|déc)[a-z]* (\d{2,4})\b',  # 1 jan 2023
            r'\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche) (\d{1,2}) (janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\b',  # lundi 1 janvier
            r'\b(\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December) (\d{2,4})\b',  # 1 January 2023
            r'\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{2,4})\b',  # 1 Jan 2023
            r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) (\d{1,2})(st|nd|rd|th) (of )?(January|February|March|April|May|June|July|August|September|October|November|December)\b'  # Monday 1st January
        ]
        self.extraction_rules["date"] = date_patterns
        
        # Règles pour les heures
        time_patterns = [
            r'\b(\d{1,2})[h:](\d{2})(?:[:](\d{2}))?\b',  # 14h30, 14:30, 14:30:45
            r'\b(\d{1,2}) heures(?: (\d{1,2})(?:min(?:utes)?)?)?',  # 14 heures 30, 14 heures
            r'\b(\d{1,2})(am|pm)\b',  # 2pm, 11am
            r'\b(\d{1,2})[.:] ?(\d{2}) ?(am|pm)\b'  # 2:30pm, 11.45am
        ]
        self.extraction_rules["time"] = time_patterns
        
        # Règles pour les emails
        email_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'  # nom@domaine.com
        ]
        self.extraction_rules["email"] = email_patterns
        
        # Règles pour les numéros de téléphone (formats internationaux et français)
        phone_patterns = [
            r'\b(?:\+\d{1,3}[-.\s]?)?(?:\(?\d{1,4}\)?[-.\s]?)?(?:\d{1,4}[-.\s]?){1,4}\d{1,4}\b',  # +33 1 23 45 67 89, (123) 456-7890
            r'\b0\d[-.\s]?\d{2}[-.\s]?\d{2}[-.\s]?\d{2}[-.\s]?\d{2}\b'  # 01 23 45 67 89, 01.23.45.67.89
        ]
        self.extraction_rules["phone"] = phone_patterns
        
        # Règles pour les URLs
        url_patterns = [
            r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.-]*\??[-\w&=.%]*',  # http://example.com, https://example.com/path?query=1
            r'www\.(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.-]*\??[-\w&=.%]*'  # www.example.com, www.example.com/path
        ]
        self.extraction_rules["url"] = url_patterns
        
        # Règles pour les chiffres et nombres
        number_patterns = [
            r'\b\d+(?:[.,]\d+)?(?:\s?[€$%]| euros?| dollars?)\b',  # 123, 123.45, 123,45, 123€, 123 euros
            r'\b\d+(?:[.,]\d+)?\b'  # 123, 123.45, 123,45
        ]
        self.extraction_rules["number"] = number_patterns
    
    @log_execution_time
    def extract_entities(self, text: str, entity_types: Optional[List[str]] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extrait les entités d'un texte
        
        Args:
            text: Le texte à analyser
            entity_types: Liste des types d'entités à extraire (None pour tous les types activés)
            
        Returns:
            Dictionnaire des entités extraites, regroupées par type
        """
        if not self.initialized:
            self.logger.error("Le module n'est pas initialisé")
            return {}
        
        # Vérifier si le résultat est dans le cache
        cache_key = f"{text}_{entity_types}"
        if cache_key in self.results_cache:
            return self.results_cache[cache_key]
        
        # Déterminer les types d'entités à extraire
        if entity_types is None:
            entity_types = [t for t, enabled in self.supported_entities.items() if enabled]
        else:
            # Filtrer les types non supportés ou désactivés
            entity_types = [t for t in entity_types if t in self.supported_entities and self.supported_entities[t]]
        
        if not entity_types:
            return {}
        
        self.logger.debug(f"Extraction d'entités ({', '.join(entity_types)}) à partir de: {text[:50]}...")
        
        # Résultat pour chaque type d'entité
        results = {}
        
        # Extraire les entités de chaque type demandé
        for entity_type in entity_types:
            if entity_type not in self.extraction_rules:
                continue
                
            entities = self._extract_entity_type(text, entity_type)
            if entities:
                results[entity_type] = entities
        
        # Mettre en cache le résultat
        if len(self.results_cache) >= self.max_cache_size:
            # Supprimer une entrée aléatoire si le cache est plein
            self.results_cache.pop(next(iter(self.results_cache)))
        self.results_cache[cache_key] = results
        
        return results
    
    def _extract_entity_type(self, text: str, entity_type: str) -> List[Dict[str, Any]]:
        """
        Extrait les entités d'un type spécifique
        
        Args:
            text: Le texte à analyser
            entity_type: Le type d'entité à extraire
            
        Returns:
            Liste des entités extraites avec leurs propriétés
        """
        entities = []
        
        # Appliquer toutes les règles d'extraction pour ce type
        for pattern in self.extraction_rules.get(entity_type, []):
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entity_text = match.group(0)
                start = match.start()
                end = match.end()
                
                # Normaliser la valeur selon le type d'entité
                normalized = self._normalize_entity(entity_text, entity_type, match)
                
                # Créer l'objet entité
                entity = {
                    "text": entity_text,
                    "type": entity_type,
                    "start": start,
                    "end": end,
                    "normalized": normalized
                }
                
                # Vérifier les doublons
                if not any(e["start"] == start and e["end"] == end for e in entities):
                    entities.append(entity)
        
        return entities
    
    def _normalize_entity(self, entity_text: str, entity_type: str, match) -> Any:
        """
        Normalise une entité extraite selon son type
        
        Args:
            entity_text: Le texte de l'entité
            entity_type: Le type d'entité
            match: L'objet match de l'expression régulière
            
        Returns:
            Valeur normalisée de l'entité
        """
        if entity_type == "date":
            # Tenter de convertir en objet date
            try:
                # Divers formats possibles selon le pattern qui a matché
                if "/" in entity_text or "-" in entity_text:
                    # Format JJ/MM/AAAA ou JJ-MM-AAAA
                    sep = "/" if "/" in entity_text else "-"
                    parts = entity_text.split(sep)
                    if len(parts) == 3:
                        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                        if year < 100:
                            year += 2000 if year < 50 else 1900
                        return datetime.date(year, month, day).isoformat()
                # Autres formats...
                
                # Si aucun format spécifique ne correspond, retourner le texte tel quel
                return entity_text
            except:
                return entity_text
                
        elif entity_type == "time":
            # Tenter de normaliser l'heure
            try:
                if "h" in entity_text:
                    # Format 14h30
                    parts = entity_text.split("h")
                    hour = int(parts[0])
                    minute = int(parts[1]) if parts[1] else 0
                    return f"{hour:02d}:{minute:02d}"
                # Autres formats...
                
                return entity_text
            except:
                return entity_text
                
        elif entity_type == "number":
            # Tenter de convertir en nombre
            try:
                # Remplacer la virgule par un point pour les décimaux
                num_text = entity_text.replace(",", ".")
                # Extraire seulement les chiffres et le point décimal
                num_text = re.sub(r'[^\d.]', '', num_text)
                if "." in num_text:
                    return float(num_text)
                else:
                    return int(num_text)
            except:
                return entity_text
                
        # Pour les autres types, retourner le texte tel quel
        return entity_text
    
    @log_execution_time
    def extract_dates(self, text: str) -> List[Dict[str, Any]]:
        """
        Méthode pratique pour extraire uniquement les dates
        
        Args:
            text: Le texte à analyser
            
        Returns:
            Liste des dates extraites
        """
        result = self.extract_entities(text, ["date"])
        return result.get("date", [])
    
    @log_execution_time
    def extract_contact_info(self, text: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Méthode pratique pour extraire les informations de contact
        
        Args:
            text: Le texte à analyser
            
        Returns:
            Dictionnaire des informations de contact extraites
        """
        return self.extract_entities(text, ["email", "phone", "url"])

# Fonction de création du module appelée par le système
def create_module(module_id: str, config: Optional[Dict[str, Any]] = None) -> EntityExtractionModule:
    """
    Crée une instance du module d'extraction d'entités
    
    Args:
        module_id: Identifiant unique du module
        config: Configuration spécifique au module
        
    Returns:
        Instance configurée du module
    """
    return EntityExtractionModule(module_id, config)


# Pour le test
if __name__ == "__main__":
    # Configuration de test
    test_config = {
        "disabled_entities": ["organization"]
    }
    
    # Créer et initialiser le module
    module = create_module("entity_extraction", test_config)
    module.initialize()
    
    # Texte de test
    test_text = """
    Bonjour, j'ai rendez-vous le 15 mars 2023 à 14h30 avec Jean Dupont. 
    Son email est jean.dupont@example.com et son numéro est le 06 12 34 56 78.
    L'adresse est 123 rue de Paris, et son site web est https://example.com.
    Le montant total est de 127,50 euros.
    """
    
    # Extraire les entités
    entities = module.extract_entities(test_text)
    
    # Afficher les résultats
    for entity_type, entity_list in entities.items():
        print(f"\n{entity_type.upper()}:")
        for entity in entity_list:
            print(f"  - {entity['text']} ({entity['normalized']})")
