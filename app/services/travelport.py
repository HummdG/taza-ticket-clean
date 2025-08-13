"""
Travelport API service for authentication and flight search
"""

import asyncio
import hashlib
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..config import settings
from ..models.schemas import (
    TravelportResponse, 
    Slots, 
    Itinerary, 
    FlightSegment, 
    PriceBreakdown, 
    BaggageInfo,
    TripType
)
from ..utils.errors import TravelportError, RateLimitError
from ..utils.logging import get_logger
from ..payloads.flight_search import (
    build_oneway_flight_payload,
    build_roundtrip_flight_payload,
    build_multi_city_payload
)

logger = get_logger(__name__)


class TravelportService:
    """Travelport API service for flight search operations"""
    
    def __init__(self):
        self.access_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError))
    )
    async def _get_access_token(self) -> str:
        """Get OAuth access token from Travelport"""
        
        data = {
            "grant_type": "password",
            "username": settings.travelport_username,
            "password": settings.travelport_password,
            "client_id": settings.travelport_client_id,
            "client_secret": settings.travelport_client_secret,
            "scope": "openid"
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            response = await self.client.post(
                settings.travelport_oauth_url,
                headers=headers,
                data=data
            )
            response.raise_for_status()
            
            token_data = response.json()
            access_token = token_data["access_token"]
            
            # Set token expiry (typically 1 hour, but we'll refresh early)
            self.token_expiry = datetime.utcnow() + timedelta(minutes=45)
            
            logger.info("Successfully obtained Travelport access token")
            return access_token
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to obtain access token: {e.response.status_code} - {e.response.text}")
            raise TravelportError(f"Authentication failed: {e.response.text}", status_code=e.response.status_code)
        except httpx.RequestError as e:
            logger.error(f"Request error during authentication: {str(e)}")
            raise TravelportError(f"Authentication request failed: {str(e)}")
    
    async def _ensure_valid_token(self) -> str:
        """Ensure we have a valid access token"""
        
        if (not self.access_token or 
            not self.token_expiry or 
            datetime.utcnow() >= self.token_expiry):
            
            self.access_token = await self._get_access_token()
            
        return self.access_token
    
    def _get_request_headers(self, token: str) -> Dict[str, str]:
        """Get request headers for Travelport API calls"""
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
            "Authorization": f"Bearer {token}",
            "Accept-Version": "11",
            "Content-Version": "11",
        }
        
        if settings.travelport_access_group:
            headers["XAUTH_TRAVELPORT_ACCESSGROUP"] = settings.travelport_access_group
            
        return headers
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError, TravelportError))
    )
    async def search_flights(
        self,
        from_iata: str,
        to_iata: str,
        departure_date: str,
        return_date: Optional[str] = None,
        passengers: int = 1,
        preferred_carriers: Optional[List[str]] = None
    ) -> TravelportResponse:
        """
        Search for flights using Travelport API
        
        Args:
            from_iata: Origin airport IATA code
            to_iata: Destination airport IATA code  
            departure_date: Departure date in YYYY-MM-DD format
            return_date: Return date for round trip (optional)
            passengers: Number of passengers
            preferred_carriers: List of preferred airline codes
            
        Returns:
            TravelportResponse with search results
        """
        
        token = await self._ensure_valid_token()
        headers = self._get_request_headers(token)
        
        # Build payload based on trip type
        if return_date:
            payload = build_roundtrip_flight_payload(
                from_city=from_iata,
                to_city=to_iata,
                departure_date=departure_date,
                return_date=return_date,
                passengers=passengers,
                preferred_carriers=preferred_carriers
            )
        else:
            payload = build_oneway_flight_payload(
                from_city=from_iata,
                to_city=to_iata,
                departure_date=departure_date,
                passengers=passengers,
                preferred_carriers=preferred_carriers
            )
        
        try:
            logger.info(
                f"Searching flights: {from_iata} -> {to_iata}, "
                f"departure: {departure_date}, return: {return_date}, "
                f"passengers: {passengers}"
            )
            
            response = await self.client.post(
                settings.travelport_catalog_url,
                headers=headers,
                json=payload
            )
            
            if response.status_code == 429:
                raise RateLimitError("Travelport API rate limit exceeded", service="travelport")
            
            response.raise_for_status()
            result = response.json()
            
            # Extract transaction ID and check for errors
            transaction_id = result.get("CatalogProductOfferingsResponse", {}).get("transactionId")
            catalog_response = result.get("CatalogProductOfferingsResponse", {})
            
            # Check for API errors
            if "Result" in catalog_response and "Error" in catalog_response["Result"]:
                errors = catalog_response["Result"]["Error"]
                error_messages = [error.get("Message", "Unknown error") for error in errors]
                
                logger.warning(f"Travelport API errors: {error_messages}")
                
                return TravelportResponse(
                    transaction_id=transaction_id,
                    offerings=[],
                    errors=errors,
                    success=False
                )
            
            # Extract offerings
            offerings = []
            if "CatalogProductOfferings" in catalog_response:
                catalog_offerings = catalog_response["CatalogProductOfferings"]
                if "CatalogProductOffering" in catalog_offerings:
                    offerings = catalog_offerings["CatalogProductOffering"]
                    if not isinstance(offerings, list):
                        offerings = [offerings]
            
            logger.info(f"Found {len(offerings)} flight offerings")
            
            return TravelportResponse(
                transaction_id=transaction_id,
                offerings=offerings,
                errors=[],
                success=True
            )
            
        except httpx.HTTPStatusError as e:
            error_msg = f"Travelport API error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise TravelportError(error_msg, status_code=e.response.status_code)
        except httpx.RequestError as e:
            error_msg = f"Request error during flight search: {str(e)}"
            logger.error(error_msg)
            raise TravelportError(error_msg)
    
    def _extract_baggage_info(self, offering: Dict, reference_data: Dict) -> Optional[BaggageInfo]:
        """Extract baggage information from offering and reference data"""
        
        try:
            # Get terms and conditions reference
            product_brand = offering.get("Product", {}).get("ProductBrand", {})
            if not product_brand:
                return None
                
            terms_conditions = product_brand.get("TermsAndConditions", {})
            terms_ref = terms_conditions.get("termsAndConditionsRef")
            
            if not terms_ref:
                return None
            
            # Find matching terms in reference data
            reference_terms = reference_data.get("ReferenceListTermsAndConditions", {}).get("TermsAndConditions", [])
            if not isinstance(reference_terms, list):
                reference_terms = [reference_terms]
            
            for terms in reference_terms:
                if terms.get("id") == terms_ref:
                    # Extract baggage allowance
                    baggage_allowance = terms.get("BaggageAllowance", {})
                    if baggage_allowance:
                        baggage_items = baggage_allowance.get("BaggageItem", [])
                        if not isinstance(baggage_items, list):
                            baggage_items = [baggage_items]
                        
                        if baggage_items:
                            item = baggage_items[0]
                            return BaggageInfo(
                                weight=item.get("Weight"),
                                pieces=item.get("Pieces"),
                                included=True,
                                description=item.get("Description")
                            )
            
            return BaggageInfo(included=False, description="No baggage included")
            
        except Exception as e:
            logger.warning(f"Failed to extract baggage info: {str(e)}")
            return None
    
    def _parse_flight_segments(self, product_air: Dict) -> List[FlightSegment]:
        """Parse flight segments from Travelport product air data"""
        
        segments = []
        
        try:
            journey = product_air.get("Journey", {})
            if not journey:
                return segments
            
            flight_segments = journey.get("FlightSegment", [])
            if not isinstance(flight_segments, list):
                flight_segments = [flight_segments]
            
            for segment in flight_segments:
                flight_detail = segment.get("FlightDetail", {})
                equipment = flight_detail.get("Equipment", {})
                
                segments.append(FlightSegment(
                    flight_number=f"{flight_detail.get('MarketingCarrier', {}).get('code', '')}{flight_detail.get('FlightNumber', '')}",
                    carrier_code=flight_detail.get("MarketingCarrier", {}).get("code", ""),
                    carrier_name=flight_detail.get("MarketingCarrier", {}).get("name", ""),
                    departure_airport=segment.get("From", {}).get("value", ""),
                    departure_city=segment.get("From", {}).get("cityName", ""),
                    arrival_airport=segment.get("To", {}).get("value", ""),
                    arrival_city=segment.get("To", {}).get("cityName", ""),
                    departure_time=segment.get("DepartureTime", ""),
                    arrival_time=segment.get("ArrivalTime", ""),
                    duration=segment.get("FlightTime", ""),
                    aircraft_type=equipment.get("code", "")
                ))
                
        except Exception as e:
            logger.warning(f"Failed to parse flight segments: {str(e)}")
            
        return segments
    
    def _parse_price_breakdown(self, pricing: Dict) -> PriceBreakdown:
        """Parse price breakdown from offering pricing data"""
        
        try:
            total_price = pricing.get("TotalPrice", {})
            base_price = pricing.get("BasePrice", {})
            taxes = pricing.get("Taxes", {})
            
            return PriceBreakdown(
                base_fare=float(base_price.get("value", 0)),
                taxes=float(taxes.get("value", 0)) if taxes else 0,
                total=float(total_price.get("value", 0)),
                currency=total_price.get("code", "USD")
            )
            
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse price breakdown: {str(e)}")
            return PriceBreakdown(base_fare=0, taxes=0, total=0, currency="USD")
    
    def parse_search_results(self, response: TravelportResponse) -> List[Itinerary]:
        """Parse Travelport search response into structured itineraries"""
        
        itineraries = []
        
        if not response.success or not response.offerings:
            return itineraries
        
        for offering in response.offerings:
            try:
                # Extract product information
                product = offering.get("Product", {})
                product_air = product.get("ProductAir", {})
                
                # Parse flight segments
                segments = self._parse_flight_segments(product_air)
                if not segments:
                    continue
                
                # Split segments into outbound/return
                outbound_segments = segments
                return_segments = None
                
                # For round trips, split segments (this is a simplified approach)
                if len(segments) > 1:
                    # Heuristic: if we have segments that go back to origin, split them
                    origin = segments[0].departure_airport
                    for i, segment in enumerate(segments[1:], 1):
                        if segment.arrival_airport == origin:
                            outbound_segments = segments[:i]
                            return_segments = segments[i:]
                            break
                
                # Parse pricing
                offering_pricing = offering.get("OfferingPricing", {})
                price = self._parse_price_breakdown(offering_pricing)
                
                # Extract baggage info (simplified - would need reference data)
                baggage = BaggageInfo(included=False, description="Baggage policy varies by carrier")
                
                # Calculate total duration and stops
                total_duration = None
                stops = max(0, len(outbound_segments) - 1)
                if return_segments:
                    stops += max(0, len(return_segments) - 1)
                
                # Extract brand/cabin info
                brand = product.get("ProductBrand", {}).get("BrandID")
                cabin_class = "Economy"  # Default, would need to parse from segments
                
                itinerary = Itinerary(
                    outbound_segments=outbound_segments,
                    return_segments=return_segments,
                    price=price,
                    baggage=baggage,
                    total_duration=total_duration,
                    stops=stops,
                    brand=brand,
                    cabin_class=cabin_class
                )
                
                itineraries.append(itinerary)
                
            except Exception as e:
                logger.warning(f"Failed to parse offering: {str(e)}")
                continue
        
        logger.info(f"Parsed {len(itineraries)} itineraries from {len(response.offerings)} offerings")
        return itineraries
    
    def get_search_hash(self, slots: Slots) -> str:
        """Generate a hash for search parameters to detect changes"""
        
        search_params = {
            "from_iata": slots.from_iata_codes,
            "to_iata": slots.to_iata_codes,
            "date": slots.date,
            "return_date": slots.return_date,
            "passengers": slots.passengers,
            "trip_type": slots.trip_type,
            "preferred_carrier": slots.preferred_carrier
        }
        
        search_string = json.dumps(search_params, sort_keys=True)
        return hashlib.md5(search_string.encode()).hexdigest()
    
    async def search_with_slots(self, slots: Slots) -> List[Itinerary]:
        """
        Search for flights using slot information
        
        Args:
            slots: Complete slot information for search
            
        Returns:
            List of parsed itineraries
        """
        
        if not slots.from_iata_codes or not slots.to_iata_codes:
            raise TravelportError("Missing IATA codes for search")
        
        if not slots.date:
            raise TravelportError("Missing departure date for search")
        
        # For now, use first IATA code from each list
        # TODO: Implement multi-airport search strategy
        from_iata = slots.from_iata_codes[0]
        to_iata = slots.to_iata_codes[0]
        
        preferred_carriers = [slots.preferred_carrier] if slots.preferred_carrier else None
        
        response = await self.search_flights(
            from_iata=from_iata,
            to_iata=to_iata,
            departure_date=slots.date,
            return_date=slots.return_date,
            passengers=slots.passengers or 1,
            preferred_carriers=preferred_carriers
        )
        
        return self.parse_search_results(response) 