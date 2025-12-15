from __future__ import annotations

"""HERMES integration for Mnemosyne."""
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class HermesSearchResult:
    """A search result from HERMES."""
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    score: float
    chunk_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HermesEntity:
    """An entity from HERMES knowledge graph."""
    name: str
    entity_type: str
    confidence: float
    paper_ids: list[str] = field(default_factory=list)


class HermesClient:
    """
    HTTP client for HERMES knowledge retrieval system.

    HERMES provides:
    - Semantic search over research papers
    - Entity extraction from papers
    - Knowledge graph queries
    """

    def __init__(
        self,
        base_url: str = "http://hermes:8780",
        timeout: float = 30.0,
    ):
        """
        Initialize HERMES client.

        Args:
            base_url: HERMES API base URL
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    async def health_check(self) -> bool:
        """
        Check if HERMES is available.

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = await self._client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"HERMES health check failed: {e}")
            return False

    async def search(
        self,
        query: str,
        top_k: int = 5,
        collection: str | None = None,
        min_score: float = 0.0,
    ) -> list[HermesSearchResult]:
        """
        Search for relevant papers/chunks.

        Args:
            query: Search query
            top_k: Number of results to return
            collection: Optional collection to search in
            min_score: Minimum relevance score

        Returns:
            List of search results
        """
        try:
            params = {
                "q": query,
                "top_k": top_k,
            }
            if collection:
                params["collection"] = collection

            response = await self._client.get(
                f"{self.base_url}/search",
                params=params,
            )
            response.raise_for_status()

            data = response.json()
            results = []

            for item in data.get("results", []):
                score = item.get("score", 0)
                if score >= min_score:
                    results.append(HermesSearchResult(
                        paper_id=item.get("paper_id", ""),
                        title=item.get("title", ""),
                        authors=item.get("authors", []),
                        abstract=item.get("abstract", ""),
                        score=score,
                        chunk_text=item.get("chunk_text"),
                        metadata=item.get("metadata", {}),
                    ))

            return results

        except Exception as e:
            logger.error(f"HERMES search failed: {e}")
            return []

    async def get_paper(self, paper_id: str) -> dict[str, Any] | None:
        """
        Get a paper by ID.

        Args:
            paper_id: Paper ID (e.g., arxiv ID)

        Returns:
            Paper data or None if not found
        """
        try:
            response = await self._client.get(
                f"{self.base_url}/papers/{paper_id}"
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"HERMES get_paper failed: {e}")
            return None

    async def get_entities(
        self,
        paper_id: str | None = None,
        entity_type: str | None = None,
    ) -> list[HermesEntity]:
        """
        Get entities from HERMES knowledge graph.

        Args:
            paper_id: Optional paper ID to filter by
            entity_type: Optional entity type to filter by

        Returns:
            List of entities
        """
        try:
            params = {}
            if paper_id:
                params["paper_id"] = paper_id
            if entity_type:
                params["type"] = entity_type

            response = await self._client.get(
                f"{self.base_url}/entities",
                params=params,
            )
            response.raise_for_status()

            data = response.json()
            entities = []

            for item in data.get("entities", []):
                entities.append(HermesEntity(
                    name=item.get("name", ""),
                    entity_type=item.get("type", ""),
                    confidence=item.get("confidence", 0.5),
                    paper_ids=item.get("paper_ids", []),
                ))

            return entities

        except Exception as e:
            logger.error(f"HERMES get_entities failed: {e}")
            return []

    async def get_related_entities(
        self,
        entity_name: str,
        max_hops: int = 2,
    ) -> list[tuple[HermesEntity, float]]:
        """
        Get entities related to a given entity.

        Args:
            entity_name: Name of the entity
            max_hops: Maximum graph traversal depth

        Returns:
            List of (entity, relevance_score) tuples
        """
        try:
            response = await self._client.get(
                f"{self.base_url}/entities/{entity_name}/related",
                params={"max_hops": max_hops},
            )
            response.raise_for_status()

            data = response.json()
            related = []

            for item in data.get("related", []):
                entity = HermesEntity(
                    name=item.get("name", ""),
                    entity_type=item.get("type", ""),
                    confidence=item.get("confidence", 0.5),
                    paper_ids=item.get("paper_ids", []),
                )
                score = item.get("relevance", 0.5)
                related.append((entity, score))

            return related

        except Exception as e:
            logger.error(f"HERMES get_related_entities failed: {e}")
            return []

    async def search_v2(
        self,
        query: str,
        top_k: int = 5,
        use_entity_ranking: bool = True,
    ) -> list[HermesSearchResult]:
        """
        Search using HERMES v2 with entity-first ranking.

        Args:
            query: Search query
            top_k: Number of results
            use_entity_ranking: Whether to use entity-first ranking

        Returns:
            List of search results
        """
        try:
            response = await self._client.post(
                f"{self.base_url}/v2/search",
                json={
                    "query": query,
                    "top_k": top_k,
                    "use_entity_ranking": use_entity_ranking,
                },
            )
            response.raise_for_status()

            data = response.json()
            results = []

            for item in data.get("results", []):
                results.append(HermesSearchResult(
                    paper_id=item.get("paper_id", ""),
                    title=item.get("title", ""),
                    authors=item.get("authors", []),
                    abstract=item.get("abstract", ""),
                    score=item.get("score", 0),
                    chunk_text=item.get("chunk_text"),
                    metadata=item.get("metadata", {}),
                ))

            return results

        except Exception as e:
            logger.error(f"HERMES v2 search failed: {e}")
            return []


# Synchronous wrapper for when async isn't needed
class HermesClientSync:
    """Synchronous wrapper for HermesClient."""

    def __init__(
        self,
        base_url: str = "http://hermes:8780",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health_check(self) -> bool:
        """Check if HERMES is available."""
        try:
            response = httpx.get(
                f"{self.base_url}/health",
                timeout=self.timeout,
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"HERMES health check failed: {e}")
            return False

    def search(
        self,
        query: str,
        top_k: int = 5,
        collection: str | None = None,
    ) -> list[HermesSearchResult]:
        """Search for relevant papers/chunks."""
        try:
            params = {"q": query, "top_k": top_k}
            if collection:
                params["collection"] = collection

            response = httpx.get(
                f"{self.base_url}/search",
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()

            data = response.json()
            results = []

            for item in data.get("results", []):
                results.append(HermesSearchResult(
                    paper_id=item.get("paper_id", ""),
                    title=item.get("title", ""),
                    authors=item.get("authors", []),
                    abstract=item.get("abstract", ""),
                    score=item.get("score", 0),
                    chunk_text=item.get("chunk_text"),
                    metadata=item.get("metadata", {}),
                ))

            return results

        except Exception as e:
            logger.error(f"HERMES search failed: {e}")
            return []
