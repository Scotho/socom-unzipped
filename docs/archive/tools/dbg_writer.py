# ARCHIVED 2026-09-25 (Sprint 13 Task H4, harness audit H27) -- was tools_py/dbg_writer.py (no docstring of its own).
#   What it did: find which pcs write a range of the DNAS overlay while it decrypts. Last mattered 2026-09-04.
#   A bring-up probe of the APACHE00.ZDB decryption under the Unicorn harness, from the week the decryptor was
#   written. Its question closed at 329bbdac (2026-09-04, "APACHE00.ZDB decryption works end-to-end"); the
#   decryption is tools_py/decrypt_apache.py, run by tools_py/disc_to_elf.py and tested. It was moved here
#   from tools_py/ and no longer imports as a module (it sys.path-imports decrypt_apache from its own folder).
#   Nothing here is an instruction.
import sys, os, struct, collections
sys.path.insert(0, os.path.dirname(__file__))
import decrypt_apache as da
from ee_unicorn import EE, sext32
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.mips_const import UC_MIPS_REG_PC
ee = EE(verbose=False)
entry, gp = da.load_elf(ee, os.path.join(da.GAME, 'SCUS_972.75'))
da.load_overlay(ee, os.path.join(da.GAME, 'OVERLAY', 'REL', 'DNAS.dec.bin'), 0x4c5380)
ee.setreg(28, gp)
ee.syscall_handlers[0x64] = lambda ee: ee.setreg(2, 0)
da.install_sif_hle(ee)
SP=0x01fe0000; BUF=0x01000000; OUT8=0xf00000
blobs = da.zdb_entries(os.path.join(da.GAME, 'RUN', 'RAW', 'APACHE00.ZDB'))
writers=collections.Counter(); first=[]
def onw(uc, access, address, size, value, ud):
    pc=uc.reg_read(UC_MIPS_REG_PC)
    writers[pc]+=1
    if len(first)<5: first.append((hex(pc),hex(address),size,hex(value), hex(ee.reg(31))))
ee.uc.hook_add(UC_HOOK_MEM_WRITE, onw, None, 0x5375d0, 0x537678)
ee.call(0x534830, (), sp=SP)
blob=blobs['ftscore']; ee.write(BUF, blob); ee.w64(OUT8,0)
try:
    rc = sext32(ee.call(0x539d00, (len(blob), BUF, OUT8), sp=SP)); print("step1 ->", rc)
except Exception as e:
    print("ERR", e)
print("writers:", [(hex(p),n) for p,n in writers.most_common(8)]); print("first writes:", first)
