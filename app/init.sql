-- Initializes the PostgreSQL database with TimescaleDB + PostGIS for tracking.
-- Creates extensions, table `positions`, indexes, and converts it to a hypertable.

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create the positions table if it doesn't exist
CREATE TABLE IF NOT EXISTS positions (
    id        BIGSERIAL PRIMARY KEY,
    object_id TEXT NOT NULL,
    ts        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lat       DOUBLE PRECISION NOT NULL,
    lon       DOUBLE PRECISION NOT NULL,
    speed     DOUBLE PRECISION,
    geom      GEOGRAPHY(Point, 4326) NOT NULL
);

-- Convert to hypertable on column ts
SELECT create_hypertable('positions', 'ts', if_not_exists => TRUE);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_positions_object_ts ON positions (object_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_positions_geom ON positions USING GIST (geom);

