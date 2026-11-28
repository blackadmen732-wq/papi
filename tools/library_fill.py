#!/usr/bin/env python3
"""LIBRARY FILL: Poly Haven models (CC0) -> paper -> the asset library (docs/LIBRARY.md), from library/library-assets.json.

    python3 tools/library_fill.py build [ids...] [--force]      # download (1k), paperize -> output/library/paper/<id>/
    python3 tools/library_fill.py sheet [ids...] --out <png>    # contact sheet of the stills, to LOOK at them
    python3 tools/library_fill.py publish [ids...] --checked "<what was looked at>"
                       # upload original/..., paper.glb, preview.png, paper.json; one catalogue row each
    python3 tools/library_fill.py status                        # built / published per id, MB so far

Library layout per asset: poly-haven/<id>/original/<the .gltf, .bin, textures/...>, poly-haven/<id>/paper.glb,
poly-haven/<id>/preview.png, poly-haven/<id>/paper.json. Row: id poly-haven/<id>, kind, source poly-haven, licence CC0,
title (name and authors), tags, the three paths, size_m [x, y, z], tris (paper), credits 0 (free), checked.
The free plan is 1 GB in all and 50 MB a file: `build` refuses a model whose largest 1k file is over 50 MB.
"""
import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(REPO, 'tools'))
import library as L  # noqa: E402
import polyhaven as PH  # noqa: E402

B = os.environ.get('BLENDER', '/opt/blender-dl/blender-4.5.16-linux-x64/blender')
MANIFEST = os.path.join(REPO, 'library', 'library-assets.json')
OUT = os.path.join(REPO, 'output', 'library', 'paper')
DONE = os.path.join(REPO, 'output', 'library', 'published.json')


def entries(ids):
    M = json.load(open(MANIFEST))['poly-haven']
    return [(i, M[i]) for i in (ids or M)]


def src_gltf(aid):
    d = os.path.join(PH.CACHE, aid)
    g = [f for f in sorted(os.listdir(d)) if f.endswith('.gltf')] if os.path.isdir(d) else []
    return os.path.join(d, g[0]) if g else None


def build(ids, force=False):
    for aid, e in entries(ids):
        out = os.path.join(OUT, aid)
        if not force and os.path.exists(os.path.join(out, 'preview.png')):
            print('[fill] %s: built' % aid)
            continue
        if not src_gltf(aid):
            PH.get(aid, '1k')
        g = src_gltf(aid)
        big = max(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(os.path.dirname(g)) for f in fs)
        if big > 50 * 1024 * 1024:
            print('[fill] %s: a file is %.0f MB, over the free plan\'s 50 MB: skipped' % (aid, big / 1e6))
            continue
        cmd = [B, '-b', '-P', os.path.join(REPO, 'tools', 'paperize_model.py'), '--', '--in', g, '--out', out,
               '--id', 'poly-haven/' + aid, '--faces', str(e.get('faces', 1500)), '--cards', str(e.get('cards', 24000))]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
        line = [l for l in r.stdout.splitlines() if l.startswith('[paperize]')]
        print('[fill] %s: %s' % (aid, line[-1] if line else 'FAILED\n' + r.stdout[-1500:] + r.stderr[-1500:]), flush=True)


def sheet(ids, png, cols=6, cell=256):
    from PIL import Image, ImageDraw
    items = [(aid, os.path.join(OUT, aid, 'preview.png')) for aid, _ in entries(ids)]
    items = [(a, p) for a, p in items if os.path.exists(p)]
    rows = (len(items) + cols - 1) // cols
    im = Image.new('RGB', (cols * cell, rows * (cell + 18)), (20, 20, 20))
    dr = ImageDraw.Draw(im)
    for k, (aid, p) in enumerate(items):
        x, y = (k % cols) * cell, (k // cols) * (cell + 18)
        im.paste(Image.open(p).convert('RGB').resize((cell, cell)), (x, y))
        dr.text((x + 4, y + cell + 3), aid[:36], fill=(230, 230, 230))
    os.makedirs(os.path.dirname(os.path.abspath(png)), exist_ok=True)
    im.save(png)
    print('[fill] contact sheet of %d stills -> %s' % (len(items), png))


def published():
    return json.load(open(DONE)) if os.path.exists(DONE) else {}


def publish(ids, checked):
    done = published()
    for aid, e in entries(ids):
        out = os.path.join(OUT, aid)
        if not os.path.exists(os.path.join(out, 'preview.png')):
            print('[fill] %s: not built' % aid)
            continue
        st = json.load(open(os.path.join(out, 'paper.json')))
        d = os.path.dirname(src_gltf(aid))
        meta = json.load(open(os.path.join(d, 'meta.json')))
        base = 'poly-haven/%s' % aid
        orig = None
        for r, _, fs in os.walk(d):
            for f in sorted(fs):
                if f.endswith('.part'):
                    continue
                rel = os.path.relpath(os.path.join(r, f), d)
                L.put(os.path.join(r, f), '%s/original/%s' % (base, rel))
                if f.endswith('.gltf'):
                    orig = '%s/original/%s' % (base, rel)
        for f in ('paper.glb', 'preview.png', 'paper.json'):
            L.put(os.path.join(out, f), '%s/%s' % (base, f))
        row = {'id': base, 'kind': e['kind'], 'source': 'poly-haven', 'licence': 'CC0',
               'title': '%s (Poly Haven: %s; %s)' % (meta.get('name', aid), ', '.join(meta.get('authors', [])), meta.get('url')),
               'tags': e['tags'], 'original_path': orig, 'paper_path': base + '/paper.glb',
               'preview_path': base + '/preview.png', 'size_m': st['size_m'], 'tris': st['tris'], 'credits': 0,
               'checked': checked}
        L.call('upsert-row', data=row)
        done[aid] = {'tris': st['tris'], 'size_m': st['size_m']}
        json.dump(done, open(DONE, 'w'), indent=1)
        print('[fill] published %s (%s, %d tris)' % (base, e['kind'], st['tris']), flush=True)


def status():
    done = published()
    mb = 0.0
    for aid, e in entries(None):
        built = os.path.exists(os.path.join(OUT, aid, 'preview.png'))
        g = src_gltf(aid)
        if g:
            mb += sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(os.path.dirname(g)) for f in fs) / 1e6
        if built:
            mb += sum(os.path.getsize(os.path.join(OUT, aid, f)) for f in os.listdir(os.path.join(OUT, aid))) / 1e6
        print('%-28s %-9s built=%-5s published=%s' % (aid, e['kind'], built, aid in done))
    print('[fill] %.0f MB for all of it (free plan: 1000 MB)' % mb)


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    flags = {'--out', '--checked'}
    ids = [x for i, x in enumerate(a[1:], 1) if not x.startswith('--') and a[i - 1] not in flags]
    if a[0] == 'build':
        build(ids, '--force' in a)
    elif a[0] == 'sheet':
        sheet(ids, a[a.index('--out') + 1])
    elif a[0] == 'publish':
        if '--checked' not in a:
            sys.exit('[fill] publish needs --checked "<the still you looked at>"')
        publish(ids, a[a.index('--checked') + 1])
    elif a[0] == 'status':
        status()
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
