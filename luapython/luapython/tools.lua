local functions = ({ ... })[0]

local tools = {}

function tools.shouldConvertToDict(obj)
    if type(obj) ~= "table" then
        error("tools.lua: table expected, got " .. type(obj))
    end
    local ncount = 0
    local scount = 0
    for i, _ in pairs(obj) do
        if type(i) == "number" then
            ncount = ncount + 1
        elseif type(i) == "string" then
            scount = scount + 1
        end
    end
    return scount >= ncount
end

function tools.releaseToEnv(luapython, env, key)
    if env == nil and key == nil then
        env = _G
        key = nil
    elseif type(env) == "string" and key == nil then
        key = env
        env = _G
    elseif type(env) ~= "table" then
        error("tools.lua: Env table expected")
    end
    
    if key ~= nil and type(key) ~= "string" then
        error("tools.lua: Key must be a string")
    end

    if type(luapython) ~= "table" then
        error("tools.lua: First arguement must be a table")
    end

    if key then
        env[key] = luapython[key]
    else
        for k, v in pairs(luapython) do
            if k ~= "init" then
                env[k] = v
            end
        end
    end
end

function tools.getPythonAdaptFunction(python_function)
    if type(python_function) ~= "function" then
        error("tools.lua: function expected, got " .. type(python_function))
    end
    local adaptfunction = function(self, ...)
        local args = { ... }
        local n = #args
        local arg_dict = args[n]
        if type(arg_dict) == "table" and tools.shouldConvertToDict(arg_dict) then
            args[n] = nil
            n = n - 1
        else
            arg_dict = {}
        end
        return python_function(self, args, arg_dict, n)
    end
    return adaptfunction
end

function tools.getIterFunction(iter, get)
    if type(iter) ~= "function" then
        error("tools.lua: first argument is not a function")
    end

    if type(get) ~= "function" then
        error("tools.lua: second argument is not a function")
    end
    local function iter_func(array)
        return iter, get(array), nil
    end

    return iter_func
end

return tools
