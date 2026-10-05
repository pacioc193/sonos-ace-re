// ace.exe - Sonos Ace BLE control, Windows (C++/WinRT, plain Win32 console app).
//
// Verbose by default: every step, status code, GATT handle and byte is logged to the
// console and to ace_debug_<date>.log, so a failure can be diagnosed from the log alone.
// Protocol: ../../protocol/NOTES.md. Core encoding: ../core/ace_protocol.hpp.

#include <windows.h>

#include <winrt/Windows.Devices.Bluetooth.Advertisement.h>
#include <winrt/Windows.Devices.Bluetooth.GenericAttributeProfile.h>
#include <winrt/Windows.Devices.Bluetooth.h>
#include <winrt/Windows.Devices.Enumeration.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Storage.Streams.h>

#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <ctime>
#include <deque>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "../core/ace_protocol.hpp"

using namespace winrt;
using namespace winrt::Windows::Foundation;
using namespace winrt::Windows::Devices::Bluetooth;
using namespace winrt::Windows::Devices::Bluetooth::Advertisement;
using namespace winrt::Windows::Devices::Bluetooth::GenericAttributeProfile;
using namespace winrt::Windows::Devices::Enumeration;
using namespace winrt::Windows::Storage::Streams;

// ---------------------------------------------------------------- logging

class Logger {
   public:
    bool verbose = true;

    void open(const std::string& path) {
        file_.open(path, std::ios::app);
        path_ = path;
    }
    const std::string& path() const { return path_; }

    void info(const std::string& m) { line("INF", m); }
    void warn(const std::string& m) { line("WRN", m); }
    void error(const std::string& m) { line("ERR", m); }
    void debug(const std::string& m) {
        if (verbose) line("DBG", m);
    }

   private:
    static std::string stamp() {
        using namespace std::chrono;
        const auto now = system_clock::now();
        const auto ms = duration_cast<milliseconds>(now.time_since_epoch()) % 1000;
        const std::time_t t = system_clock::to_time_t(now);
        std::tm tm{};
        localtime_s(&tm, &t);
        char buf[32];
        std::snprintf(buf, sizeof buf, "%02d:%02d:%02d.%03d", tm.tm_hour, tm.tm_min, tm.tm_sec, static_cast<int>(ms.count()));
        return buf;
    }
    void line(const char* level, const std::string& m) {
        std::lock_guard<std::mutex> g(mutex_);
        const std::string s = stamp() + " [" + level + "] " + m;
        std::cout << s << std::endl;
        if (file_) file_ << s << std::endl;
    }
    std::mutex mutex_;
    std::ofstream file_;
    std::string path_;
};

static Logger g_log;

// ---------------------------------------------------------------- helpers

static std::string u8(hstring const& h) { return winrt::to_string(h); }

static std::string hex_error(winrt::hresult_error const& e) {
    char buf[16];
    std::snprintf(buf, sizeof buf, "0x%08X", static_cast<unsigned>(e.code().value));
    return std::string(buf) + " " + u8(e.message());
}

static std::string guid_str(guid const& g) {
    char b[40];
    std::snprintf(b, sizeof b, "%08x-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x", g.Data1, g.Data2, g.Data3, g.Data4[0],
                  g.Data4[1], g.Data4[2], g.Data4[3], g.Data4[4], g.Data4[5], g.Data4[6], g.Data4[7]);
    return b;
}

static guid parse_guid(const std::string& s) {
    unsigned a = 0, b = 0, c = 0, d[8] = {};
    if (std::sscanf(s.c_str(), "%8x-%4x-%4x-%2x%2x-%2x%2x%2x%2x%2x%2x", &a, &b, &c, &d[0], &d[1], &d[2], &d[3], &d[4], &d[5],
                    &d[6], &d[7]) != 11)
        throw std::invalid_argument("bad UUID: " + s);
    guid g{};
    g.Data1 = a;
    g.Data2 = static_cast<uint16_t>(b);
    g.Data3 = static_cast<uint16_t>(c);
    for (int i = 0; i < 8; ++i) g.Data4[i] = static_cast<uint8_t>(d[i]);
    return g;
}

