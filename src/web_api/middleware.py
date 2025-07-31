"""
Custom Middleware
Rate limiting, request logging, and other middleware components.
"""

import time
import logging
import json
from typing import Dict, Any, Optional
from collections import defaultdict, deque
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio
import uuid


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with per-endpoint and per-IP limits"""
    
    def __init__(self, app, config: Optional[Dict[str, Any]] = None):
        super().__init__(app)
        self.logger = logging.getLogger(__name__)
        self.config = config or {}
        
        # Rate limiting storage
        self._request_counts: Dict[str, deque] = defaultdict(deque)
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Default limits (requests per minute)
        self.default_limit = self.config.get('default_requests_per_minute', 100)
        self.burst_multiplier = self.config.get('burst_multiplier', 1.5)
        
        # Per-endpoint limits
        self.endpoint_limits = {
            '/api/v1/sensors': self.config.get('sensor_data_rpm', 200),
            '/api/v1/navigation': self.config.get('navigation_rpm', 60),
            '/api/v1/config': self.config.get('configuration_rpm', 30),
        }
        
        # Start cleanup task
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_old_requests())
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting"""
        if not self.config.get('enabled', True):
            return await call_next(request)
        
        # Get client identifier
        client_id = self._get_client_id(request)
        endpoint = self._get_endpoint_pattern(request.url.path)
        
        # Check rate limit
        if not await self._check_rate_limit(client_id, endpoint):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": 60
                },
                headers={"Retry-After": "60"}
            )
        
        # Record request
        await self._record_request(client_id, endpoint)
        
        # Process request
        response = await call_next(request)
        return response
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting"""
        # Try to get user ID from auth first
        auth_header = request.headers.get("authorization")
        if auth_header:
            # In production, extract user ID from JWT token
            return f"user_{hash(auth_header) % 10000}"
        
        # Fall back to IP address
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        client_host = request.client.host if request.client else "unknown"
        return client_host
    
    def _get_endpoint_pattern(self, path: str) -> str:
        """Get endpoint pattern for rate limiting"""
        for pattern in self.endpoint_limits.keys():
            if path.startswith(pattern):
                return pattern
        return "default"
    
    async def _check_rate_limit(self, client_id: str, endpoint: str) -> bool:
        """Check if request is within rate limit"""
        key = f"{client_id}:{endpoint}"
        current_time = time.time()
        window_start = current_time - 60  # 1 minute window
        
        # Get request timestamps for this client/endpoint
        requests = self._request_counts[key]
        
        # Remove old requests
        while requests and requests[0] < window_start:
            requests.popleft()
        
        # Get rate limit for this endpoint
        limit = self.endpoint_limits.get(endpoint, self.default_limit)
        burst_limit = int(limit * self.burst_multiplier)
        
        # Check if under limit
        return len(requests) < burst_limit
    
    async def _record_request(self, client_id: str, endpoint: str):
        """Record a request for rate limiting"""
        key = f"{client_id}:{endpoint}"
        self._request_counts[key].append(time.time())
    
    async def _cleanup_old_requests(self):
        """Periodically clean up old request records"""
        while True:
            try:
                await asyncio.sleep(60)  # Cleanup every minute
                current_time = time.time()
                window_start = current_time - 60
                
                for key, requests in list(self._request_counts.items()):
                    # Remove old requests
                    while requests and requests[0] < window_start:
                        requests.popleft()
                    
                    # Remove empty queues
                    if not requests:
                        del self._request_counts[key]
                        
            except Exception as e:
                self.logger.error(f"Error in rate limit cleanup: {e}")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Request logging middleware with structured logging"""
    
    def __init__(self, app, config: Optional[Dict[str, Any]] = None):
        super().__init__(app)
        self.logger = logging.getLogger("api_requests")
        self.config = config or {}
        
        # Configure logging format
        self.log_level = getattr(logging, self.config.get('log_level', 'INFO').upper())
        self.log_request_body = self.config.get('log_request_body', False)
        self.log_response_body = self.config.get('log_response_body', False)
        
        # Skip logging for certain paths
        self.skip_paths = {
            '/health',
            '/metrics',
            '/api/docs',
            '/api/redoc',
            '/api/openapi.json'
        }
    
    async def dispatch(self, request: Request, call_next):
        """Log request and response"""
        # Skip logging for certain paths
        if request.url.path in self.skip_paths:
            return await call_next(request)
        
        # Generate request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Start timing
        start_time = time.time()
        
        # Log request
        await self._log_request(request, request_id)
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Add headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            
            # Log response
            await self._log_response(request, response, request_id, process_time)
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            
            # Log error
            self.logger.error(
                "Request failed",
                extra={
                    'request_id': request_id,
                    'method': request.method,
                    'url': str(request.url),
                    'client_ip': self._get_client_ip(request),
                    'process_time': process_time,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
            
            raise
    
    async def _log_request(self, request: Request, request_id: str):
        """Log incoming request"""
        log_data = {
            'request_id': request_id,
            'method': request.method,
            'url': str(request.url),
            'client_ip': self._get_client_ip(request),
            'user_agent': request.headers.get('user-agent', ''),
            'content_type': request.headers.get('content-type', ''),
            'content_length': request.headers.get('content-length', 0)
        }
        
        # Log request body if enabled and appropriate
        if (self.log_request_body and 
            request.method in ['POST', 'PUT', 'PATCH'] and
            request.headers.get('content-type', '').startswith('application/json')):
            try:
                body = await request.body()
                if body:
                    log_data['request_body'] = body.decode('utf-8')[:1000]  # Limit size
            except Exception as e:
                log_data['request_body_error'] = str(e)
        
        self.logger.info("Incoming request", extra=log_data)
    
    async def _log_response(self, request: Request, response: Response, 
                           request_id: str, process_time: float):
        """Log outgoing response"""
        log_data = {
            'request_id': request_id,
            'method': request.method,
            'url': str(request.url),
            'status_code': response.status_code,
            'process_time': process_time,
            'response_size': len(getattr(response, 'body', b''))
        }
        
        # Log response body if enabled and appropriate
        if (self.log_response_body and 
            hasattr(response, 'body') and
            response.headers.get('content-type', '').startswith('application/json')):
            try:
                if response.body:
                    body_str = response.body.decode('utf-8')[:1000]  # Limit size
                    log_data['response_body'] = body_str
            except Exception as e:
                log_data['response_body_error'] = str(e)
        
        # Choose log level based on status code
        if response.status_code >= 500:
            log_level = logging.ERROR
        elif response.status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO
        
        self.logger.log(log_level, "Request completed", extra=log_data)
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to responses"""
    
    def __init__(self, app, config: Optional[Dict[str, Any]] = None):
        super().__init__(app)
        self.config = config or {}
        
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }
        
        # Only add HSTS in production with HTTPS
        if self.config.get('use_hsts', False):
            self.security_headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    async def dispatch(self, request: Request, call_next):
        """Add security headers to response"""
        response = await call_next(request)
        
        # Add security headers
        for header, value in self.security_headers.items():
            response.headers[header] = value
        
        return response


class CompressionMiddleware(BaseHTTPMiddleware):
    """Custom compression middleware with performance optimization"""
    
    def __init__(self, app, config: Optional[Dict[str, Any]] = None):
        super().__init__(app)
        self.config = config or {}
        self.minimum_size = self.config.get('minimum_size', 1000)
        self.compressible_types = {
            'application/json',
            'application/javascript',
            'text/html',
            'text/css',
            'text/plain',
            'text/xml'
        }
    
    async def dispatch(self, request: Request, call_next):
        """Apply compression if appropriate"""
        response = await call_next(request)
        
        # Check if compression is appropriate
        if not self._should_compress(request, response):
            return response
        
        # Compression would be implemented here
        # For now, we rely on FastAPI's built-in GZipMiddleware
        return response
    
    def _should_compress(self, request: Request, response: Response) -> bool:
        """Check if response should be compressed"""
        # Check accept-encoding header
        accept_encoding = request.headers.get('accept-encoding', '')
        if 'gzip' not in accept_encoding:
            return False
        
        # Check content type
        content_type = response.headers.get('content-type', '')
        if not any(ct in content_type for ct in self.compressible_types):
            return False
        
        # Check response size
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) < self.minimum_size:
            return False
        
        return True
