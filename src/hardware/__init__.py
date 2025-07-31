# Hardware interface layer package
from .managers import I2CManager, SerialManager, CameraManager, GPIOManager
from .plugin_system import HardwarePlugin, PluginManager
from .exceptions import HardwareError, DeviceNotFoundError, CommunicationError

__all__ = [
    'I2CManager',
    'SerialManager', 
    'CameraManager',
    'GPIOManager',
    'HardwarePlugin',
    'PluginManager',
    'HardwareError',
    'DeviceNotFoundError',
    'CommunicationError'
]