static std::string addr_str(uint64_t a) {
    char b[24];
    std::snprintf(b, sizeof b, "%02X:%02X:%02X:%02X:%02X:%02X", static_cast<unsigned>((a >> 40) & 0xFF),
                  static_cast<unsigned>((a >> 32) & 0xFF), static_cast<unsigned>((a >> 24) & 0xFF),
                  static_cast<unsigned>((a >> 16) & 0xFF), static_cast<unsigned>((a >> 8) & 0xFF), static_cast<unsigned>(a & 0xFF));
    return b;
}

static bool parse_addr(const std::string& s, uint64_t& out) {
    unsigned v[6];
    if (std::sscanf(s.c_str(), "%2x:%2x:%2x:%2x:%2x:%2x", &v[0], &v[1], &v[2], &v[3], &v[4], &v[5]) != 6) return false;
    out = 0;
    for (int i = 0; i < 6; ++i) out = (out << 8) | v[i];
    return true;
}

static std::string comm_status(GattCommunicationStatus s) {
    switch (s) {
        case GattCommunicationStatus::Success: return "Success";
        case GattCommunicationStatus::Unreachable: return "Unreachable";
        case GattCommunicationStatus::ProtocolError: return "ProtocolError";
        case GattCommunicationStatus::AccessDenied: return "AccessDenied";
    }
    return "Unknown(" + std::to_string(static_cast<int>(s)) + ")";
}

static std::string protocol_error(IReference<uint8_t> const& pe) {
    if (!pe) return "";
    char b[32];
    std::snprintf(b, sizeof b, " ATT-error=0x%02X", static_cast<unsigned>(pe.Value()));
    return b;
}

static std::string props_str(GattCharacteristicProperties p) {
    const uint32_t v = static_cast<uint32_t>(p);
    static const std::pair<uint32_t, const char*> names[] = {
        {0x001, "broadcast"}, {0x002, "read"},   {0x004, "write-without-response"}, {0x008, "write"},
        {0x010, "notify"},    {0x020, "indicate"}, {0x040, "signed-write"},          {0x080, "extended"},
        {0x100, "reliable-write"}, {0x200, "writable-aux"}};
    std::string s;
    for (const auto& n : names)
        if (v & n.first) s += (s.empty() ? "" : ",") + std::string(n.second);
    return s.empty() ? "none" : s;
}

static IBuffer to_buffer(const ace::Bytes& b) {
    DataWriter w;
    w.WriteBytes(array_view<uint8_t const>(b.data(), b.data() + b.size()));
    return w.DetachBuffer();
}

static ace::Bytes from_buffer(IBuffer const& buf) {
    ace::Bytes v(buf.Length());
    if (!v.empty()) {
        DataReader r = DataReader::FromBuffer(buf);
        r.ReadBytes(array_view<uint8_t>(v.data(), v.data() + v.size()));
    }
    return v;
}

static void log_environment() {
    g_log.info("ace.exe built " __DATE__ " " __TIME__);
    typedef LONG(WINAPI * RtlGetVersionFn)(OSVERSIONINFOW*);
    if (HMODULE nt = GetModuleHandleW(L"ntdll.dll")) {
        if (auto fn = reinterpret_cast<RtlGetVersionFn>(GetProcAddress(nt, "RtlGetVersion"))) {
            OSVERSIONINFOW vi{};
            vi.dwOSVersionInfoSize = sizeof vi;
            if (fn(&vi) == 0)
                g_log.info("Windows " + std::to_string(vi.dwMajorVersion) + "." + std::to_string(vi.dwMinorVersion) + " build " +
                           std::to_string(vi.dwBuildNumber));
        }
    }
    try {
        auto adapter = BluetoothAdapter::GetDefaultAsync().get();
        if (!adapter) {
            g_log.error("no Bluetooth adapter found");
            return;
        }
        g_log.info("adapter " + addr_str(adapter.BluetoothAddress()) + " LE=" + std::to_string(adapter.IsLowEnergySupported()) +
                   " central=" + std::to_string(adapter.IsCentralRoleSupported()) +
                   " peripheral=" + std::to_string(adapter.IsPeripheralRoleSupported()) +
                   " secure-conn=" + std::to_string(adapter.AreLowEnergySecureConnectionsSupported()));
    } catch (winrt::hresult_error const& e) {
        g_log.warn("adapter query failed: " + hex_error(e));
    }
}

