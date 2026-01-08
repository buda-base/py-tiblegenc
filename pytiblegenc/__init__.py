"""
Top-level package exports for `pytiblegenc`.

Important: keep this module *lightweight*.

Many users only need `pytiblegenc.char_converter.convert_string`. Importing a
submodule like `pytiblegenc.char_converter` still executes this `__init__.py`
first, so we must avoid importing heavy/side-effectful modules here.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    # Character conversion (no pdfminer dependency)
    "convert_string",
    "normalize_font_name",
    "default_error_chr",
    # Existing public API (lazy-imported)
    "DuffedTextConverter",
    "get_glyph_hashes_from_bytes",
    "identify_font",
    "identify_pdf_fonts_from_db",
    "build_font_hash_index_from_csv",
    "build_font_hash_index",
    "get_glyph_db_path",
    "pdf_to_txt",
]

if TYPE_CHECKING:
    # These imports are only for type-checkers; at runtime we resolve lazily.
    from .char_converter import convert_string, default_error_chr, normalize_font_name
    from .font_utils import (
        build_font_hash_index,
        build_font_hash_index_from_csv,
        get_glyph_db_path,
        get_glyph_hashes_from_bytes,
        identify_font,
        identify_pdf_fonts_from_db,
    )
    from .pdfminer_text_converter import DuffedTextConverter
    from .utils import pdf_to_txt


_EXPORT_MAP = {
    # char_converter.py
    "convert_string": (".char_converter", "convert_string"),
    "normalize_font_name": (".char_converter", "normalize_font_name"),
    "default_error_chr": (".char_converter", "default_error_chr"),
    # pdfminer_text_converter.py
    "DuffedTextConverter": (".pdfminer_text_converter", "DuffedTextConverter"),
    # font_utils.py
    "get_glyph_hashes_from_bytes": (".font_utils", "get_glyph_hashes_from_bytes"),
    "identify_font": (".font_utils", "identify_font"),
    "identify_pdf_fonts_from_db": (".font_utils", "identify_pdf_fonts_from_db"),
    "build_font_hash_index_from_csv": (".font_utils", "build_font_hash_index_from_csv"),
    "build_font_hash_index": (".font_utils", "build_font_hash_index"),
    "get_glyph_db_path": (".font_utils", "get_glyph_db_path"),
    # utils.py
    "pdf_to_txt": (".utils", "pdf_to_txt"),
}


def __getattr__(name: str) -> Any:
    """
    Lazily expose the public API.

    This keeps `import pytiblegenc` and `import pytiblegenc.char_converter` safe
    in environments that don't need (or can't import) pdfminer/font tools.
    """

    target = _EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = target
    mod = import_module(module_name, __name__)
    value = getattr(mod, attr_name)
    globals()[name] = value  # cache for subsequent accesses
    return value
