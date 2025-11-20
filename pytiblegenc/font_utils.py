#!/usr/bin/env python3
# font_utils.py
"""
Font-related utilities using fontTools, with optional repair via FontForge CLI.

Main public pieces:

    - get_glyph_hashes_from_bytes(font_bytes: bytes)
        -> (postscript_name: str, glyph_records: set[(glyph_name, glyph_hash, codepoints_tuple)])

    - build_font_hash_index_from_csv(csv_path: Union[str, Path])
        -> Dict[font_postscript_name, Set[glyph_hash]]

    - identify_font(font_bytes: bytes, font_hash_index: Dict[str, Set[str]])
        -> Set[str]  # set of candidate font PostScript names

where a "match" is defined as:
    1. If the font's PostScript name directly exists in the index,
       return a set of length 1 containing that name.

    2. Otherwise, return all PostScript names whose glyph-hash sets
       are *supersets* of the glyph hashes in the given font bytes
       (typical case for subsetted PDF fonts).
"""

from __future__ import annotations

import csv
import io
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Iterable, Union
from pdfminer.pdfpage import PDFPage
from pdfminer.pdftypes import resolve1, stream_value
from pdfminer.psparser import PSLiteral

from fontTools.ttLib import TTFont, TTLibError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# Each glyph record: (glyph_name, glyph_hash, codepoints)
GlyphRecord = Tuple[str, str, Tuple[int, ...]]

@dataclass
class GlyphDetail:
    """Detailed information about a glyph in a font."""
    glyph_name: str
    glyph_hash: str
    codepoint: Optional[int]
    
    def __hash__(self):
        return hash((self.glyph_name, self.glyph_hash, self.codepoint))
    
    def __eq__(self, other):
        if not isinstance(other, GlyphDetail):
            return False
        return (self.glyph_name == other.glyph_name and 
                self.glyph_hash == other.glyph_hash and 
                self.codepoint == other.codepoint)


# ---------------------------------------------------------------------------
# Low-level fontTools helpers
# ---------------------------------------------------------------------------

def _compute_glyph_hash(ttfont: TTFont, glyph_name: str) -> str:
    """
    Compute a normalized hash of a glyph outline using fontTools.

    Normalization:
      - scale coordinates by unitsPerEm
      - translate so min x,y is at (0,0)
      - encode with fixed decimals and on/off-curve flags
      - separate contours with '|'

    Returns a hex SHA-256 string.

    Raises if the font has no 'glyf' table or the glyph can't be processed.
    """
    if "glyf" not in ttfont:
        raise TTLibError("Font has no 'glyf' table (likely CFF).")

    glyf = ttfont["glyf"]
    glyph = glyf[glyph_name]
    coords, end_pts, flags = glyph.getCoordinates(glyf)
    upem = ttfont["head"].unitsPerEm

    if not coords:
        # Empty glyph: constant hash; all empty glyphs match
        return sha256(f"EMPTY:{glyph_name}".encode("utf-8")).hexdigest()

    # Normalize scale
    norm_coords = [(x / upem, y / upem) for (x, y) in coords]

    # Normalize translation
    min_x = min(p[0] for p in norm_coords)
    min_y = min(p[1] for p in norm_coords)
    norm_coords = [(x - min_x, y - min_y) for (x, y) in norm_coords]

    contour_ends = set(end_pts)
    parts: List[str] = []
    for i, (x, y) in enumerate(norm_coords):
        on_curve = flags[i] & 1  # 1 = on-curve, 0 = off-curve
        parts.append(f"{x:.6f},{y:.6f},{on_curve}")
        if i in contour_ends:
            parts.append("|")  # contour separator

    blob = ";".join(parts)
    return sha256(blob.encode("utf-8")).hexdigest()


def _get_postscript_name(ttfont: TTFont, fallback: str) -> str:
    """
    Try to get PostScript name (nameID 6). If unavailable, return fallback.
    """
    try:
        name_table = ttfont["name"]
    except KeyError:
        return fallback

    for record in name_table.names:
        if record.nameID == 6:
            try:
                return record.toUnicode()
            except Exception:
                try:
                    return record.string.decode(record.getEncoding(), errors="replace")
                except Exception:
                    pass
    return fallback


