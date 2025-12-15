from __future__ import annotations

"""Knowledge integration between Mnemosyne and HERMES."""
import logging
from dataclasses import dataclass
from typing import Any

from ..db.database import get_db
from ..models.entities import Entity, EntityType, RelationshipType
from .hermes import HermesClient, HermesSearchResult

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeContext:
    """Contextual knowledge retrieved from HERMES."""
    concept: str
    papers: list[HermesSearchResult]
    related_concepts: list[str]
    summary: str | None = None


class KnowledgeBridge:
    """
    Bridge between Mnemosyne memory and HERMES knowledge.

    Responsibilities:
    - Enrich memory concepts with paper knowledge
    - Link memory entities to HERMES entities
    - Retrieve knowledge context for current conversation
    """

    def __init__(self, hermes_url: str = "http://hermes:8780"):
        self.db = get_db()
        self.hermes = HermesClient(hermes_url)

    async def close(self):
        """Close connections."""
        await self.hermes.close()

    async def enrich_concept(
        self,
        concept_entity: Entity,
        top_k: int = 3,
    ) -> list[HermesSearchResult]:
        """
        Enrich a concept entity with related papers from HERMES.

        Args:
            concept_entity: The concept to enrich
            top_k: Number of papers to retrieve

        Returns:
            List of related papers
        """
        if concept_entity.entity_type != EntityType.CONCEPT:
            logger.warning(f"Entity {concept_entity.name} is not a concept")
            return []

        # Search HERMES for related papers
        papers = await self.hermes.search(
            concept_entity.name,
            top_k=top_k,
        )

        if papers:
            # Update concept metadata with paper references
            concept_entity.metadata["related_papers"] = [
                {
                    "paper_id": p.paper_id,
                    "title": p.title,
                    "score": p.score,
                }
                for p in papers
            ]
            self.db.update_entity(concept_entity)

            logger.debug(f"Enriched concept '{concept_entity.name}' with {len(papers)} papers")

        return papers

    async def enrich_technology(
        self,
        tech_entity: Entity,
        top_k: int = 3,
    ) -> list[HermesSearchResult]:
        """
        Enrich a technology entity with related papers from HERMES.

        Args:
            tech_entity: The technology to enrich
            top_k: Number of papers to retrieve

        Returns:
            List of related papers
        """
        if tech_entity.entity_type != EntityType.TECHNOLOGY:
            logger.warning(f"Entity {tech_entity.name} is not a technology")
            return []

        # Search HERMES for papers about this technology
        papers = await self.hermes.search(
            f"{tech_entity.name} implementation tutorial",
            top_k=top_k,
        )

        if papers:
            tech_entity.metadata["related_papers"] = [
                {
                    "paper_id": p.paper_id,
                    "title": p.title,
                    "score": p.score,
                }
                for p in papers
            ]
            self.db.update_entity(tech_entity)

        return papers

    async def get_knowledge_context(
        self,
        concepts: list[str],
        technologies: list[str] | None = None,
        top_k_per_concept: int = 2,
    ) -> list[KnowledgeContext]:
        """
        Get knowledge context for a set of concepts/technologies.

        Args:
            concepts: List of concept names
            technologies: Optional list of technology names
            top_k_per_concept: Papers to retrieve per concept

        Returns:
            List of KnowledgeContext objects
        """
        contexts = []

        # Get context for concepts
        for concept in concepts:
            papers = await self.hermes.search(concept, top_k=top_k_per_concept)

            # Get related concepts from HERMES
            related = await self.hermes.get_related_entities(concept, max_hops=1)
            related_names = [e.name for e, _ in related[:5]]

            contexts.append(KnowledgeContext(
                concept=concept,
                papers=papers,
                related_concepts=related_names,
            ))

        # Get context for technologies
        if technologies:
            for tech in technologies:
                papers = await self.hermes.search(
                    f"{tech} best practices",
                    top_k=top_k_per_concept,
                )
                contexts.append(KnowledgeContext(
                    concept=tech,
                    papers=papers,
                    related_concepts=[],
                ))

        return contexts

    async def suggest_learning_resources(
        self,
        technology: str,
        proficiency: float,
    ) -> list[HermesSearchResult]:
        """
        Suggest learning resources based on proficiency level.

        Args:
            technology: Technology name
            proficiency: User's proficiency level (0-1)

        Returns:
            List of relevant papers/resources
        """
        # Tailor query based on proficiency
        if proficiency < 0.3:
            # Beginner - look for tutorials and introductions
            query = f"{technology} introduction tutorial beginner"
        elif proficiency < 0.7:
            # Intermediate - look for best practices and patterns
            query = f"{technology} best practices patterns intermediate"
        else:
            # Advanced - look for advanced topics and cutting edge
            query = f"{technology} advanced optimization cutting edge"

        return await self.hermes.search(query, top_k=5)

    async def find_related_concepts_in_knowledge(
        self,
        entity: Entity,
    ) -> list[str]:
        """
        Find concepts related to an entity using HERMES knowledge.

        Args:
            entity: Entity to find related concepts for

        Returns:
            List of related concept names
        """
        related = await self.hermes.get_related_entities(entity.name, max_hops=2)
        return [e.name for e, score in related if score > 0.3]

    def link_memory_to_knowledge(
        self,
        memory_entity: Entity,
        hermes_entity_name: str,
        confidence: float = 0.7,
    ) -> None:
        """
        Create a link between a memory entity and a HERMES knowledge entity.

        Args:
            memory_entity: The memory entity
            hermes_entity_name: Name of the HERMES entity
            confidence: Confidence in the link
        """
        # Store the link in metadata
        memory_entity.metadata.setdefault("hermes_links", []).append({
            "entity_name": hermes_entity_name,
            "confidence": confidence,
        })
        self.db.update_entity(memory_entity)

        logger.debug(f"Linked memory '{memory_entity.name}' to HERMES '{hermes_entity_name}'")


