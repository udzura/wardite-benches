ROOT := $(abspath ..)
WARDITE_DIR ?= $(ROOT)/../wardite
SPINEL ?= spinel
SPINELFLAGS ?= -O2

.PHONY: wardite
wardite:
	mkdir -p "$(ROOT)/build"
	cd "$(WARDITE_DIR)" && "$(SPINEL)" -I lib --strict-require $(SPINELFLAGS) exe/wardite -o "$(ROOT)/build/wardite"
	{ git -C "$(WARDITE_DIR)" describe --always --dirty; "$(SPINEL)" --version; } > "$(ROOT)/build/wardite.version"
