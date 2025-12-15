from __future__ import annotations

"""Preference inference for Mnemosyne."""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..db.database import get_db
from ..models.entities import Entity, EntityType, RelationshipType

logger = logging.getLogger(__name__)


@dataclass
class PreferenceSignal:
    """A signal about user preference."""
    item: str
    sentiment: float  # -1 to 1
    confidence: float
    context: str
    timestamp: datetime


# Preference indicators with sentiment
POSITIVE_INDICATORS = [
    (r"(?:I\s+)?prefer\s+(.+?)(?:\s+over|\s+to|\.|,|$)", 0.8),
    (r"(?:I\s+)?(?:like|love|enjoy)\s+(.+?)(?:\.|,|$)", 0.7),
    (r"(?:I\s+)?always\s+use\s+(.+?)(?:\.|,|$)", 0.9),
    (r"(.+?)\s+is\s+(?:my\s+)?(?:favorite|preferred|go-to)", 0.85),
    (r"(?:I'm\s+)?a\s+fan\s+of\s+(.+?)(?:\.|,|$)", 0.7),
    (r"(?:I\s+)?recommend\s+(.+?)(?:\.|,|$)", 0.75),
]

NEGATIVE_INDICATORS = [
    (r"(?:I\s+)?(?:don't|do not)\s+like\s+(.+?)(?:\.|,|$)", -0.7),
    (r"(?:I\s+)?hate\s+(.+?)(?:\.|,|$)", -0.9),
    (r"(?:I\s+)?avoid\s+(.+?)(?:\.|,|$)", -0.8),
    (r"(?:I\s+)?never\s+use\s+(.+?)(?:\.|,|$)", -0.85),
    (r"(.+?)\s+is\s+(?:terrible|awful|bad|annoying)", -0.8),
    (r"(?:I\s+)?(?:don't|do not)\s+recommend\s+(.+?)(?:\.|,|$)", -0.75),
]

# Choice patterns - when user chooses between options
CHOICE_PATTERNS = [
    r"(?:let's\s+)?(?:go\s+)?with\s+(.+?)(?:\s+(?:instead|rather))?(?:\.|,|$)",
    r"(?:I'll\s+)?(?:use|pick|choose)\s+(.+?)(?:\.|,|$)",
]


class PreferenceInferrer:
    """
    Infers user preferences from behavior and statements.

    Tracks:
    - Explicit preference statements
    - Choices made between alternatives
    - Consistent patterns over time
    """

    def __init__(self):
        self.db = get_db()

    def record_preference(
        self,
        item: str,
        sentiment: float,
        confidence: float = 0.7,
        context: str | None = None,
    ) -> Entity:
        """
        Record a preference signal.

        Args:
            item: The item/thing preference is about
            sentiment: -1 (dislike) to 1 (like)
            confidence: How confident we are in this signal
            context: Optional context string

        Returns:
            Preference entity
        """
        from ..graph.operations import GraphOperations
        ops = GraphOperations()

        # Create or update preference entity
        pref_entity = self.db.get_entity_by_name(EntityType.PREFERENCE, item)
        if not pref_entity:
            pref_entity = ops.record_preference(item, weight=max(0, sentiment))
        else:
            # Activate existing
            self.db.activate_entity(pref_entity.id)

        # Get user and update PREFERS relationship
        user = ops.get_user_entity()
        relationships = self.db.get_relationships_from(user.id, RelationshipType.PREFERS)

        for rel in relationships:
            if rel.target_id == pref_entity.id:
                # Update with exponential moving average
                alpha = 0.3  # Learning rate
                new_weight = alpha * max(0, sentiment) + (1 - alpha) * rel.weight
                rel.weight = new_weight
                rel.confidence = max(rel.confidence, confidence)
                rel.metadata.setdefault("signals", []).append({
                    "sentiment": sentiment,
                    "confidence": confidence,
                    "context": context,
                    "timestamp": datetime.now().isoformat(),
                })
                self.db.update_relationship(rel)
                break

        logger.debug(f"Recorded preference for '{item}': sentiment={sentiment:.2f}")
        return pref_entity

    def record_choice(
        self,
        chosen: str,
        rejected: list[str] | None = None,
        context: str | None = None,
    ) -> Entity:
        """
        Record when user makes a choice.

        Args:
            chosen: The item that was chosen
            rejected: Items that were rejected (optional)
            context: Optional context string

        Returns:
            Preference entity for chosen item
        """
        # Record positive preference for chosen item
        entity = self.record_preference(chosen, sentiment=0.7, context=context)

        # Record mild negative preference for rejected items
        if rejected:
            for item in rejected:
                self.record_preference(item, sentiment=-0.3, context=context)

        return entity

    def get_preferences(self) -> list[tuple[str, float]]:
        """
        Get all user preferences with their weights.

        Returns:
            List of (item, weight) tuples sorted by weight descending
        """
        from ..graph.operations import GraphOperations
        ops = GraphOperations()
        return [(e.name, w) for e, w in ops.get_user_preferences()]

    def get_strong_preferences(self, threshold: float = 0.7) -> list[str]:
        """
        Get items user strongly prefers.

        Args:
            threshold: Minimum weight to be considered strong

        Returns:
            List of item names
        """
        prefs = self.get_preferences()
        return [item for item, weight in prefs if weight >= threshold]

    def get_dislikes(self, threshold: float = 0.3) -> list[str]:
        """
        Get items user dislikes (low preference weight).

        Note: True dislikes should have very low weights approaching 0.

        Args:
            threshold: Maximum weight to be considered a dislike

        Returns:
            List of item names
        """
        prefs = self.get_preferences()
        return [item for item, weight in prefs if weight <= threshold]

    def infer_from_message(self, message: str) -> list[PreferenceSignal]:
        """
        Infer preference signals from a user message.

        Args:
            message: User's message

        Returns:
            List of PreferenceSignal objects
        """
        signals = []
        now = datetime.now()

        # Check positive indicators
        for pattern, sentiment in POSITIVE_INDICATORS:
            for match in re.finditer(pattern, message, re.IGNORECASE):
                item = match.group(1).strip()
                if item and len(item) > 2:
                    signals.append(PreferenceSignal(
                        item=item,
                        sentiment=sentiment,
                        confidence=0.7,
                        context=match.group(0),
                        timestamp=now,
                    ))

        # Check negative indicators
        for pattern, sentiment in NEGATIVE_INDICATORS:
            for match in re.finditer(pattern, message, re.IGNORECASE):
                item = match.group(1).strip()
                if item and len(item) > 2:
                    signals.append(PreferenceSignal(
                        item=item,
                        sentiment=sentiment,
                        confidence=0.7,
                        context=match.group(0),
                        timestamp=now,
                    ))

        # Check choice patterns
        for pattern in CHOICE_PATTERNS:
            for match in re.finditer(pattern, message, re.IGNORECASE):
                item = match.group(1).strip()
                if item and len(item) > 2:
                    signals.append(PreferenceSignal(
                        item=item,
                        sentiment=0.6,  # Moderate positive for choices
                        confidence=0.6,
                        context=match.group(0),
                        timestamp=now,
                    ))

        return signals

    def apply_signals(
        self,
        signals: list[PreferenceSignal],
    ) -> list[Entity]:
        """
        Apply preference signals to the graph.

        Args:
            signals: List of preference signals

        Returns:
            List of updated preference entities
        """
        entities = []
        for signal in signals:
            entity = self.record_preference(
                signal.item,
                signal.sentiment,
                signal.confidence,
                signal.context,
            )
            entities.append(entity)
        return entities
