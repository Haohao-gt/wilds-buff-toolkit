import sys, struct
import pefile
from capstone import *

p = r"C:/Program Files/4399野蛮人大作战/Bin/Release.win32/GameLogic.dll"
pe = pefile.PE(p, fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase
secs = [(s.Name.rstrip(b'\0').decode('latin1'), base + s.VirtualAddress, s.VirtualAddress, s.SizeOfRawData, s.PointerToRawData) for s in pe.sections]

def va2off(va):
    for n, vb, rva, size, ptr in secs:
        if vb <= va < vb + size:
            return ptr + (va - vb)

def off2va(off):
    for n, vb, rva, size, ptr in secs:
        if ptr <= off < ptr + size:
            return vb + (off - ptr)

# imports
msg_iat = None
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    if entry.dll.lower() != b'user32.dll':
        continue
    for imp in entry.imports:
        if imp.name == b'MessageBoxA':
            msg_iat = imp.address
print('MessageBoxA IAT', hex(msg_iat) if msg_iat else None)

text = [s for s in secs if s[0] == '.text'][0]
code = pe.__data__[text[4]:text[4] + text[3]]
md = Cs(CS_ARCH_X86, CS_MODE_32); md.detail = True

# find call dword ptr [msg_iat]
hits = []
for ins in md.disasm(code, text[1]):
    if ins.mnemonic == 'call' and 'dword ptr' in ins.op_str:
        # op_str like 'dword ptr [0x1010f16a8]'
        try:
            addr = int(ins.op_str.split('[')[1].rstrip(']'), 16)
        except Exception:
            continue
        if addr == msg_iat:
            hits.append(ins.address)
print('call [MessageBoxA] sites:', [hex(x) for x in hits])

# string VAs
strings = {}
for name, off in [('Random Skill index: ', 0xcab11), ('Carry Skill: ', 0xcab29), ('PreOperation: ', 0xcab3c)]:
    strings[name] = off2va(off)
    print(name, hex(strings[name]))

# find pointers to those strings anywhere
for name, va in strings.items():
    pat = struct.pack('<I', va)
    idx = []
    start = 0
    while True:
        i = pe.__data__.find(pat, start)
        if i < 0:
            break
        idx.append((i, off2va(i)))
        start = i + 1
    print('ptr to', name, [(hex(a), hex(b)) for a, b in idx[:6]])

# disassemble around messagebox call sites
for a in hits:
    print('\n=== site', hex(a), '===')
    off = va2off(a - 0x120)
    for ins in md.disasm(code[off - text[4]:off - text[4] + 0x180], a - 0x120):
        print('  %08x %-8s %s' % (ins.address, ins.mnemonic, ins.op_str))
