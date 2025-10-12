"""
HardwareBaseline model for LawnBerry Pi v2
Hardware configuration and capability tracking
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, ConfigDict


class RaspberryPiModel(str, Enum):
    """Supported Raspberry Pi models"""
    PI5_4GB = "pi5_4gb"
    PI5_8GB = "pi5_8gb"
    PI5_16GB = "pi5_16gb"
    PI4B_4GB = "pi4b_4gb"
    PI4B_8GB = "pi4b_8gb"


class GpsModuleType(str, Enum):
    """GPS module options"""
    ZED_F9P_USB = "zed_f9p_usb"  # u-blox ZED-F9P via USB (preferred)
    NEO8M_UART = "neo8m_uart"    # u-blox Neo-8M via UART (alternative)


class DriveControllerType(str, Enum):
    """Drive controller options"""
    ROBOHAT_CYTRON = "robohat_cytron"  # RoboHAT + Cytron MDDRC10 (preferred)
    L298N = "l298n"                    # L298N Dual H-Bridge (alternative)


class AIAcceleratorType(str, Enum):
    """AI acceleration hardware"""
    CORAL_USB = "coral_usb"    # Google Coral USB Accelerator
    HAILO_HAT = "hailo_hat"    # Hailo-8 AI Hat (optional, conflicts with RoboHAT)
    CPU_ONLY = "cpu_only"      # CPU-only inference


class ComponentStatus(str, Enum):
    """Hardware component status"""
    PRESENT = "present"        # Component detected and functional
    MISSING = "missing"        # Component not detected
    ERROR = "error"           # Component detected but malfunctioning
    DISABLED = "disabled"     # Component disabled by configuration
    UNKNOWN = "unknown"       # Status cannot be determined


class HardwareComponent(BaseModel):
    """Individual hardware component specification"""
    component_name: str
    component_type: str  # "sensor", "controller", "accelerator", "display", etc.
    required: bool = True
    
    # Hardware details
    model: str
    interface: str  # "I2C", "UART", "USB", "GPIO", "SPI"
    address_or_pin: Optional[str] = None  # I2C address, GPIO pin, etc.
    
    # Status and health
    status: ComponentStatus = ComponentStatus.UNKNOWN
    last_detected: Optional[datetime] = None
    error_message: Optional[str] = None
    
    # Specifications
    specifications: Dict[str, Any] = Field(default_factory=dict)
    capabilities: List[str] = Field(default_factory=list)
    
    # Alternative options
    alternative_models: List[str] = Field(default_factory=list)
    fallback_available: bool = False
    

class GPIOPinAssignment(BaseModel):
    """GPIO pin assignment tracking"""
    physical_pin: int
    gpio_number: int
    role: str
    component: str
    direction: str = "output"  # "input", "output", "bidirectional"
    pull_resistor: Optional[str] = None  # "up", "down", "none"
    initial_state: Optional[bool] = None
    
    # Alternative assignments for different Pi models
    pi4_alternative_pin: Optional[int] = None
    pi5_alternative_pin: Optional[int] = None
    
    @field_validator('physical_pin', 'gpio_number')
    def validate_pin_numbers(cls, v):
        if v < 1 or v > 40:
            raise ValueError('Pin numbers must be between 1 and 40')
        return v


class I2CDeviceMap(BaseModel):
    """I2C device address mapping"""
    address: str  # Hex address like "0x29"
    device_name: str
    component_type: str
    bus_number: int = 1  # Default I2C bus
    
    # Conflict detection
    address_conflicts: List[str] = Field(default_factory=list)
    shared_bus_compatible: bool = True


class UARTAssignment(BaseModel):
    """UART port assignment"""
    uart_id: str  # "UART0", "UART1", "UART4"
    role: str
    device: str
    baud_rate: int = 115200
    
    # Pi model specific pins
    tx_pin: int
    rx_pin: int
    pi4_tx_pin: Optional[int] = None
    pi4_rx_pin: Optional[int] = None


class PowerSpecification(BaseModel):
    """Power system specifications"""
    # Battery specifications
    battery_chemistry: str = "LiFePO4"
    battery_voltage: float = 12.8  # Nominal voltage
    battery_capacity_ah: float = 30.0
    battery_max_voltage: float = 14.6
    battery_min_voltage: float = 10.0
    
    # Solar specifications
    solar_panel_watts: float = 30.0
    solar_controller_type: str = "15A MPPT"
    
    # Power monitoring (INA3221 channels)
    ina3221_channels: Dict[str, str] = Field(default_factory=lambda: {
        "channel_1": "Battery",
        "channel_2": "Unused", 
        "channel_3": "Solar Input"
    })


class HardwareBaseline(BaseModel):
    """Complete hardware baseline configuration"""
    baseline_id: str
    baseline_name: str = "LawnBerry Pi v2 Standard"
    version: str = "2.0"
    
    # Platform specification
    pi_model: RaspberryPiModel = RaspberryPiModel.PI4B_4GB
    os_version: str = "Raspberry Pi OS Bookworm (64-bit)"
    python_version: str = "3.11.x"
    
    # Core hardware selection
    gps_module: GpsModuleType = GpsModuleType.NEO8M_UART
    drive_controller: DriveControllerType = DriveControllerType.L298N
    ai_accelerator: AIAcceleratorType = AIAcceleratorType.CPU_ONLY
    
    # Hardware components
    components: List[HardwareComponent] = Field(default_factory=list)
    
    # Pin and interface assignments
    gpio_assignments: List[GPIOPinAssignment] = Field(default_factory=list)
    i2c_devices: List[I2CDeviceMap] = Field(default_factory=list)
    uart_assignments: List[UARTAssignment] = Field(default_factory=list)
    usb_devices: List[str] = Field(default_factory=list)
    
    # Power system
    power_spec: PowerSpecification = Field(default_factory=PowerSpecification)
    
    # Detection and validation
    last_hardware_scan: Optional[datetime] = None
    hardware_scan_results: Dict[str, Any] = Field(default_factory=dict)
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
    
    # Compatibility and constraints
    known_conflicts: List[str] = Field(default_factory=list)
    unsupported_combinations: List[str] = Field(default_factory=list)
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(use_enum_values=True)
    
    def add_component(self, component: HardwareComponent):
        """Add a hardware component"""
        self.components.append(component)
        self.last_modified = datetime.now(timezone.utc)
    
    def get_component(self, name: str) -> Optional[HardwareComponent]:
        """Get component by name"""
        return next(
            (comp for comp in self.components if comp.component_name == name),
            None
        )
    
    def get_components_by_type(self, component_type: str) -> List[HardwareComponent]:
        """Get all components of a specific type"""
        return [
            comp for comp in self.components 
            if comp.component_type == component_type
        ]
    
    def validate_configuration(self) -> List[str]:
        """Validate hardware configuration and return issues"""
        issues = []
        
        # Check for GPIO conflicts
        used_gpio_pins = set()
        for assignment in self.gpio_assignments:
            if assignment.gpio_number in used_gpio_pins:
                issues.append(f"GPIO {assignment.gpio_number} assigned multiple times")
            used_gpio_pins.add(assignment.gpio_number)
        
        # Check for I2C address conflicts
        used_i2c_addresses = set()
        for device in self.i2c_devices:
            if device.address in used_i2c_addresses:
                issues.append(f"I2C address {device.address} assigned multiple times")
            used_i2c_addresses.add(device.address)
        
        # Check for UART conflicts
        used_uart_ports = set()
        for uart in self.uart_assignments:
            if uart.uart_id in used_uart_ports:
                issues.append(f"UART {uart.uart_id} assigned multiple times")
            used_uart_ports.add(uart.uart_id)
        
        # Check hardware combinations
        if (self.ai_accelerator == AIAcceleratorType.HAILO_HAT and 
            self.drive_controller == DriveControllerType.ROBOHAT_CYTRON):
            issues.append("Hailo HAT conflicts with RoboHAT - requires HAT splitter")
        
        return issues
    
    def get_missing_components(self) -> List[HardwareComponent]:
        """Get list of required components that are missing"""
        return [
            comp for comp in self.components
            if comp.required and comp.status == ComponentStatus.MISSING
        ]
    
    def get_power_requirements(self) -> Dict[str, float]:
        """Calculate estimated power requirements"""
        power_budget = {
            "raspberry_pi": 5.0,  # Base Pi consumption
            "sensors": 1.0,       # All sensors combined
            "camera": 2.0,        # Camera system
            "wireless": 1.5,      # Wi-Fi
            "drive_motors": 0.0,  # Variable, up to 50W
            "blade_motor": 0.0,   # Variable, up to 100W
            "ai_accelerator": 0.0,
            "other": 1.0
        }
        
        # Add AI accelerator consumption
        if self.ai_accelerator == AIAcceleratorType.CORAL_USB:
            power_budget["ai_accelerator"] = 2.5
        elif self.ai_accelerator == AIAcceleratorType.HAILO_HAT:
            power_budget["ai_accelerator"] = 5.0
        
        return power_budget
    
    @classmethod
    def create_standard_baseline(cls) -> 'HardwareBaseline':
        """Create standard hardware baseline"""
        baseline = cls(
            baseline_id="standard_v2",
            baseline_name="LawnBerry Pi v2 Standard Configuration"
        )
        
        # Add standard components
        components = [
            HardwareComponent(
                component_name="ToF Left",
                component_type="sensor",
                model="VL53L0X",
                interface="I2C",
                address_or_pin="0x29"
            ),
            HardwareComponent(
                component_name="ToF Right", 
                component_type="sensor",
                model="VL53L0X",
                interface="I2C",
                address_or_pin="0x30"
            ),
            HardwareComponent(
                component_name="Environmental Sensor",
                component_type="sensor",
                model="BME280",
                interface="I2C",
                address_or_pin="0x76"
            ),
            HardwareComponent(
                component_name="Power Monitor",
                component_type="sensor",
                model="INA3221",
                interface="I2C",
                address_or_pin="0x40"
            ),
            HardwareComponent(
                component_name="OLED Display",
                component_type="display",
                model="SSD1306 128x64",
                interface="I2C",
                address_or_pin="0x3C",
                required=False
            ),
            HardwareComponent(
                component_name="IMU",
                component_type="sensor",
                model="BNO085",
                interface="UART",
                address_or_pin="UART4"
            ),
            HardwareComponent(
                component_name="Camera",
                component_type="camera",
                model="Pi Camera v2",
                interface="CSI",
                address_or_pin="CSI0"
            )
        ]
        
        for component in components:
            baseline.add_component(component)
        
        return baseline