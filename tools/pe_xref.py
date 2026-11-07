import sys, struct
import pefile
from capstone import *

path = sys.argv[1]
pe = pefile.PE(path, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
secs = []
for s in pe.sections:
    name = s.Name.rstrip(b'\x00').decode('latin1')
    secs.append((name, base + s.VirtualAddress, s.VirtualAddress, s.SizeOfRawData, s.PointerToRawData))

def va_to_off(va):
    for name, vbase, rva, size, ptr in secs:
        if vbase <= va < vbase + size:
            return ptr + (va - vbase)
    return None

def read_str(va):
    off = va_to_off(va)
    if off is None:
        return ''
    data = pe.__data__[off:off+200]
    end = data.find(b'\x00')
    return data[:end].decode('latin1', 'replace')

# find strings
targets = [b'Error:Buff id %d error', b'Random Skill index: ', b'Carry Skill: ', b'Error: Skill %d create error',
           b'Character\\SkillRandom.cpp', b'Character\\Buff.cpp', b'choose skill', b'ConformRandomSkill']
found = {}
for t in targets:
    idx = pe.__data__.find(t)
    if idx < 0:
        continue
    # map file offset -> va
    for name, vbase, rva, size, ptr in secs:
        if ptr <= idx < ptr + size:
            found[t.decode('latin1')] = vbase + (idx - ptr)
            break
print('strings:')
for k, v in found.items():
    print(f'  {hex(v)}  {k}')

text = [s for s in secs if s[0] == '.text'][0]
name, vbase, rva, size, ptr = text
code = pe.__data__[ptr:ptr+size]
md = Cs(CS_ARCH_X86, CS_MODE_32)

# scan for imm32 references to string VAs
for k, va in found.items():
    b = struct.pack('<I', va)
    hits = []
    start = 0
    while True:
        i = code.find(b, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    print(f'\nrefs to {k} ({hex(va)}): {len(hits)}')
    for h in hits[:6]:
        vh = vbase + h
        # disassemble from a bit before
        s = max(0, h - 24)
        print('  ref at', hex(vh))
        for ins in md.disasm(code[s:h+12], vbase + s):
            print('    %08x  %-8s %s' % (ins.address, ins.mnemonic, ins.op_str))
