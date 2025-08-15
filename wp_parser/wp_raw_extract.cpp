/*
  Attempt-raw extractor using libwpd-0.10 + librevenge-0.0.

  Build:
    cd /home/eroux/BUDA/softs/pydeduff/wp_parser
    make

  Usage:
    ./wp_raw_extract file.wpd

  Behavior:
  - Calls libwpd::WPDocument::parse with a custom librevenge::RVNGTextInterface that
    collects decoded text runs (as provided by libwpd).
  - For each decoded run, attempts to find the exact byte sequence in the original file
    (best-effort). If found, prints offset and the original bytes in hex.
  - If not found, prints the UTF-8 bytes in hex and marks them as fallback.

  If compilation fails due to RVNGTextInterface method signature differences, adapt the
  overridden method(s) in TextCollector to the signatures in your installed librevenge headers.
*/

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <iostream>
#include <iomanip>
#include <cctype>

#include <librevenge/librevenge.h>
#include <libwpd-0.10/libwpd/WPDocument.h>
#include <librevenge-stream/librevenge-stream.h>
#include <librevenge-stream/librevenge-stream.h> // For RVNGFileInputStream

using namespace std;

// Helper: print byte buffer as hex
static void print_hex_bytes(const unsigned char *buf, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        if (i) putchar(' ');
        printf("%02x", buf[i]);
    }
    putchar('\n');
}

// Find all occurrences of needle in haystack
static vector<size_t> find_all_occurrences(const vector<unsigned char> &haystack,
                                           const vector<unsigned char> &needle) {
    vector<size_t> res;
    if (needle.empty() || haystack.size() < needle.size()) return res;
    for (size_t i = 0; i + needle.size() <= haystack.size(); ++i) {
        if (memcmp(haystack.data() + i, needle.data(), needle.size()) == 0) {
            res.push_back(i);
        }
    }
    return res;
}

// In TextCollector: add a flag and emit a single warning when name lookup fails.
class TextCollector : public librevenge::RVNGTextInterface {
public:
    std::vector<std::string> runs;
    std::vector<std::string> fonts;      // parallel vector: fonts[i] is font for runs[i]
    std::string current_font;            // current font label
    unsigned int font_counter = 0;
    const std::vector<unsigned char> *m_filebuf;
    librevenge::RVNGInputStream *m_instream;
    bool font_name_found_any = false;    // true if we discovered any real font name
    bool font_name_warning_emitted = false; // emit warning only once

    TextCollector(const std::vector<unsigned char> *filebuf = nullptr,
                  librevenge::RVNGInputStream *instream = nullptr)
        : current_font("default"), m_filebuf(filebuf), m_instream(instream),
          font_name_found_any(false), font_name_warning_emitted(false) {}

    // Helper to push text with current font
    void pushRun(const std::string &s) {
        runs.emplace_back(s);
        fonts.emplace_back(current_font);
    }

    // Helper: fetch a string property from RVNGPropertyList by key
    std::string getPropString(const librevenge::RVNGPropertyList &pl, const char *key) {
        const librevenge::RVNGProperty *p = pl[key];
        if (!p) return std::string();
        try {
            librevenge::RVNGString s = p->getStr();
            const char *c = s.cstr();
            unsigned long sz = s.size();
            if (c && sz) return std::string(c, c + sz);
            if (c) return std::string(c);
        } catch(...) {}
        return std::string();
    }

