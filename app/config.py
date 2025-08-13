"""
Application configuration using Pydantic BaseSettings
"""

from pydantic import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # OpenAI Configuration
    openai_api_key: str
    
    # Travelport Configuration
    travelport_client_id: str
    travelport_client_secret: str
    travelport_username: str
    travelport_password: str
    travelport_target_branch: Optional[str] = None
    travelport_access_group: str
    
    # Twilio Configuration
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_from: str  # e.g., "whatsapp:+14155238886"
    
    # AWS Configuration
    aws_region: str = "us-east-1"
    aws_access_key_id: str
    aws_secret_access_key: str
    s3_bucket: str = "tazaticket"
    
    # DynamoDB Configuration
    dynamodb_table_name: str = "tazaticket-conversations"
    
    # Application Configuration
    app_timezone: str = "Europe/London"
    log_level: str = "INFO"
    
    # API URLs
    travelport_oauth_url: str = "https://oauth.pp.travelport.com/oauth/oauth20/token"
    travelport_catalog_url: str = "https://api.pp.travelport.com/11/air/catalog/search/catalogproductofferings"
    travelport_airprice_url: str = "https://api.pp.travelport.com/11/air/price/offers/buildfromcatalogproductofferings"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings() 