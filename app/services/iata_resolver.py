"""
IATA code resolver with LLM assistance and fallback mapping for major cities
"""

from typing import List, Optional, Dict
import asyncio

from ..services.openai_io import OpenAIService
from ..utils.errors import IATAResolutionError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class IATAResolver:
    """Service for resolving city names to IATA airport codes"""
    
    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service
        
        # Major cities with multiple airports (metro areas)
        self.multi_airport_cities = {
            # Major hubs with multiple airports
            "london": ["LHR", "LGW", "STN", "LTN", "LCY", "SEN"],
            "new york": ["JFK", "LGA", "EWR"],
            "paris": ["CDG", "ORY", "BVA"],
            "tokyo": ["NRT", "HND"],
            "milan": ["MXP", "LIN", "BGY"],
            "rome": ["FCO", "CIA"],
            "istanbul": ["IST", "SAW"],
            "moscow": ["SVO", "DME", "VKO"],
            "bangkok": ["BKK", "DMK"],
            "chicago": ["ORD", "MDW"],
            "los angeles": ["LAX", "BUR", "LGB", "SNA"],
            "washington": ["DCA", "IAD", "BWI"],
            "berlin": ["BER", "SXF"],
            "buenos aires": ["EZE", "AEP"],
            "rio de janeiro": ["GIG", "SDU"],
            "sao paulo": ["GRU", "CGH", "VCP"],
            "shanghai": ["PVG", "SHA"],
            "beijing": ["PEK", "PKX"],
            "osaka": ["KIX", "ITM"],
            "stockholm": ["ARN", "BMA", "NYO"],
            "montreal": ["YUL", "YMX"],
            "houston": ["IAH", "HOU"],
            "miami": ["MIA", "FLL", "PBI"],
            "dubai": ["DXB", "DWC"],
            "tehran": ["IKA", "THR"],
        }
        
        # Single-airport cities (major destinations)
        self.single_airport_cities = {
            # Europe
            "madrid": ["MAD"],
            "barcelona": ["BCN"],
            "amsterdam": ["AMS"],
            "frankfurt": ["FRA"],
            "munich": ["MUC"],
            "zurich": ["ZUR"],
            "vienna": ["VIE"],
            "copenhagen": ["CPH"],
            "oslo": ["OSL"],
            "helsinki": ["HEL"],
            "dublin": ["DUB"],
            "edinburgh": ["EDI"],
            "manchester": ["MAN"],
            "brussels": ["BRU"],
            "lisbon": ["LIS"],
            "athens": ["ATH"],
            "warsaw": ["WAW"],
            "prague": ["PRG"],
            "budapest": ["BUD"],
            "bucharest": ["OTP"],
            "sofia": ["SOF"],
            "zagreb": ["ZAG"],
            "belgrade": ["BEG"],
            "kiev": ["KBP"],
            "minsk": ["MSQ"],
            "riga": ["RIX"],
            "tallinn": ["TLL"],
            "vilnius": ["VNO"],
            
            # Middle East & Central Asia
            "doha": ["DOH"],
            "kuwait": ["KWI"],
            "riyadh": ["RUH"],
            "jeddah": ["JED"],
            "muscat": ["MCT"],
            "abu dhabi": ["AUH"],
            "sharjah": ["SHJ"],
            "cairo": ["CAI"],
            "casablanca": ["CMN"],
            "tunis": ["TUN"],
            "algiers": ["ALG"],
            "baku": ["GYD"],
            "yerevan": ["EVN"],
            "tbilisi": ["TBS"],
            "almaty": ["ALA"],
            "tashkent": ["TAS"],
            "ashgabat": ["ASB"],
            
            # Asia
            "delhi": ["DEL"],
            "mumbai": ["BOM"],
            "chennai": ["MAA"],
            "bangalore": ["BLR"],
            "hyderabad": ["HYD"],
            "kolkata": ["CCU"],
            "ahmedabad": ["AMD"],
            "pune": ["PNQ"],
            "cochin": ["COK"],
            "goa": ["GOI"],
            "singapore": ["SIN"],
            "kuala lumpur": ["KUL"],
            "jakarta": ["CGK"],
            "manila": ["MNL"],
            "cebu": ["CEB"],
            "ho chi minh": ["SGN"],
            "hanoi": ["HAN"],
            "phnom penh": ["PNH"],
            "yangon": ["RGN"],
            "dhaka": ["DAC"],
            "karachi": ["KHI"],
            "lahore": ["LHE"],
            "islamabad": ["ISB"],
            "peshawar": ["PEW"],
            "faisalabad": ["LYP"],
            "multan": ["MUX"],
            "sialkot": ["SKT"],
            "quetta": ["UET"],
            "colombo": ["CMB"],
            "male": ["MLE"],
            "kathmandu": ["KTM"],
            "kabul": ["KBL"],
            "seoul": ["ICN"],
            "busan": ["PUS"],
            "hong kong": ["HKG"],
            "macau": ["MFM"],
            "taipei": ["TPE"],
            "kaohsiung": ["KHH"],
            
            # Africa
            "johannesburg": ["JNB"],
            "cape town": ["CPT"],
            "durban": ["DUR"],
            "lagos": ["LOS"],
            "abuja": ["ABV"],
            "nairobi": ["NBO"],
            "addis ababa": ["ADD"],
            "khartoum": ["KRT"],
            "accra": ["ACC"],
            "dakar": ["DKR"],
            "bamako": ["BKO"],
            "ouagadougou": ["OUA"],
            "abidjan": ["ABJ"],
            "douala": ["DLA"],
            "libreville": ["LBV"],
            "kinshasa": ["FIH"],
            "luanda": ["LAD"],
            "maputo": ["MPM"],
            "antananarivo": ["TNR"],
            "mauritius": ["MRU"],
            
            # Americas
            "toronto": ["YYZ"],
            "vancouver": ["YVR"],
            "calgary": ["YYC"],
            "ottawa": ["YOW"],
            "mexico city": ["MEX"],
            "cancun": ["CUN"],
            "guadalajara": ["GDL"],
            "tijuana": ["TIJ"],
            "bogota": ["BOG"],
            "medellin": ["MDE"],
            "lima": ["LIM"],
            "quito": ["UIO"],
            "guayaquil": ["GYE"],
            "caracas": ["CCS"],
            "la paz": ["LPB"],
            "santa cruz": ["VVI"],
            "asuncion": ["ASU"],
            "montevideo": ["MVD"],
            "santiago": ["SCL"],
            "san francisco": ["SFO"],
            "san diego": ["SAN"],
            "las vegas": ["LAS"],
            "phoenix": ["PHX"],
            "denver": ["DEN"],
            "atlanta": ["ATL"],
            "orlando": ["MCO"],
            "tampa": ["TPA"],
            "charlotte": ["CLT"],
            "nashville": ["BNA"],
            "new orleans": ["MSY"],
            "dallas": ["DFW"],
            "austin": ["AUS"],
            "san antonio": ["SAT"],
            "seattle": ["SEA"],
            "portland": ["PDX"],
            "salt lake city": ["SLC"],
            "minneapolis": ["MSP"],
            "detroit": ["DTW"],
            "cleveland": ["CLE"],
            "pittsburgh": ["PIT"],
            "philadelphia": ["PHL"],
            "boston": ["BOS"],
            
            # Oceania
            "sydney": ["SYD"],
            "melbourne": ["MEL"],
            "brisbane": ["BNE"],
            "perth": ["PER"],
            "adelaide": ["ADL"],
            "auckland": ["AKL"],
            "wellington": ["WLG"],
            "christchurch": ["CHC"],
            "suva": ["SUV"],
            "port moresby": ["POM"],
        }
        
        # Combine all cities for easy lookup
        self.all_cities = {**self.multi_airport_cities, **self.single_airport_cities}
    
    async def resolve_city_to_iata(self, city_name: str) -> List[str]:
        """
        Resolve a city name to IATA airport codes
        
        Args:
            city_name: City name in any language
            
        Returns:
            List of IATA codes for the city
        """
        
        if not city_name or not city_name.strip():
            return []
        
        city_name = city_name.lower().strip()
        
        # First check our static mapping
        static_result = self._check_static_mapping(city_name)
        if static_result:
            logger.info(f"Resolved '{city_name}' to {static_result} via static mapping")
            return static_result
        
        # If not found, use LLM to resolve
        try:
            llm_result = await self._resolve_with_llm(city_name)
            if llm_result:
                logger.info(f"Resolved '{city_name}' to {llm_result} via LLM")
                return llm_result
        except Exception as e:
            logger.warning(f"LLM resolution failed for '{city_name}': {str(e)}")
        
        # If all else fails, return empty list
        logger.warning(f"Could not resolve city '{city_name}' to IATA codes")
        return []
    
    def _check_static_mapping(self, city_name: str) -> Optional[List[str]]:
        """Check static city-to-IATA mapping"""
        
        city_name = city_name.lower().strip()
        
        # Direct match
        if city_name in self.all_cities:
            return self.all_cities[city_name]
        
        # Try partial matches for common variations
        variations = [
            city_name.replace("city", "").strip(),
            city_name.replace("airport", "").strip(),
            city_name.replace("international", "").strip(),
        ]
        
        for variation in variations:
            if variation in self.all_cities:
                return self.all_cities[variation]
        
        # Try finding cities that contain the search term
        for city, codes in self.all_cities.items():
            if city_name in city or city in city_name:
                return codes
        
        return None
    
    async def _resolve_with_llm(self, city_name: str) -> Optional[List[str]]:
        """Use LLM to resolve city name to IATA codes"""
        
        prompt = f"""You are an airport code expert. Convert the city name to IATA airport codes.

City: {city_name}

Rules:
1. Return only valid 3-letter IATA codes
2. For cities with multiple airports, list all major ones
3. If you don't know the city or it has no major airport, return "UNKNOWN"
4. Format: comma-separated codes (e.g., "LHR,LGW,STN" for London)

Examples:
- London -> LHR,LGW,STN,LTN,LCY
- Paris -> CDG,ORY
- Delhi -> DEL
- Unknown City -> UNKNOWN

Airport codes for {city_name}:"""
        
        try:
            response = await self.openai_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="gpt-4o-mini",
                temperature=0.1,
                max_tokens=50
            )
            
            response = response.strip().upper()
            
            if response == "UNKNOWN" or not response:
                return None
            
            # Parse comma-separated codes
            codes = [code.strip() for code in response.split(",")]
            
            # Validate codes (should be 3 letters)
            valid_codes = []
            for code in codes:
                if len(code) == 3 and code.isalpha():
                    valid_codes.append(code)
            
            return valid_codes if valid_codes else None
            
        except Exception as e:
            logger.error(f"LLM resolution error for '{city_name}': {str(e)}")
            return None
    
    def get_city_name(self, iata_code: str) -> Optional[str]:
        """
        Get city name from IATA code (reverse lookup)
        
        Args:
            iata_code: 3-letter IATA airport code
            
        Returns:
            City name if found, None otherwise
        """
        
        iata_code = iata_code.upper().strip()
        
        for city, codes in self.all_cities.items():
            if iata_code in codes:
                return city.title()
        
        return None
    
    def is_multi_airport_city(self, city_name: str) -> bool:
        """
        Check if a city has multiple airports
        
        Args:
            city_name: City name
            
        Returns:
            True if city has multiple airports
        """
        
        city_name = city_name.lower().strip()
        return city_name in self.multi_airport_cities
    
    def get_primary_airport(self, city_name: str) -> Optional[str]:
        """
        Get the primary/main airport for a city
        
        Args:
            city_name: City name
            
        Returns:
            Primary IATA code if found
        """
        
        city_name = city_name.lower().strip()
        
        if city_name in self.all_cities:
            codes = self.all_cities[city_name]
            return codes[0] if codes else None
        
        return None
    
    async def resolve_multiple_cities(self, city_names: List[str]) -> Dict[str, List[str]]:
        """
        Resolve multiple cities to IATA codes in parallel
        
        Args:
            city_names: List of city names
            
        Returns:
            Dictionary mapping city names to IATA codes
        """
        
        tasks = []
        for city_name in city_names:
            task = self.resolve_city_to_iata(city_name)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        city_to_codes = {}
        for i, city_name in enumerate(city_names):
            result = results[i]
            if isinstance(result, Exception):
                logger.error(f"Error resolving city '{city_name}': {str(result)}")
                city_to_codes[city_name] = []
            else:
                city_to_codes[city_name] = result
        
        return city_to_codes 