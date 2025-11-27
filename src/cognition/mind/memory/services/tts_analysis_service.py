"""
TTS analysis service for memory system.

Provides TTS output quality analysis and insight generation for
speech synthesis optimization.

This service wraps the TTSAnalyzer, centralizing TTS analysis
logic and exposing it through the UMN bus for agentic housekeeping.
"""

import logging
import time
from typing import Any, Dict, Optional

from src.orchestration.core.umn_bus import UMNSub, UMNPub

logger = logging.getLogger(__name__)

try:
    from tts.analysis import TTSAnalyzer
    HAS_TTS_ANALYZER = True
except ImportError:
    HAS_TTS_ANALYZER = False
    TTSAnalyzer = None


class TTSAnalysisService:
    """
    TTS analysis service for speech synthesis quality monitoring.

    Provides:
    - TTS output quality analysis
    - Improvement insights generation
    - Trend analysis and recommendations
    - Speech synthesis parameter optimization tracking

    Can operate as UMN subscriber for agentic housekeeping architecture.
    """

    def __init__(self):
        """
        Initialize TTS analysis service.
        """
        self._analyzer: Optional['TTSAnalyzer'] = None

        self._umn_sub: Optional[UMNSub] = None
        self._umn_pub: Optional[UMNPub] = None

    @property
    def analyzer(self) -> 'TTSAnalyzer':
        """Lazy-load TTS analyzer."""
        if self._analyzer is None and HAS_TTS_ANALYZER:
            self._analyzer = TTSAnalyzer()
        return self._analyzer

    def subscribe_to_umn(self) -> None:
        """Subscribe to UMN for agentic housekeeping."""
        self._umn_pub = UMNPub()
        self._umn_sub = UMNSub(
            topic="Q_HOUSEKEEPING.TTS_ANALYSIS",
            on_json=self._handle_analysis_request,
            zooid_name="tts_analysis_service",
            niche="memory"
        )
        logger.info("[tts_analysis] Subscribed to Q_HOUSEKEEPING.TTS_ANALYSIS")

    def _handle_analysis_request(self, msg: dict) -> None:
        """Handle UMN request for TTS analysis."""
        request_id = msg.get('request_id', 'unknown')

        try:
            results = self.analyze_tts_quality()

            self._umn_pub.emit(
                signal="Q_HOUSEKEEPING.TTS_ANALYSIS.COMPLETE",
                ecosystem="memory",
                facts={
                    'request_id': request_id,
                    'success': True,
                    'results': results
                }
            )

        except Exception as e:
            logger.error(f"[tts_analysis] Error during analysis: {e}", exc_info=True)
            if self._umn_pub:
                self._umn_pub.emit(
                    signal="Q_HOUSEKEEPING.TTS_ANALYSIS.COMPLETE",
                    ecosystem="memory",
                    facts={
                        'request_id': request_id,
                        'success': False,
                        'error': str(e)
                    }
                )

    def analyze_tts_quality(self) -> Dict[str, Any]:
        """
        Analyze TTS output quality and generate improvement insights.

        Performs passive analysis of generated TTS files to identify quality
        issues and optimization opportunities for speech synthesis.

        Returns:
            Dictionary with analysis results:
            - analysis_performed: bool, whether analysis was executed
            - files_analyzed: int, number of TTS files analyzed
            - quality_score: float, overall quality metric (0-1)
            - quality_metrics: dict, detailed quality measurements
            - insights_generated: int, count of improvement insights
            - improvement_insights: list, detailed insight objects
            - trend_analysis: dict, quality trends over time
            - recommendations: list, optimization recommendations
            - errors: list, any errors encountered during analysis
        """
        if not HAS_TTS_ANALYZER or self.analyzer is None:
            logger.warning("[tts_analysis] TTSAnalyzer not available")
            return {
                "analysis_performed": False,
                "files_analyzed": 0,
                "quality_score": 0.0,
                "quality_metrics": {},
                "insights_generated": 0,
                "improvement_insights": [],
                "trend_analysis": {},
                "recommendations": [],
                "errors": ["TTSAnalyzer module not available"]
            }

        results = {
            "analysis_performed": False,
            "files_analyzed": 0,
            "quality_score": 0.0,
            "quality_metrics": {},
            "insights_generated": 0,
            "improvement_insights": [],
            "trend_analysis": {},
            "recommendations": [],
            "errors": []
        }

        start_time = time.time()

        try:
            # Perform TTS analysis
            analysis_results = self.analyzer.analyze_recent_tts_outputs()

            # Mark as performed
            results["analysis_performed"] = True

            # Extract files analyzed
            results["files_analyzed"] = analysis_results.get("files_analyzed", 0)

            # Extract quality metrics
            quality_metrics = analysis_results.get("quality_metrics", {})
            results["quality_metrics"] = quality_metrics

            if quality_metrics:
                results["quality_score"] = quality_metrics.get("overall_quality_mean", 0.0)

            # Extract improvement insights
            insights = analysis_results.get("improvement_insights", [])
            results["improvement_insights"] = insights
            results["insights_generated"] = len(insights)

            # Extract trend analysis
            results["trend_analysis"] = analysis_results.get("trend_analysis", {})

            # Extract recommendations
            results["recommendations"] = analysis_results.get("recommendations", [])

            # Extract errors
            results["errors"] = analysis_results.get("errors", [])

            if results["files_analyzed"] > 0:
                logger.info(
                    f"[tts_analysis] Analysis complete: {results['files_analyzed']} files, "
                    f"quality {results['quality_score']:.3f}"
                )
            else:
                logger.info("[tts_analysis] Insufficient files for analysis")

        except Exception as e:
            logger.error(f"[tts_analysis] Error analyzing TTS quality: {e}", exc_info=True)
            results["errors"].append(str(e))

        finally:
            results["analysis_time_seconds"] = time.time() - start_time

        return results

    def get_quality_metrics(self) -> Dict[str, Any]:
        """
        Get current TTS quality metrics without full analysis.

        Returns:
            Dictionary with quality metrics or empty dict if unavailable
        """
        if not HAS_TTS_ANALYZER or self.analyzer is None:
            logger.warning("[tts_analysis] TTSAnalyzer not available")
            return {}

        try:
            analysis_results = self.analyzer.analyze_recent_tts_outputs()
            return analysis_results.get("quality_metrics", {})
        except Exception as e:
            logger.error(f"[tts_analysis] Error getting quality metrics: {e}", exc_info=True)
            return {}

    def get_recommendations(self) -> list:
        """
        Get current TTS optimization recommendations.

        Returns:
            List of recommendation strings
        """
        if not HAS_TTS_ANALYZER or self.analyzer is None:
            logger.warning("[tts_analysis] TTSAnalyzer not available")
            return []

        try:
            analysis_results = self.analyzer.analyze_recent_tts_outputs()
            return analysis_results.get("recommendations", [])
        except Exception as e:
            logger.error(f"[tts_analysis] Error getting recommendations: {e}", exc_info=True)
            return []

    def shutdown(self) -> None:
        """Close UMN subscriptions."""
        if self._umn_sub:
            self._umn_sub.close()
            logger.info("[tts_analysis] Closed UMN subscription")
