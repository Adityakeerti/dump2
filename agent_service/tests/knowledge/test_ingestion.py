import pymupdf
import pytest

from src.knowledge.chunking import chunk_text
from src.knowledge.ingestion import parse_source, read_source


def test_real_pdf_parser(tmp_path):
    path = tmp_path / "document.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((70, 70), "Required documents: identity proof.")
        pdf.save(str(path))
    assert "identity proof" in read_source(path)


def test_bad_pdf_and_non_utf8_are_rejected(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a PDF")
    with pytest.raises(Exception):
        read_source(bad)
    text = tmp_path / "bad.txt"
    text.write_bytes(b"\xff\xfe\xff")
    with pytest.raises(UnicodeError):
        read_source(text)


def test_long_prose_is_bounded_and_table_rows_remain_intact():
    chunks = chunk_text(" ".join(["word"] * 1500))
    assert all(len(chunk.text.split()) <= 400 for chunk in chunks)
    row = "| Identity | Required |"
    assert any(row in chunk.text.splitlines() for chunk in chunk_text(row))
    with pytest.raises(ValueError):
        chunk_text("1. " + "word " * 500)


async def test_isolated_parser_handles_text_and_rejects_bad_files(tmp_path):
    path = tmp_path / "text.txt"
    path.write_text("Verified content", encoding="utf-8")
    assert await parse_source(path) == "Verified content"
    path.write_bytes(b"\xff\xfe\xff")
    with pytest.raises(ValueError):
        await parse_source(path)