// ---------------------------------------------------------------- options

struct Options {
    std::vector<std::string> pos;
    std::string write_uuid = ace::kControlWriteUuid;
    std::string notify_uuid = ace::kControlNotifyUuid;
    std::string log_path;
    int timeout_ms = 3000;
    bool cached = false;
    bool no_session = false;
    bool no_register = false;
    std::string token = "placeholder";  // placeholder | random | 32 hex digits
    bool quiet = false;
};

static const char* kHelp = R"(ace.exe - Sonos Ace control (BLE)

  ace list                        paired Bluetooth devices (name + id)
  ace scan [seconds]              BLE advertisements (look for "Sonos Ace")
  ace <dev> services              dump every GATT service/characteristic (UUIDs, handles)
  ace <dev> probe                 run all read-only requests, decode replies
  ace <dev> sniff [seconds]       just listen to notifications (default 30 s)
  ace <dev> get anc|eq|balance|name|volume|info|charging|adaptive-anc|selfvoice|autooff|wear|spatial|buttons
  ace <dev> mode anc|aware|off
  ace <dev> bass|treble|balance -10..10
  ace <dev> loudness on|off
  ace <dev> raw <hex>             send any bytes, e.g. raw 00020e

<dev> = Bluetooth address (80:4A:F2:05:AF:27), part of the name ("sonos"), or "auto".

options: --quiet            less logging (default: everything)
         --log=<file>       log file (default ace_debug_<date>.log)
         --timeout=<ms>     reply timeout (default 3000)
         --cached           use cached GATT data instead of re-discovering
         --no-session       do not call GattSession.MaintainConnection
         --write-uuid=<u> --notify-uuid=<u>   override control characteristics
         --no-register      skip the registration step (default: register first, like the phone app)
         --token=<x>        registration token: your 32 hex digits (default: redacted placeholder) | random
)";

// ---------------------------------------------------------------- discovery

static void cmd_list() {
    for (bool le : {true, false}) {
        hstring selector = le ? BluetoothLEDevice::GetDeviceSelectorFromPairingState(true)
                              : BluetoothDevice::GetDeviceSelectorFromPairingState(true);
        auto devices = DeviceInformation::FindAllAsync(selector).get();
        g_log.info(std::string(le ? "paired BLE" : "paired classic") + " devices: " + std::to_string(devices.Size()));
        for (auto const& d : devices)
            g_log.info("  " + u8(d.Name()) + "  paired=" + std::to_string(d.Pairing().IsPaired()) + "  id=" + u8(d.Id()));
    }
}

static void cmd_scan(int seconds) {
    BluetoothLEAdvertisementWatcher watcher;
    watcher.ScanningMode(BluetoothLEScanningMode::Active);
    std::mutex m;
    std::set<std::string> seen;
    auto token = watcher.Received([&](auto&&, BluetoothLEAdvertisementReceivedEventArgs const& a) {
        const std::string name = u8(a.Advertisement().LocalName());
        std::ostringstream o;
        o << addr_str(a.BluetoothAddress()) << " rssi=" << a.RawSignalStrengthInDBm() << " type=" << static_cast<int>(a.AdvertisementType())
          << " name=\"" << name << "\"";
        for (auto const& u : a.Advertisement().ServiceUuids()) o << " svc=" << guid_str(u);
        for (auto const& md : a.Advertisement().ManufacturerData()) {
            char b[16];
            std::snprintf(b, sizeof b, "%04X", static_cast<unsigned>(md.CompanyId()));
            o << " mfg=" << b << ":" << ace::to_hex(from_buffer(md.Data()));
        }
        std::lock_guard<std::mutex> g(m);
        if (seen.insert(o.str()).second) g_log.info((name.find("Sonos") != std::string::npos ? "** " : "   ") + o.str());
    });
    g_log.info("scanning " + std::to_string(seconds) + " s (active)...");
    watcher.Start();
    std::this_thread::sleep_for(std::chrono::seconds(seconds));
    watcher.Stop();
    watcher.Received(token);
    g_log.info("scan done, " + std::to_string(seen.size()) + " distinct advertisements");
}

