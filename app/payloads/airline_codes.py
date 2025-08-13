"""
Comprehensive list of airline IATA codes used in flight search payloads
"""

# Complete airline codes with their full names for reference
AIRLINE_CODES = {
    # Major US Carriers
    "AA": "American Airlines",
    "DL": "Delta Air Lines", 
    "UA": "United Airlines",
    "WN": "Southwest Airlines",
    "B6": "JetBlue Airways",
    "NK": "Spirit Airlines",
    "F9": "Frontier Airlines",
    
    # Major European Carriers
    "LH": "Lufthansa",
    "BA": "British Airways",
    "AF": "Air France",
    "KL": "KLM Royal Dutch Airlines",
    "AZ": "ITA Airways (formerly Alitalia)",
    "LX": "Swiss International Air Lines",
    "OS": "Austrian Airlines",
    "SN": "Brussels Airlines",
    "SK": "SAS Scandinavian Airlines",
    "IB": "Iberia",
    "AY": "Finnair",
    "FR": "Ryanair",
    "U2": "easyJet",
    
    # Middle East Carriers
    "EK": "Emirates",
    "QR": "Qatar Airways",
    "EY": "Etihad Airways",
    "GF": "Gulf Air",
    "SV": "Saudi Arabian Airlines (Saudia)",
    "MS": "EgyptAir",
    "RJ": "Royal Jordanian",
    "WY": "Oman Air",
    
    # Asian Carriers
    "SQ": "Singapore Airlines",
    "CX": "Cathay Pacific",
    "TK": "Turkish Airlines",
    "NH": "All Nippon Airways (ANA)",
    "JL": "Japan Airlines (JAL)",
    "TG": "Thai Airways",
    "CI": "China Airlines",
    "BR": "EVA Air",
    "PR": "Philippine Airlines",
    "KE": "Korean Air",
    "ZH": "Shenzhen Airlines",
    "MU": "China Eastern Airlines",
    "CA": "Air China",
    "CZ": "China Southern Airlines",
    "FM": "Shanghai Airlines",
    "HU": "Hainan Airlines",
    "9W": "Jet Airways",
    
    # Canadian Carriers
    "AC": "Air Canada",
    
    # Low Cost and Regional
    "G4": "Allegiant Air",
    "SY": "Sun Country Airlines",
    "PC": "Pegasus Airlines",
    "XY": "flynas"
}

# Default preferred carriers list (comprehensive coverage)
DEFAULT_PREFERRED_CARRIERS = [
    # Major International Carriers
    "AA", "DL", "UA", "LH", "BA", "AF", "KL", "EK", "QR", "SQ", 
    "CX", "TK", "AC", "NH", "JL", "AZ", "LX", "OS", "SN", "SK",
    # Middle East & Asia
    "EY", "GF", "SV", "MS", "RJ", "WY", "TG", "CI", "BR", "PR",
    # Low Cost & Regional
    "FR", "U2", "WN", "B6", "NK", "F9", "G4", "SY", "PC", "XY",
    # Additional Major Carriers
    "IB", "AY", "KE", "ZH", "MU", "CA", "CZ", "FM", "HU", "9W"
]


def get_airline_name(code: str) -> str:
    """Get the full airline name from IATA code"""
    return AIRLINE_CODES.get(code.upper(), f"Unknown Airline ({code})")


def get_all_carrier_codes() -> list:
    """Get all available airline codes"""
    return list(AIRLINE_CODES.keys())


def get_carriers_by_region(region: str) -> list:
    """Get airline codes by region"""
    regions = {
        "us": ["AA", "DL", "UA", "WN", "B6", "NK", "F9"],
        "europe": ["LH", "BA", "AF", "KL", "AZ", "LX", "OS", "SN", "SK", "IB", "AY", "FR", "U2"],
        "middle_east": ["EK", "QR", "EY", "GF", "SV", "MS", "RJ", "WY"],
        "asia": ["SQ", "CX", "TK", "NH", "JL", "TG", "CI", "BR", "PR", "KE", "ZH", "MU", "CA", "CZ", "FM", "HU", "9W"],
        "low_cost": ["FR", "U2", "WN", "B6", "NK", "F9", "G4", "SY", "PC", "XY"]
    }
    return regions.get(region.lower(), []) 