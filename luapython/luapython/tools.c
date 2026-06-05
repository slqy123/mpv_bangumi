#include "tools.h"
#include "luapython.h"

int tools_should_convert_to_dict = -1;
int tools_release_to_env = -1;
int tools_get_python_adapt_function = -1;
int tools_get_iter_function = -1;

int luapython_astable(lua_State* L) {
    if(!isPythonObject(L, -1)) {
        luaL_error(L, "luapython_astable: Not a Python object");
        return 0;
    }
    PyObject* obj = *(PyObject**)lua_touserdata(L, -1);
    Py_XINCREF(obj);
    PyObject* iter = PyObject_GetIter(obj);
    if(PyErr_Occurred()) {
        PyErr_Clear();
    }
    if(iter) {
        lua_newtable(L);
        PyObject* item;
        int index = 1;
        while((item = PyIter_Next(iter)) != NULL) {
            pushLua(L, item);
            lua_rawseti(L, -2, index++);
        }
        Py_XDECREF(iter);
        Py_XDECREF(obj);
        return 1;
    }
    Py_XDECREF(iter);
    PyObject* dir = PyObject_Dir(obj);
    if(PyErr_Occurred()) {
        PyErr_Print();
        Py_XDECREF(dir);
        Py_XDECREF(obj);
        luaL_error(L, "luapython_astable: Failed to get attributes of Python object");
        return 0;
    }
    if(!PyList_Check(dir)) {
        Py_XDECREF(dir);
        Py_XDECREF(obj);
        luaL_error(L, "luapython_astable: Internal error, PyObject_Dir did not return a list");
        return 0;
    }
    Py_ssize_t size = PyList_Size(dir);
    lua_createtable(L, 0, (int)size);
    for(Py_ssize_t index = 0; index < size; index++) {
        PyObject* item = PyList_GetItem(dir, index);
        Py_XINCREF(item);
        if(!PyUnicode_Check(item)) {
            Py_XDECREF(item);
            continue;
        }
        PyObject* bytes = PyUnicode_AsEncodedString(item, "utf-8", "surrogateescape");
        const char* key = PyBytes_AsString(bytes);
        Py_XDECREF(bytes);
        if(key == NULL) {
            PyErr_Print();
            Py_XDECREF(dir);
            Py_XDECREF(obj);
            luaL_error(L, "luapython_astable: Failed to convert attribute name to UTF-8");
            return 0;
        }
        PyObject* value = PyObject_GetAttr(obj, item);
        Py_XDECREF(item);
        if(value == NULL) {
            PyErr_Clear();
            continue;
        }
        pushLua(L, value);
        lua_setfield(L, -2, key);
    }
    Py_XDECREF(dir);
    Py_XDECREF(obj);
    return 1;
}

void loadTools(lua_State* L){
    if(luaL_dostring(L, "return require \"luapython.tools\"") != LUA_OK){
        luaL_error(L, "loadTools: Failed to load internal tools");
    }
    int index = -4;
    if(lua_istable(L, -1)){
        index = -2;
    }else if(lua_istable(L, -2)){
        index = -3;
    }else{
        luaL_error(L, "loadtools: table expected, got %s", luaL_typename(L, -1));
    }
    lua_pushstring(L, "shouldConvertToDict");
    lua_rawget(L, index);
    if(!lua_isfunction(L, -1)){
        luaL_error(L, "loadTools: index shouldConvertToDict - function expected, got %s", luaL_typename(L, -1));
    }
    tools_should_convert_to_dict = luaL_ref(L, LUA_REGISTRYINDEX);
    lua_pushstring(L, "releaseToEnv");
    lua_rawget(L, index);
    if(!lua_isfunction(L, -1)){
        luaL_error(L, "loadTools: index releaseToEnv - function expected, got %s", luaL_typename(L, -1));
    }
    tools_release_to_env = luaL_ref(L, LUA_REGISTRYINDEX);
    lua_pushstring(L, "getPythonAdaptFunction");
    lua_rawget(L, index);
    if(!lua_isfunction(L, -1)){
        luaL_error(L, "loadTools: index getPythonAdaptFunction - function expected, got %s", luaL_typename(L, -1));
    }
    tools_get_python_adapt_function = luaL_ref(L, LUA_REGISTRYINDEX);
    lua_pushstring(L, "getIterFunction");
    lua_rawget(L, index);
    if(!lua_isfunction(L, -1)){
        luaL_error(L, "loadTools: index getIterFunction - function expected, got %s", luaL_typename(L, -1));
    }
    tools_get_iter_function = luaL_ref(L, LUA_REGISTRYINDEX);
    lua_pop(L, -(index+1));
}
