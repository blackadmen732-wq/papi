# Generated parts: a Tripo head on the paper rig (27 Nov 2026)

A generated mesh is one fused shell, so it is never a character. It is a **rigid part**: a head, a hat, a mask,
a plate, a prop on a socket of the one rig. Everything below is data plus two tools; no part code per model.

## The chain (Kojiro's head: 35 credits, ~20 s of Blender)
| step | command | what it does | Kojiro |
|---|---|---|---|
| 1 concept | `python3 tools/tripo.py image --ref <crop> --prompt "..." --out output/tripo/<n>` | Tripo `generate_image` edits a reference crop into the part, alone, front view | 5 credits |
| 2 model | `python3 tools/tripo.py model --image <concept> --version v3.0-20250812 --out ...` | Tripo `image_to_model`, textured | 30 credits, 70 s, 944k faces |
| 3 manifest | an entry in `library/ai-parts.json` | slot, socket, bone, `cut`, `fit`, `faces`, `sheets`, `glow`, `ink` | `kojiro_head_t1` |
| 4 prepare | `$B -b -P tools/ai_part.py -- <id>` | face found from the eye paint and turned to -Y; seams welded; cut under the chin; fitted (chin, height, centred on the eyes and the neck); reduced; paint baked; sheets per facet; ink + glow masks | 944k -> 4,008 facets, 17 s |
| 5 recipe | `library/character-recipes/kojiro-ai.json` | `drop: face, hair`, `add: kojiro_head_t1` | test recipe |
| 6 check | `$B -b -P blender/character/head_compare.py -- --recipe ... --out ... [--light cinematic] [--poses a,b]` | same cameras on any recipe; the head box in metres; a pose sweep | `output/heads/` |
| 7 film | `film.cast.<id>.recipe` in a film file | one actor on the test recipe, production untouched | `film/kojiro-exchange-ai.json` |

Every task's cost is in `output/tripo/ledger.jsonl` (balance before/after). Raw models stay in `output/` (29 MB);
`tools/tripo.py fetch <task>` downloads one again. The prepared part (`assets/models/ai/<id>/`: part.glb, ink.png,
glow.png, report.json; ~230 KB) is committed.

## The look: paper, not a game model
- **Two sheets, chosen by the paint under each facet**: light paint -> `washi_natural`, dark -> `washi_sumi`
  (new: ink-black washi; `card_charcoal`'s lacquer sheen read grey). Colour changes at fold edges, like real origami.
- **Printed ink** for what is too thin for a facet (brows, eye lines, the hairline): `pm.add_paint()` mixes it
  over the washi from `ink.png`. **Glow** from `glow.png`: the eye slits, amber, strength 3.5.
- **Despeckle**: islands under 10 facets join the sheet around them (an ear tip through the hair).

## Size (Mark: "issue the size")
Chin to crown = 0.225 m, the rig's existing head (mask 1.506-1.731). The kept piece (cut just under the chin to
the bun) is 0.284 m; the face is then ~0.15 m wide, a third of the shoulders, eyes at mid-head (~1.61 m).
The old mask was 0.258 m wide: cartoon-wide.

