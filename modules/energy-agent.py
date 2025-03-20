import logging
import time
from typing import Dict, Any, List, Optional
import json
from datetime import datetime, timedelta

from base_agent import BaseAgent

class EnergyAgent(BaseAgent):
    """
    Agent spécialisé dans la gestion et l'optimisation énergétique de la maison.
    Contrôle la consommation d'énergie, intègre les énergies renouvelables,
    et optimise l'utilisation des appareils en fonction des tarifs d'électricité.
    """
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        """
        Initialise l'agent de gestion énergétique.
        
        Args:
            agent_id: Identifiant unique de l'agent
            config: Configuration de l'agent
        """
        super().__init__(agent_id, config)
        
        # Configuration spécifique à l'énergie
        self.energy_preferences = config.get("energy_preferences", {})
        self.utility_rates = config.get("utility_rates", {})
        self.renewables = config.get("renewables", {})
        self.battery_storage = config.get("battery_storage", {})
        self.load_priority = config.get("load_priority", {})
        
        # État interne
        self.energy_consumption = {}  # device_id -> {timestamp, watts, etc.}
        self.energy_production = {}   # source_id -> {timestamp, watts, etc.}
        self.daily_consumption = {}   # date -> {total_kwh, peak_kw, etc.}
        self.current_power_state = {
            "grid_power": True,
            "solar_active": False,
            "battery_active": False,
            "grid_import": 0,         # watts
            "grid_export": 0,         # watts
            "solar_production": 0,    # watts
            "battery_charge": 0,      # percentage
            "battery_power": 0,       # watts (+ charging, - discharging)
            "home_consumption": 0     # watts
        }
        
        self.logger.info("Agent de gestion énergétique initialisé")
        
        # Enregistrer les gestionnaires de messages spécifiques
        self._register_specific_handlers()
    
    def _register_specific_handlers(self):
        """Enregistre les gestionnaires de messages spécifiques à l'agent énergétique."""
        self.message_bus.register_handler("energy/consumption", self._handle_consumption_update)
        self.message_bus.register_handler("energy/production", self._handle_production_update)
        self.message_bus.register_handler("energy/status", self._handle_energy_status_request)
        self.message_bus.register_handler("energy/optimize", self._handle_optimization_request)
        self.message_bus.register_handler("energy/device/control", self._handle_device_control)
        self.message_bus.register_handler("energy/rates", self._handle_utility_rates_update)
        self.message_bus.register_handler("weather/forecast", self._handle_weather_forecast)
    
    def start(self):
        """Démarre l'agent énergétique et initialise les modules nécessaires."""
        super().start()
        
        self.logger.info("Démarrage de l'agent de gestion énergétique")
        
        # Vérifier et démarrer les modules requis
        self._ensure_required_modules()
        
        # Initialiser les systèmes énergétiques
        self._initialize_energy_systems()
        
        # Charger les données historiques si disponibles
        self._load_historical_data()
        
        # Planifier la première optimisation
        self._schedule_energy_optimization()
        
        # Publier un événement d'initialisation complète
        self.message_bus.publish("energy/initialized", {
            "agent_id": self.agent_id,
            "timestamp": time.time()
        })
    
    def _ensure_required_modules(self):
        """S'assure que tous les modules requis sont démarrés."""
        required_modules = [
            "weather",
            "scheduler"
        ]
        
        # Modules optionnels mais recommandés
        optional_modules = [
            "notification"
        ]
        
        # Vérifier que tous les modules requis sont présents et actifs
        for module_type in required_modules:
            modules = self.module_manager.get_modules_by_type(module_type)
            
            if not modules:
                self.logger.warning(f"Module requis non trouvé: {module_type}")
                
                # Essayer de démarrer le module avec la configuration par défaut
                try:
                    default_config = self.config.get("default_modules", {}).get(module_type, {})
                    self.module_manager.create_module(module_type, f"{module_type}_default", default_config)
                except Exception as e:
                    self.logger.error(f"Erreur lors de la création du module {module_type}: {e}")
        
        # Vérifier les modules optionnels
        for module_type in optional_modules:
            modules = self.module_manager.get_modules_by_type(module_type)
            
            if not modules:
                self.logger.info(f"Module optionnel non trouvé: {module_type}")
    
    def _initialize_energy_systems(self):
        """Initialise les systèmes de gestion d'énergie."""
        # Initialiser les compteurs d'énergie
        self._initialize_energy_meters()
        
        # Initialiser les systèmes renouvelables
        if self.renewables.get("solar", {}).get("enabled", False):
            self._initialize_solar_system()
        
        if self.renewables.get("wind", {}).get("enabled", False):
            self._initialize_wind_system()
        
        # Initialiser les systèmes de stockage
        if self.battery_storage.get("enabled", False):
            self._initialize_battery_system()
        
        # Initialiser les contrôles de charge
        self._initialize_load_controls()
    
    def _initialize_energy_meters(self):
        """Initialise les compteurs d'énergie."""
        meters = self.config.get("energy_meters", {})
        
        for meter_id, meter_config in meters.items():
            self.logger.info(f"Initialisation du compteur d'énergie: {meter_id}")
            
            # Dans une implémentation réelle, nous initialiserions la communication
            # avec les compteurs d'énergie physiques
            
            # Pour les besoins de cet exemple, nous simulons simplement l'initialisation
    
    def _initialize_solar_system(self):
        """Initialise le système solaire photovoltaïque."""
        solar_config = self.renewables.get("solar", {})
        
        self.logger.info(f"Initialisation du système solaire: {solar_config.get('capacity', 0)} kW")
        
        # Dans une implémentation réelle, nous initialiserions la communication
        # avec l'onduleur solaire et autres équipements
        
        # Pour les besoins de cet exemple, nous simulons simplement l'initialisation
        self.current_power_state["solar_active"] = solar_config.get("enabled", False)
    
    def _initialize_wind_system(self):
        """Initialise le système éolien."""
        wind_config = self.renewables.get("wind", {})
        
        self.logger.info(f"Initialisation du système éolien: {wind_config.get('capacity', 0)} kW")
        
        # Dans une implémentation réelle, nous initialiserions la communication
        # avec l'onduleur éolien et autres équipements
        
        # Pour les besoins de cet exemple, nous simulons simplement l'initialisation
    
    def _initialize_battery_system(self):
        """Initialise le système de stockage par batterie."""
        battery_config = self.battery_storage
        
        self.logger.info(f"Initialisation du système de batterie: {battery_config.get('capacity', 0)} kWh")
        
        # Dans une implémentation réelle, nous initialiserions la communication
        # avec le système de gestion de batterie
        
        # Pour les besoins de cet exemple, nous simulons simplement l'initialisation
        self.current_power_state["battery_active"] = battery_config.get("enabled", False)
        self.current_power_state["battery_charge"] = battery_config.get("initial_charge", 50)
    
    def _initialize_load_controls(self):
        """Initialise les contrôles de charge électrique."""
        controllable_loads = self.config.get("controllable_loads", {})
        
        for load_id, load_config in controllable_loads.items():
            self.logger.info(f"Initialisation du contrôle de charge: {load_id}")
            
            # Dans une implémentation réelle, nous initialiserions la communication
            # avec les dispositifs de contrôle de charge
            
            # Pour les besoins de cet exemple, nous simulons simplement l'initialisation
    
    def _load_historical_data(self):
        """Charge les données historiques d'énergie."""
        # Dans une implémentation réelle, nous chargerions les données
        # depuis une base de données ou des fichiers
        
        # Pour les besoins de cet exemple, nous initialisons simplement
        # avec des valeurs par défaut
        
        today = datetime.now().strftime("%Y-%m-%d")
        self.daily_consumption[today] = {
            "total_kwh": 0,
            "peak_kw": 0,
            "off_peak_kwh": 0,
            "peak_kwh": 0,
            "solar_kwh": 0,
            "grid_kwh": 0,
            "battery_kwh": 0,
            "exported_kwh": 0
        }
    
    def _schedule_energy_optimization(self):
        """Planifie l'optimisation énergétique périodique."""
        # Programmer une optimisation toutes les heures
        self.message_bus.publish("scheduler/add", {
            "task": {
                "schedule_type": "interval",
                "interval": 3600,  # 1 heure
                "enabled": True,
                "actions": [
                    {
                        "type": "publish",
                        "topic": "energy/optimize",
                        "message": {
                            "source": "scheduled"
                        }
                    }
                ]
            },
            "reply_topic": "energy/schedule_confirm"
        })
        
        # Programmer une optimisation au changement de tarif (si applicable)
        if self.utility_rates.get("type") == "time_of_use":
            rate_periods = self.utility_rates.get("periods", {})
            
            for period_name, period_config in rate_periods.items():
                start_time = period_config.get("start_time")
                
                if start_time:
                    self.message_bus.publish("scheduler/add", {
                        "task": {
                            "schedule_type": "daily",
                            "time": start_time,
                            "enabled": True,
                            "actions": [
                                {
                                    "type": "publish",
                                    "topic": "energy/optimize",
                                    "message": {
                                        "source": "rate_change",
                                        "period": period_name
                                    }
                                }
                            ]
                        },
                        "reply_topic": "energy/schedule_confirm"
                    })
    
    def _handle_consumption_update(self, message: Dict[str, Any]):
        """Gère les mises à jour de consommation d'énergie."""
        device_id = message.get("device_id")
        watts = message.get("watts", 0)
        timestamp = message.get("timestamp", time.time())
        
        if not device_id:
            return
            
        # Mettre à jour la consommation du dispositif
        self.energy_consumption[device_id] = {
            "watts": watts,
            "timestamp": timestamp
        }
        
        # Mettre à jour la consommation totale
        total_consumption = sum(device["watts"] for device in self.energy_consumption.values())
        self.current_power_state["home_consumption"] = total_consumption
        
        # Mettre à jour la consommation quotidienne
        today = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        if today not in self.daily_consumption:
            self.daily_consumption[today] = {
                "total_kwh": 0,
                "peak_kw": 0,
                "off_peak_kwh": 0,
                "peak_kwh": 0,
                "solar_kwh": 0,
                "grid_kwh": 0,
                "battery_kwh": 0,
                "exported_kwh": 0
            }
        
        # Convertir watts en kWh pour le temps écoulé depuis la dernière mise à jour
        if "last_update" in self.energy_consumption.get(device_id, {}):
            last_update = self.energy_consumption[device_id].get("last_update", timestamp)
            hours_elapsed = (timestamp - last_update) / 3600
            kwh = (watts / 1000) * hours_elapsed
            
            # Ajouter à la consommation quotidienne
            self.daily_consumption[today]["total_kwh"] += kwh
            
            # Déterminer si c'est une période de pointe et mettre à jour en conséquence
            if self._is_peak_period(timestamp):
                self.daily_consumption[today]["peak_kwh"] += kwh
            else:
                self.daily_consumption[today]["off_peak_kwh"] += kwh
            
            # Mettre à jour la puissance de pointe
            if total_consumption / 1000 > self.daily_consumption[today]["peak_kw"]:
                self.daily_consumption[today]["peak_kw"] = total_consumption / 1000
        
        # Enregistrer l'horodatage de la mise à jour
        self.energy_consumption[device_id]["last_update"] = timestamp
        
        # Recalculer les flux d'énergie
        self._calculate_energy_flows()
        
        # Vérifier si une optimisation est nécessaire
        self._check_optimization_triggers(device_id, watts)
    
    def _handle_production_update(self, message: Dict[str, Any]):
        """Gère les mises à jour de production d'énergie."""
        source_id = message.get("source_id")
        watts = message.get("watts", 0)
        timestamp = message.get("timestamp", time.time())
        
        if not source_id:
            return
            
        # Mettre à jour la production de la source
        self.energy_production[source_id] = {
            "watts": watts,
            "timestamp": timestamp
        }
        
        # Mettre à jour la production solaire totale si applicable
        if source_id.startswith("solar"):
            self.current_power_state["solar_production"] = sum(
                source["watts"] for src, source in self.energy_production.items() 
                if src.startswith("solar")
            )
        
        # Mettre à jour la production quotidienne
        today = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        if today not in self.daily_consumption:
            self.daily_consumption[today] = {
                "total_kwh": 0,
                "peak_kw": 0,
                "off_peak_kwh": 0,
                "peak_kwh": 0,
                "solar_kwh": 0,
                "grid_kwh": 0,
                "battery_kwh": 0,
                "exported_kwh": 0
            }
        
        # Convertir watts en kWh pour le temps écoulé depuis la dernière mise à jour
        if "last_update" in self.energy_production.get(source_id, {}):
            last_update = self.energy_production[source_id].get("last_update", timestamp)
            hours_elapsed = (timestamp - last_update) / 3600
            kwh = (watts / 1000) * hours_elapsed
            
            # Ajouter à la production quotidienne
            if source_id.startswith("solar"):
                self.daily_consumption[today]["solar_kwh"] += kwh
        
        # Enregistrer l'horodatage de la mise à jour
        self.energy_production[source_id]["last_update"] = timestamp
        
        # Recalculer les flux d'énergie
        self._calculate_energy_flows()
        
        # Vérifier si une optimisation est nécessaire
        self._check_production_triggers(source_id, watts)
    
    def _calculate_energy_flows(self):
        """Calcule les flux d'énergie actuels dans le système."""
        # Consommation totale de la maison
        home_consumption = self.current_power_state["home_consumption"]
        
        # Production solaire totale
        solar_production = self.current_power_state["solar_production"]
        
        # Capacité de la batterie
        battery_enabled = self.current_power_state["battery_active"]
        battery_charge = self.current_power_state["battery_charge"]
        battery_capacity = self.battery_storage.get("capacity", 0)  # kWh
        battery_power_max = self.battery_storage.get("power_max", 0)  # watts
        
        # Logique de flux d'énergie
        if solar_production >= home_consumption:
            # Surplus solaire
            surplus = solar_production - home_consumption
            
            # Énergie utilisée directement
            solar_used = home_consumption
            
            # Gestion du surplus
            if battery_enabled and battery_charge < 100:
                # Charger la batterie avec le surplus (limité par la puissance max)
                battery_charge_power = min(surplus, battery_power_max)
                self.current_power_state["battery_power"] = battery_charge_power
                
                # Calculer le nouveau niveau de charge (approximation)
                # Dans une implémentation réelle, cela serait plus complexe
                battery_charge_kwh = battery_charge_power / 1000
                battery_charge_percent = (battery_charge_kwh / battery_capacity) * 100
                self.current_power_state["battery_charge"] += battery_charge_percent
                
                # Limiter à 100%
                self.current_power_state["battery_charge"] = min(100, self.current_power_state["battery_charge"])
                
                # Surplus restant après charge de la batterie
                remaining_surplus = surplus - battery_charge_power
                
                # Exporter le surplus restant vers le réseau
                self.current_power_state["grid_export"] = remaining_surplus
                self.current_power_state["grid_import"] = 0
            else:
                # Exporter tout le surplus vers le réseau
                self.current_power_state["grid_export"] = surplus
                self.current_power_state["grid_import"] = 0
                self.current_power_state["battery_power"] = 0
        else:
            # Déficit énergétique
            deficit = home_consumption - solar_production
            
            # Énergie solaire utilisée directement
            solar_used = solar_production
            
            # Gestion du déficit
            if battery_enabled and battery_charge > self.battery_storage.get("min_charge", 20):
                # Décharger la batterie pour combler le déficit (limité par la puissance max)
                battery_discharge_power = min(deficit, battery_power_max)
                self.current_power_state["battery_power"] = -battery_discharge_power
                
                # Calculer le nouveau niveau de charge (approximation)
                battery_discharge_kwh = battery_discharge_power / 1000
                battery_discharge_percent = (battery_discharge_kwh / battery_capacity) * 100
                self.current_power_state["battery_charge"] -= battery_discharge_percent
                
                # Limiter au minimum
                min_charge = self.battery_storage.get("min_charge", 20)
                self.current_power_state["battery_charge"] = max(min_charge, self.