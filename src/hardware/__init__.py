# Hardware interface layer package
from .managers import I2CManager, SerialManager, CameraManager, GPIOManager
from .plugin_system import HardwarePlugin, PluginManager, PluginConfig
from .hardware_interface import HardwareInterface
from .exceptions import HardwareError, DeviceNotFoundError, CommunicationError

__all__ = [
    'I2CManager',
    'SerialManager', 
    'CameraManager',
    'GPIOManager',
    'HardwarePlugin',
    'PluginManager',
    'PluginConfig',
    'HardwareInterface',
    'HardwareError',
    'DeviceNotFoundError',
    'CommunicationError'
]
