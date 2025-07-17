local utils = require "lib.utils"
local mp_utils = require "mp.utils"

local M = {}

-- force id will skip the matching process and use the provided id directly
function M.match(force_id)
  local file_path = mp.get_property "path"
  local file_info = mp_utils.file_info(file_path)

  if not file_info or not file_info.is_file then
    mp.msg.error("文件不存在或不是有效的文件: " .. file_path)
    return utils.subprocess_err()
  end
  local args = {
    Options.bgm_path,
    "dandanplay",
    "fetch",
    file_path,
  }
  if force_id then
    table.insert(args, "--force-id")
    table.insert(args, tostring(force_id))
  end

  return utils.subprocess_wrapper(args)
end

function M.send_danmaku(episode_id, comment)
  local color = NamedColors[Options.user_default_danmaku_color]
  local position_map = {
    normal = 1,
    n = 1,
    bottom = 4,
    b = 4,
    top = 5,
    t = 5,
  }
  local position = position_map[Options.user_default_danmaku_position] or 1
  local start = 1
  while true do
    local char = comment:sub(start, start)
    if char == " " then
      start = start + 1
    elseif char == "/" then
      local end_pos = comment:find(" ", start)
      if not end_pos then
        start = start + 1
        goto continue
      end
      local cmd = comment:sub(start + 1, end_pos - 1)
      start = end_pos + 1
      if position_map[cmd] then
        position = position_map[cmd]
      elseif NamedColors[cmd] then
        color = NamedColors[cmd]
      else
        if cmd:match "^[0-9A-Fa-f]+$" and #cmd == 6 then
          color = tonumber(cmd, 16)
        else
          mp.msg.error("无效命令：" .. cmd)
        end
      end
    else
      break
    end
    ::continue::
  end
  comment = comment:sub(start)
  if comment == "" then
    mp.msg.verbose "弹幕内容为空"
    return
  end

  local time_pos = mp.get_property_number "time-pos" - Delay
  return utils.subprocess_wrapper {
    Options.bgm_path,
    "dandanplay",
    "comment",
    comment,
    "--episode-id",
    tostring(episode_id),
    "--color",
    tostring(color),
    "--position",
    tostring(position),
    "--time",
    tostring(time_pos),
  }
end

function M.update_metadata()
  local file_path = mp.get_property "path"
  local file_info = mp_utils.file_info(file_path)

  if not file_info or not file_info.is_file then
    mp.msg.error("文件不存在或不是有效的文件: " .. file_path)
    return utils.subprocess_err()
  end

  return utils.subprocess_wrapper {
    Options.bgm_path,
    "dandanplay",
    "update-metadata",
    file_path,
  }
end

function M.open_url(url)
  return utils.subprocess_wrapper {
    Options.bgm_path,
    "open-url",
    url,
  }
end

function M.update_bangumi_collection()
  if not AnimeInfo.bgm_id then
    mp.msg.error "未匹配到Bangumi ID，更新条目失败"
    return utils.subprocess_err()
  end

  return utils.subprocess_wrapper {
    Options.bgm_path,
    "bangumi",
    "update-collection",
    tostring(AnimeInfo.bgm_id),
  }
end

function M.fetch_episodes()
  if not AnimeInfo.bgm_id then
    mp.msg.error "未匹配到Bangumi ID，更新剧集失败"
    return utils.subprocess_err()
  end
  local file_path = mp.get_property "path"
  local file_info = mp_utils.file_info(file_path)

  if not file_info or not file_info.is_file then
    mp.msg.error("文件不存在或不是有效的文件: " .. file_path)
    return utils.subprocess_err()
  end

  return utils.subprocess_wrapper {
    Options.bgm_path,
    "bangumi",
    "fetch-episodes",
    file_path,
  }
end

function M.update_episode()
  if not AnimeInfo.bgm_id then
    mp.msg.error "未匹配到Bangumi ID，更新剧集失败"
    return utils.subprocess_err()
  end
  local file_path = mp.get_property "path"
  local file_info = mp_utils.file_info(file_path)

  if not file_info or not file_info.is_file then
    mp.msg.error("文件不存在或不是有效的文件: " .. file_path)
    return utils.subprocess_err()
  end

  return utils.subprocess_wrapper {
    Options.bgm_path,
    "bangumi",
    "update-episode",
    file_path,
  }
end

function M.dandanplay_search(keyword)
  return utils.subprocess_wrapper {
    Options.bgm_path,
    "dandanplay",
    "search",
    keyword,
  }
end

function M.get_dandanplay_episodes(anime_id)
  return utils.subprocess_wrapper {
    Options.bgm_path,
    "dandanplay",
    "get-episodes",
    tostring(anime_id),
  }
end

return M
