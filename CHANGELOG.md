# Changelog

## 0.2.0
- Photo recognition now covers all 25 elements (the beta recognized only boundary, wall, player start, enemy spawn and door).
  Terrain (grass, water, lava, ice, mud, conveyor), markers (exit, checkpoint, patrol waypoint) and every interactable are read from the photo.
- The player start is an arrow (its direction sets the facing); a star is now the torch.
- More forgiving of real phone photos: small, thick, shaky symbols; triangles/circles/boxes left open at a corner; neighbouring symbols
  are no longer merged when each already reads as a symbol; an open "M" is lava; asterisks are spike traps.
- New `tools/glyph_draw.py` hand-drawn renderer shared by the drawing guide and the demo sheet.
- Removed the beta banner and notices, and the status text and "On the map" lines from the Library.
- Bent hand-drawn walls (L, U, S shapes) are no longer mistaken for jagged breakable lines (they were turned into rows of breakable props).
