#ifndef PS2RECOMP_VU_TRANSLATOR_H
#define PS2RECOMP_VU_TRANSLATOR_H

#include <string>

namespace ps2recomp
{
    struct Instruction;
    class CodeGenerator;

    class VuTranslator
    {
    public:
        explicit VuTranslator(CodeGenerator &codeGenerator);
        std::string translate(const Instruction &inst);

    private:
        std::string translateInner(const Instruction &inst);
        // Appends the VU0 MAC/STATUS flag update to the code of an FMAC-class macro instruction
        // (ADD/SUB/MUL/MADD/MSUB/OPMULA/OPMSUB and their broadcast, i, q and A forms); the
        // emitters bind the lane result to a local named `res` inside a braced block.
        std::string appendFmacFlags(const Instruction &inst, std::string code) const;

        CodeGenerator &m_codeGenerator;
    };
}

#endif // PS2RECOMP_VU_TRANSLATOR_H
