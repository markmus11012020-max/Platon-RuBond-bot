# Deployment runbook — Platon RuBond VK bot

## Текущая схема VPS

| Компонент | Проект | Порт | VK-группа |
|---|---|---|---|
| Freelance-бот | `freelance-bot` | `127.0.0.1:8080` | 242715231 |
| Bondbot | `platon-bond-bot` | `127.0.0.1:8081` | 242762834 |
| Caddy (freelance) | `freelance-bot` | 80/443 | — |

Caddy и freelance-бот не трогаем. У bondbot отдельные compose-project, база, каталог данных и VK-сообщество.

## Каталог и данные

```
/opt/platon-bond-bot/
  .env                  # секреты, chmod 600
  bondbot-data/
    bondbot.db          # SQLite
    backups/            # ежедневные копии
```

## Обновление

```bash
cd /opt/platon-bond-bot
git pull --ff-only
chown -R 10001:10001 bondbot-data
docker compose -p platon-bond-bot -f docker-compose.bondbot.yml up -d --build
docker compose -p platon-bond-bot -f docker-compose.bondbot.yml ps
curl -s http://127.0.0.1:8081/healthz
docker logs --tail 80 platon-bond-bot-bondbot-1
```

## Первичная загрузка / ручные операции

```bash
docker exec platon-bond-bot-bondbot-1 python -m bondbot.cli update --pages 3
docker exec platon-bond-bot-bondbot-1 python -m bondbot.cli details
docker exec platon-bond-bot-bondbot-1 python -m bondbot.cli rate
docker exec platon-bond-bot-bondbot-1 python -m bondbot.cli safe --limit 5
docker exec platon-bond-bot-bondbot-1 python -m bondbot.cli exit
docker exec platon-bond-bot-bondbot-1 python -m bondbot.cli alloc
docker exec platon-bond-bot-bondbot-1 python -m bondbot.cli digest
docker exec platon-bond-bot-bondbot-1 python -m bondbot.cli jobs
docker exec platon-bond-bot-bondbot-1 python -m bondbot.cli backup
docker exec platon-bond-bot-bondbot-1 python -m bondbot.cli repair
```

## Бэкап и восстановление

```bash
# копия
docker exec platon-bond-bot-bondbot-1 python -m bondbot.cli backup

# восстановление: остановить бота, заменить БД, запустить
docker compose -p platon-bond-bot -f docker-compose.bondbot.yml stop
cp bondbot-data/backups/bondbot-YYYYMMDD-HHMMSS.db bondbot-data/bondbot.db
chown 10001:10001 bondbot-data/bondbot.db
docker compose -p platon-bond-bot -f docker-compose.bondbot.yml start
```

## Rollback

1. Вернуть предыдущий commit: `git checkout <previous-sha>`.
2. Вернуть образ `platon-bond-bot:0.1.0` или пересобрать.
3. Восстановить БД из бэкапа, если миграция несовместима.
4. `docker compose -p platon-bond-bot -f docker-compose.bondbot.yml up -d --build`.

## Публичный режим

- `BONDBOT_PUBLIC_ACCESS=1` — доступ для участников сообщества.
- `BONDBOT_COMMUNITY_MEMBERS_ONLY=1` — проверка через VK `groups.isMember`.
- `BONDBOT_DIALOGUE_TTL_MINUTES=120` — короткая память диалога, без профилей.
- `BONDBOT_LLM_DAILY_TOKEN_LIMIT=500000` — лимит на пользователя в сутки.
- Админские команды остаются только `BONDBOT_VK_ADMIN_USER_ID`.

## Брокеры

- T-Invest: задать `BONDBOT_TINVEST_TOKEN` (read-only токен) и при необходимости
  `BONDBOT_TINVEST_ACCOUNT_ID`; проверить `python -m bondbot.cli broker accounts`,
  затем `/broker sync tinvest` в VK или `python -m bondbot.cli broker sync`.
  В образ включены сертификаты Russian Trusted CA (`bondbot/certs/`); при истечении
  обновить их с `https://gu-st.ru/content/lending/`.
- Автосинк: `BONDBOT_BROKER_SYNC_ENABLED=1`, интервал `BONDBOT_BROKER_SYNC_MINUTES`.
- СберИнвестиции: официального API для брокерских счетов физлиц нет. Не добавлять
  неофициальные/скрапинговые коннекторы; использовать импорт брокерского отчёта.

## Правила

- Не выполнять `docker system prune`, не перезапускать `freelance-bot` и Caddy.
- Не публиковать 8081 наружу.
- `.env` не коммитить; токены не выводить в логи.
- После обновления проверить `/healthz`, `last_jobs`, `last_market_refresh`.

## Premarket PWA

Новый слой не заменяет VK-бота и не меняет его базу.

- `apps/web` — Next.js PWA, мобильный интерфейс и установка на экран.
- `services/api` — FastAPI gateway, MCP-клиент и read-only адаптеры.
- `docker-compose.premarket.yml` — отдельный compose-проект `platon-premarket`.
- `infra/Caddyfile.premarket` — site block для `platoninvest.pro`.

Порты на хосте:

- `127.0.0.1:3000` — Next.js;
- `127.0.0.1:8000` — FastAPI.

Caddy проксирует `https://platoninvest.pro/api/*` на API, остальное — на web.
Токен T-Invest MCP хранится только в `.env` на сервере и не попадает в браузер.
LLM включается через `PREMARKET_LLM_ENABLED=1`; ключ берётся из `BONDBOT_OPENAI_API_KEY`.
Если LLM недоступен, чат автоматически падает в детерминированные ответы.

Сборка и запуск:

```bash
docker compose -p platon-premarket -f docker-compose.premarket.yml up -d --build
```

Для VPS с 1 vCPU образы лучше собирать локально или в CI, затем загружать:

```bash
docker save platon-premarket-api:0.1.0 platon-premarket-web:0.1.0 -o premarket-images.tar
gzip -c premarket-images.tar | ssh root@94.228.173.244 'gunzip -c | docker load'
```

Проверка:

```bash
curl -s https://platoninvest.pro/api/health
curl -s -o /dev/null -w '%{http_code}\n' https://platoninvest.pro/
```
