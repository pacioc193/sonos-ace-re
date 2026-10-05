// Self-contained tests for ace_protocol.hpp (no framework). Byte vectors come from the
// captures documented in captures/EXPERIMENTS.md.
#include <cstdlib>
#include <iostream>

#include "../core/ace_protocol.hpp"

static int failures = 0;
#define CHECK(cond)                                                              \
    do {                                                                         \
        if (!(cond)) {                                                           \
            std::cerr << "FAIL " << __FILE__ << ":" << __LINE__ << "  " #cond "\n"; \
            ++failures;                                                          \
        }                                                                        \
    } while (0)

static std::string hex(const ace::Bytes& b) { return ace::to_hex(b); }

template <class F>
static bool throws(F f) {
    try {
        f();
    } catch (const std::exception&) {
        return true;
    }
    return false;
}

int main() {
    // EXP-01/02: modes
    CHECK(hex(ace::mode_command("aware")) == "00020f02");
    CHECK(hex(ace::mode_command("off")) == "00020f00");
    CHECK(hex(ace::mode_command("ANC")) == "00020f01");
    CHECK(throws([] { ace::mode_command("loud"); }));

    // EXP-02: signed int8 values
    CHECK(hex(ace::bass_command(10)) == "00021e0a");
    CHECK(hex(ace::bass_command(-10)) == "00021ef6");
    CHECK(hex(ace::bass_command(-1)) == "00021eff");
    CHECK(hex(ace::treble_command(-6)) == "00021ffa");
    CHECK(hex(ace::balance_command(-3)) == "000222fd");
    CHECK(hex(ace::balance_command(0)) == "00022200");
    CHECK(hex(ace::loudness_command(true)) == "00022001");
    CHECK(throws([] { ace::bass_command(11); }));
    CHECK(throws([] { ace::treble_command(-11); }));

    // getters
    CHECK(hex(ace::get_command("anc")) == "00020e");
    CHECK(hex(ace::get_command("eq")) == "00021c");
    CHECK(hex(ace::get_command("volume")) == "000303");
    CHECK(throws([] { ace::get_command("bogus"); }));

    // acks and matching
    const auto cmd = ace::bass_command(4);
    CHECK(ace::is_ack(cmd, ace::from_hex("02021e00")));
    CHECK(!ace::is_ack(cmd, ace::from_hex("02021f00")));
    CHECK(!ace::is_ack(cmd, ace::from_hex("02021e01")));
    CHECK(ace::matches(ace::get_command("eq"), ace::from_hex("02021c00040001")));
    CHECK(!ace::matches(ace::get_command("eq"), ace::from_hex("01038041")));

    // decoding of real replies
    CHECK(ace::describe(ace::from_hex("02021c00040001")).find("bass=4 treble=0 loudness=1") != std::string::npos);
    CHECK(ace::describe(ace::from_hex("02020e0001")).find("mode=anc") != std::string::npos);
    CHECK(ace::describe(ace::from_hex("0202090009536f6e6f7320416365")).find("name=\"Sonos Ace\"") != std::string::npos);
    CHECK(ace::describe(ace::from_hex("02021802")).find("COMMAND_NOT_SUPPORTED") != std::string::npos);
    CHECK(ace::describe(ace::from_hex("010380" "26")).find("volume=38") != std::string::npos);
    CHECK(ace::describe(ace::from_hex("02022100f6")).find("balance=-10") != std::string::npos);

    // hex parsing
    CHECK(hex(ace::from_hex("00 02:0f,01")) == "00020f01");
    CHECK(throws([] { ace::from_hex("0g"); }));
    CHECK(throws([] { ace::from_hex("abc"); }));
    CHECK(hex(ace::registration_message(ace::kPlaceholderToken)) == "010604001400000010" "00000000000000000000000000000000");
    CHECK(ace::registration_message(ace::kPlaceholderToken).size() == 25);
    CHECK(throws([] { ace::registration_message(ace::Bytes(15)); }));
    CHECK(ace::random_token().size() == 16);

    if (failures) {
        std::cerr << failures << " test(s) failed\n";
        return 1;
    }
    std::cout << "all core tests passed\n";
    return 0;
}
