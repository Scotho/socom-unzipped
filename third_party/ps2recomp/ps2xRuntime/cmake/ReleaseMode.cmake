include(CheckIPOSupported)

check_ipo_supported(RESULT IPO_SUPPORTED OUTPUT IPO_ERROR)

option(PS2X_ENABLE_LTO "Enable link-time optimization for release builds" ON)
set(PS2X_LTO_SCOPE "all" CACHE STRING "all: LTO every target EnableFastReleaseMode names; runtime: leave ps2EntryRunner (the generated code) out")

function(EnableFastReleaseMode TargetName)
    message("> Enabling optimization for: ${TargetName}")
    if(MSVC)
        target_compile_options(${TargetName} PRIVATE
            $<$<CONFIG:Release>:
                /O2 # speed
                /Ob2 # inline aggressively
                /Oi # intrinsics
                /GL # whole program opt
                /Gy # function-level linking
                /Gw # global data in COMDAT
                /GF # string pooling
                /Zc:inline # remove unreferenced inline
                /fp:fast # fast math (graphics friendly)
                /DNDEBUG
                /arch:AVX2 # Advanced Vector Extensions 2
                /GS- # Disable Buffer Security Check (faster)
                /Qspectre- # Disable Spectre mitigations (faster)
            >
        )

        if(TARGET ${TargetName})
            target_link_options(${TargetName} PRIVATE
                $<$<CONFIG:Release>:
                    /LTCG # link-time code generation
                    /OPT:REF # remove unreferenced
                    /OPT:ICF # fold identical COMDATs
                >
            )
        endif()
    endif()

    if(PS2X_ENABLE_LTO AND PS2X_LTO_SCOPE STREQUAL "runtime" AND TargetName STREQUAL "ps2EntryRunner")
        message("> LTO skipped for ${TargetName} (PS2X_LTO_SCOPE=runtime: the generated code stays native objects)")
    elseif(IPO_SUPPORTED AND PS2X_ENABLE_LTO)
        set_property(TARGET ${TargetName} PROPERTY INTERPROCEDURAL_OPTIMIZATION_RELEASE TRUE)
    elseif(NOT PS2X_ENABLE_LTO)
        message("> LTO disabled for ${TargetName} (PS2X_ENABLE_LTO=OFF)")
    else()
        message(WARNING "Interprocedural optimization not supported: ${ipo_error}")
    endif()
endfunction()