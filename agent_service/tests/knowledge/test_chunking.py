from src.knowledge.chunking import chunk_text


def test_chunking_preserves_heading_context():
    chunks = chunk_text(
        "# Eligibility\n\nResidents may apply.\n\n# Documents\n\nIdentity proof is required.",
        target_tokens=4,
        overlap_tokens=1,
    )
    assert chunks
    assert chunks[0].section == "Eligibility"
    assert any(chunk.section == "Documents" for chunk in chunks)
