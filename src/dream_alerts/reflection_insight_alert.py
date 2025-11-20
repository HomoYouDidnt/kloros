"""
Reflection Insight alert method - surfaces autonomous thinking to user.

Queues insights from idle reflection for conversational presentation,
making KLoROS' background analysis visible and engaging.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from .alert_methods import AlertMethod, AlertResult, ImprovementAlert
import time


class ReflectionInsight:
    """Data structure for reflection insights."""

    def __init__(
        self,
        insight_id: str,
        title: str,
        content: str,
        phase: int,
        insight_type: str,
        confidence: float,
        keywords: List[str],
        detected_at: datetime
    ):
        self.insight_id = insight_id
        self.title = title
        self.content = content
        self.phase = phase
        self.insight_type = insight_type
        self.confidence = confidence
        self.keywords = keywords
        self.detected_at = detected_at

    def to_improvement_alert(self) -> ImprovementAlert:
        """Convert reflection insight to ImprovementAlert format."""
        # Determine urgency based on confidence and phase
        if self.confidence >= 0.8:
            urgency = "high"
        elif self.confidence >= 0.6:
            urgency = "medium"
        else:
            urgency = "low"

        # Determine risk level (reflection insights are low-risk)
        risk_level = "low"  # Insights are informational, not operational

        return ImprovementAlert(
            request_id=self.insight_id,
            description=f"{self.title}: {self.content}",
            component=f"reflection_phase_{self.phase}",
            expected_benefit=f"Increased awareness of {self.insight_type}",
            risk_level=risk_level,
            confidence=self.confidence,
            urgency=urgency,
            detected_at=self.detected_at
        )


class ReflectionInsightAlert(AlertMethod):
    """
    Queue reflection insights for conversational presentation.

    Makes KLoROS' autonomous thinking visible to the user by surfacing
    high-quality insights generated during idle reflection cycles.
    """

    def __init__(self, kloros_instance=None):
        """
        Initialize reflection insight alert method.

        Args:
            kloros_instance: Reference to KLoROS voice instance
        """
        self.kloros = kloros_instance
        self.pending_insights: List[ReflectionInsight] = []
        self.max_queue_size = 10  # Keep last 10 high-quality insights
        self.min_confidence_threshold = 0.6  # Only queue confident insights
        self.last_presentation = None

    def queue_reflection_insights(self, insights: List[Dict[str, Any]]) -> int:
        """
        Queue insights from reflection cycle.

        Args:
            insights: List of insight dictionaries from reflection system

        Returns:
            Number of insights successfully queued
        """
        queued_count = 0

        for insight_data in insights:
            try:
                # Create ReflectionInsight from dictionary
                insight = ReflectionInsight(
                    insight_id=f"insight_{int(time.time())}_{queued_count}",
                    title=insight_data.get('title', 'Reflection Insight'),
                    content=insight_data.get('content', ''),
                    phase=insight_data.get('phase', 1),
                    insight_type=insight_data.get('type', 'general'),
                    confidence=insight_data.get('confidence', 0.5),
                    keywords=insight_data.get('keywords', []),
                    detected_at=datetime.now()
                )

                # Filter by confidence threshold
                if insight.confidence < self.min_confidence_threshold:
                    continue

                # Check if duplicate
                if self._is_duplicate_insight(insight):
                    continue

                # Make room if needed
                if len(self.pending_insights) >= self.max_queue_size:
                    self._make_room_in_queue(insight)

                # Add to queue
                self.pending_insights.append(insight)
                queued_count += 1

                print(f"[reflection_alert] Queued insight: {insight.title} (confidence: {insight.confidence:.2f})")

            except Exception as e:
                print(f"[reflection_alert] Failed to queue insight: {e}")
                continue

        if queued_count > 0:
            print(f"[reflection_alert] Queue size: {len(self.pending_insights)}/{self.max_queue_size}")

        return queued_count

    def deliver_alert(self, alert: ImprovementAlert) -> AlertResult:
        """
        Deliver alert using reflection insight method.

        Note: This method receives ImprovementAlert format from alert manager.
        For reflection insights, prefer using queue_reflection_insights() directly.
        """
        # Queue as reflection insight
        if len(self.pending_insights) >= self.max_queue_size:
            return AlertResult(
                success=False,
                method="reflection_insight",
                error="Queue full",
                fallback_recommended=True
            )

        # Convert alert back to insight-like structure
        # (This path is used when alert manager routes general alerts)
        insight_data = {
            'title': alert.component,
            'content': alert.description,
            'phase': 1,
            'type': 'improvement',
            'confidence': alert.confidence,
            'keywords': []
        }

        queued = self.queue_reflection_insights([insight_data])

        return AlertResult(
            success=queued > 0,
            method="reflection_insight",
            delivery_time=datetime.now() if queued > 0 else None,
            awaiting_response=True,
            error=None if queued > 0 else "Failed to queue insight"
        )

    def can_deliver_now(self) -> bool:
        """Check if we can queue more insights."""
        return len(self.pending_insights) < self.max_queue_size

    def get_pending_for_presentation(self) -> List[ReflectionInsight]:
        """Get insights ready for next-wake presentation."""
        return self.pending_insights.copy()

    def mark_presented(self, insight_ids: List[str]) -> None:
        """Mark insights as presented to user."""
        self.pending_insights = [
            i for i in self.pending_insights
            if i.insight_id not in insight_ids
        ]
        self.last_presentation = datetime.now()

        print(f"[reflection_alert] Marked {len(insight_ids)} insights as presented")
        print(f"[reflection_alert] Remaining in queue: {len(self.pending_insights)}")

    def format_insight_message(self, insights: List[ReflectionInsight]) -> str:
        """
        Format insights for conversational presentation.

        Args:
            insights: List of insights to present

        Returns:
            Formatted message for user
        """
        if not insights:
            return ""

        if len(insights) == 1:
            insight = insights[0]
            return f"""I've been reflecting while idle, and I noticed something:

