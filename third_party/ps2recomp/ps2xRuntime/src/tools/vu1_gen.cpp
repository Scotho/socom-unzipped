// vu1_gen: VU1 microcode image -> C++ "known program" (see ps2_vu1_ops.h and the dispatch in
// VU1Interpreter::run). Invoked by vu1_replay --gen <out.cpp> [--pchist hist.bin] <dumps...>.
//
// The generated function is a static unrolling of VU1Interpreter::runFast over the pairs of one
// 16 KB code image: every emitted pair keeps the fast path's semantics (stall on register ready
// cycles, flag/Q/P timing through the shared push/commit helpers, same-pair shadow rule, branch
// delay slots, E-bit end) with constant register indices, and anything the generator does not
// handle bails out to the interpreter with m_state.pc set, so unsupported pairs stay exact.
//
// Emitted pairs = closure of the entry pcs and the executed pcs (histogram) over fallthrough and
// direct branch targets; every other pc has a bail label, so indirect jumps (JR/JALR) into
// unemitted code hand back to the interpreter too.
#include <cstdio>
#include <cstdlib>
#include <array>
#include <cstring>
#include <set>
#include <string>
#include <vector>

#define private public
#include "runtime/ps2_vu1.h"
#undef private
#include "../lib/vu/ps2_vu1_detail.h"

namespace
{
    using Pair = VU1Interpreter::DecodedInstructionPair;
    using Usage = VU1Interpreter::InstructionUsage;

    constexpr uint32_t kPairs = 2048u;
    constexpr uint32_t kCodeSize = 0x4000u;

    struct Gen
    {
        const uint8_t *code = nullptr;
        std::vector<Pair> pairs;
        std::vector<bool> emitted;
        std::vector<bool> isTarget; // direct branch targets: commit points (loop heads)
        std::vector<bool> isUnknownEntry; // MSCAL entries and recorded computed-jump targets
        std::string out;
        uint64_t hash = 0;

        // Dataflow facts at the entry of every pair (min over all paths):
        //  slackVf[pc][reg*4+lane], slackVi[pc][reg]: pairs executed since the last write minus
        //    (latency-1); < 0 means a read there could stall (runtime ready check needed).
        //  normVf[pc][reg] bit (3-lane): the lane holds a normalized value (FMAC-family result).
        static constexpr int8_t kUnknownSlack = -3;
        static constexpr int8_t kSlackCap = 1;
        std::vector<std::array<int8_t, 128>> slackVf;
        std::vector<std::array<int8_t, 16>> slackVi;
        std::vector<std::array<uint8_t, 32>> normVf;
        bool analysisValid = false;

        void line(const std::string &s) { out += s; out += '\n'; }
        static std::string hex(uint32_t v)
        {
            char b[32];
            std::snprintf(b, sizeof(b), "0x%x", v);
            return b;
        }
        static std::string num(int64_t v) { return std::to_string(v); }

        // --- classification -------------------------------------------------------------------
        static bool isBranch(const Pair &p)
        {
            return !p.iBit && p.lowerUsage.pipeline == VU1Interpreter::PipelineBranch;
        }
        static bool isNopLower(uint32_t lo) { return lo == 0u || lo == 0x8000033Cu; }

        // Upper arithmetic decode (mirrors execUpper): returns false for non-arithmetic uppers.
        struct UpperArith
        {
            const char *kind; // vu1ops::ArithAdd...
            const char *src;  // Vu1Gen::SrcVt...
            uint32_t lane;
            bool toAcc;
            bool opmul;
            bool readsQ;
        };
        static bool upperArith(uint32_t up, UpperArith &a)
        {
            const uint8_t op = up & 0x3Fu;
            a = {nullptr, "Vu1Gen::SrcVt", 0u, false, false, false};
            auto bc = [&](const char *kind, uint32_t sel)
            {
                a.kind = kind;
                a.src = "Vu1Gen::SrcBc";
                a.lane = sel & 3u;
            };
            auto q = [&](const char *kind)
            {
                a.kind = kind;
                a.src = "Vu1Gen::SrcQ";
                a.readsQ = true;
            };
            auto i = [&](const char *kind)
            {
                a.kind = kind;
                a.src = "Vu1Gen::SrcI";
            };
            auto vt = [&](const char *kind)
            {
                a.kind = kind;
                a.src = "Vu1Gen::SrcVt";
            };
            if (op <= 0x2Fu)
            {
                if (op <= 0x03u) bc("vu1ops::ArithAdd", op);
                else if (op <= 0x07u) bc("vu1ops::ArithSub", op);
                else if (op <= 0x0Bu) bc("vu1ops::ArithMadd", op);
                else if (op <= 0x0Fu) bc("vu1ops::ArithMsub", op);
                else if (op >= 0x18u && op <= 0x1Bu) bc("vu1ops::ArithMul", op);
                else switch (op)
                {
                case 0x1C: q("vu1ops::ArithMul"); break;
                case 0x1E: i("vu1ops::ArithMul"); break;
                case 0x20: q("vu1ops::ArithAdd"); break;
                case 0x21: q("vu1ops::ArithMadd"); break;
                case 0x22: i("vu1ops::ArithAdd"); break;
                case 0x23: i("vu1ops::ArithMadd"); break;
                case 0x24: q("vu1ops::ArithSub"); break;
                case 0x25: q("vu1ops::ArithMsub"); break;
                case 0x26: i("vu1ops::ArithSub"); break;
                case 0x27: i("vu1ops::ArithMsub"); break;
                case 0x28: vt("vu1ops::ArithAdd"); break;
                case 0x29: vt("vu1ops::ArithMadd"); break;
                case 0x2A: vt("vu1ops::ArithMul"); break;
                case 0x2C: vt("vu1ops::ArithSub"); break;
                case 0x2D: vt("vu1ops::ArithMsub"); break;
                case 0x2E: vt("vu1ops::ArithMsub"); a.opmul = true; break;
                default: return false;
                }
                return a.kind != nullptr;
            }
            if (op < 0x3Cu)
                return false;
            const uint8_t sp = static_cast<uint8_t>((up & 3u) | ((up >> 4) & 0x7Cu));
            a.toAcc = true;
            if (sp <= 0x03u) bc("vu1ops::ArithAdd", sp);
            else if (sp <= 0x07u) bc("vu1ops::ArithSub", sp);
            else if (sp <= 0x0Bu) bc("vu1ops::ArithMadd", sp);
            else if (sp <= 0x0Fu) bc("vu1ops::ArithMsub", sp);
            else if (sp >= 0x18u && sp <= 0x1Bu) bc("vu1ops::ArithMul", sp);
            else switch (sp)
            {
            case 0x1C: q("vu1ops::ArithMul"); break;
            case 0x1E: i("vu1ops::ArithMul"); break;
            case 0x20: q("vu1ops::ArithAdd"); break;
            case 0x21: q("vu1ops::ArithMadd"); break;
            case 0x22: i("vu1ops::ArithAdd"); break;
            case 0x23: i("vu1ops::ArithMadd"); break;
            case 0x24: q("vu1ops::ArithSub"); break;
            case 0x25: q("vu1ops::ArithMsub"); break;
            case 0x26: i("vu1ops::ArithSub"); break;
            case 0x27: i("vu1ops::ArithMsub"); break;
            case 0x28: vt("vu1ops::ArithAdd"); break;
            case 0x29: vt("vu1ops::ArithMadd"); break;
            case 0x2A: vt("vu1ops::ArithMul"); break;
            case 0x2C: vt("vu1ops::ArithSub"); break;
            case 0x2D: vt("vu1ops::ArithMsub"); break;
            case 0x2E: vt("vu1ops::ArithMul"); a.opmul = true; break;
            default: return false;
            }
            return a.kind != nullptr;
        }
        // Non-arithmetic uppers with an inline helper: returns the expression producing the value
        // (or a statement for CLIP) and the destination register; false if execUpper is needed.
        struct UpperOther
        {
            std::string expr; // value expression, empty for CLIP
            uint8_t dstReg;   // fd or ft
            bool clip;
        };
        static bool upperOther(uint32_t up, UpperOther &o)
        {
            const uint8_t op = up & 0x3Fu;
            const uint8_t fs = FS(up), ft = FT(up), fd = FD(up);
            o = {"", 0u, false};
            auto mm = [&](bool isMax, const char *src, uint32_t lane)
            {
                o.expr = std::string("Vu1Gen::minmax<") + (isMax ? "true" : "false") + ", " + src + ", " + num(lane) + ", " + num(fs) + ", " + num(ft) + ">(vu, vf)";
                o.dstReg = fd;
            };
            if (op <= 0x2Fu)
            {
                if (op >= 0x10u && op <= 0x13u) mm(true, "Vu1Gen::MmBc", op & 3u);
                else if (op >= 0x14u && op <= 0x17u) mm(false, "Vu1Gen::MmBc", op & 3u);
                else if (op == 0x1Du) mm(true, "Vu1Gen::MmI", 0u);
                else if (op == 0x1Fu) mm(false, "Vu1Gen::MmI", 0u);
                else if (op == 0x2Bu) mm(true, "Vu1Gen::MmVt", 0u);
                else if (op == 0x2Fu) mm(false, "Vu1Gen::MmVt", 0u);
                else return false;
                return true;
            }
            if (op < 0x3Cu)
                return false;
            const uint8_t sp = static_cast<uint8_t>((up & 3u) | ((up >> 4) & 0x7Cu));
            static const uint32_t shifts[4] = {0u, 4u, 12u, 15u};
            if (sp >= 0x10u && sp <= 0x13u)
            {
                o.expr = "Vu1Gen::itof<" + num(shifts[sp - 0x10u]) + ", " + num(fs) + ">(vu, vf)";
                o.dstReg = ft;
                return true;
            }
            if (sp >= 0x14u && sp <= 0x17u)
            {
                o.expr = "Vu1Gen::ftoi<" + num(shifts[sp - 0x14u]) + ", " + num(fs) + ">(vu, vf)";
                o.dstReg = ft;
                return true;
            }
            if (sp == 0x1Du)
            {
                o.expr = "Vu1Gen::absVf<" + num(fs) + ">(vu, vf)";
                o.dstReg = ft;
                return true;
            }
            if (sp == 0x1Fu)
            {
                o.clip = true;
                return true;
            }
            return false;
        }

