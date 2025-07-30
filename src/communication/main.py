#!/usr/bin/env python3
"""
Main entry point for Lawnberry Communication System
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from communication.service_manager import CommunicationService


def setup_logging():
    """Setup logging configuration"""
    log_dir = Path('/var/log/lawnberry')
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('/var/log/lawnberry/communication.log')
        ]
    )


async def main():
    """Main entry point"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Lawnberry Communication System")
    
    try:
        service = CommunicationService()
        await service.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Communication service failed: {e}")
        sys.exit(1)
    
    logger.info("Communication System stopped")


if __name__ == "__main__":
    asyncio.run(main())
