local input = require "mp.input"
local bgm = require "lib.bgm"

local M = {}
local dialog
local pending
local view

local function dismiss()
  if pending then
    pending:kill()
    pending = nil
  end
  local previous = dialog
  dialog = nil
  if previous then
    if previous.opened then
      input.terminate(previous.id)
    end
    if previous.pause ~= nil then
      mp.set_property_native("pause", previous.pause)
    end
  end
end

function M.close()
  view = nil
  dismiss()
end

local function show(method, options, name, pause)
  dismiss()
  view = name
  local current = {}
  dialog = current
  -- Allow mp.input to finish closing before reopening: https://github.com/mpv-player/mpv/pull/17256
  pending = mp.add_timeout(0.2, function()
    pending = nil
    if pause then
      current.pause = mp.get_property_native "pause"
      mp.set_property_native("pause", true)
    end
    local submit = options.submit
    options.submit = function(value)
      if dialog == current then
        submit(value)
      end
    end
    options.closed = function()
      if dialog ~= current then
        return
      end
      dialog = nil
      if current.pause ~= nil then
        mp.set_property_native("pause", current.pause)
      end
      if view == name then
        view = nil
      end
    end
    current.opened = true
    current.id = input[method](options)
  end)
end

local function select_menu(prompt, entries, name, pause)
  local items = {}
  for i, entry in ipairs(entries) do
    items[i] = entry.label
  end
  show("select", {
    prompt = prompt,
    items = items,
    submit = function(index)
      local entry = entries[index]
      if entry then
        entry.action()
      end
    end,
  }, name, pause)
end

local function notify(message)
  mp.osd_message(message, 4)
end

function M.show_comment()
  show("get", {
    prompt = "请输入弹幕内容：",
    submit = function(text)
      M.close()
      bgm.send_danmaku(EpisodeInfo.episodeId, text)
    end,
  }, "comment", true)
end

function M.show_match_results(results, on_match)
  if not results then
    show("get", {
      prompt = "请输入番剧名：",
      submit = function(text)
        M.close()
        if text:match "%S" then
          MatchResults = nil
          bgm.dandanplay_search(text)
        end
      end,
    }, "match-search", true)
    return
  end
  local entries = {}
  for _, result in ipairs(results) do
    entries[#entries + 1] = {
      label = string.format("%s\t[%s]", result.animeTitle, result.episodeTitle),
      action = function()
        M.close()
        on_match(result.episodeId)
      end,
    }
  end
  entries[#entries + 1] = {
    label = "没有结果，手动搜索",
    action = function()
      M.show_match_results(nil, on_match)
    end,
  }
  select_menu("请选择匹配结果：", entries, "match-results", true)
end

function M.show_anime_results(results)
  if not results or #results == 0 then
    notify "没有找到匹配的番剧"
    return
  end
  local entries = {}
  for _, result in ipairs(results) do
    entries[#entries + 1] = {
      label = string.format("%s\t[%s]", result.title, result.type),
      action = function()
        M.close()
        bgm.get_dandanplay_episodes(result.id)
      end,
    }
  end
  select_menu("请选择正确番剧：", entries, "anime-results")
end

function M.show_episode_results(results, on_match)
  if not results or #results == 0 then
    notify "没有找到匹配的剧集"
    return
  end
  local entries = {}
  for _, result in ipairs(results) do
    entries[#entries + 1] = {
      label = result.title,
      action = function()
        M.close()
        on_match(result.id)
      end,
    }
  end
  select_menu("请选择正确剧集：", entries, "episode-results")
end

local function update_source(source, changes)
  local sources = {}
  for key, info in pairs(SourceStatus) do
    sources[key] = {}
    for name, value in pairs(info) do
      sources[key][name] = value
    end
  end
  sources[source] = sources[source] or {}
  for name, value in pairs(changes) do
    sources[source][name] = value
  end
  dismiss()
  view = "settings-wait"
  bgm.update_source_status(EpisodeInfo, sources)
end

