"""
LangChain memory integration for conversation history management
"""

from typing import List, Dict, Any, Optional
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import BaseMessage, HumanMessage, AIMessage

from ..models.schemas import Message, ConversationData, MessageModality
from ..integrations.dynamodb import DynamoDBRepository
from ..utils.logging import get_logger

logger = get_logger(__name__)


class ConversationMemory:
	"""LangChain memory wrapper for DynamoDB-backed conversation history"""
	
	def __init__(self, dynamodb_repo: DynamoDBRepository, window_size: int = 10):
		self.dynamodb_repo = dynamodb_repo
		self.window_size = window_size
		self._memory_cache: Dict[str, ConversationBufferWindowMemory] = {}
		# Track how many messages since last persist/summary per user
		self._pending_counts: Dict[str, int] = {}
		# Cache full conversation objects to avoid DB reads each request
		self._conversation_cache: Dict[str, ConversationData] = {}
	
	async def get_or_create_conversation(self, user_id: str) -> ConversationData:
		"""Return cached ConversationData or initialize from DB/empty."""
		if user_id in self._conversation_cache:
			return self._conversation_cache[user_id]
		
		conversation_data = await self.dynamodb_repo.get_conversation(user_id)
		if not conversation_data:
			from ..models.schemas import Slots, ConversationState
			conversation_data = ConversationData(
				user_id=user_id,
				slots=Slots(),
				messages=[],
				state=ConversationState.INITIAL
			)
		self._conversation_cache[user_id] = conversation_data
		return conversation_data
	
	def set_conversation(self, conversation_data: ConversationData) -> None:
		"""Update cached ConversationData for user."""
		self._conversation_cache[conversation_data.user_id] = conversation_data
	
	async def get_memory(self, user_id: str) -> ConversationBufferWindowMemory:
		"""Get or create LangChain memory for user"""
		
		if user_id not in self._memory_cache:
			# Create new memory instance
			memory = ConversationBufferWindowMemory(
				k=self.window_size,
				return_messages=True,
				memory_key="chat_history"
			)
			# Initialize counter
			self._pending_counts[user_id] = 0
			
			# Prefer cached conversation to seed memory
			conversation_data: Optional[ConversationData] = self._conversation_cache.get(user_id)
			if conversation_data is None:
				try:
					conversation_data = await self.dynamodb_repo.get_conversation(user_id)
				except Exception as e:
					logger.warning(f"Failed to load conversation history for {user_id}: {str(e)}")
			
			if conversation_data and conversation_data.messages:
				# If a summary exists, seed memory with it as an assistant message
				if getattr(conversation_data, "conversation_summary", None):
					memory.chat_memory.add_ai_message(f"[Summary] {conversation_data.conversation_summary}")
				# Convert our messages to LangChain format (only recent window)
				langchain_messages = self._convert_to_langchain_messages(
					conversation_data.messages[-self.window_size:]
				)
				# Add messages to memory
				for message in langchain_messages:
					if isinstance(message, HumanMessage):
						memory.chat_memory.add_user_message(message.content)
					elif isinstance(message, AIMessage):
						memory.chat_memory.add_ai_message(message.content)
				logger.info(f"Loaded {len(langchain_messages)} messages into memory for user {user_id}")
			
			self._memory_cache[user_id] = memory
		
		return self._memory_cache[user_id]
	
	def _convert_to_langchain_messages(self, messages: List[Message]) -> List[BaseMessage]:
		"""Convert our Message objects to LangChain format"""
		
		langchain_messages = []
		
		for msg in messages:
			if msg.role == "user":
				langchain_messages.append(HumanMessage(content=msg.content))
			elif msg.role == "assistant":
				langchain_messages.append(AIMessage(content=msg.content))
		
		return langchain_messages
	
	async def add_user_message(self, user_id: str, message: str) -> None:
		"""Add user message to memory"""
		
		memory = await self.get_memory(user_id)
		memory.chat_memory.add_user_message(message)
		self._pending_counts[user_id] = self._pending_counts.get(user_id, 0) + 1
		logger.debug(f"Added user message to memory for {user_id}")
	
	async def add_ai_message(self, user_id: str, message: str) -> None:
		"""Add AI message to memory"""
		
		memory = await self.get_memory(user_id)
		memory.chat_memory.add_ai_message(message)
		self._pending_counts[user_id] = self._pending_counts.get(user_id, 0) + 1
		logger.debug(f"Added AI message to memory for {user_id}")
	
	async def flush_and_summarize_if_needed(self, user_id: str, summarizer: "ConversationSummarizer") -> Optional[str]:
		"""If 10 messages accumulated in memory, summarize older context and persist to DynamoDB.
		Returns summary text if created."""
		
		# Only flush when threshold met
		if self._pending_counts.get(user_id, 0) < self.window_size:
			return None
		
		# Reset counter first to avoid duplicate flushes on concurrent calls
		self._pending_counts[user_id] = 0
		
		# Build Message list from memory to summarize
		memory = await self.get_memory(user_id)
		messages_texts: List[BaseMessage] = memory.chat_memory.messages
		
		# Convert LangChain messages back to our Message model
		converted: List[Message] = []
		for m in messages_texts:
			if isinstance(m, HumanMessage):
				converted.append(Message(role="user", content=m.content, modality=MessageModality.TEXT))
			elif isinstance(m, AIMessage):
				converted.append(Message(role="assistant", content=m.content, modality=MessageModality.TEXT))
		
		# Retrieve full conversation to keep slots/state, but we will not append every message
		conversation_data = await self.dynamodb_repo.get_conversation(user_id)
		if not conversation_data:
			from ..models.schemas import Slots, ConversationState
			conversation_data = ConversationData(user_id=user_id, slots=Slots(), messages=[], state=ConversationState.INITIAL)
		
		# Create/update summary from the converted memory messages
		summary_text = await summarizer.summarize_conversation(converted)
		if not summary_text:
			return None
		
		conversation_data.conversation_summary = summary_text
		# Reset stored messages to only keep the last small window for continuity
		conversation_data.messages = converted[-4:]
		
		# Persist a compact record
		await self.dynamodb_repo.save_conversation(conversation_data)
		logger.info(f"Persisted summarized conversation for user {user_id}")
		return summary_text
	
	async def get_chat_history(self, user_id: str) -> List[BaseMessage]:
		"""Get chat history as LangChain messages"""
		
		memory = await self.get_memory(user_id)
		return memory.chat_memory.messages
	
	async def get_conversation_context(self, user_id: str) -> str:
		"""Get conversation context as formatted string"""
		
		messages = await self.get_chat_history(user_id)
		
		if not messages:
			return "No previous conversation"
		
		context_lines = []
		for msg in messages[-6:]:  # Last 6 messages for context
			role = "Human" if isinstance(msg, HumanMessage) else "Assistant"
			context_lines.append(f"{role}: {msg.content}")
		
		return "\n".join(context_lines)
	
	async def clear_memory(self, user_id: str) -> None:
		"""Clear memory for user"""
		
		if user_id in self._memory_cache:
			self._memory_cache[user_id].clear()
			del self._memory_cache[user_id]
			logger.info(f"Cleared memory for user {user_id}")
	
	async def get_memory_variables(self, user_id: str) -> Dict[str, Any]:
		"""Get memory variables for use in prompts"""
		
		memory = await self.get_memory(user_id)
		return memory.load_memory_variables({})
	
	def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
		"""Get memory statistics"""
		
		if user_id not in self._memory_cache:
			return {"message_count": 0, "memory_loaded": False}
		
		memory = self._memory_cache[user_id]
		return {
			"message_count": len(memory.chat_memory.messages),
			"memory_loaded": True,
			"window_size": self.window_size
		}


