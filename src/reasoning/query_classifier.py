"""Query classification for RAG retrieval gating.

Determines whether a query should use RAG retrieval or skip it.
"""

import re
from typing import Tuple


# Conversational patterns that don't need RAG retrieval
CONVERSATIONAL_PATTERNS = [
    # Greetings
    r"^(hi|hello|hey|howdy|greetings)(\s|$)",
    r"^(good\s+(morning|afternoon|evening|day))(\s|$)",
    
    # How are you
    r"^how\s+(are|r)\s+you",
    r"^how('s|s)?\s+it\s+going",
    r"^what('s|s)?\s+up",
    
    # Simple acknowledgments
    r"^(okay|ok|alright|fine|sure|yes|yeah|yep|yup|no|nope)(\s|$)",
    r"^(thanks|thank\s+you|thx)(\s|$)",
    
    # Simple requests
    r"^(please|can\s+you|could\s+you|would\s+you)(\s|$)",
    
    # Status checks (conversational, not diagnostic)
    r"^(you\s+there|are\s+you\s+there|listening)(\?)?$",
]

# Factual question patterns that benefit from RAG
FACTUAL_PATTERNS = [
    # Question words
    r"\b(what|when|where|which|who|whom|whose|why)\s+",
    r"\b(how\s+does|how\s+do|how\s+can|how\s+to)\s+",
    r"\b(tell\s+me\s+about|explain|describe|define)\s+",
    
    # Information requests
    r"\b(show|list|display|get|find|search)\s+",
    r"\b(status|diagnostic|check|test|verify)\s+",
]


def classify_query(query: str, conversation_history: list = None) -> Tuple[str, bool]:
    """Classify query as conversational or factual.

    Args:
        query: User query text
        conversation_history: Optional list of recent conversation turns for context

    Returns:
        Tuple of (query_type, should_use_rag)
        query_type: "conversational", "factual", "introspective", "nonsense", or "ambiguous"
        should_use_rag: True if RAG retrieval recommended
    """
    if not query or not query.strip():
        return ("empty", False)

    normalized = query.strip().lower()

    # Context-aware classification: if we're in mid-conversation,
    # confirmations/acknowledgments should NOT trigger canned responses
    in_conversation = conversation_history and len(conversation_history) > 0

    # Detect nonsense/gibberish queries - low semantic coherence
    words = normalized.split()
    if len(words) >= 3:
        # Check for too many filler words (expanded to catch echo fragments)
        filler_words = {
            'yes', 'yeah', 'yep', 'yup', 'no', 'nope',
            'oh', 'um', 'uh', 'er', 'ah',
            'like', 'you', 'i', 'me', 'my', 'your',
            'please', 'sir', 'ma\'am',
            'just', 'really', 'very', 'so',
            'the', 'a', 'an'
        }
        filler_count = sum(1 for w in words if w in filler_words)

        # If >60% filler words, likely nonsense (lowered from 70% to catch more)
        if filler_count / len(words) > 0.6:
            return ("nonsense", False)

    # Detect echo fragments (common TTS feedback patterns)
    echo_patterns = [
        r'^(yeah|yes|yep|yup)\s+(i|you)\s+(don\'t|didn\'t|can\'t|couldn\'t)\s+hear',
        r'^(i|you)\s+(don\'t|didn\'t|can\'t|couldn\'t)\s+(hear|see|understand)',
        r'^(what|huh|eh)\s*\??$',
        r'^(repeat|say\s+that|come\s+again)',
    ]

    for pattern in echo_patterns:
        if re.search(pattern, normalized, re.IGNORECASE):
            return ("nonsense", False)
    
    # Check conversational patterns first (higher priority)
    # BUT: Don't classify as conversational if query contains substantive content
    # OR if we're in the middle of a conversation (context-aware fix)
    has_substantive_content = any(keyword in normalized for keyword in [
        'status', 'report', 'check', 'show', 'list', 'tell', 'what',
        'when', 'where', 'why', 'who', 'how', 'system', 'audio',
        'diagnostic', 'error', 'problem', 'help', 'can you', 'could you',
        # Command keywords (fixes "please start the voice service" being classified as conversational)
        'start', 'stop', 'restart', 'enable', 'disable', 'initiate', 'terminate',
        'launch', 'kill', 'run', 'execute', 'activate', 'deactivate',
        'voice', 'service', 'server', 'process', 'daemon', 'agent'
    ])

    if not has_substantive_content and not in_conversation:
        for pattern in CONVERSATIONAL_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                return ("conversational", False)
    
    # Check for introspective/system queries (should route to tools, not RAG hallucination)
    introspective_keywords = [
        'memory', 'chromadb', 'sqlite', 'database', 'chroma',
        'system status', 'how are you', 'how is your',
        'functioning', 'working correctly', 'working as expected',
        'embeddings', 'collections', 'voice samples', 'samples stored'
    ]
    if any(keyword in normalized for keyword in introspective_keywords):
        return ("introspective", True)

    # Check factual patterns
    for pattern in FACTUAL_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return ("factual", True)
    
    # Override: tool-related queries should use RAG regardless of length (CRITICAL FIX)
    tool_keywords = ['tool', 'create', 'investigate', 'implement', 'build', 'make', 'develop', 'generate']
    if any(keyword in normalized for keyword in tool_keywords):
        return ("factual", True)
    
    # Default: short queries (< 5 words) are likely conversational
    # UNLESS we're in mid-conversation OR have substantive content (context-aware fix)
    word_count = len(normalized.split())
    if word_count < 5 and not in_conversation and not has_substantive_content:
        return ("conversational", False)
    
    # Longer queries benefit from RAG context
    return ("ambiguous", True)


def should_retrieve_rag(query: str, threshold: str = "medium") -> bool:
    """Determine if query should use RAG retrieval.
    
    Args:
        query: User query text
        threshold: Retrieval threshold ("strict", "medium", "permissive")
        
    Returns:
        True if RAG retrieval recommended
    """
    query_type, default_rag = classify_query(query)
    
    if threshold == "strict":
        # Only retrieve for explicit factual questions
        return query_type == "factual"
    elif threshold == "permissive":
        # Retrieve for everything except explicit conversational
        return query_type != "conversational"
    else:  # medium (default)
        # Use classifier recommendation
        return default_rag
