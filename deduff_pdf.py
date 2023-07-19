from io import StringIO
import re
from pathlib import Path
import json
import logging

from pdfminer_text_converter import DuffedTextConverter
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from pdfminer.layout import LTPage
from pdfminer.pdfparser import PDFParser
from pdfminer.layout import LAParams
from pdfminer.converter import PDFLayoutAnalyzer
from pdfminer.utils import apply_matrix_pt

# uncomment to debug region
#logging.basicConfig(level=logging.DEBUG)

# region is x, y, w, h as in https://iiif.io/api/image/3.0/#41-region
# REGION = [132,0,928,100000] # KWSB
#REGION = [125,0,935,100000] # KWKB
REGION = [0,0,100000,100000] # KWKB

# see https://github.com/pdfminer/pdfminer.six/issues/900
# for some reason pdfminer uses the mediabox coordinates for LTPage
# but it seems that cropbox is a better choice. This hack does this:

def cropbox_begin_page(self, page, ctm):
    (x0, y0, x1, y1) = page.cropbox
    (x0, y0) = apply_matrix_pt(ctm, (x0, y0))
    (x1, y1) = apply_matrix_pt(ctm, (x1, y1))
    mediabox = (0, 0, abs(x0 - x1), abs(y0 - y1))
    self.cur_item = LTPage(self.pageno, mediabox)

def cropbox_process_page(self, page: PDFPage) -> None:
    #log.debug("Processing page: %r", page)
    (x0, y0, x1, y1) = page.cropbox
    if page.rotate == 90:
        ctm = (0, -1, 1, 0, -y0, x1)
    elif page.rotate == 180:
        ctm = (-1, 0, 0, -1, x1, y1)
    elif page.rotate == 270:
        ctm = (0, 1, -1, 0, y1, -x0)
    else:
        ctm = (1, 0, 0, 1, -x0, -y0)
    self.device.begin_page(page, ctm)
    self.render_contents(page.resources, page.contents, ctm=ctm)
    self.device.end_page(page)
    return

PDFLayoutAnalyzer.begin_page = cropbox_begin_page
PDFPageInterpreter.process_page = cropbox_process_page

def deduffed_txt_from_pdf(pdf_file_name, region=None, page_break_str="\n\n-- page {} --\n\n", remove_non_hz=True):
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
        rsrcmgr = PDFResourceManager()
        device = DuffedTextConverter(rsrcmgr, output_string, stats, region = region, pbs = page_break_str, remove_non_hz=remove_non_hz)
        interpreter = PDFPageInterpreter(rsrcmgr, device)
        pnum = 1
        for page in PDFPage.create_pages(doc):
            interpreter.process_page(page)
            pnum += 1
            #break
    res = output_string.getvalue()
    res = re.sub(r"\n\n+", "\n", res)
    print(json.dumps(stats))
    for fontname in stats["unknown_characters"]:
        for c in stats["unknown_characters"][fontname]:
            print("%s,%d,??(%s)" % (fontname, ord(c), c))
    return res

def deduff_folder(input_folder="input/", output_folder="output/", region=None, page_break_str="\n\n-- page {} --\n\n"):
    paths = sorted(Path(input_folder).glob("*.pdf"))
    for path in paths:
        txt = deduffed_txt_from_pdf(path, region, page_break_str)
        txt_path = Path(output_folder) / Path(str(path.stem) + ".txt")
        print(txt_path)
        with open(txt_path, "w") as f:
            f.write(txt)
        #break

# [0,50,1000000,500]
deduff_folder("input/", "output/", None, "\n\n-- page {} --\n\n")
#txt = deduffed_txt_from_pdf("input/v7p6.pdf", REGION, "--lb--")
#print(txt)