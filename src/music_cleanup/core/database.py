"""
Database Manager for DJ Music Cleanup Tool
Provides centralized database management with connection pooling,
thread safety, and WAL mode for better concurrent access.
"""

import sqlite3
import threading
import logging
import queue
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union
from contextlib import contextmanager
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Wrapper for SQLite connection with usage tracking"""
    
    def __init__(self, connection: sqlite3.Connection, pool: 'ConnectionPool'):
        self.connection = connection
        self.pool = pool
        self.in_use = False
        self.last_used = time.time()
        self.created_at = time.time()
        
    def execute(self, query: str, params: Optional[Tuple] = None) -> sqlite3.Cursor:
        """Execute a query with optional parameters"""
        if params:
            return self.connection.execute(query, params)
        return self.connection.execute(query)
    
    def executemany(self, query: str, params: List[Tuple]) -> sqlite3.Cursor:
        """Execute a query multiple times with different parameters"""
        return self.connection.executemany(query, params)
    
    def commit(self):
        """Commit the current transaction"""
        self.connection.commit()
        
    def rollback(self):
        """Rollback the current transaction"""
        self.connection.rollback()
        
    def close(self):
        """Return connection to pool instead of closing"""
        self.pool.return_connection(self)


class ConnectionPool:
    """Thread-safe connection pool for SQLite"""
    
    def __init__(self, db_path: Path, pool_size: int = 5, enable_wal: bool = True):
        self.db_path = db_path
        self.pool_size = pool_size
        self.enable_wal = enable_wal
        self._connections = queue.Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._created_connections = 0
        self._initialize_pool()
        
    def _initialize_pool(self):
        """Initialize the connection pool"""
        # Create at least one connection to set up WAL mode
        conn = self._create_connection()
        self._connections.put(conn)
        
    def _create_connection(self) -> DatabaseConnection:
        """Create a new database connection"""
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30.0
        )
        
        # Enable WAL mode for better concurrent access
        if self.enable_wal:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys=ON")
        
        # Set row factory for dict-like access
        conn.row_factory = sqlite3.Row
        
        self._created_connections += 1
        return DatabaseConnection(conn, self)
        
    def get_connection(self, timeout: float = 5.0) -> DatabaseConnection:
        """Get a connection from the pool"""
        try:
            # Try to get existing connection
            conn = self._connections.get(timeout=timeout)
            conn.in_use = True
            conn.last_used = time.time()
            return conn
        except queue.Empty:
            # Create new connection if pool not full
            with self._lock:
                if self._created_connections < self.pool_size:
                    conn = self._create_connection()
                    conn.in_use = True
                    return conn
            raise RuntimeError("Connection pool exhausted")
            
    @contextmanager
    def get_connection_context(self, timeout: float = 5.0):
        """Context manager for getting a connection"""
        conn = self.get_connection(timeout)
        try:
            yield conn
        finally:
            conn.close()
            
    def return_connection(self, conn: DatabaseConnection):
        """Return a connection to the pool"""
        conn.in_use = False
        conn.last_used = time.time()
        try:
            self._connections.put_nowait(conn)
        except queue.Full:
            # Pool is full, close the connection
            conn.connection.close()
            with self._lock:
                self._created_connections -= 1
                
    def close_all(self):
        """Close all connections in the pool"""
        while not self._connections.empty():
            try:
                conn = self._connections.get_nowait()
                conn.connection.close()
            except queue.Empty:
                break
                

class DatabaseManager:
    """
    Centralized database manager for the DJ Music Cleanup Tool.
    Manages multiple databases with connection pooling and thread safety.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance
        
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._pools: Dict[str, ConnectionPool] = {}
            self._db_configs: Dict[str, Dict[str, Any]] = {
                'fingerprints': {
                    'filename': 'fingerprints.db',
                    'pool_size': 5
                },
                'operations': {
                    'filename': 'file_operations.db',
                    'pool_size': 3
                },
                'progress': {
                    'filename': 'progress.db',
                    'pool_size': 2
                }
            }
            self._base_path = Path.cwd()
            
    def set_base_path(self, path: Union[str, Path]):
        """Set the base path for database files"""
        self._base_path = Path(path)
        self._base_path.mkdir(parents=True, exist_ok=True)
        
    def initialize_database(self, db_name: str, schema_func: Optional[callable] = None):
        """Initialize a database with its schema"""
        if db_name not in self._db_configs:
            raise ValueError(f"Unknown database: {db_name}")
            
        config = self._db_configs[db_name]
        db_path = self._base_path / config['filename']
        
        # Create connection pool
        pool = ConnectionPool(db_path, config['pool_size'])
        self._pools[db_name] = pool
        
        # Initialize schema if provided
        if schema_func:
            with self.get_connection(db_name) as conn:
                schema_func(conn)
                conn.commit()
                
        logger.info(f"Initialized database: {db_name} at {db_path}")
        
    @contextmanager
    def get_connection(self, db_name: str) -> DatabaseConnection:
        """Get a database connection from the pool"""
        if db_name not in self._pools:
            raise ValueError(f"Database not initialized: {db_name}")
            
        conn = self._pools[db_name].get_connection()
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error in {db_name}: {e}")
            raise
        finally:
            conn.close()  # Returns to pool
            
    def execute_query(self, db_name: str, query: str, 
                     params: Optional[Union[Tuple, Dict]] = None) -> List[sqlite3.Row]:
        """Execute a SELECT query and return results"""
        with self.get_connection(db_name) as conn:
            cursor = conn.execute(query, params or ())
            return cursor.fetchall()
            
    def execute_update(self, db_name: str, query: str, 
                      params: Optional[Union[Tuple, Dict]] = None) -> int:
        """Execute an INSERT/UPDATE/DELETE query and return affected rows"""
        with self.get_connection(db_name) as conn:
            cursor = conn.execute(query, params or ())
            conn.commit()
            return cursor.rowcount
            
    def execute_many(self, db_name: str, query: str, 
                    params_list: List[Union[Tuple, Dict]]) -> int:
        """Execute a query multiple times with different parameters"""
        with self.get_connection(db_name) as conn:
            cursor = conn.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount
            
    @contextmanager
    def transaction(self, db_name: str):
        """Context manager for database transactions"""
        with self.get_connection(db_name) as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
                
    def backup_database(self, db_name: str, backup_path: Union[str, Path]):
        """Create a backup of a database"""
        if db_name not in self._pools:
            raise ValueError(f"Database not initialized: {db_name}")
            
        backup_path = Path(backup_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self.get_connection(db_name) as conn:
            backup_conn = sqlite3.connect(str(backup_path))
            conn.connection.backup(backup_conn)
            backup_conn.close()
            
        logger.info(f"Backed up {db_name} to {backup_path}")
        
    def vacuum_database(self, db_name: str):
        """Vacuum a database to reclaim space"""
        with self.get_connection(db_name) as conn:
            conn.execute("VACUUM")
            
    def analyze_database(self, db_name: str):
        """Update database statistics for query optimization"""
        with self.get_connection(db_name) as conn:
            conn.execute("ANALYZE")
            
    def get_table_info(self, db_name: str, table_name: str) -> List[Dict[str, Any]]:
        """Get information about a table's columns"""
        query = f"PRAGMA table_info({table_name})"
        rows = self.execute_query(db_name, query)
        
        return [
            {
                'cid': row['cid'],
                'name': row['name'],
                'type': row['type'],
                'notnull': bool(row['notnull']),
                'default': row['dflt_value'],
                'primary_key': bool(row['pk'])
            }
            for row in rows
        ]
        
    def table_exists(self, db_name: str, table_name: str) -> bool:
        """Check if a table exists in the database"""
        query = """
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name=?
        """
        result = self.execute_query(db_name, query, (table_name,))
        return len(result) > 0
        
    def close_all(self):
        """Close all database connections"""
        for pool in self._pools.values():
            pool.close_all()
        self._pools.clear()
        logger.info("Closed all database connections")
        
    def __del__(self):
        """Cleanup when the manager is destroyed"""
        if hasattr(self, '_pools'):
            self.close_all()


# Convenience function for getting the singleton instance
def get_database_manager() -> DatabaseManager:
    """Get the singleton DatabaseManager instance"""
    return DatabaseManager()