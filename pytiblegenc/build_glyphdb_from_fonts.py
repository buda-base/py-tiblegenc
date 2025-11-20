#!/usr/bin/env python3
# create_db.py
"""
Create a glyph-hash CSV database from a folder of fonts.

Uses font_utils.get_glyph_hashes_from_bytes(), which:
  - parses fonts with fontTools
  - falls back to FontForge CLI repair when needed

Output CSV columns:
    glyph_hash,font_postscript_name,font_file,glyph_name,codepoint,unicode_char,unicode_hex

Usage:
    python create_db.py /path/to/fonts -o glyph_db.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Tuple, Set

from font_utils import get_glyph_hashes_from_bytes, GlyphRecord


def build_glyph_db(root_dir: Path, output_csv: Path, extensions=(".ttf",)) -> None:
    """
    Walk root_dir recursively, process all font files with given extensions,
    and write the glyph hash database to output_csv.
    """
    font_files = [p for p in root_dir.rglob("*") if p.suffix.lower() in extensions]

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
                "glyph_name",
                "codepoint"
            ]
        )

        for font_path in font_files:
            font_path_str = str(font_path)
            print(f"Processing {font_path_str}...")

            try:
                font_bytes = font_path.read_bytes()
            except Exception as e:
                print(f"  Skipping (failed to read file): {e}", file=sys.stderr)
                continue

            try:
                ps_name, records = get_glyph_hashes_from_bytes(font_bytes)
            except Exception as e:
                print(f"  Skipping (failed to process font): {e}", file=sys.stderr)
                continue

            _write_font_records(writer, font_path_str, ps_name, records)


def _write_font_records(
    writer: csv.writer,
    font_path_str: str,
    ps_name: str,
    records: Set[GlyphRecord],
) -> None:
    """
    Write CSV rows for all glyph records of a single font.
    Each record is (glyph_name, glyph_hash, codepoints_tuple).
    """
    for glyph_name, glyph_hash, cps in records:
        if cps:
            for cp in cps:
                writer.writerow(
                    [
                        glyph_hash,
                        ps_name,
                        glyph_name,
                        cp
                    ]
                )
        else:
            writer.writerow(
                [
                    glyph_hash,
                    ps_name,
                    glyph_name,
                    ""
                ]
            )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Build glyph-hash database from fonts using fontTools (+ optional FontForge repair)."
    )
    parser.add_argument(
        "root",
        type=str,
        help="Root folder containing fonts (scanned recursively).",
    )
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
        help="Also include .otf files.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

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
