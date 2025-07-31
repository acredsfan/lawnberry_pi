#!/usr/bin/env python3
"""
Core Power Management Logic Validation
Tests the essential power management components without hardware dependencies.
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, Any, Optional, List
import math

# Core Power Management Classes (standalone for validation)

class PowerMode(Enum):
    HIGH_PERFORMANCE = "high_performance"
    ECO_MODE = "eco_mode"  
    CHARGING_MODE = "charging_mode"
    EMERGENCY_MODE = "emergency_mode"

class ChargingMode(Enum):
    AUTO = "auto"
    MANUAL = "manual"
    ECO = "eco"

@dataclass
class BatteryMetrics:
    voltage: float
    current: float
    power: float
    state_of_charge: float
    temperature: Optional[float] = None
    health: float = 1.0
    cycles: int = 0
    time_remaining: Optional[int] = None

@dataclass
class SolarMetrics:
    voltage: float
    current: float
    power: float
    daily_energy: float = 0.0
    efficiency: float = 0.0

@dataclass  
class SunnySpot:
    latitude: float
    longitude: float
    efficiency_rating: float
    last_measured: datetime
    time_of_day_optimal: List[int]
    seasonal_factor: float = 1.0

class CorePowerLogic:
    """Core power management logic for validation"""
    
    def __init__(self):
        self.CRITICAL_BATTERY_LEVEL = 0.05
        self.LOW_BATTERY_LEVEL = 0.20
        self.OPTIMAL_BATTERY_LEVEL = 0.80
        
        self.voltage_calibration_points = [
            (10.0, 0.0), (12.0, 0.2), (12.8, 0.5), (13.2, 0.8), (14.0, 1.0)
        ]
    
    def calculate_soc_from_voltage(self, voltage: float) -> float:
        """Calculate State of Charge from voltage"""
        cal_points = self.voltage_calibration_points
        
        if voltage <= cal_points[0][0]:
            return cal_points[0][1]
        if voltage >= cal_points[-1][0]:
            return cal_points[-1][1]
        
        for i in range(len(cal_points) - 1):
            v1, soc1 = cal_points[i]
            v2, soc2 = cal_points[i + 1]
            
            if v1 <= voltage <= v2:
                ratio = (voltage - v1) / (v2 - v1)
                return soc1 + ratio * (soc2 - soc1)
        
        return 0.5
    
    def determine_optimal_power_mode(self, soc: float, solar_power: float) -> PowerMode:
        """Determine optimal power mode"""
        if soc <= self.CRITICAL_BATTERY_LEVEL:
            return PowerMode.EMERGENCY_MODE
        elif soc <= self.LOW_BATTERY_LEVEL and solar_power > 5.0:
            return PowerMode.CHARGING_MODE
        elif soc <= self.LOW_BATTERY_LEVEL:
            return PowerMode.ECO_MODE
        elif soc >= self.OPTIMAL_BATTERY_LEVEL:
            return PowerMode.HIGH_PERFORMANCE
        else:
            return PowerMode.ECO_MODE
    
    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between GPS coordinates"""
        lat_diff = lat1 - lat2
        lon_diff = lon1 - lon2
        
        meters_per_lat_degree = 111320.0
        meters_per_lon_degree = 111320.0 * math.cos(math.radians((lat1 + lat2) / 2))
        
        distance_m = math.sqrt(
            (lat_diff * meters_per_lat_degree) ** 2 + 
            (lon_diff * meters_per_lon_degree) ** 2
        )
        
        return distance_m
    
    def estimate_time_remaining(self, current: float, soc: float) -> Optional[int]:
        """Estimate remaining battery time"""
        if current >= 0:
            return None
        
        battery_capacity_ah = 30.0
        remaining_capacity_ah = battery_capacity_ah * soc
        current_draw = abs(current)
        
        if current_draw > 0.01:
            time_remaining_hours = remaining_capacity_ah / current_draw
            return int(time_remaining_hours * 60)
        
        return None
    
    def calculate_seasonal_factor(self) -> float:
        """Calculate seasonal adjustment factor"""
        current_date = datetime.now()
        day_of_year = current_date.timetuple().tm_yday
        
        # Peak solar around summer solstice (day 172)
        seasonal_factor = 0.5 + 0.5 * math.cos(2 * math.pi * (day_of_year - 172) / 365)
        return max(0.3, min(1.0, seasonal_factor))

