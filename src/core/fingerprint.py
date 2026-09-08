"""
Fingerprint helpers for files: a perceptual dhash for PNGs, a simhash-style
hash for text, and plain SHA-256 fallbacks. Pure and deterministic, standard
library only — no DB or config access (the caller handles caching).
"""
import hashlib
import re
import struct
import zlib
from pathlib import Path
from typing import List, Optional, Tuple


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_IHDR_STRUCT = struct.Struct(">IIBBBBB")

_CHUNK_IHDR = b"IHDR"
_CHUNK_PLTE = b"PLTE"
_CHUNK_IDAT = b"IDAT"
_CHUNK_IEND = b"IEND"

_TEXT_SUFFIXES = frozenset(".txt .md .csv .py .json .xml .html .css .js .ts .log".split())
_IMAGE_HASH_ONLY = frozenset((".jpg", ".jpeg", ".gif", ".bmp"))

_TEXT_HEAD_LIMIT = 64 * 1024
_SHA1_DIGEST_BYTES = 20


class _PNGError(Exception):
    """Internal error for invalid or unsupported PNG data."""


def png_dhash(file_path: Path, size: int = 8) -> Optional[int]:
    """Perceptual hash (dhash) of a PNG image, or None on any parse failure.

    The 64-bit result (size=8) encodes 63 downscaled left-to-right brightness
    comparisons plus one overall-brightness bit, so solid-colour images still
    hash distinctly. Supports bit depth 8 for colour types 0/2/6 and 1/2/4/8
    for indexed colour (type 3, mapped through PLTE).
    """
    try:
        decoded = _decode_png(file_path)
    except (OSError, _PNGError, zlib.error, struct.error, IndexError):
        return None
    if decoded is None or size <= 0:
        return None
    gray, width, height = decoded
    return _dhash(gray, width, height, size)


