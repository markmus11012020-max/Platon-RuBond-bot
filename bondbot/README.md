# Platon Bond Bot — VK

Детерминированное ядро для VK-бота по российским облигациям.

## Что уже есть

- парсер screener smart-lab (`/q/bonds/`) — 100 бумаг на страницу;
- парсер карточки бумаги и графика купонов;
- SQLite: бумаги, купоны, watchlist;
- фильтр по доходности, дюрации, рейтингу, цене, объёму и ликвидности;
- расчёт допустимого объёма позиции относительно дневного оборота;
- CLI для проверки данных без VK.

## CLI

```powershell
.\.venv\Scripts\python -m bondbot.cli update --pages 1
.\.venv\Scripts\python -m bondbot.cli screen --limit 10
.\.venv\Scripts\python -m bondbot.cli bond RU000A10G1T5
.\.venv\Scripts\python -m bondbot.cli watch add RU000A10G1T5
.\.venv\Scripts\python -m bondbot.cli portfolio
```

## Принципы

- LLM не считает числа. Все метрики берутся из smart-lab/MOEX и хранятся с датой источника.
- YTM выше 35% и цена ниже 90% по умолчанию не рекомендуются — это зона риска/амортизации/оферты.
- Позиция 1 млн ₽ не должна быть больше 5% дневного оборота бумаги; отсюда минимальный объём 20 млн ₽.
- Watchlist — это бумажный портфель/список наблюдения, а не реальные позиции.

## Переменные

См. корневой `.env.example`. Для бота используются `BONDBOT_*`:

- `BONDBOT_DB_PATH`
- `BONDBOT_VK_GROUP_TOKEN`, `BONDBOT_VK_GROUP_ID`, `BONDBOT_VK_ADMIN_USER_ID`
- `BONDBOT_MIN_YIELD_PCT`, `BONDBOT_MAX_YIELD_PCT`, `BONDBOT_MAX_DURATION_YEARS`, `BONDBOT_MIN_RATING`
- `BONDBOT_POSITION_SIZE_RUB`, `BONDBOT_MAX_PCT_DAILY_VOLUME`
- `BONDBOT_OPENAI_BASE_URL`, `BONDBOT_OPENAI_API_KEY`, `BONDBOT_OPENAI_MODEL`