def _extract_glyph_records(
    ttfont: TTFont,
    fallback_font_name: str = "Unknown",
) -> Tuple[str, Set[GlyphRecord]]:
    """
    Extract glyph records from a TTFont:

        (postscript_name, set_of_records)

    where each record is:
        (glyph_name, glyph_hash, codepoints_tuple)

    - codepoints are taken from the best cmap.
    """
    ps_name = _get_postscript_name(ttfont, fallback=fallback_font_name)

    # Build glyph -> list[codepoint] mapping from best cmap
    glyph_to_cps: Dict[str, List[int]] = {}
    try:
        cmap = ttfont["cmap"].getBestCmap() or {}
    except Exception:
        cmap = {}

    for cp, gname in cmap.items():
        glyph_to_cps.setdefault(gname, []).append(cp)

    if "glyf" not in ttfont:
        raise TTLibError("Font has no 'glyf' table (likely CFF).")

    glyf = ttfont["glyf"]
    records: Set[GlyphRecord] = set()

    for glyph_name in glyf.keys():
        glyph_hash = _compute_glyph_hash(ttfont, glyph_name)
        cps = glyph_to_cps.get(glyph_name, [])
        cps_tuple = tuple(sorted(cps)) if cps else tuple()
        records.add((glyph_name, glyph_hash, cps_tuple))

    return ps_name, records


# ---------------------------------------------------------------------------
# FontForge-based repair (CLI, not Python module)
# ---------------------------------------------------------------------------

def fix_font_with_fontforge(font_bytes: bytes) -> Optional[bytes]:
    """
    Try to "repair" a font using the FontForge CLI.

    Steps:
      - Check if 'fontforge' executable is available.
      - Write the original font bytes to a temp input file.
      - Create a small FontForge script that does:
            Open($1)
            Generate($2)
            Close()
            Quit()
      - Call: fontforge -lang=ff -script script.pe input.ttf output.ttf
      - If success and output.ttf exists, return its bytes.
      - Otherwise return None.

    This function never raises; returns None on any failure.
    """
    if shutil.which("fontforge") is None:
        return None

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            in_path = tmp / "input_font.ttf"
            out_path = tmp / "output_font.ttf"
            script_path = tmp / "repair.pe"

            # Write input font
            in_path.write_bytes(font_bytes)

            # Write FontForge script
            script_content = (
                "Open($1)\n"
                "Generate($2)\n"
                "Close()\n"
                "Quit()\n"
            )
            script_path.write_text(script_content, encoding="utf-8")

            # Run FontForge
            cmd = [
                "fontforge",
                "-lang=ff",
                "-script",
                str(script_path),
                str(in_path),
                str(out_path),
            ]
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if proc.returncode != 0:
                return None

            if not out_path.exists():
                return None

            return out_path.read_bytes()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public: glyph hashes from bytes
# ---------------------------------------------------------------------------

def get_glyph_hashes_from_bytes(font_bytes: bytes) -> Tuple[str, Set[GlyphRecord]]:
    """
    Main public function.

    Takes font bytes and returns:
        (postscript_name, glyph_records)

    where glyph_records is a set of tuples:
        (glyph_name: str, glyph_hash: str, codepoints: Tuple[int, ...])

    Workflow:
      - Try parsing with fontTools TTFont.
      - If that fails for any reason:
          * Try to repair with FontForge CLI (if available).
          * If repair succeeds, parse repaired bytes with TTFont.
      - If both fail, re-raise the original fontTools exception.

    This is the function you should use:
      - for building the glyph DB from font files
      - later for embedded fonts extracted from PDFs
    """
    # First attempt: original bytes
    initial_error: Optional[Exception] = None
    try:
        ttfont = TTFont(io.BytesIO(font_bytes))
        return _extract_glyph_records(ttfont)
    except Exception as e:
        initial_error = e

    # Second attempt: try FontForge repair
    fixed_bytes = fix_font_with_fontforge(font_bytes)
    if not fixed_bytes:
        # No repair possible
        raise initial_error

    try:
        ttfont_fixed = TTFont(io.BytesIO(fixed_bytes))
        return _extract_glyph_records(ttfont_fixed)
    except Exception:
        # Even repaired font failed; give up with original error
        raise initial_error


# ---------------------------------------------------------------------------
# DB index helpers (for identification)
# ---------------------------------------------------------------------------

def build_font_hash_index_from_csv(csv_path: Union[str, Path]) -> Dict[str, Set[str]]:
    """
    Build an index from the glyph DB CSV:

        font_postscript_name -> set[glyph_hash]

    Assumes CSV columns created by create_db.py:
        glyph_hash,font_postscript_name,glyph_name,codepoint
    """
    csv_path = Path(csv_path)
    index: Dict[str, Set[str]] = {}

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            glyph_hash = row["glyph_hash"]
            ps_name = row["font_postscript_name"]

            if not glyph_hash or not ps_name:
                continue

            index.setdefault(ps_name, set()).add(glyph_hash)

    return index


