local mp_utils = require "mp.utils"
local M = {}

function M.table_merge(dest, source, forceOverride)
  if not dest or not source then
    return dest
  end
  for k, v in pairs(source) do
    if
      (not forceOverride and type(v) == "table" and type(dest[k])) == "table"
    then
      -- don't overwrite one table with another
      -- instead merge them recurisvely
      M.table_merge(dest[k], v)
    else
      dest[k] = v
    end
  end
  return dest
end

function M.file_exists(filename)
  local file_info = mp_utils.file_info(filename)
  return file_info and file_info.is_file
end

-- 将弹幕转换为factory可读的json格式
function M.save_json_for_factory(comments, json_filename)
  local temp_file = "danmaku-" .. Pid .. ".json"
  json_filename = json_filename or utils.join_path(danmaku_path, temp_file)
  local json_file = io.open(json_filename, "w")

  if json_file then
    json_file:write "[\n"
    for _, comment in ipairs(comments) do
      local p = comment["p"]
      local shift = comment["shift"]
      if p then
        local fields = split(p, ",")
        if shift ~= nil then
          fields[1] = tonumber(fields[1]) + tonumber(shift)
        end
        local c_value = string.format(
          "%s,%s,%s,25,,,",
          tostring(fields[1]), -- first field of p to first field of c
          fields[3], -- third field of p to second field of c
          fields[2] -- second field of p to third field of c
        )
        local m_value = comment["m"]

        -- Write the JSON object as a single line, no spaces or extra formatting
        local json_entry =
          string.format('{"c":"%s","m":"%s"},\n', c_value, m_value)
        json_file:write(json_entry)
      end
    end
    json_file:write "]"
    json_file:close()
    return true
  end

  return false
end

-- 对mpv subprocess 命令的封装
---@param args table
function M.subprocess_wrapper(args)
  ---检查并返回subprocess的stdout结果(必须为json)
  ---@param result any
  -- ---@return table?
  local check_result = function(result)
    if result.status ~= 0 then
      mp.msg.error("subprocess 执行失败: status=" .. result.status)
      return nil
    end

    if not result.stdout or result.stdout == "" then
      mp.msg.verbose "stdout为空"
      return {}
    end

    local json_result = mp_utils.parse_json(result.stdout)
    if not json_result then
      mp.msg.error("解析JSON失败: " .. result.stdout)
      return nil
    end

    return json_result
  end

  local function async(cb)
    cb = cb or {}
    cb.resp = cb.resp or function(_) end
    cb.err = cb.err or function() end

    mp.command_native_async({
      name = "subprocess",
      args = args,
      playback_only = false,
      capture_stdout = true,
      capture_stderr = true,
    }, function(success, result, error)
      if not success or not result or result.status ~= 0 then
        local exit_code = (result and result.status or "unknown")
        local message = error
          or (result and result.stdout .. result.stderr)
          or ""
        mp.msg.error(
          "Calling failed. Exit code: " .. exit_code .. " Error: " .. message
        )
        cb.err()
        return
      end
      local json_result = check_result(result)
      cb.resp(json_result)
    end)
  end

  return {
    execute = function()
      local result = mp.command_native {
        name = "subprocess",
        args = args,
        playback_only = false,
        capture_stdout = true,
        capture_stderr = true,
      }
      return check_result(result)
    end,
    async = async,
  }
end

function M.subprocess_err()
  return {
    execute = function()
      return nil
    end,
    async = function(cb)
      if cb and cb.err then
        cb.err()
      end
    end,
  }
end

function M.is_protocol(path)
    return type(path) == 'string' and (path:find('^%a[%w.+-]-://') ~= nil or path:find('^%a[%w.+-]-:%?') ~= nil)
end

return M
