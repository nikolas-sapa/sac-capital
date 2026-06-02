from strategies.weather.stations import STATIONS, StationInfo


def test_all_entries_have_required_fields():
    for city, info in STATIONS.items():
        assert isinstance(info, StationInfo), f"{city} is not a StationInfo"
        assert info.lat != 0.0, f"{city} lat is zero"
        assert info.lon != 0.0, f"{city} lon is zero"
        assert info.station, f"{city} station code missing"
        assert info.unit in ("F", "C"), f"{city} unit must be F or C"


def test_us_cities_use_fahrenheit():
    for city in ("New York", "Atlanta", "Miami", "Chicago", "Dallas"):
        assert STATIONS[city].unit == "F", f"{city} should be Fahrenheit"


def test_asia_europe_use_celsius():
    for city in ("Tokyo", "Hong Kong", "Singapore", "Seoul", "London", "Paris"):
        assert STATIONS[city].unit == "C", f"{city} should be Celsius"


def test_tokyo_is_haneda_not_narita():
    # Haneda (RJTT) ≈ 35.55, 139.78 — NOT Narita (RJNT ≈ 35.77, 140.39)
    t = STATIONS["Tokyo"]
    assert t.station == "RJTT"
    assert abs(t.lat - 35.5494) < 0.05
    assert abs(t.lon - 139.7798) < 0.05


def test_paris_is_le_bourget_not_cdg():
    # Le Bourget (LFPB) ≈ 48.97, 2.44 — NOT CDG (LFPG ≈ 49.01, 2.55)
    p = STATIONS["Paris"]
    assert p.station == "LFPB"
    assert abs(p.lat - 48.9694) < 0.05
    assert abs(p.lon - 2.4414) < 0.05


def test_nyc_is_laguardia():
    nyc = STATIONS["New York"]
    assert nyc.station == "KLGA"


def test_station_count():
    assert len(STATIONS) >= 45


def test_nyc_alias_exists_and_matches_laguardia():
    assert "NYC" in STATIONS
    assert STATIONS["NYC"].station == "KLGA"
    assert STATIONS["NYC"].unit == "F"


def test_new_us_cities_use_fahrenheit():
    for city in ("NYC", "Houston", "Seattle", "San Francisco", "Los Angeles", "Austin", "Denver"):
        assert STATIONS[city].unit == "F", f"{city} should be Fahrenheit"


def test_new_asia_cities_use_celsius():
    for city in ("Beijing", "Shanghai", "Seoul", "Busan", "Taipei", "Manila", "Kuala Lumpur"):
        assert STATIONS[city].unit == "C", f"{city} should be Celsius"


def test_new_europe_cities_use_celsius():
    for city in ("Munich", "Milan", "Amsterdam", "Warsaw", "Helsinki", "Madrid", "Moscow"):
        assert STATIONS[city].unit == "C", f"{city} should be Celsius"
