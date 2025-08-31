"""
Comprehensive tests for the Power Management System
Tests battery monitoring, solar charging, sunny spot navigation, and power optimization.
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from dataclasses import asdict
from typing import List, Dict, Any

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.power_management.power_manager import (
    PowerManager, PowerMode, ChargingMode, BatteryMetrics, 
    SolarMetrics, PowerConsumption, SunnySpot
)
from src.power_management.power_service import PowerService


class TestPowerManager:
    """Test cases for PowerManager class"""
    
    @pytest.fixture
    async def power_manager(self):
        """Create PowerManager instance with mocked dependencies"""
        hardware_mock = AsyncMock()
        mqtt_mock = AsyncMock()
        cache_mock = AsyncMock()
        weather_mock = AsyncMock()
        
        # Mock hardware sensor data
        hardware_mock.get_sensor_data.return_value = MagicMock(
            voltage=12.5,
            current=-2.0,
            power=-25.0,
            temperature=25.0
        )
        
        # Mock cache operations
        cache_mock.get.return_value = {"soc": 0.7, "timestamp": datetime.now().isoformat()}
        cache_mock.set.return_value = True
        
        # Mock MQTT operations
        mqtt_mock.publish.return_value = True
        mqtt_mock.subscribe.return_value = True
        
        manager = PowerManager(
            hardware_interface=hardware_mock,
            mqtt_client=mqtt_mock,
            cache_manager=cache_mock,
            weather_service=weather_mock
        )
        
        yield manager
        
        # Cleanup
        if manager._initialized:
            await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_power_manager_initialization(self, power_manager):
        """Test power manager initialization"""
        assert not power_manager._initialized
        
        # Initialize
        result = await power_manager.initialize()
        assert result is True
        assert power_manager._initialized is True
        
        # Check that monitoring tasks are started
        assert power_manager._monitoring_task is not None
        assert power_manager._optimization_task is not None
        assert power_manager._sunny_spot_task is not None
    
    @pytest.mark.asyncio
    async def test_battery_monitoring(self, power_manager):
        """Test battery metrics calculation and monitoring"""
        await power_manager.initialize()
        
        # Mock power data
        mock_power_data = MagicMock()
        mock_power_data.voltage = 12.8
        mock_power_data.current = -1.5
        mock_power_data.power = -19.2
        
        # Update battery metrics
        await power_manager._update_battery_metrics(mock_power_data)
        
        # Check metrics
        battery = power_manager.battery_metrics
        assert battery.voltage == 12.8
        assert battery.current == -1.5
        assert battery.power == -19.2
        assert 0.0 <= battery.state_of_charge <= 1.0
        assert battery.time_remaining is not None
    
    @pytest.mark.asyncio
    async def test_soc_calculation_from_voltage(self, power_manager):
        """Test State of Charge calculation from voltage"""
        # Test various voltage levels
        test_cases = [
            (10.0, 0.0),    # Minimum voltage
            (12.0, 0.2),    # 20% charge
            (12.8, 0.5),    # 50% charge (nominal)
            (13.2, 0.8),    # 80% charge
            (14.0, 1.0),    # Full charge
        ]
        
        for voltage, expected_soc in test_cases:
            soc = power_manager._calculate_soc_from_voltage(voltage)
            assert abs(soc - expected_soc) < 0.1, f"Voltage {voltage}V should give ~{expected_soc} SoC, got {soc}"
    
    @pytest.mark.asyncio
    async def test_solar_data_estimation(self, power_manager):
        """Test solar power estimation based on time and weather"""
        await power_manager.initialize()
        
        # Test during peak solar hours (noon)
        with patch('src.power_management.power_manager.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 6, 15, 12, 0)  # Noon
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            solar_data = await power_manager._read_solar_data()
            
            assert solar_data is not None
            assert solar_data['power'] > 0
            assert solar_data['voltage'] > 0
            assert solar_data['current'] > 0
        
        # Test during night (should return None)
        with patch('src.power_management.power_manager.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 6, 15, 2, 0)  # 2 AM
            
            solar_data = await power_manager._read_solar_data()
            assert solar_data is None
    
    @pytest.mark.asyncio
    async def test_power_mode_determination(self, power_manager):
        """Test automatic power mode determination"""
        await power_manager.initialize()
        
        # Test emergency mode (critical battery)
        power_manager.battery_metrics.state_of_charge = 0.03
        mode = await power_manager._determine_optimal_power_mode()
        assert mode == PowerMode.EMERGENCY_MODE
        
        # Test charging mode (low battery + solar available)
        power_manager.battery_metrics.state_of_charge = 0.15
        power_manager.solar_metrics.power = 20.0
        mode = await power_manager._determine_optimal_power_mode()
        assert mode == PowerMode.CHARGING_MODE
        
        # Test eco mode (low battery)
        power_manager.battery_metrics.state_of_charge = 0.15
        power_manager.solar_metrics.power = 2.0
        mode = await power_manager._determine_optimal_power_mode()
        assert mode == PowerMode.ECO_MODE
        
        # Test high performance mode (good battery)
        power_manager.battery_metrics.state_of_charge = 0.85
        mode = await power_manager._determine_optimal_power_mode()
        assert mode == PowerMode.HIGH_PERFORMANCE
    
    @pytest.mark.asyncio
    async def test_sunny_spot_creation(self, power_manager):
        """Test sunny spot creation and management"""
        await power_manager.initialize()
        
        # Mock GPS data
        mock_gps = MagicMock()
        mock_gps.latitude = 40.7128
        mock_gps.longitude = -74.0060
        power_manager.hardware.get_sensor_data.return_value = mock_gps
        
        # Set good solar conditions
        power_manager.solar_metrics.power = 25.0
        power_manager.solar_metrics.efficiency = 0.8
        
        # Update sunny spot data
        await power_manager._update_sunny_spot_data()
        
        # Check that a sunny spot was created
        assert len(power_manager.sunny_spots) == 1
        spot = power_manager.sunny_spots[0]
        assert spot.latitude == 40.7128
        assert spot.longitude == -74.0060
        assert spot.efficiency_rating == 0.8
    
    @pytest.mark.asyncio
    async def test_sunny_spot_finding(self, power_manager):
        """Test finding the best sunny spot"""
        await power_manager.initialize()
        
        # Create test sunny spots
        current_hour = datetime.now().hour
        
        spot1 = SunnySpot(
            latitude=40.7128,
            longitude=-74.0060,
            efficiency_rating=0.7,
            last_measured=datetime.now(),
            time_of_day_optimal=[current_hour],
            seasonal_factor=1.0
        )
        
        spot2 = SunnySpot(
            latitude=40.7500,
            longitude=-73.9857,
            efficiency_rating=0.9,
            last_measured=datetime.now() - timedelta(hours=2),
            time_of_day_optimal=[current_hour - 1],
            seasonal_factor=0.8
        )
        
        power_manager.sunny_spots = [spot1, spot2]
        
        # Find best spot
        best_spot = await power_manager._find_best_sunny_spot()
        
        # Should prefer spot1 due to current time optimization
        assert best_spot == spot1
    
    @pytest.mark.asyncio
    async def test_distance_calculation(self, power_manager):
        """Test GPS distance calculation"""
        # Test known distance (approximately 1 degree = 111km)
        lat1, lon1 = 40.0, -74.0
        lat2, lon2 = 41.0, -74.0  # 1 degree north
        
        distance = power_manager._calculate_distance(lat1, lon1, lat2, lon2)
        
        # Should be approximately 111,320 meters
        assert 110000 < distance < 112000
    
    @pytest.mark.asyncio
    async def test_power_consumption_calculation(self, power_manager):
        """Test power consumption estimation"""
        await power_manager.initialize()
        
        # Mock active sensors
        power_manager.hardware.get_all_sensor_data.return_value = {
            'sensor1': MagicMock(timestamp=datetime.now()),
            'sensor2': MagicMock(timestamp=datetime.now()),
            'sensor3': MagicMock(timestamp=datetime.now())
        }
        
        # Test high performance mode
        power_manager.current_mode = PowerMode.HIGH_PERFORMANCE
        await power_manager._calculate_power_consumption()
        
        consumption = power_manager.power_consumption
        assert consumption.total > 0
        assert consumption.cpu > 0
        assert consumption.sensors > 0
        
        # Test eco mode (should be less power)
        power_manager.current_mode = PowerMode.ECO_MODE
        await power_manager._calculate_power_consumption()
        
        eco_consumption = power_manager.power_consumption
        assert eco_consumption.cpu < consumption.cpu
    
    @pytest.mark.asyncio
    async def test_safety_checks(self, power_manager):
        """Test safety monitoring and alerts"""
        await power_manager.initialize()
        
        # Test critical battery alert
        power_manager.battery_metrics.state_of_charge = 0.03
        power_manager.battery_metrics.voltage = 10.5
        power_manager.battery_metrics.temperature = 55.0
        
        await power_manager._perform_safety_checks()
        
        # Verify MQTT alerts were published
        power_manager.mqtt.publish.assert_called()
        
        # Check if any calls were made to safety topics
        safety_calls = [
            call for call in power_manager.mqtt.publish.call_args_list
            if 'safety/' in str(call[0][0])
        ]
        assert len(safety_calls) > 0
    
    @pytest.mark.asyncio
    async def test_charging_mode_switching(self, power_manager):
        """Test charging mode changes"""
        await power_manager.initialize()
        
        # Test setting different charging modes
        modes = ['auto', 'manual', 'eco']
        
        for mode in modes:
            result = await power_manager.set_charging_mode(mode)
            assert result is True
            assert power_manager.charging_mode == ChargingMode(mode)
        
        # Test invalid mode
        result = await power_manager.set_charging_mode('invalid')
        assert result is False
    
    @pytest.mark.asyncio
    async def test_power_saving_mode(self, power_manager):
        """Test power saving mode functionality"""
        await power_manager.initialize()
        
        # Enable power saving
        await power_manager.enable_power_saving(True)
        assert power_manager.power_saving_enabled is True
        
        # Disable power saving
        await power_manager.enable_power_saving(False)
        assert power_manager.power_saving_enabled is False
    
    @pytest.mark.asyncio
    async def test_coulomb_counting(self, power_manager):
        """Test coulomb counting for SoC estimation"""
        await power_manager.initialize()
        
        # Mock cache with previous SoC data
        power_manager.cache.get.return_value = {
            'soc': 0.5,
            'timestamp': (datetime.now() - timedelta(seconds=5)).isoformat()
        }
        
        # Test with discharge current
        current = -2.0  # 2A discharge
        voltage_soc = 0.45  # Voltage-based SoC
        
        result_soc = await power_manager._update_coulomb_counting(current, voltage_soc)
        
        # SoC should be updated based on current and time
        assert isinstance(result_soc, float)
        assert 0.0 <= result_soc <= 1.0
    
    @pytest.mark.asyncio
    async def test_time_remaining_estimation(self, power_manager):
        """Test battery time remaining estimation"""
        # Test with discharge current
        current = -2.0  # 2A discharge
        soc = 0.6  # 60% charge
        
        time_remaining = power_manager._estimate_time_remaining(current, soc)
        
        # Should return time in minutes
        assert isinstance(time_remaining, int)
        assert time_remaining > 0
        
        # Test with charging current (should return None)
        current = 1.0  # 1A charge
        time_remaining = power_manager._estimate_time_remaining(current, soc)
        assert time_remaining is None
    
    @pytest.mark.asyncio
    async def test_seasonal_factor_calculation(self, power_manager):
        """Test seasonal adjustment factor"""
        # Test summer solstice (day 172)
        with patch('src.power_management.power_manager.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 6, 21)  # Summer solstice
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            factor = power_manager._calculate_seasonal_factor()
            assert 0.8 < factor <= 1.0  # Should be near maximum
        
        # Test winter solstice (day 355)
        with patch('src.power_management.power_manager.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 12, 21)  # Winter solstice
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            factor = power_manager._calculate_seasonal_factor()
            assert 0.3 <= factor < 0.5  # Should be near minimum


class TestPowerService:
    """Test cases for PowerService class"""
    
    @pytest.fixture
    async def power_service(self):
        """Create PowerService instance with mocked dependencies"""
        mqtt_mock = AsyncMock()
        cache_mock = AsyncMock()
        hardware_mock = AsyncMock()
        weather_mock = AsyncMock()
        
        # Mock basic operations
        mqtt_mock.subscribe.return_value = True
        mqtt_mock.publish.return_value = True
        cache_mock.get.return_value = None
        cache_mock.set.return_value = True
        
        service = PowerService(
            mqtt_client=mqtt_mock,
            cache_manager=cache_mock,
            hardware_interface=hardware_mock,
            weather_service=weather_mock
        )
        
        yield service
        
        # Cleanup
        if service._initialized:
            await service.shutdown()
    
    @pytest.mark.asyncio
    async def test_power_service_initialization(self, power_service):
        """Test power service initialization"""
        assert not power_service._initialized
        
        with patch.object(power_service.power_manager, 'initialize', return_value=True):
            result = await power_service.initialize()
            assert result is True
            assert power_service._initialized is True
    
    @pytest.mark.asyncio
    async def test_service_health_check(self, power_service):
        """Test service health monitoring"""
        await power_service.initialize()
        
        # Mock power status
        mock_status = {
            "battery": {"state_of_charge": 0.75},
            "solar": {"power": 15.0},
            "mode": "high_performance",
            "sunny_spots_count": 5
        }
        
        with patch.object(power_service.power_manager, 'get_power_status', return_value=mock_status):
            health = await power_service._get_health_status()
            
            assert isinstance(health, dict)
            assert 'healthy' in health
            assert 'components' in health
            assert 'metrics' in health
    
    @pytest.mark.asyncio
    async def test_power_command_handling(self, power_service):
        """Test handling of power management commands"""
        await power_service.initialize()
        
        # Test charging mode command
        command_payload = {
            'command': 'set_charging_mode',
            'mode': 'eco'
        }
        
        with patch.object(power_service.power_manager, 'set_charging_mode', return_value=True) as mock_set:
            await power_service._handle_power_command("commands/power", command_payload)
            mock_set.assert_called_once_with('eco')
    
    @pytest.mark.asyncio
    async def test_critical_condition_monitoring(self, power_service):
        """Test monitoring for critical power conditions"""
        await power_service.initialize()
        
        # Mock critical battery condition
        mock_status = {
            "battery": {
                "state_of_charge": 0.03,  # Critical level
                "voltage": 10.5,
                "temperature": 25.0,
                "time_remaining": 5
            },
            "solar": {"power": 0.0}
        }
        
        with patch.object(power_service.power_manager, 'get_power_status', return_value=mock_status):
            await power_service._check_critical_conditions()
            
            # Should have published alert
            power_service.mqtt.publish.assert_called()
            
            # Check for critical alert
            critical_calls = [
                call for call in power_service.mqtt.publish.call_args_list
                if 'alerts/critical' in str(call[0][0])
            ]
            assert len(critical_calls) > 0


class TestIntegration:
    """Integration tests for power management system"""
    
    @pytest.mark.asyncio
    async def test_full_power_cycle_simulation(self):
        """Test complete power management cycle"""
        # Create mocked components
        hardware_mock = AsyncMock()
        mqtt_mock = AsyncMock()
        cache_mock = AsyncMock()
        
        # Mock sensor readings for discharge cycle
        power_readings = [
            {'voltage': 13.2, 'current': -2.0, 'power': -26.4},  # High load
            {'voltage': 12.8, 'current': -1.5, 'power': -19.2},  # Normal load  
            {'voltage': 12.0, 'current': -1.0, 'power': -12.0},  # Low battery
            {'voltage': 11.5, 'current': -0.5, 'power': -5.75},  # Critical
        ]
        
        power_manager = PowerManager(
            hardware_interface=hardware_mock,
            mqtt_client=mqtt_mock,
            cache_manager=cache_mock
        )
        
        try:
            await power_manager.initialize()
            
            # Simulate power readings over time
            for i, reading in enumerate(power_readings):
                mock_data = MagicMock()
                mock_data.voltage = reading['voltage']
                mock_data.current = reading['current']
                mock_data.power = reading['power']
                
                hardware_mock.get_sensor_data.return_value = mock_data
                
                # Update battery metrics
                await power_manager._update_battery_metrics(mock_data)
                
                # Check power mode adaptation
                optimal_mode = await power_manager._determine_optimal_power_mode()
                
                if i == 0:  # High battery
                    assert optimal_mode in [PowerMode.HIGH_PERFORMANCE, PowerMode.ECO_MODE]
                elif i == len(power_readings) - 1:  # Critical battery
                    assert optimal_mode == PowerMode.EMERGENCY_MODE
                
                # Verify safety checks
                await power_manager._perform_safety_checks()
                
                # Verify MQTT publishing
                await power_manager._publish_power_data()
            
            # Final verification
            assert power_manager.battery_metrics.voltage == 11.5
            assert power_manager.current_mode == PowerMode.EMERGENCY_MODE
            
        finally:
            await power_manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_sunny_spot_learning_cycle(self):
        """Test complete sunny spot learning and navigation cycle"""
        hardware_mock = AsyncMock()
        mqtt_mock = AsyncMock()
        cache_mock = AsyncMock()
        
        power_manager = PowerManager(
            hardware_interface=hardware_mock,
            mqtt_client=mqtt_mock,
            cache_manager=cache_mock
        )
        
        try:
            await power_manager.initialize()
            
            # Simulate GPS positions with varying solar efficiency
            test_positions = [
                {'lat': 40.7128, 'lon': -74.0060, 'solar_power': 25.0, 'efficiency': 0.85},
                {'lat': 40.7130, 'lon': -74.0065, 'solar_power': 15.0, 'efficiency': 0.50},
                {'lat': 40.7125, 'lon': -74.0055, 'solar_power': 28.0, 'efficiency': 0.95},
            ]
            
            for pos in test_positions:
                # Mock GPS data
                mock_gps = MagicMock()
                mock_gps.latitude = pos['lat']
                mock_gps.longitude = pos['lon']
                hardware_mock.get_sensor_data.return_value = mock_gps
                
                # Set solar conditions
                power_manager.solar_metrics.power = pos['solar_power']
                power_manager.solar_metrics.efficiency = pos['efficiency']
                
                # Update sunny spot data
                await power_manager._update_sunny_spot_data()
            
            # Verify sunny spots were created
            assert len(power_manager.sunny_spots) == 3
            
            # Find best spot
            best_spot = await power_manager._find_best_sunny_spot()
            assert best_spot is not None
            assert best_spot.efficiency_rating >= 0.85  # Should be the best one
            
            # Test navigation to sunny spot
            power_manager.battery_metrics.state_of_charge = 0.15  # Low battery
            await power_manager._navigate_to_sunny_spot(best_spot)
            
            # Verify navigation command was sent
            mqtt_mock.publish.assert_called()
            nav_calls = [
                call for call in mqtt_mock.publish.call_args_list
                if 'commands/navigation' in str(call[0][0])
            ]
            assert len(nav_calls) > 0
            
        finally:
            await power_manager.shutdown()


if __name__ == "__main__":
    # Run tests with coverage
    pytest.main([
        __file__,
        "-v",
        "--cov=src.power_management",
        "--cov-report=html",
        "--cov-report=term-missing"
    ])
