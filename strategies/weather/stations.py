"""
Resolution station coordinate registry.

# VERIFY against live market rules before trading.
# For each city, open the Polymarket market and confirm which station is named.
# The #1 documented loss cause is wrong station coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StationInfo:
    lat: float    # decimal degrees
    lon: float    # decimal degrees
    station: str  # ICAO or WMO code (reference only — not used in API call)
    unit: str     # "F" (US) or "C" (rest of world)


# VERIFY: each entry must match the exact station named in the live Polymarket market rules.
STATIONS: dict[str, StationInfo] = {
    # ---------------------------------------------------------------------------
    # United States (°F)
    # ---------------------------------------------------------------------------
    "NYC":           StationInfo(lat=40.7772,  lon=-73.8726,   station="KLGA",  unit="F"),  # LaGuardia
    "New York":      StationInfo(lat=40.7772,  lon=-73.8726,   station="KLGA",  unit="F"),  # alias
    "Atlanta":       StationInfo(lat=33.6407,  lon=-84.4277,   station="KATL",  unit="F"),  # Hartsfield-Jackson
    "Miami":         StationInfo(lat=25.7959,  lon=-80.2870,   station="KMIA",  unit="F"),  # Miami Intl
    "Chicago":       StationInfo(lat=41.9742,  lon=-87.9073,   station="KORD",  unit="F"),  # O'Hare
    "Dallas":        StationInfo(lat=32.8481,  lon=-96.8512,   station="KDAL",  unit="F"),  # Dallas Love Field
    "Houston":       StationInfo(lat=29.6454,  lon=-95.2789,   station="KHOU",  unit="F"),  # Hobby
    "Seattle":       StationInfo(lat=47.4502,  lon=-122.3088,  station="KSEA",  unit="F"),  # SeaTac
    "San Francisco": StationInfo(lat=37.6213,  lon=-122.3790,  station="KSFO",  unit="F"),  # SFO
    "Los Angeles":   StationInfo(lat=33.9425,  lon=-118.4081,  station="KLAX",  unit="F"),  # LAX
    "Austin":        StationInfo(lat=30.1975,  lon=-97.6664,   station="KAUS",  unit="F"),  # Austin-Bergstrom
    "Denver":        StationInfo(lat=39.8561,  lon=-104.6737,  station="KDEN",  unit="F"),  # Denver Intl

    # ---------------------------------------------------------------------------
    # East Asia (°C)
    # ---------------------------------------------------------------------------
    "Tokyo":         StationInfo(lat=35.5494,  lon=139.7798,   station="RJTT",  unit="C"),  # Haneda (NOT Narita)
    "Seoul":         StationInfo(lat=37.4692,  lon=126.4503,   station="RKSI",  unit="C"),  # Incheon
    "Busan":         StationInfo(lat=35.1796,  lon=128.9383,   station="RKPK",  unit="C"),  # Gimhae
    "Beijing":       StationInfo(lat=40.0799,  lon=116.5848,   station="ZBAA",  unit="C"),  # Capital Intl
    "Shanghai":      StationInfo(lat=31.1434,  lon=121.8052,   station="ZSPD",  unit="C"),  # Pudong
    "Shenzhen":      StationInfo(lat=22.6393,  lon=113.8108,   station="ZGSZ",  unit="C"),  # Shenzhen Bao'an
    "Guangzhou":     StationInfo(lat=23.3924,  lon=113.2988,   station="ZGGG",  unit="C"),  # Baiyun
    "Chongqing":     StationInfo(lat=29.7192,  lon=106.6414,   station="ZUCK",  unit="C"),  # Jiangbei
    "Chengdu":       StationInfo(lat=30.5785,  lon=103.9470,   station="ZUUU",  unit="C"),  # Shuangliu
    "Wuhan":         StationInfo(lat=30.7838,  lon=114.2088,   station="ZHHH",  unit="C"),  # Tianhe
    "Qingdao":       StationInfo(lat=36.2661,  lon=120.3747,   station="ZSQD",  unit="C"),  # Jiaodong
    "Taipei":        StationInfo(lat=25.0777,  lon=121.2333,   station="RCTP",  unit="C"),  # Taoyuan
    "Hong Kong":     StationInfo(lat=22.3089,  lon=114.1747,   station="HKO",   unit="C"),  # HK Observatory
    "Singapore":     StationInfo(lat=1.3644,   lon=103.9915,   station="WSSS",  unit="C"),  # Changi
    "Kuala Lumpur":  StationInfo(lat=2.7456,   lon=101.7099,   station="WMKK",  unit="C"),  # KLIA
    "Manila":        StationInfo(lat=14.5086,  lon=121.0197,   station="RPLL",  unit="C"),  # Ninoy Aquino
    "Lucknow":       StationInfo(lat=26.7606,  lon=80.8893,    station="VILK",  unit="C"),  # Chaudhary Charan Singh

    # ---------------------------------------------------------------------------
    # South / West Asia (°C)
    # ---------------------------------------------------------------------------
    "Karachi":       StationInfo(lat=24.9008,  lon=67.1608,    station="OPKC",  unit="C"),  # Jinnah Intl
    "Istanbul":      StationInfo(lat=41.2753,  lon=28.7519,    station="LTFM",  unit="C"),  # Istanbul Airport
    "Ankara":        StationInfo(lat=40.1282,  lon=32.9951,    station="LTAC",  unit="C"),  # Esenboga
    "Tel Aviv":      StationInfo(lat=32.0055,  lon=34.8854,    station="LLBG",  unit="C"),  # Ben Gurion
    "Jeddah":        StationInfo(lat=21.6796,  lon=39.1565,    station="OEJN",  unit="C"),  # King Abdulaziz

    # ---------------------------------------------------------------------------
    # Europe (°C)
    # ---------------------------------------------------------------------------
    "London":        StationInfo(lat=51.5048,  lon=0.0495,     station="EGLC",  unit="C"),  # London City
    "Paris":         StationInfo(lat=48.9694,  lon=2.4414,     station="LFPB",  unit="C"),  # Le Bourget (NOT CDG)
    "Madrid":        StationInfo(lat=40.4936,  lon=-3.5671,    station="LEMD",  unit="C"),  # Barajas
    "Amsterdam":     StationInfo(lat=52.3105,  lon=4.7683,     station="EHAM",  unit="C"),  # Schiphol
    "Munich":        StationInfo(lat=48.3538,  lon=11.7861,    station="EDDM",  unit="C"),  # Franz Josef Strauss
    "Milan":         StationInfo(lat=45.4654,  lon=9.2790,     station="LIML",  unit="C"),  # Linate
    "Warsaw":        StationInfo(lat=52.1672,  lon=20.9679,    station="EPWA",  unit="C"),  # Chopin
    "Helsinki":      StationInfo(lat=60.3172,  lon=24.9633,    station="EFHK",  unit="C"),  # Vantaa
    "Moscow":        StationInfo(lat=55.9736,  lon=37.4125,    station="UUEE",  unit="C"),  # Sheremetyevo

    # ---------------------------------------------------------------------------
    # Americas (°C)
    # ---------------------------------------------------------------------------
    "Toronto":       StationInfo(lat=43.6772,  lon=-79.6306,   station="CYYZ",  unit="C"),  # Pearson
    "Mexico City":   StationInfo(lat=19.4363,  lon=-99.0721,   station="MMMX",  unit="C"),  # Benito Juarez
    "Panama City":   StationInfo(lat=9.0714,   lon=-79.3835,   station="MPTO",  unit="C"),  # Tocumen
    "Buenos Aires":  StationInfo(lat=-34.8222, lon=-58.5358,   station="SAEZ",  unit="C"),  # Ezeiza
    "Sao Paulo":     StationInfo(lat=-23.4356, lon=-46.4731,   station="SBGR",  unit="C"),  # Guarulhos

    # ---------------------------------------------------------------------------
    # Africa / Oceania (°C)
    # ---------------------------------------------------------------------------
    "Cape Town":     StationInfo(lat=-33.9715, lon=18.6021,    station="FACT",  unit="C"),  # Cape Town Intl
    "Wellington":    StationInfo(lat=-41.3272, lon=174.8052,   station="NZWN",  unit="C"),  # Wellington Intl
}