static BluetoothLEDevice open_device(const std::string& target) {
    uint64_t addr = 0;
    BluetoothLEDevice dev{nullptr};
    if (parse_addr(target, addr)) {
        g_log.debug("opening by address " + addr_str(addr));
        dev = BluetoothLEDevice::FromBluetoothAddressAsync(addr).get();
    } else {
        const std::string want = ace::lower(target == "auto" ? "sonos ace" : target);
        for (bool paired : {true, false}) {
            auto devices = DeviceInformation::FindAllAsync(BluetoothLEDevice::GetDeviceSelectorFromPairingState(paired)).get();
            g_log.debug(std::string("candidates (") + (paired ? "paired" : "unpaired") + " LE): " + std::to_string(devices.Size()));
            for (auto const& d : devices) {
                g_log.debug("  " + u8(d.Name()) + "  id=" + u8(d.Id()));
                if (!dev && ace::lower(u8(d.Name())).find(want) != std::string::npos) {
                    g_log.info("selected " + u8(d.Name()) + "  id=" + u8(d.Id()));
                    dev = BluetoothLEDevice::FromIdAsync(d.Id()).get();
                }
            }
            if (dev) break;
        }
    }
    if (!dev) throw std::runtime_error("device not found: " + target + " (try: ace list / ace scan, or pass the address)");
    g_log.info("device \"" + u8(dev.Name()) + "\" address=" + addr_str(dev.BluetoothAddress()) +
               " connection=" + (dev.ConnectionStatus() == BluetoothConnectionStatus::Connected ? "Connected" : "Disconnected") +
               " paired=" + std::to_string(dev.DeviceInformation().Pairing().IsPaired()));
    return dev;
}

static void dump_services(BluetoothLEDevice const& dev, BluetoothCacheMode mode) {
    auto res = dev.GetGattServicesAsync(mode).get();
    g_log.info("GetGattServices status=" + comm_status(res.Status()) + protocol_error(res.ProtocolError()) +
               " services=" + std::to_string(res.Services().Size()));
    for (auto const& svc : res.Services()) {
        std::string handle;
        try {
            handle = " handle=0x" + ace::to_hex(ace::Bytes{static_cast<uint8_t>(svc.AttributeHandle() >> 8), static_cast<uint8_t>(svc.AttributeHandle())});
        } catch (...) {
        }
        g_log.info("service " + guid_str(svc.Uuid()) + handle);
        auto chars = svc.GetCharacteristicsAsync(mode).get();
        if (chars.Status() != GattCommunicationStatus::Success)
            g_log.warn("  characteristics status=" + comm_status(chars.Status()) + protocol_error(chars.ProtocolError()));
        for (auto const& ch : chars.Characteristics()) {
            std::string h;
            try {
                h = " handle=0x" + ace::to_hex(ace::Bytes{static_cast<uint8_t>(ch.AttributeHandle() >> 8), static_cast<uint8_t>(ch.AttributeHandle())});
            } catch (...) {
            }
            g_log.info("  char " + guid_str(ch.Uuid()) + h + "  [" + props_str(ch.CharacteristicProperties()) + "]");
        }
        svc.Close();
    }
}

// ---------------------------------------------------------------- connection

class Link {
   public:
    BluetoothLEDevice dev{nullptr};
    GattSession session{nullptr};
    GattDeviceService service{nullptr};
    GattCharacteristic write{nullptr};
    GattCharacteristic notify{nullptr};
    GattCharacteristic setup_write{nullptr};
    GattCharacteristic setup_notify{nullptr};
    std::deque<ace::Bytes> setup_inbox;

    std::mutex m;
    std::condition_variable cv;
    std::deque<ace::Bytes> inbox;

