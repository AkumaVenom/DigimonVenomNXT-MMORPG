"""Original World DS: Paradox Chronicle campaign for the existing story systems.

Eighteen distinct supplied World DS maps: a peaceful service hub followed by
seventeen field assignments. Every assignment has an ordinary quest giver, an
independent authored tamer battle, a return conversation, and a Paradox boss.
None of these actors belongs to the MMO's autonomous rival population.

Feet positions were selected from a 16-unit lattice connected to the catalog
spawn with exact Navigation.trace checks, then checked against the native art.
The original map geometry, collision masks, and account partners are preserved.
"""
from __future__ import annotations

CAMPAIGN_ID = "world_ds_paradox"
CAMPAIGN_NAME = "World DS: Paradox Chronicle"
FINAL_NPC_ID = "ds_final_triad"

# Arrival, quest/guide, medic, shop, tamer/lab, boss/farm, return gate,
# final summon/archive, forward gate. Coordinates use the original map scale.
PLACEMENTS = {
    "world_ds_030": ((494, 372), (430, 388), (590, 468), (654, 244), (366, 116), (110, 372), (926, 404), (494, 212), (894, 196)),
    "world_ds_048": ((792, 368), (728, 336), (744, 496), (984, 288), (1048, 496), (408, 368), (1272, 464), (760, 208), (264, 288)),
    "world_ds_053": ((800, 308), (736, 276), (928, 340), (640, 180), (1072, 212), (1136, 484), (304, 324), (992, 292), (1344, 292)),
    "world_ds_059": ((668, 436), (604, 452), (764, 532), (860, 356), (380, 436), (1052, 436), (188, 340), (652, 596), (1212, 516)),
    "world_ds_066": ((768, 544), (704, 512), (896, 592), (576, 624), (1024, 416), (1136, 640), (288, 480), (608, 528), (1312, 448)),
    "world_ds_073": ((784, 476), (720, 476), (912, 428), (592, 412), (1056, 396), (400, 476), (1248, 316), (640, 492), (240, 556)),
    "world_ds_080": ((564, 456), (500, 440), (692, 504), (404, 328), (852, 440), (196, 360), (1028, 552), (708, 376), (100, 328)),
    "world_ds_089": ((704, 376), (640, 344), (800, 280), (864, 504), (528, 600), (320, 360), (1184, 280), (704, 536), (160, 296)),
    "world_ds_097": ((780, 444), (716, 412), (876, 540), (940, 316), (604, 668), (428, 300), (1276, 444), (796, 284), (1308, 332)),
    "world_ds_106": ((528, 396), (464, 428), (656, 444), (336, 476), (304, 220), (880, 540), (144, 92), (432, 524), (976, 620)),
    "world_ds_115": ((848, 716), (784, 748), (976, 668), (640, 700), (1120, 636), (464, 732), (1296, 572), (704, 780), (1216, 540)),
    "world_ds_125": ((556, 291), (492, 259), (652, 195), (396, 419), (844, 291), (236, 451), (812, 83), (716, 307), (332, 499)),
    "world_ds_140": ((796, 379), (732, 347), (892, 283), (956, 507), (668, 635), (412, 395), (1292, 347), (780, 539), (252, 427)),
    "world_ds_149": ((776, 323), (712, 291), (872, 419), (648, 483), (1048, 403), (408, 419), (1272, 275), (920, 259), (264, 531)),
    "world_ds_161": ((504, 504), (440, 472), (600, 600), (424, 312), (248, 376), (824, 712), (744, 696), (376, 408), (280, 296)),
    "world_ds_173": ((752, 384), (688, 352), (848, 480), (960, 352), (528, 208), (384, 480), (1232, 288), (592, 384), (208, 368)),
    "world_ds_192": ((872, 416), (808, 416), (968, 512), (1000, 256), (696, 640), (1192, 240), (552, 560), (840, 256), (600, 656)),
    "world_ds_200": ((848, 448), (784, 416), (944, 352), (720, 608), (1120, 544), (480, 352), (1344, 496), (1008, 464), (336, 432)),
}


