local utils = require "lib.utils"
local M = {
  INTERVAL = 0.001,
  visible = true,
  paused = false,
  osd_width = 0,
  osd_height = 0,
  _initialized = false,
  timer = nil,
  danmaku_merge_tolerance = -1,
  comments = {},
  style = {
    fontname = "sans-serif",
    fontsize = 36,
    shadow = 1,
    bold = true,
    displayarea = 0.50,
    outline = 1.0,
    transparency = 0x30,
  },
}

---解析弹幕文件
---@param danmaku_file string 弹幕文件的路径，格式为.ass
function M:parse_danmaku(danmaku_file)
  -- utils
  local function time_to_seconds(time_str)
    local h, m, s = time_str:match "(%d+):(%d+):([%d%.]+)"
    return tonumber(h) * 3600 + tonumber(m) * 60 + tonumber(s)
  end
  local function should_merge(current_event, events)
    local merged = false
    for _, existing_event in ipairs(events) do
      if
        not (
          existing_event.clean_text == current_event.clean_text
          and math.abs(existing_event.start_time - current_event.start_time)
            <= self.danmaku_merge_tolerance
        )
      then
        goto continue
      end

      if
        not (
          (existing_event.style == current_event.style)
          and (existing_event.pos == current_event.pos)
          and (existing_event.move == current_event.move)
        )
      then
        goto continue
      end

      existing_event.end_time =
        math.max(existing_event.end_time, current_event.end_time)
      existing_event.count = (existing_event.count or 1) + 1
      if not existing_event.text:find "{\\b1\\i1}x%d+$" then
        existing_event.text = existing_event.text
          .. "{\\b1\\i1}x"
          .. existing_event.count
      else
        existing_event.text =
          existing_event.text:gsub("x%d+$", "x" .. existing_event.count)
      end

      if true then
        merged = true
        break
      end

      ::continue::
    end

    return merged
  end

  local events = {}
  mp.msg.verbose("start analysing danmaku file: " .. danmaku_file)
  local fd = io.open(danmaku_file, "r")
  if not fd then
    mp.msg.error("无法打开弹幕文件: " .. danmaku_file)
    self.comments = events
    return events
  end

  -- parse line to events
  for line in fd:lines() do
    if not line:match "^Dialogue:" then
      goto continue
    end

    local start_time, end_time, style, text =
      line:match "Dialogue:%s*[^,]*,%s*([^,]*),%s*([^,]*),%s*([^,]*),[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,(.*)"

    if not (start_time and end_time and text) then
      goto continue
    end

    local event = {
      start_time = time_to_seconds(start_time),
      end_time = time_to_seconds(end_time),
      style = style,
      text = text:gsub("%s+$", ""),
      clean_text = text
        :gsub("\\h+", " ")
        :gsub("{[\\=].-}", "")
        :gsub("^%s*(.-)%s*$", "%1"),
      pos = text:match "\\pos",
      move = text:match "\\move",
    }

    if not should_merge(event, events) then
      event.count = 1
      table.insert(events, event)
    end

    ::continue::
  end

  table.sort(events, function(a, b)
    return a.start_time < b.start_time
  end)

  fd:close()
  self.comments = events
  mp.msg.verbose("total events: " .. #events .. " " .. #self.comments)
  return events
end

-- 开关弹幕
---@param visible boolean? 默认为当前状态取反
function M:toggle_visibility(visible)
  if visible == nil then
    visible = not self.visible
  end
  self.visible = visible
  if not self.timer or not self.overlay then
    return
  end
  if visible then
    self:render()
    if not self.paused then
      self.timer:resume()
    end
    -- self.overlay:update()
  else
    self.timer:kill()
    self.overlay.data = ""
    self.overlay:remove()
  end
end

function M:render()
  -- 提取 \move 参数 (x1, y1, x2, y2) 并返回
  local function parse_move_tag(text)
    -- 匹配包括小数和负数在内的坐标值
    local x1, y1, x2, y2 =
      text:match "\\move%((%-?[%d%.]+),%s*(%-?[%d%.]+),%s*(%-?[%d%.]+),%s*(%-?[%d%.]+).*%)"
    if x1 and y1 and x2 and y2 then
      return tonumber(x1), tonumber(y1), tonumber(x2), tonumber(y2)
    end
    return nil
  end
  local function parse_comment(event, pos, height)
    local x1, y1, x2, y2 = parse_move_tag(event.text)
    local displayarea = tonumber(height * self.style.displayarea)
    if not x1 then
      local current_x, current_y =
        event.text:match "\\pos%((%-?[%d%.]+),%s*(%-?[%d%.]+).*%)"
      if tonumber(current_y) > displayarea then
        return
      end
      if event.style ~= "SP" and event.style ~= "MSG" then
        return string.format("{\\an8}%s", event.text)
      else
        return string.format("{\\an7}%s", event.text)
      end
    end

    -- 计算移动的时间范围
    local duration = event.end_time - event.start_time --mean: options.scrolltime
    local progress = (pos - event.start_time - Delay) / duration -- 移动进度 [0, 1]

    -- 计算当前坐标
    local current_x = tonumber(x1 + (x2 - x1) * progress)
    local current_y = tonumber(y1 + (y2 - y1) * progress)

    -- 移除 \move 标签并应用当前坐标
    local clean_text = event.text:gsub("\\move%(.-%)", "")
    if current_y > displayarea then
      return
    end
    if event.style ~= "SP" and event.style ~= "MSG" then
      return string.format(
        "{\\pos(%.1f,%.1f)\\an8}%s",
        current_x,
        current_y,
        clean_text
      )
    else
      return string.format(
        "{\\pos(%.1f,%.1f)\\an7}%s",
        current_x,
        current_y,
        clean_text
      )
    end
  end
  if self.comments == nil then
    return
  end
  local pos, err = mp.get_property_number "time-pos"
  if err ~= nil then
    mp.msg.verbose(err)
    return
  end

  local fontsize = self.style.fontsize
  local width, height = 1920, 1080
  local ratio = self.osd_width / self.osd_height
  if width / height < ratio then
    height = width / ratio
    fontsize = self.style.fontsize - ratio * 2
  end

  local ass_events = {}

  for _, event in ipairs(self.comments) do
    if pos >= event.start_time + Delay and pos <= event.end_time + Delay then
      local text = parse_comment(event, pos, height)
      if text then
        text = text:gsub("&#%d+;", "")
      end

      if text and text:match "\\fs%d+" then
        local font_size = text:match "\\fs(%d+)" * 1.5
        text = text:gsub("\\fs%d+", string.format("\\fs%s", font_size))
      end

      -- 构建 ASS 字符串
      local ass_text = text
        and string.format(
          "{\\rDefault\\fn%s\\fs%d\\c&HFFFFFF&\\alpha&H%x\\bord%s\\shad%s\\b%s\\q2}%s",
          self.style.fontname,
          text:match "{\\b1\\i1}x%d+$" and fontsize + text:match "x(%d+)$"
            or fontsize,
          self.style.transparency,
          self.style.outline,
          self.style.shadow,
          self.style.bold and "1" or "0",
          text
        )

      table.insert(ass_events, ass_text)
    end
  end

  self.overlay.res_x = width
  self.overlay.res_y = height
  self.overlay.data = table.concat(ass_events, "\n")
  -- mp.msg.verbose(self.overlay.data)
  self.overlay:update()
end

function M:restart_timer()
  if self.timer then
    self.timer:kill()
  end
  self.timer = mp.add_periodic_timer(self.INTERVAL, function()
    self:render()
  end, true)
end

function M:setup(opts)
  if self._initialized then
    return self
  end

  utils.table_merge(M, opts)

  mp.observe_property("osd-width", "number", function(_, value)
    self.osd_width = value or self.osd_width
  end)
  mp.observe_property("osd-height", "number", function(_, value)
    self.osd_height = value or self.osd_height
  end)
  mp.observe_property("display-fps", "number", function(_, value)
    if not value then
      return
    end
    local interval = 1 / value / 10
    if interval > self.INTERVAL then
      mp.msg.verbose("danmaku render fps updated", interval)
      self.INTERVAL = interval
      self:restart_timer()
    end
  end)

  mp.observe_property("pause", "bool", function(_, pause)
    self.paused = pause
    if not self.timer then
      return
    end
    if pause then
      self.timer:kill()
    else
      if self.visible then
        self.timer:resume()
      end
    end
  end)
  self.overlay = mp.create_osd_overlay "ass-events"

  mp.add_hook("on_unload", 50, function()
    self.comments = {}
  end)
  self:restart_timer()

  self._initialized = true
  return self
end

return M
