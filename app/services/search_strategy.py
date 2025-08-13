"""
Search strategy service for bulk flight searches across dates and airports
"""

import asyncio
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import itertools

from ..models.schemas import Slots, Itinerary, TripType
from ..services.travelport import TravelportService
from ..services.date_parse import DateParsingService
from ..utils.errors import TazaTicketError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class SearchStrategy:
    """Service for implementing bulk search strategies"""
    
    def __init__(self, travelport_service: TravelportService, date_service: DateParsingService):
        self.travelport_service = travelport_service
        self.date_service = date_service
        self.max_concurrent_searches = 5  # Limit concurrent API calls
        
    async def search_exact_date(self, slots: Slots) -> List[Itinerary]:
        """
        Search for flights on exact date(s)
        
        Args:
            slots: Complete slot information with exact dates
            
        Returns:
            List of itineraries
        """
        
        if not slots.from_iata_codes or not slots.to_iata_codes or not slots.date:
            raise TazaTicketError("Missing required search parameters for exact date search")
        
        try:
            # If single origin and destination, use simple search
            if len(slots.from_iata_codes) == 1 and len(slots.to_iata_codes) == 1:
                return await self.travelport_service.search_with_slots(slots)
            
            # Multiple airports - search all combinations
            return await self._search_multi_airport_combinations(slots)
            
        except Exception as e:
            logger.error(f"Exact date search failed: {str(e)}")
            raise TazaTicketError(f"Flight search failed: {str(e)}")
    
    async def search_over_dates(
        self, 
        slots: Slots, 
        outbound_dates: List[str], 
        return_dates: Optional[List[str]] = None
    ) -> List[Itinerary]:
        """
        Search across multiple dates and return cheapest options
        
        Args:
            slots: Slot information
            outbound_dates: List of outbound dates in YYYY-MM-DD format
            return_dates: List of return dates for round trips (optional)
            
        Returns:
            List of itineraries sorted by price (cheapest first)
        """
        
        if not slots.from_iata_codes or not slots.to_iata_codes:
            raise TazaTicketError("Missing origin or destination for date range search")
        
        if not outbound_dates:
            raise TazaTicketError("No outbound dates provided for search")
        
        logger.info(f"Searching across {len(outbound_dates)} outbound dates")
        
        # Prepare date combinations
        date_combinations = []
        
        if slots.trip_type == TripType.ROUND_TRIP and return_dates:
            # Round trip with return date options
            for outbound_date in outbound_dates:
                for return_date in return_dates:
                    date_combinations.append((outbound_date, return_date))
        else:
            # One-way or round trip with fixed return date
            for outbound_date in outbound_dates:
                return_date = slots.return_date if slots.trip_type == TripType.ROUND_TRIP else None
                date_combinations.append((outbound_date, return_date))
        
        logger.info(f"Searching {len(date_combinations)} date combinations")
        
        # Search all date combinations with concurrency control
        all_itineraries = []
        semaphore = asyncio.Semaphore(self.max_concurrent_searches)
        
        async def search_date_combination(outbound_date: str, return_date: Optional[str]):
            async with semaphore:
                try:
                    # Create slots copy for this date combination
                    search_slots = Slots(
                        from_city=slots.from_city,
                        to_city=slots.to_city,
                        date=outbound_date,
                        return_date=return_date,
                        passengers=slots.passengers,
                        trip_type=slots.trip_type,
                        preferred_carrier=slots.preferred_carrier,
                        from_iata_codes=slots.from_iata_codes,
                        to_iata_codes=slots.to_iata_codes
                    )
                    
                    itineraries = await self.search_exact_date(search_slots)
                    
                    # Tag itineraries with search dates for tracking
                    for itinerary in itineraries:
                        itinerary.search_date = outbound_date
                        if return_date:
                            itinerary.search_return_date = return_date
                    
                    return itineraries
                    
                except Exception as e:
                    logger.warning(f"Search failed for dates {outbound_date}-{return_date}: {str(e)}")
                    return []
        
        # Execute searches concurrently
        tasks = []
        for outbound_date, return_date in date_combinations:
            task = search_date_combination(outbound_date, return_date)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect all successful results
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Search task failed: {str(result)}")
            elif isinstance(result, list):
                all_itineraries.extend(result)
        
        # Sort by total price (cheapest first)
        all_itineraries.sort(key=lambda x: x.price.total)
        
        logger.info(f"Found {len(all_itineraries)} total itineraries across all dates")
        
        return all_itineraries
    
    async def search_month(self, slots: Slots, month: int, year: int) -> List[Itinerary]:
        """
        Search for cheapest flights in a specific month
        
        Args:
            slots: Slot information
            month: Month number (1-12)
            year: Year
            
        Returns:
            List of itineraries sorted by price
        """
        
        logger.info(f"Searching for cheapest flights in {month}/{year}")
        
        # Get all valid travel dates in the month
        month_dates = self.date_service.get_month_dates(month, year, exclude_past=True)
        
        if not month_dates:
            raise TazaTicketError(f"No valid travel dates found in {month}/{year}")
        
        # For round trips, determine return date strategy
        return_dates = None
        if slots.trip_type == TripType.ROUND_TRIP:
            if slots.return_date:
                # Fixed return date
                return_dates = [slots.return_date]
            else:
                # Return dates 7-14 days after outbound (typical vacation length)
                return_dates = []
                for outbound_date in month_dates:
                    try:
                        outbound_dt = datetime.strptime(outbound_date, "%Y-%m-%d")
                        for days_later in [7, 10, 14]:  # Common return periods
                            return_dt = outbound_dt + timedelta(days=days_later)
                            return_date_str = return_dt.strftime("%Y-%m-%d")
                            if self.date_service.is_valid_travel_date(return_date_str):
                                return_dates.append(return_date_str)
                    except ValueError:
                        continue
                
                # Remove duplicates and sort
                return_dates = sorted(list(set(return_dates)))
        
        # Search across all dates in the month
        return await self.search_over_dates(slots, month_dates, return_dates)
    
    async def search_date_range(
        self, 
        slots: Slots, 
        start_date: str, 
        end_date: str,
        return_start_date: Optional[str] = None,
        return_end_date: Optional[str] = None
    ) -> List[Itinerary]:
        """
        Search for cheapest flights in a date range
        
        Args:
            slots: Slot information
            start_date: Range start date in YYYY-MM-DD format
            end_date: Range end date in YYYY-MM-DD format
            return_start_date: Return range start (for round trips)
            return_end_date: Return range end (for round trips)
            
        Returns:
            List of itineraries sorted by price
        """
        
        logger.info(f"Searching date range {start_date} to {end_date}")
        
        # Expand outbound date range
        outbound_dates = self.date_service.expand_date_range(start_date, end_date)
        
        # Filter out past dates
        valid_outbound_dates = [
            date for date in outbound_dates 
            if self.date_service.is_valid_travel_date(date)
        ]
        
        if not valid_outbound_dates:
            raise TazaTicketError(f"No valid travel dates in range {start_date} to {end_date}")
        
        # Handle return dates for round trips
        return_dates = None
        if slots.trip_type == TripType.ROUND_TRIP:
            if return_start_date and return_end_date:
                # Specific return date range
                return_dates = self.date_service.expand_date_range(return_start_date, return_end_date)
                return_dates = [
                    date for date in return_dates 
                    if self.date_service.is_valid_travel_date(date)
                ]
            elif slots.return_date:
                # Fixed return date
                return_dates = [slots.return_date]
        
        # Search across the date range
        return await self.search_over_dates(slots, valid_outbound_dates, return_dates)
    
    async def _search_multi_airport_combinations(self, slots: Slots) -> List[Itinerary]:
        """
        Search all combinations of origin and destination airports
        
        Args:
            slots: Slot information with multiple IATA codes
            
        Returns:
            Combined list of itineraries from all airport combinations
        """
        
        origin_codes = slots.from_iata_codes[:3]  # Limit to 3 origins to avoid explosion
        destination_codes = slots.to_iata_codes[:3]  # Limit to 3 destinations
        
        logger.info(f"Searching {len(origin_codes)} x {len(destination_codes)} airport combinations")
        
        # Generate all combinations
        airport_combinations = list(itertools.product(origin_codes, destination_codes))
        
        semaphore = asyncio.Semaphore(self.max_concurrent_searches)
        
        async def search_airport_combination(from_iata: str, to_iata: str):
            async with semaphore:
                try:
                    # Create slots copy for this airport combination
                    search_slots = Slots(
                        from_city=slots.from_city,
                        to_city=slots.to_city,
                        date=slots.date,
                        return_date=slots.return_date,
                        passengers=slots.passengers,
                        trip_type=slots.trip_type,
                        preferred_carrier=slots.preferred_carrier,
                        from_iata_codes=[from_iata],
                        to_iata_codes=[to_iata]
                    )
                    
                    itineraries = await self.travelport_service.search_with_slots(search_slots)
                    
                    # Tag itineraries with airport info
                    for itinerary in itineraries:
                        itinerary.origin_airport = from_iata
                        itinerary.destination_airport = to_iata
                    
                    return itineraries
                    
                except Exception as e:
                    logger.warning(f"Search failed for {from_iata}-{to_iata}: {str(e)}")
                    return []
        
        # Execute searches concurrently
        tasks = []
        for from_iata, to_iata in airport_combinations:
            task = search_airport_combination(from_iata, to_iata)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect all successful results
        all_itineraries = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Multi-airport search task failed: {str(result)}")
            elif isinstance(result, list):
                all_itineraries.extend(result)
        
        # Sort by total price and remove duplicates
        all_itineraries.sort(key=lambda x: x.price.total)
        
        logger.info(f"Found {len(all_itineraries)} itineraries across all airport combinations")
        
        return all_itineraries
    
    async def search_with_carrier_filter(self, slots: Slots, carrier_code: str) -> List[Itinerary]:
        """
        Search flights with specific carrier preference
        
        Args:
            slots: Slot information
            carrier_code: Preferred airline carrier code
            
        Returns:
            List of itineraries for the specified carrier
        """
        
        logger.info(f"Searching with carrier filter: {carrier_code}")
        
        # Create slots copy with carrier preference
        filtered_slots = Slots(
            from_city=slots.from_city,
            to_city=slots.to_city,
            date=slots.date,
            return_date=slots.return_date,
            passengers=slots.passengers,
            trip_type=slots.trip_type,
            preferred_carrier=carrier_code,
            from_iata_codes=slots.from_iata_codes,
            to_iata_codes=slots.to_iata_codes,
            date_search_type=slots.date_search_type,
            date_range_start=slots.date_range_start,
            date_range_end=slots.date_range_end
        )
        
        # Route to appropriate search method based on date search type
        if slots.date_search_type == "exact":
            return await self.search_exact_date(filtered_slots)
        elif slots.date_search_type == "month":
            month_year = self.date_service.parse_month_year(f"{slots.date_range_start} {slots.date_range_end}")
            if month_year:
                month, year = month_year
                return await self.search_month(filtered_slots, month, year)
        elif slots.date_search_type == "range":
            return await self.search_date_range(
                filtered_slots, 
                slots.date_range_start, 
                slots.date_range_end
            )
        
        # Fallback to exact date search
        return await self.search_exact_date(filtered_slots)
    
    def get_cheapest_itineraries(self, itineraries: List[Itinerary], limit: int = 5) -> List[Itinerary]:
        """
        Get the cheapest itineraries from a list
        
        Args:
            itineraries: List of itineraries
            limit: Maximum number to return
            
        Returns:
            List of cheapest itineraries
        """
        
        if not itineraries:
            return []
        
        # Sort by total price
        sorted_itineraries = sorted(itineraries, key=lambda x: x.price.total)
        
        return sorted_itineraries[:limit]
    
    def group_by_date(self, itineraries: List[Itinerary]) -> Dict[str, List[Itinerary]]:
        """
        Group itineraries by travel date
        
        Args:
            itineraries: List of itineraries
            
        Returns:
            Dictionary mapping dates to itineraries
        """
        
        date_groups = {}
        
        for itinerary in itineraries:
            search_date = getattr(itinerary, 'search_date', None)
            if search_date:
                if search_date not in date_groups:
                    date_groups[search_date] = []
                date_groups[search_date].append(itinerary)
        
        return date_groups 