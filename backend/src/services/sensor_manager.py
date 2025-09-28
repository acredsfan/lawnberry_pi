"""
SensorManager service for LawnBerry Pi v2
Hardware sensor interfaces with I2C/UART coordination and validation
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any
from contextlib import asynccontextmanager

from ..models import (
    SensorData, GpsReading, ImuReading, TofReading, EnvironmentalReading, 
    PowerReading, SensorType, SensorStatus, GpsMode
)

logger = logging.getLogger(__name__)


class SensorCoordinator:
    """Coordinates access to shared I2C/UART resources"""
    
    def __init__(self):
        self._i2c_lock = asyncio.Lock()
        self._uart_locks = {
            "UART0": asyncio.Lock(),
            "UART1": asyncio.Lock(), 
            "UART4": asyncio.Lock()
        }
        self._active_sensors = set()
    
    @asynccontextmanager
    async def acquire_i2c(self, sensor_name: str):
        """Acquire I2C bus access"""
        async with self._i2c_lock:
            self._active_sensors.add(sensor_name)
            try:
                yield
            finally:
                self._active_sensors.discard(sensor_name)
    
    @asynccontextmanager
    async def acquire_uart(self, uart_port: str, sensor_name: str):
        """Acquire UART port access"""
        if uart_port not in self._uart_locks:
            raise ValueError(f"Unknown UART port: {uart_port}")
        
        async with self._uart_locks[uart_port]:
            self._active_sensors.add(sensor_name)
            try:
                yield
            finally:
                self._active_sensors.discard(sensor_name)


class GPSSensorInterface:
    """GPS sensor interface supporting multiple modules"""
    
    def __init__(self, gps_mode: GpsMode, coordinator: SensorCoordinator):
        self.gps_mode = gps_mode
        self.coordinator = coordinator
        self.last_reading: Optional[GpsReading] = None
        self.status = SensorStatus.OFFLINE
        
    async def initialize(self) -> bool:
        """Initialize GPS sensor"""
        try:
            if self.gps_mode == GpsMode.F9P_USB:
                # Initialize u-blox ZED-F9P via USB
                logger.info("Initializing u-blox ZED-F9P GPS via USB")
                # USB GPS initialization would go here
                self.status = SensorStatus.ONLINE
                
            elif self.gps_mode == GpsMode.NEO8M_UART:
                # Initialize u-blox Neo-8M via UART
                logger.info("Initializing u-blox Neo-8M GPS via UART0")
                async with self.coordinator.acquire_uart("UART0", "GPS"):
                    # UART GPS initialization would go here
                    self.status = SensorStatus.ONLINE
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize GPS: {e}")
            self.status = SensorStatus.ERROR
            return False
    
    async def read_gps(self) -> Optional[GpsReading]:
        """Read GPS data"""
        if self.status != SensorStatus.ONLINE:
            return None
        
        try:
            if self.gps_mode == GpsMode.F9P_USB:
                # Read from USB GPS
                reading = GpsReading(
                    latitude=40.7128,  # Placeholder data
                    longitude=-74.0060,
                    altitude=10.0,
                    accuracy=0.5,
                    satellites=12,
                    mode=GpsMode.F9P_USB,
                    rtk_status="RTK_FIXED"
                )
                
            else:  # NEO8M_UART
                async with self.coordinator.acquire_uart("UART0", "GPS"):
                    # Read from UART GPS
                    reading = GpsReading(
                        latitude=40.7128,  # Placeholder data
                        longitude=-74.0060,
                        altitude=10.0,
                        accuracy=3.0,
                        satellites=8,
                        mode=GpsMode.NEO8M_UART
                    )
            
            self.last_reading = reading
            return reading
            
        except Exception as e:
            logger.error(f"GPS reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None


class IMUSensorInterface:
    """BNO085 IMU sensor interface"""
    
    def __init__(self, coordinator: SensorCoordinator):
        self.coordinator = coordinator
        self.last_reading: Optional[ImuReading] = None
        self.status = SensorStatus.OFFLINE
        
    async def initialize(self) -> bool:
        """Initialize BNO085 IMU"""
        try:
            async with self.coordinator.acquire_uart("UART4", "IMU"):
                logger.info("Initializing BNO085 IMU via UART4")
                # BNO085 initialization would go here
                self.status = SensorStatus.ONLINE
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize IMU: {e}")
            self.status = SensorStatus.ERROR
            return False
    
    async def read_imu(self) -> Optional[ImuReading]:
        """Read IMU data"""
        if self.status != SensorStatus.ONLINE:
            return None
        
        try:
            async with self.coordinator.acquire_uart("UART4", "IMU"):
                # Read from BNO085
                reading = ImuReading(
                    roll=0.0,    # Placeholder data
                    pitch=2.1,
                    yaw=45.5,
                    accel_x=0.1,
                    accel_y=0.0,
                    accel_z=9.8,
                    gyro_x=0.0,
                    gyro_y=0.0,
                    gyro_z=0.0,
                    calibration_status="fully_calibrated"
                )
                
                self.last_reading = reading
                return reading
                
        except Exception as e:
            logger.error(f"IMU reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None


class ToFSensorInterface:
    """VL53L0X Time-of-Flight sensor interface"""
    
    def __init__(self, coordinator: SensorCoordinator):
        self.coordinator = coordinator
        self.left_reading: Optional[TofReading] = None
        self.right_reading: Optional[TofReading] = None
        self.status = SensorStatus.OFFLINE
        
    async def initialize(self) -> bool:
        """Initialize VL53L0X sensors"""
        try:
            async with self.coordinator.acquire_i2c("TOF"):
                logger.info("Initializing VL53L0X ToF sensors")
                # VL53L0X initialization would go here
                # Setup left sensor at 0x29, right at 0x30
                self.status = SensorStatus.ONLINE
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize ToF sensors: {e}")
            self.status = SensorStatus.ERROR
            return False
    
    async def read_tof_sensors(self) -> tuple[Optional[TofReading], Optional[TofReading]]:
        """Read both ToF sensors"""
        if self.status != SensorStatus.ONLINE:
            return None, None
        
        try:
            async with self.coordinator.acquire_i2c("TOF"):
                # Read left sensor (0x29)
                left_reading = TofReading(
                    distance=1250.0,  # mm, placeholder
                    signal_strength=80.0,
                    range_status="valid",
                    sensor_side="left"
                )
                
                # Read right sensor (0x30)
                right_reading = TofReading(
                    distance=2100.0,  # mm, placeholder
                    signal_strength=75.0,
                    range_status="valid",
                    sensor_side="right"
                )
                
                self.left_reading = left_reading
                self.right_reading = right_reading
                return left_reading, right_reading
                
        except Exception as e:
            logger.error(f"ToF reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None, None


class EnvironmentalSensorInterface:
    """BME280 environmental sensor interface"""
    
    def __init__(self, coordinator: SensorCoordinator):
        self.coordinator = coordinator
        self.last_reading: Optional[EnvironmentalReading] = None
        self.status = SensorStatus.OFFLINE
        
    async def initialize(self) -> bool:
        """Initialize BME280 sensor"""
        try:
            async with self.coordinator.acquire_i2c("BME280"):
                logger.info("Initializing BME280 environmental sensor")
                # BME280 initialization would go here
                self.status = SensorStatus.ONLINE
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize BME280: {e}")
            self.status = SensorStatus.ERROR
            return False
    
    async def read_environmental(self) -> Optional[EnvironmentalReading]:
        """Read environmental data"""
        if self.status != SensorStatus.ONLINE:
            return None
        
        try:
            async with self.coordinator.acquire_i2c("BME280"):
                # Read from BME280
                reading = EnvironmentalReading(
                    temperature=22.5,    # °C, placeholder
                    humidity=65.0,       # %RH
                    pressure=1013.25,    # hPa
                    altitude=100.0       # meters
                )
                
                self.last_reading = reading
                return reading
                
        except Exception as e:
            logger.error(f"Environmental reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None


class PowerSensorInterface:
    """INA3221 power monitoring interface"""
    
    def __init__(self, coordinator: SensorCoordinator):
        self.coordinator = coordinator
        self.last_reading: Optional[PowerReading] = None
        self.status = SensorStatus.OFFLINE
        
    async def initialize(self) -> bool:
        """Initialize INA3221 power monitor"""
        try:
            async with self.coordinator.acquire_i2c("INA3221"):
                logger.info("Initializing INA3221 power monitor")
                # INA3221 initialization would go here
                self.status = SensorStatus.ONLINE
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize INA3221: {e}")
            self.status = SensorStatus.ERROR
            return False
    
    async def read_power(self) -> Optional[PowerReading]:
        """Read power monitoring data"""
        if self.status != SensorStatus.ONLINE:
            return None
        
        try:
            async with self.coordinator.acquire_i2c("INA3221"):
                # Read from INA3221 - Channel 1: Battery, Channel 3: Solar
                reading = PowerReading(
                    battery_voltage=12.6,    # V, placeholder
                    battery_current=-2.5,    # A (negative = discharging)
                    battery_power=-31.5,     # W
                    solar_voltage=14.2,      # V
                    solar_current=1.8,       # A
                    solar_power=25.6         # W
                )
                
                self.last_reading = reading
                return reading
                
        except Exception as e:
            logger.error(f"Power reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None


class SensorManager:
    """Main sensor manager coordinating all sensor interfaces"""
    
    def __init__(self, gps_mode: GpsMode = GpsMode.NEO8M_UART):
        self.coordinator = SensorCoordinator()
        
        # Initialize sensor interfaces
        self.gps = GPSSensorInterface(gps_mode, self.coordinator)
        self.imu = IMUSensorInterface(self.coordinator)
        self.tof = ToFSensorInterface(self.coordinator)
        self.environmental = EnvironmentalSensorInterface(self.coordinator)
        self.power = PowerSensorInterface(self.coordinator)
        
        self.initialized = False
        self.validation_enabled = True
        
    async def initialize(self) -> bool:
        """Initialize all sensors"""
        logger.info("Initializing sensor manager")
        
        results = await asyncio.gather(
            self.gps.initialize(),
            self.imu.initialize(),
            self.tof.initialize(),
            self.environmental.initialize(),
            self.power.initialize(),
            return_exceptions=True
        )
        
        success_count = sum(1 for result in results if result is True)
        total_sensors = len(results)
        
        logger.info(f"Sensor initialization: {success_count}/{total_sensors} successful")
        
        # Consider initialized if at least core sensors are working
        self.initialized = success_count >= 3
        return self.initialized
    
    async def read_all_sensors(self) -> SensorData:
        """Read data from all sensors"""
        if not self.initialized:
            logger.warning("Sensor manager not initialized")
            return SensorData()
        
        # Read all sensors concurrently where possible
        tasks = [
            self.gps.read_gps(),
            self.imu.read_imu(),
            self.tof.read_tof_sensors(),
            self.environmental.read_environmental(),
            self.power.read_power()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        gps_data = results[0] if not isinstance(results[0], Exception) else None
        imu_data = results[1] if not isinstance(results[1], Exception) else None
        tof_data = results[2] if not isinstance(results[2], Exception) else (None, None)
        env_data = results[3] if not isinstance(results[3], Exception) else None
        power_data = results[4] if not isinstance(results[4], Exception) else None
        
        # Create sensor health status
        sensor_health = {
            SensorType.GPS: self.gps.status,
            SensorType.IMU: self.imu.status,
            SensorType.TOF_LEFT: self.tof.status,
            SensorType.TOF_RIGHT: self.tof.status,
            SensorType.ENVIRONMENTAL: self.environmental.status,
            SensorType.POWER: self.power.status
        }
        
        sensor_data = SensorData(
            gps=gps_data,
            imu=imu_data,
            tof_left=tof_data[0] if tof_data else None,
            tof_right=tof_data[1] if tof_data else None,
            environmental=env_data,
            power=power_data,
            sensor_health=sensor_health
        )
        
        if self.validation_enabled:
            self._validate_sensor_data(sensor_data)
        
        return sensor_data
    
    def _validate_sensor_data(self, sensor_data: SensorData):
        """Validate sensor data for consistency and reasonable values"""
        # GPS validation
        if sensor_data.gps:
            gps = sensor_data.gps
            if gps.latitude and (gps.latitude < -90 or gps.latitude > 90):
                logger.warning(f"Invalid GPS latitude: {gps.latitude}")
            if gps.longitude and (gps.longitude < -180 or gps.longitude > 180):
                logger.warning(f"Invalid GPS longitude: {gps.longitude}")
            if gps.accuracy and gps.accuracy > 50.0:
                logger.warning(f"Poor GPS accuracy: {gps.accuracy}m")
        
        # Power validation
        if sensor_data.power:
            power = sensor_data.power
            if power.battery_voltage and power.battery_voltage < 9.0:
                logger.warning(f"Low battery voltage: {power.battery_voltage}V")
            if power.battery_voltage and power.battery_voltage > 16.0:
                logger.warning(f"High battery voltage: {power.battery_voltage}V")
        
        # Environmental validation
        if sensor_data.environmental:
            env = sensor_data.environmental
            if env.temperature and (env.temperature < -40 or env.temperature > 80):
                logger.warning(f"Extreme temperature: {env.temperature}°C")
    
    async def get_sensor_status(self) -> Dict[str, Any]:
        """Get status of all sensors"""
        return {
            "initialized": self.initialized,
            "gps_status": self.gps.status,
            "gps_mode": self.gps.gps_mode,
            "imu_status": self.imu.status,
            "tof_status": self.tof.status,
            "environmental_status": self.environmental.status,
            "power_status": self.power.status,
            "active_sensors": list(self.coordinator._active_sensors),
            "validation_enabled": self.validation_enabled
        }
    
    async def shutdown(self):
        """Shutdown sensor manager"""
        logger.info("Shutting down sensor manager")
        # Sensor shutdown logic would go here
        self.initialized = False