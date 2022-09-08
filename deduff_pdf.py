from io import StringIO
import re

from pdfminer_text_converter import DuffedTextConverter
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.layout import LAParams

PAGE_BREAK_STR = "\n\n-- page {} --\n\n"
FILE_NAME = 'Copy of v1.pdf'
# region is x, y, w, h as in https://iiif.io/api/image/3.0/#41-region
REGION = [120,0,950,100000]

output_string = StringIO()
with open(FILE_NAME, 'rb') as in_file:
    parser = PDFParser(in_file)
    doc = PDFDocument(parser)
    rsrcmgr = PDFResourceManager()
    device = DuffedTextConverter(rsrcmgr, output_string, region = REGION, pbs = PAGE_BREAK_STR)
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    for page in PDFPage.create_pages(doc):
        interpreter.process_page(page)

res = output_string.getvalue()
res = re.sub(r"\n\n+", "\n", res)
print(res)