"""
Data models for KLoROS Dashboard API.

Pydantic models for structured data validation and serialization.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime


class QualityScores(BaseModel):
    """Conversation quality metrics."""
    progress: float = Field(..., ge=0, le=1, description="Progress score (0-1)")
    clarity: float = Field(..., ge=0, le=1, description="Clarity score (0-1)")
    engagement: float = Field(..., ge=0, le=1, description="Engagement score (0-1)")


class Issues(BaseModel):
    """Detected conversation issues."""
    repetition: bool = Field(..., description="Repetitive responses detected")
    stuck: bool = Field(..., description="Stuck pattern detected")
    confusion: bool = Field(..., description="User confusion detected")


class Interventions(BaseModel):
    """Meta-cognitive interventions."""
    clarify: bool = Field(..., description="Should clarify response")
    change_approach: bool = Field(..., description="Should change approach")
    summarize: bool = Field(..., description="Should summarize conversation")
    confirm: bool = Field(..., description="Should confirm understanding")
    break_suggested: bool = Field(False, description="Break suggested")


class Affect(BaseModel):
    """Consciousness affective state."""
    valence: float = Field(..., ge=-1, le=1, description="Emotional valence (-1 to +1)")
    arousal: float = Field(..., ge=-1, le=1, description="Arousal level (-1 to +1)")
    uncertainty: float = Field(..., ge=0, le=1, description="Uncertainty (0-1)")
    fatigue: float = Field(0.0, ge=0, le=1, description="Fatigue level (0-1)")
    curiosity: float = Field(0.5, ge=0, le=1, description="Curiosity level (0-1)")


class SessionInfo(BaseModel):
    """Current conversation session information."""
    turn_count: int = Field(..., ge=0, description="Number of turns in conversation")
    duration_seconds: int = Field(0, ge=0, description="Session duration in seconds")
    topics: List[str] = Field(default_factory=list, description="Topics discussed")
    entities: List[str] = Field(default_factory=list, description="Entities mentioned")


class MetaState(BaseModel):
    """Complete meta-cognitive state snapshot."""
    timestamp: datetime = Field(default_factory=datetime.now)
    conversation_health: float = Field(..., ge=0, le=1, description="Overall conversation health (0-1)")
    quality_scores: QualityScores
    issues: Issues
    interventions: Interventions
    affect: Affect
    session: SessionInfo
    meta_confidence: float = Field(0.5, ge=0, le=1, description="Confidence in meta-assessment")


class HistoricalSample(BaseModel):
    """Single historical data point."""
    timestamp: datetime
    value: float


class HistoricalData(BaseModel):
    """Historical metrics data."""
    metric: str = Field(..., description="Metric name (e.g., 'conversation_health')")
    samples: List[HistoricalSample]
    average: float = Field(..., description="Average value over period")
    min_value: float = Field(..., description="Minimum value")
    max_value: float = Field(..., description="Maximum value")


class InterventionLog(BaseModel):
    """Log entry for meta-cognitive intervention."""
    timestamp: datetime
    intervention_type: str = Field(..., description="Type of intervention")
    triggered: bool = Field(..., description="Was intervention triggered")
    reason: str = Field(..., description="Reason for intervention")
    conversation_health_before: float = Field(..., ge=0, le=1)


class DashboardSummary(BaseModel):
    """Dashboard summary statistics."""
    uptime_seconds: int
    total_turns: int
    interventions_triggered: int
    avg_conversation_health: float
    current_status: str

# ===== Enhanced Models for Dashboard Features =====

class ConversationTurn(BaseModel):
    """Single conversation turn."""
    role: str = Field(..., description="'user' or 'assistant'")
    text: str = Field(..., description="Turn text content")
    timestamp: Optional[datetime] = Field(None, description="When this turn occurred")


class GPUInfo(BaseModel):
    """GPU utilization and memory info."""
    index: int
    name: str
    utilization_gpu: float = Field(..., ge=0, le=100)
    utilization_memory: float = Field(..., ge=0, le=100)
    memory_used_mb: float
    memory_total_mb: float
    temperature_c: float = 0.0


class SystemResources(BaseModel):
    """System resource usage metrics."""
    timestamp: datetime
    cpu_percent: float = Field(..., ge=0, le=100)
    memory_percent: float = Field(..., ge=0, le=100)
    memory_used_gb: float
    memory_total_gb: float
    process_cpu: float = Field(0.0, ge=0)
    process_memory_mb: float = 0.0
    gpus: List[GPUInfo] = Field(default_factory=list)


class PrimaryEmotions(BaseModel):
    """Panksepp's 7 primary emotions."""
    seeking: float = Field(0.0, ge=0, le=1)
    rage: float = Field(0.0, ge=0, le=1)
    fear: float = Field(0.0, ge=0, le=1)
    panic: float = Field(0.0, ge=0, le=1)
    care: float = Field(0.0, ge=0, le=1)
    play: float = Field(0.0, ge=0, le=1)
    lust: float = Field(0.0, ge=0, le=1)


