#!/usr/bin/env python3
"""
Web API Server Startup Script
Production-ready startup script for the FastAPI web API backend.
"""

import asyncio
import logging
import signal
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
project_root = Path(__file__).parent.parent.parent
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn
from web_api.config import get_settings
from web_api.main import create_app


def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('/var/log/lawnberry/web_api.log', mode='a')
        ]
    )
    
    # Set specific log levels
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    logging.getLogger('fastapi').setLevel(logging.INFO)
    logging.getLogger('websockets').setLevel(logging.WARNING)


def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully"""
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)


def main():
    """Main entry point"""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Setup signal handlers
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    
    # Get settings
    settings = get_settings()
    
    logger.info("Starting Lawnberry Web API Backend...")
    logger.info(f"Host: {settings.host}:{settings.port}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Log level: {settings.log_level}")
    
    # Create log directory if it doesn't exist
    log_dir = Path('/var/log/lawnberry')
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Run the server
    try:
        # For Raspberry Pi production keep workers=1 (shared state + MQTT bridge)
        uvicorn.run(
            "web_api.main:app",
            host=settings.host,
            port=settings.port,
            reload=False,  # disable auto-reload in production
            log_level=settings.log_level.lower(),
            access_log=True,
            use_colors=False,
            workers=1,  # single process ensures hardware/MQTT singletons behave
            loop="asyncio",
            lifespan="on"
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
