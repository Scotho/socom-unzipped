import sys, os, struct, collections
sys.path.insert(0, os.path.dirname(__file__))
import decrypt_apache as da
from ee_unicorn import EE
from unicorn import UC_HOOK_CODE
ee = EE(verbose=False)
entry, gp = da.load_elf(ee, os.path.join(da.GAME, 'SCUS_972.75'))
da.load_overlay(ee, os.path.join(da.GAME, 'OVERLAY', 'REL', 'DNAS.BIN'), 0x4c5380)
ee.setreg(28, gp)
ring = collections.deque(maxlen=12)
cnt = [0]
def code(uc, address, size, ud):
    ring.append(address); cnt[0] += 1
ee.uc.hook_add(UC_HOOK_CODE, code)
ee.syscall_handlers[0x64] = lambda ee: ee.setreg(2, 0)
try:
    r = ee.call(0x534830, (), sp=0x01fe0000)
    print("init ->", hex(r), "insns", cnt[0])
except Exception as e:
    print("ERR", e, "after", cnt[0], "insns")
    from capstone import *
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64 | CS_MODE_LITTLE_ENDIAN)
    for a in ring:
        w = ee.r32(a); orig = ee.patched.get(a)
        ins = list(md.disasm(struct.pack('<I', orig if orig else w), a))
        print(f"  {a:08x} {w:08x} {'(patched '+hex(orig)+')' if orig else ''} {ins[0].mnemonic+' '+ins[0].op_str if ins else '??'}")
