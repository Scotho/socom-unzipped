// Export decompiled C and a function list for the whole program.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.symbol.*;
import java.io.*;

public class ExportAll extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outDir = getScriptArgs().length > 0 ? getScriptArgs()[0] : ".";
        new File(outDir).mkdirs();
        DecompInterface ifc = new DecompInterface();
        DecompileOptions opts = new DecompileOptions();
        ifc.setOptions(opts);
        ifc.openProgram(currentProgram);
        FunctionManager fm = currentProgram.getFunctionManager();
        PrintWriter c = new PrintWriter(new FileWriter(new File(outDir, currentProgram.getName() + ".decomp.c")));
        PrintWriter list = new PrintWriter(new FileWriter(new File(outDir, currentProgram.getName() + ".functions.txt")));
        PrintWriter strs = new PrintWriter(new FileWriter(new File(outDir, currentProgram.getName() + ".strings.txt")));
        int n = 0;
        for (Function f : fm.getFunctions(true)) {
            list.printf("%s %08x %d\n", f.getName(), f.getEntryPoint().getOffset(), f.getBody().getNumAddresses());
            DecompileResults res = ifc.decompileFunction(f, 60, monitor);
            c.printf("// ---- %s @ %08x ----\n", f.getName(), f.getEntryPoint().getOffset());
            if (res != null && res.decompileCompleted() && res.getDecompiledFunction() != null) {
                c.println(res.getDecompiledFunction().getC());
            } else {
                c.println("// decompile failed");
            }
            n++;
            if (n % 100 == 0) println("decompiled " + n);
        }
        DataIterator di = currentProgram.getListing().getDefinedData(true);
        while (di.hasNext()) {
            Data d = di.next();
            if (d.hasStringValue()) strs.printf("%08x %s\n", d.getAddress().getOffset(), d.getValue().toString().replace("\n","\n"));
        }
        c.close(); list.close(); strs.close();
        println("exported " + n + " functions to " + outDir);
    }
}
