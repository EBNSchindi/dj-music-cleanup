"""
Utility decorators for the DJ Music Cleanup Tool

Provides common decorators for error handling, logging, and performance tracking.
"""

import functools
import logging
import time
from typing import Any, Callable, Optional, TypeVar, Union, cast
from pathlib import Path

# Type variables for generic decorators
F = TypeVar('F', bound=Callable[..., Any])
T = TypeVar('T')


def handle_errors(
    log_level: str = "error",
    return_on_error: Optional[Any] = None,
    reraise: bool = False,
    error_types: tuple = (Exception,)
) -> Callable[[F], F]:
    """
    Decorator for consistent error handling across the application.
    
    Args:
        log_level: Logging level for errors (debug, info, warning, error, critical)
        return_on_error: Value to return when an error occurs
        reraise: Whether to re-raise the exception after logging
        error_types: Tuple of exception types to catch
    
    Returns:
        Decorated function with error handling
    
    Example:
        @handle_errors(log_level="error", return_on_error=None)
        def analyze_file(self, file_path: str) -> Optional[Dict]:
            # Implementation
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except error_types as e:
                # Get logger from class instance or module
                if args and hasattr(args[0], 'logger'):
                    logger = args[0].logger
                else:
                    logger = logging.getLogger(func.__module__)
                
                # Build error context
                context = []
                if args and hasattr(args[0], '__class__'):
                    context.append(f"Class: {args[0].__class__.__name__}")
                context.append(f"Function: {func.__name__}")
                
                # Add file path if present in arguments
                for arg in args[1:]:
                    if isinstance(arg, (str, Path)) and str(arg).endswith(
                        ('.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg')
                    ):
                        context.append(f"File: {arg}")
                        break
                
                # Log the error with context
                error_msg = f"{' | '.join(context)} | Error: {str(e)}"
                getattr(logger, log_level)(error_msg, exc_info=True)
                
                if reraise:
                    raise
                
                return return_on_error
        
        return cast(F, wrapper)
    
    return decorator


def track_performance(
    threshold_ms: Optional[float] = None,
    log_slow: bool = True
) -> Callable[[F], F]:
    """
    Decorator to track function execution time.
    
    Args:
        threshold_ms: Log warning if execution time exceeds this threshold (milliseconds)
        log_slow: Whether to log slow executions
    
    Returns:
        Decorated function with performance tracking
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            result = func(*args, **kwargs)
            execution_time = (time.time() - start_time) * 1000  # Convert to ms
            
            if threshold_ms and execution_time > threshold_ms and log_slow:
                # Get logger
                if args and hasattr(args[0], 'logger'):
                    logger = args[0].logger
                else:
                    logger = logging.getLogger(func.__module__)
                
                logger.warning(
                    f"{func.__name__} took {execution_time:.2f}ms "
                    f"(threshold: {threshold_ms}ms)"
                )
            
            # Store execution time if object has metrics
            if args and hasattr(args[0], '_performance_metrics'):
                if not hasattr(args[0]._performance_metrics, func.__name__):
                    args[0]._performance_metrics[func.__name__] = []
                args[0]._performance_metrics[func.__name__].append(execution_time)
            
            return result
        
        return cast(F, wrapper)
    
    return decorator


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Callable[[F], F]:
    """
    Decorator to retry function execution with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to retry on
    
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:
                        # Get logger
                        if args and hasattr(args[0], 'logger'):
                            logger = args[0].logger
                        else:
                            logger = logging.getLogger(func.__module__)
                        
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_attempts}), "
                            f"retrying in {current_delay:.1f}s: {str(e)}"
                        )
                        
                        time.sleep(current_delay)
                        current_delay *= backoff
            
            # All retries failed
            if last_exception:
                raise last_exception
        
        return cast(F, wrapper)
    
    return decorator


def validate_path(
    must_exist: bool = True,
    file_type: Optional[str] = None
) -> Callable[[F], F]:
    """
    Decorator to validate file/directory paths in function arguments.
    
    Args:
        must_exist: Whether the path must exist
        file_type: Expected file extension (e.g., '.mp3', '.json')
    
    Returns:
        Decorated function with path validation
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Check both positional and keyword arguments for paths
            all_args = list(args) + list(kwargs.values())
            
            for arg in all_args:
                if isinstance(arg, (str, Path)):
                    path = Path(arg)
                    
                    # Check if it looks like a path
                    if '/' in str(arg) or '\\' in str(arg) or '.' in str(arg):
                        if must_exist and not path.exists():
                            raise FileNotFoundError(f"Path does not exist: {path}")
                        
                        if file_type and path.suffix != file_type:
                            raise ValueError(
                                f"Invalid file type: expected {file_type}, "
                                f"got {path.suffix} for {path}"
                            )
            
            return func(*args, **kwargs)
        
        return cast(F, wrapper)
    
    return decorator


def deprecated(
    reason: str,
    version: Optional[str] = None,
    alternative: Optional[str] = None
) -> Callable[[F], F]:
    """
    Decorator to mark functions as deprecated.
    
    Args:
        reason: Reason for deprecation
        version: Version when deprecated
        alternative: Suggested alternative function/method
    
    Returns:
        Decorated function with deprecation warning
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            import warnings
            
            message = f"{func.__name__} is deprecated"
            if version:
                message += f" (since version {version})"
            message += f": {reason}"
            if alternative:
                message += f". Use {alternative} instead."
            
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)
        
        return cast(F, wrapper)
    
    return decorator