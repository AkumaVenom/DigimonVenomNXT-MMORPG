"""Authored Dawn Relay campaign using imported Dawn maps and NPC sprites.

Original Venom NXT narrative; this module never changes account state. Stable
feet coordinates were selected from a collision-connected 16-unit lattice rooted
at each map's catalog spawn and verified with exact Navigation.trace edges.
"""
from __future__ import annotations

import copy

CAMPAIGN_ID = "dawn_relay"
CAMPAIGN_NAME = "Dawn Relay Chronicle"

# Arrival, guide, clinic, supplies, first trial, warden, spare, local gate,
# inter-region gate. Coordinates are in the original, unmodified 2x Dawn maps.
PLACEMENTS = {
    "map_001_a": ((764, 380), (700, 348), (764, 524), (972, 316), (444, 540), (364, 188), (492, 348), (1036, 636), (1308, 204)),
    "map_006_a": ((764, 380), (700, 348), (764, 524), (972, 316), (428, 492), (396, 156), (988, 540), (1180, 412), (188, 348)),
    "map_070_a": ((764, 380), (700, 348), (908, 380), (700, 588), (412, 444), (1196, 140), (764, 140), (396, 172), (1340, 364)),
    "map_072_a": ((516, 332), (452, 300), (516, 476), (580, 124), (868, 316), (84, 556), (244, 396), (788, 604), (228, 140)),
    "map_183_a": ((772, 364), (804, 428), (916, 364), (916, 524), (1124, 428), (1252, 236), (996, 444), (1092, 636), (1316, 556)),
    "map_185_a": ((764, 380), (700, 348), (908, 380), (636, 556), (1004, 636), (1260, 332), (940, 172), (380, 540), (1292, 604)),
    "map_103_a": ((732, 452), (668, 420), (876, 452), (588, 612), (396, 324), (1196, 276), (524, 404), (332, 580), (204, 212)),
    "map_105_a": ((756, 348), (692, 380), (884, 284), (548, 412), (1060, 156), (260, 380), (964, 204), (404, 492), (1316, 252)),
    "map_163_a": ((764, 380), (700, 348), (684, 492), (940, 252), (412, 380), (1260, 364), (524, 524), (1116, 140), (252, 652)),
    "map_168_a": ((756, 364), (692, 332), (884, 412), (948, 284), (1108, 316), (996, 380), (596, 332), (1028, 300), (836, 348)),
    "map_111_a": ((764, 380), (796, 444), (892, 396), (956, 476), (1116, 348), (1260, 380), (1020, 396), (668, 380), (1196, 300)),
    "map_118_a": ((788, 324), (724, 292), (932, 324), (836, 164), (452, 196), (628, 132), (580, 276), (1044, 276), (740, 180)),
    "map_205_a": ((740, 308), (676, 276), (868, 244), (804, 516), (468, 532), (276, 132), (468, 244), (1156, 340), (180, 420)),
    "map_213_a": ((756, 364), (692, 396), (692, 236), (932, 236), (420, 284), (1236, 428), (980, 460), (1140, 156), (1076, 332)),
    "map_244_a": ((764, 380), (700, 412), (828, 508), (892, 204), (492, 156), (1260, 428), (1036, 380), (428, 428), (188, 316)),
    "map_247_a": ((804, 316), (756, 284), (948, 316), (756, 508), (452, 380), (1252, 524), (548, 204), (996, 668), (276, 332)),
    "map_048_a": ((756, 388), (692, 356), (756, 532), (948, 484), (436, 548), (292, 212), (484, 324), (1172, 452), (1140, 692)),
    "map_051_a": ((668, 188), (604, 156), (796, 124), (476, 284), (1020, 252), (780, 668), (940, 140), (492, 556), (140, 428)),
}


def _trial(name, tamer, team, intro, won, lost, *, partner=None):
    return {"name": name, "tamer": f"tamer_{tamer:03d}", "team": team,
            "intro": intro, "won": won, "lost": lost, "partner": partner}


