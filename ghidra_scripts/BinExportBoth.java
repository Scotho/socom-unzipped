// Impose a function table on the current program, then write it as a .BinExport for BinDiff.
// Sprint 12, research note 49 (docs/research/49-bindiff-crosscheck.md), Goal 4 of the spec.
//
//   analyzeHeadless <projdir> <proj> -import <elf> -processor r5900:LE:32:default \
//       -scriptPath ghidra_scripts -preScript BinExportBoth.java <functions.csv> none <names> \
//       -postScript BinExportBoth.java <functions.csv> <out.BinExport> <names>
// docs/research/49-bindiff-crosscheck.md §1 has the two exact commands, one per image.
//
// <functions.csv>  Name,Start,End,Size (recomp/socom2_ghidra.csv's shape). [Start, End) is the body, cut
//                  at the next row's Start where two rows overlap (a Ghidra function cannot overlap
//                  another), so both images carry the PROJECT's boundaries, not Ghidra's guesses.
// <out.BinExport>  "none" imposes the table and writes nothing: run it so as a -preScript, and analysis then
//                  works from the table's entries (switch tables, references), and again as the
//                  -postScript that re-imposes it over what analysis added and exports.
// <names>          "keep": name each function from the csv (the demo, whose csv is its own .symtab);
//                  "auto": leave Ghidra's FUN_xxxxxxxx (r0001, so no hand name can reach BinDiff's
//                  name matcher and the diff stays a structural signal).
//
// Every function Ghidra's analysis made that the table does not have is removed first; then every row
// is disassembled inside its own body and created with that body. Needs the BinExport extension
// (google/binexport, Ghidra 11.0.3 build) installed in the Ghidra that runs it.
// @category PS2Recomp

import com.google.security.binexport.BinExportExporter;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.SourceType;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class BinExportBoth extends GhidraScript {

    private static final class Row {
        final String name;
        final long start;
        long end;
        Row(String name, long start, long end) { this.name = name; this.start = start; this.end = end; }
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 3) {
            printerr("BinExportBoth: usage <functions.csv> <out.BinExport> keep|auto");
            return;
        }
        boolean keepNames = args[2].equals("keep");
        List<Row> rows = new ArrayList<>();
        try (BufferedReader r = new BufferedReader(new FileReader(args[0]))) {
            String line = r.readLine(); // header
            while ((line = r.readLine()) != null) {
                String[] f = line.split(",");
                if (f.length < 3) continue;
                // A demo name can hold a comma (template arguments); Start/End are the last-but-one fields.
                int n = f.length;
                String name = String.join(",", java.util.Arrays.copyOfRange(f, 0, n - 3));
                rows.add(new Row(name, Long.parseLong(f[n - 3].replace("0x", ""), 16),
                                 Long.parseLong(f[n - 2].replace("0x", ""), 16)));
            }
        }
        rows.sort((a, b) -> Long.compare(a.start, b.start));
        int cut = 0;
        for (int i = 0; i + 1 < rows.size(); i++) {
            if (rows.get(i).end > rows.get(i + 1).start) { rows.get(i).end = rows.get(i + 1).start; cut++; }
        }
        Set<Long> starts = new HashSet<>();
        for (Row row : rows) starts.add(row.start);

        FunctionManager fm = currentProgram.getFunctionManager();
        Memory mem = currentProgram.getMemory();
        int removed = 0;
        List<Function> all = new ArrayList<>();
        FunctionIterator it = fm.getFunctions(true);
        while (it.hasNext()) all.add(it.next());
        for (Function f : all) {
            // Every function goes: the table's are re-made below with the table's body.
            if (!starts.contains(f.getEntryPoint().getOffset())) removed++;
            fm.removeFunction(f.getEntryPoint());
        }

        int created = 0, failed = 0, nobytes = 0, empty = 0, retried = 0;
        for (Row row : rows) {
            if (row.end <= row.start) { empty++; continue; }
            Address a = toAddr(row.start);
            Address last = toAddr(row.end - 1);
            if (!mem.contains(a) || !mem.contains(last)) { nobytes++; continue; }
            AddressSet body = new AddressSet(a, last);
            new DisassembleCommand(a, body, true).applyTo(currentProgram, monitor);
            String name = keepNames ? row.name.replace(' ', '_') : null;
            SourceType src = keepNames ? SourceType.IMPORTED : SourceType.DEFAULT;
            CreateFunctionCmd cmd = new CreateFunctionCmd(name, a, body, src);
            if (cmd.applyTo(currentProgram, monitor)) {
                created++;
            } else {
                // A name Ghidra refuses (an illegal character) must not cost the function its body.
                if (keepNames && new CreateFunctionCmd(null, a, body, SourceType.DEFAULT).applyTo(currentProgram, monitor)) {
                    created++;
                    continue;
                }
                // Analysis can lay data (a pointer, a string) over the entry; clear the data, keep the code.
                String why = cmd.getStatusMsg();
                Listing listing = currentProgram.getListing();
                DataIterator di = listing.getDefinedData(body, true);
                List<Address> data = new ArrayList<>();
                while (di.hasNext()) data.add(di.next().getMinAddress());
                for (Address d : data) listing.clearCodeUnits(d, d, false);
                new DisassembleCommand(a, body, true).applyTo(currentProgram, monitor);
                if (new CreateFunctionCmd(name, a, body, src).applyTo(currentProgram, monitor)) {
                    created++;
                    retried++;
                } else {
                    failed++;
                    if (failed <= 10) println("BinExportBoth: failed at " + a + ": " + why);
                }
            }
        }
        println(String.format("BinExportBoth: rows %d, bodies cut at the next start %d, Ghidra-only functions removed %d, "
                + "created %d (after clearing analysis data %d), failed %d, no bytes %d, empty %d", rows.size(), cut, removed,
                created, retried, failed, nobytes, empty));

        if (args[1].equals("none")) return; // the -preScript run: impose the table, let analysis follow
        File out = new File(args[1]);
        BinExportExporter exporter = new BinExportExporter();
        long t0 = System.currentTimeMillis();
        boolean ok = exporter.export(out, currentProgram, null, monitor);
        println(String.format("BinExportBoth: export %s -> %s, %d bytes, %.1f s", ok ? "ok" : "FAILED", out,
                out.length(), (System.currentTimeMillis() - t0) / 1000.0));
    }
}
