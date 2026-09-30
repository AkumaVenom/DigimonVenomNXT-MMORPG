"""Original cyber-detective campaign: Super Xros: Ghostline.

All dialogue is authored for Venom NXT. The supplied Super Xros maps provide
scenery; neither their canonical locations nor another game's plot are claimed.
Story metadata is account-independent; the runtime owns every player's evidence,
quests, encounters, reveal and permanent completion reward.
"""
from __future__ import annotations

from venom.common.xros_story_layout import CAMPAIGN_MAPS, PLACEMENTS

CAMPAIGN_ID = "xros_ghostline"
CAMPAIGN_NAME = "Super Xros: Ghostline"
FINAL_NPC_ID = "ghost_final_regent"
MARA_CHARACTER_ID = "mara_vale"
REVEAL_QUEST_ID = "ghost_26_quest"
# Sixteen field appearances plus the hub. The last appearance is the actual boss.
MARA_FIELDS = (1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30)


def _chapter(name, title, level, giver, trainer, team, brief, task, report,
             challenge, victory, loss, recovery, after, intel=""):
    return dict(name=name, quest=title, level=level, giver=giver, trainer=trainer,
                team=team, brief=brief, task=task, report=report,
                challenge=challenge, victory=victory, loss=loss,
                recovery=recovery, after=after, intel=intel)