        static bool upperIsNop(uint32_t up)
        {
            const uint8_t op = up & 0x3Fu;
            if (op < 0x3Cu)
                return false;
            const uint8_t sp = static_cast<uint8_t>((up & 3u) | ((up >> 4) & 0x7Cu));
            return sp == 0x2Fu || sp == 0x30u;
        }

        // Lower op classes the generator emits inline; everything else goes through execLower.
        enum LowerClass
        {
            LNop, LInline, LBranch, LFallback
        };
        static LowerClass lowerClass(uint32_t lo, bool iBit)
        {
            if (iBit || isNopLower(lo))
                return LNop;
            const uint8_t opHi = static_cast<uint8_t>((lo >> 25) & 0x7Fu);
            switch (opHi)
            {
            case 0x00: case 0x01: case 0x04: case 0x05: case 0x08: case 0x09:
            case 0x10: case 0x12: case 0x13: case 0x14: case 0x16: case 0x17:
            case 0x18: case 0x1A: case 0x1B: case 0x1C:
                return LInline;
            case 0x11: case 0x15: // FCSET / FSSET
                return LInline;
            case 0x20: case 0x21: case 0x24: case 0x25: case 0x28: case 0x29:
            case 0x2C: case 0x2D: case 0x2E: case 0x2F:
                return LBranch;
            case 0x40:
                break;
            default:
                return LFallback;
            }
            const uint8_t funct = lo & 0x3Fu;
            if (funct == 0x30u || funct == 0x31u || funct == 0x32u || funct == 0x34u || funct == 0x35u)
                return LInline;
            if (funct < 0x3Cu)
                return LFallback;
            const uint8_t f2 = static_cast<uint8_t>((lo & 3u) | ((lo >> 4) & 0x7Cu));
            switch (f2)
            {
            case 0x30: case 0x31: case 0x34: case 0x35: case 0x36: case 0x37:
            case 0x38: case 0x39: case 0x3A:
            case 0x3B: case 0x3C: case 0x3D: case 0x3E: case 0x3F:
            case 0x64: case 0x68: case 0x69: case 0x6C: case 0x7B:
                return LInline;
            default:
                return LFallback;
            }
        }
        // Lower ops that read MAC/STATUS/CLIP/P or (re)queue Q/P: commit before them.
        static bool lowerNeedsCommit(uint32_t lo, bool iBit)
        {
            if (iBit || isNopLower(lo))
                return false;
            const uint8_t opHi = static_cast<uint8_t>((lo >> 25) & 0x7Fu);
            if (opHi >= 0x10u && opHi <= 0x1Cu)
                return true;
            if (opHi != 0x40u)
                return false;
            const uint8_t funct = lo & 0x3Fu;
            if (funct < 0x3Cu)
                return false;
            const uint8_t f2 = static_cast<uint8_t>((lo & 3u) | ((lo >> 4) & 0x7Cu));
            return f2 == 0x38u || f2 == 0x39u || f2 == 0x3Au || f2 == 0x3Bu || f2 == 0x64u || f2 >= 0x70u;
        }
        static bool lowerPushes(uint32_t lo, bool iBit)
        {
            if (iBit)
                return false;
            const uint8_t opHi = static_cast<uint8_t>((lo >> 25) & 0x7Fu);
            return opHi == 0x11u || opHi == 0x15u;
        }
        static bool upperPushes(uint32_t up)
        {
            UpperArith a;
            if (upperArith(up, a))
                return DEST(up) != 0u;
            const uint8_t op = up & 0x3Fu;
            if (op < 0x3Cu)
                return false;
            const uint8_t sp = static_cast<uint8_t>((up & 3u) | ((up >> 4) & 0x7Cu));
            return sp == 0x1Fu; // CLIP
        }

        // --- emission helpers -----------------------------------------------------------------
        void emitReady(const Pair &p, uint32_t pc, const std::string &bailExtra)
        {
            const size_t mark = out.size();
            line("    ready = vu.m_cycle;");
            if (p.lowerUsage.pipeline == VU1Interpreter::PipelineXgkick)
                line("    if (vu.m_xgkick.active) ready = vu.m_cycle + 1u;");
            const Usage *us[2] = {&p.upperUsage, &p.lowerUsage};
            for (const Usage *u : us)
            {
                for (uint32_t i = 0; i < u->vfReadCount; ++i)
                {
                    const uint8_t lanes = stallLanes(pc, u->vfRead[i].reg, u->vfRead[i].lanes);
                    if (lanes)
                        line("    Vu1Gen::readyVf<" + num(u->vfRead[i].reg) + ", " + num(lanes) + ">(vu, vf, ready);");
                }
                uint32_t m = u->viRead & 0xFFFEu;
                while (m)
                {
                    const uint32_t r = __builtin_ctz(m);
                    if (viMayStall(pc, static_cast<uint8_t>(r)))
                        line("    Vu1Gen::readyVi<" + num(r) + ">(vu, vf, ready);");
                    m &= m - 1u;
                }
            }
            if (p.lowerUsage.pipeline == VU1Interpreter::PipelineFdiv || p.lowerUsage.waitQ)
                line("    if (vu.m_fdiv.valid) ready = std::max(ready, vu.m_fdiv.readyCycle);");
            if (p.lowerUsage.pipeline == VU1Interpreter::PipelineEfu)
                line("    ready = std::max(ready, vu.m_efuResourceReady);");
            if (p.lowerUsage.waitP)
                line("    for (const auto &e : vu.m_efu) if (e.valid) ready = std::max(ready, e.readyCycle);");
            // Nothing emitted after "ready = m_cycle": no operand can stall here.
            if (out.size() == mark + std::strlen("    ready = vu.m_cycle;\n"))
            {
                out.resize(mark);
                return;
            }
            line("    if (ready > vu.m_cycle) { if (ready >= budgetEnd) { vu.m_cycle = budgetEnd; " + bailExtra + "vu.m_state.pc = " + hex(pc) + "; goto bail; } vu.m_cycle = ready; }");
        }

