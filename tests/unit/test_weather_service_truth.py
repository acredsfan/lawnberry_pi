from backend.src.services.weather_service import WeatherService


def test_planning_advice_is_insufficient_without_rain_and_wind_truth():
    advice = WeatherService().get_planning_advice(
        {
            "temperature_c": 20.0,
            "humidity_percent": 50.0,
            "wind_speed_mps": None,
            "precipitation_mm": None,
        }
    )

    assert advice["advice"] == "insufficient-data"
    assert advice["reasons"] == ["wind-unavailable", "precipitation-unavailable"]


def test_planning_advice_proceeds_only_with_complete_safe_weather():
    advice = WeatherService().get_planning_advice(
        {
            "temperature_c": 20.0,
            "humidity_percent": 50.0,
            "wind_speed_mps": 2.0,
            "precipitation_mm": 0.0,
        }
    )

    assert advice == {"advice": "proceed", "reasons": []}