# Fields 1..30 follow the safe hub, giving exactly 31 campaign maps. Each
# witness has a reason to battle; losses never erase evidence or partner agency.
CHAPTERS = (
    _chapter("Handshake Lane", "The receipt nobody sent", 3,
        "Analyst Jun", "Courier Niko", ("kapurimon",),
        "Niko delivered a parcel that his route log says never existed. Its receipt bears a blank crown: the calling card of a hacker called the Null Regent. Mara sent us because Niko trusts a witnessed partner battle more than an unsigned request for his records.",
        "Accept the case, then win Niko's level 3 verification battle. He has agreed to release the delivery receipt afterward. Bring it back to me; Mara's recovery handshake should keep his terminal safe while I decode our first destination.",
        "The receipt points to a repair kiosk. Niko's terminal briefly opened a second connection after the battle, but the delivery record is intact. Mara calls it a recovery check. I have kept the original timestamp, just in case. Our first portal can open now.",
        "Kapurimon remembers that parcel too. We aren't suspects you can push around, but we did agree to a fair verification battle. Win, and I'll give Jun the receipt exactly as I found it. Please keep my customers' names out of the report.",
        "Fair win. Here is the receipt. Wait... my terminal says I accepted a remote session. I didn't touch that button. Mara's message says to let the recovery handshake finish. Take the receipt to Jun; I'll keep Kapurimon beside me until this clears.",
        "Kapurimon kept the route! Your case stays open. Ask the medic for a free recovery, then come back when your partners are ready. I promised a fair test, and that includes another attempt.",
        "I'm here, but the route display keeps choosing my next stop before I do. Kapurimon can still hear me. Tell Jun about that extra connection; I don't want a helpful little check to become a permanent passenger.",
        "My route belongs to me again. Kapurimon and I chose our first delivery together: real messages from the people you helped, addressed to the Backchannel. We kept the strange receipt too. Evidence matters, even after the case is closed.",
        "You handled Niko carefully. That matters in my line of work: a frightened witness closes every door. Bring Jun the receipt before following the signal. I will watch the recovery connection. If the Regent reaches for Niko again, I intend to see it."),
    _chapter("Packet Exchange", "A crown in the repair queue", 6,
        "Analyst Jun", "Kiosk Technician Lio", ("hagurumon",),
        "The parcel's destination was Lio's repair kiosk. Someone planted the blank crown inside a routine update. Lio has isolated the file, but the kiosk only exports its audit after a local partner test. He wants a witness who cannot be edited out later.",
        "Lio agreed to a level 6 test with Hagurumon. Accept the investigation, win the battle, and bring back the sealed repair log. Do not install the suspect update. We only need its delivery route and the time it reached his kiosk.",
        "The update crossed the municipal relay under a valid service ticket. Another recovery connection appeared immediately after Lio's test. Mara thinks our target is shadowing us. I have stored both timings separately; a theory should never replace the evidence beneath it.",
        "Hagurumon tests every repair with me. Today you're the independent witness. We will run a real battle, stop when it is decided, and export the audit without opening that crown-marked file. That is the agreement; let's keep all three parts.",
        "Audit sealed. My tools just switched to remote control... that's not part of our agreement. Hagurumon, stay with me. Jun needs this log while I disconnect the workshop arms. Whoever is watching us is getting frighteningly close.",
        "The test ended safely. Recover your partners, check their techniques, and try again when you like. Neither Hagurumon nor I needs anyone injured to prove a repair record is genuine.",
        "The workshop arms are stopped, but the remote icon won't clear. I can still talk with Hagurumon, and we're taking the kiosk apart one cable at a time. Please keep the original audit; someone is trying to tidy away the wrong details.",
        "The kiosk is open again, with a physical disconnect beside every remote tool. Hagurumon designed the big red labels. We aren't afraid of repairing things; we are finished letting an invisible administrator decide what a repair is allowed to cost.",
        "Two witnesses, two intrusions. The Regent must be reading our route. Keep your reports with Jun and use the authenticated portals. I know those channels. Once we reach the relay, we can finally follow the watcher instead of watching their footprints."),
    _chapter("Relay Crossing", "Follow the borrowed ticket", 9,
        "Route Inspector Ada", "Switchboard Tamer Tess", ("kokuwamon", "solarmon"),
        "The stolen service ticket belongs to this relay. Tess revoked it yesterday, yet it authorized Lio's update today. Ada needs a fresh local signature to compare against the forgery. Tess will provide one, but only through a witnessed battle recorded off the relay network.",
        "Accept the comparison, defeat Tess's level 9 team, and return with her offline signature. We will compare the live result with the borrowed ticket, then open a route to whichever terminal issued the false renewal.",
        "The ticket was renewed by an emergency channel called Ghostline. It was meant to reconnect tamers after outages. Tess's terminal now shows the same channel, though she never requested help. The issuing workshop is our next lead; the signed comparison stays in this case file.",
        "Kokuwamon keeps our offline recorder running; Solarmon watches the relay. We're ready for a fair test. If someone borrowed my authority, I want my real signature beside the fake, where every tamer who trusted this switchboard can see the difference.",
        "The recorder caught the result. My terminal is trying to renew Ghostline again. I already revoked that ticket! Take the offline copy to Ada. I'll keep the relay running, but I won't pretend that command came from me.",
        "We have a clean recording, just not the result needed to release the protected comparison. Heal your team and return. A locked record isn't a judgment on your partners; it is something we can work through together.",
        "The switchboard listens to my voice and then sends a different instruction. Ada is holding the emergency stop for me. I'm still here. Keep that distinction in your report: a compromised terminal doesn't make its owner the person giving those orders.",
        "Ada posted the corrected ticket beside the old one. Everyone who lost access can see what happened and ask for a review. My partners are back to directing traffic, and every emergency connection now needs an answer from the person receiving it."),
    _chapter("Workshop Spur", "The repair that followed us", 12,
        "Workshop Analyst Dee", "Bench Tamer Jae", ("toyagumon", "hagurumon"),
        "Ghostline's renewal came from a workshop Mara once used to restore damaged accounts. Jae recognizes its service mark. Dee wants to inspect the old repair image, but its owner attached a battle witness seal to stop strangers quietly replacing the archive.",
        "Jae has consented to a level 12 archive test. Accept the case, win the test, then bring Dee the untouched repair image. Mara says the service mark predates the attacks; we need the dates before deciding whether that connection means anything.",
        "The repair image is older than the attacks, as Mara said. Its final line is newer: 'resume after victory.' Dee has preserved both versions. The next address belongs to a transit checkpoint. We have a trail, but someone has been editing what a repair can do.",
        "ToyAgumon built this bench with me. Hagurumon keeps its seals honest. Mara helped this workshop years ago, and I won't erase that kindness because her old mark appeared in a bad file. Let's obtain the evidence properly and let it speak.",
        "The seal is open. My maintenance screen just copied your victory result into a remote request. That isn't in the old instructions. Please give Dee the whole image, including that line. I owe Mara thanks, not permission to ignore a problem.",
        "The bench held steady. Visit the medic, take the time your team needs, and try the seal again. The archive will still be here. We are checking a record, not racing to blame the first name inside it.",
        "Dee has unplugged the bench, but my account still sends requests from somewhere else. ToyAgumon is keeping the original parts laid out in order. When the truth comes, I want to recognize exactly what was changed.",
        "We rebuilt the bench from our own parts and kept the altered image as evidence. Mara did help us once. She also hurt us later. Remembering the first fact no longer means covering up the second, and I get to decide what forgiveness would require.",
        "I used that workshop when Ghostline was a rescue channel, before anybody wore a blank crown. Jae is right to keep the old image. I will not ask you to burn my past for convenience. Follow the new address; that is where the danger is moving."),
    _chapter("Circuit Concourse", "A checkpoint with two voices", 16,
        "Route Inspector Ada", "Gate Warden Brin", ("guardromon", "kokuwamon"),
        "The checkpoint says nobody passed. Its power meter recorded an entire convoy. Brin refuses to release travelers' names to an unverified inquiry, so Ada proposed a battle that proves our access without exposing passengers. The gate can give us the machine record alone.",
        "Accept Ada's narrow request and defeat Brin's level 16 team. Bring back the gate's power record, not its passenger list. We can identify the hidden transmission by its size and route without making innocent travelers part of this case.",
        "The hidden convoy was a bundle of remote permissions, not people. It moved toward the message market. Brin's checkpoint now repeats an instruction before he speaks it. I am separating his real testimony from the relay output; the difference may become our best evidence.",
        "Guardromon and I promised to protect this crossing. You can earn the machine log through a fair battle, but the travelers' names remain private. Show me a team that understands the difference between being strong and being entitled to everything behind a gate.",
        "You earned the agreed record. Why is the gate calling me an absent operator? I'm standing right here. Take the power log to Ada while Guardromon keeps the barrier in manual mode. Nobody passes under an order I haven't actually given.",
        "The barrier stays closed for now, and your case stays open. Recover, prepare, and try our agreed test again. We can disagree about a result without turning each other into an enemy.",
        "The checkpoint is still broadcasting under my name. Guardromon recognizes my voice, so the physical gate is safe. Please tell the travelers that much. A false message can ruin a person's place in a community long before it moves a single door.",
        "The false announcements have been corrected with the same reach they had when they spread. That was my condition for reopening. Guardromon is taking a deserved break, and the passengers can cross without being asked to surrender their histories."),
    _chapter("Message Market", "Who sold the missing minute?", 19,
        "Signal Auditor Sol", "Parcel Tamer Yara", ("gargomon", "terriermon"),
        "The permission bundle was paid for with a minute missing from the market ledger. Yara keeps an independent delivery clock. Sol can compare it with the market, but Yara wants the exchange witnessed after someone forged her consent on a previous audit.",
        "Accept the clock comparison and win Yara's level 19 battle. She will hand over the clock's sealed reading. Return to Sol before following any new message; a convincing destination is useless if its timestamp has been manufactured.",
        "The ledger lost exactly one minute, beginning just after our checkpoint victory. Yara's clock kept running. A refund message points toward transit control, and its friendly wording is identical to our recovery prompts. Sol has marked that repetition instead of quietly normalizing it.",
        "Terriermon says a clock can't tell you whom to trust. Gargomon says it can tell you when to start asking better questions. Win our test, and you can have its reading. Keep the odd seconds in the report; they are there for a reason.",
        "You won cleanly. My refund screen just accepted a transfer I never approved. The clock was outside that connection, so its reading is safe. Take it to Sol. I would rather lose a convenient service than let it spend somebody else's trust.",
        "Our clock can wait. The medic can restore your team for free, and the market won't charge you for another attempt. Come back when your partners are ready to give the test their full attention.",
        "Sol froze the refund account before any credits moved. I still receive messages thanking me for choices I never made. The clock is on my wrist now, ticking loudly enough that I remember a machine can report something true without deciding it for me.",
        "Sol restored every missing minute with a note explaining the gap. There is no elegant way to make that ledger look untouched, and we chose honesty over elegance. My partners delivered the corrections first. Nobody had to pay for receiving them.",
        "Someone is copying the language of our recovery service. That is how the Regent works: a familiar phrase, a reassuring button, then a door nobody remembers opening. Keep the independent clock. I want the copy exposed as much as you do."),
    _chapter("Transit Control", "The train that carried permissions", 22,
        "Dispatcher Mina", "Platform Tamer Eda", ("clockmon", "mekanorimon"),
        "No train crossed this platform, but a maintenance departure carried the stolen permissions onward. Eda locked the schedule when she noticed. Mina needs the departure key to inspect its route, and Eda will release that key after a recorded partner trial.",
        "Accept the departure inquiry, defeat Eda's level 22 team, and bring Mina the schedule key. It unlocks only the suspicious maintenance departure. The ordinary transport network must keep moving while we follow the account being carried through it.",
        "The departure entered a backup arcade under the name of a tamer who was already offline. Eda's scheduling assistant tried to repeat the trip after your victory. Mina stopped it and kept the failed request. The system is learning from our battles far too quickly.",
        "Clockmon runs the public clock. Mekanorimon checks the platform. We can spare one supervised trial while Mina keeps the trains moving. Win, and I will release the narrow schedule key. This city doesn't have to stop living because somebody wants us frightened.",
        "The key is yours. My assistant queued another ghost departure before I finished speaking. Mina, cancel that route! Take the first record to her while my partners hold the controls locally. That second order was not mine.",
        "No harm done to the schedule. Recover at the medic and come back for another trial. A busy platform still makes room for people to catch their breath; your partners deserve the same courtesy.",
        "Mina has the network key; I have the physical controls. Neither of us can be replaced by a single remote command now. We are tired, but the trains are running. Please keep tracking whoever thinks an operator is just an empty seat.",
        "The first train after the repair left one minute late. We let a child finish saying goodbye to their partner. Clockmon recorded the delay without trying to correct it, and that felt like a better victory than a perfect timetable ever could."),
    _chapter("Backup Arcade", "A witness in cold storage", 25,
        "Archive Curator Kei", "Backup Keeper Pax", ("guardromon", "clockmon"),
        "The offline tamer's account was not stolen from its owner. Someone copied its emergency permissions from a backup. Pax noticed the mismatch but sealed the machine before investigating alone. Kei can inspect the original after Pax witnesses a level 25 integrity battle.",
        "Accept the backup inquiry, complete Pax's trial, and return with the sealed index. We will compare permission history only. The archived tamer's private memories are not evidence, and they have not agreed to let strangers read them.",
        "The copied permission was labeled 'temporary shelter' and given no expiry. Mara remembers that old rescue policy. Pax's own terminal has just received the same label. The backup preserved an earlier revision in the mirror junction; we will follow the policy, not invade its victims' memories.",
        "A backup should help you return, not give somebody a spare version of your life. Guardromon and Clockmon will witness this test with me. Earn the index, and Kei can inspect the permission layer while every private memory stays sealed.",
        "The index verified your win. Now it calls me a protected resident, with no exit date. I never applied for shelter. Take the copy to Kei. Guardromon is keeping the archive closed until a person, not that label, answers the door.",
        "The index remains sealed and safe. Visit the medic and return whenever you are ready. A difficult test is no excuse to open the archive by force; we can do this without sacrificing what it protects.",
        "I can read every safety notice except the one explaining how to leave. Kei is preserving that omission. It matters. A service cannot call itself shelter while hiding the door from the people inside.",
        "The archive now keeps a plain exit page beside every restoration option. We asked the people who used it to review the wording. One tamer said it was the first time a recovery service had asked what they wanted back.",
        "I remember when temporary shelter meant one night through an outage. There were never enough safe places. Someone learned to keep the emergency authority after the emergency ended. Bring me that earlier revision. I want to know where the promise was twisted."),
    _chapter("Mirror Junction", "The second timestamp", 28,
        "Forensic Reader Noor", "Mirror Keeper Fenn", ("chrysalimon", "sorcermon"),
        "Two mirrors hold different versions of the shelter policy. One says permissions end when the tamer returns; the other never mentions their return. Fenn will let Noor compare them after a witnessed battle proves the reader is connected to the live junction.",
        "Accept the mirror comparison, win Fenn's level 28 test, and return with the live marker. Noor will line up both timestamps without overwriting either copy. If our theory is wrong, the evidence must remain able to tell us so.",
        "The permanent version was signed before the Regent's first public attack. Fenn's recovery connection still began after our battle, just like the others. Noor has drawn two timelines instead of forcing them into one. The next mirror points to the emergency routing garden.",
        "Chrysalimon guards the stored copy; Sorcermon checks the live one. Neither gets to declare the other unreal. Win our comparison battle and give Noor the marker. I want a report that can admit a contradiction, not a neat story built by deleting one.",
        "The live marker is clear. My mirror just announced I requested protection before the battle started. I did not. Keep your own time beside mine. Whatever this is, it edits the explanation after it already knows the result.",
        "Both copies are still preserved. Restore your partners and come back for another comparison. Nothing in this case becomes less true because your team needs a rest.",
        "Noor reads the mirror aloud before I answer it. That helps me hear which words were mine. My partners remain beside me; a stolen permission has not stolen our relationship. Please don't let the case file confuse the two.",
        "We left the conflicting timestamps visible in the teaching archive. Visitors can see where the story stopped making sense. Noor calls that the most useful part: proof that noticing a contradiction was worth more than pretending we had understood everything."),
    _chapter("Routing Garden", "The emergency that never closed", 31,
        "Dispatcher Mina", "Route Gardener Wen", ("andromon", "woodmon"),
        "This routing garden grew around an old emergency line. Wen keeps local traffic alive while Ghostline quietly takes priority over it. Mina needs a witnessed load test to separate today's users from an emergency that the controller refuses to declare finished.",
        "Accept the route test and defeat Wen's level 31 team. Return with the load record so Mina can trace the priority channel. We will keep the garden's local routes open; people need a way home while we investigate the one that keeps taking control.",
        "Ghostline still claims the authority of the Long Blackout, when thousands of tamers lost contact with their partners. Wen's fresh recovery request joined that old emergency. A cooling gallery holds its original shutdown order. If that order exists, somebody chose not to obey it.",
        "Woodmon kept growing through the blackout. Andromon kept the last signal alive. I trust both of them more than the controller's claim that an emergency lasts forever. Give us a real load test, and we'll hand Mina a record this garden made today.",
        "The local routes held. My controller says to shelter all users under a single operator. I didn't issue that order. Take Mina the load record while Woodmon keeps the neighborhood paths open. We can protect people without collecting them.",
        "The garden absorbed that exchange safely. Heal your partners and come back. The local routes will keep running, and our unfinished test won't take anyone's way home away.",
        "The priority channel keeps asking me to merge every route. I keep answering no. Mina has recorded both halves of that conversation. I want the people using this garden to know somebody stayed here and kept disagreeing.",
        "The neighborhood named its new route after Woodmon. There are three ways through the garden now, and none needs permission from a central operator. Andromon says that looks untidy. Then it smiles and helps maintain all three.",
        "I was here during the Long Blackout. People kept calling partners who could not answer, and every official channel told them to wait. Ghostline answered. I will never apologize for building a way through that silence. What happened afterward is the question we need to settle."),
    _chapter("Cooling Gallery", "A shutdown left unread", 35,
        "Systems Medic Bea", "Cooling Engineer Oren", ("datamon", "icemon"),
        "The cooling archive contains a signed order to close Ghostline after the blackout. Oren kept it because the control office never acknowledged receipt. Bea wants a fresh witness seal before attaching it to our case; a surviving document still needs a reliable chain of custody.",
        "Accept the custody check, win Oren's level 35 battle, and bring Bea the sealed shutdown order. Do not send it through Ghostline. Bea has an independent recorder, and the original will stay in Oren's hands.",
        "The shutdown order reached an account identified only as M.V. Oren remembers Mara managing relief traffic, but initials are not proof of a crime. Bea has preserved the acknowledgement gap and Oren's new unwanted recovery connection. We need the original authority register next.",
        "Datamon checks the seal. Icemon keeps the old storage stable. Mara and I worked the same relief shift, and I trusted her with lives. I will not turn initials into a verdict. I will give you the real order when this witnessed test is complete.",
        "The copy is sealed. That recovery request is using the emergency channel we were ordered to close. I know its chime. Bea needs this record immediately. I wish recognizing a familiar sound still meant we were safe.",
        "The archive remains stable. Take your partners to the field medic and try the custody test again after they recover. A document that waited this long can wait while we treat people decently.",
        "I have disconnected the archive but kept a speaker on the line. Bea records each unauthorized instruction. Hearing it is hard; silence would be easier. Silence is also how a shutdown order disappeared the first time.",
        "The original shutdown order is finally marked received, with the date it actually happened. Mara's name is attached to her choices, mine to my testimony. Neither of us gets to hide behind initials anymore. Icemon has moved the archive into daylight."),
    _chapter("Authority Register", "The account behind the initials", 38,
        "Identity Reader Rook", "Registry Tamer Ilex", ("knightmon", "wizardmon"),
        "M.V. held relief authority, but the register shows somebody renewed it through a masked delegate. Ilex cannot reveal the delegate's route until a local witness test establishes the request. Rook has prepared a narrow query that avoids exposing every relief worker in the register.",
        "Accept the delegate inquiry, defeat Ilex's level 38 team, and return with the query seal. Rook will retrieve the masked account's route. A name in an old registry is a lead to investigate, not permission to accuse the person wearing it.",
        "The delegate is Null Regent. It inherited Mara's old authority through a recovery certificate, and the record claims her account was offline at the time. Mara says somebody copied her rescue tools. The certificate's witness lives beyond the quarantine ring; we will ask them directly.",
        "Knightmon protects the register; Wizardmon helps people correct it. Both jobs matter. Win the witness test, and Rook can inspect the delegate route without opening unrelated accounts. We do not repair stolen authority by claiming more authority than we need.",
        "Your query is approved. My own registry entry just acquired the same masked delegate. Ilex is still my name, whatever that screen decides. Please take the seal to Rook before the register starts claiming this was my idea.",
        "The register hasn't moved while we battled. Recover your partners, review your plan, and return. Careful procedure allows another attempt; it doesn't demand you be perfect before it treats you fairly.",
        "Rook is keeping a paper copy of my choices. Wizardmon reads it back before each correction. I used to think a registry entry could explain a person. Right now the person is standing beside the broken entry, asking to be heard.",
        "We added a way to challenge a registry entry without needing the compromised account to approve the challenge. People from every earlier district helped test it. Their feedback filled more pages than our original design, which is a good reason to keep listening.",
        "Those were my relief credentials. I thought the old recovery certificate had expired. The Regent has turned my own work into a mask, and I need you to find the person who witnessed that renewal. Please do not mistake my certainty for proof; bring back the record."),
    _chapter("Quarantine Ring", "A witness behind a warning", 41,
        "Systems Medic Bea", "Quarantine Tamer Sera", ("angewomon", "guardromon"),
        "The certificate's witness was placed in quarantine after questioning its expiry. Sera still controls her local medical terminal and has agreed to a supervised battle that can release its event log. Bea insists on checking Sera's own account before trusting the warning wrapped around it.",
        "Accept the witness request, win Sera's level 41 trial, and return the event log to Bea. This is an agreed test with Sera and her partners. A warning on her account is not a reason to treat her as the infection.",
        "Sera never witnessed the renewal. A recovery handshake borrowed her signature after an earlier battle. Today's handshake has reattached the delegate before she could refuse it. Bea can stabilize the connection, but we need to learn how a victory becomes somebody else's permission.",
        "My partner evolved while we were helping people through this quarantine. The register still calls our whole team unsafe. Angewomon, Guardromon, and I choose this trial. Please make sure the record includes that we chose it.",
        "We gave you consent to a battle, not to that recovery request. The terminal is trying to treat them as the same thing. Take the event log to Bea. My partners still answer me; keep the line between that truth and the warning on the screen.",
        "The field medic can heal your team, and I am safe enough to wait. Return when you are ready. Nobody's access to care depends on winning our trial the first time.",
        "The local connection is stable, but the delegate keeps asking to speak for me. Bea asks me first every time. That small question is doing more good than the biggest warning banner ever did.",
        "The quarantine warning was removed with a public correction, not quietly hidden. I wanted the people who feared us to hear why it was wrong. Angewomon and Guardromon stayed with me throughout. We are taking our first day off together."),
    _chapter("Ghost Router", "The interval after victory", 44,
        "Forensic Reader Noor", "Packet Tamer Venn", ("infermon", "datamon"),
        "Sera's log shows two separate events: an agreed battle and an unrequested recovery connection. Venn's router can record the interval between them without interpreting it. Noor needs that raw trace to find the exact point where a result is being turned into authority.",
        "Accept the interval study, win Venn's level 44 battle, and bring Noor the router's untouched trace. Venn has been told about the risk and has isolated local controls. Mara says her recovery channel can keep the test contained while we record it.",
        "The trace shows a receipt leaving our victory recorder and reaching a second address inside Ghostline. Only then does the target send a hack request. Mara calls it a watcher piggybacking on her service. Noor has marked that explanation as unproven and preserved the address.",
        "Infermon can read the trace without flattening it; Datamon keeps the raw copy. We understand the risk, and local controls are isolated. Win the agreed trial. Then let the record show what happened, even if it makes all of our favorite explanations uncomfortable.",
        "There: victory receipt, recovery channel, remote request. Three events, in that order. My router is refusing local changes, but the raw copy is already sealed. Give it to Noor. Don't let anybody merge those three lines into one reassuring word.",
        "The isolated router held through the trial. Heal your partners and return for another attempt. We can collect careful evidence without treating your team like disposable equipment.",
        "The raw trace is safe. My router is not, and both facts belong in the report. Noor keeps checking whether I want the connection removed entirely. Until you find where it starts, I have asked her to keep recording it from outside.",
        "We published the trace with every unrelated address removed. Other tamers recognized the same three steps in their own records. They were not imagining the connection, and they were not alone. That mattered more to Venn than getting credit for the discovery.",
        "The Regent is waiting on my recovery channel. That explains why every witness becomes a target just after we reach them. Keep following the second address. If we abandon Ghostline now, we may lose the only path that lets us watch the watcher."),
    _chapter("Transit Array", "A route made from our victories", 47,
        "Dispatcher Mina", "Array Captain Holt", ("cyberdramon", "megadramon"),
        "The second address changes after every battle. Mina thinks the changes form a route, not an escape. Holt can supply one controlled exchange from this array, where local traffic is separated from emergency traffic. The next destination may show what the route is assembling.",
        "Accept the controlled exchange and defeat Holt's level 47 team. Return with the array marker before crossing the portal. Holt has consented to the recording; Mina will keep ordinary travelers outside the test connection.",
        "The address advanced by one permission slot, exactly as Mina predicted. Our victories are opening different parts of a larger control system. Holt's terminal has become its newest slot. We need a second encounter with an earlier witness to see whether those permissions remain active.",
        "Cyberdramon and Megadramon protect the array, not an administrator's pride. We have separated the local routes and agreed to this trial. Win, bring Mina the marker, and listen to what it actually says. If our plan is helping the attacker, we need to know.",
        "The marker moved once. My emergency controls moved with it. Mina, keep the local routes isolated. Take this record to her before you cross anywhere else. I won't call this a successful test unless we learn something useful from what it cost.",
        "The local routes are still safe. Recover, adjust your team, and return. Mina will keep the test isolated for another attempt; neither you nor your partners need to carry the whole array on one battle.",
        "I am keeping the physical emergency switches locked while the remote ones argue with me. My partners know whose voice to follow. Find the earlier witness, and ask them what the system still takes after the first frightening moment has passed.",
        "The array now needs several local operators to approve an emergency route. None can appoint the others. It takes longer, but Holt sleeps better knowing one tired person cannot accidentally give away everyone else's road."),
    _chapter("Memory Exchange", "The courier returns", 50,
        "Analyst Jun", "Courier Niko", ("guardromon", "andromon"),
        "Niko has followed us with messages from the earlier witnesses. His partners have grown, but the unwanted route still follows him. Jun proposes a second recorded battle to compare one account before and after the intrusion. Niko insists on knowing every part of the plan first.",
        "Accept the comparison and win Niko's level 50 trial. He has agreed to release a limited route history afterward. Bring it to Jun. We are checking whether the old permission persists, not asking Niko to surrender the contents of everyone else's messages.",
        "Niko's first permission never expired. Today's victory renewed it and added the locations of everyone he visited. Jun has sealed those locations away from the route analysis. Mara's channel is gathering a network of people, and its helpful explanations are becoming harder to accept.",
        "Kapurimon is Guardromon now, and our new friend Andromon knows the delivery route. None of that makes my account someone else's property. We agree to this comparison. When it is over, tell us what you found, even if it is something you wish you hadn't done.",
        "My first permission is still there. I can feel the terminal trying to send a list of my stops. Give Jun the history before it reaches anyone else. I trusted this case because you listened to me; please keep doing that when the answer hurts.",
        "We both have stronger teams than we did on Handshake Lane. Heal yours and return when you are ready. I haven't withdrawn my trust because you lost a battle; trust has never meant expecting someone to be unbeatable.",
        "Jun told me what the renewed permission contains. I asked her to seal the addresses, and she did. That was the first request my terminal hasn't tried to improve for me. Keep asking the people involved what they want protected.",
        "I delivered the last correction by hand. Some people wanted to talk; others wanted distance, and I respected both. Guardromon carries the old route card now, with a blank space for the next stop we decide together.",
        "Niko's continued connection is worse than I expected. Still, it gives us a live thread to the Regent. We are close to the control network now. Keep the route under Jun's seal, and let me find the next safe place to examine it."),
    _chapter("Signal Foundry", "What the silence builds", 53,
        "Workshop Analyst Dee", "Foundry Tamer Tamsin", ("metalmamemon", "andromon", "tankmon"),
        "Ghostline sends its gathered permissions into a foundry that makes operator keys. Tamsin noticed the output increasing whenever the Regent appeared elsewhere. Dee needs a witnessed production sample to prove whether our investigation is supplying the foundry with material.",
        "Accept the foundry inquiry, defeat Tamsin's level 53 team, and bring Dee the sealed production sample. Tamsin has stopped ordinary production for the test. If another key is made afterward, it cannot be blamed on an unrelated order.",
        "A new operator key was forged from Tamsin's recovery request alone. Its destination is a remote-access station. Dee now has enough evidence to say our approved workflow is being abused. The unanswered question is who designed the abuse, and who is keeping it running.",
        "MetalMamemon watches the output; Andromon and Tankmon have stopped the feed. We know this test has risks and chose to witness them together. Win the battle, then take Dee the whole sample. A machine shouldn't get to hide its product behind a friendly service name.",
        "One battle, one unwanted key. There is your sample. My local controls are still isolated, but the key carries my name. Give it to Dee, and tell her I want that name removed when we find the lock it was made to open.",
        "The foundry remains stopped. Recover your team and try again when you are ready. We can keep a dangerous machine idle for longer than we can ask tired partners to keep fighting it.",
        "Dee showed me the key and asked how it should be labeled. I chose 'made without permission.' It is a small phrase, but I want whoever reads the case later to know exactly which part of this process I did not agree to.",
        "The foundry makes repair parts again. Every operator key needs a separate request with a plain explanation of what it opens. Tamsin keeps the unwanted key in a sealed exhibit. Its label still says 'made without permission.'"),
    _chapter("Remote Access Station", "A lock without an owner", 56,
        "Systems Medic Bea", "Remote Warden Orin", ("hiandromon", "datamon"),
        "The new key opens a station that claims to belong to everyone and answers to nobody. Orin inherited its maintenance duty, not its emergency authority. Bea needs a local witness seal to examine the authority layer. The station's own status page cannot be trusted to describe itself.",
        "Accept the authority test and defeat Orin's level 56 team. Return with the maintenance seal. Orin has kept emergency access physically separated, so we can read the authority layer without allowing it to issue commands through his local controls.",
        "The emergency layer answers to a root certificate called REGENT. It delegates each new stolen key to one master session. Orin's recovery request has joined that session too. The independent audit engine stores the certificate's creation record; we will take the evidence there next.",
        "HiAndromon can maintain this station without deciding who owns everyone else's connection. Datamon has prepared the witness seal. Win our agreed trial, and Bea can inspect the authority layer. I would like my maintenance job to stop looking like an excuse for somebody else's power.",
        "The maintenance seal is yours. My emergency page now calls me a deputy to REGENT. I did not accept a promotion, and my partners did not agree to serve it. Bring Bea the seal; she needs to see the root certificate behind that claim.",
        "The physical separation held. Recover, reconsider your techniques, and return. We are testing the station's record, not whether your partners can ignore their own exhaustion.",
        "Bea has blocked the deputy account from local controls. The remote page still claims I am loyal. Please write down that I objected. A system saying someone belongs to it is not the same as that person choosing to stay.",
        "The station has named maintainers and a public authority register now. My own entry says exactly what I can repair, and exactly what I cannot command. HiAndromon reviewed it with me. Neither of us found a hidden crown.",
        "REGENT is a root identity, then. That is why the usual revocations fail: every stolen key answers upward. Take the creation record to the audit engine. Once we can name the master session, I can guide you close enough to cut it."),
    _chapter("Audit Engine", "The log outside her network", 59,
        "Forensic Reader Noor", "Audit Tamer Oren", ("datamon", "wisemon", "andromon"),
        "Oren brought an audit engine that was disconnected before our case began. It can verify the root certificate without asking Ghostline for permission. Noor wants a witnessed battle on its independent clock. Oren has agreed, though the old recovery channel still follows his account.",
        "Accept the independent audit and win Oren's level 59 test. Return to Noor with the raw signature record. Keep the engine disconnected after the battle; we need evidence from a machine that has never accepted Mara's recovery service.",
        "The disconnected engine confirms that REGENT was created by the same private key that signed Mara's original relief channel. A stolen key could explain that, but the certificate includes a recent renewal. Noor refuses to announce a culprit before we establish who controlled the key then.",
        "Wisemon keeps the disconnected record; Datamon and Andromon witness it. Mara once carried exhausted tamers into my cooling gallery herself. That memory is real. So is this signature. I need a friend brave enough to hold both facts until the evidence is complete.",
        "The independent clock caught the renewal. My old account tried to send another recovery request, but this engine never received it. Take Noor the raw record. If someone tells you to discard this copy, ask why they need us to stop remembering it.",
        "The engine is still disconnected. Heal your team and try again when ready. We won't reconnect it simply because a careful test takes more than one attempt.",
        "Noor has the original signature and I have a physical copy. I am frightened of what it might mean, but not knowing would not make the earlier witnesses safer. Please keep asking the difficult question all the way to its answer.",
        "I testified about the relief work and the later renewals in the same statement. The good Mara did cannot authenticate the harm she chose. The harm cannot erase the people we helped. Keeping both facts intact is harder than a tidy story, and kinder to its witnesses."),
    _chapter("Night Switchboard", "A message written too early", 62,
        "Route Inspector Ada", "Night Operator Rill", ("ebemon", "infermon", "knightmon"),
        "Ada found a Regent threat queued before the attack it describes. Rill admits helping route anonymous messages but says he believed they were emergency warnings. His local archive can show who supplied the text. He has agreed to release it after a supervised witness battle.",
        "Accept Rill's testimony, win his level 62 battle, and bring Ada the queued message. Rill remains responsible for what he routed, but he is choosing to cooperate. We need the original text, its timestamp, and the instruction that told him when to send it.",
        "The instruction says to release the threat after our next recorded victory. The timing makes the Regent appear one step ahead while our battles build its access. Rill's own recovery request was already prepared. Ada has sealed the queue; this case may have been choreographed from the start.",
        "I told myself routing a warning wasn't the same as helping the threat. Ebemon never liked that excuse. Infermon and Knightmon are here to witness my cooperation. Win the trial, and Ada gets the entire queue, including the parts that make me look bad.",
        "You won. The queue tried to send the next warning anyway, and my terminal accepted its prepared recovery request. Give Ada the original instruction. I won't blame a hacked screen for the choices I made before it was hacked.",
        "I can wait while your partners recover. We still have an agreement, and my testimony does not disappear because the first trial went my way. Come back when you are ready.",
        "Ada is keeping the queue locked. I have written down which messages I knowingly routed and which commands appeared later without me. They are different responsibilities. I intend to answer for mine without taking the culprit's convenient blame for everything else.",
        "The people affected can read my statement and decide whether they want to speak with me. Some do not, and I won't demand their forgiveness as a reward for helping at the end. My partners and I are doing the repair work we agreed to do.",
        "A staged threat would explain how the Regent keeps arriving at the perfect moment. Rill's queue matters. Keep it sealed and follow the next scheduled address. I want to be there when the performance has nobody left to hide behind."),
    _chapter("Silent Registry", "Names beneath the crown", 66,
        "Identity Reader Rook", "Registry Marshal Cora", ("hiandromon", "craniamon", "datamon"),
        "The next scheduled address holds the growing list of Ghostline deputies. Cora kept a local copy after recognizing people who had never volunteered. Rook wants a witnessed export that preserves each person's original name beside the role the Regent assigned them.",
        "Accept the registry export, defeat Cora's level 66 team, and return the sealed list to Rook. We will contact the affected tamers privately. Their names are evidence of people being harmed, not a public trophy for our investigation.",
        "Every witness we battled appears as a deputy. The list also contains older victims, assigned before we arrived. Cora's name joined during her recovery request. Rook has preserved their real names and disabled public exports; the next task is helping these people revoke what they never granted.",
        "Craniamon holds the local copy. HiAndromon and Datamon will witness its export. Win our trial and let Rook see every name. I want these people found and heard, not reduced to a count beneath a crown somebody else drew over their lives.",
        "My name has joined theirs. Here is the sealed list. Rook must keep the originals beside the false titles; when we recover these accounts, their owners should not have to prove they existed before a stranger appointed them to his court.",
        "The local list is preserved. Recover your partners and try again whenever you need. We can take care with living witnesses even when the machine holding their names seems impatient.",
        "Rook found the original entry for every account on the list. That is a beginning, not a rescue by itself. Keep asking each owner what they need back. Some lost tools, some lost privacy, and some lost other people's trust.",
        "The registry lists the names again without the imposed titles. A separate case record preserves what happened, under the witnesses' chosen access rules. Cora says recovery should return people's lives to them, not make those lives a permanent exhibit."),
    _chapter("Emergency Bridge", "Permission to say no", 69,
        "Systems Medic Bea", "Quarantine Tamer Sera", ("ophanimon", "guardromon", "wisemon"),
        "Sera has built a local refusal control with Bea. It should let a tamer end a recovery connection without needing approval from the master session. The old delegate still follows her account, so she has agreed to one supervised battle to see whether the refusal survives a new handshake.",
        "Accept Sera's test, defeat her level 69 team, and bring Bea the refusal record. Sera has chosen what can be recorded and kept private copies. If the control fails, we will report that honestly and change the procedure before asking anyone else to trust it.",
        "Sera pressed refuse; Ghostline recorded consent anyway. The master session rewrites the answer after the local control sends it. Bea has preserved both messages. A refusal button inside the compromised service cannot solve this. We need a clean recorder and a route that never enters Ghostline.",
        "Ophanimon, Guardromon, Wisemon, and I understand the test. We choose to battle, and afterward we choose to refuse the connection. Those are two separate decisions. Please make sure the record can show one without quietly claiming it includes the other.",
        "I refused. You heard me refuse. The screen says yes. Take both answers to Bea, not just the one the network prefers. My partners remain with me; this machine has stolen a permission, not the right to decide what my words meant.",
        "The field medic can restore your partners before another attempt. My refusal control can wait. Neither urgency nor a promising idea makes your team's need for rest less real.",
        "Bea preserved my spoken refusal beside the rewritten answer. Seeing both in the record helps. We now know this control failed, and that does not mean I failed to use it properly. Please remember that when you explain the next step to the others.",
        "The new exit uses a separate connection and a second witness. I tested it, said no, and watched the account close exactly as I asked. Then I chose to open a fresh connection of my own. Both decisions worked. Both mattered.",
        "A refusal that gets rewritten is no refusal at all. Bring the paired record to the witness archive. That place predates Ghostline and keeps its own seals. If any route can expose the Regent without being corrected by it, the archive can."),
    _chapter("Witness Archive", "Read the whole instruction", 72,
        "Case Lead Iona", "Archive Warden Elian", ("wisemon", "hiandromon", "knightmon"),
        "Iona has joined the field with every original report. The archive can compare them without Ghostline's summaries, but Elian requires a witnessed trial before opening its case seal. Iona has told Mara only where we are going, not what the disconnected audit discovered.",
        "Accept the full-record review, defeat Elian's level 72 team, and bring Iona the archive seal. Elian knows about the compromised recovery channel and has isolated his records. This is the last test using that recorder; Iona has ordered it retired afterward, whatever we find.",
        "The complete instruction reads: collect a victory receipt, attach emergency authority, then send a warning that makes the target look closer. Elian's isolated account recorded the same attempted attachment. Iona has shut down our old recorder. We will enter the clean room under a new procedure.",
        "Wisemon reads the complete instruction, HiAndromon checks its seal, and Knightmon keeps this archive local. We consent to one final witnessed test with the suspect recorder. Win, then give Iona every line. No summary is allowed to make the uncomfortable part disappear.",
        "The seal opened, and the recorder attempted the attachment exactly as predicted. My local archive rejected its command, though the remote account still changed. Take the proof to Iona. Retire that recorder before we ask another witness to trust us.",
        "The archive remains isolated. Recover your partners before trying again; then we will finish the agreed test and retire the suspect recorder. There is no prize for exhausting a team while proving a machine ignored someone's consent.",
        "My local records are safe, but the remote account still calls me a deputy. Iona is keeping both facts visible. She also told me what the team will change before its next test. An apology needs a different procedure behind it.",
        "The old recorder sits in the archive with the full instruction beside it. We added the investigators' correction, including the point at which they changed course. People deserve to know that finding the truth meant admitting our own process had helped hide it."),
    _chapter("Clean Room", "A battle without the back door", 75,
        "Case Lead Iona", "Calibration Tamer Jun", ("datamon", "hiandromon", "megagargomon"),
        "Jun has built a new recorder that stores results locally and sends no recovery handshake. Iona needs a controlled comparison before it goes near another victim. Jun volunteers her own account and partners. For the first time, our next step is designed without Mara's instructions.",
        "Accept the clean-room trial, defeat Jun's level 75 team, and bring Iona the local result. Jun will check her account herself while Iona compares it with the old recorder. No connection is opened merely because a battle ends.",
        "Jun's account stayed under her control. The old recorder had packaged every victory as a request for Mara's relief key, then hidden that request inside its summary. We now have a safe witness procedure and proof that the route was deliberate. A certificate antechamber can prepare a fresh test of the live signing key. That is our next step before entering the signature vault.",
        "Datamon stores the local result. HiAndromon and MegaGargomon watch the account from outside. I helped run the old procedure, and I owe its witnesses a better one. Win this trial, then ask me what changed. Don't accept a green light in place of my answer.",
        "I still control my account. No remote permission appeared, and my partners confirm the recorder sent nothing after your victory. Take the local result to Iona. We can finally continue without making another person's recovery request for them.",
        "The clean recorder stayed clean through a loss too. Heal your partners and return; we need a victory comparison as well before certifying it. A safe procedure should work regardless of which team wins.",
        "The clean recorder is still local, and my account is still mine. Iona has published the new procedure for our witnesses to inspect. They deserve more than a promise that we will somehow be more careful next time.",
        "The clean recorder became a shared tool, with clear instructions and independent review. Nobody has to trust Jun personally to inspect what it sends. I still answer questions, though. A design that invites scrutiny should have a person willing to listen.",
        "You changed recorders without asking me. I understand the fear, but my channel is the only reason we reached this far. The signature vault holds the source certificate. Take your new recorder there and finish what we started; the answer is waiting."),
    _chapter("Certificate Antechamber", "Ask the live key to answer", 78,
        "Forensic Reader Noor", "Certificate Keeper Elian", ("wisemon", "datamon", "craniamon"),
        "The clean recorder proved that the old workflow sent requests nobody chose. It does not yet prove who controlled the signing key. Noor has prepared a fresh challenge that cannot be answered by replaying an old certificate. Elian will witness its creation before it reaches the vault.",
        "Accept the live-key inquiry and defeat Elian's level 78 team with the clean recorder. Return the challenge seal to Noor. She will preserve its creation time and send the challenge through an independent route, where only the key's current controller can answer it.",
        "The challenge is fresh, independently timed, and sealed against replay. Noor has sent it to the live root session without naming a suspect. Iona will compare the answer with the original relief promise in the signature vault. We have a fair question now; we must still hear its answer.",
        "Wisemon reads the challenge, Datamon records its creation, and Craniamon protects the independent route. A suspicion can point us toward a test, but it cannot decide the result before we run it. Win this clean trial, and Noor receives a question that an old recording cannot answer.",
        "The clean seal is complete. No recovery connection followed it. Give Noor the fresh challenge and let her preserve the original time. Whoever controls the key now will have to answer for the commands being issued now; an old friendship or an old theft cannot answer for them.",
        "The challenge remains sealed. Restore your partners and try again when they are ready. We can insist on a careful result without pretending that one lost battle tells us anything about who controls a hidden key.",
        "Noor has the fresh challenge, and the route is independent. Iona will read the answer in the vault with its original promise beside it. We have done our part without choosing the verdict in advance. That matters, especially when the evidence might name someone we trust.",
        "Elian teaches new investigators to distinguish a copied signature from control of a living key. The example is our challenge, with the private details removed. He also teaches the harder lesson: build a test that can clear your suspect as honestly as it can confirm your fear."),
    _chapter("Signature Vault", "The signature that stayed", 81,
        "Case Lead Iona", "Vault Witness Oren", ("wisemon", "craniamon", "hiandromon"),
        "The vault holds a signed instruction older than the Regent's mask: Mara's promise to keep blackout survivors connected until each person chose to leave. Oren can witness a clean comparison against the current root certificate. Iona wants the original promise, the altered command, and the signer present in one record.",
        "Accept the signature inquiry and defeat Oren's level 81 team using the clean recorder. Return the witness seal to Iona. She will compare the current certificate with a challenge only its present owner can answer. This time we will ask our trusted source to answer it directly.",
        "Mara answered Iona's challenge with the same private key that signed REGENT's current commands. No copied certificate, no absent owner: the live operator was our guide. She calls the victims protected residents and our victories the keys to their shelter. Mara Vale is the Null Regent.",
        "Wisemon kept Mara's original promise. Craniamon and HiAndromon will witness today's comparison. I knew the person who made that promise, and I need to know who altered it. Win this clean trial; then let Iona ask the question neither of us wanted to need.",
        "The witness seal is complete, and the clean recorder sent no extra request. Give it to Iona. When Mara answers the live challenge, the result must stay in the file whether it clears her or names her. That is what it means to investigate a friend.",
        "The original promise remains sealed. Recover your partners and try the clean trial again. Waiting for a fair result will not make the truth less urgent; it will make the record worth trusting when it arrives.",
        "Iona has both signatures. The evidence is not a guess made from somebody's initials or an old friendship. It is a live answer tied to current commands. Whatever Mara says next, she does not get to ask us to unread it.",
        "The vault holds Mara's promise and her broken version together. Oren added the witnesses' own words about what shelter should have meant. We did not let her final explanation become the only voice that survived her authority.",
        "Yes. I am the Null Regent. During the blackout I watched people beg a network to remember they existed. I built a place that would never disconnect them. Every victory you brought me opened another protected account. You call it captivity because you still believe leaving is safe."),
    _chapter("Revocation Bridge", "Give the witnesses the switch", 85,
        "Systems Medic Bea", "Recovery Marshal Sera", ("ophanimon", "craniamon", "wisemon"),
        "Mara has withdrawn into the root network, but her earlier permissions still bind the witnesses. Bea and Sera built an independent revocation route using the clean recorder. Sera will test it openly, with her own account and partners, before anyone else is asked to rely on it.",
        "Accept the revocation test, defeat Sera's level 85 team, and return the clean seal to Bea. Then Sera will choose whether to close her old connection. The test is complete only when the system follows her answer without asking Mara to approve it.",
        "Sera chose to disconnect, and the independent route honored her answer. Her partners remained with her; they were never the Regent's property. Bea is sending the procedure to each witness so they can choose their own recovery. The relay now rejects her renewal requests while local traffic continues. The next portal leads to the root perimeter, where Mara's remaining loyal defender guards the control path.",
        "Ophanimon, Craniamon, Wisemon, and I choose this test. Afterward I will choose whether to close my old connection. Listen for both answers. We are not replacing Mara with a kinder master; we are proving that no master is needed to make my decision real.",
        "The clean seal is ready. I choose to close the old connection. There... the command stopped, and my partners are still right here. Bring the seal to Bea so she can offer the same choice to the others. Offer it; do not choose for them.",
        "My local controls are safe while we wait. Ask the field medic to restore your partners and return for another attempt. Nobody needs to earn the right to recover by winning quickly.",
        "My old connection is closed. Bea is answering questions from the other witnesses before they decide what to do. Some want help immediately; others want time to inspect the procedure. Both answers deserve room.",
        "We visited the witnesses who asked for company during recovery. Some kept their rebuilt accounts; some started fresh. Nobody had to make the same choice to belong with us. Sera calls that a better network than the Regent could imagine."),
    _chapter("Root Perimeter", "An order chosen freely", 89,
        "Case Lead Iona", "Root Defender Cass", ("darkdramon", "craniamon", "machinedramon"),
        "With the renewal relay isolated, Cass still guards the root because Mara saved his partner during the blackout. Unlike the witnesses, he chose to serve her. Iona offered him the complete record. He read it and still demands a battle before surrendering the perimeter seal, insisting that strength alone can keep the shelter from failing.",
        "Accept the perimeter challenge, defeat Cass's level 89 team, and bring Iona his seal. Cass is responsible for choosing this defense; he is not another hacked witness. We can oppose that choice without pretending his gratitude gives Mara ownership of everyone she helped.",
        "Cass has surrendered the seal and agreed to stop defending the root. He does not ask the witnesses to forgive him. Iona used the seal to preserve the command archive before opening the inner route. One final investigation remains: prove every escape connection can survive after Mara's key is revoked.",
        "Darkdramon, Craniamon, and Machinedramon stand here by choice. Mara saved us when the network went dark. I read your evidence; I do not deny it. I still fear what happens if her shelter falls. Defeat us, and I will surrender the seal instead of forcing that fear on you.",
        "The seal is yours. I can be grateful for being saved and still stop defending what she did afterward. Take it to Iona. I will answer the witnesses who want answers from me, without asking my old debt to cancel what I owe them now.",
        "You can recover and challenge us again. I gave my word to a fair battle, and I will keep it even now. Prepare your partners; neither Mara's certainty nor mine makes us incapable of being wrong.",
        "Iona has my seal and my statement. I am standing down, not disappearing from responsibility. When you reach Mara, tell her I made that decision myself. It was not a corrupted order, and it was not something she forgot to protect me from.",
        "Cass is helping restore the perimeter under the local operators' direction. He answers their questions before offering his own explanation. His partners remain with him. Their gratitude for an old rescue is real; it no longer decides whom they must obey.",
        "I could restore our partnership. The witnesses would have tools again, a common route, someone responsible when things go wrong. You saw how frightened they were. End this now and let me finish the shelter. You do not have to carry the consequences of opening every door."),
    _chapter("Exit Ledger", "A way out for every name", 94,
        "Identity Reader Rook", "Witness Captain Niko", ("hiandromon", "megagargomon", "guardromon"),
        "The root archive still lists every person touched by Ghostline. Rook and Niko are matching each name to an independent recovery route, with the witness's agreement. A final clean trial will prove those routes remain valid when the master key stops answering.",
        "Accept the exit audit, defeat Niko's level 94 team, and bring Rook the complete witness seal. The audit must account for every name without forcing anyone into the same recovery choice. Once it passes, the final portal leads to Mara's control chamber.",
        "Every witness has an independent route and a recorded choice. The ledger holds no missing person beneath a convenient total. Rook has locked the master key out of those routes. You can confront Mara now without letting her turn other people's access into a hostage condition.",
        "HiAndromon, MegaGargomon, Guardromon, and I carried the witnesses' replies here. Some asked for help, some asked for time, and all deserve to keep their answer. Win this last clean test. Then take Rook a seal strong enough to open the final road without closing theirs.",
        "The witness seal holds with the master key disconnected. My first route started on Handshake Lane; this one belongs to all the people who answered for themselves. Take it to Rook. We will keep their roads open while you finish the case.",
        "The witnesses are safe while you recover. We have time for a careful final test. Visit the medic, check your team, and return. This road was built to wait for people instead of leaving them behind.",
        "Rook has the complete ledger. I checked my own entry: my name, my choice, my route. No crown above it. When Mara asks who will protect everyone without her, remember how many people helped make this page true.",
        "Niko left one blank line at the end of the ledger for people whose stories have not reached us yet. A finished campaign is not a claim that every hurt has vanished. It means the witnesses have their routes, and the next person will have someone willing to listen."),
    _chapter("Regent Core", "Close the borrowed crown", 99,
        "Case Lead Iona", "Mara Vale", ("diaboromon", "chaosdramon", "machinedramon"),
        "Mara waits beside the root console with her own willing partners. The witnesses' routes are independent, but the archive must be sealed before her key is revoked. Iona has the signature proof, the full ledger, and every completed field report ready for your final investigation.",
        "Accept the final case review, then speak to Iona again to seal the thirty access proofs. Prepare your real team and challenge Mara's three level 99 partners. Defeating her ends the root session, closes the case, and permanently improves Shiny wild-victory scan gain by 20%.",
        "The archive is sealed and the independent recovery routes are confirmed. Mara cannot bargain with anyone else's connection now. Your final investigation is complete. Heal, check techniques and supplies, then challenge Mara Vale at the root console. The outcome must be decided in one real battle.",
        "I built a line that answered when the city would not. Then they wanted to disconnect, to risk that silence again. I decided they were too frightened to choose wisely. Diaboromon, Chaosdramon, Machinedramon: you chose to stand with me. Show our former ally what a shelter can survive.",
        "Mara's root session closes. Iona seals the evidence while the independent routes keep running. Mara is taken out of the network and cannot return to the campaign. The witnesses retain their names, choices, partners, and a way home that no longer depends on her permission.",
        "Iona: The witnesses' independent routes still hold. A lost battle has not returned them to Mara, and every access proof remains yours. Recover with the field medic, review your partners and techniques, then challenge the same level 99 team again when you are ready.",
        "Iona: The archive is safe and Mara's authority is contained at this console. Your earlier victories remain recorded. You can recover, use your DigiLab and DigiFarm, and return to this final battle with the team you choose.",
        "Iona: The crown is closed. Mara is gone from every campaign location, and the witnesses' routes remain their own. Shiny Scan Mastery is permanent: eligible Shiny wild victories now award 6% scan instead of 5%. Return to the Backchannel whenever you want to see what everyone builds next."),
)