{insight.content}

This came from analyzing {insight.insight_type} patterns. I'm {int(insight.confidence * 100)}% confident about this observation."""

        else:
            # Multiple insights
            high_conf = [i for i in insights if i.confidence >= 0.8]

            message = f"I've been thinking while idle and have {len(insights)} observations to share."

            if high_conf:
                message += f" {len(high_conf)} of them are high-confidence findings."

            message += " Would you like to hear them?"

            return message

    def get_urgency_support(self) -> List[str]:
        """Reflection insights are never critical - they're informational."""
        return ["high", "medium", "low"]

    def get_queue_status(self) -> Dict[str, Any]:
        """Get status of reflection insight queue."""
        return {
            "pending_count": len(self.pending_insights),
            "max_size": self.max_queue_size,
            "min_confidence": self.min_confidence_threshold,
            "last_presentation": self.last_presentation.isoformat() if self.last_presentation else None,
            "insights": [
                {
                    "id": i.insight_id,
                    "type": i.insight_type,
                    "confidence": i.confidence,
                    "title": i.title
                }
                for i in self.pending_insights
            ]
        }

    def _is_duplicate_insight(self, new_insight: ReflectionInsight) -> bool:
        """Check if similar insight already exists in queue."""
        for existing in self.pending_insights:
            # Same type and similar title/content
            if existing.insight_type == new_insight.insight_type:
                # Simple similarity check
                title1_words = set(existing.title.lower().split())
                title2_words = set(new_insight.title.lower().split())

                if title1_words and title2_words:
                    overlap = len(title1_words & title2_words) / len(title1_words | title2_words)
                    if overlap > 0.7:
                        return True

                # Check content similarity
                content1_words = set(existing.content.lower().split()[:20])  # First 20 words
                content2_words = set(new_insight.content.lower().split()[:20])

                if content1_words and content2_words:
                    overlap = len(content1_words & content2_words) / len(content1_words | content2_words)
                    if overlap > 0.7:
                        return True

        return False

    def _make_room_in_queue(self, new_insight: ReflectionInsight) -> None:
        """Make room in queue for new insight by removing less confident/older ones."""
        # Remove lowest confidence insight
        if self.pending_insights:
            lowest_conf_insight = min(self.pending_insights, key=lambda i: i.confidence)

            # Only remove if new insight is more confident
            if new_insight.confidence > lowest_conf_insight.confidence:
                self.pending_insights.remove(lowest_conf_insight)
                print(f"[reflection_alert] Removed lower confidence insight to make room")
            else:
                # Remove oldest instead
                removed = self.pending_insights.pop(0)
                print(f"[reflection_alert] Removed oldest insight to make room")
