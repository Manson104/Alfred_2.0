# Guide d'installation du système de logging pour Alfred

Ce guide vous explique comment mettre en place et intégrer le système de journalisation (logging) dans votre projet Alfred.

## 1. Structure des dossiers

Voici la structure de dossiers à mettre en place :

```
alfred/
├── core/
│   ├── alfred_core.py (modifié)
├── providers/
│   ├── provider_base.py
│   ├── provider_anthropic.py
│   ├── provider_openai.py
│   ├── provider_perplexity.py
│   └── provider_perplexity_hub.py
├── ai/
│   ├── ai_router.py (modifié)
│   ├── context_manager.py
│   └── provider_factory.py
├── agents/
│   ├── interaction/
│   └── learning/
├── utils/
│   ├── __init__.py
│   └── logger.py (nouveau)
├── main.py (modifié)
└── config.json (modifié)
```

## 2. Étapes d'installation

### Étape 1 : Créer le dossier utils

```bash
mkdir -p alfred/utils
touch alfred/utils/__init__.py
```

### Étape 2 : Ajouter le fichier logger.py

Copiez le contenu du fichier `logger.py` que nous avons généré dans le dossier `utils`.

### Étape 3 : Mettre à jour alfred_core.py

Mettez à jour le fichier `alfred_core.py` avec la version modifiée qui inclut l'intégration du système de logging.

### Étape 4 : Mettre à jour config.json

Mettez à jour votre fichier `config.json` pour inclure la section `logging` comme dans la version modifiée.

### Étape 5 : Mettre à jour main.py

Mettez à jour le fichier `main.py` pour utiliser le nouveau système de logging.

## 3. Utilisation du système de logging

### Dans vos modules

Pour utiliser le système de logging dans un module, importez-le comme ceci :

```python
from utils.logger import get_logger

# Créer un logger pour votre module
logger = get_logger("nom_du_module")

# Utiliser le logger
logger.debug("Message de débogage")
logger.info("Message d'information")
logger.warning("Avertissement")
logger.error("Erreur")
logger.critical("Erreur critique")
```

### Mesurer les performances

Vous pouvez utiliser le décorateur `log_execution_time` pour mesurer le temps d'exécution des fonctions :

```python
from utils.logger import get_logger, log_execution_time

logger = get_logger("mon_module")

@log_execution_time
def ma_fonction():
    # Code de la fonction
    pass
```

### Configuration des niveaux de log

Vous pouvez configurer les niveaux de log par module dans le fichier `config.json` :

```json
"logging": {
  "log_level": "INFO",
  "module_levels": {
    "ai.AIRouter": "DEBUG",
    "providers": "INFO"
  }
}
```

Ou dynamiquement dans le code :

```python
from utils.logger import initialize

logger_system = initialize()
logger_system.set_module_level("ai.AIRouter", "DEBUG")
```

## 4. Logs disponibles

Le système créera les fichiers de log suivants :

- `~/.alfred/logs/alfred.log` : Log général de l'application
- `~/.alfred/logs/errors.log` : Uniquement les erreurs (niveau ERROR et plus)

Vous pouvez également créer des logs spécifiques à certains modules :

```python
from utils.logger import initialize

logger_system = initialize()
logger_system.add_module_file_handler("ai.AIRouter")
```

Ce qui créera un fichier `~/.alfred/logs/ai.AIRouter.log`.

## 5. Commandes CLI pour la gestion des logs

Le CLI d'Alfred a été mis à jour avec une nouvelle commande pour gérer les logs :

```
log <level>   - Change the global logging level (DEBUG, INFO, WARNING, ERROR)
```

Par exemple :
```
alfred> log DEBUG
```

## 6. Logs de performance

Les logs de performance seront disponibles dans la console et dans les fichiers de log avec le préfixe "perf." :

```
2025-03-17 10:15:30 | INFO     | perf.ai.AIRouter    | route_query exécuté en 0.1234 secondes
```

Ces logs vous aideront à identifier les goulots d'étranglement dans votre application.

## 7. Bonnes pratiques de logging

Voici quelques bonnes pratiques à suivre pour utiliser efficacement le système de logging :

### Niveaux de log appropriés

- **DEBUG** : Informations détaillées utiles pour le débogage
- **INFO** : Confirmation que les choses fonctionnent comme prévu
- **WARNING** : Indication que quelque chose d'inattendu s'est produit, mais l'application fonctionne encore
- **ERROR** : Une erreur s'est produite et une fonctionnalité n'a pas pu être exécutée
- **CRITICAL** : Une erreur grave qui peut empêcher l'application de continuer à fonctionner

### Format des messages

- Soyez clair et concis
- Incluez des informations contextelles importantes (IDs, noms, etc.)
- Pour les erreurs, incluez suffisamment d'informations pour comprendre et résoudre le problème

Exemple :
```python
logger.info(f"Module {module_id} chargé avec succès")
logger.error(f"Échec du chargement du module {module_id}: {str(e)}", exc_info=True)
```

### Utilisation de exc_info

Pour les erreurs, il est souvent utile d'inclure le traceback complet :

```python
try:
    # Code pouvant lever une exception
except Exception as e:
    logger.error(f"Message d'erreur: {str(e)}", exc_info=True)
```

## 8. Rotation et nettoyage des logs

Le système gère automatiquement la rotation des fichiers de log :

- Chaque fichier de log est limité à 10 Mo par défaut
- 5 fichiers de backup sont conservés par défaut
- Les noms des fichiers de backup suivent le format `alfred.log.1`, `alfred.log.2`, etc.

Vous pouvez configurer ces paramètres dans `config.json` :

```json
"logging": {
  "max_file_size": 5242880,  // 5 Mo
  "backup_count": 3
}
```

## 9. Visualisation des logs

Pour une meilleure visualisation des logs, vous pouvez utiliser des outils comme :

- **tail** : `tail -f ~/.alfred/logs/alfred.log` pour suivre les logs en temps réel
- **grep** : `grep ERROR ~/.alfred/logs/alfred.log` pour filtrer les erreurs
- **less** : `less ~/.alfred/logs/alfred.log` pour parcourir les logs

Pour une expérience plus riche, des outils comme Lnav (https://lnav.org/) offrent une interface conviviale pour explorer les fichiers de log.

## 10. Dépannage du système de logging

Si vous rencontrez des problèmes avec le système de logging :

1. Vérifiez que le dossier de logs existe et est accessible en écriture
2. Assurez-vous que la configuration dans `config.json` est correcte
3. Si les logs n'apparaissent pas, vérifiez le niveau de log configuré

Si les logs ne sont toujours pas générés, vous pouvez forcer un log de débogage au démarrage :

```python
# Dans main.py, avant l'initialisation du système de logging
import logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   handlers=[logging.StreamHandler()])
```

## Conclusion

Ce système de logging vous offre une visibilité complète sur le fonctionnement de votre application Alfred. Utilisez-le pour améliorer la qualité de votre code, identifier les problèmes rapidement et optimiser les performances.

Pour toute question ou besoin d'assistance, n'hésitez pas à demander de l'aide !
