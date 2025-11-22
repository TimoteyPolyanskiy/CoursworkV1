"""
Простий FastAPI бекенд для відстеження доставки (TimescaleDB + PostGIS).
Ендпоїнти: /track, /last_positions, /map
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy import create_engine, text
from app.builder import (
    compute_average_speed,
    compute_total_distance,
    detect_stops,
    path_to_xy,
)


# Налаштування середовища (див. docker-compose)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "delivery_v2")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admintp")

# Шлях до фронтенду
APP_BASE_DIR = Path(os.getenv("APP_BASE_DIR", Path(__file__).resolve().parent.parent))
FRONTEND_INDEX = APP_BASE_DIR / "frontend" / "index.html"
FRONTEND_MONITOR = APP_BASE_DIR / "frontend" / "monitor.html"

# In-memory positions log (FORMAT A)
positions_log: List[dict] = []
# Object roles mapping provided by simulator
object_roles: Dict[str, str] = {}


class TrackPayload(BaseModel):
    """Модель даних для /track."""

    object_id: str = Field(..., description="Унікальний ідентифікатор об'єкта")
    lat: float = Field(..., description="Широта (WGS84)")
    lon: float = Field(..., description="Довгота (WGS84)")
    speed: Optional[float] = Field(None, description="Speed (km/h, optional)")

    @validator("object_id")
    def validate_object_id(cls, v: str) -> str:
        if not v.startswith("obj_"):
            raise ValueError("object_id must start with 'obj_'")
        return v

    @validator("lat")
    def validate_lat(cls, v: float) -> float:
        if not (-90.0 <= v <= 90.0):
            raise ValueError("lat must be between -90 and 90")
        return v

    @validator("lon")
    def validate_lon(cls, v: float) -> float:
        if not (-180.0 <= v <= 180.0):
            raise ValueError("lon must be between -180 and 180")
        return v


app = FastAPI(title="Delivery Tracking MVP", version="0.1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)


@app.get("/health")
def health() -> dict:
    """Перевірка стану сервісу."""
    return {"status": "ok"}


@app.get("/health/db")
def health_db() -> dict:
    """Simple DB connectivity check."""
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        print("DB error in /health/db:", repr(e))
        raise HTTPException(status_code=500, detail=f"DB health failed: {e}")
    return {"db": "ok"}


@app.post("/track")
def track_position(payload: TrackPayload) -> JSONResponse:
    """Приймає одну позицію об'єкта та зберігає в БД."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO positions (object_id, lat, lon, speed, geom)
                    VALUES (:object_id, :lat, :lon, :speed,
                            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)
                    """
                ),
                {
                    "object_id": payload.object_id,
                    "lat": payload.lat,
                    "lon": payload.lon,
                    "speed": payload.speed,
                },
            )
    except Exception as e:
        print("DB error in /track:", repr(e))
        raise HTTPException(status_code=500, detail=f"DB insert failed: {e}")

    # Append to in-memory log using FORMAT A and safe types
    timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    raw_speed = float(payload.speed) if payload.speed is not None else 0.0
    speed_int = int(round(raw_speed)) if raw_speed else 0
    status = "Stopped" if raw_speed <= 0.5 else "Moving"
    positions_log.append(
        {
            "iteration_id": len(positions_log) + 1,
            "timestamp": timestamp,
            "object_id": payload.object_id,
            "latitude": float(payload.lat),
            "longitude": float(payload.lon),
            "speed": speed_int,
            "status": status,
        }
    )

    return JSONResponse({"status": "ok"})


@app.get("/last_positions")
def last_positions() -> List[dict]:
    """Остання позиція для кожного об'єкта."""
    sql = text(
        """
        SELECT DISTINCT ON (object_id)
            object_id, ts, lat, lon, speed
        FROM positions
        ORDER BY object_id, ts DESC
        """
    )
    try:
        with engine.begin() as conn:
            rows = conn.execute(sql).mappings().all()
            return [
                {
                    "object_id": r["object_id"],
                    "ts": r["ts"].isoformat(),
                    "lat": float(r["lat"]),
                    "lon": float(r["lon"]),
                    "speed": (
                        int(round(float(r["speed"])))
                        if r["speed"] is not None
                        else None
                    ),
                }
                for r in rows
            ]
    except Exception as e:
        print("DB error in /last_positions:", repr(e))
        raise HTTPException(status_code=500, detail=f"DB query failed: {e}")


