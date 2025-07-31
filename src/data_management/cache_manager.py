"""
Redis Cache Manager
High-performance caching with Redis integration
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Union, Set
from datetime import datetime, timedelta
import redis.asyncio as redis
from redis.asyncio import Redis

from .models import SensorReading, NavigationData, OperationalState, DataType


class CacheManager:
    """Redis-based cache manager for high-speed data access"""
    
    def __init__(self, redis_config: Dict[str, Any] = None):
        self.logger = logging.getLogger(__name__)
        
        # Redis configuration
        config = redis_config or {}
        self.redis_host = config.get('host', 'localhost')
        self.redis_port = config.get('port', 6379)
        self.redis_db = config.get('db', 0)
        
        # Get Redis password from environment variable (no config fallback for security)
        self.redis_password = os.getenv('REDIS_PASSWORD')
        
        # Connection pool
        self.redis_pool: Optional[redis.ConnectionPool] = None
        self.redis_client: Optional[Redis] = None
        
        # Cache settings
        self.default_ttl = config.get('default_ttl', 300)  # 5 minutes
        self.sensor_ttl = config.get('sensor_ttl', 60)     # 1 minute
        self.config_ttl = config.get('config_ttl', 3600)   # 1 hour
        self.state_ttl = config.get('state_ttl', 30)       # 30 seconds
        
        # Performance tracking
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'errors': 0
        }
        
        # Key prefixes
        self.key_prefixes = {
            DataType.SENSOR: "sensor:",
            DataType.NAVIGATION: "nav:",
            DataType.OPERATIONAL: "ops:",
            DataType.CONFIGURATION: "config:",
            DataType.PERFORMANCE: "perf:",
            DataType.SAFETY: "safety:"
        }
        
        self._connected = False
        self._connection_lock = asyncio.Lock()
    
    async def connect(self) -> bool:
        """Establish Redis connection"""
        async with self._connection_lock:
            if self._connected:
                return True
            
            try:
                # Create connection pool
                self.redis_pool = redis.ConnectionPool(
                    host=self.redis_host,
                    port=self.redis_port,
                    db=self.redis_db,
                    password=self.redis_password,
                    decode_responses=True,
                    max_connections=20,
                    retry_on_timeout=True
                )
                
                # Create Redis client
                self.redis_client = Redis(connection_pool=self.redis_pool)
                
                # Test connection
                await self.redis_client.ping()
                
                self._connected = True
                self.logger.info(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to connect to Redis: {e}")
                self._connected = False
                return False
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
        if self.redis_pool:
            await self.redis_pool.disconnect()
        self._connected = False
        self.logger.info("Disconnected from Redis")
    
    def _make_key(self, data_type: DataType, identifier: str) -> str:
        """Generate cache key"""
        prefix = self.key_prefixes.get(data_type, "data:")
        return f"{prefix}{identifier}"
    
    async def get(self, data_type: DataType, key: str) -> Optional[Any]:
        """Get cached data with <10ms target response time"""
        if not self._connected:
            await self.connect()
        
        try:
            start_time = time.perf_counter()
            cache_key = self._make_key(data_type, key)
            
            # Get from Redis
            cached_data = await self.redis_client.get(cache_key)
            
            response_time = (time.perf_counter() - start_time) * 1000
            
            if cached_data is not None:
                self.stats['hits'] += 1
                data = json.loads(cached_data)
                
                # Log performance if > 10ms
                if response_time > 10:
                    self.logger.warning(f"Cache get took {response_time:.2f}ms for key {cache_key}")
                
                return data
            else:
                self.stats['misses'] += 1
                return None
                
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Cache get error for {key}: {e}")
            return None
    
    async def set(self, data_type: DataType, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set cached data with optional TTL"""
        if not self._connected:
            await self.connect()
        
        try:
            cache_key = self._make_key(data_type, key)
            
            # Determine TTL
            if ttl is None:
                if data_type == DataType.SENSOR:
                    ttl = self.sensor_ttl
                elif data_type == DataType.CONFIGURATION:
                    ttl = self.config_ttl
                elif data_type == DataType.OPERATIONAL:
                    ttl = self.state_ttl
                else:
                    ttl = self.default_ttl
            
            # Serialize and store
            serialized_data = json.dumps(value, default=str)
            await self.redis_client.setex(cache_key, ttl, serialized_data)
            
            self.stats['sets'] += 1
            return True
            
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Cache set error for {key}: {e}")
            return False
    
    async def delete(self, data_type: DataType, key: str) -> bool:
        """Delete cached data"""
        if not self._connected:
            await self.connect()
        
        try:
            cache_key = self._make_key(data_type, key)
            result = await self.redis_client.delete(cache_key)
            
            if result > 0:
                self.stats['deletes'] += 1
                return True
            return False
            
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Cache delete error for {key}: {e}")
            return False
    
    async def get_pattern(self, data_type: DataType, pattern: str) -> Dict[str, Any]:
        """Get multiple keys matching pattern"""
        if not self._connected:
            await self.connect()
        
        try:
            cache_pattern = self._make_key(data_type, pattern)
            keys = await self.redis_client.keys(cache_pattern)
            
            if not keys:
                return {}
            
            # Get all matching values
            values = await self.redis_client.mget(keys)
            result = {}
            
            for key, value in zip(keys, values):
                if value is not None:
                    # Remove prefix from key
                    clean_key = key.replace(self.key_prefixes.get(data_type, "data:"), "")
                    result[clean_key] = json.loads(value)
            
            return result
            
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Cache pattern get error for {pattern}: {e}")
            return {}
    
    async def add_to_stream(self, stream_name: str, data: Dict[str, Any], max_length: int = 1000) -> bool:
        """Add data to Redis stream for time series data"""
        if not self._connected:
            await self.connect()
        
        try:
            # Add to stream with automatic trimming
            await self.redis_client.xadd(
                stream_name,
                data,
                maxlen=max_length,
                approximate=True
            )
            return True
            
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Stream add error for {stream_name}: {e}")
            return False
    
    async def read_stream(self, stream_name: str, count: int = 100, start: str = "-") -> List[Dict[str, Any]]:
        """Read from Redis stream"""
        if not self._connected:
            await self.connect()
        
        try:
            messages = await self.redis_client.xrange(stream_name, start, "+", count)
            result = []
            
            for message_id, fields in messages:
                entry = {"id": message_id, "data": fields}
                result.append(entry)
            
            return result
            
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Stream read error for {stream_name}: {e}")
            return []
    
    async def publish(self, channel: str, message: Any) -> bool:
        """Publish message to Redis pub/sub"""
        if not self._connected:
            await self.connect()
        
        try:
            serialized_message = json.dumps(message, default=str)
            await self.redis_client.publish(channel, serialized_message)
            return True
            
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Publish error for channel {channel}: {e}")
            return False
    
    async def flush_expired(self) -> int:
        """Remove expired keys (Redis handles this automatically, but useful for stats)"""
        # Redis handles expiration automatically, this is mainly for monitoring
        try:
            info = await self.redis_client.info("keyspace")
            return info.get('expired_keys', 0)
        except Exception as e:
            self.logger.error(f"Error getting expiration info: {e}")
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        total_operations = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_operations * 100) if total_operations > 0 else 0
        
        redis_info = {}
        if self._connected:
            try:
                redis_info = await self.redis_client.info()
            except Exception as e:
                self.logger.error(f"Error getting Redis info: {e}")
        
        return {
            'connected': self._connected,
            'hit_rate': hit_rate,
            'operations': self.stats,
            'redis_info': {
                'used_memory': redis_info.get('used_memory_human', 'N/A'),
                'connected_clients': redis_info.get('connected_clients', 0),
                'total_commands_processed': redis_info.get('total_commands_processed', 0)
            }
        }
    
    async def clear_all(self) -> bool:
        """Clear all cached data (use with caution)"""
        if not self._connected:
            await self.connect()
        
        try:
            await self.redis_client.flushdb()
            self.logger.warning("All cache data cleared")
            return True
        except Exception as e:
            self.logger.error(f"Error clearing cache: {e}")
            return False
