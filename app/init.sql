-- Підключення необхідних розширень

-- PostGIS: додає підтримку геопросторових типів даних (Geography/Geometry) та функцій
CREATE EXTENSION IF NOT EXISTS postgis;

-- TimescaleDB: оптимізує PostgreSQL для роботи з часовими рядами (Time-Series)
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Створення таблиці для зберігання телеметрії

-- Використовується тип GEOGRAPHY(Point, 4326) для точних розрахунків на сфероїді
CREATE TABLE IF NOT EXISTS positions (
    id        BIGSERIAL PRIMARY KEY,
    object_id TEXT NOT NULL,
    ts        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lat       DOUBLE PRECISION NOT NULL,
    lon       DOUBLE PRECISION NOT NULL,
    speed     DOUBLE PRECISION,
    geom      GEOGRAPHY(Point, 4326) NOT NULL
);

-- Конвертація таблиці у гіпертаблицю (Hypertable)

-- Забезпечує автоматичне партиціонування даних по колонці часу 'ts'
SELECT create_hypertable('positions', 'ts', if_not_exists => TRUE);

-- Створення індексів для оптимізації продуктивності

-- Композитний B-Tree індекс: пришвидшує вибірку історії руху конкретного об'єкта
CREATE INDEX IF NOT EXISTS idx_positions_object_ts ON positions (object_id, ts DESC);

-- Просторовий GIST індекс: пришвидшує геометричні запити (напр. пошук у радіусі)
CREATE INDEX IF NOT EXISTS idx_positions_geom ON positions USING GIST (geom);