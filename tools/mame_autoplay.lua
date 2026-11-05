-- MAME autoboot script: let the attract mode run, insert a coin, start a game
-- and play crudely (walk forward, alternate punches and kicks, sometimes
-- turn around).  usage: mame bkungfulle -autoboot_script mame_autoplay.lua
local COIN_AT  = tonumber(os.getenv("BKF_COIN_AT")  or "1800")  -- frames
local QUIT_AT  = tonumber(os.getenv("BKF_QUIT_AT")  or "9000")
local fields = {}
for _, port in pairs(manager.machine.ioport.ports) do
  for name, field in pairs(port.fields) do fields[name] = field end
end
local function set(name, v)
  local f = fields[name]
  if f then f:set_value(v) end
end
local frame = 0
local function release_all()
  for _, n in ipairs({"P1 Left", "P1 Right", "P1 Up", "P1 Down",
                      "P1 Button 1", "P1 Button 2", "Coin 1", "1 Player Start"}) do
    set(n, 0)
  end
end
subscription = emu.add_machine_frame_notifier(function()
  frame = frame + 1
  release_all()
  if frame >= COIN_AT and frame < COIN_AT + 6 then set("Coin 1", 1) end
  if frame >= COIN_AT + 90 and frame < COIN_AT + 96 then set("1 Player Start", 1) end
  if frame > COIN_AT + 300 then
    local t = frame % 400
    set(t < 330 and "P1 Right" or "P1 Left", 1)        -- mostly forward
    local a = frame % 24
    if a < 4 then set("P1 Button 1", 1) end             -- punch
    if a >= 12 and a < 16 then set("P1 Button 2", 1) end -- kick
    if frame % 150 < 10 then set("P1 Down", 1) end      -- crouch now and then
  end
  if frame >= QUIT_AT then manager.machine:exit() end
end)
