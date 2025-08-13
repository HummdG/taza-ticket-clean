"""
Logging configuration for the application
"""

import logging
import sys
from typing import Any, Dict
import json
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present (excluding private keys and 'context' which we flatten later)
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                'filename', 'module', 'lineno', 'funcName', 'created',
                'msecs', 'relativeCreated', 'thread', 'threadName',
                'processName', 'process', 'getMessage', 'exc_info',
                'exc_text', 'stack_info', 'context', '_log_ctx'
            } and not key.startswith('_'):
                log_entry[key] = value
        
        # Safely flatten context dictionaries into top-level fields (without overwriting)
        def _merge_context(ctx: Dict[str, Any]) -> None:
            if isinstance(ctx, dict):
                for k, v in ctx.items():
                    if k not in log_entry:
                        log_entry[k] = v
        
        # Merge from private log context set by LogContext
        _merge_context(getattr(record, '_log_ctx', {}))
        # Merge from standard 'context' if used via log_with_context
        _merge_context(getattr(record, 'context', {}))
        
        return json.dumps(log_entry, default=str)


def setup_logging(log_level: str = "INFO") -> None:
    """Setup application logging configuration"""
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(StructuredFormatter())
    
    # Add handler to root logger
    root_logger.addHandler(console_handler)
    
    # Set specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    return logging.getLogger(name)


def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    **context: Any
) -> None:
    """Log with additional context"""
    extra = {"context": context} if context else {}
    getattr(logger, level.lower())(message, extra=extra)


class LogContext:
    """Context manager for adding context to logs"""
    
    def __init__(self, **context: Any):
        self.context = context
        self.old_factory = logging.getLogRecordFactory()
    
    def __enter__(self):
        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            try:
                # Store context in a private container to avoid collisions with 'extra' keys
                existing_ctx = getattr(record, '_log_ctx', {})
                if not isinstance(existing_ctx, dict):
                    existing_ctx = {}
                merged_ctx = {**existing_ctx, **self.context}
                setattr(record, '_log_ctx', merged_ctx)
            except Exception:
                pass
            return record
        
        logging.setLogRecordFactory(record_factory)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.setLogRecordFactory(self.old_factory) 