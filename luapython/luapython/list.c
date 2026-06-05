#include "luapython.h"

#define isPythonList(L, index) (isPythonObject(L, index) && PyList_Check(*(PyObject**)lua_touserdata(L, index)))

int list_len(lua_State* L) {
    if (!(lua_istable(L, -1) || isPythonList(L, -1))) {
        luaL_error(L, "list_len: Attempt to get length of %s", luaL_typename(L, -1));
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
    PyObject* py_list = *(PyObject**)lua_touserdata(L, -1);
    Py_XINCREF(py_list);
    Py_ssize_t len = PyList_Size(py_list);
    Py_XDECREF(py_list);
    lua_pushinteger(L, len);
    return 1;
}

int list_index(lua_State* L) {
    if (!(lua_istable(L, -2) || isPythonList(L, -2))) {
        luaL_error(L, "list_index: Attempt to index %s", luaL_typename(L, -2));
        return 0;
    }

#if LUA_VERSION_NUM >= 503
    if (!lua_isinteger(L, -1)) {
#else
    double num = lua_tonumber(L, -1);
    if(num != ((lua_Integer)num)){
#endif
        luaL_error(L, "list_index: List index must be an integer");
        return 0;
    }
    lua_Integer idx = lua_tointeger(L, -1);
    if (lua_istable(L, -1)) {
        lua_pushinteger(L, idx);
        lua_gettable(L, -2);
        return 1;
    }
    PyObject* py_list = *(PyObject**)lua_touserdata(L, -2);
    Py_XINCREF(py_list);
    Py_ssize_t len = PyList_Size(py_list);
    Py_XDECREF(py_list);
    Py_ssize_t py_idx = idx;
    if (py_idx < 0 || py_idx >= len) {
        lua_pushnil(L);
        return 1;
    }
    PyObject* py_value = PyList_GetItem(py_list, py_idx);
    Py_XINCREF(py_value);
    pushLua(L, py_value);
    return 1;
}

int list_newindex(lua_State* L) {
    if (!isPythonList(L, -3)) {
        luaL_error(L, "list_newindex: Attempt to assign to %s", luaL_typename(L, -3));
        return 0;
    }
#if LUA_VERSION_NUM >= 503
    if (!lua_isinteger(L, -2)) {
#else
    double num = lua_tonumber(L, -2);
    if(num != ((lua_Integer)num)){
#endif
        luaL_error(L, "list_newindex: List index must be an integer");
        return 0;
    }
    lua_Integer idx = lua_tointeger(L, -2);
    PyObject* py_list = *(PyObject**)lua_touserdata(L, -3);
    Py_XINCREF(py_list);
    Py_ssize_t len = PyList_Size(py_list);
    Py_ssize_t py_idx = idx - 1;
    if (py_idx < 0 || py_idx >= len) {
        Py_XDECREF(py_list);
        luaL_error(L, "list_newindex: List index out of range");
        return 0;
    }
    PyObject* py_value = convertPython(L, -1);
    if (!py_value) {
        Py_XDECREF(py_value);
        Py_XDECREF(py_list);
        luaL_error(L, "list_newindex: Invalid value type for list assignment");
        return 0;
    }
    int result = PyList_SetItem(py_list, py_idx, py_value);
    Py_XDECREF(py_value);
    Py_XDECREF(py_list);
    if (result < 0) {
        luaL_error(L, "list_newindex: Failed to set list item");
        return 0;
    }
    return 0;
}

int list_add(lua_State* L) {
    if (!(lua_istable(L, -1) || isPythonList(L, -1)) || !(lua_istable(L, -2) || isPythonList(L, -2))) {
        luaL_error(L, "list_add: Attempt to concatenate %s and %s", luaL_typename(L, -2), luaL_typename(L, -1));
        return 0;
    }
    PyObject* py_list1 = NULL;
    PyObject* py_list2 = NULL;
    if (lua_istable(L, -2)) {
        py_list1 = convertPython(L, -2);
    } else {
        py_list1 = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_list1);
    }
    if (lua_istable(L, -1)) {
        py_list2 = convertPython(L, -1);
    } else {
        py_list2 = *(PyObject**)lua_touserdata(L, -1);
        Py_XINCREF(py_list2);
    }
    if (!py_list1 || !py_list2) {
        Py_XDECREF(py_list1);
        Py_XDECREF(py_list2);
        luaL_error(L, "list_add: Failed to create Python lists");
        return 0;
    }
    PyObject* result = PyList_New(PyList_Size(py_list1) + PyList_Size(py_list2));
    if (!result) {
        Py_XDECREF(py_list1);
        Py_XDECREF(py_list2);
        Py_XDECREF(result);
        luaL_error(L, "list_add: Failed to create new list");
        return 0;
    }
    for (Py_ssize_t i = 0; i < PyList_Size(py_list1); ++i) {
        PyObject* item = PyList_GetItem(py_list1, i);
        Py_XINCREF(item);
        PyList_SetItem(result, i, item);
    }
    Py_ssize_t offset = PyList_Size(py_list1);
    for (Py_ssize_t i = 0; i < PyList_Size(py_list2); ++i) {
        PyObject* item = PyList_GetItem(py_list2, i);
        Py_XINCREF(item);
        PyList_SetItem(result, offset + i, item);
    }
    Py_XDECREF(py_list1);
    Py_XDECREF(py_list2);
    pushListLua(L, result);
    return 1;
}

int list_mul(lua_State* L) {
    if (!(lua_istable(L, -2) || isPythonList(L, -2))){
        luaL_error(L, "list_mul: Attempt to repeat %s with non-integer", luaL_typename(L, -2));
        return 0;
    }

#if LUA_VERSION_NUM >= 503
    if (!lua_isinteger(L, -1)){
        luaL_error(L, "list_mul: List index must be an integer");
    }
    lua_Integer n = lua_tointeger(L, -1);
#else
    double dn = lua_tonumber(L, -1);
    if(dn != ((lua_Integer)dn)){
        luaL_error(L, "list_mul: List index must be an integer");
    }
    lua_Integer n = (lua_Integer)dn;
#endif
    if (n < 0) {
        luaL_error(L, "list_mul: Repeat count must be non-negative");
        return 0;
    }
    PyObject* py_list = NULL;
    if (lua_istable(L, -2)) {
        py_list = convertPython(L, -2);
    } else {
        py_list = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_list);
    }
    if (!py_list) {
        luaL_error(L, "list_mul: Failed to create Python list");
        return 0;
    }
    PyObject* result = PySequence_Repeat(py_list, n);
    Py_XDECREF(py_list);
    if (!result) {
        luaL_error(L, "list_mul: Failed to repeat list");
        return 0;
    }
    pushListLua(L, result);
    return 1;
}

int table_list_index = 0;

int pushListLua(lua_State* L, PyObject* obj) {
    if (!PyList_Check(obj)) {
        luaL_error(L, "pushListLua: Attempt to push a non-list Python object");
        return 0;
    }
    if (table_list_index != 0) {
        void* point = lua_newuserdata(L, sizeof(PyObject*));
        *(PyObject**)point = obj;
        lua_rawgeti(L, LUA_REGISTRYINDEX, table_list_index);
        if (!lua_istable(L, -1)) {
            luaL_error(L, "pushListLua: Internal error, class index is not a table");
            return 0;
        }
        lua_setmetatable(L, -2);
        return 1;
    }
    lua_createtable(L, 0, 8);
    lua_pushcfunction(L, list_len);
    lua_setfield(L, -2, "__len");
    lua_pushcfunction(L, list_add);
    lua_setfield(L, -2, "__add");
    lua_pushcfunction(L, list_mul);
    lua_setfield(L, -2, "__mul");
    lua_pushcfunction(L, list_index);
    lua_setfield(L, -2, "__index");
    lua_pushcfunction(L, list_newindex);
    lua_setfield(L, -2, "__newindex");
    lua_pushcfunction(L, python_tostring);
    lua_setfield(L, -2, "__tostring");
    lua_pushcfunction(L, python_gc);
    lua_setfield(L, -2, "__gc");
    lua_pushstring(L, PYTHON_LIST_NAME);
    lua_setfield(L, -2, "__name");
    table_list_index = luaL_ref(L, LUA_REGISTRYINDEX);
    return pushListLua(L, obj);
}

PyObject* convertListPython(lua_State* L, int index) {
    if (lua_istable(L, index)) {
        lua_pushvalue(L, index);
#if LUA_VERSION_NUM >= 502
        lua_Integer len = lua_rawlen(L, -1);
#else
        lua_Integer len = lua_objlen(L, -1);
#endif
        PyObject* py_list = PyList_New(len);
        for (lua_Integer i = 1; i <= len; ++i) {
            lua_rawgeti(L, -1, i);
            PyObject* item = convertPython(L, -1);
            PyList_SetItem(py_list, i - 1, item);
            lua_pop(L, 1);
        }
        lua_pop(L, 1);
        return py_list;
    } else if (isPythonList(L, index)) {
        PyObject* py_list = *(PyObject**)lua_touserdata(L, index);
        Py_XINCREF(py_list);
        return py_list;
    }
    return 0;
}