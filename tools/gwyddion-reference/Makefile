CC ?= cc
PKG_CONFIG ?= pkg-config
GWYDDION_PREFIX ?= /usr
TARGET := spmkit-gwyddion-roughness-reference
SOURCE := gwyddion_roughness_reference.c
GWY_PKG_CONFIG_PATH := $(GWYDDION_PREFIX)/lib/pkgconfig$(if $(PKG_CONFIG_PATH),:$(PKG_CONFIG_PATH))
GWY_CFLAGS := $(shell PKG_CONFIG_PATH="$(GWY_PKG_CONFIG_PATH)" $(PKG_CONFIG) --cflags gwyddion)
GWY_SYSTEM_CFLAGS := $(patsubst -I%,-isystem %,$(GWY_CFLAGS))
CPPFLAGS += $(GWY_SYSTEM_CFLAGS)
CFLAGS += -std=c11 -O2 -g0 -Wall -Wextra -Werror -fno-fast-math
LDLIBS += $(shell PKG_CONFIG_PATH="$(GWY_PKG_CONFIG_PATH)" $(PKG_CONFIG) --libs gwyddion) -lm

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SOURCE)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ $< $(LDLIBS)

clean:
	rm -f $(TARGET)
