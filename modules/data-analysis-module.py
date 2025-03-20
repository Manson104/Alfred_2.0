"""
modules/data_analysis_module.py
------------------
Module d'analyse des données pour Alfred.
Fournit des fonctionnalités d'analyse, de prédiction et d'optimisation
basées sur les données collectées par le système.
"""

import logging
import json
import time
import datetime
import threading
import os
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Union, Tuple
from collections import defaultdict

from modules.module_interface import ModuleInterface

class DataAnalysisModule(ModuleInterface):
    """
    Module d'analyse des données pour Alfred.
    Permet d'analyser les données du système pour identifier des tendances,
    faire des prédictions et optimiser le fonctionnement du système.
    """
    
    def __init__(self, module_id: str, config: Dict[str, Any] = None):
        """
        Initialise le module d'analyse des données.
        
        Args:
            module_id: Identifiant unique du module
            config: Configuration du module (optionnelle)
        """
        super().__init__(module_id, config)
        self.logger = logging.getLogger(f"data_analysis.{module_id}")
        
        # Configuration par défaut
        self.default_config = {
            "data_dir": "./data",
            "analysis_interval": 3600,  # 1 heure
            "history_length": 30,  # 30 jours
            "prediction_horizon": 24,  # 24 heures
            "enable_energy_analysis": True,
            "enable_presence_analysis": True,
            "enable_temperature_analysis": True,
            "enable_behavior_analysis": True
        }
        
        # Fusionner avec la configuration fournie
        self.config = {**self.default_config, **(config or {})}
        
        # État interne
        self.data_dir = self.config["data_dir"]
        self.analysis_thread = None
        self.running = False
        self.message_bus = None
        self.state_manager = None
        self.datasets = {}
        self.models = {}
        self.predictions = {}
        self.insights = []
        self.last_analysis_time = 0
    
    def initialize(self) -> bool:
        """
        Initialise le module d'analyse des données.
        
        Returns:
            True si l'initialisation est réussie, False sinon
        """
        self.logger.info("Initialisation du module d'analyse des données")
        
        # Récupérer les dépendances
        self.message_bus = self.get_dependency("message_bus")
        self.state_manager = self.get_dependency("state_manager")
        
        if not self.message_bus or not self.state_manager:
            self.logger.error("MessageBus ou StateManager non disponible")
            return False
        
        # Créer le répertoire de données s'il n'existe pas
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Charger les données historiques
        self._load_historical_data()
        
        # Enregistrer les gestionnaires de messages
        self._register_message_handlers()
        
        # Démarrer le thread d'analyse périodique
        self.running = True
        self.analysis_thread = threading.Thread(target=self._analysis_thread_func, daemon=True)
        self.analysis_thread.start()
        
        self.initialized = True
        return True
    
    def cleanup(self) -> bool:
        """
        Nettoie les ressources utilisées par le module.
        
        Returns:
            True si le nettoyage est réussi, False sinon
        """
        self.logger.info("Nettoyage du module d'analyse des données")
        self.running = False
        
        if self.analysis_thread and self.analysis_thread.is_alive():
            self.analysis_thread.join(timeout=3.0)
        
        # Sauvegarder les données et modèles
        self._save_data_and_models()
        
        return True
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Renvoie les capacités du module.
        
        Returns:
            Dictionnaire des capacités
        """
        return {
            "data_analysis": True,
            "prediction": True,
            "anomaly_detection": True,
            "pattern_recognition": True,
            "energy_analysis": self.config["enable_energy_analysis"],
            "presence_analysis": self.config["enable_presence_analysis"],
            "temperature_analysis": self.config["enable_temperature_analysis"],
            "behavior_analysis": self.config["enable_behavior_analysis"]
        }
    
    def _register_message_handlers(self) -> None:
        """Enregistre les gestionnaires de messages pour le bus de messages."""
        handlers = {
            "data_analysis/analyze": self._handle_analyze_request,
            "data_analysis/predict": self._handle_predict_request,
            "data_analysis/insights": self._handle_insights_request,
            "data_analysis/export": self._handle_export_request,
            "data_analysis/status": self._handle_status_request
        }
        
        for topic, handler in handlers.items():
            self.message_bus.subscribe(topic, handler)
            self.logger.debug(f"Gestionnaire enregistré pour le topic: {topic}")
    
    def _load_historical_data(self) -> None:
        """Charge les données historiques depuis le stockage."""
        try:
            # Vérifier les fichiers de données disponibles
            for data_type in ["energy", "presence", "temperature", "behavior"]:
                data_file = os.path.join(self.data_dir, f"{data_type}_data.csv")
                if os.path.exists(data_file):
                    try:
                        df = pd.read_csv(data_file, parse_dates=["timestamp"])
                        self.datasets[data_type] = df
                        self.logger.info(f"Données historiques chargées: {data_type} ({len(df)} enregistrements)")
                    except Exception as e:
                        self.logger.error(f"Erreur lors du chargement des données {data_type}: {str(e)}")
                else:
                    self.logger.info(f"Aucune donnée historique trouvée pour {data_type}")
                    # Créer un DataFrame vide avec les colonnes appropriées
                    if data_type == "energy":
                        self.datasets[data_type] = pd.DataFrame({
                            "timestamp": [], 
                            "device_id": [], 
                            "consumption": [], 
                            "unit": []
                        })
                    elif data_type == "presence":
                        self.datasets[data_type] = pd.DataFrame({
                            "timestamp": [], 
                            "person_id": [], 
                            "state": [], 
                            "location": []
                        })
                    elif data_type == "temperature":
                        self.datasets[data_type] = pd.DataFrame({
                            "timestamp": [], 
                            "sensor_id": [], 
                            "temperature": [], 
                            "humidity": []
                        })
                    elif data_type == "behavior":
                        self.datasets[data_type] = pd.DataFrame({
                            "timestamp": [], 
                            "user_id": [], 
                            "action": [], 
                            "context": []
                        })
            
            # Charger les modèles pré-entraînés si disponibles
            model_file = os.path.join(self.data_dir, f"{data_type}_model.pkl")
            if os.path.exists(model_file):
                try:
                    import pickle
                    with open(model_file, "rb") as f:
                        self.models[data_type] = pickle.load(f)
                    self.logger.info(f"Modèle chargé: {data_type}")
                except Exception as e:
                    self.logger.error(f"Erreur lors du chargement du modèle {data_type}: {str(e)}")
        except Exception as e:
            self.logger.error(f"Erreur générale lors du chargement des données historiques: {str(e)}")
    
    def _save_data_and_models(self) -> None:
        """Sauvegarde les données et modèles sur le disque."""
        try:
            # Sauvegarder les données collectées
            for data_type, df in self.datasets.items():
                if not df.empty:
                    data_file = os.path.join(self.data_dir, f"{data_type}_data.csv")
                    df.to_csv(data_file, index=False)
                    self.logger.info(f"Données sauvegardées: {data_type} ({len(df)} enregistrements)")
            
            # Sauvegarder les modèles entraînés
            for data_type, model in self.models.items():
                if model:
                    import pickle
                    model_file = os.path.join(self.data_dir, f"{data_type}_model.pkl")
                    with open(model_file, "wb") as f:
                        pickle.dump(model, f)
                    self.logger.info(f"Modèle sauvegardé: {data_type}")
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde des données et modèles: {str(e)}")
    
    def _analysis_thread_func(self) -> None:
        """Thread d'analyse périodique des données."""
        while self.running:
            current_time = time.time()
            
            # Vérifier si une analyse est nécessaire
            if current_time - self.last_analysis_time >= self.config["analysis_interval"]:
                self.logger.info("Démarrage de l'analyse périodique des données")
                
                try:
                    # Collecter les nouvelles données
                    self._collect_data()
                    
                    # Effectuer l'analyse des données
                    self._analyze_data()
                    
                    # Mettre à jour les prédictions
                    self._update_predictions()
                    
                    # Générer des insights
                    self._generate_insights()
                    
                    # Mettre à jour l'heure de la dernière analyse
                    self.last_analysis_time = current_time
                    
                    # Publier un événement d'analyse complétée
                    self.message_bus.publish("data_analysis/analysis_completed", {
                        "timestamp": current_time,
                        "insights_count": len(self.insights)
                    })
                    
                    self.logger.info("Analyse périodique des données terminée")
                except Exception as e:
                    self.logger.error(f"Erreur lors de l'analyse périodique: {str(e)}")
            
            # Attendre avant la prochaine vérification
            time.sleep(60)  # Vérifier toutes les minutes
    
    def _collect_data(self) -> None:
        """Collecte les nouvelles données depuis les autres modules."""
        try:
            # Collecter les données de consommation d'énergie
            if self.config["enable_energy_analysis"]:
                energy_state = self.state_manager.get("energy")
                if energy_state:
                    # Extraire les données pertinentes
                    devices = energy_state.get("devices", {})
                    for device_id, device_data in devices.items():
                        consumption = device_data.get("consumption", 0)
                        unit = device_data.get("unit", "W")
                        
                        # Ajouter à notre jeu de données
                        new_row = pd.DataFrame({
                            "timestamp": [datetime.datetime.now()],
                            "device_id": [device_id],
                            "consumption": [consumption],
                            "unit": [unit]
                        })
                        self.datasets["energy"] = pd.concat([self.datasets["energy"], new_row], ignore_index=True)
            
            # Collecter les données de présence
            if self.config["enable_presence_analysis"]:
                presence_state = self.state_manager.get("presence")
                if presence_state:
                    persons = presence_state.get("persons", {})
                    for person_id, person_data in persons.items():
                        state = person_data.get("state", "unknown")
                        location = person_data.get("location", "unknown")
                        
                        new_row = pd.DataFrame({
                            "timestamp": [datetime.datetime.now()],
                            "person_id": [person_id],
                            "state": [state],
                            "location": [location]
                        })
                        self.datasets["presence"] = pd.concat([self.datasets["presence"], new_row], ignore_index=True)
            
            # Collecter les données de température
            if self.config["enable_temperature_analysis"]:
                climate_state = self.state_manager.get("climate")
                if climate_state:
                    sensors = climate_state.get("sensors", {})
                    for sensor_id, sensor_data in sensors.items():
                        temperature = sensor_data.get("temperature", 0)
                        humidity = sensor_data.get("humidity", 0)
                        
                        new_row = pd.DataFrame({
                            "timestamp": [datetime.datetime.now()],
                            "sensor_id": [sensor_id],
                            "temperature": [temperature],
                            "humidity": [humidity]
                        })
                        self.datasets["temperature"] = pd.concat([self.datasets["temperature"], new_row], ignore_index=True)
            
            # Collecter les données de comportement
            if self.config["enable_behavior_analysis"]:
                # Les données de comportement peuvent provenir de différentes sources
                # Ici, nous nous abonnons au bus de messages pour collecter les actions des utilisateurs
                pass
            
            # Limiter la taille des données historiques
            for data_type, df in self.datasets.items():
                if not df.empty:
                    # Convertir la colonne timestamp en datetime si ce n'est pas déjà fait
                    if df["timestamp"].dtype != "datetime64[ns]":
                        df["timestamp"] = pd.to_datetime(df["timestamp"])
                    
                    # Filtrer pour ne garder que les données des X derniers jours
                    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=self.config["history_length"])
                    self.datasets[data_type] = df[df["timestamp"] >= cutoff_date]
        except Exception as e:
            self.logger.error(f"Erreur lors de la collecte des données: {str(e)}")
    
    def _analyze_data(self) -> None:
        """Analyse les données collectées pour identifier des tendances et anomalies."""
        try:
            # Analyse de la consommation d'énergie
            if self.config["enable_energy_analysis"] and "energy" in self.datasets:
                df = self.datasets["energy"]
                if not df.empty:
                    # Agréger la consommation par appareil et par jour
                    df["date"] = df["timestamp"].dt.date
                    daily_consumption = df.groupby(["date", "device_id"])["consumption"].mean().reset_index()
                    
                    # Détecter les anomalies (consommation anormalement élevée)
                    for device_id in daily_consumption["device_id"].unique():
                        device_data = daily_consumption[daily_consumption["device_id"] == device_id]
                        
                        # Utiliser une méthode simple pour la détection d'anomalies
                        mean = device_data["consumption"].mean()
                        std = device_data["consumption"].std()
                        threshold = mean + 2 * std  # 2 écarts-types au-dessus de la moyenne
                        
                        anomalies = device_data[device_data["consumption"] > threshold]
                        
                        if not anomalies.empty:
                            for _, row in anomalies.iterrows():
                                insight = {
                                    "type": "anomaly",
                                    "category": "energy",
                                    "device_id": device_id,
                                    "date": row["date"].strftime("%Y-%m-%d"),
                                    "consumption": row["consumption"],
                                    "threshold": threshold,
                                    "message": f"Consommation anormalement élevée détectée pour {device_id} le {row['date']} ({row['consumption']} > {threshold:.2f})"
                                }
                                if insight not in self.insights:
                                    self.insights.append(insight)
            
            # Analyse des habitudes de présence
            if self.config["enable_presence_analysis"] and "presence" in self.datasets:
                df = self.datasets["presence"]
                if not df.empty:
                    # Ajouter des colonnes pour l'heure et le jour de la semaine
                    df["hour"] = df["timestamp"].dt.hour
                    df["day_of_week"] = df["timestamp"].dt.dayofweek  # 0 = lundi, 6 = dimanche
                    
                    # Analyser les habitudes pour chaque personne
                    for person_id in df["person_id"].unique():
                        person_data = df[df["person_id"] == person_id]
                        
                        # Déterminer les heures habituelles de présence
                        presence_hours = person_data[person_data["state"] == "home"]["hour"].value_counts().sort_index()
                        
                        if not presence_hours.empty:
                            # Identifier les heures de pointe de présence
                            peak_hours = presence_hours[presence_hours > presence_hours.mean()].index.tolist()
                            
                            if peak_hours:
                                insight = {
                                    "type": "pattern",
                                    "category": "presence",
                                    "person_id": person_id,
                                    "peak_hours": peak_hours,
                                    "message": f"Heures de présence habituelles pour {person_id}: {', '.join(map(str, peak_hours))}"
                                }
                                if insight not in self.insights:
                                    self.insights.append(insight)
            
            # Analyse des données de température
            if self.config["enable_temperature_analysis"] and "temperature" in self.datasets:
                df = self.datasets["temperature"]
                if not df.empty:
                    # Ajouter des colonnes pour l'heure et le jour
                    df["hour"] = df["timestamp"].dt.hour
                    df["date"] = df["timestamp"].dt.date
                    
                    # Analyser les tendances pour chaque capteur
                    for sensor_id in df["sensor_id"].unique():
                        sensor_data = df[df["sensor_id"] == sensor_id]
                        
                        # Calculer les statistiques quotidiennes
                        daily_stats = sensor_data.groupby("date")["temperature"].agg(["mean", "min", "max"]).reset_index()
                        
                        # Détecter les jours avec des variations importantes
                        daily_stats["variation"] = daily_stats["max"] - daily_stats["min"]
                        high_variation_days = daily_stats[daily_stats["variation"] > daily_stats["variation"].mean() + daily_stats["variation"].std()]
                        
                        if not high_variation_days.empty:
                            for _, row in high_variation_days.iterrows():
                                insight = {
                                    "type": "observation",
                                    "category": "temperature",
                                    "sensor_id": sensor_id,
                                    "date": row["date"].strftime("%Y-%m-%d"),
                                    "min_temp": row["min"],
                                    "max_temp": row["max"],
                                    "variation": row["variation"],
                                    "message": f"Variation importante de température détectée par {sensor_id} le {row['date']} (min: {row['min']}°C, max: {row['max']}°C, variation: {row['variation']}°C)"
                                }
                                if insight not in self.insights:
                                    self.insights.append(insight)
            
            # Analyse des comportements
            if self.config["enable_behavior_analysis"] and "behavior" in self.datasets:
                df = self.datasets["behavior"]
                if not df.empty:
                    # Ajouter des colonnes pour l'heure et le jour
                    df["hour"] = df["timestamp"].dt.hour
                    df["day_of_week"] = df["timestamp"].dt.dayofweek
                    
                    # Analyser les actions fréquentes pour chaque utilisateur
                    for user_id in df["user_id"].unique():
                        user_data = df[df["user_id"] == user_id]
                        
                        # Compter les actions les plus fréquentes
                        action_counts = user_data["action"].value_counts()
                        top_actions = action_counts.head(3).index.tolist()
                        
                        if top_actions:
                            insight = {
                                "type": "behavior",
                                "category": "user_actions",
                                "user_id": user_id,
                                "top_actions": top_actions,
                                "message": f"Actions les plus fréquentes pour {user_id}: {', '.join(top_actions)}"
                            }
                            if insight not in self.insights:
                                self.insights.append(insight)
        except Exception as e:
            self.logger.error(f"Erreur lors de l'analyse des données: {str(e)}")
    
    def _update_predictions(self) -> None:
        """Met à jour les prédictions basées sur les données historiques."""
        try:
            # Prédiction de consommation d'énergie
            if self.config["enable_energy_analysis"] and "energy" in self.datasets:
                df = self.datasets["energy"]
                if not df.empty and len(df) > 24:  # Au moins 24 points de données
                    # Grouper par appareil et par heure
                    df["hour"] = df["timestamp"].dt.hour
                    df["date"] = df["timestamp"].dt.date
                    hourly_consumption = df.groupby(["device_id", "hour"])["consumption"].mean().reset_index()
                    
                    # Pour chaque appareil, prédire la consommation future
                    for device_id in hourly_consumption["device_id"].unique():
                        device_data = hourly_consumption[hourly_consumption["device_id"] == device_id]
                        
                        # Modèle simple: moyenne par heure
                        predicted_consumption = []
                        for hour in range(24):
                            hour_data = device_data[device_data["hour"] == hour]
                            if not hour_data.empty:
                                predicted_consumption.append({
                                    "hour": hour,
                                    "consumption": hour_data["consumption"].mean()
                                })
                        
                        self.predictions[f"energy_{device_id}"] = predicted_consumption
            
            # Prédiction de présence
            if self.config["enable_presence_analysis"] and "presence" in self.datasets:
                df = self.datasets["presence"]
                if not df.empty:
                    # Ajouter des colonnes pour l'heure et le jour
                    df["hour"] = df["timestamp"].dt.hour
                    df["day_of_week"] = df["timestamp"].dt.dayofweek
                    
                    # Pour chaque personne, prédire la présence future
                    for person_id in df["person_id"].unique():
                        person_data = df[df["person_id"] == person_id]
                        
                        # Calculer la probabilité de présence par heure et jour de la semaine
                        presence_prob = {}
                        for day in range(7):
                            day_data = person_data[person_data["day_of_week"] == day]
                            if not day_data.empty:
                                for hour in range(24):
                                    hour_data = day_data[day_data["hour"] == hour]
                                    if not hour_data.empty:
                                        # Calculer la probabilité de présence
                                        presence_count = hour_data[hour_data["state"] == "home"].shape[0]
                                        total_count = hour_data.shape[0]
                                        probability = presence_count / total_count if total_count > 0 else 0
                                        
                                        if day not in presence_prob:
                                            presence_prob[day] = {}
                                        presence_prob[day][hour] = probability
                        
                        self.predictions[f"presence_{person_id}"] = presence_prob
            
            # Prédiction de température
            if self.config["enable_temperature_analysis"] and "temperature" in self.datasets:
                df = self.datasets["temperature"]
                if not df.empty:
                    # Ajouter des colonnes pour l'heure
                    df["hour"] = df["timestamp"].dt.hour
                    
                    # Pour chaque capteur, prédire la température future
                    for sensor_id in df["sensor_id"].unique():
                        sensor_data = df[df["sensor_id"] == sensor_id]
                        
                        # Calculer la température moyenne par heure
                        hourly_temp = sensor_data.groupby("hour")["temperature"].mean().reset_index()
                        
                        predicted_temp = []
                        for _, row in hourly_temp.iterrows():
                            predicted_temp.append({
                                "hour": row["hour"],
                                "temperature": row["temperature"]
                            })
                        
                        self.predictions[f"temperature_{sensor_id}"] = predicted_temp
        except Exception as e:
            self.logger.error(f"Erreur lors de la mise à jour des prédictions: {str(e)}")
    
    def _generate_insights(self) -> None:
        """Génère des insights basés sur l'analyse des données."""
        try:
            # Limiter le nombre d'insights
            max_insights = 100
            if len(self.insights) > max_insights:
                self.insights = self.insights[-max_insights:]
            
            # Trier les insights par catégorie et type
            sorted_insights = sorted(self.insights, key=lambda x: (x["category"], x["type"]))
            
            # Publier les insights dans le gestionnaire d'état
            self.state_manager.set("data_analysis.insights", sorted_insights)
            
            # Identifier les insights importants à notifier
            important_insights = [insight for insight in self.insights if insight.get("type") == "anomaly"]
            if important_insights:
                # Publier les insights importants sur le bus de messages
                self.message_bus.publish("data_analysis/important_insights", {
                    "insights": important_insights
                })
                
                # Envoyer des notifications pour les insights importants
                for insight in important_insights:
                    self.message_bus.publish("notification/send", {
                        "title": "Insight important",
                        "message": insight["message"],
                        "priority": "high",
                        "category": "insights"
                    })
        except Exception as e:
            self.logger.error(f"Erreur lors de la génération des insights: {str(e)}")
    
    # Gestionnaires de messages
    
    def _handle_analyze_request(self, message: Dict[str, Any]) -> None:
        """Gère les demandes d'analyse manuelle."""
        data_type = message.get("data_type")
        
        reply_topic = message.get("reply_topic")
        if not reply_topic:
            return
        
        try:
            # Collecter les données
            self._collect_data()
            
            # Effectuer l'analyse spécifique ou globale
            if data_type:
                # Analyse spécifique
                if data_type == "energy":
                    self._analyze_energy_data()
                elif data_type == "presence":
                    self._analyze_presence_data()
                elif data_type == "temperature":
                    self._analyze_temperature_data()
                elif data_type == "behavior":
                    self._analyze_behavior_data()
                else:
                    self.message_bus.publish(reply_topic, {
                        "success": False,
                        "error": f"Type de données inconnu: {data_type}"
                    })
                    return
            else:
                # Analyse globale
                self._analyze_data()
            
            # Mettre à jour les prédictions
            self._update_predictions()
            
            # Générer des insights
            self._generate_insights()
            
            # Répondre avec succès
            self.message_bus.publish(reply_topic, {
                "success": True,
                "insights_count": len(self.insights),
                "data_type": data_type or "all"
            })
        except Exception as e:
            self.logger.error(f"Erreur lors de l'analyse manuelle: {str(e)}")
            self.message_bus.publish(reply_topic, {
                "success": False,
                "error": str(e)
            })
    
    def _handle_predict_request(self, message: Dict[str, Any]) -> None:
        """Gère les demandes de prédiction."""
        prediction_type = message.get("prediction_type")
        entity_id = message.get("entity_id")
        
        reply_topic = message.get("reply_topic")
        if not reply_topic:
            return
        
        try:
            if not prediction_type or not entity_id:
                self.message_bus.publish(reply_topic, {
                    "success": False,
                    "error": "Type de prédiction ou ID d'entité manquant"
                })
                return
            
            prediction_key = f"{prediction_type}_{entity_id}"
            
            if prediction_key in self.predictions:
                self.message_bus.publish(reply_topic, {
                    "success": True,
                    "prediction_type": prediction_type,
                    "entity_id":