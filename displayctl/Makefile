CXX ?= g++
CPPFLAGS ?=
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra -Wpedantic -fno-exceptions -fno-rtti
LDFLAGS ?=

TARGET := displayctl
SOURCE := displayctl.cpp

.PHONY: all static clean install

all: $(TARGET)

$(TARGET): $(SOURCE)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SOURCE) $(LDFLAGS) -o $@

# Preferred initramfs build. Requires a static C++ toolchain/libc on the build host.
static: clean
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -static $(SOURCE) $(LDFLAGS) -o $(TARGET)
	@echo "Built static binary:"
	@file $(TARGET)
	@ldd $(TARGET) 2>&1 || true

install: $(TARGET)
	install -D -m 0755 $(TARGET) /usr/local/bin/displayctl

clean:
	rm -f $(TARGET)
