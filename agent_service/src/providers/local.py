def _extractive_answer(context: list[str], language: str | None) -> str:
    if not context:
        return "I do not have verified information for that question."
    # No translation is fabricated: Hindi mode must retrieve Hindi passages.
    prefix = "सत्यापित स्रोतों से:\n" if language == "hi" else "Based on verified sources:\n"
    return prefix + "\n\n".join(context[:2])