function M.set_bangumi(value)
  if not EpisodeInfo then
    notify "请先完成 DandanPlay 番剧匹配"
    return
  end
  if value then
    if not value:match "%S" then
      M.close()
      return
    end
    dismiss()
    view = "bangumi-validate"
    bgm.validate_bangumi_id(value)
    return
  end
  show("get", {
    prompt = "请输入 Bangumi ID 或条目链接：",
    default_text = AnimeInfo and AnimeInfo.bgm_id and tostring(
      AnimeInfo.bgm_id
    ) or "",
    submit = M.set_bangumi,
  }, "bangumi-input")
end

function M.confirm_bangumi(subject)
  if view ~= "bangumi-validate" then
    return
  end
  if subject.error then
    notify(subject.error)
    M.set_bangumi()
    return
  end
  select_menu(
    string.format(
      "《%s》 [%d]：将应用于当前 DandanPlay 番剧，并同步收藏和进度。",
      subject.title,
      subject.bgm_id
    ),
    {
      {
        label = "确认关联",
        action = function()
          dismiss()
          view = "settings-wait"
          bgm.set_bangumi_id(subject.bgm_id)
        end,
      },
      { label = "取消", action = M.close },
    },
    "bangumi-confirm"
  )
end

function M.clear_bangumi()
  if not EpisodeInfo or not AnimeInfo or AnimeInfo.source ~= "manual" then
    notify "当前没有手动 Bangumi 关联"
    return
  end
  dismiss()
  view = "settings-wait"
  bgm.set_bangumi_id(nil)
end

function M.show_settings()
  if not EpisodeInfo or not SourceStatus then
    notify "番剧或弹幕源信息尚未就绪"
    return
  end
  local entries = {}
  for _, source in ipairs {
    { key = "main", label = "DandanPlay" },
    { key = "niconico", label = "Niconico" },
  } do
    local enabled = SourceStatus[source.key]
      and SourceStatus[source.key].enabled
    entries[#entries + 1] = {
      label = string.format(
        "%s 弹幕：%s → %s",
        source.label,
        enabled and "开启" or "关闭",
        enabled and "关闭" or "开启"
      ),
      action = function()
        update_source(source.key, { enabled = not enabled })
      end,
    }
  end
  entries[#entries + 1] = {
    label = "Niconico 集数映射…",
    action = function()
      local episode = EpisodeInfo.episodeId % 10000
      show("get", {
        prompt = string.format("将当前集数 (%d) 映射到：", episode),
        submit = function(text)
          local target = tonumber(text)
          if not target or target < 1 or target % 1 ~= 0 then
            notify "请输入正整数集数"
            return
          end
          update_source("niconico", { offset = target - episode })
        end,
      }, "niconico-offset")
    end,
  }
  entries[#entries + 1] = {
    label = "Niconico Series ID…",
    action = function()
      show("get", {
        prompt = "请输入 Niconico Series ID：",
        submit = function(text)
          if not text:match "^%d+$" or tonumber(text) <= 0 then
            notify "请输入正整数 Series ID"
            return
          end
          update_source("niconico", { series = text })
        end,
      }, "niconico-series")
    end,
  }
  local anime = AnimeInfo or {}
  local association = "未关联"
  if anime.bgm_id then
    association = string.format(
      "%d（%s）",
      anime.bgm_id,
      anime.source == "manual" and "手动" or "自动"
    )
  end
  entries[#entries + 1] = {
    label = "Bangumi 关联："
      .. association
      .. (anime.bgm_id and " → 修改…" or " → 设置…"),
    action = function()
      M.set_bangumi()
    end,
  }
  if anime.source == "manual" then
    entries[#entries + 1] = {
      label = "恢复 Bangumi 自动关联",
      action = M.clear_bangumi,
    }
  end
  select_menu("番剧与弹幕设置：", entries, "settings")
end

function M.refresh_settings()
  if view == "settings" or view == "settings-wait" then
    M.show_settings()
  end
end

return M
