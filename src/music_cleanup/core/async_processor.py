"""
Async File Processor

Performance optimization using asyncio for concurrent file processing.
Significantly improves throughput for I/O-bound operations like metadata extraction.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor
import time

from .constants import (
    DEFAULT_BATCH_SIZE,
    MAX_CONCURRENT_WORKERS,
    MIN_HEALTH_SCORE_DEFAULT
)


class AsyncFileProcessor:
    """
    Async file processor for high-performance file operations.
    
    Uses asyncio and thread pools to process files concurrently,
    significantly improving throughput for metadata extraction,
    fingerprinting, and quality analysis.
    """
    
    def __init__(self, max_workers: int = MAX_CONCURRENT_WORKERS):
        self.max_workers = max_workers
        self.logger = logging.getLogger(__name__)
        self._executor = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._executor:
            self._executor.shutdown(wait=True)
    
    async def process_files_async(
        self,
        file_paths: List[str],
        processor_func: Callable,
        batch_size: int = DEFAULT_BATCH_SIZE,
        progress_callback: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Process files asynchronously in batches.
        
        Args:
            file_paths: List of file paths to process
            processor_func: Function to process each file
            batch_size: Number of files to process in each batch
            progress_callback: Optional progress callback
            
        Returns:
            List of processing results
        """
        start_time = time.time()
        results = []
        total_files = len(file_paths)
        
        self.logger.info(f"🚀 Starting async processing of {total_files} files...")
        
        # Process files in batches
        for i in range(0, total_files, batch_size):
            batch = file_paths[i:i + batch_size]
            batch_results = await self._process_batch_async(
                batch, processor_func, progress_callback, i, total_files
            )
            results.extend(batch_results)
            
            # Memory cleanup between batches
            if i % (batch_size * 5) == 0:
                await asyncio.sleep(0.01)  # Allow other tasks to run
        
        duration = time.time() - start_time
        self.logger.info(f"✅ Async processing completed in {duration:.2f}s")
        
        return results
    
    async def _process_batch_async(
        self,
        file_batch: List[str],
        processor_func: Callable,
        progress_callback: Optional[Callable],
        batch_start: int,
        total_files: int
    ) -> List[Dict[str, Any]]:
        """Process a batch of files asynchronously."""
        
        # Create async tasks for concurrent processing
        loop = asyncio.get_event_loop()
        tasks = []
        
        for i, file_path in enumerate(file_batch):
            task = loop.run_in_executor(
                self._executor,
                processor_func,
                file_path
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and log errors
        valid_results = []
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                self.logger.error(f"Error processing {file_batch[i]}: {result}")
            elif result is not None:
                valid_results.append(result)
        
        # Update progress
        if progress_callback:
            progress_callback(batch_start + len(file_batch), total_files)
        
        return valid_results
    
    async def extract_metadata_async(
        self,
        file_paths: List[str],
        metadata_extractor: Callable,
        progress_callback: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract metadata from files asynchronously.
        
        Args:
            file_paths: List of file paths
            metadata_extractor: Metadata extraction function
            progress_callback: Optional progress callback
            
        Returns:
            List of metadata dictionaries
        """
        return await self.process_files_async(
            file_paths,
            metadata_extractor,
            batch_size=50,  # Smaller batches for metadata extraction
            progress_callback=progress_callback
        )
    
    async def analyze_quality_async(
        self,
        file_infos: List[Dict[str, Any]],
        quality_analyzer: Callable,
        progress_callback: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze file quality asynchronously.
        
        Args:
            file_infos: List of file information dictionaries
            quality_analyzer: Quality analysis function
            progress_callback: Optional progress callback
            
        Returns:
            List of quality analysis results
        """
        def analyze_wrapper(file_info):
            return quality_analyzer(file_info['file_path'])
        
        return await self.process_files_async(
            [info['file_path'] for info in file_infos],
            analyze_wrapper,
            batch_size=25,  # Quality analysis is more CPU intensive
            progress_callback=progress_callback
        )
    
    async def generate_fingerprints_async(
        self,
        file_paths: List[str],
        fingerprinter: Callable,
        progress_callback: Optional[Callable] = None
    ) -> List[Tuple[str, str]]:
        """
        Generate fingerprints asynchronously.
        
        Args:
            file_paths: List of file paths
            fingerprinter: Fingerprinting function
            progress_callback: Optional progress callback
            
        Returns:
            List of (file_path, fingerprint) tuples
        """
        def fingerprint_wrapper(file_path):
            fingerprint = fingerprinter(file_path)
            return (file_path, fingerprint) if fingerprint else None
        
        results = await self.process_files_async(
            file_paths,
            fingerprint_wrapper,
            batch_size=20,  # Fingerprinting is very CPU intensive
            progress_callback=progress_callback
        )
        
        # Filter out None results
        return [r for r in results if r is not None]


class AsyncBatchProcessor:
    """
    Async batch processor for memory-efficient large-scale operations.
    
    Processes large collections of files in manageable async batches
    to prevent memory exhaustion while maximizing throughput.
    """
    
    def __init__(self, batch_size: int = DEFAULT_BATCH_SIZE):
        self.batch_size = batch_size
        self.logger = logging.getLogger(__name__)
    
    async def process_in_batches(
        self,
        items: List[Any],
        async_processor: Callable,
        progress_callback: Optional[Callable] = None
    ) -> List[Any]:
        """
        Process items in async batches.
        
        Args:
            items: List of items to process
            async_processor: Async processing function
            progress_callback: Optional progress callback
            
        Returns:
            List of processing results
        """
        total_items = len(items)
        all_results = []
        
        self.logger.info(f"📦 Processing {total_items} items in async batches...")
        
        for i in range(0, total_items, self.batch_size):
            batch = items[i:i + self.batch_size]
            
            try:
                batch_results = await async_processor(batch)
                all_results.extend(batch_results)
                
                if progress_callback:
                    progress_callback(i + len(batch), total_items)
                
                # Small delay to prevent overwhelming the system
                await asyncio.sleep(0.001)
                
            except Exception as e:
                self.logger.error(f"Error processing batch {i//self.batch_size + 1}: {e}")
                continue
        
        self.logger.info(f"✅ Completed async batch processing")
        return all_results