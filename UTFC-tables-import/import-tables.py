import csv

TABLE_CONTENT = {}

def get_table_content(fname, table_length):
    global TABLE_CONTENT
    if fname in TABLE_CONTENT:
        return TABLE_CONTENT[fname]
    with open('../UTFC/'+fname) as tblf:
        reslists = []
        reslist = []
        reslists.append(reslist)
        encodedunilist = tblf.read().replace('\n', '').split(' ')
        for encodedunichars in encodedunilist:
            unichars = ''
            while len(encodedunichars) > 3:
                unichars += str(chr(int(encodedunichars[:4], base=10)))
                encodedunichars = encodedunichars[4:]
            reslist.append(unichars)
            if len(reslist) >= table_length:
                reslist = []
                reslists.append(reslist)
        resdicts = []
        for reslist in reslists:
            resdict = {}
            for i, r in enumerate(reslist):
                nonunicp = i + 33
                noncpbytes = nonunicp.to_bytes(1, "big")
                try:
                    unistr = noncpbytes.decode("cp1252")
                    #print("decoding %d (%s) into %s (%s, %d)" % (nonunicp, noncpbytes.hex(), unistr, unistr.encode('utf16').hex()[4:], ord(unistr)))
                except UnicodeDecodeError:
                    continue
                resdict[ord(unistr)] = r
            resdicts.append(resdict)
        TABLE_CONTENT[fname] = resdicts
        return resdicts

with open('font-tables.csv', newline='') as csvfile:
    reader = csv.reader(csvfile, quotechar='"')
    for row in reader:
        global_table = get_table_content(row[1], int(row[3]))
        table = global_table[int(row[2])]
        for o, r in table.items():
           print("%s,%s,%s" % (row[0], o, r))
        #   continue
        
       