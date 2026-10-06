from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseParser(ABC):
    """
    Абстрактный базовый класс для всех парсеров данных.
    Реализует принцип Open/Closed: новые источники данных
    добавляются через наследование без изменения ядра.

    Конкретные реализации могут расширять сигнатуру fetch_data
    (например, принимать secid или query).
    """

    @abstractmethod
    def fetch_data(self, *args: Any, **kwargs: Any) -> Any:
        """
        Получение сырых данных из внешнего источника.
        Должен быть реализован в каждом конкретном парсере.
        """
        pass

    @abstractmethod
    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        """
        Преобразование сырых данных в унифицированный формат.
        Возвращает список словарей с нормализованными полями.
        """
        pass
