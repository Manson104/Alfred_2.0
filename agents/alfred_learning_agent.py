"""
alfred_learning_agent.py
------------------------
Module de gestion et d'apprentissage progressif pour Alfred.
Ce module permet de collecter différents types de données (interaction, énergie, température, feedback, commande, erreur),
d'analyser ces données pour détecter des anomalies et des tendances, et de proposer des améliorations automatiques.
À placer dans le dossier 'alfred/agents/' de votre projet Alfred.
"""

import os
import json
import time
import datetime
import logging
import threading
import random
from enum import Enum
from collections import defaultdict

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest, GradientBoostingRegressor
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("alfred_learning.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("LearningAgent")

# --- Définition des Enums pour les types de données et modes ---
class DataType(Enum):
    INTERACTION = "interaction"   # Interactions utilisateur
    ENERGY = "energy"             # Consommation d'énergie
    TEMPERATURE = "temperature"   # Données de température
    FEEDBACK = "feedback"         # Retours utilisateur
    COMMAND = "command"           # Commandes exécutées
    ERROR = "error"               # Erreurs rencontrées

class FeedbackType(Enum):
    POSITIVE = 1
    NEUTRAL = 0
    NEGATIVE = -1

class LearningMode(Enum):
    PASSIVE = "passive"   # Collecte sans adaptation automatique
    ACTIVE = "active"     # Collecte et adaptation automatique

class AnomalyType(Enum):
    ENERGY_SPIKE = "energy_spike"
    UNUSUAL_PATTERN = "unusual_pattern"
    REPEATED_ERROR = "repeated_error"
    FEEDBACK_TREND = "feedback_trend"

# --- DataCollector : collecte et écriture des données ---
class DataCollector:
    """
    Classe responsable de la collecte et du stockage des données pour l'apprentissage.
    Les données sont conservées dans un buffer en mémoire et écrites sur disque lorsque le seuil est atteint.
    """
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self._ensure_data_dirs()
        # Buffer en mémoire par type de donnée
        self.memory_buffer = {dtype.value: [] for dtype in DataType}
        # Seuils pour déclencher l'écriture sur disque
        self.buffer_thresholds = {
            DataType.INTERACTION.value: 100,
            DataType.ENERGY.value: 50,
            DataType.TEMPERATURE.value: 50,
            DataType.FEEDBACK.value: 20,
            DataType.COMMAND.value: 100,
            DataType.ERROR.value: 10
        }
        # Verrous pour l'accès concurrent
        self.locks = {dtype.value: threading.Lock() for dtype in DataType}

    def _ensure_data_dirs(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            logger.info(f"Répertoire de données créé : {self.data_dir}")
        for dtype in DataType:
            dtype_dir = os.path.join(self.data_dir, dtype.value)
            if not os.path.exists(dtype_dir):
                os.makedirs(dtype_dir)

    def _get_file_path(self, data_type: DataType) -> str:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.data_dir, data_type.value, f"{today}.json")

    def collect(self, data_type: DataType, data: dict) -> bool:
        try:
            if "timestamp" not in data:
                data["timestamp"] = datetime.datetime.now().isoformat()
            dtype_val = data_type.value
            with self.locks[dtype_val]:
                self.memory_buffer[dtype_val].append(data)
                if len(self.memory_buffer[dtype_val]) >= self.buffer_thresholds[dtype_val]:
                    self._write_buffer(data_type)
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la collecte de {dtype_val}: {e}")
            return False

    def _write_buffer(self, data_type: DataType) -> bool:
        dtype_val = data_type.value
        file_path = self._get_file_path(data_type)
        try:
            existing = []
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            combined = existing + self.memory_buffer[dtype_val]
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(combined, f, ensure_ascii=False, indent=2)
            self.memory_buffer[dtype_val] = []
            logger.info(f"Données {dtype_val} écrites dans {file_path}")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'écriture de {dtype_val}: {e}")
            return False

    def flush(self):
        for dtype in DataType:
            with self.locks[dtype.value]:
                if self.memory_buffer[dtype.value]:
                    self._write_buffer(dtype)
        return True

    # Fonctions pratiques de collecte
    def collect_interaction(self, user_query: str, response: str, mode: str, duration_ms: int = None) -> bool:
        data = {"user_query": user_query, "response": response, "mode": mode}
        if duration_ms is not None:
            data["duration_ms"] = duration_ms
        return self.collect(DataType.INTERACTION, data)

    def collect_energy(self, device: str, consumption: float, unit: str = "kWh") -> bool:
        data = {"device": device, "consumption": consumption, "unit": unit}
        return self.collect(DataType.ENERGY, data)

    def collect_temperature(self, room: str, temperature: float, target_temperature: float = None) -> bool:
        data = {"room": room, "temperature": temperature}
        if target_temperature is not None:
            data["target_temperature"] = target_temperature
        return self.collect(DataType.TEMPERATURE, data)

    def collect_feedback(self, feature: str, rating: FeedbackType, comment: str = None) -> bool:
        data = {"feature": feature, "rating": rating.value}
        if comment:
            data["comment"] = comment
        return self.collect(DataType.FEEDBACK, data)

    def collect_command(self, command: str, source: str, success: bool, duration_ms: int = None) -> bool:
        data = {"command": command, "source": source, "success": success}
        if duration_ms is not None:
            data["duration_ms"] = duration_ms
        return self.collect(DataType.COMMAND, data)

    def collect_error(self, error_type: str, message: str, context: dict = None) -> bool:
        data = {"error_type": error_type, "message": message}
        if context:
            data["context"] = context
        return self.collect(DataType.ERROR, data)

# --- DataAnalyzer : analyse des données collectées ---
class DataAnalyzer:
    """
    Analyse les données collectées pour détecter des anomalies et extraire des tendances.
    """
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.scaler = StandardScaler()
        self.anomaly_models = {}  # Pour stocker les modèles par type de donnée

    def _load_data(self, data_type: DataType, days: int = 30) -> pd.DataFrame:
        dtype_dir = os.path.join(self.data_dir, data_type.value)
        all_data = []
        if not os.path.exists(dtype_dir):
            logger.warning(f"Répertoire {dtype_dir} inexistant.")
            return pd.DataFrame()
        for filename in os.listdir(dtype_dir):
            if filename.endswith(".json"):
                try:
                    file_date = datetime.datetime.strptime(filename.split('.')[0], "%Y-%m-%d")
                    if file_date >= datetime.datetime.now() - datetime.timedelta(days=days):
                        with open(os.path.join(dtype_dir, filename), "r", encoding="utf-8") as f:
                            data = json.load(f)
                            all_data.extend(data)
                except Exception as e:
                    logger.error(f"Erreur dans le fichier {filename}: {e}")
        if all_data:
            df = pd.DataFrame(all_data)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df.sort_values("timestamp", inplace=True)
            return df
        return pd.DataFrame()

    def detect_energy_anomalies(self, days: int = 30) -> dict:
        df = self._load_data(DataType.ENERGY, days)
        if df.empty or "consumption" not in df.columns:
            return {"status": "warning", "message": "Pas assez de données énergétiques.", "anomalies": []}
        try:
            features = df[["consumption"]]
            model = IsolationForest(contamination=0.05, random_state=42)
            predictions = model.fit_predict(features)
            df["anomaly"] = predictions
            anomalies = df[df["anomaly"] == -1]
            self.anomaly_models["energy"] = model
            records = anomalies.to_dict("records")
            return {"status": "success", "message": f"{len(records)} anomalies détectées.", "anomalies": records}
        except Exception as e:
            return {"status": "error", "message": str(e), "anomalies": []}

    def analyze_energy_trends(self, days: int = 30) -> dict:
        df = self._load_data(DataType.ENERGY, days)
        if df.empty:
            return {"status": "error", "message": "Pas de données énergétiques.", "data": {}}
        try:
            df["date"] = df["timestamp"].dt.date
            daily = df.groupby("date")["consumption"].sum()
            avg = daily.mean()
            total = df["consumption"].sum()
            return {
                "status": "success",
                "message": "Analyse énergétique complétée.",
                "data": {"total_consumption": total, "avg_daily_consumption": avg, "days_analyzed": len(daily)}
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "data": {}}

# --- LearningAgent : intègre collecte, analyse et apprentissage ---
class LearningAgent:
    """
    Agent d'apprentissage progressif pour Alfred.
    Il utilise DataCollector pour stocker les données et DataAnalyzer pour analyser l'historique.
    Il met à jour automatiquement ses modèles et propose des améliorations.
    """
    def __init__(self, data_dir="data", learning_mode=LearningMode.ACTIVE):
        self.learning_mode = learning_mode
        self.data_collector = DataCollector(data_dir=data_dir)
        self.data_analyzer = DataAnalyzer(data_dir=data_dir)
        self.history = []  # Historique des événements enregistrés (en complément)
        self.running = True
        self.learning_thread = threading.Thread(target=self.learning_loop, daemon=True)
        self.learning_thread.start()

    def record_event(self, event_type: DataType, data: dict) -> bool:
        success = self.data_collector.collect(event_type, data)
        if success:
            self.history.append({
                "event_type": event_type.value,
                "data": data,
                "timestamp": datetime.datetime.now().isoformat()
            })
        return success

    # Méthodes pratiques d'enregistrement (similaires à celles de DataCollector)
    def collect_interaction(self, user_query: str, response: str, mode: str, duration_ms: int = None) -> bool:
        return self.data_collector.collect_interaction(user_query, response, mode, duration_ms)

    def collect_energy(self, device: str, consumption: float, unit: str = "kWh") -> bool:
        return self.data_collector.collect_energy(device, consumption, unit)

    def collect_temperature(self, room: str, temperature: float, target_temperature: float = None) -> bool:
        return self.data_collector.collect_temperature(room, temperature, target_temperature)

    def collect_feedback(self, feature: str, rating: FeedbackType, comment: str = None) -> bool:
        return self.data_collector.collect_feedback(feature, rating, comment)

    def collect_command(self, command: str, source: str, success: bool, duration_ms: int = None) -> bool:
        return self.data_collector.collect_command(command, source, success, duration_ms)

    def collect_error(self, error_type: str, message: str, context: dict = None) -> bool:
        return self.data_collector.collect_error(error_type, message, context)

    def update_models(self):
        """
        Met à jour les modèles d'apprentissage en analysant les données énergétiques.
        Ici, on utilise GradientBoostingRegressor et KMeans pour prédire et segmenter la consommation.
        """
        energy_data = self.data_analyzer._load_data(DataType.ENERGY, days=30)
        if energy_data.empty or "consumption" not in energy_data.columns:
            logger.info("Pas assez de données pour mettre à jour les modèles énergétiques.")
            return
        try:
            energy_data["hour"] = energy_data["timestamp"].dt.hour
            X = energy_data[["hour"]]
            y = energy_data["consumption"]
            model = GradientBoostingRegressor(n_estimators=100)
            model.fit(X, y)
            self.energy_model = model
            logger.info("Modèle prédictif de consommation énergétique mis à jour.")
        except Exception as e:
            logger.error(f"Erreur de mise à jour du modèle énergétique: {e}")

        # Mise à jour d'un modèle de clustering pour les tendances horaires
        try:
            features = energy_data[["hour"]].values
            kmeans = KMeans(n_clusters=3, random_state=42)
            kmeans.fit(features)
            self.cluster_model = kmeans
            logger.info("Modèle de clustering des habitudes énergétiques mis à jour.")
        except Exception as e:
            logger.error(f"Erreur de mise à jour du modèle de clustering: {e}")

    def propose_improvements(self) -> str:
        """
        Propose des améliorations automatiques basées sur l'analyse des données collectées.
        Par exemple, en cas d'anomalie énergétique détectée, proposer une réduction de la consommation.
        """
        analysis = self.data_analyzer.detect_anomalies(DataType.ENERGY, days=30)
        if analysis.get("status") == "success" and analysis.get("anomalies"):
            suggestion = "Réduire les appareils énergivores durant les heures de pointe."
            logger.info(f"Suggestion : {suggestion}")
            self.record_event(DataType.FEEDBACK, {"suggestion": suggestion})
            return f"Suggestion d'amélioration : {suggestion}"
        return "Aucune amélioration majeure détectée pour le moment."

    def learning_loop(self):
        """
        Boucle d'apprentissage continue qui met à jour les modèles et propose des améliorations.
        S'exécute toutes les 10 minutes.
        """
        while self.running:
            try:
                self.update_models()
                improvement = self.propose_improvements()
                logger.info(improvement)
                self.data_collector.flush()  # Sauvegarder régulièrement les buffers
            except Exception as e:
                logger.error(f"Erreur dans la boucle d'apprentissage : {e}")
            time.sleep(600)

    def stop(self):
        """Arrête la boucle d'apprentissage."""
        self.running = False
        if self.learning_thread:
            self.learning_thread.join(timeout=5)
        logger.info("LearningAgent arrêté.")

# ----- Exemple d'utilisation -----
if __name__ == "__main__":
    agent = LearningAgent(data_dir="data", learning_mode=LearningMode.ACTIVE)
    # Simulation d'enregistrement d'événements énergétiques
    for i in range(15):
        consumption = random.uniform(50, 100)
        agent.collect_energy("Chauffage", consumption, unit="kWh")
        time.sleep(1)
    # Simulation d'enregistrement d'interactions
    agent.collect_interaction("Quelle est la consommation aujourd'hui ?", "La consommation est de 75 kWh.", "majordome", duration_ms=200)
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        agent.stop()
