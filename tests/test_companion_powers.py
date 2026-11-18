"""The left panel's power switches (owner, 2026-11-18): Tears of the Kingdom's sages through the runtime's actions,
Breath of the Wild's Champion powers through one guarded byte write.

- The sages: companion_actions.c's summonSage / dismissSage run against the fake 1.4.3 layout of
  games/totk/tests/companion/test_companion.c (the same program as `make companiontest`), and its function table: the
  study's entries, each guarded by the SHA-256 of its first 64 bytes, the 24 item-action entries unchanged.
- Breath of the Wild: the write path is DuoPort ABI 4 (duo_port.h / duo_port.c, run for real by
  test_companion_gate.CompanionGate.test_duo_route); here the module's guards are checked as data: 1.6.0 only, the
  manager's cache slots, the item's type and name, the snapshot's item, a three-op batch with every expect.
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOTK = ROOT / 'games/totk'
MODULES = TOTK / 'duo/vendor/companions/native/modules'

# The study's sage entries (2026-11-17; hashes of the Thor's rewritten main, re-checked by its verifier)
SAGE_FN = {
    'F_SAGE_TYPE': (0xc1eb14, '7ec8363e69a35395fe4820b37a95c13ca5ab63687d1d80b3c62b9051d9c080f8'),
    'F_SAGE_PREP': (0x1fa1e20, '443ba90b6e6693ff2b3c882ec138c31af1f3a9378e24df4033fed54edac4013e'),
    'F_SAGE_SUMMON': (0xc6c700, 'ccde563f82891fa55119106e1614752ffb466193b1386f779065a6a09749729d'),
    'F_SAGE_DISMISS': (0x1fa1658, '6c4563fddf4e4b63f498da632bbbb492872acd1dd009de73d46d4b24bb6ee203'),
    'F_SAGE_SET': (0x1fa1c60, 'f7f906a903d4bacde04ac67aa02a72a36bc3d92631754d4cd97e582002bd3ae0'),
    'F_SAGE_GET': (0x1fa1d38, '9dcaa562cb90df32f72396570e5e89c44a2729f43d06509c92c5c3d65c1614fe'),
}
SAGE_QUERY = (0xc6d214, '37695330f01e2f3fdcd13a7ebaa1a1391a9787ebd89f3b5d4d4fc71e20f624bd')
# The 24 entries the item actions had before (their hashes match the original main: the study re-hashed all 24)
ITEM_OFFSETS = [0x20a1128, 0x20a9a28, 0x20ac5c4, 0x20ac080, 0x20af148, 0x20afab4, 0x20affa8, 0x20aff18, 0x63307c,
                0x711000, 0x89f9b0, 0xc1ee50, 0x3d01a0, 0x1cce94c, 0x1fa4e44, 0x1fa4fec, 0x20af2b4, 0x20af1b8,
                0x20b356c, 0x20a837c, 0x20a871c, 0x20a8ad0, 0x20a7680, 0x20a6af8]


class SagePowers(unittest.TestCase):
    def actions(self):
        return (TOTK / 'runtime/companion_actions.c').read_text()

    def test_function_table(self):
        src = self.actions()
        table = src[src.index('static const struct { uint32_t off; const char *sha64; } FN[] = {'):]
        table = table[:table.index('};')]
        entries = re.findall(r'\{0x([0-9a-f]+), "([0-9a-f]+)"\}', table)
        offsets = [int(o, 16) for o, _ in entries]
        self.assertEqual(len(offsets), len(set(offsets)), 'one entry per function')
        for _, h in entries:
            self.assertRegex(h, r'^[0-9a-f]{64}$')
        for o in offsets:
            self.assertLess(o, 0x2bb9c00)   # main's code
        for name, (off, sha) in SAGE_FN.items():
            self.assertIn(f'[{name}] = {{{off:#x}, "{sha}"}}', table, name)
        self.assertIn(f'{{{SAGE_QUERY[0]:#x}, "{SAGE_QUERY[1]}"}}', table)
        self.assertEqual(set(offsets) - {o for o, _ in SAGE_FN.values()} - {SAGE_QUERY[0]}, set(ITEM_OFFSETS))
        enum = src[src.index('enum {\n    F_EQUIP'):src.index('F_CALLED,')]
        self.assertLess(enum.index('F_REFILL'), enum.index('F_SAGE_TYPE'))   # named entries before the checked-only ones
        self.assertIn('SAGE_QUERY = 0xc6d214', src)
        # the test program lays out a stand-in prologue at every entry
        fake = (TOTK / 'tests/companion/test_companion.c').read_text()
        fake = fake[fake.index('static const uint32_t FN_OFF[] = {'):]
        fake = {int(x, 16) for x in re.findall(r'0x([0-9a-f]+)', fake[:fake.index('};')])}
        self.assertEqual(fake, set(offsets))

    def test_gates_and_sequence(self):
        src = self.actions()
        self.assertIn('static int verified_sages = 0;', src)   # not offered until checked on a device
        rules = src[src.index('static unsigned sage_rules('):src.index('unsigned companion_sage_actions(')]
        for reason in ('"unsupported"', 'st.reason', '"notNow"', '"notJoined"', '"sagesSuppressed"', '"sageUnavailableHere"',
                       '"notAvailableYet"'):
            self.assertIn(reason, rules)
        run = src[src.index('static void run_sage('):src.index('static void read_back_sage(')]
        summon = run[run.index('if (req.action == A_SUMMON_SAGE) {'):run.index('} else {')]
        self.assertLess(summon.index('F_SAGE_PREP'), summon.index('F_SAGE_SUMMON'))
        self.assertLess(summon.index('F_SAGE_SUMMON'), summon.index('F_SAGE_SET, mgr, (uint64_t)i, 1'))
        dismiss = run[run.index('} else {'):]
        self.assertLess(dismiss.index('F_SAGE_DISMISS'), dismiss.index('F_SAGE_SET, mgr, (uint64_t)i, 0'))
        self.assertIn('"stateChanged"', run)
        back = src[src.index('static void read_back_sage('):src.index('/* Run the queued request')]
        self.assertIn('"flagOnly"', back)        # the game changed only the flag: a distinct outcome
        self.assertIn('SAGE_LINK_HANDLE', back)  # the avatar link and the mask bit, beside IsSummon
        self.assertIn('SAGE_MASK', back)

    def test_actions_against_the_fake_game(self):
        cc = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
        if not cc:
            self.skipTest('no C compiler')
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'companiontest'
            base = [cc, '-O1', '-g', '-D_GNU_SOURCE', '-DTOTK_GAME_V143=1', '-I', str(TOTK / 'runtime'),
                    '-DCOMPANION_ACTIONS_TEST', '-o', str(exe), str(TOTK / 'tests/companion/test_companion.c'),
                    str(TOTK / 'runtime/companion_snapshot.c'), str(TOTK / 'runtime/companion_actions.c'), '-lm', '-lpthread']
            built = subprocess.run(base[:1] + ['-fsanitize=address,undefined'] + base[1:], capture_output=True, text=True,
                                   timeout=600)
            if built.returncode:
                built = subprocess.run(base, capture_output=True, text=True, timeout=600)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120,
                                 env={'ASAN_OPTIONS': 'detect_leaks=0', 'PATH': '/usr/bin:/bin'})
            self.assertEqual(run.returncode, 0, run.stderr[-4000:])
            self.assertIn('companion reader: all checks passed', run.stdout)
            self.assertIn('summonSage sages/0 Wind: done', run.stderr)
            self.assertIn('dismissSage sages/0 Wind: done flagOnly', run.stderr)


class ChampionPowers(unittest.TestCase):
    def test_port_abi_and_the_write_path(self):
        port = (TOTK / 'duo/duo_port.h').read_text()
        self.assertIn('#define DUO_PORT_ABI 4u', port)
        self.assertIn('#define DUO_PORT_WRITE_MAX_BYTES 8u', port)
        table = port[port.index('typedef struct DuoPort {'):port.index('} DuoPort;')]
        self.assertTrue(table.rstrip().endswith('int (*guarded_write)(const DuoPortWrite *ops, unsigned count);'))
        runtime = (TOTK / 'runtime/duo_port.c').read_text()
        botw = runtime[runtime.index('#ifdef GAME_BOTW'):runtime.index('#else')]
        totk = runtime[runtime.index('#else'):runtime.index('#endif', runtime.index('#else'))]
        self.assertIn('#define DUO_GUEST_WRITES 1', botw)
        self.assertIn('#define DUO_GUEST_WRITES 0', totk)   # Tears of the Kingdom stays as it was
        apply = runtime[runtime.index('static void apply_writes(void) {'):]
        apply = apply[:apply.index('\n}\n')]
        self.assertLess(apply.index('memcmp(now, batch.expect[i]'), apply.index('memcpy((void *)(uintptr_t)batch.address[i]'))
        self.assertIn('in_heap(batch.address[i], batch.size[i])', apply)
        self.assertLess(runtime.index('apply_writes();'), runtime.index('if (frame) frame();'))
        module = (TOTK / 'duo/port_module.cpp').read_text()
        self.assertIn('op.expect == nullptr', module)            # compare-then-write only
        self.assertIn('loaded->write_extensions = &g_tapped_writes;', module)
        cmake = (TOTK / 'duo/CMakeLists.txt').read_text()
        botw_cmake = cmake[cmake.index('if (DUO_TITLE STREQUAL "01007EF00011E000")'):cmake.index('elseif (DUO_TITLE')]
        self.assertIn('set(DUO_MODULE_WRITES 1)', botw_cmake)
        shim = (TOTK / 'duo/shim/system.cpp').read_text()
        self.assertIn('bool Memory::WriteBlock(VAddr, const void*, std::size_t) {', shim)   # still refuses everything
        self.assertIn('return false;', shim[shim.index('bool Memory::WriteBlock('):][:400])

    def test_guards_as_data(self):
        toggle = (MODULES / 'botw_champion_toggle.h').read_text()
        self.assertIn('static constexpr std::array<uint64_t,4> CacheSlot{0x44528,0x44518,0x44520,0x44530};', toggle)
        self.assertIn('static bool offered(const EdenDsmodHostApi& h){return matches_build(h,Build);}', toggle)   # 1.6.0
        for guard in ('vt!=h.main_base+off->pouch_vtable', 'type!=9', 'byte>1', 'name!=Names[i]&&name!=Upgraded[i]',
                      'n!=1||listed->address!=item'):
            self.assertIn(guard, toggle)
        self.assertIn('const EdenDsmodWriteOp ops[3]{{t.slot,8,0,&item,&item},{t.item+0x18,4,0,&key,&key},'
                      '{t.item+0x24,1,0,&seen,&want}};', toggle)
        self.assertIn('if(original[i]<0){', toggle)                       # the byte seen before the first change
        self.assertIn('if(event||ctx!=UiContext::Menu)return;', toggle)    # pause menu only: never mid-use in the world
        self.assertNotIn('ab[i].valid', toggle)                           # a stable read is not an idle power
        # not offered until the device checks pass (the TotK sages' verified_sages counterpart)
        self.assertIn('static constexpr bool Verified=false;', toggle)
        self.assertIn('if(!Verified||argument<0', toggle)
        self.assertIn('if(!Verified)return finish(', toggle)
        self.assertIn('const bool live=Verified&&', toggle)
        self.assertIn('const bool show=Verified&&', toggle)
        self.assertIn('"Switches not available yet"', toggle)
        self.assertIn('Off stays off in this save until turned on here', toggle)
        offsets = (MODULES / 'botw_inventory_offsets.h').read_text()
        self.assertIn('0x2CA6D50, // pouch_root', offsets)
        self.assertIn('0x2B87780, // pouch_vtable', offsets)
        names = re.findall(r'"(Obj_(?:DLC_)?HeroSoul_\w+)"', toggle)
        champions = (MODULES / 'botw_ready_panes.h').read_text()
        for n in names:
            self.assertIn(f'"{n}"', champions)                             # the names publish_champion_ownership uses
        # never a GameData flag: no Clear_Remains, IsGet_ or HeroSoulProhibition write
        for flag in ('Clear_Remains', 'IsGet_', 'HeroSoulProhibition"'):
            self.assertNotIn(flag, toggle.split('#include')[-1].split('namespace botw {')[1])
        bundle = (MODULES / '01007EF00011E000.cpp').read_text()
        self.assertIn('eden_dsmod_get_write_extensions(uint32_t v,uint64_t hash)', bundle)
        actions = (MODULES / '01007EF00011E000_actions.h').read_text()
        self.assertIn('if(!s.ready_panes.powers)return false;', actions)   # switches only on the Powers panel


if __name__ == '__main__':
    unittest.main()
