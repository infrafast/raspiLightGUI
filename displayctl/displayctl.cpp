#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <linux/i2c-dev.h>

#include "icons.h"

namespace {
constexpr const char* kI2cDevice = "/dev/i2c-1";
constexpr int kI2cAddress = 0x3C;
constexpr int kWidth = 128;
constexpr int kHeight = 64;
constexpr int kPages = kHeight / 8;
constexpr std::size_t kFramebufferSize = kWidth * kPages;

static_assert(kFramebufferSize == displayctl_icons::kSize,
              "DisplayCTL icon size must match the SSD1306 framebuffer");

template <std::size_t N>
void write_stderr(const char (&message)[N]) {
    std::size_t offset = 0;
    constexpr std::size_t size = N - 1;
    while (offset < size) {
        const ssize_t written = ::write(STDERR_FILENO, message + offset, size - offset);
        if (written < 0) {
            if (errno == EINTR) continue;
            return;
        }
        offset += static_cast<std::size_t>(written);
    }
}

bool write_all(int fd, const std::uint8_t* bytes, std::size_t size) {
    while (size > 0) {
        const ssize_t written = ::write(fd, bytes, size);
        if (written < 0) {
            if (errno == EINTR) continue;
            return false;
        }
        bytes += written;
        size -= static_cast<std::size_t>(written);
    }
    return true;
}

bool command(int fd, std::uint8_t value) {
    const std::uint8_t packet[2] = {0x00, value};
    return write_all(fd, packet, sizeof(packet));
}

bool data(int fd, const std::uint8_t* bytes, std::size_t size) {
    std::uint8_t packet[17];
    packet[0] = 0x40;
    while (size > 0) {
        const std::size_t chunk = size > 16 ? 16 : size;
        std::memcpy(packet + 1, bytes, chunk);
        if (!write_all(fd, packet, chunk + 1)) return false;
        bytes += chunk;
        size -= chunk;
    }
    return true;
}

bool init_ssd1306(int fd) {
    static constexpr std::uint8_t init[] = {
        0xAE,       // display off
        0xD5, 0x80, // clock divide
        0xA8, 0x3F, // multiplex 1/64
        0xD3, 0x00, // display offset
        0x40,       // start line
        0x8D, 0x14, // charge pump
        0x20, 0x00, // horizontal addressing mode
        0xA1,       // segment remap
        0xC8,       // COM scan direction
        0xDA, 0x12, // COM pins
        0x81, 0xCF, // contrast
        0xD9, 0xF1, // precharge
        0xDB, 0x40, // VCOM detect
        0xA4,       // display follows RAM
        0xA6,       // normal display
        0xAF        // display on
    };
    for (const auto byte : init) {
        if (!command(fd, byte)) return false;
    }
    return true;
}

bool show_bitmap(int fd, const std::uint8_t* bitmap) {
    if (!command(fd, 0x21) || !command(fd, 0x00) || !command(fd, 0x7F)) return false;
    if (!command(fd, 0x22) || !command(fd, 0x00) || !command(fd, 0x07)) return false;
    return data(fd, bitmap, kFramebufferSize);
}

const std::uint8_t* select_icon(const char* name) {
    using namespace displayctl_icons;
    if (std::strcmp(name, "boot") == 0) return kBoot.data();
    if (std::strcmp(name, "shutdown") == 0) return kShutdown.data();
    if (std::strcmp(name, "reboot") == 0) return kReboot.data();
    if (std::strcmp(name, "panic") == 0) return kPanic.data();
    if (std::strcmp(name, "updating") == 0) return kUpdating.data();
    return nullptr;
}

void usage() {
    write_stderr("Usage: displayctl {boot|shutdown|reboot|panic|updating}\n");
}
} // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        usage();
        return 2;
    }

    const auto* bitmap = select_icon(argv[1]);
    if (!bitmap) {
        usage();
        return 2;
    }

    const int fd = ::open(kI2cDevice, O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        write_stderr("displayctl: cannot open /dev/i2c-1\n");
        return 1;
    }

    if (::ioctl(fd, I2C_SLAVE, kI2cAddress) < 0) {
        write_stderr("displayctl: cannot select I2C address 0x3C\n");
        ::close(fd);
        return 1;
    }

    const bool ok = init_ssd1306(fd) && show_bitmap(fd, bitmap);
    if (!ok) {
        write_stderr("displayctl: I2C write failed\n");
    }

    ::close(fd);
    return ok ? 0 : 1;
}
