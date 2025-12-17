import os
import sys
import subprocess
import signal
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, validator
from sqlalchemy import create_engine, text
from app.builder import (
    compute_average_speed,
    compute_total_distance,
    detect_stops,
    path_to_xy,
)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "delivery_v2")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admintp")

APP_BASE_DIR = Path(os.getenv("APP_BASE_DIR", Path(__file__).resolve().parent.parent))
FRONTEND_INDEX = APP_BASE_DIR / "frontend" / "index.html"
FRONTEND_MONITOR = APP_BASE_DIR / "frontend" / "monitor.html"

positions_log: List[dict] = []
object_roles: Dict[str, str] = {}

sim_process: Optional[subprocess.Popen] = None

START_LAT = 49.840048
START_LON = 24.021917

class TrackPayload(BaseModel):
    object_id: str
    lat: float
    lon: float
    speed: Optional[float] = None

    @validator("object_id")
    def validate_id(cls, v):
        if not v.startswith("obj_"): raise ValueError("Invalid ID")
        return v

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

@app.on_event("startup")
def startup_event():
    print("System Startup: Cleaning DB...")
    positions_log.clear()
    try:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE positions RESTART IDENTITY;"))
            
            for i in range(1, 4):
                obj_id = f"obj_{i}"
                conn.execute(text(
                    "INSERT INTO positions (object_id, lat, lon, speed, geom) "
                    "VALUES (:id, :lat, :lon, 0, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)"
                ), {"id": obj_id, "lat": START_LAT, "lon": START_LON})
                
                positions_log.append({
                    "iteration_id": i,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "object_id": obj_id,
                    "latitude": START_LAT,
                    "longitude": START_LON,
                    "speed": 0, 
                    "status": "Stopped"
                })
        print(f"Spawned at: {START_LAT}, {START_LON}")
    except Exception as e:
        print(f"Startup Error: {e}")


@app.get("/simulation/status")
def get_sim_status():
    global sim_process
    is_running = sim_process is not None and sim_process.poll() is None
    return {"running": is_running}

@app.post("/simulation/start")
def start_simulation():
    global sim_process
    if sim_process is not None and sim_process.poll() is None:
        return {"status": "already_running"}
    
    try:
        sim_process = subprocess.Popen([sys.executable, "simulator.py"])
        return {"status": "started", "pid": sim_process.pid}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/simulation/stop")
def stop_simulation():
    global sim_process
    if sim_process is None:
        return {"status": "not_running"}
    
    try:
        sim_process.terminate()
        try:
            sim_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            sim_process.kill()
        
        sim_process = None
        return {"status": "stopped"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/track")
def track_position(payload: TrackPayload):
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO positions (object_id, lat, lon, speed, geom) "
                "VALUES (:id, :lat, :lon, :spd, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)"
            ), {"id": payload.object_id, "lat": payload.lat, "lon": payload.lon, "spd": payload.speed})
    except Exception as e:
        return JSONResponse({"status": "error"}, status_code=500)

    spd = int(round(payload.speed or 0))
    positions_log.append({
        "iteration_id": len(positions_log) + 1,
        "timestamp": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "object_id": payload.object_id,
        "latitude": payload.lat,
        "longitude": payload.lon,
        "speed": spd,
        "status": "Stopped" if spd <= 1.0 else "Moving",
    })
    return {"status": "ok"}

@app.get("/last_positions")
def last_positions():
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(
                "SELECT DISTINCT ON (object_id) object_id, ts, lat, lon, speed FROM positions ORDER BY object_id, ts DESC"
            )).mappings().all()
            return [{
                "object_id": r["object_id"],
                "ts": r["ts"].isoformat(),
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "speed": int(round(r["speed"] or 0))
            } for r in rows]
    except Exception:
        return []

@app.get("/")
def root(): return RedirectResponse(url="/map")
@app.get("/map")
def map_page(): return FileResponse(FRONTEND_INDEX)
@app.get("/monitor")
def monitor_page(): return FileResponse(FRONTEND_MONITOR)
@app.get("/object_roles")
def get_roles(): return object_roles
@app.post("/object_roles")
def set_roles(m: Dict[str, str]):
    object_roles.clear()
    object_roles.update(m)
    return {"status": "ok"}
@app.get("/positions_log")
def get_log(): return positions_log
@app.get("/analytics/object_ids")
def get_ids(): return sorted({e["object_id"] for e in positions_log})
@app.get("/analytics/metrics/{object_id}")
def get_metrics(object_id: str):
    path = [p for p in positions_log if p["object_id"] == object_id]
    return {
        "total_distance_km": compute_total_distance(path),
        "average_speed_kmh": compute_average_speed(path),
        "stops": detect_stops(path),
    }
@app.get("/analytics/diagram/{object_id}")
def get_diagram(object_id: str):
    path = [p for p in positions_log if p["object_id"] == object_id]
    return path_to_xy(path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)