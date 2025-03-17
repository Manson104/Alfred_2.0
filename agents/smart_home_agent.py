"""
smart_home_agent.py
-------------------
Agent Domotique - Optimisation Intelligente des Ressources Domestiques.
Ce script implémente un agent qui intègre l’irrigation intelligente,
l’analyse des habitudes domestiques et le suivi énergétique pour optimiser l'environnement.
"""

import datetime
import random
import time
import json
import logging
from collections import defaultdict
from typing import Dict, Optional
import requests

# Importation de BaseAgent.
# Assure-toi que le module base_agent.py existe dans ton projet.
from base_agent import BaseAgent

# Configuration du logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("smart_home_agent.log"), logging.StreamHandler()]
)
logger = logging.getLogger("SmartHomeAgent")

# --------------------------------------------------
# Module d'irrigation intelligente
# --------------------------------------------------
class IrrigationManager:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.moisture_threshold = 30  # Niveau d'humidité optimal en %

    def get_weather_data(self, location: str) -> Optional[dict]:
        url = f"https://api.openweathermap.org/data/2.5/forecast?q={location}&appid={self.api_key}&units=metric"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Erreur météo: {e}")
            return None

    def check_rain_forecast(self, weather_data: dict) -> bool:
        if not weather_data or 'list' not in weather_data:
            return False
        now = datetime.datetime.now()
        for forecast in weather_data['list']:
            forecast_time = datetime.datetime.fromtimestamp(forecast['dt'])
            if (forecast_time - now).total_seconds() <= 86400:  # 24h
                if forecast['weather'][0]['main'].lower() in ['rain', 'drizzle']:
                    return True
        return False

    def irrigation_decision(self, location: str, soil_moisture: float) -> bool:
        weather = self.get_weather_data(location)
        rain_expected = self.check_rain_forecast(weather)
        # Si l'humidité est inférieure au seuil et qu'aucune pluie n'est prévue, on irrigue
        return soil_moisture < self.moisture_threshold and not rain_expected

# --------------------------------------------------
# Module d'analyse des habitudes domestiques
# --------------------------------------------------
class HabitAnalyzer:
    def __init__(self):
        self.activities = defaultdict(list)
        self.patterns = {}

    def log_activity(self, category: str, timestamp: datetime.datetime):
        self.activities[category].append(timestamp)

    def detect_patterns(self, window_size: int = 30) -> Dict[str, Dict]:
        patterns = {}
        for category, timestamps in self.activities.items():
            time_diffs = []
            for i in range(1, len(timestamps)):
                delta = timestamps[i] - timestamps[i-1]
                time_diffs.append(delta.total_seconds() / 3600)  # en heures
            if time_diffs:
                avg_interval = sum(time_diffs) / len(time_diffs)
                patterns[category] = {
                    'frequency': 24 / avg_interval if avg_interval > 0 else 0,
                    'last_occurrence': timestamps[-1],
                    'std_deviation': random.uniform(0.5, 2.0)  # simulation d'écart-type
                }
        self.patterns = patterns
        return patterns

    def predict_next_occurrence(self, category: str) -> Optional[datetime.datetime]:
        if category not in self.patterns:
            return None
        last = self.patterns[category]['last_occurrence']
        avg_interval = 24 / self.patterns[category]['frequency']
        return last + datetime.timedelta(hours=avg_interval)

# --------------------------------------------------
# Module de gestion énergétique optimisée
# --------------------------------------------------
class EnergyOptimizer:
    def __init__(self):
        self.devices = defaultdict(list)
        self.optimization_rules = {
            'heater': {'threshold': 45, 'action': 'adjust_temperature'},
            'lights': {'threshold': 18, 'action': 'dim_lights'}
        }

    def log_consumption(self, device: str, consumption: float):
        self.devices[device].append(consumption)

    def analyze_consumption(self) -> Dict[str, Dict]:
        recommendations = {}
        for device, data in self.devices.items():
            if data:
                avg = sum(data) / len(data)
                if device in self.optimization_rules:
                    threshold = self.optimization_rules[device]['threshold']
                    if avg > threshold:
                        action = self.optimization_rules[device]['action']
                        recommendations[device] = {
                            'action': action,
                            'current_consumption': avg,
                            'savings_estimate': avg * 0.15  # estimation des économies
                        }
        return recommendations

# --------------------------------------------------
# Système de gestion global de la domotique
# --------------------------------------------------
class SmartHomeManager:
    def __init__(self, weather_api_key: str):
        self.irrigation = IrrigationManager(weather_api_key)
        self.habits = HabitAnalyzer()
        self.energy = EnergyOptimizer()

    def daily_update(self, location: str):
        # Simulation d'une lecture de capteur d'humidité (en %)
        soil_moisture = random.uniform(20, 40)
        irrigation_needed = self.irrigation.irrigation_decision(location, soil_moisture)
        habits = self.habits.detect_patterns()
        energy_report = self.energy.analyze_consumption()
        return {
            'irrigation': irrigation_needed,
            'habits': habits,
            'energy_recommendations': energy_report
        }

# --------------------------------------------------
# Agent SmartHome intégré dans Alfred
# --------------------------------------------------
class SmartHomeAgent(BaseAgent):
    def __init__(self, weather_api_key: str, location: str):
        super().__init__("domotique")
        self.location = location
        self.manager = SmartHomeManager(weather_api_key)
        self.running = False

    def run(self):
        self.running = True
        logger.info("SmartHomeAgent démarré.")
        # Simulation d'enregistrements d'activités et de consommation
        now = datetime.datetime.now()
        self.manager.habits.log_activity("wake_up", now - datetime.timedelta(hours=2))
        self.manager.habits.log_activity("lights_off", now - datetime.timedelta(hours=1))
        self.manager.energy.log_consumption("heater", 50)
        self.manager.energy.log_consumption("lights", 20)
        report = self.manager.daily_update(self.location)
        logger.info(f"Rapport domotique: {json.dumps(report, default=str)}")
        while self.running:
            time.sleep(1)

if __name__ == "__main__":
    # Remplace "your_openweathermap_api_key" par ta clé API et "Paris" par ta localisation
    agent = SmartHomeAgent("your_openweathermap_api_key", "Paris")
    try:
        agent.run()
    except KeyboardInterrupt:
        agent.running = False
        logger.info("Arrêt du SmartHomeAgent.")
