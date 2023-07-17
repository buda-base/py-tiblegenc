from pdfminer.layout import LAParams
from pdfminer.converter import PDFConverter
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.layout import LAParams, LTComponent, TextGroupElement
from pdfminer.layout import LTAnno
from pdfminer.layout import LTChar
from pdfminer.layout import LTContainer
from pdfminer.layout import LTCurve
from pdfminer.layout import LTFigure
from pdfminer.layout import LTImage
from pdfminer.layout import LTItem
from pdfminer.layout import LTLayoutContainer
from pdfminer.layout import LTLine
from pdfminer.layout import LTPage
from pdfminer.layout import LTRect
from pdfminer.layout import LTText
from pdfminer.layout import LTTextBox
from pdfminer.layout import LTTextBoxVertical
from pdfminer.layout import LTTextGroup
from pdfminer.layout import LTTextLine
from pdfminer.utils import AnyIO, Point, Matrix, Rect, PathSegment, make_compat_str, compatible_encode_method
from char_converter import convert_string
import logging

from typing import (
    BinaryIO,
    Dict,
    Generic,
    List,
    Optional,
    Sequence,
    TextIO,
    Tuple,
    TypeVar,
    Union,
    cast,
)

USUAL_LA_PARAMS = LAParams(word_margin=10000, char_margin=1000)

class DuffedTextConverter(PDFConverter[AnyIO]):
    def __init__(
        self,
        rsrcmgr: PDFResourceManager,
        outfp: AnyIO,
        stats: dict,
        codec: str = "utf-8",
        pageno: int = 1,
        laparams: Optional[LAParams] = USUAL_LA_PARAMS,
        imagewriter = None,
        region = None,
        maxlines = 100,
        remove_non_hz=True,
        pbs = "\n\n-- page {} --\n\n",
    ) -> None:
        super().__init__(rsrcmgr, outfp, codec=codec, pageno=pageno, laparams=laparams)
        self.imagewriter = imagewriter
        self.region = region
        self.stats = stats
        self.maxlines = maxlines
        if region and len(region) == 4:
            # adding x2 and y2
            self.region.append(region[0]+region[2])
            self.region.append(region[1]+region[3])
        self.pbs = pbs
        self.remove_non_hz = remove_non_hz

    def in_region(self, item, ltpage):
        if not self.region or not hasattr(item, "x0"):
            return True
        if item.x0 < self.region[0] or item.y0 < self.region[1]:
            return False
        if item.x1 > self.region[4] or item.y1 > self.region[5]:
            return False
        # remove if you also want to convert invisible characters
        if hasattr(ltpage, "x0"):
            if item.x0 < ltpage.x0 or item.x1 > ltpage.x1 or item.y0 < ltpage.y0 or item.y1 > ltpage.y1:
                return False
        return True

    def is_rotated(self, item):
        if not item.matrix:
            return False
        return item.matrix[1] != 0.0 or item.matrix[2] != 0.0

    def convert_item(self, item, ltpage) -> None:
        text = item.get_text()
        if not hasattr(item, "fontname"):
            self.write_text(text)
            return
        if not self.in_region(item, ltpage):
            if hasattr(item, "x0"):
               logging.debug("x0: %f, x1: %f, y0: %f, y1: %f, in_region=False" % (item.x0, item.x1, item.y0, item.y1))
            return
        if self.remove_non_hz and self.is_rotated(item):
            logging.debug("matrix: %s is_rotated=True", item.matrix)
            self.stats["nb_non_horizontal_removed"] += 1
            return
        #logging.error("x0: %f, x1: %f, y0: %f, y1: %f, in_region=True %s" % (item.x0, item.x1, item.y0, item.y1, item))
        #logging.error(ltpage.y1)
        fontname = item.fontname
        fontname = fontname[fontname.find('+')+1:]
        ctext = convert_string(text, fontname, self.stats)
        if ctext is not None:
            text = ctext
        self.write_text(text)

    def write_text(self, text: str) -> None:
        text = compatible_encode_method(text, self.codec, "ignore")
        if self.outfp_binary:
            cast(BinaryIO, self.outfp).write(text.encode())
        else:
            cast(TextIO, self.outfp).write(text)

    def receive_layout(self, ltpage: LTPage) -> None:
        def render(item: LTItem, linenumref) -> None:
            if isinstance(item, LTContainer):
                for child in item:
                    render(child, linenumref)
            elif isinstance(item, LTText):
                if linenumref["linenum"] <= self.maxlines:
                    self.convert_item(item, ltpage)
            if isinstance(item, LTTextBox):
                self.write_text("\n")
                linenumref["linenum"] += 1
            elif isinstance(item, LTImage):
                if self.imagewriter is not None:
                    self.imagewriter.export_image(item)
        self.write_text(self.pbs.format(ltpage.pageid))
        render(ltpage, {"linenum": 1})

    # Some dummy functions to save memory/CPU when all that is wanted
    # is text.  This stops all the image and drawing output from being
    # recorded and taking up RAM.
    def render_image(self, name: str, stream) -> None:
        if self.imagewriter is None:
            return
        PDFConverter.render_image(self, name, stream)

    def paint_path(
        self,
        gstate,
        stroke: bool,
        fill: bool,
        evenodd: bool,
        path: Sequence[PathSegment],
    ) -> None:
        return