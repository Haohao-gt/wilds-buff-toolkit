"""野蛮人大作战 · 自定义 BUFF 编排台 — 本地 WebUI 后端"""
import ctypes
import ctypes.wintypes as wt
import csv
import json
import os
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, 'web')
CSV_PATH = os.path.join(ROOT, 'work', 'buff_catalog.csv')
PORT = 8777

if sys.stdout is None:
    sys.stdout = open(os.path.join(ROOT, 'work', 'server.out'), 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = sys.stdout
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ALIAS = {'宝藏': '磁铁', '滑步': '双重撞击'}


def load_skills():
    out = []
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            name = r['名称']
            for k, v in ALIAS.items():
                if name.startswith(k):
                    name = v + name[len(k):]
            lv = r['等级']
            out.append({'id': int(r['技能ID']), 'cfg': int(r['配置ID']),
                        'name': name, 'cat': r['分类'], 'lv': int(lv) if lv else 0})
    return out


_RAW_SKILLS = load_skills()
_RANK = {'随机BUFF': 0, '主动技能': 1, '特殊/局外': 2}
_BEST = {}
for _s in _RAW_SKILLS:
    _old = _BEST.get(_s['cfg'])
    if _old is None or _RANK.get(_s['cat'], 9) < _RANK.get(_old['cat'], 9):
        _BEST[_s['cfg']] = _s
SKILLS = list(_BEST.values())

ICON_DIR = os.path.join(ROOT, 'icons')


def icon_for(cfg):
    fn = os.path.join(ICON_DIR, '%d.png' % cfg)
    return ('/icons/%d.png' % cfg) if os.path.exists(fn) else ''


for _sk in SKILLS:
    _sk['icon'] = icon_for(_sk['cfg'])
BY_ID = {s['id']: s for s in SKILLS}
BY_CFG = {}
for _s in SKILLS:
    _old = BY_CFG.get(_s['cfg'])
    if (_old is None) or (_old['cat'] != '随机BUFF' and _s['cat'] == '随机BUFF'):
        BY_CFG[_s['cfg']] = _s
CFG_SET = set(BY_CFG)

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)
READABLE = {0x02, 0x04, 0x20, 0x40, 0x80, 0x08}
PAGE_GUARD = 0x100


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wt.DWORD), ('RegionSize', ctypes.c_size_t),
                ('State', wt.DWORD), ('Protect', wt.DWORD), ('Type', wt.DWORD)]


