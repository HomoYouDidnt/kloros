#!/usr/bin/env python3
"""
Library Exploration Monitor - Generates curiosity questions about knowledge library content.

Purpose:
    Enable KLoROS to autonomously explore and learn from the knowledge library
    by generating questions about interesting topics in the indexed library.
"""

import logging
import random
from pathlib import Path
from typing import List, Any, Dict
import sys

sys.path.insert(0, '/home/kloros/src')

try:
    from src.cognition.mind.memory.kosmos import get_kosmos
except ImportError:
    get_kosmos = None

logger = logging.getLogger(__name__)


class LibraryExplorationMonitor:
    """
    Monitor that generates curiosity questions about library content for autonomous learning.
    
    Works with KOSMOS to identify interesting library topics and generate exploration questions.
    """
    
    def __init__(self, lineage_path: Path = Path("/home/kloros/.kloros/knowledge_lineage.jsonl")):
        self.lineage_path = lineage_path
        self.kosmos = None
        
        # Initialize KOSMOS connection
        if get_kosmos:
            try:
                self.kosmos = get_kosmos()
                logger.debug("[library_exploration] KOSMOS connection established")
            except Exception as e:
                logger.warning(f"[library_exploration] Failed to connect to KOSMOS: {e}")
    
    def generate_library_exploration_questions(self, max_questions: int = 3) -> List[Any]:
        """
        Generate curiosity questions about library content.
        
        Returns:
            List of CuriosityQuestion objects about library topics
        """
        if not self.kosmos:
            logger.warning("[library_exploration] KOSMOS not available, skipping library questions")
            return []
        
        questions = []
        
        # Define exploration themes that map to library sections
        themes = [
            ("first principles thinking", "01_Core_Methods/problem_solving", 0.8),
            ("systems thinking leverage points", "01_Core_Methods/thinking_frameworks", 0.7),
            ("CAP theorem distributed systems", "03_Systems_Architecture", 0.75),
            ("cognitive biases decision making", "06_Cognition_Psychology", 0.7),
            ("evolutionary algorithms optimization", "07_Cross_Pollination/biology", 0.65),
            ("software failures postmortems", "04_Failures_Postmortems", 0.8),
            ("clean code patterns", "05_Datasets_Examples", 0.6),
        ]
        
        # Randomly select themes for exploration (prevents always asking the same questions)
        selected_themes = random.sample(themes, min(max_questions, len(themes)))
        
        for query, section, value_estimate in selected_themes:
            try:
                # Query KOSMOS to see if we have content on this topic
                results = self.kosmos.search_knowledge(query, top_k=1)
                
                if not results:
                    continue
                
                result = results[0]
                file_name = Path(result['file_path']).name
                similarity = result['similarity']
                
                # Only generate question if similarity is high (we actually have good content)
                if similarity < 0.5:
                    continue
                
                # Import here to avoid circular dependency
                try:
                    from src.cognition.mind.cognition.curiosity_core import CuriosityQuestion, ActionClass, QuestionStatus
                except ImportError:
                    logger.warning("[library_exploration] Cannot import CuriosityQuestion, skipping")
                    return []
                
                # Generate exploration question
                question_text = f"What can I learn from '{file_name}' about {query}?"
                hypothesis = f"LIBRARY_LEARNING_{query.upper().replace(' ', '_')}"
                
                evidence = [
                    f"library_file:{file_name}",
                    f"topic:{query}",
                    f"similarity:{similarity:.3f}",
                    f"section:{section}",
                    f"summary_preview:{result.get('summary', '')[:100]}"
                ]
                
                q = CuriosityQuestion(
                    id=f"library.explore.{file_name.replace('.md', '')}",
                    hypothesis=hypothesis,
                    question=question_text,
                    evidence=evidence,
                    action_class=ActionClass.INVESTIGATE,
                    autonomy=2,  # Low autonomy - learning, not critical
                    value_estimate=value_estimate,
                    cost=0.1,  # Low cost - just reading/learning
                    status=QuestionStatus.READY,
                    capability_key=f"knowledge.{section}"
                )
                
                questions.append(q)
                logger.info(f"[library_exploration] Generated question about {file_name} (sim={similarity:.3f})")
                
            except Exception as e:
                logger.warning(f"[library_exploration] Failed to generate question for '{query}': {e}")
                continue
        
        logger.info(f"[library_exploration] Generated {len(questions)} library exploration questions")
        return questions


def main():
    """Test the library exploration monitor."""
    logging.basicConfig(level=logging.INFO)
    
    monitor = LibraryExplorationMonitor()
    questions = monitor.generate_library_exploration_questions(max_questions=3)
    
    print(f"\n=== Generated {len(questions)} Library Exploration Questions ===\n")
    for q in questions:
        print(f"Question: {q.question}")
        print(f"  Hypothesis: {q.hypothesis}")
        print(f"  Value: {q.value_estimate}")
        print(f"  Evidence: {len(q.evidence)} items")
        print()


if __name__ == "__main__":
    main()
