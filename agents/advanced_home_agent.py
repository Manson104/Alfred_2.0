"""
advanced_home_agent.py
----------------------
Advanced Smart Home Agent pour Alfred.
Intègre une gestion robuste des données météo, la lecture de capteurs de sol,
une analyse comportementale avancée et une optimisation énergétique.
"""

import datetime
import time
import json
import logging
import random
import requests
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import GradientBoostingRegressor, IsolationForest
from prophet import Prophet  # Assure-toi que Prophet est installé

# Configuration du logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AdvancedSmartHomeAgent")

# Importation de BaseAgent (doit exister dans ton projet)
from base_agent import BaseAgent

# --------------------------------------------------
# Module météo robuste (inspiré de perplexity 2)
# --------------------------------------------------
class WeatherManager:
    def __init__(self, api_keys: dict, cache_file='weather_cache.json'):
        self.api_endpoints = {
            'primary': {
                'url': 'https://api.weatherapi.com/v1/forecast.json',
                'params': {'key': api_keys['primary'], 'days': 2}
            },
            'secondary': {
                'url': 'https://api.openweathermap.org/data/2.5/forecast',
                'params': {'appid': api_keys['secondary'], 'units': 'metric'}
            }
        }
        self.cache_file = cache_file
        self.cache_expiry = datetime.timedelta(hours=1)
        self.timeout = 10
        self.max_retries = 3

    def _load_cache(self):
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except Exception:
            return None

    def _save_cache(self, data):
        with open(self.cache_file, 'w') as f:
            json.dump({
                'timestamp': datetime.datetime.now().isoformat(),
                'data': data
            }, f)

    def _get_from_api(self, endpoint: str, location: str):
        config = self.api_endpoints[endpoint]
        params = {**config['params'], 'q': location}
        for attempt in range(self.max_retries):
            try:
                response = requests.get(config['url'], params=params, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                # Validation simple : vérifier si certaines clés existent
                if 'forecast' in data or 'list' in data:
                    return data
                else:
                    raise ValueError("Données incomplètes")
            except Exception as e:
                logger.error(f"Erreur API {endpoint} (tentative {attempt+1}) : {e}")
                time.sleep(2 ** attempt)
        return None

    def get_weather_data(self, location: str):
        data = self._get_from_api('primary', location)
        if data:
            self._save_cache(data)
            return data
        data = self._get_from_api('secondary', location)
        if data:
            self._save_cache(data)
            return data
        cached = self._load_cache()
        if cached:
            ts = datetime.datetime.fromisoformat(cached['timestamp'])
            if datetime.datetime.now() - ts < self.cache_expiry:
                return cached['data']
        return None

# --------------------------------------------------
# Module de capteurs de sol (inspiré de perplexity 3)
# --------------------------------------------------
class SoilSensor:
    def __init__(self):
        # Pour la simulation, on fixe des valeurs de calibration
        self.calibration = {'dry': 430, 'wet': 260}

    def read_moisture(self):
        # Simule une lecture brute entre 'wet' et 'dry'
        raw = random.uniform(self.calibration['wet'], self.calibration['dry'])
        # Conversion en pourcentage (valeurs simulées)
        moisture = max(0, min(100, (raw - self.calibration['dry']) / (self.calibration['wet'] - self.calibration['dry']) * 100))
        return moisture

# --------------------------------------------------
# Module d'analyse comportementale avancée (inspiré de perplexity 4)
# --------------------------------------------------
class HabitEngine:
    def __init__(self):
        self.behavior_db = pd.DataFrame(columns=['timestamp', 'activity', 'duration', 'intensity'])
        self.cluster_model = KMeans(n_clusters=3)
        self.habit_profiles = {}

    def log_activity(self, activity: str, duration: float, intensity: int):
        new_entry = {
            'timestamp': datetime.datetime.now(),
            'activity': activity,
            'duration': duration,
            'intensity': intensity
        }
        self.behavior_db = pd.concat([self.behavior_db, pd.DataFrame([new_entry])], ignore_index=True)

    def detect_patterns(self):
        if self.behavior_db.empty:
            return {}
        df = self.behavior_db.copy()
        df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
        features = df[['hour', 'duration', 'intensity']].values
        self.cluster_model.fit(features)
        df['cluster'] = self.cluster_model.labels_
        patterns = {}
        for cluster in range(3):
            cluster_data = df[df['cluster'] == cluster]
            if not cluster_data.empty:
                dominant = cluster_data['activity'].mode()[0]
                patterns[cluster] = dominant
        return patterns

# --------------------------------------------------
# Module d'optimisation énergétique avancée (inspiré de perplexity 5)
# --------------------------------------------------
class AdvancedEnergyOptimizer:
    def __init__(self):
        self.energy_data = pd.DataFrame()
        self.energy_ratings = {
            'washing_machine': {'A': 0.8, 'B': 1.0, 'C': 1.2},
            'dishwasher': {'A': 1.1, 'B': 1.3, 'C': 1.5}
        }

    def log_consumption(self, device: str, consumption: float):
        new_entry = {
            'timestamp': datetime.datetime.now(),
            'device': device,
            'consumption': consumption
        }
        self.energy_data = pd.concat([self.energy_data, pd.DataFrame([new_entry])], ignore_index=True)

    def analyze_consumption(self):
        if self.energy_data.empty:
            return {}
        recommendations = {}
        grouped = self.energy_data.groupby('device')['consumption'].mean()
        for device, avg in grouped.items():
            if device == 'heater' and avg > 45:
                recommendations[device] = {
                    'action': 'adjust_temperature',
                    'current_consumption': avg,
                    'savings_estimate': round(avg * 0.15, 1)
                }
            elif device == 'lights' and avg > 18:
                recommendations[device] = {
                    'action': 'dim_lights',
                    'current_consumption': avg,
                    'savings_estimate': round(avg * 0.15, 1)
                }
        return recommendations

# --------------------------------------------------
# Advanced Smart Home Agent
# --------------------------------------------------
class AdvancedSmartHomeAgent(BaseAgent):
    def __init__(self, weather_api_keys: dict, location: str):
        super().__init__("advanced_domotique")
        self.location = location
        self.weather_manager = WeatherManager(weather_api_keys)
        self.soil_sensor = SoilSensor()
        self.habit_engine = HabitEngine()
        self.energy_optimizer = AdvancedEnergyOptimizer()
        self.running = False

    def run(self):
        self.running = True
        logger.info("AdvancedSmartHomeAgent démarré.")
        # Récupération météo
        weather_data = self.weather_manager.get_weather_data(self.location)
        if weather_data:
            logger.info("Données météo récupérées.")
        else:
            logger.warning("Aucune donnée météo récupérée.")
        # Lecture du capteur de sol
        soil_moisture = self.soil_sensor.read_moisture()
        logger.info(f"Humidité du sol : {soil_moisture:.2f}%")
        # Simulation d'enregistrement d'activités
        self.habit_engine.log_activity("wake_up", 0.5, 3)
        self.habit_engine.log_activity("lights_off", 0.3, 2)
        habit_patterns = self.habit_engine.detect_patterns()
        logger.info(f"Patterns d'habitudes détectés : {habit_patterns}")
        # Simulation de consommation énergétique
        self.energy_optimizer.log_consumption("heater", random.uniform(40, 60))
        self.energy_optimizer.log_consumption("lights", random.uniform(15, 25))
        energy_recommendations = self.energy_optimizer.analyze_consumption()
        logger.info(f"Recommandations énergétiques : {energy_recommendations}")
        # Constitution d'un rapport global
        report = {
            'weather': weather_data,
            'soil_moisture': soil_moisture,
            'habit_patterns': habit_patterns,
            'energy_recommendations': energy_recommendations
        }
        logger.info(f"Rapport domotique avancé : {json.dumps(report, default=str)}")
        while self.running:
            time.sleep(1)

if __name__ == "__main__":
    # Remplace les clés API par les tiennes
    API_KEYS = {
        'primary': 'clé_api_weatherapi',
        'secondary': 'clé_api_openweathermap'
    }
    agent = AdvancedSmartHomeAgent(API_KEYS, "Paris")
    try:
        agent.run()
    except KeyboardInterrupt:
        agent.running = False
        logger.info("Arrêt de l'AdvancedSmartHomeAgent.")
