import asyncio
import logging
import re

import pytest

from src.hardware.plugin_system import PluginConfig, EnvironmentalSensorPlugin, PowerMonitorPlugin


class DummyI2CManager:
    def __init__(self, responses=None):
        self._responses = responses or {}

    async def read_register(self, addr, reg, length):
        # Return known chip id for BME280 when probed at 0x76
        if (addr, reg) in self._responses:
            return self._responses[(addr, reg)]
        # Default: raise to simulate not-present
        raise Exception("I2C read failed")

    async def write_register(self, addr, reg, data):
        return True


@pytest.mark.asyncio
async def test_environmental_plugin_autodetect_logs(caplog):
    caplog.set_level(logging.DEBUG)
    # Simulate BME280 present at 0x76 returning chip id 0x60 for reg 0xD0
    responses = { (0x76, 0xD0): [0x60] }
    i2c = DummyI2CManager(responses=responses)
    managers = {"i2c": i2c}
    cfg = PluginConfig(name="env1", enabled=True, parameters={"auto_detect_address": True})
    plugin = EnvironmentalSensorPlugin(cfg, managers)

    result = await plugin.initialize()
    assert result is True

    # Ensure logs mention detection at 0x76
    found = any("BME280 detected at 0x76" in r.message for r in caplog.records)
    assert found, "Expected log entry for BME280 autodetect at 0x76"


@pytest.mark.asyncio
async def test_power_monitor_probing_logs(caplog):
    caplog.set_level(logging.DEBUG)
    # Simulate INA3221 present at 0x41 by returning two bytes for reg 0x00
    responses = { (0x41, 0x00): [0x12, 0x34] }
    i2c = DummyI2CManager(responses=responses)
    managers = {"i2c": i2c}
    cfg = PluginConfig(name="power1", enabled=True, parameters={"auto_detect_address": True, "i2c_address": 0x40})
    plugin = PowerMonitorPlugin(cfg, managers)

    result = await plugin.initialize()
    assert result is True

    # Ensure probing logs exist
    probes_logged = any(re.search(r"Probing INA3221 at 0x4[0-3]", r.message) for r in caplog.records)
    assert probes_logged, "Expected INA3221 probe logs"
