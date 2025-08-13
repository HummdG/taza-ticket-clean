"""
LangGraph flight agent for processing user messages and orchestrating flight search
"""

from typing import Dict, Any, Tuple, Optional, TypedDict, List
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from ..models.schemas import (
    AgentState, 
    ConversationData, 
    Message, 
    MessageModality, 
    ConversationState,
    Slots,
    QueryReformulatorInput,
    QueryReformulatorOutput,
    Itinerary,
    TripType
)


class AgentStateDict(TypedDict):
    """TypedDict version of AgentState for LangGraph"""
    user_id: str
    user_message: str
    conversation_data: ConversationData
    reformulated_query: Optional[QueryReformulatorOutput]
    search_results: Optional[List[Itinerary]]
    response_text: Optional[str]
    response_audio_url: Optional[str]
    should_search: bool
    needs_clarification: bool
    clarification_question: Optional[str]
from ..services.openai_io import OpenAIService
from ..services.travelport import TravelportService
from ..services.twilio_client import TwilioClient
from ..services.s3_media import S3MediaService
from ..services.date_parse import DateParsingService
from ..services.iata_resolver import IATAResolver
from ..services.search_strategy import SearchStrategy
from ..services.formatter import ItineraryFormatter
from ..integrations.dynamodb import DynamoDBRepository
from .memory import ConversationMemory, ConversationSummarizer, ContextManager
from .policies import TransitionConditions, NodeDecision
from ..utils.logging import get_logger
from ..utils.errors import TazaTicketError

logger = get_logger(__name__)


