# Import of font conversion tables from other softwares

### UTFC

UTFC's code is [available on Github](https://github.com/tracefoundation/UTFC/) but we were unfortunately unable to get the C code to work. The tables are not easy to extract from the code but in order to do it:

```sh
git clone "https://github.com/tracefoundation/UTFC.git"
python3 import-utfc-tables.py > "../font-tables/utfc.csv"
```

### UDP

The UDP tables are part of the source code but are even more difficult to extract. Since UDP runs well, we can generate an RDF file with all possible characters:

```sh
python3 create_all_chars_rtf.py
```

Then open the file `allchars-udp.rtf` in UDP, and save it in Unicode TXT format. This will give you the font conversion table in the right format (after a minimal cleanup).

### ATTU

For ATTU we use the same technique, first generate an RTF file with:

```sh
python3 create_all_chars_rtf.py
```

Then convert it with ATTU, for instance under Linux:

```sh
wine Attu.exe -b -f "Noto Sans Tibetan" -O 'allchars-attu.rtf'
```

And then run

```sh
python3 parse_uni_rtf.py > "../font-tables/attu.csv"
```