class HomeostaticVariable(BaseModel):
    """Single homeostatic variable state."""
    name: str
    current: float
    target: float
    pressure: float = Field(..., ge=0, le=1)
    satisfied: bool


class CoreAffect(BaseModel):
    """Extended affective state."""
    valence: float = Field(..., ge=-1, le=1)
    arousal: float = Field(..., ge=-1, le=1)
    dominance: float = Field(0.0, ge=-1, le=1)
    uncertainty: float = Field(..., ge=0, le=1)
    fatigue: float = Field(..., ge=0, le=1)
    curiosity: float = Field(..., ge=0, le=1)


class ConsciousnessDetails(BaseModel):
    """Detailed consciousness state."""
    core_affect: Optional[CoreAffect] = None
    primary_emotions: Optional[PrimaryEmotions] = None
    homeostatic: List[HomeostaticVariable] = Field(default_factory=list)


class Reflection(BaseModel):
    """Memory reflection/insight."""
    pattern_type: str
    insight: str
    confidence: float = Field(..., ge=0, le=1)
    timestamp: Optional[str] = None


class MemoryStats(BaseModel):
    """Memory system statistics."""
    total_memories: int = 0
    episodic_count: int = 0
    semantic_count: int = 0


class MemoryInsights(BaseModel):
    """Memory and reflection insights."""
    recent_reflections: List[Reflection] = Field(default_factory=list)
    active_patterns: List[str] = Field(default_factory=list)
    memory_stats: MemoryStats = Field(default_factory=MemoryStats)


class InterventionHistoryEntry(BaseModel):
    """Single intervention history entry."""
    timestamp: str
    type: str
    reason: str


class QualityHistorySample(BaseModel):
    """Historical quality metrics sample."""
    timestamp: str
    health: float = Field(..., ge=0, le=1)
    progress: float = Field(..., ge=0, le=1)
    clarity: float = Field(..., ge=0, le=1)
    engagement: float = Field(..., ge=0, le=1)


class EmotionalTrajectoryPoint(BaseModel):
    """Point in emotional trajectory (valence/arousal over time)."""
    timestamp: str
    valence: float = Field(..., ge=-1, le=1)
    arousal: float = Field(..., ge=-1, le=1)


class EnhancedMetaState(BaseModel):
    """Enhanced meta-cognitive state with all dashboard data."""
    # Core state (same as MetaState)
    timestamp: datetime
    conversation_health: float = Field(..., ge=0, le=1)
    quality_scores: QualityScores
    issues: Issues
    interventions: Interventions
    affect: Dict  # Will be core_affect or simple affect
    session: SessionInfo
    meta_confidence: float = Field(..., ge=0, le=1)
    
    # Enhanced data
    recent_turns: List[ConversationTurn] = Field(default_factory=list)
    consciousness_details: ConsciousnessDetails = Field(default_factory=ConsciousnessDetails)
    memory_insights: MemoryInsights = Field(default_factory=MemoryInsights)
    system_resources: SystemResources
    
    # Historical data
    intervention_history: List[InterventionHistoryEntry] = Field(default_factory=list)
    quality_history: List[QualityHistorySample] = Field(default_factory=list)
    emotional_trajectory: List[EmotionalTrajectoryPoint] = Field(default_factory=list)
    resource_history: List[SystemResources] = Field(default_factory=list)


class NetworkNode(BaseModel):
    """Node in topic/entity network graph."""
    id: str
    label: str
    type: str  # 'topic' or 'entity'
    weight: float = 1.0


class NetworkEdge(BaseModel):
    """Edge in network graph."""
    source: str
    target: str
    weight: float = 1.0


class NetworkGraph(BaseModel):
    """Topic/Entity network graph."""
    nodes: List[NetworkNode]
    edges: List[NetworkEdge]


# ===== Curiosity & Introspection Models =====

