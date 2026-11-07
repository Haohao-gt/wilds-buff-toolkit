"""Hook libtms.dll 的 WSASend，记录上行数据"""
import os
import ctypes
import ctypes.wintypes as wt
import json
import struct
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)
PAGE_EXECUTE_READWRITE = 0x40
PAGE_READWRITE = 0x04
MEM = 0x3000
WSASEND_IAT_RVA = 0x371C0
STATE = 'work/hook_wsasend_state.json'

pid = int(os.environ.get('WILDS_PID') or subprocess.check_output(['powershell', '-NoProfile', '-Command', "(Get-Process Wilds).Id"]).decode().split()[0])
h = k32.OpenProcess(0x1F0FFF, False, pid)


def modules():
    arr = (ctypes.c_void_p * 1024)(); need = wt.DWORD()
    psapi.EnumProcessModulesEx(h, ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(need), 1)
    out = {}
    for i in range(need.value // ctypes.sizeof(ctypes.c_void_p)):
        nm = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(h, ctypes.c_void_p(arr[i]), nm, 260)
        out[nm.value.lower()] = arr[i]
    return out


def rd(a, n):
    b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(g)) or g.value != n:
        return b''
    return b.raw


def wr(a, data):
    old = wt.DWORD()
    k32.VirtualProtectEx(h, ctypes.c_void_p(a), len(data), PAGE_EXECUTE_READWRITE, ctypes.byref(old))
    g = ctypes.c_size_t()
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(a), data, len(data), ctypes.byref(g))
    k32.VirtualProtectEx(h, ctypes.c_void_p(a), len(data), old, ctypes.byref(old))
    k32.FlushInstructionCache(h, ctypes.c_void_p(a), len(data))
    return ok


def p32(v):
    return struct.pack('<I', v & 0xFFFFFFFF)


def stub(buf, entries, real):
    c = bytearray()
    c += b'\x60'
    c += b'\x8B\x44\x24\x28'          # mov eax,[esp+0x28]  lpBuffers
    c += b'\x8B\x08'                  # mov ecx,[eax]      len
    c += b'\x8B\x70\x04'              # mov esi,[eax+4]    buf
    c += b'\x8B\x3D' + p32(buf)       # mov edi,[buf]
    c += b'\xFF\x05' + p32(buf)       # inc [buf]
    c += b'\x81\xE7\xFF\x00\x00\x00'
    c += b'\x6B\xFF\x48'
    c += b'\x81\xC7' + p32(entries)
    c += b'\x89\x0F'
    c += b'\x83\xF9\x40'
    c += b'\x7E\x05'
    c += b'\xB9\x40\x00\x00\x00'
    c += b'\x83\xC7\x04'
    c += b'\xF3\xA4'
    c += b'\x61'
    c += b'\xB8' + p32(real)
    c += b'\xFF\xE0'
    return bytes(c)


def hook():
    base = modules().get('libtms.dll')
    if not base:
        print('libtms.dll not loaded'); return
    iat = base + WSASEND_IAT_RVA
    real = int.from_bytes(rd(iat, 4), 'little')
    print('base', hex(base), 'iat', hex(iat), 'real', hex(real))
    buf = k32.VirtualAllocEx(h, None, 0x20, MEM, PAGE_READWRITE)
    entries = k32.VirtualAllocEx(h, None, 0x4800, MEM, PAGE_READWRITE)
    cave = k32.VirtualAllocEx(h, None, 0x200, MEM, PAGE_EXECUTE_READWRITE)
    print('buf', hex(buf), 'entries', hex(entries), 'cave', hex(cave))
    if not wr(cave, stub(buf, entries, real)):
        print('stub fail'); return
    if not wr(iat, p32(cave)):
        print('iat fail'); return
    json.dump({'pid': pid, 'iat': iat, 'real': real, 'buf': buf, 'entries': entries, 'cave': cave}, open(STATE, 'w'))
    print('hooked')


def poll():
    st = json.load(open(STATE))
    hh = k32.OpenProcess(0x0410, False, st['pid'])
    seen = 0
    t0 = time.time()
    limit = float(sys.argv[2]) if len(sys.argv) > 2 else 12
    while time.time() - t0 < limit:
        b = ctypes.create_string_buffer(4); g = ctypes.c_size_t()
        k32.ReadProcessMemory(hh, ctypes.c_void_p(st['buf']), b, 4, ctypes.byref(g))
        idx = int.from_bytes(b.raw[:4], 'little')
        if idx > seen:
            for k in range(seen, min(idx, seen + 40)):
                e = ctypes.create_string_buffer(0x48); gg = ctypes.c_size_t()
                k32.ReadProcessMemory(hh, ctypes.c_void_p(st['entries'] + (k % 256) * 0x48), e, 0x48, ctypes.byref(gg))
                ln = int.from_bytes(e.raw[:4], 'little')
                print('SEND len=%d %s' % (ln, e.raw[4:4 + min(ln, 0x40)].hex(' ')))
            seen = idx
        time.sleep(0.2)


def restore():
    st = json.load(open(STATE))
    hh = k32.OpenProcess(0x1F0FFF, False, st['pid'])
    wr(st['iat'], p32(st['real']))
    print('restored')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'hook'
    if cmd == 'hook': hook()
    elif cmd == 'poll': poll()
    elif cmd == 'restore': restore()