def build_detailed_glyph_index_from_csv(csv_path: Union[str, Path]) -> Dict[str, Dict[str, Set[GlyphDetail]]]:
    """
    Build a detailed index from the glyph DB CSV:

        font_postscript_name -> glyph_hash -> set[GlyphDetail]

    This allows us to get detailed information (glyph names, codepoints) for each 
    glyph hash in each font, useful for debugging ambiguous font matches.

    Assumes CSV columns:
        glyph_hash,font_postscript_name,glyph_name,codepoint
    """
    csv_path = Path(csv_path)
    index: Dict[str, Dict[str, Set[GlyphDetail]]] = {}

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            glyph_hash = row["glyph_hash"]
            ps_name = row["font_postscript_name"]
            glyph_name = row["glyph_name"]
            codepoint_str = row.get("codepoint", "")

            if not glyph_hash or not ps_name:
                continue

            # Parse codepoint
            codepoint = None
            if codepoint_str and codepoint_str != "None":
                try:
                    codepoint = int(codepoint_str)
                except ValueError:
                    pass

            detail = GlyphDetail(
                glyph_name=glyph_name,
                glyph_hash=glyph_hash,
                codepoint=codepoint
            )

            if ps_name not in index:
                index[ps_name] = {}
            if glyph_hash not in index[ps_name]:
                index[ps_name][glyph_hash] = set()
            index[ps_name][glyph_hash].add(detail)

    return index


def identify_font(font_bytes: bytes, font_hash_index: Dict[str, Set[str]]) -> Set[str]:
    """
    Identify candidate fonts for the given font bytes.

    Returns:
        set of PostScript names (strings).

    Matching logic:
      1. Compute (ps_name, glyph_records) from font_bytes via get_glyph_hashes_from_bytes().
      2. If ps_name is present as a key in font_hash_index:
            -> return {ps_name} only.
         (Exact PS-name match – treat as decisive.)
      3. Otherwise:
            - Let H = set of glyph_hashes in the given font.
            - Return all font_postscript_name F such that:
                  H ⊆ font_hash_index[F]
              i.e. fonts whose glyph set is a superset of the subset font.

    Typical usage:
        index = build_font_hash_index_from_csv("glyph_db.csv")
        candidates = identify_font(embedded_font_bytes, index)
    """
    ps_name, records = get_glyph_hashes_from_bytes(font_bytes)

    # 1. Exact PostScript name match
    if ps_name in font_hash_index:
        return {ps_name}

    # 2. Superset match on glyph hashes
    glyph_hashes_in_font = {rec[1] for rec in records}  # rec[1] is glyph_hash

    if not glyph_hashes_in_font:
        # No glyphs? We can't really say; return empty set.
        return set()

    candidates: Set[str] = set()
    for candidate_ps, candidate_hashes in font_hash_index.items():
        # Subset test: all glyph hashes present in candidate font
        if glyph_hashes_in_font.issubset(candidate_hashes):
            candidates.add(candidate_ps)

    return candidates