class Game:
    def __init__(self):
        self.lock = threading.Lock()
        self.h = None
        self.pid = 0
        self.coco = 0
        self.logic = 0
        self.hero = 0
        self.vec_begin = 0
        self.vec_end = 0
        self.map_ready = False
        self.map_progress = 0
        self.ptr_map = {}
        self.logs = []
        self.arm = None
        self.arm_thread = None

    # ---------- 基础 ----------
    def log(self, msg):
        line = time.strftime('%H:%M:%S') + '  ' + msg
        self.logs.append(line)
        del self.logs[:-200]
        print(line, flush=True)

    def find_pid(self):
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
            try:
                buf = ctypes.create_unicode_buffer(1024)
                n = wt.DWORD(1024)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) and buf.value.lower().endswith('\\wilds.exe'):
                    return pid
            finally:
                k32.CloseHandle(h)
        return 0

    def connect(self):
        pid = self.find_pid()
        if not pid:
            return False, '未找到 Wilds.exe，请先启动游戏'
        h = k32.OpenProcess(0x1F0FFF, False, pid)
        if not h:
            return False, '无法打开进程（权限不足）'
        arr = (ctypes.c_void_p * 1024)()
        need = wt.DWORD()
        psapi.EnumProcessModulesEx(h, ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(need), 1)
        coco = logic = 0
        for i in range(need.value // ctypes.sizeof(ctypes.c_void_p)):
            nm = ctypes.create_unicode_buffer(260)
            psapi.GetModuleBaseNameW(h, ctypes.c_void_p(arr[i]), nm, 260)
            n = nm.value.lower()
            if n == 'libcocos2d.dll':
                coco = arr[i] or 0
            if n == 'gamelogic.dll':
                logic = arr[i] or 0
        if not coco or not logic:
            return False, '未加载游戏模块（还在启动器界面？）'
        with self.lock:
            self.h, self.pid, self.coco, self.logic = h, pid, coco, logic
        self.log('已连接 PID %d  libcocos2d=%08X  GameLogic=%08X' % (pid, coco, logic))
        self.patch_popup()
        self.refresh_hero()
        self.map_ready = True
        self.map_progress = 100
        return True, '已连接 PID %d' % pid

    def read(self, addr, n):
        b = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), b, n, ctypes.byref(got)) or got.value != n:
            return None
        return b.raw

    def u32(self, addr):
        d = self.read(addr, 4)
        return int.from_bytes(d, 'little') if d else 0

    def refresh_hero(self):
        if not self.h:
            return False
        p = self.u32(self.coco + 0xAAAEEC)
        for off in (0xB4, 0x2B8, 0x2B4, 0x2E4):
            if not p:
                return False
            p = self.u32(p + off)
        if not p:
            return False
        self.hero = p
        sr = p + 0x3D4
        self.vec_begin = self.u32(sr + 0x1C)
        self.vec_end = self.u32(sr + 0x20)
        return self.vec_begin != 0 and self.vec_end > self.vec_begin

    def patch_popup(self):
        try:
            addr = self.logic + 0x4D02A
            cur = self.read(addr, 6)
            if not cur or len(cur) < 6:
                return
            if cur[:2] == bytes.fromhex('83C4'):
                self.log('弹窗补丁已在位')
                return
            expect = (self.logic + 0xC8194) & 0xFFFFFFFF
            if cur[:2] != bytes.fromhex('FF15') or int.from_bytes(cur[2:6], 'little') != expect:
                self.log('弹窗补丁跳过：字节不符 %s' % cur.hex(' '))
                return
            old = wt.DWORD()
            patch = bytes.fromhex('83C410909090')
            k32.VirtualProtectEx(self.h, ctypes.c_void_p(addr), 6, 0x40, ctypes.byref(old))
            got = ctypes.c_size_t()
            ok = k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), patch, 6, ctypes.byref(got))
            k32.VirtualProtectEx(self.h, ctypes.c_void_p(addr), 6, old, ctypes.byref(old))
            k32.FlushInstructionCache(self.h, ctypes.c_void_p(addr), 6)
            self.log('弹窗补丁已应用' if ok else '弹窗补丁写入失败')
        except Exception as e:
            self.log('弹窗补丁异常: %s' % e)

    # ---------- 技能对象索引 ----------
    def anchor_ptr(self):
        try:
            if not self.refresh_hero():
                return 0
            n = int((self.vec_end - self.vec_begin) / 16)
            if n < 1:
                return 0
            raw = self.read(self.vec_begin + (n - 1) * 16, 4)
            return int.from_bytes(raw, 'little') if raw else 0
        except Exception:
            return 0

    def find_cfg(self, cfg):
        with self.lock:
            if cfg in self.ptr_map:
                return self.ptr_map[cfg]
        anchor = self.anchor_ptr()
        if not anchor:
            return 0
        lo, hi = max(0, anchor - 0x200000), anchor + 0x200000
        target = np.array([cfg], dtype=np.int32)
        addr = lo
        deadline = time.time() + 4.0
        while addr < hi and time.time() < deadline:
            mbi = MBI()
            if not k32.VirtualQueryEx(self.h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize
            if size <= 0:
                break
            end = base + size
            start = max(base, lo)
            stop = min(end, hi)
            if (stop > start and mbi.State == 0x1000
                    and (mbi.Protect & 0xFF) in READABLE and not (mbi.Protect & PAGE_GUARD)):
                length = stop - start
                if length <= 0x800000:
                    buf = ctypes.create_string_buffer(length)
                    got = ctypes.c_size_t()
                    if k32.ReadProcessMemory(self.h, ctypes.c_void_p(start), buf, length, ctypes.byref(got)) and got.value >= 8:
                        data = buf.raw[:got.value]
                        arr = np.frombuffer(data[:len(data) // 4 * 4], dtype='<i4')
                        hits = np.nonzero(arr == cfg)[0]
                        for k in hits:
                            off = int(k) * 4
                            if off < 4:
                                continue
                            head = int.from_bytes(data[off - 4:off], 'little')
                            if 0x00400000 < head < 0x7FFF0000:
                                ptr = start + off - 4
                                with self.lock:
                                    self.ptr_map[cfg] = ptr
                                return ptr
            addr = end
        return 0

    def build_map(self):
        with self.lock:
            self.map_ready = False
            self.map_progress = 0
        found = {}
        targets = np.array(sorted(CFG_SET), dtype=np.int32)
        addr = 0
        scanned = 0
        while addr < 0x7FFF0000:
            mbi = MBI()
            if not k32.VirtualQueryEx(self.h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize
            if size <= 0:
                break
            if (mbi.State == 0x1000 and (mbi.Protect & 0xFF) in READABLE
                    and not (mbi.Protect & PAGE_GUARD) and 0x1000 <= size <= 0x4000000):
                buf = ctypes.create_string_buffer(size)
                got = ctypes.c_size_t()
                if k32.ReadProcessMemory(self.h, ctypes.c_void_p(base), buf, size, ctypes.byref(got)) and got.value >= 8:
                    data = buf.raw[:got.value]
                    arr = np.frombuffer(data[:len(data) // 4 * 4], dtype='<i4')
                    hits = np.nonzero(np.isin(arr, targets))[0]
                    for k in hits:
                        off = int(k) * 4
                        if off < 4:
                            continue
                        cfg = int(arr[k])
                        head = int.from_bytes(data[off - 4:off], 'little')
                        if 0x00400000 < head < 0x7FFF0000 and cfg not in found:
                            found[cfg] = base + off - 4
                    scanned += len(data)
                    self.map_progress = min(99, int(scanned / 9000000))
            addr = base + size
        with self.lock:
            self.ptr_map = found
            self.map_ready = True
            self.map_progress = 100
        self.log('技能索引完成：%d / %d' % (len(found), len(SKILLS)))

    # ---------- 卡组 ----------
    def cards(self):
        with self.lock:
            if not self.refresh_hero():
                return []
            n = int((self.vec_end - self.vec_begin) / 16)
            out = []
            for i in range(max(0, n - 3), n):
                e = self.vec_begin + i * 16
                raw = self.read(e, 16)
                if not raw:
                    continue
                ptr = int.from_bytes(raw[0:4], 'little')
                cfg = self.u32(ptr + 4) if ptr else 0
                sk = BY_CFG.get(cfg)
                out.append({'cfg': cfg, 'slot': len(out), 'icon': icon_for(cfg),
                            'name': sk['name'] if sk else ('未知 %d' % cfg),
                            'id': sk['id'] if sk else 0,
                            'cat': sk['cat'] if sk else '',
                            'lv': sk['lv'] if sk else 0})
            return out

    def level(self):
        with self.lock:
            if not self.hero:
                return 0
            return int((self.vec_end - self.vec_begin) / 16 / 3)

    def apply(self, ids, hold=120):
        if not self.refresh_hero():
            return False, '角色未就绪（还没进对局）'
        n = int((self.vec_end - self.vec_begin) / 16)
        if n < 3:
            return False, '当前没有三张卡'
        plan = []
        names = []
        for i, sid in enumerate(ids[:3]):
            if not sid:
                continue
            sk = BY_ID.get(int(sid))
            if not sk:
                continue
            ptr = self.find_cfg(sk['cfg'])
            if not ptr:
                return False, '找不到「%s」的配置对象' % sk['name']
            plan.append((i, ptr))
            names.append(sk['name'])
        if not plan:
            return False, '没有可写入的卡'
        self.arm = {'plan': plan, 'until': time.time() + float(hold), 'count': n}
        self._write_once()
        if (not self.arm_thread) or (not self.arm_thread.is_alive()):
            self.arm_thread = threading.Thread(target=self._arm_loop, daemon=True)
            self.arm_thread.start()
        return True, '已装填：' + '、'.join(names) + '（%d 秒内点卡生效）' % int(float(hold))

    def _write_once(self):
        a = self.arm
        if not a:
            return
        try:
            if not self.refresh_hero():
                return
            n = int((self.vec_end - self.vec_begin) / 16)
            if n < 3 or n != a['count']:
                self.arm = None
                return
            base = self.vec_begin + (n - 3) * 16
            for i, ptr in a['plan']:
                cur = self.read(base + i * 16, 16)
                if not cur:
                    continue
                p8 = int.from_bytes(cur[8:12], 'little')
                pc = int.from_bytes(cur[12:16], 'little')
                entry = ptr.to_bytes(4, 'little') + (60).to_bytes(4, 'little') + p8.to_bytes(4, 'little') + pc.to_bytes(4, 'little')
                old = wt.DWORD()
                k32.VirtualProtectEx(self.h, ctypes.c_void_p(base + i * 16), 16, 0x40, ctypes.byref(old))
                got = ctypes.c_size_t()
                k32.WriteProcessMemory(self.h, ctypes.c_void_p(base + i * 16), entry, 16, ctypes.byref(got))
                k32.VirtualProtectEx(self.h, ctypes.c_void_p(base + i * 16), 16, old, ctypes.byref(old))
        except Exception:
            pass

    def _arm_loop(self):
        while True:
            a = self.arm
            if (not a) or time.time() > a['until']:
                self.arm = None
                return
            self._write_once()
            time.sleep(0.08)



GAME = Game()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urlparse(self.path).path
        if p.startswith('/icons/'):
            fn = os.path.join(ICON_DIR, os.path.basename(p))
            if os.path.exists(fn):
                data = open(fn, 'rb').read()
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Cache-Control', 'max-age=86400')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404)
            return
        if p == '/api/skills':
            return self.send_json({'skills': SKILLS})
        if p == '/api/state':
            connected = GAME.h is not None and bool(GAME.refresh_hero())
            return self.send_json({
                'connected': connected,
                'pid': GAME.pid,
                'hero': '%08X' % GAME.hero if GAME.hero else '',
                'level': GAME.level(),
                'cards': GAME.cards() if connected else [],
                'mapReady': GAME.map_ready,
                'mapProgress': GAME.map_progress,
                'armed': max(0, int(GAME.arm['until'] - time.time())) if GAME.arm else 0,
                'logs': GAME.logs[-8:],
            })
        return super().do_GET()

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(n) or b'{}')
        if p == '/api/connect':
            ok, msg = GAME.connect()
            return self.send_json({'ok': ok, 'msg': msg})
        if p == '/api/apply':
            ok, msg = GAME.apply(body.get('slots', []), body.get('hold', 120))
            GAME.log(msg)
            return self.send_json({'ok': ok, 'msg': msg})
        if p == '/api/rebuild':
            threading.Thread(target=GAME.build_map, daemon=True).start()
            return self.send_json({'ok': True, 'msg': '开始重建索引'})
        return self.send_json({'ok': False, 'msg': 'unknown'}, 404)


def main():
    if not os.path.isdir(WEB):
        print('web 目录不存在')
        return
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print('http://127.0.0.1:%d' % PORT, flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
