"""
Custom exception classes for the application
"""


class TazaTicketError(Exception):
    """Base exception for all application errors"""
    
    def __init__(self, message: str, error_code: str = None, details: dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class TravelportError(TazaTicketError):
    """Travelport API related errors"""
    
    def __init__(self, message: str, transaction_id: str = None, status_code: int = None, **kwargs):
        self.transaction_id = transaction_id
        self.status_code = status_code
        super().__init__(message, error_code="TRAVELPORT_ERROR", **kwargs)


class OpenAIError(TazaTicketError):
    """OpenAI API related errors"""
    
    def __init__(self, message: str, request_id: str = None, **kwargs):
        self.request_id = request_id
        super().__init__(message, error_code="OPENAI_ERROR", **kwargs)


class TwilioError(TazaTicketError):
    """Twilio API related errors"""
    
    def __init__(self, message: str, error_code: str = None, **kwargs):
        super().__init__(message, error_code=f"TWILIO_{error_code}" if error_code else "TWILIO_ERROR", **kwargs)


class DynamoDBError(TazaTicketError):
    """DynamoDB related errors"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="DYNAMODB_ERROR", **kwargs)


class S3Error(TazaTicketError):
    """S3 related errors"""
    
    def __init__(self, message: str, bucket: str = None, key: str = None, **kwargs):
        self.bucket = bucket
        self.key = key
        super().__init__(message, error_code="S3_ERROR", **kwargs)


class ValidationError(TazaTicketError):
    """Data validation errors"""
    
    def __init__(self, message: str, field: str = None, **kwargs):
        self.field = field
        super().__init__(message, error_code="VALIDATION_ERROR", **kwargs)


class SlotFillingError(TazaTicketError):
    """Slot filling related errors"""
    
    def __init__(self, message: str, missing_slots: list = None, **kwargs):
        self.missing_slots = missing_slots or []
        super().__init__(message, error_code="SLOT_FILLING_ERROR", **kwargs)


class DateParsingError(TazaTicketError):
    """Date parsing related errors"""
    
    def __init__(self, message: str, date_input: str = None, **kwargs):
        self.date_input = date_input
        super().__init__(message, error_code="DATE_PARSING_ERROR", **kwargs)


class IATAResolutionError(TazaTicketError):
    """IATA code resolution errors"""
    
    def __init__(self, message: str, city_name: str = None, **kwargs):
        self.city_name = city_name
        super().__init__(message, error_code="IATA_RESOLUTION_ERROR", **kwargs)


class RateLimitError(TazaTicketError):
    """Rate limiting errors"""
    
    def __init__(self, message: str, service: str = None, retry_after: int = None, **kwargs):
        self.service = service
        self.retry_after = retry_after
        super().__init__(message, error_code="RATE_LIMIT_ERROR", **kwargs)


class ConfigurationError(TazaTicketError):
    """Configuration related errors"""
    
    def __init__(self, message: str, config_key: str = None, **kwargs):
        self.config_key = config_key
        super().__init__(message, error_code="CONFIGURATION_ERROR", **kwargs) 