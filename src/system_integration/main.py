#!/usr/bin/env python3
"""
Main entry point for Lawnberry System Integration
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from system_integration.system_manager import SystemManager


def setup_logging():
    """Setup logging configuration"""
    # Create log directory
    log_dir = Path('/var/log/lawnberry')
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('/var/log/lawnberry/system.log')
        ]
    )
    
    # Set specific log levels
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('psutil').setLevel(logging.WARNING)


async def main():
    """Main entry point"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Lawnberry System Integration Manager")
    
    try:
        system_manager = SystemManager()
        await system_manager.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"System manager failed: {e}")
        sys.exit(1)
    
    logger.info("System Integration Manager stopped")


if __name__ == "__main__":
    asyncio.run(main())
