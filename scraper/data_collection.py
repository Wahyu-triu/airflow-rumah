"""
BeliRumah.co Property Scraper
==============================
Scrapes property listings from https://belirumah.co/jual/rumah

Usage:
    pip install requests beautifulsoup4 lxml
    python belirumah_scraper.py

Inputs (edit at bottom of file):
    location (str) : e.g. "bogor"
    pages    (int) : number of listing pages to scrape, e.g. 2

Output fields per listing:
    property_name      (str)       : listing title
    location           (str)       : neighbourhood / district
    property_id        (str)       : numeric ID from the listing URL
    price              (int)       : price in IDR
    land_area_m2       (int|None)  : LT (Luas Tanah) in m²
    building_area_m2   (int|None)  : LB (Luas Bangunan) in m²
    certificate        (str|None)  : e.g. "SHM", "HGB"
    hoek               (bool)      : True if corner lot
    bedrooms           (int|None)  : number of bedrooms (KT)
    bathrooms          (int|None)  : number of bathrooms (KM)
    floors             (int|None)  : number of floors
    electrical_voltage (int|None)  : electrical power in Watts/VA
"""

import json
from utils import scrape_belirumah


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # ── Inputs ──────────────────────────────────────────────────────────────
    location = "bogor"
    pages    = 2
    # ────────────────────────────────────────────────────────────────────────

    listings = scrape_belirumah(location=location, pages=pages)

    print(f"\n{'='*60}")
    print(f"Scraped {len(listings)} listings  |  location='{location}'  |  pages={pages}")
    print(f"{'='*60}\n")

    for i, p in enumerate(listings, 1):
        price_str = f"Rp {p['price']:,}" if p['price'] else "N/A"
        print(f"[{i:>3}] {p['property_name']}")
        print(f"       ID          : {p['property_id']}")
        print(f"       Location    : {p['location']}")
        print(f"       Price       : {price_str}")
        print(f"       Land / Bldg : {p['land_area_m2']} m² / {p['building_area_m2']} m²")
        print(f"       Certificate : {p['certificate']}")
        print(f"       Hoek        : {p['hoek']}")
        print(f"       Bed / Bath  : {p['bedrooms']} / {p['bathrooms']}")
        print(f"       Floors      : {p['floors']}")
        print(f"       Electricity : {p['electrical_voltage']} W")
        print()

    output_file = "belirumah_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)
    print(f"Results saved → {output_file}")