"""扫描角色对象里的技能配置指针（PVE/PVP 通用，未知 CFG 也打印）"""
import ctypes
import ctypes.wintypes as wt
import csv
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)

rows = list(csv.DictReader(open(r'G:/My/野蛮人大作战/work/buff_catalog.csv', encoding='utf-8-sig')))
NAME = {int(r['配置ID']): r['名称'] for r in rows}


def find_pid():
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
arr = (ctypes.c_void_p * 1024)(); need = wt.DWORD()
psapi.EnumProcessModulesEx(h, ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(need), 1)
mods = {}
for i in range(need.value // ctypes.sizeof(ctypes.c_void_p)):
    nm = ctypes.create_unicode_buffer(260)
    psapi.GetModuleBaseNameW(h, ctypes.c_void_p(arr[i]), nm, 260)
    mods[nm.value.lower()] = arr[i]


def rd(a, n):
    b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(g)) or g.value != n:
        return None
    return b.raw


p = int.from_bytes(rd(mods['libcocos2d.dll'] + 0xAAAEEC, 4), 'little')
for off in (0xB4, 0x2B8, 0x2B4, 0x2E4):
    p = int.from_bytes(rd(p + off, 4), 'little')
print('hero', hex(p))

data = bytearray()
for base in range(0, 0x10000, 0x1000):
    chunk = rd(p + base, 0x1000)
    if chunk:
        data += chunk
    else:
        data += b'\x00' * 0x1000
print('readable bytes', sum(1 for i in range(0, len(data), 0x1000) if data[i:i+16] != b'\x00'*16) * 0x1000)

hits = []
for off in range(0, len(data) - 8, 4):
    v = int.from_bytes(data[off:off + 4], 'little')
    if not (0x10000 < v < 0x7FFFFFFF):
        continue
    head = rd(v, 4)
    if not head:
        continue
    hv = int.from_bytes(head, 'little')
    if not (0x00400000 < hv < 0x7FFF0000):
        continue
    t = rd(v + 4, 4)
    if not t:
        continue
    cfg = int.from_bytes(t, 'little')
    if 100000000 <= cfg <= 999999999:
        hits.append((off, v, cfg))
    elif 10000 <= cfg <= 9999999:
        hits.append((off, v, cfg))

print('pointer hits', len(hits))
groups = []
cur = []
for off, v, cfg in hits:
    if cur and off - cur[-1][0] > 64:
        groups.append(cur); cur = []
    cur.append((off, v, cfg))
if cur:
    groups.append(cur)

for g in groups:
    if len(g) >= 1:
        print('group hero+0x%X  n=%d' % (g[0][0], len(g)))
        for off, v, cfg in g[:12]:
            print('   +0x%04X -> %08X  cfg=%d %s' % (off, v, cfg, NAME.get(cfg, '')))
