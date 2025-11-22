# Delivery Tracking MVP

Короткий приклад сервісу для відстеження об’єктів у реальному часі:
- бекенд на FastAPI (Python)
- PostgreSQL з TimescaleDB + PostGIS (через Docker)
- проста мапа на Leaflet (`/map`)
- опціональний симулятор позицій (`simulator.py`)

## Структура

```
delivery_mvp/
  app/
    main.py          # FastAPI: /track, /last_positions, /map
    requirements.txt # Залежності бекенду
    init.sql         # Розширення, таблиця positions, індекси, hypertable
  frontend/
    index.html       # Проста сторінка з мапою (Leaflet)
  simulator.py      # Симулятор відправки позицій на бекенд
  docker-compose.yml# Сервіси: db, app, pgadmin
```

## Запуск

Docker (база, API, pgAdmin):

```
cd delivery_mvp
docker compose up --build
```

Порти:
- db: 5432 (Postgres + TimescaleDB + PostGIS)
- app: 8000 (FastAPI)
- pgadmin: 5050 (pgAdmin)

pgAdmin: `http://localhost:5050` (email: `admin@example.com`, пароль: `admin`).
Підключення до БД в pgAdmin: host `db`, port `5432`, user `postgres`, password `postgres`, db `delivery`.

Зупинка:

```
docker compose down
```

## Ендпоїнти

- `GET /map` — сторінка з мапою
- `GET /docs` — Swagger UI
- `GET /health` — перевірка стану
- `POST /track` — прийом позиції об’єкта
  Приклад JSON: `{ "object_id": "car-1", "lat": 50.45, "lon": 30.52, "speed": 12.3 }`
- `GET /last_positions` — остання позиція для кожного `object_id`

## Симулятор (опційно)

Надсилає випадкові позиції на бекенд:

```
cd delivery_mvp
python simulator.py --count 4 --interval 2.0
```

Параметри:
- `--count` — кількість об’єктів (за замовчуванням 3)
- `--interval` — інтервал відправлення (сек.) (за замовчуванням 2.0)
- `--endpoint` — URL ендпоїнту `/track` (за замовчуванням `http://localhost:8000/track`)

## Налаштування

Змінні середовища БД задаються у `docker-compose.yml` (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD).
Зазвичай міняти нічого не потрібно для локального запуску.

