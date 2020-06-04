
import logging.config

from .logger import LOGGING_CONF

__version__ = '0.0.0-auto.0'

logging.config.dictConfig(LOGGING_CONF)