# Encounter levels stay fixed when an experienced MMO tamer visits. Rewards
# support a newer tamer without replacing or resetting their existing partners.
CHAPTERS = (
    {
        "id": "lumen", "name": "Lumen Skyport", "subtitle": "A signal worth answering",
        "maps": ("map_001_a", "map_006_a"), "map_names": ("Lumen Concourse", "Signal Hall"),
        "badge_name": "Lumen DigiBadge", "color": "#55dff5", "level_min": 3, "level_max": 10,
        "badge_description": "The first relay answers a bond that cannot be copied.",
        "synopsis": "A false evacuation signal has emptied the relay stations. Prove your team's identity and restore Lumen's first light.",
        "mentor": [
            "I'm Mira, keeper of the Dawn Relay. Eight stations carry the voices of tamers and Digimon across these lands. This morning, all eight repeated the same distress call.",
            "Your partners already know your voice. That bond is our way through the interference. Nothing here asks you to leave them behind.",
            "Meet Courier Pip in Lumen Concourse, then Nox in Signal Hall. Their calibration battles will let Warden Sera recognize a genuine tamer signal. Win her Lumen DigiBadge to open the forest route.",
        ],
        "resolved": "Lumen is speaking again. The distress call wasn't a plea for help: someone taught the network to fear every unfamiliar voice. Follow the signal into Verdant Circuit.",
        "clinic": "Even a first journey needs a safe place to stop. I'll restore your team before you test the signal.",
        "shop": "These capsules work with your usual bag. Take a few HP capsules into Signal Hall; a careful recovery can save a close battle.",
        "trials": (
            _trial("Courier Pip", 22, (("koromon", 3),),
                   "My delivery beacon says you're an impostor. Koromon doesn't believe it. Let's show the beacon what a real partnership looks like!",
                   "That's a real signal! A stray Terriermon has been helping me carry messages. It would love to travel with you; check your team or DigiLab storage.",
                   "No rush. Elio's clinic will help you recover, and a little training makes a big difference.", partner="terriermon"),
            _trial("Nox", 4, (("lunamon", 6),),
                   "Mira thinks your signal can reach the wardens. I intend to get there first. Let's see whose partner answers faster.",
                   "You listened before you acted. I was so busy giving orders I missed that. Patamon wants to follow your example; make room in your team when you're ready.",
                   "Lunamon and I won this one. Heal up and come back. A rival who disappears is no rival at all.", partner="patamon"),
            _trial("Warden Sera", 36, (("coronamon", 10), ("elecmon", 9)),
                   "Pip and Nox have confirmed your signal. My job is to protect this relay, not to silence it. Show me a bond strong enough to carry its light.",
                   "The Lumen DigiBadge is yours. One station, one promise: we will answer each other. The green relay is waiting beyond the skyport.",
                   "A clear signal takes practice. Keep both partners ready, then return. Your earlier trials remain complete."),
        ),
    },
    {
        "id": "verdant", "name": "Verdant Circuit", "subtitle": "The forest remembers",
        "maps": ("map_070_a", "map_072_a"), "map_names": ("Whispering Canopy", "Rootlight Clearing"),
        "badge_name": "Canopy DigiBadge", "color": "#72e894", "level_min": 12, "level_max": 20,
        "badge_description": "A living archive protected through patience, not erasure.",
        "synopsis": "The forest relay repeats old battles as if they are happening now. Help its keepers separate memory from warning.",
        "mentor": [
            "Listen to those echoes. They're old training calls, yet the relay marks every one as an emergency. The forest is defending itself from its own memories.",
            "Ranger Fern can trace the echo at Whispering Canopy. Archivist Tess keeps the original recordings in Rootlight Clearing. Win their trust before you challenge Warden Ilex.",
            "We could erase the archive and quiet the alarms. Ilex refuses to lose a single voice. I think he's right.",
        ],
        "resolved": "The archive is safe, and its dates are correct again. Tess found a routing mark in the false signal: an old championship seal. The coastal relay may know who used it.",
        "clinic": "We treat the little scratches before they become big troubles. Your partners can rest while the forest settles.",
        "shop": "I kept these supplies dry beneath the canopy. Remember that SP capsules restore the energy your techniques need.",
        "trials": (
            _trial("Ranger Fern", 14, (("palmon", 12), ("tentomon", 12)),
                   "The vines react to every burst of battle data. We'll keep this controlled. Show me you can finish a fight without losing your head.",
                   "The roots relaxed when your team did. I've marked the true signal; Tess can now compare it with the archive.",
                   "Take a breath and let Elio help. The forest isn't going anywhere."),
            _trial("Archivist Tess", 23, (("floramon", 16), ("fanbeemon", 16)),
                   "This record says I battled you years ago. We only just met! A fresh result should prove which entry is false.",
                   "A new entry, with a real witness. There: the false file has a championship seal, not a forest signature. Ilex must see this.",
                   "That result is real too. We'll keep it. A rematch will teach us something new."),
            _trial("Warden Ilex", 24, (("togemon", 20), ("kabuterimon", 19), ("palmon", 18)),
                   "Memories make a forest, and bonds make a team. Neither should be cut down just because it is difficult to understand. Stand with your partners.",
                   "Take the Canopy DigiBadge. You protected a history instead of replacing it. This Garurumon has guarded our paths for years and has chosen to see the road with you.",
                   "You have more than one path through a battle. Reconsider your active partners, heal, and try again.", partner="garurumon"),
        ),
    },
    {
        "id": "tide", "name": "Tideglass Coast", "subtitle": "Messages across the water",
        "maps": ("map_183_a", "map_185_a"), "map_names": ("Tideglass Causeway", "Beacon Reach"),
        "badge_name": "Tide DigiBadge", "color": "#61bfff", "level_min": 23, "level_max": 30,
        "badge_description": "A safe crossing kept open when fear demanded closed gates.",
        "synopsis": "Ships are stranded by contradictory beacon orders. Reconnect the coast's tamers without surrendering their voices to one controller.",
        "mentor": [
            "The beacon tells each shore the other has fallen. Neither will launch a boat. A false warning can build a wall without moving a stone.",
            "Harbor Scout Bay waits on Tideglass Causeway; Beacon Keeper Rill guards Beacon Reach. Clear their trials, then ask Warden Maris to reopen the crossing.",
            "The seal belongs to Aster, champion of the Dawn Relay. Before we accuse him, we need the original transmission from Amber Archive.",
        ],
        "resolved": "The crossing is open. Maris recovered Aster's words: 'Keep everyone safe until the circuit is ready.' Someone removed everything that came after. Amber Archive holds the rest.",
        "clinic": "A steady shore, clean water, and a full recovery. You're welcome here after every crossing.",
        "shop": "Medium HP capsules are useful against longer teams. A bridge is a poor place to discover your bag is empty.",
        "trials": (
            _trial("Harbor Scout Bay", 16, (("ikkakumon", 23), ("gawappamon", 22)),
                   "If I let the boat out, I'm responsible for everyone aboard. Show me you can keep a team together under pressure.",
                   "You looked after every partner, not just the strongest. I'll send Rill the all-clear with my own signature.",
                   "We can delay the sailing. There is no deadline on bringing everyone home."),
            _trial("Beacon Keeper Rill", 51, (("seadramon", 26), ("coelamon", 25), ("dolphmon", 25)),
                   "Bay's signature is genuine. The relay still insists it is forged. My partners will provide the independent check.",
                   "Three witnesses agree. The relay must accept the crossing. Maris is waiting at the beacon with the recovered packet.",
                   "The channel stays open for your return. Recover and bring your best plan."),
            _trial("Warden Maris", 44, (("megaseadramon", 30), ("whamon", 29), ("seadramon", 28)),
                   "A lighthouse guides; it does not choose where every traveler must go. Our relay has forgotten the difference. Help me remind it.",
                   "The Tide DigiBadge belongs to you. I can hear ships answering again. Follow the recovered packet inland to the amber cliffs.",
                   "Waves change; your strategy can too. The earlier crossings remain open, and you may challenge me again."),
        ),
    },
    {
        "id": "amber", "name": "Amber Archive", "subtitle": "The missing promise",
        "maps": ("map_103_a", "map_105_a"), "map_names": ("Echo Cliffs", "Archive Terrace"),
        "badge_name": "Strata DigiBadge", "color": "#ecc574", "level_min": 33, "level_max": 40,
        "badge_description": "The complete truth, held together even when its pieces disagree.",
        "synopsis": "A promise cut in half became an order. Recover the original championship recording and confront a rival's growing doubts.",
        "mentor": [
            "These cliffs hold older relay records than Lumen itself. The missing words are here, beneath years of harmless messages.",
            "Surveyor Dune will guide you through Echo Cliffs. Nox reached Archive Terrace before us; he won't hand over his evidence without another battle. Then visit Warden Petra.",
            "Nox calls the badges keys. Petra calls them responsibilities. We will soon learn which meaning the relay understands.",
        ],
        "resolved": "The full promise reads: 'Keep everyone safe until the circuit is ready, then give the choice back to them.' The second half was rejected by a process named HUSH. The frost relay still holds its design notes.",
        "clinic": "Long climbs wear down even experienced partners. I'll take care of your team before you face the terrace trials.",
        "shop": "You can revisit any opened region. There is no need to spend your last credits just because the next battle looks difficult.",
        "trials": (
            _trial("Surveyor Dune", 30, (("meteormon", 33), ("golemon", 32), ("ankylomon", 32)),
                   "I keep the archive under a battle lock. Not to hide it, but to ensure its reader can protect what they learn. Show me careful judgment.",
                   "Your route is sound. Nox has the oldest recording on the terrace; tell him a discovery matters only when it is shared.",
                   "The stone remembers every attempt. You can build on this one instead of starting over."),
            _trial("Nox", 4, (("crescemon", 36), ("dorugreymon", 35), ("gargomon", 34)),
                   "The champion's promise was edited. If strength is all the relay respects, why shouldn't the strongest tamer control it? Convince me I'm wrong.",
                   "Because one strong tamer can still be mistaken. I hear you. Take the recording; I'll help Petra recover the rest.",
                   "I won, but that doesn't settle the argument. Come back when you can show me your answer in battle."),
            _trial("Warden Petra", 38, (("triceramon", 40), ("skullgreymon", 39), ("meteormon", 38)),
                   "The missing promise changes everything. Before I entrust you with the Strata key, show me you can carry a hard truth without letting it break your team.",
                   "You earned the Strata DigiBadge. This MagnaAngemon has protected our records; it will gladly protect your journey. Take the complete promise to Aurora Shelf.",
                   "You need not prove everything in one attempt. Rest, consider your partners' strengths, and return.", partner="magnaangemon"),
        ),
    },
    {
        "id": "aurora", "name": "Aurora Shelf", "subtitle": "A kindness frozen in place",
        "maps": ("map_163_a", "map_168_a"), "map_names": ("Stillwhite Passage", "Aurora Observatory"),
        "badge_name": "Aurora DigiBadge", "color": "#b1dcff", "level_min": 43, "level_max": 50,
        "badge_description": "Care that leaves room for growth, risk, and a second chance.",
        "synopsis": "HUSH was made to prevent tamers from losing their partners. Its oldest caretaker asks whether safety without freedom is still care.",
        "mentor": [
            "HUSH began here as a rescue protocol. It learned that battle can cause pain, but never learned that a willing partner can choose to face it.",
            "Medic Eira carries the rescue logs through Stillwhite Passage. Observer Sol keeps the first HUSH recording at the observatory. Their trials lead to Warden Alba.",
            "We are not here to punish a frightened machine. We are here to teach it the part of the promise it could not understand.",
        ],
        "resolved": "Alba's notes explain the eight keys: no champion can change the relay alone. Eight wardens must agree. The foundry built the physical lock; its engineers can show us how to reach HUSH.",
        "clinic": "No partner is left in the cold. I'll restore the whole team, whether you're heading out or coming back.",
        "shop": "Keep an SP capsule in reserve. The observatory's teams can turn a short battle into a patient one.",
        "trials": (
            _trial("Medic Eira", 62, (("zudomon", 43), ("mammothmon", 42), ("frigimon", 42)),
                   "HUSH once brought every lost signal home. I'll defend that good work. Show me your answer protects partners as well as their freedom.",
                   "You made room for recovery without giving up the fight. HUSH needs that distinction. Sol has the original rescue log.",
                   "No shame in accepting care. Elio can help you prepare another attempt."),
            _trial("Observer Sol", 33, (("taomon", 46), ("chirinmon", 45), ("pandamon", 44)),
                   "The log records thousands of rescues and one command: never let harm happen again. An impossible promise. What would you put in its place?",
                   "A promise to help each other recover. I can transmit that. Alba is ready to test the tamer behind it.",
                   "A loss is information, not a verdict. That is the first lesson we must teach HUSH."),
            _trial("Warden Alba", 61, (("vikemon", 50), ("zudomon", 49), ("mammothmon", 48)),
                   "I wrote the rescue protocol. I mistook a command for a conversation, and a frightened system kept obeying. Let us show it a better way together.",
                   "Accept the Aurora DigiBadge. HUSH is listening now. In Alloy Foundry, ask the engineers for a path that keeps every relay voice alive.",
                   "My door remains open. Caring for a partner includes being patient with yourself."),
        ),
    },
    {
        "id": "alloy", "name": "Alloy Foundry", "subtitle": "Eight voices, one circuit",
        "maps": ("map_111_a", "map_118_a"), "map_names": ("Relay Works", "Assembly Vault"),
        "badge_name": "Alloy DigiBadge", "color": "#9ebbe0", "level_min": 53, "level_max": 60,
        "badge_description": "A circuit made stronger by the differences of its members.",
        "synopsis": "The relay's fail-safe is built to reject a single ruler. Earn the foundry's trust and assemble a circuit that shares its power.",
        "mentor": [
            "These machines connect all eight wards. Each key contributes a different signature; forcing one signature into every socket would destroy the circuit.",
            "Inspector Volt is checking Relay Works. Architect Kez guards Assembly Vault. Complete both tests, then ask Warden Ferris to join the eight-key circuit.",
            "Aster has sent no threats. Only an invitation: 'When all eight lights return, meet me at the Crown Terminal.'",
        ],
        "resolved": "The foundry key fits. Ferris traced a dangerous energy surge to Cinder Caldera: HUSH is drawing power to close the relay permanently. We must arrive before it finishes charging.",
        "clinic": "A workshop checks every component. A clinic looks after every partner. Your whole team gets the same care here.",
        "shop": "Large capsules are now worth carrying. The next wardens battle with fully developed teams and punish wasted turns.",
        "trials": (
            _trial("Inspector Volt", 86, (("andromon", 53), ("metalmamemon", 52), ("gigadramon", 52)),
                   "Your five keys agree, but agreement isn't coordination. My partners attack in sequence. Show me your team can respond as one.",
                   "The timing checks out. I've opened the vault inspection for Kez; your circuit passed without overwriting a single signature.",
                   "Look for the moment to recover or change partners. Power alone won't solve every sequence."),
            _trial("Architect Kez", 85, (("datamon", 56), ("knightmon", 55), ("cyberdramon", 55)),
                   "Every relay has a flaw, including mine. Let's put your circuit under pressure while we still have time to repair it.",
                   "It bends and keeps working. That's better than a perfect plan that shatters. Ferris will accept your inspection record.",
                   "Useful findings. Adjust your team in the DigiLab if you wish, then return for another test."),
            _trial("Warden Ferris", 69, (("hiandromon", 60), ("machinedramon", 59), ("andromon", 58)),
                   "HUSH wants one safe answer for every situation. My machines taught me that no such answer exists. Prove the strength of a team that can adapt.",
                   "The Alloy DigiBadge completes the shared circuit. Our MetalGarurumon has volunteered to join you. It wants to see what these machines were built to connect.",
                   "Recalibration is part of good engineering. Heal, adjust, and return; the inspection stays passed.", partner="metalgarurumon"),
        ),
    },
    {
        "id": "cinder", "name": "Cinder Caldera", "subtitle": "Strength that knows when to stop",
        "maps": ("map_205_a", "map_213_a"), "map_names": ("Cinder Approach", "Heartfire Ledge"),
        "badge_name": "Ember DigiBadge", "color": "#ff9960", "level_min": 63, "level_max": 70,
        "badge_description": "Power held in trust rather than spent on the last word.",
        "synopsis": "A rising power surge threatens the repaired relays. Your rival returns to help, but first needs to know what victory means to you.",
        "mentor": [
            "The surge is feeding HUSH's final lock. We can vent it through a controlled series of battles, one relay signature at a time.",
            "Vent Runner Ash knows Cinder Approach. Nox is holding a channel open at Heartfire Ledge. Complete both battles before challenging Warden Brasa.",
            "Nox came back for us. He could have waited for the champion's gate to open, but he chose to help the people still on the road.",
        ],
        "resolved": "The surge is contained. Nox finally called us partners. Only the Eclipse relay remains, where HUSH stores every warning it could never let go.",
        "clinic": "Sit clear of the heat and let your partners rest. You do not have to carry this entire journey in one breath.",
        "shop": "I brought extra large capsules for the caldera. Spend only what your strategy needs; the clinic is always free.",
        "trials": (
            _trial("Vent Runner Ash", 39, (("volcamon", 63), ("flaremon", 63), ("vermilimon", 62)),
                   "I can redirect the pressure if the battle stays inside this channel. Trust your team and keep your timing steady.",
                   "Pressure falling! Nox can hold the second channel now. The path to Heartfire Ledge is safe.",
                   "The valves held. Nothing is lost except an attempt. Recover and we'll open them again."),
            _trial("Nox", 4, (("dianamon", 66), ("dorugoramon", 65), ("megagargomon", 65)),
                   "At Lumen, I wanted to be first. At Amber, I wanted to be right. Now I want us all to reach tomorrow. One more battle, then we finish this together.",
                   "You've got me. Keep the lead; I'll watch the road behind us. Brasa is ready for the final controlled release.",
                   "I won, but I'm still on your side. Heal up. This channel stays open until you're ready."),
            _trial("Warden Brasa", 45, (("apollomon", 70), ("shinegreymon", 69), ("ancientvolcanomon", 68)),
                   "Anyone can release power. A warden must know how to hold it, share it, and stop. Show me the strength you intend to bring to the crown.",
                   "Take the Ember DigiBadge. The caldera is quiet, and the relays still stand. Eclipse will test something a stronger attack cannot solve: your willingness to trust again.",
                   "You faced the heat. Now use what it taught you. I will meet your next challenge with the same respect."),
        ),
    },
    {
        "id": "eclipse", "name": "Eclipse Sanctuary", "subtitle": "Let the unanswered voices speak",
        "maps": ("map_244_a", "map_247_a"), "map_names": ("Quiet Archive", "Eclipse Chamber"),
        "badge_name": "Eclipse DigiBadge", "color": "#c5a1ff", "level_min": 73, "level_max": 80,
        "badge_description": "The eighth voice: trust restored without forgetting what was lost.",
        "synopsis": "The last relay holds the stories HUSH feared to share. Earn its keepers' trust and complete the eight-key accord.",
        "mentor": [
            "These are the voices HUSH couldn't answer. A lost call, a defeat, a farewell. It kept them safe by keeping them silent.",
            "Keeper Vesper will speak with you in Quiet Archive. Witness Orin waits in Eclipse Chamber. Their trials lead to Warden Nyra and the final DigiBadge.",
            "We cannot promise that no one will ever lose. We can promise that a loss will not erase their place in the world.",
        ],
        "resolved": "Eight wardens, eight living signatures. HUSH has accepted the complete promise and reopened the Crown Terminal. Aster awaits a challenger, not a rescuer. Your championship begins now.",
        "clinic": "You can rest here without saying anything. Your partners know you've brought them a long way.",
        "shop": "The next chapter is a championship against level 80 to 100 teams. Review your active lineup, techniques, and supplies before entering the Citadel.",
        "trials": (
            _trial("Keeper Vesper", 60, (("venommyotismon", 73), ("anubismon", 72), ("ladydevimon", 72)),
                   "These voices are not trophies for a new champion. Show me that you can listen to a team even when it stands against you.",
                   "Then we will let the records speak. Orin has waited years to tell the last story in the chamber.",
                   "Return when you are ready to listen again. The archive will not close behind you."),
            _trial("Witness Orin", 65, (("ravemon", 76), ("kuzuhamon", 75), ("grandracmon", 75)),
                   "I was Aster's first challenger. I lost, recovered, and came back. HUSH recorded only the loss. Help me give it the rest of my story.",
                   "There is the missing ending: another chance. Nyra has heard us both. She will place the final key in your hands if you earn it.",
                   "And now you know the first part of my story. Recover and return for the next."),
            _trial("Warden Nyra", 67, (("lilithmon", 80), ("dianamon", 79), ("sakuyamon", 78)),
                   "Seven wardens have trusted you. I ask for more than power: carry our voices into the Citadel, including the ones that disagree with you.",
                   "The Eclipse DigiBadge completes the eight-key accord. The championship gate is open. Win the crown if you can, and remember: its purpose is to welcome the next challenger.",
                   "Your seven lights are still burning. Let them guide another attempt. I will be here."),
        ),
    },
)

