from math import atan2, cos, radians, sin, sqrt
from typing import Dict, List

EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    lat1_rad, lon1_rad = radians(lat1), radians(lon1)
    lat2_rad, lon2_rad = radians(lat2), radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def compute_total_distance(path: List[Dict]) -> float:
    """Sum haversine distances between sequential points."""
    if len(path) < 2:
        return 0.0
    distance = 0.0
    for prev, curr in zip(path, path[1:]):
        distance += haversine(
            prev["latitude"],
            prev["longitude"],
            curr["latitude"],
            curr["longitude"],
        )
    return round(distance, 3)


def compute_average_speed(path: List[Dict]) -> float:
    """Average speed (km/h) across samples."""
    speeds = [float(p.get("speed", 0) or 0) for p in path]
    if not speeds:
        return 0.0
    avg = sum(speeds) / len(speeds)
    return round(avg, 2)


def detect_stops(path: List[Dict], threshold_kmh: float = 1.0) -> List[Dict[str, int]]:
    """Detect contiguous segments where speed below threshold."""
    segments: List[Dict[str, int]] = []
    start = None
    for record in path:
        speed = float(record.get("speed", 0) or 0)
        iteration_id = int(record.get("iteration_id", 0))
        if speed < threshold_kmh:
            if start is None:
                start = iteration_id
        else:
            if start is not None:
                segments.append({"from": start, "to": iteration_id})
                start = None
    if start is not None and path:
        segments.append({"from": start, "to": int(path[-1].get("iteration_id", start))})
    return segments


def path_to_xy(path: List[Dict]) -> Dict[str, List[float]]:
    """Normalize path to planar offsets (meters)."""
    if not path:
        return {"x": [], "y": []}
    origin = path[0]
    origin_lat = origin["latitude"]
    origin_lon = origin["longitude"]

    xs: List[float] = []
    ys: List[float] = []

    for record in path:
        dlat = record["latitude"] - origin_lat
        dlon = record["longitude"] - origin_lon
        # approximate meters per degree
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = 111_320.0 * cos(radians(origin_lat))
        y = dlat * meters_per_deg_lat
        x = dlon * meters_per_deg_lon
        xs.append(round(x, 2))
        ys.append(round(y, 2))

    return {"x": xs, "y": ys}
