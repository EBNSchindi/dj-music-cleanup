"""
Streaming architecture for memory-efficient processing of large music libraries.
Provides base classes and utilities for streaming-based file processing.
"""

import os
import time
import logging
import resource
import threading
from abc import ABC, abstractmethod
from typing import Generator, Iterator, Any, Dict, List, Optional, Callable, TypeVar, Union
from pathlib import Path
from dataclasses import dataclass
from queue import Queue, Empty, Full
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from datetime import datetime

from .database import get_database_manager

T = TypeVar('T')
U = TypeVar('U')

logger = logging.getLogger(__name__)


@dataclass
class StreamingConfig:
    """Configuration for streaming operations"""
    # File discovery settings
    file_discovery_batch_size: int = 1000
    file_discovery_buffer_size: int = 100
    
    # Audio processing settings
    fingerprint_chunk_size: int = 8192
    audio_chunk_size: int = 65536  # 64KB chunks for audio processing
    
    # Database settings
    database_batch_size: int = 500
    database_page_size: int = 1000
    
    # Memory management
    max_memory_usage_mb: int = 1024
    memory_check_interval: int = 10  # Check every N items
    enable_memory_monitoring: bool = True
    
    # Parallel processing
    max_workers: int = 4
    parallel_streams: int = 2
    stream_buffer_size: int = 50
    
    # Rate limiting
    api_rate_limit: float = 1.0  # calls per second
    file_processing_delay: float = 0.001  # seconds between files
    
    # Error handling
    max_retries: int = 3
    retry_delay: float = 1.0
    error_threshold: float = 0.1  # Stop if >10% of items fail


