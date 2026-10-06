from src.data_providers.base_parser import BaseParser
from src.data_providers.moex_api import MoexParser
from src.data_providers.news_scraper import NewsParser
from src.data_providers.macro_parser import MacroParser

__all__ = ["BaseParser", "MoexParser", "NewsParser", "MacroParser"]