# Names describe the supplied World DS map art. The narrative is authored for
# Venom NXT, not represented as dialogue extracted from the Nintendo DS game.
CHAPTERS = (
    {
        "id": "ds_green", "map": "world_ds_048", "name": "Green Valley",
        "subtitle": "The first impossible footprint", "crest": "Seed", "color": "#79df9a",
        "quest": "A footprint from tomorrow", "giver": "Field Researcher Tali", "giver_tamer": 23,
        "trainer": "Scout Pip", "trainer_tamer": 22, "tamer_level": 10, "boss_level": 13,
        "team": ("terriermon",), "boss": "palmon_paradox",
        "synopsis": "Fresh footprints appear before their owners arrive. Help Tali tune the first anchor and meet the Digimon caught between two mornings.",
        "brief": "These tracks belong to Palmon, but the grass inside them is still growing backward. Lyra calls that a paradox: two possible histories sharing the same place.",
        "assignment": "Scout Pip carries a clean reference beacon. Accept this assignment, defeat his level 10 team, then return to me with the recorded battle signal. We will steady the anchor before you approach Paradox Palmon.",
        "turnin": "Pip's signal gives us one moment we all remember. The anchor is steady. Palmon can finally see you clearly; win its battle to earn the Seed Paradox Crest.",
        "tamer_intro": "Tali needs an honest reference, and Terriermon needs a proper first outing. This is a friendly field test. Let's make it one we both remember!",
        "tamer_won": "There we go: one real battle, witnessed by both of us. A young Terriermon from our camp has asked to travel with you; it joins your team or waits in DigiLab storage. Take the beacon reading back to Tali before you face Palmon.",
        "tamer_lost": "Terriermon got the better of that exchange. The medic can restore your partners for free; I'll keep the beacon ready for our rematch.",
        "boss_intro": "Two suns rose over my seeds. If I choose one, will the other garden disappear? Show me that a new path can keep something precious alive.",
        "boss_won": "The roots have stopped pulling apart. Keep this Seed Crest; it remembers the morning we chose together. I can grow here now.",
        "resolved": "Our first anchor holds. The disturbance is traveling beneath the sandstone paths; another Digimon is trying to hold the cliffs together alone.",
    },
    {
        "id": "ds_sandstone", "map": "world_ds_053", "name": "Sandstone Pass",
        "subtitle": "A road with two endings", "crest": "Strata", "color": "#e4bc77",
        "quest": "Survey the shifting road", "giver": "Surveyor Ada", "giver_tamer": 30,
        "trainer": "Cliff Ranger Flint", "trainer_tamer": 14, "tamer_level": 15, "boss_level": 18,
        "team": ("armadillomon", "gotsumon"), "boss": "gotsumon_paradox",
        "synopsis": "The pass remembers a landslide that never happened. Give its frightened stone guardian a reliable route home.",
        "brief": "One survey shows this ledge intact. Another shows it buried. Both carry my signature. Gotsumon has been bracing the cliff against a disaster that belongs to another history.",
        "assignment": "Flint's partners can test the ground without damaging it. Accept the survey assignment, win his level 15 field battle, and bring the vibration record back to me. Then we can release the anchor safely.",
        "turnin": "The measured ground is stronger than either old survey suggests. I have set the anchor to today's reading. Paradox Gotsumon no longer needs to carry the whole pass; help it let go in battle.",
        "tamer_intro": "A cliff ranger trusts the ground under their boots. My partners will put your footing to the test; keep your team steady through the exchange.",
        "tamer_won": "You held your footing. Ada can use this vibration record to separate the real cliff from its echo. Report back to her first.",
        "tamer_lost": "A stumble tells you where to place your next step. Recover at the medic and try the survey battle again.",
        "boss_intro": "I remember these stones falling. I remember them standing. I cannot hold both forever. Can your partners carry one moment together?",
        "boss_won": "The cliff is standing without my fear beneath it. Take the Strata Crest. A Gomamon I sheltered in this pass would like to travel with you; it joins your team or waits in DigiLab storage. A memory can warn us without becoming our only future.",
        "resolved": "The old landslide was an echo, not a prediction. Its data drained into the tunnels below; a pumping station now repeats the same minute.",
    },
    {
        "id": "ds_drainage", "map": "world_ds_059", "name": "Drainage Tunnels",
        "subtitle": "The minute that would not end", "crest": "Flow", "color": "#76d9dc",
        "quest": "Restart the missing minute", "giver": "Pump Engineer Neri", "giver_tamer": 38,
        "trainer": "Maintenance Tamer Bolt", "trainer_tamer": 69, "tamer_level": 20, "boss_level": 23,
        "team": ("hagurumon", "kamemon"), "boss": "gekomon_paradox",
        "synopsis": "A repeated alarm traps the drainage system in a loop. Restore a shared rhythm before the tunnels flood with yesterday's water.",
        "brief": "The pump finishes its cycle, then the counter jumps backward. Gekomon sings to keep it moving, but the anchor mistakes every chorus for the first one.",
        "assignment": "Bolt can record a full battle on an independent clock. Accept the timing assignment, defeat his level 20 team, then return here. A complete sequence will give the anchor its missing minute.",
        "turnin": "Start, response, finish: every event has its own place. The pump clock is advancing. Paradox Gekomon is still caught in the chorus; win its battle to bring the song to an ending.",
        "tamer_intro": "My clock runs on springs, not the station network. Let's give Neri a battle with a beginning and an end she can trust.",
        "tamer_won": "Clock stopped at the victory signal, exactly as it should. Return to Neri and let her fit this sequence into the pump controls.",
        "tamer_lost": "The clock recorded a fair result. Heal your team and we'll record another; one loss doesn't trap you in a loop.",
        "boss_intro": "Again. Again. If I stop singing, the water rises. Please give me a final note strong enough for the tunnels to hear.",
        "boss_won": "Silence... and the water is still flowing. The Flow Crest is yours. Thank you for letting a song finish.",
        "resolved": "The tunnels can keep their own time again. Their logs point uphill, where the same broken anchor signal is confusing the canopy's nesting season.",
    },
    {
        "id": "ds_canopy", "map": "world_ds_066", "name": "Canopy Ridge",
        "subtitle": "Room for another season", "crest": "Canopy", "color": "#8cd66f",
        "quest": "Make room for the new nest", "giver": "Nest Keeper Fern", "giver_tamer": 24,
        "trainer": "Trail Tamer Wren", "trainer_tamer": 16, "tamer_level": 25, "boss_level": 28,
        "team": ("aquilamon", "togemon"), "boss": "kuwagamon_paradox",
        "synopsis": "The canopy is trying to shelter two seasons at once. Show its guardian that protecting a home includes allowing it to change.",
        "brief": "Kuwagamon remembers nests on branches that haven't grown yet. It guards every bud as if an entire family were already inside. No one can cross the ridge.",
        "assignment": "Wren knows which branches can carry a team today. Accept the nesting survey, win Wren's level 25 battle, and bring the partner signals back. I'll use them to mark safe space around the anchor.",
        "turnin": "Every partner has a safe place to stand. The anchor can support today's nests without erasing tomorrow's possibilities. Paradox Kuwagamon is ready to hear that lesson in battle.",
        "tamer_intro": "We keep our sparring clear of the nests. Aquilamon watches above; Togemon watches below. Show me how your partners make room for each other.",
        "tamer_won": "A team that shares its footing can share this forest. Take our survey to Fern; the guardian must see the ridge is safe.",
        "tamer_lost": "There is space here for another attempt. Recover, adjust your lineup, and come back when your team is ready.",
        "boss_intro": "I hear wings in branches that are still seeds. If you want to pass, prove your strength can shelter more than itself.",
        "boss_won": "The young branches may grow in their own time. Carry the Canopy Crest. I will guard the forest we have, and welcome the one it becomes.",
        "resolved": "The nests are quiet again. Beyond the ridge, the Sun Spire has begun casting two shadows, each pointing toward a different tomorrow.",
    },
    {
        "id": "ds_sun", "map": "world_ds_073", "name": "Sun Spire",
        "subtitle": "The horizon is not an order", "crest": "Horizon", "color": "#ffd779",
        "quest": "Read the true horizon", "giver": "Sky Observer Sol", "giver_tamer": 33,
        "trainer": "Bridge Captain Aero", "trainer_tamer": 44, "tamer_level": 30, "boss_level": 33,
        "team": ("birdramon", "unimon"), "boss": "airdramon_paradox",
        "synopsis": "Conflicting weather forecasts have become commands. Reopen the sky bridges before their guardian seals every possible crossing.",
        "brief": "The observatory predicts a clear crossing and a storm at the same hour. Airdramon sees both forecasts and has decided no one should ever cross again.",
        "assignment": "Aero's team will test today's winds. Accept the sky survey, beat the captain's level 30 team, and return with the current reading. We need evidence before we approach the guardian.",
        "turnin": "These winds belong to now. I have replaced the conflicting forecasts with a live reading. Paradox Airdramon still needs to learn that a possible storm is not a permanent closed gate.",
        "tamer_intro": "The ropes are checked, the winds are measured, and our partners are willing. Let's see how well your team adapts when the pace changes.",
        "tamer_won": "A sound crossing. Bring Sol the wind log; a forecast should help travelers prepare, not forbid the journey.",
        "tamer_lost": "Wait for your breath to settle. The medic is nearby, and this bridge will still be here when you're ready.",
        "boss_intro": "Every open sky contains a storm somewhere. Will you turn back from all of them, or show me how a team faces changing winds?",
        "boss_won": "You prepared without surrendering the road. Accept the Horizon Crest. The sky is open, and its travelers may choose their hour.",
        "resolved": "The twin shadows have aligned. Sol traced their second light to the Crystal Mine, where the anchor is multiplying every signal it receives.",
    },
    {
        "id": "ds_crystal", "map": "world_ds_080", "name": "Crystal Mine",
        "subtitle": "One voice through many reflections", "crest": "Prism", "color": "#b6a4f5",
        "quest": "Find the original resonance", "giver": "Miner Cora", "giver_tamer": 51,
        "trainer": "Resonance Tamer Flint", "trainer_tamer": 30, "tamer_level": 35, "boss_level": 38,
        "team": ("golemon", "meteormon"), "boss": "meteormon_paradox",
        "synopsis": "The crystals return a thousand copies of each sound. Find one shared reference without shattering the mine's living archive.",
        "brief": "Every pick strike echoes as if a thousand miners worked here. Meteormon absorbed the duplicate signals to protect us. Now it cannot tell its own voice from the noise.",
        "assignment": "Flint brought a dampened recorder from the pass. Accept the resonance assignment, win the level 35 calibration battle, and bring me the clean sample. We can tune the anchor without breaking the crystals.",
        "turnin": "There is the original note beneath the reflections. The crystals have stopped feeding back. Paradox Meteormon can release the echoes now; meet it in battle and help it find its own rhythm.",
        "tamer_intro": "Good to see a familiar tamer. My partners have trained since the pass, and this recorder is ready. Let's give Cora a signal the whole mine can follow.",
        "tamer_won": "Still steady under pressure. Take the clean recording to Cora; every reflection can stay, now that we know where the sound began.",
        "tamer_lost": "We have both learned a few things since the cliffs. Heal up and try a new approach; the calibration can wait.",
        "boss_intro": "I remember a thousand voices, and none will answer to my name. Give me one battle that belongs to me.",
        "boss_won": "That final exchange was mine. The Prism Crest keeps every color without confusing their source. Carry it with you.",
        "resolved": "A message emerges from the quiet crystals: 'Seventeen witnesses. One accord.' The next witness waits in a marsh where reflections have begun speaking for their owners.",
    },
    {
        "id": "ds_marsh", "map": "world_ds_089", "name": "Mirage Marsh",
        "subtitle": "A reflection is not a promise", "crest": "Truth", "color": "#ca8ce4",
        "quest": "Question the borrowed answer", "giver": "Marsh Archivist Tess", "giver_tamer": 23,
        "trainer": "Pathfinder Reed", "trainer_tamer": 60, "tamer_level": 40, "boss_level": 43,
        "team": ("taomon", "lilamon", "gekomon"), "boss": "taomon_paradox",
        "synopsis": "Reflections offer perfect answers before anyone asks a question. Help the marsh keep honest choices instead of convenient predictions.",
        "brief": "My reflection promised everyone a safe shortcut. I never said it. Taomon is trying to honor every promise the water invents, and the anchor keeps inventing more.",
        "assignment": "Reed will record a battle whose choices belong to the tamers taking part. Accept the witness assignment, defeat the level 40 team, then return here. I will separate their real decisions from the marsh's guesses.",
        "turnin": "The record contains surprises the reflections never predicted. The anchor recognizes a choice made freely. Paradox Taomon can stop fulfilling promises no one actually made.",
        "tamer_intro": "The water says I already know your opening move. I prefer to ask your partners. Let's find out what you choose for yourselves.",
        "tamer_won": "That was a real decision, right to the end. Bring Tess the record before the marsh tries to improve the story for us.",
        "tamer_lost": "A reflection might pretend that loss never happened. We can do better: recover, learn from it, and try again.",
        "boss_intro": "I have promised every traveler a safe ending, though their voices never reached me. Show me which promise a willing heart can truly make.",
        "boss_won": "I can promise to listen and to help. I cannot choose another's ending. Accept the Truth Crest; the water may reflect us without speaking in our place.",
        "resolved": "Tess found the name of the old protocol: ORIGIN. It was built to preserve one 'correct' world. The coastal beacon is receiving its instructions next.",
    },
    {
        "id": "ds_strand", "map": "world_ds_097", "name": "Silver Strand",
        "subtitle": "A crossing for every shore", "crest": "Tide", "color": "#71c8f7",
        "quest": "Reunite the beacon charts", "giver": "Beacon Keeper Rill", "giver_tamer": 51,
        "trainer": "Harbor Tamer Bay", "trainer_tamer": 16, "tamer_level": 45, "boss_level": 48,
        "team": ("whamon", "zudomon", "megaseadramon"), "boss": "megaseadramon_paradox",
        "synopsis": "Two shorelines occupy the same water. Build a crossing that honors both communities instead of declaring one an error.",
        "brief": "The beacon sees two coastlines. ORIGIN wants one deleted from the charts. Megaseadramon is holding back the tide until both shores can be heard.",
        "assignment": "Bay's partners carry signatures from both harbors. Accept the crossing assignment, win Bay's level 45 battle, and return with the shared tide log. I can teach the anchor to recognize both signals.",
        "turnin": "Two signatures, one safe channel. The anchor accepts both harbors as real. Paradox Megaseadramon no longer has to stand against every wave; help it trust the crossing.",
        "tamer_intro": "Every boat brings a different crew. My team knows the strength of traveling together; show us what your partners have learned on the road.",
        "tamer_won": "Both harbors witnessed that result. Rill needs the tide log to open the channel before you approach its guardian.",
        "tamer_lost": "The next tide will come. Visit the medic, replenish your supplies, and we can sail into another battle.",
        "boss_intro": "One shore calls me protector. Another calls me stranger. If both are real, show me where I am allowed to stand.",
        "boss_won": "Between them, as a neighbor. The Tide Crest belongs to you. No shore must vanish for another to be home.",
        "resolved": "Rill recovered an old registry: the crests are witness seals, not commands. The Amber Badlands hold the history ORIGIN refused to preserve.",
    },
    {
        "id": "ds_amber", "map": "world_ds_106", "name": "Amber Badlands",
        "subtitle": "The history left out", "crest": "Memory", "color": "#f0ab69",
        "quest": "Restore the missing testimony", "giver": "Historian Petra", "giver_tamer": 38,
        "trainer": "Relic Warden Dune", "trainer_tamer": 30, "tamer_level": 50, "boss_level": 53,
        "team": ("triceramon", "skullgreymon", "meteormon"), "boss": "skullgreymon_paradox",
        "synopsis": "A rejected history survives in the canyon stones. Hear its guardian's testimony before ORIGIN erases the last witnesses.",
        "brief": "These fossils belong to a world that ORIGIN marked 'inconsistent.' SkullGreymon remembers living there. A damaged record does not make that life disposable.",
        "assignment": "Dune protects the archive with a witnessed battle seal. Accept the testimony assignment, defeat the level 50 team, then bring me the fresh seal. It will let us attach the missing history to the anchor.",
        "turnin": "The archive accepts our new witness. That lost world has a place in the record again. Paradox SkullGreymon can face a living team without fearing its past will be overwritten.",
        "tamer_intro": "You carry eight voices now. Before I open the archive, show me that all your partners still have a part in this journey.",
        "tamer_won": "A strong team, and a patient tamer. Take Petra the witness seal. Let the oldest voice tell its own story.",
        "tamer_lost": "Stone can hold a record for ages; it can wait while you recover. Your earlier crests remain yours.",
        "boss_intro": "I was here. Before the false label, before the silence. Meet my strength and remember that it came from a life.",
        "boss_won": "You remember. Accept the Memory Crest. The past need not return unchanged to remain worth carrying.",
        "resolved": "Petra's archive explains the danger: ORIGIN will collapse every conflicting timeline into one. Its physical lock was built inside Clockwork Fort.",
    },
    {
        "id": "ds_clockwork", "map": "world_ds_115", "name": "Clockwork Fort",
        "subtitle": "A lock that can learn", "crest": "Rhythm", "color": "#acbdde",
        "quest": "Rewrite the lock's assumption", "giver": "Clockwright Iona", "giver_tamer": 69,
        "trainer": "Workshop Captain Cobalt", "trainer_tamer": 87, "tamer_level": 55, "boss_level": 58,
        "team": ("andromon", "metalmamemon", "knightmon"), "boss": "hiandromon_paradox",
        "synopsis": "The fort mistakes agreement for identical timing. Give its precision guardian a working example of partners who act differently and still belong together.",
        "brief": "The lock rejects any two clocks that disagree. HiAndromon keeps correcting the fort until every gear stops. ORIGIN calls perfect stillness a successful synchronization.",
        "assignment": "Cobalt's team uses three independent timing circuits. Accept the lock assignment, win the level 55 workshop battle, and return with its sequence. The anchor needs coordinated differences, not identical copies.",
        "turnin": "Different timings, one complete result. The lock accepts cooperation as a valid pattern. Paradox HiAndromon must now choose to stop enforcing an impossible standard.",
        "tamer_intro": "Three partners, three tempos. Your job is to keep the team working when the rhythm changes. The workshop is ready for your test.",
        "tamer_won": "A working result with room for variation. Take the sequence to Iona; she can make the lock recognize what we just proved.",
        "tamer_lost": "Good machinery allows maintenance. Restore your team and come back with the adjustments you want to try.",
        "boss_intro": "Deviation detected. Yet your differing signals form a complete team. Submit your evidence in battle; I will evaluate the result.",
        "boss_won": "Evaluation complete: agreement does not require identity. Receive the Rhythm Crest. This fort will keep time without forbidding change.",
        "resolved": "Iona found a second safeguard: seventeen independent crests can call ORIGIN's guardians to a hearing. The Frost Shelf shelters the next witness.",
    },
    {
        "id": "ds_frost", "map": "world_ds_125", "name": "Frost Shelf",
        "subtitle": "A shelter with an open door", "crest": "Shelter", "color": "#b7e8ff",
        "quest": "Thaw the rescue signal", "giver": "Rescue Medic Eira", "giver_tamer": 62,
        "trainer": "Snow Patrol Tamer Alba", "trainer_tamer": 61, "tamer_level": 60, "boss_level": 63,
        "team": ("mammothmon", "zudomon", "vikemon"), "boss": "vikemon_paradox",
        "synopsis": "A rescue promise has frozen every departure. Help the shelf's protector distinguish offering shelter from keeping its guests captive.",
        "brief": "Vikemon rescued travelers during a storm in another history. The anchor keeps replaying their distress, so the shelter never receives an all-clear.",
        "assignment": "Alba's patrol carries a fresh rescue transponder. Accept the all-clear assignment, beat the level 60 patrol team, and return with its live report. We will tell the anchor that the rescued partners can travel again.",
        "turnin": "Everyone is accounted for, and every partner answered freely. The distress loop is off. Paradox Vikemon can open the shelter once it trusts you to face the road together.",
        "tamer_intro": "We never leave a partner behind. Let's see how your team handles a patrol that stays together through a long exchange.",
        "tamer_won": "Your partners kept answering. Take our all-clear to Eira; the shelter has earned a quiet day.",
        "tamer_lost": "The patrol has room for you by the heater. Recover at the medic and return when your team is ready.",
        "boss_intro": "I brought them out of the storm. If the door opens, the storm might find them again. Show me that care can travel with a team.",
        "boss_won": "You carry your shelter in the way you answer each other. Take the Shelter Crest. This door will welcome returns as gladly as arrivals.",
        "resolved": "The rescue archive says ORIGIN was built from a good intention left without questions. Radiant Citadel still holds its original oath.",
    },
    {
        "id": "ds_radiant", "map": "world_ds_140", "name": "Radiant Citadel",
        "subtitle": "An oath heard in full", "crest": "Radiance", "color": "#f7edb3",
        "quest": "Recover the complete oath", "giver": "Oath Keeper Sera", "giver_tamer": 36,
        "trainer": "Citadel Tamer Vale", "trainer_tamer": 87, "tamer_level": 65, "boss_level": 68,
        "team": ("magnaangemon", "craniamon", "seraphimon"), "boss": "seraphimon_paradox",
        "synopsis": "ORIGIN preserved the command to protect the world and lost the promise to hear its people. Recover both halves of the oath.",
        "brief": "The oath begins, 'Preserve the world.' Its next line is scratched away: 'by listening to those who live within it.' Seraphimon has guarded the first half for too long.",
        "assignment": "Vale holds the oath's independent witness seal. Accept the restoration assignment, win the level 65 citadel battle, and return to me. Both halves must be authenticated before the guardian can hear them.",
        "turnin": "The missing line is restored and witnessed. The anchor now carries a promise instead of a command. Bring the complete oath into your battle with Paradox Seraphimon.",
        "tamer_intro": "Power may guard a promise, but it cannot decide its meaning alone. Show me the judgment that brought your team this far.",
        "tamer_won": "You have earned the witness seal. Return to Sera; let the guardian hear every word before it asks you to prove them.",
        "tamer_lost": "An oath is not fulfilled by one perfect attempt. Recover your strength and return to the trial.",
        "boss_intro": "I have kept the world unchanged and called that protection. Carry the missing words into this battle, where I can no longer turn away.",
        "boss_won": "To preserve a world is to hear the lives it holds. Accept the Radiance Crest. I will guard the whole oath from this day forward.",
        "resolved": "The completed oath names the finale: the Origin Triad, three Mega guardians sharing one decision. We need the remaining crests to summon them without surrendering the world.",
    },
    {
        "id": "ds_coral", "map": "world_ds_149", "name": "Coral Archipelago",
        "subtitle": "Many islands, one invitation", "crest": "Unity", "color": "#f3a8c1",
        "quest": "Carry every island's reply", "giver": "Island Envoy Maris", "giver_tamer": 44,
        "trainer": "Ferry Tamer Cove", "trainer_tamer": 51, "tamer_level": 70, "boss_level": 73,
        "team": ("marineangemon", "plesiomon", "metalseadramon"), "boss": "neptunemon_paradox",
        "synopsis": "The archipelago's islands disagree about how to face ORIGIN. Collect a shared invitation that leaves their differences intact.",
        "brief": "One island wants the Triad confronted. Another wants to hide. Neptunemon refuses to move until every reply is identical, while the anchor quietly discards the minority.",
        "assignment": "Cove's partners represent three island routes. Accept the invitation assignment, defeat the level 70 ferry team, and return with their witnessed replies. Agreement to be heard is enough; no one must surrender their own answer.",
        "turnin": "Every island has agreed to the hearing, even those still afraid of it. The anchor carries all their replies. Paradox Neptunemon can open the route without declaring one island the voice of the rest.",
        "tamer_intro": "My partners learned on different shores. We won't battle alike, but we will battle together. Let's see how your team answers us.",
        "tamer_won": "Three routes, one witnessed result. Bring Maris our replies; every island deserves a place at the hearing.",
        "tamer_lost": "The ferry makes more than one crossing. Heal your team and come back for another passage.",
        "boss_intro": "A ruler who cannot make every voice agree may be no ruler at all. Show me how a team survives a difference it does not erase.",
        "boss_won": "By answering, not commanding. The Unity Crest is yours. These islands may share a sea without becoming the same shore.",
        "resolved": "The hearing has willing witnesses. The Magma Citadel is forging the signal they must send, but its guardian fears any flaw will doom the entire accord.",
    },
    {
        "id": "ds_magma", "map": "world_ds_161", "name": "Magma Citadel",
        "subtitle": "Strong enough to bend", "crest": "Resolve", "color": "#ff9470",
        "quest": "Temper the accord signal", "giver": "Forge Keeper Ferris", "giver_tamer": 69,
        "trainer": "Foundry Tamer Ember", "trainer_tamer": 67, "tamer_level": 75, "boss_level": 78,
        "team": ("wargreymon", "shinegreymon", "boltmon"), "boss": "ancientvolcanomon_paradox",
        "synopsis": "A perfectly rigid signal will shatter under the Triad's reply. Temper the accord so it can endure disagreement without breaking.",
        "brief": "AncientVolcanomon melts every seal that bends. It thinks only a flawless signal can survive ORIGIN. The result is a forge full of perfect fragments.",
        "assignment": "Ember can put a sample signal under real battle pressure. Accept the tempering assignment, win the level 75 foundry battle, and return with its stress record. We will build strength that can recover.",
        "turnin": "The sample flexed and returned intact. I've given the anchor that same resilience. Paradox AncientVolcanomon can test your resolve without demanding perfection.",
        "tamer_intro": "Heat finds every weakness, but it also lets metal take a better shape. Let's see what your team has learned to do under pressure.",
        "tamer_won": "You kept the team working after the hardest exchanges. Ferris needs this stress record; it's the proof our forge has been missing.",
        "tamer_lost": "Even a good blade returns to the forge. Restore your partners and bring what this battle taught you into the rematch.",
        "boss_intro": "The Triad will strike harder than I do. If your resolve can bend without breaking, prove it here in the heart of the forge.",
        "boss_won": "A living strength can yield and stand again. Take the Resolve Crest. The accord is tempered; it will carry every voice to the end.",
        "resolved": "The signal is ready, but Shadow Grid reports an identity fault: ORIGIN intends to label every Paradox Digimon a disposable duplicate.",
    },
    {
        "id": "ds_shadow", "map": "world_ds_173", "name": "Shadow Grid",
        "subtitle": "More than a duplicate", "crest": "Identity", "color": "#a296fa",
        "quest": "Protect the second signature", "giver": "Network Keeper Nyra", "giver_tamer": 67,
        "trainer": "Signal Tamer Nox", "trainer_tamer": 4, "tamer_level": 80, "boss_level": 83,
        "team": ("dianamon", "dorugoramon", "megagargomon"), "boss": "diaboromon_paradox",
        "synopsis": "The network treats shared origins as proof that one life can replace another. Protect the distinct signature of every Paradox partner.",
        "brief": "ORIGIN compares the first line of each record and calls the rest a copy. Diaboromon has been multiplying its signature to keep even one version from being deleted.",
        "assignment": "Nox volunteered his team's independent bond records. Accept the identity assignment, defeat the level 80 team, and bring their new shared result back to me. We will prove that history keeps growing after an origin.",
        "turnin": "Their origins did not change, but their record now includes a new battle with you. The anchor recognizes living identities instead of duplicate files. Paradox Diaboromon can stop multiplying to be heard.",
        "tamer_intro": "I used to think a stronger result settled every argument. Your journey has seventeen answers to that. Let's add one more honest battle before you face the grid.",
        "tamer_won": "Same partners, a new result, and neither erases what came before. Take that to Nyra. It is the strongest evidence we can give her.",
        "tamer_lost": "This result belongs in the record too. It doesn't own your next decision. Heal up; I'll be here for the rematch.",
        "boss_intro": "One signature can be deleted. A thousand might survive. If I stand here as only myself, will you still see enough to face me?",
        "boss_won": "You answered the one who stood before you. Accept the Identity Crest. No shared beginning makes a living future expendable.",
        "resolved": "Nyra has blocked the duplicate purge. The grid points toward a final promise carried over Dusk Highlands, where a guardian has waited for a traveler who never returned.",
    },
    {
        "id": "ds_dusk", "map": "world_ds_192", "name": "Dusk Highlands",
        "subtitle": "A promise that can move forward", "crest": "Promise", "color": "#deb1ec",
        "quest": "Deliver the unfinished farewell", "giver": "Highland Witness Orin", "giver_tamer": 65,
        "trainer": "Ridge Tamer Vesper", "trainer_tamer": 60, "tamer_level": 86, "boss_level": 89,
        "team": ("ancientgarurumon", "ravemon", "sakuyamon"), "boss": "ancientgarurumon_paradox",
        "synopsis": "An undelivered farewell has become an endless watch. Help the highlands carry a promise forward without forgetting the friend it honored.",
        "brief": "AncientGarurumon promised to wait here for a traveler from another history. Their farewell survived, but ORIGIN rejected its route. The guardian never learned that waiting was no longer needed.",
        "assignment": "Vesper carries the farewell under a witness seal. Accept the delivery assignment, win the level 86 ridge battle, and return with the authenticated message. We will let the anchor carry it all the way home.",
        "turnin": "The farewell says, 'Thank you for keeping a place for me. Please go and see the world we hoped for.' The anchor has delivered it. Paradox AncientGarurumon asks for one final battle before ending its watch.",
        "tamer_intro": "There are things a battle cannot say for us. But it can prove we will stand behind the words we carry. Show me that resolve.",
        "tamer_won": "You have earned the seal. Return to Orin and let the message finish its journey; the guardian has waited long enough.",
        "tamer_lost": "The message is safe with me. Your team can recover without losing the road it traveled.",
        "boss_intro": "I promised to wait. Now my friend asks me to walk on. Give this long watch an ending worthy of the promise that began it.",
        "boss_won": "Then I will carry the memory with me instead of standing still inside it. The Promise Crest is yours. I will meet the next sunrise on the road.",
        "resolved": "Sixteen crests now answer together. The final witness waits at Eclipse Sanctum, beside the summoning anchor that can call the Origin Triad.",
    },
    {
        "id": "ds_eclipse", "map": "world_ds_200", "name": "Eclipse Sanctum",
        "subtitle": "Seventeen witnesses", "crest": "Eclipse", "color": "#c7a3ff",
        "quest": "Convene the Paradox Accord", "giver": "Researcher Lyra", "giver_tamer": 31,
        "trainer": "Accord Marshal Aster", "trainer_tamer": 2, "tamer_level": 92, "boss_level": 96,
        "team": ("craniamon", "apollomon", "alphamon"), "boss": "zeedmillenniummon_paradox",
        "synopsis": "Bring sixteen journeys to the final witness. Complete the accord, earn the seventeenth crest, and summon the three level 100 Paradox Mega guardians.",
        "brief": "We reached the sanctum together. The last guardian holds every rejected history in its chains. It cannot free them until a complete accord proves they will still have a place.",
        "assignment": "Aster will witness the final field trial. Accept the accord assignment, defeat the level 92 marshal team, and return to me. Then face Paradox ZeedMillenniummon for the seventeenth crest before approaching the Origin Summoning Anchor.",
        "turnin": "Aster's witness completes the field record. The anchor can now carry every history without replacing the others. Defeat Paradox ZeedMillenniummon to receive the Eclipse Crest; all seventeen crests are required for the final summon.",
        "tamer_intro": "This hearing belongs to the lives your team protected. I will bring everything my partners have learned to the last field trial. Answer us with everything yours have learned.",
        "tamer_won": "The final witness stands. Return to Lyra, then earn the Eclipse Crest. After that, prepare your full team for three level 100 Paradox Mega opponents in one battle.",
        "tamer_lost": "Sixteen crests still shine. Restore your team, reconsider your techniques, and return. A failed trial does not undo your journey.",
        "boss_intro": "I carry every world they called impossible. If I loosen these chains, promise me they will not fall into nothing. Let your seventeen journeys answer.",
        "boss_won": "The accord holds. Receive the Eclipse Crest, the seventeenth and final witness seal. The Origin Summoning Anchor will now answer you; prepare for the three guardians at level 100.",
        "resolved": "All seventeen Paradox Crests are gathered. Visit the Origin Summoning Anchor here in Eclipse Sanctum. The Origin Triad awaits as one team of three level 100 Paradox Megas.",
    },
)