    // Try to extract a font name from a property list (returns empty if none)
    std::string extractFontNameFromProps(const librevenge::RVNGPropertyList &pl) {
        // List of candidate property keys commonly used for font names
        const char *candidates[] = {
            "font", "fontname", "Name", "FaceName", "PostScriptName", "Family", "typeface", "typefaceName", nullptr
        };
        for (const char **kp = candidates; *kp; ++kp) {
            std::string v = getPropString(pl, *kp);
            if (!v.empty()) return v;
        }

        // Fallback: inspect the textual representation of the whole property list
        try {
            librevenge::RVNGString ps = pl.getPropString();
            const char *p = ps.cstr();
            unsigned long psz = ps.size();
            if (p && psz) {
                std::string s(p, p + psz);
                // look for "font-name:" or "style:font-name:"
                const char *keys[] = {"font-name:", "style:font-name:", nullptr};
                for (const char **k = keys; *k; ++k) {
                    size_t pos = s.find(*k);
                    if (pos != std::string::npos) {
                        pos += strlen(*k);
                        // skip spaces
                        while (pos < s.size() && std::isspace((unsigned char)s[pos])) ++pos;
                        // capture until comma, semicolon, parenthesis, or newline
                        size_t end = pos;
                        while (end < s.size() && s[end] != ',' && s[end] != ';' && s[end] != ')' && s[end] != '\n') ++end;
                        // trim trailing spaces
                        while (end > pos && std::isspace((unsigned char)s[end-1])) --end;
                        if (end > pos) {
                            std::string name = s.substr(pos, end - pos);
                            // Remove trailing words like "Normal" if you want only family; keep full name for now
                            // trim both ends
                            size_t a = 0; while (a < name.size() && std::isspace((unsigned char)name[a])) ++a;
                            size_t b = name.size(); while (b > a && std::isspace((unsigned char)name[b-1])) --b;
                            if (b > a) return name.substr(a, b - a);
                        }
                    }
                }
            }
        } catch(...) {}

        return std::string();
    }

