/* The Tears of the Kingdom page's quest reader (duo/vendor/companions/native/modules/totk_reader: totk_quests.c, its
   BYML reader totk_byml.c, the quest state of totk_gamedata.c) against a made-up catalogue and a fake GameDataMgr: no
   game files. tests/test_companion_quests.py writes the catalogue (a little-endian BYML v7 shaped like
   RSDB/Challenge.Product.<v>.rstbl) and runs this.

       test_totk_quests <catalogue.byml> */
#include "companion.h"
#include "totk_gamedata.h"
#include "totk_quests.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;
static void check(int ok, const char *what) { if (!ok) { fprintf(stderr, "FAIL: %s\n", what); failures++; } }
static int rd(uint64_t a, void *out, size_t n) { if (a < 0x1000) return 0; memcpy(out, (const void *)(uintptr_t)a, n); return 1; }
static int find(const TotkQuestCatalog *c, const char *name) {
    for (uint32_t q = 0; q < c->nquests; q++) if (!strcmp(c->quests[q].name, name)) return (int)q;
    return -1;
}
static uint32_t H(const char *s) { return companion_hash(s); }

/* ---------- a fake GameDataMgr (totk_gamedata.c's layout) ---------- */
enum { GDM_SLOT = 0x3ad66b0 };
static uint8_t *gdm;
/* one table at gdm+base: count, entries, index, capacity; values of `size` bytes at +value of each entry */
static void table(unsigned base, unsigned stride, unsigned value, int n, const uint32_t *hash, const void *values, size_t size) {
    uint32_t cap = 31;
    uint8_t *entries = calloc((size_t)n, stride), *index = calloc(cap, 8);
    for (int i = 0; i < n; i++) {
        memcpy(entries + (size_t)i * stride + value, (const uint8_t *)values + (size_t)i * size, size);
        uint32_t slot = hash[i] % cap;
        for (;;) { uint32_t h; memcpy(&h, index + 8 * slot, 4); if (!h) break; slot = (slot + 1) % cap; }
        uint32_t cell[2] = {hash[i], (uint32_t)i};
        memcpy(index + 8 * slot, cell, 8);
    }
    int32_t count = n; uint64_t e = (uintptr_t)entries, x = (uintptr_t)index;
    memcpy(gdm + base + 8, &count, 4); memcpy(gdm + base + 0x10, &e, 8); memcpy(gdm + base + 0x18, &x, 8);
    memcpy(gdm + base + 0x24, &cap, 4);
}
static int blackout_value = -1;
static int blackout(void *ctx, uint32_t hash) { (void)ctx; return hash == H("Flag_Black") ? blackout_value : -1; }

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 2;
    static uint8_t doc[1 << 16];
    size_t n = fread(doc, 1, sizeof doc, f);
    fclose(f);
    TotkQuestCatalog c;
    check(totk_quest_catalog((const uint8_t *)"XX", 2, &c) == -1 && !c.nquests, "not a BYML: refused");
    static const uint8_t big_endian[16] = {'B', 'Y', 0, 7};
    check(totk_quest_catalog(big_endian, sizeof big_endian, &c) == -1, "a big-endian BYML (GameDataList's) is not a catalogue");
    check(totk_quest_catalog(doc, n, &c) == 0, "the catalogue parses");
    check(c.nquests == 7, "seven quests (a row without a proper __RowId is skipped)");
    const int main_a = find(&c, "MainA"), main_b = find(&c, "MainB"), main_c = find(&c, "MainC"), adv = find(&c, "AdvA"),
              side = find(&c, "SideA"), mini = find(&c, "MiniGame"), crystal = find(&c, "Crystal");
    check(main_a >= 0 && main_b >= 0 && main_c >= 0 && adv >= 0 && side >= 0 && mini >= 0 && crystal >= 0, "every row by name");
    if (failures) return 1;
    const TotkQuest *qa = &c.quests[main_a];
    check(qa->category == TOTK_QUEST_MAIN && c.quests[adv].category == TOTK_QUEST_ADVENTURE &&
          c.quests[side].category == TOTK_QUEST_SIDE && c.quests[crystal].category == TOTK_QUEST_SHRINE, "categories");
    check(qa->sort == 20 && c.quests[main_c].sort == TOTK_QUEST_NO_SORT, "SortIndex, and none sorts last");
    check(qa->listed && !c.quests[mini].listed, "IsListAdventureLog, true by default");
    check(qa->name_hash == H("MainA") && qa->step_flag == H("Step_MainA"), "the hashes are computed, not shipped");
    check(qa->nsteps == 3 && !strcmp(c.steps[qa->first_step].name, "Ready") && c.steps[qa->first_step + 2].hash == H("Fight"),
          "steps in order");
    check(c.steps[qa->first_step + 1].ndest == 1 && c.steps[qa->first_step + 2].ndest == 2, "destinations per step");
    const TotkQuestDest *d = &c.dests[c.steps[qa->first_step + 2].first_dest];
    check(d[0].z == 30 && d[0].blackout == H("Flag_Black") && d[1].z == 50 && !d[1].blackout,
          "AlternativePos with its BlackOutFlag, and a nested Pos");
    check(c.steps[c.quests[main_b].first_step + 1].not_change_log, "IsNotChangeAdventureLog");

    /* a quest's step from its Step_ value */
    check(totk_quest_step(&c, (uint32_t)main_a, H("Fight")) == 2, "step by name hash");
    check(totk_quest_step(&c, (uint32_t)main_a, H("NotReady")) == TOTK_QUEST_NOT_READY, "NotReady");
    check(totk_quest_step(&c, (uint32_t)main_a, H("Complete")) == 3, "Complete is after the last step");
    check(totk_quest_step(&c, (uint32_t)main_a, 0) == TOTK_QUEST_UNKNOWN &&
          totk_quest_step(&c, (uint32_t)main_a, H("S1")) == TOTK_QUEST_UNKNOWN, "unread or another quest's step");
    check(!totk_quest_open(&c, (uint32_t)main_a, 0) && totk_quest_open(&c, (uint32_t)main_a, 1) &&
          !totk_quest_open(&c, (uint32_t)main_a, 3) && !totk_quest_open(&c, (uint32_t)mini, 1), "open: past Ready, not Complete, listed");

    /* the two pages */
    int step[7], out[2], tracked[2];
    uint64_t changed[7] = {0};
    for (int q = 0; q < 7; q++) step[q] = 1;
    step[adv] = 0;   /* offered, not taken */
    totk_quest_pick(&c, step, 0, NULL, out, tracked);
    check(out[0] == main_b && !tracked[0], "nothing tracked: the main quest with the lowest SortIndex");
    check(out[1] == side, "no open Side Adventure: a Side Quest");
    totk_quest_pick(&c, step, H("MainA"), NULL, out, tracked);
    check(out[0] == main_a && tracked[0] && out[1] == side && !tracked[1], "the tracked main quest");
    step[main_a] = 3;
    totk_quest_pick(&c, step, H("MainA"), NULL, out, tracked);
    check(out[0] == main_b && !tracked[0], "a tracked quest that is Complete is not shown (a save can hold one)");
    step[main_a] = 1;
    changed[main_c] = 5;
    totk_quest_pick(&c, step, 0, changed, out, tracked);
    check(out[0] == main_c, "the main quest that changed last in this session");
    changed[main_c] = 0;
    step[adv] = 1;
    totk_quest_pick(&c, step, 0, changed, out, tracked);
    check(out[1] == adv, "an open Side Adventure before a Side Quest");
    totk_quest_pick(&c, step, H("SideA"), changed, out, tracked);
    check(out[1] == side && tracked[1] && out[0] == main_b && !tracked[0], "the tracked side quest");
    totk_quest_pick(&c, step, H("Crystal"), changed, out, tracked);
    check(out[1] == crystal && tracked[1], "a tracked crystal quest is the side page's");
    totk_quest_pick(&c, step, H("MiniGame"), changed, out, tracked);
    check(out[1] == adv && !tracked[1], "an unlisted quest is never shown");
    for (int q = 0; q < 7; q++) step[q] = TOTK_QUEST_NOT_READY;
    totk_quest_pick(&c, step, 0, NULL, out, tracked);
    check(out[0] == -1 && out[1] == -1, "no open quest: none (No active quest)");

    /* the distance: the nearest destination of the current step, on the map plane, unless blacked out */
    check(fabs(totk_quest_distance(&c, (uint32_t)main_a, 1, 0, 0, NULL, NULL) - 100) < 1e-6, "one destination");
    check(fabs(totk_quest_distance(&c, (uint32_t)main_a, 2, 0, 0, NULL, NULL) - 30) < 1e-6, "the nearest");
    blackout_value = 1;
    check(fabs(totk_quest_distance(&c, (uint32_t)main_a, 2, 0, 0, blackout, NULL) - 50) < 1e-6, "a blacked-out one is skipped");
    blackout_value = 0;
    check(fabs(totk_quest_distance(&c, (uint32_t)main_a, 2, 0, 40, blackout, NULL) - 10) < 1e-6, "measured on x and z");
    check(totk_quest_distance(&c, (uint32_t)main_a, 0, 0, 0, NULL, NULL) < 0, "a step without a destination");

    /* the state from GameData: Step_<Name> (Enum), SelectChallengeHash (UInt), Bool flags by hash */
    uint8_t *main_ = calloc(GDM_SLOT + 8, 1);
    gdm = calloc(0x800, 1);
    uint64_t g = (uintptr_t)gdm;
    memcpy(main_ + GDM_SLOT, &g, 8);
    const uint32_t enum_hash[2] = {H("Step_MainA"), H("Step_MainB")}, enum_value[2] = {H("Fight"), H("Complete")};
    table(0x248, 0x38, 0x1c, 2, enum_hash, enum_value, 4);
    const uint32_t uint_hash[1] = {TOTK_SELECT_CHALLENGE_HASH}, uint_value[1] = {H("MainB")};
    table(0x788, 0x28, 0x1c, 1, uint_hash, uint_value, 4);
    const uint32_t bool_hash[1] = {H("Flag_Black")}; const uint8_t bool_value[1] = {1};
    table(0x008, 0x18, 0x16, 1, bool_hash, bool_value, 1);
    check(TOTK_SELECT_CHALLENGE_HASH == H("SelectChallengeHash"), "SelectChallengeHash is the flag's own hash");
    uint32_t flags[3] = {H("Step_MainA"), H("Step_MainB"), H("Step_Nothing")}, states[3], selected = 0;
    check(totk_quest_state((uintptr_t)main_, rd, flags, 3, states, &selected) == 1, "state read");
    check(states[0] == H("Fight") && states[1] == H("Complete") && states[2] == 0 && selected == H("MainB"),
          "each quest's step, the tracked quest; an unknown flag reads 0");
    uint32_t bools[2] = {H("Flag_Black"), H("Flag_Exp")};
    signed char set[2];
    check(totk_gamedata_bools((uintptr_t)main_, rd, bools, 2, set) == 1 && set[0] == 1 && set[1] == -1,
          "a Bool by hash; a BoolExp (no Bool) is unknown");
    memset(main_ + GDM_SLOT, 0, 8);
    check(totk_quest_state((uintptr_t)main_, rd, flags, 3, states, &selected) == 0 && !states[0] && !selected,
          "no manager: nothing");

    totk_quest_catalog_free(&c);
    if (failures) { fprintf(stderr, "%d failure(s)\n", failures); return 1; }
    printf("pass: quest catalogue, pages, distance and state\n");
    return 0;
}