    void connect(const std::string& target, Options const& o) {
        dev = open_device(target);
        dev.ConnectionStatusChanged([](BluetoothLEDevice const& d, IInspectable const&) {
            g_log.info(std::string("connection status -> ") +
                       (d.ConnectionStatus() == BluetoothConnectionStatus::Connected ? "Connected" : "Disconnected"));
        });
        if (!o.no_session) {
            session = GattSession::FromDeviceIdAsync(dev.BluetoothDeviceId()).get();
            session.MaintainConnection(true);
            g_log.info("GATT session status=" + std::to_string(static_cast<int>(session.SessionStatus())) +
                       " (0=Closed,1=Active) maxPdu=" + std::to_string(session.MaxPduSize()));
        }
        const auto mode = o.cached ? BluetoothCacheMode::Cached : BluetoothCacheMode::Uncached;
        g_log.info(std::string("discovering service ") + ace::kServiceUuid + (o.cached ? " (cached)" : " (uncached)"));
        auto svcs = dev.GetGattServicesForUuidAsync(parse_guid(ace::kServiceUuid), mode).get();
        g_log.info("  status=" + comm_status(svcs.Status()) + protocol_error(svcs.ProtocolError()) +
                   " found=" + std::to_string(svcs.Services().Size()));
        if (svcs.Status() != GattCommunicationStatus::Success || svcs.Services().Size() == 0) {
            g_log.error("service not found; full service list follows");
            dump_services(dev, mode);
            throw std::runtime_error("Sonos service 0xFE07 not available (headphones connected to another host? not paired?)");
        }
        service = svcs.Services().GetAt(0);
        write = find_char(o.write_uuid, mode);
        notify = find_char(o.notify_uuid, mode);
        if (!write || !notify) {
            g_log.error("control characteristics missing; dumping all characteristics of the service");
            dump_services(dev, mode);
            throw std::runtime_error("control characteristics not found (override with --write-uuid/--notify-uuid)");
        }
        g_log.info("write  " + o.write_uuid + " [" + props_str(write.CharacteristicProperties()) + "]");
        g_log.info("notify " + o.notify_uuid + " [" + props_str(notify.CharacteristicProperties()) + "]");

        // The phone registers on the setup characteristic BEFORE enabling control notifications
        // (captures EXP-01/02); without it every control reply is NO_PERMISSIONS.
        if (!o.no_register) do_register(o, mode);

        notify.ValueChanged([this](GattCharacteristic const&, GattValueChangedEventArgs const& a) {
            ace::Bytes b = from_buffer(a.CharacteristicValue());
            g_log.info("RX " + ace::to_hex(b, " ") + "   " + ace::describe(b));
            {
                std::lock_guard<std::mutex> g(m);
                inbox.push_back(std::move(b));
            }
            cv.notify_all();
        });
        enable_notifications(notify, "control");
    }

    void enable_notifications(GattCharacteristic const& ch, const char* what) {
        const auto kind = (static_cast<uint32_t>(ch.CharacteristicProperties()) & 0x10)
                              ? GattClientCharacteristicConfigurationDescriptorValue::Notify
                              : GattClientCharacteristicConfigurationDescriptorValue::Indicate;
        auto st = ch.WriteClientCharacteristicConfigurationDescriptorWithResultAsync(kind).get();
        g_log.info(std::string("enable ") + what + " notifications status=" + comm_status(st.Status()) + protocol_error(st.ProtocolError()));
        if (st.Status() != GattCommunicationStatus::Success) throw std::runtime_error(std::string("cannot enable ") + what + " notifications");
    }

