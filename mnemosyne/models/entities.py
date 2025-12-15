"""Data models for Mnemosyne memory entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class EntityType(str, Enum):
    """Types of entities in the memory graph."""
    USER = "USER"                # The user themselves (singleton)
    PROJECT = "PROJECT"          # Projects user works on
    TECHNOLOGY = "TECHNOLOGY"    # Languages, frameworks, tools
    CONCEPT = "CONCEPT"          # Abstract concepts, patterns
    SESSION = "SESSION"          # Conversation sessions
    EVENT = "EVENT"              # Notable events (deploy, bug, success)
    PREFERENCE = "PREFERENCE"    # User preferences
    GOAL = "GOAL"                # User's stated goals
    FRUSTRATION = "FRUSTRATION"  # Things that frustrated user


class RelationshipType(str, Enum):
    """Types of relationships between entities."""
    WORKS_ON = "WORKS_ON"           # USER → PROJECT
    USES = "USES"                   # PROJECT → TECHNOLOGY
    KNOWS = "KNOWS"                 # USER → TECHNOLOGY (with proficiency)
    PREFERS = "PREFERS"             # USER → PREFERENCE
    PURSUING = "PURSUING"           # USER → GOAL
    FRUSTRATED_BY = "FRUSTRATED_BY" # USER → FRUSTRATION
    RELATED_TO = "RELATED_TO"       # CONCEPT → CONCEPT
    OCCURRED_IN = "OCCURRED_IN"     # EVENT → SESSION
    INFORMED_BY = "INFORMED_BY"     # CONCEPT → HERMES knowledge


class Tier(str, Enum):
    """Memory tiers for decay rate classification."""
    CORE = "CORE"           # Very slow decay (λ = 0.01)
    STABLE = "STABLE"       # Moderate decay (λ = 0.03)
    EPHEMERAL = "EPHEMERAL" # Fast decay (λ = 0.1)


class FeedbackType(str, Enum):
    """Types of feedback signals."""
    POSITIVE = "POSITIVE"       # "thanks", "perfect", etc.
    NEGATIVE = "NEGATIVE"       # "wrong", "doesn't work", etc.
    CORRECTION = "CORRECTION"   # User correcting an assumption


class ActivationType(str, Enum):
    """Types of entity activation."""
    EXPLICIT = "EXPLICIT"   # Direct mention by user
    INFERRED = "INFERRED"   # Inferred from context
    SPREAD = "SPREAD"       # Activated via spreading activation


@dataclass
class Entity:
    """A node in the memory graph."""
    id: Optional[int] = None
    entity_type: EntityType = EntityType.CONCEPT
    name: str = ""
    normalized_name: str = ""
    tier: Tier = Tier.EPHEMERAL
    confidence: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)
    last_activated_at: datetime = field(default_factory=datetime.now)
    activation_count: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.normalized_name:
            self.normalized_name = self.name.lower().strip()
        if isinstance(self.entity_type, str):
            self.entity_type = EntityType(self.entity_type)
        if isinstance(self.tier, str):
            self.tier = Tier(self.tier)


@dataclass
class Relationship:
    """An edge in the memory graph."""
    id: Optional[int] = None
    source_id: int = 0
    target_id: int = 0
    relationship_type: RelationshipType = RelationshipType.RELATED_TO
    weight: float = 0.5
    confidence: float = 0.5
    evidence_count: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    last_strengthened_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.relationship_type, str):
            self.relationship_type = RelationshipType(self.relationship_type)


@dataclass
class Activation:
    """A record of entity activation."""
    id: Optional[int] = None
    entity_id: int = 0
    session_id: Optional[str] = None
    activation_type: ActivationType = ActivationType.EXPLICIT
    activation_strength: float = 1.0
    activated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if isinstance(self.activation_type, str):
            self.activation_type = ActivationType(self.activation_type)


@dataclass
class Session:
    """A conversation session."""
    id: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None
    project_context: Optional[str] = None
    summary: Optional[str] = None


@dataclass
class Feedback:
    """A feedback signal from the user."""
    id: Optional[int] = None
    session_id: Optional[str] = None
    entity_id: Optional[int] = None
    signal_type: FeedbackType = FeedbackType.POSITIVE
    signal_text: Optional[str] = None
    captured_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if isinstance(self.signal_type, str):
            self.signal_type = FeedbackType(self.signal_type)
