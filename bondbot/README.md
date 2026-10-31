# Platon Bond Bot — VK

Детерминированное ядро для VK-бота по российским облигациям.

## Что уже есть

- парсер screener smart-lab (`/q/bonds/`) — 100 бумаг на страницу;
- парсер карточки бумаги и графика купонов;
- ставка ЦБ с TTL-кэшем и fallback;
- SQLite: бумаги, купоны, watchlist, позиции, аудит стратегий;
- фильтр по доходности, дюрации, рейтингу, цене, объёму и ликвидности;
- расчёт допустимого объёма позиции относительно дневного оборота;
- фильтры по типу купона (постоянный/плавающий/структурный), частоте выплат 2/4/12 в год,
  датам погашения/оферты и полная сортировка по всем полям;
- публичный режим для участников сообщества, без личных профилей и портфелей;
- справочные `/tax` и `/iis`, лимит LLM-токенов на пользователя в день;
- стратегии: `/safe` (коридор ЦБ +5…10 п.п.), `/exit` (ликвидность и выход), `/alloc` (целевая аллокация);
- скоринг стабильности, YTM после налога, модифицированная дюрация, G/Z-спред, carry;
- риск-скор, стресс-тест по ставке, новые выпуски, журнал идей и стратегия недели;
- RSS-новости (Интерфакс, РБК, Коммерсантъ, Ведомости, Banki.ru, smart-lab) с привязкой к бумагам;
- живой поиск по эмитенту, если в RSS нет свежих материалов (DuckDuckGo HTML, кэш 6 часов);
- ИИ-ассистент `/ask` с инструментами (числа берутся из БД, не из LLM);
- CLI для проверки данных без VK.

## CLI

```powershell
.\.venv\Scripts\python -m bondbot.cli update --pages 1
.\.venv\Scripts\python -m bondbot.cli screen --limit 10
.\.venv\Scripts\python -m bondbot.cli bond RU000A10G1T5
.\.venv\Scripts\python -m bondbot.cli rate
.\.venv\Scripts\python -m bondbot.cli safe --limit 5
.\.venv\Scripts\python -m bondbot.cli exit
.\.venv\Scripts\python -m bondbot.cli alloc
.\.venv\Scripts\python -m bondbot.cli audit
.\.venv\Scripts\python -m bondbot.cli watch add RU000A10G1T5
.\.venv\Scripts\python -m bondbot.cli portfolio
```

## VK-команды

`/portfolio`, `/bond ISIN`, `/issuer НАЗВАНИЕ`, `/value ISIN`, `/watch`, `/screen [постоянный|плавающий] [2 4 12]`, `/safe`, `/exit`, `/alloc`,
`/risk [ISIN]`, `/stress [б.п.]`, `/news [ISIN]`, `/new`, `/idea`, `/journal`,
`/preset консервативный|сбалансированный|максимальная доходность`,
`/strategy`, `/relative [ISIN]`, `/calendar [дней]`, `/doctor`, `/whatsnew`,
`/position add|remove|list`, `/ask вопрос`, `/tax [купон]`, `/iis`, `/clear`, `/keyboard`, `/status`,
`/help`, `/broker status|accounts|sync tinvest`.

Обновление портфеля: отправь боту файл `portfolio.html`, сохранённый из Smart-Lab.
Бот заменит состав портфеля, удалит старые позиции и обновит карточки бумаг.
Если VK не передаёт файл, используй `/portfolio url <прямая ссылка на html>`.

Публичные команды доступны участникам сообщества. `/portfolio`, `/position`, `/watch`,
`/exit`, `/alloc`, `/stress`, `/strategy`, `/calendar`, `/doctor`, `/whatsnew`, `/journal`,
`/connect` и `/broker` — только администратору.

Брокеры:

- T-Invest — официальный read-only API (`BONDBOT_TINVEST_TOKEN`). `/broker accounts`
  покажет счета, `/broker sync tinvest` заменит бумажный портфель реальными позициями.
  Автосинк включается через `BONDBOT_BROKER_SYNC_ENABLED=1`.
  В Docker-образ добавлены официальные сертификаты Russian Trusted Root/Sub CA
  (`bondbot/certs/`), без них TLS-запросы к T-Invest API не проходят.
- СберИнвестиции — официального API для брокерских счетов физлиц нет; подключение
  через API невозможно. Рабочий путь — импорт брокерского отчёта Сбера.

Можно не писать `/ask`: любой обычный текст уходит в диалог с ИИ. Бот помнит последние сообщения
в течение `BONDBOT_DIALOGUE_TTL_MINUTES` (по умолчанию 120 минут), сброс — `/clear`.
Персональные профили и портфели пользователей не сохраняются.

