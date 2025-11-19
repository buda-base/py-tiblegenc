#!/usr/bin/env python3
"""
build_font_db.py

Recursively scan a folder for TTF fonts, compute glyph outline hashes,
and write a CSV database mapping:

    glyph_hash -> font_postscript_name, glyph_name, codepoint, unicode_hex

Usage:
    python build_font_db.py /path/to/fonts --output glyph_db.csv
"""

import argparse
import csv
import sys
from pathlib import Path
from hashlib import sha256

from fontTools.ttLib import TTFont
from fontTools.ttLib.ttFont import TTLibError


def compute_glyph_hash(ttfont: TTFont, glyph_name: str) -> str:
    """
    Compute a normalized hash of the glyph outlines for a given glyph name.

    Normalization:
      - Scale by unitsPerEm so different EM sizes match.
      - Translate so min x,y is at 0,0.
      - Include on-curve/off-curve info and contour separators.

    Returns a hex SHA-256 hash string.
    """
    if "glyf" not in ttfont:
        # CFF / other outlines not handled in this basic version
        raise ValueError("Font has no 'glyf' table; CFF outlines not supported in this script.")

    glyf = ttfont["glyf"]
    glyph = glyf[glyph_name]
    # getCoordinates() also resolves composites
    coords, end_pts, flags = glyph.getCoordinates(glyf)
    upem = ttfont["head"].unitsPerEm

    if not coords:
        # Empty glyph: just hash its name as a fallback
        return sha256(f"EMPTY:{glyph_name}".encode("utf-8")).hexdigest()

    # Normalize scale
    norm_coords = [(x / upem, y / upem) for (x, y) in coords]

    # Normalize translation (shift so minimum is at 0,0)
    min_x = min(p[0] for p in norm_coords)
    min_y = min(p[1] for p in norm_coords)
    norm_coords = [(x - min_x, y - min_y) for (x, y) in norm_coords]

    contour_ends = set(end_pts)

    # Build a stable textual representation
    parts = []
    for i, (x, y) in enumerate(norm_coords):
        on_curve = flags[i] & 1  # 1 = on-curve, 0 = off-curve
        # fixed number of decimals to reduce noise
        parts.append(f"{x:.6f},{y:.6f},{on_curve}")
        if i in contour_ends:
            parts.append("|")  # contour separator

    blob = ";".join(parts)
    return sha256(blob.encode("utf-8")).hexdigest()


def get_postscript_name(ttfont: TTFont, fallback: str) -> str:
    """
    Try to get the PostScript name (nameID 6). If not present, use fallback.
    """
    try:
        name_table = ttfont["name"]
    except KeyError:
        return fallback

    for record in name_table.names:
        if record.nameID == 6:  # PostScript name
            try:
                return record.toUnicode()
            except Exception:
                try:
                    return record.string.decode(record.getEncoding(), errors="replace")
                except Exception:
                    pass
    return fallback


def build_glyph_db(root_dir: Path, output_csv: Path, extensions=(".ttf",)) -> None:
    """
    Walk root_dir recursively, process all font files with given extensions,
    and write the glyph hash database to output_csv.
    """
    font_files = list(root_dir.rglob("*"))
    font_files = [p for p in font_files if p.suffix.lower() in extensions]

    if not font_files:
        print(f"No font files with extensions {extensions} found under {root_dir}", file=sys.stderr)
        return

    print(f"Found {len(font_files)} font file(s). Building database...")

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "glyph_hash",
                "font_postscript_name",
                "font_file",
                "glyph_name",
                "codepoint",
                "unicode_char",
                "unicode_hex",
            ]
        )

        for font_path in font_files:
            print(f"Processing {font_path}...")
            try:
                ttfont = TTFont(font_path)
            except TTLibError as e:
                print(f"  Skipping (failed to open): {e}", file=sys.stderr)
                continue

            ps_name = get_postscript_name(ttfont, fallback=font_path.stem)

            if "glyf" not in ttfont:
                print(f"  Skipping (no 'glyf' table – likely CFF): {font_path}", file=sys.stderr)
                continue

            # Build glyph -> list[codepoint] from the best cmap
            glyph_to_cps = {}
            try:
                cmap = ttfont["cmap"].getBestCmap()
            except Exception:
                cmap = None

            if cmap is None:
                cmap = {}

            for cp, gname in cmap.items():
                glyph_to_cps.setdefault(gname, []).append(cp)

            glyf = ttfont["glyf"]
            for glyph_name in glyf.keys():
                try:
                    glyph_hash = compute_glyph_hash(ttfont, glyph_name)
                except Exception as e:
                    print(f"  Failed hashing glyph '{glyph_name}' in {font_path}: {e}", file=sys.stderr)
                    continue

                cps = glyph_to_cps.get(glyph_name, [])
                if cps:
                    # Record a row per codepoint
                    for cp in cps:
                        ch = chr(cp)
                        unicode_hex = f"U+{cp:04X}"
                        writer.writerow(
                            [
                                glyph_hash,
                                ps_name,
                                glyph_name,
                                cp,
                                unicode_hex,
                            ]
                        )
                else:
                    # Glyph not mapped to any Unicode codepoint
                    writer.writerow(
                        [
                            glyph_hash,
                            ps_name,
                            glyph_name,
                            "",
                            "",
                        ]
                    )


def main():
    parser = argparse.ArgumentParser(description="Build glyph-hash database from TTF fonts.")
    parser.add_argument("root", type=str, help="Root folder containing fonts (scanned recursively).")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="glyph_db.csv",
        help="Output CSV file (default: glyph_db.csv)",
    )
    parser.add_argument(
        "--include-otf",
        action="store_true",
        help="Also include .otf files (note: CFF outlines not yet supported).",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"Root path is not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    exts = [".ttf"]
    if args.include_otf:
        exts.append(".otf")

    build_glyph_db(root, Path(args.output), extensions=tuple(exts))


if __name__ == "__main__":
    main()
