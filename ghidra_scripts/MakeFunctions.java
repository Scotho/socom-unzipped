// Create functions at the given hex addresses (script args), then let analysis run.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.cmd.disassemble.DisassembleCommand;
public class MakeFunctions extends GhidraScript {
    @Override public void run() throws Exception {
        for (String a : getScriptArgs()) {
            Address addr = toAddr(Long.parseLong(a.replace("0x",""), 16));
            new DisassembleCommand(addr, null, true).applyTo(currentProgram, monitor);
            new CreateFunctionCmd(addr).applyTo(currentProgram, monitor);
            println("function at " + addr);
        }
    }
}
