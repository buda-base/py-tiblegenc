from io import StringIO
import re
import logging
from typing import Optional, Callable

from .pdfminer_text_converter import DuffedTextConverter
from .font_utils import (
    get_glyph_db_path,
    build_font_hash_index_from_csv,
    identify_pdf_fonts_from_db,
)
from .normalization import normalize_unicode
from .font_size_utils import simplify_font_sizes

from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser


def pdf_to_txt(
    pdf_path: str,
    region: Optional[list] = None,
    page_break_str: str = "\n\n-- page {} --\n\n",
    remove_non_hz: bool = True,
    track_font_size: bool = False,
    font_size_format: str = "<fs:{}>",
    error_chr_fun: Optional[Callable] = None,
    normalize: bool = False,
    simplify_font_sizes_option: bool = False,
) -> str:
    """
    High-level function to convert a PDF file to text.
    
    Args:
        pdf_path: Path to the PDF file to convert
        region: Optional region to extract [x, y, width, height]. 
                If coordinates are floats between 0 and 1, they are treated as relative.
        page_break_str: String format for page breaks (default: "\\n\\n-- page {} --\\n\\n")
        remove_non_hz: Whether to remove non-horizontal text (default: True)
        track_font_size: Whether to track and mark font size changes (default: False)
        font_size_format: Format string for font size markers when track_font_size=True (default: "<fs:{}>")
        error_chr_fun: Optional function to handle unrecognized characters.
                      Signature: error_chr_fun(char, font_name, char_code) -> str
                      If None, uses default handler that returns the original character.
        normalize: Whether to apply Unicode normalization (default: False)
        simplify_font_sizes_option: Whether to simplify font size markup (default: False)
                                    Only effective if track_font_size=True
    
    Returns:
        String containing the converted text
    
    Example:
        >>> text = pdf_to_txt("document.pdf", normalize=True)
        >>> text = pdf_to_txt("document.pdf", track_font_size=True, simplify_font_sizes_option=True)
    """
    stats = {
        "unhandled_fonts": {},
        "handled_fonts": {},
        "unknown_characters": {},
        "error_characters": 0,
        "diffs_with_utfc": {},
        "nb_non_horizontal_removed": 0
    }
    
    output_string = StringIO()
    
    with open(pdf_path, 'rb') as in_file:
        parser = PDFParser(in_file)
        doc = PDFDocument(parser)
        
        # Identify fonts from DB and get normalization mapping
        font_normalization = None
        try:
            glyph_db_path = get_glyph_db_path()
            glyph_index = build_font_hash_index_from_csv(str(glyph_db_path))
            font_normalization = identify_pdf_fonts_from_db(doc, glyph_index)
        except Exception as e:
            logging.warning(f"Could not load font normalization: {e}")
        
        rsrcmgr = PDFResourceManager()
        device = DuffedTextConverter(
            rsrcmgr, 
            output_string, 
            stats, 
            region=region, 
            pbs=page_break_str, 
            remove_non_hz=remove_non_hz, 
            font_normalization=font_normalization, 
            error_chr_fun=error_chr_fun, 
            track_font_size=track_font_size, 
            font_size_format=font_size_format
        )
        interpreter = PDFPageInterpreter(rsrcmgr, device)
        for page in PDFPage.create_pages(doc):
            interpreter.process_page(page)
    
    # Get the raw converted text
    res = output_string.getvalue()
    
    # Post-process: collapse multiple newlines
    res = re.sub(r"\n\n+", "\n", res)
    
    # Post-process: simplify font sizes if requested
    if simplify_font_sizes_option and track_font_size:
        res = simplify_font_sizes(res)
    
    # Post-process: normalize Unicode if requested
    if normalize:
        res = normalize_unicode(res)
    
    return res

