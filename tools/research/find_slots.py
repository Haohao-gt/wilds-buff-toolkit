"""列出某个技能配置对象的所有引用簇，帮助定位已拥有技能槽位"""
import ctypes
import ctypes.wintypes as wt
import csv
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
k32 = ctypes.WinDLL('kernel32')
READABLE = {0x02, 0x04, 0x20, 0x40, 0x80, 0x08}
GUARD = 0x100


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wt.DWORD), ('RegionSize', ctypes.c_size_t),
                ('State', wt.DWORD), ('Protect', wt.DWORD), ('Type', wt.DWORD)]


pid = int(subprocess.check_output(['powershell', '-NoProfile', '-Command', "(Get-Process Wilds).Id"]).decode().strip())
h = k32.OpenProcess(0x0410, False, pid)

rows = list(csv.DictReader(open('work/buff_catalog.csv', encoding='utf-8-sig')))
NAME = {int(r['配置ID']): r['名称'] for r in rows}
NAME.update({int(r['技能ID']): r['名称'] for r in rows})


def rd(a, n):
    b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(g)) or g.value != n:
        return b''
    return b.raw


def regions():
    mbi = MBI(); addr = 0
    while addr < 0x7FFF0000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        base = mbi.BaseAddress or 0; size = mbi.RegionSize
        if size <= 0:
            break
        if (mbi.State == 0x1000 and (mbi.Protect & 0xFF) in READABLE
                and not (mbi.Protect & GUARD) and 0x1000 <= size <= 0x4000000):
            yield base, size
        addr = base + size


def find_obj(cfg):
    pat = cfg.to_bytes(4, 'little')
    for base, size in regions():
        d = rd(base, size)
        if not d:
            continue
        s = 0
        while True:
            i = d.find(pat, s)
            if i < 0:
                break
            s = i + 1
            if i < 4:
                continue
            head = int.from_bytes(d[i - 4:i], 'little')
            if 0x00400000 < head < 0x7FFF0000:
                return base + i - 4
    return 0


def refs(ptr):
    pat = ptr.to_bytes(4, 'little')
    out = []
    for base, size in regions():
        d = rd(base, size)
        if not d:
            continue
        s = 0
        while True:
            i = d.find(pat, s)
            if i < 0:
                break
            out.append(base + i)
            s = i + 1
    return out


target = int(sys.argv[1]) if len(sys.argv) > 1 else 120160020
obj = find_obj(target)
print('target cfg', target, NAME.get(target, ''), 'object', hex(obj) if obj else 0)
if not obj:
    sys.exit(0)
lst = sorted(refs(obj))
print('refs', len(lst))

groups = []
cur = []
for a in lst:
    if cur and a - cur[-1] > 0x30:
        groups.append(cur); cur = []
    cur.append(a)
if cur:
    groups.append(cur)

for g in groups:
    first = g[0]
    seg = rd(first - 0x20, 0x60)
    print('--- group @ %08X  n=%d' % (first, len(g)))
    for o in range(0, len(seg), 16):
        vals = [int.from_bytes(seg[o + i:o + i + 4], 'little') for i in (0, 4, 8, 12)]
        desc = []
        for v in vals:
            t = rd(v + 4, 4) if 0x10000 < v < 0x7FFFFFFF else b''
            if t:
                cfg = int.from_bytes(t, 'little')
                if cfg in NAME:
                    desc.append(NAME[cfg])
        print('   %08X  %s   %s' % (first - 0x20 + o, seg[o:o + 16].hex(' '), ' '.join(desc)))
