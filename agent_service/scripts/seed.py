import asyncio
from pathlib import Path

from src.database import session_factory
from src.knowledge.ingestion import ingest_file
from src.knowledge.schemas import DocumentMetadata
from src.models import AgentConfig


async def seed() -> None:
    async with session_factory() as session:
        for agent in [
            AgentConfig(
                agent_id="general",
                tier="general",
                display_name="City Sense",
                system_prompt="Answer only from verified context.",
                # Municipal documents (Nagar Nigam rules, wards, property tax) are public civic information.
                tenants=["public", "municipal"],
                tools=[
                    "handoff",
                    "ask_clarification",
                    "get_events",
                    "get_active_alerts",
                    "search_schemes",
                ],
                min_similarity=0.85,
            ),
            AgentConfig(
                agent_id="municipal",
                tier="professional",
                display_name="Municipal Agent",
                system_prompt="Answer only from verified municipal context.",
                tenants=["public", "municipal"],
                tools=[
                    "create_complaint",
                    "get_complaint_status",
                    "get_events",
                    "get_active_alerts",
                    "search_schemes",
                    "ask_clarification",
                    "handoff",
                ],
                min_similarity=0.85,
            ),
        ]:
            existing = await session.get(AgentConfig, agent.agent_id)
            if not existing:
                session.add(agent)
            elif not set(agent.tenants) <= set(existing.tenants):
                # Widen an existing persona's document access; never narrow what an admin configured.
                existing.tenants = sorted(set(existing.tenants) | set(agent.tenants))
        await session.commit()
        for tenant in ("public", "municipal"):
            folder = Path("data/corpus") / tenant
            for path in sorted(folder.glob("**/*")):
                if path.is_file() and path.suffix.lower() in {".md", ".txt", ".pdf"}:
                    meta_path = path.with_suffix(".meta.json")
                    metadata = None
                    if meta_path.exists():
                        metadata = DocumentMetadata.model_validate_json(
                            meta_path.read_text(encoding="utf-8")
                        )
                    doc = await ingest_file(session, path, tenant_id=tenant, metadata=metadata)
                    doc.verification_status = "verified"
                    await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
