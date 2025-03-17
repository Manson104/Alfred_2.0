"""
alfred_agents.py
----------------
Registre des agents du projet Alfred.
Intègre l'agent Cours, l'agent SmartHome (domotique classique) et l'AdvancedSmartHomeAgent.
"""

from agent_cours import CoursAgent
from smart_home_agent import SmartHomeAgent  # si présent
from advanced_home_agent import AdvancedSmartHomeAgent
from agents.alfred_interaction_agent import InteractionAgent, InteractionMode
from agents.alfred_interaction_agent import InteractionAgent, InteractionMode
from agents.alfred_learning_agent import LearningAgent, LearningMode

def register_agents():
    agents = {}
    agents["interaction"] = InteractionAgent(default_mode=InteractionMode.MAJORDOME)
    # Initialisation de l'agent d'apprentissage avec le répertoire de données
    agents["learning"] = LearningAgent(data_dir="data", learning_mode=LearningMode.ACTIVE)
    # Démarrer les agents si nécessaire
    agents["interaction"].start_task_manager()
    # Agent Cours
    cours_agent = CoursAgent()
    agents.append(cours_agent)
    # Agent SmartHome classique (si tu souhaites le conserver)
    smart_home_agent = SmartHomeAgent("your_openweathermap_api_key", "Guainville")
    agents.append(smart_home_agent)
    # Agent Interaction
    agents["interaction"] = InteractionAgent(default_mode=InteractionMode.MAJORDOME)
    # Agent domotique avancé
    advanced_agent = AdvancedSmartHomeAgent({
        'primary': 'clé_api_weatherapi',
        'secondary': 'clé_api_openweathermap'
    }, "Guainville")
    agents.append(advanced_agent)
    return agents

if __name__ == "__main__":
    agents = register_agents()
    for agent in agents:
        print(f"Agent enregistré : {agent.__class__.__name__}")
