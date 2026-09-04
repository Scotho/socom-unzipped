// Create functions at code addresses referenced from data (vtables, function-pointer tables,
// callback registrations). Metrowerks C++ code calls thousands of virtual functions that no
// direct branch reaches, so plain flow analysis misses them.
// Heuristic: a 4-byte aligned word in an initialized non-executable block whose value points
// to a 4-byte aligned address inside an executable block, where no function already starts,
// and where the instruction is a plausible function start.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.listing.*;
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import java.util.*;

public class FindPointerTargets extends GhidraScript {
    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        FunctionManager fm = currentProgram.getFunctionManager();
        List<MemoryBlock> exec = new ArrayList<>();
        List<MemoryBlock> data = new ArrayList<>();
        for (MemoryBlock b : mem.getBlocks()) {
            if (!b.isInitialized()) continue;
            if (b.isExecute()) exec.add(b); else data.add(b);
        }
        // also scan executable blocks: Metrowerks puts jump tables / vtables in .text too
        List<MemoryBlock> scan = new ArrayList<>(data);
        scan.addAll(exec);
        Set<Long> candidates = new TreeSet<>();
        for (MemoryBlock b : scan) {
            long start = b.getStart().getOffset();
            long size = b.getSize();
            byte[] buf = new byte[(int) size];
            b.getBytes(b.getStart(), buf);
            for (int off = 0; off + 4 <= buf.length; off += 4) {
                long v = (buf[off] & 0xffL) | ((buf[off + 1] & 0xffL) << 8) | ((buf[off + 2] & 0xffL) << 16) | ((buf[off + 3] & 0xffL) << 24);
                if ((v & 3) != 0) continue;
                boolean inExec = false;
                for (MemoryBlock e : exec) {
                    if (v >= e.getStart().getOffset() && v < e.getEnd().getOffset()) { inExec = true; break; }
                }
                if (!inExec) continue;
                candidates.add(v);
            }
        }
        println("pointer candidates into code: " + candidates.size());
        int created = 0, skipped = 0;
        for (long v : candidates) {
            Address a = toAddr(v);
            if (fm.getFunctionAt(a) != null) continue;
            Function containing = fm.getFunctionContaining(a);
            if (containing != null) continue;              // mid-function pointer (label); leave it
            int w = mem.getInt(a) & 0xffffffff;
            if (!plausibleStart(w)) { skipped++; continue; }
            new DisassembleCommand(a, null, true).applyTo(currentProgram, monitor);
            if (new CreateFunctionCmd(a).applyTo(currentProgram, monitor)) created++;
        }
        println("created " + created + " functions from pointer targets, skipped " + skipped + " implausible");
    }

    private static boolean plausibleStart(int w) {
        int op = (w >>> 26);
        int rs = (w >>> 21) & 0x1f, rt = (w >>> 16) & 0x1f;
        if (w == 0) return false;
        if (op == 9 && rs == 29 && rt == 29) return true;                 // addiu sp,sp,imm
        if (op == 0x19 && rs == 29 && rt == 29) return true;              // daddiu sp,sp,imm
        if (op == 0x0f) return true;                                      // lui
        if (op == 0x23 || op == 0x37 || op == 0x2b || op == 0x3f) return true; // lw/ld/sw/sd
        if (op == 2 || op == 3) return true;                              // j/jal
        if (op == 0 && (w & 0x3f) == 8 && rs == 31) return true;          // jr ra
        if (op == 0 && (w & 0x3f) == 0x25) return true;                   // or/move
        if (op == 0 && (w & 0x3f) == 0x2d) return true;                   // daddu (move)
        if (op == 4 || op == 5 || op == 6 || op == 7 || op == 1) return true; // branches
        if (op == 9 || op == 0x0a || op == 0x0b || op == 0x0c || op == 0x0d || op == 0x0e) return true; // addiu/slti/sltiu/andi/ori/xori
        if (op == 0x11 || op == 0x12) return true;                        // COP1/COP2
        if (op == 0x1e || op == 0x1f) return true;                        // lq/sq
        if (op == 0 && (w & 0x3f) <= 0x3f && rs != 0) return true;        // other SPECIAL with rs
        return false;
    }
}
