"""
Query reformulator using GPT-4o-mini for noise-free travel intent extraction
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..services.openai_io import OpenAIService
from ..models.schemas import (
    QueryReformulatorInput, 
    QueryReformulatorOutput, 
    Message, 
    Slots,
    TripType
)
from ..utils.logging import get_logger
from ..utils.errors import ValidationError

logger = get_logger(__name__)


class QueryReformulator:
    """GPT-4o-mini powered query reformulator for travel intent extraction"""
    
    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service
        
        # Common travel-related patterns and synonyms
        self.travel_patterns = {
            "trip_types": {
                "one_way": ["one way", "single", "oneway", "one-way", "just going"],
                "round_trip": ["round trip", "return", "roundtrip", "round-trip", "both ways", "there and back"],
                "multi_city": ["multi city", "multiple cities", "several stops", "multi-city"]
            },
            "date_indicators": {
                "flexible": ["flexible", "any time", "whenever", "doesn't matter", "open"],
                "urgent": ["asap", "urgent", "soon", "quickly", "immediately"],
                "specific": ["exactly", "specifically", "precisely", "must be"]
            },
            "price_sensitivity": {
                "budget": ["cheap", "cheapest", "budget", "affordable", "low cost", "economical"],
                "premium": ["business", "first class", "luxury", "premium", "comfortable"],
                "flexible": ["any price", "price doesn't matter", "whatever it costs"]
            }
        }
    
    async def reformulate_query(self, input_data: QueryReformulatorInput) -> QueryReformulatorOutput:
        """
        Reformulate user query to extract clean travel intent
        
        Args:
            input_data: Input containing user message, history, and current slots
            
        Returns:
            Reformulated query output with extracted travel information
        """
        
        try:
            logger.info("Starting query reformulation")
            
            # Build context-aware prompt
            prompt = self._build_reformulation_prompt(input_data)
            
            # Call GPT-4o-mini
            response = await self.openai_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="gpt-4o-mini",
                temperature=0.1,  # Low temperature for consistent extraction
                response_format={"type": "json_object"}
            )
            
            # Parse and validate response
            reformulated_data = json.loads(response)
            output = self._validate_and_structure_output(reformulated_data, input_data)
            
            logger.info(f"Query reformulated successfully: {output.intent}")
            return output
            
        except Exception as e:
            logger.error(f"Query reformulation failed: {str(e)}")
            return self._create_fallback_output(input_data)
    
    def _build_reformulation_prompt(self, input_data: QueryReformulatorInput) -> str:
        """Build the reformulation prompt for GPT-4o-mini"""
        
        # Get conversation context
        history_context = self._format_conversation_history(input_data.conversation_history[-3:])
        
        # Get current slots context
        slots_context = self._format_current_slots(input_data.current_slots)
        
        # Detect user intent patterns
        intent_hints = self._detect_intent_patterns(input_data.user_message)
        
        prompt = f"""You are a travel booking query reformulator. Extract clean, structured travel information from user messages.

CONTEXT:
Previous conversation:
{history_context}

Current booking state:
{slots_context}

USER'S LATEST MESSAGE: "{input_data.user_message}"

INTENT ANALYSIS HINTS:
{intent_hints}

EXTRACTION RULES:
1. Extract ONLY explicit travel information from the latest message
2. For cities: Convert to IATA codes when possible (London=LHR,LGW,STN,LTN,LCY; NYC=JFK,LGA,EWR; etc.)
3. For dates: Handle natural language (tomorrow, next Friday, 24th August, September, etc.)
4. For ranges: Detect "cheapest in [month]" or "between [date1] and [date2]"
5. For carriers: Extract airline preferences (TK=Turkish Airlines, BA=British Airways, etc.)
6. Preserve user intent: budget-focused, date-flexible, carrier-specific
7. Flag ambiguities that need clarification

RESPONSE FORMAT (JSON):
{{
  "from_city_name": "London" or null,
  "to_city_name": "Dubai" or null,
  "from_iata_codes": ["LHR", "LGW", "STN"] or null,
  "to_iata_codes": ["DXB"] or null,
  "date": "2025-08-24" or null,
  "date_range": "12th-16th August" or null,
  "month": "September 2025" or null,
  "passengers": 2 or null,
  "trip_type": "one_way" or "round_trip" or "multi_city" or null,
  "preferred_carrier": "TK" or null,
  "intent": "search_specific_date" or "search_month_range" or "modify_destination" or "clarify_dates" etc,
  "needs_clarification": false,
  "clarification_question": "What date would you like to travel?" or null,
  "confidence_level": "high" or "medium" or "low",
  "price_sensitivity": "budget" or "flexible" or "premium" or null,
  "flexibility_indicators": ["date_flexible", "airport_flexible"] or []
}}