## What went wrong on the way (so nobody repeats it)
| symptom | cause | fix |
|---|---|---|
| HTTP 403 "error code: 1010" | Cloudflare refuses Python's default User-Agent | `tools/tripo.py` sends its own |
| results "NOT DOWNLOADED" | results live on `tripo-data.rg1.data.tripo3d.com`, outside the network list | host added to the environment |
| `v3.5-20260815` "version invalid" | that version is apiv3-only; this key is on the v2 API (`api.tripo3d.ai`) | `v3.0-20250812` |
| head shattered into spikes and holes | 30,724 open edges: the mesh is split along every UV seam; reducing a mesh full of borders fans to them | weld first (UVs per corner survive, the bake reads them) |
| head looked down +X | the service's own frame | turn from the eye paint's direction (0.3 deg off +X), snapped to 90 deg |
| centred 7 cm sideways | the light paint near the cut includes a collar the service added | centre on the eyes |
| (Kojiro body) sleeve as a cone, sash on a hanger | a section alone gives the image model nothing to fold | one whole-body concept from TEXT (an image edit keeps the reference's toy proportions), then cut |
| Tripo auto-rig unusable | generic bones, T-pose arm chains in the air, sleeves read as limbs | our own sections bound to our bones (below) |
| (Musashi) 45-75% of every bake pure black | Tripo marked 77% of his paint as METAL (ORM blue, mean 0.705; Kojiro's 0.09 / 0.02) and a diffuse-colour bake is base x (1 - metallic) | `ai_part.py` cuts the Metallic and Transmission inputs before any bake |
| 25% "black" even on the good Kojiro head | the bake's own *clear* painted the gaps between UV islands black, so they counted as misses and fed the ink mask | the target is filled magenta and `use_clear` is off: gaps = magenta = not counted (both heads now 0.0% black) |
| 56% of Musashi's torso sorted as "obi" | the palette came from the CONCEPT (a mid navy robe); the model painted the robe near-black navy, nearer the obi's black | palette from the model's OWN paint (`AI_PART_DUMP=1` + k-means per section) and **zones**: the obi may only be at the waist (0.66-1.09 m) and on the sandal thongs |
| kojiro-ai2 and musashi-ai built ONE sleeve, ONE leg, ONE foot (all day, unseen: 152/152 passed) | the recipe merge keyed parts by slot, so `*_R` replaced `*_L` | one-sided parts are keyed by slot + side (`modular_builder.load_recipe`) and the validator has a `pair` check (a one-sided slot needs both sides; held props exempt) |
| five parallel Tripo tasks each logged the whole 25-credit drop | the ledger measured the balance before/after, and other tasks spent in between | `tools/tripo.py` knows when tasks overlap (file lock + pids) and logs the price table then; the five lines corrected |
| flat skin shelf under Musashi's chin; then a 4 cm gap | a head cut 3 cm under the chin caught the collar; at the figure's own height the head sat above the folded neck | cut just under the chin, the cut to 1.51 m (the neck top) |

## Body sections (one figure, cut, bound to our bones)
`"kind": "body"` in `library/ai-parts.json` (expanded by `blender/character/ai_manifest.py`) turns ONE generated figure
into the standard sections: torso, 2 sleeves, hakama top, 2 hakama legs, 2 feet (+ optional head). One fit for the
whole figure (feet at 0, shoulder line at 1.40 m), then each section keeps its box in rig metres and is bound like
the folded part it replaces (skinned across the same bones, or rigid on one). A section needs one sheet per facet,
not a texture: each facet takes the paint of the OUTERMOST original surface over it (5 rays from outside, cut faces
skipped), the nearest colour among the classes that section may contain, inside that class's zone.
A face needs printed ink, so a head is cut from the same model in head mode (baked): `musashi_head_t1`.

| character | recipe | parts | checks |
|---|---|---|---|
| Kojiro | `kojiro-ai2` | kojiro_head_t1 (own head model) + 8 kojiro_*_t1 | validator 174/174 (both sides, since 27 Nov pm), 5-pose sweep |
| Musashi | `musashi-ai` | musashi_head_t1 + 8 musashi_* from one figure (35 credits) | validator 175/175, 5-pose sweep `output/heads/poses-ai-bodies.png` |
| Armoured samurai (look board) | `samurai-ai` | 9 armored_* from one figure (35 credits): kabuto + menpo, cuirass, shoulder guards + sleeves, skirt plates, legs, feet; folded `kote_plated` forearms | validator 225/225, same sweep |
| Ronin (look board) | `ronin-ai` | ronin_head + 8 ronin_* from one figure (body block `ronin`); ragged trouser hems kept | validator 174/174, sweep `output/cast/ronin-sweep.png` |
| Monk (look board) | `monk-ai` | monk_head + 8 monk_*; torso takes the robe to 0.62 m, the robe below is ONE skirt (`skin: skirt`), trousers under it; no sword | validator 150/150, sweep `output/cast/monk-sweep.png` |
| Noblewoman (look board) | `noblewoman-ai` | noblewoman_head + torso, 2 long sleeves, kimono + red under-skirt as ONE skirt (`skin: skirt`), 2 tabi tips; no legs, no sword | validator 129/129, sweep `output/cast/noblewoman-sweep.png` |

A body block may list its `sections` (a subset), and override `keep`, `faces` and `bind` per section. `"bind":
{"hakama": {"skin": "skirt"}}` weights a long robe by height and side (`modular_builder.skin_skirt`): by distance alone
the Monk's robe tore at the back in a stride. Cast line-up: `$B -b -P blender/character/lineup.py -- --recipes a,b,c
--out output/cast/lineup.png` (1280x720, one camera and light for the whole row).

Kept from the folded library on both: neck, forearm under-sleeve (the hand floated off the cuff without it), hands
(the sword grips swap them), sword. Known limits: a raised arm crumples the skinned sleeve; the forearm under-sleeve
reads as a flat plank in a low dodge.

## Props and headwear (fit `box`)
A prop is fitted by ONE size and anchors in rig rest space (`"fit": {"mode": "box", "size": {axis: m}, "anchor":
{axis: [min|max|mid|eyes, m]}}`, optional `rotate`, `cut`, and `size: {"x_at_eyes": m}` for a hood). Every Tripo
model came out facing +X, three-quarter concepts included. Concept first (5 credits), look at it, then the model (30).

| part | slot | fit | sheets | test recipe |
|---|---|---|---|---|
| `hood_ninja_t1` | face | 0.20 m across the eyes, eyes at 1.615 m, toy bust cut (0.37) | washi_sumi + glowing amber eyes | `assassin-ai` |
| `kabuto_t1` | hat | 0.42 m wide with the side flaps, neck guard at 1.50 m | card_charcoal, card_gold (new), washi_crimson | `ronin-ai-kabuto` |
| `oni_light_t1` | face | a head shell 0.31 m chin to horns, chin 1.50 m | washi_natural, washi_crimson | `kojiro-ai2-oni` |
| `oni_dark_t1` | face | same | card_charcoal, crimson, gold glowing eyes, bleached fangs | `oni-ai` |
| `fan_t1` | accessory (left hand) | 0.44 m open, pivot in the grip, turned point-down | washi_natural, crimson sun, charcoal ribs | `oni-ai` |

Not made: the kasa (the procedural `kasa_wide`/`kasa_narrow` already match the reference; 35 credits for nothing).
All in the catalogue: `$B -b -P blender/character/parts_catalog.py -- --tiles output/character/catalog-new [--only prefix]`,
then `python3 blender/character/parts_catalog.py --sheet output/character/catalog-new` (64 parts, 32 generated).

## Sword fittings (metal, not paper)
A sword is real metal and lacquer (blender/props/katana_real.py), so a generated fitting keeps its **baked paint as
the colour of a metal surface** (`katana_real.ai_fitting`: the colour texture on a metallic 0.85 / roughness 0.38
shader) instead of paper sheets per facet: a tsuba's wave openwork is far finer than any facet.
- `tsuba_shiokaze_t1` (round iron, openwork waves, gold crests; 35 credits): fitted in the SWORD's frame (guard at
  x 0, blade +x), 82 mm across. Tripo made the guard a 42%-deep puck, so the box fit **squashes** one axis
  (`fit.squash: {x: 0.007}`) to 7 mm after the uniform scale. The UV gaps of the bake are filled from their
  neighbours (16 rings) so no magenta bleeds into tiny islands. Used by `library/swords/shiokaze.json`
  (`tsuba.part`), shown by `blender/bench/sword_designs.py --guards 1`.
- Musashi's oar bokken (`output/tripo/board/model-bokken.pbr.glb`, 3 concepts + 1 model = 45 credits): the image
  model put a guard on every "sword" (two concepts); described as "a long curved stick carved from a boat oar, one
  continuous piece" it came out right. Next: fitted in the weapon frame (1.38 m, handle end at -0.33 m) and swapped
  in for the procedural bokken (queue item 10).