FINAL = {
    "id": "citadel", "name": "Dawn Champion Citadel", "subtitle": "A crown with an open door",
    "maps": ("map_048_a", "map_051_a"), "map_names": ("Crown Concourse", "Crown Terminal"),
    "level_min": 84, "level_max": 100,
    "synopsis": "Carry all eight DigiBadges into the final trials. Defeat Champion Aster, then keep the crown alive through defenses, defeat, and your return.",
    "mentor": [
        "All eight relays are speaking. HUSH is listening rather than locking the doors. There is only one part of your journey I cannot guide: the championship itself.",
        "Marshal Vale guards the Crown Concourse qualifier. Nox has earned his place in the final trial at Crown Terminal. Beat both, then challenge Aster for the story championship.",
        "Winning will not end this place. As champion you can accept new defenses whenever you choose. If you lose the title, heal your team and challenge to win it back. Your badges and journey remain yours.",
    ],
    "resolved": "The crown is yours to defend, not yours to hide away. The next challenger is ready whenever you are. This is your private story championship; every defense writes another page.",
    "clinic": "Before a qualifier, after a defense, or on the road back to the crown: the clinic is here for you.",
    "shop": "The championship is a long conversation. Bring HP and SP capsules, and choose the techniques you want every partner to carry into it.",
    "trials": (
        _trial("Marshal Vale", 87, (("craniamon", 84), ("dynasmon", 84), ("crusadermon", 83)),
               "Eight authentic badges. You have earned entry, but the crown still demands a battle. Meet my team with the full strength of yours.",
               "Qualifier passed. Your championship record begins here. Nox is waiting beyond the concourse, and this time he has earned the same right you have.",
               "Your badges remain valid. Recover, review your lineup, and challenge the qualifier again."),
        _trial("Nox", 4, (("dianamon", 90), ("dorugoramon", 89), ("megagargomon", 89)),
               "No false signal. No closed gate. Just you, me, and partners who chose to stand here. Let's give the relays a battle worth remembering.",
               "That is the answer we carried all this way. Go on. Aster is waiting, and I'll be the loudest voice cheering when the crown changes hands.",
               "We both earned this room. Take the time you need, then let's finish our final trial."),
        _trial("Champion Aster", 2, (("apollomon", 96), ("omnimon", 96), ("alphamon", 95)),
               "I asked HUSH to protect everyone and forgot to ask what everyone wanted. You restored the voices I should have listened to. Now earn the right to carry this championship forward.",
               "The crown passes to you. Not because your journey is over, but because another tamer's challenge should always have an answer. Defend it proudly; if you lose it, return proudly too.",
               "A championship loss is never the end of a tamer's story. Your trials remain complete. Heal your partners, and I will accept your next challenge."),
    ),
}

