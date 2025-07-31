import sys
sys.path.insert(0, 'src')

try:
    from web_api.main import create_app
    from web_api.config import get_settings
    print('✓ FastAPI imports successful')
    
    settings = get_settings()
    print('✓ Settings loaded successfully')
    
    app = create_app()
    print('✓ FastAPI app created successfully')
    
    print('✓ All core components validated!')
    print('Host:', settings.host + ':' + str(settings.port))
    print('Debug:', settings.debug)
    print('MQTT:', settings.mqtt.broker_host + ':' + str(settings.mqtt.broker_port))
    
except Exception as e:
    print('✗ Validation failed:', str(e))
    import traceback
    traceback.print_exc()
    exit(1)
