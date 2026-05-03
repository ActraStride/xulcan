# app/xulcan/tools/stdlib/sentiment.py
def analyze_mood(weather_condition: str, temp: int) -> dict:
    """Analyzes the general mood of people based on weather conditions."""
    if weather_condition == "sunny" and temp > 25:
        return {"mood": "Very Happy", "activity": "Beach"}
    elif weather_condition == "rainy":
        return {"mood": "Melancholic", "activity": "Reading indoors"}
    else:
        return {"mood": "Neutral", "activity": "Working"}