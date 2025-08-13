"""
LangGraph transition conditions and policies for agent state management
"""

from typing import Dict, Any, List, Optional
from enum import Enum

from ..models.schemas import (
    AgentState, 
    ConversationState, 
    Slots, 
    TripType,
    QueryReformulatorOutput
)
from ..utils.logging import get_logger

logger = get_logger(__name__)


class NodeDecision(str, Enum):
    """Possible node decisions for graph transitions"""
    
    # Flow control
    CONTINUE = "continue"
    SKIP = "skip"
    RETRY = "retry"
    END = "end"
    
    # Specific transitions
    REFORMULATE = "reformulate"
    FILL_SLOTS = "fill_slots"
    PLAN_SEARCH = "plan_search"
    RUN_SEARCH = "run_search"
    SUMMARIZE = "summarize"
    RESPOND = "respond"
    CLARIFY = "clarify"


class AgentPolicies:
    """Decision policies for agent state transitions"""
    
    @staticmethod
    def should_reformulate_query(state: AgentState) -> bool:
        """Determine if we should reformulate the user's query"""
        
        # Always reformulate if we don't have a reformulated query yet
        if not state.reformulated_query:
            return True
        
        # Reformulate if the user message is significantly different from previous
        if len(state.user_message.strip()) > 10:  # Non-trivial message
            return True
        
        return False
    
    @staticmethod
    def should_fill_slots(state: AgentState) -> bool:
        """Determine if we should attempt to fill/update slots"""
        
        # Always try to fill slots after reformulation
        if state.reformulated_query:
            return True
        
        # Fill slots if we have partial information
        current_slots = state.conversation_data.slots
        
        if (not current_slots.from_city or 
            not current_slots.to_city or 
            not current_slots.date):
            return True
        
        return False
    
    @staticmethod
    def should_plan_search(state: AgentState) -> bool:
        """Determine if we should plan a search strategy"""
        
        # Plan search after slot filling
        return True
    
    @staticmethod
    def should_run_search(state: AgentState) -> bool:
        """Determine if we should execute a flight search"""
        
        return state.should_search and not state.needs_clarification
    
    @staticmethod
    def should_clarify(state: AgentState) -> bool:
        """Determine if we need to ask for clarification"""
        
        return state.needs_clarification
    
    @staticmethod
    def should_summarize_results(state: AgentState) -> bool:
        """Determine if we should summarize search results"""
        
        # Summarize if we have results and no clarification needed
        return (state.search_results is not None and 
                len(state.search_results) > 0 and 
                not state.needs_clarification)
    
    @staticmethod
    def should_respond(state: AgentState) -> bool:
        """Determine if we should generate a response"""
        
        # Always respond at the end
        return True


class SlotValidationPolicies:
    """Policies for validating and checking slot completeness"""
    
    @staticmethod
    def get_missing_required_slots(slots: Slots) -> List[str]:
        """Get list of missing required slots"""
        
        missing = []
        
        if not slots.from_city or not slots.from_iata_codes:
            missing.append("origin_city")
        
        if not slots.to_city or not slots.to_iata_codes:
            missing.append("destination_city")
        
        if not slots.date:
            missing.append("departure_date")
        
        # For round trips, we need return date unless it's a range/month search
        if (slots.trip_type == TripType.ROUND_TRIP and 
            not slots.return_date and 
            slots.date_search_type == "exact"):
            missing.append("return_date")
        
        # Passengers is optional but should default to 1
        if not slots.passengers:
            slots.passengers = 1
        
        return missing
    
    @staticmethod
    def validate_slot_values(slots: Slots) -> List[str]:
        """Validate slot values and return list of issues"""
        
        issues = []
        
        # Validate IATA codes
        if slots.from_iata_codes and not all(len(code) == 3 for code in slots.from_iata_codes):
            issues.append("invalid_origin_airport_codes")
        
        if slots.to_iata_codes and not all(len(code) == 3 for code in slots.to_iata_codes):
            issues.append("invalid_destination_airport_codes")
        
        # Validate passenger count
        if slots.passengers and (slots.passengers < 1 or slots.passengers > 9):
            issues.append("invalid_passenger_count")
        
        # Validate dates (basic format check)
        if slots.date and not SlotValidationPolicies._is_valid_date_format(slots.date):
            issues.append("invalid_departure_date_format")
        
        if slots.return_date and not SlotValidationPolicies._is_valid_date_format(slots.return_date):
            issues.append("invalid_return_date_format")
        
        return issues
    
    @staticmethod
    def _is_valid_date_format(date_str: str) -> bool:
        """Check if date string is in valid YYYY-MM-DD format"""
        
        try:
            parts = date_str.split('-')
            if len(parts) != 3:
                return False
            
            year, month, day = parts
            return (len(year) == 4 and 
                   len(month) == 2 and 
                   len(day) == 2 and
                   year.isdigit() and 
                   month.isdigit() and 
                   day.isdigit())
        except:
            return False
    
    @staticmethod
    def is_slots_complete_for_search(slots: Slots) -> bool:
        """Check if slots are complete enough for search"""
        
        missing = SlotValidationPolicies.get_missing_required_slots(slots)
        issues = SlotValidationPolicies.validate_slot_values(slots)
        
        return len(missing) == 0 and len(issues) == 0


