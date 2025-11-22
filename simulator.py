"""
Simple heading-based simulator that sends coordinates for N moving couriers to /track.

Couriers start at different random locations within a Lviv bounding box and move
independently with small random heading changes. Default step is ~100 m per 2 s.

Usage:
  python simulator.py --count 5 --interval 2.0 --endpoint http://localhost:8000/track

No external dependencies required (uses urllib from the standard library).
"""

import argparse
import asyncio
import json
import math
import random
import urllib.request
from typing import Dict, List


ROLE_SPEEDS = {
    "car": (25.0, 60.0),
    "bicycle": (10.0, 25.0),
    "pedestrian": (3.0, 7.0),
}

OBJECT_TYPES = ["car", "bicycle", "pedestrian"]
object_roles: Dict[str, str] = {}
LNU_LAT = 49.839683
LNU_LON = 24.029717


def assign_object_roles(count: int) -> None:
    object_roles.clear()
    roles = OBJECT_TYPES[:]
    random.shuffle(roles)
    for i in range(count):
        role = roles[i % len(roles)]
        object_roles[f"obj_{i+1}"] = role


def broadcast_object_roles(track_endpoint: str) -> None:
    base = track_endpoint.rstrip("/")
    if base.endswith("/track"):
        base = base[: -len("/track")]
    roles_url = base.rstrip("/") + "/object_roles"
    try:
        post_json(roles_url, object_roles)
    except Exception as exc:
        print(f"Failed to push object roles: {exc}")


def post_json(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"HTTP {resp.status}")


def meters_to_deg(lat: float, north_m: float, east_m: float) -> (float, float):
    # 1 deg latitude ~ 111_320 m; 1 deg longitude ~ 111_320 * cos(lat)
    deg_lat = north_m / 111_320.0
    deg_lon = east_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    return deg_lat, deg_lon


class Courier:
    def __init__(
        self,
        object_id: str,
        lat: float,
        lon: float,
        endpoint: str,
        interval: float,
        role: str,
    ) -> None:
        self.object_id = object_id
        self.lat = lat
        self.lon = lon
        self.heading_deg = random.uniform(0, 360)
        self.endpoint = endpoint
        self.interval = interval
        self.role = role
        self.type = role
        self.speed_mps: float = 0.0
        self.speed_kmh: float = 0.0
        self.stop_ticks = 0

    def step(self) -> None:
        if self.stop_ticks > 0:
            self.speed_mps = 0.0
            self.speed_kmh = 0.0
            self.stop_ticks -= 1
            return

        if random.random() < 0.15:
            self.speed_mps = 0.0
            self.speed_kmh = 0.0
            self.stop_ticks = random.randint(1, 5)
            return

        # Small random turn each tick: ±10°..±30°
        turn_mag = random.uniform(10.0, 30.0)
        if random.random() < 0.5:
            turn_mag = -turn_mag
        self.heading_deg = (self.heading_deg + turn_mag) % 360.0

        min_kmh, max_kmh = ROLE_SPEEDS.get(self.role, (10.0, 20.0))
        self.speed_kmh = random.uniform(min_kmh, max_kmh)
        self.speed_mps = self.speed_kmh / 3.6

        dist_m = self.speed_mps * self.interval
        # Heading: 0° = north, 90° = east
        rad = math.radians(self.heading_deg)
        north_m = math.cos(rad) * dist_m
        east_m = math.sin(rad) * dist_m
        dlat, dlon = meters_to_deg(self.lat, north_m, east_m)
        self.lat += dlat
        self.lon += dlon

        # Softly keep within Lviv box by nudging heading back when out of bounds
        if not (49.80 <= self.lat <= 49.88) or not (24.00 <= self.lon <= 24.10):
            # Turn around more aggressively
            self.heading_deg = (self.heading_deg + 180.0 + random.uniform(-20, 20)) % 360.0

    def snapshot(self) -> dict:
        return {
            "object_id": self.object_id,
            "lat": self.lat,
            "lon": self.lon,
            "speed": int(round(float(self.speed_kmh))),
        }


async def run_sim_async(count: int, interval: float, endpoint: str) -> None:
    couriers: List[Courier] = []
    assign_object_roles(count)
    for i in range(count):
        lat = LNU_LAT
        lon = LNU_LON
        obj_id = f"obj_{i+1}"
        role = object_roles.get(obj_id, random.choice(OBJECT_TYPES))
        couriers.append(Courier(obj_id, lat, lon, endpoint, interval, role))

    broadcast_object_roles(endpoint)

    print(f"Sending updates for {count} objects to {endpoint} (Ctrl+C to stop)...")

    try:
        while True:
            random.shuffle(couriers)
            # Advance all couriers and post
            for c in couriers:
                c.step()
                payload = c.snapshot()
                try:
                    await asyncio.to_thread(post_json, endpoint, payload)
                except Exception as e:
                    print(f"Failed to post for {c.object_id}: {e}")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass


def run_sim(count: int, interval: float, endpoint: str) -> None:
    try:
        asyncio.run(run_sim_async(count, interval, endpoint))
    except KeyboardInterrupt:
        print("\nSimulation stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Delivery tracker simulator")
    parser.add_argument("--count", type=int, default=3, help="Number of simulated objects")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between updates")
    parser.add_argument(
        "--endpoint",
        type=str,
        default="http://localhost:8000/track",
        help="POST endpoint for tracking data",
    )
    args = parser.parse_args()

    run_sim(args.count, args.interval, args.endpoint)


if __name__ == "__main__":
    main()
