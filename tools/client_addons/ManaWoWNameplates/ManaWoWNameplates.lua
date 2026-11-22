-- ManaWoW Nameplates: keep the nameplate CVars on for every session.
--
-- 3.3.5a defaults friendly nameplates to off, and the client can rewrite
-- WTF/Config.wtf on exit.  Setting the CVars here (once on login and again
-- after entering the world) means a clean install shows every NPC's name
-- without the player pressing V/Shift+V or editing any file.  Roles are not
-- drawn on the plate; they appear in the mouseover tooltip, like vanilla.
local frame = CreateFrame("Frame")

local SETTINGS = {
    nameplateShowFriends = "1",
    nameplateShowEnemies = "1",
    nameplateShowFriendlyPets = "1",
    nameplateShowFriendlyGuardians = "1",
    nameplateShowFriendlyTotems = "1",
    nameplateShowEnemyPets = "1",
    nameplateShowEnemyGuardians = "1",
    nameplateShowEnemyTotems = "1",
    nameplateAllowOverlap = "1",
}

local function ApplyNameplateSettings()
    for name, value in pairs(SETTINGS) do
        if GetCVar(name) ~= value then
            SetCVar(name, value)
        end
    end
end

frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("PLAYER_ENTERING_WORLD")
frame:SetScript("OnEvent", ApplyNameplateSettings)
