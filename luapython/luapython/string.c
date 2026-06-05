#include "luapython.h"

#define isPythonString(L, index) (isPythonObject(L, index) && PyUnicode_Check(*(PyObject**)lua_touserdata(L, index)))

int string_concat(lua_State* L) {
    if (!(lua_isstring(L, -1) || isPythonString(L, -1)) || !(lua_isstring(L, -2) || isPythonString(L, -2))) {
        luaL_error(L, "string_concat: Attempt to concatenate %s and %s", luaL_typename(L, -2), luaL_typename(L, -1));
        return 0;
    }
    if (lua_isstring(L, -1) && lua_isstring(L, -2)) {
        lua_pushvalue(L, -2);
        lua_pushvalue(L, -2);
        lua_concat(L, 2);
        return 1;
    }
    PyObject* py_str1 = NULL;
    PyObject* py_str2 = NULL;
    if (lua_isstring(L, -1)) {
        py_str1 = PyUnicode_FromString(lua_tostring(L, -1));
    } else {
        py_str1 = *(PyObject**)lua_touserdata(L, -1);
        Py_XINCREF(py_str1);
    }
    if (lua_isstring(L, -2)) {
        py_str2 = PyUnicode_FromString(lua_tostring(L, -2));
    } else {
        py_str2 = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_str2);
    }
    if (!py_str1 || !py_str2) {
        Py_XDECREF(py_str1);
        Py_XDECREF(py_str2);
        luaL_error(L, "string_concat: Failed to create Python strings");
        return 0;
    }
    PyObject* result = PyUnicode_Concat(py_str1, py_str2);
    Py_XDECREF(py_str1);
    Py_XDECREF(py_str2);
    if (!result) {
        luaL_error(L, "string_concat: Python string concatenation failed");
        return 0;
    }
    pushStringLua(L, result);
    return 1;
}

int string_len(lua_State* L) {
    if (!(lua_isstring(L, -1) || isPythonString(L, -1))) {
        luaL_error(L, "string_len: Attempt to get length of %s", luaL_typename(L, -1));
        return 0;
    }
    if (lua_isstring(L, -1)) {
        size_t len;
        lua_tolstring(L, -1, &len);
        lua_pushinteger(L, len);
        return 1;
    }
    PyObject* py_str = *(PyObject**)lua_touserdata(L, -1);
    Py_XINCREF(py_str);
    Py_ssize_t len = PyUnicode_GetLength(py_str);
    Py_XDECREF(py_str);
    lua_pushinteger(L, len);
    return 1;
}

int string_eq(lua_State* L) {
    if (!(lua_isstring(L, -1) || isPythonString(L, -1)) || !(lua_isstring(L, -2) || isPythonString(L, -2))) {
        luaL_error(L, "string_len: Attempt to compare %s and %s as strings", luaL_typename(L, -2),
                   luaL_typename(L, -1));
        return 0;
    }
    if (lua_isstring(L, -1) && lua_isstring(L, -2)) {
        const char* str1 = lua_tostring(L, -2);
        const char* str2 = lua_tostring(L, -1);
        lua_pushboolean(L, strcmp(str1, str2) == 0);
        return 1;
    }
    PyObject* py_str1 = NULL;
    PyObject* py_str2 = NULL;
    if (lua_isstring(L, -1)) {
        py_str1 = PyUnicode_FromString(lua_tostring(L, -1));
    } else {
        py_str1 = *(PyObject**)lua_touserdata(L, -1);
        Py_XINCREF(py_str1);
    }
    if (lua_isstring(L, -2)) {
        py_str2 = PyUnicode_FromString(lua_tostring(L, -2));
    } else {
        py_str2 = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_str2);
    }
    if (!py_str1 || !py_str2) {
        Py_XDECREF(py_str1);
        Py_XDECREF(py_str2);
        luaL_error(L, "string_len: Failed to create Python strings");
        return 0;
    }
    int result = PyObject_RichCompareBool(py_str1, py_str2, Py_EQ);
    Py_XDECREF(py_str1);
    Py_XDECREF(py_str2);
    lua_pushboolean(L, result);
    return 1;
}

