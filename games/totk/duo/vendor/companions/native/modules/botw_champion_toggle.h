// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: Copyright 2026 P1R4N351
#pragma once
// Local change (TotK Native, games/totk/duo/vendor/README.md "Local changes"; greppable: champion_toggle). Not
// igawa6's: written for BotW Native's Eden Duo port, to be offered upstream only with the owner's consent.
//
// The left panel's setting (owner 2026-11-18, one option for both games, the package's settings row "Left panel",
// flag left_mode): 0 Quest details (upstream's Main quest / Side quest / Champions pager, the Champions read-only) or
// 1 Champion powers (the Champions only, each with an On/Off switch, plus "Turn all on").
//
// The switch (static analysis of 1.6.0's main, study and verifier of 2026-11-17): a Champion power is usable while the
// mEquipped byte (+0x24) of its key item (Obj_HeroSoul_<X>, or Obj_DLC_HeroSoul_<X> after the Champions' Ballad) is
// set. PauseMenuDataMgr::isHeroSoulEnabled (main+0x10C6EA0) returns that byte through the manager's cached item
// pointers (PMDM+0x44528 Zora, +0x44518 Rito, +0x44520 Goron, +0x44530 Gerudo); the four Player "power ready" getters and
// the HUD ask it. Saving stores the byte as PorchItem_EquipFlag and loading restores it, so a power turned off stays off
// in that save, through saves and reloads, until it is turned on again here (the game has no menu for it). No GameData
// flag is touched (Clear_Remains*, IsGet_* are story flags; HeroSoulProhibition is the game's own all-four switch).
//
// One change = one write batch (Eden Duo's write extension: every expect compared, all or none, guest stopped; in
// BotW Native the port's guarded write, at the game's next frame): the cache slot still holds this item (8 bytes), the
// item is still a key item (type 9, 4 bytes), the byte is still what was seen (1 byte, the only store). Before it,
// the item is checked live: 1.6.0 only (build 8E9978D5), the manager's vtable, the slot's item named Obj_(DLC_)
// HeroSoul_<X>, its byte 0 or 1, and the very item the pouch snapshot lists, the only key item of that power. Applied
// only in the world or the pause menu, outside events, and in the world only while the power's own state reads stable
// (the getters are asked when a power is about to fire; a change takes effect at the next use). Not offered on 1.9.0
// (its slots were not researched). The byte seen before the first change of the session is kept and published.
//
// To verify on the device before release (read-only first): *(PMDM+0x44520) equals the Goron item the pouch snapshot
// lists and its +0x24 reads 1 with the power on (botw_ready_panes.h notes a HUD observation that disagrees), then a
// power turned off: the HUD icon goes, the power does not fire, save + reload + restart keep it off, Turn all on
// restores it.
#include "botw_champions.h"
#include "botw_context.h"
#include "botw_inventory_offsets.h"
#include "botw_key.h"
#include "botw_pouch.h"
#include "core/mods/dsmod_module_extensions.h"
#include <array>
#include <atomic>
#include <chrono>
#include <string>
namespace botw {
inline bool left_powers_chosen(const EdenDsmodHostApi& h) {
  return h.get_i64 && h.get_i64(h.userdata,"@flag:left_mode",0)==1;
}
struct ChampionToggle {
  // canonical order Zora, Rito, Goron, Gerudo (publish_champion_ownership's)
  static constexpr std::array<uint64_t,4> CacheSlot{0x44528,0x44518,0x44520,0x44530};
  static constexpr std::array<const char*,4> Names{"Obj_HeroSoul_Zora","Obj_HeroSoul_Rito","Obj_HeroSoul_Goron","Obj_HeroSoul_Gerudo"};
  static constexpr std::array<const char*,4> Upgraded{"Obj_DLC_HeroSoul_Zora","Obj_DLC_HeroSoul_Rito","Obj_DLC_HeroSoul_Goron","Obj_DLC_HeroSoul_Gerudo"};
  static constexpr int Tries=5;
  EdenDsmodHostWriteApi writer{};bool has_writer{};
  // the request from on_action: -1 none; slot*2+on; 8 = turn all on
  std::atomic<int> wanted{-1};
  int tries{};
  std::array<int,4> original{-1,-1,-1,-1};
  std::string line;std::chrono::steady_clock::time_point line_at{};
  void configure(const EdenDsmodHostWriteApi* w) {
    has_writer=w && w->version==EDEN_DSMOD_WRITE_EXT_VERSION && w->abi_hash==EDEN_DSMOD_WRITE_EXT_HASH &&
               w->struct_size>=sizeof(EdenDsmodHostWriteApi) && w->write_batch;
    if(has_writer)writer=*w;
  }
  static bool offered(const EdenDsmodHostApi& h){return matches_build(h,Build);}   // 1.6.0 only
  bool request(int argument) {
    if(argument<0||argument>8||!has_writer)return false;
    int none=-1;return wanted.compare_exchange_strong(none,argument);   // one at a time
  }
  struct Target {bool ok{};uint64_t slot{},item{};uint8_t byte{};};
  // The power's key item, checked live against the manager's cache and the pouch snapshot.
  static Target target(const EdenDsmodHostApi& h,const Snapshot& pouch,unsigned i) {
    Target t{};
    const auto* off=inventory_offsets(h);
    if(i>=4||!offered(h)||!off||!pouch.valid||h.main_size<off->pouch_root+8)return t;
    uint64_t pmdm{},vt{},item{},name_ptr{};int32_t type{};uint8_t byte{};
    if(!read(h,h.main_base+off->pouch_root,pmdm)||!pmdm||pmdm%8||!read(h,pmdm,vt)||vt!=h.main_base+off->pouch_vtable)return t;
    const uint64_t slot=pmdm+CacheSlot[i];
    if(!read(h,slot,item)||!item||item%8||!read(h,item+0x18,type)||type!=9||!read(h,item+0x24,byte)||byte>1||
       !read(h,item+0x30,name_ptr))return t;
    std::string name;
    for(unsigned k=0;k<40;++k){char c{};if(!read(h,name_ptr+k,c))return t;if(!c)break;name+=c;}
    if(name!=Names[i]&&name!=Upgraded[i])return t;
    const Item* listed{};unsigned n{};
    for(const auto& it:pouch.items)if(it.type==9&&(it.actor==Names[i]||it.actor==Upgraded[i])){listed=&it;++n;}
    if(n!=1||listed->address!=item)return t;   // a stale cache pointer, or two items of one power: not this one
    t={true,slot,item,byte};return t;
  }
  // Sample thread, after the pouch snapshot: carries out the wanted change when the game allows it.
  void step(const EdenDsmodHostApi& h,const Snapshot& pouch,UiContext ctx,bool event,const ChampionAbilities& ab) {
    const int w=wanted.load();
    if(w<0)return;
    const auto finish=[&](std::string text){line=std::move(text);line_at=std::chrono::steady_clock::now();tries=0;wanted=-1;};
    if(!has_writer||!offered(h))return finish("Not possible in this host");
    if(event||(ctx!=UiContext::World&&ctx!=UiContext::Menu)){if(++tries>Tries*10)finish("Not possible right now");return;}
    bool any=false,failed=false;
    for(unsigned i=0;i<4;++i) {
      const bool all=w==8;
      if(!all&&unsigned(w/2)!=i)continue;
      const uint8_t want=all?1:uint8_t(w%2);
      const Target t=target(h,pouch,i);
      if(!t.ok){if(!all)failed=true;continue;}   // Turn all on: powers not obtained are left alone
      if(t.byte==want)continue;
      if(ctx==UiContext::World&&!ab[i].valid){if(++tries>Tries*10)return finish("Not possible right now");return;}
      if(original[i]<0){
        original[i]=t.byte;
        if(h.log){const std::string l="BOTW champion power "+std::to_string(i)+": first change, byte was "+std::to_string(t.byte);h.log(h.userdata,1u,l.c_str());}
      }
      const uint64_t item=t.item;const int32_t key=9;const uint8_t seen=t.byte;
      const EdenDsmodWriteOp ops[3]{{t.slot,8,0,&item,&item},{t.item+0x18,4,0,&key,&key},{t.item+0x24,1,0,&seen,&want}};
      if(writer.write_batch(writer.userdata,ops,3)){any=true;continue;}
      if(++tries>=Tries)return finish("Could not change it now");
      return;   // retried on a later sample
    }
    if(failed)return finish("Could not change it now");
    finish(w==8?(any?"All powers on":"All powers were on"):
           w%2?"On":"Off: stays off in this save until turned on here");
  }
  // Champion powers (left_mode 1): each owned power's switch (by the pouch, canonical slots), the Turn all on button
  // and the line under the panel. Also blanks the row text of a power that is off (the switch says it).
  void publish(const EdenDsmodHostApi& h,const Snapshot& pouch,bool powers,UiContext ctx,bool event) {
    const bool live=powers&&has_writer&&offered(h)&&wanted.load()<0&&!event&&(ctx==UiContext::World||ctx==UiContext::Menu);
    bool any_off=false;
    for(unsigned i=0;i<4;++i) {
      const Item* owned{};unsigned n{};
      if(pouch.valid)for(const auto& it:pouch.items)if(it.type==9&&(it.actor==Names[i]||it.actor==Upgraded[i])){owned=&it;++n;}
      const bool show=powers&&n==1;
      const bool on=show&&owned->equipped;
      any_off|=show&&!on;
      Key k("botw.ready.champion_slot.",i);
      h.publish_i64(h.userdata,k(".switch.on_tap"),show&&live&&on);
      h.publish_i64(h.userdata,k(".switch.off_tap"),show&&live&&!on);
      h.publish_i64(h.userdata,k(".switch.on_fixed"),show&&!live&&on);
      h.publish_i64(h.userdata,k(".switch.off_fixed"),show&&!live&&!on);
      Key c("botw.ready.champion.",i);
      h.publish_i64(h.userdata,c(".original"),original[i]);
      if(show&&!on){h.publish_i64(h.userdata,k(".display_kind"),3);h.publish_text(h.userdata,k(".display"),"");}
    }
    h.publish_i64(h.userdata,"botw.ready.champions.all_on.on",powers&&live&&any_off);
    std::string note;
    if(powers) {
      const bool recent=!line.empty()&&std::chrono::steady_clock::now()-line_at<std::chrono::seconds{5};
      if(wanted.load()>=0)note="Changing\xE2\x80\xA6";
      else if(recent)note=line;
      else if(!offered(h))note="Switches need version 1.6.0";
      else if(!has_writer)note="Switches are not available in this host";
      else if(!pouch.valid)note="";
      else if(any_off)note="Off stays off in this save until turned on here";
      else note="Tap a power to turn it off";
    }
    h.publish_i64(h.userdata,"botw.ready.champions.note.on",!note.empty());
    h.publish_text(h.userdata,"botw.ready.champions.note",note.c_str());
  }
};
} // namespace botw