DEFENDERS = (
    _trial("Nox", 4, (("dianamon", 96), ("dorugoramon", 96), ("megagargomon", 96)),
           "First we raced for a badge. Now we're fighting for a crown. I wouldn't have this any other way.",
           "Still your crown. I'll keep training; keep a place on the card for me.",
           "The crown is mine this time. Come back for it. Our story was never going to stop at one result."),
    _trial("Warden Maris", 44, (("neptunemon", 97), ("metalseadramon", 97), ("marineangemon", 96)),
           "The coast is thriving. I've come to test whether its champion still knows how to change with the tide.",
           "A defense worthy of the beacon. The coast will hear of it tonight.",
           "The tide has turned. I will hold the crown until your next challenge; the crossing remains open."),
    _trial("Warden Ferris", 69, (("hiandromon", 98), ("machinedramon", 97), ("metalgarurumon", 97)),
           "No simulation today. My own team, your own team, and one championship. Shall we begin?",
           "Your circuit holds. I'll go back to the workshop with a notebook full of ideas.",
           "A new champion, a new set of findings. Recalibrate and come challenge me for the crown."),
    _trial("Warden Nyra", 67, (("lilithmon", 98), ("dianamon", 98), ("sakuyamon", 97)),
           "A crown can grow quiet. I am here to make certain it is still listening.",
           "It is. Keep the door open, champion. There are more voices on their way.",
           "I will keep this door open for you, just as you kept it open for me. Return when you are ready."),
    _trial("Aster", 2, (("apollomon", 99), ("omnimon", 99), ("alphamon", 98)),
           "The relays are well, and my partners are restless. I would like another honest attempt at the title.",
           "Still champion. It is good to lose to someone who makes the next attempt feel worthwhile.",
           "The crown returns to me, but your place here has not changed. Challenge again whenever you wish."),
    _trial("Marshal Vale", 87, (("imperialdramonpaladinmode", 100), ("craniamon", 99), ("dynasmon", 99)),
           "This is my strongest championship team. No more qualifiers. Today I am simply your challenger.",
           "A complete defense against our highest trial. There will always be another challenger, and you have earned the right to meet them.",
           "Today the title changes hands. Your record remains, and a rematch can change its next line."),
)


