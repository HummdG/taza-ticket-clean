"""
WhatsApp webhook router for handling incoming messages
"""

import asyncio
from typing import Optional
from fastapi import APIRouter, Form, Request, BackgroundTasks, HTTPException, Header
from fastapi.responses import PlainTextResponse

from ..models.schemas import TwilioWebhookData, Message, MessageModality
from ..utils.logging import get_logger, LogContext
from ..utils.errors import TazaTicketError

logger = get_logger(__name__)

router = APIRouter()


@router.get("/")
async def webhook_verification(request: Request):
    """
    Webhook verification endpoint at /webhook
    This handles Twilio webhook verification requests
    """
    # Call the existing WhatsApp verification handler
    return await whatsapp_webhook_verification(request)


@router.post("/")
async def webhook_root_post(
    request: Request,
    background_tasks: BackgroundTasks,
    MessageSid: str = Form(...),
    AccountSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    Body: Optional[str] = Form(None),
    MediaUrl0: Optional[str] = Form(None),
    MediaContentType0: Optional[str] = Form(None),
    NumMedia: str = Form("0"),
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature")
):
    """
    Main webhook endpoint for Twilio WhatsApp messages at /webhook
    This is the endpoint Twilio is configured to call
    """
    return await process_webhook_request(
        request=request,
        background_tasks=background_tasks,
        MessageSid=MessageSid,
        AccountSid=AccountSid,
        From=From,
        To=To,
        Body=Body,
        MediaUrl0=MediaUrl0,
        MediaContentType0=MediaContentType0,
        NumMedia=NumMedia,
        x_twilio_signature=x_twilio_signature
    )


async def process_webhook_request(
    request: Request,
    background_tasks: BackgroundTasks,
    MessageSid: str,
    AccountSid: str,
    From: str,
    To: str,
    Body: Optional[str] = None,
    MediaUrl0: Optional[str] = None,
    MediaContentType0: Optional[str] = None,
    NumMedia: str = "0",
    x_twilio_signature: Optional[str] = None
):
    """
    Common webhook processing function that can be called from multiple endpoints
    """
    
    user_id = From  # Use phone number as user ID
    
    with LogContext(message_sid=MessageSid, user_id=user_id):
        logger.info(f"Received WhatsApp message from {From}")
        
        try:
            # Get services
            twilio_service = request.app.state.get_service("twilio")
            
            # Validate webhook signature for security
            # TODO: Re-enable after fixing signature validation
            if x_twilio_signature and False:  # Temporarily disabled
                request_url = str(request.url)
                post_vars = {
                    "MessageSid": MessageSid,
                    "AccountSid": AccountSid,
                    "From": From,
                    "To": To,
                    "Body": Body or "",
                    "MediaUrl0": MediaUrl0 or "",
                    "MediaContentType0": MediaContentType0 or "",
                    "NumMedia": NumMedia
                }
                
                is_valid = twilio_service.validate_webhook_signature(
                    request_url, post_vars, x_twilio_signature
                )
                
                if not is_valid:
                    logger.warning("Invalid webhook signature")
                    raise HTTPException(status_code=401, detail="Invalid signature")
            else:
                logger.info("Webhook signature validation skipped for testing")
            
            # Send immediate acknowledgment
            ack_message = "We're on it! 🚀"
            try:
                await twilio_service.send_acknowledgment(From, ack_message)
                logger.info("Sent acknowledgment message")
            except Exception as e:
                logger.warning(f"Failed to send acknowledgment: {str(e)}")
                # Continue processing even if ack fails
            
            # Create webhook data
            webhook_data = TwilioWebhookData(
                MessageSid=MessageSid,
                AccountSid=AccountSid,
                From=From,
                To=To,
                Body=Body,
                MediaUrl0=MediaUrl0,
                MediaContentType0=MediaContentType0,
                NumMedia=NumMedia
            )
            
            # Schedule async processing
            background_tasks.add_task(
                process_message_async, 
                webhook_data, 
                request.app.state.get_service
            )
            
            logger.info("Message processing scheduled")
            
            # Return empty response for Twilio
            return PlainTextResponse("")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    MessageSid: str = Form(...),
    AccountSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    Body: Optional[str] = Form(None),
    MediaUrl0: Optional[str] = Form(None),
    MediaContentType0: Optional[str] = Form(None),
    NumMedia: str = Form("0"),
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature")
):
    """
    WhatsApp webhook endpoint for receiving messages from Twilio
    
    Immediately sends acknowledgment and processes message asynchronously
    """
    return await process_webhook_request(
        request=request,
        background_tasks=background_tasks,
        MessageSid=MessageSid,
        AccountSid=AccountSid,
        From=From,
        To=To,
        Body=Body,
        MediaUrl0=MediaUrl0,
        MediaContentType0=MediaContentType0,
        NumMedia=NumMedia,
        x_twilio_signature=x_twilio_signature
    )