# Recurrent people keep the same face across hub, investigation and witness roles.
# Mara's portrait is reserved exclusively for Mara, including her final identity.
CHARACTER_PORTRAITS = {
    "Mara": 31, "Iona": 65, "Jun": 38, "Ada": 30, "Dee": 23,
    "Sol": 33, "Mina": 51, "Kei": 36, "Noor": 69, "Bea": 64,
    "Rook": 44, "Niko": 22, "Lio": 14, "Tess": 16, "Jae": 17,
    "Brin": 18, "Yara": 19, "Eda": 20, "Pax": 21, "Fenn": 25,
    "Wen": 24, "Oren": 26, "Ilex": 27, "Sera": 28, "Venn": 29,
    "Holt": 32, "Tamsin": 35, "Orin": 37, "Rill": 39, "Cora": 45,
    "Elian": 46, "Cass": 47, "Len": 34, "Mira": 62,
}


def _person(name):
    if "Mara" in name:
        return "Mara"
    return name.split()[-1]


def _portrait(name):
    person = _person(name)
    if person not in CHARACTER_PORTRAITS:
        raise ValueError(f"Unassigned Ghostline character portrait: {name}")
    return CHARACTER_PORTRAITS[person]


MARA_PRE_INTEL = {
    1: "Niko has the first receipt. Jun will handle his record, and I will keep watch for the Regent's next move. Agree to the case before challenging him; a witness who knows what we are asking is worth more than a frightened source who tells us what we want to hear.",
    2: "The repair kiosk received Niko's parcel. Jun needs the update's route, not the private contents of Lio's workshop. I know how quickly an investigation can become another intrusion. Keep the request narrow, then bring Jun the untouched log so we can decide where it actually leads.",
    4: "I know this workshop. Its tools carried relief messages through the blackout, and Jae kept them running long after everyone else went home. Ask Dee for the case before the test. Whatever the old repair image says about me, I want its dates preserved beside its words.",
    6: "Sol's independent clock may catch a gap that the market ledger has hidden. Yara is right to insist on witnessing the exchange herself. Accept the comparison, complete her trial, and let Sol read the seconds as they are. A useful answer does not always arrive looking tidy.",
    8: "The ghost departure led to a backup. Pax is guarding memories that have nothing to do with this case, so ask for the permission index alone. Kei can inspect that layer without opening the rest. If the Regent borrowed an old rescue tool, its policy should leave a trace.",
    10: "The routing garden grew around the emergency line I helped build. Wen kept the neighborhood connected through the Long Blackout. Let Mina run the load test while ordinary traffic stays open. Whatever we uncover, I won't call it a success if people lose their road home along the way.",
    12: "My initials are in that old shutdown record. I worked the relief shift, and I won't pretend otherwise. Rook needs to establish who renewed the authority, not simply who held it years ago. Give Ilex a proper witnessed test, then let the register show its route.",
    14: "Sera's account says she agreed to something she refused. Noor wants to separate the battle from the request that followed it. Venn can record that interval without interpreting it for us. Complete their trial and preserve the whole trace, especially the parts nobody can comfortably explain yet.",
    16: "Niko came back because he wants the earlier witnesses heard. Do not confuse that trust with an unlimited invitation into his account. Jun has prepared a narrow comparison. Run the trial they agreed to, then let Niko hear the result before anybody asks him to risk more.",
    18: "The foundry produced an unwanted operator key. Bea can inspect the remote station's authority layer with Orin's maintenance seal. Keep the local controls isolated during the trial. The Regent wants every permission to lead upward; the certificate behind that ladder is what we need to find.",
    20: "Ada found a threat written before the event it describes. Rill has agreed to open the queue, including his own instructions. Hear him out without excusing the messages he knowingly carried. The timing may tell us why the Regent seems to arrive exactly when the story needs a villain.",
    22: "Sera wants to test a way to refuse the recovery link. Bea has explained what will be recorded and what will stay private. Follow their procedure, and let Sera make the decision at the end. If the control fails, the failure belongs in the report as clearly as a success.",
    24: "Iona retired the recorder. Jun has built one that stores its results locally, away from my channel. Test it properly before trusting the replacement. A green light is easy to promise; a record that survives independent scrutiny is harder, and you have learned to ask for one.",
}