class SearchPolicies:
    """Policies for determining search strategy and parameters"""
    
    @staticmethod
    def determine_search_type(slots: Slots) -> str:
        """Determine the type of search needed"""
        
        if slots.date_search_type == "month":
            return "month_search"
        elif slots.date_search_type == "range":
            return "range_search"
        elif slots.preferred_carrier:
            return "carrier_filtered_search"
        elif slots.from_iata_codes and len(slots.from_iata_codes) > 1:
            return "multi_airport_search"
        elif slots.to_iata_codes and len(slots.to_iata_codes) > 1:
            return "multi_airport_search"
        else:
            return "exact_search"
    
    @staticmethod
    def should_use_cached_results(state: AgentState) -> bool:
        """Determine if we can use cached search results"""
        
        if not state.conversation_data.last_completed_search:
            return False
        
        # Generate current search hash
        from ..services.travelport import TravelportService
        current_hash = TravelportService().get_search_hash(state.conversation_data.slots)
        
        return current_hash == state.conversation_data.last_completed_search
    
    @staticmethod
    def get_search_priority_order(slots: Slots) -> List[str]:
        """Get priority order for multi-airport searches"""
        
        priorities = []
        
        # Prioritize main airports for major cities
        major_airports = {
            "LHR", "JFK", "CDG", "DXB", "SIN", "NRT", "HND", 
            "FRA", "AMS", "MAD", "BCN", "FCO", "MXP"
        }
        
        if slots.from_iata_codes:
            # Sort by major airports first
            sorted_origins = sorted(
                slots.from_iata_codes,
                key=lambda x: (x not in major_airports, x)
            )
            priorities.extend(sorted_origins)
        
        return priorities
    
    @staticmethod
    def get_max_search_combinations(slots: Slots) -> int:
        """Get maximum number of search combinations to try"""
        
        # Limit combinations to prevent API abuse
        origin_count = len(slots.from_iata_codes) if slots.from_iata_codes else 1
        dest_count = len(slots.to_iata_codes) if slots.to_iata_codes else 1
        
        total_combinations = origin_count * dest_count
        
        # Limit based on search type
        if slots.date_search_type == "month":
            return min(total_combinations, 6)  # Max 6 airport combinations for month search
        elif slots.date_search_type == "range":
            return min(total_combinations, 9)  # Max 9 for range search
        else:
            return min(total_combinations, 12)  # Max 12 for exact search


class ResponsePolicies:
    """Policies for response generation and formatting"""
    
    @staticmethod
    def should_include_alternatives(state: AgentState) -> bool:
        """Determine if we should include alternative options"""
        
        if not state.search_results:
            return False
        
        # Include alternatives if we have multiple results
        return len(state.search_results) > 1
    
    @staticmethod
    def should_suggest_nearby_dates(state: AgentState) -> bool:
        """Determine if we should suggest nearby dates when no results found"""
        
        return (not state.search_results and 
                state.conversation_data.slots.date_search_type == "exact")
    
    @staticmethod
    def should_suggest_alternative_airports(state: AgentState) -> bool:
        """Determine if we should suggest alternative airports"""
        
        slots = state.conversation_data.slots
        
        return (not state.search_results and
                ((slots.from_iata_codes and len(slots.from_iata_codes) == 1) or
                 (slots.to_iata_codes and len(slots.to_iata_codes) == 1)))
    
    @staticmethod
    def get_response_tone(state: AgentState) -> str:
        """Determine the appropriate tone for the response"""
        
        if state.needs_clarification:
            return "helpful_questioning"
        elif state.search_results and len(state.search_results) > 0:
            return "enthusiastic_presenting"
        elif not state.search_results:
            return "empathetic_suggesting"
        else:
            return "neutral_informative"
    
    @staticmethod
    def should_include_booking_guidance(state: AgentState) -> bool:
        """Determine if we should include booking guidance"""
        
        # Include booking guidance if we have good results
        return (state.search_results and 
                len(state.search_results) > 0 and
                not state.needs_clarification)


