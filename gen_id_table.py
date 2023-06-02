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
import argparse
from mccmdhl2 import IdTable
from typing import List, Tuple

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

def action_input(input_type: str, vtype: str = "file"):
    class _Action(argparse.Action):
        def __call__(self, parser, namespace, value: str, option):
            if vtype in ("file", "dir"):
                if not os.path.exists(value):
                    argparser.error("path does not exists: %s" % value)
                if (vtype == "file") ^ os.path.isfile(value):
                    argparser.error("path need to be a %s" % vtype)
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
    "-b", "--block-state", metavar="FILE",
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
    "-c", "--rp-block", metavar="FILE",
    help="input: blocks.json (resource pack block definition)",
    action=action_input("rp_block")
)
argparser.add_argument(
    "-o", "--out", metavar="PATH",
    help="specify the output path",
    default="./mccmdhl2/res/id_table.json"
)
argparser.add_argument(
    "-J", "--strict-json", action="store_true",
    help="use standard JSON (without comments)"
)
args = argparser.parse_args()

# Util
def json_loads(src: str):
    if not args.strict_json:
        if not src.endswith("\n"):
            src += "\n"
        src = re.sub(JSON_TOKENIZE, lambda m: m.group(1), src)
    return json.loads(src)

def json_load(file):
    return json_loads(file.read())

# Go
def handle_lang(path: str):
    res = {k: {} for k in (
        "item", "entity", "block"
    )}
    with open(path, "r") as file:
        while True:
            line = file.readline()
            if not line:
                break
            line = line.strip()
            comment_index = line.find("#")
            if comment_index != -1:
                line = line[:comment_index]
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
                res["entity"][key[7:-5]] = text
            elif key.startswith("tile.") and key.endswith(".name"):
                k = key[5:-5]
                if k.count(".") == 0 and k.lower() == k:
                    res["block"][k] = text
    print("Handled language %s" % path)
    return IdTable(res)

def handle_json_file(path: str):
    try:
        res = IdTable.from_json(path)
    except json.JSONDecodeError:
        print("JSON Failure: skipping ID table %s" % path)
        return None
    else:
        print("Handled ID table %s" % path)
        return res

def handle_json(src: str):
    try:
        res = json_loads(src)
    except json.JSONDecodeError:
        print("JSON Failure: skipping literal JSON")
        return None
    else:
        return IdTable(res)

def _families_from_component(component: dict):
    try:
        family_c = component["minecraft:type_family"]["family"]
    except KeyError:
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
        with open(spath, "r") as file:
            try:
                definition = json_load(file)
            except json.JSONDecodeError:
                print("JSON Failure: skipping entity %s" % spath)
                continue
        # Handle JSON
        ## Events
        events = []
        try:
            event_d = definition["minecraft:entity"]["events"]
        except KeyError:
            pass
        else:
            if isinstance(event_d, dict):
                events = event_d.keys()
        all_events.update(events)
        ## Families
        try:
            family_d1 = definition["minecraft:entity"]["components"]
        except KeyError:
            pass
        else:
            all_families.update(_families_from_component(family_d1))
        try:
            family_d2 = definition["minecraft:entity"]["component_groups"]
        except KeyError:
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

def handle_missing_bs(path: str):
    with open(path, "r") as file:
        try:
            root = json_load(file)
        except json.JSONDecodeError:
            print("JSON Failure: skipping block state %s" % spath)
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

def handle_fog(path: str):
    res = []
    for name in os.listdir(path):
        # Read File
        spath = os.path.join(path, name)
        if not os.path.isfile(spath):
            continue
        with open(spath, "r") as file:
            try:
                definition = json_load(file)
            except json.JSONDecodeError:
                print("JSON Failure: skipping entity %s" % spath)
                continue
        # Handle JSON
        try:
            id_ = definition["minecraft:fog_settings"]["description"] \
                            ["identifier"]
        except KeyError:
            pass
        else:
            res.append(id_)
    print("Handled fog definitions %s" % path)
    return IdTable({"fog": dict.fromkeys(res)})

def handle_biome(path: str):
    with open(path, "r") as file:
        try:
            d = json_load(file)
        except json.JSONDecodeError:
            print("JSON Failure: skipping biome %s" % path)
            return
    if (not isinstance(d, dict)
        or "biomes" not in d
        or not isinstance(d["biomes"], dict)
    ):
        print("Invalid biome definition, skipping %s" % path)
    print("Handled biome definitions %s" % path)
    return IdTable({"biome": dict.fromkeys(d["biomes"].keys())})

def handle_rp_block(path: str):
    with open(path, "r") as file:
        try:
            d = json_load(file)
        except json.JSONDecodeError:
            print("JSON Failure: skipping client blocks %s" % path)
            return
    if not isinstance(d, dict):
        print("Invalid blocks.json, skipping %s" % path)
    print("Handled client block definition %s" % path)
    return IdTable({"block": dict.fromkeys(d.keys())})

tables = []
if not args.input_list:
    argparser.error("no input file")
for type_, value in args.input_list:
    res = {
        "lang": handle_lang,
        "id_table": handle_json_file,
        "json": handle_json,
        "bp_entity": handle_bp_entity,
        "block_state": handle_missing_bs,
        "fog": handle_fog,
        "biome": handle_biome,
        "rp_block": handle_rp_block
    }[type_](value)
    if res is not None:
        tables.append(res)

result = IdTable.merge_from(*tables)
try:
    result.dump(args.out)
except OSError:
    argparser.error("error when dumping result: %s: %s"
                    % sys.exc_info()[:2])
print("Merged results, done!")
