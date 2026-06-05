local loader = require("luapython.loader")

-- It is not recommanded to call native method directly,
-- but we still keep it for advanced users who want to manage the loading process manually.
-- loader.loadNative = nil

function loader.load(version, lib_prefix)
	if not lib_prefix then
		local check = os.execute("python3-config --exec-prefix > /dev/null 2>&1")
		if not check then
			lib_prefix = ""
		else
			local handle = io.popen("python3-config --exec-prefix")
			lib_prefix = handle:read()
			handle:close()
            lib_prefix = lib_prefix.."/lib"
		end
	end
	if type(version) == "number" then
		version = tostring(version)
	elseif type(version) == "nil" then
		local command = "python3 --version"
		local check_command = os.execute(command .. " > /dev/null 2>&1")
		local check = check_command
		if check_command then
			local handle = io.popen(command)
			local version_info = handle:read()
			local version_extract = string.match(version_info, "%d%.%d+")
			if version_extract then
				version = tonumber(version_extract)
			else
				check = false
			end
		end
		if not check then
			version = "3"
		end
	elseif type(version) ~= "string" then
		error("core.load: version: string expected, got" .. type(version))
	end
	if lib_prefix ~= "" then
		lib_prefix = lib_prefix .. "/"
	end
	local path = lib_prefix .. "libpython" .. version .. ".so"
	loader.loadNative(path)
    local core = require("luapython.core")
    local luapython = loader
    for k, v in pairs(core) do
        luapython[k] = v
    end
    luapython.initialize()
    return path
end

function loader.load_prefix(prefix)
	local executable = prefix .. "/bin/python3"
	local handle = io.popen(executable ..
	[[ -c "import sysconfig, os; print(os.path.join(sysconfig.get_config_var('LIBDIR'), sysconfig.get_config_var('LDLIBRARY')))"]])
	if handle == nil then
		error("core.load_prefix: failed to call python from prefix: " .. prefix)
	end
	local lib_path = handle:read()
	loader.loadNative(lib_path)
	local core = require("luapython.core")
	local luapython = loader
	for k, v in pairs(core) do
		luapython[k] = v
	end
	luapython.initialize(executable)
	return lib_path
end

return loader
