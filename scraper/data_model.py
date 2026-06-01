# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
from dataclasses import dataclass
from typing import Optional

@dataclass
class PropertyListing:
    property_name:      str           = ""
    location:           str           = ""
    property_id:        str           = ""
    price:              Optional[int] = None
    land_area_m2:       Optional[int] = None
    building_area_m2:   Optional[int] = None
    certificate:        Optional[str] = None
    hoek:               bool          = False
    bedrooms:           Optional[int] = None
    bathrooms:          Optional[int] = None
    floors:             Optional[int] = None
    electrical_voltage: Optional[int] = None