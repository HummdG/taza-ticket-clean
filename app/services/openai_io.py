"""
OpenAI integration service for chat completions, STT, and TTS
"""

import asyncio
import io
from typing import List, Optional, Dict, Any, Tuple
import httpx
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..config import settings
from ..models.schemas import Message, MessageModality, QueryReformulatorInput, QueryReformulatorOutput
from ..utils.errors import OpenAIError, RateLimitError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class OpenAIService:
    """OpenAI service for chat, STT, and TTS operations"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.RequestError, OpenAIError))
    )
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate chat completion using OpenAI
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: OpenAI model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            response_format: Response format specification
            
        Returns:
            Generated response text
        """
        
        try:
            logger.info(f"Generating chat completion with model {model}")
            
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature
            }
            
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            
            if response_format:
                kwargs["response_format"] = response_format
            
            response = await self.client.chat.completions.create(**kwargs)
            
            content = response.choices[0].message.content
            logger.info(f"Generated response: {len(content)} characters")
            
            return content
            
        except Exception as e:
            if "rate_limit" in str(e).lower():
                raise RateLimitError("OpenAI rate limit exceeded", service="openai")
            
            error_msg = f"OpenAI chat completion failed: {str(e)}"
            logger.error(error_msg)
            raise OpenAIError(error_msg)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.RequestError, OpenAIError))
    )
    async def speech_to_text(
        self,
        audio_data: bytes,
        filename: str = "audio.ogg",
        language: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Convert speech to text using OpenAI Whisper
        
        Args:
            audio_data: Audio file bytes
            filename: Filename for the audio (for format detection)
            language: Optional language hint
            
        Returns:
            Tuple of (transcribed_text, detected_language)
        """
        
        try:
            logger.info(f"Transcribing audio: {len(audio_data)} bytes")
            
            # Create file-like object for OpenAI API
            audio_file = io.BytesIO(audio_data)
            audio_file.name = filename
            
            kwargs = {
                "file": audio_file,
                "model": "whisper-1",
                "response_format": "json"
            }
            
            if language:
                kwargs["language"] = language
            
            response = await self.client.audio.transcriptions.create(**kwargs)
            
            transcribed_text = response.text
            detected_language = getattr(response, 'language', None)
            
            logger.info(f"Transcribed text: {len(transcribed_text)} characters, language: {detected_language}")
            
            return transcribed_text, detected_language
            
        except Exception as e:
            if "rate_limit" in str(e).lower():
                raise RateLimitError("OpenAI rate limit exceeded", service="openai")
            
            error_msg = f"OpenAI speech-to-text failed: {str(e)}"
            logger.error(error_msg)
            raise OpenAIError(error_msg)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.RequestError, OpenAIError))
    )
    async def text_to_speech(
        self,
        text: str,
        voice: str = "alloy",
        model: str = "tts-1",
        response_format: str = "mp3"
    ) -> bytes:
        """
        Convert text to speech using OpenAI TTS
        
        Args:
            text: Text to convert to speech
            voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer)
            model: TTS model to use
            response_format: Audio format (mp3, opus, aac, flac)
            
        Returns:
            Audio data as bytes
        """
        
        try:
            logger.info(f"Converting text to speech: {len(text)} characters, voice: {voice}")
            
            response = await self.client.audio.speech.create(
                model=model,
                voice=voice,
                input=text,
                response_format=response_format
            )
            
            audio_data = await response.aread()
            logger.info(f"Generated audio: {len(audio_data)} bytes")
            
            return audio_data
            
        except Exception as e:
            if "rate_limit" in str(e).lower():
                raise RateLimitError("OpenAI rate limit exceeded", service="openai")
            
            error_msg = f"OpenAI text-to-speech failed: {str(e)}"
            logger.error(error_msg)
            raise OpenAIError(error_msg)
    
    async def detect_language(self, text: str) -> Optional[str]:
        """
        Detect language of text using OpenAI
        
        Args:
            text: Text to analyze
            
        Returns:
            Detected language code (e.g., 'en', 'ur', 'es') or None
        """
        
        if not text.strip():
            return None
        
        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are a language detection expert. Respond with only the ISO 639-1 language code (e.g., 'en' for English, 'ur' for Urdu, 'es' for Spanish) for the given text. If unsure, respond with 'en'."
                },
                {
                    "role": "user",
                    "content": f"Detect the language of this text: {text[:200]}"
                }
            ]
            
            response = await self.chat_completion(
                messages=messages,
                model="gpt-4o-mini",
                temperature=0.1,
                max_tokens=10
            )
            
            # Extract just the language code
            language = response.strip().lower()[:2]
            logger.info(f"Detected language: {language}")
            
            return language
            
        except Exception as e:
            logger.warning(f"Language detection failed: {str(e)}, defaulting to 'en'")
            return "en"
    
    async def reformulate_query(self, input_data: QueryReformulatorInput) -> QueryReformulatorOutput:
        """
        Reformulate user query to extract clean travel intent
        
        Args:
            input_data: Input containing user message, history, and current slots
            
        Returns:
            Reformulated query output with extracted travel information
        """
        
        # Import here to avoid circular imports
        from ..nlp.reformulator import QueryReformulator
        
        try:
            reformulator = QueryReformulator(self)
            return await reformulator.reformulate_query(input_data)
            
        except Exception as e:
            logger.error(f"Query reformulation failed: {str(e)}")
            # Return basic output with clarification needed
            return QueryReformulatorOutput(
                needs_clarification=True,
                clarification_question="I need more information about your travel plans. Could you please provide the origin, destination, and travel date?"
            )
    
    async def generate_response(
        self,
        conversation_history: List[Message],
        response_content: str,
        target_language: str = "en",
        target_modality: MessageModality = MessageModality.TEXT
    ) -> str:
        """
        Generate a natural response in the target language and style
        
        Args:
            conversation_history: Recent conversation messages
            response_content: Core content to communicate
            target_language: Target language code
            target_modality: Target modality (affects style)
            
        Returns:
            Formatted response text
        """
        
        try:
            # Build conversation context
            recent_messages = conversation_history[-3:]  # Last 3 messages
            context = []
            for msg in recent_messages:
                context.append(f"{msg.role}: {msg.content}")
            
            context_str = "\n".join(context) if context else "New conversation"
            
            # Determine response style based on modality
            style_instruction = {
                MessageModality.TEXT: "Format as a clear, well-structured text message with proper sections and bullet points where helpful.",
                MessageModality.VOICE: "Format as natural, conversational speech. Keep it concise and easy to understand when spoken aloud. Use simple sentences."
            }[target_modality]
            
            # Language instruction
            language_names = {
                "en": "English",
                "ur": "Urdu", 
                "es": "Spanish",
                "fr": "French",
                "de": "German",
                "ar": "Arabic",
                "hi": "Hindi"
            }
            
            language_name = language_names.get(target_language, "English")
            
            system_prompt = f"""You are a helpful travel booking assistant. Respond in {language_name} language.

{style_instruction}

Be friendly, professional, and helpful. If providing flight information, include all relevant details clearly."""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"""
Recent conversation:
{context_str}

Please format this response content appropriately:
{response_content}
"""}
            ]
            
            response = await self.chat_completion(
                messages=messages,
                model="gpt-4o",
                temperature=0.7
            )
            
            logger.info(f"Generated {target_modality} response in {target_language}: {len(response)} characters")
            return response
            
        except Exception as e:
            logger.error(f"Response generation failed: {str(e)}")
            # Fallback to original content
            return response_content 