int string_lt(lua_State* L) {
    if (!(lua_isstring(L, -1) || isPythonString(L, -1)) || !(lua_isstring(L, -2) || isPythonString(L, -2))) {
        luaL_error(L, "string_lt: Attempt to compare %s and %s as strings", luaL_typename(L, -2), luaL_typename(L, -1));
        return 0;
    }
    if (lua_isstring(L, -1) && lua_isstring(L, -2)) {
        const char* str1 = lua_tostring(L, -2);
        const char* str2 = lua_tostring(L, -1);
        lua_pushboolean(L, strcmp(str1, str2) < 0);
        return 1;
    }
    PyObject* py_str1 = NULL;
    PyObject* py_str2 = NULL;
    if (lua_isstring(L, -1)) {
        py_str1 = PyUnicode_FromString(lua_tostring(L, -1));
    } else {
        py_str1 = *(PyObject**)lua_touserdata(L, -1);
        Py_XINCREF(py_str1);
    }
    if (lua_isstring(L, -2)) {
        py_str2 = PyUnicode_FromString(lua_tostring(L, -2));
    } else {
        py_str2 = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_str2);
    }
    if (!py_str1 || !py_str2) {
        Py_XDECREF(py_str1);
        Py_XDECREF(py_str2);
        luaL_error(L, "string_lt: Failed to create Python strings");
        return 0;
    }
    int result = PyObject_RichCompareBool(py_str2, py_str1, Py_LT);
    Py_XDECREF(py_str1);
    Py_XDECREF(py_str2);
    lua_pushboolean(L, result);
    return 1;
}

int string_le(lua_State* L) {
    if (!(lua_isstring(L, -1) || isPythonString(L, -1)) || !(lua_isstring(L, -2) || isPythonString(L, -2))) {
        luaL_error(L, "string_le: Attempt to compare %s and %s as strings", luaL_typename(L, -1), luaL_typename(L, -2));
        return 0;
    }
    if (lua_isstring(L, -1) && lua_isstring(L, -2)) {
        const char* str1 = lua_tostring(L, -2);
        const char* str2 = lua_tostring(L, -1);
        lua_pushboolean(L, strcmp(str1, str2) <= 0);
        return 1;
    }
    PyObject* py_str1 = NULL;
    PyObject* py_str2 = NULL;
    if (lua_isstring(L, -1)) {
        py_str1 = PyUnicode_FromString(lua_tostring(L, -1));
    } else {
        py_str1 = *(PyObject**)lua_touserdata(L, -1);
        Py_XINCREF(py_str1);
    }
    if (lua_isstring(L, -2)) {
        py_str2 = PyUnicode_FromString(lua_tostring(L, -2));
    } else {
        py_str2 = *(PyObject**)lua_touserdata(L, -2);
        Py_XINCREF(py_str2);
    }
    if (!py_str1 || !py_str2) {
        Py_XDECREF(py_str1);
        Py_XDECREF(py_str2);
        luaL_error(L, "string_le: Failed to create Python strings");
        return 0;
    }

    int result = PyObject_RichCompareBool(py_str2, py_str1, Py_LE);
    Py_XDECREF(py_str1);
    Py_XDECREF(py_str2);
    lua_pushboolean(L, result);
    return 1;
}

int string_tostring(lua_State* L) {
    if (!(lua_isstring(L, -1) || isPythonString(L, -1))) {
        luaL_error(L, "string_tostring: Attempt to convert a %s value to string", luaL_typename(L, -1));
        return 0;
    }
    if (lua_isstring(L, -1)) {
        lua_pushvalue(L, -1);
        return 1;
    }
    PyObject* py_str = *(PyObject**)lua_touserdata(L, -1);
    Py_XINCREF(py_str);
    pushStringLua(L, py_str);
    Py_XDECREF(py_str);
    return 1;
}

