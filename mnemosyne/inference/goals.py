from __future__ import annotations

"""Goal inference for Mnemosyne."""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..db.database import get_db
from ..models.entities import Entity, EntityType, RelationshipType, Tier

logger = logging.getLogger(__name__)


@dataclass
class GoalSignal:
    """A signal about a user goal."""
    goal_text: str
    signal_type: str  # "stated", "working_toward", "completed", "abandoned"
    confidence: float
    context: str
    timestamp: datetime


# Goal statement patterns
GOAL_PATTERNS = [
    (r"(?:I\s+)?want\s+to\s+(.+?)(?:\.|,|!|$)", "stated", 0.8),
    (r"(?:I'm\s+)?trying\s+to\s+(.+?)(?:\.|,|!|$)", "working_toward", 0.75),
    (r"(?:my\s+)?goal\s+is\s+(?:to\s+)?(.+?)(?:\.|,|!|$)", "stated", 0.9),
    (r"(?:I\s+)?need\s+to\s+(.+?)(?:\.|,|!|$)", "working_toward", 0.7),
    (r"(?:I'm\s+)?working\s+(?:on|toward)\s+(.+?)(?:\.|,|!|$)", "working_toward", 0.8),
    (r"(?:planning|going)\s+to\s+(.+?)(?:\.|,|!|$)", "stated", 0.7),
    (r"(?:I\s+)?have\s+to\s+(.+?)(?:\.|,|!|$)", "working_toward", 0.65),
]

# Goal completion patterns
COMPLETION_PATTERNS = [
    (r"(?:I\s+)?(?:finally\s+)?(?:finished|completed|done with)\s+(.+?)(?:\.|,|!|$)", "completed", 0.9),
    (r"(?:just\s+)?(?:shipped|launched|deployed|released)\s+(.+?)(?:\.|,|!|$)", "completed", 0.85),
    (r"(.+?)\s+is\s+(?:done|complete|finished|live)", "completed", 0.85),
]

# Goal abandonment patterns
ABANDONMENT_PATTERNS = [
    (r"(?:I\s+)?(?:gave up|abandoned|dropped)\s+(.+?)(?:\.|,|!|$)", "abandoned", 0.8),
    (r"(?:not\s+)?(?:going to|gonna)\s+(.+?)\s+anymore", "abandoned", 0.7),
    (r"(?:decided\s+)?(?:not\s+to|against)\s+(.+?)(?:\.|,|!|$)", "abandoned", 0.75),
]


