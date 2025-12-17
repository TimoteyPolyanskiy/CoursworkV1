import time
import math
import random
import json
import urllib.request
import urllib.error
from typing import List, Tuple, Dict

BACKEND_URL = "http://localhost:8000/track"
OSRM_URL = "http://router.project-osrm.org"
START_HUB = (49.840048, 24.021917) 

UPDATE_INTERVAL = 1.0  
METERS_PER_SEGMENT = 2.0 

ROLE_CONFIG = {
    "car": {"speed_range": (35.0, 55.0), "osrm_mode": "driving", "stop_chance": 0.05}, 
    "bicycle": {"speed_range": (15.0, 25.0), "osrm_mode": "bike", "stop_chance": 0.02},
    "pedestrian": {"speed_range": (3.0, 5.0), "osrm_mode": "foot", "stop_chance": 0.04},
}

OBJECT_TYPES = ["car", "bicycle", "pedestrian"]
object_roles: Dict[str, str] = {}

def haversine_distance(p1, p2):
    R = 6371000
    lat1, lon1 = map(math.radians, p1)
    lat2, lon2 = map(math.radians, p2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def densify_path(path: List[Tuple[float, float]], step_meters: float) -> List[Tuple[float, float]]:
    if not path: return []
    dense_path = [path[0]]
    for i in range(len(path) - 1):
        p1 = path[i]
        p2 = path[i+1]
        dist = haversine_distance(p1, p2)
        if dist <= step_meters:
            dense_path.append(p2)
            continue
        num_steps = int(dist / step_meters)
        lat_step = (p2[0] - p1[0]) / num_steps
        lon_step = (p2[1] - p1[1]) / num_steps
        for k in range(1, num_steps + 1):
            new_pt = (p1[0] + k * lat_step, p1[1] + k * lon_step)
            dense_path.append(new_pt)
    return dense_path

def get_osrm_route(mode: str, waypoints: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    coords_str = ";".join([f"{lon},{lat}" for lat, lon in waypoints])
    url = f"{OSRM_URL}/route/v1/{mode}/{coords_str}?overview=full&geometries=geojson"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status != 200: return waypoints
            data = json.loads(response.read().decode())
            if not data.get("routes"): return waypoints
            geometry = data["routes"][0]["geometry"]["coordinates"]
            return [(lat, lon) for lon, lat in geometry]
    except Exception:
        return waypoints

def send_point(object_id: str, lat: float, lon: float, speed: float):
    payload = {"object_id": object_id, "lat": lat, "lon": lon, "speed": speed}
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(BACKEND_URL, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=1): pass
    except Exception: pass 

def broadcast_roles():
    url = BACKEND_URL.replace("/track", "/object_roles")
    try:
        data = json.dumps(object_roles).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=2): pass
    except Exception: pass

class Agent:
    def __init__(self, object_id: str, role: str):
        self.object_id = object_id
        self.role = role
        self.config = ROLE_CONFIG[role]
        
        waypoints = self._get_waypoints()
        
        if self.role == "pedestrian":
            raw_path = waypoints 
        else:
            raw_path = get_osrm_route(self.config["osrm_mode"], waypoints)
            
        self.path = densify_path(raw_path, METERS_PER_SEGMENT)
        self.path_len = len(self.path)
        self.current_idx = 0.0
        
        self.stop_ticks = 0
        self.initial_stop_duration = 0 

    def _get_waypoints(self):
        if self.role == "car":
            return [START_HUB, (49.8413, 24.0203), (49.8431, 24.0215), (49.8435, 24.0243), (49.8420, 24.0233), START_HUB]
        elif self.role == "bicycle":
            return [START_HUB, (49.8395, 24.0190), (49.8414, 24.0162), (49.8418, 24.0205), START_HUB]
        else: 
            return [
                START_HUB,                
                (49.83995, 24.02160), 
                (49.83975, 24.02140), 
                (49.83960, 24.02120), 
                (49.83940, 24.02100), 
                (49.83920, 24.02080), 
                (49.83890, 24.02060), 
                (49.83880, 24.02100), 
                (49.83890, 24.02150), 
                (49.83910, 24.02190), 
                (49.83940, 24.02210),
                (49.83970, 24.02200),
                (49.83990, 24.02180), 
                START_HUB                 
            ]

    def step(self):
        if self.stop_ticks > 0:
            self.stop_ticks -= 1
            lat, lon = self.path[int(self.current_idx)]
            
            elapsed = self.initial_stop_duration - self.stop_ticks
            
            should_send = (elapsed <= 2) 
            
            return lat, lon, 0.0, should_send

        if random.random() < self.config["stop_chance"]:
            duration = random.randint(3, 4) 
            self.stop_ticks = duration
            self.initial_stop_duration = duration
            
            lat, lon = self.path[int(self.current_idx)]
            return lat, lon, 0.0, True

        min_s, max_s = self.config["speed_range"]
        current_speed_kmh = random.uniform(min_s, max_s)
        
        speed_ms = current_speed_kmh / 3.6
        distance_moved = speed_ms * UPDATE_INTERVAL
        steps_to_move = distance_moved / METERS_PER_SEGMENT
        
        self.current_idx = (self.current_idx + steps_to_move) % self.path_len
        lat, lon = self.path[int(self.current_idx)]
        
        return lat, lon, current_speed_kmh, True 

def main():
    print("--- Simulation Started ---", flush=True)
    
    roles = OBJECT_TYPES[:]
    random.shuffle(roles)
    for i, role in enumerate(roles):
        object_roles[f"obj_{i+1}"] = role
        
    time.sleep(2)
    broadcast_roles()
    
    agents = [Agent(oid, role) for oid, role in object_roles.items()]
    
    try:
        while True:
            random.shuffle(agents)
            
            for agent in agents:
                lat, lon, speed, should_send = agent.step()
                
                if should_send:
                    send_point(agent.object_id, lat, lon, speed)
            
            time.sleep(UPDATE_INTERVAL)
    except KeyboardInterrupt:
        pass 

if __name__ == "__main__":
    main()