import re

RES_PATT = re.compile(r"\\f2\\fs48([^\\]+)\\f\d+\\f1\\fs48(\\u\d+ )+\\par")

with open("testrtf-attu_UNI.rtf") as f:
	s = f.read()
	for m in RES_PATT.finditer(s):
		unires = ""
		fontinf = ""
		for i, g in enumerate(m.groups()):
			if i == 0:
				fontinf = g
				continue
			unii = int(g[2:-1])
			if unii == 65533:
				unires = "༠༠༠༠"
			elif unii < 32 or (unii > 126 and unii < 160):
				unires = ""
			else:
				unires += str(chr(unii))
		if fontinf and unires:
			print(fontinf+unires)