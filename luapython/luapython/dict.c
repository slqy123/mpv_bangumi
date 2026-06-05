#include "luapython.h"

#define isPythonDict(L, index) (isPythonObject(L, index) && PyDict_Check(*(PyObject**)lua_touserdata(L, index)))

int dict_len(lua_State* L) {
    if (!(lua_istable(L, -1) || isPythonDict(L, -1))) {
        luaL_error(L, "dict_len: Attempt to get length of %s", luaL_typename(L, -1));
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
    PyObject* py_dict = *(PyObject**)lua_touserdata(L, -1);
    Py_XINCREF(py_dict);
    Py_ssize_t len = PyDict_Size(py_dict);
    Py_XDECREF(py_dict);
    lua_pushinteger(L, len);
    return 1;
}

int dict_index(lua_State* L) {
    if (!isPythonDict(L, -2)) {
        luaL_error(L, "dict_index: Attempt to index %s", luaL_typename(L, -2));
        return 0;
    }
    PyObject* py_dict = *(PyObject**)lua_touserdata(L, -2);
    Py_XINCREF(py_dict);
    PyObject* py_key = convertPython(L, -1);
    if (!py_key) {
        luaL_error(L, "dict_index: Invalid key type for dictionary access");
        return 0;
    }
    PyObject* py_value = PyDict_GetItem(py_dict, py_key);
    Py_XDECREF(py_dict);
    Py_XDECREF(py_key);
    if (!py_value) {
        lua_pushnil(L);
        return 1;
    }
    Py_XINCREF(py_value);
    pushLua(L, py_value);
    return 1;
}

int dict_newindex(lua_State* L) {
    if (!isPythonDict(L, -3)) {
        luaL_error(L, "dict_newindex: Attempt to assign to %s", luaL_typename(L, -3));
        return 0;
    }
    PyObject* py_dict = *(PyObject**)lua_touserdata(L, -3);
    Py_XINCREF(py_dict);
    PyObject* py_key = convertPython(L, -2);
    PyObject* py_value = convertPython(L, -1);
    if (!py_key || !py_value) {
        Py_XDECREF(py_dict);
        if (py_key)
            Py_XDECREF(py_key);
        if (py_value)
            Py_XDECREF(py_value);
        luaL_error(L, "dict_newindex: Invalid key or value type for dictionary assignment");
        return 0;
    }
    int result = PyDict_SetItem(py_dict, py_key, py_value);
    Py_XDECREF(py_dict);
    Py_XDECREF(py_key);
    Py_XDECREF(py_value);
    if (result < 0) {
        luaL_error(L, "dict_newindex: Failed to set dictionary item");
        return 0;
    }
    return 0;
}

int dict_add(lua_State* L) {
    if (!(lua_istable(L, -1) || isPythonDict(L, -1)) || !(lua_istable(L, -2) || isPythonDict(L, -2))) {
        luaL_error(L, "dict_add: Attempt to merge %s and %s", luaL_typename(L, -2), luaL_typename(L, -1));
        return 0;
    }
    PyObject* py_dict1 = NULL;
    PyObject* py_dict2 = NULL;
    if (lua_istable(L, -1)) {
        py_dict1 = convertPython(L, -1);
    } else {
        py_dict1 = *(PyObject**)lua_touserdata(L, -1);
        Py_XINCREF(py_dict1);
    }
    if (lua_istable(L, 2)) {
        py_dict2 = convertPython(L, -2);
    } else {
        py_dict2 = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_dict2);
    }
    if (!py_dict1 || !py_dict2) {
        if (py_dict1)
            Py_XDECREF(py_dict1);
        if (py_dict2)
            Py_XDECREF(py_dict2);
        luaL_error(L, "dict_add: Failed to create Python dictionaries");
        return 0;
    }
    PyObject* result = PyDict_Copy(py_dict1);
    if (!result) {
        Py_XDECREF(py_dict1);
        Py_XDECREF(py_dict2);
        luaL_error(L, "dict_add: Failed to copy dictionary");
        return 0;
    }
    PyObject *key, *value;
    Py_ssize_t pos = 0;
    while (PyDict_Next(py_dict2, &pos, &key, &value)) {
        PyDict_SetItem(result, key, value);
    }
    Py_XDECREF(py_dict1);
    Py_XDECREF(py_dict2);
    pushDictLua(L, result);
    return 1;
}

int dict_mul(lua_State* L) {
    if (!(lua_istable(L, -1) || isPythonDict(L, -1)) || !(lua_istable(L, -2) || isPythonDict(L, -2))) {
        luaL_error(L, "dict_mul: Attempt to perform intersection on %s and %s", luaL_typename(L, -2),
                   luaL_typename(L, -1));
        return 0;
    }
    PyObject* py_dict1 = NULL;
    PyObject* py_dict2 = NULL;
    if (lua_istable(L, -1)) {
        py_dict1 = convertPython(L, -1);
    } else {
        py_dict1 = *(PyObject**)lua_touserdata(L, -1);
        Py_XINCREF(py_dict1);
    }
    if (lua_istable(L, -2)) {
        py_dict2 = convertPython(L, -2);
    } else {
        py_dict2 = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_dict2);
    }
    if (!py_dict1 || !py_dict2) {
        if (py_dict1)
            Py_XDECREF(py_dict1);
        if (py_dict2)
            Py_XDECREF(py_dict2);
        luaL_error(L, "dict_mul: Failed to create Python dictionaries");
        return 0;
    }
    PyObject* result = PyDict_New();
    if (!result) {
        Py_XDECREF(py_dict1);
        Py_XDECREF(py_dict2);
        luaL_error(L, "dict_mul: Failed to create new dictionary");
        return 0;
    }
    PyObject *key, *value;
    Py_ssize_t pos = 0;
    while (PyDict_Next(py_dict1, &pos, &key, &value)) {
        if (PyDict_Contains(py_dict2, key)) {
            PyDict_SetItem(result, key, value);
        }
    }
    Py_XDECREF(py_dict1);
    Py_XDECREF(py_dict2);
    pushDictLua(L, result);
    return 1;
}

