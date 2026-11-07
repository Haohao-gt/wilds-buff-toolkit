import sys, zlib, os, json

src = r"C:/Program Files/4399野蛮人大作战/packages/final/pc/asset.vfs"
outdir = r"G:/My/野蛮人大作战/work/tables"
os.makedirs(outdir, exist_ok=True)
d = open(src, 'rb').read()
n = len(d)
i = 0
saved = 0
ok = 0
manifest = []
textchars = set(range(32, 127)) | {9, 10, 13}
while True:
    i = d.find(b'\x78', i)
    if i < 0:
        break
    if i + 2 < n and d[i+1] in (0x01, 0x5e, 0x9c, 0xda):
        try:
            o = zlib.decompressobj(15 + 32)
            out = o.decompress(d[i:i+4_000_000], 32*1024*1024)
        except Exception:
            out = b''
        if out:
            ok += 1
            head = out[:4000]
            printable = sum(1 for b in head if b in textchars)
            ratio = printable / max(1, len(head))
            if ratio > 0.9 and out[:1].isdigit() and b' ' in head[:200]:
                fn = os.path.join(outdir, 'tbl_%08x.txt' % i)
                with open(fn, 'wb') as f:
                    f.write(out)
                manifest.append((hex(i), len(out), out[:60].decode('utf-8', 'replace')))
                saved += 1
                if saved % 50 == 0:
                    print('saved', saved, 'at', hex(i), flush=True)
    i += 1
print('done ok=%d saved=%d' % (ok, saved))
with open(os.path.join(outdir, '_manifest.json'), 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=1)
