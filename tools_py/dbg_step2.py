import sys, os, collections
sys.path.insert(0, os.path.dirname(__file__))
import decrypt_apache as da
from ee_unicorn import EE, sext32
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_PC
ee = EE(verbose=False)
entry, gp = da.load_elf(ee, os.path.join(da.GAME, 'SCUS_972.75'))
ee.install_kernel_hle()
da.install_sif_hle(ee)
ee.syscall_handlers[0x3c] = lambda ee: ee.setreg(2, 0x01fffff0 if (ee.reg(5) & 0xffffffff) == 0xffffffff else ((ee.reg(5) + ee.reg(6)) & 0xffffffff & ~0xf))
ee.syscall_handlers[0x3d] = lambda ee: ee.setreg(2, 0x01f80000 if (ee.reg(5) & 0xffffffff) == 0xffffffff else (ee.reg(4) + ee.reg(5)) & 0xffffffff)
ee.hook_function(0x1ac9d8, lambda ee: 0)
ee.run(entry, 0x1c4cc0)
da.load_overlay(ee, os.path.join(da.GAME, 'OVERLAY', 'REL', 'DNAS.dec.bin'), 0x4c5380)
blobs = da.zdb_entries(os.path.join(da.GAME, 'RUN', 'RAW', 'APACHE00.ZDB'))
# call/return tracer for selected functions
WATCH = [int(a,16) for a in sys.argv[1:]] or [0x53c648, 0x5415f8, 0x540210, 0x53f8f0, 0x195768, 0x541658, 0x539e00, 0x53d3d0]
pending = {}
log = []
def on_entry(uc, address, size, ud):
    ra = ee.reg(31) & 0xffffffff
    args = [ee.reg(4+i) & 0xffffffff for i in range(4)]
    pending.setdefault(ra, []).append((address, args))
    if not any(h[0]==ra for h in rets):
        h = ee.uc.hook_add(UC_HOOK_CODE, on_ret, None, ra, ra); rets.append((ra, h))
rets = []
def on_ret(uc, address, size, ud):
    st = pending.get(address)
    if st:
        fn, args = st.pop()
        log.append((fn, args, sext32(ee.reg(2))))
for a in WATCH:
    ee.uc.hook_add(UC_HOOK_CODE, on_entry, None, a, a)
print('sceSifInitRpc ->', ee.call(0x1a6368, (0,))); print('sceCdInit ->', ee.call(0x18ea98, (0,)))
ee.call(0x534830, ())
BUF=0x01000000; OUT8=0xf00000; OUT4=0xf00010
blob=blobs['ftscore']; ee.write(BUF, blob); ee.w64(OUT8,0)
rc = sext32(ee.call(0x539d00, (len(blob), BUF, OUT8))); print("step1 ->", rc, hex(ee.r64(OUT8)))
log.clear()
sz2 = sext32(ee.call(0x539d50, (len(blob), ee.r32(OUT8), BUF))); print("step2 ->", sz2)
for fn, args, rv in log[-40:]:
    print(f"  {fn:#x}({', '.join(hex(a) for a in args)}) -> {rv} ({rv & 0xffffffff:#x})")

print("semas:", ee.semas, "DAT_001ca86c=", hex(ee.r32(0x1ca86c)), "DAT_001ca88c=", hex(ee.r32(0x1ca88c)), "cd+0x24=", hex(ee.r32(0x1cc3e4)))
