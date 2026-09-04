import sys, os, collections
os.environ['NO_TEXT_HOOKS'] = '1'
sys.path.insert(0, os.path.dirname(__file__))
import decrypt_apache as da
from ee_unicorn import EE, sext32
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_PC
ee = EE(verbose=False)
entry, gp = da.load_elf(ee, os.path.join(da.GAME, 'SCUS_972.75'))
ee.install_kernel_hle()
da.install_sif_hle(ee)
reads = collections.Counter(); readers = collections.Counter()
def onread(uc, access, address, size, value, ud):
    for a in range(address & ~3, address + size, 4):
        if a in ee.patched:
            reads[a] += 1; readers[uc.reg_read(UC_MIPS_REG_PC)] += 1
if os.environ.get('READ_HOOKS'):
    ee.uc.hook_add(UC_HOOK_MEM_READ, onread, None, 0x180000, 0x1d5600)
    ee.uc.hook_add(UC_HOOK_MEM_READ, onread, None, 0x4c5400, 0x4c5400 + 0x840c0)
# crt0
ee.syscall_handlers[0x3c] = lambda ee: ee.setreg(2, 0x01fffff0 if (ee.reg(5) & 0xffffffff) == 0xffffffff else ((ee.reg(5) + ee.reg(6)) & 0xffffffff & ~0xf))
ee.syscall_handlers[0x3d] = lambda ee: ee.setreg(2, 0x01f80000 if (ee.reg(5) & 0xffffffff) == 0xffffffff else (ee.reg(4) + ee.reg(5)) & 0xffffffff)
ee.hook_function(0x1ac9d8, lambda ee: 0)
ee.run(entry, 0x1c4cc0)
print("crt0 done sp=%x" % ee.reg(29))
da.load_overlay(ee, os.path.join(da.GAME, 'OVERLAY', 'REL', 'DNAS.dec.bin'), 0x4c5380)
blobs = da.zdb_entries(os.path.join(da.GAME, 'RUN', 'RAW', 'APACHE00.ZDB'))
import collections as C, struct
ring = C.deque(maxlen=24); cnt=[0]
def code(uc, address, size, ud): ring.append(address); cnt[0]+=1
ee.uc.hook_add(UC_HOOK_CODE, code)
from capstone import *
md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64 | CS_MODE_LITTLE_ENDIAN)
def dump_ring():
    print("insns:", cnt[0])
    for a in ring:
        w = ee.r32(a); orig = ee.patched.get(a)
        ins = list(md.disasm(struct.pack('<I', orig if orig else w), a))
        print(f"  {a:08x} {w:08x} {'(patched '+hex(orig)+')' if orig else ''} {ins[0].mnemonic+' '+ins[0].op_str if ins else '??'}")
    print("  regs " + " ".join(f"r{i}={ee.reg(i):x}" for i in range(1,32)))
from unicorn import UC_HOOK_MEM_WRITE
wlog=[]
def onw(uc, access, address, size, value, ud):
    wlog.append(('guest', hex(uc.reg_read(UC_MIPS_REG_PC)), hex(address), size, hex(value), hex(ee.reg(31))))
ee.uc.hook_add(UC_HOOK_MEM_WRITE, onw, None, 0x5609b8, 0x5609c4)
_orig_write = ee.write
def logged_write(addr, data):
    if addr < 0x5609c4 and addr + len(data) > 0x5609b8:
        wlog.append(('api', hex(ring[-1]) if ring else '?', hex(addr), len(data), bytes(data)[:16].hex()))
    return _orig_write(addr, data)
ee.write = logged_write
textw=collections.Counter(); textw_first=[]
def ontw(uc, access, address, size, value, ud):
    pc=uc.reg_read(UC_MIPS_REG_PC); textw[pc]+=1
    if len(textw_first)<8: textw_first.append((hex(pc),hex(address),size,hex(value)))
ee.uc.hook_add(UC_HOOK_MEM_WRITE, ontw, None, 0x180000, 0x1d5600)
ee.uc.hook_add(UC_HOOK_MEM_WRITE, ontw, None, 0x4c5400, 0x4c5400+0x840c0)
cblog=[]
def on_cb(uc, address, size, ud):
    cblog.append((hex(ee.reg(4)&0xffffffff), hex(ee.reg(5)&0xffffffff), hex(ee.reg(31)&0xffffffff), hex(ee.r32(0x5609bc)), hex(ee.r32(0x5609b8))))
ee.uc.hook_add(UC_HOOK_CODE, on_cb, None, 0x539e00, 0x539e00)
try:
    r = ee.call(0x534830, ()); print("init ->", hex(r))
    print("writes so far:", wlog[-6:])
    BUF=0x01000000; OUT8=0xf00000; OUT4=0xf00010
    blob=blobs['ftscore']; ee.write(BUF, blob); ee.w64(OUT8,0)
    rc = sext32(ee.call(0x539d00, (len(blob), BUF, OUT8))); print("step1 ->", rc, hex(ee.r64(OUT8)))
    sz2 = sext32(ee.call(0x539d50, (len(blob), ee.r32(OUT8), BUF))); print("step2 ->", sz2)
    rc = sext32(ee.call(0x534848, (sz2, BUF, OUT4))); print("step3 ->", rc, hex(ee.r32(OUT4)))
    rc = sext32(ee.call(0x535018, (sz2, ee.r32(OUT4), BUF))); print("step4 ->", rc)
    print("guest writes into code:", sum(textw.values()), "by", [(hex(p),n) for p,n in textw.most_common(5)], textw_first)
except Exception as e:
    print("guest writes into code:", sum(textw.values()), "by", [(hex(p),n) for p,n in textw.most_common(5)], textw_first)
    print("ERR", repr(e), str(e)); print("callbacks:", cblog[:6], len(cblog)); dump_ring()
    from unicorn.mips_const import UC_MIPS_REG_CP0_STATUS
    print("CP0 status:", hex(ee.uc.reg_read(UC_MIPS_REG_CP0_STATUS)))
    for start in (0x53c480, 0x53c4b4, 0x53c4b8, 0x53c4bc, 0x53c4c0):
        try:
            ee.uc.emu_start(start, 0x53c4c8); print("fresh start at %x OK, pc=%x" % (start, ee.reg(29)))
        except Exception as e2:
            print("fresh start at %x -> %r" % (start, e2))
print("patched words read as data:", len(reads), "total reads", sum(reads.values()))
print("top readers:", [(hex(p), n) for p, n in readers.most_common(6)])
print("sample:", [hex(a) for a in list(reads)[:12]])