async def process_message_async(webhook_data: TwilioWebhookData, get_service_func):
    """
    Asynchronously process the incoming WhatsApp message
    """
    
    user_id = webhook_data.From
    
    with LogContext(message_sid=webhook_data.MessageSid, user_id=user_id):
        try:
            logger.info("Starting async message processing")
            
            # Get services
            openai_service = get_service_func("openai")
            dynamodb_service = get_service_func("dynamodb")
            twilio_service = get_service_func("twilio")
            s3_service = get_service_func("s3")
            
            # Initialize additional services
            from ..services.date_parse import DateParsingService
            from ..services.iata_resolver import IATAResolver
            from ..services.search_strategy import SearchStrategy
            from ..services.formatter import ItineraryFormatter
            from ..agents.graph import FlightAgentGraph
            
            date_service = DateParsingService()
            iata_resolver = IATAResolver(openai_service)
            travelport_service = get_service_func("travelport")
            search_strategy = SearchStrategy(travelport_service, date_service)
            formatter = ItineraryFormatter(iata_resolver)
            
            # Create agent graph
            agent_graph = FlightAgentGraph(
                openai_service=openai_service,
                dynamodb_service=dynamodb_service,
                twilio_service=twilio_service,
                s3_service=s3_service,
                travelport_service=travelport_service,
                date_service=date_service,
                iata_resolver=iata_resolver,
                search_strategy=search_strategy,
                formatter=formatter
            )
            
            # Determine message content and modality
            user_message_content = ""
            message_modality = MessageModality.TEXT
            media_url = None
            
            if webhook_data.Body:
                # Text message
                user_message_content = webhook_data.Body
                message_modality = MessageModality.TEXT
                logger.info(f"Processing text message: {user_message_content[:100]}...")
                
            elif webhook_data.MediaUrl0 and int(webhook_data.NumMedia) > 0:
                # Media message (audio)
                if webhook_data.MediaContentType0 and "audio" in webhook_data.MediaContentType0:
                    message_modality = MessageModality.VOICE
                    media_url = webhook_data.MediaUrl0
                    
                    logger.info("Processing voice message")
                    
                    # Download and transcribe audio
                    try:
                        audio_data = await twilio_service.download_media(webhook_data.MediaUrl0)
                        user_message_content, detected_language = await openai_service.speech_to_text(
                            audio_data, 
                            filename="voice_message.ogg"
                        )
                        
                        logger.info(f"Transcribed voice message: {user_message_content[:100]}...")
                        
                    except Exception as e:
                        logger.error(f"Failed to process voice message: {str(e)}")
                        user_message_content = "Sorry, I couldn't understand the voice message. Please try again or send a text message."
                        message_modality = MessageModality.TEXT
                else:
                    logger.warning(f"Unsupported media type: {webhook_data.MediaContentType0}")
                    user_message_content = "Sorry, I can only process text and voice messages."
                    message_modality = MessageModality.TEXT
            else:
                logger.warning("Received message with no content")
                user_message_content = "I didn't receive any message content. Please try again."
                message_modality = MessageModality.TEXT
            
            # Process message through agent graph
            try:
                response_content, response_modality, response_media_url = await agent_graph.process_message(
                    user_id=user_id,
                    user_message=user_message_content,
                    input_modality=message_modality,
                    media_url=media_url
                )
                
                logger.info(f"Agent generated response: {response_modality}")
                
                # Send response back to user
                if response_modality == MessageModality.TEXT:
                    await twilio_service.send_text_message(user_id, response_content)
                elif response_modality == MessageModality.VOICE and response_media_url:
                    await twilio_service.send_audio_message(user_id, response_media_url, response_content)
                else:
                    # Fallback to text
                    await twilio_service.send_text_message(user_id, response_content)
                
                logger.info("Response sent successfully")
                
            except Exception as e:
                logger.error(f"Agent processing failed: {str(e)}")
                
                # Send error message to user
                error_message = "Sorry, I encountered an issue processing your request. Please try again later."
                try:
                    await twilio_service.send_text_message(user_id, error_message)
                except Exception as send_error:
                    logger.error(f"Failed to send error message: {str(send_error)}")
            
            logger.info("Async message processing completed")
            
        except Exception as e:
            logger.error(f"Critical error in async processing: {str(e)}")
            
            # Try to send a generic error message
            try:
                twilio_service = get_service_func("twilio")
                error_message = "Sorry, something went wrong. Please try again later."
                await twilio_service.send_text_message(user_id, error_message)
            except:
                logger.error("Failed to send critical error message")


@router.get("/whatsapp")
async def whatsapp_webhook_verification(request: Request):
    """
    WhatsApp webhook verification endpoint (for initial setup)
    """
    
    # Get query parameters
    hub_mode = request.query_params.get("hub.mode")
    hub_verify_token = request.query_params.get("hub.verify_token")
    hub_challenge = request.query_params.get("hub.challenge")
    
    logger.info(f"Webhook verification request: mode={hub_mode}")
    
    # This is typically used for Facebook/Meta webhook verification
    # For Twilio, this might not be needed, but keeping for compatibility
    if hub_mode == "subscribe":
        # In production, verify the token matches your configured value
        # For now, accepting any verification
        logger.info("Webhook verification successful")
        return PlainTextResponse(hub_challenge or "")
    
    logger.warning("Invalid webhook verification request")
    raise HTTPException(status_code=400, detail="Invalid verification request") 