class CuriosityQuestion(BaseModel):
    """A curiosity question generated by KLoROS."""
    id: str = Field(..., description="Unique question ID")
    hypothesis: str = Field(..., description="Hypothesis being investigated")
    question: str = Field(..., description="The actual question")
    evidence: List[str] = Field(default_factory=list, description="Evidence supporting the question")
    action_class: str = Field(..., description="Action classification")
    autonomy: int = Field(..., ge=1, le=3, description="Autonomy level (1=notify, 2=propose, 3=execute)")
    value_estimate: float = Field(..., ge=0, le=1, description="Expected value")
    cost: float = Field(..., ge=0, le=1, description="Expected cost/risk")
    status: str = Field(..., description="Question status (READY, INVESTIGATING, ANSWERED)")
    created_at: str = Field(..., description="ISO timestamp of creation")
    capability_key: Optional[str] = Field(None, description="Related capability")


class InternalDialogue(BaseModel):
    """Internal dialogue/thought from KLoROS."""
    timestamp: str = Field(..., description="ISO timestamp")
    type: str = Field(..., description="Type of thought (reflection, planning, concern, insight)")
    content: str = Field(..., description="The actual internal thought")
    context: Optional[str] = Field(None, description="What triggered this thought")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in this assessment")


class XAIReasoningStep(BaseModel):
    """Single step in XAI reasoning trace."""
    step: int = Field(..., description="Step number")
    description: str = Field(..., description="What happened in this step")
    inputs: Dict = Field(default_factory=dict, description="Inputs to this step")
    outputs: Dict = Field(default_factory=dict, description="Outputs from this step")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="Confidence score")


class XAITrace(BaseModel):
    """Complete XAI reasoning trace for a decision."""
    decision_id: str = Field(..., description="Unique decision ID")
    decision_type: str = Field(..., description="Type of decision (curiosity_generation, response_strategy, etc.)")
    timestamp: str = Field(..., description="ISO timestamp")
    question: str = Field(..., description="What question was being answered")
    final_decision: str = Field(..., description="The final decision made")
    reasoning_steps: List[XAIReasoningStep] = Field(..., description="Step-by-step reasoning")
    confidence: float = Field(..., ge=0, le=1, description="Overall confidence in decision")
    alternatives_considered: List[str] = Field(default_factory=list, description="Other options considered")


class CuriosityState(BaseModel):
    """Current curiosity and introspection state."""
    curiosity_level: float = Field(..., ge=0, le=1, description="Current curiosity level from consciousness")
    active_questions: List[CuriosityQuestion] = Field(default_factory=list, description="Currently active curiosity questions")
    recent_investigations: List[CuriosityQuestion] = Field(default_factory=list, description="Recently answered questions")
    internal_dialogue: List[InternalDialogue] = Field(default_factory=list, description="Recent internal thoughts")
    total_questions_generated: int = Field(0, description="Total questions generated this session")
    total_questions_answered: int = Field(0, description="Total questions answered this session")


class ExternalLLMConfig(BaseModel):
    """Configuration for external LLM access (e.g., Windows rig passthrough)."""
    enabled: bool = Field(False, description="Whether external LLM access is enabled")
    endpoint_url: Optional[str] = Field(None, description="URL of the external LLM endpoint")
    model_name: Optional[str] = Field(None, description="Name of the external model")
    description: Optional[str] = Field(None, description="Human-readable description")
    last_updated: Optional[str] = Field(None, description="ISO timestamp of last update")



class RemoteLLMConfig(BaseModel):
    """Configuration for remote LLM server (Ollama on ALTIMITOS)."""
    enabled: bool = Field(False, description="Whether remote LLM access is enabled")
    selected_model: str = Field("qwen2.5:72b", description="Currently selected model")
    server_url: str = Field("http://100.67.244.66:11434", description="Remote Ollama server URL")
    last_updated: Optional[str] = Field(None, description="ISO timestamp of last update")


class RemoteLLMQuery(BaseModel):
    """Request model for remote LLM query."""
    model: str = Field(..., description="Model to use (qwen2.5:72b, deepseek-r1:70b, qwen2.5-coder:32b)")
    prompt: str = Field(..., description="Prompt to send to the model")
    enabled: bool = Field(True, description="Whether remote LLM is enabled")


class RemoteLLMResponse(BaseModel):
    """Response model for remote LLM query."""
    success: bool = Field(..., description="Whether the query was successful")
    response: Optional[str] = Field(None, description="Generated text from the model")
    error: Optional[str] = Field(None, description="Error message if failed")
    model_used: str = Field(..., description="Model that was used")
    response_time_ms: Optional[float] = Field(None, description="Response time in milliseconds")


class RemoteLLMStatus(BaseModel):
    """Status of remote LLM server."""
    reachable: bool = Field(..., description="Whether the server is reachable")
    available_models: List[str] = Field(default_factory=list, description="List of available models")
    error: Optional[str] = Field(None, description="Error message if unreachable")
