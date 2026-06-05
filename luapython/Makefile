CC = gcc
LUA_INCDIR ?= /usr/include
CFLAGS ?= -I$(LUA_INCDIR)
CFLAGS += $(shell python3-config --includes)
LUA_LIBDIR ?= /usr/lib
LUA_VERSION ?= 5.4
LDFLAGS = -L$(LUA_LIBDIR) $(shell python3-config --ldflags)

PREFIX ?= /usr

CC ?= gcc

# It appears that -O0 is necessary to avoid segmentation faults when running the tests. We should investigate this further but for now we will keep it as is.
CFLAGS += -O0 -fPIC -g -I./luapython/
LUA_VERSION ?= 5.4
LDFLAGS += -lm -ldl -shared

TARGET = luapython.so

INSTALL_LIBDIR ?= $(PREFIX)/lib/lua/$(LUA_VERSION)
INSTALL_LUADIR ?= $(PREFIX)/share/lua/$(LUA_VERSION)

SOURCES = \
    luapython/luapython.c \
    luapython/number.c \
    luapython/string.c \
    luapython/set.c \
    luapython/dict.c \
    luapython/list.c \
    luapython/tuple.c \
    luapython/module.c \
    luapython/function.c \
    luapython/class.c \
    luapython/iter.c \
    luapython/tools.c

# SOURCES = $(wildcard *.c)

OBJECTS = $(SOURCES:.c=.o)

all: $(TARGET) loader.so
	@echo CFLAGS: $(CFLAGS)

$(TARGET): $(OBJECTS)
	$(CC) $(LDFLAGS) -shared -o $@ $^

loader.so: luapython/loader.c
	$(CC) $(CFLAGS) $(LDFLAGS) -shared -o loader.so luapython/loader.c

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -rf luapython/*.o
	rm -f *.so
	rm -f *.o

install: 
	mkdir -p $(INSTALL_LIBDIR)/luapython
	mkdir -p $(INSTALL_LUADIR)/luapython
	cp $(TARGET) $(INSTALL_LIBDIR)/luapython/core.so
	cp loader.so $(INSTALL_LIBDIR)/luapython/loader.so
	cp luapython/*.lua $(INSTALL_LUADIR)/luapython

uninstall:
	rm -rf $(INSTALL_LUADIR)/luapython
	rm -rf $(INSTALL_LIBDIR)/luapython

