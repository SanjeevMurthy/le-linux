#!/usr/bin/env python3
"""
PDF Extraction Script for Linux Knowledge Base.

Extracts structured markdown from PDF books, organized by chapter.
Requires: PyMuPDF >= 1.23.0 (pip install pymupdf)

Usage: python3 scripts/extract_pdfs.py
"""

import fitz  # PyMuPDF
import json
import os
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# --- Configuration ---

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BASE_DIR / "sources"
OUTPUT_DIR = BASE_DIR / "sources" / "extracted"

BOOKS = [
    {
        "pdf": SOURCE_DIR / "How Linux Works_ What Every Superuser Should Know-No Starch Press (2021).pdf",
        "output_dir": OUTPUT_DIR / "how-linux-works",
        "short_name": "HLW",
        "full_name": "How Linux Works: What Every Superuser Should Know (2021)",
        "has_toc": True,
    },
    {
        "pdf": SOURCE_DIR / "Linux Basics for Hackers, 2nd Edition.pdf",
        "output_dir": OUTPUT_DIR / "linux-basics-hackers",
        "short_name": "LBH",
        "full_name": "Linux Basics for Hackers, 2nd Edition",
        "has_toc": True,
    },
    {
        "pdf": SOURCE_DIR / "UNIX and Linux System Administration Handbook-Addison-Wesley (2017).pdf",
        "output_dir": OUTPUT_DIR / "ulsah",
        "short_name": "ULSAH",
        "full_name": "UNIX and Linux System Administration Handbook, 5th Edition (2017)",
        "has_toc": True,
    },
]


@dataclass
class Chapter:
    """Represents an extracted chapter."""
    title: str
    chapter_num: int
    start_page: int  # 0-indexed
    end_page: int    # 0-indexed, exclusive
    book_name: str
    book_short: str


@dataclass
class ExtractionResult:
    """Result of extracting a single book."""
    book_short: str
    book_full: str
    chapters_extracted: int
    files_generated: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    status: str = "success"


# --- TOC Parsing ---

def get_chapters_from_toc(doc: fitz.Document, book: dict) -> list[Chapter]:
    """Extract chapter boundaries from PDF TOC bookmarks."""
    toc = doc.get_toc()
    if not toc:
        return []

    chapters = []
    chapter_num = 0

    for i, (level, title, page) in enumerate(toc):
        # Only top-level or level-2 entries that look like chapters
        if level > 2:
            continue

        # Skip front matter
        skip_patterns = [
            r"(?i)^(preface|foreword|acknowledge|copyright|table of contents|contents$|"
            r"about|index$|colophon|glossary$|afterword|safari|how to contact|"
            r"references|contributors|share your|download|get in touch|conventions|"
            r"who should|what this|livebook|other online|cover illustration)"
        ]
        if any(re.match(p, title.strip()) for p in skip_patterns):
            continue

        # Detect chapter-like entries
        is_chapter = (
            re.match(r"(?i)^(chapter\s+\d|part\s+\d|\d+[\.\s])", title.strip())
            or (level == 1 and len(title.strip()) > 3)
        )

        if not is_chapter:
            continue

        chapter_num += 1
        start_page = page - 1  # TOC pages are 1-indexed

        # Find end page: next chapter's start or end of doc
        end_page = doc.page_count
        for j in range(i + 1, len(toc)):
            next_level, _, next_page = toc[j]
            if next_level <= level:
                end_page = next_page - 1
                break

        chapters.append(Chapter(
            title=title.strip(),
            chapter_num=chapter_num,
            start_page=max(0, start_page),
            end_page=min(end_page, doc.page_count),
            book_name=book["full_name"],
            book_short=book["short_name"],
        ))

    return chapters


def get_chapters_by_font_analysis(doc: fitz.Document, book: dict) -> list[Chapter]:
    """Detect chapters in PDFs without TOC using font size analysis."""
    # Pass 1: collect all font sizes to find median body size
    font_sizes = []
    for page_num in range(doc.page_count):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if len(text) > 5:
                        font_sizes.append(span["size"])

    if not font_sizes:
        return []

    font_sizes.sort()
    median_size = font_sizes[len(font_sizes) // 2]
    header_threshold = median_size * 1.3

    # Pass 2: find section headers
    chapters = []
    chapter_num = 0

    for page_num in range(doc.page_count):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                line_text = "".join(span["text"] for span in line["spans"]).strip()
                max_font = max((span["size"] for span in line["spans"]), default=0)

                is_header = False
                if max_font >= header_threshold and len(line_text) > 5:
                    is_header = True
                if (line_text.isupper() and len(line_text) > 10
                        and not line_text.startswith("HTTP")):
                    is_header = True

                if is_header and len(line_text) < 200:
                    if chapters:
                        chapters[-1].end_page = page_num

                    chapter_num += 1
                    chapters.append(Chapter(
                        title=line_text,
                        chapter_num=chapter_num,
                        start_page=page_num,
                        end_page=doc.page_count,
                        book_name=book["full_name"],
                        book_short=book["short_name"],
                    ))

    # Merge very short "chapters" (< 1 page) into their successor
    merged = []
    for ch in chapters:
        page_span = ch.end_page - ch.start_page
        if merged and page_span < 1:
            merged[-1].end_page = ch.end_page
        else:
            merged.append(ch)

    return merged


# --- Text Extraction ---

def extract_page_text(page: fitz.Page) -> str:
    """Extract clean text from a single page."""
    text = page.get_text("text")
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'(?<=[a-z])-\n(?=[a-z])', '', text)
    return text