def identify_pdf_fonts_from_db(
    doc, 
    font_hash_index: Dict[str, Set[str]], 
    detailed_index: Optional[Dict[str, Dict[str, Set[GlyphDetail]]]] = None,
    log_ambiguous: bool = False
) -> Dict[str, Set[str]]:
    """
    Identify all fonts in a PDF document against a glyph-hash database.

    Args:
        doc: pdfminer.pdfdocument.PDFDocument
        font_hash_index: Dict[postscript_name, Set[glyph_hash]]
            Usually built with build_font_hash_index_from_csv("glyph_db.csv").
        detailed_index: Optional detailed index from build_detailed_glyph_index_from_csv()
            If provided and log_ambiguous is True, used to log detailed information
            about ambiguous font matches.
        log_ambiguous: If True, log warnings when fonts have multiple candidates.

    Returns:
        Dict[str, Set[str]]

        Keys are "names of fonts in the PDF":
          - resource font names from page /Resources /Font (e.g. '/F1')
          - AND their BaseFont names (without leading '/') when available
            (e.g. 'ANIELG+Dedris-a')

        Values are sets of PostScript names from your DB that match:
          - FAST PATH: if BaseFont looks like 'ABCDEE+Dedris-a' and
            'Dedris-a' exists in font_hash_index, we use {'Dedris-a'}
            directly (no glyph hashing).
          - Otherwise: fonts whose glyph hash set is a superset of the
            glyph hashes in the subset font (via identify_font()).
    """
    normalized: Dict[str, Set[str]] = {}

    # To avoid processing the same embedded font multiple times across pages
    seen_font_stream_ids: Set[int] = set()

    for page in PDFPage.create_pages(doc):
        resources = resolve1(page.resources)
        if not resources:
            continue

        font_dict = resources.get("Font")
        if not font_dict:
            continue

        font_dict = resolve1(font_dict)

        for res_name, font_ref in font_dict.items():
            # res_name is a PDF name object like '/F1'
            res_name_str = str(res_name)

            font_obj = resolve1(font_ref)
            if not isinstance(font_obj, dict):
                continue

            basefont = font_obj.get("BaseFont")
            # Handle PSLiteral objects properly - extract the .name attribute
            if basefont is not None:
                if isinstance(basefont, PSLiteral):
                    basefont_name = basefont.name
                else:
                    basefont_name = str(basefont)
                    if basefont_name.startswith("/"):
                        basefont_name = basefont_name[1:]
            else:
                basefont_name = None

            # ------------------------------------------------------------------
            # FAST PATH: try to infer original font from subset BaseFont name.
            # Example: 'ANIELG+Dedris-a' -> 'Dedris-a'
            # If 'Dedris-a' is a key in font_hash_index, use that and skip
            # embedded font bytes / glyph hashing for this font.
            # ------------------------------------------------------------------
            fast_candidates: Optional[Set[str]] = None
            if basefont_name and "+" in basefont_name:
                suffix = basefont_name.split("+", 1)[1]
                if suffix in font_hash_index:
                    fast_candidates = {suffix}

            if fast_candidates:
                # Map by resource name (e.g. '/F1')
                normalized.setdefault(res_name_str, set()).update(fast_candidates)
                # And by BaseFont name (e.g. 'ANIELG+Dedris-a')
                normalized.setdefault(basefont_name, set()).update(fast_candidates)
                # Done with this font; no need to look at embedded font program
                continue

            # ------------------------------------------------------------------
            # SLOW PATH: use embedded font bytes + identify_font()
            # ------------------------------------------------------------------
            # For Type0 (CIDFonts), the FontDescriptor is in DescendantFonts
            font_desc = resolve1(font_obj.get("FontDescriptor"))
            
            # If no direct FontDescriptor, check DescendantFonts (Type0/CIDFont)
            if not font_desc or not isinstance(font_desc, dict):
                descendant_fonts = resolve1(font_obj.get("DescendantFonts"))
                if descendant_fonts:
                    # DescendantFonts is typically an array with one element
                    for df in descendant_fonts:
                        df_obj = resolve1(df)
                        if isinstance(df_obj, dict):
                            font_desc = resolve1(df_obj.get("FontDescriptor"))
                            if font_desc and isinstance(font_desc, dict):
                                break
            
            if not isinstance(font_desc, dict):
                continue

            font_bytes = None
            font_stream_obj = None
            for key in ("FontFile2", "FontFile", "FontFile3"):
                ff = font_desc.get(key)
                if ff is None:
                    continue
                try:
                    font_stream_obj = stream_value(ff)
                except Exception:
                    font_stream_obj = None
                if font_stream_obj is not None:
                    try:
                        font_bytes = font_stream_obj.get_data()
                    except Exception:
                        font_bytes = None
                if font_bytes:
                    break

            if not font_bytes or font_stream_obj is None:
                continue

            # Deduplicate by id() of the stream object (cheap but effective)
            sid = id(font_stream_obj)
            if sid in seen_font_stream_ids:
                continue
            seen_font_stream_ids.add(sid)

            # Identify this font against the DB (glyph-hash superset logic)
            try:
                candidates = identify_font(font_bytes, font_hash_index)
            except Exception:
                continue

            if not candidates:
                continue

            # Log ambiguous matches if requested
            if log_ambiguous and len(candidates) > 1:
                _log_ambiguous_font_match(
                    res_name_str, 
                    basefont_name,
                    candidates, 
                    font_bytes, 
                    font_hash_index,
                    detailed_index
                )

            # Map by resource name (e.g. '/F1')
            normalized.setdefault(res_name_str, set()).update(candidates)

            # Also map by BaseFont name (e.g. 'ANIELG+Dedris-a') if present
            if basefont_name:
                normalized.setdefault(basefont_name, set()).update(candidates)

    # Log any ambiguities that arose from aggregating multiple font streams under the same resource name
    if log_ambiguous and detailed_index:
        for font_name, candidates in normalized.items():
            if len(candidates) > 1:
                _log_aggregated_ambiguity(font_name, candidates, detailed_index)

    return normalized


