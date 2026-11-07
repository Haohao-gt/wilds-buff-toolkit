"""试验：把疑似技能槽位里的「吸血」替换成「磁铁5级」"""
import ctypes
import ctypes.wintypes as wt
import json
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
h = k32.OpenProcess(0x1F0FFF, False, pid)


def rd(a, n):
    b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(g)) or g.value != n:
        return b''
    return b.raw


def wr(a, data):
    old = wt.DWORD()
    k32.VirtualProtectEx(h, ctypes.c_void_p(a), len(data), 0x40, ctypes.byref(old))
    g = ctypes.c_size_t()
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(a), data, len(data), ctypes.byref(g))
    k32.VirtualProtectEx(h, ctypes.c_void_p(a), len(data), old, ctypes.byref(old))
    return ok


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


TARGET = 120410020  # 磁铁lv5
SLOTS = [0x26CDE058, 0x26CE4748]

if len(sys.argv) > 1 and sys.argv[1] == 'restore':
    data = json.load(open('work/slot_backup.json'))
    for a, hx in data.items():
        print('restore', a, wr(int(a, 16), bytes.fromhex(hx)))
    sys.exit(0)

obj = find_obj(TARGET)
print('磁铁lv5 object', hex(obj) if obj else 0)
if not obj:
    sys.exit(0)

backup = {}
for a in SLOTS:
    cur = rd(a, 16)
    if not cur:
        print('slot unreadable', hex(a)); continue
    backup[str(a)] = cur.hex()
    print('slot', hex(a), cur.hex(' '))
    new = obj.to_bytes(4, 'little') + cur[4:]
    print(' write', wr(a, new), '->', rd(a, 16).hex(' '))
json.dump(backup, open('work/slot_backup.json', 'w'))
print('backup saved')