class ConversationSummarizer:
	"""Summarizes long conversations to maintain context while reducing token usage"""
	
	def __init__(self, openai_service, max_messages: int = 20):
		self.openai_service = openai_service
		self.max_messages = max_messages
	
	async def should_summarize(self, messages: List[Message]) -> bool:
		"""Determine if conversation should be summarized"""
		return len(messages) > self.max_messages
	
	async def summarize_conversation(self, messages: List[Message]) -> str:
		"""Create a summary of the conversation"""
		
		if len(messages) <= 4:
			return ""
		
		# Take messages excluding the last 4 (keep recent context)
		messages_to_summarize = messages[:-4]
		
		conversation_text = []
		for msg in messages_to_summarize:
			role = "User" if msg.role == "user" else "Assistant"
			conversation_text.append(f"{role}: {msg.content}")
		
		conversation_str = "\n".join(conversation_text)
		
		try:
			summary_prompt = f"""Please summarize this conversation between a user and a travel booking assistant. Focus on:
1. Travel preferences and requirements mentioned
2. Searches performed and results discussed
3. Any booking decisions or preferences
4. Important context for future interactions

Conversation:
{conversation_str}

Summary:"""
			
			summary = await self.openai_service.chat_completion(
				messages=[{"role": "user", "content": summary_prompt}],
				model="gpt-4o-mini",
				temperature=0.3,
				max_tokens=200
			)
			
			logger.info("Generated conversation summary")
			return summary
			
		except Exception as e:
			logger.error(f"Failed to summarize conversation: {str(e)}")
			return "Previous conversation context available."
	
	async def create_summarized_history(self, messages: List[Message]) -> List[Message]:
		"""Create a summarized version of conversation history"""
		
		if not await self.should_summarize(messages):
			return messages
		
		# Create summary of older messages
		summary = await self.summarize_conversation(messages)
		
		if summary:
			# Create a summary message
			summary_message = Message(
				role="assistant",
				content=f"[Conversation Summary: {summary}]",
				modality=MessageModality.TEXT,
				language="en"
			)
			
			# Return summary + recent messages
			recent_messages = messages[-4:]
			return [summary_message] + recent_messages
		
		return messages


class ContextManager:
	"""Manages conversation context for the agent"""
	
	def __init__(self, memory: ConversationMemory, summarizer: ConversationSummarizer):
		self.memory = memory
		self.summarizer = summarizer
	
	async def get_context_for_prompt(self, user_id: str, include_summary: bool = True) -> Dict[str, str]:
		"""Get formatted context for use in prompts"""
		
		try:
			# Get recent conversation
			conversation_context = await self.memory.get_conversation_context(user_id)
			
			# Get conversation data for summary if needed
			context = {
				"recent_conversation": conversation_context,
				"summary": ""
			}
			
			if include_summary:
				# This would integrate with the summarizer if we have long conversations
				context["summary"] = "No previous summary available."
			
			return context
			
		except Exception as e:
			logger.error(f"Failed to get context for user {user_id}: {str(e)}")
			return {
				"recent_conversation": "No conversation history available",
				"summary": ""
			}
	
	async def update_context(self, user_id: str, user_message: str, ai_response: str) -> None:
		"""Update conversation context with new messages"""
		
		try:
			await self.memory.add_user_message(user_id, user_message)
			await self.memory.add_ai_message(user_id, ai_response)
			
		except Exception as e:
			logger.error(f"Failed to update context for user {user_id}: {str(e)}")
	
	async def reset_context(self, user_id: str) -> None:
		"""Reset conversation context for user"""
		
		await self.memory.clear_memory(user_id)
		logger.info(f"Reset conversation context for user {user_id}") 