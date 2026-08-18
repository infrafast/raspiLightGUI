#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace displayctl_icons {

constexpr int kWidth = 128;
constexpr int kHeight = 64;
constexpr int kPages = kHeight / 8;
constexpr int kReservedTopRows = 16;
constexpr int kArtworkHeight = kHeight - kReservedTopRows;
constexpr int kArtworkWidth = 96; // 128 * 3 / 4, preserving aspect ratio.
constexpr int kArtworkXOffset = (kWidth - kArtworkWidth) / 2;
constexpr std::size_t kSize = kWidth * kPages;
using Framebuffer = std::array<std::uint8_t, kSize>;

constexpr void pixel(Framebuffer& fb, int x, int y) {
    if (x < 0 || x >= kWidth || y < 0 || y >= kHeight) return;
    fb[static_cast<std::size_t>((y / 8) * kWidth + x)] |=
        static_cast<std::uint8_t>(1u << (y & 7));
}

constexpr bool get_pixel(const Framebuffer& fb, int x, int y) {
    if (x < 0 || x >= kWidth || y < 0 || y >= kHeight) return false;
    return (fb[static_cast<std::size_t>((y / 8) * kWidth + x)] &
            static_cast<std::uint8_t>(1u << (y & 7))) != 0;
}

constexpr void filled_rect(Framebuffer& fb, int x0, int y0, int x1, int y1) {
    for (int y = y0; y <= y1; ++y)
        for (int x = x0; x <= x1; ++x)
            pixel(fb, x, y);
}

constexpr void line(Framebuffer& fb, int x0, int y0, int x1, int y1, int thickness = 1) {
    int dx = x1 >= x0 ? x1 - x0 : x0 - x1;
    int sx = x0 < x1 ? 1 : -1;
    int dy_abs = y1 >= y0 ? y1 - y0 : y0 - y1;
    int dy = -dy_abs;
    int sy = y0 < y1 ? 1 : -1;
    int err = dx + dy;
    const int radius = thickness / 2;

    while (true) {
        for (int oy = -radius; oy <= radius; ++oy)
            for (int ox = -radius; ox <= radius; ++ox)
                pixel(fb, x0 + ox, y0 + oy);
        if (x0 == x1 && y0 == y1) break;
        const int e2 = 2 * err;
        if (e2 >= dy) { err += dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
    }
}

constexpr void ring(Framebuffer& fb, int cx, int cy, int inner_r2, int outer_r2,
                    bool top_gap = false) {
    for (int y = 0; y < kHeight; ++y) {
        for (int x = 0; x < kWidth; ++x) {
            const int dx = x - cx;
            const int dy = y - cy;
            const int r2 = dx * dx + dy * dy;
            if (r2 < inner_r2 || r2 > outer_r2) continue;
            if (top_gap && dy < -8 && dx > -8 && dx < 8) continue;
            pixel(fb, x, y);
        }
    }
}

constexpr void triangle_outline(Framebuffer& fb, int ax, int ay, int bx, int by,
                                int cx, int cy, int thickness) {
    line(fb, ax, ay, bx, by, thickness);
    line(fb, bx, by, cx, cy, thickness);
    line(fb, cx, cy, ax, ay, thickness);
}

// Scale a full 128x64 source uniformly to 96x48 and place it in rows 16..63.
// This guarantees that rows 0..15 stay completely blank for every icon while
// preserving the source artwork aspect ratio.
constexpr Framebuffer fit_below_reserved_area(const Framebuffer& source) {
    Framebuffer output{};
    for (int y = 0; y < kArtworkHeight; ++y) {
        const int source_y = (y * kHeight) / kArtworkHeight;
        for (int x = 0; x < kArtworkWidth; ++x) {
            const int source_x = (x * kWidth) / kArtworkWidth;
            if (get_pixel(source, source_x, source_y)) {
                pixel(output, kArtworkXOffset + x, kReservedTopRows + y);
            }
        }
    }
    return output;
}

constexpr Framebuffer make_boot_source() {
    Framebuffer fb{};
    // Hourglass: two horizontal caps, crossed sides and a compact sand pile.
    line(fb, 43, 10, 85, 10, 4);
    line(fb, 43, 54, 85, 54, 4);
    line(fb, 46, 13, 82, 51, 3);
    line(fb, 82, 13, 46, 51, 3);
    filled_rect(fb, 58, 29, 70, 35);
    line(fb, 53, 45, 75, 45, 2);
    return fb;
}

constexpr Framebuffer make_shutdown_source() {
    Framebuffer fb{};
    // Power symbol only; no directional arrow.
    ring(fb, 64, 34, 17 * 17, 22 * 22, true);
    line(fb, 64, 8, 64, 34, 5);
    return fb;
}

constexpr Framebuffer make_reboot_source() {
    Framebuffer fb{};
    // Two broken halves of one circular arrow, leaving clear gaps left/right.
    for (int y = 0; y < kHeight; ++y) {
        for (int x = 0; x < kWidth; ++x) {
            const int dx = x - 64;
            const int dy = y - 32;
            const int r2 = dx * dx + dy * dy;
            if (r2 < 20 * 20 || r2 > 25 * 25) continue;
            if ((x < 48 && y < 31) || (x > 80 && y > 33)) continue;
            pixel(fb, x, y);
        }
    }
    for (int i = 0; i < 11; ++i) {
        line(fb, 83 - i, 18 + i / 2, 83 - i, 28 - i / 2, 1);
        line(fb, 45 + i, 46 - i / 2, 45 + i, 36 + i / 2, 1);
    }
    return fb;
}

constexpr Framebuffer make_panic_source() {
    Framebuffer fb{};
    triangle_outline(fb, 64, 5, 112, 56, 16, 56, 4);
    filled_rect(fb, 61, 19, 67, 41);
    filled_rect(fb, 61, 47, 67, 52);
    return fb;
}

constexpr Framebuffer make_updating_source() {
    Framebuffer fb{};
    for (int y = 0; y < 50; ++y) {
        for (int x = 35; x < 93; ++x) {
            const int dx = x - 64;
            const int dy = y - 27;
            const int r2 = dx * dx + dy * dy;
            if (r2 < 17 * 17 || r2 > 21 * 21) continue;
            if ((x < 50 && y < 25) || (x > 78 && y > 29)) continue;
            pixel(fb, x, y);
        }
    }
    for (int i = 0; i < 9; ++i) {
        line(fb, 79 - i, 13 + i / 2, 79 - i, 22 - i / 2, 1);
        line(fb, 49 + i, 41 - i / 2, 49 + i, 32 + i / 2, 1);
    }

    line(fb, 24, 54, 104, 54, 2);
    line(fb, 24, 61, 104, 61, 2);
    line(fb, 24, 54, 24, 61, 2);
    line(fb, 104, 54, 104, 61, 2);
    filled_rect(fb, 28, 57, 76, 59);
    return fb;
}

inline constexpr Framebuffer kBoot = fit_below_reserved_area(make_boot_source());
inline constexpr Framebuffer kShutdown = fit_below_reserved_area(make_shutdown_source());
inline constexpr Framebuffer kReboot = fit_below_reserved_area(make_reboot_source());
inline constexpr Framebuffer kPanic = fit_below_reserved_area(make_panic_source());
inline constexpr Framebuffer kUpdating = fit_below_reserved_area(make_updating_source());

static_assert(kBoot.size() == 1024, "SSD1306 framebuffer must be 1024 bytes");

} // namespace displayctl_icons