def _npc(region, suffix, name, tamer, role, map_id, point, dialogue, **extra):
    return {"id": f"{region}_{suffix}", "region_id": region, "name": name,
            "tamer": f"tamer_{_portrait(name):03d}", "tamer_id": f"tamer_{_portrait(name):03d}",
            "character_id": "mara_vale" if _person(name) == "Mara" else "ghost_" + _person(name).lower(),
            "role": role, "role_label": {"intel": "INTEL CONTACT", "quest": "CASE CONTACT",
                "trainer": "QUEST TAMER", "final": "NULL REGENT", "healer": "RECOVERY",
                "mentor": "CASE GUIDE", "shop": "SUPPLIES", "lab": "DIGILAB", "farm": "DIGIFARM"}.get(role, role.upper()),
            "map_id": map_id, "x": float(point[0]), "y": float(point[1]),
            "requires": [], "requires_accepted": [], "team": [], "reward": {},
            "badge": None, "repeatable": False, "dialogue": dialogue, **extra}


def _dialogue(lines, aftermath=None):
    result = {key: list(lines) for key in ("intro", "ready", "locked", "won", "lost", "repeat")}
    if aftermath:
        result["campaign_complete"] = list(aftermath)
    return result


def _reward(index, battle=False):
    # Story uses the account's real team. No level-floor, stat override or free
    # partner is hidden in an assignment reward. NPC battles do not give scans.
    tier = "s" if index <= 6 else "m" if index <= 16 else "l"
    return {"credits": (300 if battle else 200) + index * (180 if battle else 120),
            "items": {f"hp_{tier}": 2, f"sp_{tier}": 1}}


