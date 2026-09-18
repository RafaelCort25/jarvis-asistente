import requests
from skills.base import Skill

# Coordenadas de ciudades comunes (lat, lon)
CITIES = {
    "lima": (-12.0464, -77.0428),
    "bogota": (4.7110, -74.0721),
    "buenos aires": (-34.6037, -58.3816),
    "mexico": (19.4326, -99.1332),
    "madrid": (40.4168, -3.7038),
    "barcelona": (41.3874, 2.1686),
    "santiago": (-33.4489, -70.6693),
    "quito": (-0.1807, -78.4678),
    "caracas": (10.4806, -66.9036),
    "montevideo": (-34.9011, -56.1645),
    "nueva york": (40.7128, -74.0060),
    "new york": (40.7128, -74.0060),
    "paris": (48.8566, 2.3522),
    "londres": (51.5074, -0.1278),
    "tokio": (35.6762, 139.6503),
}

WEATHER_CODES = {
    0: "despejado",
    1: "mayormente despejado", 2: "parcialmente nublado", 3: "nublado",
    45: "niebla", 48: "niebla con escarcha",
    51: "llovizna ligera", 53: "llovizna", 55: "llovizna intensa",
    61: "lluvia ligera", 63: "lluvia moderada", 65: "lluvia fuerte",
    71: "nieve ligera", 73: "nieve moderada", 75: "nieve fuerte",
    80: "chubascos ligeros", 81: "chubascos", 82: "chubascos fuertes",
    95: "tormenta", 96: "tormenta con granizo", 99: "tormenta fuerte",
}


class WeatherSkill(Skill):
    name = "weather"
    description = "Consulta el clima actual de una ciudad"

    def run(self, action, params):
        if action == "current":
            return self._current(params.get("city", "lima"))
        return f"Accion desconocida: {action}"

    def _current(self, city):
        city_lower = city.lower().strip()

        # Buscar en ciudades conocidas
        coords = CITIES.get(city_lower)
        if not coords:
            # Intentar geocodificar con Open-Meteo
            coords = self._geocode(city_lower)
            if not coords:
                return f"No conozco la ciudad '{city}'."

        lat, lon = coords
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
                f"&timezone=auto"
            )
            r = requests.get(url, timeout=10)
            data = r.json()
            cur = data.get("current", {})
            temp = cur.get("temperature_2m", "?")
            humidity = cur.get("relative_humidity_2m", "?")
            wind = cur.get("wind_speed_10m", "?")
            code = cur.get("weather_code", 0)
            desc = WEATHER_CODES.get(code, "desconocido")

            return {
                "thought": f"Consultar clima de {city}",
                "display": (
                    f"🌤️ Clima en {city.title()}:\n"
                    f"  Estado: {desc}\n"
                    f"  Temperatura: {temp}°C\n"
                    f"  Humedad: {humidity}%\n"
                    f"  Viento: {wind} km/h"
                ),
                "voice": f"En {city.title()} esta {desc}, {temp} grados.",
            }
        except Exception as e:
            return f"Error consultando clima: {e}"

    def _geocode(self, city):
        """Convierte nombre de ciudad a coordenadas."""
        try:
            url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=es"
            r = requests.get(url, timeout=10)
            data = r.json()
            results = data.get("results", [])
            if results:
                return (results[0]["latitude"], results[0]["longitude"])
        except Exception:
            pass
        return None