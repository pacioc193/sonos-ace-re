// Sonos Ace protocol core: pure C++17, no platform dependencies.
// Mirrors client/ace.py. Protocol notes: protocol/NOTES.md.
#pragma once

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <iomanip>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace ace {

using Bytes = std::vector<uint8_t>;

// GATT UUIDs from the app's identifiers (NOTES.md); roles on a real device are unverified.
inline constexpr const char* kServiceUuid = "0000fe07-0000-1000-8000-00805f9b34fb";
inline constexpr const char* kControlWriteUuid = "c44f42b1-f5cf-479b-b515-9f1bb0099c9a";
inline constexpr const char* kControlNotifyUuid = "c44f42b1-f5cf-479b-b515-9f1bb0099c9b";
inline constexpr const char* kSetupWriteUuid = "c44f42b1-f5cf-479b-b515-9f1bb0099c9e";  // role unverified

inline constexpr const char* kSetupNotifyUuid = "c44f42b1-f5cf-479b-b515-9f1bb0099c9f";  // role unverified

// "Registration" message the phone sends on the setup characteristic right before the first
// command (25 bytes: 9-byte prefix + 16-byte access token), identical in both captures. The
// reply seen on the setup notify characteristic was `01 07 00 00 02 00 00` (accepted).
// The real token is a per-device credential bound to the phone's bond (see protocol/AUTH.md):
// it is intentionally NOT committed. Supply your own with --token=<32 hex digits>.
inline const Bytes kRegistrationPrefix = {0x01, 0x06, 0x04, 0x00, 0x14, 0x00, 0x00, 0x00, 0x10};
inline const Bytes kPlaceholderToken(16, 0x00);  // redacted; not a working credential

inline Bytes registration_message(const Bytes& token) {
    if (token.size() != 16) throw std::invalid_argument("token must be 16 bytes (32 hex digits)");
    Bytes m = kRegistrationPrefix;
    m.insert(m.end(), token.begin(), token.end());
    return m;
}

inline Bytes random_token() {
    std::random_device rd;
    Bytes t(16);
    for (auto& b : t) b = static_cast<uint8_t>(rd() & 0xFF);
    return t;
}

constexpr uint8_t kCatSettings = 0x02;
constexpr uint8_t kIdMode = 0x0F;
constexpr uint8_t kIdBass = 0x1E;
constexpr uint8_t kIdTreble = 0x1F;
constexpr uint8_t kIdLoudness = 0x20;
constexpr uint8_t kIdBalance = 0x22;

inline std::string lower(std::string s) {
    for (auto& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

inline std::string to_hex(const Bytes& b, const char* sep = "") {
    std::ostringstream o;
    for (size_t i = 0; i < b.size(); ++i) {
        if (i) o << sep;
        o << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(b[i]);
    }
    return o.str();
}

inline Bytes from_hex(const std::string& text) {
    std::string h;
    for (char c : text)
        if (std::isxdigit(static_cast<unsigned char>(c))) h += c;
        else if (!(std::isspace(static_cast<unsigned char>(c)) || c == ':' || c == ',' || c == '-'))
            throw std::invalid_argument(std::string("bad hex character '") + c + "'");
    if (h.size() % 2) throw std::invalid_argument("odd number of hex digits");
    Bytes out;
    for (size_t i = 0; i < h.size(); i += 2) out.push_back(static_cast<uint8_t>(std::stoi(h.substr(i, 2), nullptr, 16)));
    return out;
}

// Value in -10..10 as an unsigned byte (two's complement).
inline uint8_t int8(int value) {
    if (value < -10 || value > 10) throw std::out_of_range("value must be between -10 and 10");
    return static_cast<uint8_t>(value & 0xFF);
}

inline Bytes command(uint8_t id, uint8_t value, uint8_t category = kCatSettings) {
    return Bytes{0x00, category, id, value};
}

inline Bytes mode_command(const std::string& name) {
    const std::string n = lower(name);
    if (n == "off") return command(kIdMode, 0x00);
    if (n == "anc") return command(kIdMode, 0x01);
    if (n == "aware" || n == "transparency") return command(kIdMode, 0x02);
    throw std::invalid_argument("unknown mode '" + name + "' (use: anc, aware, off)");
}
inline Bytes bass_command(int v) { return command(kIdBass, int8(v)); }
inline Bytes treble_command(int v) { return command(kIdTreble, int8(v)); }
inline Bytes balance_command(int v) { return command(kIdBalance, int8(v)); }
inline Bytes loudness_command(bool on) { return command(kIdLoudness, on ? 1 : 0); }

struct Getter {
    const char* name;
    uint8_t group;
    uint8_t pdu;
};

// Read-only requests: group 02 = settings, 03 = volume, 00 = status (NOTES.md).
inline const std::vector<Getter>& getters() {
    static const std::vector<Getter> g = {
        {"anc", 0x02, 0x0E},      {"eq", 0x02, 0x1C},        {"balance", 0x02, 0x21},
        {"name", 0x02, 0x09},     {"adaptive-anc", 0x02, 0x37}, {"selfvoice", 0x02, 0x35},
        {"autooff", 0x02, 0x1A},  {"wear", 0x02, 0x0C},      {"spatial", 0x02, 0x10},
        {"buttons", 0x02, 0x04},  {"volume", 0x03, 0x03},    {"info", 0x00, 0x03},
        {"charging", 0x00, 0x04},
    };
    return g;
}

inline Bytes get_command(const std::string& name) {
    const std::string n = lower(name);
    std::string known;
    for (const auto& g : getters()) {
        if (n == g.name) return Bytes{0x00, g.group, g.pdu};
        known += std::string(known.empty() ? "" : ", ") + g.name;
    }
    throw std::invalid_argument("unknown getter '" + name + "' (use: " + known + ")");
}

inline const char* status_name(int s) {
    static const char* names[] = {"OK", "NAMESPACE_NOT_SUPPORTED", "COMMAND_NOT_SUPPORTED",
                                  "INSUFFICIENT_RESOURCES", "INVALID_PARAMETER", "INVALID_STATE",
                                  "INVALID_HEADER", "INVALID_LENGTH", "UNEXPECTED_ERROR", "NO_PERMISSIONS"};
    return (s >= 0 && s <= 9) ? names[s] : "UNKNOWN_STATUS";
}

// A set command is acknowledged by `02 <group> <pdu> 00` (exactly 4 bytes).
inline bool is_ack(const Bytes& cmd, const Bytes& reply) {
    return cmd.size() >= 3 && reply.size() == 4 && reply[0] == 0x02 && reply[1] == cmd[1] &&
           reply[2] == cmd[2] && reply[3] == 0x00;
}

// True if `reply` is the response (type 02) to `cmd` (same group and PDU id).
inline bool matches(const Bytes& cmd, const Bytes& reply) {
    return cmd.size() >= 3 && reply.size() >= 3 && reply[0] == 0x02 && reply[1] == cmd[1] && reply[2] == cmd[2];
}

// Human-readable decode of `02 <group> <pdu> <status> <data...>` or `01 ...` events.
inline std::string describe(const Bytes& r) {
    if (r.size() >= 3 && r[0] == 0x01) {
        std::ostringstream o;
        o << "EVENT group=" << static_cast<int>(r[1]) << " pdu=" << static_cast<int>(r[2])
          << " data=" << to_hex(Bytes(r.begin() + 3, r.end()));
        if (r[1] == 0x03 && r[2] == 0x80 && r.size() >= 4) o << " (volume=" << static_cast<int>(r[3]) << ")";
        return o.str();
    }
    if (r.size() < 4 || r[0] != 0x02) return "UNPARSED " + to_hex(r);
    const int status = r[3];
    const Bytes data(r.begin() + 4, r.end());
    std::ostringstream o;
    o << "RESPONSE group=" << static_cast<int>(r[1]) << " pdu=" << static_cast<int>(r[2]) << " status="
      << status_name(status);
    if (status == 0 && !data.empty()) {
        o << " data=" << to_hex(data);
        if (r[1] == 0x02 && r[2] == 0x1C && data.size() >= 3)
            o << " (bass=" << static_cast<int>(static_cast<int8_t>(data[0])) << " treble="
              << static_cast<int>(static_cast<int8_t>(data[1])) << " loudness=" << static_cast<int>(data[2]) << ")";
        else if (r[1] == 0x02 && r[2] == 0x0E) {
            const char* m = data[0] == 0 ? "off" : data[0] == 1 ? "anc" : data[0] == 2 ? "aware" : "?";
            o << " (mode=" << m << ")";
        } else if (r[1] == 0x02 && r[2] == 0x21 && data.size() >= 1)
            o << " (balance=" << static_cast<int>(static_cast<int8_t>(data[0])) << ")";
        else if (r[1] == 0x02 && r[2] == 0x09 && data.size() > 1) {
            const size_t n = std::min<size_t>(data[0], data.size() - 1);
            o << " (name=\"" << std::string(data.begin() + 1, data.begin() + 1 + n) << "\")";
        }
    }
    return o.str();
}

}  // namespace ace
