import ctypes, ctypes.wintypes as wt, sys, struct

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
h = k32.OpenProcess(0x0410, False, int(sys.argv[1]))
addr = int(sys.argv[2], 16)
size = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x200

buf = ctypes.create_string_buffer(size)
got = ctypes.c_size_t()
ok = k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got))
print('read', ok, got.value)
data = buf.raw[:got.value]
for off in range(0, len(data), 16):
    chunk = data[off:off+16]
    ints = struct.unpack('<4i', chunk)
    print('%08x  %s  | %s' % (addr + off, ' '.join('%11d' % v for v in ints), chunk.hex(' ')))
