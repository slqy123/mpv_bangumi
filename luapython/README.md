# luapython

Library of manipulating Python in Lua.

**This project is under development...**

Create an issue if any bug occurred.

> This project is only supported on Linux temporarily.

## Requirements

Lua, Python & Luarocks installed on your system.

## Quick start

1. Install Lua and Python. (Latest Lua version recommended)

2. Build & install this project.
```bash
git clone https://github.com/imitoy/luapython.git
cd luapython
sudo luarocks make # require python headers
# when uninstall, run sudo luarocks remove luapython
```
3. Import this library and load with python version in Lua.
```lua
luapython=require "luapython"
luapython.load()
```

4. Import python modules in Lua.
```lua
numpy=luapython.import"numpy" -- Make sure numpy is installed
print(numpy.array({1,2,3}))

math=luapython.import"math"
print(math.tan(90))
```

5. Create Python structure by using `dict`, `set`, `list`, `tuple`.
```lua
json=luapython.import"json"
local data = luapython.dict{name="Alice", age=18}
print(json.dumps(data))
```

6. Create a table to adapt keywords parameters.
```lua
local OpenAI = luapython.import"openai.OpenAI"
local client = OpenAI({api_key="<DeepSeek API Key>", base_url="https://api.deepseek.com"})

local response = client.chat.completions.create({
    model="deepseek-chat",
    messages={
        {role = "system", content = "You are a helpful assistant"},
        {role = "user", content = "Hello"},
    },
    stream=false
})

print(response.choices[0].message.content)
```

7. Append `()` to the Python Iter Object.
```lua
local response = client.chat.completions.create({
    model="deepseek-chat",
    messages={
        {role = "system", content = "You are a helpful assistant"},
        {role = "user", content = "Hello"},
    },
    stream=true
})

for chunk in response() do
    io.write(chunk.choices[0].delta.content)
    io.flush()
end
```

## Use in a virtual env (Conda recommended)
1. Activate virtual env & check `python3-config --exec-prefix`.
```bash
conda activate v_env
python3-config --exec-prefix
```

2. Call the function load().
```lua
local luapython = require"luapython"
local path = luapython.load(3.14, "/path_to_v_env/lib")
-- or luapython.load()                              -- will find libpython automatically
-- or luapython.loadNative("/path_to_libpython.so") -- will load lib directly
```

## TODO

- [x] Support for Python version above 3.8
- [x] Support for Lua5.5
- [x] Conda support
- [ ] Integrate Python error in Lua
