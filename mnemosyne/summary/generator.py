from __future__ import annotations

"""Core summary generation for Mnemosyne."""
import logging
from datetime import datetime
from typing import Any

from ..db.database import get_db
from ..graph.decay import compute_relevance
from ..graph.operations import GraphOperations
from ..inference.goals import GoalInferrer
from ..inference.preferences import PreferenceInferrer
from ..inference.proficiency import ProficiencyInferrer
from ..models.entities import EntityType
from .templates import (
    CORE_SUMMARY_TEMPLATE,
    EMPTY_EVENTS,
    EMPTY_FRUSTRATIONS,
    EMPTY_GOALS,
    EMPTY_PREFERENCES,
    EMPTY_PROJECTS,
    EMPTY_SESSION,
    EMPTY_TECHNOLOGIES,
    EXPERTISE_GUIDELINES,
    GUIDELINES_TEMPLATE,
    LEARNING_GUIDELINES,
    PREFERENCE_GUIDELINES,
    SESSION_CONTEXT_TEMPLATE,
    USER_CONTEXT_TEMPLATE,
    get_proficiency_label,
)

logger = logging.getLogger(__name__)


class CoreSummaryGenerator:
    """
    Generates the core summary for session startup.

    The core summary provides Claude with essential context about the user:
    - What projects they work on
    - What technologies they know (and at what level)
    - What their goals are
    - What their preferences are
    - Recent events and frustrations

    Target: ≤500 tokens
    """

    def __init__(
        self,
        max_projects: int = 3,
        max_technologies: int = 5,
        max_goals: int = 3,
        max_preferences: int = 3,
        max_events: int = 3,
        max_frustrations: int = 2,
    ):
        self.db = get_db()
        self.ops = GraphOperations()
        self.prof_inferrer = ProficiencyInferrer()
        self.pref_inferrer = PreferenceInferrer()
        self.goal_inferrer = GoalInferrer()

        self.max_projects = max_projects
        self.max_technologies = max_technologies
        self.max_goals = max_goals
        self.max_preferences = max_preferences
        self.max_events = max_events
        self.max_frustrations = max_frustrations

    def generate(self) -> str:
        """
        Generate the core summary.

        Returns:
            Formatted summary string (≤500 tokens target)
        """
        user_context = self._generate_user_context()
        session_context = self._generate_session_context()
        guidelines = self._generate_guidelines()

        summary = CORE_SUMMARY_TEMPLATE.format(
            user_context=user_context,
            session_context=session_context,
            guidelines=guidelines,
        )

        return summary.strip()

    def _generate_user_context(self) -> str:
        """Generate the user context section."""
        # Get projects
        projects = self.ops.get_user_projects()
        project_names = [p.name for p, _ in projects[:self.max_projects]]
        projects_str = ", ".join(project_names) if project_names else EMPTY_PROJECTS

        # Get technologies with proficiency
        techs = self.ops.get_user_technologies()
        tech_items = []
        for tech, prof in techs[:self.max_technologies]:
            label = get_proficiency_label(prof)
            tech_items.append(f"{tech.name} ({label})")
        techs_str = ", ".join(tech_items) if tech_items else EMPTY_TECHNOLOGIES

        # Get active goals
        goals = self.goal_inferrer.get_active_goals()
        goal_names = [g.name for g in goals[:self.max_goals]]
        goals_str = ", ".join(goal_names) if goal_names else EMPTY_GOALS

        # Get preferences
        prefs = self.pref_inferrer.get_strong_preferences()
        prefs_str = ", ".join(prefs[:self.max_preferences]) if prefs else EMPTY_PREFERENCES

        return USER_CONTEXT_TEMPLATE.format(
            projects=projects_str,
            technologies=techs_str,
            goals=goals_str,
            preferences=prefs_str,
        )

    def _generate_session_context(self) -> str:
        """Generate the session context section."""
        # Get last session
        sessions = self.db.get_recent_sessions(limit=1)
        if sessions:
            last = sessions[0]
            last_session = f"{last.started_at.strftime('%Y-%m-%d')}"
            if last.project_context:
                last_session += f" ({last.project_context})"
            if last.summary:
                last_session += f" - {last.summary[:50]}..."
        else:
            last_session = EMPTY_SESSION

        # Get recent events
        events = self.db.get_entities_by_type(EntityType.EVENT)
        events = sorted(events, key=lambda e: e.last_activated_at, reverse=True)[:self.max_events]
        event_items = []
        for event in events:
            when = event.last_activated_at.strftime("%m/%d")
            event_items.append(f"{event.name} ({when})")
        events_str = ", ".join(event_items) if event_items else EMPTY_EVENTS

        # Get active frustrations
        frustrations = self.ops.get_recent_frustrations(limit=self.max_frustrations)
        frustration_names = [f.name for f in frustrations]
        frustrations_str = ", ".join(frustration_names) if frustration_names else EMPTY_FRUSTRATIONS

        return SESSION_CONTEXT_TEMPLATE.format(
            last_session=last_session,
            recent_events=events_str,
            frustrations=frustrations_str,
        )

    def _generate_guidelines(self) -> str:
        """Generate the interaction guidelines section."""
        # Expertise areas
        expertise = self.prof_inferrer.get_expertise_areas()
        if expertise:
            expertise_note = EXPERTISE_GUIDELINES["has_expertise"].format(
                technologies=", ".join(expertise[:3])
            )
        else:
            expertise_note = EXPERTISE_GUIDELINES["no_expertise"]

        # Learning areas
        learning = self.prof_inferrer.get_learning_areas()
        if learning:
            learning_note = LEARNING_GUIDELINES["has_learning"].format(
                technologies=", ".join(learning[:3])
            )
        else:
            learning_note = LEARNING_GUIDELINES["no_learning"]

        # Preferences
        prefs = self.pref_inferrer.get_strong_preferences()
        if prefs:
            preference_note = PREFERENCE_GUIDELINES["has_preferences"].format(
                preferences=", ".join(prefs[:3])
            )
        else:
            preference_note = PREFERENCE_GUIDELINES["no_preferences"]

        return GUIDELINES_TEMPLATE.format(
            expertise_note=expertise_note,
            learning_note=learning_note,
            preference_note=preference_note,
        )

    def get_session_context(self, project_name: str | None = None) -> dict[str, Any]:
        """
        Get structured context for a session.

        This provides more detailed context that can be used programmatically.

        Args:
            project_name: Optional project to focus on

        Returns:
            Dictionary with detailed context
        """
        context = {
            "projects": [],
            "technologies": [],
            "goals": [],
            "preferences": [],
            "recent_events": [],
            "frustrations": [],
            "proficiency_summary": {
                "expertise_areas": [],
                "learning_areas": [],
            },
        }

        # Projects
        projects = self.ops.get_user_projects()
        for project, weight in projects[:5]:
            techs = self.ops.get_project_technologies(project.id)
            context["projects"].append({
                "name": project.name,
                "weight": weight,
                "technologies": [t.name for t in techs],
                "relevance": compute_relevance(project),
            })

        # Technologies
        techs = self.ops.get_user_technologies()
        for tech, prof in techs[:10]:
            context["technologies"].append({
                "name": tech.name,
                "proficiency": prof,
                "level": get_proficiency_label(prof),
            })

        # Goals
        goals = self.goal_inferrer.get_active_goals()
        for goal in goals[:5]:
            context["goals"].append({
                "name": goal.name,
                "confidence": goal.confidence,
            })

        # Preferences
        prefs = self.pref_inferrer.get_preferences()
        for item, weight in prefs[:5]:
            context["preferences"].append({
                "item": item,
                "weight": weight,
            })

        # Recent events
        events = self.db.get_entities_by_type(EntityType.EVENT)
        events = sorted(events, key=lambda e: e.last_activated_at, reverse=True)[:5]
        for event in events:
            context["recent_events"].append({
                "name": event.name,
                "when": event.last_activated_at.isoformat(),
            })

        # Frustrations
        frustrations = self.ops.get_recent_frustrations()
        for f in frustrations[:3]:
            context["frustrations"].append({
                "name": f.name,
                "context": f.metadata.get("context"),
            })

        # Proficiency summary
        context["proficiency_summary"]["expertise_areas"] = self.prof_inferrer.get_expertise_areas()
        context["proficiency_summary"]["learning_areas"] = self.prof_inferrer.get_learning_areas()

        return context


def generate_core_summary() -> str:
    """Convenience function to generate core summary."""
    generator = CoreSummaryGenerator()
    return generator.generate()
