// Create functions at every address listed in a text file (one hex address per line, '#'
// comments allowed).  Used to feed recomp/extra_functions.txt back into Ghidra so the
// functions get real bounds instead of "up to the next known function".
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import java.io.*;
import java.util.*;

public class MakeFunctionsFromFile extends GhidraScript {
    @Override
    public void run() throws Exception {
        String path = getScriptArgs().length > 0 ? getScriptArgs()[0] : "extra_functions.txt";
        FunctionManager fm = currentProgram.getFunctionManager();
        int created = 0, existing = 0, failed = 0;
        try (BufferedReader r = new BufferedReader(new FileReader(path))) {
            String line;
            while ((line = r.readLine()) != null) {
                int hash = line.indexOf('#');
                if (hash >= 0) line = line.substring(0, hash);
                line = line.trim();
                if (line.isEmpty()) continue;
                long v = Long.parseLong(line.replace("0x", ""), 16);
                Address a = toAddr(v);
                if (fm.getFunctionAt(a) != null) { existing++; continue; }
                Function containing = fm.getFunctionContaining(a);
                if (containing != null) {
                    // split: Ghidra will not create a function inside another; clear and retry
                    fm.removeFunction(containing.getEntryPoint());
                    new DisassembleCommand(containing.getEntryPoint(), null, true).applyTo(currentProgram, monitor);
                    new CreateFunctionCmd(containing.getEntryPoint()).applyTo(currentProgram, monitor);
                }
                new DisassembleCommand(a, null, true).applyTo(currentProgram, monitor);
                if (new CreateFunctionCmd(a).applyTo(currentProgram, monitor)) created++; else failed++;
            }
        }
        println("MakeFunctionsFromFile: created " + created + ", existing " + existing + ", failed " + failed);
    }
}
