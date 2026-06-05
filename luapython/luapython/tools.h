#include <lua.h>
#include <lauxlib.h>

extern int tools_should_convert_to_dict;
extern int tools_release_to_env;
extern int tools_get_python_adapt_function;
extern int tools_get_iter_function;

int luapython_astable(lua_State* L);

void loadTools(lua_State* L);
