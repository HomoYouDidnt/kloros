"""
Voice Style Corpus

Provides access to tone-labeled speech samples for style guidance,
delivery patterns, and emotional expression reference.

Primary corpus: GLaDOS voice lines from Portal series
- 1,893 labeled samples
- Tone categories: deadpan, sarcastic, inquisitive, cheerful, threatening,
  annoyed, contemptuous, taunting, directive, error/system
"""

from .corpus import StyleCorpus, ToneCategory, StyleExample

__all__ = ["StyleCorpus", "ToneCategory", "StyleExample"]