    void do_register(Options const& o, BluetoothCacheMode mode) {
        g_log.info("registration step (setup characteristics)");
        setup_write = find_char(ace::kSetupWriteUuid, mode);
        setup_notify = find_char(ace::kSetupNotifyUuid, mode);
        if (!setup_write || !setup_notify) {
            g_log.warn("setup characteristics not found: skipping registration (run 'services' to see what exists)");
            return;
        }
        g_log.info(std::string("setup write  ") + ace::kSetupWriteUuid + " [" + props_str(setup_write.CharacteristicProperties()) + "]");
        g_log.info(std::string("setup notify ") + ace::kSetupNotifyUuid + " [" + props_str(setup_notify.CharacteristicProperties()) + "]");
        setup_notify.ValueChanged([this](GattCharacteristic const&, GattValueChangedEventArgs const& a) {
            ace::Bytes b = from_buffer(a.CharacteristicValue());
            g_log.info("RX(setup) " + ace::to_hex(b, " "));
            {
                std::lock_guard<std::mutex> g(m);
                setup_inbox.push_back(std::move(b));
            }
            cv.notify_all();
        });
        enable_notifications(setup_notify, "setup");

        ace::Bytes token = ace::kPlaceholderToken;
        if (o.token == "random") token = ace::random_token();
        else if (o.token != "placeholder") token = ace::from_hex(o.token);
        g_log.info("registration token: " + std::string(o.token == "placeholder" ? "placeholder (redacted; not a working credential)" : o.token == "random" ? "random " + ace::to_hex(token) : "custom"));
        send_on(setup_write, ace::registration_message(token), "setup");

        std::unique_lock<std::mutex> lk(m);
        if (!cv.wait_for(lk, std::chrono::milliseconds(o.timeout_ms), [this] { return !setup_inbox.empty(); })) {
            g_log.warn("no reply on the setup characteristic within " + std::to_string(o.timeout_ms) + " ms");
            return;
        }
        const ace::Bytes r = setup_inbox.front();
        g_log.info("registration reply: " + ace::to_hex(r, " ") + (r == ace::from_hex("01070000020000") ? "   (same as the phone got)" : "   (differs from the phone's 01 07 00 00 02 00 00)"));
    }

    GattCharacteristic find_char(const std::string& uuid, BluetoothCacheMode mode) {
        auto r = service.GetCharacteristicsForUuidAsync(parse_guid(uuid), mode).get();
        g_log.debug("characteristic " + uuid + " status=" + comm_status(r.Status()) + " found=" + std::to_string(r.Characteristics().Size()));
        if (r.Status() != GattCommunicationStatus::Success || r.Characteristics().Size() == 0) return nullptr;
        return r.Characteristics().GetAt(0);
    }

    bool send_on(GattCharacteristic const& ch, const ace::Bytes& b, const char* what) {
        const uint32_t props = static_cast<uint32_t>(ch.CharacteristicProperties());
        const GattWriteOption opt = (props & 0x04) ? GattWriteOption::WriteWithoutResponse : GattWriteOption::WriteWithResponse;
        g_log.info(std::string("TX ") + what + " " + ace::to_hex(b, " ") + "   (" +
                   (opt == GattWriteOption::WriteWithoutResponse ? "write-without-response" : "write-with-response") + ")");
        auto r = ch.WriteValueWithResultAsync(to_buffer(b), opt).get();
        g_log.debug("write status=" + comm_status(r.Status()) + protocol_error(r.ProtocolError()));
        return r.Status() == GattCommunicationStatus::Success;
    }

    // Sends a command and waits for its response; every other frame is logged as it arrives.
    bool request(const ace::Bytes& cmd, int timeout_ms) {
        { std::lock_guard<std::mutex> g(m); inbox.clear(); }
        if (!send_on(write, cmd, "control")) {
            g_log.error("write failed");
            return false;
        }
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
        std::unique_lock<std::mutex> lk(m);
        while (true) {
            while (!inbox.empty()) {
                ace::Bytes b = std::move(inbox.front());
                inbox.pop_front();
                if (ace::matches(cmd, b)) {
                    g_log.info(ace::is_ack(cmd, b) ? "OK (ack)" : "reply: " + ace::describe(b));
                    return true;
                }
            }
            if (cv.wait_until(lk, deadline) == std::cv_status::timeout && inbox.empty()) {
                g_log.error("no reply within " + std::to_string(timeout_ms) + " ms");
                return false;
            }
        }
    }

    void close() {
        try {
            if (notify) notify.WriteClientCharacteristicConfigurationDescriptorAsync(GattClientCharacteristicConfigurationDescriptorValue::None).get();
        } catch (...) {
        }
        if (session) session.Close();
        if (dev) dev.Close();
    }
};

// ---------------------------------------------------------------- main

