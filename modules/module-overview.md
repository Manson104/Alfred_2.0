# Architecture Modulaire d'Alfred

## Problèmes identifiés
- **Redondance de code**: Plusieurs agents réimplémentent les mêmes fonctionnalités
- **Couplage fort**: Les agents intègrent à la fois la logique métier et les mécanismes de communication
- **Difficultés de maintenance**: Les modifications doivent être répercutées dans plusieurs fichiers
- **Évolutivité limitée**: Ajout de fonctionnalités complexe du fait de la structure monolithique

## Nouvelle Architecture

### 1. Couche Core
- **Module Bus**: Gestion centralisée des communications (Redis)
- **Module State**: Gestionnaire d'état partagé entre les modules
- **Module Config**: Gestion de la configuration

### 2. Modules vs Agents
- **Modules**: Composants fonctionnels réutilisables (pas d'état, API claire)
- **Agents**: Entités autonomes utilisant les modules (logique, décision)

### 3. Structure de modules proposée

#### Modules Fonctionnels
- **weather**: Services météo (actuellement dans SmartHomeAgent)
- **energy**: Monitoring et optimisation énergétique
- **irrigation**: Gestion de l'arrosage
- **habit**: Analyse des habitudes et patterns
- **nlp**: Traitement du langage naturel
- **translation**: Traduction de textes et documents
- **security**: Monitoring de sécurité
- **command**: Exécution de commandes système
- **notification**: Système de notification

#### Agents (utilisent les modules)
- **SmartHomeAgent**: Utilise les modules weather, energy, irrigation, habit
- **AutomationAgent**: Utilise les modules command, security
- **TranslationAgent**: Utilise le module translation
- **DiscussionAgent**: Utilise les modules nlp, notification
- **DecisionAgent**: Utilise le StateManager central

## Implémentation
Chaque module sera implémenté avec:
- Une interface claire (classe abstraite)
- Des implémentations concrètes
- Une documentation des méthodes et paramètres
- Des tests unitaires

## Avantages
- **Réutilisabilité**: Les modules peuvent être utilisés par différents agents
- **Testabilité**: Modules à responsabilité unique, plus faciles à tester
- **Évolutivité**: Ajout/remplacement de modules sans affecter le reste du système
- **Maintenance**: Corrections localisées aux modules concernés
