# Hardware interface layer package
from .managers import I2CManager, SerialManager, CameraManager, GPIOManager
from .plugin_system import HardwarePlugin, PluginManager
from .exceptions import HardwareError, DeviceNotFoundError, CommunicationError
from .hardware_interface import HardwareInterface, create_hardware_interface

__all__ = [
    'I2CManager',
    'SerialManager', 
    'CameraManager',
    'GPIOManager',
    'HardwarePlugin',
    'PluginManager',
    'HardwareError',
    'DeviceNotFoundError',
    'CommunicationError',
    'HardwareInterface',
    'create_hardware_interface'
]
