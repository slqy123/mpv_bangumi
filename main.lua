require "lib.options"
require "lib.colors"
local bgm = require "lib.bgm"
local mp_utils = require "mp.utils"
local utils = require "lib.utils"
local input = require "mp.input"
local danmaku_render = require "lib.danmaku_render"

-- globals constants

PROPERTY_DISPATCH = "user-data/mpv_bangumi/dispatch"

Pid = mp_utils.getpid()
BgmReady = false

-- global variables
Delay = 0
EpisodeInfo = nil
AnimeInfo = nil
UpdateEpisodeTimer = nil
BangumiSucessFlag = 0
MatchResults = nil
InputID = nil  -- fix race condition for mp.input, need https://github.com/mpv-player/mpv/pull/17256
SourceStatus = nil

local function reset_globals()
  -- Delay = 0
  EpisodeInfo = nil
  AnimeInfo = nil
  if UpdateEpisodeTimer then
    UpdateEpisodeTimer:kill()
    UpdateEpisodeTimer = nil
  end
  BangumiSucessFlag = 0
  MatchResults = nil
  input.terminate(InputID)
  InputID = nil
  SourceStatus = nil
end

local handle_log = function(level, msg, timeout)
  timeout = timeout or 3
  if level == "verbose" then
    mp.msg.verbose(msg)
  elseif level == "info" then
    mp.msg.info(msg)
  elseif level == "warn" then
    mp.msg.warn(msg)
  elseif level == "error" then
    mp.msg.error(msg)
    mp.osd_message(msg, timeout)
  elseif level == "notify" then
    mp.msg.info(msg)
    mp.osd_message(msg, timeout)
  else
    mp.msg.error("Unkonw log level", level)
  end
end
local notify = function(msg, timeout) handle_log("notify", msg, timeout) end

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

