"""记录某个技能配置对象在内存中的引用位置，用于选卡前后差分定位槽位"""
import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
READABLE = {0x02, 0x04, 0x20, 0x40, 0x80, 0x08}
GUARD = 0x100


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wt.DWORD), ('RegionSize', ctypes.c_size_t),
                ('State', wt.DWORD), ('Protect', wt.DWORD), ('Type', wt.DWORD)]


pid = int(subprocess.check_output(['powershell', '-NoProfile', '-Command', "(Get-Process Wilds).Id"]).decode().strip())
h = k32.OpenProcess(0x0410, False, pid)


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


cfg = int(sys.argv[1]) if len(sys.argv) > 1 else 120160020
mode = sys.argv[2] if len(sys.argv) > 2 else 'before'
obj = find_obj(cfg)
print('cfg', cfg, 'object', hex(obj) if obj else 0)
if not obj:
    sys.exit(0)
lst = refs(obj)
print('refs', len(lst))
fn = 'work/refs_%d_%s.json' % (cfg, mode)
json.dump({'obj': obj, 'refs': lst}, open(fn, 'w'))
print('saved', fn)
if mode == 'after':
    before = json.load(open('work/refs_%d_before.json' % cfg))
    old = set(before['refs'])
    new = [x for x in lst if x not in old]
    print('new refs', len(new))
    for a in new[:20]:
        print('  NEW', hex(a))
        seg = rd(a - 32, 128)
        for o in range(0, len(seg), 16):
            print('    %08X  %s' % (a - 32 + o, seg[o:o + 16].hex(' ')))
