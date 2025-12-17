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
    if len(path) < 2:
        return 0.0

    path = sorted(path, key=lambda x: x['iteration_id'])
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
    speeds = [float(p.get("speed", 0) or 0) for p in path]
    if not speeds:
        return 0.0
    avg = sum(speeds) / len(speeds)
    return round(avg, 2)


def detect_stops(path: List[Dict], threshold_kmh: float = 1.0) -> List[Dict[str, int]]:

    path = sorted(path, key=lambda x: x['iteration_id'])
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
        return {"x": [], "y": [], "lats": [], "lons": []}
    

    path = sorted(path, key=lambda x: x['iteration_id'])

    origin = path[0]
    origin_lat = origin["latitude"]
    origin_lon = origin["longitude"]

    xs: List[float] = []
    ys: List[float] = []
    lats: List[float] = []
    lons: List[float] = []

    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = 111_320.0 * cos(radians(origin_lat))

    for record in path:
        clat = record["latitude"]
        clon = record["longitude"]
        
        dlat = clat - origin_lat
        dlon = clon - origin_lon
        
        y = dlat * meters_per_deg_lat
        x = dlon * meters_per_deg_lon
        
        xs.append(round(x, 2))
        ys.append(round(y, 2))
        lats.append(clat)
        lons.append(clon)

    return {"x": xs, "y": ys, "lats": lats, "lons": lons}