#include "luapython.h"

#define isPythonIter(L, index) (isPythonObject(L, index) && PyIter_Check(*(PyObject**)lua_touserdata(L, index)))

int table_iter_index = 0;

int lua_iter(lua_State* L){
    if (!isPythonIter(L, -2)) {
        luaL_error(L, "python_iter: Not a Python iter");
        return 0;
    }
    PyObject* iter = *(PyObject**)lua_touserdata(L, -2);
    Py_XINCREF(iter);
    if(PyErr_Occurred()){
        PyErr_Print();
        Py_XDECREF(iter);
        luaL_error(L, "lua_iter: Failed to get iterator");
        return 0;
    }
    PyObject* next = PyIter_Next(iter);
    Py_XDECREF(iter);
    if(PyErr_Occurred()){
        PyErr_Clear();
    }
    if(!next) {
        lua_pushnil(L);
        return 1;
    }
    pushLua(L, next);
    return 1;
}

int lua_getiter(lua_State* L){
    if (!isPythonObject(L, -1)) {
        luaL_error(L, "python_getiter: Not a Python object");
        return 0;
    }
    PyObject* obj = *(PyObject**)lua_touserdata(L, -1);
    Py_XINCREF(obj);
    PyObject* iter = PyObject_GetIter(obj);
    Py_XDECREF(obj);
    if(!iter) {
        lua_pushnil(L);
        return 1;
    }
    pushClassLua(L, iter);
    return 1;
}

int pushIterLua(lua_State* L, PyObject* iter) {
    if(table_iter_index != 0) {
        void* point = lua_newuserdata(L, sizeof(PyObject*));
        *(PyObject**)point = iter;
        lua_rawgeti(L, LUA_REGISTRYINDEX, table_iter_index);
        if(!lua_istable(L, -1)) {
            luaL_error(L, "pushIterLua: Internal error, class index is not a table");
            return 0;
        }
        lua_setmetatable(L, -2);
        return 1;
    }
    lua_createtable(L, 0, 5);
    lua_rawgeti(L, LUA_REGISTRYINDEX, tools_get_iter_function);
    if(lua_isnil(L, -1)){
        loadTools(L);
        lua_pop(L, 1);
        lua_rawgeti(L, LUA_REGISTRYINDEX, tools_get_iter_function);
    }
    lua_pushcfunction(L, lua_iter);
    lua_pushcfunction(L, lua_getiter);
    if(lua_pcall(L, 2, 1, 0) != LUA_OK) {
        luaL_error(L, "pushIterLua: Failed to load iter.lua: %s", lua_tostring(L, -1));
        return 0;
    }
    lua_setfield(L, -2, "__call");
    lua_pushstring(L, PYTHON_ITER_NAME);
    lua_setfield(L, -2, "__name");
    lua_pushcfunction(L, python_gc);
    lua_setfield(L, -2, "__gc");
    lua_pushcfunction(L, python_tostring);
    lua_setfield(L, -2, "__tostring");
    lua_pushcfunction(L, python_index);
    lua_setfield(L, -2, "__index");
    table_iter_index = luaL_ref(L, LUA_REGISTRYINDEX);
    return pushIterLua(L, iter);
}