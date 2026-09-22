# Original Dawn battle effect frames

These images decode the supplied ROM's `dat/bgeff` NCGR character tiles, NCLR
palettes and NSCR screen maps after Nintendo RLE30 decompression. Tile-map
palette banks, horizontal and vertical flips, and indexed transparency are
preserved. Each sequence shares a common crop so its frames do not shift.

96 unambiguous effect groups are exported as 1,022 frames. Each group has
one character bank or one screen map, so no pairing between independent
character and screen animation streams needs to be guessed. Other compound
groups remain unexported pending verification of Dawn's custom descriptor.

Frame order follows the source indices. Playback cadence (0.08 seconds per
frame) is chosen for Venom NXT; original effect timing is not yet decoded.
Element assignments in the catalog were selected by visual appearance.
These are original decoded pixel assets, not generated replacements.

Regenerate with:

    python tools/nds_effects.py "path/to/Digimon World - Dawn (USA)(4).nds"
