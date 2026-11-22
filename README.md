# ManaWoW (Experimental)

ManaWoW is a minimal, asyncio-based experimental Python private server for
**World of Warcraft 3.3.5a (build 12340)**.

> **Disclaimer:** This project is for educational and reverse-engineering research purposes only. Running private servers may violate Blizzard's Terms of Service depending on your jurisdiction. Use at your own risk.

## What works

A real 3.3.5a client can now log in, pick a character and **enter the world**:

- Authserver (realmd) on port `3724`
  - `AUTH_LOGON_CHALLENGE` / `AUTH_LOGON_PROOF` with full SRP6
  - correct 40-byte session-key derivation and persistence
  - 3.3.5a realm-list response
- Worldserver on port `8085`
  - `SMSG_AUTH_CHALLENGE` (4-byte server challenge + 32-byte DOS challenge)
  - `CMSG_AUTH_SESSION` parsing and digest validation
  - HMAC-SHA1 + RC4-drop1024 encrypted packet headers
  - `SMSG_AUTH_RESPONSE`, addon info, client-cache version, tutorial flags
  - `SMSG_CHAR_ENUM`, `CMSG_CHAR_CREATE`, `CMSG_CHAR_DELETE`
  - `CMSG_PLAYER_LOGIN` world-entry burst: `SMSG_LOGIN_VERIFY_WORLD`,
    account data times, feature status, MOTD, bind point, instance difficulty,
    initial spells/action buttons/factions, world states, time speed, the
    player's own create-object (`SMSG_COMPRESSED_UPDATE_OBJECT`) and time sync
  - login queries answered while in world: name query (including other
    accounts' characters), server time, played time, item query (unknown
    items) and calendar pending count
  - cross-account visibility: players entering the world receive create
    blocks for everyone already on the same map, existing clients are told
    about the newcomer, `MSG_MOVE_*` packets are relayed to other players,
    and `SMSG_DESTROY_OBJECT` is sent on logout or disconnect
  - `CMSG_LOGOUT_REQUEST` / `CMSG_LOGOUT_CANCEL` back to character selection
  - `CMSG_PING` / `SMSG_PONG`, realm split and keep-alive handling
