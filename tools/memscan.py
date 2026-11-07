import ctypes, ctypes.wintypes as wt, sys, struct, time

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
READABLE = {0x02, 0x04, 0x20, 0x40, 0x80, 0x08}  # RO, RW, EXEC_R, EXEC_RW, EXEC_W, WC

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wt.DWORD), ('RegionSize', ctypes.c_size_t),
                ('State', wt.DWORD), ('Protect', wt.DWORD), ('Type', wt.DWORD)]

def open_proc(pid):
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        raise OSError(ctypes.get_last_error(), 'OpenProcess failed')
    return h

def regions(h):
    addr = 0
    mbi = MEMORY_BASIC_INFORMATION()
    mbi_size = ctypes.sizeof(mbi)
    max_addr = 0x7FFFFFFF
    while addr < max_addr:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), mbi_size):
            break
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        if mbi.State == MEM_COMMIT and (mbi.Protect & 0xFF) in READABLE and not (mbi.Protect & PAGE_GUARD):
            yield base, size, mbi.Protect
        addr = base + size
        if size == 0:
            addr += 0x1000

def read(h, base, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t(0)
    if k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size, ctypes.byref(got)):
        return buf.raw[:got.value]
    return None

def modules(h):
    arr = (ctypes.c_void_p * 1024)()
    needed = wt.DWORD(0)
    # 32-bit target from 64-bit scanner: LIST_MODULES_32BIT = 1
    if not psapi.EnumProcessModulesEx(h, ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(needed), 1):
        return []
    n = needed.value // ctypes.sizeof(ctypes.c_void_p)
    out = []
    for i in range(n):
        hmod = arr[i]
        name = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(h, ctypes.c_void_p(hmod), name, 260)
        out.append((hmod, name.value))
    return out

def main():
    pid = int(sys.argv[1])
    targets = [int(x, 0) for x in sys.argv[2:]]
    h = open_proc(pid)
    mods = modules(h)
    print('modules:', [(hex(b), n) for b, n in mods[:6]], '...', len(mods))
    # module ranges for attribution
    mod_ranges = []
    for b, n in mods:
        mod_ranges.append((b, n))
    hits = {}
    scanned = 0
    t0 = time.time()
    for base, size, prot in regions(h):
        if size > 0x4000000:
            continue
        data = read(h, base, size)
        if not data:
            continue
        scanned += size
        for t in targets:
            pat = struct.pack('<I', t)
            pos = 0
            while True:
                i = data.find(pat, pos)
                if i < 0:
                    break
                va = base + i
                hits.setdefault(t, []).append(va)
                pos = i + 4
                if len(hits[t]) > 4000:
                    break
    print('scanned MB', round(scanned / 1048576, 1), 'in', round(time.time() - t0, 1), 's')
    for t in targets:
        lst = hits.get(t, [])
        print('target', t, hex(t), 'hits', len(lst))
        for va in lst[:15]:
            mod = next((n for b, n in sorted(mod_ranges, reverse=True) if va >= b and va - b < 0x2000000), '?')
            print('   ', hex(va), mod)

if __name__ == '__main__':
    main()
