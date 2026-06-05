local utils = require "lib.utils"
local M = {
  INTERVAL = 0.01, -- 默认调整为约 60fps 渲染频率，避免跑满单核
  visible = true,
  paused = false,
  osd_width = 0,
  osd_height = 0,
  _initialized = false,
  timer = nil,
  comments = {}, -- 存储传入的 events 数组
  style = {
    fontname = "sans-serif",
    fontsize = 36,
    shadow = 1,
    bold = true,
    displayarea = 0.5,
    outline = 1.0,
    transparency = 48, -- 对应 JSON 中的 10 进制整型
  },
}

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
  else
    self.timer:kill()
    self.overlay.data = ""
    self.overlay:remove()
  end
end

function M:render()
  if not self.comments or #self.comments == 0 then
    -- 如果弹幕被清空，隐式清空 OSD 渲染内容
    if self.overlay and self.overlay.data ~= "" then
      self.overlay.data = ""
      self.overlay:update()
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
  local ass_events = {}
  local alpha_hex = string.format("%02X", style.transparency)
  local bold_str = style.bold and "1" or "0"

  -- 统一的样式前缀
  local style_prefix = string.format(
    "{\\rDefault\\fn%s\\fs%d\\c&HFFFFFF&\\alpha&H%s\\bord%.1f\\shad%.1f\\b%s\\q2}",
    style.fontname, fontsize, alpha_hex, style.outline, style.shadow, bold_str
  )

  for _, event in ipairs(self.comments) do
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
        table.insert(ass_events, ass_text)
      end
    end
  end

  self.overlay.res_x = width
  self.overlay.res_y = height
  self.overlay.data = table.concat(ass_events, "\n")
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

function M:setup2(events, style)
  mp.msg.info("just test")
end

function M:setup(events, style)
  if events then
    self.comments = events
  end
  if style then
    utils.table_merge(self.style, style)
  end

  if self._initialized then
    if self.visible and not self.paused then
      self:render()
    end
    return self
  end

  mp.observe_property("osd-width", "number", function(_, value)
    self.osd_width = value or self.osd_width
  end)
  mp.observe_property("osd-height", "number", function(_, value)
    self.osd_height = value or self.osd_height
  end)

  mp.observe_property("display-fps", "number", function(_, value)
    if not value or value <= 0 then return end
    local interval = 1 / value
    if interval < 0.005 then interval = 0.005 end
    if math.abs(self.INTERVAL - interval) > 0.002 then
      self.INTERVAL = interval
      if self.timer and not self.paused and self.visible then
        self:restart_timer()
      end
    end
  end)

  mp.observe_property("pause", "bool", function(_, pause)
    self.paused = pause
    if not self.timer then return end
    if pause then
      self.timer:kill()
    else
      if self.visible then self.timer:resume() end
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