- SQLite storage for accounts, realms and characters
- **Item system (initial milestone):**
  - `SMSG_ITEM_QUERY_SINGLE_RESPONSE` from `item_templates` SQLite table
  - Character inventory in `character_items` table (slot -> item instance)
  - Starter kit: the exact `CharStartOutfit.dbc` outfit for the character's
    race/class (63 rows for the 62 legal 3.3.5a combinations, including the
    death-knight set and its four bags), with every referenced template seeded
    from the client's own `Item.dbc` data.  Race/class legality comes from
    `CharBaseInfo.dbc`, so `CMSG_CHAR_CREATE` rejects impossible combinations
    such as gnome paladin or tauren mage with `CHAR_CREATE_FAILED`
  - On world entry, items are emitted as `UPDATETYPE_CREATE_OBJECT2` blocks
    *before* the player block so the `PLAYER_FIELD_INV_SLOT_HEAD` / `PACK_SLOT_1`
    guids resolve immediately
  - `PLAYER_VISIBLE_ITEM_*_ENTRYID` pairs (19 slots) so other players see
    equipped gear correctly.  A 3.3.5a client does not draw another player's
    armour from those fields alone: its `CGUnit_C::InitializeComponent` can
    abort before `RefreshVisibleItems()`, which leaves only the hand items (so
    peers saw the sword but no armour).  Peer create blocks therefore also set
    `UNIT_FLAG2_MIRROR_IMAGE` (0x10); the client answers with
    `CMSG_GET_MIRRORIMAGE_DATA` and the server replies with
    `SMSG_MIRRORIMAGE_DATA` (display id, race/sex/class, skin/face/hair bytes,
    guild id, 11 armour display ids), whose handler allocates the character
    component and adds all armour slots.  Weapons still come from the visible
    item fields through `AddHandItem`.
  - `CMSG_SWAP_INV_ITEM` (equip slot <-> equip slot or backpack) persisted and
    followed by a player `UPDATETYPE_VALUES` update sent to the owner **and to
    every peer**, so the client redraws the model and the bag slots on all
    clients that can see the character
  - `CMSG_AUTOEQUIP_ITEM` (right-click to equip): the item's `Item.dbc`
    inventory type selects the destination slot, then the normal swap path runs
  - `CMSG_DESTROYITEM` (delete from equipment or backpack) persisted, with the
    slot cleared on the owner and its peers
  - `CMSG_SWAP_ITEM` accepted for the player container (bags 255/0)
  - Unsupported moves are answered with a well-formed
    `SMSG_INVENTORY_CHANGE_FAILURE`
  - Weapon templates carry the `Item.dbc` sheath type (`sheath_type` column,
    hip/back/shield). The client starts sheathed and resolves the attachment
    through it; a weapon with sheath type 0 is never attached to the model
  - `SMSG_CLIENTCACHE_VERSION` is a CRC32 of `item_templates`. The client puts
    item stats in `Cache/WDB/<locale>/itemcache.wdb` and only reloads them when
    this version changes (`DBCache<T>::VerifyAndUpdateVersion`); sending a
    constant makes edited item data (like a weapon's sheath type) stay stale
    on disk forever
- **Static creatures + gossip (full 3.3.5a world data):**
  - `creature_templates` and `creature_spawns` SQLite tables plus
    `gossip_menus`, `gossip_options` and `npc_text`.  `tools/import_wotlk_db.py`
    reads the canonical CMaNGOS `WoTLKDB` dump and fills them with the complete
    world creature data: 29,919 templates, 98,790 spawns, 4,331 gossip menus,
    3,867 options and 5,620 NPC texts.  The import is idempotent and only
    touches the NPC tables, never accounts or characters.  Spawns are filtered
    to the normal spawn mask, phase 1 and an existing template.
  - A fresh database still seeds the eleven-NPC Northshire demo population
    (Marshal McBride, Deputy Willem, Innkeeper Farley, Michelle Belle and six
    critters/beasts) using display ids that exist in the client's
    `CreatureDisplayInfo.dbc`; the seed is skipped once real spawns exist.
  - New characters start on the real 3.3.5a `playercreateinfo` position for
    their race and class (Elwynn, Durotar, Coldridge, Teldrassil, Tirisfal,
    Mulgore, Eversong, Azuremyst) instead of always Northshire; death knights
    use the Ebon Hold start.  The CMaNGOS `creature` table is nevertheless
    script-driven inside the Ebon Hold, so only a handful of static spawns
    exist on map 609.
  - Creatures are sent as `TYPEID_UNIT` create blocks in the same
    `SMSG_UPDATE_OBJECT` as the player, with
    `UPDATEFLAG_LIVING | UPDATEFLAG_HAS_POSITION` (0x60), movement info, nine
    speeds and a `UNIT_END` (148-field) update mask.  Creature guids carry the
    `HIGHGUID_UNIT` word (0xF130) in the top 16 bits and the template entry in
    bits 24-47, so they live in their own guid range, can never collide with a
    player, and the client can resolve the creature's entry (and name) from the
    guid alone.  Idle creatures wander around their spawn point or follow a
    waypoint path; the combat AI is described under "Combat + spells" below
  - `CMSG_CREATURE_QUERY` -> `SMSG_CREATURE_QUERY_RESPONSE` with name, title,
    type/family/classification, four display ids and the other fields the
    client's `DBCache` expects.  `CMSG_NAME_QUERY` also answers creature guids,
    so nameplates resolve even before the creature is targeted
  - NPC names and roles render the vanilla way: the nameplate shows the plain
    cached name (`Janos Hammerknuckle`) and the mouseover tooltip adds the
    template's `subname` as its own `<Role>` line (`<Weaponsmith>`).  The
    server therefore sends the plain `name` plus the `subname` in the separate
    `title` field, which is exactly what the stock 3.3.5a client expects.
    The tooltip works even when the client's nameplate option is off, so the
    name and role are available without enabling nameplates
  - `CMSG_GOSSIP_HELLO` opens `SMSG_GOSSIP_MESSAGE` (menu id, NPC-text id and
    options from `gossip_menus`/`gossip_options`), `CMSG_GOSSIP_SELECT_OPTION`
    switches menus or replaces the displayed text, and an option with no
    action sends `SMSG_GOSSIP_COMPLETE`
  - `CMSG_NPC_TEXT_QUERY` -> `SMSG_NPC_TEXT_UPDATE`, with the seeded text
    expanded to the eight option records the client always reads
  - `UNIT_NPC_FLAGS` (index 82) and `UNIT_NPC_EMOTESTATE` (index 83) are now
    correct 3.3.5a absolute indices; NPCs with gossip flag 1 are clickable
  - The world database also ships the content Blizzard's own tools need:
    invisible stalkers, mining/fire "bunny" helpers, quest-effect triggers,
    camera shakers, target dummies and the `[DND] TAR Pedestal` props.  Those are
    real `creature` rows but not creatures a player is meant to see.  Rendering
    them is exactly what looked like "invisible NPCs" (they use
    `Creature\InvisibleStalker\InvisibleStalker.mdx`) and "weird structures" (the
    pedestals resolve to
    `World\AZEROTH\KARAZAHN\PASSIVEDOODADS\Pedestals\KarazahnPedestals02.mdx`, a
    Karazhan doodad, and 29 of them stood inside the human start).
    `creature_templates.visible` is 0 for them and both spawn queries skip those
    rows: 1,755 templates / 4,273 spawn points, and none of the ones that are
    actually placed is a vendor, trainer or quest giver.  `^old\b` is
    deliberately *not* in the rule - it would delete real quest-givers such as
    Old Man Heming and Old Orok.  Verified against the client's own
    `CreatureDisplayInfo.dbc` -> `CreatureModelData.dbc` chain, every unit now
    sent at every starting zone resolves to a real `Creature\`/`Character\` model
  - The full spawn table is far too large to send at login, so each session
    keeps only a 150-yard neighbourhood.  The scan uses the
    `(map, x, y)` index and is repeated after the player has moved 25 yards;
    new spawns arrive as `SMSG_UPDATE_OBJECT` create blocks and spawns left
    behind are removed with `SMSG_DESTROY_OBJECT`
  - Spawn orientation `o` follows the 3.3.5a convention
    `atan2(target_y - y, target_x - x)` normalised to `[0, 2π)` (`0` = north,
    `π/2` = west, `π` = south).  Imported spawns keep the CMaNGOS heading;
    the demo NPCs face the human start point so they greet the player

The create-object values are taken from the client's own DBC data
(`ChrRaces.dbc`/`FactionTemplate.dbc`/`CreatureDisplayInfo.dbc`). The 3.3.5a
client dereferences the race's faction-template and display rows while building
the player, so a wrong id (for example `160`/`162` for Blood Elf/Draenei, or the
old `61`/`63` Gnome/Troll display ids) makes it crash with `ERROR #132` right
after the loading screen. The current mapping is
Human/Orc/Dwarf/Night Elf/Undead/Tauren/Gnome/Troll/Blood Elf/Draenei =
`1/2/3/4/5/6/115/116/1610/1629`.

The world is still minimal, but it is playable: the client can walk around from
any race's start zone, see the imported NPCs and creatures, watch other
accounts' characters move, see equipped items appear on the character and in
the bag slots, open the gossip menus the world database defines, and fight and
loot PvE creatures.  Questing and the vendor/trainer economy are still missing,
so gossip options that would open a vendor/trainer/quest window do nothing.
Movement is client-authoritative: `MSG_MOVE_*` packets are accepted, the newest
position is saved to SQLite, and the same packet is relayed to every other
in-world session on the same map.

- **Combat + spells (real 3.3.5a layouts):**
  - `character_spells` stores the spells a character knows; each class gets its
    3.3.5a starter kit on creation (Auto Attack, Heroic Strike, languages, ...)
  - `SMSG_LOGIN_VERIFY_WORLD` is the first world packet, followed by
    `SMSG_INITIAL_SPELLS` with `InitialLogin = 1` and `SMSG_ACTION_BUTTONS`
    (reason 1, 144 packed buttons).  The client only rebuilds the spellbook on
    `InitialLogin = 1`, and only accepts action buttons for spells it already
    knows, so the order matters.  Passive/hidden spells stay in the spellbook
    but are not put on the bar; Attack (6603) is always button 0
  - `CMSG_CAST_SPELL` / `CMSG_CANCEL_CAST` use the imported `spell_templates`:
    cast time, range, power cost, GCD (`StartRecoveryTime`), school, damage /
    heal rolls and the real effect/aura enums
  - melee auto-attack, weapon damage/delay, creature aggro + chase + leash AI,
    creature melee, death, respawn, XP and level-up
  - `SMSG_SPELL_START` / `SMSG_SPELL_GO` / `SMSG_CAST_FAILED`,
    `SMSG_ATTACKERSTATEUPDATE` (miss/crit flags), `SMSG_SPELLHEALLOG`,
    `SMSG_SPELLENERGIZELOG`, `SMSG_LOG_XPGAIN` and `SMSG_LEVELUP_INFO`
  - `SMSG_SPELL_GO` carries the 3.3.5 cast flags (`CAST_FLAG_NO_GCD` for
    instant spells, `CAST_FLAG_PREDICTED_POWER` with the remaining
    mana/rage), the hit/miss target lists and the server tick; the client
    needs all of them to accept the cast.  The hit and miss lists use full
    `uint64` guids (`WriteSpellGoTargets` writes `ObjectGuid`, not the packed
    form); writing packed guids shifts the target mask by two bytes per entry,
    and the client then misreads bit `0x80000` as an element count and
    `alloca`s a guid fragment, crashing with a stack overflow
  - rage is stored in tenths (a full warrior bar is `UNIT_FIELD_MAXPOWER1`
    1000) and generated with the real 3.3.5 formula (damage /
    `CalculateRageConversion()` plus the truncated weapon-speed factor,
    doubled on crits), so spell costs like Heroic Strike's 150 (15 rage)
    compare against the same number the client checks and the button stays
    usable.  Normal-school melee damage also grants the victim rage
    (`Unit::DealDamage`); spell and DoT damage does not.  Out of combat rage
    decays 25 points every two seconds, as in `Player::Regenerate`
  - spell power costs follow `Spell::CalculatePowerCost`: flat `ManaCost`
    plus `ManaCostPerlevel * (rank - baseLevel)`, percentage costs added on
    top, and `SPELL_ATTR_EX_USE_ALL_MANA` (Lay on Hands) draining the whole
    pool; rage costs are already in tenths in `Spell.dbc`
  - energy regenerates 10 per second (`(diff / 100) * rate`) for rogues, and
    mana uses the client's `GtRegenMPPerSpt.dbc` ratio:
    `sqrt(Intellect) * Spirit * ratio[level]` per second, published in
    `UNIT_FIELD_POWER_REGEN_FLAT_MODIFIER` with a zero interrupted rate and
    suppressed for five seconds after a mana spend (the 5-second rule);
    `SPELL_ATTR_EX2_DONT_BLOCK_MANA_REGEN` spells leave the timer alone
  - rogue combo points are per-target state pushed with
    `SMSG_UPDATE_COMBO_POINTS` (packed target guid + `uint8` points, max 5):
    builders such as Sinister Strike add their rolled effect-80 value,
    finishing moves (the `SPELL_ATTR_EX_FINISHING_MOVE_*` bits) scale by
    `EffectPointsPerComboPoint` and consume the points after their effects,
    and the counter is cleared on target death, player death or a new target;
    a finisher without points is refused with `SPELL_FAILED_NO_COMBO_POINTS`
    (78, or `SPELL_FAILED_CASTER_AURASTATE` for warriors)
  - starting attributes come from the imported CMaNGOS `player_levelstats`
    rows (all 62 legal race/class pairs at every level) and the pools follow
    `Unit::UpdateMaxHealth`/`UpdateMaxPower`: `basehp + health-from-stamina`
    (20 stamina worth 1 health each, everything above 20 worth 10) plus flat
    item health, then the Tauren Endurance 5% racial; mana is
    `basemana + mana-from-intellect` (20 intellect worth 1 mana each, above 20
    worth 15).  Death knights start at level 55 like the real client
  - equipped items (slots 0..18 only; bags and backpack are excluded) add
    their primary stats, flat health/mana, attack power and resistances,
    mirroring `Player::_ApplyItemMods`.  Armor is item armor plus twice the
    final agility (`Player::UpdateArmor`); melee attack power uses the
    `Player::UpdateAttackPowerAndDamage` class formula (warrior/paladin/DK/
    druid `level*3 + str*2 - 20`, rogue/hunter/shaman
    `level*2 + str + agi - 20`, mage/priest/warlock `str - 10`) plus flat item
    AP, with the separate ranged formula for `UNIT_FIELD_RANGED_ATTACK_POWER`.
    Equipping, unequipping and destroying gear recompute all of these and
    broadcast the new values (attributes, health/mana bars, armor, AP) in the
    same `UPDATETYPE_VALUES` update as the visible items
  - creature melee is mitigated by the player's armor with
    `Unit::CalcArmorReducedDamage` (0.1 * armor / (8.5 * levelMod + 40),
    `levelMod` growing past level 59, capped at 75% and never below 1 damage)
  - creatures turn towards their target in melee range via a zero-length
    `SMSG_MONSTER_MOVE` spline with face mode 4 (`MonsterMoveFacingAngle`
    followed by the float angle); the spline start position is a plain
    `Vector3` with no orientation, matching
    `Movement::PacketBuilder::WriteCommonMonsterMovePart`
  - death knight runes are real state, not just a power-type constant:
    `Player::InitRunes` order (blood, blood, unholy, unholy, frost, frost), a
    10 s cooldown per spent rune regenerated with `PLAYER_RUNE_REGEN_1 = 0.1`,
    death runes that pay for their base type and revert on spend, and the
    `SMSG_RESYNC_RUNES` / `SMSG_ADD_RUNE_POWER` packets the client needs to
    draw the rune bar.  Costs come from the imported `SpellRuneCost.dbc`
    (`spell_rune_cost`, 474 rows), and `Spell::CheckOrTakeRunePower` semantics
    decide both the `SPELL_FAILED_NO_POWER` refusal and the runic-power gain;
    only `POWER_RUNE` spells spend slots, so Death Coil (runic power, also
    carrying a `RuneCostID`) leaves the six runes untouched but still sends
    `CAST_FLAG_PREDICTED_RUNES` with identical before/after masks.  Runic power
    decays 2.5 per two seconds out of combat (`Player::Regenerate`)
  - creatures use their database spell lists in combat, following
    `UnitAI::UpdateSpellLists` / `Creature::GetSpellCooldown`: a 1200 ms list
    tick, `Availability` rolled once when the list is assigned, `Probability`
    as a selection weight, `InitialMin/Max` and `RepeatMin/Max` in
    milliseconds, the header's `ChanceSupportAction`/`ChanceRangedAttack` gates
    (ranged chance is 50 lower in melee), the category-cooldown flag and the
    `SPELL_ATTR_EX_NO_AUTOCAST_AI` exclusion.  The rare non-blocking flag is
    treated as a normal entry because a creature here can only cast one spell at
    a time (only Naxxramas Noth's Blink uses it).  Target ids below
    100 use the hardcoded rules (current victim, self, friendly dispel/missing
    buff, current-not-alone) and ids 100+ resolve through
    `creature_spell_targeting`.  Creatures with `SpellList = 0` fall back to the
    legacy `creature_template_spells` ten-slot set plus `creature_cooldowns`,
    inferring self-targets from the spell's range/effect targets.  Mana comes
    from `creature_template_classlevelstats.base_mana` scaled by
    `energy_multiplier`; casting stops movement and melee, spends the cost when
    the cast finishes, and applies damage, heals, weapon damage, triggered
    spells and periodic auras (whose ticks are attributed to the casting
    creature)
  - idle creatures move like `WanderMovementGenerator` / `WaypointMovementGenerator`
    (CMaNGOS 3.3.5): a random-wander creature walks to a point inside its
    `creature.spawndist` radius around the respawn coordinate, pauses 3-10 s
    after a group of up to three steps, and never leaves the radius.  NPCs with
    `npc_flags`, `UNIT_FLAG_DISABLE_MOVE` units, dead spawns and creatures with
    `MovementType = 0` stay put.  A per-spawn `creature_movement` path or a
    shared `creature_movement_template` path (`MovementTemplateId`) is followed
    node by node at walk speed, honouring each node's `WaitTime` and looping.
    Every step is a straight-line `SMSG_MONSTER_MOVE` (this server has no
    terrain/pathfinding data), and the server tracks the destination so chase,
    melee range and facing use the creature's real position.  Databases imported
    before these columns existed fall back to a heuristic (wild creatures wander
    a default 5 yards, NPCs are idle); a fresh `import_wotlk_db.py` run imports
    `creature.MovementType`/`spawndist` and both waypoint tables
- **Loot:**
  - `creature_loot_template` (218,066 rows) and `reference_loot_template`
    (44,244 rows / 896 pools) are imported from CMaNGOS.  Reference pools are
    resolved recursively with TrinityCore's group semantics (one single roll,
    subtract each explicit chance, then a random equal-chanced entry)
  - loot is rolled exactly once, when the creature dies, and stored in
    `creature_spawns.loot_json` as `{"items": [[entry,count],...], "money": n}`.
    Every take rewrites the remaining loot, so closing and reopening the corpse
    shows only what is left and a fully looted corpse stays empty.  There is no
    fallback re-roll
  - `creature_template.LootId` is respected (190 creatures share another
    creature's pool); entries without an `item_templates` row are filtered out
    so the window never shows an unnamed item
  - `CMSG_LOOT`, `CMSG_AUTOSTORE_LOOT_ITEM` (fills partial stacks first, then
    free backpack slots), `CMSG_LOOT_MONEY`, `CMSG_LOOT_RELEASE`, with
    `SMSG_LOOT_RESPONSE`, `SMSG_LOOT_MONEY_NOTIFY`, `SMSG_LOOT_REMOVED` and
    `SMSG_ITEM_PUSH_RESULT`
  - `CMSG_DESTROYITEM`: `Count == 0` destroys the whole stack (TrinityCore
    behaviour); partial destroys update `ITEM_FIELD_STACK_COUNT`, full destroys
    send `SMSG_DESTROY_OBJECT` and refresh equipment/bag fields for owner and
    peers

- **Chat + emotes:**
  - `CMSG_MESSAGECHAT` / `SMSG_MESSAGECHAT`: `/say`, `/yell`, `/whisper` and
    `/me` (emote) relayed across accounts on the same map.  Whisper lookups
    use the character database by name; missing targets return the correct
    "player not found" system message.  The wire format matches the client's
    `ChatFrame.cpp` default handler exactly (`uint8 type, uint32 language,
    uint64 sender, uint32 sender_unk, uint64 target, uint32 length,
    cstring message, uint8 chat_tag`; the length includes the trailing NUL and
    there is no target-unk field).
  - `CMSG_TEXT_EMOTE` / `SMSG_TEXT_EMOTE`: text emotes like `/wave`, `/dance`,
    `/bow` etc. broadcast to peers so other players see the animation.
  - `CMSG_EMOTE` / `SMSG_EMOTE`: animation-only emotes (no text).
  - `CMSG_SET_SHEATHED`: weapon draw/sheath state (byte 0 of
    `UNIT_FIELD_BYTES_2`) persisted and relayed so peers see weapons drawn.

Two accounts are enough to see the relay in the real client:

```bash
python tools/create_test_account.py TEST TEST
python tools/create_test_account.py TEST2 TEST
```

Log in with `TEST`, enter the world, then start a second client with `TEST2`
(or a scripted session). Each character gets a create block when entering, and
the other client sees it appear, walk and disappear. The create block for a
*non-self* player deliberately omits `UPDATEFLAG_SELF` (0x1) and
`UPDATEFLAG_HIGHGUID`/the 0x2F word: with `SELF` set, the client would replace
its active player with the other character.

In-world keyboard input depends on one easily missed packet detail:
`SMSG_ACCOUNT_DATA_TIMES` must announce every account-data type (mask `0xFF`).
The client marks the bindings cache as "downloading" when it enters the world and
only finishes `FinishLoadBindings()` once the matching record clears that flag.
With an empty mask the *current* binding set stays empty, so movement, `ESC`,
`C`, `M` and every other key silently do nothing even though the key events
themselves arrive. The server also answers `CMSG_REQUEST_ACCOUNT_DATA` with an
empty blob and acknowledges `CMSG_UPDATE_ACCOUNT_DATA`.

## Requirements

- Python 3.11+
- `pyyaml`

```bash
pip install -r requirements.txt
```

The SRP6, HMAC and RC4 implementations use only the Python standard library.

## Quick start

```bash
# 1. Create/upgrade data/auth.db and data/world.db
python tools/init_db.py

# 2. (optional) Load the full CMaNGOS 3.3.5a creature/spawn/gossip data.
#    Stop the worldserver first; the import replaces the demo NPC population.
python tools/import_wotlk_db.py --dump C:\path\to\WoTLKDB.sql

# 3. Create an account (username TEST, password TEST)
python tools/create_test_account.py TEST TEST

# 4. Start the servers. Either one combined process/terminal:
python run_servers.py
# ...or two separate terminals:
python run_auth.py
python run_world.py
```

The world dump can be downloaded from the
[`cmangos/wotlk-db`](https://github.com/cmangos/wotlk-db) repository
(`Full_DB/WoTLKDB_*.sql`).  The importer is dependency-free and prints how many
rows it loaded plus the number of visible spawns at every race's start point.
`data/world.db` is already imported in this checkout, so the optional step is
only needed to refresh it.

If a server exits with `Port 3724 is already in use` (or `8085`), an older
instance is still running. Stop it instead of starting a second copy:

```bash
python tools/stop_servers.py          # only stops this project's run_*.py processes
python tools/stop_servers.py --force  # kill whatever owns the port
```

`config/config.yaml` is optional. If it is missing, both run scripts fall back to
`config/config.example.yaml`. Copy it to `config/config.yaml` if you want to edit
the realm name, ports, MOTD, etc.

Point the client at the authserver with a `realmlist.wtf` containing:

```
set realmlist 127.0.0.1
```

Then log in as `TEST` / `TEST`. If the client is on another machine, set
`authserver.realm_address` to the server's LAN IP (the address advertised in the
realm list) and make sure ports `3724` and `8085` are reachable.

### Client settings (required on a clean install)

Run this once for every client folder (or after deleting `WTF/`):

```bash
python tools/apply_client_settings.py "C:\path\to\client"
python tools/apply_client_settings.py --search   # patch every client under Desktop/Documents
```

It writes `realmlist.wtf` and the nameplate CVars into `WTF/Config.wtf`.  A
stock 3.3.5a install has **friendly nameplates off**, so no name is drawn over
a quest giver, trainer or vendor until the unit is clicked — even though the
server answered every creature query and the client cached the name in
`Cache/WDB/enUS/creaturecache.wdb`.  The server cannot change client CVars, so
this one-time client-side step is what makes NPC names appear on their own:

```
SET nameplateShowFriends "1"
SET nameplateShowEnemies "1"
```

In game, `V` toggles enemy nameplates and `Shift+V` toggles friendly ones.

NPC job titles need no addon either.  Stock 3.3.5a nameplates only draw the
unit name, so the server folds the template's `subname` into the name it sends
(`Janos Hammerknuckle <Weaponsmith>`) and leaves the separate title field empty
so the tooltip does not print the title twice.

## Verifying the protocol without a game client

`tools/protocol_selftest.py` starts both servers in-process against temporary
databases and simulates full client sessions, including the encrypted world
handshake, character create/enum/delete, entering the world, creature
query/gossip/NPC-text round-trips, per-race starting positions, the 150-yard
creature visibility query, logging out, and two accounts seeing each other
spawn/move/despawn:

```bash
python tools/protocol_selftest.py
```

Expected final line:

```
[5/5] PASS - auth -> realm list -> world auth -> character select -> world entry -> movement -> cross-account relay -> logout works
```

## Layout

```
wow335a-pyserver/
├── config/        # YAML config
├── data/          # SQLite databases
├── info/          # protocol notes/opcode dumps
├── logs/          # runtime logs
├── run_auth.py
├── run_world.py
├── run_servers.py
├── tools/
│   ├── init_db.py
│   ├── import_wotlk_db.py   # CMaNGOS world dump -> NPC tables
│   ├── wotlk_dump.py        # dependency-free MySQL dump parser
│   ├── create_test_account.py
│   ├── apply_client_settings.py  # realmlist + nameplate CVars for a client
│   ├── protocol_selftest.py
│   └── stop_servers.py
└── src/
    ├── auth/      # authserver + realm list
    ├── common/    # config, logging, utils
    ├── crypto/    # SRP6 + world header RC4 crypt
    ├── network/   # packet headers/logging
    ├── protocol/  # 3.3.5a opcodes
    └── world/     # worldserver, sockets, character storage
```

## Protocol notes

Useful details are documented in the code:

- Client headers are 6 bytes: `uint16 size` (big-endian, includes the 4-byte
  opcode) + `uint32 opcode` (little-endian).
- Server headers are `uint16 size` (big-endian, payload + 2-byte opcode) +
  `uint16 opcode` (little-endian); packets over `0x7FFF` use a 3-byte size.
- Only world packet **headers** are RC4-encrypted; payloads stay plaintext.
- The 40-byte SRP6 session key is `SHA1Interleave(S)` and must be stored
  exactly as 40 bytes.