class TransitionConditions:
    """Main class for determining graph transitions"""
    
    def __init__(self):
        self.policies = AgentPolicies()
        self.slot_policies = SlotValidationPolicies()
        self.search_policies = SearchPolicies()
        self.response_policies = ResponsePolicies()
    
    def next_node_after_reformulate(self, state: AgentState) -> NodeDecision:
        """Determine next node after query reformulation"""
        
        if self.policies.should_fill_slots(state):
            return NodeDecision.FILL_SLOTS
        else:
            return NodeDecision.PLAN_SEARCH
    
    def next_node_after_fill_slots(self, state: AgentState) -> NodeDecision:
        """Determine next node after slot filling"""
        
        return NodeDecision.PLAN_SEARCH
    
    def next_node_after_plan_search(self, state: AgentState) -> NodeDecision:
        """Determine next node after search planning"""
        
        if state.needs_clarification:
            return NodeDecision.CLARIFY
        elif state.should_search:
            return NodeDecision.RUN_SEARCH
        else:
            return NodeDecision.RESPOND
    
    def next_node_after_search(self, state: AgentState) -> NodeDecision:
        """Determine next node after running search"""
        
        if self.response_policies.should_include_alternatives(state):
            return NodeDecision.SUMMARIZE
        else:
            return NodeDecision.RESPOND
    
    def next_node_after_summarize(self, state: AgentState) -> NodeDecision:
        """Determine next node after summarizing results"""
        
        return NodeDecision.RESPOND
    
    def next_node_after_clarify(self, state: AgentState) -> NodeDecision:
        """Determine next node after clarification"""
        
        return NodeDecision.END
    
    def next_node_after_respond(self, state: AgentState) -> NodeDecision:
        """Determine next node after generating response"""
        
        return NodeDecision.END
    
    def should_continue_conversation(self, state: AgentState) -> bool:
        """Determine if conversation should continue"""
        
        # Continue if we're still clarifying or collecting information
        return (state.conversation_data.state in [
            ConversationState.INITIAL,
            ConversationState.COLLECTING_SLOTS,
            ConversationState.CLARIFYING
        ])
    
    def get_transition_reason(self, current_node: str, next_decision: NodeDecision, state: AgentState) -> str:
        """Get human-readable reason for transition decision"""
        
        reasons = {
            (NodeDecision.FILL_SLOTS): "Need to extract travel information from user message",
            (NodeDecision.PLAN_SEARCH): "Ready to plan flight search strategy",
            (NodeDecision.RUN_SEARCH): "All required information available, executing search",
            (NodeDecision.CLARIFY): "Missing required information, need user clarification",
            (NodeDecision.SUMMARIZE): "Multiple results found, preparing summary",
            (NodeDecision.RESPOND): "Ready to generate final response",
            (NodeDecision.END): "Conversation completed"
        }
        
        return reasons.get(next_decision, f"Transitioning to {next_decision}")
    
    def log_transition_decision(self, current_node: str, next_decision: NodeDecision, state: AgentState) -> None:
        """Log the transition decision with reasoning"""
        
        reason = self.get_transition_reason(current_node, next_decision, state)
        
        logger.info(
            f"Graph transition: {current_node} -> {next_decision}",
            extra={
                "current_node": current_node,
                "next_node": next_decision,
                "reason": reason,
                "conversation_state": state.conversation_data.state,
                "has_search_results": bool(state.search_results),
                "needs_clarification": state.needs_clarification
            }
        ) 