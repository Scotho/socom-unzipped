// Sprint 7 Task 9a (owner request 2026-09-18): the miniaudio half of launcher::MicDevices -- enumerate the
// host's capture devices, open the one the player picked, and keep the last callback's RMS where the panel's
// meter can read it every frame.
//
// miniaudio.h is included WITHOUT MINIAUDIO_IMPLEMENTATION: raylib's raudio.c (:178) already compiled it into
// libraylib, and its define list (:163-178: MA_NO_JACK/WAV/FLAC/MP3/RESOURCE_MANAGER/NODE_GRAPH/ENGINE/
// GENERATION) removes decoders and the high-level engine but NOT device I/O, so capture is there.
#include "launcher/mic_devices.h"

#include <atomic>
#include <cstring>

#include "external/miniaudio.h"

namespace launcher
{
    namespace
    {
        class MiniaudioMicDevices final : public MicDevices
        {
        public:
            ~MiniaudioMicDevices() override { stopMeter(); }

            std::vector<std::string> list() override
            {
                std::vector<std::string> names;
                ma_context ctx;
                if (ma_context_init(nullptr, 0, nullptr, &ctx) != MA_SUCCESS)
                    return names;   // the host's audio backend would not start: "None" alone, not a crash
                ma_device_info *playback = nullptr;
                ma_uint32 playbackCount = 0;
                ma_device_info *capture = nullptr;
                ma_uint32 captureCount = 0;
                if (ma_context_get_devices(&ctx, &playback, &playbackCount, &capture, &captureCount) == MA_SUCCESS)
                {
                    for (ma_uint32 i = 0; i < captureCount; ++i)
                        names.push_back(std::string(capture[i].name));
                }
                ma_context_uninit(&ctx);
                return names;
            }

            bool startMeter(const std::string &name) override
            {
                stopMeter();
                if (name.empty())
                    return false;
                if (ma_context_init(nullptr, 0, nullptr, &m_ctx) != MA_SUCCESS)
                    return false;
                m_ctxOpen = true;
                ma_device_info *playback = nullptr;
                ma_uint32 playbackCount = 0;
                ma_device_info *capture = nullptr;
                ma_uint32 captureCount = 0;
                if (ma_context_get_devices(&m_ctx, &playback, &playbackCount, &capture, &captureCount) != MA_SUCCESS)
                {
                    stopMeter();
                    return false;
                }
                const ma_device_info *picked = nullptr;
                for (ma_uint32 i = 0; i < captureCount; ++i)
                {
                    if (name == capture[i].name)
                    {
                        picked = &capture[i];
                        break;
                    }
                }
                if (picked == nullptr)
                {
                    stopMeter();
                    return false;
                }
                ma_device_config cfg = ma_device_config_init(ma_device_type_capture);
                cfg.capture.pDeviceID = const_cast<ma_device_id *>(&picked->id);
                cfg.capture.format = ma_format_f32;
                cfg.capture.channels = 1;
                cfg.sampleRate = 16000;
                cfg.dataCallback = &MiniaudioMicDevices::onData;
                cfg.pUserData = this;
                if (ma_device_init(&m_ctx, &cfg, &m_device) != MA_SUCCESS)
                {
                    stopMeter();
                    return false;
                }
                m_deviceOpen = true;
                if (ma_device_start(&m_device) != MA_SUCCESS)
                {
                    stopMeter();
                    return false;
                }
                m_level.store(-INFINITY, std::memory_order_relaxed);
                m_running = true;
                return true;
            }

            float levelDb() const override { return m_level.load(std::memory_order_relaxed); }

            void stopMeter() override
            {
                if (m_deviceOpen)
                {
                    ma_device_uninit(&m_device);
                    m_deviceOpen = false;
                }
                if (m_ctxOpen)
                {
                    ma_context_uninit(&m_ctx);
                    m_ctxOpen = false;
                }
                m_running = false;
                m_level.store(-INFINITY, std::memory_order_relaxed);
            }

        private:
            static void onData(ma_device *device, void *pOutput, const void *pInput, ma_uint32 frameCount)
            {
                (void)pOutput;
                auto *self = static_cast<MiniaudioMicDevices *>(device->pUserData);
                if (self == nullptr || pInput == nullptr)
                    return;
                self->m_level.store(micLevelDb(static_cast<const float *>(pInput), frameCount), std::memory_order_relaxed);
            }

            ma_context m_ctx{};
            ma_device m_device{};
            bool m_ctxOpen = false;
            bool m_deviceOpen = false;
            bool m_running = false;
            std::atomic<float> m_level{-INFINITY};
        };
    }

    std::unique_ptr<MicDevices> makeMicDevices()
    {
        return std::unique_ptr<MicDevices>(new MiniaudioMicDevices());
    }
}
