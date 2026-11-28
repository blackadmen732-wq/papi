# SETS: modular, data-driven Blender sets (castle, dojo, bamboo, beach, 2.5D skylines)

A **set** is one JSON file in `library/sets/`. It lists **kit pieces** (procedural, seeded set pieces from
`blender/sets/kit.py`) with positions, sizes and seeds, plus the lighting rig, the weather, camera anchors
(`CAM_*`) and fighter marks (`MARK_*`). `blender/sets/build_set.py` turns the JSON into a `.blend`, can put the
origami samurai on the marks in a pose, and renders preview stills. **A new location = a new JSON file**; no code.

Final Blender renders of a film use a set from `library/sets/` (see the paper-cinema-film skill).

## 1. Run it

Blender 4.5 LTS, headless, Cycles on CPU. On this shared machine: `nice -n 15`, `-t 2`, one Blender at a time.

```bash
B=/opt/blender-dl/blender-4.5.16-linux-x64/blender
# build + two previews (first cam -> castle.png, others -> castle-CAM_x.png)
nice -n 15 $B -b -t 2 -P blender/sets/build_set.py -- --set castle-courtyard \
    --out output/sets/castle.blend --preview output/sets/castle.png --cams CAM_wide,CAM_medium
# with the origami samurai on the marks (role:pose[:demon]; poses from library/poses.json)
... --with-character hero:wide-stance,foe:hasso:demon
# quick look (270x480, 12 samples), no fog, no compositor
... --quick --no-fog --no-post
python3 blender/sets/kit.py            # list every kit piece and its parameters (no Blender needed)
```

| Option | Default | Meaning |
|---|---|---|
| `--set` | `castle-courtyard` | `library/sets/<name>.json` or a path |
| `--out` | `output/sets/<name>.blend` | Saved set (open it in your own scripts and film inside) |
| `--preview` | none | Render stills from `--cams` |
| `--cams` | the set's `preview_cams` | Comma list of `CAM_*` anchors |
| `--with-character` | none | `hero:wide-stance,foe:hasso:demon`: builds `blender/character/origami_samurai.py` on `MARK_<role>`, facing the mark's direction, plus the set's fighter key / fill / rim lights. Add `:trellis` (`hero:chudan:trellis,foe:hasso:trellis`) to place the rigged TRELLIS character instead (`docs/CHARACTER-BLENDER.md`) |
| `--res`, `--samples` | set `render` block, else 540x960, 32 | Preview size and Cycles samples (OpenImageDenoise on) |
| `--quick` | off | 270x480, 12 samples: composition and light check in 15–30 s |
| `--seed` | set `seed` | Re-roll every piece (stones, culms, trees) at once |
| `--exposure` | lighting `exposure` | AgX exposure override |
| `--frame` | 1 | Particles and rain are animated over frames 1–240 |
| `--no-fog`, `--no-post` | off | Skip fog pieces / the compositor (bloom, vignette) |
| `--polyhaven`, `--no-polyhaven` | the set's `polyhaven` | Force the Poly Haven layer (CC0 photo textures + HDRI ambient, §5b) on or off for this build: before/after checks |

## 2. The sets

