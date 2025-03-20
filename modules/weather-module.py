"""
modules/weather_module.py
------------------------
Module météo pour Alfred, basé sur les implémentations présentes dans les agents domotiques.
Fournit des fonctionnalités de récupération et d'analyse de données météo.
"""

import time
import json
import logging
import datetime
import requests
from typing import Dict, Any, List, Optional, Union, Tuple

from modules.module_interface import WeatherModule, BaseModule

# Configuration du logger
logger = logging.getLogger("WeatherModule")

class WeatherAPIModule(WeatherModule):
    """
    Module météo utilisant principalement l'API WeatherAPI.com,
    avec fallback sur OpenWeatherMap en cas d'erreur.
    """
    
    def __init__(self):
        self.name = "weather"
        self.api_keys = {}
        self.cache = {}
        self.cache_expiry = 3600  # 1 heure
        self.timeout = 10
        self.max_retries = 3
        self.version = "1.0.0"
    
    @property
    def name(self) -> str:
        return self._name
    
    @name.setter
    def name(self, value: str):
        self._name = value
    
    def initialize(self) -> bool:
        """
        Initialise le module météo avec les API configurées.
        
        Returns:
            True si au moins une API est configurée, False sinon
        """
        # Charger la configuration
        try:
            config_file = "config/weather_config.json"
            with open(config_file, 'r') as f:
                config = json.load(f)
                self.api_keys = config.get("api_keys", {})
                self.cache_expiry = config.get("cache_expiry", 3600)
                self.timeout = config.get("timeout", 10)
                self.max_retries = config.get("max_retries", 3)
                
                logger.info(f"Module météo initialisé avec {len(self.api_keys)} API configurées")
                return len(self.api_keys) > 0
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du module météo: {e}")
            
                            # Valeurs par défaut pour permettre les tests
            self.api_keys = {
                "weatherapi": "YOUR_WEATHERAPI_KEY",
                "openweathermap": "YOUR_OPENWEATHERMAP_KEY"
            }
            return True
    
    def shutdown(self) -> bool:
        """
        Arrête proprement le module météo.
        
        Returns:
            True, car il n'y a pas d'action particulière à effectuer
        """
        self.cache = {}  # Vider le cache
        logger.info("Module météo arrêté")
        return True
    
    def get_current_weather(self, location: str) -> Dict[str, Any]:
        """
        Récupère les conditions météo actuelles pour une localisation donnée.
        
        Args:
            location: Localisation (ville, coordonnées, etc.)
            
        Returns:
            Dictionnaire contenant les infos météo
        """
        # Vérifier le cache
        cache_key = f"current_{location}"
        if cache_key in self.cache:
            cache_time, data = self.cache[cache_key]
            if time.time() - cache_time < self.cache_expiry:
                logger.debug(f"Données météo pour {location} récupérées depuis le cache")
                return data
        
        # Essayer d'abord WeatherAPI
        if "weatherapi" in self.api_keys:
            try:
                data = self._get_from_weatherapi(location)
                if data:
                    # Normaliser les données
                    result = self._normalize_weather_data(data, "weatherapi")
                    # Mettre en cache
                    self.cache[cache_key] = (time.time(), result)
                    return result
            except Exception as e:
                logger.warning(f"Erreur lors de la récupération depuis WeatherAPI: {e}")
        
        # Fallback sur OpenWeatherMap
        if "openweathermap" in self.api_keys:
            try:
                data = self._get_from_openweathermap(location)
                if data:
                    # Normaliser les données
                    result = self._normalize_weather_data(data, "openweathermap")
                    # Mettre en cache
                    self.cache[cache_key] = (time.time(), result)
                    return result
            except Exception as e:
                logger.warning(f"Erreur lors de la récupération depuis OpenWeatherMap: {e}")
        
        # En cas d'échec complet
        logger.error(f"Impossible de récupérer les données météo pour {location}")
        return {"error": "Données météo non disponibles", "location": location}
    
    def get_forecast(self, location: str, days: int = 5) -> List[Dict[str, Any]]:
        """
        Récupère les prévisions météo pour une localisation donnée.
        
        Args:
            location: Localisation (ville, coordonnées, etc.)
            days: Nombre de jours de prévision
            
        Returns:
            Liste de dictionnaires contenant les prévisions
        """
        # Vérifier le cache
        cache_key = f"forecast_{location}_{days}"
        if cache_key in self.cache:
            cache_time, data = self.cache[cache_key]
            if time.time() - cache_time < self.cache_expiry:
                logger.debug(f"Prévisions météo pour {location} récupérées depuis le cache")
                return data
        
        # Limiter le nombre de jours
        days = min(max(days, 1), 10)  # Entre 1 et 10 jours
        
        # Essayer d'abord WeatherAPI
        if "weatherapi" in self.api_keys:
            try:
                data = self._get_from_weatherapi(location, forecast=True, days=days)
                if data and "forecast" in data:
                    # Normaliser les données
                    result = self._normalize_forecast_data(data, "weatherapi", days)
                    # Mettre en cache
                    self.cache[cache_key] = (time.time(), result)
                    return result
            except Exception as e:
                logger.warning(f"Erreur lors de la récupération des prévisions depuis WeatherAPI: {e}")
        
        # Fallback sur OpenWeatherMap
        if "openweathermap" in self.api_keys:
            try:
                data = self._get_from_openweathermap(location, forecast=True)
                if data:
                    # Normaliser les données
                    result = self._normalize_forecast_data(data, "openweathermap", days)
                    # Mettre en cache
                    self.cache[cache_key] = (time.time(), result)
                    return result
            except Exception as e:
                logger.warning(f"Erreur lors de la récupération des prévisions depuis OpenWeatherMap: {e}")
        
        # En cas d'échec complet
        logger.error(f"Impossible de récupérer les prévisions météo pour {location}")
        return []
    
    def check_rain_forecast(self, location: str, hours: int = 24) -> bool:
        """
        Vérifie s'il va pleuvoir dans les prochaines heures.
        
        Args:
            location: Localisation (ville, coordonnées, etc.)
            hours: Nombre d'heures à vérifier
            
        Returns:
            True s'il va pleuvoir, False sinon
        """
        # Vérifier le cache
        cache_key = f"rain_{location}_{hours}"
        if cache_key in self.cache:
            cache_time, data = self.cache[cache_key]
            if time.time() - cache_time < self.cache_expiry:
                logger.debug(f"Prévision de pluie pour {location} récupérée depuis le cache")
                return data
        
        # Limiter le nombre d'heures
        hours = min(max(hours, 1), 48)  # Entre 1 et 48 heures
        
        # Vérifier la pluie dans les prévisions
        forecast = self.get_forecast(location, days=2)  # 2 jours max
        rain_expected = False
        now = datetime.datetime.now()
        
        for day_forecast in forecast:
            forecast_time = day_forecast.get("datetime")
            if forecast_time:
                if isinstance(forecast_time, str):
                    forecast_time = datetime.datetime.fromisoformat(forecast_time.replace('Z', '+00:00'))
                
                # Vérifier si la prévision est dans la fenêtre demandée
                time_diff = (forecast_time - now).total_seconds() / 3600
                if 0 <= time_diff <= hours:
                    # Vérifier s'il pleut
                    condition = day_forecast.get("condition", {}).get("text", "").lower()
                    precipitation = day_forecast.get("precipitation", 0)
                    
                    if ("rain" in condition or "drizzle" in condition or "shower" in condition or 
                        "thunderstorm" in condition or precipitation > 0.5):
                        rain_expected = True
                        break
        
        # Mettre en cache
        self.cache[cache_key] = (time.time(), rain_expected)
        return rain_expected
    
    def _get_from_weatherapi(self, location: str, forecast: bool = False, days: int = 1) -> Dict[str, Any]:
        """
        Récupère les données depuis WeatherAPI.com.
        
        Args:
            location: Localisation
            forecast: True pour les prévisions, False pour le temps actuel
            days: Nombre de jours de prévision (si forecast=True)
            
        Returns:
            Données météo brutes
        """
        api_key = self.api_keys.get("weatherapi")
        if not api_key:
            raise ValueError("Clé API WeatherAPI manquante")
        
        endpoint = "forecast.json" if forecast else "current.json"
        url = f"https://api.weatherapi.com/v1/{endpoint}"
        
        params = {
            "key": api_key,
            "q": location,
            "days": days,
            "aqi": "yes",
            "alerts": "yes"
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.warning(f"Tentative {attempt+1}/{self.max_retries} échouée: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Backoff exponentiel
        
        return None
    
    def _get_from_openweathermap(self, location: str, forecast: bool = False) -> Dict[str, Any]:
        """
        Récupère les données depuis OpenWeatherMap.
        
        Args:
            location: Localisation
            forecast: True pour les prévisions, False pour le temps actuel
            
        Returns:
            Données météo brutes
        """
        api_key = self.api_keys.get("openweathermap")
        if not api_key:
            raise ValueError("Clé API OpenWeatherMap manquante")
        
        endpoint = "forecast" if forecast else "weather"
        url = f"https://api.openweathermap.org/data/2.5/{endpoint}"
        
        params = {
            "q": location,
            "appid": api_key,
            "units": "metric"
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.warning(f"Tentative {attempt+1}/{self.max_retries} échouée: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Backoff exponentiel
        
        return None
    
    def _normalize_weather_data(self, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        """
        Normalise les données météo dans un format standard.
        
        Args:
            data: Données brutes
            source: Source des données (weatherapi, openweathermap)
            
        Returns:
            Données normalisées
        """
        if source == "weatherapi":
            current = data.get("current", {})
            location = data.get("location", {})
            
            return {
                "location": {
                    "name": location.get("name"),
                    "region": location.get("region"),
                    "country": location.get("country"),
                    "lat": location.get("lat"),
                    "lon": location.get("lon"),
                    "timezone": location.get("tz_id")
                },
                "current": {
                    "temperature": current.get("temp_c"),
                    "temperature_feels_like": current.get("feelslike_c"),
                    "humidity": current.get("humidity"),
                    "wind_speed": current.get("wind_kph"),
                    "wind_direction": current.get("wind_dir"),
                    "pressure": current.get("pressure_mb"),
                    "precipitation": current.get("precip_mm"),
                    "cloud": current.get("cloud"),
                    "uv": current.get("uv"),
                    "condition": {
                        "text": current.get("condition", {}).get("text"),
                        "code": current.get("condition", {}).get("code"),
                        "icon": current.get("condition", {}).get("icon")
                    },
                    "is_day": current.get("is_day") == 1,
                    "last_updated": current.get("last_updated")
                }
            }
        
        elif source == "openweathermap":
            main = data.get("main", {})
            weather = data.get("weather", [{}])[0] if data.get("weather") else {}
            wind = data.get("wind", {})
            
            return {
                "location": {
                    "name": data.get("name"),
                    "region": None,
                    "country": data.get("sys", {}).get("country"),
                    "lat": data.get("coord", {}).get("lat"),
                    "lon": data.get("coord", {}).get("lon"),
                    "timezone": None
                },
                "current": {
                    "temperature": main.get("temp"),
                    "temperature_feels_like": main.get("feels_like"),
                    "humidity": main.get("humidity"),
                    "wind_speed": wind.get("speed") * 3.6 if wind.get("speed") is not None else None,  # m/s à km/h
                    "wind_direction": self._wind_degree_to_direction(wind.get("deg")),
                    "pressure": main.get("pressure"),
                    "precipitation": data.get("rain", {}).get("1h", 0) + data.get("snow", {}).get("1h", 0),
                    "cloud": data.get("clouds", {}).get("all"),
                    "uv": None,
                    "condition": {
                        "text": weather.get("description"),
                        "code": weather.get("id"),
                        "icon": f"http://openweathermap.org/img/wn/{weather.get('icon')}@2x.png" if weather.get("icon") else None
                    },
                    "is_day": "d" in weather.get("icon", "") if weather.get("icon") else True,
                    "last_updated": datetime.datetime.fromtimestamp(data.get("dt", 0)).isoformat() if data.get("dt") else None
                }
            }
        
        else:
            logger.warning(f"Source non supportée: {source}")
            return {}
    
    def _normalize_forecast_data(self, data: Dict[str, Any], source: str, days: int) -> List[Dict[str, Any]]:
        """
        Normalise les données de prévision dans un format standard.
        
        Args:
            data: Données brutes
            source: Source des données (weatherapi, openweathermap)
            days: Nombre de jours de prévision
            
        Returns:
            Liste de prévisions normalisées
        """
        result = []
        
        if source == "weatherapi":
            forecast_days = data.get("forecast", {}).get("forecastday", [])
            for day_data in forecast_days[:days]:
                day = day_data.get("day", {})
                astro = day_data.get("astro", {})
                
                # Prévisions par heure
                hours = []
                for hour_data in day_data.get("hour", []):
                    hour = {
                        "time": hour_data.get("time"),
                        "temperature": hour_data.get("temp_c"),
                        "temperature_feels_like": hour_data.get("feelslike_c"),
                        "humidity": hour_data.get("humidity"),
                        "wind_speed": hour_data.get("wind_kph"),
                        "wind_direction": hour_data.get("wind_dir"),
                        "pressure": hour_data.get("pressure_mb"),
                        "precipitation": hour_data.get("precip_mm"),
                        "precipitation_chance": hour_data.get("chance_of_rain"),
                        "cloud": hour_data.get("cloud"),
                        "condition": {
                            "text": hour_data.get("condition", {}).get("text"),
                            "code": hour_data.get("condition", {}).get("code"),
                            "icon": hour_data.get("condition", {}).get("icon")
                        },
                        "is_day": hour_data.get("is_day") == 1
                    }
                    hours.append(hour)
                
                # Prévision journalière
                forecast = {
                    "date": day_data.get("date"),
                    "datetime": f"{day_data.get('date')}T00:00:00",
                    "temperature_max": day.get("maxtemp_c"),
                    "temperature_min": day.get("mintemp_c"),
                    "temperature_avg": day.get("avgtemp_c"),
                    "humidity": day.get("avghumidity"),
                    "wind_speed": day.get("maxwind_kph"),
                    "precipitation": day.get("totalprecip_mm"),
                    "precipitation_chance": day.get("daily_chance_of_rain"),
                    "condition": {
                        "text": day.get("condition", {}).get("text"),
                        "code": day.get("condition", {}).get("code"),
                        "icon": day.get("condition", {}).get("icon")
                    },
                    "sunrise": astro.get("sunrise"),
                    "sunset": astro.get("sunset"),
                    "hours": hours
                }
                result.append(forecast)
        
        elif source == "openweathermap":
            # OpenWeatherMap fournit des prévisions par tranches de 3 heures
            forecast_list = data.get("list", [])
            
            # Grouper par jour
            forecasts_by_day = {}
            for item in forecast_list:
                dt = datetime.datetime.fromtimestamp(item.get("dt", 0))
                date_key = dt.strftime("%Y-%m-%d")
                
                if date_key not in forecasts_by_day:
                    forecasts_by_day[date_key] = {
                        "date": date_key,
                        "hours": [],
                        "temperature_max": -float("inf"),
                        "temperature_min": float("inf"),
                        "temperature_avg": 0,
                        "precipitation": 0,
                        "precipitation_chance": 0,
                        "wind_speeds": [],
                        "humidities": []
                    }
                
                # Données horaires
                main = item.get("main", {})
                weather = item.get("weather", [{}])[0] if item.get("weather") else {}
                wind = item.get("wind", {})
                
                hour = {
                    "time": dt.isoformat(),
                    "temperature": main.get("temp"),
                    "temperature_feels_like": main.get("feels_like"),
                    "humidity": main.get("humidity"),
                    "wind_speed": wind.get("speed") * 3.6 if wind.get("speed") is not None else None,  # m/s à km/h
                    "wind_direction": self._wind_degree_to_direction(wind.get("deg")),
                    "pressure": main.get("pressure"),
                    "precipitation": item.get("rain", {}).get("3h", 0) + item.get("snow", {}).get("3h", 0),
                    "precipitation_chance": item.get("pop", 0) * 100 if item.get("pop") is not None else 0,
                    "cloud": item.get("clouds", {}).get("all"),
                    "condition": {
                        "text": weather.get("description"),
                        "code": weather.get("id"),
                        "icon": f"http://openweathermap.org/img/wn/{weather.get('icon')}@2x.png" if weather.get("icon") else None
                    },
                    "is_day": "d" in weather.get("icon", "") if weather.get("icon") else True
                }
                
                # Mettre à jour les statistiques journalières
                day_data = forecasts_by_day[date_key]
                day_data["hours"].append(hour)
                day_data["temperature_max"] = max(day_data["temperature_max"], main.get("temp_max", -float("inf")))
                day_data["temperature_min"] = min(day_data["temperature_min"], main.get("temp_min", float("inf")))
                day_data["wind_speeds"].append(hour["wind_speed"] if hour["wind_speed"] is not None else 0)
                day_data["humidities"].append(main.get("humidity", 0))
                day_data["precipitation"] += hour["precipitation"]
                day_data["precipitation_chance"] = max(day_data["precipitation_chance"], hour["precipitation_chance"])
            
            # Finaliser les statistiques journalières
            for date_key, day_data in forecasts_by_day.items():
                day_data["temperature_avg"] = sum(h["temperature"] for h in day_data["hours"]) / len(day_data["hours"]) if day_data["hours"] else None
                day_data["humidity"] = sum(day_data["humidities"]) / len(day_data["humidities"]) if day_data["humidities"] else None
                day_data["wind_speed"] = max(day_data["wind_speeds"]) if day_data["wind_speeds"] else None
                
                # Choisir la condition la plus représentative (milieu de journée)
                if day_data["hours"]:
                    middle_index = len(day_data["hours"]) // 2
                    day_data["condition"] = day_data["hours"][middle_index]["condition"]
                
                # Supprimer les champs temporaires
                del day_data["wind_speeds"]
                del day_data["humidities"]
                
                # Ajouter aux résultats
                day_data["datetime"] = f"{date_key}T00:00:00"
                day_data["sunrise"] = None  # OpenWeatherMap ne fournit pas directement ces informations
                day_data["sunset"] = None   # dans l'API de prévision
                result.append(day_data)
            
            # Limiter au nombre de jours demandés
            result = sorted(result, key=lambda x: x["date"])[:days]
        
        else:
            logger.warning(f"Source non supportée: {source}")
        
        return result
    
    def _wind_degree_to_direction(self, degrees: Optional[float]) -> Optional[str]:
        """
        Convertit un angle en degrés en direction du vent.
        
        Args:
            degrees: Angle en degrés
            
        Returns:
            Direction du vent (N, NE, E, etc.) ou None si degrees est None
        """
        if degrees is None:
            return None
            
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        
        # Diviser 360 degrés en 16 sections de 22.5 degrés
        index = round(degrees / 22.5) % 16
        return directions[index]
