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
from pdfminer.converter import PDFLayoutAnalyzer
from pdfminer.pdffont import PDFFont
from pdfminer.pdfdevice import PDFUnicodeNotDefined
from pdfminer.pdfcolor import PDFColorSpace
from pdfminer.pdfinterp import PDFGraphicState
from pdfminer.utils import AnyIO, Point, Matrix, Rect, PathSegment, make_compat_str, compatible_encode_method
from pdfminer.utils import apply_matrix_pt

from .char_converter import convert_string
import logging

MIN_TEXT_SIZE = 5  # points

from typing import (
    BinaryIO,
    Dict,
    Generic,
    List,
    Optional,
    Sequence,
    Set,
    TextIO,
    Tuple,
    TypeVar,
    Union,
    cast,
)

USUAL_LA_PARAMS = LAParams(
    char_margin=1000,    # merge far-apart glyph runs on same visual line
    word_margin=1000,    # allow wide spacing without splitting words
    char_margin_left=2,  # new parameter, see https://github.com/pdfminer/pdfminer.six/issues/1173
    line_overlap=0.0, # for some reason, just makes things crazy
    line_margin=1.8,  # merge close baselines
    boxes_flow=None,  # don't attempt column-flow reordering
    detect_vertical=False,
    all_texts=False,
)

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

