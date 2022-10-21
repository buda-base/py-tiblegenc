# Python Tibetan Legacy Encodings tool

Python script to convert PDFs using non-Unicode Tibetan fonts in Unicode text.

The code is work in progress, use at your own risk!

The conversion tables come from a [previous work for InDesign](https://github.com/eroux/tibetan-unicode-scripts/). The font tables from [UTFC](https://github.com/tracefoundation/UTFC/), [UDP](http://udp.leighb.com/index.html) and [ATTU](http://www.pechamaker.com/attu/) have been [extracted](font-tables-import/) and kept in [separate files](font-tables/). In debug mode, the code indicates where the two tables diverge and fixes are made over time to the non-UTFC tables.

If you have PDFs you would like to convert in the best quality, please send it to help AT bdrc.io, it will be converted and reviewed.

The code has a `region` argument that specified PDF coordinates of the text to convert on each page; use it to remove headers, footer and marginal content.

### Acknowledgement

We want to thank:
- Daniel Coppo for the initial inspiration in 2010
- the Padmakara Translation Committee for the review of the TibetanChogyal tables
- Leigh Brasington for the UDP software, his authorization to use the data from UDP and his precious help
- the Trace Foundation, Tashi Tsering and Nyima Droma for the UTFC software
- Frederick Johnson for the ATTU software

### Supported fonts

The supported fonts (combining all the conversion tables) are:

- Tibetisch dBu-can
- DBu-can
- Youtsoweb (TCRC)
- Youtso (TCRC)
- Bod-Yig (TCRC)
- Ededris
- Dedris
- Drutsa
- Khamdris
- Sama / Esama
- LTibetan, LTibetanExtension and LMantra
- TibetanMachine
- TibetanMachineWeb
- TibetanMachineSkt
- TibetanChogyal (PKTC)
- TibetanClassic (PKTC)
- DzongkhaCalligraphic (PKTC)
- TB-Youtso, TB-TTYoutso, TB2-Youtso, TB2-TTYoutso (LTWA)
- Monlam ouchan and Monlam yigchong

### Caveats

##### First version of the Tibetan Machine Web encoding

The Tibetan Machine Web fonts have two different encodings:
- the first version was only used for PKTC's plugin to WordPerfect
- the second is the most common one and the only one handled by this code

They can be differenciated by looking at the encoding of the tsheg: if it corresponds to the ANSI hyphen (0x2D, decimal 45) it's the second encoding, else it's the first one.

We want to thank Leigh Brasington for this information.