def extract_tables_from_page(page: fitz.Page) -> list[str]:
    """Extract tables using PyMuPDF's find_tables API."""
    tables_md = []
    try:
        tables = page.find_tables()
        for table in tables:
            data = table.extract()
            if not data or len(data) < 2:
                continue
            headers = data[0]
            md = "| " + " | ".join(str(h or "").strip() for h in headers) + " |\n"
            md += "| " + " | ".join("---" for _ in headers) + " |\n"
            for row in data[1:]:
                md += "| " + " | ".join(str(c or "").strip() for c in row) + " |\n"
            tables_md.append(md)
    except Exception:
        pass
    return tables_md


def tag_examples(text: str) -> list[str]:
    """Identify example/scenario passages in text."""
    examples = []
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        is_example = (
            re.match(r'(?i)^\s*(example|case study|scenario)\s*[:.]', line)
            or re.search(r'(?i)for example,|for instance,|e\.g\.,', line)
        )
        if is_example:
            example_lines = [line.strip()]
            j = i + 1
            while j < len(lines) and j < i + 10 and lines[j].strip():
                example_lines.append(lines[j].strip())
                j += 1
            examples.append('\n'.join(example_lines))
            i = j
        else:
            i += 1
    return examples


def tag_comparisons(text: str) -> list[str]:
    """Identify comparison/tradeoff passages near section headers."""
    comparisons = []
    lines = text.split('\n')
    header_indices = set()
    for i, line in enumerate(lines):
        if re.match(r'^#{1,4}\s', line) or (line.isupper() and len(line.strip()) > 10):
            for j in range(max(0, i - 2), min(len(lines), i + 15)):
                header_indices.add(j)

    for i, line in enumerate(lines):
        if re.search(r'(?i)\bvs\.?\b|\bpros and cons\b|\btradeoff\b|\btrade-off\b|\bcomparison\b', line):
            near_header = i in header_indices
            if near_header or re.match(r'^#{1,4}\s', lines[max(0, i-3)].strip() if i >= 3 else ''):
                start = max(0, i - 1)
                end = min(len(lines), i + 5)
                comparisons.append('\n'.join(l.strip() for l in lines[start:end] if l.strip()))
    return comparisons


# --- Chapter to Markdown ---

def chapter_to_markdown(doc: fitz.Document, chapter: Chapter) -> str:
    """Convert a chapter's pages to structured markdown."""
    full_text = ""
    all_tables = []

    for page_num in range(chapter.start_page, chapter.end_page):
        if page_num >= doc.page_count:
            break
        page = doc[page_num]
        full_text += extract_page_text(page) + "\n\n"
        all_tables.extend(extract_tables_from_page(page))

    examples = tag_examples(full_text)
    comparisons = tag_comparisons(full_text)

    md = f"# {chapter.title}\n\n"
    md += f"> Source: {chapter.book_name}, Chapter {chapter.chapter_num}, "
    md += f"Pages {chapter.start_page + 1}-{chapter.end_page}\n\n"

    md += "## Key Concepts\n\n"
    first_paragraphs = full_text[:2000].split('\n\n')
    for para in first_paragraphs[:5]:
        clean = para.strip()
        if clean and len(clean) > 20:
            md += f"- {clean[:200]}\n"
    md += "\n"

    md += "## Content\n\n"
    md += full_text.strip() + "\n\n"

    if examples:
        md += "## Examples & Scenarios\n\n"
        for ex in examples[:20]:
            md += f"- {ex}\n\n"

    if all_tables:
        md += "## Tables & Comparisons\n\n"
        for table in all_tables:
            md += table + "\n"

    if comparisons and not all_tables:
        md += "## Key Takeaways\n\n"
        for comp in comparisons[:10]:
            md += f"- {comp}\n\n"

    return md


def slugify(title: str) -> str:
    """Convert a chapter title to a filename slug."""
    title = re.sub(r'^(chapter\s+\d+[\.:]\s*|part\s+\d+[\.:]\s*|\d+[\.\s]+)', '', title, flags=re.IGNORECASE)
    slug = title.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug[:60]


# --- Main Extraction ---

def extract_book(book: dict) -> ExtractionResult:
    """Extract all chapters from a single book."""
    result = ExtractionResult(
        book_short=book["short_name"],
        book_full=book["full_name"],
        chapters_extracted=0,
    )

    pdf_path = book["pdf"]
    if not pdf_path.exists():
        result.status = "failed"
        result.errors.append(f"PDF not found: {pdf_path}")
        return result

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        result.status = "failed"
        result.errors.append(f"Failed to open PDF: {e}")
        return result

    if book["has_toc"]:
        chapters = get_chapters_from_toc(doc, book)
    else:
        chapters = get_chapters_by_font_analysis(doc, book)

    if not chapters:
        result.status = "failed"
        result.errors.append("No chapters detected")
        doc.close()
        return result

    output_dir = book["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  Extracting {book['short_name']}: {len(chapters)} chapters detected")

    for chapter in chapters:
        try:
            md_content = chapter_to_markdown(doc, chapter)
            slug = slugify(chapter.title)
            filename = f"ch{chapter.chapter_num:02d}-{slug}.md"
            filepath = output_dir / filename

            filepath.write_text(md_content, encoding="utf-8")
            result.files_generated.append(str(filepath.relative_to(BASE_DIR)))
            result.chapters_extracted += 1

            print(f"    + {filename} ({chapter.end_page - chapter.start_page} pages)")

        except Exception as e:
            result.errors.append(f"Chapter '{chapter.title}': {e}")
            print(f"    x {chapter.title}: {e}")

    doc.close()

    if result.chapters_extracted == 0:
        result.status = "failed"
    elif result.errors:
        result.status = "partial"

    return result


def write_manifest(results: list[ExtractionResult]):
    """Write extraction manifest for Phase 1 validation gate."""
    manifest = {
        "extraction_complete": True,
        "books": [],
        "total_files": 0,
        "total_errors": 0,
        "books_succeeded": 0,
        "books_failed": 0,
    }

    for r in results:
        book_entry = asdict(r)
        manifest["books"].append(book_entry)
        manifest["total_files"] += len(r.files_generated)
        manifest["total_errors"] += len(r.errors)
        if r.status in ("success", "partial"):
            manifest["books_succeeded"] += 1
        else:
            manifest["books_failed"] += 1

    manifest["phase1_gate"] = manifest["books_succeeded"] >= 3

    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def validate_output(manifest: dict):
    """Validate extraction output meets minimum quality bar."""
    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)

    for book in manifest["books"]:
        status_icon = "+" if book["status"] in ("success", "partial") else "x"
        print(f"  {status_icon} {book['book_short']}: {book['chapters_extracted']} chapters, "
              f"{len(book['files_generated'])} files")
        if book["errors"]:
            for err in book["errors"]:
                print(f"    ! {err}")

    print(f"\n  Total files: {manifest['total_files']}")
    print(f"  Total errors: {manifest['total_errors']}")
    print(f"  Books succeeded: {manifest['books_succeeded']}/3")
    print(f"  Phase 1 gate: {'PASS' if manifest['phase1_gate'] else 'FAIL'}")

    empty_files = []
    for book in manifest["books"]:
        for fpath in book["files_generated"]:
            full_path = BASE_DIR / fpath
            if full_path.exists():
                content = full_path.read_text(encoding="utf-8")
                if len(content) < 100:
                    empty_files.append(fpath)

    if empty_files:
        print(f"\n  ! {len(empty_files)} files below 100 char minimum:")
        for f in empty_files:
            print(f"    - {f}")

    print("=" * 60)
    return manifest["phase1_gate"]


def main():
    print("=" * 60)
    print("PDF EXTRACTION FOR LINUX KNOWLEDGE BASE")
    print("=" * 60)

    version = fitz.__version__.split(".")
    major, minor = int(version[0]), int(version[1])
    if major < 1 or (major == 1 and minor < 23):
        print(f"WARNING: PyMuPDF {fitz.__version__} < 1.23.0. Table extraction may not work.")
        print("Run: pip install --upgrade pymupdf")

    results = []
    for book in BOOKS:
        print(f"\nProcessing: {book['short_name']}...")
        result = extract_book(book)
        results.append(result)

    manifest = write_manifest(results)
    gate_passed = validate_output(manifest)

    if not gate_passed:
        print("\nPhase 1 gate FAILED. Books failed extraction.")
        print("Fix errors above and re-run, or proceed with degraded coverage.")
        sys.exit(1)
    else:
        print("\nPhase 1 gate PASSED. Ready for Phase 1 agents.")
        sys.exit(0)


if __name__ == "__main__":
    main()
