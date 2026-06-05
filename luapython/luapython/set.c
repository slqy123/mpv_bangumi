#include "luapython.h"

#define isPythonSet(L, index) (isPythonObject(L, index) && PySet_Check(*(PyObject**)lua_touserdata(L, index)))

int set_len(lua_State* L) {
    if (!(lua_istable(L, -1) || isPythonSet(L, -1))) {
        luaL_error(L, "set_len: Attempt to get length of %s", luaL_typename(L, -1));
        return 0;
    }
    if (lua_istable(L, -1)) {
#if LUA_VERSION_NUM >= 502
        lua_len(L, -1);
#else
        lua_pushnumber(L, lua_objlen(L, -1));
#endif
        return 1;
    }
    PyObject* py_set = *(PyObject**)lua_touserdata(L, -1);
    Py_XINCREF(py_set);
    Py_ssize_t len = PySet_Size(py_set);
    Py_XDECREF(py_set);
    lua_pushinteger(L, len);
    return 1;
}

int set_index(lua_State* L) {
    if (!isPythonSet(L, -2)) {
        luaL_error(L, "set_index: Attempt to index %s", luaL_typename(L, -2));
        return 0;
    }
    luaL_error(L, "set_index: Set objects do not support indexing");
    return 0;
}

int set_newindex(lua_State* L) {
    if (!isPythonSet(L, -3)) {
        luaL_error(L, "set_newindex: Attempt to assign to %s", luaL_typename(L, -3));
        return 0;
    }
    luaL_error(L, "set_newindex: Set objects do not support assignment");
    return 0;
}

int set_add(lua_State* L) {
    if (!(lua_istable(L, -1) || isPythonSet(L, -1)) || !(lua_istable(L, -2) || isPythonSet(L, -2))) {
        luaL_error(L, "set_add: Attempt to perform union on %s and %s", luaL_typename(L, -2), luaL_typename(L, -1));
        return 0;
    }
    PyObject* py_set1 = NULL;
    PyObject* py_set2 = NULL;
    if (lua_istable(L, -1)) {
        py_set1 = convertPython(L, -1);
    } else {
        py_set1 = *(PyObject**)lua_touserdata(L, -1);
        Py_XINCREF(py_set1);
    }
    if (lua_istable(L, -2)) {
        py_set2 = convertPython(L, -2);
    } else {
        py_set2 = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_set2);
    }
    if (!py_set1 || !py_set2) {
        Py_XDECREF(py_set1);
        Py_XDECREF(py_set2);
        luaL_error(L, "set_add: Failed to create Python sets");
        return 0;
    }
    PyObject* result = PyNumber_Or(py_set1, py_set2);
    Py_XDECREF(py_set1);
    Py_XDECREF(py_set2);
    if (!result) {
        luaL_error(L, "set_add: Python set union failed");
        return 0;
    }
    pushSetLua(L, result);
    return 1;
}

int set_mul(lua_State* L) {
    luaL_error(L, "set_mul: Set objects do not support intersection");
    return 0;
}

int set_sub(lua_State* L) {
    if (!(lua_istable(L, -1) || isPythonSet(L, -1)) || !(lua_istable(L, -2) || isPythonSet(L, -2))) {
        luaL_error(L, "set_sub: Attempt to perform difference on %s and %s", luaL_typename(L, -2),
                   luaL_typename(L, -1));
        return 0;
    }
    PyObject* py_set1 = NULL;
    PyObject* py_set2 = NULL;
    if (lua_istable(L, -1)) {
        py_set1 = convertPython(L, -1);
    } else {
        py_set1 = *(PyObject**)lua_touserdata(L, -1);
        Py_XINCREF(py_set1);
    }
    if (lua_istable(L, -2)) {
        py_set2 = convertPython(L, -2);
    } else {
        py_set2 = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_set2);
    }
    if (!py_set1 || !py_set2) {
        Py_XDECREF(py_set1);
        Py_XDECREF(py_set2);
        luaL_error(L, "set_sub: Failed to create Python sets");
        return 0;
    }
    PyObject* result = PyNumber_Subtract(py_set1, py_set2);
    Py_XDECREF(py_set1);
    Py_XDECREF(py_set2);
    if (!result) {
        luaL_error(L, "set_sub: Python set difference failed");
        return 0;
    }
    pushSetLua(L, result);
    return 1;
}

