# Sprint 9 Goal 1: what the runner (socom2) and the launcher both need, and nothing either of them owns.
# Plain C++20: no raylib, no GL, no ps2_runtime. The runner links this so that it never links the launcher;
# the launcher's tested core (ps2x_launcher_core) links it PUBLIC, so every existing
# #include "launcher/launcher_config.h" keeps resolving.
add_library(ps2x_shared STATIC
    src/iso9660.cpp
    src/sha256.cpp
    src/launcher_config.cpp
    src/client_mode.cpp     # Sprint 18 T2 (R-A): launcher.json, the NATIVE/PCSX2 mode
    src/pcsx2_config.cpp    # Sprint 18 T2 (R-A): config.pcsx2.json, the PCSX2 client's own settings
    src/pcsx2_files.cpp     # Sprint 18 T3: the ini merge, the embedded pnach, the data root, the DNS pick
    src/pcsx2_install.cpp   # Sprint 18 T4 (R-C): INSTALL -- the release parse, the redirect rule, the adapter pick
    src/preflight.cpp
    src/exe_dir.cpp
    src/bare_run.cpp
    src/process_fatal.cpp
    src/zip_store.cpp
    src/diagnostics.cpp
    src/bug_report.cpp
    src/patch_fetch.cpp   # Sprint 16 R2a (#71): the r0004 package's URL and its check
    src/mapping.cpp
    src/personas.cpp      # Sprint 16 L1b (#73): the persona ledger beside the card, read by the launcher, written by the runner
    src/card_save.cpp     # the persona-card plan Task 1: the card's save file -- scrambler, ZAR v2, AcctInfo.rdr records
    src/knobs.cpp
    src/host_window.cpp   # Sprint 10 Q4: the game window's title and the launcher's palette on its chrome
)
target_include_directories(ps2x_shared PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
# Sprint 18 T3: the guarded pnach the launcher writes for PCSX2, embedded at configure time from the tracked master.
# Its LF form: git stores LF, a Windows checkout may hold CRLF, and the compiler reads a raw string's line endings
# as LF anyway -- so the embed is the same bytes on every host (tools_py/tests/test_pcsx2_masters.py holds them).
# PRIVATE: only pcsx2_files.cpp includes it (the one definition of kPnachMaster).
get_filename_component(PS2X_PNACH_MASTER_FILE
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../scripts/parity/pcsx2/0F6FC6CF.pnach" ABSOLUTE)
file(READ "${PS2X_PNACH_MASTER_FILE}" PNACH_MASTER)
string(REPLACE "\r\n" "\n" PNACH_MASTER "${PNACH_MASTER}")
string(FIND "${PNACH_MASTER}" ")pnach\"" PS2X_PNACH_CLOSE_AT)
string(FIND "${PNACH_MASTER}" "@" PS2X_PNACH_AT_AT)
if(NOT PS2X_PNACH_CLOSE_AT EQUAL -1 OR NOT PS2X_PNACH_AT_AT EQUAL -1)
    message(FATAL_ERROR "${PS2X_PNACH_MASTER_FILE} holds )pnach\" or @ and cannot be embedded as a raw string")
endif()
configure_file(pcsx2_pnach_embedded.h.in
    ${CMAKE_CURRENT_BINARY_DIR}/generated/launcher/pcsx2_pnach_embedded.h @ONLY NEWLINE_STYLE LF)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${PS2X_PNACH_MASTER_FILE}")
target_include_directories(ps2x_shared PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/generated)
target_compile_features(ps2x_shared PUBLIC cxx_std_20)
# PIC: kept from upstream's SHARED Android runner (removed by Sprint 13 Task C7); a harmless default here.
set_target_properties(ps2x_shared PROPERTIES POSITION_INDEPENDENT_CODE ON)
# The persona-card plan Task 2: personas.cpp resolves the server to the address the card's HOST holds (getaddrinfo).
if(WIN32)
    target_link_libraries(ps2x_shared PUBLIC ws2_32)
endif()
