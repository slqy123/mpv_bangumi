#include "luapython.h"

int class_index(lua_State* L) {
    if (!lua_isuserdata(L, -2)) {
        luaL_error(L, "class_index: Attempt to index a %s value", luaL_typename(L, -2));
        return 0;
    }
    const char* key = lua_tostring(L, -1);
    if (!isPythonObject(L, -2)) {
        luaL_error(L, "class_index: Not a Python object");
        return 0;
    }
    PyObject* obj = *(PyObject**)lua_touserdata(L, -2);
    Py_XINCREF(obj);
    if (!PyObject_HasAttrString(obj, lua_tostring(L, -1))) {
        lua_pushnil(L);
        return 1;
    }
    PyObject* attr = PyObject_GetAttrString(obj, key);
    Py_DECREF(obj);
    pushLua(L, attr);
    return 1;
}

int table_class_index = 0;

int pushClassLua(lua_State* L, PyObject* obj) {
    if (table_class_index != 0) {
        void* point = lua_newuserdata(L, sizeof(PyObject*));
        *(PyObject**)point = obj;
        lua_rawgeti(L, LUA_REGISTRYINDEX, table_class_index);
        if (!lua_istable(L, -1)) {
            luaL_error(L, "pushClassLua: Internal error, class index is not a table");
            return 0;
        }
        lua_setmetatable(L, -2);
        return 1;
    }
    lua_createtable(L, 0, 5);
    lua_pushcfunction(L, class_index);
    lua_setfield(L, -2, "__index");
    lua_pushcfunction(L, python_newindex);
    lua_setfield(L, -2, "__newindex");
    lua_pushcfunction(L, python_gc);
    lua_setfield(L, -2, "__gc");
    lua_pushstring(L, PYTHON_CLASS_NAME);
    lua_setfield(L, -2, "__name");
    lua_pushcfunction(L, python_tostring);
    lua_setfield(L, -2, "__tostring");
    table_class_index = luaL_ref(L, LUA_REGISTRYINDEX);
    return pushClassLua(L, obj);
}