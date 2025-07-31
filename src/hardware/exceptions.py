"""Hardware interface exceptions"""


class HardwareError(Exception):
    """Base exception for hardware interface layer"""
    pass


class DeviceNotFoundError(HardwareError):
    """Device not found or not accessible"""
    pass


class CommunicationError(HardwareError):
    """Communication with device failed"""
    pass


class DeviceBusyError(HardwareError):
    """Device is busy or locked by another process"""
    pass


class DeviceTimeoutError(HardwareError):
    """Device operation timed out"""
    pass


class DeviceConfigurationError(HardwareError):
    """Device configuration error"""
    pass