def text_fingerprint(text: str, bits: int = 64) -> int:
    """Simhash-style fingerprint over lowercased alphanumeric word tokens."""
    if bits <= 0:
        return 0
    tokens = [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]
    bytes_needed = min((bits + 7) // 8, _SHA1_DIGEST_BYTES)
    vector = [0] * bits
    for token in tokens:
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        value = int.from_bytes(digest[:bytes_needed], "big")
        for bit in range(bits):
            if value & (1 << bit):
                vector[bit] += 1
            else:
                vector[bit] -= 1
    result = 0
    for bit in range(bits):
        if vector[bit] >= 0:
            result |= 1 << bit
    return result


def sha256_fingerprint(file_path: Path) -> Optional[str]:
    """Hex SHA-256 of the file's bytes; None on any read error."""
    hasher = hashlib.sha256()
    try:
        with file_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                hasher.update(chunk)
    except OSError:
        return None
    return hasher.hexdigest()


def hamming_distance(a: int, b: int) -> int:
    """Number of differing bits between two integers (popcount of a xor b)."""
    return bin(a ^ b).count("1")


def fingerprint_file(file_path: Path) -> dict:
    """Return a kind-tagged fingerprint dict for a file.

    - ".png"               -> {"kind": "image", "value": png_dhash or sha256 fallback}
    - jpg/jpeg/gif/bmp     -> {"kind": "image", "value": sha256 hex} (no image lib)
    - text-like suffixes   -> {"kind": "text", "value": simhash int of first 64 KB}
    - everything else      -> {"kind": "binary", "value": sha256 hex}
    """
    suffix = file_path.suffix.lower()
    if suffix == ".png":
        value = png_dhash(file_path)
        if value is None:
            value = sha256_fingerprint(file_path)
        return {"kind": "image", "value": value}
    if suffix in _IMAGE_HASH_ONLY:
        return {"kind": "image", "value": sha256_fingerprint(file_path)}
    if suffix in _TEXT_SUFFIXES:
        return {"kind": "text", "value": text_fingerprint(_read_text_head(file_path))}
    return {"kind": "binary", "value": sha256_fingerprint(file_path)}


# ---------------------------------------------------------------------------
# PNG decoding (zlib + struct only)
# ---------------------------------------------------------------------------

def _decode_png(file_path: Path):
    if not file_path.is_file():
        return None
    return _decode_png_data(file_path.read_bytes())


def _decode_png_data(data: bytes):
    if not data.startswith(_PNG_SIGNATURE):
        raise _PNGError("missing PNG signature")
    pos = len(_PNG_SIGNATURE)
    width = height = bit_depth = color_type = 0
    palette: List[Tuple[int, int, int]] = []
    idat = bytearray()

    while pos < len(data):
        if pos + 8 > len(data):
            raise _PNGError("truncated chunk header")
        (chunk_len,) = struct.unpack(">I", data[pos:pos + 4])
        chunk_type = data[pos + 4:pos + 8]
        chunk_end = pos + 8 + chunk_len
        if chunk_end + 4 > len(data):
            raise _PNGError("truncated chunk data")
        payload = data[pos + 8:chunk_end]

        if chunk_type == _CHUNK_IHDR:
            if len(payload) != _IHDR_STRUCT.size:
                raise _PNGError("bad IHDR length")
            w, h, bit_depth, color_type, comp, filt, interlace = _IHDR_STRUCT.unpack(payload)
            width, height = w, h
            if comp != 0 or filt != 0 or interlace != 0:
                raise _PNGError("unsupported compression/filter/interlace")
        elif chunk_type == _CHUNK_PLTE:
            palette = _decode_palette(payload)
        elif chunk_type == _CHUNK_IDAT:
            idat += payload
        elif chunk_type == _CHUNK_IEND:
            break
        pos = chunk_end + 4
    else:
        raise _PNGError("missing IEND")

    if width <= 0 or height <= 0:
        raise _PNGError("bad dimensions")

    row_bytes, bpp = _pixel_format(color_type, bit_depth, width)
    raw = zlib.decompress(bytes(idat))
    if len(raw) != (row_bytes + 1) * height:
        raise _PNGError("IDAT size mismatch")
    unfiltered = _unfilter(raw, height, row_bytes, bpp)
    gray = _to_gray(unfiltered, width, height, color_type, bit_depth, palette)
    return gray, width, height


def _decode_palette(payload: bytes) -> List[Tuple[int, int, int]]:
    if len(payload) % 3 != 0:
        raise _PNGError("bad PLTE length")
    return [(payload[i], payload[i + 1], payload[i + 2]) for i in range(0, len(payload), 3)]


def _pixel_format(color_type: int, bit_depth: int, width: int) -> Tuple[int, int]:
    """Return (bytes_per_scanline, bytes_per_pixel_for_filtering)."""
    if color_type == 0:  # grayscale
        if bit_depth != 8:
            raise _PNGError("unsupported grayscale bit depth")
        return width, 1
    if color_type == 2:  # truecolour RGB
        if bit_depth != 8:
            raise _PNGError("unsupported RGB bit depth")
        return width * 3, 3
    if color_type == 6:  # truecolour with alpha
        if bit_depth != 8:
            raise _PNGError("unsupported RGBA bit depth")
        return width * 4, 4
    if color_type == 3:  # indexed
        if bit_depth not in (1, 2, 4, 8):
            raise _PNGError("unsupported indexed bit depth")
        pixels_per_byte = 8 // bit_depth
        return (width + pixels_per_byte - 1) // pixels_per_byte, 1
    raise _PNGError("unsupported colour type")


def _unfilter(raw: bytes, height: int, row_bytes: int, bpp: int) -> bytes:
    out = bytearray(height * row_bytes)
    stride = row_bytes + 1
    prev = bytearray(row_bytes)
    for y in range(height):
        start = y * stride
        filt = raw[start]
        src = raw[start + 1:start + 1 + row_bytes]
        row_start = y * row_bytes
        if filt == 0:
            out[row_start:row_start + row_bytes] = src
        elif filt == 1:
            _unfilter_sub(out, src, row_start, bpp)
        elif filt == 2:
            _unfilter_up(out, src, row_start, prev)
        elif filt == 3:
            _unfilter_average(out, src, row_start, prev, bpp)
        elif filt == 4:
            _unfilter_paeth(out, src, row_start, prev, bpp)
        else:
            raise _PNGError("unknown filter type")
        prev[:] = out[row_start:row_start + row_bytes]
    return bytes(out)


def _unfilter_sub(out: bytearray, src: bytes, row_start: int, bpp: int) -> None:
    for i in range(len(src)):
        left = out[row_start + i - bpp] if i >= bpp else 0
        out[row_start + i] = (src[i] + left) & 0xFF


def _unfilter_up(out: bytearray, src: bytes, row_start: int, prev: bytearray) -> None:
    for i in range(len(src)):
        out[row_start + i] = (src[i] + prev[i]) & 0xFF


def _unfilter_average(out: bytearray, src: bytes, row_start: int, prev: bytearray,
                      bpp: int) -> None:
    for i in range(len(src)):
        left = out[row_start + i - bpp] if i >= bpp else 0
        out[row_start + i] = (src[i] + ((left + prev[i]) // 2)) & 0xFF


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_paeth(out: bytearray, src: bytes, row_start: int, prev: bytearray, bpp: int) -> None:
    for i in range(len(src)):
        left = out[row_start + i - bpp] if i >= bpp else 0
        upper = prev[i]
        upper_left = prev[i - bpp] if i >= bpp else 0
        out[row_start + i] = (src[i] + _paeth(left, upper, upper_left)) & 0xFF


def _to_gray(raw: bytes, width: int, height: int, color_type: int, bit_depth: int,
             palette: List[Tuple[int, int, int]]) -> List[int]:
    gray = [0] * (width * height)
    if color_type == 0:
        for i, value in enumerate(raw):
            gray[i] = value
    elif color_type in (2, 6):
        channels = 3 if color_type == 2 else 4
        for y in range(height):
            base = y * width * channels
            row_start = y * width
            for x in range(width):
                i = base + x * channels
                gray[row_start + x] = _luma(raw[i], raw[i + 1], raw[i + 2])
    else:
        if not palette or len(palette) < 1 << bit_depth:
            raise _PNGError("insufficient palette for indexed image")
        pixels_per_byte = 8 // bit_depth
        mask = (1 << bit_depth) - 1
        row_bytes = (width + pixels_per_byte - 1) // pixels_per_byte
        for y in range(height):
            base = y * row_bytes
            row_start = y * width
            for x in range(width):
                byte = raw[base + x // pixels_per_byte]
                shift = 8 - bit_depth * ((x % pixels_per_byte) + 1)
                r, g, b = palette[(byte >> shift) & mask]
                gray[row_start + x] = _luma(r, g, b)
    return gray


def _luma(r: int, g: int, b: int) -> int:
    """BT.601 luma in 0..255 using integer maths (platform-deterministic)."""
    return (299 * r + 587 * g + 114 * b) // 1000


def _dhash(gray: List[int], width: int, height: int, size: int) -> int:
    """Region-average downscale to (size+1) x size, then dhash bits.

    63 of the 64 bits (size=8) are left-to-right gradient comparisons; the top
    bit is the overall mean brightness, so uniform images hash distinctly.
    """
    total_bits = size * size
    mean = 0
    count = 0
    for ty in range(size):
        y0 = ty * height // size
        y1 = (ty + 1) * height // size
        for tx in range(size + 1):
            x0 = tx * width // (size + 1)
            x1 = (tx + 1) * width // (size + 1)
            total = 0
            for y in range(y0, y1):
                row_start = y * width
                for x in range(x0, x1):
                    total += gray[row_start + x]
                    count += 1
            mean += total
    mean //= max(1, count)

    result = 0
    for ty in range(size):
        avgs = []
        for tx in range(size + 1):
            x0 = tx * width // (size + 1)
            x1 = (tx + 1) * width // (size + 1)
            y0 = ty * height // size
            y1 = (ty + 1) * height // size
            total = 0
            cells = 0
            for y in range(y0, y1):
                row_start = y * width
                for x in range(x0, x1):
                    total += gray[row_start + x]
                    cells += 1
            avgs.append(total // cells if cells else 0)
        for pair in range(size):
            bit_pos = ty * size + pair
            if bit_pos < total_bits - 1 and avgs[pair] > avgs[pair + 1]:
                result |= 1 << bit_pos
    if mean >= 128:
        result |= 1 << (total_bits - 1)
    return result


def _read_text_head(file_path: Path) -> str:
    try:
        with file_path.open("rb") as fh:
            data = fh.read(_TEXT_HEAD_LIMIT)
    except OSError:
        return ""
    return data.decode("utf-8", errors="ignore")