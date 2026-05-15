"""Tests that BME280 init failure is logged, not silently swallowed."""
import asyncio
import pytest
import logging
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_bme280_init_failure_is_logged(caplog):
    import os
    os.environ["SIM_MODE"] = "0"
    try:
        from backend.src.drivers.sensors.bme280_driver import BME280Driver
        drv = BME280Driver({"address": 0x76, "bus": 1})

        # Simulate smbus2.SMBus raising on read_i2c_block_data.
        # The driver imports SMBus inside initialize() via 'from smbus2 import SMBus',
        # so we patch smbus2.SMBus at the source module level.
        mock_bus_instance = MagicMock()
        mock_bus_instance.__enter__ = MagicMock(return_value=mock_bus_instance)
        mock_bus_instance.__exit__ = MagicMock(return_value=False)
        mock_bus_instance.read_i2c_block_data = MagicMock(side_effect=OSError("I2C read error"))
        mock_smbus2 = MagicMock()
        mock_smbus2.SMBus = MagicMock(return_value=mock_bus_instance)

        with patch.dict("sys.modules", {"smbus2": mock_smbus2}):
            with caplog.at_level(logging.WARNING):
                await drv.initialize()

        assert drv._calibration is None
        assert any("BME280" in r.message or "calibration" in r.message.lower() for r in caplog.records), \
            f"Expected BME280 warning in logs, got: {[r.message for r in caplog.records]}"
    finally:
        os.environ.pop("SIM_MODE", None)