PDFLayoutAnalyzer.begin_page = cropbox_begin_page
PDFPageInterpreter.process_page = cropbox_process_page

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
        font_normalization: Optional[Dict[str, Set[str]]] = None,
        error_chr_fun = None,
        track_font_size: bool = False,
        font_size_format: str = "<fs:{}>",
    ) -> None:
        super().__init__(rsrcmgr, outfp, codec=codec, pageno=pageno, laparams=laparams)
        self.imagewriter = imagewriter
        if region and len(region) == 4:
            self.region = [region[0], region[1], region[0]+region[2], region[1]+region[3]]
        else:
            self.region = None
        self.stats = stats
        self.maxlines = maxlines
        self.pbs = pbs
        self.remove_non_hz = remove_non_hz
        self.font_normalization = font_normalization
        self.error_chr_fun = error_chr_fun
        self.track_font_size = track_font_size
        self.font_size_format = font_size_format
        self.current_font_size = None
        # Keep a handle to the current LTPage so we can apply region tests
        # during render_char (i.e., before layout analysis runs).
        self._current_ltpage: Optional[LTPage] = None

    def begin_page(self, page: PDFPage, ctm: Matrix) -> None:
        """
        Override begin_page so we can track the current LTPage for pre-analysis
        filtering. We intentionally mirror the global cropbox hack behavior.
        """
        (x0, y0, x1, y1) = page.cropbox
        (x0, y0) = apply_matrix_pt(ctm, (x0, y0))
        (x1, y1) = apply_matrix_pt(ctm, (x1, y1))
        mediabox = (0, 0, abs(x0 - x1), abs(y0 - y1))
        self.cur_item = LTPage(self.pageno, mediabox)
        self._current_ltpage = self.cur_item

    def _is_rotated_matrix(self, matrix: Matrix) -> bool:
        # Same criterion as is_rotated(item): any non-zero shear terms.
        return bool(matrix and (matrix[1] != 0.0 or matrix[2] != 0.0))

    def render_char(
        self,
        matrix: Matrix,
        font: PDFFont,
        fontsize: float,
        scaling: float,
        rise: float,
        cid: int,
        ncs: PDFColorSpace,
        graphicstate: PDFGraphicState,
    ) -> float:
        """
        Create the LTChar, but drop it *before it is added to the layout tree*
        when it is out of region or rotated. This prevents ignored glyphs from
        influencing pdfminer's layout analysis (line grouping / textboxes).
        """
        try:
            text = font.to_unichr(cid)
            assert isinstance(text, str), str(type(text))
        except PDFUnicodeNotDefined:
            text = self.handle_undefined_char(font, cid)

        textwidth = font.char_width(cid)
        textdisp = font.char_disp(cid)
        item = LTChar(
            matrix,
            font,
            fontsize,
            scaling,
            rise,
            text,
            textwidth,
            textdisp,
            ncs,
            graphicstate,
        )

        # Pre-analysis filters: do NOT add ignored chars to the layout tree.
        if self.remove_non_hz and self._is_rotated_matrix(matrix):
            self.stats["nb_non_horizontal_removed"] += 1
            return item.adv

        if self._current_ltpage is not None and not self.in_region(item, self._current_ltpage):
            return item.adv

        self.cur_item.add(item)
        return item.adv

    def scale_region_box(self, ltpage):
        if not hasattr(ltpage, "x0"):
            return self.region
        res = []
        ltpage_w = ltpage.x1 - ltpage.x0
        ltpage_h = ltpage.y1 - ltpage.y0
        for i, c in enumerate(self.region):
            if c > 0 and c < 1:
                if i % 2 == 0:
                    c = int(c * ltpage_w) + ltpage.x0 
                else:
                    c = int(c * ltpage_h) + ltpage.y0
            res.append(c)
        # print("scale %s to %s" % (self.region, res))
        return res

    def in_region(self, item, ltpage):
        if not hasattr(item, "x0"):
            return True
        if hasattr(ltpage, "x0"):
            if item.x0 < ltpage.x0 or item.x1 > ltpage.x1 or item.y0 < ltpage.y0 or item.y1 > ltpage.y1:
                return False
        if self.region is None:
            return True
        # if region coordinates are floats between 0 and 1, we scale them with the ltpage coordinates:
        region_box = self.scale_region_box(ltpage)
        if item.x0 < region_box[0] or item.y0 < region_box[1]:
            return False
        if item.x1 > region_box[2] or item.y1 > region_box[3]:
            return False
        # remove if you also want to convert invisible characters
        
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
            #if hasattr(item, "x0"):
            #   logging.error("x0: %f, x1: %f, y0: %f, y1: %f, in_region=False" % (item.x0, item.x1, item.y0, item.y1))
            return
        if self.remove_non_hz and self.is_rotated(item):
            #logging.debug("matrix: %s is_rotated=True", item.matrix)
            self.stats["nb_non_horizontal_removed"] += 1
            return
        #logging.error("x0: %f, x1: %f, y0: %f, y1: %f, in_region=True %s" % (item.x0, item.x1, item.y0, item.y1, item))
        #logging.error(ltpage)
        fontname = item.fontname
        #logging.error(item.graphicstate)
        
        # Apply font normalization from DB if available (before any other normalization)
        if self.font_normalization is not None:
            # Try to find the font in the normalization mapping
            # Check full fontname first (e.g., 'ANIELG+Dedris-a')
            if fontname in self.font_normalization:
                normalized_set = self.font_normalization[fontname]
                if normalized_set:
                    # Use the first normalized name from the set
                    fontname = next(iter(normalized_set))
            else:
                # Try BaseFont part after '+' (e.g., 'Dedris-a')
                plus_pos = fontname.find('+')
                if plus_pos >= 0:
                    basefont = fontname[plus_pos+1:]
                    if basefont in self.font_normalization:
                        normalized_set = self.font_normalization[basefont]
                        if normalized_set:
                            fontname = next(iter(normalized_set))
        
        fontname = fontname[fontname.find('+')+1:]
        ctext = convert_string(text, fontname, self.stats, self.error_chr_fun)
        if ctext is not None:
            text = ctext
        
        # ignore very small decorative characters
        #if isinstance(item, LTChar) and item.size < MIN_TEXT_SIZE:
        #    return

        # Track font size if enabled (use LTChar.size for actual font size in points)
        if self.track_font_size and isinstance(item, LTChar):
            font_size = round(item.size)
            if self.current_font_size != font_size:
                self.current_font_size = font_size
                self.write_text(self.font_size_format.format(font_size))
        
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
        # Reset font size at the beginning of each page
        if self.track_font_size:
            self.current_font_size = None
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