@app.get("/")
def root() -> RedirectResponse:
    """Редірект на інтерфейс мапи."""
    return RedirectResponse(url="/map")


@app.get("/map")
def map_page() -> FileResponse:
    """Повертає HTML сторінку з мапою."""
    if not FRONTEND_INDEX.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Frontend index not found at {FRONTEND_INDEX}",
        )
    return FileResponse(FRONTEND_INDEX)


@app.get("/monitor")
def monitor_page() -> FileResponse:
    """Serve monitoring dashboard."""
    if not FRONTEND_MONITOR.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Frontend monitor not found at {FRONTEND_MONITOR}",
        )
    return FileResponse(FRONTEND_MONITOR)


@app.get("/object_roles")
def get_object_roles_endpoint() -> Dict[str, str]:
    """Return the latest object role assignments."""
    return object_roles


@app.post("/object_roles")
def set_object_roles_endpoint(mapping: Dict[str, str]) -> dict:
    """Update the current role mapping (called by simulator)."""
    object_roles.clear()
    for key, value in mapping.items():
        object_roles[str(key)] = str(value)
    return {"status": "ok", "count": len(object_roles)}


@app.get("/positions_log")
def get_positions_log() -> List[dict]:
    """Return in-memory positions log in FORMAT A with safe JSON types."""
    return [
        {
            "iteration_id": int(entry["iteration_id"]),
            "timestamp": str(entry["timestamp"]),
            "object_id": str(entry["object_id"]),
            "latitude": float(entry["latitude"]),
            "longitude": float(entry["longitude"]),
            "speed": int(entry["speed"]),
            "status": str(entry["status"]),
        }
        for entry in positions_log
    ]


@app.get("/object_list")
def get_object_list() -> List[str]:
    """Return sorted list of unique object IDs from the log."""
    uniq = sorted({entry["object_id"] for entry in positions_log})
    return uniq


@app.get("/object_path")
def get_object_path(object_id: str) -> List[dict]:
    """Return ordered path for the given object from in-memory log."""
    filtered = [
        {
            "iteration_id": entry["iteration_id"],
            "latitude": entry["latitude"],
            "longitude": entry["longitude"],
            "timestamp": entry["timestamp"],
        }
        for entry in positions_log
        if entry["object_id"] == object_id
    ]
    filtered.sort(key=lambda e: e["iteration_id"])
    return filtered


def _analytics_path(object_id: str) -> List[dict]:
    path = [
        {
            "iteration_id": int(entry["iteration_id"]),
            "timestamp": str(entry["timestamp"]),
            "latitude": float(entry["latitude"]),
            "longitude": float(entry["longitude"]),
            "speed": float(entry["speed"]),
        }
        for entry in positions_log
        if entry["object_id"] == object_id
    ]
    path.sort(key=lambda e: e["iteration_id"])
    return path


@app.get("/analytics/object_ids")
def analytics_object_ids() -> List[str]:
    return sorted({entry["object_id"] for entry in positions_log})


@app.get("/analytics/path/{object_id}")
def analytics_path(object_id: str) -> List[dict]:
    return _analytics_path(object_id)


@app.get("/analytics/metrics/{object_id}")
def analytics_metrics(object_id: str) -> dict:
    path = _analytics_path(object_id)
    return {
        "total_distance_km": compute_total_distance(path),
        "average_speed_kmh": compute_average_speed(path),
        "stops": detect_stops(path),
    }


@app.get("/analytics/diagram/{object_id}")
def analytics_diagram(object_id: str) -> dict:
    path = _analytics_path(object_id)
    return path_to_xy(path)


# Локальний запуск (поза контейнером)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
