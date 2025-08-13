"""
Pydantic models for data structures used throughout the application
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum


class TripType(str, Enum):
    """Trip type enumeration"""
    ONE_WAY = "one_way"
    ROUND_TRIP = "round_trip"
    MULTI_CITY = "multi_city"


class MessageModality(str, Enum):
    """Message modality enumeration"""
    TEXT = "text"
    VOICE = "voice"


class ConversationState(str, Enum):
    """Conversation state enumeration"""
    INITIAL = "initial"
    COLLECTING_SLOTS = "collecting_slots"
    SEARCHING = "searching"
    PRESENTING_RESULTS = "presenting_results"
    CLARIFYING = "clarifying"


class Slots(BaseModel):
    """Travel search slot information"""
    from_city: Optional[str] = None
    to_city: Optional[str] = None
    date: Optional[str] = None  # YYYY-MM-DD format
    return_date: Optional[str] = None  # For round trips
    passengers: Optional[int] = 1
    trip_type: Optional[TripType] = None
    preferred_carrier: Optional[str] = None
    
    # Resolved IATA codes
    from_iata_codes: Optional[List[str]] = None
    to_iata_codes: Optional[List[str]] = None
    
    # Date search type
    date_search_type: Optional[Literal["exact", "month", "range"]] = "exact"
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None


class BaggageInfo(BaseModel):
    """Baggage allowance information"""
    weight: Optional[str] = None
    pieces: Optional[int] = None
    included: bool = False
    description: Optional[str] = None


class FlightSegment(BaseModel):
    """Single flight segment information"""
    flight_number: str
    carrier_code: str
    carrier_name: str
    departure_airport: str
    departure_city: str
    arrival_airport: str
    arrival_city: str
    departure_time: str
    arrival_time: str
    duration: Optional[str] = None
    aircraft_type: Optional[str] = None


class PriceBreakdown(BaseModel):
    """Price breakdown information"""
    base_fare: float
    taxes: float
    total: float
    currency: str = "USD"


class Itinerary(BaseModel):
    """Complete flight itinerary"""
    outbound_segments: List[FlightSegment]
    return_segments: Optional[List[FlightSegment]] = None
    price: PriceBreakdown
    baggage: Optional[BaggageInfo] = None
    total_duration: Optional[str] = None
    stops: int = 0
    brand: Optional[str] = None
    cabin_class: Optional[str] = None


class Message(BaseModel):
    """Individual message in conversation"""
    role: Literal["user", "assistant"]
    content: str
    modality: MessageModality
    language: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    media_url: Optional[str] = None  # For voice messages


class ConversationData(BaseModel):
    """Complete conversation data structure"""
    user_id: str
    slots: Slots
    messages: List[Message]
    state: ConversationState = ConversationState.INITIAL
    language: Optional[str] = None
    last_modality: Optional[MessageModality] = None
    last_completed_search: Optional[str] = None  # Hash of search parameters
    last_itinerary_summary: Optional[str] = None
    state_version: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TwilioWebhookData(BaseModel):
    """Twilio webhook incoming data"""
    MessageSid: str
    AccountSid: str
    From: str
    To: str
    Body: Optional[str] = None
    MediaUrl0: Optional[str] = None
    MediaContentType0: Optional[str] = None
    NumMedia: str = "0"


class SearchRequest(BaseModel):
    """Flight search request"""
    slots: Slots
    user_id: str
    language: Optional[str] = None


class QueryReformulatorInput(BaseModel):
    """Input for query reformulator"""
    user_message: str
    conversation_history: List[Message]
    current_slots: Slots


class QueryReformulatorOutput(BaseModel):
    """Output from query reformulator"""
    from_city_name: Optional[str] = None
    to_city_name: Optional[str] = None
    date: Optional[str] = None
    date_range: Optional[str] = None
    month: Optional[str] = None
    passengers: Optional[int] = None
    trip_type: Optional[TripType] = None
    preferred_carrier: Optional[str] = None
    from_iata_codes: Optional[List[str]] = None
    to_iata_codes: Optional[List[str]] = None
    intent: Optional[str] = None
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


class TravelportResponse(BaseModel):
    """Travelport API response structure"""
    transaction_id: Optional[str] = None
    offerings: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    success: bool = True


class AgentState(BaseModel):
    """LangGraph agent state"""
    user_id: str
    user_message: str
    conversation_data: ConversationData
    reformulated_query: Optional[QueryReformulatorOutput] = None
    search_results: Optional[List[Itinerary]] = None
    response_text: Optional[str] = None
    response_audio_url: Optional[str] = None
    should_search: bool = False
    needs_clarification: bool = False
    clarification_question: Optional[str] = None 