def _log_aggregated_ambiguity(
    font_name: str,
    candidates: Set[str],
    detailed_index: Dict[str, Dict[str, Set[GlyphDetail]]]
) -> None:
    """
    Log information about a font name that has accumulated multiple candidate fonts.
    
    This happens when a PDF resource name (like 'F9') points to different BaseFont names
    on different pages, and those BaseFonts identify to different font families.
    """
    candidates_str = ", ".join(sorted(candidates))
    logger.warning(
        f"Font {font_name} could have multiple correspondences: {candidates_str}"
    )
    
    # Show some sample characters from each candidate font
    for candidate in sorted(candidates):
        if candidate not in detailed_index:
            continue
        
        sample_chars = []
        candidate_glyph_details = detailed_index[candidate]
        
        # Collect some sample glyphs (limit to first 10)
        for glyph_hash, details_set in list(candidate_glyph_details.items())[:10]:
            for detail in details_set:
                if detail.codepoint is not None:
                    char_info = f"{detail.glyph_name} (U+{detail.codepoint:04X}, chr={chr(detail.codepoint)!r})"
                else:
                    char_info = f"{detail.glyph_name} (no codepoint)"
                sample_chars.append(char_info)
                break  # Only take one detail per glyph hash
            if len(sample_chars) >= 10:
                break
        
        if sample_chars:
            chars_summary = ", ".join(sample_chars)
            if len(candidate_glyph_details) > 10:
                chars_summary += f", ... ({len(candidate_glyph_details) - 10} more glyphs)"
            
            logger.warning(
                f"  - {candidate}: sample characters: {chars_summary}"
            )


def _log_ambiguous_font_match(
    res_name: str,
    basefont_name: Optional[str],
    candidates: Set[str],
    font_bytes: bytes,
    font_hash_index: Dict[str, Set[str]],
    detailed_index: Optional[Dict[str, Dict[str, Set[GlyphDetail]]]]
) -> None:
    """
    Log detailed information about an ambiguous font match.
    
    This is called when a single embedded font stream matches multiple candidate fonts.
    
    Args:
        res_name: Resource name like '/F1'
        basefont_name: BaseFont name if available
        candidates: Set of candidate font names
        font_bytes: The embedded font bytes
        font_hash_index: The hash index for quick lookups
        detailed_index: Optional detailed index with glyph information
    """
    try:
        ps_name, records = get_glyph_hashes_from_bytes(font_bytes)
        glyph_hashes_in_font = {rec[1] for rec in records}  # rec[1] is glyph_hash
        
        font_label = basefont_name if basefont_name else res_name
        candidates_str = ", ".join(sorted(candidates))
        
        logger.warning(
            f"Font {font_label} (embedded stream) could have multiple correspondences: {candidates_str}"
        )
        
        if detailed_index:
            # Build a map of characters that exist in the embedded font
            embedded_glyphs = {rec[0]: rec for rec in records}  # glyph_name -> full record
            
            # For each candidate font, show which characters match
            for candidate in sorted(candidates):
                if candidate not in detailed_index:
                    continue
                
                matching_chars = []
                candidate_glyph_details = detailed_index[candidate]
                
                # Find glyphs that are in both the embedded font and the candidate
                for glyph_hash in glyph_hashes_in_font:
                    if glyph_hash in candidate_glyph_details:
                        for detail in candidate_glyph_details[glyph_hash]:
                            # Format: glyph_name (U+XXXX)
                            if detail.codepoint is not None:
                                char_info = f"{detail.glyph_name} (U+{detail.codepoint:04X}, chr={chr(detail.codepoint)!r})"
                            else:
                                char_info = f"{detail.glyph_name} (no codepoint)"
                            matching_chars.append(char_info)
                
                if matching_chars:
                    # Limit the output to first 20 characters to avoid excessive logging
                    chars_to_show = matching_chars[:20]
                    if len(matching_chars) > 20:
                        chars_summary = ", ".join(chars_to_show) + f", ... ({len(matching_chars) - 20} more)"
                    else:
                        chars_summary = ", ".join(chars_to_show)
                    
                    logger.warning(
                        f"  - {candidate}: matching characters: {chars_summary}"
                    )
    except Exception as e:
        logger.debug(f"Error logging ambiguous font match: {e}")