"""Death knight rune state, costs and regeneration."""
from __future__ import annotations

from typing import Optional

from src.protocol.opcodes import Opcodes
from src.world import spells

class RunesMixin:
    def _is_death_knight(self) -> bool:
        return bool(self.character) and int(self.character.get("class", 0)) == 6

    def _init_runes(self) -> None:
        """``Player::InitRunes``: two blood, two unholy and two frost runes."""
        combat = self._get_combat_state()
        combat["runes"] = [
            {"base": int(rune_type), "current": int(rune_type),
             "cooldown": 0.0}
            for rune_type in spells.RUNE_SLOT_TYPES
        ]
        combat["last_rune_regen"] = 0.0
        combat["rune_prediction"] = None

    def _rune_state_mask(self) -> int:
        """``Player::GetRunesState``: one bit per rune that is off cooldown."""
        mask = 0
        for index, rune in enumerate(self._get_combat_state()["runes"]):
            if float(rune["cooldown"]) <= 0.0:
                mask |= 1 << index
        return mask

    def _rune_cost(self, template) -> tuple[int, int, int, int]:
        """``(blood, unholy, frost, runic_power)`` for the spell's RuneCostID."""
        return spells.get_rune_cost(self.config.database.world_path,
                                    getattr(template, "rune_cost_id", 0))

    def _pay_runes(self, template, take: bool) -> Optional[list[int]]:
        """``Spell::CheckOrTakeRunePower`` without the packet side effects.

        Returns the indices of the runes that were (or would be) spent, or
        ``None`` when the player cannot afford the cost.  A death rune can pay
        for any basic rune and turns back into its base type when spent.
        """
        combat = self._get_combat_state()
        runes = combat["runes"]
        if not runes:
            return None
        blood, unholy, frost, _runic_power = self._rune_cost(template)
        remaining = [blood, unholy, frost, 0]      # death is aggregated later
        spent: list[int] = []

        # Scan the basic runes in slot order (death runes are not explicit).
        for index, rune in enumerate(runes):
            current = int(rune["current"])
            if remaining[current] <= 0:
                continue
            if float(rune["cooldown"]) > 0.0:
                continue
            if take:
                rune["cooldown"] = float(spells.RUNE_COOLDOWN)
            remaining[current] -= 1
            spent.append(index)

        remaining[spells.RUNE_DEATH] = sum(remaining[:spells.RUNE_DEATH])

        # Death runes whose base type matches an unpaid cost.
        if remaining[spells.RUNE_DEATH] > 0:
            for index, rune in enumerate(runes):
                if remaining[spells.RUNE_DEATH] <= 0:
                    break
                if int(rune["current"]) != spells.RUNE_DEATH:
                    continue
                if float(rune["cooldown"]) > 0.0:
                    continue
                base = int(rune["base"])
                if remaining[base] <= 0:
                    continue
                if take:
                    rune["cooldown"] = float(spells.RUNE_COOLDOWN)
                    rune["current"] = base
                remaining[base] -= 1
                remaining[spells.RUNE_DEATH] -= 1
                spent.append(index)

        # Any remaining death runes can cover whatever is left.
        if remaining[spells.RUNE_DEATH] > 0:
            for index, rune in enumerate(runes):
                if remaining[spells.RUNE_DEATH] <= 0:
                    break
                if int(rune["current"]) != spells.RUNE_DEATH:
                    continue
                if float(rune["cooldown"]) > 0.0:
                    continue
                if take:
                    rune["cooldown"] = float(spells.RUNE_COOLDOWN)
                    rune["current"] = int(rune["base"])
                remaining[spells.RUNE_DEATH] -= 1
                spent.append(index)

        if remaining[spells.RUNE_DEATH] > 0:
            return None
        return spent

    def _can_afford_runes(self, template) -> bool:
        return self._pay_runes(template, take=False) is not None

    async def _take_runes(self, template) -> bool:
        """Spend runes and grant the spell's runic power income."""
        before = self._rune_state_mask()
        spent = self._pay_runes(template, take=True)
        if spent is None:
            return False
        after = self._rune_state_mask()
        runic_power_gain = self._rune_cost(template)[3]
        if runic_power_gain:
            power = int(self.character.get("power", self._max_power()))
            await self._set_player_power(
                min(self._max_power(), power + int(runic_power_gain))
            )
        # ``Spell::SendSpellGo`` predicts the rune cooldowns; the progress byte
        # is 0 for a rune that was just spent.
        progress = []
        for index in range(len(self._get_combat_state()["runes"])):
            bit = 1 << index
            if before & bit and not after & bit:
                progress.append(0)
        self._get_combat_state()["rune_prediction"] = {
            "before": before,
            "after": after,
            "progress": progress,
        }
        return True

    async def _send_resync_runes(self) -> None:
        """Send the authoritative rune types and cooldowns."""
        combat = self._get_combat_state()
        if not combat["runes"]:
            return
        runes = [
            (int(rune["current"]), int(round(float(rune["cooldown"]))))
            for rune in combat["runes"]
        ]
        await self.send_packet(Opcodes.SMSG_RESYNC_RUNES,
                               spells.build_resync_runes(runes))

    async def _regenerate_runes(self, now: float) -> None:
        """``Player::Regenerate(POWER_RUNE)``: one rune every ten seconds."""
        combat = self._get_combat_state()
        runes = combat["runes"]
        if not runes:
            return
        last = float(combat.get("last_rune_regen") or 0.0)
        if last <= 0.0:
            combat["last_rune_regen"] = now
            return
        elapsed_ms = max(0.0, (now - last) * 1000.0)
        combat["last_rune_regen"] = now
        if elapsed_ms <= 0.0:
            return
        for index, rune in enumerate(runes):
            cooldown = float(rune["cooldown"])
            if cooldown <= 0.0:
                continue
            # ``PLAYER_RUNE_REGEN_1 + type`` defaults to 0.1, i.e. the stored
            # cooldown drops by ``elapsed * 10`` percent per second.
            cooldown -= elapsed_ms * spells.RUNE_REGEN_RATE * 10.0
            if cooldown <= 0.0:
                cooldown = 0.0
                await self.send_packet(Opcodes.SMSG_ADD_RUNE_POWER,
                                       spells.build_add_rune_power(index))
            rune["cooldown"] = cooldown

    def _note_rune_prediction(self, template) -> None:
        """Mark a DK ``RuneCostID`` cast for ``CAST_FLAG_PREDICTED_RUNES``.

        ``Spell::SendSpellGo`` sets the flag for every death knight spell with a
        RuneCostID, including runic-power spells such as Death Coil that do not
        change the rune masks (before == after, no progress bytes).
        """
        if (not self._is_death_knight()
                or not int(getattr(template, "rune_cost_id", 0))):
            return
        combat = self._get_combat_state()
        if combat.get("rune_prediction") is not None:
            return
        mask = self._rune_state_mask()
        combat["rune_prediction"] = {
            "before": mask, "after": mask, "progress": [],
        }
