"""通过两个已拥有技能（攻击力UP/生命UP）反查技能槽数组"""
import ctypes
import ctypes.wintypes as wt
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
READABLE = {0x02, 0x04, 0x20, 0x40, 0x80, 0x08}
GUARD = 0x100


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wt.DWORD), ('RegionSize', ctypes.c_size_t),
                ('State', wt.DWORD), ('Protect', wt.DWORD), ('Type', wt.DWORD)]


def find_pid():
    psapi = ctypes.WinDLL('psapi')
    arr = (wt.DWORD * 4096)(); need = wt.DWORD()
    psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(need))
    for i in range(need.value // 4):
        pid = arr[i]
        if not pid:
            continue
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            continue
        buf = ctypes.create_unicode_buffer(1024); n = wt.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) and buf.value.lower().endswith('\\wilds.exe'):
            k32.CloseHandle(h); return pid
        k32.CloseHandle(h)
    return 0


pid = find_pid()
h = k32.OpenProcess(0x0410, False, pid)


def rd(a, n):
    b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(g)) or g.value != n:
        return None
    return b.raw


TARGETS = {254440020: '攻击力UP', 254450020: '血量UP'}
objs = {k: [] for k in TARGETS}
regions = []
mbi = MBI(); addr = 0
while addr < 0x7FFF0000:
    if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        break
    base = mbi.BaseAddress or 0
    size = mbi.RegionSize
    if size <= 0:
        break
    if mbi.State == 0x1000 and (mbi.Protect & 0xFF) in READABLE and not (mbi.Protect & GUARD) and 0x1000 <= size <= 0x4000000:
        regions.append((base, size))
    addr = base + size

print('regions', len(regions))
for base, size in regions:
    data = rd(base, size)
    if not data:
        continue
    for cfg in TARGETS:
        pat = cfg.to_bytes(4, 'little')
        start = 0
        while True:
            i = data.find(pat, start)
            if i < 0:
                break
            start = i + 1
            if i < 4:
                continue
            head = int.from_bytes(data[i - 4:i], 'little')
            if 0x00400000 < head < 0x7FFF0000:
                objs[cfg].append(base + i - 4)

for k, v in objs.items():
    print(TARGETS[k], 'objects:', [hex(x) for x in v[:5]], 'count', len(v))

p1 = objs[254440020][0] if objs[254440020] else 0
p2 = objs[254450020][0] if objs[254450020] else 0
print('p1', hex(p1), 'p2', hex(p2))
if p1 and p2:
    b1 = p1.to_bytes(4, 'little'); b2 = p2.to_bytes(4, 'little')
    for base, size in regions:
        data = rd(base, size)
        if not data:
            continue
        i1 = data.find(b1); i2 = data.find(b2)
        if i1 >= 0 and i2 >= 0 and abs(i1 - i2) < 0x400:
            print('HIT region', hex(base), 'offsets', hex(i1), hex(i2), 'delta', i1 - i2)
            lo = max(0, min(i1, i2) - 64)
            seg = data[lo:lo + 320]
            for o in range(0, len(seg), 16):
                print('  %08X  %s' % (base + lo + o, seg[o:o + 16].hex(' ')))
            break