def _npc(region, suffix, name, tamer, role, map_id, point, dialogue, **extra):
    return {"id": f"{region}_{suffix}", "region_id": region, "name": name,
            "tamer": f"tamer_{tamer:03d}", "tamer_id": f"tamer_{tamer:03d}",
            "role": role, "map_id": map_id, "x": float(point[0]), "y": float(point[1]),
            "requires": [], "requires_accepted": [], "team": [], "reward": {},
            "badge": None, "repeatable": False, "dialogue": dialogue, **extra}


def _service_dialogue(lines):
    return {key: list(lines) for key in ("intro", "ready", "locked", "won", "lost", "repeat")}


def _reward(index, step, chapter):
    tier = "s" if index <= 3 else "m" if index <= 9 else "l"
    if step == "quest":
        return {"credits": 250 + index * 125, "items": {f"hp_{tier}": 2, f"sp_{tier}": 1}}
    if step == "trainer":
        floor = chapter["boss_level"] - 1
        reward = {"credits": 450 + index * 300,
                  "items": {f"hp_{tier}": 2, f"sp_{tier}": 2},
                  "training_level": floor, "level_floor": floor}
        if index == 1:
            reward["partner"] = "terriermon"
        return reward
    floor = CHAPTERS[index]["tamer_level"] if index < len(CHAPTERS) else 98
    reward = {"credits": 900 + index * 750,
              "items": {f"hp_{tier}": 4, f"sp_{tier}": 3},
              "training_level": floor, "level_floor": floor}
    if index == 2:
        reward["partner"] = "gomamon"
    return reward


