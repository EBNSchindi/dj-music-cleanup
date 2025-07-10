"""
Quality-Based Rejection Handler for DJ Music Cleanup Tool

Handles rejection of files based on quality scores and thresholds.
Integrates with the RejectedHandler to move low-quality files instead of deleting them.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from .rejected_handler import RejectedHandler
from ..utils.decorators import handle_errors, track_performance


class QualityRejectionHandler:
    """
    Handles quality-based file rejection using configurable thresholds.
    
    Features:
    - Quality score-based rejection
    - Configurable thresholds for different use cases
    - Integration with rejection manifest system
    - Preserves files instead of deleting them
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize quality rejection handler.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Quality configuration
        self.quality_config = config.get('quality', {})
        self.min_quality_score = self.quality_config.get('min_score', 70)
        self.always_keep_best = self.quality_config.get('always_keep_best', True)
        self.auto_reject_below = self.quality_config.get('auto_reject_below', 50)
        self.production_threshold = self.quality_config.get('production_threshold', 85)
        
        # Organization config for context
        self.organization_config = config.get('organization', {})
        
        # Initialize rejected handler
        self.rejected_handler = RejectedHandler(config)
        
        # Statistics
        self.stats = {
            'files_analyzed': 0,
            'files_rejected': 0,
            'files_kept': 0,
            'total_space_freed': 0
        }
        
        self.logger.info(f"QualityRejectionHandler initialized")
        self.logger.info(f"  Min quality score: {self.min_quality_score}")
        self.logger.info(f"  Auto-reject below: {self.auto_reject_below}")
        self.logger.info(f"  Production threshold: {self.production_threshold}")
    
    @handle_errors(log_level="error")
    @track_performance(threshold_ms=10000)
    def filter_by_quality(self, files: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Filter files based on quality scores.
        
        Args:
            files: List of file information dictionaries with quality scores
            
        Returns:
            Tuple of (kept_files, rejected_files)
        """
        kept_files = []
        rejected_files = []
        
        self.logger.info(f"🎯 Filtering {len(files)} files by quality (threshold: {self.min_quality_score})")
        
        for file_info in files:
            quality_score = self._get_quality_score(file_info)
            
            if quality_score is None:
                # No quality score available, keep file but log warning
                self.logger.warning(f"No quality score for: {Path(file_info['file_path']).name}")
                kept_files.append(file_info)
                continue
            
            # Update file info with normalized quality score
            file_info['quality_score'] = quality_score
            
            if self._should_reject_file(file_info, quality_score):
                rejected_files.append(file_info)
                self.logger.debug(f"Rejected low quality: {Path(file_info['file_path']).name} (QS: {quality_score:.1f})")
            else:
                kept_files.append(file_info)
            
            self.stats['files_analyzed'] += 1
        
        # Handle rejected files
        if rejected_files:
            self._handle_rejected_files(rejected_files)
        
        self.stats['files_kept'] = len(kept_files)
        self.stats['files_rejected'] = len(rejected_files)
        
        self.logger.info(f"🎯 Quality filtering results:")
        self.logger.info(f"   Files kept: {len(kept_files)}")
        self.logger.info(f"   Files rejected: {len(rejected_files)}")
        
        return kept_files, rejected_files
    
    def _get_quality_score(self, file_info: Dict[str, Any]) -> Optional[float]:
        """
        Extract or calculate quality score for a file.
        
        Args:
            file_info: File information dictionary
            
        Returns:
            Quality score as float, or None if not available
        """
        # Try different possible quality score fields
        quality_fields = ['quality_score', 'overall_score', 'calculated_score', 'final_score']
        
        for field in quality_fields:
            if field in file_info and file_info[field] is not None:
                return float(file_info[field])
        
        # Try to calculate basic quality score from available info
        if 'bitrate' in file_info:
            bitrate = file_info['bitrate']
            if bitrate:
                # Simple quality estimation: normalize bitrate to 0-100 scale
                # Assume 320 kbps = 100%, 128 kbps = 40%, etc.
                normalized_score = min(100.0, (bitrate / 320.0) * 100.0)
                return normalized_score
        
        return None
    
    def _should_reject_file(self, file_info: Dict[str, Any], quality_score: float) -> bool:
        """
        Determine if a file should be rejected based on quality.
        
        Args:
            file_info: File information dictionary
            quality_score: Quality score of the file
            
        Returns:
            True if file should be rejected, False otherwise
        """
        # Auto-reject extremely low quality files
        if quality_score < self.auto_reject_below:
            return True
        
        # Check against minimum threshold
        if quality_score < self.min_quality_score:
            # If always_keep_best is enabled, we might keep some low-quality files
            # if they are the only version available (this would be handled upstream)
            return True
        
        # Additional rejection criteria
        
        # Check file format preferences
        file_path = Path(file_info['file_path'])
        extension = file_path.suffix.lower()
        
        # Prefer lossless formats - reject low-quality lossy when lossless available
        if extension in ['.mp3', '.aac', '.ogg'] and quality_score < self.production_threshold:
            # This would typically be handled by duplicate detection,
            # but we can flag for additional review
            pass
        
        # Check duration - very short files are usually poor quality
        duration = file_info.get('duration', 0)
        if duration < 30:  # Less than 30 seconds
            return True
        
        return False
    
    def _handle_rejected_files(self, rejected_files: List[Dict[str, Any]]) -> None:
        """
        Handle rejected files by moving them using the rejection system.
        
        Args:
            rejected_files: List of rejected file information
        """
        for file_info in rejected_files:
            try:
                quality_score = file_info.get('quality_score', 0)
                
                # Extract metadata if available
                metadata = {
                    'artist': file_info.get('artist'),
                    'title': file_info.get('title'),
                    'year': file_info.get('year'),
                    'genre': file_info.get('genre')
                }
                
                # Move file using rejection system
                rejected_path = self.rejected_handler.reject_low_quality(
                    file_path=file_info['file_path'],
                    quality_score=quality_score,
                    metadata=metadata
                )
                
                if rejected_path:
                    file_size = file_info.get('file_size', 0)
                    self.stats['total_space_freed'] += file_size
                    
                    self.logger.debug(f"Moved low quality file: {Path(file_info['file_path']).name}")
                
            except Exception as e:
                self.logger.error(f"Error handling rejected file {file_info['file_path']}: {e}")
                continue
    
    def process_quality_analysis(self, files: List[Dict[str, Any]], 
                                context: str = "general") -> Dict[str, Any]:
        """
        Process quality analysis for a set of files with context.
        
        Args:
            files: List of file information dictionaries
            context: Context for quality analysis (e.g., "duplicates", "general", "production")
            
        Returns:
            Dictionary with analysis results
        """
        results = {
            'context': context,
            'total_files': len(files),
            'quality_distribution': {},
            'recommendations': [],
            'files_processed': []
        }
        
        # Analyze quality distribution
        quality_ranges = {
            'excellent': (90, 100),
            'good': (75, 89),
            'acceptable': (60, 74),
            'poor': (40, 59),
            'unacceptable': (0, 39)
        }
        
        distribution = {category: 0 for category in quality_ranges.keys()}
        
        for file_info in files:
            quality_score = self._get_quality_score(file_info)
            
            if quality_score is not None:
                # Categorize quality
                category = 'unacceptable'
                for cat, (min_score, max_score) in quality_ranges.items():
                    if min_score <= quality_score <= max_score:
                        category = cat
                        break
                
                distribution[category] += 1
                
                # Store processed file info
                results['files_processed'].append({
                    'file_path': file_info['file_path'],
                    'quality_score': quality_score,
                    'category': category,
                    'recommended_action': self._get_recommended_action(quality_score, context)
                })
        
        results['quality_distribution'] = distribution
        
        # Generate recommendations based on context
        results['recommendations'] = self._generate_quality_recommendations(distribution, context)
        
        return results
    
    def _get_recommended_action(self, quality_score: float, context: str) -> str:
        """
        Get recommended action for a file based on quality and context.
        
        Args:
            quality_score: Quality score of the file
            context: Processing context
            
        Returns:
            Recommended action string
        """
        if context == "production" and quality_score < self.production_threshold:
            return "Consider upgrading to higher quality version"
        elif quality_score < self.auto_reject_below:
            return "Reject - extremely low quality"
        elif quality_score < self.min_quality_score:
            return "Reject - below minimum threshold"
        elif quality_score < 75:
            return "Keep but flag for review"
        else:
            return "Keep - good quality"
    
    def _generate_quality_recommendations(self, distribution: Dict[str, int], 
                                        context: str) -> List[str]:
        """
        Generate quality-based recommendations.
        
        Args:
            distribution: Quality distribution dictionary
            context: Processing context
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        total_files = sum(distribution.values())
        if total_files == 0:
            return ["No files to analyze"]
        
        # Calculate percentages
        poor_percentage = (distribution['poor'] + distribution['unacceptable']) / total_files * 100
        excellent_percentage = distribution['excellent'] / total_files * 100
        
        if poor_percentage > 20:
            recommendations.append(f"⚠️ {poor_percentage:.1f}% of files have poor quality - consider re-acquiring from better sources")
        
        if excellent_percentage < 30 and context == "production":
            recommendations.append("🎯 Consider upgrading more files to excellent quality for professional use")
        
        if distribution['unacceptable'] > 0:
            recommendations.append(f"🚫 {distribution['unacceptable']} files have unacceptable quality and should be rejected")
        
        if distribution['acceptable'] > distribution['good'] + distribution['excellent']:
            recommendations.append("📈 Most files are only 'acceptable' quality - room for improvement")
        
        return recommendations
    
    def get_quality_stats(self) -> Dict[str, Any]:
        """Get quality rejection statistics"""
        return {
            **self.stats,
            'rejection_rate': round(self.stats['files_rejected'] / max(self.stats['files_analyzed'], 1) * 100, 1),
            'space_freed_mb': round(self.stats['total_space_freed'] / (1024 * 1024), 2),
            'thresholds': {
                'min_score': self.min_quality_score,
                'auto_reject_below': self.auto_reject_below,
                'production_threshold': self.production_threshold
            }
        }
    
    def reset_stats(self) -> None:
        """Reset statistics"""
        self.stats = {key: 0 for key in self.stats.keys()}
    
    def update_thresholds(self, min_score: Optional[float] = None,
                         auto_reject_below: Optional[float] = None,
                         production_threshold: Optional[float] = None) -> None:
        """
        Update quality thresholds dynamically.
        
        Args:
            min_score: New minimum quality score
            auto_reject_below: New auto-reject threshold
            production_threshold: New production threshold
        """
        if min_score is not None:
            self.min_quality_score = min_score
            
        if auto_reject_below is not None:
            self.auto_reject_below = auto_reject_below
            
        if production_threshold is not None:
            self.production_threshold = production_threshold
        
        self.logger.info(f"Updated quality thresholds:")
        self.logger.info(f"  Min score: {self.min_quality_score}")
        self.logger.info(f"  Auto-reject below: {self.auto_reject_below}")
        self.logger.info(f"  Production threshold: {self.production_threshold}")