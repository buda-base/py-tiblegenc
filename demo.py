from io import StringIO
import re
from pathlib import Path
import json
import logging
import sys

from pytiblegenc import DuffedTextConverter, build_font_hash_index_from_csv, identify_pdf_fonts_from_db, get_glyph_db_path
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from pdfminer.layout import LTPage
from pdfminer.pdfparser import PDFParser
from pdfminer.layout import LAParams

# uncomment to debug region
#logging.basicConfig(level=logging.DEBUG)

def custom_error_chr(char, font_name, char_code=None):
    """
    Custom error character handler that logs to stderr and returns [u] in the output.
    """
    if char_code is None:
        char_code = ord(char)
    print(f"Unknown character: '{char}' (U+{char_code:04X}, {char_code}) in font '{font_name}'", file=sys.stderr)
    return "[u]"

# region is x, y, w, h as in https://iiif.io/api/image/3.0/#41-region
# REGION = [132,0,928,100000] # KWSB
#REGION = [125,0,935,100000] # KWKB
#REGION = [99,0,645,100000] # KWKB
REGION = None



def converted_txt_from_pdf(pdf_file_name, region=None, page_break_str="\n\n-- page {} --\n\n", remove_non_hz=True):
    stats = {
        "unhandled_fonts": {},
        "handled_fonts": {},
        "unknown_characters": {},
        "error_characters": 0,
        "diffs_with_utfc": {},
        "nb_non_horizontal_removed": 0
    }
    output_string = StringIO()
    with open(pdf_file_name, 'rb') as in_file:
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
        device = DuffedTextConverter(rsrcmgr, output_string, stats, region = region, pbs = page_break_str, remove_non_hz=remove_non_hz, font_normalization=font_normalization, error_chr_fun=custom_error_chr)
        interpreter = PDFPageInterpreter(rsrcmgr, device)
        for page in PDFPage.create_pages(doc):
            interpreter.process_page(page)
            #break
    res = output_string.getvalue()
    res = re.sub(r"\n\n+", "\n", res)
    print(json.dumps(stats))
    for fontname in stats["unknown_characters"]:
        for c in stats["unknown_characters"][fontname]:
            print("%s,%d,??(%s)" % (fontname, ord(c), c))
    return res

def convert_folder(input_folder="input/", output_folder="output/", region=None, page_break_str="\n\n-- page {} --\n\n"):
    paths = sorted(Path(input_folder).glob("*.pdf"))
    for path in paths:
        try:
            txt = converted_txt_from_pdf(path, region, page_break_str)
            txt_path = Path(output_folder) / Path(str(path.stem) + ".txt")
            print(txt_path)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(txt)
        except ValueError:
            print("couldn't open %s" % path)

def identify_fonts_in_pdf(pdf_file_path):
    glyph_db_path = get_glyph_db_path()
    glyph_index = build_font_hash_index_from_csv(glyph_db_path)
    #print(glyph_index)
    with open(pdf_file_path, 'rb') as in_file:
        parser = PDFParser(in_file)
        doc = PDFDocument(parser)
        normalized_fonts = identify_pdf_fonts_from_db(doc, glyph_index)
        print(normalized_fonts)

# [0,50,1000000,500]
#convert_folder("input7/", "output/", None, "\n\n-- page {} --\n\n")
# for KR: cropbox is 595x842
# margin left = 550/4674  * 842 = 99
# right region = 4133/4674  * 842 = 744
txt = converted_txt_from_pdf("withoutnames.pdf", REGION, "\n\n-- page {} --\n\n")
print(txt)

identify_fonts_in_pdf("withoutnames.pdf")