class MemoryMonitor:
    """Monitor memory usage and provide alerts when limits are exceeded"""
    
    def __init__(self, max_memory_mb: int, check_interval: int = 10):
        self.max_memory_mb = max_memory_mb
        self.check_interval = check_interval
        self.check_counter = 0
        self.last_check_time = time.time()
        
    def check_memory(self) -> bool:
        """Check if memory usage is within limits"""
        self.check_counter += 1
        
        # Only check memory every N calls to avoid overhead
        if self.check_counter % self.check_interval != 0:
            return True
            
        current_time = time.time()
        memory_mb = self._get_memory_usage_mb()
        
        if memory_mb > self.max_memory_mb:
            logger.warning(
                f"Memory usage ({memory_mb:.1f}MB) exceeds limit ({self.max_memory_mb}MB). "
                f"Consider reducing batch sizes or enabling garbage collection."
            )
            return False
            
        # Log memory usage periodically
        if current_time - self.last_check_time > 30:  # Every 30 seconds
            logger.debug(f"Memory usage: {memory_mb:.1f}MB / {self.max_memory_mb}MB")
            self.last_check_time = current_time
            
        return True
    
    def _get_memory_usage_mb(self) -> float:
        """Get current memory usage in MB using resource module"""
        try:
            # Use resource.getrusage for memory info (Unix-like systems)
            usage = resource.getrusage(resource.RUSAGE_SELF)
            # On Linux, ru_maxrss is in KB, on macOS it's in bytes
            if os.name == 'posix':
                return usage.ru_maxrss / 1024  # Convert KB to MB
            else:
                return usage.ru_maxrss / (1024 * 1024)  # Convert bytes to MB
        except (OSError, AttributeError):
            # Fallback: use a simple estimation
            return 100.0  # Default safe value
    
    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics"""
        memory_mb = self._get_memory_usage_mb()
        return {
            'rss_mb': memory_mb,
            'vms_mb': memory_mb * 1.2,  # Estimate
            'percent': min(100.0, (memory_mb / 2048) * 100),  # Assume 2GB total
            'available_mb': max(0, 2048 - memory_mb)  # Estimate available
        }


class RateLimiter:
    """Rate limiter for API calls and resource access"""
    
    def __init__(self, calls_per_second: float):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second if calls_per_second > 0 else 0
        self.last_call_time = 0
        self._lock = threading.Lock()
    
    def wait(self):
        """Wait if necessary to respect rate limit"""
        if self.min_interval <= 0:
            return
            
        with self._lock:
            current_time = time.time()
            elapsed = current_time - self.last_call_time
            
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                time.sleep(sleep_time)
                
            self.last_call_time = time.time()


class StreamingError(Exception):
    """Base exception for streaming operations"""
    pass


class MemoryLimitExceeded(StreamingError):
    """Raised when memory usage exceeds configured limits"""
    pass


class StreamProcessor(ABC):
    """Abstract base class for streaming processors"""
    
    def __init__(self, config: StreamingConfig):
        self.config = config
        self.memory_monitor = MemoryMonitor(
            config.max_memory_usage_mb, 
            config.memory_check_interval
        ) if config.enable_memory_monitoring else None
        self.error_count = 0
        self.processed_count = 0
        
    @abstractmethod
    def process_item(self, item: T) -> U:
        """Process a single item"""
        pass
    
    def process_stream(self, stream: Iterator[T]) -> Generator[U, None, None]:
        """Process a stream of items with memory monitoring"""
        for item in stream:
            # Check memory usage
            if self.memory_monitor and not self.memory_monitor.check_memory():
                if self.config.enable_memory_monitoring:
                    raise MemoryLimitExceeded(
                        f"Memory usage exceeded {self.config.max_memory_usage_mb}MB"
                    )
            
            try:
                result = self.process_item(item)
                self.processed_count += 1
                
                # Add small delay if configured
                if self.config.file_processing_delay > 0:
                    time.sleep(self.config.file_processing_delay)
                
                yield result
                
            except Exception as e:
                self.error_count += 1
                error_rate = self.error_count / (self.processed_count + self.error_count)
                
                if error_rate > self.config.error_threshold:
                    logger.error(
                        f"Error rate ({error_rate:.1%}) exceeds threshold "
                        f"({self.config.error_threshold:.1%}). Stopping stream."
                    )
                    raise StreamingError(f"Too many errors in stream: {error_rate:.1%}")
                
                logger.warning(f"Error processing item: {e}")
                # Yield error info instead of stopping
                yield self._create_error_result(item, e)
    
    def _create_error_result(self, item: T, error: Exception) -> U:
        """Create error result for failed item"""
        return {
            'item': item,
            'error': str(error),
            'status': 'failed'
        }


class FileDiscoveryStream:
    """Stream-based file discovery for music files"""
    
    def __init__(self, config: StreamingConfig):
        self.config = config
        self.supported_formats = {'.mp3', '.flac', '.m4a', '.ogg', '.opus', '.wav'}
        
    def stream_files(self, source_folders: List[str], 
                    protected_paths: List[str] = None) -> Generator[str, None, None]:
        """Stream music files from source folders"""
        protected_paths = protected_paths or []
        processed_count = 0
        
        for source_folder in source_folders:
            if not os.path.exists(source_folder):
                logger.warning(f"Source folder not found: {source_folder}")
                continue
                
            logger.info(f"Streaming files from {source_folder}")
            
            for root, dirs, files in os.walk(source_folder):
                # Skip protected folders
                if any(root.startswith(protected) for protected in protected_paths):
                    logger.debug(f"Skipping protected folder: {root}")
                    dirs.clear()  # Don't descend into subdirectories
                    continue
                
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in self.supported_formats:
                        file_path = os.path.join(root, file)
                        processed_count += 1
                        
                        # Log progress periodically
                        if processed_count % 1000 == 0:
                            logger.debug(f"Discovered {processed_count} files")
                        
                        yield file_path


class BatchStream:
    """Convert a stream into batches for batch processing"""
    
    @staticmethod
    def batch_stream(stream: Iterator[T], batch_size: int) -> Generator[List[T], None, None]:
        """Convert stream into batches of specified size"""
        batch = []
        
        for item in stream:
            batch.append(item)
            
            if len(batch) >= batch_size:
                yield batch
                batch = []
        
        # Yield remaining items
        if batch:
            yield batch
    
    @staticmethod
    def unbatch_stream(batch_stream: Iterator[List[T]]) -> Generator[T, None, None]:
        """Convert batched stream back to individual items"""
        for batch in batch_stream:
            for item in batch:
                yield item


class DatabaseStreamer:
    """Stream-based database operations with pagination"""
    
    def __init__(self, config: StreamingConfig):
        self.config = config
        self.db_manager = get_database_manager()
    
    def stream_query_results(self, db_name: str, query: str, 
                           params: tuple = (), 
                           batch_size: int = None) -> Generator[List[Dict], None, None]:
        """Stream query results in batches"""
        batch_size = batch_size or self.config.database_batch_size
        offset = 0
        
        while True:
            # Add LIMIT and OFFSET to query
            paginated_query = f"{query} LIMIT {batch_size} OFFSET {offset}"
            
            try:
                results = self.db_manager.execute_query(db_name, paginated_query, params)
                
                if not results:
                    break
                
                # Convert to list of dicts
                result_list = [dict(row) for row in results]
                yield result_list
                
                # If we got fewer results than batch_size, we're done
                if len(results) < batch_size:
                    break
                    
                offset += batch_size
                
            except Exception as e:
                logger.error(f"Error streaming query results: {e}")
                break
    
    def stream_table_scan(self, db_name: str, table_name: str, 
                         columns: List[str] = None,
                         where_clause: str = None,
                         order_by: str = None) -> Generator[Dict, None, None]:
        """Stream all rows from a table"""
        columns_str = ', '.join(columns) if columns else '*'
        query = f"SELECT {columns_str} FROM {table_name}"
        
        if where_clause:
            query += f" WHERE {where_clause}"
        if order_by:
            query += f" ORDER BY {order_by}"
            
        for batch in self.stream_query_results(db_name, query):
            for row in batch:
                yield row


class ParallelStreamProcessor:
    """Process streams in parallel with memory management"""
    
    def __init__(self, config: StreamingConfig):
        self.config = config
        self.memory_monitor = MemoryMonitor(
            config.max_memory_usage_mb,
            config.memory_check_interval
        ) if config.enable_memory_monitoring else None
    
    def process_parallel(self, stream: Iterator[T], 
                        processor_func: Callable[[T], U],
                        max_workers: int = None) -> Generator[U, None, None]:
        """Process stream items in parallel"""
        max_workers = max_workers or self.config.max_workers
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit initial batch of work
            future_to_item = {}
            item_iterator = iter(stream)
            
            # Fill initial queue
            for _ in range(max_workers * 2):  # 2x buffer
                try:
                    item = next(item_iterator)
                    future = executor.submit(processor_func, item)
                    future_to_item[future] = item
                except StopIteration:
                    break
            
            # Process results as they complete
            while future_to_item:
                # Check memory usage
                if (self.memory_monitor and 
                    not self.memory_monitor.check_memory() and 
                    self.config.enable_memory_monitoring):
                    logger.warning("Memory limit exceeded, reducing parallelism")
                    # Could implement backpressure here
                
                # Get completed futures
                for future in as_completed(future_to_item.keys(), timeout=1.0):
                    item = future_to_item.pop(future)
                    
                    try:
                        result = future.result()
                        yield result
                    except Exception as e:
                        logger.error(f"Error processing {item}: {e}")
                        yield {'item': item, 'error': str(e), 'status': 'failed'}
                    
                    # Submit next item if available
                    try:
                        next_item = next(item_iterator)
                        next_future = executor.submit(processor_func, next_item)
                        future_to_item[next_future] = next_item
                    except StopIteration:
                        pass  # No more items


class StreamingProgressTracker:
    """Progress tracking for streaming operations"""
    
    def __init__(self, description: str, enable_db_tracking: bool = True):
        self.description = description
        self.enable_db_tracking = enable_db_tracking
        self.start_time = time.time()
        self.processed_count = 0
        self.error_count = 0
        self.last_report_time = time.time()
        self.report_interval = 10.0  # seconds
        
        if enable_db_tracking:
            self.db_manager = get_database_manager()
    
    def update(self, items_processed: int = 1, has_error: bool = False):
        """Update progress counters"""
        self.processed_count += items_processed
        if has_error:
            self.error_count += 1
        
        # Report progress periodically
        current_time = time.time()
        if current_time - self.last_report_time >= self.report_interval:
            self._report_progress()
            self.last_report_time = current_time
    
    def _report_progress(self):
        """Report current progress"""
        elapsed = time.time() - self.start_time
        rate = self.processed_count / elapsed if elapsed > 0 else 0
        error_rate = self.error_count / self.processed_count if self.processed_count > 0 else 0
        
        logger.info(
            f"{self.description}: {self.processed_count} processed, "
            f"{rate:.1f} items/sec, {error_rate:.1%} error rate"
        )
    
    def finalize(self) -> Dict[str, Any]:
        """Finalize progress tracking and return summary"""
        elapsed = time.time() - self.start_time
        rate = self.processed_count / elapsed if elapsed > 0 else 0
        
        summary = {
            'description': self.description,
            'processed_count': self.processed_count,
            'error_count': self.error_count,
            'elapsed_seconds': elapsed,
            'items_per_second': rate,
            'error_rate': self.error_count / self.processed_count if self.processed_count > 0 else 0
        }
        
        logger.info(f"Streaming complete: {summary}")
        return summary


class StreamingConfigManager:
    """Manage streaming configuration with adaptive tuning"""
    
    def __init__(self, base_config: StreamingConfig):
        self.base_config = base_config
        self.current_config = base_config
        self.performance_history = []
        
    def adapt_config(self, memory_usage: Dict[str, float], 
                    processing_rate: float, error_rate: float) -> StreamingConfig:
        """Adapt configuration based on performance metrics"""
        new_config = StreamingConfig(**self.current_config.__dict__)
        
        # Adjust batch sizes based on memory usage
        memory_percent = memory_usage.get('percent', 0)
        if memory_percent > 80:
            # Reduce batch sizes
            new_config.database_batch_size = max(100, new_config.database_batch_size // 2)
            new_config.file_discovery_batch_size = max(100, new_config.file_discovery_batch_size // 2)
            logger.info("Reduced batch sizes due to high memory usage")
        elif memory_percent < 40 and processing_rate > 10:
            # Increase batch sizes
            new_config.database_batch_size = min(2000, new_config.database_batch_size * 2)
            new_config.file_discovery_batch_size = min(5000, new_config.file_discovery_batch_size * 2)
            logger.info("Increased batch sizes due to low memory usage and good performance")
        
        # Adjust workers based on error rate
        if error_rate > 0.05:  # >5% error rate
            new_config.max_workers = max(1, new_config.max_workers - 1)
            logger.info("Reduced worker count due to high error rate")
        elif error_rate < 0.01 and processing_rate > 5:  # <1% error rate
            new_config.max_workers = min(8, new_config.max_workers + 1)
            logger.info("Increased worker count due to low error rate")
        
        self.current_config = new_config
        return new_config
    
    def get_optimal_config(self, library_size: int, available_memory_mb: int) -> StreamingConfig:
        """Get optimal configuration for given library size and memory"""
        config = StreamingConfig(**self.base_config.__dict__)
        
        # Adjust for library size
        if library_size > 100000:  # Very large library
            config.database_batch_size = 200
            config.file_discovery_batch_size = 500
            config.max_workers = 2
        elif library_size > 10000:  # Large library
            config.database_batch_size = 500
            config.file_discovery_batch_size = 1000
            config.max_workers = 4
        else:  # Small library
            config.database_batch_size = 1000
            config.file_discovery_batch_size = 2000
            config.max_workers = 6
        
        # Adjust for available memory
        if available_memory_mb < 512:
            config.max_memory_usage_mb = min(config.max_memory_usage_mb, 256)
            config.max_workers = min(config.max_workers, 2)
        elif available_memory_mb > 4096:
            config.max_memory_usage_mb = min(config.max_memory_usage_mb, 2048)
            config.max_workers = min(config.max_workers, 8)
        
        return config