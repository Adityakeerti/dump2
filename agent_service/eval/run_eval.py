"""Evaluate retrieval with declared labels; no LLM calls are made."""

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.agent.service import evidence_for, get_agent
from src.config import settings
from src.database import session_factory
from src.knowledge.chunking import chunk_text
from src.knowledge.embeddings import get_embedder
from src.knowledge.ingestion import read_source
from src.knowledge.retrieval import RetrievalHit, retrieve
from src.knowledge.schemas import DocumentMetadata
from src.models import utcnow


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    language: Literal["en", "hi"]
    question: str = Field(min_length=1)
    answerable: bool
    agentId: str = "general"
    cityId: str = "dehradun"
    expected_doc: str | None = None
    expected_title: str | None = None


def metrics(records: list[tuple[Question, list]], threshold: float) -> dict:
    total = {"en": 0, "hi": 0}
    correct = {"en": 0, "hi": 0}
    tp = fp = fn = 0
    unlabeled = 0
    for question, hits in records:
        if question.answerable:
            if question.expected_doc or question.expected_title:
                total[question.language] += 1
                correct[question.language] += any(
                    str(h.doc_id) == question.expected_doc
                    or (question.expected_title and h.title == question.expected_title)
                    for h in hits[:4]
                )
            else:
                unlabeled += 1
        abstained = evidence_for(hits, threshold, question.cityId).abstain
        tp += abstained and not question.answerable
        fp += abstained and question.answerable
        fn += not abstained and not question.answerable
    return {
        "threshold": threshold,
        "hit_at_4": {lang: round(correct[lang] / total[lang], 4) if total[lang] else None for lang in total},
        "labeled_answerable_counts": total,
        "unlabeled_answerable": unlabeled,
        "abstain_precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "abstain_recall": round(tp / (tp + fn), 4) if tp + fn else None,
    }


def load_in_memory_corpus(corpus_dir: Path) -> list[dict]:
    chunks_data = []
    embedder = get_embedder()
    for tenant in ("public", "municipal"):
        folder = corpus_dir / tenant
        if not folder.exists():
            continue
        for path in sorted(folder.glob("**/*")):
            if path.is_file() and path.suffix.lower() in {".md", ".txt", ".pdf"}:
                meta_path = path.with_suffix(".meta.json")
                if meta_path.exists():
                    metadata = DocumentMetadata.model_validate_json(meta_path.read_text(encoding="utf-8"))
                else:
                    metadata = DocumentMetadata(
                        tenant_id=tenant,
                        title=path.stem,
                        publisher="Local corpus",
                        jurisdiction="dehradun" if tenant == "municipal" else "national",
                        language="hi" if "_hi" in path.stem else "en",
                    )
                content = read_source(path)
                chunks = chunk_text(content)
                doc_id = uuid4()
                now = utcnow()
                for c in chunks:
                    vec = embedder.embed(f"passage: {c.text}")
                    chunks_data.append(
                        {
                            "chunk_id": uuid4(),
                            "doc_id": doc_id,
                            "tenant_id": metadata.tenant_id,
                            "title": metadata.title,
                            "source_url": str(metadata.source_url) if metadata.source_url else None,
                            "jurisdiction": metadata.jurisdiction,
                            "text": c.text,
                            "section": c.section,
                            "embedding": vec,
                            "fetched_at": now,
                            "expires_at": metadata.expires_at,
                        }
                    )
    return chunks_data


def retrieve_in_memory(
    chunks_data: list[dict], query: str, tenants: list[str], limit: int = 6
) -> list[RetrievalHit]:
    eligible = [c for c in chunks_data if c["tenant_id"] in tenants]
    if not eligible:
        return []
    embedder = get_embedder()
    q_vec = embedder.embed(f"query: {query}")

    # Vector leg
    def dot(v1: list[float], v2: list[float]) -> float:
        return sum(a * b for a, b in zip(v1, v2, strict=True))

    scored_vector = [(c, dot(c["embedding"], q_vec)) for c in eligible]
    scored_vector.sort(key=lambda x: x[1], reverse=True)
    v_ranks = {id(c): rank + 1 for rank, (c, _) in enumerate(scored_vector[:20])}

    # Lexical leg (token match overlap)
    q_tokens = set(re.findall(r"\w+", query.lower()))
    scored_lexical = []
    for c in eligible:
        c_tokens = re.findall(r"\w+", c["text"].lower())
        overlap = sum(1 for t in c_tokens if t in q_tokens)
        if overlap > 0:
            scored_lexical.append((c, overlap))
    scored_lexical.sort(key=lambda x: x[1], reverse=True)
    l_ranks = {id(c): rank + 1 for rank, (c, _) in enumerate(scored_lexical[:20])}

    # Fused RRF leg (k=60)
    candidate_ids = set(v_ranks.keys()) | set(l_ranks.keys())
    id_to_chunk = {id(c): c for c in eligible}
    id_to_vscore = {id(c): score for c, score in scored_vector}

    fused = []
    for cid in candidate_ids:
        vr = v_ranks.get(cid)
        lr = l_ranks.get(cid)
        f_score = (1.0 / (60 + vr) if vr else 0.0) + (1.0 / (60 + lr) if lr else 0.0)
        c = id_to_chunk[cid]
        v_score = id_to_vscore.get(cid, 0.0)
        fused.append((c, v_score, vr, lr, f_score))

    fused.sort(key=lambda x: x[4], reverse=True)

    return [
        RetrievalHit(
            chunk_id=c["chunk_id"],
            doc_id=c["doc_id"],
            tenant_id=c["tenant_id"],
            text=c["text"],
            section=c["section"],
            vector_score=v_score,
            vector_rank=vr,
            lexical_rank=lr,
            fused_score=f_score,
            jurisdiction=c["jurisdiction"],
            verified=True,
            expires_at=c["expires_at"],
            title=c["title"],
            source_url=c["source_url"],
            fetched_at=c["fetched_at"],
        )
        for c, v_score, vr, lr, f_score in fused[:limit]
    ]


async def run(path: Path, thresholds: list[float], in_memory: bool = False) -> None:
    questions = [
        Question.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len({q.id for q in questions}) != len(questions):
        raise ValueError("Question IDs must be unique")
    records = []

    use_in_memory = in_memory
    if not use_in_memory:
        try:
            async with session_factory() as session:
                for question in questions:
                    agent = await get_agent(session, question.agentId)
                    hits = await retrieve(session, question.question, agent.tenants)
                    records.append((question, hits))
        except Exception:
            use_in_memory = True
            records = []

    if use_in_memory:
        corpus = load_in_memory_corpus(Path("data/corpus"))
        tenant_map = {
            "general": ["public"],
            "municipal": ["public", "municipal"],
        }
        for question in questions:
            tenants = tenant_map.get(question.agentId, ["public"])
            hits = retrieve_in_memory(corpus, question.question, tenants)
            records.append((question, hits))

    report = {
        "questions": len(questions),
        "embedding_model": settings.embed_model
        if settings.use_sentence_transformer
        else "demo-hash-v1",
        "results": [metrics(records, t) for t in thresholds],
    }
    output = json.dumps(report, indent=2, ensure_ascii=False)
    print(output)
    report_file = Path("eval/eval_report.json")
    report_file.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=Path("eval/questions.jsonl"))
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.7, 0.75, 0.8, 0.85, 0.9])
    parser.add_argument("--in-memory", action="store_true", help="Force in-memory evaluation against data/corpus")
    args = parser.parse_args()
    asyncio.run(run(args.questions, args.thresholds, in_memory=args.in_memory))
