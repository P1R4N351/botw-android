"""The Tears of the Kingdom page's quest reader and the left panel's option (owner, 2026-11-18).

- games/totk/tests/companion/test_totk_quests.c runs the reader's C (totk_quests.c, TotK Native's BYML reader
  totk_byml.c, totk_gamedata.c's quest state) against a catalogue written here in the shape of the 1.4.3
  RSDB/Challenge table (no game file) and a fake GameDataMgr.
- The packages: both have the Left panel row (flag left_mode, Quest details by default), the quest pages are Breath of
  the Wild's widgets by index, the switches are bound to module values and actions only.
"""
import json
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOTK = ROOT / 'games/totk'
VENDOR = TOTK / 'duo/vendor/companions'
READER = VENDOR / 'native/modules/totk_reader'


def byml(root):
    """A little-endian BYML v7 document ("YB"): dictionaries, arrays, strings, ints, floats, bools."""
    keys, strings = set(), set()

    def scan(v):
        if isinstance(v, dict):
            for k, x in v.items():
                keys.add(k)
                scan(x)
        elif isinstance(v, list):
            for x in v:
                scan(x)
        elif isinstance(v, str):
            strings.add(v)
    scan(root)
    keys, strings = sorted(keys), sorted(strings)

    def table(items):
        head = struct.pack('<I', 0xC2 | len(items) << 8)
        offsets, blob = [], b''
        base = 4 + 4 * (len(items) + 1)
        for s in items:
            offsets.append(base + len(blob))
            blob += s.encode() + b'\0'
        offsets.append(base + len(blob))
        out = head + b''.join(struct.pack('<I', o) for o in offsets) + blob
        return out + b'\0' * (-len(out) % 4)
    out = bytearray(16)
    key_at = len(out)
    out += table(keys)
    str_at = len(out)
    out += table(strings)

    def scalar(v):
        if isinstance(v, bool):
            return 0xD0, int(v)
        if isinstance(v, int):
            return 0xD1, v & 0xFFFFFFFF
        if isinstance(v, float):
            return 0xD2, struct.unpack('<I', struct.pack('<f', v))[0]
        if isinstance(v, str):
            return 0xA0, strings.index(v)
        raise TypeError(v)

    def node(v):
        """Writes a container at the end of out; returns its offset."""
        items = list(v.items()) if isinstance(v, dict) else list(enumerate(v))
        children = {}
        for k, x in items:   # children first, so the node's values are known
            if isinstance(x, (dict, list)):
                children[k] = node(x)
        at = len(out)
        if isinstance(v, dict):
            out.extend(struct.pack('<I', 0xC1 | len(items) << 8))
            for k, x in sorted(items, key=lambda kv: kv[0]):
                t, val = (0xC1 if isinstance(x, dict) else 0xC0, children[k]) if k in children else scalar(x)
                out.extend(struct.pack('<I', keys.index(k) | t << 24) + struct.pack('<I', val))
        else:
            out.extend(struct.pack('<I', 0xC0 | len(items) << 8))
            vals = []
            for k, x in items:
                t, val = (0xC1 if isinstance(x, dict) else 0xC0, children[k]) if k in children else scalar(x)
                out.append(t)
                vals.append(val)
            out.extend(b'\0' * (-len(out) % 4))
            for val in vals:
                out.extend(struct.pack('<I', val))
        return at
    root_at = node(root)
    out[0:16] = b'YB' + struct.pack('<HIII', 7, key_at, str_at, root_at)
    return bytes(out)


def row(name, steps, **extra):
    return {'__RowId': f'Work/Challenge/{name}.game__challenge__Challenge.gyml', 'Steps': steps, **extra}


def step(name, *dests, **extra):
    return {'Name': name, 'DestinationPoint': list(dests), 'IsNotChangeAdventureLog': False, **extra}


CATALOGUE = [
    row('MainA', [step('Ready'),
                  step('Go', {'game__challenge__DestinationPos': {'Pos': {'X': 100.0, 'Y': 5.0, 'Z': 0.0}}}),
                  step('Fight', {'Actor': 'Npc_Test', 'InstanceName': 'x',
                                 'AlternativePos': {'X': 0.0, 'Y': 0.0, 'Z': 30.0}, 'BlackOutFlag': 'Flag_Black'},
                       {'game__challenge__DestinationPos': {'Pos': {'X': 0.0, 'Y': 0.0, 'Z': 50.0}, 'BlackOutFlag': ''}})],
        Category='Main', SortIndex=20),
    row('MainB', [step('Ready'), step('S1', IsNotChangeAdventureLog=True), step('S2')], Category='Main', SortIndex=10),
    row('MainC', [step('Ready'), step('S1')], Category='Main'),
    row('AdvA', [step('Ready'), step('A1')], Category='ImportantMini', SortIndex=5),
    row('SideA', [step('Ready'), step('B1')], SortIndex=1),
    row('MiniGame', [step('Ready'), step('M1')], SortIndex=0, IsListAdventureLog=False),
    row('Crystal', [step('Ready'), step('C1')], Category='Sub', SortIndex=3),
    {'__RowId': 'Work/Other/Nope.gyml', 'Steps': [step('Ready')]},
]


