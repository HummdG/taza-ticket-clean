"""
Twilio client for WhatsApp messaging
"""

import asyncio
from typing import Optional
import httpx
from twilio.rest import Client
from twilio.base.exceptions import TwilioException

from ..config import settings
from ..models.schemas import MessageModality
from ..utils.errors import TwilioError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class TwilioClient:
    """Twilio client for sending WhatsApp messages"""
    
    def __init__(self):
        self.client = Client(
            settings.twilio_account_sid,
            settings.twilio_auth_token
        )
        self.from_number = settings.twilio_whatsapp_from
    
    async def send_text_message(
        self,
        to_number: str,
        message_body: str
    ) -> str:
        """
        Send a text message via WhatsApp
        
        Args:
            to_number: Recipient WhatsApp number (e.g., "whatsapp:+1234567890")
            message_body: Text message content
            
        Returns:
            Twilio message SID
        """
        
        try:
            logger.info(f"Sending WhatsApp text message to {to_number}")
            
            # Ensure proper WhatsApp formatting
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"
            
            # Send message using Twilio client
            message = self.client.messages.create(
                body=message_body,
                from_=self.from_number,
                to=to_number
            )
            
            logger.info(f"Successfully sent WhatsApp text message: {message.sid}")
            
            return message.sid
            
        except TwilioException as e:
            error_msg = f"Twilio API error sending text message: {str(e)}"
            logger.error(error_msg)
            raise TwilioError(error_msg, error_code=getattr(e, 'code', None))
        except Exception as e:
            error_msg = f"Unexpected error sending text message: {str(e)}"
            logger.error(error_msg)
            raise TwilioError(error_msg)
    
    async def send_audio_message(
        self,
        to_number: str,
        audio_url: str,
        caption: Optional[str] = None
    ) -> str:
        """
        Send an audio message via WhatsApp
        
        Args:
            to_number: Recipient WhatsApp number (e.g., "whatsapp:+1234567890")
            audio_url: Public URL of the audio file
            caption: Optional caption for the audio message
            
        Returns:
            Twilio message SID
        """
        
        try:
            logger.info(f"Sending WhatsApp audio message to {to_number}")
            
            # Ensure proper WhatsApp formatting
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"
            
            # Prepare message parameters
            message_params = {
                'from_': self.from_number,
                'to': to_number,
                'media_url': [audio_url]
            }
            
            # Add caption if provided
            if caption:
                message_params['body'] = caption
            
            # Send message using Twilio client
            message = self.client.messages.create(**message_params)
            
            logger.info(f"Successfully sent WhatsApp audio message: {message.sid}")
            
            return message.sid
            
        except TwilioException as e:
            error_msg = f"Twilio API error sending audio message: {str(e)}"
            logger.error(error_msg)
            raise TwilioError(error_msg, error_code=getattr(e, 'code', None))
        except Exception as e:
            error_msg = f"Unexpected error sending audio message: {str(e)}"
            logger.error(error_msg)
            raise TwilioError(error_msg)
    
    async def send_message(
        self,
        to_number: str,
        content: str,
        modality: MessageModality = MessageModality.TEXT,
        media_url: Optional[str] = None
    ) -> str:
        """
        Send a message via WhatsApp (text or audio)
        
        Args:
            to_number: Recipient WhatsApp number
            content: Message content (text or caption for audio)
            modality: Message modality (TEXT or VOICE)
            media_url: URL of media file for audio messages
            
        Returns:
            Twilio message SID
        """
        
        if modality == MessageModality.TEXT:
            return await self.send_text_message(to_number, content)
        elif modality == MessageModality.VOICE:
            if not media_url:
                raise TwilioError("Media URL required for voice messages")
            return await self.send_audio_message(to_number, media_url, content)
        else:
            raise TwilioError(f"Unsupported message modality: {modality}")
    
    async def download_media(self, media_url: str) -> bytes:
        """
        Download media file from Twilio
        
        Args:
            media_url: Twilio media URL
            
        Returns:
            Media file bytes
        """
        
        try:
            logger.info(f"Downloading media from Twilio: {media_url}")
            
            # Use httpx for async HTTP request with redirect following
            async with httpx.AsyncClient(follow_redirects=True) as client:
                # Add Twilio authentication
                auth = (settings.twilio_account_sid, settings.twilio_auth_token)
                
                response = await client.get(media_url, auth=auth)
                response.raise_for_status()
                
                media_data = response.content
                
                logger.info(f"Successfully downloaded media: {len(media_data)} bytes")
                
                return media_data
                
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error downloading media: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise TwilioError(error_msg)
        except httpx.RequestError as e:
            error_msg = f"Request error downloading media: {str(e)}"
            logger.error(error_msg)
            raise TwilioError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error downloading media: {str(e)}"
            logger.error(error_msg)
            raise TwilioError(error_msg)
    
    async def get_message_status(self, message_sid: str) -> dict:
        """
        Get message delivery status
        
        Args:
            message_sid: Twilio message SID
            
        Returns:
            Message status information
        """
        
        try:
            logger.info(f"Getting message status: {message_sid}")
            
            message = self.client.messages(message_sid).fetch()
            
            status_info = {
                'sid': message.sid,
                'status': message.status,
                'error_code': message.error_code,
                'error_message': message.error_message,
                'date_created': message.date_created,
                'date_updated': message.date_updated,
                'date_sent': message.date_sent
            }
            
            logger.info(f"Message status: {status_info['status']}")
            
            return status_info
            
        except TwilioException as e:
            error_msg = f"Twilio API error getting message status: {str(e)}"
            logger.error(error_msg)
            raise TwilioError(error_msg, error_code=getattr(e, 'code', None))
        except Exception as e:
            error_msg = f"Unexpected error getting message status: {str(e)}"
            logger.error(error_msg)
            raise TwilioError(error_msg)
    
    async def send_acknowledgment(
        self,
        to_number: str,
        ack_message: str = "We're on it! 🚀"
    ) -> str:
        """
        Send immediate acknowledgment message
        
        Args:
            to_number: Recipient WhatsApp number
            ack_message: Acknowledgment message text
            
        Returns:
            Twilio message SID
        """
        
        return await self.send_text_message(to_number, ack_message)
    
    def validate_webhook_signature(
        self,
        request_url: str,
        post_vars: dict,
        signature: str
    ) -> bool:
        """
        Validate Twilio webhook signature for security
        
        Args:
            request_url: The full URL of the webhook request
            post_vars: Dictionary of POST variables
            signature: The signature from the X-Twilio-Signature header
            
        Returns:
            True if signature is valid, False otherwise
        """
        
        try:
            from twilio.request_validator import RequestValidator
            
            validator = RequestValidator(settings.twilio_auth_token)
            
            is_valid = validator.validate(request_url, post_vars, signature)
            
            if is_valid:
                logger.info("Twilio webhook signature validation passed")
            else:
                logger.warning("Twilio webhook signature validation failed")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Error validating webhook signature: {str(e)}")
            return False
    
    async def health_check(self) -> bool:
        """
        Perform a health check on the Twilio connection
        
        Returns:
            True if healthy, False otherwise
        """
        
        try:
            # Simple account fetch to test connectivity
            account = self.client.api.accounts(settings.twilio_account_sid).fetch()
            
            logger.info(f"Twilio health check passed: {account.friendly_name}")
            return True
            
        except Exception as e:
            logger.error(f"Twilio health check failed: {str(e)}")
            return False 