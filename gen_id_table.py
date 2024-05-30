# `mccmdhl2` - Minecraft Bedrock command parser and autocompleter.
# Copyright (C) 2023  CBerJun<cberjun@163.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Generates ID Table for autocompleter,
using different sources of data.

This is a command line tool, use -h to see usages.
"""

import os
import re
import sys
import json
import glob
import codecs
import argparse
from mccmdhl2 import IdTable
from typing import Dict, Callable
from functools import partial

JSON_TOKENIZE = re.compile(
    r"""
    ( # String Literal
        \"(?:\\.|[^\\\"])*?\"
    )
    |
    ( # Comment
        \/\*.*?\*\/
        |
        \/\/[^\r\n]*?(?:[\r\n])
    )
    """, flags=re.DOTALL | re.VERBOSE
)
MISSING = object()  # Sentinel

def action_input(input_type: str, vtype: str = "file"):
    class _Action(argparse.Action):
        def __call__(self, parser, namespace, value: str, option: str):
            if vtype in ("file", "dir"):
                if not os.path.exists(value):
                    argparser.error("%s: path does not exist: %s"
                                    % (option, value))
                if (vtype == "file") ^ os.path.isfile(value):
                    argparser.error("%s: need to be a %s" % (option, vtype))
            else:
                assert vtype == "plain"
            if not hasattr(namespace, "input_list"):
                namespace.input_list = []
            namespace.input_list.append((input_type, value))
    return _Action

argparser = argparse.ArgumentParser(
    prog="gen_id_table",
    description="Generate ID Table for autocompleter."
)
argparser.add_argument(
    "-l", "--lang", metavar="FILE",
    help="input: a Minecraft .lang file",
    action=action_input("lang")
)
argparser.add_argument(
    "-m", "--merge", metavar="FILE",
    help="input: an existing ID table of JSON format",
    action=action_input("id_table")
)
argparser.add_argument(
    "-j", "--json", metavar="JSON",
    help="input: an existing ID table shown by a JSON string",
    action=action_input("json", vtype="plain")
)
argparser.add_argument(
    "-e", "--bp-entity", metavar="DIR",
    help="input: a directory of server entity definitions",
    action=action_input("bp_entity", vtype="dir")
)
argparser.add_argument(
    "-B", "--block-state", metavar="FILE",
    help="input: the block state table by @Missing245 "
         "(https://commandsimulator.great-site.net/?i=1)",
    action=action_input("block_state")
)
argparser.add_argument(
    "-f", "--fog", metavar="DIR",
    help="input: a directory of client fog difinitions",
    action=action_input("fog", vtype="dir")
)
argparser.add_argument(
    "-i", "--biome", metavar="FILE",
    help="input: biomes_client.json (resource pack biome definition)",
    action=action_input("biome")
)
argparser.add_argument(
    "-b", "--rp-block", metavar="FILE",
    help="input: blocks.json (resource pack block definition)",
    action=action_input("rp_block")
)
argparser.add_argument(
    "-s", "--sound", metavar="FILE",
    help="input: sound_definitions.json (sound definition)",
    action=action_input("sound")
)
argparser.add_argument(
    "-L", "--loot", metavar="DIR",
    help="input: a directory of loot table definitions",
    action=action_input("loot_table", vtype="dir")
)
argparser.add_argument(
    "-E", "--rp-entity", metavar="DIR",
    help="input: a directory of client entity definitions",
    action=action_input("rp_entity", vtype="dir")
)
argparser.add_argument(
    "-A", "--anim-controller", metavar="DIR",
    help="input: a directory of client animation controller definitions",
    action=action_input("rp_ac", vtype="dir")
)
argparser.add_argument(
    "-a", "--animation", metavar="DIR",
    help="input: a directory of client animation definitions",
    action=action_input("rp_anim", vtype="dir")
)
argparser.add_argument(
    "-r", "--recipe", metavar="DIR",
    help="input: a directory of recipe definitions",
    action=action_input("recipe", vtype="dir")
)
argparser.add_argument(
    "-y", "--ease", metavar="FILE",
    help="input: easing translation definition",
    action=action_input("ease")
)
argparser.add_argument(
    "-p", "--particle", metavar="DIR",
    help="input: a directory of particle definitions",
    action=action_input("particle", vtype="dir")
)
argparser.add_argument(
    "--bp", metavar="DIR",
    help="input: a bahavior pack directory",
    action=action_input("bp", vtype="dir")
)
argparser.add_argument(
    "--rp", metavar="DIR",
    help="input: a resource pack directory",
    action=action_input("rp", vtype="dir")
)
argparser.add_argument(
    "--pack-lang", metavar="LANG",
    help="used with --bp or --rp to specify language",
    default="en_US"
)
argparser.add_argument(
    "-o", "--out", metavar="PATH",
    help="specify the output path",
    default="./mccmdhl2/res/id_table.json"
)
argparser.add_argument(
    "-C", "--encoding", metavar="CODEC",
    help="specify file encoding; see also --out-encoding",
    default="utf-8"
)
argparser.add_argument(
    "--out-encoding", metavar="CODEC",
    help="specify output file encoding; default to --encoding",
    default=MISSING
)
argparser.add_argument(
    "-J", "--strict-json", action="store_true",
    help="use standard JSON (without comments)"
)
args = argparser.parse_args()

# Util
def open_r(file, **kwds):
    return open(file, "r", **kwds, encoding=args.encoding)

def json_loads(src: str):
    if not args.strict_json:
        if not src.endswith("\n"):
            src += "\n"
        src = re.sub(JSON_TOKENIZE, lambda m: m.group(1), src)
    return json.loads(src)

def json_load(file):
    return json_loads(file.read())

def read_json(path: str):
    with open_r(path) as file:
        try:
            return json_load(file)
        except json.JSONDecodeError:
            return None

# Go
def handle_lang(path: str):
    res = {k: {} for k in (
        "item", "entity", "block"
    )}
    with open_r(path) as file:
        while True:
            line = file.readline()
            if not line:
                break
            comment_index = line.find("#")
            if comment_index != -1:
                line = line[:comment_index]
            line = line.strip()
            if not line:
                continue
            equals_index = line.find("=")
            if equals_index == -1:
                raise ValueError(
                    "Invalid line in language file: %r" % line)
            key, text = line[:equals_index], line[equals_index + 1:]
            # Different types of keys
            if key.startswith("item.") and key.endswith(".name"):
                k = key[5:-5]
                if k.startswith("spawn_egg.entity."):
                    k = k[17:] + "_spawn_egg"
                if k.count(".") == 0 and k.lower() == k:
                    res["item"][k] = text
            elif key.startswith("entity.") and key.endswith(".name"):
                k = key[7:-5]
                if k.count(".") == 0 and k.lower() == k:
                    res["entity"][k] = text
            elif key.startswith("tile.") and key.endswith(".name"):
                k = key[5:-5]
                if k.count(".") == 0 and k.lower() == k:
                    res["block"][k] = text
    print("Handled language %s" % path)
    return IdTable(res)

def handle_json_file(path: str):
    res = read_json(path)
    if res is None:
        print("JSON error, skipping ID table %s" % path)
        return None
    print("Handled ID table %s" % path)
    return IdTable(res)

def handle_json(src: str):
    try:
        res = json_loads(src)
    except json.JSONDecodeError:
        print("JSON error, skipping literal JSON")
        return None
    else:
        return IdTable(res)

def _families_from_component(component: dict):
    try:
        family_c = component["minecraft:type_family"]["family"]
    except (KeyError, TypeError):
        return []
    else:
        if isinstance(family_c, list):
            return family_c
        return []

def handle_bp_entity(path: str):
    all_events = set()
    all_families = set()
    for name in os.listdir(path):
        # Read File
        spath = os.path.join(path, name)
        if not os.path.isfile(spath):
            continue
        definition = read_json(spath)
        if definition is None:
            print("JSON error, skipping entity %s" % spath)
            continue
        # Handle JSON
        ## Events
        try:
            event_d = definition["minecraft:entity"]["events"]
        except (KeyError, TypeError):
            pass
        else:
            if isinstance(event_d, dict):
                all_events.update(event_d.keys())
        ## Families
        try:
            family_d1 = definition["minecraft:entity"]["components"]
        except (KeyError, TypeError):
            pass
        else:
            all_families.update(_families_from_component(family_d1))
        try:
            family_d2 = definition["minecraft:entity"]["component_groups"]
        except (KeyError, TypeError):
            pass
        else:
            if isinstance(family_d2, dict):
                for comp in family_d2.values():
                    all_families.update(_families_from_component(comp))
    print("Handled server entity %s" % path)
    return IdTable({
        "family": dict.fromkeys(all_families),
        "entity_event": dict.fromkeys(all_events)
    })

def handle_rp_entity(path: str):
    all_animations = set()
    for name in os.listdir(path):
        # Read File
        spath = os.path.join(path, name)
        if not os.path.isfile(spath):
            continue
        definition = read_json(spath)
        if definition is None:
            print("JSON error, skipping client entity %s" % spath)
            continue
        # Handle JSON
        try:
            anim_d = definition["minecraft:client_entity"]["description"] \
                               ["animations"]
        except (KeyError, TypeError):
            pass
        else:
            if isinstance(anim_d, dict):
                all_animations.update(anim_d.keys())
    res = dict.fromkeys(all_animations)
    return IdTable({"animation_ref": res, "rpac_state": res})

def handle_missing_bs(path: str):
    root = read_json(path)
    if root is None:
        print("JSON error, skipping block state %s" % path)
        return None
    res = {}
    if not isinstance(root, dict):
        return None
    for block, d in root.items():
        if block.startswith("minecraft:"):
            block = block[10:]
        if "support_value" not in d:
            continue
        sv = d["support_value"]
        if not isinstance(sv, dict):
            continue
        res[block] = subres = {}
        for bs, values in sv.items():
            if not (isinstance(values, list) and values):
                continue
            type_ = type(values[0])
            D = {int: "int", bool: "bool", str: "str"}
            if type_ not in D:
                continue
            dt = D[type_]
            if dt not in subres:
                subres[dt] = {}
            if dt == "bool":
                values = list(map(
                    lambda b: {True: "true", False: "false"}[b],
                    values))
            elif dt == "str":
                values = list(map(
                    lambda s: '"%s"' % s, values
                ))
            subres[dt][bs] = values
    print("Handled Missing245's block state file %s" % path)
    return IdTable({"block_state": res})

def _id_read(root: str, save_name: str, user_repr: str):
    # Parse and get (file)/`root`/description/identifier in a directory
    def _res(path: str):
        res = []
        for name in os.listdir(path):
            # Read File
            spath = os.path.join(path, name)
            if not os.path.isfile(spath):
                continue
            definition = read_json(spath)
            if definition is None:
                print("JSON error, skipping %s %s" % (user_repr, spath))
                continue
            # Handle JSON
            try:
                id_ = definition[root]["description"]["identifier"]
            except (KeyError, TypeError):
                pass
            else:
                res.append(id_)
        print("Handled %s %s" % (user_repr, path))
        return IdTable({save_name: dict.fromkeys(res)})
    return _res

handle_fog = _id_read("minecraft:fog_settings", "fog", "fog")
handle_particle = _id_read("particle_effect", "particle", "particle")

def handle_biome(path: str):
    d = read_json(path)
    if d is None:
        print("JSON error, skipping biome %s" % path)
        return
    if (not isinstance(d, dict)
        or "biomes" not in d
        or not isinstance(d["biomes"], dict)
    ):
        print("Invalid biome definition, skipping %s" % path)
        return
    print("Handled biome definitions %s" % path)
    return IdTable({"biome": dict.fromkeys(d["biomes"].keys())})

def handle_rp_block(path: str):
    d = read_json(path)
    if d is None:
        print("JSON error, skipping client blocks %s" % path)
        return
    if not isinstance(d, dict):
        print("Invalid blocks.json, skipping %s" % path)
        return
    print("Handled client block definition %s" % path)
    return IdTable({"block": dict.fromkeys(d.keys())})

def handle_sound(path: str):
    d = read_json(path)
    if d is None:
        print("JSON error, skipping sound %s" % path)
        return
    if (not isinstance(d, dict)
        or "sound_definitions" not in d
        or not isinstance(d["sound_definitions"], dict)
    ):
        print("Invalid sound definition, skipping %s" % path)
        return
    sounds = d["sound_definitions"]
    print("Handled sound definitions %s" % path)
    return IdTable({
        "sound": dict.fromkeys(sounds.keys()),
        "music": dict.fromkeys(key for key, val in sounds.items()
            if (key.startswith("record.")
                or isinstance(val, dict)
                   and "category" in val
                   and val["category"] == "music"))
    })

def handle_loot(path: str):
    paths = (
        '"%s"' % path.replace('\\', '/')[:-5]  # strip ".json"
        for path in glob.iglob("**/*.json", recursive=True, root_dir=path)
    )
    print("Handled loot tables %s" % path)
    return IdTable({"loot_table": dict.fromkeys(paths)})

def handle_rpac(path: str):
    all_states = set()
    all_acs = set()
    for fname in os.listdir(path):
        spath = os.path.join(path, fname)
        if not os.path.isfile(spath):
            continue
        d = read_json(spath)
        if d is None:
            print("JSON error, skipping RPAC %s" % spath)
            return
        if (not isinstance(d, dict)
            or "animation_controllers" not in d
            or not isinstance(d["animation_controllers"], dict)
        ):
            print("Invalid RPAC definition, skipping %s" % spath)
            continue
        acd = d["animation_controllers"]
        for name, def_ in acd.items():
            if (not isinstance(def_, dict)
                or "states" not in def_
                or not isinstance(def_["states"], dict)
            ):
                print("Invalid RPAC %r in %s, skipping" % (name, spath))
                continue
            all_states.update(def_["states"].keys())
        all_acs.update(acd.keys())
    print("Handled client animation controllers %s" % path)
    return IdTable({
        "rpac_state": dict.fromkeys(all_states),
        "rpac": dict.fromkeys(all_acs)
    })

def handle_rp_anim(path: str):
    all_anims = set()
    for fname in os.listdir(path):
        spath = os.path.join(path, fname)
        d = read_json(spath)
        if d is None:
            print("JSON error, skipping animation %s" % spath)
            continue
        if (not isinstance(d, dict)
            or "animations" not in d
            or not isinstance(d["animations"], dict)
        ):
            print("Invalid animation definition, skipping %s" % spath)
            continue
        all_anims.update(d["animations"].keys())
    print("Handled animation definitions %s" % path)
    return IdTable({"animation_ref": dict.fromkeys(all_anims)})

def handle_recipe(path: str):
    all_recipes = []
    for fname in os.listdir(path):
        spath = os.path.join(path, fname)
        d = read_json(spath)
        if d is None:
            print("JSON error, skipping recipe %s" % spath)
            continue
        if not isinstance(d, dict):
            print("Invalid recipe definition, skipping %s" % spath)
            continue
        ks = [k for k in d.keys() if k.startswith("minecraft:")]
        if len(ks) != 1:
            print("Invalid recipe definition, skipping %s" % spath)
            continue
        defi = d[ks[0]]
        try:
            rid = defi["description"]["identifier"]
        except KeyError:
            print("Invalid recipe definition, skipping %s" % spath)
            continue
        else:
            all_recipes.append(rid)
    print("Handled recipe definitions %s" % path)
    return IdTable({"recipe": dict.fromkeys(all_recipes)})

def handle_ease(path: str):
    d = read_json(path)
    if d is None:
        print("JSON error, skipping easing %s" % path)
        return
    if not ("range" in d and "func" in d) \
       or not (isinstance(d["range"], dict), isinstance(d["func"], dict)):
        print("Object 'range' & 'func' required, skipping easing %s" % path)
        return
    res = {"linear": d.get("linear"), "spring": d.get("spring")}
    for range_ in ("in", "out", "in_out"):
        for func in ("back", "bounce", "circ", "cubic", "elastic",
                     "expo", "quad", "quart", "quint", "sine"):
            res["%s_%s" % (range_, func)] = "".join((
                d["range"].get(range_),
                d.get("separator", ", "),
                d["func"].get(func)
            ))
    print("Handled easing %s" % path)
    return IdTable({"ease_type": res})

BP_DISPATCH = {
    "entities/": handle_bp_entity,
    "loot_tables/": handle_loot,
    "recipes/": handle_recipe,
}
RP_DISPATCH = {
    "animation_controllers/": handle_rpac,
    "animations/": handle_rp_anim,
    "entity/": handle_rp_entity,
    "fogs/": handle_fog,
    "particles/": handle_particle,
    "sounds/sound_definitions.json": handle_sound,
    "blocks.json": handle_rp_block,
    "biomes_client.json": handle_biome,
    "texts/{lang}.lang": handle_lang,
}

def handle_pack(path: str, dispatcher: Dict[str, Callable]):
    tables = []
    for subpath, func in dispatcher.items():
        subpath = subpath.format(lang=args.pack_lang)
        target = os.path.join(path, subpath)
        try:
            table = func(target)
        except OSError:
            pass
        else:
            if table is not None:
                tables.append(table)
    return IdTable.merge_from(*tables)

handle_bp = partial(handle_pack, dispatcher=BP_DISPATCH)
handle_rp = partial(handle_pack, dispatcher=RP_DISPATCH)

TYPE2FUNC = {
    "lang": handle_lang,
    "id_table": handle_json_file,
    "json": handle_json,
    "bp_entity": handle_bp_entity,
    "rp_entity": handle_rp_entity,
    "block_state": handle_missing_bs,
    "fog": handle_fog,
    "biome": handle_biome,
    "rp_block": handle_rp_block,
    "sound": handle_sound,
    "loot_table": handle_loot,
    "rp_ac": handle_rpac,
    "rp_anim": handle_rp_anim,
    "recipe": handle_recipe,
    "ease": handle_ease,
    "particle": handle_particle,
    "bp": handle_bp,
    "rp": handle_rp
}

try:
    codecs.lookup(args.encoding)
except LookupError:
    argparser.error("invalid codec %r" % args.encoding)
out_encoding = args.out_encoding
if out_encoding is MISSING:
    out_encoding = args.encoding
else:
    try:
        codecs.lookup(out_encoding)
    except LookupError:
        argparser.error("invalid output codec %r" % out_encoding)
if not hasattr(args, "input_list"):
    argparser.error("no input file")
tables = []
for type_, value in args.input_list:
    res = TYPE2FUNC[type_](value)
    if res is not None:
        tables.append(res)

result = IdTable.merge_from(*tables)
try:
    result.dump(args.out, encoding=out_encoding)
except OSError:
    argparser.error("error when dumping result: %s: %s"
                    % sys.exc_info()[:2])
print("Merged results, done!")