| Set | Look | Pieces | Notes |
|---|---|---|---|
| `castle-courtyard` | Night, moon, ground fog, warm lanterns and lit windows | gravel, stone path, ishigaki walls left/right with plaster walls on top, yaguramon gate, terrace wall, 5-storey tenshu, treeline, 4 toro, pine, rocks, embers | Full 3D. Duel line on X, camera looks +Y at the keep |
| `dojo-interior` | Day interior, god rays through the barred window band, glowing shoji, dust | floor planks, room (posts, beams, ceiling, renji windows, shoji, alcove + scroll), dust air, motes | Shafts need the fog piece (`dust_air`) |
| `bamboo-forest` | Morning mist, backlit canopy, shafts | forest floor, earth path, bamboo grove (520 culms, keeps the path clear), mossy toro, rocks, mist, motes | Duel line on Y (along the path) |
| `ganryujima-beach` | Dawn over the strait | the `ganryujima` piece (port of `blender/world/build_world.py`) | Same marks and anchors as the v1 world; realistic sand, rocks, bark |
| `edo-village` | Moonlit night street (the look board's night duel): blue sky, the moon over the plaza, warm lanterns, lit shoji | gravel road on earth, 6 machiya + 3 minka (thatch), well under a pine, 2 stalls, bamboo fences, 6 nobori, 5 toro, 3 cherry trees, 2 treelines, petals, ground fog, 15 Poly Haven prop groups (barrels, buckets, baskets, crates, bench, stools, pots, stump + axe, broom, mossy rocks, grass, ferns) | Duel line on X along the road; CAM_medium looks +Y at the minka and the moon. Nothing south of the road between x -3..4 (the medium shot's cone). `library/sets/village-pieces.json` = every village piece in a row, daylight |
| `palace-island` | Dawn over the sea: a sea castle, PAPER CRAFT (`"paper"`), mist on the water | the `ganryujima` piece with its own island off (sea, mountains, clouds, paper sun) + an `ishigaki_base` citadel 44 x 36 m rising 9 m out of the water, a 5-storey `tenshu`, 2 corner turrets, `yaguramon` sea gate, `plaster_wall`s, pines, 2 `toro`, a pine islet (`rocks`) with a red `bridge` to a stone landing; `sea_mist` (420 m box, thinning upward over 2.2 m) + `channel_mist` between the islet and the citadel | Mark, 28 Nov. Marks on the courtyard (z 7.5, flat: `check_marks.py`), duel line on X between the sea gate and the keep; `CAM_courtyard` looks at it. Anchors `CAM_sea`, `CAM_front`, `CAM_aerial`, `CAM_texture` |
| `temple-hill` | Morning: a hill shrine among pines, rising out of valley mist, PAPER CRAFT | `ground`, a `hill` (terrace r 19 m at 6 m, a cut for the stair), `stairs` (30 steps) under a foot `torii` with 2 `toro`, the `shrine` piece on the terrace (torii, lantern path, basin, `shrine_hall`), a `pagoda`, 11 pines, rocks, 3 `treeline`s, `valley_mist` | Mark, 28 Nov ("create building"). Duel line on Y along the shrine path (marks at z 6, flat). Anchors `CAM_approach`, `CAM_terrace`, `CAM_wide` |
| `castle-skyline-2d5` | Dusk, paper-cut layers in haze | small 3D foreground (gravel, path, 2 toro, rocks, pine) + `layers` (trees, castle skyline with lit windows, trees, hills, mountains, clouds) | The 2.5D method of the reference videos: cards at real depths, so camera moves get parallax |

