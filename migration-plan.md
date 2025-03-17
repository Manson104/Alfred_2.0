# Plan de migration vers la nouvelle architecture Alfred

Ce document détaille le plan de migration progressif pour passer de l'architecture actuelle à la nouvelle architecture agents/modules.

## Structure cible

```
alfred/
├── core/
│   ├── alfred_core.py
│   └── module_manager.py
├── providers/
│   ├── provider_base.py
│   ├── provider_anthropic.py
│   ├── provider_openai.py
│   ├── provider_perplexity.py
│   └── provider_perplexity_hub.py
├── ai/
│   ├── ai_router.py
│   ├── context_manager.py
│   └── provider_factory.py
├── agents/
│   ├── agent_base.py
│   ├── interaction/
│   │   ├── conversation_agent.py
│   │   └── proactive_agent.py
│   └── learning/
│       ├── preference_agent.py
│       └── feedback_agent.py
├── modules/
│   ├── module_interface.py
│   ├── nlp/
│   │   ├── entity_extraction.py
│   │   └── intent_recognition.py
│   └── knowledge/
│       └── memory_store.py
├── utils/
│   └── logger.py
├── main.py
└── config.json
```

## Phases de migration

### Phase 1: Infrastructure de base (actuelle)
- ✅ Système de logging centralisé
- ✅ Interface de base pour les agents
- ✅ Interface de base pour les modules

### Phase 2: Préparation et réorganisation
1. **Réorganiser les dossiers**
   - Créer les répertoires manquants : `agents`, `modules`
   - Déplacer les fichiers existants dans les bons dossiers

2. **Adapter le gestionnaire de modules**
   - Mettre à jour `module_manager.py` pour gérer les nouveaux types de composants
   - Adapter le système de chargement pour distinguer les agents et les modules

3. **Créer les métadonnées pour les modules GitHub**
   - Créer des fichiers `module.json` pour chaque module avec informations requises
   - Format standardisé pour les métadonnées

### Phase 3: Migration des composants existants
1. **Convertir `context_manager.py` en module**
   - Adapter pour implémenter l'interface `ModuleInterface`
   - Séparer la logique de gestion de contexte des fonctionnalités de messagerie

2. **Convertir les fournisseurs d'IA en modules**
   - Adapter l'interface des fournisseurs d'IA pour les intégrer dans la structure modulaire
   - Maintenir la compatibilité ascendante

3. **Créer l'agent conversationnel**
   - Implémenter l'agent de conversation basé sur `AgentBase`
   - Migrer progressivement les fonctionnalités de gestion de conversation

### Phase 4: Développement itératif
1. **Développer les modules NLP**
   - Module d'extraction d'entités
   - Module de reconnaissance d'intentions
   - Module d'analyse de sentiment

2. **Développer les agents spécialisés**
   - Agent proactif
   - Agent d'apprentissage des préférences
   - Agent de feedback

3. **Intégration et tests**
   - Tester les interactions entre agents et modules
   - Valider le fonctionnement du système global

## Plan d'implémentation détaillé

### Semaine 1: Infrastructure et préparation
- Mettre en place le système de logging ✅
- Définir les interfaces des agents et modules ✅
- Réorganiser la structure de dossiers
- Adapter le gestionnaire de modules

### Semaine 2: Migration des composants de base
- Convertir `context_manager.py` en module
- Adapter les fournisseurs d'IA
- Créer l'agent de conversation basique

### Semaine 3: Développement des modules NLP
- Développer le module d'extraction d'entités ✅
- Développer le module de reconnaissance d'intentions
- Intégrer ces modules à l'agent de conversation

### Semaine 4: Développement des agents spécialisés
- Développer l'agent proactif
- Développer l'agent d'apprentissage des préférences
- Intégrer et tester l'ensemble du système

## Principes directeurs pendant la migration

1. **Compatibilité ascendante**
   - Maintenir la compatibilité avec les composants existants
   - Permettre une migration progressive sans interruption de service

2. **Tests unitaires**
   - Écrire des tests pour chaque nouveau composant
   - S'assurer que les fonctionnalités existantes continuent de fonctionner

3. **Documentation**
   - Documenter clairement les interfaces entre agents et modules
   - Maintenir un guide de contribution pour les nouveaux développeurs

4. **Isolation des responsabilités**
   - Un agent ou module = une responsabilité claire
   - Éviter les dépendances circulaires

## Priorités immédiates

1. **Réorganiser la structure de dossiers**
   ```bash
   mkdir -p alfred/agents/interaction alfred/agents/learning
   mkdir -p alfred/modules/nlp alfred/modules/knowledge
   ```

2. **Déplacer `agent_base.py` dans le dossier agents**
   ```bash
   cp agent_base.py alfred/agents/
   ```

3. **Déplacer `module_interface.py` dans le dossier modules**
   ```bash
   cp module_interface.py alfred/modules/
   ```

4. **Adapter le module manager pour charger les nouveaux types de composants**
   - Modifier `module_manager.py` pour reconnaître les types agents et modules
   - Ajouter un mécanisme de résolution des dépendances entre modules
   - Mettre en place une gestion des métadonnées pour agents et modules

5. **Créer un fichier de configuration standardisé pour les agents et modules**
   - Définir le format des fichiers de métadonnées `module.json` et `agent.json`
   - Créer des exemples pour guider les développeurs