class QuestReader(unittest.TestCase):
    def test_reader_against_a_made_up_catalogue(self):
        cc = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
        if not cc:
            self.skipTest('no C compiler')
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            (temp / 'challenge.byml').write_bytes(byml(CATALOGUE))
            exe = temp / 'test_totk_quests'
            built = subprocess.run([cc, '-std=c11', '-D_GNU_SOURCE', '-Wall', '-Wextra', '-Werror', '-I', str(READER),
                                    str(TOTK / 'tests/companion/test_totk_quests.c'), str(READER / 'totk_quests.c'),
                                    str(READER / 'totk_byml.c'), str(READER / 'totk_gamedata.c'),
                                    str(READER / 'companion_snapshot.c'), str(READER / 'totk_reader_ro.c'),
                                    '-lm', '-lpthread', '-o', str(exe)], capture_output=True, text=True, timeout=300)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            run = subprocess.run([str(exe), str(temp / 'challenge.byml')], capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('pass: quest catalogue, pages, distance and state', run.stdout)

    def test_byml_reader_is_tot_native_s(self):
        # TotK Native's cg_byml, renamed: the same type cases and bounds, nothing new
        ours = (READER / 'totk_byml.c').read_text()
        theirs = (TOTK / 'android/setup/companion/cg_formats.c').read_text()
        self.assertIn('cg_formats.c', ours)
        for case in ('case 0xa0:', 'case 0xc0: case 0xc1:', 'case 0xd0:', 'case 0xd1:', 'case 0xd2:', 'case 0xd3:',
                     'case 0xd4: case 0xd5: case 0xd6:', 'case 0xff:', 'if (depth > 64) return -1;',
                     'uint64_t start = ((uint64_t)v + 4 + cnt + 3) & ~3ull;'):
            self.assertIn(case, ours)
            self.assertIn(case, theirs)
        self.assertNotIn('GPL', ours)
        self.assertNotIn('GPL', (READER / 'totk_quests.c').read_text())

    def test_no_quest_data_is_shipped(self):
        for name in ('totk_quests.c', 'totk_quests.h', 'totk_gamedata.c'):
            text = (READER / name).read_text()
            for quest in ('DefeatGanondorf', 'AisyaRescue', 'ExcavateFossil1', 'FindWhereabouts'):
                self.assertNotIn(quest, text, name)
        # the tracked quest's flag is the one constant: SelectChallengeHash's own hash
        self.assertIn('#define TOTK_SELECT_CHALLENGE_HASH 0x2029d3d8u', (READER / 'totk_gamedata.h').read_text())
        self.assertIn('[T_UINT] = {0x788, 0x28, 0x1c}', (READER / 'totk_gamedata.c').read_text())


class LeftPanel(unittest.TestCase):
    PACKAGES = {'botw': 'BreathOfTheWild', 'totk': 'TearsOfTheKingdom'}

    def manifest(self, game):
        return json.loads((VENDOR / 'packages' / self.PACKAGES[game] / 'dualscreen/manifest.json').read_text())

    def test_both_packages_have_the_option_quest_details_first(self):
        for game, powers in (('botw', 'Champion powers'), ('totk', 'Sage powers')):
            with self.subTest(game=game):
                m = self.manifest(game)
                rows = {r['flag']: r for r in m['settings']}
                self.assertEqual(rows['left_mode'], {'flag': 'left_mode', 'label': 'Left panel', 'type': 'toggle',
                                                     'choices': ['Quest details', powers], 'default': 0})
                self.assertNotIn('left_mode', m.get('flags', {}))
                ready = next(p for p in m['pages'] if p['id'] == 'ready')['widgets']
                pager = [w for w in ready if w.get('id') in ('ready_left_pager', 'pane21_champion_input')]
                self.assertEqual(len(pager), 2)
                for w in pager:   # holding the left pager opens the settings page
                    self.assertEqual(w['on_hold'], 'open_settings')
                    self.assertEqual(w['on_swipe_up'], 'ready_left_next')

    def test_botw_keeps_every_widget_index(self):
        # the TotK generator addresses BotW's Ready widgets by index: the local change appends, moves nothing
        ready = next(p for p in self.manifest('botw')['pages'] if p['id'] == 'ready')['widgets']
        self.assertEqual(len(ready), 1034)
        self.assertEqual(ready[160]['text_bind'], 'botw.ready.quest.name')
        self.assertEqual(ready[163]['on_tap'], 'quest')
        self.assertEqual(ready[166]['text'], 'Champions')
        self.assertEqual(ready[863]['id'], 'champion26_4_3_state')
        self.assertTrue(all(str(w.get('id', '')).startswith('champion_power') or 'on_tap' in w or 'bind_text' in w
                            or w.get('text') in ('On', 'Off', 'Turn all on') for w in ready[990:]))

    def test_totk_quest_pages_are_botw_s(self):
        m = self.manifest('totk')
        ready = next(p for p in m['pages'] if p['id'] == 'ready')['widgets']
        by_bind = {}
        for w in ready:
            for k in ('bind_text', 'text_bind'):
                if k in w:
                    by_bind.setdefault(w[k], []).append(w)
        self.assertEqual(by_bind['totk.ready.left.page'][0]['text_map'], {'0': 'Main quest', '1': 'Side quest'})
        name = by_bind['totk.ready.quest.name'][0]
        self.assertEqual(name['rect'], [111, 388, 168, 267])
        self.assertNotIn('text_map', name)   # the module publishes the player's own text
        self.assertEqual(by_bind['totk.ready.quest.distance'][0]['need_bind'], 'totk.ready.left.quest')
        self.assertTrue(any(w.get('text') == 'No active quest' for w in ready))
        pager = next(w for w in ready if w.get('id') == 'ready_left_pager')
        self.assertNotIn('on_tap', pager)    # no Quest page to open yet
        self.assertEqual(m['actions']['ready_left_next'], {'kind': 'module', 'action': 'totk.left', 'argument': 1})
        self.assertEqual(m['actions']['ready_left_previous'], {'kind': 'module', 'action': 'totk.left', 'argument': -1})
        dots = [w for w in ready if w.get('hide_bind') == 'totk.ready.left.page']
        self.assertEqual(len(dots), 3)
        self.assertTrue(all(w['need_bind'] == 'totk.ready.left.dots' for w in dots))
        derived = {d['name']: d.get('expr', '') for d in m['derived']}
        self.assertIn('totk.ready.left.dots == 1', derived['pp_ready_underlay_194'])
        self.assertIn('totk.ready.left.champions == 1', derived['sage5_0_row'])

    def test_switches_are_module_values_and_actions(self):
        for game, action, count in (('botw', 'botw.champion.toggle', 4), ('totk', 'totk.sage', 5)):
            with self.subTest(game=game):
                m = self.manifest(game)
                acts = {k: a for k, a in m['actions'].items() if a.get('action') == action}
                self.assertEqual(sorted(a['argument'] for a in acts.values()), list(range(2 * count)))
                derived = {d['name']: d.get('expr', '') for d in m['derived']}
                gates = [e for e in derived.values() if '.switch.' in e]
                self.assertTrue(gates)
                for e in gates:   # only while the Powers panel is chosen
                    self.assertIn(f'{game}.ready.left.powers == 1', e)
                    self.assertIn('pp_ready_base == 1', e)
                ready = next(p for p in m['pages'] if p['id'] == 'ready')['widgets']
                taps = [w for w in ready if str(w.get('on_tap', '')) in acts]
                self.assertTrue(taps)
                for w in taps:    # a tap is only there while the switch may be used
                    self.assertRegex(derived[w['need_bind']], r'switch\.(on|off)_tap == 1')
                notes = [w for w in ready if w.get('bind_text') == f'{game}.ready.champions.note']
                self.assertEqual(len(notes), 1)
        botw = self.manifest('botw')
        self.assertEqual(botw['actions']['champion_power_all_on']['action'], 'botw.champion.all_on')

    def test_the_modules_read_the_flag(self):
        modules = VENDOR / 'native/modules'
        self.assertIn('h.get_i64(h.userdata,"@flag:left_mode",0)==1', (modules / 'botw_champion_toggle.h').read_text())
        totk = (modules / '0100F2C0115B6000.cpp').read_text()
        self.assertIn('Get("@flag:left_mode", 0) == 1', totk)
        self.assertIn('n->item_actions(n->userdata, TOTK_NATIVE_SAGES, sage, out)', totk)
        self.assertIn('native->request(native->userdata, id, "sages"', totk)
        self.assertIn('#define TOTK_NATIVE_SAGES 9', (modules / 'totk_native_actions.h').read_text())
        self.assertIn('COMPANION_SAGES = 9', (TOTK / 'runtime/companion.h').read_text())


if __name__ == '__main__':
    unittest.main()
