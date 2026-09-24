"""How much of the 479 is new? Proposals against recomp/socom2.toml's name@addr list, and the
recomp/output name census. (Task 7 review, socom-pc-6c)

Run from the repo root:  python <this file>
"""
import collections
import csv
import os
import re

TOML = "recomp/socom2.toml"
RENAMES = "game/demo_symbol_renames.csv"
OURS = "recomp/socom2_ghidra.csv"
OUTPUT = "recomp/output"


def main() -> None:
    toml = open(TOML).read()
    in_toml = {"0x%08x" % int(a, 16): n
               for n, a in re.findall(r'"([^"@]+)@0x([0-9A-Fa-f]+)"', toml)}
    print(f"toml name@addr entries {len(in_toml)}")

    rows = list(csv.DictReader(open(RENAMES)))
    same, diff = 0, []
    for r in rows:
        a = r["Address"].lower()
        if a in in_toml:
            if in_toml[a] == r["Mangled"]:
                same += 1
            else:
                diff.append((a, in_toml[a], r["Mangled"]))
    print(f"proposals on toml-named addresses {same + len(diff)}: identical {same}, "
          f"different {len(diff)} {diff}")
    print(f"proposals with no toml name (genuinely new): {len(rows) - same - len(diff)}")

    named = [r["Name"] for r in csv.DictReader(open(OURS)) if not r["Name"].startswith("FUN_")]
    print(f"csv rows named: {len(named)} (of which address-derived caseD_/thunk_/LAB_: "
          f"{sum(1 for n in named if re.match(r'(caseD_|thunk_|LAB_|switchD)', n))})")

    if os.path.isdir(OUTPUT):
        files = os.listdir(OUTPUT)
        kinds = collections.Counter(
            "FUN_" if f.startswith("FUN_") else "sub_" if f.startswith("sub_")
            else "caseD_" if f.startswith("caseD_") else "named" for f in files if f.endswith(".cpp"))
        print(f"recomp/output .cpp census: {dict(kinds)} (total {sum(kinds.values())})")


if __name__ == "__main__":
    main()
