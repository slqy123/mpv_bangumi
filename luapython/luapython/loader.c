#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>
#include <dlfcn.h>

void* dl_addr = NULL;

static int loadPython(lua_State* L){
    if(dl_addr != NULL){
        luaL_error(L, "luapython has been loaded");
        return 0;
    }
    const char* path = lua_tostring(L, -1);
    dl_addr = dlopen(path, RTLD_LAZY | RTLD_GLOBAL);
    if(!dl_addr){
        luaL_error(L, "Failed to load %s\n%s", path, dlerror());
    }
    return 0;
}

static int isPythonLoaded(lua_State* L){
    lua_pushboolean(L, dl_addr != NULL);
    return 1;
}

static int unloadPython(lua_State* L){
    // TODO
    return 0;

    if(!dl_addr){
        luaL_error(L, "luapython has not been loaded. You may load luapython first by calling luapython.load(<python_version>).");
        return 0;
    }
    //Py_Finalize();
    int ret = dlclose(dl_addr);
    if(!ret){
        luaL_error(L, "unloadPython: dlclose error. \n%s", dlerror());
        return 0;
    }
    return 0;
}

int luaopen_luapython_loader(lua_State *L) {
    lua_createtable(L, 0, 2);
    lua_pushcfunction(L, loadPython);
    lua_setfield(L, -2, "loadNative");
    lua_pushcfunction(L, isPythonLoaded);
    lua_setfield(L, -2, "isLoadedNative");
    lua_pushcfunction(L, unloadPython);
    lua_setfield(L, -2, "unloadNative");
    return 1;
}
