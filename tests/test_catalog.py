"""Release-content invariants across the complete supplied catalog."""
from pathlib import Path
import json
from PIL import Image
from venom.common.game import GameEngine

ROOT=Path(__file__).resolve().parents[1]


def test_all_supplied_forms_can_be_encountered():
    engine=GameEngine(ROOT,seed=17)
    reachable=set()
    for normal,paradox in engine._pools.values():
        reachable.update(normal);reachable.update(paradox)
    assert set(engine.species)==reachable
    normal=[s for s in engine.species.values() if not s['paradox']]
    paradox=[s for s in engine.species.values() if s['paradox']]
    assert len(normal)==len(paradox)==502
    assert all(s['base_id'] in engine.species for s in paradox)


def test_every_map_has_matching_collision_and_safe_spawn():
    catalog=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf8'))
    dawn=[m for m in catalog['maps'] if m.get('region_id','dawn')=='dawn']
    world_ds=[m for m in catalog['maps'] if m.get('region_id')=='world_ds']
    assert len(dawn)==254
    assert len(world_ds)==150
    assert len(catalog['maps'])==404
    assert len({m['id'] for m in catalog['maps']})==404
    for area in catalog['maps']:
        with Image.open(ROOT/area['path']) as image:
            assert image.size==(area['width'],area['height']),area['id']
        with Image.open(ROOT/area['walkable']) as mask:
            assert mask.size==(area['width'],area['height']),area['id']
            assert mask.getpixel(tuple(map(int,area['spawn'])))>=128,area['id']
        if area.get('foreground'):
            with Image.open(ROOT/area['foreground']) as front:
                assert front.size==(area['width'],area['height']),area['id']


def test_all_tamers_have_eight_real_walk_directions():
    catalog=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf8'))
    assert len(catalog['tamers'])==64
    expected={'up','up_right','right','down_right','down','down_left','left','up_left'}
    for tamer in catalog['tamers']:
        assert set(tamer['frames'])==expected,tamer['id']
        for direction,frames in tamer['frames'].items():
            assert len(frames)==4
            assert len(tamer['frame_seconds'][direction])==4
            assert all((ROOT/p).is_file() for p in frames)
