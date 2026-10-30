-- Initial placement must wait for actual colliders, even if the terrain is ready.
-- The caller owns the pause only if the player had not already paused the game.
local M = {}
function M.new(wasPaused) return { pausedByUs = not wasPaused, readyFrames = 0 } end
function M.step(h, ready, paused)
  if h.pausedByUs and not paused then return 'cancel' end -- manual resume wins
  h.readyFrames = ready and (h.readyFrames + 1) or 0
  if h.readyFrames >= 3 then return 'place' end
end
return M
