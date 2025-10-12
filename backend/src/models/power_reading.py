from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class PowerSource(str, Enum):
    BATTERY = "battery"
    CHARGING = "charging"
    EXTERNAL = "external"


class BatteryHealth(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class PowerReading(BaseModel):
    """Power system readings and battery status."""
    
    # Battery status
    battery_voltage: Optional[float] = None
    battery_current_a: Optional[float] = None
    battery_percentage: Optional[float] = None
    battery_health: Optional[BatteryHealth] = None
    
    # Charging status
    charging_active: bool = False
    charging_voltage: Optional[float] = None
    charging_current_a: Optional[float] = None
    
    # Power consumption
    total_power_w: Optional[float] = None
    motor_power_w: Optional[float] = None
    blade_power_w: Optional[float] = None
    system_power_w: Optional[float] = None
    
    # Power source
    active_source: PowerSource = PowerSource.BATTERY
    
    # Temperature monitoring
    battery_temp_c: Optional[float] = None
    controller_temp_c: Optional[float] = None
    
    # Runtime estimates
    estimated_runtime_minutes: Optional[int] = None
    time_to_full_charge_minutes: Optional[int] = None
    
    # Alerts
    low_battery_alert: bool = False
    critical_battery_alert: bool = False
    overheating_alert: bool = False
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @field_validator('battery_percentage')
    def validate_percentage(cls, v):
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError('Battery percentage must be between 0.0 and 100.0')
        return v
    
    @field_validator('battery_voltage', 'charging_voltage')
    def validate_voltage(cls, v):
        if v is not None and v < 0:
            raise ValueError('Voltage values must be non-negative')
        return v
    
    model_config = ConfigDict(use_enum_values=True)