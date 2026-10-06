"""
Настройка логирования ошибок и прогонов агента.
"""

import logging


def setup_logger(name: str = "platon_rubond", level: int = logging.INFO) -> logging.Logger:
    """Инициализация логгера приложения."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger
