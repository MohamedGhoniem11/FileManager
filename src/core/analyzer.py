"""
Analyzer — ContentProfile extraction (roadmap 4.1, ADR-011)
-----------------------------------------------------------
Pulls real signals out of file content using the standard library only:
- PDF: text from (optionally FlateDecode-compressed) content streams
- PNG: IHDR dimensions + tEXt metadata
- JPEG: APP1 Exif presence + SOF dimensions
- code: shebang + language + keyword detection
- archives: member manifests (zip/tar)
- everything else: a typed profile (binary/text/unknown), never an exception

This is the deterministic, testable core of the "intelligence story": the
classifier consumes ContentProfile instead of trusting the extension alone.
"""
import io
import re
import struct
import tarfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Known code extensions used when no shebang is present.
_CODE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".c", ".cpp",
    ".h", ".hpp", ".java", ".rb", ".php", ".cs", ".swift", ".kt", ".sh",
    ".bash", ".zsh", ".pl", ".lua", ".r", ".m", ".sql",
}

# Shebang -> language name (lowercase, for metadata + subcategory signals).
_SHEBANG_LANGS = {
    "python": "python", "python3": "python",
    "bash": "bash", "sh": "bash", "zsh": "bash",
    "node": "javascript", "nodejs": "javascript",
    "ruby": "ruby", "perl": "perl", "php": "php",
    "fish": "fish",
}

_STOPWORDS = {
    "the", "a", "an", "of", "to", "for", "and", "or", "in", "on", "with",
    "this", "that", "is", "are", "was", "were", "it", "as", "at", "by",
}


@dataclass
class ContentProfile:
    """Typed result of content inspection — the classifier's raw input."""
    kind: str                                          # pdf|image|code|text|archive|binary|unknown
    text_sample: str = ""                              # extracted text (pdf/code/text)
    dimensions: Optional[Tuple[int, int]] = None       # images
    keywords: List[str] = field(default_factory=list)  # top content tokens
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_content(self) -> bool:
        """True when we extracted any usable signal (text/tokens/dims/manifest)."""
        return bool(self.text_sample or self.keywords or self.dimensions
                    or self.metadata)


def extract_profile(file_path: Path) -> ContentProfile:
    """Inspects a file and returns its ContentProfile. Raises if missing."""
    if not file_path.exists():
        raise FileNotFoundError(str(file_path))
    if file_path.is_dir():
        return ContentProfile(kind="directory")

    magic = _read_head(file_path)
    suffix = file_path.suffix.lower()

    if magic.startswith(b"%PDF-"):
        return _pdf_profile(file_path, magic)
    if magic.startswith(b"\x89PNG\r\n\x1a\n"):
        return _png_profile(magic)
    if magic.startswith(b"\xff\xd8"):
        return _jpeg_profile(magic)
    if magic.startswith(b"PK\x03\x04"):
        return _archive_profile(file_path, "zip")
    if _is_tar(file_path):
        return _archive_profile(file_path, "tar")
    if suffix in _CODE_EXTS or _looks_like_code(file_path):
        return _code_profile(file_path)
    if _is_mostly_text(file_path):
        return _text_profile(file_path)
    return ContentProfile(kind="binary" if suffix else "unknown")


# ---------------------------------------------------------------------------
# heads and sniffing helpers
# ---------------------------------------------------------------------------

def _read_head(file_path: Path, n: int = 8192) -> bytes:
    """First n bytes of a file; empty bytes on error."""
    try:
        with open(file_path, "rb") as f:
            return f.read(n)
    except OSError:
        return b""


def _is_tar(file_path: Path) -> bool:
    """Cheap tar check on the 512-byte header magic (no full parse)."""
    head = _read_head(file_path, 265)
    return b"ustar" in head


def _is_mostly_text(file_path: Path) -> bool:
    """True when the first chunk decodes as printable text with few NULs."""
    head = _read_head(file_path)
    if not head:
        return False
    if b"\x00" in head[:512]:
        return False
    sample = head[:2048]
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            sample.decode("latin-1")
            return True
        except UnicodeDecodeError:
            return False


def _tokenize(text: str) -> List[str]:
    """Lowercase word tokens, stopwords removed, for keyword scoring."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9_'-]{1,}", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def _top_keywords(text: str, limit: int = 8) -> List[str]:
    """Most frequent content tokens, most frequent first."""
    from collections import Counter
    tokens = _tokenize(text)
    if not tokens:
        return []
    return [w for w, _ in Counter(tokens).most_common(limit)]


# ---------------------------------------------------------------------------
# per-kind profiles
# ---------------------------------------------------------------------------

#: bytes between 'stream' and 'endstream' (raw or FlateDecode).
_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)


def _pdf_text(data: bytes) -> str:
    """Extracts text from PDF content streams: '(...)' operators, or the raw
    decompressed stream text when no parenthesized strings exist."""
    segments: List[bytes] = []
    stream_texts: List[bytes] = []
    for raw in _STREAM_RE.findall(data):
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass  # already uncompressed
        stream_texts.append(raw)
        segments.extend(re.findall(rb"\(((?:[^()\\]|\\.)*)\)", raw))
    if not segments:
        # Fallback: full-document (string) scan, then raw stream text.
        segments = re.findall(rb"\(((?:[^()\\]|\\.)*)\)", data)
    if segments:
        text = b" ".join(segments)
        text = text.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
    else:
        text = b" ".join(stream_texts)
    return text.decode("latin-1", errors="ignore")


def _pdf_profile(file_path: Path, _data: bytes) -> ContentProfile:
    try:
        data = file_path.read_bytes()  # streams can live past our 8KB head
    except OSError:
        return ContentProfile(kind="pdf")
    text = _pdf_text(data)
    return ContentProfile(
        kind="pdf",
        text_sample=text.strip(),
        keywords=_top_keywords(text),
        metadata={"pages": None},
    )


def _png_profile(data: bytes) -> ContentProfile:
    """Reads IHDR dimensions and tEXt metadata from a PNG byte stream."""
    profile = ContentProfile(kind="image")
    text_parts: List[str] = []
    pos = 8  # skip signature
    try:
        while pos + 8 <= len(data):
            (length,) = struct.unpack(">I", data[pos:pos + 4])
            chunk_type = data[pos + 4:pos + 8]
            chunk_data = data[pos + 8:pos + 8 + length]
            if chunk_type == b"IHDR" and length >= 8:
                profile.dimensions = struct.unpack(">II", chunk_data[:8])
            elif chunk_type == b"tEXt":
                key, _, value = chunk_data.partition(b"\x00")
                text_parts.append(f"{key.decode('latin-1', 'ignore')}: {value.decode('latin-1', 'ignore')}")
            elif chunk_type == b"IEND":
                break
            pos += 12 + length
    except (struct.error, IndexError):
        pass
    if text_parts:
        profile.metadata["text"] = " ".join(text_parts)
    return profile


def _jpeg_profile(data: bytes) -> ContentProfile:
    """Minimal JPEG parse: APP1 Exif presence + SOF0..SOF3 dimensions."""
    profile = ContentProfile(kind="image")
    profile.metadata["has_exif"] = b"Exif\x00\x00" in data
    pos = 2
    try:
        while pos + 4 <= len(data):
            if data[pos] != 0xFF:
                break
            marker = data[pos + 1]
            (seg_len,) = struct.unpack(">H", data[pos + 2:pos + 4])
            if marker in (0xC0, 0xC1, 0xC2, 0xC3) and seg_len >= 7:
                height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
                profile.dimensions = (width, height)
                break
            pos += 2 + seg_len
    except (struct.error, IndexError):
        pass
    return profile


def _archive_profile(file_path: Path, kind: str) -> ContentProfile:
    members: List[str] = []
    try:
        if kind == "zip":
            import zipfile
            with zipfile.ZipFile(file_path) as zf:
                members = zf.namelist()[:50]
        else:
            with tarfile.open(file_path) as tf:
                members = [m.name for m in tf.getmembers()[:50]]
    except Exception:
        pass
    return ContentProfile(kind="archive", metadata={"members": members})


def _code_profile(file_path: Path) -> ContentProfile:
    text = _read_head(file_path, 65536).decode("utf-8", errors="ignore")
    metadata: Dict[str, Any] = {}
    first_line = text.splitlines()[0] if text.splitlines() else ""
    shebang = ""
    language = ""
    if first_line.startswith("#!"):
        shebang = first_line[2:].strip()
        for key, lang in _SHEBANG_LANGS.items():
            if key in shebang:
                language = lang
                break
    if not language:
        language = file_path.suffix.lstrip(".") or ""
    metadata["shebang"] = shebang
    metadata["language"] = language
    return ContentProfile(
        kind="code",
        text_sample=text.strip(),
        keywords=_top_keywords(text),
        metadata=metadata,
    )


def _text_profile(file_path: Path) -> ContentProfile:
    text = _read_head(file_path, 65536).decode("utf-8", errors="ignore")
    return ContentProfile(
        kind="text",
        text_sample=text.strip(),
        keywords=_top_keywords(text),
    )


def _looks_like_code(file_path: Path) -> bool:
    """Heuristic: dense code keywords beat dense prose words in the first chunk."""
    text = _read_head(file_path, 4096).decode("utf-8", errors="ignore")
    if not text.strip():
        return False
    code_kw = sum(1 for w in _tokenize(text) if w in {
        "def", "class", "import", "return", "const", "let", "function",
        "if", "else", "for", "while", "print", "self", "true", "false", "null",
    })
    prose_kw = sum(1 for w in _tokenize(text) if w in {
        "the", "and", "was", "with", "from", "they", "were", "chapter",
    })
    return code_kw > prose_kw