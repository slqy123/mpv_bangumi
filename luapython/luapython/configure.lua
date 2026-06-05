local args = {...}

local prefix_lua = "/usr"
local prefix_python = "/usr"
local lua_version
local libpython = "libpython3.so"
local compiler = "gcc"
local conda_python

local help_text = [[
Usage: lua configure.lua or luajit configure.lua

Options:

    --help, -h                              Show this help message.
    --lua-version=<lua-version>             Lua version(5.1, 5.2, 5.3, 5.4, luajit)
                                                Default: _VERSION in Lua enviorment
    --python-lib=<python-lib>               Python libname
                                                Default: libpython3.so
    --compiler=<compiler>                   Compiler executable
                                                Default: gcc (which is recommended)
    --conda-lua=<true or false>             Whether enable lua in conda. 
                                                Default is false.
    --conda-python=<true or false>          Whether enable python in conda. 
                                                Default is true if in conda enviorment.]]

for _, arg in ipairs(args) do
    if arg == "--help" or arg == "-h" then
        print(help_text)
        return
    end
    if arg:match("%-%-lua%-version=") then
        lua_version = arg:match("%-%-lua%-version=(.+)$")
        if lua_version == "luajit" then
            lua_version = "luajit"
        end
    end
    if arg:match("%-%-python%-lib=") then
        libpython = arg:match("%-%-python-%lib=(.+)$")
    end
    if arg:match("%-%-compiler=") then
        compiler = arg:match("%-%-compiler=(.+)$")
    end
    if arg:match("%-%-conda%-lua=") then
        local conda_lua = arg:match("%-%-conda%-lua=(.+)$") == "true"
        local prefix = os.getenv("CONDA_PREFIX")
        if conda_lua and prefix then
            prefix_lua = prefix
        else
            error("Conda Lua requested but CONDA_PREFIX is not set. You may not be in a conda environment. \nTo activate conda environment, use \"conda activate <env_name>\". ")
        end
    end
    if arg:match("%-%-conda%-python=") then
        local conda_python1 = arg:match("%-%-conda%-python=(.+)$") == "true"
        local prefix = os.getenv("CONDA_PREFIX")
        conda_python = false
        if conda_python1 and prefix then
            prefix_python = prefix
            conda_python = true
        else
            error("Conda Python requested but CONDA_PREFIX is not set. You may not be in a conda environment. \nTo activate conda environment, use \"conda activate <env_name>\". ")
        end
    end
end

local function getLuaVersion(force)
    if _G.jit and not(force) then
        return "luajit"
    end
    return _VERSION:match("Lua (%d+%.%d+)")
end

lua_version = lua_version or getLuaVersion()

local function commandExists(command)
    local result, exit_type, exit_code = os.execute("command -v "..command)
    return result and exit_type == "exit" and exit_code == 0
end

local function findPythonLib()
    local f = io.popen("find "..prefix_python.."/lib -name '"..libpython.."'")
    local path = f:read("*a")
    f:close()
    if not path or path == "" then
        local f2 = io.popen("find "..prefix_python.."/lib -name 'libpython3.*.so*'")
        local filename = {}
        for path1 in f2:lines() do
            table.insert(filename, path1)
        end
        f2:close()
        if #filename == 0 then
            error("Failed to find "..libpython.." in "..prefix_python.."/lib. Please check your python installation or use --python-lib option to specify the libpython name.")
        end
        table.sort(filename)
        path = filename[#filename]
    end
    path = path:gsub("\n", "")
    return path
end

if commandExists("python3") then
    local version_stream = io.popen("python3 --version")
    local version = version_stream:read("*a")
    version_stream:close()
    print("Found python3 version:" ..version)
else
    error("python3 not found. Please install python3 package.")
end

if commandExists("python3-config") then
    print("Found python3-config")
else
    error("python3-config not found. Please install python3 package.")
end

if not commandExists(compiler) then
    error(compiler.." not found. Please install "..compiler.." package.")
end

if conda_python == nil then
    local prefix = os.getenv("CONDA_PREFIX")
    if prefix then
        prefix_python = prefix
    end
end

local ldflags = ""
do
    --local f = io.popen("python3-config --ldflags")
    --ldflags = f:read("*a")
    --f:close()
    --if not ldflags or ldflags == "" then
        --error("Failed to get python ldflags from python3-config.")
    --end
    --ldflags = ldflags:gsub("\n", " ")
    if lua_version == "luajit" then
        ldflags = ldflags .. " "..prefix_lua.."/lib/libluajit-"..getLuaVersion(true)..".so"
    else
        ldflags = ldflags .. " "..prefix_lua.."/lib/liblua.so."..lua_version
    end
end

ldflags = ldflags .. " "..findPythonLib()

local makeprefix = string.format([[
PREFIX = %s
CXX = %s
LUA_VERSION = %s
LUA_VERSION_A = %s
LDFLAGS = %s
LD_LIBRARY_PATH=%s

]], prefix_lua, compiler, lua_version, lua_version == "luajit" and getLuaVersion(true) or lua_version, ldflags, prefix_python.."/lib")

print("Using compiler: "..compiler)
print("Using lua version: "..lua_version)
print("Using python lib: "..libpython)
print("Using prefix: "..prefix_lua)
print("Using python prefix: "..prefix_python)

local make = [[PREFIX ?= /usr

LUA_VERSION ?= 5.4

CXX ?= gcc
CXXFLAGS = -shared -fPIC -g -I$(PREFIX)/include/lua$(LUA_VERSION) $(shell python3-config --includes) -DPREFIX="\"$(PREFIX)\"" -DPYTHON_LIB="\"libpython3.so\""
LDFLAGS += -lm -ldl

SOURCES = luapython.c number.c string.c set.c dict.c list.c tuple.c module.c function.c class.c tools.c iter.c
OBJECTS = $(SOURCES:.c=.o)

TARGET = luapython.so

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CXX) -shared -o $@ $^ $(LDFLAGS)

%.o: %.c
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(OBJECTS) $(TARGET)

install: $(TARGET)
	mkdir -p $(PREFIX)/local/lib/lua/$(LUA_VERSION)/luapython/
	cp $(TARGET) $(PREFIX)/local/lib/lua/$(LUA_VERSION)/
	cp convert_pre.lua $(PREFIX)/local/lib/lua/$(LUA_VERSION)/luapython/
	cp python_init.lua $(PREFIX)/local/lib/lua/$(LUA_VERSION)/luapython/
	cp python_function.lua $(PREFIX)/local/lib/lua/$(LUA_VERSION)/luapython/
	cp import.lua $(PREFIX)/local/lib/lua/$(LUA_VERSION)/luapython/
	cp tools.lua $(PREFIX)/local/lib/lua/$(LUA_VERSION)/luapython/
	cp iter.lua $(PREFIX)/local/lib/lua/$(LUA_VERSION)/luapython/

uninstall:
	rm -rf $(PREFIX)/local/lib/lua/$(LUA_VERSION)/$(TARGET)
	rm -rf $(PREFIX)/local/lib/lua/$(LUA_VERSION)/luapython/

.PHONY: all clean install uninstall
]]

local f = io.open("Makefile", "w")
if not f then
    error("Failed to open Makefile for writing.")
end
f:write(makeprefix)
f:write(make)
f:close()