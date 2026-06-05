return function(func)
    if type(func) ~= "function" then
        error("import.lua: function expected, got " .. type(func))
    end

    return function(module_name)
        if type(module_name) ~= "string" then
            error("import.lua: string expected, got " .. type(module_name))
        end

        local module = func(module_name, false)

        if module then
            return module
        end

        local index = string.find(module_name, "%.")
        if index then
            local submodule_name = string.sub(module_name, 1, index - 1)
            module = func(submodule_name, true)
        else
            error("import.lua: module '" .. module_name .. "' not found")
        end

        if module then
            for w in string.gmatch(string.sub(module_name, index + 1) .. ".", "[^%.]+%.") do
                module = module[string.sub(w, 1, -2)]
                if not(module) then
                    error("import.lua: module'" .. module_name .. "' not found")
                end
            end
        else
            func(module_name, true)
            error("import.lua: module '" .. module_name .. "' not found")
        end

        return module
    end
end
