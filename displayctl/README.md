# DisplayCTL

`displayctl` is a deliberately tiny one-shot SSD1306 renderer for Raspberry Pi.
It is intended to bridge the periods where the normal Python raspiLightGUI
process is not running, especially early boot/initramfs and late shutdown.

It has no daemon mode, no fonts, no text renderer and no external image files.
Each command selects one 128x64 monochrome framebuffer compiled directly into
the executable.

## Commands

```text
displayctl boot
displayctl shutdown
displayctl reboot
displayctl panic
displayctl updating
```

The command opens `/dev/i2c-1`, selects SSD1306 address `0x3c`, initializes the
controller, transfers exactly one framebuffer and exits. The pixels remain on
the OLED after the process exits.

## Build on Raspberry Pi

```bash
cd displayctl
make
sudo make install
```

For the initramfs use case, prefer a genuinely static executable:

```bash
make static
file displayctl
ldd displayctl
```

`ldd` should report that the executable is not dynamically linked. A static
binary still needs the kernel I2C device node and the Raspberry Pi I2C driver to
exist in the initramfs before it can display anything.

## Bitmap format

The SSD1306 is configured for horizontal addressing and expects 1024 bytes for
a 128x64 display. Bitmaps in `displayctl.cpp` therefore contain 8 pages of 128
bytes; bit 0 is the top pixel of each 8-pixel page.

The current arrays are intentionally placeholder/blank images. Replace each
1024-byte array with the final artwork while keeping the command names stable.
No runtime asset files are required.

## Boot ownership model

The intended lifecycle is:

```text
firmware/kernel -> initramfs -> displayctl boot -> systemd -> raspiLightGUI
                                                     |
                                                     +-> interactive OLED UI

shutdown/reboot -> raspiLightGUI stops -> displayctl shutdown|reboot -> poweroff/reboot
```

Do not run `displayctl` concurrently with raspiLightGUI. Both programs own the
same SSD1306 and I2C address; lifecycle ordering must ensure that only one is
writing at a time.

## Initramfs integration note

Copying the executable alone into an initramfs is not sufficient. The image
must also contain/activate the I2C controller support needed to expose
`/dev/i2c-1`. The exact hook depends on the Raspberry Pi OS/initramfs tooling,
so initramfs installation is intentionally kept separate from this minimal
renderer.