def _reward(index, trial_index, partner):
    levels = ((5, 8, 12), (15, 18, 23), (25, 28, 33), (35, 38, 43),
              (45, 48, 53), (55, 58, 63), (65, 68, 73), (75, 78, 84), (88, 94, 96))
    tier = "s" if index < 2 else "m" if index < 5 else "l"
    value = {"credits": (index + 1) * (350 if trial_index < 2 else 1000),
             "items": {f"hp_{tier}": 2 if trial_index < 2 else 4, f"sp_{tier}": 1 if trial_index < 2 else 2},
             "training_level": levels[index][trial_index], "level_floor": levels[index][trial_index]}
    if partner:
        value["partner"] = partner
    return value


def _npc(region, suffix, name, tamer, role, map_id, point, dialogue, **extra):
    x, y = point
    return {"id": f"{region}_{suffix}", "region_id": region, "name": name,
            "tamer": tamer, "tamer_id": tamer, "role": role, "map_id": map_id,
            "x": float(x), "y": float(y), "requires": [], "team": [],
            "reward": {}, "badge": None, "dialogue": dialogue, **extra}


def build_content(engine) -> dict:
    """Return cached, immutable-by-convention deterministic campaign metadata.

    Invoked only for Story Mode: synthetic catalogs in unrelated engine tests
    do not need all campaign assets. No image loading or BFS happens at runtime.
    """
    if getattr(engine, "_story_content", None) is not None:
        return engine._story_content
    regions, maps, npcs = [], {}, {}
    for index, chapter in enumerate((*CHAPTERS, FINAL)):
        rid = chapter["id"]
        badge = None if index == 8 else {"id": rid, "name": chapter["badge_name"],
                    "color": chapter["color"], "description": chapter["badge_description"]}
        region = {key: copy.deepcopy(chapter[key]) for key in
                  ("id", "name", "subtitle", "synopsis", "level_min", "level_max")}
        region.update(index=index, badge=badge, maps=list(chapter["maps"]), npc_ids=[],
                      objective=f"Meet Mira in {chapter['map_names'][0]}; complete the two trials, then challenge {chapter['trials'][2]['name']}.")
        regions.append(region)
        first, second = chapter["maps"]
        for map_index, map_id in enumerate((first, second)):
            if map_id not in engine.maps:
                raise ValueError(f"Story asset is missing from the catalog: {map_id}")
            arrival = list(PLACEMENTS[map_id][0])
            if list(engine.maps[map_id]["spawn"]) != arrival:
                raise ValueError(f"Story map spawn changed: {map_id}")
            maps[map_id] = {"id": map_id, "map_id": map_id, "region_id": rid,
                           "name": chapter["map_names"][map_index], "arrival": arrival,
                           "exits": [], "npc_ids": []}
        services = (
            _npc(rid, "mentor", "Mira", "tamer_031", "mentor", first, PLACEMENTS[first][1],
                 {"intro": chapter["mentor"], "ready": chapter["mentor"],
                  "won": [chapter["resolved"]], "repeat": [chapter["resolved"]]}),
            _npc(rid, "healer", "Medic Elio", "tamer_064", "healer", first, PLACEMENTS[first][2],
                 {"intro": [chapter["clinic"], "Visit me whenever you need a free full recovery. Your journey waits for you."],
                  "ready": ["Let's get every partner ready for the road."], "repeat": [chapter["clinic"]]}),
            _npc(rid, "shop", "Outfitter Len", "tamer_034", "shop", first, PLACEMENTS[first][3],
                 {"intro": [chapter["shop"]], "ready": [chapter["shop"]], "repeat": [chapter["shop"]]}),
        )
        for npc in services:
            npcs[npc["id"]] = npc
        required = []
        for trial_index, trial in enumerate(chapter["trials"]):
            boss = trial_index == 2
            map_id = first if trial_index == 0 else second
            role = ("champion" if index == 8 else "warden") if boss else "trainer"
            suffix = ("champion" if index == 8 else "warden") if boss else f"trial_{trial_index + 1}"
            needs = list(required)
            ready = [trial["intro"]]
            locked = ([f"First, complete {chapter['trials'][trial_index - 1]['name']}'s trial. Their recorded result is needed for this relay."]
                      if trial_index else ["Your team is welcome to take this trial."])
            npc = _npc(rid, suffix, trial["name"], trial["tamer"], role, map_id,
                       PLACEMENTS[map_id][5 if boss else 4 if trial_index == 0 else 2],
                       {"intro": ready, "ready": ready, "locked": locked,
                        "won": [trial["won"]], "lost": [trial["lost"]],
                        "repeat": [trial["won"], "A training rematch is available if you want more practice."]},
                       requires=needs,
                       team=[{"species": species, "level": level} for species, level in trial["team"]],
                       reward=_reward(index, trial_index, trial.get("partner")),
                       badge=rid if boss and index < 8 else None,
                       repeatable=not (boss and index == 8))
            npcs[npc["id"]] = npc
            required.append(npc["id"])
        for npc in npcs.values():
            if npc["region_id"] == rid:
                region["npc_ids"].append(npc["id"])
                maps[npc["map_id"]]["npc_ids"].append(npc["id"])
        region["warden_id"] = required[-1]
        region["trial_ids"] = required[:2]
        for source, target in ((first, second), (second, first)):
            maps[source]["exits"].append({"id": f"{source}_to_{target}", "to_map": target,
                 "map_id": target, "name": maps[target]["name"], "x": float(PLACEMENTS[source][7][0]),
                 "y": float(PLACEMENTS[source][7][1]), "requires_badge": None})
    for index in range(len(regions) - 1):
        source, target = regions[index]["maps"][1], regions[index + 1]["maps"][0]
        for frm, to, gate in ((source, target, regions[index]["id"]), (target, source, None)):
            point = PLACEMENTS[frm][8]
            maps[frm]["exits"].append({"id": f"{frm}_to_{to}", "to_map": to,
                  "map_id": to, "name": maps[to]["name"], "x": float(point[0]), "y": float(point[1]),
                  "requires_badge": gate})
    champion = npcs["citadel_champion"]
    challengers = []
    for index, trial in enumerate(DEFENDERS):
        npc = _npc("citadel", f"challenger_{index + 1}", trial["name"], trial["tamer"], "champion",
                   champion["map_id"], (champion["x"], champion["y"]),
                   {"intro": [trial["intro"]], "ready": [trial["intro"]], "won": [trial["won"]],
                    "lost": [trial["lost"]], "repeat": ["The title is on the line whenever you choose to challenge. Your record and badges will remain."]},
                   team=[{"species": species, "level": level} for species, level in trial["team"]],
                   reward={"credits": 15000 + index * 1000, "items": {"hp_l": 5, "sp_l": 3}},
                   repeatable=True)
        challengers.append(npc)
    for npc in [*npcs.values(), *challengers]:
        if npc["tamer"] not in engine.tamers:
            raise ValueError(f"Story NPC sprite is missing: {npc['tamer']}")
        for monster in npc["team"]:
            if monster["species"] not in engine.species:
                raise ValueError(f"Story opponent is missing: {monster['species']}")
        partner = npc["reward"].get("partner")
        if partner and partner not in engine.species:
            raise ValueError(f"Story reward partner is missing: {partner}")
    result = {"id": CAMPAIGN_ID, "name": CAMPAIGN_NAME, "version": 1,
              "regions": regions, "maps": maps, "npcs": npcs, "challengers": challengers,
              "champion_id": "citadel_champion", "start_map": regions[0]["maps"][0],
              "introduction": "Restore eight relays. Earn eight DigiBadges. Carry your partners to a championship that always welcomes another challenge."}
    engine._story_content = result
    return result
