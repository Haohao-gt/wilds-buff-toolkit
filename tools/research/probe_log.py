"""持续记录探针数据到 probe_log.txt（后台运行）"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import struct
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'probe_state.json')
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'probe_log.txt')


def rmem(h, addr, n):
    b = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), b, n, ctypes.byref(got)):
        return b''
    return b.raw[:got.value]


def main():
    st = json.load(open(STATE))
    h = k32.OpenProcess(0x0410, False, st['pid'])
    buf = st['buf']
    prev = None
    f = open(LOG, 'a', encoding='utf-8')
    f.write('\n===== start %s =====\n' % time.strftime('%H:%M:%S'))
    f.flush()
    while True:
        data = rmem(h, buf, 0x24)
        if len(data) == 0x24:
            vals = struct.unpack('<9I', data)
            if vals != prev:
                ts = time.strftime('%H:%M:%S')
                names = ['this', '+1C', '+20', '+24', '+3C', '+0C', '+4C', '+50', 'calls']
                line = ts + '  ' + '  '.join('%s=%08X' % (n, v) for n, v in zip(names, vals))
                extra = ''
                beg, end = vals[1], vals[2]
                if 0x10000 < beg < 0x7FFFFFFF and 0 < end - beg <= 0x200:
                    raw = rmem(h, beg, end - beg)
                    extra = '  vec=' + raw.hex(' ')
                f.write(line + extra + '\n')
                f.flush()
                print(line + extra)
                prev = vals
        time.sleep(0.08)


if __name__ == '__main__':
    main()
