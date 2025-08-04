"""
Custom Exceptions and Error Handlers
Centralized exception handling for the web API.
"""

import logging
from typing import Any, Dict, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import traceback
from datetime import datetime


class APIException(Exception):
    """Base API exception"""
    
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.error_code = error_code or self.__class__.__name__
        super().__init__(self.message)


class ValidationError(APIException):
    """Validation error"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
            error_code="VALIDATION_ERROR"
        )


class NotFoundError(APIException):
    """Resource not found error"""
    
    def __init__(self, resource: str, identifier: str = ""):
        message = f"{resource} not found"
        if identifier:
            message += f": {identifier}"
        
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "identifier": identifier},
            error_code="NOT_FOUND"
        )


class ConflictError(APIException):
    """Resource conflict error"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
            error_code="CONFLICT"
        )


class UnauthorizedError(APIException):
    """Authentication required error"""
    
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED"
        )


class ForbiddenError(APIException):
    """Permission denied error"""
    
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN"
        )


class RateLimitError(APIException):
    """Rate limit exceeded error"""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after": retry_after},
            error_code="RATE_LIMIT_EXCEEDED"
        )


class ServiceUnavailableError(APIException):
    """Service unavailable error"""
    
    def __init__(self, service: str, message: Optional[str] = None):
        if not message:
            message = f"Service unavailable: {service}"
        
        super().__init__(
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"service": service},
            error_code="SERVICE_UNAVAILABLE"
        )


class HardwareError(APIException):
    """Hardware-related error"""
    
    def __init__(self, component: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Hardware error in {component}: {message}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"component": component, **(details or {})},
            error_code="HARDWARE_ERROR"
        )


class CommunicationError(APIException):
    """Communication/MQTT error"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Communication error: {message}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
            error_code="COMMUNICATION_ERROR"
        )


class SafetyError(APIException):
    """Safety system error"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Safety error: {message}",
            status_code=status.HTTP_423_LOCKED,  # Locked due to safety
            details=details,
            error_code="SAFETY_ERROR"
        )


class ConfigurationError(APIException):
    """Configuration error"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Configuration error: {message}",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
            error_code="CONFIGURATION_ERROR"
        )


# Error response models
def create_error_response(
    message: str,
    status_code: int,
    error_code: str = "UNKNOWN_ERROR",
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None
) -> Dict[str, Any]:
    """Create standardized error response"""
    
    error_response = {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
    }
    
    if details:
        error_response["error"]["details"] = details
    
    if request_id:
        error_response["error"]["request_id"] = request_id
    
    # Add additional context for development
    if status_code >= 500:
        error_response["error"]["type"] = "server_error"
    elif status_code >= 400:
        error_response["error"]["type"] = "client_error"
    
    return error_response


# Exception handlers
async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    """Handle custom API exceptions"""
    logger = logging.getLogger("api_exceptions")
    
    # Get request ID if available
    request_id = getattr(request.state, 'request_id', None)
    
    # Log the exception
    log_data = {
        'request_id': request_id,
        'method': request.method,
        'url': str(request.url),
        'error_code': getattr(exc, 'error_code', 'UNKNOWN'),
        'error_message': getattr(exc, 'message', str(exc.detail) if hasattr(exc, 'detail') else str(exc)),
        'status_code': exc.status_code,
        'details': getattr(exc, 'details', None)
    }
    
    if exc.status_code >= 500:
        logger.error("API Exception", extra=log_data, exc_info=True)
    else:
        logger.warning("API Exception", extra=log_data)
    
    # Create error response
    error_response = create_error_response(
        message=exc.message,
        status_code=exc.status_code,
        error_code=exc.error_code,
        details=exc.details,
        request_id=request_id
    )
    
    # Add retry-after header for rate limiting
    headers = {}
    if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS and exc.details.get('retry_after'):
        headers['Retry-After'] = str(exc.details['retry_after'])
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response,
        headers=headers
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions"""
    logger = logging.getLogger("api_exceptions")
    
    request_id = getattr(request.state, 'request_id', None)
    
    # Log the exception
    log_data = {
        'request_id': request_id,
        'method': request.method,
        'url': str(request.url),
        'status_code': exc.status_code,
        'detail': exc.detail
    }
    
    if exc.status_code >= 500:
        logger.error("HTTP Exception", extra=log_data)
    else:
        logger.warning("HTTP Exception", extra=log_data)
    
    # Create error response
    error_response = create_error_response(
        message=str(exc.detail),
        status_code=exc.status_code,
        error_code="HTTP_ERROR",
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response,
        headers=getattr(exc, 'headers', {})
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors"""
    logger = logging.getLogger("api_exceptions")
    
    request_id = getattr(request.state, 'request_id', None)
    
    # Format validation errors
    validation_errors = []
    for error in exc.errors():
        validation_errors.append({
            "field": ".".join(str(x) for x in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    # Log the exception
    log_data = {
        'request_id': request_id,
        'method': request.method,
        'url': str(request.url),
        'validation_errors': validation_errors
    }
    
    logger.warning("Validation Exception", extra=log_data)
    
    # Create error response
    error_response = create_error_response(
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_code="VALIDATION_ERROR",
        details={"validation_errors": validation_errors},
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions"""
    logger = logging.getLogger("api_exceptions")
    
    request_id = getattr(request.state, 'request_id', None)
    
    # Log the exception with full traceback
    log_data = {
        'request_id': request_id,
        'method': request.method,
        'url': str(request.url),
        'exception_type': type(exc).__name__,
        'exception_message': str(exc),
        'traceback': traceback.format_exc()
    }
    
    logger.error("Unexpected Exception", extra=log_data, exc_info=True)
    
    # Create generic error response (don't expose internal details)
    error_response = create_error_response(
        message="An internal server error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="INTERNAL_SERVER_ERROR",
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response
    )


# Exception handler registration helper
def register_exception_handlers(app):
    """Register all exception handlers with the FastAPI app"""
    app.add_exception_handler(APIException, api_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)


# Utility functions for raising common exceptions
def raise_not_found(resource: str, identifier: str = ""):
    """Raise a not found exception"""
    raise NotFoundError(resource, identifier)


def raise_validation_error(message: str, details: Optional[Dict[str, Any]] = None):
    """Raise a validation error"""
    raise ValidationError(message, details)


def raise_service_unavailable(service: str, message: Optional[str] = None):
    """Raise a service unavailable error"""
    raise ServiceUnavailableError(service, message)


def raise_hardware_error(component: str, message: str, details: Optional[Dict[str, Any]] = None):
    """Raise a hardware error"""
    raise HardwareError(component, message, details)


def raise_communication_error(message: str, details: Optional[Dict[str, Any]] = None):
    """Raise a communication error"""
    raise CommunicationError(message, details)


def raise_safety_error(message: str, details: Optional[Dict[str, Any]] = None):
    """Raise a safety error"""
    raise SafetyError(message, details)