async def validate_core_logic():
    """Validate core power management logic"""
    
    print("🔋 Validating Core Power Management Logic...")
    print("=" * 50)
    
    try:
        logic = CorePowerLogic()
        
        # Test 1: Battery SoC Calculation
        print("📊 Testing SoC calculation...")
        test_voltages = [10.0, 12.0, 12.8, 13.2, 14.0]
        expected_socs = [0.0, 0.2, 0.5, 0.8, 1.0]
        
        for voltage, expected in zip(test_voltages, expected_socs):
            soc = logic.calculate_soc_from_voltage(voltage)
            assert abs(soc - expected) < 0.05, f"SoC calculation failed for {voltage}V"
            print(f"  ✅ {voltage}V -> {soc:.1%} (expected {expected:.1%})")
        
        # Test 2: Power Mode Determination
        print("\n⚡ Testing power mode determination...")
        test_cases = [
            (0.03, 0.0, PowerMode.EMERGENCY_MODE),
            (0.15, 20.0, PowerMode.CHARGING_MODE),
            (0.15, 2.0, PowerMode.ECO_MODE),
            (0.85, 15.0, PowerMode.HIGH_PERFORMANCE),
        ]
        
        for soc, solar, expected_mode in test_cases:
            mode = logic.determine_optimal_power_mode(soc, solar)
            assert mode == expected_mode, f"Mode determination failed for SoC={soc}, Solar={solar}W"
            print(f"  ✅ SoC {soc:.1%}, Solar {solar}W -> {mode.value}")
        
        # Test 3: Distance Calculation
        print("\n🗺️ Testing GPS distance calculation...")
        # Test known distance (1 degree latitude ≈ 111km)
        distance = logic.calculate_distance(40.0, -74.0, 41.0, -74.0)
        assert 110000 < distance < 112000, f"Distance calculation incorrect: {distance}m"
        print(f"  ✅ 1° lat difference = {distance:.0f}m (expected ~111,320m)")
        
        # Test 4: Time Remaining Estimation
        print("\n⏱️ Testing time remaining estimation...")
        time_remaining = logic.estimate_time_remaining(-2.0, 0.6)  # 2A discharge, 60% SoC
        assert isinstance(time_remaining, int), "Time remaining should be integer minutes"
        assert time_remaining > 0, "Time remaining should be positive"
        print(f"  ✅ 2A discharge at 60% SoC = {time_remaining} minutes")
        
        # Test with charging current
        time_remaining = logic.estimate_time_remaining(1.0, 0.6)  # Charging
        assert time_remaining is None, "Time remaining should be None when charging"
        print(f"  ✅ Charging current returns None")
        
        # Test 5: Data Structures
        print("\n📦 Testing data structures...")
        
        battery = BatteryMetrics(
            voltage=12.8,
            current=-1.5,
            power=-19.2,
            state_of_charge=0.75,
            temperature=25.0
        )
        print(f"  ✅ BatteryMetrics: {battery.voltage}V, {battery.state_of_charge:.1%}")
        
        solar = SolarMetrics(
            voltage=14.0,
            current=2.0, 
            power=28.0,
            efficiency=0.9
        )
        print(f"  ✅ SolarMetrics: {solar.power}W, {solar.efficiency:.1%}")
        
        sunny_spot = SunnySpot(
            latitude=40.7128,
            longitude=-74.0060,
            efficiency_rating=0.85,
            last_measured=datetime.now(),
            time_of_day_optimal=[12, 13, 14]
        )
        print(f"  ✅ SunnySpot: ({sunny_spot.latitude:.4f}, {sunny_spot.longitude:.4f})")
        
        # Test 6: Seasonal Factor
        print("\n🌞 Testing seasonal factor...")
        seasonal_factor = logic.calculate_seasonal_factor()
        assert 0.3 <= seasonal_factor <= 1.0, "Seasonal factor out of range"
        print(f"  ✅ Seasonal factor: {seasonal_factor:.2f}")
        
        # Test 7: JSON Serialization
        print("\n💾 Testing data serialization...")
        battery_dict = asdict(battery)
        assert 'voltage' in battery_dict, "Battery serialization failed"
        print(f"  ✅ Battery serialization: {len(battery_dict)} fields")
        
        solar_dict = asdict(solar)
        assert 'power' in solar_dict, "Solar serialization failed"
        print(f"  ✅ Solar serialization: {len(solar_dict)} fields")
        
        print("\n🎉 All core logic validation tests passed!")
        print("✅ Power Management System core logic is working correctly")
        
        # Test 8: Integration Scenario
        print("\n🔄 Testing integration scenario...")
        
        # Simulate a complete power management cycle
        scenarios = [
            {"name": "Morning startup", "voltage": 13.0, "solar": 5.0},
            {"name": "Midday operation", "voltage": 12.5, "solar": 25.0},
            {"name": "Afternoon work", "voltage": 12.0, "solar": 15.0},
            {"name": "Evening return", "voltage": 11.5, "solar": 2.0},
            {"name": "Night charging", "voltage": 11.8, "solar": 0.0},
        ]
        
        for scenario in scenarios:
            soc = logic.calculate_soc_from_voltage(scenario["voltage"])
            mode = logic.determine_optimal_power_mode(soc, scenario["solar"])
            time_left = logic.estimate_time_remaining(-1.5, soc)
            
            print(f"  📋 {scenario['name']}: {scenario['voltage']}V ({soc:.1%}) -> {mode.value}")
            if time_left:
                print(f"      Time remaining: {time_left} minutes")
        
        print("\n✅ Integration scenario completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Core validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(validate_core_logic())
    sys.exit(0 if success else 1)
