"""
DEPRECATED: Use orchestrator_refactored.py instead.

This file remains for backward compatibility but should not be modified.
The main orchestrator has been split into specialized modules:
- PipelineExecutor: Main workflow coordination
- BatchProcessor: Memory-efficient batch processing  
- CorruptionHandler: Phase 2.5 corruption filtering
- DuplicateHandler: Phase 3 duplicate detection on healthy files only

KRITISCH: Corruption filter runs BEFORE duplicate detection!
"""

import logging
from .orchestrator_refactored import MusicCleanupOrchestrator as _RefactoredOrchestrator

# Import the refactored version for backward compatibility
class MusicCleanupOrchestrator(_RefactoredOrchestrator):
    """Backward compatibility wrapper for the refactored orchestrator."""
    pass