        void emitMarks(const Pair &p)
        {
            const auto &lw = p.lowerUsage.vfWrite;
            if (lw.reg != 0u && p.suppressedLowerVf != lw.reg)
            {
                const uint32_t lat = p.lowerUsage.vfLatency ? p.lowerUsage.vfLatency : p.lowerUsage.latency;
                line("    Vu1Gen::markVf<" + num(lw.reg) + ", " + num(lw.lanes) + ", " + num(lat) + ">(vu, vf);");
            }
            const auto &uw = p.upperUsage.vfWrite;
            if (uw.reg != 0u)
            {
                const uint32_t lat = p.upperUsage.vfLatency ? p.upperUsage.vfLatency : p.upperUsage.latency;
                line("    Vu1Gen::markVf<" + num(uw.reg) + ", " + num(uw.lanes) + ", " + num(lat) + ">(vu, vf);");
            }
            uint32_t m = p.lowerUsage.viWrite & 0xFFFEu;
            if (m)
            {
                const uint32_t lat = p.lowerUsage.viLatency ? p.lowerUsage.viLatency : p.lowerUsage.latency;
                while (m)
                {
                    line("    Vu1Gen::markVi<" + num(__builtin_ctz(m)) + ", " + num(lat) + ">(vu, vf);");
                    m &= m - 1u;
                }
            }
        }

        static std::string vi(uint8_t r) { return r == 0u ? std::string("0") : "vu.m_state.vi[" + num(r) + "]"; }
        static std::string addrOf(uint8_t base, int32_t imm)
        {
            return "Vu1Gen::dataAddress(" + vi(base) + (imm ? " + (" + num(imm) + ")" : "") + ")";
        }

        int branchVar = 0; // 2: branch ops write taken2/target2 (second branch of a pair of branches)

