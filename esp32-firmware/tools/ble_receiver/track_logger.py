import csv
import os
import threading
from datetime import datetime


class TrackLogger:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        self.filename = os.path.join(output_dir, f"track_{timestamp}.csv")
        self._lock = threading.Lock()
        with open(self.filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["local_time", "utc_time", "lat", "lon", "speed_kmh", "valid"]
            )

    def log(self, utc_time: str, lat: float, lon: float, speed_kmh: float, valid: bool):
        local_time = datetime.now().astimezone().strftime("%H:%M:%S")
        with self._lock, open(self.filename, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    local_time,
                    utc_time,
                    f"{lat:.6f}",
                    f"{lon:.6f}",
                    f"{speed_kmh:.1f}",
                    int(valid),
                ]
            )
