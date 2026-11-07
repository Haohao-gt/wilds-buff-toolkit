"""Hook msc.dll 的 send()，把发出的数据包记录到共享缓冲区"""
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

PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT_RESERVE = 0x3000
PAGE_EXECUTE_READWRITE = 0x40
PAGE_READWRITE = 0x04
SEND_IAT_RVA = 0x1B53E8
STATE = 'work/hook_send_state.json'

pid = int(os.environ.get('WILDS_PID') or subprocess.check_output(['powershell', '-NoProfile', '-Command', "(Get-Process Wilds).Id"]).decode().split()[0])
h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)


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


def build_stub(buf, entries, real_ptr):
    code = bytearray()
    code += b'\x60'                              # pushad
    code += b'\x8B\x74\x24\x28'                  # mov esi,[esp+0x28]  buf
    code += b'\x8B\x4C\x24\x2C'                  # mov ecx,[esp+0x2C]  len
    code += b'\x8B\x3D' + p32(buf)               # mov edi,[buf]
    code += b'\xFF\x05' + p32(buf)               # inc dword [buf]
    code += b'\x81\xE7\xFF\x00\x00\x00'          # and edi,0xFF
    code += b'\x6B\xFF\x48'                      # imul edi,edi,0x48
    code += b'\x81\xC7' + p32(entries)           # add edi,entries
    code += b'\x89\x0F'                          # mov [edi],ecx
    code += b'\x83\xF9\x40'                      # cmp ecx,0x40
    code += b'\x7E\x05'                          # jle +5
    code += b'\xB9\x40\x00\x00\x00'              # mov ecx,0x40
    code += b'\x83\xC7\x04'                      # add edi,4
    code += b'\xF3\xA4'                          # rep movsb
    code += b'\x61'                              # popad
    code += b'\xFF\x25' + p32(real_ptr)          # jmp [real_send]
    return bytes(code)


def main():
    mods = modules()
    base = mods.get('msc.dll')
    if not base:
        print('msc.dll not loaded'); return
    iat = base + SEND_IAT_RVA
    real = int.from_bytes(rd(iat, 4), 'little')
    print('msc base', hex(base), 'IAT', hex(iat), 'real send', hex(real))

    buf = k32.VirtualAllocEx(h, None, 0x20, MEM_COMMIT_RESERVE, PAGE_READWRITE)
    entries = k32.VirtualAllocEx(h, None, 0x4800, MEM_COMMIT_RESERVE, PAGE_READWRITE)
    cave = k32.VirtualAllocEx(h, None, 0x200, MEM_COMMIT_RESERVE, PAGE_EXECUTE_READWRITE)
    print('buf', hex(buf), 'entries', hex(entries), 'cave', hex(cave))
    if not wr(cave, build_stub(buf, entries, iat)):
        print('stub write failed'); return
    if not wr(iat, p32(cave)):
        print('iat patch failed'); return
    json.dump({'pid': pid, 'iat': iat, 'real': real, 'buf': buf, 'entries': entries, 'cave': cave},
              open(STATE, 'w'))
    print('hooked')


def poll():
    st = json.load(open(STATE))
    hh = k32.OpenProcess(0x0410, False, st['pid'])
    seen = 0
    t0 = time.time()
    limit = float(sys.argv[2]) if len(sys.argv) > 2 else 15
    while time.time() - t0 < limit:
        b = ctypes.create_string_buffer(4); g = ctypes.c_size_t()
        k32.ReadProcessMemory(hh, ctypes.c_void_p(st['buf']), b, 4, ctypes.byref(g))
        idx = int.from_bytes(b.raw[:4], 'little')
        if idx > seen:
            for k in range(seen, min(idx, seen + 50)):
                e = ctypes.create_string_buffer(0x48); gg = ctypes.c_size_t()
                k32.ReadProcessMemory(hh, ctypes.c_void_p(st['entries'] + (k % 256) * 0x48), e, 0x48, ctypes.byref(gg))
                ln = int.from_bytes(e.raw[:4], 'little')
                data = e.raw[4:4 + min(ln, 0x40)]
                print('SEND len=%d %s' % (ln, data.hex(' ')))
            seen = idx
        time.sleep(0.2)


def restore():
    st = json.load(open(STATE))
    hh = k32.OpenProcess(PROCESS_ALL_ACCESS, False, st['pid'])
    old = wt.DWORD()
    k32.VirtualProtectEx(hh, ctypes.c_void_p(st['iat']), 4, 0x40, ctypes.byref(old))
    g = ctypes.c_size_t()
    k32.WriteProcessMemory(hh, ctypes.c_void_p(st['iat']), p32(st['real']), 4, ctypes.byref(g))
    k32.VirtualProtectEx(hh, ctypes.c_void_p(st['iat']), 4, old, ctypes.byref(old))
    print('restored')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'hook'
    if cmd == 'hook':
        main()
    elif cmd == 'poll':
        poll()
    elif cmd == 'restore':
        restore()
