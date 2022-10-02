import re

RES_PATT = re.compile(r"\\f2\\fs48([^\\]+)\\f\d+\\f1\\fs48(\\u\d+ )+\\par")

def normalize(s):
	s = s.replace("\u0F00", "\u0F68\u0F7C\u0F7E").replace("གྷ", "གྷ")
	s = s.replace("\u0f43", "\u0f42\u0fb7")
	s = s.replace("\u0f4d", "\u0f4c\u0fb7")
	s = s.replace("\u0f52", "\u0f51\u0fb7")
	s = s.replace("\u0f57", "\u0f56\u0fb7")
	s = s.replace("\u0f5c", "\u0f5b\u0fb7")
	s = s.replace("\u0f69", "\u0f40\u0fb5")
	s = s.replace("\u0f73", "\u0f71\u0f72")
	s = s.replace("\u0f75", "\u0f71\u0f74")
	s = s.replace("\u0f76", "\u0fb2\u0f80")
	s = s.replace("\u0f77", "\u0fb2\u0f71\u0f80")
	s = s.replace("\u0f78", "\u0fb3\u0f80")
	s = s.replace("\u0f79", "\u0fb3\u0f71\u0f80")
	s = s.replace("\u0f81", "\u0f71\u0f80")
	s = s.replace("\u0f93", "\u0f92\u0fb7")
	s = s.replace("\u0f9d", "\u0f9c\u0fb7")
	s = s.replace("\u0fa2", "\u0fa1\u0fb7")
	s = s.replace("\u0fa7", "\u0fa6\u0fb7")
	s = s.replace("\u0fac", "\u0fab\u0fb7")
	s = s.replace("\u0fb9", "\u0f90\u0fb5")
	s = s.replace("\u0f6a\u0fb3", "\u0f62\u0fb3")
	return s

with open("allchars-attu_UNI.rtf") as f:
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
			print(fontinf+normalize(unires))