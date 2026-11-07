import ctypes, ctypes.wintypes as wt, sys, csv, time
import numpy as np

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)
READABLE = {0x02, 0x04, 0x20, 0x40, 0x80, 0x08}
PAGE_GUARD = 0x100


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wt.DWORD), ('RegionSize', ctypes.c_size_t),
                ('State', wt.DWORD), ('Protect', wt.DWORD), ('Type', wt.DWORD)]


pid = int(sys.argv[1]) if len(sys.argv) > 1 else 33128
gap = int(sys.argv[2]) if len(sys.argv) > 2 else 16  # ints (~64 bytes)
ids = []
for r in csv.DictReader(open(r'G:/My/野蛮人大作战/work/buff_catalog.csv', encoding='utf-8-sig')):
    ids.append(int(r['技能ID']))
ids = np.array(sorted(set(ids)), dtype=np.int32)

h = k32.OpenProcess(0x0410, False, pid)
mbi = MBI(); addr = 0; clusters = []; scanned = 0; t0 = time.time()
while addr < 0x7FFFFFFF:
    if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        break
    base, size = mbi.BaseAddress or 0, mbi.RegionSize
    if (mbi.State == 0x1000 and (mbi.Protect & 0xFF) in READABLE
            and not (mbi.Protect & PAGE_GUARD) and 0x1000 <= size <= 0x4000000):
        buf = ctypes.create_string_buffer(size); got = ctypes.c_size_t()
        if k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size, ctypes.byref(got)) and got.value >= 4:
            data = buf.raw[:got.value]
            arr = np.frombuffer(data[:len(data) // 4 * 4], dtype='<i4')
            mask = np.isin(arr, ids)
            idx = np.nonzero(mask)[0]
            scanned += len(data)
            if len(idx) >= 2:
                start = 0
                for k in range(1, len(idx) + 1):
                    if k == len(idx) or idx[k] - idx[k - 1] > gap:
                        grp = idx[start:k]
                        if len(grp) >= 2:
                            clusters.append((base + int(grp[0]) * 4,
                                             [int(arr[g]) for g in grp]))
                        start = k
    addr = base + size

print('扫描 %.0f MB, 用时 %.1fs, 聚集区 %d' % (scanned / 1048576, time.time() - t0, len(clusters)))
clusters.sort(key=lambda c: -len(c[1]))
for a, vals in clusters[:30]:
    print(hex(a), len(vals), vals[:14])
