from __future__ import annotations

"""Extraction patterns for Mnemosyne entity extraction."""
import re
from dataclasses import dataclass, field
from typing import Callable

from ..models.entities import EntityType


@dataclass
class ExtractionPattern:
    """A pattern for extracting entities from text."""
    entity_type: EntityType
    pattern: re.Pattern
    confidence: float = 0.7
    normalizer: Callable[[str], str] | None = None


# Technology patterns - languages, frameworks, tools
TECHNOLOGY_PATTERNS = [
    # Programming languages
    r"\b(Python|JavaScript|TypeScript|Rust|Go|Java|C\+\+|C#|Ruby|PHP|Swift|Kotlin|Scala)\b",
    # Web frameworks
    r"\b(React|Vue|Angular|Next\.js|Nuxt|Svelte|FastAPI|Django|Flask|Express|NestJS|Rails)\b",
    # Databases
    r"\b(PostgreSQL|MySQL|MongoDB|Redis|SQLite|DynamoDB|Cassandra|Elasticsearch)\b",
    # Cloud/DevOps
    r"\b(Docker|Kubernetes|AWS|GCP|Azure|Terraform|Ansible|Jenkins|GitHub Actions)\b",
    # AI/ML
    r"\b(PyTorch|TensorFlow|Keras|scikit-learn|HuggingFace|LangChain|OpenAI|Claude|Ollama)\b",
    # Tools
    r"\b(Git|VSCode|Vim|Neovim|npm|yarn|pnpm|pip|poetry|cargo)\b",
]

# Project patterns - detecting project names
PROJECT_PATTERNS = [
    r"(?:working on|building|developing|creating)\s+(?:a\s+)?([A-Z][a-zA-Z0-9_-]+)",
    r"(?:the|my|our)\s+([A-Z][a-zA-Z0-9_-]+)\s+(?:project|app|application|service|system)",
    r"(?:in|for|on)\s+([A-Z][a-zA-Z0-9_-]+)\s+(?:project|repo|repository)",
]

# Concept patterns - abstract ideas and patterns
CONCEPT_PATTERNS = [
    r"\b(microservices?|monolith|REST|GraphQL|gRPC|event[ -]driven|CQRS|DDD)\b",
    r"\b(authentication|authorization|OAuth|JWT|SSO|RBAC)\b",
    r"\b(caching|memoization|lazy[ -]loading|pagination|rate[ -]limiting)\b",
    r"\b(CI/CD|continuous integration|continuous deployment|DevOps|GitOps)\b",
    r"\b(TDD|BDD|unit test|integration test|e2e test)\b",
    r"\b(RAG|retrieval|embedding|vector|semantic search|knowledge graph)\b",
]

# Preference indicators
PREFERENCE_INDICATORS = {
    "positive": [
        r"(?:I\s+)?(?:prefer|like|love|always use|usually use|fan of)\s+(.+?)(?:\.|,|$)",
        r"(.+?)\s+(?:is|are)\s+(?:my\s+)?(?:favorite|preferred|go-to)",
        r"(?:I\s+)?(?:recommend|suggest)\s+(.+?)(?:\.|,|$)",
    ],
    "negative": [
        r"(?:I\s+)?(?:don't like|hate|avoid|never use|dislike)\s+(.+?)(?:\.|,|$)",
        r"(.+?)\s+(?:is|are)\s+(?:terrible|awful|bad|problematic)",
    ],
}

# Goal indicators
GOAL_INDICATORS = [
    r"(?:I\s+)?(?:want to|trying to|working toward|goal is to|planning to)\s+(.+?)(?:\.|,|$)",
    r"(?:need to|have to|must|should)\s+(.+?)(?:\.|,|$)",
    r"(?:my\s+)?(?:goal|objective|aim|target)\s+(?:is\s+)?(?:to\s+)?(.+?)(?:\.|,|$)",
]

# Frustration indicators
FRUSTRATION_INDICATORS = [
    r"(?:I'm\s+)?(?:frustrated|annoyed|struggling)\s+(?:with|by)\s+(.+?)(?:\.|,|$)",
    r"(.+?)\s+(?:is|are)\s+(?:frustrating|annoying|painful|driving me crazy)",
    r"(?:can't|cannot|unable to)\s+(?:figure out|understand|get|make)\s+(.+?)(?:\.|,|$)",
    r"(?:keeps?|keep)\s+(?:failing|breaking|crashing|erroring)",
]