class ContextualKnowledgeRetriever:
    """
    Retrieves relevant knowledge based on current conversation context.

    Uses both:
    - Mnemosyne memory (user model, preferences, history)
    - HERMES knowledge (papers, entities, relationships)
    """

    def __init__(self, hermes_url: str = "http://hermes:8780"):
        self.db = get_db()
        self.bridge = KnowledgeBridge(hermes_url)

    async def close(self):
        """Close connections."""
        await self.bridge.close()

    async def get_context_for_session(
        self,
        project_name: str | None = None,
        mentioned_concepts: list[str] | None = None,
        mentioned_technologies: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Get comprehensive context for a session.

        Combines memory and knowledge to provide:
        - User's background with relevant technologies
        - Papers relevant to current discussion
        - Suggested resources based on proficiency gaps

        Args:
            project_name: Current project (if any)
            mentioned_concepts: Concepts mentioned in conversation
            mentioned_technologies: Technologies mentioned

        Returns:
            Context dictionary
        """
        context = {
            "memory_context": {},
            "knowledge_context": [],
            "suggestions": [],
        }

        # Get memory context
        from ..graph.operations import GraphOperations
        ops = GraphOperations()

        if project_name:
            project = self.db.get_entity_by_name(EntityType.PROJECT, project_name)
            if project:
                context["memory_context"]["project"] = {
                    "name": project.name,
                    "technologies": [
                        e.name for e, _ in self.db.get_neighbors(project.id, direction="out")
                        if e.entity_type == EntityType.TECHNOLOGY
                    ],
                }

        # Get user's technology proficiencies
        from ..inference.proficiency import ProficiencyInferrer
        prof_inferrer = ProficiencyInferrer()
        proficiencies = prof_inferrer.get_all_proficiencies()
        context["memory_context"]["proficiencies"] = proficiencies

        # Get knowledge context for mentioned concepts
        if mentioned_concepts:
            context["knowledge_context"] = await self.bridge.get_knowledge_context(
                mentioned_concepts,
                mentioned_technologies,
            )

        # Suggest resources for technologies where user is learning
        if mentioned_technologies:
            for tech in mentioned_technologies:
                prof = proficiencies.get(tech.lower(), 0.5)
                if prof < 0.7:  # Not an expert yet
                    resources = await self.bridge.suggest_learning_resources(tech, prof)
                    if resources:
                        context["suggestions"].append({
                            "technology": tech,
                            "proficiency": prof,
                            "resources": [
                                {"title": r.title, "paper_id": r.paper_id}
                                for r in resources[:3]
                            ],
                        })

        return context