class GoalInferrer:
    """
    Infers and tracks user goals.

    Tracks:
    - Stated goals from conversation
    - Goal progress based on activity
    - Goal completion and abandonment
    """

    def __init__(self):
        self.db = get_db()

    def record_goal(
        self,
        goal_text: str,
        active: bool = True,
        confidence: float = 0.7,
    ) -> Entity:
        """
        Record a user goal.

        Args:
            goal_text: Description of the goal
            active: Whether goal is actively being pursued
            confidence: Confidence in this goal inference

        Returns:
            Goal entity
        """
        from ..graph.operations import GraphOperations
        ops = GraphOperations()

        # Normalize goal text
        normalized = goal_text.lower().strip()

        # Create or update goal entity
        goal_entity = self.db.get_entity_by_name(EntityType.GOAL, normalized)
        if not goal_entity:
            goal_entity = ops.record_goal(goal_text, active=active)
            goal_entity.confidence = confidence
            self.db.update_entity(goal_entity)
        else:
            # Update existing goal
            goal_entity.metadata["active"] = active
            goal_entity.confidence = max(goal_entity.confidence, confidence)
            self.db.activate_entity(goal_entity.id)
            self.db.update_entity(goal_entity)

        logger.debug(f"Recorded goal: '{goal_text}' (active={active})")
        return goal_entity

    def mark_goal_completed(self, goal_text: str) -> Entity | None:
        """
        Mark a goal as completed.

        Args:
            goal_text: Description of the goal

        Returns:
            Updated goal entity or None if not found
        """
        normalized = goal_text.lower().strip()
        goal_entity = self.db.get_entity_by_name(EntityType.GOAL, normalized)

        if not goal_entity:
            # Try to find a similar goal
            all_goals = self.db.get_entities_by_type(EntityType.GOAL)
            for goal in all_goals:
                if normalized in goal.normalized_name or goal.normalized_name in normalized:
                    goal_entity = goal
                    break

        if goal_entity:
            goal_entity.metadata["active"] = False
            goal_entity.metadata["completed"] = True
            goal_entity.metadata["completed_at"] = datetime.now().isoformat()
            goal_entity.tier = Tier.STABLE  # Completed goals are stable memories
            self.db.update_entity(goal_entity)
            logger.info(f"Goal completed: '{goal_entity.name}'")
            return goal_entity

        return None

    def mark_goal_abandoned(self, goal_text: str) -> Entity | None:
        """
        Mark a goal as abandoned.

        Args:
            goal_text: Description of the goal

        Returns:
            Updated goal entity or None if not found
        """
        normalized = goal_text.lower().strip()
        goal_entity = self.db.get_entity_by_name(EntityType.GOAL, normalized)

        if goal_entity:
            goal_entity.metadata["active"] = False
            goal_entity.metadata["abandoned"] = True
            goal_entity.metadata["abandoned_at"] = datetime.now().isoformat()
            # Abandoned goals decay faster
            goal_entity.tier = Tier.EPHEMERAL
            self.db.update_entity(goal_entity)
            logger.info(f"Goal abandoned: '{goal_entity.name}'")
            return goal_entity

        return None

    def get_active_goals(self) -> list[Entity]:
        """
        Get all active goals.

        Returns:
            List of active goal entities
        """
        from ..graph.operations import GraphOperations
        ops = GraphOperations()
        return ops.get_active_goals()

    def get_completed_goals(self) -> list[Entity]:
        """
        Get completed goals.

        Returns:
            List of completed goal entities
        """
        goals = self.db.get_entities_by_type(EntityType.GOAL)
        return [g for g in goals if g.metadata.get("completed", False)]

    def get_goal_history(self) -> dict[str, list[Entity]]:
        """
        Get all goals organized by status.

        Returns:
            Dictionary with "active", "completed", "abandoned" keys
        """
        goals = self.db.get_entities_by_type(EntityType.GOAL)
        return {
            "active": [g for g in goals if g.metadata.get("active", True) and not g.metadata.get("completed") and not g.metadata.get("abandoned")],
            "completed": [g for g in goals if g.metadata.get("completed", False)],
            "abandoned": [g for g in goals if g.metadata.get("abandoned", False)],
        }

    def infer_from_message(self, message: str) -> list[GoalSignal]:
        """
        Infer goal signals from a user message.

        Args:
            message: User's message

        Returns:
            List of GoalSignal objects
        """
        signals = []
        now = datetime.now()

        # Check goal statements
        for pattern, signal_type, confidence in GOAL_PATTERNS:
            for match in re.finditer(pattern, message, re.IGNORECASE):
                goal_text = match.group(1).strip()
                if goal_text and len(goal_text) > 5:
                    signals.append(GoalSignal(
                        goal_text=goal_text,
                        signal_type=signal_type,
                        confidence=confidence,
                        context=match.group(0),
                        timestamp=now,
                    ))

        # Check completions
        for pattern, signal_type, confidence in COMPLETION_PATTERNS:
            for match in re.finditer(pattern, message, re.IGNORECASE):
                goal_text = match.group(1).strip()
                if goal_text and len(goal_text) > 3:
                    signals.append(GoalSignal(
                        goal_text=goal_text,
                        signal_type=signal_type,
                        confidence=confidence,
                        context=match.group(0),
                        timestamp=now,
                    ))

        # Check abandonments
        for pattern, signal_type, confidence in ABANDONMENT_PATTERNS:
            for match in re.finditer(pattern, message, re.IGNORECASE):
                goal_text = match.group(1).strip()
                if goal_text and len(goal_text) > 3:
                    signals.append(GoalSignal(
                        goal_text=goal_text,
                        signal_type=signal_type,
                        confidence=confidence,
                        context=match.group(0),
                        timestamp=now,
                    ))

        return signals

    def apply_signals(self, signals: list[GoalSignal]) -> list[Entity]:
        """
        Apply goal signals to the graph.

        Args:
            signals: List of goal signals

        Returns:
            List of goal entities
        """
        entities = []
        for signal in signals:
            if signal.signal_type in ("stated", "working_toward"):
                entity = self.record_goal(
                    signal.goal_text,
                    active=True,
                    confidence=signal.confidence,
                )
            elif signal.signal_type == "completed":
                entity = self.mark_goal_completed(signal.goal_text)
                if not entity:
                    # Create as completed if not found
                    entity = self.record_goal(signal.goal_text, active=False)
                    entity = self.mark_goal_completed(signal.goal_text)
            elif signal.signal_type == "abandoned":
                entity = self.mark_goal_abandoned(signal.goal_text)
                if not entity:
                    entity = self.record_goal(signal.goal_text, active=False)
                    entity = self.mark_goal_abandoned(signal.goal_text)

            if entity:
                entities.append(entity)

        return entities

    def suggest_related_goals(self, current_goal: str) -> list[str]:
        """
        Suggest goals related to a current goal using graph traversal.

        Args:
            current_goal: Current goal text

        Returns:
            List of related goal suggestions
        """
        normalized = current_goal.lower().strip()
        goal_entity = self.db.get_entity_by_name(EntityType.GOAL, normalized)

        if not goal_entity:
            return []

        # Use spreading activation to find related goals
        from ..graph.activation import SpreadingActivation
        activator = SpreadingActivation()
        activated = activator.spread([goal_entity.id], depth=2, budget=20)

        related_goals = []
        for entity_id, strength in activated.items():
            entity = self.db.get_entity(entity_id)
            if entity and entity.entity_type == EntityType.GOAL and entity.id != goal_entity.id:
                if entity.metadata.get("active", True):
                    related_goals.append(entity.name)

        return related_goals[:5]  # Top 5 related goals
