local opt = require "mp.options"
local mp_utils = require "mp.utils"

Options = {
  bgm_path = "",

  -- 发送弹幕时默认的颜色和位置
  user_default_danmaku_color = "white",
  user_default_danmaku_position = "normal", -- normal, top, bottom
}

opt.read_options(Options, mp.get_script_name(), function() end)

-- set default values for bgm_path if not set
---@param exe string
local function binary_fallback(exe)
  local py_binary_dir
  if mp.get_property_native "platform" == "windows" then
    if exe:sub(-4) ~= ".exe" then
      exe = exe .. ".exe"
    end
    py_binary_dir = mp_utils.join_path(mp.get_script_directory(), "bgm/.venv/Scripts")
  else
    py_binary_dir = mp_utils.join_path(mp.get_script_directory(), "bgm/.venv/bin")
  end
  local path = mp_utils.join_path(py_binary_dir, exe)

  local file_info = mp_utils.file_info(path)
  if not file_info or not file_info.is_file then
    mp.msg.verbose("Binary not found in bin directory: " .. path)
    path = exe
  end
  return path
end

if not Options.bgm_path or #Options.bgm_path == 0 then
  Options.bgm_path = binary_fallback "bgm"
end