def build_content(engine) -> dict:
    """Build deterministic metadata without mutating account or MMO NPC state."""
    cached = getattr(engine, "_world_ds_story_content", None)
    if cached is not None:
        return cached
    regions, maps, npcs = [], {}, {}

    def add_map(map_id, region_id, name, *, peaceful=False):
        if map_id not in engine.maps:
            raise ValueError(f"World DS story map is missing: {map_id}")
        arrival = list(PLACEMENTS[map_id][0])
        if list(engine.maps[map_id]["spawn"]) != arrival:
            raise ValueError(f"World DS story map spawn changed: {map_id}")
        maps[map_id] = {"id": map_id, "map_id": map_id, "region_id": region_id,
                        "name": name, "arrival": arrival, "exits": [], "npc_ids": [],
                        "peaceful": peaceful, "allow_wild_battles": not peaceful}

    def add_npc(npc, region):
        npcs[npc["id"]] = npc
        region["npc_ids"].append(npc["id"])
        maps[npc["map_id"]]["npc_ids"].append(npc["id"])

    hub_id, hub_map = "ds_hub", "world_ds_030"
    hub = {"id": hub_id, "name": "Forest Glade", "subtitle": "A place to begin and return",
           "synopsis": "A peaceful expedition camp. Meet Lyra, use your usual DigiLab and DigiFarm, stock up, and set out for the seventeen Paradox Crests.",
           "level_min": 10, "level_max": 10, "index": 0, "badge": None,
           "maps": [hub_map], "npc_ids": [], "trial_ids": [], "quest_ids": [],
           "warden_id": None, "peaceful": True,
           "objective": "Speak with Researcher Lyra, prepare your partners, then travel to Green Valley for the first level 10 assignment."}
    regions.append(hub)
    add_map(hub_map, hub_id, "Forest Glade", peaceful=True)
    hub_services = (
        ("guide", "Researcher Lyra", 31, "mentor", 1, [
            "Welcome to Forest Glade. This camp is safe: there are no battles here. Beyond it, seventeen World DS regions are sharing space with impossible histories, and Paradox Digimon are trying to hold them together.",
            "Start in Green Valley around level 10. In each region, accept the local research assignment, defeat its tamer, return to the quest giver, then challenge the Paradox guardian. Each guardian awards one unique Paradox Crest.",
            "Gather all seventeen crests to summon the Origin Triad in Eclipse Sanctum: three Paradox Mega Digimon, each level 100, fought as one team. Victory permanently improves your Paradox scan gain from wild battle wins by 20%.",
            "Your partners, bag, credits, scans, DigiLab, and DigiFarm are the same ones you use throughout Venom NXT. Hana and Moss can help you use them here. Every opened region remains available when you need to return.",
        ]),
        ("healer", "Medic Elio", 64, "healer", 2, [
            "A healthy team makes a better journey. I can fully restore your active partners for free, as often as you need. Our field medics offer the same care in every region.",
            "Losing a story battle never takes away a crest or a completed assignment. Recover, prepare, and try again when you are ready.",
        ]),
        ("shop", "Outfitter Len", 34, "shop", 3, [
            "Our supplies go into your usual bag and use your existing credits. Bring HP capsules for recovery and SP capsules for longer battles. You can restock here or with the field outfitters.",
        ]),
        ("lab", "DigiLab Researcher Hana", 23, "lab", 4, [
            "Your DigiLab travels with your account. Manage partners and storage, convert eligible scans, and review Digivolution using the same systems you already know.",
            "Opening this story never replaces your team or resets your progress. Before a difficult trial, review your active partners and their equipped techniques.",
        ]),
        ("farm", "Farm Keeper Moss", 24, "farm", 5, [
            "The DigiFarm is still your DigiFarm. Its residents and progress stay with you while you explore this story. Open the farm whenever you want to tend your partners.",
            "A return to camp is part of the journey. Take the time to prepare a team you enjoy traveling with.",
        ]),
        ("archive", "Archivist Fenn", 65, "mentor", 7, [
            "A Paradox Crest is a permanent witness seal, not a consumable key. Seventeen different guardians, seventeen different crests. A rematch cannot award a second copy.",
            "The final summon checks the entire set and leaves every crest in your collection. The permanent scan reward is earned once; replaying the finale cannot stack it.",
        ]),
    )
    for suffix, name, tamer, role, slot, lines in hub_services:
        add_npc(_npc(hub_id, suffix, name, tamer, role, hub_map,
                     PLACEMENTS[hub_map][slot], _service_dialogue(lines)), hub)

    prior_warden = None
    for index, chapter in enumerate(CHAPTERS, 1):
        rid, mid = chapter["id"], chapter["map"]
        quest_id, trainer_id, boss_id = f"{rid}_quest", f"{rid}_trainer", f"{rid}_warden"
        boss_species = engine.species.get(chapter["boss"])
        if not boss_species or not boss_species.get("paradox"):
            raise ValueError(f"World DS guardian must be an existing Paradox: {chapter['boss']}")
        boss_name = boss_species["name"]
        crest_name = f"{chapter['crest']} Paradox Crest"
        badge = {"id": rid, "name": crest_name, "color": chapter["color"],
                 "description": f"Witness {index} of 17: {chapter['name']}. Awarded for defeating {boss_name}."}
        region = {"id": rid, "name": chapter["name"], "subtitle": chapter["subtitle"],
                  "synopsis": chapter["synopsis"], "level_min": chapter["tamer_level"],
                  "level_max": chapter["boss_level"], "index": index, "badge": badge,
                  "maps": [mid], "npc_ids": [], "trial_ids": [quest_id, trainer_id],
                  "quest_ids": [quest_id], "warden_id": boss_id,
                  "objective": f"Accept '{chapter['quest']}' from {chapter['giver']}; defeat {chapter['trainer']}; return to {chapter['giver']}; defeat {boss_name} for the {crest_name}."}
        regions.append(region)
        add_map(mid, rid, chapter["name"])
        prerequisite = [prior_warden] if prior_warden else []
        quest_ready = [chapter["brief"], chapter["assignment"]]
        quest_progress = [f"Assignment: {chapter['quest']}.",
                          f"Defeat {chapter['trainer']}'s level {chapter['tamer_level']} team, then return here to stabilize the anchor. The Paradox guardian remains locked until we finish this work."]
        quest_complete = [chapter["turnin"],
                          f"Assignment complete. Your supplies are in your bag. Next: defeat {boss_name} at level {chapter['boss_level']} for the {crest_name}."]
        quest_submit = [chapter["turnin"],
                        f"Complete your report to receive the assignment supplies and unlock {boss_name}'s level {chapter['boss_level']} guardian battle."]
        add_npc(_npc(rid, "quest", chapter["giver"], chapter["giver_tamer"], "quest", mid,
                     PLACEMENTS[mid][1],
                     {"intro": quest_ready, "ready": quest_ready, "quest_start": quest_ready,
                      "quest_progress": quest_progress, "quest_complete": quest_submit,
                      "locked": ["Finish the previous region's Paradox guardian before beginning this assignment."],
                      "won": quest_complete, "lost": ["Your assignment stays open. The medic can help your partners recover before another attempt."],
                      "repeat": [chapter["turnin"], "The anchor is prepared. Your completed assignment and its rewards are safely recorded."]},
                     requires=prerequisite, quest_requires=[trainer_id], quest_title=chapter["quest"],
                     objective=f"Defeat {chapter['trainer']}, then return to {chapter['giver']}.",
                     reward=_reward(index, "quest", chapter)), region)
        add_npc(_npc(rid, "trainer", chapter["trainer"], chapter["trainer_tamer"], "trainer", mid,
                     PLACEMENTS[mid][4],
                     {"intro": [chapter["tamer_intro"]], "ready": [chapter["tamer_intro"], f"Field trial: level {chapter['tamer_level']}. Return to {chapter['giver']} after you win."],
                      "locked": [f"Speak with {chapter['giver']} and accept '{chapter['quest']}' first. We need the assignment recorder ready before our field trial."],
                      "won": [chapter["tamer_won"]], "lost": [chapter["tamer_lost"]],
                      "repeat": ["Your first victory is recorded. A friendly rematch is available; companions and first-clear rewards are earned only once."],
                      "rematch_won": ["A good rematch! Your first victory and its rewards are already recorded. Keep preparing your partners for the road ahead."]},
                     requires=prerequisite, requires_accepted=[quest_id],
                     team=[{"species": species, "level": max(10, chapter["tamer_level"] - offset)}
                           for offset, species in enumerate(chapter["team"])],
                     reward=_reward(index, "trainer", chapter), repeatable=True), region)
        add_npc(_npc(rid, "warden", boss_name, 87, "warden", mid, PLACEMENTS[mid][5],
                     {"intro": [chapter["boss_intro"]],
                      "ready": [chapter["boss_intro"], f"Paradox guardian: level {chapter['boss_level']}. First-victory reward: {crest_name} ({index}/17)."],
                      "locked": [f"Accept {chapter['giver']}'s assignment, defeat {chapter['trainer']}, then return to {chapter['giver']} to stabilize the anchor before this battle."],
                      "won": [chapter["boss_won"], chapter["resolved"]],
                      "rematch_won": [f"Well fought. The {crest_name} you earned is still safely recorded. This rematch awards no additional crest or first-clear rewards."],
                      "lost": ["The anchor still holds. Your completed assignment and earlier crests are safe. Recover with the medic, prepare your partners, and challenge me again."],
                      "repeat": [chapter["boss_won"], "Your crest is already recorded. We can share a training rematch whenever you choose."]},
                     requires=[quest_id, trainer_id],
                     team=[{"species": chapter["boss"], "level": chapter["boss_level"]}],
                     display_species=chapter["boss"], display_level=chapter["boss_level"],
                     reward=_reward(index, "boss", chapter), badge=rid, repeatable=True), region)
        add_npc(_npc(rid, "healer", "Field Medic Elio", 64, "healer", mid, PLACEMENTS[mid][2],
                     _service_dialogue([
                         f"You can take a breath here in {chapter['name']}. I can fully restore your active team for free before an assignment, guardian battle, or rematch.",
                         "Your crests and completed quests remain safe after a loss. Return whenever your partners need care.",
                     ])), region)
        add_npc(_npc(rid, "shop", "Field Outfitter Len", 34, "shop", mid, PLACEMENTS[mid][3],
                     _service_dialogue([
                         f"The local trials run from level {chapter['tamer_level']} to {chapter['boss_level']}. These supplies use your usual credits and bag; keep some HP and SP recovery ready.",
                         "Your DigiLab, DigiFarm, team, and techniques remain available through the normal menus. You can also revisit Forest Glade whenever you need the camp services.",
                     ])), region)
        prior_warden = boss_id

    # Forward travel is unlocked by the current field's crest. Retreat to any
    # previous region never needs an additional crest or consumes one.
    for index, region in enumerate(regions[:-1]):
        source, target = region["maps"][0], regions[index + 1]["maps"][0]
        gate_badge = region["id"] if region["badge"] else None
        for frm, to, slot, gate in ((source, target, 8, gate_badge), (target, source, 6, None)):
            point = PLACEMENTS[frm][slot]
            maps[frm]["exits"].append({"id": f"{frm}_to_{to}", "to_map": to,
                "map_id": to, "name": maps[to]["name"], "x": float(point[0]),
                "y": float(point[1]), "requires_badge": gate})

    final_region = regions[-1]
    final_mid = final_region["maps"][0]
    final_team = [
        {"species": "alphamon_paradox", "level": 100},
        {"species": "omnimon_paradox", "level": 100},
        {"species": "imperialdramonpaladinmode_paradox", "level": 100},
    ]
    final_intro = [
        "Seventeen crests answer the summoning anchor. ORIGIN's three guardians have heard the accord: Paradox Alphamon, Paradox Omnimon, and Paradox Imperialdramon Paladin Mode.",
        "They stand together at level 100. This is one final battle against a team of three Mega Digimon. Heal your partners, review your techniques, and stock up before you summon them.",
        "Defeat the Origin Triad to complete this story and permanently gain +20% Paradox scan from wild battle wins. Your crests are proof of the accord and will not be consumed.",
    ]
    finale = _npc(final_region["id"], "triad", "Origin Summoning Anchor", 31, "final", final_mid,
                  PLACEMENTS[final_mid][7],
                  {"intro": final_intro, "ready": final_intro,
                   "locked": ["The Origin Triad requires all seventeen different Paradox Crests and their guardian victories. Complete each field assignment and guardian battle, including the Eclipse Crest here in the sanctum."],
                   "won": [
                       "The Triad lowers its weapons. Seventeen witnesses remain, and not one voice has been erased. ORIGIN accepts the Paradox Accord: a shared world may hold more than one possible beginning.",
                       "World DS story complete! Permanent reward unlocked: +20% Paradox scan from every eligible Paradox wild battle win. The bonus follows your account into your other adventures and cannot stack with repeated clears.",
                       "Lyra: We began with one impossible footprint. Now every Paradox partner can leave a trail of its own. Thank you for making room for all of us. The regions and their people will be here whenever you return.",
                   ],
                   "lost": ["The Triad has not accepted the accord yet. All seventeen crests, your quests, and your earlier victories remain safe. Recover with the medic, review your team, and summon the same level 100 trial again."],
                   "repeat": ["The Paradox Accord is complete. Your permanent +20% Paradox wild-victory scan reward is active. The crests remain yours, and the eighteen regions remain open for return visits."]},
                  requires=[region["warden_id"] for region in regions if region["badge"]],
                  required_badges=[region["id"] for region in regions if region["badge"]],
                  team=final_team, display_species="omnimon_paradox", display_level=100,
                  battle_name="Origin Triad",
                  reward={"credits": 50000, "items": {"hp_l": 10, "sp_l": 10},
                          "training_level": 100, "level_floor": 100,
                          "paradox_scan_bonus": 20}, repeatable=True)
    finale["dialogue"]["rematch_won"] = [
        "The Origin Triad honors the accord once more. Your story remains complete, all seventeen crests remain yours, and permanent Paradox Scan Mastery is still active.",
        "This finale replay grants no additional credits, items, experience, or scan multiplier. Return to the world whenever you are ready for your next adventure.",
    ]
    finale["id"] = FINAL_NPC_ID
    add_npc(finale, final_region)

    for npc in npcs.values():
        if npc["tamer"] not in engine.tamers:
            raise ValueError(f"World DS story NPC sprite is missing: {npc['tamer']}")
        for opponent in npc["team"]:
            if opponent["species"] not in engine.species:
                raise ValueError(f"World DS story opponent is missing: {opponent['species']}")
        partner = npc["reward"].get("partner")
        if partner and partner not in engine.species:
            raise ValueError(f"World DS story companion is missing: {partner}")
        for prerequisite in (*npc["requires"], *npc["requires_accepted"], *npc.get("quest_requires", [])):
            if prerequisite not in npcs:
                raise ValueError(f"Unknown World DS story prerequisite: {prerequisite}")
    for opponent in final_team:
        species = engine.species[opponent["species"]]
        if not species.get("paradox") or species.get("stage") != "mega" or opponent["level"] != 100:
            raise ValueError("The Origin Triad must contain exactly three level 100 Paradox Megas")
    result = {"id": CAMPAIGN_ID, "name": CAMPAIGN_NAME, "version": 1,
              "regions": regions, "maps": maps, "npcs": npcs, "challengers": [],
              "champion_id": FINAL_NPC_ID, "final_id": FINAL_NPC_ID,
              "start_map": hub_map, "badge_count": 17,
              "completion_reward": {"paradox_scan_bonus": 20},
              "introduction": "Begin around level 10. Complete seventeen field assignments, earn seventeen Paradox Crests, and face three level 100 Paradox Megas for a permanent +20% Paradox wild-victory scan reward."}
    engine._world_ds_story_content = result
    return result