static Options parse_options(int argc, char** argv) {
    Options o;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto val = [&](const char* key) { return a.substr(std::string(key).size()); };
        if (a == "--quiet") o.quiet = true;
        else if (a == "--cached") o.cached = true;
        else if (a == "--no-session") o.no_session = true;
        else if (a == "--no-register") o.no_register = true;
        else if (a.rfind("--token=", 0) == 0) o.token = val("--token=");
        else if (a.rfind("--log=", 0) == 0) o.log_path = val("--log=");
        else if (a.rfind("--timeout=", 0) == 0) o.timeout_ms = std::stoi(val("--timeout="));
        else if (a.rfind("--write-uuid=", 0) == 0) o.write_uuid = ace::lower(val("--write-uuid="));
        else if (a.rfind("--notify-uuid=", 0) == 0) o.notify_uuid = ace::lower(val("--notify-uuid="));
        else if (a.rfind("--", 0) == 0) throw std::invalid_argument("unknown option " + a);
        else o.pos.push_back(a);
    }
    return o;
}

static int run(Options const& o) {
    const auto& p = o.pos;
    if (p.empty() || p[0] == "help") {
        std::cout << kHelp;
        return p.empty() ? 1 : 0;
    }
    log_environment();
    if (p[0] == "list") { cmd_list(); return 0; }
    if (p[0] == "scan") { cmd_scan(p.size() > 1 ? std::stoi(p[1]) : 8); return 0; }
    if (p.size() < 2) { std::cout << kHelp; return 1; }

    const std::string target = p[0], cmd = p[1], value = p.size() > 2 ? p[2] : "";

    // Validate and build the command before touching Bluetooth.
    ace::Bytes bytes;
    if (cmd == "mode") bytes = ace::mode_command(value);
    else if (cmd == "bass") bytes = ace::bass_command(std::stoi(value));
    else if (cmd == "treble") bytes = ace::treble_command(std::stoi(value));
    else if (cmd == "balance") bytes = ace::balance_command(std::stoi(value));
    else if (cmd == "loudness") bytes = ace::loudness_command(ace::lower(value) == "on" || value == "1");
    else if (cmd == "get") bytes = ace::get_command(value);
    else if (cmd == "raw") bytes = ace::from_hex(value);
    else if (cmd != "services" && cmd != "probe" && cmd != "sniff") throw std::invalid_argument("unknown command '" + cmd + "' (ace help)");

    if (cmd == "services") {
        BluetoothLEDevice dev = open_device(target);
        dump_services(dev, o.cached ? BluetoothCacheMode::Cached : BluetoothCacheMode::Uncached);
        dev.Close();
        return 0;
    }

    Link link;
    int rc = 0;
    try {
        link.connect(target, o);
        if (cmd == "probe") {
            for (const auto& g : ace::getters()) {
                g_log.info(std::string("--- ") + g.name);
                if (!link.request(ace::Bytes{0x00, g.group, g.pdu}, o.timeout_ms)) rc = 3;
            }
        } else if (cmd == "sniff") {
            const int secs = value.empty() ? 30 : std::stoi(value);
            g_log.info("listening for " + std::to_string(secs) + " s (change volume / noise mode on the headphones)...");
            std::this_thread::sleep_for(std::chrono::seconds(secs));
        } else if (!link.request(bytes, o.timeout_ms)) {
            rc = 3;
        }
    } catch (...) {
        link.close();
        throw;
    }
    link.close();
    return rc;
}

int main(int argc, char** argv) {
    SetConsoleOutputCP(CP_UTF8);
    winrt::init_apartment();
    Options o;
    try {
        o = parse_options(argc, argv);
        g_log.verbose = !o.quiet;
        if (o.log_path.empty()) {
            const std::time_t t = std::time(nullptr);
            std::tm tm{};
            localtime_s(&tm, &t);
            char b[64];
            std::snprintf(b, sizeof b, "ace_debug_%04d%02d%02d_%02d%02d%02d.log", tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday,
                          tm.tm_hour, tm.tm_min, tm.tm_sec);
            o.log_path = b;
        }
        g_log.open(o.log_path);
        const int rc = run(o);
        if (!g_log.path().empty()) g_log.info("log saved to " + g_log.path());
        return rc;
    } catch (winrt::hresult_error const& e) {
        g_log.error("Windows error " + hex_error(e));
        g_log.error("log saved to " + g_log.path());
        return 2;
    } catch (std::exception const& e) {
        g_log.error(std::string("error: ") + e.what());
        g_log.error("log saved to " + g_log.path());
        return 2;
    }
}