int string_mul(lua_State* L) {
    if (!(lua_isstring(L, -2) || isPythonString(L, -2))) {
        luaL_error(L, "string_mul: Attempt to multiply a %s value", luaL_typename(L, -2));
        return 0;
    }
    if (!lua_isnumber(L, -1)) {
        luaL_error(L, "string_mul: Attempt to multiply string by %s", luaL_typename(L, -1));
        return 0;
    }
    int count = lua_tointeger(L, -1);
    if (count < 0) {
        luaL_error(L, "string_mul: String repetition count must be non-negative");
        return 0;
    }
    if (lua_isstring(L, -2)) {
        const char* str = lua_tostring(L, -2);
        char result[strlen(str) * count + 1];
        for(int i = 0; i < count; i++) {
            strcat(result, str);
        }
        lua_pushstring(L, result);
        return 1;
    }
    PyObject* py_str = *(PyObject**)lua_touserdata(L, -2);
    PyObject* py_count = PyLong_FromLong(count);
    if (!py_count) {
        Py_XDECREF(py_str);
        luaL_error(L, "string_mul: Failed to create Python integer");
        return 0;
    }
    PyObject* result = PyNumber_Multiply(py_str, py_count);
    Py_XDECREF(py_count);
    Py_XDECREF(py_str);
    if (!result) {
        luaL_error(L, "string_mul: Python string repetition failed");
        return 0;
    }
    pushStringLua(L, result);
    return 1;
}

int table_string_index = 0;

int pushStringLua(lua_State* L, PyObject* obj) {
    if (!PyUnicode_Check(obj)) {
        luaL_error(L, "pushStringLua: Expected a Python string object");
        return 1;
    }
    PyObject* bytes = PyUnicode_AsEncodedString(obj, "utf-8", "surrogateescape");
    if (!PyErr_Occurred()) {
        const char* str = PyBytes_AsString(bytes);
        Py_ssize_t size = PyBytes_Size(bytes);
        lua_pushlstring(L, str, size);
        Py_DECREF(bytes);
        return 1;
    }
    if (table_string_index != 0) {
        void* point = lua_newuserdata(L, sizeof(PyObject*));
        *(PyObject**)point = obj;
        lua_rawgeti(L, LUA_REGISTRYINDEX, table_string_index);
        if (!lua_istable(L, -1)) {
            luaL_error(L, "pushStringLua: Internal error, class index is not a table");
            return 0;
        }
        lua_setmetatable(L, -2);
        return 1;
    }
    lua_createtable(L, 0, 9);
    lua_pushcfunction(L, string_concat);
    lua_setfield(L, -2, "__concat");
    lua_pushcfunction(L, string_len);
    lua_setfield(L, -2, "__len");
    lua_pushcfunction(L, string_eq);
    lua_setfield(L, -2, "__eq");
    lua_pushcfunction(L, string_lt);
    lua_setfield(L, -2, "__lt");
    lua_pushcfunction(L, string_le);
    lua_setfield(L, -2, "__le");
    lua_pushcfunction(L, string_tostring);
    lua_setfield(L, -2, "__tostring");
    lua_pushcfunction(L, string_mul);
    lua_setfield(L, -2, "__mul");
    lua_pushcfunction(L, python_gc);
    lua_setfield(L, -2, "__gc");
    lua_pushstring(L, PYTHON_STRING_NAME);
    lua_setfield(L, -2, "__name");
    table_string_index = luaL_ref(L, LUA_REGISTRYINDEX);
    return pushStringLua(L, obj);
}

PyObject* convertStringPython(lua_State* L, int index) {
    if (lua_isstring(L, index)) {
        return PyUnicode_FromString(lua_tostring(L, index));
    } else if (isPythonString(L, index)) {
        PyObject* py_str = *(PyObject**)lua_touserdata(L, index);
        Py_XINCREF(py_str);
        return py_str;
    }
    luaL_error(L, "convertStringPython: Expected a string or Python string object at index %d", index);
    return NULL;
}