### Paper craft: `"paper": "craft"` (`blender/sets/paper_craft.py`)
The kit's materials are procedural stone, plaster, tile and wood: a set reads as a realistic 3D place, which is right
for some films and wrong for a paper world. A set whose JSON says `"paper": "craft"` is built as a PAPER MODEL of
itself: `build_set.py` runs `paper_craft.apply()` after the pieces, so the saved .blend, its stills and every film
staged in it (`tools/film.sh --set`) wear it. `--paper craft|none` forces it on or off for one build.
```json
"paper": "craft"
"paper": {"look": "craft", "width": 0.03, "angle": 35, "colors": {"earth": [0.19, 0.26, 0.10]}}
```
- every `SET_*` material becomes a paper SHEET of its colour (washi plaster, dark card roofs, kraft stones,
  near-black backfill between them, brown card wood, red card lacquer, green card pine, bark-brown cypress roofs,
  green copper...), each facet its own tone (`facet_rand`); glows (windows, lanterns, shoji) stay. The stone gaps
  must stay near-black: in tan paper too the wall pattern vanished. `colors` recolours a sheet for one set (same
  substring rule as the table `SHEETS` in `paper_craft.py`; the temple hill's earth is moss-green card)
- every set mesh gets fold lines (`add_fold_lines`, folds sharper than `angle`) and the characters' paper surface
  (ink in the valleys, a light edge on the ridges, a mottle), the ink line `width` metres wide: 2-6 cm at
  architecture distance (a character's 3.5 mm line is sub-pixel on a keep 50 m away)
- untouched: the sea, sky, paper sun, mountains and clouds, 2.5D cards, fog, rain, particles (their look is their
  own), and anything outside the SET collection (characters keep their own paper)
- `blender/sets/palace/paperize_set.py --blend <built.blend> --craft` runs the same pass on an already built set
  (without `--craft`: fold lines only)
Measured: palace 37 meshes, ~233k folds, 8.7 s; temple hill 47 meshes, ~121k folds, 4.2 s.

### Are the marks flat? (`blender/sets/check_marks.py`)
```bash
$B -b output/sets/palace-island.blend -P blender/sets/check_marks.py -- --radius 3 --step 0.5 --tol 0.05
```
Casts rays down on a grid round every `MARK_*` (the rule of `production_bake.py` ground_sampler: the highest
up-facing hit on any visible mesh but the sea, sky, characters, fog) and prints the height span, the steepest step
and holes; exit 1 when a patch spans more than `tol` m or has a hole.

## 3. Write a new set (the JSON)

```json
{
  "name": "my-set", "seed": 1, "clear": 1.6,
  "lighting": {
    "preset": "night",                       // night | dusk | dawn | day | overcast (fills everything below)
    "sun": {"elev": 30, "az": 18, "color": [0.55, 0.66, 1.0], "energy": 0.9, "angle": 1.2},  // az 0 = +Y, + toward +X
    "sky": {"type": "night", "zenith": [..], "horizon": [..], "stars": 1.0},   // or nishita / color
    "exposure": 0.9, "look": "AgX - Medium High Contrast", "bloom": 0.8, "vignette": 0.45,
    "fighter": {"lamp_scale": 0.3,            // inner lantern of the samurai
                "key":  {"offset": [-1.6, 2.6, 2.6], "energy": 18, "color": [1, 0.72, 0.45], "size": 1.4},
                "fill": {"offset": [2.6, 1.8, 1.3], "energy": 4, ...},
                "rim":  {"offset": [0.8, -2.8, 2.8], "energy": 60, ...}},   // offsets in the MARK's frame (+Y = facing)
    "pieces": [ {"kit": "fog", ...}, {"kit": "moon", ...} ],               // weather / atmosphere pieces
    "lights": [ {"name": "garden_bounce", "pos": [8, 3, 1.4], "type": "AREA", "energy": 1600, "size": [11, 3], "look": [0, 3, 1.4]} ]
  },
  "materials": {"window_glow": {"strength": 9.0}, "gravel": {"color": [0.22, 0.21, 0.2]}},
  "pieces": [
    {"kit": "ishigaki", "name": "wall_left", "pos": [-9, 2, 0], "rot": 90, "seed": 0, "params": {"length": 26, "height": 5.5}}
  ],
  "marks":   {"MARK_hero": {"pos": [-1.8, 0, 0], "face": [1.8, 0]}},
  "cameras": {"CAM_wide": {"pos": [0.8, -11.5, 1.25], "look": [0, 14, 8.5], "lens": 24},
              "CAM_medium": {"pos": [0.6, -7.5, 1.35], "look_mark": "MARK_center", "look_z": 1.7, "lens": 30, "fstop": 4, "focus": "MARK_center"}},
  "preview_cams": ["CAM_wide", "CAM_medium"],
  "render": {"samples": 32, "res": "540x960", "volume_step_rate": 4.0}
}
```

(The `//` comments are explanations only; real JSON files have none.)

Rules of thumb:
- Units are metres, Z up. Every piece is built in its own frame with its **front facing -Y**; `rot` (degrees about Z)
  turns it: `rot: 90` faces +X, `-90` faces -X, `180` faces +Y. `pos` is its origin (base centre).
- `seed` per piece re-rolls only that piece; the set `seed` re-rolls all. Same seeds = identical set.
- Marks are snapped onto the surface below them (terrain, floor, sand; fog, particles and foliage ignored),
  searching from `snap_reach` (2.5 m) above the mark so roofs over an interior never catch them. `"snap_marks": false` turns it off.
- Scatter pieces (bamboo, rocks) keep `clear` metres free around `MARK_hero`, `MARK_foe`, `MARK_center`, and 0.8 m
  around every camera anchor.
- Materials are keys (below); `"materials": {"key": {kwarg: value}}` overrides a recipe for the whole set, and
  `"stone#2"` makes a second copy of a recipe with its own overrides.
- Put a mark on the duel line and make the camera anchors look at marks (`look_mark`), so moving the duel moves the
  shots. Vertical 9:16: a 24 mm lens sees ±0.42 × distance sideways, so side walls only show in OTS and reverse shots.
- Look at every preview (quick first), change one thing at a time (lookdev skill), then render the 540x960 stills.

## 4. The kit (`blender/sets/kit.py`)

`python3 blender/sets/kit.py` prints this list with every default. Geometry is real (individual stones, planks,
tiles, culms), faceted like folded card, with a faint washi-fibre bump; textures are procedural, with an optional
Poly Haven photo layer on top (§5b).

| Piece | What | Main params |
|---|---|---|
| `ishigaki` | Castle stone wall: battered concave face (ogi-no-kobai), individual irregular stones, wedge stones in the joints, dark rubble in the gaps, earth top | length, height, batter, curve, stone, style (`nozura` rough / `uchikomi` fitted / `kirikomi` dressed), thickness, detail |
| `ishigaki_base` | Four-sided battered platform with sangi-zumi long corner stones | width, depth, height, batter, stone, style |
| `plaster_wall` | Dobei: stone footing, black board skirt, plaster bays between posts, tiled cap, triangle/square loopholes | length, height, thickness, skirt, posts, sama, sama_shape |
| `roof` | Tiled roof: `hip` (upturned corners, concave slopes, plaster eaves, ridge, onigawara, optional golden shachihoko; `v_max` < 1 = pent skirt) or `gable` | width, depth, pitch, overhang, upturn, kind, v_max, shachi |
| `tenshu` | Castle keep: stone base, storeys stepping in, pent roofs, chidori gables, barred windows (share lit), top roof + shachihoko | base_w, base_d, base_h, storeys, storey_h, inset, lit, gables, skirt (black boards) |
| `yaguramon` | Turret gate: two stone blocks, gatehouse storey, posts and lintel, plank doors with iron studs/straps | width, passage, depth, base_h, upper_h, open (0..1), lit |
| `floor_planks` | Staggered planks, own tone each, hairline gaps, polished | width, depth, plank, along, key |
| `tatami` | Mats with dark borders, running bond | nx, ny, mat_l, mat_w |
| `shoji` | Sliding screens, kumiko lattice, translucent washi; `backlight` W adds an area light behind | width, height, panels, cols, rows, backlight, open |
| `room` | Timber hall: posts, beams, ceiling boards, walls per side (`plaster`, `renji` barred window band, `shoji`, `wood`, `open`), wainscot, alcove with scroll, roof slab | width, depth, height, walls, window_z, window_h |
| `torii` | Myojin torii, leaning pillars, curved kasagi, plaque | height, span, key, upcurve |
| `toro` | Kasuga stone lantern; paper firebox with a warm point light inside | height, lit, energy, color |
| `stairs` | Dressed stone steps (2–3 blocks each) with cheeks, climbing +Y | width, steps, rise, run |
| `bridge` | Arched taikobashi: deck planks, stringers, red rails with finials, piers | length, width, arch, rails |
| `ground` | Bumpy ground plane | width, depth, key (`gravel`, `gravel_wet`, `sand`, `earth`, `forest_floor`), bumps, edge_rise |
| `paving` | Ishidatami slab path | length, width, along |
| `bamboo_grove` | Leaning culms with node rings, twigs and folded leaves; keeps paths and marks clear | width, depth, count, height, radius, lean, leaves, path, clear |
| `pine` | Garden kuromatsu: kinked leaning trunk, cloud pads with needle tufts | height, spread, lean, lean_dir, pads |
| `cherry` | Sakura: recursive branches, blossom puffs, fallen petals | height, spread, depth, blossoms, petals_ground |
| `rocks` | Noise-displaced mossy boulders | count, radius, size, squash, sink |
| `treeline` | Cheap conifer silhouettes for skylines behind walls | width, depth, count, height |
| `layers` | **2.5D backdrop**: paper-cut silhouette cards (`mountains`, `hills`, `trees`, `clouds`, `castle` with lit windows, or `image` = a PNG with alpha) at real depths, coloured toward a haze colour with distance, lit a little from inside | layers [{shape, dist, height, x, z, color, haze, seed, storeys, image}], haze_color, glow, translucency |
| `fog` | Volume box; `height` = ground mist thinning upward, `noise` = banks. Makes god rays where light is blocked | size, density, color, anisotropy, height, noise |
| `rain` | Crossed thin streaks, seamless looping fall | area, height, count, length, angle, speed |
| `particles` | Pre-rolled particle box: `petals` (tumbling), `embers` (glow, rising), `dust` (motes for shafts), `snow`, `ash` | kind, area, count, size, velocity, brownian |
| `light` | Practical/shaping light: POINT, SPOT (beam in fog), AREA, SUN | type, energy, color, size, look, spot |
| `moon` | Cut-paper moon disc + halo, camera-only | elev, az, size, strength |
| `ganryujima` | The whole v1 island world as one piece | sea, island, rocks, pines, mountains, clouds, paper_sun, realistic |
| `pagoda` | Five-storey pagoda: stone platform, red posts and plaster bays, bracket rings under deep eaves, balconies, tiled pent roofs, bronze spire with nine rings | base_w, storeys, storey_h, taper, overhang, pitch, platform, spire |
| `shrine_hall` | Shinto main hall (nagare-zukuri): round red posts, raised floor, veranda and rail, lattice doors, thick curved cypress-bark roof running long over the front steps, chigi, katsuogi, rope with paper streamers | width, depth, floor_h, wall_h, front_ext, pitch, roof, chigi, katsuogi |
| `shrine` | A whole shrine in one piece: torii, stone path, `lanterns` pairs of toro, purification basin, the hall at the end | path, path_w, lanterns, torii_h, hall {}, torii {}, toro {} |
| `hill` | A mound with a flat terrace (marks stay level), smooth slopes, an optional straight cut down the front for `stairs` | top, base, height, key, cut_width |

### Materials (keys; recipes in `blender/world/paper_materials.py`, section SET MATERIALS)

`stone`, `stone_dark`, `stone_mossy`, `stone_dressed`, `stone_lantern`, `backfill` (granite / andesite: per-stone
tone, grain, flecks, cracks, moss on top faces, rain grime, AO crevice dirt, wet option) · `plaster`, `plaster_old`,
`plaster_earth` (lime plaster: drift, hairline cracks, rain streaks, splash-back) · `wood`, `wood_dark`,
`wood_dark_z`, `wood_aged`, `wood_light`, `wood_floor`, `wood_floor_y`, `wood_post` (grain rings + streaks along
an axis, per-plank tone, edge wear, polish) · `tile` (kawara: per-tile tone, sheen, lichen) · `lacquer_red`,
`lacquer_black` (glossy coat, worn edges) · `shoji`, `lantern_paper` (translucent washi) · `tatami`,
`tatami_border` · `gravel`, `gravel_wet`, `sand`, `earth`, `forest_floor` · `bamboo`, `bamboo_node`,
`bamboo_leaf`, `pine_needle`, `blossom`, `maple_red`, `bark`, `bark_cherry` · `iron`, `gold` · `window_glow`,
`window_dark` · `paper`, `cloth_dark`, `cloth_red` · `rain`, `ember`, `petal`, `dust`.

Every recipe reads the `piece_rand` face attribute (one random per stone / plank / tile / culm, written by the kit's
mesh builder) and `facet_rand`, so neighbours never share a tone. To add a material: write a function in
`paper_materials.py` and a line in `_M()` in `kit.py`.

### Add a piece

```python
@piece('lantern_post', height=2.4, energy=20.0)
def lantern_post(ctx, P, rnd):
    """One line that the list shows. Built in local space, front -Y."""
    mb = MB(ctx, ctx.info['name'], rnd)          # one mesh, a material slot per key
    mb.box('wood_post', (0.12, 0.12, P['height']), loc=(0, 0, P['height'] / 2), bevel=0.01)
    mb.finish()
    ctx.light('POINT', (0, 0, P['height']), P['energy'], (1, 0.55, 0.2), name=ctx.info['name'] + '_flame')
```
Helpers: `MB.box / cyl / stone / tube / grid / poly`, `tile_patch`, `hip_roof`, `gable_roof`, `stone_face`,
`ishigaki_block`, `shoji_panels`, `beam_between`; village: `thatch_roof` (kit_village.py).

**Village pieces** (`blender/sets/kit_village.py`, registered into the same KIT): `minka` (posts on foundation stones,
earthen walls, doma, shoji bays, engawa, a thick steep straw hip roof with ridge sticks), `machiya` (lattice front,
noren, tiled pent roof, clay-slat windows, tiled gable roof, a paper lantern that lights the street), `well`,
`bamboo_fence` (`kenninji` / `yotsume`), `stall`, `nobori`, `chochin`, and `ph_prop`: a Poly Haven model
(library/polyhaven.json "models") reduced to flat facets with its own photo textures, `count` copies scattered off
the fight marks. New material keys: `thatch` (Poly Haven `thatch_roof_angled` photo layer), `thatch_dark`,
`thatch_edge`, `noren_indigo`, `banner_white`.

**Temple pieces** (`blender/sets/kit_temple.py`, registered the same way): `pagoda`, `shrine_hall`, `shrine`,
`hill` (table above). New material keys: `cypress` (bark-shingle roofs), `cypress_edge`, `copper` (green ridge),
`rope`, `shide` (paper streamers).

**Piece names are unique per set** (set pieces + `lighting.pieces`): `build_set.py` refuses a repeat, because a
second piece of the same name replaces the first one's material (27 Nov: a castle lighting block copied into the
village brought its own `fog`, which emptied the village fog's material and fogged the sky black).

## 5. Lighting presets

| Preset | Sky | Sun / moon | Exposure | Use |
|---|---|---|---|---|
| `night` | Gradient + stars | Moon, blue, 30–40° | ~0 to +1 | Lanterns, lit windows, fog glow |
| `dusk` | Nishita, sun just above horizon | Orange, low | ~-1 | Backlit paper cards (2.5D), silhouettes |
| `dawn` | Nishita | Warm, 4° | ~-2.3 | Ganryujima |
| `day` | Nishita | White, 30–40° | ~-3 outdoors, ~-0.6 interiors | Shafts through windows / canopy |
| `overcast` | Flat grey | Weak | ~-0.5 | Soft, rain |

Fighters always get the three-point rig from `lighting.fighter` (key, fill, rim area lights placed in the mark's
frame), plus their inner lantern (`lamp_scale`). The rim is what separates a paper figure from a dark set: keep it
the brightest of the three at night. Compositor: bloom (glare) and a soft vignette.

## 5b. POLYHAVEN: real CC0 texture detail and HDRI ambient (`"polyhaven": true`)

All five sets have `"polyhaven": true` (bamboo: `{"hdri": "forest"}`). It adds two things and keeps the paper look:

1. **Photo detail in the set materials.** Each recipe has a `ph` role (`stone`, `stone_rough`, `plaster`, `wood`,
   `wood_floor`, `roof_tiles`, `gravel`, `sand`, `earth`, `forest_floor`, `bamboo`, `bark`, `bark_cherry`, `tatami`;
   set in `_M()` in `kit.py`). `ph_layer()` in `paper_materials.py` projects the Poly Haven maps triplanar in object
   space (kit meshes have no UVs; sharp blend so facets stay crisp; offset per stone / plank by `piece_rand`) and mixes
   them **into** the procedural result: the photo's light/dark pattern multiplies the procedural colour (`detail`),
   its hue pulls only a little (`tint`), its displacement joins the procedural + washi-fibre bump (`bump`), its
   roughness and AO (both normalised to their mean) vary roughness and darken crevices. True-normal facets, fibre
   and per-piece tone stay. Paper, shoji, lacquer, foliage and glow materials get no photo layer.
2. **HDRI ambient** (`build_set.py` `add_hdri`). Diffuse rays (and 25 % of glossy rays, `reflect`) see a Poly Haven
   HDRI; the **camera still sees the procedural sky**. The HDRI is normalised to the mean radiance of the procedural
   sky it replaces (a 128×64 equirect probe render, `gain` 1.0 = same), its colour pulled 70 % to the procedural
   sky's average colour (`match`, so the art-directed mood stays), its photographed sun clamped off (`clamp` × mean:
   the set's sun / moon lamp keeps the only hard shadow) and its brightest spot turned to the set's sun azimuth.
   Key / fill / rim and practical lights are untouched.

```json
"polyhaven": true                                         // textures + the preset's HDRI (night/dusk/dawn/day/overcast)
"polyhaven": {"hdri": "forest", "detail": 0.8}            // other HDRI role; detail scales every role's detail/tint/bump
"polyhaven": {"textures": false, "hdri": {"role": "night", "gain": 1.3, "match": 1.0}}
"materials": {"gravel": {"ph": null}, "stone": {"ph": {"role": "stone", "tile": 3.0}}}   // per material
```

Assets: `python3 tools/polyhaven.py sync` downloads every id in `library/polyhaven.json` (role → id + mix settings)
to `assets/polyhaven/<id>/` (≈95 MB, not committed; textures 1k, stone/plaster/gravel 2k, HDRIs 2k);
`assets/polyhaven/CREDITS.md` (committed) lists id, name, authors, CC0. `search <words> [--type hdris]` and
`get <id> [--res 2k]` find and add more. Without the cache the build prints a warning and stays procedural.

What it changed (540×960, 24 spp, before/after sheets `output/sets/ph-<set>.png`): gravel reads as real river
pebbles with moonlit glints (castle, skyline), the bamboo path and forest floor get stones, twigs and leaf litter
(the biggest gain), the beach sand gets grain, the dojo ceiling and plaster get subtle wood grain and stains. Cost:
+10–30 % render time and +1–2 s build (measured CAM_medium / dojo CAM_wide, before → after: castle 117 → 145 s,
dojo 158 → 205 s, bamboo 100 → 126 s, beach 68 → 74 s, skyline 52 → 64 s). Weak spots: the dressed path stones of the skyline read a
little darker than before; roof tiles change little (the relief is modelled); a too-high `detail` on plaster or wood
looks like dirt, keep plaster ≤ 0.4.

## 6. Render settings and measured times

Cycles CPU, OpenImageDenoise, adaptive sampling, light tree, volume step rate 2–4, 6 bounces (volume 0: single
scattering is enough for shafts). Container with 4 shared CPUs, `nice -n 15`, `-t 2`.

Measured 2026-11-23. "Quick" = `--quick` (270×480, 12 spp) on a lightly loaded machine; "Final" = 540×960,
24 spp, while another agent was also rendering (load 11–15 on 4 CPUs), so expect them faster on a quiet machine.
All include the two origami samurai.

| Set | Build (s) | Faces | Quick still | Final still (540×960, 24 spp) |
|---|---|---|---|---|
| `castle-skyline-2d5` (2.5D) | 0.4 | 7 k | 7.6 s | CAM_wide 112 s, CAM_medium 116 s |
| `castle-courtyard` (full 3D, fog) | 35–55 (the keep's tiled roofs: 30–50) | 237 k | 14–15 s | CAM_wide 204 s, CAM_medium 281 s |
| `dojo-interior` (fog, sun shafts) | 1.8 | 14 k | 20–21 s | CAM_wide 281 s |
| `bamboo-forest` (mist, 520 culms, 1.2 M faces) | 5–6 | 1.2 M | 16–34 s | CAM_wide 199–208 s |
| `ganryujima-beach` (ocean) | 0.5 | 21 k | 10 s | CAM_medium 124 s |

2.5D versus full 3D at the same framing and size: about half the render time (112 s vs 204 s for CAM_wide under
the same load) and 0.4 s vs 35–55 s to build, with 3 % of the faces.

A 1080×1920 frame costs about 4× the 540×960 time. Fog volumes are the main cost; `--no-fog` for layout checks.
The 2.5D cards cost almost nothing: the `castle-skyline-2d5` skyline is cheaper than the courtyard's keep alone.

## 7. Known weaknesses

- **Characters**: the origami samurai (`blender/character/origami_samurai.py`) is still a set of crude boxes and
  frustums; it is now matte paper with a soft inner glow (`fighter.lamp_scale`, `seam_glow`, `inner_glow`), but it
  does not yet have the crisp folded facets of `research/ref-origami-samurai-standing.jpg`. It is the weakest
  element in every still.
- Castle: the wide shot has too much empty gravel in the lower third (dress it: a lantern or rocks near the camera,
  raked gravel lines); pine pads read as dark blobs at night; roof tile relief only reads in close shots; the keep
  takes 30–50 s to build (Python bmesh, not instanced).
- Bamboo: the canopy is dense now but the low backlit sun gives soft mist rather than crisp god rays; add `light`
  SPOT pieces in the mist for hero shafts. 1.2 M faces: the heaviest set to load.
- Dojo: volumetric shafts are faint (the floor stripes carry the effect); fog density 0.05+ shows beams but greys
  the room.
- Ganryujima: the v1 torn-paper foam strips at the waterline still look like white flakes in low shots.
- 2.5D cards are flat colour with a fibre bump; image layers (`shape: image`) are supported but no images are
  committed yet. Particles (embers, petals, dust) are pre-rolled per render; they move when you render later frames.
- Everything is CPU Cycles: a 1080×1920 frame is about 4× the times above. Films belong on a GPU (BLENDER-PLAN §I).
