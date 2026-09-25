"""Decrypt the update package the server writes to the memory card, by running the loader's
*memory-card* path under the same Unicorn harness tools_py/decrypt_apache.py uses for the disc.

Why a second entry point exists at all
--------------------------------------
`SCUS_972.75` has two package readers, and `main()` prefers the card one:

    FUN_001C4CC0 (main)
      -> FUN_001C5B30(port)      when mc<port>:/BASCUS-97275SOCOMII/APACHE00.ZDB is present
      -> FUN_001C59C0()          otherwise: the disc's RUN/RAW/APACHE00.ZDB

Both build the same 0xA0-byte-header + 0x5C-row archive walk and both hand each entry to
DNAS.BIN. What they do *not* share is the decryption sequence:

    disc  FUN_001C5DA0:  0x539D00 -> 0x539D50 -> 0x534848 -> 0x535018 -> inflate
    card  FUN_001C60B0:                          0x534848 -> 0x535018 -> inflate

The two missing calls are the signed-container layer. On the disc the package is additionally
wrapped for cdvd delivery: 0x539D00 parses that wrapper's header and answers the payload
length, and 0x539D50 decrypts the body in place. A package downloaded to the memory card never
went through cdvd, carries no such wrapper, and the loader accordingly never asks for one -- it
passes the bytes the card read returned, at the card read's own length, straight into the
content layer (0x534848 parses the content header and answers the inflated length; 0x535018
decrypts the deflate stream; the loader then inflates it into the overlay slot).

That is the whole difference. No second key, no extra file, no DNAS271.IMG, no console ID: the
same DNAS.BIN, the same two functions, one wrapper fewer.

Usage
-----
    python -m tools_py.decrypt_card_package <disc tree> <card APACHE00.ZDB> <out dir>

`<disc tree>` supplies SCUS_972.75 and OVERLAY/REL/DNAS.dec.bin -- the loader and the decryptor
are the console's, not the card's -- and `<out dir>` receives ftscore.bin and zsealetc.bin, the
same two names and the same shape scripts/build_revision.sh step 1 expects.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools_py.decrypt_apache import decrypt_package


def main(game, zdb, out):
    """Decrypt the card package `zdb` with the loader in the disc tree `game`; returns the
    two written paths."""
    return decrypt_package(game, zdb, out, card=True)


def cli(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('game', help='extracted disc tree (SCUS_972.75 + OVERLAY/REL/DNAS.dec.bin)')
    p.add_argument('zdb', help="the memory card's BASCUS-97275SOCOMII/APACHE00.ZDB")
    p.add_argument('out', help='directory for ftscore.bin and zsealetc.bin')
    a = p.parse_args(argv)
    for path in (os.path.join(a.game, 'SCUS_972.75'),
                 os.path.join(a.game, 'OVERLAY', 'REL', 'DNAS.dec.bin'),
                 a.zdb):
        if not os.path.isfile(path):
            p.error('missing input: %s' % path)
    written = main(a.game, a.zdb, a.out)
    for path in written:
        print('wrote', path, os.path.getsize(path), 'bytes')
    return 0


if __name__ == '__main__':
    raise SystemExit(cli())