int set_band(lua_State* L) {
    if (!(lua_istable(L, -1) || isPythonSet(L, -1)) || !(lua_istable(L, -2) || isPythonSet(L, -2))) {
        luaL_error(L, "set_band: Attempt to perform symmetric difference on %s and %s", luaL_typename(L, -2),
                   luaL_typename(L, -1));
        return 0;
    }
    PyObject* py_set1 = NULL;
    PyObject* py_set2 = NULL;
    if (lua_istable(L, -1)) {
        py_set1 = convertPython(L, -1);
    } else {
        py_set1 = *(PyObject**)lua_touserdata(L, -1);
        Py_XINCREF(py_set1);
    }
    if (lua_istable(L, -2)) {
        py_set2 = convertPython(L, -2);
    } else {
        py_set2 = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_set2);
    }
    if (!py_set1 || !py_set2) {
        Py_XDECREF(py_set1);
        Py_XDECREF(py_set2);
        luaL_error(L, "set_band: Failed to create Python sets");
        return 0;
    }
    PyObject* result = PyNumber_And(py_set1, py_set2);
    Py_XDECREF(py_set1);
    Py_XDECREF(py_set2);
    if (!result) {
        luaL_error(L, "set_band: Python set symmetric difference failed");
        return 0;
    }
    pushSetLua(L, result);
    return 1;
}

int table_set_index = 0;

int pushSetLua(lua_State* L, PyObject* obj) {
    if (!PySet_Check(obj)) {
        luaL_error(L, "pushSetLua: Failed to set metatable for set");
        return 0;
    }
    if (table_set_index != 0) {
        void* point = lua_newuserdata(L, sizeof(PyObject*));
        *(PyObject**)point = obj;
        lua_rawgeti(L, LUA_REGISTRYINDEX, table_set_index);
        if (!lua_istable(L, -1)) {
            luaL_error(L, "pushSetLua: Internal error, class index is not a table");
            return 0;
        }
        lua_setmetatable(L, -2);
        return 1;
    }
    lua_createtable(L, 0, 9);
    lua_pushcfunction(L, set_add);
    lua_setfield(L, -2, "__add");
    lua_pushcfunction(L, set_mul);
    lua_setfield(L, -2, "__mul");
    lua_pushcfunction(L, set_sub);
    lua_setfield(L, -2, "__sub");
    lua_pushcfunction(L, set_band);
    lua_setfield(L, -2, "__band");
    lua_pushcfunction(L, set_index);
    lua_setfield(L, -2, "__index");
    lua_pushcfunction(L, set_newindex);
    lua_setfield(L, -2, "__newindex");
    lua_pushcfunction(L, python_tostring);
    lua_setfield(L, -2, "__tostring");
    lua_pushcfunction(L, python_gc);
    lua_setfield(L, -2, "__gc");
    lua_pushstring(L, PYTHON_SET_NAME);
    lua_setfield(L, -2, "__name");
    table_set_index = luaL_ref(L, LUA_REGISTRYINDEX);
    return pushSetLua(L, obj);
}

PyObject* convertSetPython(lua_State* L, int index) {
    if (lua_istable(L, index)) {
        PyObject* list = convertListPython(L, index);
        PyObject* py_set = PySet_New(list);
        Py_XDECREF(list);
        return py_set;
    } else if (isPythonSet(L, index)) {
        PyObject* py_set = *(PyObject**)lua_touserdata(L, index);
        Py_XINCREF(py_set);
        return py_set;
    }
    luaL_error(L, "convertSetPython: Attempt to convert a %s value to Python set", luaL_typename(L, index));
    return NULL;
}