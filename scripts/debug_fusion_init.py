import asyncio
import sys
import traceback
from unittest.mock import Mock, AsyncMock, patch

sys.path.insert(0, '.')

from src.sensor_fusion import SensorFusionEngine
from src.communication import MQTTClient

async def main():
    try:
        config = {
            'mqtt': {'host': 'localhost', 'port': 1883, 'start_local_broker': False},
            'hardware': {'i2c_devices': {}, 'serial_devices': {}, 'gpio_pins': {}}
        }
        engine = SensorFusionEngine(config)
        engine.mqtt_client = Mock(spec=MQTTClient)
        engine.mqtt_client.connect = AsyncMock()
        engine.mqtt_client.disconnect = AsyncMock()
        engine.mqtt_client.publish = AsyncMock()
        engine.mqtt_client.subscribe = AsyncMock()
        engine.mqtt_client.is_connected = Mock(return_value=True)

        print('Patching HardwareInterface in src.sensor_fusion.fusion_engine...')
        with patch('src.sensor_fusion.fusion_engine.HardwareInterface'):
            print('Calling engine.initialize()...')
            await engine.initialize()
        print('Initialization succeeded')
    except Exception as e:
        print('Initialization raised exception:')
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