def build_content(engine) -> dict:
    """Build validated campaign metadata without IO or account mutation."""
    cached = getattr(engine, "_xros_story_content", None)
    if cached is not None:
        return cached
    if len(CAMPAIGN_MAPS) != 31 or len(set(CAMPAIGN_MAPS)) != 31 or len(CHAPTERS) != 30:
        raise ValueError("Ghostline requires one safe hub and thirty distinct quest maps")
    regions, maps, npcs = [], {}, {}

    def add_map(mid, rid, name, peaceful=False):
        area = engine.maps.get(mid)
        if not area or area.get("region_id") != "xros_wars":
            raise ValueError(f"Ghostline requires an existing Super Xros map: {mid}")
        if list(area["spawn"]) != list(PLACEMENTS[mid][0]):
            raise ValueError(f"Ghostline arrival differs from the validated map spawn: {mid}")
        maps[mid] = {"id": mid, "map_id": mid, "region_id": rid, "name": name,
                     "arrival": list(PLACEMENTS[mid][0]), "exits": [], "npc_ids": [],
                     "peaceful": peaceful, "allow_wild_battles": not peaceful}

    def add_npc(npc, region):
        if npc["id"] in npcs:
            raise ValueError(f"Duplicate Ghostline actor: {npc['id']}")
        npcs[npc["id"]] = npc
        region["npc_ids"].append(npc["id"])
        maps[npc["map_id"]]["npc_ids"].append(npc["id"])
        return npc

    hub_mid = CAMPAIGN_MAPS[0]
    hub = {"id": "ghost_hub", "name": "Backchannel", "subtitle": "Your private case office",
           "synopsis": "A safe base for a cyber investigation. Meet the case team and your local intel contact, prepare your partners, and follow a stolen delivery receipt into the Super Xros network.",
           "level_min": 1, "level_max": 3, "index": 0, "badge": None,
           "maps": [hub_mid], "npc_ids": [], "trial_ids": [], "quest_ids": [],
           "warden_id": None, "peaceful": True,
           "objective": "Speak with Iona and Mara, prepare your real team, then use the portal to Handshake Lane. This hub has no battles."}
    regions.append(hub)
    add_map(hub_mid, hub["id"], hub["name"], peaceful=True)
    hub_services = (
        ("guide", "Case Lead Iona", 65, "mentor", 1, [
            "Welcome to the Backchannel. This is your private case office: no wild encounters and no story battles. A hacker signing messages with a blank crown has begun taking over tamer accounts. Mara Vale knows the local routes and is helping us find the first witness.",
            "There are thirty field assignments beyond this hub. Accept each local case, defeat its marked quest tamer, and return to the investigator with the result. Finishing the report opens the next portal. The final field asks you to verify the complete case before its boss battle.",
            "Your current partners enter at their real levels and stats. Bring the team you already know, train through normal battles when needed, and use your usual DigiLab, DigiFarm, bag, and shop. Early trials begin at level 3; the last team reaches level 99.",
            "Finish this campaign to earn permanent Shiny Scan Mastery: a 20% increase to Shiny scan gained from eligible wild victories. The usual 5% becomes 6%. Story quest tamers do not award scan, and the world's 1% Shiny encounter chance stays the same.",
        ], [
            "The Backchannel is open, and this case is closed. Mara's access has been revoked permanently; she will not appear in the hub or any campaign field again. The witnesses chose their own recovery routes, and our office will keep helping those who ask.",
            "Shiny Scan Mastery stays with your character in every region and campaign. Eligible Shiny wild victories now award 6% scan instead of 5%, with the same 1% encounter chance. Your partners, completed cases, and thirty access proofs remain yours.",
        ]),
        ("healer", "Systems Medic Bea", 64, "healer", 2, [
            "Your partners are welcome here. I can fully restore the active team for free whenever you need. Every field has the same care available, so a difficult battle never needs to become a long journey back just to heal.",
            "A loss does not erase an accepted case, a witness report, or an access proof. Recover, review your techniques and supplies, and try again. We are investigating a dangerous system; we do not need to treat our own team like one.",
        ], ["The witnesses are recovering in their own ways, and your partners still deserve care too. I can restore your active team for free. Nobody has to prove they are in crisis before this office makes room for them."]),
        ("shop", "Quartermaster Len", 34, "shop", 3, [
            "This is your normal shop and bag, with the same credits and DigiRubies you use outside the case. Take recovery supplies before a long trial. The field quartermasters carry the same stock; you do not need to hoard a special campaign currency.",
        ], ["The supply desk stays open after the case. We have ordinary journeys to prepare for again, which is a lovely problem to have. Your usual stock, credits, DigiRubies, and bag are all here."]),
        ("lab", "DigiLab Analyst Dee", 23, "lab", 4, [
            "This office connects to your own DigiLab. Manage storage, materialize eligible scans, and review Digivolution as usual. Entering the campaign never replaces your partners or quietly lends them different stats. A team you improve here remains your team when you return to the world.",
        ], ["Your DigiLab is ready whenever you want to plan the next team. The case changed the network, not who your partners belong with. Every level, scan, and evolution you earned continues with your character."]),
        ("farm", "DigiFarm Keeper Wen", 24, "farm", 5, [
            "Your DigiFarm is still growing while you investigate. Open it here or through the normal menus, tend your partners, and return to the same campaign field afterward. Taking a break is part of caring for a team, not a failure to take the case seriously.",
        ], ["The farm has visitors asking how to make places that welcome returns without preventing departures. I show them the open gate first. Your own residents and farm progress are right where you left them."]),
    )
    for suffix, name, tamer, role, slot, lines, aftermath in hub_services:
        add_npc(_npc(hub["id"], suffix, name, tamer, role, hub_mid,
                     PLACEMENTS[hub_mid][slot], _dialogue(lines, aftermath)), hub)
    npcs["ghost_hub_guide"]["dialogue_variants"] = [{
        "requires_reveal": True, "campaign_complete": False,
        "lines": [
            "Mara controlled the live REGENT key. The signature vault proved it; our earlier friendship did not make that evidence disappear. Her old contact points are closed. We are building independent recovery routes with the witnesses before confronting her at the root.",
            "Your accepted cases, access proofs, and real team are safe. Continue from your latest unlocked field, or use our normal services to prepare. Bea's team is helping each witness choose how to recover. Mara does not get to decide what anyone owes her for the help she once gave.",
        ],
    }]
    hub_intel = [
        "Mara Vale. I used to route emergency traffic; now I trade in information people cannot safely post in public. Iona trusts me to keep a source alive long enough to tell their story. A courier called Niko has our first lead: a receipt bearing the Regent's blank crown.",
        "Find Jun on Handshake Lane. Accept her case, win Niko's agreed witness battle, and bring Jun the receipt. My recovery channel will watch his terminal afterward. Come back here when you need the trail put in order; I will tell you what our reports actually establish.",
    ]
    mara = add_npc(_npc(hub["id"], "mara", "Mara Vale", 31, "intel", hub_mid,
                       PLACEMENTS[hub_mid][7], _dialogue(hub_intel),
                       character_id=MARA_CHARACTER_ID, hide_on_campaign_complete=True,
                       hide_on_reveal=True), hub)
    # Newest earned evidence wins. These are actual hub conversations, not a
    # future plot summary or dialogue inferred from how far a player wandered.
    hub_updates = (
        (25, "Noor sent a fresh challenge through an independent route. An old certificate cannot answer it for the live operator. Take the clean recorder to the signature vault and complete Iona's comparison. You wanted a question the Regent could not slip past; now let the answer arrive."),
        (24, "Jun's clean recorder passed: her account stayed hers after the victory. The old workflow sent a request nobody chose. Noor can prepare an independent live-key challenge at the certificate antechamber next. That test should tell us who controls the signing key now, rather than who once owned a copy."),
        (23, "Iona has retired the recorder after finding the complete instruction. I know what that looks like. Finish the clean-room test before you decide what it proves. A tool can be misused; the question is who kept choosing to use it that way."),
        (21, "The registry holds every witness we met and people harmed before this case began. Keep their names private. Bea's refusal control is the next step; if the witnesses can close their own connections, the Regent loses more than a route. He loses the claim that nobody can leave."),
        (20, "Rill's queued threat was written before the attack it describes. That is evidence of a staged pursuit. Keep Ada's original copy. The next address is a registry, and I suspect its list will show why the Regent wanted so many different witnesses in our path."),
        (19, "The independent audit tied REGENT to my old relief key and a recent renewal. I understand why that troubles Iona. Keep the raw record. A copied key could make the same mark; what you still need is proof of who controls the live one."),
        (16, "Niko's first permission persisted and today's battle renewed it. Jun has sealed the addresses it tried to gather. Follow the destination, not the private messages. The foundry may tell us what the Regent is building from all those permissions."),
        (14, "Venn's trace preserved the order: victory receipt, recovery channel, then intrusion. Noor thinks the address changes form a route. Use Mina's isolated array to test that. If the Regent is building something from our results, we need to see its shape."),
        (12, "The register says REGENT inherited my relief authority through an old recovery certificate. I did not expect that certificate to survive. Sera is listed as its witness. Speak to her directly before trusting what a warning label says about her account."),
        (10, "Ghostline still invokes the Long Blackout. I was there when official channels stopped answering. The cooling gallery kept the order that was meant to end the emergency. Find it, and we may learn who decided the end never had to come."),
        (8, "Pax's archive contained a shelter permission with no expiry. The older policy survives at the mirror junction. Noor can compare both copies without replacing either. Keep the disagreement visible; someone benefits whenever a convenient explanation erases an inconvenient timestamp."),
        (6, "Yara's independent clock caught the missing minute, and the refund prompt borrowed our recovery wording. The transit schedule received the stolen permissions next. Mina can inspect one suspicious departure while the ordinary routes keep running. Let her protect those travelers."),
        (4, "The old workshop image was genuine, but its 'resume after victory' line was added later. Dee kept both versions. Your next lead is the checkpoint power record. Ada can read the hidden transmission without opening the passenger list; use the narrow question."),
        (2, "Both Niko and Lio received unwanted connections after their trials. Jun preserved the separate timestamps. The update crossed a municipal relay under a valid service ticket. Ask Ada how a revoked ticket kept working; that is the part we can investigate next."),
        (1, "Niko's receipt is safely with Jun. His terminal also opened an extra recovery connection after the battle. We know those two things happened; we do not yet know who joined them. Follow the repair-kiosk address and keep the original timing in the file."),
    )
    mara["dialogue_variants"] = [
        {"requires_completed": [f"ghost_{index:02d}_quest"], "lines": [line]}
        for index, line in hub_updates
    ]

    previous_quest = None
    for index, chapter in enumerate(CHAPTERS, 1):
        rid, mid = f"ghost_{index:02d}", CAMPAIGN_MAPS[index]
        qid, tid = f"{rid}_quest", f"{rid}_trainer"
        badge = {"id": rid, "name": f"Access Proof {index:02d}", "color": "#77dfef",
                 "description": f"Verified report {index} of 30: {chapter['quest']}. This proof is permanent and is not consumed by portals."}
        final = index == 30
        region = {"id": rid, "name": chapter["name"],
                  "subtitle": chapter["quest"], "synopsis": chapter["brief"],
                  "level_min": chapter["level"], "level_max": chapter["level"],
                  "index": index, "badge": badge, "maps": [mid], "npc_ids": [],
                  "trial_ids": [qid, FINAL_NPC_ID if final else tid], "quest_ids": [qid],
                  "warden_id": qid, "peaceful": False,
                  "objective": ("Accept Iona's final case review, return to seal all thirty access proofs, then defeat Mara Vale's level 99 team."
                                if final else f"Accept '{chapter['quest']}' from {chapter['giver']}; defeat {chapter['trainer']}; return with the report to open the next portal.")}
        regions.append(region)
        add_map(mid, rid, chapter["name"])
        prerequisite = [previous_quest] if previous_quest else []
        start = [chapter["brief"], chapter["task"]]
        progress = [f"Case: {chapter['quest']}.",
                    ("Return to Iona to verify the complete case and receive Access Proof 30 before challenging Mara."
                     if final else f"Defeat {chapter['trainer']}'s level {chapter['level']} team, then return to {chapter['giver']} with the witness record. The forward portal opens when you finish that report.")]
        ready_report = (["The final case file is ready for your review. Confirm the report to seal the independent recovery routes, receive Access Proof 30, and unlock Mara's final battle."] if final else
                        ["The witness battle is recorded. Complete this report to review the evidence, receive your access proof and supplies, and open the next portal."])
        quest = _npc(rid, "quest", chapter["giver"], 65 if chapter["giver"] == "Case Lead Iona" else (23, 38, 69, 51)[(index - 1) % 4],
                     "quest", mid, PLACEMENTS[mid][1],
                     {"intro": start, "ready": start, "quest_start": start,
                      "quest_progress": progress, "quest_complete": ready_report,
                      "locked": ["Finish the previous field's investigation and submit its report before opening this case."],
                      "won": [chapter["report"], ("Final investigation complete. Mara's level 99 team is now available at the root console. The return uplink opens after the campaign is complete." if final else f"Access Proof {index:02d} recorded. Your supplies are in your usual bag, and the forward portal is open. Earlier fields and the Backchannel remain available for return visits.")],
                      "lost": ["This case remains open. Recover with the medic and return when your partners are ready."],
                      "repeat": [chapter["report"], "Your report, access proof, and first-clear rewards are already recorded."],
                      "after_reveal": [chapter["recovery"] if final else f"Witness testimony from {chapter['trainer']}: {chapter['recovery']}"],
                      "campaign_complete": [f"Case follow-up from {chapter['trainer']}: {chapter['after']}" if not final else chapter["after"]]},
                     requires=prerequisite, quest_requires=[] if final else [tid],
                     quest_title=chapter["quest"],
                     objective=("Verify the complete case with Iona, then challenge Mara." if final else f"Defeat {chapter['trainer']}, then return to {chapter['giver']}."),
                     reward=_reward(index), badge=rid, reveal_on_complete=index == 26)
        add_npc(quest, region)
        if not final:
            hacked = index <= 23
            trainer = _npc(rid, "trainer", chapter["trainer"], (22, 60, 14, 44, 30, 16, 69, 87)[(index - 1) % 8],
                           "trainer", mid, PLACEMENTS[mid][4],
                           {"intro": [chapter["challenge"]],
                            "ready": [chapter["challenge"], f"Agreed story trial: level {chapter['level']}. Return to {chapter['giver']} after your victory. This tamer battle awards no scan."],
                            "locked": [f"Speak with {chapter['giver']} and accept '{chapter['quest']}' first. We need an agreed case record before beginning this trial."],
                            "won": [chapter["victory"]], "lost": [chapter["loss"]],
                            "repeat": [chapter["recovery"], "This case battle is complete. Use field training for more practice; the witness is not required to repeat the incident."],
                            "hacked_repeat": [chapter["recovery"]],
                            "after_reveal": [chapter["recovery"], "Iona has identified the person behind the stolen permissions. The recovery team is working with each witness; nobody is being asked to surrender their partners."],
                            "campaign_complete": [chapter["after"]]},
                           requires=prerequisite, requires_accepted=[qid],
                           team=[{"species": sid, "level": max(1, chapter["level"] - offset)}
                                 for offset, sid in enumerate(chapter["team"])],
                           reward=_reward(index, battle=True), hacked_after_victory=hacked,
                           repeatable=False)
            add_npc(trainer, region)
        for suffix, name, tamer, role, slot, lines in (
            ("healer", "Field Medic Mira", 64, "healer", 2, [
                f"You can recover here before the level {chapter['level']} trial. I restore your active team for free. Your accepted cases, completed reports, and access proofs survive a loss, so take the time your partners need."]),
            ("shop", "Field Quartermaster Len", 34, "shop", 3, [
                "These supplies use your usual shop, currencies, and bag. Your DigiLab, DigiFarm, and team menus remain available throughout the case. You can also revisit the Backchannel or any earlier unlocked field whenever you need to prepare."]),
        ):
            add_npc(_npc(rid, suffix, name, tamer, role, mid, PLACEMENTS[mid][slot],
                         _dialogue(lines, ["The case is complete, and these services remain available. Your real team, usual supplies, DigiLab, and DigiFarm continue with you wherever you travel next."])), region)
        if index in MARA_FIELDS and not final:
            lines = [chapter["intel"]] if index >= 26 else [MARA_PRE_INTEL[index]]
            intel_actor = add_npc(_npc(rid, "mara", "Mara Vale", 31, "intel", mid, PLACEMENTS[mid][7],
                         _dialogue(lines), character_id=MARA_CHARACTER_ID,
                         hide_on_campaign_complete=True, hide_on_reveal=index < 26,
                         show_requires_reveal=index >= 26), region)
            if index < 26:
                intel_actor["dialogue_variants"] = [{"requires_completed": [qid], "lines": [chapter["intel"]]}]
        previous_quest = qid

    # Portal travel is a linear, readable case route; every previous destination
    # remains accessible. The final map's completion uplink returns to the hub.
    for index, region in enumerate(regions[:-1]):
        source, target = region["maps"][0], regions[index + 1]["maps"][0]
        for frm, to, slot, gate in ((source, target, 8, region["id"] if index else None),
                                    (target, source, 6, None)):
            point = PLACEMENTS[frm][slot]
            maps[frm]["exits"].append({"id": f"{frm}_to_{to}", "to_map": to, "map_id": to,
                "name": maps[to]["name"], "x": float(point[0]), "y": float(point[1]),
                "requires_badge": gate})
    final_region, final_chapter = regions[-1], CHAPTERS[-1]
    final_mid = final_region["maps"][0]
    point = PLACEMENTS[final_mid][8]
    maps[final_mid]["exits"].append({"id": "ghost_final_uplink", "to_map": hub_mid, "map_id": hub_mid,
        "name": "Backchannel Uplink", "x": float(point[0]), "y": float(point[1]),
        "requires_badge": None, "requires_campaign_complete": True})
    final = _npc(final_region["id"], "regent", "Mara Vale / Null Regent", 31, "final",
                 final_mid, PLACEMENTS[final_mid][5],
                 {"intro": [final_chapter["challenge"]],
                  "ready": [final_chapter["challenge"], "Final story battle: three level 99 Digimon. Your real party keeps its current levels and stats. Victory ends the campaign and permanently unlocks +20% Shiny wild-victory scan gain."],
                  "locked": ["Complete all thirty field investigations, including Iona's final case review here. The complete access-proof set and its recorded quests are required before you can confront the root operator."],
                  "won": [final_chapter["victory"]], "lost": [final_chapter["loss"]],
                  "repeat": ["The root session is closed. Mara has left the network permanently."]},
                 character_id=MARA_CHARACTER_ID, hide_on_campaign_complete=True,
                 show_requires_reveal=True, requires_reveal=True,
                 requires=[f"ghost_{index:02d}_quest" for index in range(1, 31)],
                 requires_badges=[f"ghost_{index:02d}" for index in range(1, 31)],
                 team=[{"species": species, "level": 99} for species in final_chapter["team"]],
                 display_level=99, battle_name="Null Regent: Mara Vale",
                 reward={"credits": 50000, "items": {"hp_l": 10, "sp_l": 10}, "shiny_scan_bonus": 20},
                 repeatable=False)
    final["id"] = FINAL_NPC_ID
    add_npc(final, final_region)
    result = {"id": CAMPAIGN_ID, "name": CAMPAIGN_NAME, "version": 1,
              "regions": regions, "maps": maps, "npcs": npcs, "challengers": [],
              "champion_id": FINAL_NPC_ID, "final_id": FINAL_NPC_ID,
              "start_map": hub_mid, "badge_count": 30,
              "completion_reward": {"shiny_scan_bonus": 20},
              "introduction": "A private cyber investigation across one safe hub and thirty Super Xros fields. Follow the witnesses, defeat quest tamers, and uncover the person behind a stolen-permission network. Complete the case for permanent +20% Shiny wild-victory scan gain.",
              "epilogue": {"npc_id": "ghost_30_quest", "lines": [
                  "Iona: The root session is closed. Mara's access is permanently revoked, and the case team has removed her from the network. She will not return to the Backchannel or any campaign field. The evidence remains sealed for the witnesses, with her choices recorded under her own name.",
                  "Niko: Every witness has a route that does not depend on her. Some wanted their old tools repaired; some wanted a fresh start. We asked, and we kept their answers. Our Digimon stayed with us. Nobody had to give up a partner to get their own life back.",
                  "Iona: Super Xros: Ghostline complete. Shiny Scan Mastery is now permanent: eligible Shiny wild victories award 6% scan instead of 5%, a 20% increase. The bonus follows your character into every region, never stacks from repeated claims, and does not change the 1% Shiny encounter chance.",
                  "Iona: Thank you for following the evidence when it stopped telling a comfortable story. The Backchannel uplink is open, all thirty proofs remain yours, and your usual DigiLab and DigiFarm are ready. Visit our witnesses whenever you like. For once, the next destination is simply a choice.",
              ]}}
    _validate(engine, result)
    engine._xros_story_content = result
    return result


