from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.service import evidence_for
from src.agent.subagents.base import BaseSubAgent, SubAgentResult
from src.auth.schemas import Principal
from src.config import settings
from src.knowledge.retrieval import RetrievalHit, retrieve


class KnowledgeSpecialist(BaseSubAgent):
    name: str = "knowledge_specialist"
    description: str = "Specialist for verified civic knowledge retrieval, evidence validation, and grounded citations"

    async def execute(
        self,
        session: AsyncSession | None,
        principal: Principal,
        message: str,
        context: Any = None,
        language: str = "en",
        **kwargs: Any,
    ) -> SubAgentResult:
        execution_steps: list[str] = []

        # Step 1: retrieve_evidence
        execution_steps.append("retrieve_evidence")

        tenants = kwargs.get("tenants") or ["civic", "municipal", "general"]
        min_similarity = kwargs.get("min_similarity", 0.70)
        city = (
            getattr(context, "cityId", None)
            if context
            else None
        ) or (
            context.get("cityId") if isinstance(context, dict) else None
        ) or settings.default_city_id

        hits: list[RetrievalHit] = []

        if session is not None:
            try:
                hits = await retrieve(session, message, tenants, limit=kwargs.get("limit", 6))
            except Exception:
                hits = []

        if not hits:
            # Check offline corpus fallback
            try:
                from src.agent.offline import offline_corpus
                scored_docs = offline_corpus.search(message, language)
                for rank, (doc, score, excerpt) in enumerate(scored_docs[:3], 1):
                    # Map offline score to similarity scale (scores >= 5.0 map to >= 0.70)
                    normalized_score = min(score / 7.0, 0.95) if score >= 2.0 else 0.40
                    hits.append(
                        RetrievalHit(
                            chunk_id=uuid4(),
                            doc_id=uuid4(),
                            tenant_id="municipal",
                            text=excerpt or doc["content"][:500],
                            section=None,
                            vector_score=normalized_score,
                            vector_rank=rank,
                            lexical_rank=rank,
                            fused_score=score,
                            jurisdiction=doc.get("jurisdiction", city),
                            verified=True,
                            expires_at=None,
                            title=doc["title"],
                            source_url=doc["url"],
                            fetched_at=datetime.now(timezone.utc),
                        )
                    )
            except Exception:
                hits = []

        # Step 2: validate_evidence
        execution_steps.append("validate_evidence")

        if hits:
            evidence = evidence_for(hits, min_similarity, city)
        else:
            from src.knowledge.evidence import EvidenceResult
            evidence = EvidenceResult(usable_hits=[], abstain=True, flags=["no_hits"])

        # Step 3: synthesize_or_abstain
        execution_steps.append("synthesize_or_abstain")

        if evidence.abstain or not evidence.usable_hits:
            if language == "hi":
                answer = (
                    "मेरे पास इस प्रश्न के लिए देहरादून नागरिक रिकॉर्ड में सीधे सत्यापित जानकारी नहीं है। "
                    "सहायता के लिए आप नगर निगम देहरादून नागरिक हेल्पलाइन (1800-180-4107) पर संपर्क कर सकते हैं या नागरिक शिकायत दर्ज कर सकते हैं।"
                )
            else:
                answer = (
                    "I do not have verified municipal information for that specific inquiry in Dehradun civic records.\n\n"
                    "For assistance, you can report a civic issue directly to Nagar Nigam Dehradun, "
                    "call the Citizen Toll-Free Helpline at **1800-180-4107**, or explore our live alerts."
                )

            return SubAgentResult(
                status="ABSTAINED",
                response_text=answer,
                sources=[],
                cta="file_complaint",
                execution_steps=execution_steps,
                metadata={"abstain": True, "flags": list(evidence.flags)},
            )

        supported_ids = {h.chunk_id for h in evidence.usable_hits}
        usable = [h for h in hits if str(h.chunk_id) in supported_ids]
        if not usable:
            usable = hits[:1]

        best = usable[0]
        sources = [
            {
                "docId": str(h.doc_id),
                "title": h.title,
                "url": h.source_url,
                "excerpt": h.text[:500],
                "fetchedAt": h.fetched_at.isoformat() if hasattr(h.fetched_at, "isoformat") else str(h.fetched_at),
                "stale": False,
            }
            for h in usable
        ]

        # Synthesize via live LLM with grounded fallback
        response_text = None
        try:
            from src.providers.registry import generate_with_failover
            gen = await generate_with_failover(
                system=(
                    f"You are City Sense, the municipal AI assistant for Dehradun. "
                    f"Answer the user's question directly, clearly, and informatively using the verified evidence provided. "
                    f"Mention the verified source '{best.title}' in your answer."
                ),
                user=message,
                context=[h.text for h in usable[:2]],
                language=language,
            )
            if gen and gen.text and len(gen.text.strip()) > 20:
                response_text = gen.text.strip()
        except Exception:
            pass

        if not response_text:
            if language == "hi":
                response_text = (
                    f"सत्यापित स्रोत ({best.title}) के अनुसार:\n\n{best.text.strip()}\n\n"
                    f"*स्रोत: {best.title}*"
                )
            else:
                response_text = (
                    f"Based on verified municipal records ({best.title}):\n\n{best.text.strip()}\n\n"
                    f"*Source: {best.title}*"
                )

        return SubAgentResult(
            status="ANSWERED",
            response_text=response_text,
            sources=sources,
            cta=None,
            execution_steps=execution_steps,
            metadata={"usable_count": len(usable), "top_title": best.title},
        )

    async def recommend_businesses(
        self, message: str, principal: Principal, language: str = "en", trace: Any = None,
        latitude: float | None = None, longitude: float | None = None, area: str | None = None,
    ) -> SubAgentResult:
        """Popular local businesses from the city directory, nearest to the named place or the citizen."""
        import re as _re

        from src.agent.tool_registry import KNOWLEDGE, call_tool

        m = _re.search(r"\b(cafe|caf\u00e9|coffee|bakery|bakeries|restaurant|food|eat|sweets?|mithai|book(?:s|store|shop)?|"
                       r"shop(?:ping)?|market|clothes|outfitters?)\b", message, _re.I)
        category = None
        if m:
            word = m.group(1).lower()
            category = {"coffee": "cafe", "caf\u00e9": "cafe", "bakeries": "bakery", "food": None, "eat": None,
                        "sweet": "sweets", "mithai": "sweets", "book": "bookstore", "books": "bookstore",
                        "bookshop": "bookstore", "shop": "shopping", "market": "shopping", "clothes": "shopping",
                        "outfitter": "shopping", "outfitters": "shopping"}.get(word, word)
        res = await call_tool(KNOWLEDGE, "find_local_businesses", {"area": area or "", "category": category, "limit": 5},
                              principal.user_id, trace, latitude=latitude, longitude=longitude)
        items = res.get("items") or []
        if not items and category:  # nothing in that category: show what is popular nearby instead
            res = await call_tool(KNOWLEDGE, "find_local_businesses", {"area": area or "", "limit": 5},
                                  principal.user_id, trace, latitude=latitude, longitude=longitude)
            items = res.get("items") or []
        hi = language == "hi"
        if items:
            lines = ["लोकप्रिय स्थानीय व्यवसाय:" if hi else "Popular local businesses:"]
            for b in items:
                dist = f" · {b['distanceMeters'] / 1000:.1f} km" if b.get("distanceMeters") is not None else ""
                lines.append(f"- **{b['name']}** ({b['category']}, {b['locality']}{dist}) — {b['description']}")
            text = "\n".join(lines)
        else:
            text = "निर्देशिका में अभी कोई व्यवसाय नहीं मिला।" if hi else "No businesses found in the city directory right now."
        return SubAgentResult(status="ANSWERED", response_text=text, sources=[], cta="explore_businesses",
                              execution_steps=["find_local_businesses"],
                              metadata={"card": {"businesses": items}})

    async def area_brief(self, area: str, principal: Principal, trace: Any = None) -> list[str]:
        """Ward / zone facts and helplines for an area, from the verified corpus (this desk's own tool)."""
        from src.agent.tool_registry import KNOWLEDGE, call_tool

        res = await call_tool(KNOWLEDGE, "get_ward_councillor_info", {"area": area[:200]}, principal.user_id, trace)
        return [p["excerpt"] for p in res.get("passages", [])[:2]]

