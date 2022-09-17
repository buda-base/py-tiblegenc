from io import StringIO
import re
from pathlib import Path

from pdfminer_text_converter import DuffedTextConverter
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.layout import LAParams

# region is x, y, w, h as in https://iiif.io/api/image/3.0/#41-region
REGION = [120,0,950,100000]

def deduffed_txt_from_pdf(pdf_file_name, region=None, page_break_str="\n\n-- page {} --\n\n"):
    output_string = StringIO()
    with open(pdf_file_name, 'rb') as in_file:
        parser = PDFParser(in_file)
        doc = PDFDocument(parser)
        rsrcmgr = PDFResourceManager()
        device = DuffedTextConverter(rsrcmgr, output_string, region = REGION, pbs = page_break_str)
        interpreter = PDFPageInterpreter(rsrcmgr, device)
        for page in PDFPage.create_pages(doc):
            interpreter.process_page(page)
    res = output_string.getvalue()
    res = re.sub(r"\n\n+", "\n", res)
    return res

def deduff_folder(input_folder="input/", output_folder="output/", region=None, page_break_str="\n\n-- page {} --\n\n"):
    paths = Path(input_folder).glob("*.pdf")
    for path in paths:
        txt = deduffed_txt_from_pdf(path, region, page_break_str)
        txt_path = Path(output_folder) / Path(str(path.stem) + ".txt")
        print(txt_path)
        with open(txt_path, "w") as f:
            f.write(txt)

deduff_folder("input/", "output/", [120,0,950,100000], "\n\n-- page {} --\n\n")