class FlightAgentGraph:
    """LangGraph-based flight agent for processing user requests"""
    
    def __init__(
        self,
        openai_service: OpenAIService,
        dynamodb_service: DynamoDBRepository,
        twilio_service: TwilioClient,
        s3_service: S3MediaService,
        travelport_service: TravelportService,
        date_service: DateParsingService,
        iata_resolver: IATAResolver,
        search_strategy: SearchStrategy,
        formatter: ItineraryFormatter
    ):
        self.openai_service = openai_service
        self.dynamodb_service = dynamodb_service
        self.twilio_service = twilio_service
        self.s3_service = s3_service
        self.travelport_service = travelport_service
        self.date_service = date_service
        self.iata_resolver = iata_resolver
        self.search_strategy = search_strategy
        self.formatter = formatter
        
        # Initialize memory and context management
        self.memory = ConversationMemory(dynamodb_service, window_size=10)
        self.summarizer = ConversationSummarizer(openai_service, max_messages=20)
        self.context_manager = ContextManager(self.memory, self.summarizer)
        
        # Initialize transition policies
        self.transition_conditions = TransitionConditions()
        
        # Build the LangGraph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph"""
        
        # Create state graph
        workflow = StateGraph(AgentStateDict)
        
        # Add nodes
        workflow.add_node("reformulate", self._reformulate_query_node)
        workflow.add_node("fill_slots", self._fill_slots_node)
        workflow.add_node("plan_search", self._plan_search_node)
        workflow.add_node("run_search", self._run_search_node)
        workflow.add_node("summarize", self._summarize_results_node)
        workflow.add_node("respond", self._generate_response_node)
        workflow.add_node("clarify", self._generate_clarification_node)
        
        # Set entry point
        workflow.set_entry_point("reformulate")
        
        # Add conditional edges based on policies
        workflow.add_conditional_edges(
            "reformulate",
            self._decide_after_reformulate,
            {
                NodeDecision.FILL_SLOTS: "fill_slots",
                NodeDecision.PLAN_SEARCH: "plan_search"
            }
        )
        
        workflow.add_conditional_edges(
            "fill_slots", 
            self._decide_after_fill_slots,
            {NodeDecision.PLAN_SEARCH: "plan_search"}
        )
        
        workflow.add_conditional_edges(
            "plan_search",
            self._decide_after_plan_search,
            {
                NodeDecision.RUN_SEARCH: "run_search",
                NodeDecision.CLARIFY: "clarify",
                NodeDecision.RESPOND: "respond"
            }
        )
        
        workflow.add_conditional_edges(
            "run_search",
            self._decide_after_search,
            {
                NodeDecision.SUMMARIZE: "summarize",
                NodeDecision.RESPOND: "respond"
            }
        )
        
        workflow.add_conditional_edges(
            "summarize",
            self._decide_after_summarize,
            {NodeDecision.RESPOND: "respond"}
        )
        
        # Terminal nodes
        workflow.add_edge("clarify", END)
        workflow.add_edge("respond", END)
        
        return workflow.compile()
    
    def _decide_after_reformulate(self, state: AgentStateDict) -> NodeDecision:
        """Decision function after reformulate node"""
        # Convert dict to AgentState for policy decisions
        agent_state = AgentState(**state)
        decision = self.transition_conditions.next_node_after_reformulate(agent_state)
        self.transition_conditions.log_transition_decision("reformulate", decision, agent_state)
        return decision
    
    def _decide_after_fill_slots(self, state: AgentStateDict) -> NodeDecision:
        """Decision function after fill_slots node"""
        agent_state = AgentState(**state)
        decision = self.transition_conditions.next_node_after_fill_slots(agent_state)
        self.transition_conditions.log_transition_decision("fill_slots", decision, agent_state)
        return decision
    
    def _decide_after_plan_search(self, state: AgentStateDict) -> NodeDecision:
        """Decision function after plan_search node"""
        agent_state = AgentState(**state)
        decision = self.transition_conditions.next_node_after_plan_search(agent_state)
        self.transition_conditions.log_transition_decision("plan_search", decision, agent_state)
        return decision
    
    def _decide_after_search(self, state: AgentStateDict) -> NodeDecision:
        """Decision function after run_search node"""
        agent_state = AgentState(**state)
        decision = self.transition_conditions.next_node_after_search(agent_state)
        self.transition_conditions.log_transition_decision("run_search", decision, agent_state)
        return decision
    
    def _decide_after_summarize(self, state: AgentStateDict) -> NodeDecision:
        """Decision function after summarize node"""
        agent_state = AgentState(**state)
        decision = self.transition_conditions.next_node_after_summarize(agent_state)
        self.transition_conditions.log_transition_decision("summarize", decision, agent_state)
        return decision
    
    async def process_message(
        self,
        user_id: str,
        user_message: str,
        input_modality: MessageModality = MessageModality.TEXT,
        media_url: Optional[str] = None
    ) -> Tuple[str, MessageModality, Optional[str]]:
        """
        Process user message through the agent graph
        
        Args:
            user_id: User identifier
            user_message: User's message content
            input_modality: Modality of input (text/voice)
            media_url: URL of media file if voice message
            
        Returns:
            Tuple of (response_content, response_modality, response_media_url)
        """
        
        logger.info(f"Processing message for user {user_id}: {input_modality}")
        
        try:
            # Load conversation data
            conversation_data = await self.dynamodb_service.get_conversation(user_id)
            if not conversation_data:
                conversation_data = ConversationData(
                    user_id=user_id,
                    slots=Slots(),
                    messages=[],
                    state=ConversationState.INITIAL
                )
            
            # Detect language if not already set
            detected_language = await self.openai_service.detect_language(user_message)
            if not conversation_data.language:
                conversation_data.language = detected_language
            
            # Add user message to conversation
            user_msg = Message(
                role="user",
                content=user_message,
                modality=input_modality,
                language=detected_language,
                media_url=media_url
            )
            conversation_data.messages.append(user_msg)
            conversation_data.last_modality = input_modality
            
            # Create agent state as TypedDict for LangGraph
            state: AgentStateDict = {
                "user_id": user_id,
                "user_message": user_message,
                "conversation_data": conversation_data,
                "reformulated_query": None,
                "search_results": None,
                "response_text": None,
                "response_audio_url": None,
                "should_search": False,
                "needs_clarification": False,
                "clarification_question": None
            }
            
            # Process through LangGraph
            final_state = await self.graph.ainvoke(state)
            
            # Generate audio if needed
            response_media_url = None
            target_modality = final_state["conversation_data"].last_modality
            
            if target_modality == MessageModality.VOICE and final_state.get("response_text"):
                try:
                    audio_data = await self.openai_service.text_to_speech(
                        final_state["response_text"],
                        voice="alloy"
                    )
                    response_media_url = await self.s3_service.upload_audio(
                        audio_data,
                        user_id,
                        content_type="audio/mpeg",
                        file_extension="mp3"
                    )
                    final_state["response_audio_url"] = response_media_url
                    logger.info("Generated TTS audio response")
                except Exception as e:
                    logger.warning(f"TTS generation failed, falling back to text: {str(e)}")
                    target_modality = MessageModality.TEXT
            
            # Add assistant message to conversation
            assistant_msg = Message(
                role="assistant",
                content=final_state.get("response_text", "Sorry, I encountered an issue processing your request."),
                modality=target_modality,
                language=conversation_data.language,
                media_url=response_media_url
            )
            final_state["conversation_data"].messages.append(assistant_msg)
            
            # Save updated conversation
            await self.dynamodb_service.save_conversation(final_state["conversation_data"])
            
            logger.info(f"Agent processing completed: {target_modality}")
            
            return final_state.get("response_text", "Sorry, I encountered an issue processing your request."), target_modality, response_media_url
            
        except Exception as e:
            logger.error(f"Agent processing failed: {str(e)}")
            
            # Generate fallback response
            fallback_message = self._get_fallback_response(detected_language if 'detected_language' in locals() else "en")
            return fallback_message, MessageModality.TEXT, None
    
    async def _reformulate_query_node(self, state: AgentStateDict) -> Dict[str, Any]:
        """Reformulate user query to extract travel intent"""
        
        logger.info("Reformulating user query")
        
        try:
            # Import here to avoid circular imports
            from ..nlp.reformulator import QueryReformulator
            
            reformulator = QueryReformulator(self.openai_service)
            
            reformulator_input = QueryReformulatorInput(
                user_message=state["user_message"],
                conversation_history=state["conversation_data"].messages[-5:],  # Last 5 messages
                current_slots=state["conversation_data"].slots
            )
            
            # Use the enhanced reformulator with confidence scoring
            reformulated, confidence = await reformulator.reformulate_with_confidence(reformulator_input)
            
            logger.info(f"Query reformulated: {reformulated.intent} (confidence: {confidence:.2f})")
            
            # Update context with reformulation
            await self.context_manager.update_context(
                state["user_id"], 
                state["user_message"], 
                f"[Reformulated: {reformulated.intent}]"
            )
            
            # Return only the updated fields
            updates = {
                "reformulated_query": reformulated
            }
            
            # If the reformulated query suggests clarification is needed, pass that along
            if reformulated.needs_clarification and reformulated.clarification_question:
                updates["needs_clarification"] = True
                updates["clarification_question"] = reformulated.clarification_question
            
            return updates
            
        except Exception as e:
            logger.warning(f"Query reformulation failed: {str(e)}")
            return {
                "reformulated_query": None
            }
    
    async def _fill_slots_node(self, state: AgentStateDict) -> Dict[str, Any]:
        """Fill travel booking slots from reformulated query"""
        
        logger.info("Filling travel slots")
        
        current_slots = state["conversation_data"].slots
        updated = False
        
        if state.get("reformulated_query"):
            query = state["reformulated_query"]
            
            # Update slots with new information
            if query.from_city_name and query.from_city_name != current_slots.from_city:
                current_slots.from_city = query.from_city_name
                updated = True
                
                # Resolve IATA codes
                if query.from_iata_codes:
                    current_slots.from_iata_codes = query.from_iata_codes
                else:
                    iata_codes = await self.iata_resolver.resolve_city_to_iata(query.from_city_name)
                    current_slots.from_iata_codes = iata_codes
                
            if query.to_city_name and query.to_city_name != current_slots.to_city:
                current_slots.to_city = query.to_city_name
                updated = True
                
                # Resolve IATA codes
                if query.to_iata_codes:
                    current_slots.to_iata_codes = query.to_iata_codes
                else:
                    iata_codes = await self.iata_resolver.resolve_city_to_iata(query.to_city_name)
                    current_slots.to_iata_codes = iata_codes
            
            # Handle date information
            if query.date:
                date_type, start_date, end_date = self.date_service.parse_date(query.date)
                if date_type and start_date:
                    current_slots.date = start_date
                    current_slots.date_search_type = date_type
                    if date_type in ["month", "range"]:
                        current_slots.date_range_start = start_date
                        current_slots.date_range_end = end_date
                    updated = True
            
            elif query.date_range:
                date_type, start_date, end_date = self.date_service.parse_date(query.date_range)
                if date_type and start_date:
                    current_slots.date = start_date
                    current_slots.date_search_type = date_type
                    current_slots.date_range_start = start_date
                    current_slots.date_range_end = end_date
                    updated = True
            
            elif query.month:
                date_type, start_date, end_date = self.date_service.parse_date(query.month)
                if date_type and start_date:
                    current_slots.date = start_date
                    current_slots.date_search_type = date_type
                    current_slots.date_range_start = start_date
                    current_slots.date_range_end = end_date
                    updated = True
            
            if query.passengers and query.passengers != current_slots.passengers:
                current_slots.passengers = query.passengers
                updated = True
            
            if query.trip_type and query.trip_type != current_slots.trip_type:
                current_slots.trip_type = query.trip_type
                updated = True
            
            if query.preferred_carrier and query.preferred_carrier != current_slots.preferred_carrier:
                current_slots.preferred_carrier = query.preferred_carrier
                updated = True
        
        # Update conversation state
        updates = {}
        if updated:
            state["conversation_data"].state = ConversationState.COLLECTING_SLOTS
            logger.info("Slots updated from user message")
            updates["conversation_data"] = state["conversation_data"]
        
        return updates
    
    async def _plan_search_node(self, state: AgentStateDict) -> Dict[str, Any]:
        """Determine if we should search and what clarification is needed"""
        
        logger.info("Planning search strategy")
        
        slots = state["conversation_data"].slots
        
        # Check if we have minimum required information
        missing_slots = []
        
        if not slots.from_city or not slots.from_iata_codes:
            missing_slots.append("origin city")
        
        if not slots.to_city or not slots.to_iata_codes:
            missing_slots.append("destination city")
        
        if not slots.date:
            missing_slots.append("travel date")
        
        if slots.trip_type == TripType.ROUND_TRIP and not slots.return_date and slots.date_search_type == "exact":
            missing_slots.append("return date")
        
        if missing_slots:
            clarification_question = f"I need more information about your trip. Please provide: {', '.join(missing_slots)}."
            logger.info(f"Missing slots: {missing_slots}")
            return {
                "needs_clarification": True,
                "clarification_question": clarification_question
            }
        else:
            # Check if search parameters have changed
            current_search_hash = self.travelport_service.get_search_hash(slots)
            
            if current_search_hash != state["conversation_data"].last_completed_search:
                logger.info("Search needed - parameters changed")
                return {
                    "should_search": True
                }
            else:
                logger.info("Using cached search results")
                return {
                    "should_search": False
                }
    
    async def _run_search_node(self, state: AgentStateDict) -> Dict[str, Any]:
        """Execute flight search based on slots"""
        
        logger.info("Running flight search")
        
        try:
            slots = state["conversation_data"].slots
            
            # Route to appropriate search strategy
            if slots.date_search_type == "exact":
                itineraries = await self.search_strategy.search_exact_date(slots)
            elif slots.date_search_type == "month":
                month_year = self.date_service.parse_month_year(f"{slots.date_range_start} {slots.date_range_end}")
                if month_year:
                    month, year = month_year
                    itineraries = await self.search_strategy.search_month(slots, month, year)
                else:
                    raise TazaTicketError("Could not parse month for search")
            elif slots.date_search_type == "range":
                itineraries = await self.search_strategy.search_date_range(
                    slots, 
                    slots.date_range_start, 
                    slots.date_range_end
                )
            else:
                itineraries = await self.search_strategy.search_exact_date(slots)
            
            # Limit results and sort by price
            limited_itineraries = self.search_strategy.get_cheapest_itineraries(itineraries, limit=3)
            
            # Update conversation state
            conversation_data = state["conversation_data"]
            conversation_data.state = ConversationState.PRESENTING_RESULTS
            search_hash = self.travelport_service.get_search_hash(slots)
            conversation_data.last_completed_search = search_hash
            
            logger.info(f"Search completed: {len(limited_itineraries)} results")
            
            return {
                "search_results": limited_itineraries,
                "conversation_data": conversation_data
            }
            
        except Exception as e:
            logger.error(f"Flight search failed: {str(e)}")
            return {
                "search_results": []
            }
    
    async def _generate_clarification_node(self, state: AgentStateDict) -> Dict[str, Any]:
        """Generate clarification question for missing information"""
        
        logger.info("Generating clarification response")
        
        if state.get("clarification_question"):
            response_text = state["clarification_question"]
        else:
            response_text = "I need more information to help you find flights. Could you please provide your origin, destination, and travel date?"
        
        # Use OpenAI to make it more natural and in the right language
        try:
            formatted_response = await self.openai_service.generate_response(
                conversation_history=state["conversation_data"].messages,
                response_content=response_text,
                target_language=state["conversation_data"].language or "en",
                target_modality=state["conversation_data"].last_modality or MessageModality.TEXT
            )
            response_text = formatted_response
        except Exception as e:
            logger.warning(f"Response formatting failed: {str(e)}")
        
        conversation_data = state["conversation_data"]
        conversation_data.state = ConversationState.CLARIFYING
        
        return {
            "response_text": response_text,
            "conversation_data": conversation_data
        }
    
    async def _generate_response_node(self, state: AgentStateDict) -> Dict[str, Any]:
        """Generate final response with search results or other content"""
        
        logger.info("Generating final response")
        
        try:
            conversation_data = state["conversation_data"]
            
            if state.get("search_results"):
                # Format search results
                formatted_results = self.formatter.format_multiple_options(
                    state["search_results"],
                    modality=conversation_data.last_modality or MessageModality.TEXT,
                    max_options=3
                )
                
                # Store itinerary summary
                conversation_data.last_itinerary_summary = formatted_results[:500]  # Truncate for storage
                
            else:
                # No results found
                search_criteria = {
                    "from": conversation_data.slots.from_city,
                    "to": conversation_data.slots.to_city,
                    "date": conversation_data.slots.date,
                    "passengers": str(conversation_data.slots.passengers or 1)
                }
                
                formatted_results = self.formatter.format_no_results(
                    search_criteria,
                    modality=conversation_data.last_modality or MessageModality.TEXT
                )
            
            # Generate natural response using OpenAI
            final_response = await self.openai_service.generate_response(
                conversation_history=conversation_data.messages,
                response_content=formatted_results,
                target_language=conversation_data.language or "en",
                target_modality=conversation_data.last_modality or MessageModality.TEXT
            )
            
            conversation_data.state = ConversationState.PRESENTING_RESULTS
            
            return {
                "response_text": final_response,
                "conversation_data": conversation_data
            }
            
        except Exception as e:
            logger.error(f"Response generation failed: {str(e)}")
            return {
                "response_text": "I apologize, but I encountered an issue while processing your request. Please try again."
            }
    
    async def _summarize_results_node(self, state: AgentStateDict) -> Dict[str, Any]:
        """Summarize search results for presentation"""
        
        logger.info("Summarizing search results")
        
        try:
            if state.get("search_results"):
                # Get the best options
                best_options = self.search_strategy.get_cheapest_itineraries(
                    state["search_results"], 
                    limit=3
                )
                
                # Group by date if we have date range results
                if state["conversation_data"].slots.date_search_type in ["month", "range"]:
                    date_groups = self.search_strategy.group_by_date(state["search_results"])
                    
                    # Find the best date option
                    if date_groups:
                        best_date = min(date_groups.keys(), 
                                      key=lambda date: min(it.price.total for it in date_groups[date]))
                        
                        # Highlight the best date in the results
                        for itinerary in best_options:
                            if hasattr(itinerary, 'search_date') and itinerary.search_date == best_date:
                                itinerary.is_recommended = True
                
                # Create summary text
                summary_parts = []
                if len(best_options) == 1:
                    summary_parts.append("I found the perfect flight for you!")
                else:
                    summary_parts.append(f"I found {len(best_options)} great options for you:")
                
                # Add price range
                if len(best_options) > 1:
                    min_price = min(it.price.total for it in best_options)
                    max_price = max(it.price.total for it in best_options)
                    currency = best_options[0].price.currency
                    
                    if min_price != max_price:
                        summary_parts.append(f"Prices range from {self.formatter.format_price(min_price, currency)} to {self.formatter.format_price(max_price, currency)}")
                    else:
                        summary_parts.append(f"All options are priced at {self.formatter.format_price(min_price, currency)}")
                
                summary_text = " ".join(summary_parts)
                logger.info(f"Generated summary for {len(best_options)} results")
                
                return {
                    "search_results": best_options,
                    "summary_text": summary_text
                }
            
        except Exception as e:
            logger.error(f"Failed to summarize results: {str(e)}")
            return {
                "summary_text": "I found some flight options for you."
            }
        
        return {}
    
    def _get_fallback_response(self, language: str) -> str:
        """Get fallback response for errors"""
        
        fallback_responses = {
            "en": "I apologize, but I'm having technical difficulties. Please try again in a moment.",
            "ur": "معذرت، مجھے تکنیکی مسائل کا سامنا ہے۔ کرپیا ایک لحظے میں دوبارہ کوشش کریں۔",
            "es": "Me disculpo, pero estoy teniendo dificultades técnicas. Por favor, inténtalo de nuevo en un momento.",
            "fr": "Je m'excuse, mais j'ai des difficultés techniques. Veuillez réessayer dans un moment.",
            "de": "Entschuldigung, ich habe technische Schwierigkeiten. Bitte versuchen Sie es in einem Moment erneut.",
            "ar": "أعتذر، لكنني أواجه صعوبات تقنية. يرجى المحاولة مرة أخرى بعد لحظة."
        }
        
        return fallback_responses.get(language, fallback_responses["en"]) 