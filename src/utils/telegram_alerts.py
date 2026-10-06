"""
Класс TelegramNotifier для отправки мгновенных уведомлений.
"""

from typing import Optional


class TelegramNotifier:
    """Отправка алертов в Telegram при важных триггерах."""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_alert(self, message: str) -> bool:
        """Отправка текстового уведомления."""
        pass
