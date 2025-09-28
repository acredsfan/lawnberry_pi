"""
PowerManagement model for LawnBerry Pi v2
Battery status, solar charging, and power monitoring
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator


class PowerMode(str, Enum):
    """Power management modes"""
    NORMAL = "normal"  # Standard operation
    POWER_SAVE = "power_save"  # Reduced power consumption
    CHARGING = "charging"  # Prioritize charging
    LOW_BATTERY = "low_battery"  # Conservative operation
    CRITICAL_BATTERY = "critical_battery"  # Emergency power saving
    SUN_SEEKING = "sun_seeking"  # Actively seek solar charging


class BatteryChemistry(str, Enum):
    """Battery chemistry types"""
    LIFEPO4 = "lifepo4"  # LiFePO4 (default for system)
    LIPO = "lipo"  # LiPo (alternative)
    LEAD_ACID = "lead_acid"  # Lead acid (backup)


class ChargingStatus(str, Enum):
    """Battery charging status"""
    NOT_CHARGING = "not_charging"
    BULK_CHARGE = "bulk_charge"
    ABSORPTION = "absorption"
    FLOAT = "float"
    EQUALIZATION = "equalization"
    FAULT = "fault"


class BatteryStatus(BaseModel):
    """Battery status and health information"""
    # Voltage and capacity
    voltage: float = 0.0  # Volts
    current: float = 0.0  # Amperes (positive = charging, negative = discharging)
    power: float = 0.0  # Watts
    percentage: float = 0.0  # 0-100%
    capacity_ah: float = 30.0  # Amp-hours total capacity
    remaining_ah: float = 0.0  # Amp-hours remaining
    
    # Chemistry-specific parameters
    chemistry: BatteryChemistry = BatteryChemistry.LIFEPO4
    nominal_voltage: float = 12.8  # Volts (12.8V for LiFePO4)
    max_voltage: float = 14.6  # Volts (charging cutoff)
    min_voltage: float = 10.0  # Volts (discharge cutoff)
    
    # Health and status
    temperature: Optional[float] = None  # °C
    internal_resistance: Optional[float] = None  # Ohms
    cycle_count: int = 0
    health_percentage: float = 100.0  # 0-100%
    charging_status: ChargingStatus = ChargingStatus.NOT_CHARGING
    
    # Safety flags
    over_voltage_fault: bool = False
    under_voltage_fault: bool = False
    over_current_fault: bool = False
    over_temperature_fault: bool = False
    
    @validator('percentage', 'health_percentage')
    def validate_percentage(cls, v):
        return max(0.0, min(100.0, v))
    
    @validator('voltage')
    def validate_voltage_range(cls, v):
        if v < 0:
            raise ValueError('Voltage cannot be negative')
        return v


class SolarStatus(BaseModel):
    """Solar panel and charging status"""
    # Solar panel metrics
    voltage: float = 0.0  # Volts
    current: float = 0.0  # Amperes
    power: float = 0.0  # Watts
    
    # Environmental factors
    irradiance: Optional[float] = None  # W/m² (if available)
    panel_temperature: Optional[float] = None  # °C
    
    # MPPT controller status
    mppt_efficiency: Optional[float] = None  # 0-100%
    mppt_mode: Optional[str] = None  # "tracking", "absorption", "float"
    
    # Daily statistics
    energy_today: float = 0.0  # Wh generated today
    peak_power_today: float = 0.0  # W maximum power today
    
    # Panel specifications
    panel_watts: float = 30.0  # Rated panel capacity
    panel_efficiency: float = 0.22  # Typical solar panel efficiency


class INA3221Reading(BaseModel):
    """INA3221 triple power monitor reading"""
    # Channel 1: Battery
    channel1_voltage: float = 0.0  # V
    channel1_current: float = 0.0  # A
    channel1_power: float = 0.0  # W
    
    # Channel 2: Unused (reserved)
    channel2_voltage: float = 0.0  # V
    channel2_current: float = 0.0  # A
    channel2_power: float = 0.0  # W
    
    # Channel 3: Solar Input
    channel3_voltage: float = 0.0  # V
    channel3_current: float = 0.0  # A
    channel3_power: float = 0.0  # W
    
    # Chip status
    chip_temperature: Optional[float] = None  # °C
    measurement_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PowerBudget(BaseModel):
    """System power consumption budget"""
    # Major power consumers
    drive_motors: float = 0.0  # W
    blade_motor: float = 0.0  # W
    compute_pi: float = 5.0  # W (Raspberry Pi baseline)
    sensors: float = 1.0  # W (all sensors combined)
    camera: float = 2.0  # W (camera system)
    ai_accelerator: float = 0.0  # W (Coral/Hailo when active)
    wireless: float = 1.5  # W (Wi-Fi)
    other: float = 1.0  # W (misc systems)
    
    # Total calculations
    total_consumption: float = 0.0  # W (calculated)
    efficiency_factor: float = 0.85  # Overall system efficiency
    
    def calculate_total(self) -> float:
        """Calculate total power consumption"""
        self.total_consumption = (
            self.drive_motors + self.blade_motor + self.compute_pi +
            self.sensors + self.camera + self.ai_accelerator +
            self.wireless + self.other
        ) / self.efficiency_factor
        return self.total_consumption


class PowerManagement(BaseModel):
    """Complete power management state"""
    # Current status
    battery_status: BatteryStatus = Field(default_factory=BatteryStatus)
    solar_status: SolarStatus = Field(default_factory=SolarStatus)
    ina3221_reading: Optional[INA3221Reading] = None
    power_budget: PowerBudget = Field(default_factory=PowerBudget)
    
    # Power mode and strategy
    power_mode: PowerMode = PowerMode.NORMAL
    auto_power_management: bool = True
    sun_seeking_enabled: bool = True
    
    # Thresholds and limits
    low_battery_threshold: float = 20.0  # % to enter power save
    critical_battery_threshold: float = 10.0  # % to enter critical mode
    charging_start_threshold: float = 90.0  # % to start seeking charging
    max_discharge_current: float = 10.0  # A maximum discharge
    
    # Runtime estimates
    estimated_runtime_hours: Optional[float] = None  # Hours remaining
    estimated_charge_time_hours: Optional[float] = None  # Hours to full charge
    time_to_low_battery: Optional[datetime] = None
    
    # Historical data
    energy_consumed_today: float = 0.0  # Wh
    energy_generated_today: float = 0.0  # Wh
    net_energy_today: float = 0.0  # Wh (positive = surplus)
    
    # Safety and alerts
    power_alerts: List[str] = Field(default_factory=list)
    emergency_power_off: bool = False
    thermal_throttling: bool = False
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    def update_power_mode(self) -> PowerMode:
        """Update power mode based on current conditions"""
        battery_pct = self.battery_status.percentage
        charging = self.battery_status.charging_status != ChargingStatus.NOT_CHARGING
        
        if battery_pct <= self.critical_battery_threshold:
            self.power_mode = PowerMode.CRITICAL_BATTERY
        elif battery_pct <= self.low_battery_threshold:
            self.power_mode = PowerMode.LOW_BATTERY
        elif charging:
            self.power_mode = PowerMode.CHARGING
        elif (self.sun_seeking_enabled and 
              battery_pct <= self.charging_start_threshold and
              self.solar_status.power < 5.0):  # Low solar input
            self.power_mode = PowerMode.SUN_SEEKING
        else:
            self.power_mode = PowerMode.NORMAL
        
        return self.power_mode
    
    def calculate_runtime_estimate(self) -> Optional[float]:
        """Calculate estimated runtime in hours"""
        if self.power_budget.total_consumption <= 0:
            return None
        
        remaining_wh = (self.battery_status.remaining_ah * 
                       self.battery_status.voltage)
        
        self.estimated_runtime_hours = remaining_wh / self.power_budget.total_consumption
        return self.estimated_runtime_hours
    
    def is_charging_recommended(self) -> bool:
        """Check if charging is recommended"""
        return (
            self.battery_status.percentage <= self.charging_start_threshold or
            self.power_mode in [PowerMode.LOW_BATTERY, PowerMode.CRITICAL_BATTERY]
        )