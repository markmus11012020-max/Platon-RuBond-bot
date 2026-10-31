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

## Правила

- Не выполнять `docker system prune`, не перезапускать `freelance-bot` и Caddy.
- Не публиковать 8081 наружу.
- `.env` не коммитить; токены не выводить в логи.
- После обновления проверить `/healthz`, `last_jobs`, `last_market_refresh`.
