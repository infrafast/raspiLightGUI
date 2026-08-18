#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <string_view>
#include <sys/ioctl.h>
#include <unistd.h>

#include <linux/i2c-dev.h>

namespace {
constexpr const char* kI2cDevice = "/dev/i2c-1";
constexpr int kI2cAddress = 0x3C;
constexpr int kWidth = 128;
constexpr int kHeight = 64;
constexpr int kPages = kHeight / 8;
constexpr std::size_t kFramebufferSize = kWidth * kPages;

using Bitmap = const std::uint8_t (&)[kFramebufferSize];

constexpr std::uint8_t kBoot[kFramebufferSize] = {
    // Placeholder icon. Replace with generated 128x64 monochrome bitmap bytes.
    0x00
};
constexpr std::uint8_t kShutdown[kFramebufferSize] = {0x00};
constexpr std::uint8_t kReboot[kFramebufferSize] = {0x00};
constexpr std::uint8_t kPanic[kFramebufferSize] = {0x00};
constexpr std::uint8_t kUpdating[kFramebufferSize] = {0x00};

bool write_all(int fd, const std::uint8_t* data, std::size_t size) {
    while (size > 0) {
        const ssize_t written = ::write(fd, data, size);
        if (written < 0) {
            if (errno == EINTR) continue;
            return false;
        }
        data += written;
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

const std::uint8_t* select_icon(std::string_view name) {
    if (name == "boot") return kBoot;
    if (name == "shutdown") return kShutdown;
    if (name == "reboot") return kReboot;
    if (name == "panic") return kPanic;
    if (name == "updating") return kUpdating;
    return nullptr;
}

void usage(const char* argv0) {
    std::cerr << "Usage: " << argv0 << " {boot|shutdown|reboot|panic|updating}\n";
}
} // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        usage(argv[0]);
        return 2;
    }

    const auto* bitmap = select_icon(argv[1]);
    if (!bitmap) {
        usage(argv[0]);
        return 2;
    }

    const int fd = ::open(kI2cDevice, O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        std::cerr << "displayctl: cannot open " << kI2cDevice << ": " << std::strerror(errno) << "\n";
        return 1;
    }

    if (::ioctl(fd, I2C_SLAVE, kI2cAddress) < 0) {
        std::cerr << "displayctl: cannot select I2C address 0x3C: " << std::strerror(errno) << "\n";
        ::close(fd);
        return 1;
    }

    const bool ok = init_ssd1306(fd) && show_bitmap(fd, bitmap);
    if (!ok) {
        std::cerr << "displayctl: I2C write failed: " << std::strerror(errno) << "\n";
    }

    ::close(fd);
    return ok ? 0 : 1;
}
