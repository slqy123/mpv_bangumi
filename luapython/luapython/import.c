#include "luapython.h"

static int python_import(lua_State* L) {
    if (!lua_isstring(L, -2)) {
        luaL_error(L, luaL_typename(L, -2));
        return 0;
    }
    const char* module_name = lua_tostring(L, -2);
    PyObject* module = PyImport_Import(PyUnicode_FromString(module_name));
    if (module == NULL) {
        bool b = PyErr_Occurred();
        if (lua_toboolean(L, -1)) {
            PyErr_Print();
        } else {
            PyErr_Clear();
        }
        return 0;
    }
    pushLua(L, module);
    Py_XDECREF(module);
    return 1;
}