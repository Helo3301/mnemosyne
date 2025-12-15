from __future__ import annotations

"""Proficiency inference for Mnemosyne."""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..db.database import get_db
from ..models.entities import Entity, EntityType, RelationshipType

logger = logging.getLogger(__name__)


@dataclass
class ProficiencySignal:
    """A signal about user proficiency in a technology."""
    technology: str
    signal_type: str  # "explains", "asks_basic", "uses_advanced", "mentions", "struggles"
    weight: float     # How much this signal affects proficiency estimate
    timestamp: datetime


# Signal weights for proficiency inference
SIGNAL_WEIGHTS = {
    "explains": 0.3,       # User explains something -> high proficiency
    "uses_advanced": 0.2,  # Uses advanced patterns -> high proficiency
    "mentions": 0.05,      # Just mentions it -> slight increase
    "asks_basic": -0.2,    # Asks basic questions -> lower proficiency
    "struggles": -0.15,    # Struggles with something -> lower proficiency
}


class ProficiencyInferrer:
    """
    Infers user proficiency levels in technologies.

    Uses signals from conversation:
    - User explains something to Claude -> HIGH proficiency
    - User asks basic questions -> LOW proficiency
    - User uses advanced patterns -> increases proficiency
    - User struggles with something -> decreases proficiency
    """

    def __init__(self):
        self.db = get_db()

    def record_signal(
        self,
        technology: str,
        signal_type: str,
        session_id: str | None = None,
    ) -> Entity | None:
        """
        Record a proficiency signal.

        Args:
            technology: Technology name
            signal_type: Type of signal (from SIGNAL_WEIGHTS keys)
            session_id: Optional session ID

        Returns:
            Updated technology entity
        """
        weight = SIGNAL_WEIGHTS.get(signal_type, 0)
        if weight == 0:
            logger.warning(f"Unknown signal type: {signal_type}")
            return None

        # Get or create technology entity
        tech_entity = self.db.get_entity_by_name(EntityType.TECHNOLOGY, technology)
        if not tech_entity:
            # Create new technology entity
            from ..graph.operations import GraphOperations
            ops = GraphOperations()
            tech_entity = ops.record_technology(technology, proficiency=0.5)

        # Get user entity
        user_entity = self.db.get_entity_by_name(EntityType.USER, "user")
        if not user_entity:
            from ..graph.operations import GraphOperations
            ops = GraphOperations()
            user_entity = ops.get_user_entity()

        # Find KNOWS relationship
        relationships = self.db.get_relationships_from(
            user_entity.id,
            RelationshipType.KNOWS
        )
        knows_rel = None
        for rel in relationships:
            if rel.target_id == tech_entity.id:
                knows_rel = rel
                break

        if knows_rel:
            # Update proficiency in relationship
            current_prof = knows_rel.metadata.get("proficiency", knows_rel.weight)
            new_prof = max(0.0, min(1.0, current_prof + weight))

            knows_rel.weight = new_prof
            knows_rel.metadata["proficiency"] = new_prof
            knows_rel.metadata.setdefault("signals", []).append({
                "type": signal_type,
                "weight": weight,
                "timestamp": datetime.now().isoformat(),
            })
            self.db.update_relationship(knows_rel)

            logger.debug(
                f"Updated proficiency for {technology}: {current_prof:.2f} -> {new_prof:.2f} "
                f"(signal: {signal_type})"
            )

        # Also update technology entity metadata
        tech_entity.metadata["proficiency"] = knows_rel.weight if knows_rel else 0.5
        self.db.update_entity(tech_entity)

        return tech_entity

    def get_proficiency(self, technology: str) -> float:
        """
        Get current proficiency estimate for a technology.

        Args:
            technology: Technology name

        Returns:
            Proficiency score (0-1)
        """
        tech_entity = self.db.get_entity_by_name(EntityType.TECHNOLOGY, technology)
        if not tech_entity:
            return 0.0

        user_entity = self.db.get_entity_by_name(EntityType.USER, "user")
        if not user_entity:
            return 0.0

        relationships = self.db.get_relationships_from(
            user_entity.id,
            RelationshipType.KNOWS
        )

        for rel in relationships:
            if rel.target_id == tech_entity.id:
                return rel.metadata.get("proficiency", rel.weight)

        return 0.0

    def get_all_proficiencies(self) -> dict[str, float]:
        """
        Get proficiency estimates for all known technologies.

        Returns:
            Dictionary mapping technology name -> proficiency score
        """
        proficiencies = {}

        user_entity = self.db.get_entity_by_name(EntityType.USER, "user")
        if not user_entity:
            return proficiencies

        neighbors = self.db.get_neighbors(user_entity.id, direction="out")
        for entity, rel in neighbors:
            if entity.entity_type == EntityType.TECHNOLOGY and rel.relationship_type == RelationshipType.KNOWS:
                proficiencies[entity.name] = rel.metadata.get("proficiency", rel.weight)

        return proficiencies

    def get_expertise_areas(self, threshold: float = 0.7) -> list[str]:
        """
        Get technologies where user has high proficiency.

        Args:
            threshold: Minimum proficiency to be considered an expert

        Returns:
            List of technology names
        """
        proficiencies = self.get_all_proficiencies()
        return [tech for tech, prof in proficiencies.items() if prof >= threshold]

    def get_learning_areas(self, threshold: float = 0.3) -> list[str]:
        """
        Get technologies where user is still learning.

        Args:
            threshold: Maximum proficiency to be considered learning

        Returns:
            List of technology names
        """
        proficiencies = self.get_all_proficiencies()
        return [tech for tech, prof in proficiencies.items() if prof <= threshold]

    def infer_from_conversation(
        self,
        user_message: str,
        assistant_response: str | None = None,
    ) -> list[tuple[str, str, float]]:
        """
        Infer proficiency signals from a conversation turn.

        Args:
            user_message: User's message
            assistant_response: Optional assistant's response

        Returns:
            List of (technology, signal_type, weight) tuples
        """
        signals = []
        import re

        # Pattern for user explaining something
        explain_patterns = [
            r"(?:let me explain|I'll show you|here's how|the way it works)\s+(?:.*?)([A-Z][a-zA-Z]+)",
            r"in\s+([A-Z][a-zA-Z]+),?\s+(?:you|we)\s+(?:can|would|should)",
        ]

        # Pattern for asking basic questions
        basic_patterns = [
            r"(?:what is|what's|how do I|how does)\s+(?:.*?)([A-Z][a-zA-Z]+)",
            r"(?:new to|just started|learning)\s+([A-Z][a-zA-Z]+)",
        ]

        # Pattern for using advanced patterns
        advanced_patterns = [
            r"(?:async|await|yield|decorator|metaclass|generic)\s+(?:.*?)([A-Z][a-zA-Z]+)?",
            r"(?:optimization|performance|architecture|design pattern)",
        ]

        # Pattern for struggles
        struggle_patterns = [
            r"(?:can't|cannot|unable to|struggling with)\s+(?:.*?)([A-Z][a-zA-Z]+)?",
            r"([A-Z][a-zA-Z]+)\s+(?:error|exception|bug|issue)",
        ]

        # Check for explains
        for pattern in explain_patterns:
            for match in re.finditer(pattern, user_message, re.IGNORECASE):
                tech = match.group(1)
                if tech:
                    signals.append((tech, "explains", SIGNAL_WEIGHTS["explains"]))

        # Check for basic questions
        for pattern in basic_patterns:
            for match in re.finditer(pattern, user_message, re.IGNORECASE):
                tech = match.group(1)
                if tech:
                    signals.append((tech, "asks_basic", SIGNAL_WEIGHTS["asks_basic"]))

        # Check for advanced usage
        for pattern in advanced_patterns:
            if re.search(pattern, user_message, re.IGNORECASE):
                # This is a general signal, might apply to current context
                signals.append(("general", "uses_advanced", SIGNAL_WEIGHTS["uses_advanced"]))

        # Check for struggles
        for pattern in struggle_patterns:
            for match in re.finditer(pattern, user_message, re.IGNORECASE):
                tech = match.group(1) if match.groups() else "general"
                if tech:
                    signals.append((tech, "struggles", SIGNAL_WEIGHTS["struggles"]))

        return signals
