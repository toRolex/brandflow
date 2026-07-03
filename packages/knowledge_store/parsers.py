from __future__ import annotations

from pathlib import Path


def parse_pdf(file_path: Path) -> str:
    """Parse a PDF file and return extracted text using PyMuPDF (fitz).

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text content as a single string.

    Raises:
        FileNotFoundError: If the file does not exist.
        fitz.FileDataError: If the file is not a valid PDF.
    """
    import fitz

    doc = fitz.open(str(file_path))
    try:
        text_parts: list[str] = []
        for page in doc:
            page_text = page.get_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)
    finally:
        doc.close()


def parse_docx(file_path: Path) -> str:
    """Parse a DOCX file and return extracted text using python-docx.

    Args:
        file_path: Path to the .docx file.

    Returns:
        Extracted text content as a single string (paragraphs joined by newlines).

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    from docx import Document

    doc = Document(str(file_path))
    text_parts: list[str] = []
    for paragraph in doc.paragraphs:
        if paragraph.text:
            text_parts.append(paragraph.text)
    return "\n".join(text_parts)


def parse_file(file_path: Path) -> str:
    """Auto-detect file type by extension and parse accordingly.

    Supported formats: .txt, .pdf, .docx

    Args:
        file_path: Path to the file to parse.

    Returns:
        Extracted text content.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file type is not supported.
    """
    ext = file_path.suffix.lower()

    if ext == ".txt":
        return file_path.read_text(encoding="utf-8")
    elif ext == ".pdf":
        return parse_pdf(file_path)
    elif ext == ".docx":
        return parse_docx(file_path)
    else:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: .txt, .pdf, .docx"
        )
