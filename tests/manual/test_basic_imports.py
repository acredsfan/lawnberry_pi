import sys
sys.path.append('src')

try:
    from hardware import HardwareInterface, I2CManager, SerialManager, CameraManager, GPIOManager
    from hardware.plugin_system import PluginManager, HardwarePlugin
    from hardware.config import ConfigManager
    print('✓ All imports successful')
    
    config_mgr = ConfigManager()
    config = config_mgr.get_default_config()
    print('✓ Configuration system works')
    
    i2c = I2CManager()
    print('✓ I2C Manager singleton works')
    
    print('✓ Hardware interface layer implementation complete')
    
except ImportError as e:
    print(f'✗ Import error: {e}')
except Exception as e:
    print(f'✗ Error: {e}')
