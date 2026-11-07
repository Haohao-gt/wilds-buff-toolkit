"""动态探针 v2：Hook GameLogic!0x1004CCC0，捕获 CSkillRandom 状态，
并可在升级刷出三张卡时把最后三个候选改写成指定技能。

用法:
    python tools/probe.py check
    python tools/probe.py inject
    python tools/probe.py poll
    python tools/probe.py arm  <entry0_hex> <entry1_hex> <entry2_hex> [target_hero]
    python tools/probe.py disarm
    python tools/probe.py restore
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import struct
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)

PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT_RESERVE = 0x3000
PAGE_EXECUTE_READWRITE = 0x40
PAGE_READWRITE = 0x04

TARGET_RVA = 0x4CCC0
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'probe_state.json')
BUF_SIZE = 0x100
CAVE_SIZE = 0x300
ORIG_LEN = 10


def p32(v):
    return struct.pack('<I', v & 0xFFFFFFFF)


def find_pid(name='Wilds'):
    arr = (wt.DWORD * 4096)()
    need = wt.DWORD()
    psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(need))
    for i in range(need.value // 4):
        pid = arr[i]
        if not pid:
            continue
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            continue
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) and buf.value.lower().endswith('\\' + name.lower() + '.exe'):
            k32.CloseHandle(h)
            return pid
        k32.CloseHandle(h)
    return None


def module_base(h, dll='gamelogic.dll'):
    arr = (ctypes.c_void_p * 1024)()
    need = wt.DWORD()
    psapi.EnumProcessModulesEx(h, ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(need), 1)
    for i in range(need.value // ctypes.sizeof(ctypes.c_void_p)):
        nm = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(h, ctypes.c_void_p(arr[i]), nm, 260)
        if nm.value.lower() == dll:
            return arr[i]
    raise RuntimeError('module not found')


def rmem(h, addr, n):
    b = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), b, n, ctypes.byref(got)):
        return b''
    return b.raw[:got.value]


def wmem(h, addr, data):
    old = wt.DWORD()
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), PAGE_EXECUTE_READWRITE, ctypes.byref(old))
    got = ctypes.c_size_t()
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(got))
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), old, ctypes.byref(old))
    k32.FlushInstructionCache(h, ctypes.c_void_p(addr), len(data))
    return ok and got.value == len(data)


def build_stub(cave, buf, back, orig):
    code = bytearray()
    code += b'\x60'                                     # pushad
    code += b'\x8B\x44\x24\x18'                         # mov eax,[esp+0x18] -> ECX
    code += b'\xA3' + p32(buf + 0x00)
    for src, dst in ((0x0C, 0x14), (0x1C, 0x04), (0x20, 0x08), (0x24, 0x0C),
                     (0x3C, 0x10), (0x4C, 0x18), (0x50, 0x1C)):
        code += b'\x8B\x50' + bytes([src])
        code += b'\x89\x15' + p32(buf + dst)
    code += b'\x9C\xFF\x05' + p32(buf + 0x20) + b'\x9D'

    # if (!enable) skip
    code += b'\x83\x3D' + p32(buf + 0x30) + b'\x00'
    jz1 = len(code)
    code += b'\x74\x00'
    # if (target && this-0x3D4 != target) skip
    code += b'\x8B\xD0'                                  # mov edx,eax
    code += b'\x81\xEA' + p32(0x3D4)                     # sub edx,0x3D4
    code += b'\x3B\x15' + p32(buf + 0x34)                # cmp edx,[buf+34]
    jz2 = len(code)
    code += b'\x74\x00'                                  # je ok_target
    code += b'\x83\x3D' + p32(buf + 0x34) + b'\x00'      # cmp [buf+34],0
    jz3 = len(code)
    code += b'\x74\x00'                                  # je ok_target
    jmp_skip = len(code)
    code += b'\xEB\x00'                                  # jmp skip
    ok_target = len(code)
    # patch last three entries
    code += b'\x8B\x78\x20'                              # mov edi,[eax+0x20]
    code += b'\x8B\x48\x1C'                              # mov ecx,[eax+0x1C]
    code += b'\x2B\xF9'                                  # sub edi,ecx
    code += b'\x83\xFF\x30'                              # cmp edi,48
    jb1 = len(code)
    code += b'\x72\x00'
    code += b'\x8B\x78\x20'                              # mov edi,[eax+0x20]
    code += b'\x83\xEF\x30'                              # sub edi,48
    code += b'\xBE' + p32(buf + 0x40)                    # mov esi,entries
    code += b'\xB9\x0C\x00\x00\x00'                      # mov ecx,12
    code += b'\xF3\xA5'                                  # rep movsd
    skip = len(code)
    code[jz1 + 1] = (skip - (jz1 + 2)) & 0xFF
    code[jz2 + 1] = (ok_target - (jz2 + 2)) & 0xFF
    code[jz3 + 1] = (ok_target - (jz3 + 2)) & 0xFF
    code[jmp_skip + 1] = (skip - (jmp_skip + 2)) & 0xFF
    code[jb1 + 1] = (skip - (jb1 + 2)) & 0xFF

    code += b'\x61'                                      # popad
    code += orig
    rel = back - (cave + len(code) + 5)
    code += b'\xE9' + p32(rel)
    return bytes(code)


def open_target():
    pid = find_pid()
    if not pid:
        print('未找到 Wilds.exe')
        return None
    h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    base = module_base(h)
    return h, pid, base, base + TARGET_RVA


def check():
    r = open_target()
    if not r:
        return
    h, pid, base, target = r
    print('PID=%d base=%08X target=%08X' % (pid, base, target))
    print('字节:', rmem(h, target, 16).hex(' '))


def inject():
    r = open_target()
    if not r:
        return
    h, pid, base, target = r
    orig = rmem(h, target, ORIG_LEN)
    print('PID=%d base=%08X target=%08X 原字节=%s' % (pid, base, target, orig.hex(' ')))
    if orig[:1] == b'\xE9':
        print('已 Hook，先 restore')
        return
    buf = k32.VirtualAllocEx(h, None, BUF_SIZE, MEM_COMMIT_RESERVE, PAGE_READWRITE)
    cave = k32.VirtualAllocEx(h, None, CAVE_SIZE, MEM_COMMIT_RESERVE, PAGE_EXECUTE_READWRITE)
    stub = build_stub(cave, buf, target + ORIG_LEN, orig)
    if not wmem(h, cave, stub):
        print('stub 写入失败')
        return
    patch = b'\xE9' + p32(cave - (target + 5)) + b'\x90' * (ORIG_LEN - 5)
    if not wmem(h, target, patch):
        print('Hook 写入失败')
        return
    json.dump({'pid': pid, 'base': base, 'target': target, 'buf': buf, 'cave': cave,
               'orig': orig.hex(), 'stub_len': len(stub)}, open(STATE, 'w'))
    print('Hook 完成 buffer=%08X cave=%08X stub=%d字节' % (buf, cave, len(stub)))


def poll():
    st = json.load(open(STATE))
    h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, st['pid'])
    data = rmem(h, st['buf'], 0x38)
    vals = struct.unpack('<14I', data)
    names = ['this', '+1C', '+20', '+24', '+3C', '+0C', '+4C', '+50', 'calls',
             'pad', 'pad', 'pad', 'enable', 'target']
    print('  '.join('%s=%08X' % (n, v) for n, v in zip(names, vals)))


def arm():
    st = json.load(open(STATE))
    h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, st['pid'])
    entries = b''.join(bytes.fromhex(x) for x in sys.argv[2:5])
    if len(entries) != 48:
        print('需要 3 个 16 字节的 entry 十六进制')
        return
    target = int(sys.argv[5], 16) if len(sys.argv) > 5 else 0
    wmem(h, st['buf'] + 0x40, entries)
    wmem(h, st['buf'] + 0x34, p32(target))
    wmem(h, st['buf'] + 0x30, p32(1))
    print('已装填，target=%08X' % target)
    poll()


def disarm():
    st = json.load(open(STATE))
    h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, st['pid'])
    wmem(h, st['buf'] + 0x30, p32(0))
    print('已关闭改写')
    poll()


def restore():
    st = json.load(open(STATE))
    h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, st['pid'])
    ok = wmem(h, st['target'], bytes.fromhex(st['orig']))
    print('还原:', ok, rmem(h, st['target'], ORIG_LEN).hex(' '))
    k32.VirtualFreeEx(h, ctypes.c_void_p(st['cave']), 0, 0x8000)
    k32.VirtualFreeEx(h, ctypes.c_void_p(st['buf']), 0, 0x8000)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    {'check': check, 'inject': inject, 'poll': poll, 'arm': arm,
     'disarm': disarm, 'restore': restore}.get(cmd, check)()
