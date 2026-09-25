#pragma once

#include "iop_service.h"

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace ps2x::iop::detail
{
    std::unique_ptr<IopService> createDbcmanService(IopHost &host);
    std::unique_ptr<IopService> createLibSdService(IopHost &host);
    std::unique_ptr<IopService> createMcservService(IopHost &host);
    std::unique_ptr<IopService> createSnd989Service(IopHost &host);
    std::unique_ptr<IopService> createLgAudService(IopHost &host);
    std::unique_ptr<IopService> createEzNetCnfService(IopHost &host);
}
