"""屏蔽野蛮人大作战 CSkillRandom 调试弹窗（Error / PreOperation / Carry Skill / Random Skill index）

用法:
    python tools/patch_popup.py             # 打补丁
    python tools/patch_popup.py --restore   # 还原
"""
import ctypes
import ctypes.wintypes as wt
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)

PROCESS_ALL_ACCESS = 0x1F0FFF
PAGE_EXECUTE_READWRITE = 0x40
OLD_PROTECT = wt.DWORD()

MODULE = 'gamelogic.dll'
PATCH_RVA = 0x4D02A
MSG_IAT_RVA = 0xC8194
ORIG_TAIL = bytes.fromhex('c745')            # 仅用于核对
PATCH = bytes.fromhex('83C410909090')        # add esp,0x10 ; nop nop nop


def find_pid(name):
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
        size = wt.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            if buf.value.lower().endswith('\\' + name.lower() + '.exe'):
                k32.CloseHandle(h)
                return pid
        k32.CloseHandle(h)
    return None


def module_base(h, dllname):
    arr = (ctypes.c_void_p * 1024)()
    need = wt.DWORD()
    if not psapi.EnumProcessModulesEx(h, ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(need), 1):
        raise OSError(ctypes.get_last_error(), 'EnumProcessModulesEx')
    for i in range(need.value // ctypes.sizeof(ctypes.c_void_p)):
        nm = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(h, ctypes.c_void_p(arr[i]), nm, 260)
        if nm.value.lower() == dllname:
            return arr[i]
    raise RuntimeError('module not found: ' + dllname)


def read(h, addr, n=6):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got))
    return buf.raw[:got.value]


def write(h, addr, data):
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), PAGE_EXECUTE_READWRITE, ctypes.byref(OLD_PROTECT))
    got = ctypes.c_size_t()
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(got))
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), OLD_PROTECT, ctypes.byref(OLD_PROTECT))
    k32.FlushInstructionCache(h, ctypes.c_void_p(addr), len(data))
    return ok, got.value


def main():
    restore = '--restore' in sys.argv
    pid = None
    for j, a in enumerate(sys.argv):
        if a == '--pid':
            pid = int(sys.argv[j + 1])
    pid = pid or find_pid('Wilds')
    if not pid:
        print('未找到 Wilds.exe，请先启动游戏')
        return

    h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h:
        print('OpenProcess 失败，错误码', ctypes.get_last_error())
        return

    base = module_base(h, MODULE)
    addr = base + PATCH_RVA
    cur = read(h, addr)
    print('PID=%d  GameLogic=%08X  目标=%08X  当前=%s' % (pid, base, addr, cur.hex(' ')))

    if restore:
        if cur == PATCH:
            ok, n = write(h, addr, bytes.fromhex('FF15') + (base + MSG_IAT_RVA).to_bytes(4, 'little'))
            print('已还原' if ok else '还原失败', read(h, addr).hex(' '))
        else:
            print('当前不是补丁状态，无需还原')
        return

    expect_operand = (base + MSG_IAT_RVA) & 0xFFFFFFFF
    is_call = cur[:2] == bytes.fromhex('FF15') and int.from_bytes(cur[2:6], 'little') == expect_operand
    if cur == PATCH:
        print('已经是补丁状态')
        return
    if not is_call:
        print('字节不符，未修改。当前:', cur.hex(' '))
        return

    ok, n = write(h, addr, PATCH)
    print('补丁%s，写入 %d 字节，校验: %s' % ('成功' if ok else '失败', n, read(h, addr).hex(' ')))


if __name__ == '__main__':
    main()