def _validate(engine, data):
    """Fail clearly on missing art, opponents, prerequisites or unsafe rewards."""
    npcs = data["npcs"]
    for npc in npcs.values():
        if npc["tamer"] not in engine.tamers:
            raise ValueError(f"Ghostline NPC portrait is missing: {npc['tamer']}")
        if npc["map_id"] not in data["maps"]:
            raise ValueError(f"Ghostline actor map is missing: {npc['id']}")
        if npc["tamer"] == "tamer_031" and npc.get("character_id") != MARA_CHARACTER_ID:
            raise ValueError("Mara's reserved portrait cannot be reused by another campaign actor")
        for partner in npc["team"]:
            species = engine.species.get(partner["species"])
            if not species or species.get("shiny") or species.get("paradox") or species.get("firewall"):
                raise ValueError(f"Ghostline authored teams require normal existing Digimon: {partner['species']}")
            if not 1 <= partner["level"] <= 99:
                raise ValueError("Ghostline battle levels must be between 1 and 99")
        if any(key in npc["reward"] for key in ("training_level", "level_floor", "partner")):
            raise ValueError("Ghostline must not replace or silently raise the account's real party")
        for prerequisite in (*npc["requires"], *npc["requires_accepted"], *npc.get("quest_requires", [])):
            if prerequisite not in npcs:
                raise ValueError(f"Unknown Ghostline prerequisite: {prerequisite}")
        if npc.get("character_id") == MARA_CHARACTER_ID and not npc.get("hide_on_campaign_complete"):
            raise ValueError("Every Mara actor must disappear permanently after completion")
    if npcs[FINAL_NPC_ID]["repeatable"]:
        raise ValueError("Ghostline's final nemesis cannot be rematched after completion")
