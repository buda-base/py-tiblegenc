import csv
import logging

BASE = None
ERROR_CHR = "༠༠༠༠"

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
    "TibetanClassicSkt": "TibetanClassicSkt1",
    "TibetanChogyalSkt": "TibetanChogyalSkt1",
}

def convert_char(char, font_name):
    if font_name in FONT_ALIASES:
        font_name = FONT_ALIASES[font_name]
    if font_name.startswith("Dedris"):
        font_name = "Ed"+font_name[1:]
    base = get_base()
    if font_name not in base:
        logging.warn("unknown font: "+font_name)
        return None

def _convert_car(char, font_name):
    base = get_base()
    if char == "\u00a0":
        char = " "
    if char not in base[font_name]:
        logging.error("unknown character: '%s' (%d) in %s" % (char, ord(char), font_name))
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
    base = get_base()
    if font_name not in base:
        logging.warn("unknown font: "+font_name)
        return None
    res = ''
    for char in s:
        res += _convert_car(char, font_name)
    return res