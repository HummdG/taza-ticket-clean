"""
Main FastAPI application for TazaTicket flight agent
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Form, Header
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .utils.logging import setup_logging, get_logger
from .routers import webhook
from .services.travelport import TravelportService
from .services.openai_io import OpenAIService
from .services.twilio_client import TwilioClient
from .services.s3_media import S3MediaService
from .integrations.dynamodb import DynamoDBRepository

# Setup logging
setup_logging(settings.log_level)
logger = get_logger(__name__)

# Global service instances
services = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    
    logger.info("Starting TazaTicket Flight Agent application")
    
    # Initialize services
    try:
        services["openai"] = OpenAIService()
        services["travelport"] = TravelportService()
        services["twilio"] = TwilioClient()
        services["s3"] = S3MediaService()
        services["dynamodb"] = DynamoDBRepository()
        
        logger.info("All services initialized successfully")
        
        # Perform initial health checks
        await perform_startup_health_checks()
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {str(e)}")
        raise
    
    yield
    
    # Cleanup
    logger.info("Shutting down TazaTicket Flight Agent application")
    
    # Close async services
    if "travelport" in services:
        try:
            await services["travelport"].__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing Travelport service: {str(e)}")


async def perform_startup_health_checks():
    """Perform health checks on startup"""
    
    logger.info("Performing startup health checks...")
    
    # Check DynamoDB
    try:
        dynamodb_healthy = await services["dynamodb"].health_check()
        if dynamodb_healthy:
            logger.info("✅ DynamoDB connection healthy")
        else:
            logger.warning("⚠️  DynamoDB connection unhealthy")
    except Exception as e:
        logger.warning(f"⚠️  DynamoDB health check failed: {str(e)}")
    
    # Check S3
    try:
        s3_healthy = await services["s3"].health_check()
        if s3_healthy:
            logger.info("✅ S3 connection healthy")
        else:
            logger.warning("⚠️  S3 connection unhealthy")
    except Exception as e:
        logger.warning(f"⚠️  S3 health check failed: {str(e)}")
    
    # Check Twilio
    try:
        twilio_healthy = await services["twilio"].health_check()
        if twilio_healthy:
            logger.info("✅ Twilio connection healthy")
        else:
            logger.warning("⚠️  Twilio connection unhealthy")
    except Exception as e:
        logger.warning(f"⚠️  Twilio health check failed: {str(e)}")
    
    logger.info("Startup health checks completed")


# Create FastAPI app
app = FastAPI(
    title="TazaTicket Flight Agent",
    description="Production-ready FastAPI + LangGraph flight agent with multilingual WhatsApp support",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhook.router, prefix="/webhook", tags=["webhook"])

# Add a direct route for webhook to avoid redirects
@app.post("/webhook")
async def webhook_direct(
    request: Request,
    background_tasks: BackgroundTasks,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature")
):
    """
    Direct webhook endpoint to avoid redirects that break signature validation
    Accepts all form data to handle various Twilio webhook formats
    """
    from .routers.webhook import process_webhook_request_flexible
    return await process_webhook_request_flexible(
        request=request,
        background_tasks=background_tasks,
        x_twilio_signature=x_twilio_signature
    )

@app.get("/webhook")
async def webhook_verification_direct(request: Request):
    """
    Direct webhook verification endpoint
    """
    from .routers.webhook import whatsapp_webhook_verification
    return await whatsapp_webhook_verification(request)


@app.get("/healthz")
async def health_check():
    """Liveness probe endpoint"""
    
    return {
        "status": "healthy",
        "service": "taza-ticket-flight-agent",
        "version": "1.0.0",
        "timestamp": asyncio.get_event_loop().time()
    }


@app.get("/readiness")
async def readiness_check():
    """Readiness probe endpoint with dependency checks"""
    
    checks = {
        "status": "ready",
        "service": "taza-ticket-flight-agent",
        "version": "1.0.0",
        "checks": {}
    }
    
    all_healthy = True
    
    # Check DynamoDB
    try:
        if "dynamodb" in services:
            dynamodb_healthy = await services["dynamodb"].health_check()
            checks["checks"]["dynamodb"] = "healthy" if dynamodb_healthy else "unhealthy"
            if not dynamodb_healthy:
                all_healthy = False
        else:
            checks["checks"]["dynamodb"] = "not_initialized"
            all_healthy = False
    except Exception as e:
        checks["checks"]["dynamodb"] = f"error: {str(e)}"
        all_healthy = False
    
    # Check S3
    try:
        if "s3" in services:
            s3_healthy = await services["s3"].health_check()
            checks["checks"]["s3"] = "healthy" if s3_healthy else "unhealthy"
            if not s3_healthy:
                all_healthy = False
        else:
            checks["checks"]["s3"] = "not_initialized"
            all_healthy = False
    except Exception as e:
        checks["checks"]["s3"] = f"error: {str(e)}"
        all_healthy = False
    
    # Check Twilio
    try:
        if "twilio" in services:
            twilio_healthy = await services["twilio"].health_check()
            checks["checks"]["twilio"] = "healthy" if twilio_healthy else "unhealthy"
            if not twilio_healthy:
                all_healthy = False
        else:
            checks["checks"]["twilio"] = "not_initialized"
            all_healthy = False
    except Exception as e:
        checks["checks"]["twilio"] = f"error: {str(e)}"
        all_healthy = False
    
    # Check Travelport (basic connectivity)
    try:
        if "travelport" in services:
            # Simple check - try to get a token
            await services["travelport"]._ensure_valid_token()
            checks["checks"]["travelport"] = "healthy"
        else:
            checks["checks"]["travelport"] = "not_initialized"
            all_healthy = False
    except Exception as e:
        checks["checks"]["travelport"] = f"error: {str(e)}"
        all_healthy = False
    
    # Check OpenAI (basic check)
    try:
        if "openai" in services:
            # Simple language detection test
            test_result = await services["openai"].detect_language("hello")
            checks["checks"]["openai"] = "healthy" if test_result else "unhealthy"
            if not test_result:
                all_healthy = False
        else:
            checks["checks"]["openai"] = "not_initialized"
            all_healthy = False
    except Exception as e:
        checks["checks"]["openai"] = f"error: {str(e)}"
        all_healthy = False
    
    if not all_healthy:
        checks["status"] = "degraded"
        raise HTTPException(status_code=503, detail=checks)
    
    return checks


@app.get("/")
async def root():
    """Root endpoint with basic service info"""
    
    return {
        "service": "TazaTicket Flight Agent",
        "description": "Production-ready FastAPI + LangGraph flight agent with multilingual WhatsApp support",
        "version": "1.0.0",
        "endpoints": {
            "health": "/healthz",
            "readiness": "/readiness",
            "webhook": "/webhook/whatsapp"
        },
        "features": [
            "Multilingual support",
            "Multimodal (text + voice)",
            "WhatsApp integration",
            "Travelport flight search",
            "Date range and monthly searches",
            "Multi-airport support",
            "Conversation memory"
        ]
    }


def get_service(service_name: str):
    """Get service instance by name"""
    
    if service_name not in services:
        raise HTTPException(
            status_code=503, 
            detail=f"Service {service_name} not available"
        )
    
    return services[service_name]


# Make services accessible to routers
app.state.get_service = get_service 