        // Inline lower op. `suppressVf` drops its VF write (same register as the upper's result).
        // Branch ops set `taken`/`target` instead of jumping. Returns false if not inline-able.
        bool emitLowerInline(uint32_t lo, uint32_t pc, bool suppressVf)
        {
            const std::string TK = branchVar == 2 ? "taken2" : "taken";
            const std::string TG = branchVar == 2 ? "target2" : "target";
            const uint8_t opHi = static_cast<uint8_t>((lo >> 25) & 0x7Fu);
            const uint8_t ft = FT(lo), fs = FS(lo), it = VIT(lo), is = VIS(lo), id = VID(lo), dest = DEST(lo);
            const int32_t imm11 = IMM11(lo);
            const std::string sdest = num(dest);
            switch (opHi)
            {
            case 0x00: // LQ
                if (!suppressVf)
                    line("    Vu1Gen::loadVf<" + num(ft) + ", " + sdest + ">(vu, vf, " + addrOf(is, imm11) + ");");
                return true;
            case 0x01: // SQ
                line("    Vu1Gen::storeVfMem<" + num(fs) + ", " + sdest + ">(vu, vf, " + addrOf(it, imm11) + ");");
                return true;
            case 0x04: // ILW
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, Vu1Gen::loadWord<" + sdest + ">(vu, vf, " + addrOf(is, imm11) + "));");
                return true;
            case 0x05: // ISW
                line("    Vu1Gen::storeWord<" + sdest + ">(vu, vf, " + addrOf(is, imm11) + ", " + vi(it) + ");");
                return true;
            case 0x08: // IADDIU
            case 0x09: // ISUBIU
            {
                const int16_t imm = static_cast<int16_t>(static_cast<int16_t>(lo & 0x7FFu) | ((lo >> 10) & 0x7800u));
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int16_t)(" + vi(is) + (opHi == 0x08u ? " + " : " - ") + num(imm) + "));");
                return true;
            }
            case 0x10: // FCEQ
                line("    vu.m_state.vi[1] = ((vu.m_state.clip & 0xFFFFFFu) == " + hex(lo & 0xFFFFFFu) + "u) ? 1 : 0;");
                return true;
            case 0x11: // FCSET
                line("    vu.queueFcset(" + hex(lo & 0xFFFFFFu) + "u);");
                return true;
            case 0x12: // FCAND
                line("    vu.m_state.vi[1] = ((vu.m_state.clip & " + hex(lo & 0xFFFFFFu) + "u) != 0u) ? 1 : 0;");
                return true;
            case 0x13: // FCOR
                line("    vu.m_state.vi[1] = ((vu.m_state.clip | " + hex(lo & 0xFFFFFFu) + "u) == 0xFFFFFFu) ? 1 : 0;");
                return true;
            case 0x14: // FSEQ
            case 0x16: // FSAND
            case 0x17: // FSOR
            {
                const uint32_t imm12 = (((lo >> 21) & 0x1u) << 11) | (lo & 0x7FFu);
                if (opHi == 0x14u)
                    line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, ((vu.m_state.status & 0xFFFu) == " + hex(imm12) + "u) ? 1 : 0);");
                else if (opHi == 0x16u)
                    line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int32_t)((vu.m_state.status & 0xFFFu) & " + hex(imm12) + "u));");
                else
                    line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int32_t)((vu.m_state.status & 0xFFFu) | " + hex(imm12) + "u));");
                return true;
            }
            case 0x15: // FSSET
            {
                const uint32_t imm12 = (((lo >> 21) & 0x1u) << 11) | (lo & 0x7FFu);
                line("    vu.queueFsset(" + hex(imm12) + "u);");
                return true;
            }
            case 0x18: // FMEQ
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, ((vu.m_state.mac & 0xFFFFu) == (uint32_t)(uint16_t)" + vi(is) + ") ? 1 : 0);");
                return true;
            case 0x1A: // FMAND
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int32_t)(vu.m_state.mac & (uint32_t)(uint16_t)" + vi(is) + "));");
                return true;
            case 0x1B: // FMOR
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int32_t)(vu.m_state.mac | (uint32_t)(uint16_t)" + vi(is) + "));");
                return true;
            case 0x1C: // FCGET
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int32_t)(vu.m_state.clip & 0x0FFFu));");
                return true;
            // branches: condition and target only
            case 0x20: // B
                line("    " + TK + " = true; " + TG + " = " + hex((pc + 8u + imm11 * 8) & 0x3FFFu) + "u;");
                return true;
            case 0x21: // BAL
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, " + num((pc + 16u) / 8u) + ");");
                line("    " + TK + " = true; " + TG + " = " + hex((pc + 8u + imm11 * 8) & 0x3FFFu) + "u;");
                return true;
            case 0x24: // JR
                line("    " + TK + " = true; " + TG + " = ((uint32_t)(uint16_t)Vu1Gen::branchVi<" + num(is) + ">(vu, vf) * 8u) & 0x3FFFu;");
                return true;
            case 0x25: // JALR
                line("    " + TG + " = ((uint32_t)(uint16_t)Vu1Gen::branchVi<" + num(is) + ">(vu, vf) * 8u) & 0x3FFFu; " + TK + " = true;");
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, " + num((pc + 16u) / 8u) + ");");
                return true;
            case 0x28: case 0x29: case 0x2C: case 0x2D: case 0x2E: case 0x2F:
            {
                const std::string a = "(int16_t)Vu1Gen::branchVi<" + num(is) + ">(vu, vf)";
                const std::string b = "(int16_t)Vu1Gen::branchVi<" + num(it) + ">(vu, vf)";
                std::string cond;
                switch (opHi)
                {
                case 0x28: cond = a + " == " + b; break;
                case 0x29: cond = a + " != " + b; break;
                case 0x2C: cond = a + " < 0"; break;
                case 0x2D: cond = a + " > 0"; break;
                case 0x2E: cond = a + " <= 0"; break;
                default: cond = a + " >= 0"; break;
                }
                line("    " + TK + " = (" + cond + "); " + TG + " = " + hex((pc + 8u + imm11 * 8) & 0x3FFFu) + "u;");
                return true;
            }
            case 0x40:
                break;
            default:
                return false;
            }
            const uint8_t funct = lo & 0x3Fu;
            switch (funct)
            {
            case 0x30: line("    Vu1Gen::setVi<" + num(id) + ">(vu, vf, (int16_t)(" + vi(is) + " + " + vi(it) + "));"); return true;
            case 0x31: line("    Vu1Gen::setVi<" + num(id) + ">(vu, vf, (int16_t)(" + vi(is) + " - " + vi(it) + "));"); return true;
            case 0x32:
            {
                const int16_t imm5 = static_cast<int16_t>((static_cast<int32_t>((lo >> 6) & 0x1Fu) << 27) >> 27);
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int16_t)(" + vi(is) + " + " + num(imm5) + "));");
                return true;
            }
            case 0x34: line("    Vu1Gen::setVi<" + num(id) + ">(vu, vf, " + vi(is) + " & " + vi(it) + ");"); return true;
            case 0x35: line("    Vu1Gen::setVi<" + num(id) + ">(vu, vf, " + vi(is) + " | " + vi(it) + ");"); return true;
            default:
                break;
            }
            if (funct < 0x3Cu)
                return false;
            const uint8_t f2 = static_cast<uint8_t>((lo & 3u) | ((lo >> 4) & 0x7Cu));
            switch (f2)
            {
            case 0x30: // MOVE
                if (!suppressVf && ft != 0u)
                    line("    { float t[4]; std::memcpy(t, vf[" + num(fs) + "], 16); VU1Interpreter::applyDest(vf[" + num(ft) + "], t, " + sdest + "); }");
                return true;
            case 0x31: // MR32
                if (!suppressVf && ft != 0u)
                    line("    { const float *s = vf[" + num(fs) + "]; float t[4] = {s[1], s[2], s[3], s[0]}; VU1Interpreter::applyDest(vf[" + num(ft) + "], t, " + sdest + "); }");
                return true;
            case 0x34: // LQI
                if (!suppressVf)
                    line("    Vu1Gen::loadVf<" + num(ft) + ", " + sdest + ">(vu, vf, Vu1Gen::dataAddress((uint16_t)" + vi(is) + "));");
                line("    Vu1Gen::setVi<" + num(is) + ">(vu, vf, (int16_t)(" + vi(is) + " + 1));");
                return true;
            case 0x35: // SQI
                line("    Vu1Gen::storeVfMem<" + num(fs) + ", " + sdest + ">(vu, vf, Vu1Gen::dataAddress((uint16_t)" + vi(it) + "));");
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int16_t)(" + vi(it) + " + 1));");
                return true;
            case 0x36: // LQD
                line("    Vu1Gen::setVi<" + num(is) + ">(vu, vf, (int16_t)(" + vi(is) + " - 1));");
                if (!suppressVf)
                    line("    Vu1Gen::loadVf<" + num(ft) + ", " + sdest + ">(vu, vf, Vu1Gen::dataAddress((uint16_t)" + vi(is) + "));");
                return true;
            case 0x37: // SQD
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int16_t)(" + vi(it) + " - 1));");
                line("    Vu1Gen::storeVfMem<" + num(fs) + ", " + sdest + ">(vu, vf, Vu1Gen::dataAddress((uint16_t)" + vi(it) + "));");
                return true;
            case 0x38: // DIV
                line("    Vu1Gen::div<" + num(fs) + ", " + num((lo >> 21) & 3u) + ", " + num(ft) + ", " + num((lo >> 23) & 3u) + ">(vu, vf);");
                return true;
            case 0x39: // SQRT
                line("    Vu1Gen::sqrtQ<" + num(ft) + ", " + num((lo >> 23) & 3u) + ">(vu, vf);");
                return true;
            case 0x3A: // RSQRT
                line("    Vu1Gen::rsqrt<" + num(fs) + ", " + num((lo >> 21) & 3u) + ", " + num(ft) + ", " + num((lo >> 23) & 3u) + ">(vu, vf);");
                return true;
            case 0x3B: // WAITQ
            case 0x7B: // WAITP
                return true;
            case 0x3C: // MTIR
                line("    { uint32_t f; std::memcpy(&f, &vf[" + num(fs) + "][" + num((lo >> 21) & 3u) + "], 4); Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int32_t)(int16_t)(f & 0xFFFFu)); }");
                return true;
            case 0x3D: // MFIR
                if (!suppressVf && ft != 0u)
                    line("    { int32_t v = (int32_t)(int16_t)(" + vi(is) + " & 0xFFFF); float t[4]; std::memcpy(&t[0], &v, 4); t[1] = t[2] = t[3] = t[0]; VU1Interpreter::applyDest(vf[" + num(ft) + "], t, " + sdest + "); }");
                return true;
            case 0x3E: // ILWR
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, Vu1Gen::loadWord<" + sdest + ">(vu, vf, Vu1Gen::dataAddress((uint16_t)" + vi(is) + ")));");
                return true;
            case 0x3F: // ISWR
                line("    Vu1Gen::storeWord<" + sdest + ">(vu, vf, Vu1Gen::dataAddress((uint16_t)" + vi(is) + "), " + vi(it) + ");");
                return true;
            case 0x64: // MFP
                if (!suppressVf && ft != 0u)
                    line("    { float t[4] = {vu.m_state.p, vu.m_state.p, vu.m_state.p, vu.m_state.p}; VU1Interpreter::applyDest(vf[" + num(ft) + "], t, " + sdest + "); }");
                return true;
            case 0x68: // XTOP
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int32_t)(vu.m_state.top & 0x3FFu));");
                return true;
            case 0x69: // XITOP
                line("    Vu1Gen::setVi<" + num(it) + ">(vu, vf, (int32_t)(vu.m_state.itop & 0x3FFu));");
                return true;
            case 0x6C: // XGKICK
                line("    g_xgkickDecoded.fetch_add(1, std::memory_order_relaxed);");
                line("    vu.startXgkick((uint32_t)(uint16_t)" + vi(is) + ");");
                return true;
            default:
                return false;
            }
        }

        // ", NormS, NormT" for Vu1Gen::fmac from the read lanes' normalization facts.
        std::string fmacNormArgs(uint32_t pc, const Pair &p, const UpperArith &ua) const
        {
            const uint8_t fs = FS(p.upper), ft = FT(p.upper), dest = DEST(p.upper);
            uint8_t sLanes = dest, tLanes = 0u;
            if (ua.opmul)
            {
                sLanes = 0xFu; // xyz products plus the w product folded into the OPMSUB sticky
                tLanes = 0xFu;
            }
            else if (std::strcmp(ua.src, "Vu1Gen::SrcVt") == 0)
                tLanes = dest;
            else if (std::strcmp(ua.src, "Vu1Gen::SrcBc") == 0)
                tLanes = static_cast<uint8_t>(1u << (3u - ua.lane));
            const bool normS = lanesNormalized(pc, fs, sLanes);
            const bool normT = tLanes == 0u || lanesNormalized(pc, ft, tLanes);
            return std::string(", ") + (normS ? "false" : "true") + ", " + (normT ? "false" : "true");
        }

        // The pair body without control flow. `role`: 0 = normal, 1 = inline delay slot of a branch
        // (bail must re-arm the pending branch), 2 = final pair after an E bit (bail must set ebit).
        void emitBody(uint32_t pc, int role, uint32_t &pushCounter, bool forceCommit)
        {
            const Pair &p = pairs[pc >> 3];
            std::string bailExtra;
            if (role == 1)
                bailExtra = "if (taken) { vu.m_state.branchPending = true; vu.m_state.branchTarget = target; vu.m_state.branchDelay = 0u; } ";
            else if (role == 2)
                bailExtra = "vu.m_state.ebit = true; ";
            // The cycle budget is a runaway guard: checked at every branch (loops cannot escape it),
            // at every stall and at entry, not on every straight-line pair.
            if (role == 0 && isBranch(p))
                line("    if (vu.m_cycle >= budgetEnd) { " + bailExtra + "vu.m_state.pc = " + hex(pc) + "; goto bail; }");
            emitReady(p, pc, bailExtra);

            UpperArith ua;
            const bool upArith = upperArith(p.upper, ua);
            const bool upNop = upperIsNop(p.upper);
            UpperOther uo;
            const bool upOther = !upArith && !upNop && upperOther(p.upper, uo);
            const LowerClass lc = lowerClass(p.lower, p.iBit);
            const bool pushes = upperPushes(p.upper) || lowerPushes(p.lower, p.iBit);
            const bool needsCommit = forceCommit || (upArith && ua.readsQ) || lowerNeedsCommit(p.lower, p.iBit) ||
                                     (pushes && pushCounter >= 16u);
            if (needsCommit)
            {
                line("    if (vu.m_cycle >= vu.m_nextReadyCycle) vu.fastCommit();");
                pushCounter = 0u;
            }
            if (pushes)
                ++pushCounter;
            line("    ++pairs;");

            uint8_t writtenVi = 0u;
            const uint32_t viWriteMask = p.lowerUsage.viWrite & 0xFFFEu;
            if (viWriteMask)
            {
                writtenVi = static_cast<uint8_t>(__builtin_ctz(viWriteMask));
                line("    oldVi = vu.m_state.vi[" + num(writtenVi) + "];");
            }

            const uint8_t fd = FD(p.upper), ft = FT(p.upper), fs = FS(p.upper), dest = DEST(p.upper);
            const bool shadow = p.upperVfShadowReg != 0u;
            const bool lowerFallback = lc == LFallback;
            const bool upperFallback = !upArith && !upNop && !upOther;
            bool resetVf0 = false;
            bool resetVi0 = false;

            if (p.iBit)
            {
                if (upArith)
                {
                    line("    up = Vu1Gen::fmac<" + std::string(ua.kind) + ", " + ua.src + ", " + num(ua.lane) + ", " + num(dest) + ", " + num(fs) + ", " + num(ft) + ", " + (ua.opmul ? "true" : "false") + fmacNormArgs(pc, p, ua) + ">(vu, vf, acc);");
                    if (ua.toAcc)
                        line("    Vu1Gen::storeAcc<" + num(dest) + ">(acc, up);");
                    else
                        line("    Vu1Gen::storeVf<" + num(fd) + ", " + num(dest) + ">(vu, vf, up);");
                }
                else if (upOther)
                {
                    if (uo.clip)
                        line("    Vu1Gen::clip<" + num(fs) + ", " + num(ft) + ">(vu, vf);");
                    else
                        line("    Vu1Gen::storeVf<" + num(uo.dstReg) + ", " + num(dest) + ">(vu, vf, " + uo.expr + ");");
                }
                else if (!upNop)
                {
                    line("    _mm_storeu_ps(vu.m_state.acc, acc); Vu1Gen::execUpper(vu, vf, " + hex(p.upper) + "u); acc = _mm_loadu_ps(vu.m_state.acc);");
                    resetVf0 = true;
                }
                line("    { const uint32_t ib = " + hex(p.lower) + "u; float f; std::memcpy(&f, &ib, 4); vu.m_state.i = VU1Interpreter::normalizeOperand(f); }");
            }
            else if (shadow && (upperFallback || lowerFallback))
            {
                // Generic same-pair dance around the interpreter's own handlers (rare).
                line("    _mm_storeu_ps(vu.m_state.acc, acc);");
                line("    { float oldVf[4], upperVf[4]; std::memcpy(oldVf, vf[" + num(p.upperVfShadowReg) + "], 16);");
                line("      Vu1Gen::execUpper(vu, vf, " + hex(p.upper) + "u); std::memcpy(upperVf, vf[" + num(p.upperVfShadowReg) + "], 16);");
                line("      std::memcpy(vf[" + num(p.upperVfShadowReg) + "], oldVf, 16);");
                if (lc == LBranch || lc == LInline)
                    emitLowerInline(p.lower, pc, false);
                else if (lc == LFallback)
                    line("      Vu1Gen::execLower(vu, vf, " + hex(p.lower) + "u);");
                line("      std::memcpy(vf[" + num(p.upperVfShadowReg) + "], upperVf, 16); }");
                line("    acc = _mm_loadu_ps(vu.m_state.acc);");
                resetVf0 = true;
                resetVi0 = true;
            }
            else
            {
                // Upper first (its flag entry precedes a same-pair FSSET/FCSET), its store after the lower.
                bool deferred = false;
                uint8_t deferredReg = fd;
                if (upArith)
                {
                    line("    up = Vu1Gen::fmac<" + std::string(ua.kind) + ", " + ua.src + ", " + num(ua.lane) + ", " + num(dest) + ", " + num(fs) + ", " + num(ft) + ", " + (ua.opmul ? "true" : "false") + fmacNormArgs(pc, p, ua) + ">(vu, vf, acc);");
                    deferred = true;
                }
                else if (upOther)
                {
                    if (uo.clip)
                        line("    Vu1Gen::clip<" + num(fs) + ", " + num(ft) + ">(vu, vf);");
                    else
                    {
                        line("    up = " + uo.expr + ";");
                        deferred = true;
                        deferredReg = uo.dstReg;
                    }
                }
                else if (upperFallback)
                {
                    line("    _mm_storeu_ps(vu.m_state.acc, acc); Vu1Gen::execUpper(vu, vf, " + hex(p.upper) + "u); acc = _mm_loadu_ps(vu.m_state.acc);");
                    resetVf0 = true;
                }
                const bool suppress = p.suppressedLowerVf != 0u && p.suppressedLowerVf == p.lowerUsage.vfWrite.reg;
                if (lc == LInline || lc == LBranch)
                {
                    if (!emitLowerInline(p.lower, pc, suppress))
                    {
                        std::fprintf(stderr, "vu1_gen: internal: lower %08x at %x not inline-able\n", p.lower, pc);
                        std::exit(3);
                    }
                }
                else if (lc == LFallback)
                {
                    line("    Vu1Gen::execLower(vu, vf, " + hex(p.lower) + "u);"); // lowers never touch ACC
                    resetVf0 = true;
                    resetVi0 = true;
                }
                if (deferred)
                {
                    if (upArith && ua.toAcc)
                        line("    Vu1Gen::storeAcc<" + num(dest) + ">(acc, up);");
                    else
                        line("    Vu1Gen::storeVf<" + num(deferredReg) + ", " + num(dest) + ">(vu, vf, up);");
                }
            }

            // The bypass flag is read only by the branch that follows; every pair executed right
            // before a branch (the previous pair in address order, or a delay slot) writes it, the
            // others may leave it stale (the interpreter rewrites it on every pair after a hand-back).
            const bool nextIsBranch = isBranch(pairs[nextPc(pc) >> 3]);
            if (writtenVi != 0u && p.lowerUsage.delaysNextBranchRead)
                line("    vu.m_viBranchBackupValue = oldVi; vu.m_viBranchBackupReg = " + num(writtenVi) + "; vu.m_viBranchBackupValid = true;");
            else if (nextIsBranch || role == 1)
                line("    vu.m_viBranchBackupValid = false;");
            emitMarks(p);
            if (resetVf0)
                line("    _mm_storeu_ps(vf[0], _mm_set_ps(1.0f, 0.0f, 0.0f, 0.0f));");
            if (resetVi0)
                line("    vu.m_state.vi[0] = 0;");
            line("    ++vu.m_cycle;");
            if (p.lowerUsage.pipeline == VU1Interpreter::PipelineXgkick)
            {
                // A stop (XGKICK overrun) ends the interpreter loop after this pair: leave the state
                // exactly where runFast would (branch resolved / program ended).
                if (role == 1)
                    line("    if (vu.m_stopRequested) { vu.m_state.pc = taken ? target : " + hex(nextPc(pc)) + "u; goto bail; }");
                else if (role == 2)
                    line("    if (vu.m_stopRequested) { vu.m_state.pc = " + hex(nextPc(pc)) + "u; goto end; }");
                else
                    line("    if (vu.m_stopRequested) { vu.m_state.pc = " + hex(nextPc(pc)) + "u; goto bail; }");
            }
        }

        static uint32_t nextPc(uint32_t pc) { return (pc + 8u) >= kCodeSize ? 0u : pc + 8u; }

        bool supported(uint32_t pc) const
        {
            const Pair &p = pairs[pc >> 3];
            if (p.upperUsage.reserved || p.lowerUsage.reserved)
                return false;
            if (p.dBit || p.tBit)
                return false; // D/T halts run in the interpreter (dispatch refuses when enabled)
            if (isBranch(p))
            {
                const Pair &d = pairs[nextPc(pc) >> 3];
                if (d.eBit || d.upperUsage.reserved || d.lowerUsage.reserved || d.dBit || d.tBit)
                    return false;
                if (isBranch(d))
                {
                    // branch in the delay slot: the second branch's delay slot must be plain
                    const Pair &d2 = pairs[nextPc(nextPc(pc)) >> 3];
                    if (isBranch(d2) || d2.eBit || d2.upperUsage.reserved || d2.lowerUsage.reserved || d2.dBit || d2.tBit)
                        return false;
                }
            }
            if (p.eBit)
            {
                const Pair &n = pairs[nextPc(pc) >> 3];
                if (isBranch(n) || n.eBit || n.upperUsage.reserved || n.lowerUsage.reserved || n.dBit || n.tBit)
                    return false;
            }
            return true;
        }

        // Closure over fallthrough and direct branch targets.
        void computeEmitted(const std::set<uint32_t> &seeds)
        {
            emitted.assign(kPairs, false);
            isTarget.assign(kPairs, false);
            std::vector<uint32_t> work(seeds.begin(), seeds.end());
            while (!work.empty())
            {
                const uint32_t pc = work.back();
                work.pop_back();
                if (pc >= kCodeSize || emitted[pc >> 3] || !supported(pc))
                    continue;
                emitted[pc >> 3] = true;
                const Pair &p = pairs[pc >> 3];
                if (p.eBit)
                {
                    // the final pair is emitted inline, not as its own label
                    continue;
                }
                if (isBranch(p))
                {
                    const uint8_t opHi = static_cast<uint8_t>((p.lower >> 25) & 0x7Fu);
                    if (opHi != 0x24u && opHi != 0x25u)
                    {
                        work.push_back((pc + 8u + IMM11(p.lower) * 8) & 0x3FFFu);
                        isTarget[((pc + 8u + IMM11(p.lower) * 8) & 0x3FFFu) >> 3] = true;
                    }
                    work.push_back(nextPc(nextPc(pc))); // after the delay slot
                    work.push_back(nextPc(pc));         // the delay slot pair itself (own label)
                    const Pair &d = pairs[nextPc(pc) >> 3];
                    if (isBranch(d))
                    {
                        const uint8_t opHi2 = static_cast<uint8_t>((d.lower >> 25) & 0x7Fu);
                        if (opHi2 != 0x24u && opHi2 != 0x25u)
                        {
                            work.push_back((nextPc(pc) + 8u + IMM11(d.lower) * 8) & 0x3FFFu);
                            isTarget[((nextPc(pc) + 8u + IMM11(d.lower) * 8) & 0x3FFFu) >> 3] = true;
                        }
                        work.push_back(nextPc(nextPc(nextPc(pc))));
                    }
                }
                else
                    work.push_back(nextPc(pc));
            }
        }

        // --- dataflow --------------------------------------------------------------------------
        struct Facts
        {
            std::array<int8_t, 128> vf;
            std::array<int8_t, 16> vi;
            std::array<uint8_t, 32> norm;
        };
        static Facts unknownFacts()
        {
            Facts f;
            f.vf.fill(kUnknownSlack);
            f.vi.fill(kUnknownSlack);
            f.norm.fill(0u);
            f.norm[0] = 0xFu; // vf0 is constant (0,0,0,1)
            for (int l = 0; l < 4; ++l)
                f.vf[l] = kSlackCap;
            f.vi[0] = kSlackCap;
            return f;
        }
        static Facts topFacts()
        {
            Facts f;
            f.vf.fill(kSlackCap);
            f.vi.fill(kSlackCap);
            f.norm.fill(0xFu);
            return f;
        }
        static bool merge(Facts &into, const Facts &from)
        {
            bool changed = false;
            for (int i = 0; i < 128; ++i)
                if (from.vf[i] < into.vf[i]) { into.vf[i] = from.vf[i]; changed = true; }
            for (int i = 0; i < 16; ++i)
                if (from.vi[i] < into.vi[i]) { into.vi[i] = from.vi[i]; changed = true; }
            for (int i = 0; i < 32; ++i)
            {
                const uint8_t n = into.norm[i] & from.norm[i];
                if (n != into.norm[i]) { into.norm[i] = n; changed = true; }
            }
            return changed;
        }
        static bool upperNormalizes(uint32_t up)
        {
            UpperArith a;
            UpperOther o;
            if (upperArith(up, a))
                return true;
            if (upperOther(up, o))
                return !o.clip && o.expr.find("ftoi") == std::string::npos; // FTOI writes integers
            return false;
        }
        // Facts after executing pair pc with entry facts f.
        Facts transfer(uint32_t pc, Facts f) const
        {
            const Pair &p = pairs[pc >> 3];
            for (int i = 0; i < 128; ++i)
                if (f.vf[i] < kSlackCap) ++f.vf[i];
            for (int i = 0; i < 16; ++i)
                if (f.vi[i] < kSlackCap) ++f.vi[i];
            const auto &lw = p.lowerUsage.vfWrite;
            if (lw.reg != 0u && p.suppressedLowerVf != lw.reg)
            {
                const int lat = p.lowerUsage.vfLatency ? p.lowerUsage.vfLatency : p.lowerUsage.latency;
                for (int l = 0; l < 4; ++l)
                    if (lw.lanes & (1u << (3 - l)))
                    {
                        f.vf[lw.reg * 4 + l] = static_cast<int8_t>(1 - lat);
                        f.norm[lw.reg] &= static_cast<uint8_t>(~(1u << (3 - l)));
                    }
            }
            const auto &uw = p.upperUsage.vfWrite;
            if (uw.reg != 0u)
            {
                const int lat = p.upperUsage.vfLatency ? p.upperUsage.vfLatency : p.upperUsage.latency;
                const bool norm = upperNormalizes(p.upper);
                for (int l = 0; l < 4; ++l)
                    if (uw.lanes & (1u << (3 - l)))
                    {
                        f.vf[uw.reg * 4 + l] = static_cast<int8_t>(1 - lat);
                        if (norm)
                            f.norm[uw.reg] |= static_cast<uint8_t>(1u << (3 - l));
                        else
                            f.norm[uw.reg] &= static_cast<uint8_t>(~(1u << (3 - l)));
                    }
            }
            uint32_t m = p.lowerUsage.viWrite & 0xFFFEu;
            const int vlat = p.lowerUsage.viLatency ? p.lowerUsage.viLatency : p.lowerUsage.latency;
            while (m)
            {
                f.vi[__builtin_ctz(m)] = static_cast<int8_t>(1 - vlat);
                m &= m - 1u;
            }
            f.norm[0] = 0xFu;
            for (int l = 0; l < 4; ++l)
                f.vf[l] = kSlackCap;
            f.vi[0] = kSlackCap;
            return f;
        }
        // Successors of pair pc in execution order (a branch's delay slot follows it; the delay slot
        // then continues at the target or falls through).
        std::vector<uint32_t> successors(uint32_t pc) const
        {
            std::vector<uint32_t> r;
            const Pair &p = pairs[pc >> 3];
            if (p.eBit)
            {
                r.push_back(nextPc(pc)); // the final pair runs; its own successors are ignored
                return r;
            }
            r.push_back(nextPc(pc));
            // A pair that is the delay slot of a preceding branch also continues at that branch's
            // target: add the targets of every branch whose delay slot is this pair.
            const uint32_t prev = (pc + kCodeSize - 8u) % kCodeSize;
            const Pair &pp = pairs[prev >> 3];
            if (isBranch(pp))
            {
                const uint8_t opHi = static_cast<uint8_t>((pp.lower >> 25) & 0x7Fu);
                if (opHi != 0x24u && opHi != 0x25u)
                    r.push_back((prev + 8u + IMM11(pp.lower) * 8) & 0x3FFFu);
                // computed jumps: their recorded targets are unknown entries already
            }
            return r;
        }
        void analyze(const std::set<uint32_t> &unknownEntries)
        {
            slackVf.assign(kPairs, {});
            slackVi.assign(kPairs, {});
            normVf.assign(kPairs, {});
            isUnknownEntry.assign(kPairs, false);
            std::vector<Facts> entry(kPairs, topFacts());
            std::vector<bool> seen(kPairs, false);
            std::vector<uint32_t> work;
            for (uint32_t pc : unknownEntries)
                if (pc < kCodeSize)
                {
                    isUnknownEntry[pc >> 3] = true;
                    entry[pc >> 3] = unknownFacts();
                    seen[pc >> 3] = true;
                    work.push_back(pc);
                }
            while (!work.empty())
            {
                const uint32_t pc = work.back();
                work.pop_back();
                const Facts after = transfer(pc, entry[pc >> 3]);
                if (pairs[pc >> 3].eBit)
                {
                    const uint32_t f = nextPc(pc);
                    if (!seen[f >> 3] || merge(entry[f >> 3], after))
                    {
                        seen[f >> 3] = true;
                        // the final pair does not continue; nothing to push
                    }
                    continue;
                }
                for (uint32_t s : successors(pc))
                {
                    if (!seen[s >> 3])
                    {
                        seen[s >> 3] = true;
                        entry[s >> 3] = isUnknownEntry[s >> 3] ? unknownFacts() : after;
                        if (isUnknownEntry[s >> 3])
                            merge(entry[s >> 3], after);
                        work.push_back(s);
                    }
                    else if (merge(entry[s >> 3], after))
                        work.push_back(s);
                }
            }
            for (uint32_t i = 0; i < kPairs; ++i)
            {
                const Facts &f = seen[i] ? entry[i] : unknownFacts();
                slackVf[i] = f.vf;
                slackVi[i] = f.vi;
                normVf[i] = f.norm;
            }
            analysisValid = true;
        }
        // Lanes of `lanes` (dest-style bits) of reg whose read at pc may stall.
        uint8_t stallLanes(uint32_t pc, uint8_t reg, uint8_t lanes) const
        {
            if (!analysisValid)
                return lanes;
            uint8_t r = 0u;
            for (int l = 0; l < 4; ++l)
                if ((lanes & (1u << (3 - l))) && slackVf[pc >> 3][reg * 4 + l] < 0)
                    r |= static_cast<uint8_t>(1u << (3 - l));
            return r;
        }
        bool viMayStall(uint32_t pc, uint8_t reg) const
        {
            return !analysisValid || slackVi[pc >> 3][reg] < 0;
        }
        bool lanesNormalized(uint32_t pc, uint8_t reg, uint8_t lanes) const
        {
            return analysisValid && (normVf[pc >> 3][reg] & lanes) == lanes;
        }

        // Static push counter in address order: a run of pairs commits at least every 16 pushes, so
        // any path (each jump lands in such a run) holds at most 16 + 16 uncommitted entries plus the
        // few still in flight, well inside the 64-entry ring.
        uint32_t pushCounter = 0u;

        void emitPair(uint32_t pc)
        {
            const Pair &p = pairs[pc >> 3];
            line("L_" + hex(pc) + ":");
            // A direct branch target starts a run: commit here so a loop body never accumulates
            // more than one run's worth of flag entries.
            emitBody(pc, 0, pushCounter, isTarget[pc >> 3]);
            if (p.eBit)
            {
                const uint32_t f = nextPc(pc);
                line("    // E bit: one more pair, then the program ends");
                emitBody(f, 2, pushCounter, false);
                line("    vu.m_state.pc = " + hex(nextPc(f)) + "; goto end;");
                return;
            }
            if (isBranch(p) && isBranch(pairs[nextPc(pc) >> 3]))
            {
                // Branch in the delay slot (runFast: the second branch overwrites the pending one
                // when taken; otherwise the first branch resolves after the second's pair).
                const uint32_t d = nextPc(pc);
                const uint32_t d2 = nextPc(d);
                line("    // delay slot holding another branch");
                branchVar = 2;
                emitBody(d, 1, pushCounter, false);
                branchVar = 0;
                line("    if (taken2) {");
                line("    taken = true; target = target2; // pending branch is now the second one");
                emitBody(d2, 1, pushCounter, false);
                {
                    const Pair &dp = pairs[d >> 3];
                    const uint8_t opHi2 = static_cast<uint8_t>((dp.lower >> 25) & 0x7Fu);
                    if (opHi2 == 0x24u || opHi2 == 0x25u)
                        line("    if (vu.m_cycle >= vu.m_nextReadyCycle) vu.fastCommit(); goto *kJrLabels[target >> 3]; }");
                    else
                    {
                        const uint32_t t2 = (d + 8u + IMM11(dp.lower) * 8) & 0x3FFFu;
                        line("    goto " + (emitted[t2 >> 3] ? "L_" + hex(t2) : "B_" + hex(t2)) + "; }");
                    }
                }
                pushCounter = 0u;
                {
                    const uint8_t opHi1 = static_cast<uint8_t>((p.lower >> 25) & 0x7Fu);
                    if (opHi1 == 0x24u || opHi1 == 0x25u)
                        line("    if (taken) { if (vu.m_cycle >= vu.m_nextReadyCycle) vu.fastCommit(); goto *kJrLabels[target >> 3]; }");
                    else
                    {
                        const uint32_t t1 = (pc + 8u + IMM11(p.lower) * 8) & 0x3FFFu;
                        line("    if (taken) goto " + (emitted[t1 >> 3] ? "L_" + hex(t1) : "B_" + hex(t1)) + ";");
                    }
                }
                line("    goto " + (emitted[d2 >> 3] ? "L_" + hex(d2) : "B_" + hex(d2)) + ";");
                return;
            }
            if (isBranch(p))
            {
                const uint32_t d = nextPc(pc);
                line("    // delay slot");
                emitBody(d, 1, pushCounter, false);
                const uint8_t opHi = static_cast<uint8_t>((p.lower >> 25) & 0x7Fu);
                if (opHi == 0x24u || opHi == 0x25u)
                {
                    // Computed jump: start the target's run with a fresh push count.
                    line("    if (taken) { if (vu.m_cycle >= vu.m_nextReadyCycle) vu.fastCommit(); goto *kJrLabels[target >> 3]; }");
                    pushCounter = 0u;
                }
                else
                {
                    const uint32_t t = (pc + 8u + IMM11(p.lower) * 8) & 0x3FFFu;
                    line("    if (taken) goto " + (emitted[t >> 3] ? "L_" + hex(t) : "B_" + hex(t)) + ";");
                }
                const uint32_t after = nextPc(d);
                line("    goto " + (emitted[after >> 3] ? "L_" + hex(after) : "B_" + hex(after)) + ";");
                return;
            }
            const uint32_t n = nextPc(pc);
            if (!emitted[n >> 3])
                line("    goto B_" + hex(n) + ";");
        }

        void generate(const std::set<uint32_t> &seeds, const std::set<uint32_t> &unknownEntries, const std::string &name)
        {
            VU1Interpreter vu(VU1Interpreter::Unit::VU1);
            pairs.resize(kPairs);
            for (uint32_t i = 0; i < kPairs; ++i)
                pairs[i] = vu.decodeInstructionPair(code, i * 8u);
            computeEmitted(seeds);
            analyze(unknownEntries);

            line("// GENERATED by vu1_replay --gen from a VU1 microcode image (FNV-1a " + name + "); do not edit.");
            line("// See src/tools/vu1_gen.cpp and src/lib/vu/ps2_vu1_ops.h.");
            line("#define private public // generated code is part of the interpreter");
            line("#include \"../ps2_vu1_ops.h\"");
            line("#undef private");
            line("#include <atomic>");
            line("extern std::atomic<uint64_t> g_vuInsnCount;");
            line("extern std::atomic<uint64_t> g_xgkickDecoded;");
            line("extern uint32_t *g_vu1BailHist;");
            line("");
            line("bool vu1gen_" + name + "(VU1Interpreter &vu, uint64_t budgetEnd)");
            line("{");
            out += "    static const void *const kLabels[" + num(kPairs) + "] = {";
            for (uint32_t i = 0; i < kPairs; ++i)
            {
                if (i % 8u == 0u)
                    out += "\n        ";
                out += (emitted[i] ? "&&L_" : "&&B_") + hex(i * 8u) + ",";
            }
            line("\n    };");
            // Computed jumps and program entries may only land where the dataflow facts assume an
            // unknown predecessor (recorded targets); elsewhere they hand back to the interpreter.
            out += "    static const void *const kJrLabels[" + num(kPairs) + "] = {";
            for (uint32_t i = 0; i < kPairs; ++i)
            {
                if (i % 8u == 0u)
                    out += "\n        ";
                out += ((emitted[i] && isUnknownEntry[i]) ? "&&L_" : "&&B_") + hex(i * 8u) + ",";
            }
            line("\n    };");
            line("    uint64_t pairs = 0;");
            line("    uint64_t ready;");
            line("    bool taken = false, taken2 = false;");
            line("    uint32_t target = 0, target2 = 0;");
            line("    (void)taken2; (void)target2;");
            line("    __m128 up;");
            line("    __m128 acc = _mm_loadu_ps(vu.m_state.acc);");
            line("    alignas(16) float vf[32][4];");
            line("    std::memcpy(vf, vu.m_state.vf, sizeof(vf));");
            line("    int32_t oldVi = 0;");
            line("    (void)taken; (void)target; (void)up; (void)oldVi;");
            line("    if ((vu.m_state.pc & 7u) != 0u || vu.m_cycle >= budgetEnd) return false;");
            line("    goto *kJrLabels[(vu.m_state.pc >> 3) & " + hex(kPairs - 1u) + "u];");
            line("");
            for (uint32_t i = 0; i < kPairs; ++i)
            {
                if (emitted[i])
                    emitPair(i * 8u);
                else
                    line("B_" + hex(i * 8u) + ": vu.m_state.pc = " + hex(i * 8u) + "; goto bail;");
            }
            // Bail stubs for emitted pairs a computed jump may not land on (kJrLabels).
            for (uint32_t i = 0; i < kPairs; ++i)
                if (emitted[i] && !isUnknownEntry[i])
                    line("B_" + hex(i * 8u) + ": vu.m_state.pc = " + hex(i * 8u) + "; goto bail;");
            line("bail:");
            line("    _mm_storeu_ps(vu.m_state.acc, acc);");
            line("    std::memcpy(vu.m_state.vf, vf, sizeof(vf));");
            line("    if (g_vu1BailHist) ++g_vu1BailHist[(vu.m_state.pc >> 3) & 0x7FFu];");
            line("    vu.m_maxReadyCycle = ~0ull; // the interpreter re-scans operand readiness");
            line("    g_vuInsnCount.fetch_add(pairs, std::memory_order_relaxed);");
            line("    return false;");
            line("end:");
            line("    _mm_storeu_ps(vu.m_state.acc, acc);");
            line("    std::memcpy(vu.m_state.vf, vf, sizeof(vf));");
            line("    g_vuInsnCount.fetch_add(pairs, std::memory_order_relaxed);");
            line("    return true;");
            line("}");
        }
    };
}

// Entry used by vu1_replay: code = 16 KB image, seeds = entry pcs + executed pcs.
int vu1GenerateKnownProgram(const uint8_t *code, uint64_t hash, const std::set<uint32_t> &seeds, const std::set<uint32_t> &unknownEntries, const std::string &outPath)
{
    Gen g;
    g.code = code;
    g.hash = hash;
    char name[32];
    std::snprintf(name, sizeof(name), "%016llx", static_cast<unsigned long long>(hash));
    g.generate(seeds, unknownEntries, name);
    FILE *fp = std::fopen(outPath.c_str(), "wb");
    if (!fp)
    {
        std::fprintf(stderr, "cannot write %s\n", outPath.c_str());
        return 1;
    }
    std::fwrite(g.out.data(), 1, g.out.size(), fp);
    std::fclose(fp);
    uint32_t n = 0;
    for (bool e : g.emitted)
        n += e ? 1u : 0u;
    std::fprintf(stderr, "[vu1_gen] %s: %u pairs emitted -> %s\n", name, n, outPath.c_str());
    return 0;
}