Extract information accurately and flag any ambiguities:"""
        
        return prompt
    
    def _format_conversation_history(self, messages: List[Message]) -> str:
        """Format conversation history for context"""
        
        if not messages:
            return "No previous conversation"
        
        formatted = []
        for msg in messages:
            role = "User" if msg.role == "user" else "Assistant"
            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            formatted.append(f"{role}: {content}")
        
        return "\n".join(formatted)
    
    def _format_current_slots(self, slots: Slots) -> str:
        """Format current slots for context"""
        
        return f"""Origin: {slots.from_city or 'Not specified'} ({slots.from_iata_codes or 'No codes'})
Destination: {slots.to_city or 'Not specified'} ({slots.to_iata_codes or 'No codes'})
Departure: {slots.date or 'Not specified'}
Return: {slots.return_date or 'Not specified'}
Passengers: {slots.passengers or 1}
Trip Type: {slots.trip_type or 'Not specified'}
Preferred Carrier: {slots.preferred_carrier or 'No preference'}
Search Type: {slots.date_search_type or 'exact'}"""
    
    def _detect_intent_patterns(self, user_message: str) -> str:
        """Detect intent patterns in user message"""
        
        message_lower = user_message.lower()
        detected_patterns = []
        
        # Check for trip type patterns
        for trip_type, patterns in self.travel_patterns["trip_types"].items():
            if any(pattern in message_lower for pattern in patterns):
                detected_patterns.append(f"Trip type: {trip_type}")
        
        # Check for date patterns
        for date_type, patterns in self.travel_patterns["date_indicators"].items():
            if any(pattern in message_lower for pattern in patterns):
                detected_patterns.append(f"Date preference: {date_type}")
        
        # Check for price sensitivity
        for price_type, patterns in self.travel_patterns["price_sensitivity"].items():
            if any(pattern in message_lower for pattern in patterns):
                detected_patterns.append(f"Price sensitivity: {price_type}")
        
        # Check for specific patterns
        if any(word in message_lower for word in ["cheapest", "best price", "lowest fare"]):
            detected_patterns.append("Intent: Find cheapest option")
        
        if any(word in message_lower for word in ["tomorrow", "today", "next week"]):
            detected_patterns.append("Date type: Relative date")
        
        if any(word in message_lower for word in ["september", "october", "november", "december", "january", "february", "march", "april", "may", "june", "july", "august"]):
            detected_patterns.append("Date type: Monthly search")
        
        if "between" in message_lower and "and" in message_lower:
            detected_patterns.append("Date type: Range search")
        
        return "\n".join(detected_patterns) if detected_patterns else "No specific patterns detected"
    
    def _validate_and_structure_output(self, raw_data: Dict[str, Any], input_data: QueryReformulatorInput) -> QueryReformulatorOutput:
        """Validate and structure the reformulated output"""
        
        try:
            # Create output with validation
            output = QueryReformulatorOutput(**raw_data)
            
            # Additional validation and corrections
            output = self._apply_business_logic(output, input_data)
            
            return output
            
        except Exception as e:
            logger.warning(f"Failed to validate reformulated output: {str(e)}")
            return self._create_fallback_output(input_data)
    
    def _apply_business_logic(self, output: QueryReformulatorOutput, input_data: QueryReformulatorInput) -> QueryReformulatorOutput:
        """Apply business logic corrections to the output"""
        
        # Inherit from current slots if not specified
        current_slots = input_data.current_slots
        
        if not output.from_city_name and current_slots.from_city:
            output.from_city_name = current_slots.from_city
            output.from_iata_codes = current_slots.from_iata_codes
        
        if not output.to_city_name and current_slots.to_city:
            output.to_city_name = current_slots.to_city
            output.to_iata_codes = current_slots.to_iata_codes
        
        if not output.passengers and current_slots.passengers:
            output.passengers = current_slots.passengers
        
        if not output.trip_type and current_slots.trip_type:
            output.trip_type = current_slots.trip_type
        
        # Set default trip type if not specified
        if not output.trip_type:
            # Infer from context
            if output.date and not output.month and not output.date_range:
                output.trip_type = TripType.ONE_WAY  # Default for specific dates
        
        # Validate IATA codes format
        if output.from_iata_codes:
            output.from_iata_codes = [code.upper() for code in output.from_iata_codes if len(code) == 3]
        
        if output.to_iata_codes:
            output.to_iata_codes = [code.upper() for code in output.to_iata_codes if len(code) == 3]
        
        # Determine if clarification is needed
        if not output.needs_clarification:
            missing_critical = []
            
            if not output.from_city_name and not current_slots.from_city:
                missing_critical.append("origin")
            
            if not output.to_city_name and not current_slots.to_city:
                missing_critical.append("destination")
            
            if not output.date and not output.month and not output.date_range and not current_slots.date:
                missing_critical.append("travel date")
            
            if missing_critical:
                output.needs_clarification = True
                output.clarification_question = f"I need to know your {', '.join(missing_critical)} to find flights for you."
        
        return output
    
    def _create_fallback_output(self, input_data: QueryReformulatorInput) -> QueryReformulatorOutput:
        """Create fallback output when reformulation fails"""
        
        logger.warning("Creating fallback reformulation output")
        
        return QueryReformulatorOutput(
            intent="clarification_needed",
            needs_clarification=True,
            clarification_question="I need more information about your travel plans. Could you please tell me your origin, destination, and travel date?",
            confidence_level="low"
        )
    
    def extract_entities_with_patterns(self, text: str) -> Dict[str, Any]:
        """Extract travel entities using pattern matching as fallback"""
        
        text_lower = text.lower()
        entities = {}
        
        # Simple city extraction patterns
        city_patterns = [
            r'\bfrom\s+([a-zA-Z\s]+)\s+to\s+([a-zA-Z\s]+)',
            r'\b([a-zA-Z\s]+)\s+to\s+([a-zA-Z\s]+)',
            r'\bgoing\s+to\s+([a-zA-Z\s]+)',
            r'\btravel\s+to\s+([a-zA-Z\s]+)'
        ]
        
        # Date extraction patterns
        date_patterns = [
            r'\btomorrow\b',
            r'\btoday\b',
            r'\bnext\s+\w+',
            r'\b\d{1,2}(st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)',
            r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}',
            r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}'
        ]
        
        # This would contain actual regex matching logic
        # For now, return empty dict as this is a fallback
        
        return entities
    
    def get_reformulation_confidence(self, output: QueryReformulatorOutput, input_data: QueryReformulatorInput) -> float:
        """Calculate confidence score for the reformulation"""
        
        confidence_score = 0.0
        total_factors = 0
        
        # Factor 1: How much information was extracted
        extracted_info = 0
        if output.from_city_name: extracted_info += 1
        if output.to_city_name: extracted_info += 1
        if output.date or output.month or output.date_range: extracted_info += 1
        if output.passengers: extracted_info += 1
        if output.trip_type: extracted_info += 1
        
        confidence_score += (extracted_info / 5) * 0.4  # 40% weight
        total_factors += 0.4
        
        # Factor 2: IATA code resolution success
        if output.from_iata_codes and len(output.from_iata_codes) > 0:
            confidence_score += 0.2
        if output.to_iata_codes and len(output.to_iata_codes) > 0:
            confidence_score += 0.2
        total_factors += 0.4
        
        # Factor 3: Intent clarity
        if output.intent and output.intent != "clarification_needed":
            confidence_score += 0.2
        total_factors += 0.2
        
        # Normalize
        if total_factors > 0:
            return min(confidence_score / total_factors, 1.0)
        else:
            return 0.0
    
    async def reformulate_with_confidence(self, input_data: QueryReformulatorInput) -> tuple[QueryReformulatorOutput, float]:
        """Reformulate query and return confidence score"""
        
        output = await self.reformulate_query(input_data)
        confidence = self.get_reformulation_confidence(output, input_data)
        
        # Adjust output based on confidence
        if confidence < 0.3:
            output.needs_clarification = True
            if not output.clarification_question:
                output.clarification_question = "I need more details to help you find the right flights."
        
        logger.info(f"Reformulation confidence: {confidence:.2f}")
        
        return output, confidence 