mp.register_event("file-loaded", function()
  if utils.is_protocol(mp.get_property "path") then
    mp.msg.verbose("Skipping init for protocol:", mp.get_property "path")
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
  ["Alt+n"] = { "niconico-danmaku" }
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
    mp.set_property("pause", "yes")
    InputID = input.get {
      prompt = "请输入弹幕内容：",
      submit = function(text)
        input.terminate(InputID)
        mp.set_property("pause", "no")
        comment = text
        bgm.send_danmaku(EpisodeInfo.episodeId, comment)
      end,
    }
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
  mp.set_property("pause", "yes")
  if not MatchResults then
    InputID = input.get {
      prompt = "请输入番剧名：",
      submit = function(text)
        input.terminate(InputID)
        bgm.dandanplay_search(text)
      end,
      closed = function()
        mp.set_property("pause", "no")
      end,
    }
    return
  end

  local match_items = {}
  for i, match in ipairs(MatchResults) do
    match_items[i] =
        string.format("%d. %s\t[%s]", i, match.animeTitle, match.episodeTitle)
  end
  match_items[#match_items + 1] = "没有结果，手动搜索"

  InputID = input.select {
    prompt = "请选择匹配结果：",
    items = match_items,
    submit = function(idx)
      input.terminate(InputID)
      if idx < 1 or idx > #match_items then
        mp.msg.error "无效的选择"
        return
      end
      if idx == #match_items then
        mp.msg.verbose "选择了手动搜索"
        MatchResults = nil
        mp.command "script-message manual-match"
        return
      end
      local selected_match = MatchResults[idx]
      mp.msg.verbose(
        "选择的匹配结果:",
        selected_match.animeTitle,
        selected_match.episodeTitle
      )
      init(selected_match.episodeId)
    end,
    closed = function()
      mp.set_property("pause", "no")
    end,
  }
end)

local select_episode = function(data)
  if not data or #data == 0 then
    mp.msg.error "没有找到匹配的剧集"
    mp.osd_message("没有找到匹配的剧集", 3)
    return
  end
  local episode_items = {}
  for i, item in ipairs(data) do
    episode_items[i] = item.title
  end
  input.select {
    prompt = "请选择正确剧集：",
    items = episode_items,
    submit = function(idx)
      if idx < 1 or idx > #data then
        mp.msg.error "无效的选择"
        return
      end
      local selected_episode = data[idx]
      mp.msg.verbose(
        "选择的剧集:",
        selected_episode.id,
        selected_episode.title
      )
      init(selected_episode.id)
    end,
  }
end
local select_anime = function(data)
  if not data or #data == 0 then
    mp.msg.error "没有找到匹配的番剧"
    mp.osd_message("没有找到匹配的番剧", 3)
    return
  end
  local anime_items = {}
  for i, item in ipairs(data) do
    anime_items[i] = string.format("%d. %s\t[%s]", i, item.title, item.type)
  end
  InputID = input.select {
    prompt = "请选择正确番剧：",
    items = anime_items,
    submit = function(idx)
      input.terminate(InputID)
      if idx < 1 or idx > #data then
        mp.msg.error "无效的选择"
        return
      end
      local selected_anime = data[idx]
      mp.msg.verbose("选择的番剧:", selected_anime.title)
      bgm.get_dandanplay_episodes(selected_anime.id)
    end,
  }
end


mp.register_script_message("niconico-danmaku", function()
  local function update_status_and_reload_danmaku()
    bgm.update_source_status(EpisodeInfo, SourceStatus)
  end

  if SourceStatus == nil then
    mp.msg.error("No sources information found!")
    mp.osd_message("获取弹幕源状态失败！")
    return
  end

  SourceStatus.niconico = SourceStatus.niconico or {}
  SourceStatus.main = SourceStatus.main or {}

  InputID = input.select {
    prompt = "N站弹幕设置：",
    items = {
      "仅显示N站弹幕",
      "不显示N站弹幕",
      "同时显示N站与dandanplay弹幕",
      "修改剧集匹配映射关系",
      "通过series id匹配"
    },
    submit = function(idx)
      input.terminate(InputID)
      if idx < 1 or idx > 5 then
        mp.msg.error "无效的选择"
        return
      end
      if idx == 4 then
        mp.add_timeout(0.2, function()
          InputID = input.get {
            prompt = string.format("将当前章节数(%d)映射到：", EpisodeInfo.episodeId % 10000),
            submit = function(ep)
              mp.msg.verbose("submit")
              input.terminate(InputID)
              local ep_offset = tonumber(ep) - EpisodeInfo.episodeId % 10000
              SourceStatus.niconico.offset = ep_offset
              update_status_and_reload_danmaku()
            end
          }
        end)
        return
      end

      if idx == 5 then
        mp.add_timeout(0.2, function()
          InputID = input.get {
            prompt = "请输入series id：",
            submit = function(series_id)
              input.terminate(InputID)
              SourceStatus.niconico.series = series_id
              update_status_and_reload_danmaku()
            end
          }
        end)
        return
      end

      --- idx == 1, 2, 3

      if idx == 1 then
        SourceStatus.main.enabled = false
        SourceStatus.niconico.enabled = true
      end

      if idx == 2 then
        SourceStatus.main.enabled = true
        SourceStatus.niconico.enabled = false
      end

      if idx == 3 then
        SourceStatus.main.enabled = true
        SourceStatus.niconico.enabled = true
      end
      update_status_and_reload_danmaku()
    end
  }
end)


mp.register_script_message("mpvbangumi-action", function(_args)
  local args = mp_utils.parse_json(_args)
  if type(args) ~= "table" then
    mp.msg.error("Json parse error: ", args)
    return
  end

  local action = args.action
  local data = args.data

  if action == "log" then
    handle_log(data.level, data.msg)
  elseif action == "ready" then
    mp.msg.info("mpv python ipc ready")
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
  elseif action == "set-danmaku" then
    danmaku_render:setup(data.events, data.style)
  elseif action == "set-bangumi-id" then
    AnimeInfo = data
    init_bangumi_timer()
  elseif action == "select-match" then
    notify "匹配结果不唯一，请手动选择"
    MatchResults = data["matches"]
  elseif action == "search-results" then
    select_anime(data)
  elseif action == "anime-episodes" then
    select_episode(data)
  end
end)
