#include "luapython.h"

int module_index(lua_State* L) {
    if (!lua_isstring(L, -1)) {
        luaL_error(L, "module_index: Attempt to index a %s value", luaL_typename(L, -1));
        return 0;
    }
    const char* key = lua_tostring(L, -1);
    PyObject* module = convertPython(L, -2);
    PyObject* value = PyObject_GetAttrString(module, key);
    if (value == NULL) {
        const char* moduleName = getPythonTypeName(module);
        Py_XDECREF(module);
        Py_XDECREF(value);
        luaL_error(L, "module_index: Attribute %s not found in module %s", key, moduleName);
        return 0;
    }
    Py_XDECREF(module);
    pushLua(L, value);
    return 1;
}

int module_tostring(lua_State* L) {
    PyObject* module = *(PyObject**)lua_touserdata(L, -1);
    Py_XINCREF(module);
    if (!module) {
        Py_XDECREF(module);
        luaL_error(L, "module_tostring: Invalid Python module");
        return 0;
    }
    PyObject* str = PyObject_Str(module);
    Py_XDECREF(module);
    pushLua(L, str);
    return 1;
}

int table_module_index = 0;

int pushModuleLua(lua_State* L, PyObject* obj) {
    if (table_module_index != 0) {
        void* point = lua_newuserdata(L, sizeof(PyObject*));
        *(PyObject**)point = obj;
        lua_rawgeti(L, LUA_REGISTRYINDEX, table_module_index);
        if (!lua_istable(L, -1)) {
            luaL_error(L, "pushModuleLua: Internal error, class index is a %s", luaL_typename(L, -1));
            return 0;
        }
        lua_setmetatable(L, -2);
        return 1;
    }
    lua_createtable(L, 0, 4);
    lua_pushcfunction(L, module_index);
    lua_setfield(L, -2, "__index");
    lua_pushstring(L, PYTHON_MODULE_NAME);
    lua_setfield(L, -2, "__name");
    lua_pushcfunction(L, python_gc);
    lua_setfield(L, -2, "__gc");
    lua_pushcfunction(L, python_tostring);
    lua_setfield(L, -2, "__tostring");
    table_module_index = luaL_ref(L, LUA_REGISTRYINDEX);
    return pushModuleLua(L, obj);
}
