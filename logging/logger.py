import logging
from config.config import load_config

config = load_config()

logging.basicConfig(level=config.logger.level, format=config.logger.format)
logger = logging.getLogger("my_bot")
