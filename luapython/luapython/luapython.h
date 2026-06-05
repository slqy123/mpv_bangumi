#define Py_LIMITED_API 0x03080000

#include <Python.h>
#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>

#include "tools.h"

#ifndef PREFIX
#define PREFIX "/usr"
#endif

#define PYTHON_OBJECT_NAME "python_object"
#define PYTHON_CLASS_NAME "python_class"
#define PYTHON_MODULE_NAME "python_module"
#define PYTHON_FUNCTION_NAME "python_function"
#define PYTHON_ITER_NAME "python_iter"
#define PYTHON_SET_NAME "python_set"
#define PYTHON_DICT_NAME "python_dict"
#define PYTHON_TUPLE_NAME "python_tuple"
#define PYTHON_LIST_NAME "python_list"
#define PYTHON_STRING_NAME "python_string"
#define PYTHON_NUMBER_NAME "python_number"

#define getPythonTypeName(obj) (PyBytes_AsString(PyUnicode_AsEncodedString(PyObject_GetAttrString((PyObject*)Py_TYPE(obj), "__name__"), "utf-8", "surrogateescape")))

#define isPythonTuple(L, index) (isPythonObject(L, index) && PyTuple_Check(*(PyObject**)lua_touserdata(L, index)))

#if LUA_VERSION_NUM <= 501
#define LUA_OK 0
#endif

int luaopen_luapython(lua_State* L);

int python_tostring(lua_State* L);
int python_gc(lua_State* L);
int python_index(lua_State* L);
int python_newindex(lua_State* L);

int isPythonObject(lua_State* L, int index);

int pushNumberLua(lua_State* L, PyObject* number);
int pushStringLua(lua_State* L, PyObject* string);
int pushSetLua(lua_State* L, PyObject* set);
int pushDictLua(lua_State* L, PyObject* dict);
int pushTupleLua(lua_State* L, PyObject* tuple);
int pushListLua(lua_State* L, PyObject* list);
int pushFunctionLua(lua_State* L, PyObject* function);
int pushModuleLua(lua_State* L, PyObject* module);
int pushClassLua(lua_State* L, PyObject* obj);
int pushIterLua(lua_State* L, PyObject* iter);

int pushLua(lua_State* L, PyObject* obj);

PyObject* convertNumberPython(lua_State* L, int index);
PyObject* convertBooleanPython(lua_State* L, int index);
PyObject* convertStringPython(lua_State* L, int index);
PyObject* convertSetPython(lua_State* L, int index);
PyObject* convertDictPython(lua_State* L, int index);
PyObject* convertTuplePython(lua_State* L, int index);
PyObject* convertListPython(lua_State* L, int index);
PyObject* convertFunctionPython(lua_State* L, int index);
PyObject* convertModulePython(lua_State* L, int index);

PyObject* convertPython(lua_State* L, int index);
