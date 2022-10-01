# Python Tibetan Legacy Encodings tool

Python script to convert PDFs using non-Unicode Tibetan fonts in Unicode text.

The code is work in progress, use at your own risk!

The conversion tables come from a [previous work for InDesign](https://github.com/eroux/tibetan-unicode-scripts/). The font tables from [UTFC](https://github.com/tracefoundation/UTFC/) have been [extracted](UTFC-tables-import/) and kept in a [separate file](utfc-font-data.csv). In debug mode, the code indicates where the two tables diverge and fixes are made over time to the non-UTFC tables.

If you have PDFs you would like to convert in the best quality, please send it to help AT bdrc.io, it will be converted and reviewed.

The code has a `region` argument that specified PDF coordinates of the text to convert on each page; use it to remove headers, footer and marginal content.

### Supported fonts

The supported fonts (combining all the conversion tables) are:

- Tibetisch dBu-can
- DBu-can
- Youtsoweb (TCRC)
- Youtso (TCRC)
- Bod-Yig (TCRC)
- Ededris
- Dedris
- Esama
- LTibetan and LMantra
- TibetanMachine
- TibetanMachineWeb
- TibetanMachineSkt
- TibetanChogyal (PKTC)
- TibetanClassic (PKTC)
