"""
Debug script for geology API.  py debug_geology.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from src.core.geology import _fetch_ga, classify

TEST_POINTS = [
    (-27.5, 152.5, "Brisbane QLD"),
    (-33.9, 151.2, "Sydney NSW"),
    (-37.8, 145.0, "Melbourne VIC"),
    (-23.7, 133.9, "Alice Springs NT"),
    (-31.9, 115.9, "Perth WA"),
]

for lat, lng, label in TEST_POINTS:
    print(f"\n{label} ({lat}, {lng})")
    result = _fetch_ga(lat, lng)
    if result:
        ec = classify(result["unit_name"], result["lithology"], result["age"])
        print(f"  source:    {result['source']}")
        print(f"  unit_name: {result['unit_name']}")
        print(f"  lithology: {result['lithology'][:80]}")
        print(f"  age:       {result['age']}")
        print(f"  class:     {ec}")
    else:
        print("  GA returned no feature (offshore or outside Australia)")
