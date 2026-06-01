"""
Resolution station coordinate registry.

# VERIFY against live market rules before trading.
# For each city, open the Polymarket market and confirm:
#   "recorded at the [STATION_NAME] Station"
# The #1 documented loss cause is wrong station coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StationInfo:
    lat: float    # decimal degrees
    lon: float    # decimal degrees
    station: str  # ICAO or WMO code
    unit: str     # "F" (US) or "C" (Asia/Europe)


# VERIFY: each entry must match the exact station named in the live Polymarket market rules.
STATIONS: dict[str, StationInfo] = {
    # --- United States (°F) ---
    "New York":  StationInfo(lat=40.7772, lon=-73.8726, station="KLGA",  unit="F"),  # LaGuardia
    "Atlanta":   StationInfo(lat=33.6407, lon=-84.4277, station="KATL",  unit="F"),  # Hartsfield-Jackson
    "Miami":     StationInfo(lat=25.7959, lon=-80.2870, station="KMIA",  unit="F"),  # Miami Intl
    "Chicago":   StationInfo(lat=41.9742, lon=-87.9073, station="KORD",  unit="F"),  # O'Hare
    "Dallas":    StationInfo(lat=32.8481, lon=-96.8512, station="KDAL",  unit="F"),  # Dallas Love Field
    # --- Asia / Europe (°C) ---
    "Tokyo":     StationInfo(lat=35.5494, lon=139.7798, station="RJTT",  unit="C"),  # Haneda (NOT Narita)
    "Hong Kong": StationInfo(lat=22.3089, lon=114.1747, station="HKO",   unit="C"),  # HK Observatory
    "Singapore": StationInfo(lat=1.3644,  lon=103.9915, station="WSSS",  unit="C"),  # Changi
    "Seoul":     StationInfo(lat=37.4692, lon=126.4503, station="RKSI",  unit="C"),  # Incheon
    "London":    StationInfo(lat=51.5048, lon=0.0495,   station="EGLC",  unit="C"),  # London City
    "Paris":     StationInfo(lat=48.9694, lon=2.4414,   station="LFPB",  unit="C"),  # Le Bourget (NOT CDG)
}
