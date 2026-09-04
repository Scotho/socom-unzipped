import sys, os, struct, collections
sys.path.insert(0, os.path.dirname(__file__))
import decrypt_apache as da
from ee_unicorn import EE, sext32
from unicorn import UC_HOOK_CODE
ee = EE(verbose=True)
entry, gp = da.load_elf(ee, os.path.join(da.GAME, 'SCUS_972.75'))
da.load_overlay(ee, os.path.join(da.GAME, 'OVERLAY', 'REL', 'DNAS.dec.bin'), 0x4c5380)
ee.setreg(28, gp)
ee.syscall_handlers[0x64] = lambda ee: ee.setreg(2, 0)
da.install_sif_hle(ee)
SP=0x01fe0000; BUF=0x01000000; OUT8=0xf00000; OUT4=0xf00010
blobs = da.zdb_entries(os.path.join(da.GAME, 'RUN', 'RAW', 'APACHE00.ZDB'))
ring = collections.deque(maxlen=16); cnt=[0]
def code(uc, address, size, ud):
    ring.append(address); cnt[0]+=1
ee.uc.hook_add(UC_HOOK_CODE, code)
try:
    ee.call(0x534830, (), sp=SP)
    print('INIT OK; block words:', [hex(ee.r32(a)) for a in range(0x53c4b4,0x53c4e8,4)])
except Exception as e:
    print('INIT ERR', e, 'after', cnt[0]); print('block words:', [hex(ee.r32(a)) for a in range(0x53c4b4,0x53c4e8,4)])
    for a in ring: print('   ', hex(a), hex(ee.r32(a)), ee.patched.get(a) and hex(ee.patched[a]))
    raise SystemExit
blob=blobs['ftscore']; ee.write(BUF, blob); ee.w64(OUT8,0)
try:
    rc = sext32(ee.call(0x539d00, (len(blob), BUF, OUT8), sp=SP)); print("step1 ->", rc, hex(ee.r64(OUT8)), "insns", cnt[0])
except Exception as e:
    print("ERR", e, "after", cnt[0], "insns")
    from capstone import *
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64 | CS_MODE_LITTLE_ENDIAN)
    import struct as st
    print("  memory at fault site vs file:")
    fd=open(os.path.join(da.GAME,'OVERLAY','REL','DNAS.dec.bin'),'rb').read()
    last=ring[-1]
    for a in range(last-0x20,last+0x24,4):
        print(f"    {a:08x} mem={ee.r32(a):08x} file={st.unpack_from('<I',fd,a-0x4c5380)[0]:08x}")
    print("  regs " + " ".join(f"r{i}={ee.reg(i):x}" for i in range(1,32)))
    print("  DAT_5609b8=%x DAT_5609c0=%x" % (ee.r32(0x5609b8), ee.r32(0x5609c0)))
    for a in ring:
        w = ee.r32(a); orig = ee.patched.get(a)
        ins = list(md.disasm(struct.pack('<I', orig if orig else w), a))
        print(f"  {a:08x} {w:08x} {'(patched '+hex(orig)+')' if orig else ''} {ins[0].mnemonic+' '+ins[0].op_str if ins else '??'}")
