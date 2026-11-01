require "lib.options"
require "lib.colors"
local bgm = require "lib.bgm"
local mp_utils = require "mp.utils"
local utils = require "lib.utils"
local menu = require "lib.menu"
local danmaku_render = require "lib.danmaku_render"

-- globals constants

PROPERTY_DISPATCH = "user-data/mpv_bangumi/dispatch"

Pid = mp_utils.getpid()
BgmReady = false
RequestID = 0

-- global variables
Delay = 0
EpisodeInfo = nil
AnimeInfo = nil
UpdateEpisodeTimer = nil
MatchResults = nil
SourceStatus = nil

local function stop_bangumi_timer()
  if UpdateEpisodeTimer then
    UpdateEpisodeTimer:kill()
    UpdateEpisodeTimer = nil
  end
end

local function reset_globals()
  EpisodeInfo = nil
  AnimeInfo = nil
  stop_bangumi_timer()
  MatchResults = nil
  menu.close()
  SourceStatus = nil
end

local handle_log = function(level, msg)
  if level == "verbose" then
    mp.msg.verbose(msg)
  elseif level == "info" then
    mp.msg.info(msg)
  elseif level == "warn" then
    mp.msg.warn(msg)
  elseif level == "error" then
    mp.msg.error(msg)
  else
    mp.msg.error("Unknown log level", level)
  end
end
local notify = function(msg, timeout) mp.osd_message(msg, timeout or 3) end

local function init_bgm()
  if BgmReady then
    return
  end

  local ipc_path = ""
  if package.config:sub(1,1) == "\\" then
      -- Windows syntax for named pipes
      ipc_path = [[\\.\pipe\mpv-ipc-]] .. Pid
  else
      -- Linux / macOS syntax for Unix domain sockets
      ipc_path = "/tmp/mpv-ipc-" .. Pid
  end
  mp.set_property("input-ipc-server", ipc_path)
  mp.msg.verbose("IPC Server created: " .. ipc_path)
  mp.register_event("shutdown", function()
    if package.config:sub(1, 1) == "\\" then
      os.remove(ipc_path)
    end
  end)

  mp_utils.subprocess_detached({args={Options.bgm_path, ipc_path}})
end

local function init_bangumi_timer()
  stop_bangumi_timer()
  UpdateEpisodeTimer = mp.add_periodic_timer(5, function()
    local current_time = mp.get_property_number "time-pos"
    local total_time = mp.get_property_number "duration"
    if not current_time or not total_time then
      return
    end
    local ratio = current_time / total_time
    if ratio < 0.8 then
      return
    end
    if AnimeInfo == nil then
      mp.msg.verbose "No AnimeInfo, skip update"
      return
    end
    if UpdateEpisodeTimer then
      UpdateEpisodeTimer:kill()
      UpdateEpisodeTimer = nil
      bgm.update_episode()
    else
      mp.msg.error "Unexpected value: UpdateEpisodeTimer = nil"
      return
    end
  end)
end

local function init(episode_id)
  reset_globals()
  if BgmReady then
    bgm.match(episode_id)
  else
    init_bgm()
  end
end

mp.add_hook("on_unload", 50, function()
  RequestID = RequestID + 1
  if BgmReady then
    bgm.send_action("invalidate", {})
  end
  reset_globals()
end)

mp.register_event("file-loaded", function()
  local path = mp.get_property "path"
  if path == "-" then
    mp.msg.verbose("Skipping init for stdin stream:", mp.get_property "path")
    return
  end
  if utils.is_protocol(path) then
    mp.msg.verbose("Skipping init for protocol:", mp.get_property "path")
    return
  end
  if not utils.is_video() then
    mp.msg.verbose("No video tracks, skip init:", mp.get_property "path")
    return
  end
  init()
end)

-- key bindings

local key_bindings = {
  ["C"] = { "send-danmaku" },
  ["Alt+z"] = { "danmaku-delay", "-0.5" },
  ["Alt+x"] = { "danmaku-delay", "+0.5" },
  ["Alt+."] = { "toggle-danmaku-visibility" },
  ["Alt+o"] = { "open-bangumi-url" },
  ["Alt+m"] = { "manual-match" },
  ["Alt+n"] = { "bangumi-settings" }
}

for key, binding in pairs(key_bindings) do
  table.insert(binding, 1, "script-message")
  local desc = table.concat(binding, "", 2)
  mp.msg.verbose("key:", key, "binding:", binding[2], "desc:", desc)
  mp.add_key_binding(key, desc, function()
    mp.command_native(binding)
  end)
end

-- script messages

mp.register_script_message("send-danmaku", function(comment)
  if not EpisodeInfo or not EpisodeInfo.episodeId then
    mp.msg.error "未匹配到视频信息"
    return
  end

  if not comment then
    menu.show_comment()
  else
    bgm.send_danmaku(EpisodeInfo.episodeId, comment)
  end
end)

mp.register_script_message("danmaku-delay", function(delay)
  delay = tonumber(delay)
  if not delay then
    mp.msg.error "无效的延迟值"
    return
  end
  if delay == 0 then
    Delay = 0
  else
    Delay = Delay + delay
  end
  mp.osd_message(
    "弹幕延迟: " .. string.format("%.1f", Delay + 1e-10) .. "秒",
    3
  )
end)

mp.register_script_message("toggle-danmaku-visibility", function()
  require("lib.danmaku_render"):toggle_visibility()
end)

mp.register_script_message("open-bangumi-url", function()
  if not AnimeInfo or not AnimeInfo.bgm_id then
    mp.msg.error "未匹配到番剧信息"
    return
  end
  bgm.open_url(AnimeInfo.bgm_id)
  notify("网页打开成功", 2)
end)


mp.register_script_message("manual-match", function()
  menu.show_match_results(MatchResults, init)
end)
mp.register_script_message("bangumi-settings", menu.show_settings)
mp.register_script_message("niconico-danmaku", menu.show_settings)
mp.register_script_message("set-bangumi-id", menu.set_bangumi)
mp.register_script_message("clear-bangumi-id", menu.clear_bangumi)


mp.register_script_message("mpvbangumi-action", function(_args)
  local args = mp_utils.parse_json(_args)
  if type(args) ~= "table" then
    mp.msg.error("Json parse error: ", args)
    return
  end

  if args.request_id and args.request_id ~= RequestID then
    return
  end

  local action = args.action
  local data = args.data

  if action == "log" then
    handle_log(data.level, data.msg)
  elseif action == "notify" then
    notify(data.message)
  elseif action == "ready" then
    mp.msg.verbose("mpv python ipc ready")
    BgmReady = true
    init()
  elseif action == "match" then
    EpisodeInfo = data.info
    notify(
      string.format(
        "匹配成功：%s",
        data.desc
      )
    )
  elseif action == "sources" then
    SourceStatus = data
    menu.refresh_settings()
  elseif action == "set-danmaku" then
    danmaku_render:setup(data.events, data.style)
  elseif action == "set-bangumi-id" then
    AnimeInfo = data
    stop_bangumi_timer()
    if data.bgm_id and data.ready then
      init_bangumi_timer()
    end
    menu.refresh_settings()
  elseif action == "bangumi-subject" then
    menu.confirm_bangumi(data)
  elseif action == "select-match" then
    notify "匹配结果不唯一，请手动选择"
    MatchResults = data["matches"]
  elseif action == "search-results" then
    menu.show_anime_results(data)
  elseif action == "anime-episodes" then
    menu.show_episode_results(data, init)
  end
end)