В публичном режиме бот принимает команды от участников сообщества
(`BONDBOT_PUBLIC_ACCESS=1`, `BONDBOT_COMMUNITY_MEMBERS_ONLY=1`), админ-команды —
только от `BONDBOT_VK_ADMIN_USER_ID`.

## Планировщик

- `market_refresh` — ежедневно в 23:30 MSK: smart-lab + MOEX ISS, новые выпуски, алерты;
- `detail_refresh` — ежедневно в 10:00 MSK: карточки watchlist и позиций;
- `key_rate` — каждые 6 часов;
- `news_refresh` — каждые 30 минут;
- `digest` — ежедневно в 09:00 MSK;
- `strategy_note` — пятница 19:00 MSK;
- `backup` — ежедневно в 03:00 MSK в `/data/backups`;
- `broker_sync` — каждые `BONDBOT_BROKER_SYNC_MINUTES` минут, если включён
  `BONDBOT_BROKER_SYNC_ENABLED=1` и задан `BONDBOT_TINVEST_TOKEN`.

Все запуски пишутся в `job_runs`; статус виден в `/healthz` и `python -m bondbot.cli jobs`.

## Принципы

- LLM не считает числа. Все метрики берутся из smart-lab/MOEX и хранятся с датой источника.
- Верхняя граница доходности динамическая: ключевая ставка ЦБ + 10 п.п. (по умолчанию). Если ЦБ недоступен, используется последний кэш, затем фиксированный fallback 35%.
- Цена ниже 90% по умолчанию не рекомендуется — это зона риска/амортизации/оферты.
- Позиция 1 млн ₽ не должна быть больше 5% дневного оборота бумаги; отсюда минимальный объём 20 млн ₽.
- Watchlist — это бумажный портфель/список наблюдения, а не реальные позиции.

## Переменные

См. корневой `.env.example`. Для бота используются `BONDBOT_*`:

- `BONDBOT_DB_PATH`
- `BONDBOT_VK_GROUP_TOKEN`, `BONDBOT_VK_GROUP_ID`, `BONDBOT_VK_ADMIN_USER_ID`
- `BONDBOT_PUBLIC_ACCESS`, `BONDBOT_COMMUNITY_MEMBERS_ONLY`, `BONDBOT_DIALOGUE_TTL_MINUTES`
- `BONDBOT_LLM_DAILY_TOKEN_LIMIT` (по умолчанию 500 000 токенов на пользователя в день)
- `BONDBOT_MIN_YIELD_PCT`, `BONDBOT_MAX_YIELD_PCT` (fallback), `BONDBOT_MAX_DURATION_YEARS`, `BONDBOT_MIN_RATING`
- `BONDBOT_DYNAMIC_MAX_YIELD`, `BONDBOT_KEY_RATE_MARGIN_PCT`, `BONDBOT_KEY_RATE_TTL_HOURS`, `BONDBOT_KEY_RATE_TIMEOUT`, `BONDBOT_KEY_RATE_URL`
- `BONDBOT_POSITION_SIZE_RUB`, `BONDBOT_MAX_PCT_DAILY_VOLUME`, `BONDBOT_EXIT_HORIZON_DAYS`
- `BONDBOT_SCHEDULER_ENABLED`, `BONDBOT_REFRESH_HOUR`, `BONDBOT_ALERTS_ENABLED`, `BONDBOT_OWNER_PEER_ID`
- `BONDBOT_NEWS_ENABLED`, `BONDBOT_NEWS_FEEDS`, `BONDBOT_NEWS_INTERVAL_MINUTES`
- `BONDBOT_LIVE_SEARCH_ENABLED`, `BONDBOT_LIVE_SEARCH_TIMEOUT`, `BONDBOT_LIVE_SEARCH_TTL_HOURS`
- `BONDBOT_BROKER_SYNC_ENABLED`, `BONDBOT_BROKER_SYNC_MINUTES`, `BONDBOT_BROKER_TIMEOUT`
- `BONDBOT_TINVEST_TOKEN`, `BONDBOT_TINVEST_ACCOUNT_ID`, `BONDBOT_TINVEST_BASE_URL`
- `BONDBOT_LLM_ENABLED`, `BONDBOT_OPENAI_BASE_URL`, `BONDBOT_OPENAI_API_KEY`, `BONDBOT_OPENAI_MODEL`

## Деплой

```powershell
docker compose -p platon-bond-bot -f docker-compose.bondbot.yml up -d --build
```

Контейнер проекта `platon-bond-bot`, health `127.0.0.1:8081/healthz`, БД `/data/bondbot.db` (bind-каталог `./bondbot-data`). Проект изолирован от freelance-бота: отдельные compose-project, порт, база и VK-сообщество.
