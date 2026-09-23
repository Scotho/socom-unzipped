"""Sprint 11 Task 10 (milestone R): the per-function fingerprint.

One routine, compiled once and linked twice, is the same instruction stream with different addresses in
it. This hashes the stream with every immediate that carries an address zeroed -- the `lui`/`addiu`/`ori`
halves of an address materialisation, the 26-bit `jal`/`j` target, a branch displacement -- and every
load/store displacement kept, because a structure offset is part of the code and a relink does not move
it. Two builds of the same routine therefore fingerprint equal; two different routines do not.

FNV-1a 64 over the masked little-endian words, returned as sixteen lowercase hex digits.

This module is deliberately tiny and dependency-free: tools_py/address_matcher.py matches two images with
it, and the demo-symbol import (a later task) hashes the demo's functions with the same function. Keep it
here rather than inlining it in either consumer -- the two must agree byte for byte or neither is usable.
"""

FNV_OFFSET, FNV_PRIME = 0xcbf29ce484222325, 0x100000001b3
IMM_ZEROED_OPCODES = {0x0f, 0x09, 0x0d, 0x03, 0x02, 0x04, 0x05, 0x06, 0x07, 0x01}   # lui addiu ori jal j beq bne blez bgtz regimm


def fingerprint(code: bytes) -> str:
    h = FNV_OFFSET
    for i in range(0, len(code) - 3, 4):
        w = int.from_bytes(code[i:i+4], "little")
        op = w >> 26
        if op in IMM_ZEROED_OPCODES:
            w &= 0xFFFF0000 if op not in (0x02, 0x03) else 0xFC000000
        for b in w.to_bytes(4, "little"):
            h = ((h ^ b) * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return "%016x" % h