# Event indicators
EVENT_INDICATORS = [
    r"(?:just|finally)\s+(?:deployed|released|shipped|launched|finished|completed)\s+(.+?)(?:\.|,|$)",
    r"(?:fixed|resolved|solved)\s+(?:the\s+)?(.+?)(?:\s+bug|\s+issue|\s+problem)?(?:\.|,|$)",
    r"(?:encountered|hit|found|discovered)\s+(?:a\s+)?(.+?)(?:\s+bug|\s+issue|\s+error)?(?:\.|,|$)",
]

# Proficiency indicators
PROFICIENCY_INDICATORS = {
    "high": [
        r"(?:I'm\s+)?(?:expert|experienced|proficient|advanced|senior)\s+(?:in|with|at)\s+(.+?)(?:\.|,|$)",
        r"(?:I've\s+)?(?:been using|worked with)\s+(.+?)\s+for\s+(?:\d+\s+)?years",
        r"(?:I\s+)?(?:know|understand)\s+(.+?)\s+(?:very\s+)?well",
    ],
    "low": [
        r"(?:I'm\s+)?(?:new to|learning|beginner|novice|just started)\s+(?:with\s+)?(.+?)(?:\.|,|$)",
        r"(?:don't|do not)\s+(?:know|understand)\s+(.+?)\s+(?:well|much)?(?:\.|,|$)",
        r"(?:never|haven't)\s+(?:used|worked with|tried)\s+(.+?)(?:\.|,|$)",
    ],
}


def normalize_technology(name: str) -> str:
    """Normalize technology names."""
    # Common normalizations
    normalizations = {
        "js": "javascript",
        "ts": "typescript",
        "py": "python",
        "rb": "ruby",
        "postgres": "postgresql",
        "mongo": "mongodb",
        "k8s": "kubernetes",
        "tf": "terraform",
        "gh actions": "github actions",
        "gha": "github actions",
    }
    lower = name.lower().strip()
    return normalizations.get(lower, lower)


def normalize_concept(name: str) -> str:
    """Normalize concept names."""
    # Remove extra whitespace and hyphens
    normalized = re.sub(r"[\s-]+", " ", name.lower().strip())
    # Common normalizations
    normalizations = {
        "ci cd": "ci/cd",
        "continuous integration": "ci/cd",
        "event driven": "event-driven",
        "tdd": "test-driven development",
        "bdd": "behavior-driven development",
        "ddd": "domain-driven design",
    }
    return normalizations.get(normalized, normalized)


def compile_patterns() -> dict[EntityType, list[ExtractionPattern]]:
    """Compile all patterns into ExtractionPattern objects."""
    patterns = {
        EntityType.TECHNOLOGY: [],
        EntityType.PROJECT: [],
        EntityType.CONCEPT: [],
        EntityType.PREFERENCE: [],
        EntityType.GOAL: [],
        EntityType.FRUSTRATION: [],
        EntityType.EVENT: [],
    }

    # Technology patterns
    for pattern in TECHNOLOGY_PATTERNS:
        patterns[EntityType.TECHNOLOGY].append(
            ExtractionPattern(
                entity_type=EntityType.TECHNOLOGY,
                pattern=re.compile(pattern, re.IGNORECASE),
                confidence=0.9,
                normalizer=normalize_technology,
            )
        )

    # Project patterns
    for pattern in PROJECT_PATTERNS:
        patterns[EntityType.PROJECT].append(
            ExtractionPattern(
                entity_type=EntityType.PROJECT,
                pattern=re.compile(pattern, re.IGNORECASE),
                confidence=0.7,
            )
        )

    # Concept patterns
    for pattern in CONCEPT_PATTERNS:
        patterns[EntityType.CONCEPT].append(
            ExtractionPattern(
                entity_type=EntityType.CONCEPT,
                pattern=re.compile(pattern, re.IGNORECASE),
                confidence=0.8,
                normalizer=normalize_concept,
            )
        )

    # Goal patterns
    for pattern in GOAL_INDICATORS:
        patterns[EntityType.GOAL].append(
            ExtractionPattern(
                entity_type=EntityType.GOAL,
                pattern=re.compile(pattern, re.IGNORECASE),
                confidence=0.7,
            )
        )

    # Frustration patterns
    for pattern in FRUSTRATION_INDICATORS:
        patterns[EntityType.FRUSTRATION].append(
            ExtractionPattern(
                entity_type=EntityType.FRUSTRATION,
                pattern=re.compile(pattern, re.IGNORECASE),
                confidence=0.8,
            )
        )

    # Event patterns
    for pattern in EVENT_INDICATORS:
        patterns[EntityType.EVENT].append(
            ExtractionPattern(
                entity_type=EntityType.EVENT,
                pattern=re.compile(pattern, re.IGNORECASE),
                confidence=0.7,
            )
        )

    return patterns


# Pre-compiled patterns
COMPILED_PATTERNS = compile_patterns()
