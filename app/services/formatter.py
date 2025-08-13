"""
Formatter service for creating user-friendly itinerary responses
"""

from typing import List, Optional, Dict
from datetime import datetime, timedelta

from ..models.schemas import Itinerary, FlightSegment, MessageModality, TripType
from ..services.iata_resolver import IATAResolver
from ..utils.logging import get_logger

logger = get_logger(__name__)


class ItineraryFormatter:
    """Service for formatting flight itineraries for user responses"""
    
    def __init__(self, iata_resolver: IATAResolver):
        self.iata_resolver = iata_resolver
    
    def format_duration(self, minutes: int) -> str:
        """Format duration from minutes to human-readable format"""
        
        if minutes < 60:
            return f"{minutes}m"
        
        hours = minutes // 60
        remaining_minutes = minutes % 60
        
        if remaining_minutes == 0:
            return f"{hours}h"
        else:
            return f"{hours}h {remaining_minutes}m"
    
    def format_time(self, time_str: str) -> str:
        """Format time string for display"""
        
        try:
            # Handle various time formats
            if 'T' in time_str:
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                return dt.strftime("%H:%M")
            else:
                # Assume it's already in HH:MM format
                return time_str
        except:
            return time_str
    
    def format_date(self, date_str: str) -> str:
        """Format date string for display"""
        
        try:
            if 'T' in date_str:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return dt.strftime("%d %b %Y")
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.strftime("%d %b %Y")
        except:
            return date_str
    
    def format_price(self, price: float, currency: str = "USD") -> str:
        """Format price for display"""
        
        if currency == "USD":
            return f"${price:,.0f}"
        else:
            return f"{currency} {price:,.0f}"
    
    def format_airport_info(self, airport_code: str) -> str:
        """Format airport code with city name if available"""
        
        city_name = self.iata_resolver.get_city_name(airport_code)
        if city_name:
            return f"{airport_code} ({city_name})"
        else:
            return airport_code
    
    def format_segment(self, segment: FlightSegment, include_date: bool = False) -> Dict[str, str]:
        """Format a single flight segment"""
        
        departure_time = self.format_time(segment.departure_time)
        arrival_time = self.format_time(segment.arrival_time)
        
        departure_airport = self.format_airport_info(segment.departure_airport)
        arrival_airport = self.format_airport_info(segment.arrival_airport)
        
        formatted = {
            "flight": f"{segment.carrier_code} {segment.flight_number}",
            "carrier": segment.carrier_name,
            "route": f"{departure_airport} → {arrival_airport}",
            "time": f"{departure_time} - {arrival_time}",
            "duration": self.format_duration(self._parse_duration(segment.duration)) if segment.duration else "N/A"
        }
        
        if include_date:
            # Extract date from departure time if available
            try:
                if 'T' in segment.departure_time:
                    dt = datetime.fromisoformat(segment.departure_time.replace('Z', '+00:00'))
                    formatted["date"] = dt.strftime("%d %b")
            except:
                pass
        
        return formatted
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse duration string to minutes"""
        
        if not duration_str:
            return 0
        
        # Handle various duration formats
        try:
            # ISO 8601 format (PT2H30M)
            if duration_str.startswith('PT'):
                hours = 0
                minutes = 0
                duration_str = duration_str[2:]  # Remove PT
                
                if 'H' in duration_str:
                    h_parts = duration_str.split('H')
                    hours = int(h_parts[0])
                    duration_str = h_parts[1] if len(h_parts) > 1 else ''
                
                if 'M' in duration_str:
                    m_parts = duration_str.split('M')
                    minutes = int(m_parts[0])
                
                return hours * 60 + minutes
            
            # Simple format (2h 30m, 2:30, 150)
            elif 'h' in duration_str.lower():
                parts = duration_str.lower().replace('h', '').replace('m', '').split()
                hours = int(parts[0]) if parts else 0
                minutes = int(parts[1]) if len(parts) > 1 else 0
                return hours * 60 + minutes
            
            elif ':' in duration_str:
                parts = duration_str.split(':')
                hours = int(parts[0])
                minutes = int(parts[1]) if len(parts) > 1 else 0
                return hours * 60 + minutes
            
            else:
                # Assume minutes
                return int(duration_str)
                
        except (ValueError, IndexError):
            return 0
    
    def format_itinerary_text(self, itinerary: Itinerary, include_details: bool = True) -> str:
        """Format itinerary for text display"""
        
        lines = []
        
        # Flight details
        lines.append("✈️ **Flight Details**")
        lines.append("")
        
        # Outbound flight(s)
        lines.append("🛫 **Outbound:**")
        for i, segment in enumerate(itinerary.outbound_segments):
            seg_info = self.format_segment(segment, include_date=True)
            
            if len(itinerary.outbound_segments) > 1:
                lines.append(f"  **Segment {i+1}:** {seg_info['flight']} ({seg_info['carrier']})")
            else:
                lines.append(f"  **Flight:** {seg_info['flight']} ({seg_info['carrier']})")
            
            lines.append(f"  **Route:** {seg_info['route']}")
            lines.append(f"  **Time:** {seg_info['time']}")
            
            if 'date' in seg_info:
                lines.append(f"  **Date:** {seg_info['date']}")
            
            if seg_info['duration'] != "N/A":
                lines.append(f"  **Duration:** {seg_info['duration']}")
            
            if i < len(itinerary.outbound_segments) - 1:
                lines.append("")
        
        # Return flight(s) if round trip
        if itinerary.return_segments:
            lines.append("")
            lines.append("🛬 **Return:**")
            
            for i, segment in enumerate(itinerary.return_segments):
                seg_info = self.format_segment(segment, include_date=True)
                
                if len(itinerary.return_segments) > 1:
                    lines.append(f"  **Segment {i+1}:** {seg_info['flight']} ({seg_info['carrier']})")
                else:
                    lines.append(f"  **Flight:** {seg_info['flight']} ({seg_info['carrier']})")
                
                lines.append(f"  **Route:** {seg_info['route']}")
                lines.append(f"  **Time:** {seg_info['time']}")
                
                if 'date' in seg_info:
                    lines.append(f"  **Date:** {seg_info['date']}")
                
                if seg_info['duration'] != "N/A":
                    lines.append(f"  **Duration:** {seg_info['duration']}")
                
                if i < len(itinerary.return_segments) - 1:
                    lines.append("")
        
        # Journey summary
        lines.append("")
        lines.append("📊 **Journey Summary**")
        
        if itinerary.stops > 0:
            lines.append(f"  **Stops:** {itinerary.stops}")
        else:
            lines.append("  **Type:** Direct flight")
        
        if itinerary.total_duration:
            lines.append(f"  **Total Duration:** {itinerary.total_duration}")
        
        if itinerary.cabin_class:
            lines.append(f"  **Cabin:** {itinerary.cabin_class}")
        
        # Price breakdown
        lines.append("")
        lines.append("💰 **Price Breakdown**")
        lines.append(f"  **Base Fare:** {self.format_price(itinerary.price.base_fare, itinerary.price.currency)}")
        
        if itinerary.price.taxes > 0:
            lines.append(f"  **Taxes & Fees:** {self.format_price(itinerary.price.taxes, itinerary.price.currency)}")
        
        lines.append(f"  **Total:** {self.format_price(itinerary.price.total, itinerary.price.currency)}")
        
        # Baggage information
        if itinerary.baggage and include_details:
            lines.append("")
            lines.append("🧳 **Baggage**")
            
            if itinerary.baggage.included:
                if itinerary.baggage.weight:
                    lines.append(f"  **Allowance:** {itinerary.baggage.weight}")
                elif itinerary.baggage.pieces:
                    lines.append(f"  **Allowance:** {itinerary.baggage.pieces} piece(s)")
                else:
                    lines.append("  **Allowance:** Included")
            else:
                lines.append("  **Allowance:** Not included")
            
            if itinerary.baggage.description:
                lines.append(f"  **Details:** {itinerary.baggage.description}")
        
        return "\n".join(lines)
    
    def format_itinerary_voice(self, itinerary: Itinerary) -> str:
        """Format itinerary for voice/audio response"""
        
        # Get main route info
        outbound_start = itinerary.outbound_segments[0]
        outbound_end = itinerary.outbound_segments[-1]
        
        departure_city = self.iata_resolver.get_city_name(outbound_start.departure_airport) or outbound_start.departure_airport
        arrival_city = self.iata_resolver.get_city_name(outbound_end.arrival_airport) or outbound_end.arrival_airport
        
        # Build voice response
        parts = []
        
        # Basic route and price
        total_price = self.format_price(itinerary.price.total, itinerary.price.currency)
        parts.append(f"I found a flight from {departure_city} to {arrival_city} for {total_price}.")
        
        # Flight details
        if len(itinerary.outbound_segments) == 1:
            # Direct flight
            segment = itinerary.outbound_segments[0]
            departure_time = self.format_time(segment.departure_time)
            arrival_time = self.format_time(segment.arrival_time)
            
            parts.append(f"It's a direct flight with {segment.carrier_name}, departing at {departure_time} and arriving at {arrival_time}.")
        else:
            # Connecting flight
            stops = len(itinerary.outbound_segments) - 1
            parts.append(f"This journey has {stops} stop{'s' if stops > 1 else ''}.")
        
        # Return flight for round trips
        if itinerary.return_segments:
            return_start = itinerary.return_segments[0]
            return_end = itinerary.return_segments[-1]
            
            return_departure_time = self.format_time(return_start.departure_time)
            return_arrival_time = self.format_time(return_end.arrival_time)
            
            if len(itinerary.return_segments) == 1:
                parts.append(f"The return flight departs at {return_departure_time} and arrives at {return_arrival_time}.")
            else:
                return_stops = len(itinerary.return_segments) - 1
                parts.append(f"The return journey has {return_stops} stop{'s' if return_stops > 1 else ''}, departing at {return_departure_time}.")
        
        # Baggage info if included
        if itinerary.baggage and itinerary.baggage.included:
            if itinerary.baggage.weight:
                parts.append(f"Baggage allowance is {itinerary.baggage.weight}.")
            else:
                parts.append("Baggage is included.")
        
        return " ".join(parts)
    
    def format_multiple_options(
        self, 
        itineraries: List[Itinerary], 
        modality: MessageModality = MessageModality.TEXT,
        max_options: int = 3
    ) -> str:
        """Format multiple flight options"""
        
        if not itineraries:
            return "Sorry, no flights were found for your search criteria."
        
        # Limit to max options
        limited_itineraries = itineraries[:max_options]
        
        if modality == MessageModality.VOICE:
            return self._format_multiple_options_voice(limited_itineraries)
        else:
            return self._format_multiple_options_text(limited_itineraries)
    
    def _format_multiple_options_text(self, itineraries: List[Itinerary]) -> str:
        """Format multiple options for text display"""
        
        lines = []
        lines.append(f"🎯 **Found {len(itineraries)} flight option{'s' if len(itineraries) > 1 else ''}:**")
        lines.append("")
        
        for i, itinerary in enumerate(itineraries, 1):
            # Basic info
            outbound_start = itinerary.outbound_segments[0]
            outbound_end = itinerary.outbound_segments[-1]
            
            departure_city = self.iata_resolver.get_city_name(outbound_start.departure_airport) or outbound_start.departure_airport
            arrival_city = self.iata_resolver.get_city_name(outbound_end.arrival_airport) or outbound_end.arrival_airport
            
            departure_time = self.format_time(outbound_start.departure_time)
            arrival_time = self.format_time(outbound_end.arrival_time)
            
            price = self.format_price(itinerary.price.total, itinerary.price.currency)
            
            lines.append(f"**Option {i}:** {departure_city} → {arrival_city}")
            lines.append(f"  ⏰ {departure_time} - {arrival_time}")
            lines.append(f"  💰 {price}")
            
            # Stops info
            if itinerary.stops == 0:
                lines.append("  🛫 Direct flight")
            else:
                lines.append(f"  🔄 {itinerary.stops} stop{'s' if itinerary.stops > 1 else ''}")
            
            # Carrier info
            carriers = set()
            for segment in itinerary.outbound_segments:
                carriers.add(segment.carrier_name)
            if itinerary.return_segments:
                for segment in itinerary.return_segments:
                    carriers.add(segment.carrier_name)
            
            if len(carriers) == 1:
                lines.append(f"  ✈️ {list(carriers)[0]}")
            else:
                lines.append(f"  ✈️ {', '.join(carriers)}")
            
            # Add search date if available
            search_date = getattr(itinerary, 'search_date', None)
            if search_date:
                formatted_date = self.format_date(search_date)
                lines.append(f"  📅 {formatted_date}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_multiple_options_voice(self, itineraries: List[Itinerary]) -> str:
        """Format multiple options for voice response"""
        
        if len(itineraries) == 1:
            return self.format_itinerary_voice(itineraries[0])
        
        parts = []
        parts.append(f"I found {len(itineraries)} flight options for you.")
        
        for i, itinerary in enumerate(itineraries, 1):
            outbound_start = itinerary.outbound_segments[0]
            outbound_end = itinerary.outbound_segments[-1]
            
            departure_city = self.iata_resolver.get_city_name(outbound_start.departure_airport) or outbound_start.departure_airport
            arrival_city = self.iata_resolver.get_city_name(outbound_end.arrival_airport) or outbound_end.arrival_airport
            
            departure_time = self.format_time(outbound_start.departure_time)
            price = self.format_price(itinerary.price.total, itinerary.price.currency)
            
            option_text = f"Option {i}: departing at {departure_time} for {price}"
            
            if itinerary.stops == 0:
                option_text += " with no stops"
            elif itinerary.stops == 1:
                option_text += " with one stop"
            else:
                option_text += f" with {itinerary.stops} stops"
            
            parts.append(option_text + ".")
        
        return " ".join(parts)
    
    def format_no_results(
        self, 
        search_criteria: Dict[str, str],
        modality: MessageModality = MessageModality.TEXT
    ) -> str:
        """Format no results message"""
        
        if modality == MessageModality.VOICE:
            return f"Sorry, I couldn't find any flights from {search_criteria.get('from', 'your origin')} to {search_criteria.get('to', 'your destination')} for the selected dates. Would you like to try different dates or destinations?"
        else:
            lines = []
            lines.append("❌ **No flights found**")
            lines.append("")
            lines.append("We couldn't find any flights matching your criteria:")
            
            if search_criteria.get('from'):
                lines.append(f"  **From:** {search_criteria['from']}")
            if search_criteria.get('to'):
                lines.append(f"  **To:** {search_criteria['to']}")
            if search_criteria.get('date'):
                lines.append(f"  **Date:** {search_criteria['date']}")
            if search_criteria.get('passengers'):
                lines.append(f"  **Passengers:** {search_criteria['passengers']}")
            
            lines.append("")
            lines.append("💡 **Suggestions:**")
            lines.append("• Try different dates")
            lines.append("• Check nearby airports")
            lines.append("• Consider flexible dates")
            lines.append("• Remove carrier preferences")
            
            return "\n".join(lines) 