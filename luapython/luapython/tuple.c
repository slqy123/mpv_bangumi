#include "luapython.h"

int tuple_len(lua_State* L) {
    if (!(lua_istable(L, -1) || isPythonTuple(L, -1))) {
        luaL_error(L, "tuple_len: Attempt to get length of %s", luaL_typename(L, -1));
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
    PyObject* py_tuple = *(PyObject**)lua_touserdata(L, -1);
    Py_XINCREF(py_tuple);
    Py_ssize_t len = PyTuple_Size(py_tuple);
    Py_XDECREF(py_tuple);
    lua_pushinteger(L, len);
    return 1;
}

int tuple_index(lua_State* L) {
    if (!(lua_istable(L, -2) || isPythonTuple(L, -2))) {
        luaL_error(L, "tuple_index: Attempt to index %s", luaL_typename(L, -2));
        return 0;
    }
    if (lua_istable(L, -2)) {

#if LUA_VERSION_NUM >= 503
        lua_geti(L, -2, luaL_checkinteger(L, -1));
#else
        lua_pushnumber(L, luaL_checkinteger(L, -1));
        lua_gettable(L, -3);
#endif
        return 1;
    }
    PyObject* py_tuple = *(PyObject**)lua_touserdata(L, -2);
    Py_XINCREF(py_tuple);
    long index = luaL_checkinteger(L, -1);
    Py_ssize_t py_index = index - 1;
    Py_ssize_t size = PyTuple_Size(py_tuple);
    if (py_index < 0 || py_index >= size) {
        Py_XDECREF(py_tuple);
        lua_pushnil(L);
        return 1;
    }
    PyObject* py_value = PyTuple_GetItem(py_tuple, py_index);
    Py_XDECREF(py_tuple);
    pushLua(L, py_value);
    return 1;
}

int table_tuple_index = 0;

int pushTupleLua(lua_State* L, PyObject* obj) {
    if (!PyTuple_Check(obj)) {
        luaL_error(L, "pushTupleLua: Not a tuple");
        return 0;
    }
    if (table_tuple_index != 0) {
        void* point = lua_newuserdata(L, sizeof(PyObject*));
        *(PyObject**)point = obj;
        lua_rawgeti(L, LUA_REGISTRYINDEX, table_tuple_index);
        if (!lua_istable(L, -1)) {
            luaL_error(L, "pushClassLua: Internal error, class index is not a table");
            return 0;
        }
        lua_setmetatable(L, -2);
        return 1;
    }
    lua_createtable(L, 0, 5);
    lua_pushcfunction(L, tuple_len);
    lua_setfield(L, -2, "__len");
    lua_pushcfunction(L, tuple_index);
    lua_setfield(L, -2, "__index");
    lua_pushcfunction(L, python_tostring);
    lua_setfield(L, -2, "__tostring");
    lua_pushcfunction(L, python_gc);
    lua_setfield(L, -2, "__gc");
    lua_pushstring(L, PYTHON_TUPLE_NAME);
    lua_setfield(L, -2, "__name");
    table_tuple_index = luaL_ref(L, LUA_REGISTRYINDEX);
    return pushTupleLua(L, obj);
}

PyObject* convertTuplePython(lua_State* L, int index) {
    if (lua_istable(L, index)) {
        PyObject* py_list = convertListPython(L, index);
        PyObject* py_tuple = PyList_AsTuple(py_list);
        Py_XDECREF(py_list);
        return py_tuple;
    } else if (isPythonTuple(L, index)) {
        PyObject* py_tuple = *(PyObject**)lua_touserdata(L, index);
        Py_XINCREF(py_tuple);
        return py_tuple;
    }
    luaL_error(L, "convertTuplePython: Attempt to convert a %s value to Python tuple", luaL_typename(L, index));
    return NULL;
}