int dict_sub(lua_State* L) {
    if (!(lua_istable(L, -1) || isPythonDict(L, -1)) || !(lua_istable(L, -2) || isPythonDict(L, -2))) {
        luaL_error(L, "dict_sub: Attempt to perform difference on %s and %s", luaL_typename(L, -1),
                   luaL_typename(L, -2));
        return 0;
    }
    PyObject* py_dict1 = NULL;
    PyObject* py_dict2 = NULL;
    if (lua_istable(L, -1)) {
        py_dict1 = convertPython(L, -1);
    } else {
        py_dict1 = *(PyObject**)lua_touserdata(L, -1);
        Py_XINCREF(py_dict1);
    }
    if (lua_istable(L, -2)) {
        py_dict2 = convertPython(L, -2);
    } else {
        py_dict2 = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_dict2);
    }
    if (!py_dict1 || !py_dict2) {
        if (py_dict1)
            Py_XDECREF(py_dict1);
        if (py_dict2)
            Py_XDECREF(py_dict2);
        luaL_error(L, "dict_sub: Failed to create Python dictionaries");
        return 0;
    }
    PyObject* result = PyDict_New();
    if (!result) {
        Py_XDECREF(py_dict1);
        Py_XDECREF(py_dict2);
        luaL_error(L, "dict_sub: Failed to create new dictionary");
        return 0;
    }
    PyObject *key, *value;
    Py_ssize_t pos = 0;
    while (PyDict_Next(py_dict1, &pos, &key, &value)) {
        if (!PyDict_Contains(py_dict2, key)) {
            PyDict_SetItem(result, key, value);
        }
    }
    Py_XDECREF(py_dict1);
    Py_XDECREF(py_dict2);
    pushDictLua(L, result);
    return 1;
}

int table_dict_index = 0;

int pushDictLua(lua_State* L, PyObject* obj) {
    if (!PyDict_Check(obj)) {
        luaL_error(L, "pushDictLua: Not a dict");
        return 0;
    }
    if (table_dict_index != 0) {
        void* point = lua_newuserdata(L, sizeof(PyObject*));
        *(PyObject**)point = obj;
        lua_rawgeti(L, LUA_REGISTRYINDEX, table_dict_index);
        if (!lua_istable(L, -1)) {
            luaL_error(L, "pushDictLua: Internal error, class index is not a table");
            return 0;
        }
        lua_setmetatable(L, -2);
        return 1;
    }
    lua_createtable(L, 0, 9);
    lua_pushcfunction(L, dict_len);
    lua_setfield(L, -2, "__len");
    lua_pushcfunction(L, dict_add);
    lua_setfield(L, -2, "__add");
    lua_pushcfunction(L, dict_mul);
    lua_setfield(L, -2, "__mul");
    lua_pushcfunction(L, dict_sub);
    lua_setfield(L, -2, "__sub");
    lua_pushcfunction(L, dict_index);
    lua_setfield(L, -2, "__index");
    lua_pushcfunction(L, dict_newindex);
    lua_setfield(L, -2, "__newindex");
    lua_pushcfunction(L, python_tostring);
    lua_setfield(L, -2, "__tostring");
    lua_pushcfunction(L, python_gc);
    lua_setfield(L, -2, "__gc");
    lua_pushstring(L, PYTHON_DICT_NAME);
    lua_setfield(L, -2, "__name");
    table_dict_index = luaL_ref(L, LUA_REGISTRYINDEX);
    return pushDictLua(L, obj);
}

PyObject* convertDictPython(lua_State* L, int index) {
    if (lua_istable(L, index)) {
        PyObject* py_dict = PyDict_New();
        lua_pushvalue(L, index);
        lua_pushnil(L);
        while (lua_next(L, -2) != 0) {
            if (lua_isstring(L, -2)) {
                lua_pushvalue(L, -2);
                const char* key = lua_tostring(L, -1);
                PyObject* py_key = PyUnicode_FromString(key);
                PyObject* py_value = convertPython(L, -2);
                lua_pop(L, 1);
                if (py_key && py_value) {
                    PyDict_SetItem(py_dict, py_key, py_value);
                    Py_XDECREF(py_key);
                    Py_XDECREF(py_value);
                } else {
                    Py_XDECREF(py_key);
                    Py_XDECREF(py_value);
                    Py_XDECREF(py_dict);
                    luaL_error(L, "convertDictPython: Failed to convert Lua table to Python dictionary");
                    return NULL;
                }
            }
            lua_pop(L, 1);
        }
        lua_pop(L, 1);
        return py_dict;
    } else if (isPythonDict(L, index)) {
        PyObject* py_dict = *(PyObject**)lua_touserdata(L, index);
        Py_XINCREF(py_dict);
        return py_dict;
    }
    return 0;
}