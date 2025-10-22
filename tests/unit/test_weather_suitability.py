
from backend.src.scheduler.weather_api import WeatherAPI, WeatherCache
from backend.src.scheduler.weather_sensor_fallback import EnvSnapshot, SensorFallbackRules
from backend.src.scheduler.weather_service import WeatherService


def test_weather_api_uses_cache_when_provider_none(tmp_path):
    cache_file = tmp_path / "weather_cache.json"
    cache = WeatherCache(path=cache_file)
    api = WeatherAPI(cache=cache)

    # No cache yet, provider None → None
    f = api.get_forecast(37.0, -122.0, provider=None)
    assert f is None

    # Write cache, then read back
    cache.write({"condition": "clear", "temp_c": 22.0})
    f2 = api.get_forecast(37.0, -122.0, provider=None)
    assert f2 == {"condition": "clear", "temp_c": 22.0}


def test_sensor_fallback_rules_thresholds():
    rules = SensorFallbackRules(max_humidity_percent=85.0, min_pressure_hpa=1000.0)

    # Suitable when within thresholds
    assert rules.is_suitable(
        EnvSnapshot(temperature_c=20.0, humidity_percent=60.0, pressure_hpa=1013.0)
    ) is True

    # High humidity blocks
    assert rules.is_suitable(
        EnvSnapshot(temperature_c=20.0, humidity_percent=90.0, pressure_hpa=1013.0)
    ) is False

    # Low pressure blocks
    assert rules.is_suitable(
        EnvSnapshot(temperature_c=20.0, humidity_percent=60.0, pressure_hpa=990.0)
    ) is False


def test_weather_service_combines_api_and_sensors(tmp_path):
    cache = WeatherCache(path=tmp_path / "weather_cache.json")
    service = WeatherService(api=WeatherAPI(cache=cache))

    # Provider returns explicit unsuitable flag
    def provider_unsuitable(lat, lon):
        return {"unsuitable": True}

    verdict = service.evaluate(
        37.0,
        -122.0,
        EnvSnapshot(20.0, 50.0, 1012.0),
        provider=provider_unsuitable,
    )
    assert verdict.suitable is False
    assert verdict.source == "api_or_cache"

    # No provider, no cache → sensors
    # Remove cache to simulate lack of forecast data
    if cache.path.exists():
        cache.path.unlink()
    verdict2 = service.evaluate(
        37.0,
        -122.0,
        EnvSnapshot(20.0, 50.0, 1012.0),
        provider=None,
    )
    assert verdict2.suitable is True
    assert verdict2.source == "sensors"

    # Predicate should reflect underlying evaluate
    pred = service.make_predicate(
        37.0,
        -122.0,
        lambda: EnvSnapshot(20.0, 90.0, 1012.0),
        provider=None,
    )
    assert pred() is False  # high humidity via sensors
