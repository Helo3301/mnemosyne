"""Summary templates for Mnemosyne."""

# Core summary template (≤500 tokens target)
CORE_SUMMARY_TEMPLATE = """## User Context
{user_context}

## Session Context
{session_context}

## Interaction Guidelines
{guidelines}"""

# User context section
USER_CONTEXT_TEMPLATE = """- Primary projects: {projects}
- Key technologies: {technologies}
- Current goals: {goals}
- Known preferences: {preferences}"""

# Session context section
SESSION_CONTEXT_TEMPLATE = """- Last session: {last_session}
- Recent events: {recent_events}
- Active frustrations: {frustrations}"""

# Interaction guidelines section
GUIDELINES_TEMPLATE = """- {expertise_note}
- {learning_note}
- {preference_note}"""

# Individual item templates
PROJECT_ITEM = "{name}"
TECHNOLOGY_ITEM = "{name} ({proficiency})"
GOAL_ITEM = "{name}"
PREFERENCE_ITEM = "{name}"
EVENT_ITEM = "{name} ({when})"
FRUSTRATION_ITEM = "{name}"

# Proficiency level labels
PROFICIENCY_LEVELS = {
    (0.0, 0.3): "beginner",
    (0.3, 0.5): "familiar",
    (0.5, 0.7): "proficient",
    (0.7, 0.9): "advanced",
    (0.9, 1.0): "expert",
}


def get_proficiency_label(proficiency: float) -> str:
    """Convert proficiency score to human-readable label."""
    for (low, high), label in PROFICIENCY_LEVELS.items():
        if low <= proficiency < high:
            return label
    return "expert" if proficiency >= 0.9 else "unknown"


# Guideline templates
EXPERTISE_GUIDELINES = {
    "has_expertise": "User is expert in {technologies} - can skip basics, use advanced terminology",
    "no_expertise": "No strong expertise detected - explain technical concepts when needed",
}

LEARNING_GUIDELINES = {
    "has_learning": "User is learning {technologies} - provide more explanation and examples",
    "no_learning": "No specific learning areas detected",
}

PREFERENCE_GUIDELINES = {
    "has_preferences": "User prefers: {preferences}",
    "no_preferences": "No strong preferences detected - ask when choices arise",
}

# Empty state messages
EMPTY_PROJECTS = "None tracked yet"
EMPTY_TECHNOLOGIES = "None tracked yet"
EMPTY_GOALS = "None stated"
EMPTY_PREFERENCES = "None detected"
EMPTY_EVENTS = "None recent"
EMPTY_FRUSTRATIONS = "None active"
EMPTY_SESSION = "No previous session"
