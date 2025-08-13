"""
Flight search payload construction for Travelport API
Enhanced with roundtrip and multi-city builders for unified conversation system
"""

from typing import Dict, List, Optional
from .airline_codes import DEFAULT_PREFERRED_CARRIERS


def build_flight_search_payload(
    from_city: str,
    to_city: str,
    departure_date: str,
    return_date: Optional[str] = None,
    passengers: int = 1,
    passenger_age: int = 25,
    preferred_carriers: Optional[List[str]] = None
) -> Dict:
    """
    Build flight search payload for Travelport API
    
    Args:
        from_city: Origin airport code (3-letter IATA)
        to_city: Destination airport code (3-letter IATA) 
        departure_date: Departure date in YYYY-MM-DD format
        return_date: Return date in YYYY-MM-DD format (optional for one-way)
        passengers: Number of passengers (default: 1)
        passenger_age: Age of passenger for ADT type (default: 25)
        preferred_carriers: List of preferred airline codes (optional)
        
    Returns:
        Dict: Complete API payload for flight search
    """
    
    # Build search criteria starting with outbound flight
    search_criteria = [{
        "@type": "SearchCriteriaFlight",
        "departureDate": departure_date,
        "From": {"value": from_city},
        "To": {"value": to_city}
    }]
    
    # Add return flight if specified (round trip)
    if return_date:
        search_criteria.append({
            "@type": "SearchCriteriaFlight", 
            "departureDate": return_date,
            "From": {"value": to_city},
            "To": {"value": from_city}
        })
    
    # Set default preferred carriers if not provided
    if preferred_carriers is None:
        preferred_carriers = DEFAULT_PREFERRED_CARRIERS
    
    # Build complete payload
    payload = {
        "@type": "CatalogProductOfferingsQueryRequest",
        "CatalogProductOfferingsRequest": {
            "@type": "CatalogProductOfferingsRequestAir",
            "maxNumberOfUpsellsToReturn": 1,
            "contentSourceList": ["GDS"],
            "PassengerCriteria": [{
                "@type": "PassengerCriteria",
                "number": passengers,
                "age": passenger_age,
                "passengerTypeCode": "ADT"
            }],
            "SearchCriteriaFlight": search_criteria,
            "SearchModifiersAir": {
                "@type": "SearchModifiersAir",
                "CarrierPreference": [{
                    "@type": "CarrierPreference",
                    "preferenceType": "Preferred",
                    "carriers": preferred_carriers
                }]
            },
            "CustomResponseModifiersAir": {
                "@type": "CustomResponseModifiersAir",
                "SearchRepresentation": "Journey"
            }
        }
    }
    
    return payload


def build_multi_city_payload(
    flight_segments: List[Dict[str, str]],
    passengers: int = 1,
    passenger_age: int = 25,
    preferred_carriers: Optional[List[str]] = None
) -> Dict:
    """
    Build multi-city flight search payload for complex itineraries
    
    Args:
        flight_segments: List of flight segments with 'from', 'to', 'date' keys
        passengers: Number of passengers (default: 1)
        passenger_age: Age of passenger for ADT type (default: 25)
        preferred_carriers: List of preferred airline codes (optional)
        
    Returns:
        Dict: Complete API payload for multi-city flight search
    """
    
    # Build search criteria for each segment
    search_criteria = []
    for segment in flight_segments:
        search_criteria.append({
            "@type": "SearchCriteriaFlight",
            "departureDate": segment["date"],
            "From": {"value": segment["from"]},
            "To": {"value": segment["to"]}
        })
    
    # Set default preferred carriers if not provided
    if preferred_carriers is None:
        preferred_carriers = DEFAULT_PREFERRED_CARRIERS
    
    # Build complete payload
    payload = {
        "@type": "CatalogProductOfferingsQueryRequest",
        "CatalogProductOfferingsRequest": {
            "@type": "CatalogProductOfferingsRequestAir",
            "maxNumberOfUpsellsToReturn": 1,
            "contentSourceList": ["GDS"],
            "PassengerCriteria": [{
                "@type": "PassengerCriteria",
                "number": passengers,
                "age": passenger_age,
                "passengerTypeCode": "ADT"
            }],
            "SearchCriteriaFlight": search_criteria,
            "SearchModifiersAir": {
                "@type": "SearchModifiersAir",
                "CarrierPreference": [{
                    "@type": "CarrierPreference",
                    "preferenceType": "Preferred",
                    "carriers": preferred_carriers
                }]
            },
            "CustomResponseModifiersAir": {
                "@type": "CustomResponseModifiersAir",
                "SearchRepresentation": "Journey"
            }
        }
    }
    
    return payload 

def build_roundtrip_flight_payload(
    from_city: str,
    to_city: str,
    departure_date: str,
    return_date: str,
    passengers: int = 1,
    passenger_age: int = 25,
    preferred_carriers: Optional[List[str]] = None
) -> Dict:
    """
    Build roundtrip flight search payload for Travelport API
    
    Args:
        from_city: Origin airport code (3-letter IATA)
        to_city: Destination airport code (3-letter IATA) 
        departure_date: Departure date in YYYY-MM-DD format
        return_date: Return date in YYYY-MM-DD format
        passengers: Number of passengers (default: 1)
        passenger_age: Age of passenger for ADT type (default: 25)
        preferred_carriers: List of preferred airline codes (optional)
        
    Returns:
        Dict: Complete API payload for roundtrip flight search
    """
    return build_flight_search_payload(
        from_city=from_city,
        to_city=to_city,
        departure_date=departure_date,
        return_date=return_date,
        passengers=passengers,
        passenger_age=passenger_age,
        preferred_carriers=preferred_carriers
    )


def build_oneway_flight_payload(
    from_city: str,
    to_city: str,
    departure_date: str,
    passengers: int = 1,
    passenger_age: int = 25,
    preferred_carriers: Optional[List[str]] = None
) -> Dict:
    """
    Build one-way flight search payload for Travelport API
    
    Args:
        from_city: Origin airport code (3-letter IATA)
        to_city: Destination airport code (3-letter IATA) 
        departure_date: Departure date in YYYY-MM-DD format
        passengers: Number of passengers (default: 1)
        passenger_age: Age of passenger for ADT type (default: 25)
        preferred_carriers: List of preferred airline codes (optional)
        
    Returns:
        Dict: Complete API payload for one-way flight search
    """
    return build_flight_search_payload(
        from_city=from_city,
        to_city=to_city,
        departure_date=departure_date,
        return_date=None,
        passengers=passengers,
        passenger_age=passenger_age,
        preferred_carriers=preferred_carriers
    )