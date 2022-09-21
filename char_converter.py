import csv
import logging

BASE = None
ERROR_CHR = "༠༠༠༠"
DEBUGMODE = True

def get_base():
    global BASE
    if BASE is not None:
        return BASE
    with open('font_data.csv', newline='') as csvfile:
        BASE = {}
        reader = csv.reader(csvfile, quotechar='"')
        for row in reader:
            if row[0] not in BASE:
                BASE[row[0]] = {}
            BASE[row[0]][chr(int(row[1]))] = row[2]
    return BASE

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

def _convert_char(char, font_name):
    base = get_base()
    if char == "\u00a0":
        char = " "
    if char not in base[font_name]:
        logging.error("unknown character: '%s' (%d) in %s" % (char, ord(char), font_name))
        if DEBUGMODE:
            return "%s,%d,?(%s)" % (font_name, ord(char), char)
        else:
            return ""
    res = base[font_name][char]
    if res == ERROR_CHR:
        return ''
    return res

def convert_string(s, font_name):
    if font_name in FONT_ALIASES:
        font_name = FONT_ALIASES[font_name]
    if font_name.startswith("Dedris"):
        font_name = "Ed"+font_name[1:]
    if font_name.startswith("Sam") and len(font_name) == 4:
        font_name = "Es"+font_name[1:]
    base = get_base()
    if font_name not in base:
        logging.warn("unknown font: "+font_name)
        return None
    res = ''
    for char in s:
        res += _convert_char(char, font_name)
    return res