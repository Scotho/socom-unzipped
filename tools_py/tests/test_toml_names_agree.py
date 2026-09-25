"""Sprint 12 Goal 6's agreement test (Task 8; S12-R4, S12-R13, research/57 §2-§4).

The toml's `[general].stubs` is the key the recompiler reads (the handler selector); the sidecar
`recomp/socom2_names.csv` is the one home of a name. For every `name@addr` in `stubs` whose address has a sidecar
row, the sidecar's `Mangled` equals the toml name through the applier's alias key (S12-R24: lower-cased, a
leading `socom2_`, the project's own prefix, stripped; `socom2_RsaGenerateKeyPair` is `RSAGenerateKeyPair`), so
the two files cannot drift; an alias is counted. An address the sidecar does not name is skipped and counted.
Both files are tracked; no disc is read.
"""
import os
import unittest

from tools_py import name_provenance as npv
from tools_py.apply_names import alias_key
from tools_py import toml_stub_lever as tsl

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOML = os.path.join(ROOT, "recomp", "socom2.toml")
SIDECAR = os.path.join(ROOT, "recomp", "socom2_names.csv")


class TomlStubsAgreeWithTheSidecar(unittest.TestCase):
    def test_every_stubs_name_equals_the_sidecar_mangled_name(self):
        sidecar = npv.read(SIDECAR)
        stubs = [s for s in tsl.toml_names(TOML) if s[2] == "general.stubs"]
        self.assertGreater(len(stubs), 0, "no [general].stubs selector parsed")
        checked, skipped, alias, bad = 0, 0, 0, []
        for addr, name, _key, line in stubs:
            row = sidecar.get(addr)
            if row is None:
                skipped += 1
                continue
            checked += 1
            if row["Mangled"] == name:
                continue
            if alias_key(row["Mangled"]) == alias_key(name):
                alias += 1
            else:
                bad.append("0x%08x: recomp/socom2.toml line %d says %s, the sidecar's Mangled is %s (Name %s)"
                           % (addr, line, name, row["Mangled"], row["Name"]))
        print("\n[toml-names-agree] general.stubs: %d selectors; %d with a sidecar row (%d agree, %d differ); "
              "%d alias; %d without a sidecar row, skipped"
              % (len(stubs), checked, checked - len(bad), len(bad), alias, skipped))
        self.assertEqual(bad, [], "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
