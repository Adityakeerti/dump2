import argparse
import asyncio

from src.database import session_factory
from src.knowledge.retrieval import retrieve


async def main(query: str, tenants: list[str]) -> None:
    async with session_factory() as session:
        for hit in await retrieve(session, query, tenants):
            print(
                f"{hit.doc_id}\tvector={hit.vector_score:.4f}\tlexical_rank={hit.lexical_rank}\tfused={hit.fused_score:.6f}\t{hit.text[:160]}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--tenant", action="append", default=["public"])
    args = parser.parse_args()
    asyncio.run(main(args.query, args.tenant))
