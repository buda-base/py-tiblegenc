import csv
import logging
import os

BASE = None
UTFC_BASE = None
ERROR_CHR = "༠༠༠༠"
DEBUGMODE = False

def get_base():
    global BASE
    if BASE is not None:
        return BASE
    BASE = get_base_from_file('tiblegenc.csv')
    return BASE

def get_utfc_base():
    global UTFC_BASE
    if UTFC_BASE is not None:
        return UTFC_BASE
    UTFC_BASE = get_base_from_file('utfc.csv')
    return UTFC_BASE

def get_base_from_file(filename):
    base = {}
    path = os.path.join(os.path.split(__file__)[0], 'font-tables', filename)
    with open(str(path), newline='', encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile, quotechar='"')
        for row in reader:
            if row[0] not in base:
                base[row[0]] = {}
            base[row[0]][chr(int(row[1]))] = row[2]
    return base

FONT_ALIASES = {
    "Dedris-syma": "Ededris-sym",
    "Ededris-syma": "Ededris-sym",
    "TibetanClassicSkt": "TibetanClassicSkt1",
    "TibetanChogyalSkt": "TibetanChogyalSkt1",
}

def uni_char_from_encoding(nonunicp, encoding="cp1252"):
    noncpbytes = nonunicp.to_bytes(1, "big")
    try:
        unistr = noncpbytes.decode("cp1252")
        logging.debug("decoding %d (%s) into %s (%d)" % (nonunicp, noncpbytes.hex(), unistr, ord(unistr)))
    except UnicodeDecodeError:
        return

def _convert_char(char, font_name, stats):
    base = get_base()
    utfc_base = get_utfc_base()
    if char == "\u00a0":
        char = " "
    base_ft = base.get(font_name)
    utfc_base_ft = utfc_base.get(font_name)
    if (base_ft is None or char not in base_ft) and (utfc_base_ft is None or char not in utfc_base_ft):
        if font_name not in stats["unknown_characters"]:
            stats["unknown_characters"][font_name] = {}
        if char not in stats["unknown_characters"][font_name]:
            stats["unknown_characters"][font_name][char] = 0
        stats["unknown_characters"][font_name][char] += 1
        #logging.error("unknown character: '%s' (%d) in %s" % (char, ord(char), font_name))
        if DEBUGMODE:
            #return "%s,%d,?(%s)" % (font_name, ord(char), char)
            return "[[%s]]" % (char)
        else:
            return ""
    res = base_ft.get(char) if base_ft is not None else None
    utfc_res = utfc_base_ft.get(char) if utfc_base_ft is not None else None
    if res is not None and utfc_res is not None and res != utfc_res:
        stats_key = "%s,%d" % (font_name, ord(char))
        if stats_key not in stats["diffs_with_utfc"]:
            stats["diffs_with_utfc"][stats_key] = 0
        stats["diffs_with_utfc"][stats_key] += 1
        if DEBUGMODE:
            return "[[%s,%d,%s or %s]]" % (font_name, ord(char), res, utfc_res)
        else:
            return res
    if res == ERROR_CHR:
        stats["error_characters"] += 1
        if DEBUGMODE:
            return '[[ERR]]'
        else:
            return ''
    return res if res is not None else utfc_res

def convert_string(s, font_name, stats):
    if s.startswith("(cid:"):
        return ""
    if font_name in FONT_ALIASES:
        font_name = FONT_ALIASES[font_name]
    if font_name.startswith("Dedris"):
        font_name = "Ed"+font_name[1:]
    # Todo: also replace "Drutsa-" and "Khamdris-" to "Ededris-"
    if font_name.startswith("Sam") and len(font_name) == 4:
        font_name = "Es"+font_name[1:]
    base = get_base()
    utfc_base = get_utfc_base()
    if font_name not in base and font_name not in utfc_base:
        if font_name not in stats["unhandled_fonts"]:
            stats["unhandled_fonts"][font_name] = 0
        stats["unhandled_fonts"][font_name] += 1
        return None
    if font_name not in stats["handled_fonts"]:
        stats["handled_fonts"][font_name] = 0
    stats["handled_fonts"][font_name] += 1
    res = ''
    for char in s:
        res += _convert_char(char, font_name, stats)
    #logging.error("converted %s:%s -> %s" % (font_name, s, res))
    return res