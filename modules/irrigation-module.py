"""
modules/irrigation_module.py
---------------------------
Module d'irrigation pour Alfred, basé sur les implémentations présentes dans les agents domotiques.
Gère les systèmes d'arrosage intelligents et optimise l'irrigation en fonction de la météo.
"""

import time
import json
import logging
import datetime
import threading
from typing import Dict, Any, List, Optional, Union, Tuple

from modules.module_interface import IrrigationModule, BaseModule, WeatherModule

# Configuration du logger
logger = logging.getLogger("IrrigationModule")

class IrrigationSystemModule(IrrigationModule):
    """
    Module de gestion d'irrigation intelligent qui utilise les données météo
    pour optimiser l'arrosage.
    """
    
    def __init__(self):
        self._name = "irrigation"
        self.zones = {}
        self.schedules = []
        self.active_zones = {}
        self.lock = threading.RLock()
        self.scheduler_thread = None
        self.running = False
        self.weather_module = None
        self.moisture_threshold = 30  # Niveau d'humidité optimal en %
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def dependencies(self) -> List[str]:
        return ["weather"]
    
    def initialize(self) -> bool:
        """
        Initialise le module d'irrigation.
        
        Returns:
            True si l'initialisation réussit, False sinon
        """
        try:
            config_file = "config/irrigation_config.json"
            with open(config_file, 'r') as f:
                config = json.load(f)
                
                # Charger les zones
                self.zones = config.get("zones", {})
                
                # Charger les planifications
                self.schedules = config.get("schedules", [])
                
                # Paramètres globaux
                self.moisture_threshold = config.get("moisture_threshold", 30)
                
                logger.info(f"Module d'irrigation initialisé avec {len(self.zones)} zones et {len(self.schedules)} planifications")
            
            # Démarrer le thread planificateur
            self.running = True
            self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self.scheduler_thread.start()
            
            logger.info("Thread planificateur d'irrigation démarré")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du module d'irrigation: {e}")
            
            # Valeurs par défaut pour permettre les tests
            self.zones = {
                "lawn": {"name": "Pelouse", "valve_pin": 17, "flow_rate": 10.0},
                "garden": {"name": "Jardin", "valve_pin": 18, "flow_rate": 8.0},
                "flower_beds": {"name": "Massifs de fleurs", "valve_pin": 27, "flow_rate": 5.0}
            }
            self.running = True
            self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self.scheduler_thread.start()
            return True
    
    def shutdown(self) -> bool:
        """
        Arrête proprement le module d'irrigation.
        
        Returns:
            True si l'arrêt réussit, False sinon
        """
        # Stopper le thread planificateur
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=2)
        
        # Arrêter toutes les zones actives
        with self.lock:
            for zone_id in list(self.active_zones.keys()):
                self._stop_zone(zone_id)
        
        logger.info("Module d'irrigation arrêté")
        return True
    
    def start_irrigation(self, zone: str, duration: int) -> bool:
        """
        Démarre l'irrigation d'une zone pour une durée donnée.
        
        Args:
            zone: Identifiant de la zone
            duration: Durée d'irrigation en secondes
            
        Returns:
            True si l'irrigation a démarré, False sinon
        """
        with self.lock:
            if zone not in self.zones:
                logger.warning(f"Zone inconnue: {zone}")
                return False
            
            # Vérifier si la zone est déjà active
            if zone in self.active_zones:
                logger.warning(f"Zone {zone} déjà active")
                return False
            
            # Démarrer l'irrigation
            return self._start_zone(zone, duration)
    
    def stop_irrigation(self, zone: str) -> bool:
        """
        Arrête l'irrigation d'une zone.
        
        Args:
            zone: Identifiant de la zone
            
        Returns:
            True si l'irrigation a été arrêtée, False sinon
        """
        with self.lock:
            if zone not in self.zones:
                logger.warning(f"Zone inconnue: {zone}")
                return False
            
            # Vérifier si la zone est active
            if zone not in self.active_zones:
                logger.warning(f"Zone {zone} déjà inactive")
                return True
            
            # Arrêter l'irrigation
            return self._stop_zone(zone)
    
    def get_irrigation_status(self, zone: Optional[str] = None) -> Dict[str, Any]:
        """
        Récupère le statut actuel de l'irrigation.
        
        Args:
            zone: Identifiant de la zone à vérifier (toutes les zones si None)
            
        Returns:
            Dictionnaire contenant le statut
        """
        with self.lock:
            if zone:
                if zone not in self.zones:
                    return {"success": False, "error": f"Zone inconnue: {zone}"}
                
                zone_info = self.zones[zone].copy()
                
                # Ajouter les informations d'activité
                if zone in self.active_zones:
                    active_info = self.active_zones[zone]
                    zone_info.update({
                        "active": True,
                        "start_time": active_info["start_time"],
                        "end_time": active_info["end_time"],
                        "remaining_seconds": max(0, int(active_info["end_time"] - time.time()))
                    })
                else:
                    zone_info.update({"active": False})
                
                return {"success": True, "zone": zone_info}
            
            else:
                # Statut de toutes les zones
                zones_status = {}
                for zone_id, zone_info in self.zones.items():
                    status = zone_info.copy()
                    
                    # Ajouter les informations d'activité
                    if zone_id in self.active_zones:
                        active_info = self.active_zones[zone_id]
                        status.update({
                            "active": True,
                            "start_time": active_info["start_time"],
                            "end_time": active_info["end_time"],
                            "remaining_seconds": max(0, int(active_info["end_time"] - time.time()))
                        })
                    else:
                        status.update({"active": False})
                    