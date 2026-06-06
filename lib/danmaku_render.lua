local utils = require "lib.utils"

local function filter_state(label, name)
  local filters = mp.get_property_native("vf")
  for _, filter in pairs(filters) do
    if filter.label == label or filter.name == name
        or (name and filter.params[name] ~= nil) then
      return true
    end
  end
  return false
end

local M = {
  visible = true,
  paused = true,
  osd_width = 0,
  osd_height = 0,
  _initialized = false,
  _last_pos = -1,
  _last_index = 1,
  _max_duration = 5,
  _observer_active = false,
  comments = {},
  style = {
    fontname = "sans-serif",
    fontsize = 36,
    shadow = 1,
    bold = true,
    displayarea = 0.5,
    outline = 1.0,
    transparency = 48,
    scrolltime = 15,
    fixtime = 8,
    vf_fps = true,
    fps = 60,
  },
}

function M:toggle_visibility(visible)
  if visible == nil then
    visible = not self.visible
  end
  self.visible = visible
  if not self.overlay_low then
    return
  end
  if visible then
    self:render()
    if not self.paused then
      self:_start_time_observer()
    end
  else
    self:_stop_time_observer()
    self.overlay_low:remove()
    self.overlay_high:remove()
    if filter_state("danmaku") then
      mp.commandv("vf", "remove", "@danmaku")
    end
  end
end

function M:_ensure_vf_filter()
  if not self.style.vf_fps then return end
  local display_fps = mp.get_property_number("display-fps")
  local video_fps = mp.get_property_number("estimated-vf-fps")
  if (display_fps and display_fps < 58) or (video_fps and video_fps > 58) then return end
  if not filter_state("danmaku", "fps") then
    mp.commandv("vf", "append", string.format("@danmaku:fps=fps=%s", self.style.fps))
  end
end

local function binary_search(comments, target, getter, lo, hi)
  lo = lo or 1
  hi = hi or #comments
  while lo <= hi do
    local mid = math.floor((lo + hi) / 2)
    local val = getter(comments[mid])
    if val < target then
      lo = mid + 1
    else
      hi = mid - 1
    end
  end
  return lo
end

function M:render()
  if not self.comments or #self.comments == 0 then
    -- 如果弹幕被清空，隐式清空 OSD 渲染内容
    if self.overlay_low and self.overlay_low.data ~= "" then
      self.overlay_low.data = ""
      self.overlay_low:update()
    end
    if self.overlay_high and self.overlay_high.data ~= "" then
      self.overlay_high.data = ""
      self.overlay_high:update()
    end
    return
  end

  local pos, err = mp.get_property_number "time-pos"
  if err or not pos then
    return
  end

  local style = self.style
  local fontsize = style.fontsize
  local width, height = 1920, 1080
  local ratio = self.osd_width / self.osd_height

  if (width / height) < ratio then
    height = width / ratio
    fontsize = math.max(12, style.fontsize - (ratio * 2))
  end

  local displayarea = height * style.displayarea
  local ass_events_low = {}
  local ass_events_high = {}
  local alpha_hex = string.format("%02X", style.transparency)
  local bold_str = style.bold and "1" or "0"

  -- 统一的样式前缀
  local style_prefix = string.format(
    "{\\rDefault\\fn%s\\fs%d\\c&HFFFFFF&\\alpha&H%s\\bord%.1f\\shad%.1f\\b%s\\q2}",
    style.fontname, fontsize, alpha_hex, style.outline, style.shadow, bold_str
  )

  local window_start = pos - self._max_duration
  local search_lo = 1
  if pos >= self._last_pos and self._last_pos >= 0 then
    search_lo = self._last_index
  end

  local lo = binary_search(self.comments, window_start, function(item) return item.start_time end, search_lo,
    #self.comments)

  for i = lo, #self.comments do
    local event = self.comments[i]
    if not event then break end
    if event.start_time > pos then break end
    if pos >= event.start_time and pos <= event.end_time then
      local ass_text = nil

      if event.move then
        -- 移动弹幕 (R2L)
        local duration = event.end_time - event.start_time
        local progress = (pos - event.start_time) / duration

        local x1, y1, x2, y2 = event.move[1], event.move[2], event.move[3], event.move[4]
        local current_x = x1 + (x2 - x1) * progress
        local current_y = y1 + (y2 - y1) * progress

        if current_y <= displayarea then
          local alignment = (event.style == "SP" or event.style == "MSG") and "\\an7" or "\\an8"
          ass_text = string.format("%s{\\pos(%.1f,%.1f)%s}%s", style_prefix, current_x, current_y, alignment, event.text)
        end
      else
        -- 预设位置弹幕 (TOP / BOTTOM / POS)
        local current_y = event.pos and event.pos[2] or 0

        if current_y <= displayarea then
          local alignment = (event.style == "SP" or event.style == "MSG") and "\\an7" or "\\an8"
          if event.pos then
            ass_text = string.format("%s{\\pos(%.1f,%.1f)%s}%s", style_prefix, event.pos[1], event.pos[2], alignment,
              event.text)
          else
            ass_text = string.format("%s{%s}%s", style_prefix, alignment, event.text)
          end
        end
      end

      if ass_text then
        if event.layer == nil or tonumber(event.layer) == 0 then
          table.insert(ass_events_low, ass_text)
        else
          table.insert(ass_events_high, ass_text)
        end
      end
    end
  end

  self._last_pos = pos
  self._last_index = lo

  self.overlay_low.res_x = width
  self.overlay_low.res_y = height
  self.overlay_low.z = 0
  self.overlay_low.data = table.concat(ass_events_low, "\n")
  self.overlay_low:update()

  self.overlay_high.res_x = width
  self.overlay_high.res_y = height
  self.overlay_high.z = 1
  self.overlay_high.data = table.concat(ass_events_high, "\n")
  self.overlay_high:update()
end

function M:_start_time_observer()
  if not self._observer_active then
    self:_ensure_vf_filter()
    mp.observe_property("time-pos", "number", self._time_pos_callback)
    self._observer_active = true
  end
end

function M:_stop_time_observer()
  if self._observer_active then
    mp.unobserve_property(self._time_pos_callback)
    self._observer_active = false
  end
end

function M:setup(events, style)
  if events then
    self.comments = events
    self._max_duration = math.max(style.scrolltime, style.fixtime)
    self._last_pos = -1
    self._last_index = 1
  end
  if style then
    utils.table_merge(self.style, style)
  end

  if self._initialized then
    if self.visible then
      self:_start_time_observer()
    end
    return self
  end
  mp.observe_property("osd-width", "number", function(_, value)
    self.osd_width = value or self.osd_width
  end)
  mp.observe_property("osd-height", "number", function(_, value)
    self.osd_height = value or self.osd_height
  end)

  self._time_pos_callback = function(_, time_pos)
    if time_pos then
      self:render()
    else
      if self.overlay_low then self.overlay_low:remove() end
      if self.overlay_high then self.overlay_high:remove() end
    end
  end

  mp.observe_property("pause", "bool", function(_, pause)
    self.paused = pause
    if pause then
      self:_stop_time_observer()
    else
      if self.visible then self:_start_time_observer() end
    end
  end)

  self.overlay_low = mp.create_osd_overlay "ass-events"
  self.overlay_high = mp.create_osd_overlay "ass-events"

  mp.add_hook("on_unload", 50, function()
    self.comments = {}
    self:_stop_time_observer()
    self:render()
    if filter_state("danmaku") then
      mp.commandv("vf", "remove", "@danmaku")
    end
  end)

  self._initialized = true
  return self
end

return M
