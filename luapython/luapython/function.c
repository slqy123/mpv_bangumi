#include "luapython.h"

#define isPythonFunction(L, index) (isPythonObject(L, index) && PyCallable_Check(*(PyObject**)lua_touserdata(L, index)))

int function_call(lua_State* L) {
    if (!lua_isnumber(L, -1)) {
        luaL_error(L, "function_call: The last argument must be the number of arguments");
        return 0;
    }
    int nargs = lua_tonumber(L, -1);
    if (!isPythonFunction(L, -4)) {
        luaL_error(L, "function_call: Attempt to call a %s object", luaL_typename(L, -3));
        return 0;
    }
    PyObject* function = *(PyObject**)lua_touserdata(L, -4);
    Py_XINCREF(function);
    if (!PyCallable_Check(function)) {
        Py_XDECREF(function);
        luaL_error(L, "function_call: Attempt to call a %s object", getPythonTypeName(function));
        return 0;
    }
    PyObject* args = PyTuple_New(nargs);
    PyObject* kwargs = PyDict_New();
    for(int i = 1; i <= nargs; i++){
#if LUA_VERSION_NUM >= 503
        lua_geti(L, -3, i);
#else
        lua_pushnumber(L, i);
        lua_gettable(L, -4);
#endif
        PyObject* arg = convertPython(L, -1);
        if (!arg) {
            Py_XDECREF(args);
            Py_XDECREF(kwargs);
            Py_XDECREF(function);
            luaL_error(L, "function_call: Failed to convert argument %d", i);
            return 0;
        }
        PyTuple_SetItem(args, i-1, arg);
        lua_pop(L, 1);
    }
    lua_pushnil(L);
    while (lua_next(L, -3) != 0) {
        if (lua_type(L, -2) == LUA_TSTRING) {
            const char* key = lua_tostring(L, -2);
            PyObject* key_py = PyUnicode_FromString(key);
            PyObject* value = convertPython(L, -1);
            PyDict_SetItem(kwargs, key_py, value);
            Py_XDECREF(key_py);
            Py_XDECREF(value);
        }
        lua_pop(L, 1);
    }
    PyObject* result = PyObject_Call(function, args, kwargs);
    Py_XDECREF(args);
    Py_XDECREF(kwargs);
    Py_XDECREF(function);
    if (PyErr_Occurred()) {
        PyErr_Print();
        Py_XDECREF(result);
        luaL_error(L, "function_call: Error calling function");
        return 0;
    }
    if(PyTuple_Check(result)){
        Py_ssize_t size = PyTuple_Size(result);
        for(Py_ssize_t i = 0; i < size; i++){
            PyObject* item = PyTuple_GetItem(result, i);
            Py_XINCREF(item);
            pushLua(L, item);
        }
        Py_XDECREF(result);
        return size;
    }
    pushLua(L, result);
    return 1;
}

int table_function_index = 0;

int pushFunctionLua(lua_State* L, PyObject* obj) {
    if (!PyCallable_Check(obj)) {
        luaL_error(L, "pushFunctionLua: Function is not callable");
        return 0;
    }
    if (table_function_index != 0) {
        void* point = lua_newuserdata(L, sizeof(PyObject*));
        *(PyObject**)point = obj;
        lua_rawgeti(L, LUA_REGISTRYINDEX, table_function_index);
        if (!lua_istable(L, -1)) {
            luaL_error(L, "pushFunctionLua: Internal error, class index is not a table");
            return 0;
        }
        lua_setmetatable(L, -2);
        return 1;
    }
    lua_createtable(L, 0, 5);
    lua_rawgeti(L, LUA_REGISTRYINDEX, tools_get_python_adapt_function);
    if(lua_isnil(L, -1)){
        loadTools(L);
        lua_pop(L, 1);
        lua_rawgeti(L, LUA_REGISTRYINDEX, tools_get_python_adapt_function);
    }
    lua_pushcfunction(L, function_call);
    lua_call(L, 1, 1);
    lua_setfield(L, -2, "__call");
    lua_pushcfunction(L, python_tostring);
    lua_setfield(L, -2, "__tostring");
    lua_pushcfunction(L, python_gc);
    lua_setfield(L, -2, "__gc");
    lua_pushstring(L, PYTHON_FUNCTION_NAME);
    lua_setfield(L, -2, "__name");
    lua_pushcfunction(L, python_index);
    lua_setfield(L, -2, "__index");
    table_function_index = luaL_ref(L, LUA_REGISTRYINDEX);
    return pushFunctionLua(L, obj);
}
