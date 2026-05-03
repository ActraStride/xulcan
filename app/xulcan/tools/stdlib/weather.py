# app/xulcan/tools/stdlib/weather.py
import asyncio

async def get_weather(city: str) -> dict:
    """Gets the current weather for a given city."""
    # Simulamos una llamada a una API externa que tarda un poco
    await asyncio.sleep(1) 
    
    city_lower = city.lower()
    if "london" in city_lower:
        return {"temp_celsius": 12, "condition": "rainy", "wind_kmh": 25}
    elif "miami" in city_lower:
        return {"temp_celsius": 32, "condition": "sunny", "wind_kmh": 5}
    elif "tokyo" in city_lower:
        return {"temp_celsius": 22, "condition": "cloudy", "wind_kmh": 10}
    else:
        return {"temp_celsius": 20, "condition": "unknown", "wind_kmh": 0}
