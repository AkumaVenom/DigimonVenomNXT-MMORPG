# Independent Ghostline narrative and spatial review

Reviewed all 30 field narratives, the safe-hub conversations, staged intel updates, victory/loss/recovery/aftermath branches, actor identities, and assembled NPC/portal placements. No unresolved defects remained after the corrections below.

## Narrative findings

- The investigation follows a coherent chain from a stolen receipt to forged recovery handshakes, permissions created after battles, staged threats, an independent recorder, a live-key challenge, witness recovery, and the final confrontation.
- Mara appears as a trusted recurring intel source, with plausible explanations and escalating contradictions. Her confession follows the completed Signature Vault investigation on campaign map 27; the final nemesis battle occurs on map 31.
- Hub intel is keyed to completed investigations. Field intel distinguishes the initial briefing from evidence obtained after completing the local report. Future locked chapter descriptions and the final identity are redacted before the reveal.
- The cleaner procedure explains why later battles stop creating hacked witnesses. The closing ledger establishes independent recovery routes before Mara's defeat, and the ending explicitly removes her permanently while allowing witness visits and ordinary services afterward.
- Completion text consistently describes +20% Shiny scan gain as 5% becoming 6%, with no change to the 1% Shiny encounter rate.

## Spatial and identity findings

- Exactly 31 existing, distinct Xros maps: one peaceful hub and 30 field chapters.
- Assembled content contains 141 NPC instances and 61 portals. Every instance occupies a validated layout slot; no map contains overlapping actors/portals or two copies of the same character.
- All recurring characters retain one portrait and stable identity. Mara's portrait is exclusive to her ally and final-boss appearances.
- All 279 reserved layout slots have real collision-checked paths from the unchanged public arrival, clear footing, and at least 96 world units of separation. The final completion portal returns to the hub.

## Corrections verified during review

- Aligned the late investigation sequence with the intended map-27 reveal.
- Corrected hub update thresholds and separated field pre-quest/post-quest intel.
- Replaced index-based portrait rotation with stable character identities; separated the field medic from the investigator Bea.
- Attributed witness recovery quotations explicitly rather than making investigators impersonate witnesses. Preserved Iona's own final-case dialogue.
- Updated all healing directions to the actual field medic.
- Moved the caldera portal off the lava-channel edge and onto solid platform artwork, then revalidated its walking route.

Validation: `tests/test_xros_story_layout.py` and `tests/test_xros_story_content.py`: **46 passed**. Reviewed content SHA-256: `7f01ba0c9ab1c211d1d6ee9a38ab629a89933aa7e974325526782d943683be51`. This review complements the engine, protocol, UI, and full-campaign acceptance tests; it is not a substitute for those runtime checks.
