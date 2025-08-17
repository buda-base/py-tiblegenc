#!/usr/bin/env python3
# convert_wp_html.py
"""
Convert WP-style HTML:
- Build class → font map from <style> blocks (font-family + bold/italic).
- Replace h[XX] byte sequences in body using char_converter._convert_byte().
  * If the byte < 0x20 (control code), ignore it (do not convert; drop it).
- Strip font-family/font-style/font-weight from CSS.
- In the <body>, remove regular space characters U+0020 from text content.
  * Do NOT modify &nbsp; or numeric char refs (e.g., &#160;). Keep them as-is.
"""

import argparse
import re
import sys
from pathlib import Path
import html as _html
from html.parser import HTMLParser

# --- import helpers from char_converter.py ---
try:
    from char_converter import normalize_font_name, _convert_byte  # noqa: F401
except Exception:
    # Try importing from the script's directory (fallback).
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    from char_converter import normalize_font_name, _convert_byte  # type: ignore

STYLE_BLOCK_RE = re.compile(r"(<style[^>]*>)(.*?)(</style>)", re.IGNORECASE | re.DOTALL)
CSS_RULE_RE = re.compile(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", re.DOTALL | re.IGNORECASE)
HBYTE_RE = re.compile(r"h\[\s*([0-9A-Fa-f]{2})\s*\]")

def _clean_css_remove_font_props(css: str) -> str:
    # Remove the three font-related declarations everywhere
    css = re.sub(r"font-(?:family|style|weight)\s*:\s*[^;{}]*;?", "", css, flags=re.IGNORECASE)
    # Light cleanup so we don't leave dangling semicolons
    css = re.sub(r";\s*;", ";", css)
    css = re.sub(r"\{\s*;", "{", css)
    css = re.sub(r"\s+\}", "}", css)
    return css

def _parse_weight(body: str) -> str | None:
    bold = False
    italic = False
    m = re.search(r"font-weight\s*:\s*([A-Za-z]+)", body, flags=re.IGNORECASE)
    if m and m.group(1).strip().lower() == "bold":
        bold = True
    m = re.search(r"font-style\s*:\s*([A-Za-z]+)", body, flags=re.IGNORECASE)
    if m and m.group(1).strip().lower() == "italic":
        italic = True
    if bold and italic:
        return "bi"
    if bold:
        return "b"
    if italic:
        return "i"
    return None

def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and ((s[0] == s[-1] == "'") or (s[0] == s[-1] == '"')):
        return s[1:-1].strip()
    return s

def _parse_family(body: str) -> str | None:
    m = re.search(r"font-family\s*:\s*([^;{}]+)", body, flags=re.IGNORECASE)
    if not m:
        return None
    fam_val = m.group(1).strip()
    # Only take the first family if a list is provided
    first = fam_val.split(",", 1)[0]
    return _strip_quotes(first)

def extract_class_to_font_map_and_strip_css(html_text: str):
    """
    Returns (new_html_with_stripped_css, class_to_font_map)
    """
    class_to_font: dict[str, str] = {}

    def repl_style(m):
        css = m.group(2)
        # Build/extend the class→font map from this block
        for rule_match in CSS_RULE_RE.finditer(css):
            classname, body = rule_match.groups()
            family = _parse_family(body)
            weight = _parse_weight(body)
            if family:
                normalized = normalize_font_name(family, weight=weight)
                class_to_font[classname] = normalized
        # Now strip the font-* properties
        stripped = _clean_css_remove_font_props(css)
        return f"{m.group(1)}{stripped}{m.group(3)}"

    new_html = STYLE_BLOCK_RE.sub(repl_style, html_text)
    return new_html, class_to_font

class BodyConverter(HTMLParser):
    """
    Stream HTML and convert h[XX] sequences in text nodes using
    the effective font derived from class attributes and the class→font map.
    Additionally, inside <body>:
      - Remove all regular spaces (U+0020) from text nodes.
      - Keep &nbsp; (and numeric entities like &#160;) intact; do not replace them.
    """
    def __init__(self, class_to_font: dict[str, str]):
        super().__init__(convert_charrefs=False)  # keep &nbsp; etc. as entity refs
        self.class_to_font = class_to_font
        self.out: list[str] = []
        self.tag_stack: list[str] = []
        self.in_body: bool = False
        # Stack of effective fonts (top = current). Start with None.
        self.font_stack: list[str | None] = [None]

    # ---- helpers ----
    def _attrs_to_html(self, attrs):
        parts = []
        for k, v in attrs:
            if v is None:
                parts.append(f" {k}")
            else:
                parts.append(f' {k}="{_html.escape(v, quote=True)}"')
        return "".join(parts)

    def _effective_font_for_attrs(self, attrs) -> str | None:
        # If the tag defines a class present in the map, use it; else inherit.
        class_val = None
        for k, v in attrs:
            if k.lower() == "class" and v:
                class_val = v
                break
        chosen = None
        if class_val:
            for cls in class_val.split():
                if cls in self.class_to_font:
                    chosen = self.class_to_font[cls]
                    break
        return chosen if chosen is not None else self.font_stack[-1]

    def _apply_hbyte_and_space_rules(self, text: str) -> str:
        # Apply h[XX] replacement using current font (if any)
        font = self.font_stack[-1]
        if font:
            def repl(m):
                b = int(m.group(1), 16)
                #if b < 0x20:
                #    return ""  # ignore control codes
                rep = _convert_byte(b, font)
                return rep if rep is not None else ""
            text = HBYTE_RE.sub(repl, text)
        # If we're in <body>, remove all regular spaces U+0020
        if self.in_body:
            text = text.replace(" ", "")
        return text

    def _append_text(self, text: str):
        self.out.append(self._apply_hbyte_and_space_rules(text))

    # ---- HTMLParser methods ----
    def handle_starttag(self, tag, attrs):
        self.tag_stack.append(tag.lower())
        if tag.lower() == "body":
            self.in_body = True
        self.font_stack.append(self._effective_font_for_attrs(attrs))
        self.out.append(f"<{tag}{self._attrs_to_html(attrs)}>")

    def handle_endtag(self, tag):
        self.out.append(f"</{tag}>")
        if self.font_stack:
            self.font_stack.pop()
        if self.tag_stack:
            last = self.tag_stack.pop()
            if last == "body":
                self.in_body = False

    def handle_startendtag(self, tag, attrs):
        # e.g. <br />, <meta />
        self.out.append(f"<{tag}{self._attrs_to_html(attrs)}/>")

    def handle_data(self, data):
        self._append_text(data)

    def handle_entityref(self, name):
        # Keep entities (including &nbsp;) untouched
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        # Keep numeric entities untouched
        self.out.append(f"&#{name};")

    def handle_comment(self, data):
        self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        # Preserve doctype etc.
        self.out.append(f"<!{decl}>")

    def unknown_decl(self, data):
        self.out.append(f"<![{data}]>")

    def handle_pi(self, data):
        self.out.append(f"<?{data}>")

    def get_output(self) -> str:
        return "".join(self.out)

def convert_html(html_text: str) -> str:
    # 1) Parse styles → class_to_font, and strip font-* from CSS
    stripped_html, class_to_font = extract_class_to_font_map_and_strip_css(html_text)
    # 2) Walk document and convert within <body>
    parser = BodyConverter(class_to_font)
    parser.feed(stripped_html)
    parser.close()
    return parser.get_output()

def main():
    p = argparse.ArgumentParser(description="Convert WP HTML by decoding h[XX] sequences using font tables.")
    p.add_argument("input_html", help="Path to the input HTML file.")
    p.add_argument("-o", "--output", help="Write converted HTML to this file (defaults to stdout).")
    args = p.parse_args()

    with open(args.input_html, "r", encoding="utf-8") as f:
        src = f.read()

    out = convert_html(src)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
    else:
        sys.stdout.write(out)

if __name__ == "__main__":
    main()