    // Document lifecycle / metadata
    virtual void setDocumentMetaData(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void startDocument(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void endDocument() override {}

    // Page / header / footer / styles
    virtual void definePageStyle(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void defineEmbeddedFont(const librevenge::RVNGPropertyList &propList) override {
        ++font_counter;
        std::string name = extractFontNameFromProps(propList);
        if (!name.empty()) {
            current_font = name;
            font_name_found_any = true;
        } else {
            current_font = std::string("font") + std::to_string(font_counter);
            if (!font_name_warning_emitted) {
                fprintf(stderr, "Warning: libwpd did not provide a font name in properties; using generic labels.\n");
                font_name_warning_emitted = true;
            }
        }
    }
    virtual void openPageSpan(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closePageSpan() override {}
    virtual void openHeader(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeHeader() override {}
    virtual void openFooter(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeFooter() override {}
    virtual void defineParagraphStyle(const librevenge::RVNGPropertyList & /*propList*/) override {}

    // Paragraph / spans / character styles
    virtual void openParagraph(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeParagraph() override {}
    virtual void defineCharacterStyle(const librevenge::RVNGPropertyList &propList) override {
        ++font_counter;
        std::string name = extractFontNameFromProps(propList);
        if (!name.empty()) {
            current_font = name;
            font_name_found_any = true;
        } else {
            current_font = std::string("font") + std::to_string(font_counter);
            if (!font_name_warning_emitted) {
                fprintf(stderr, "Warning: libwpd did not provide a font name in properties; using generic labels.\n");
                font_name_warning_emitted = true;
            }
        }
    }
    virtual void openSpan(const librevenge::RVNGPropertyList &propList) override {
        ++font_counter;
        std::string name = extractFontNameFromProps(propList);
        if (!name.empty()) {
            current_font = name;
            font_name_found_any = true;
        } else {
            current_font = std::string("font") + std::to_string(font_counter);
            if (!font_name_warning_emitted) {
                fprintf(stderr, "Warning: libwpd did not provide a font name in properties; using generic labels.\n");
                font_name_warning_emitted = true;
            }
        }
    }
    virtual void closeSpan() override {}

    // Links / sections
    virtual void openLink(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeLink() override {}
    virtual void defineSectionStyle(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void openSection(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeSection() override {}

    // Tabs / spaces / text insertion
    virtual void insertTab() override { pushRun("\t"); }
    virtual void insertSpace() override { pushRun(" "); }

    // Core: insertText receives RVNGString; use cstr()/size() to obtain bytes.
    virtual void insertText(const librevenge::RVNGString &text) override {
        const char *p = text.cstr();
        unsigned long sz = text.size();
        if (p && sz) {
            pushRun(std::string(p, p + sz));
        } else if (p) {
            pushRun(std::string(p));
        }
    }

    virtual void insertLineBreak() override { pushRun("\n"); }
    virtual void insertField(const librevenge::RVNGPropertyList & /*propList*/) override {}

    // Lists
    virtual void openOrderedListLevel(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void openUnorderedListLevel(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeOrderedListLevel() override {}
    virtual void closeUnorderedListLevel() override {}
    virtual void openListElement(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeListElement() override {}

    // Footnotes / endnotes / comments / text boxes
    virtual void openFootnote(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeFootnote() override {}
    virtual void openEndnote(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeEndnote() override {}
    virtual void openComment(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeComment() override {}
    virtual void openTextBox(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeTextBox() override {}

    // Tables
    virtual void openTable(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void openTableRow(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeTableRow() override {}
    virtual void openTableCell(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeTableCell() override {}
    virtual void insertCoveredTableCell(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeTable() override {}

    // Frames / drawing / binary objects / equations
    virtual void openFrame(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeFrame() override {}
    virtual void insertBinaryObject(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void insertEquation(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void openGroup(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void closeGroup() override {}
    virtual void defineGraphicStyle(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void drawRectangle(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void drawEllipse(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void drawPolygon(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void drawPolyline(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void drawPath(const librevenge::RVNGPropertyList & /*propList*/) override {}
    virtual void drawConnector(const librevenge::RVNGPropertyList & /*propList*/) override {}
};

// Small concrete RVNGInputStream that reads the entire file into memory and
// implements the virtual API required by librevenge.
class RVNGFileInputStream : public librevenge::RVNGInputStream {
private:
    std::vector<unsigned char> m_buf;
    unsigned long m_pos;
public:
    RVNGFileInputStream(const char *path) : m_pos(0) {
        if (!path) return;
        FILE *f = fopen(path, "rb");
        if (!f) return;
        if (fseek(f, 0, SEEK_END) == 0) {
            long sz = ftell(f);
            if (sz > 0) {
                rewind(f);
                m_buf.resize((size_t)sz);
                size_t got = fread(m_buf.data(), 1, (size_t)sz, f);
                m_buf.resize(got);
            }
        }
        fclose(f);
    }
    virtual ~RVNGFileInputStream() {}

    virtual bool isStructured() override { return false; }
    virtual unsigned subStreamCount() override { return 0; }
    virtual const char *subStreamName(unsigned /*id*/) override { return nullptr; }
    virtual bool existsSubStream(const char * /*name*/) override { return false; }
    virtual RVNGInputStream *getSubStreamByName(const char * /*name*/) override { return nullptr; }
    virtual RVNGInputStream *getSubStreamById(unsigned /*id*/) override { return nullptr; }

    virtual const unsigned char *read(unsigned long numBytes, unsigned long &numBytesRead) override {
        if (m_pos >= m_buf.size()) { numBytesRead = 0; return nullptr; }
        unsigned long rem = (unsigned long)(m_buf.size() - m_pos);
        numBytesRead = (numBytes > rem) ? rem : numBytes;
        const unsigned char *ptr = m_buf.data() + m_pos;
        m_pos += numBytesRead;
        return ptr;
    }

    // Use the namespace-qualified seek type and enum values so the signature matches the header.
    virtual int seek(long offset, librevenge::RVNG_SEEK_TYPE seekType) override {
        long newpos = 0;
        if (seekType == librevenge::RVNG_SEEK_SET) newpos = offset;
        else if (seekType == librevenge::RVNG_SEEK_CUR) newpos = (long)m_pos + offset;
        else return -1;
        if (newpos < 0 || (size_t)newpos > m_buf.size()) return -1;
        m_pos = (unsigned long)newpos;
        return 0;
    }

    virtual long tell() override { return (long)m_pos; }
    virtual bool isEnd() override { return m_pos >= m_buf.size(); }
};

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <file.wpd>\n", argv[0]);
        return 2;
    }
    const char *path = argv[1];

    // Read entire file into memory for raw-byte searches
    FILE *f = fopen(path, "rb");
    if (!f) { perror("fopen"); return 2; }
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return 2; }
    long sz = ftell(f);
    if (sz < 0) { fclose(f); return 2; }
    rewind(f);
    vector<unsigned char> filebuf(sz ? sz : 1);
    size_t got = fread(filebuf.data(), 1, sz, f);
    fclose(f);
    filebuf.resize(got);

    // Wrap the file in a librevenge input stream
    librevenge::RVNGInputStream *instream = new RVNGFileInputStream(path);

    // Check if libwpd thinks the file format is supported
    if (instream) {
        libwpd::WPDConfidence conf = libwpd::WPDocument::isFileFormatSupported(instream);
        if (conf == libwpd::WPD_CONFIDENCE_NONE) {
            // Not recognized as WPD document; continue but warn
            fprintf(stderr, "Warning: libwpd reports WPD_CONFIDENCE_NONE for this input.\n");
        }
    }

    // Prepare text collector and call parse
    TextCollector collector(&filebuf, instream);
    libwpd::WPDResult res = libwpd::WPDocument::parse(instream, &collector, nullptr);
    // Note: WPDocument::parse returns WPDResult; check for errors and continue with whatever we got.
    if (res != libwpd::WPD_OK) {
        fprintf(stderr, "libwpd::WPDocument::parse returned %d (continuing with collected runs)\n", (int)res);
    }

    // If no real font names were discovered, emit one non-blocking warning (if not already emitted)
    if (!collector.font_name_found_any && !collector.font_name_warning_emitted) {
        fprintf(stderr, "Note: no font names were discovered by libwpd; output uses generic labels.\n");
    }

    // If no runs were collected via libwpd, do nothing (no heuristic fallback).
    if (collector.runs.empty()) {
        if (instream) delete instream;
        return 0;
    }

    // For each decoded run, attempt to locate its original bytes in the file buffer.
    for (size_t idx = 0; idx < collector.runs.size(); ++idx) {
        const string &run = collector.runs[idx];
        const string &font_label = (idx < collector.fonts.size()) ? collector.fonts[idx] : std::string("unknown");
        // Skip runs that are just whitespace or too short (avoid printing every single-space)
        if (run.size() < 2) continue;
        bool all_ws = true;
        for (unsigned char ch : run) {
            if (!std::isspace(ch)) { all_ws = false; break; }
        }
        if (all_ws) continue;

        // Candidate encodings: Latin1 (byte-equal), UTF-8 bytes of run
        vector<unsigned char> cand_latin1;
        for (unsigned char ch : run) cand_latin1.push_back((unsigned char)ch);
        vector<unsigned char> cand_utf8(run.begin(), run.end());

        bool printed = false;
        // Try latin1 first (one-to-one mapping)
        auto occ = find_all_occurrences(filebuf, cand_latin1);
        if (!occ.empty()) {
            for (size_t pos : occ) {
                printf("%08zx: ", pos);
                for (size_t j = 0; j < cand_latin1.size(); ++j) {
                    if (j) putchar(' ');
                    printf("%02x", cand_latin1[j]);
                }
                printf(" [font:%s]\n", font_label.c_str());
            }
            printed = true;
        } else {
            // Try UTF-8
            occ = find_all_occurrences(filebuf, cand_utf8);
            if (!occ.empty()) {
                for (size_t pos : occ) {
                    printf("%08zx: ", pos);
                    for (size_t j = 0; j < cand_utf8.size(); ++j) {
                        if (j) putchar(' ');
                        printf("%02x", cand_utf8[j]);
                    }
                    printf(" [font:%s]\n", font_label.c_str());
                }
                printed = true;
            }
        }
        if (!printed) {
            // Not found: output fallback (decoded UTF-8 bytes) with marker
            printf("----------: ");
            for (size_t j = 0; j < (size_t)run.size(); ++j) {
                if (j) putchar(' ');
                printf("%02x", (unsigned char)run[j]);
            }
            printf(" [font:%s]\n", font_label.c_str());
        }
    }

    if (instream) delete instream;
    return 0;
}