CXX ?= g++
CPPFLAGS ?=
CXXFLAGS ?= -Os -std=c++17 -Wall -Wextra -Wpedantic -fno-exceptions -fno-rtti -ffunction-sections -fdata-sections -fno-unwind-tables -fno-asynchronous-unwind-tables
LDFLAGS ?= -Wl,--gc-sections

TARGET := displayctl
SOURCE := displayctl.cpp
HEADERS := icons.h

.PHONY: all static clean install

all: $(TARGET)

$(TARGET): $(SOURCE) $(HEADERS)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SOURCE) $(LDFLAGS) -o $@

# Preferred initramfs build: static, garbage-collected and stripped.
static: clean
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -static $(SOURCE) $(LDFLAGS) -Wl,--strip-all -Wl,--build-id=none -o $(TARGET)
	@echo "Built optimized static binary:"
	@ls -lh $(TARGET)
	@file $(TARGET)
	@ldd $(TARGET) 2>&1 || true
	@readelf -l $(TARGET) | grep interpreter || true

install: $(TARGET)
	install -D -m 0755 $(TARGET) /usr/local/bin/displayctl

clean:
	rm -f $(TARGET)
