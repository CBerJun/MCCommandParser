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

"""Node definition of Minecraft command arguments and the tree
definition.
"""

from typing import (
    Dict, List, Callable, Optional, Any, TypeVar, Union,
    TYPE_CHECKING
)
import itertools
import json
import re

from .parser import (
    Node, Empty, Finish, CompressedNode, SubparsingNode,
    ArgParseFailure, ExpectationFailure, SemanticError, BaseError,
    Font
)
from .reader import Reader, ReaderError, DIGITS, TERMINATORS, SIGNS
from .autocompleter import (
    Suggestion, IdSuggestion,
    str_find_rule, RULEW_OTHER, RULEW_FAILED, RULEW_STR_FIND, RuleWeight,
    AutoCompletingUnit
)
from .marker import FontMark, AutoCompletingMark, Marker
if TYPE_CHECKING:
    from .parser import MCVersion, VersionFilter
    from .autocompleter import IdTable, HandledSuggestion

NAMESPACEDID = frozenset("0123456789:._-abcdefghijklmnopqrstuvwxyz")

def char_check_rule(checker: Callable[[str], bool]):
    def _rule(s: str):
        if all(map(checker, s)):
            return RULEW_OTHER
        else:
            return RULEW_FAILED
    return _rule
def char_rule(char: str):
    def _rule(s: str):
        if (not s) or (s == char):
            return RULEW_OTHER
        return RULEW_FAILED
    return _rule

def version_le(version: "MCVersion") -> "VersionFilter":
    return lambda v: v <= version
def version_ge(version: "MCVersion") -> "VersionFilter":
    return lambda v: v >= version
def version_lt(version: "MCVersion") -> "VersionFilter":
    return lambda v: v < version

def dict_getter(d: dict, *path: List[str]):
    try:
        for s in itertools.chain(*path):
            d = d[s]
    except KeyError:
        return None
    return d

class Char(Node):
    argument_end = False

    def __init__(self, char: str):
        super().__init__()
        self.char = char

    def _parse(self, reader: Reader):
        if reader.peek() == self.char:
            reader.next()
        else:
            raise ExpectationFailure("char", char=self.char)

    def _suggest(self):
        return [Suggestion(
            name="autocomp.char",
            writes=self.char,
            name_kwds={"char": self.char},
            match_rule=char_rule(self.char)
        )]

INF = float("inf")

class Numeric(Node):
    default_font = Font.numeric

    def _parse(self, reader: Reader) -> float:
        raise NotImplementedError

    def ranged(self, min=-INF, max=INF):
        def _checker(res: float):
            if not min <= res <= max:
                raise SemanticError("error.semantic.number.out_of_range",
                                    min=min, max=max)
        return self.checker(_checker)

    def none_of(self, *numbers: float):
        def _checker(res: float):
            if res in numbers:
                raise SemanticError("error.semantic.number.cant_be", num=res)
        return self.checker(_checker)

    def one_of(self, *numbers: float):
        def _checker(res: float):
            if res not in numbers:
                raise SemanticError("error.semantic.number.must_be",
                                    nums=numbers)
        return self.checker(_checker)

class Integer(Numeric):
    def _parse(self, reader: Reader):
        try:
            res = reader.read_int()
        except ReaderError:
            raise ExpectationFailure("int")
        else:
            return res

    def _suggest(self):
        return [Suggestion(
            name="autocomp.integer", writes="0",
            match_rule=char_check_rule(
                lambda char: char in DIGITS or char in SIGNS
            )
        )]

class Float(Numeric):
    def _parse(self, reader: Reader):
        try:
            res = reader.read_float()
        except ReaderError:
            raise ExpectationFailure("float")
        else:
            return res

    def _suggest(self):
        return [Suggestion(
            name="autocomp.float", writes="0.0",
            match_rule=char_check_rule(
                lambda char: char in DIGITS or char in SIGNS or char == "."
            )
        )]

class Word(Node):
    default_font = Font.string

    def _parse(self, reader: Reader):
        word = reader.read_word()
        if not word:
            raise ExpectationFailure("word")
        return word

    def _suggest(self):
        return [Suggestion(
            name="autocomp.word", writes="word",
            match_rule=char_check_rule(
                lambda char: char not in TERMINATORS
            )
        )]

class Boolean(Word):
    default_font = Font.numeric

    def _parse(self, reader: Reader):
        word = reader.read_word()
        if word != "true" and word != "false":
            raise ExpectationFailure("bool")
        return word

    def _suggest(self):
        return [
            Suggestion(
                name="autocomp.true", writes="true",
                match_rule=str_find_rule("true")
            ),
            Suggestion(
                name="autocomp.false", writes="false",
                match_rule=str_find_rule("false")
            )
        ]

class NamespacedId(Word):
    def __init__(self, id_type: str):
        self.id_type = id_type
        super().__init__()

    def _parse(self, reader: Reader):
        word = super()._parse(reader)
        for char in word:
            if char not in NAMESPACEDID:
                raise ArgParseFailure("error.syntax.id_invalid", char=char)
        return word

    def _suggest(self):
        return [IdSuggestion(self.id_type)]

class QuotedString(SubparsingNode):
    argument_end = False
    default_font = Font.string

    def _parse(self, marker: "Marker"):
        reader = marker.reader
        pos_begin = reader.get_location()
        with marker.add_font_mark(Font.meta):  # Opening '"'
            if reader.next() != '"':
                raise ExpectationFailure("quoted_str")
        chars = []
        pos0 = reader.get_location()
        char = reader.next()
        while True:
            if char == '"' or reader.is_line_end(char):
                break
            if char == "\\":
                f = True
                char2 = reader.next()
                if char2 == "\\":
                    chars.append("\\")
                elif char2 == '"':
                    chars.append('"')
                else:
                    f = False
                    chars.append(char)
                    chars.append(char2)
                if f:
                    marker.font_marks.append(FontMark(
                        pos0, reader.get_location(), Font.meta
                    ))  # Escape
            else:
                chars.append(char)
            pos0 = reader.get_location()
            char = reader.next()
        if char != '"':
            raise ArgParseFailure("error.syntax.unclosed_str")
        pos_end = reader.get_location()
        marker.font_marks.append(FontMark(
            pos_end.offset(-1), pos_end, Font.meta
        ))  # Closing '"'
        marker.ac_marks.append(AutoCompletingMark.from_node(
            pos_begin, pos_end, self, marker.version
        ))
        return "".join(chars)

    @staticmethod
    def _rule(s: str):
        if not s:
            return RULEW_OTHER
        elif s[0] == '"':
            return RULEW_OTHER
        else:
            return RULEW_FAILED

    def _suggest(self):
        return [Suggestion(
            name="autocomp.quoted_string", writes='"string"',
            match_rule=self._rule
        )]

class String(CompressedNode):
    def _tree(self):
        self._word_part = Word()
        self._qstr_part = QuotedString()
        (self
          .branch(
            self._word_part
              .branch(self.end)
          )
          .branch(
            self._qstr_part
              .branch(self.end)
          )
        )

class IdEntity(NamespacedId):
    def __init__(self):
        super().__init__("entity")
class IdItem(NamespacedId):
    def __init__(self):
        super().__init__("item")
class IdBlock(NamespacedId):
    def __init__(self):
        super().__init__("block")
class IdFamily(String):
    def __init__(self):
        super().__init__()
        self._word_part._suggest = lambda: [IdSuggestion("family")]
class EntitySlot(Word):
    def _suggest(self):
        return [IdSuggestion("entity_slot")]
class BlockSlot(Word):
    def _suggest(self):
        return [IdSuggestion("block_slot")]
class IdDamageType(NamespacedId):
    def __init__(self):
        super().__init__("damage")
class IdEffect(NamespacedId):
    def __init__(self):
        super().__init__("effect")
class IdEnchantment(NamespacedId):
    def __init__(self):
        super().__init__("enchantment")
class IdEntityEvent(String):
    def __init__(self):
        super().__init__()
        self._word_part._suggest = lambda: [IdSuggestion("entity_event")]
class IdFog(NamespacedId):
    def __init__(self):
        super().__init__("fog")
class GameRule(Word):
    def _suggest(self):
        return [IdSuggestion("game_rule")]
class IdPermission(Word):
    def _suggest(self):
        return [IdSuggestion("permission")]
class IdStructure(Word):
    def _suggest(self):
        return [IdSuggestion("structure")]
class IdBiome(NamespacedId):
    def __init__(self):
        super().__init__("biome")

def ItemData(is_test: bool):
    return (Integer()
              .ranged(min=-1 if is_test else 0, max=32767)
              .note("note._item_data"))

_PT = TypeVar("_PT")

def ResultTracked(node: Node[_PT], callback: Callable[[_PT], Any]):
    """Call `callback` when `node` successfully parsed."""
    orig = node._parse
    def _new_parse(reader):
        v = orig(reader)
        callback(v)
        return v
    node._parse = _new_parse
    return node

class _DynamicIdSuggestion(IdSuggestion):
    def __init__(self, path: List[str],
        orig_suggest: Callable[[], Union[Suggestion, "HandledSuggestion"]],
        map_handler: Callable[[Union[dict, list]], List[str]],
        note: Union[str, None] = None
    ):
        super().__init__(path[0], note)
        self.__path = path
        self.__orig_suggest = orig_suggest
        self.__map_handler = map_handler

    def resolve(self, id_table: "IdTable") \
            -> List[Union[Suggestion, "HandledSuggestion"]]:
        val = id_table.map
        try:
            for k in self.__path:
                if not isinstance(val, dict):
                    raise TypeError
                val = val[k]
        except (KeyError, TypeError) as err:
            res = self.__orig_suggest()
            for s in res:
                if isinstance(s, Suggestion):
                    s.note = "autocomp.dynamic_id.failed"
            return res
        else:
            val = self.__map_handler(val)
            assert isinstance(val, (list, dict))
            if isinstance(val, list):
                val = dict.fromkeys(val)
            def _map(arg):
                sv = str(arg[0])
                return Suggestion(
                    name=sv, writes=sv, note=arg[1] if arg[1] else self.note,
                    match_rule=str_find_rule(sv)
                )
            return list(map(_map, val.items()))

def DynamicId(node: Node, path_getter: Callable[[], List[str]],
              map_handler: Callable[[Union[dict, list]],
                                    Union[List[str], Dict[str, str]]]
                         = lambda d: d):
    """Return the `node` that use suggestions from `IdTable`s, but
    the ID is dynamic (related to context). `path_getter` should return
    the path to values in `IdTable`, like
    `["block_state", "bamboo", "str", "leaves"]`.
    """
    orig_suggest = node._suggest
    def _new_suggest():
        return [_DynamicIdSuggestion(
            path_getter(), orig_suggest, map_handler)]
    node._suggest = _new_suggest
    return node

class BlockSpec(CompressedNode):
    class _BlockStatePair(CompressedNode):
        def __init__(self, parent_path: Callable[[], List[str]]):
            self.__parent_path = parent_path
            super().__init__()

        def _tree(self):
            self.__key = None
            def _set_key(value: str):
                self.__key = value
            def _get_vpath(type_: str):
                def _res():
                    assert self.__key is not None
                    l = self.__parent_path()
                    l.append(type_)
                    l.append(self.__key)
                    return l
                return _res
            def _kmap_handler(map_: Dict[str, Dict[str, List[str]]]):
                res = []
                for k in ("int", "bool", "str"):
                    if k in map_:
                        res.extend('"%s"' % s for s in map_[k].keys())
                return res
            (self
              .branch(
                DynamicId(
                    ResultTracked(QuotedString(), _set_key),
                    self.__parent_path, _kmap_handler
                )
                  .note("note._block_state.key")
                  .branch(
                    Char(":")
                      .branch(
                        DynamicId(QuotedString(), _get_vpath("str"))
                          .note("note._block_state.value")
                          .branch(self.end)
                      )
                      .branch(
                        DynamicId(Integer(), _get_vpath("int"))
                          .note("note._block_state.value")
                          .branch(self.end)
                      )
                      .branch(
                        DynamicId(Boolean(), _get_vpath("bool"))
                          .note("note._block_state.value")
                          .branch(self.end)
                      )
                  )
              )
            )

    def __init__(self, bs_optional: Optional[Node] = None):
        """bs_optional: allow omitting block state and just write
        this node after block ID. This only matters <1.19.80,
        since any id can omit block state >=1.19.80.
        """
        self.__bs_node = bs_optional
        super().__init__()

    def _tree(self):
        self.__block_id = None
        def _set_block_id(value: str):
            if value.startswith("minecraft:"):
                value = value[10:]
            self.__block_id = value
        def _get_path():
            return ["block_state", self.__block_id]
        root = ResultTracked(IdBlock(), _set_block_id)
        (self
          .branch(
            root
              # Block data (deprecated since 1.19.70)
              .branch(
                Integer()
                  .note("note._block_data")
                  .branch(self.end),
                version=version_le((1, 19, 70))
              )
              # Block state
              .branch(
                Series(
                  begin=Char("[")
                    .note("note._block_state.begin"),
                  end=Char("]")
                    .note("note._block_state.end"),
                  seperator=Char(",")
                    .note("note._block_state.seperator"),
                  content=self._BlockStatePair(_get_path),
                  empty_ok=True
                )
                  .branch(self.end)
              )
              # Above 1.19.80, Block state can be omitted
              .branch(self.end, version=version_ge((1, 19, 80)))
          )
        )
        if self.__bs_node:
            root.branch(self.__bs_node,
                        # Without version filter, there may be 2
                        # "(Line Finish)" hints when version >=
                        # 1.19.80.
                        version=version_lt((1, 19, 80)))

class Keyword(Node):
    default_font = Font.keyword

    def __init__(self, word: str):
        super().__init__()
        self.word = word

    def _parse(self, reader: Reader):
        if reader.read_word() != self.word:
            raise ExpectationFailure("keyword", keyword=self.word)

    def _suggest(self):
        return [Suggestion(
            name="autocomp.keyword",
            writes=self.word,
            name_kwds={"keyword": self.word},
            match_rule=str_find_rule(self.word)
        )]

class Enumerate(Node):
    default_font = Font.keyword

    def __init__(self, *options: str, note_table: Dict[str, str] = {}):
        super().__init__()
        self.options = options
        self.note_table = note_table

    def _parse(self, reader: Reader):
        word = reader.read_word()
        if word not in self.options:
            raise ExpectationFailure("enum", options=self.options)
        return word

    def _suggest(self):
        return [
            Suggestion(
                name="autocomp.option",
                writes=word,
                note=self.note_table.get(word),
                name_kwds={"option": word},
                match_rule=str_find_rule(word)
            )
            for word in self.options
        ]

def NotedEnumerate(*options: str, note_template: str):
    note_table = {}
    for o in options:
        note_table[o] = note_template % o
    return Enumerate(*options, note_table=note_table)

class Invertable(CompressedNode):
    def __init__(self, node: Node):
        self.node = node
        super().__init__()

    def _tree(self):
        self.node.branch(self.end)
        (self
          .branch(
            self.node
          )
          .branch(
            Char("!")
              .note("note._invert")
              .font(Font.meta)
              .branch(
                self.node
              )
          )
        )

class Chars(Node):
    """Multiple characters.
    `Chars("!=")` <==> `Char("!").branch(Char("="), is_close=True)`.
    In auto-completion "!=" will be treated as a single suggestion,
    but not first "!" then "=".
    """
    argument_end = False
    default_font = Font.meta

    def __init__(self, chars: str):
        super().__init__()
        self.chars = chars

    def _parse(self, reader: Reader):
        for char in self.chars:
            if reader.next() != char:
                raise ExpectationFailure("chars", chars=self.chars)

    def _suggest(self):
        return [Suggestion(
            name="autocomp.chars",
            writes=self.chars,
            name_kwds={"chars": self.chars},
            match_rule=str_find_rule(self.chars)
        )]

class CharsEnumerate(CompressedNode):
    def __init__(self, *strings: str, note_template: Optional[str] = None):
        self.strings = strings
        self.note_template = note_template
        super().__init__()

    def _tree(self):
        for chars in self.strings:
            self.branch(
              Chars(chars)
                .note(self.note_template % chars
                      if self.note_template else None)
                .branch(self.end)
            )

class IntegerNoEnd(Integer):
    """An integer that does not require argument terminator."""
    argument_end = False

class _RawIntRange(CompressedNode):
    """Un-invertable integer range."""
    def _tree(self):
        (self
          .branch(
            IntegerNoEnd()
            # If we use regular `Integer` here, there must be space
            # between integer and "..".
              .branch(
                Chars("..")
                  .note("note._int_range")
                  .branch(self.end)
                  .branch(
                    Integer()
                      .branch(self.end)
                  )
              )
              .branch(
                # Since we used `IntegerNoEnd` above, when there is
                # actually no ".." after integer, the terminator
                # should come back.
                  self.end, require_arg_end=True
              )
          )
          .branch(
            Chars("..")
              .note("note._int_range")
              .branch(
                Integer()
                  .branch(self.end)
              )
          )
        )

def IntRange():
    return Invertable(_RawIntRange())

class BareText(Node):
    default_font = Font.string

    def __init__(self, empty_ok: bool):
        super().__init__()
        self.__empty_ok = empty_ok

    def _parse(self, reader: Reader):
        s = reader.read_until_eol()
        if not s and not self.__empty_ok:
            raise ExpectationFailure("bare_text")
        return s

    def _suggest(self):
        return [Suggestion(
            name="autocomp.bare_text", writes="text",
            match_rule=lambda s: RULEW_OTHER
        )]

class OffsetFloat(Node):
    default_font = Font.position

    def _parse(self, reader: Reader):
        try:
            res = reader.read_float(no_int_part_ok=True)
        except ReaderError:
            raise ExpectationFailure("offset_float")
        else:
            return res

    def _suggest(self):
        return [Suggestion(
            name="autocomp.offset_float", writes="0",
            match_rule=char_check_rule(
                lambda char: char in DIGITS or char in SIGNS or char == "."
            )
        )]

class Pos(CompressedNode):
    def __init__(self, type_: str):
        self._type = type_
        super().__init__()

    def _tree(self):
        (self
          .branch(
            Float()
              .font(Font.position)
              .note("note._pos.absolute." + self._type)
              .branch(self.end)
          )
          .branch(
            Char("~")
              .font(Font.position)
              .note("note._pos.relative." + self._type)
              .branch(
                OffsetFloat()
                  .font(Font.position)
                  .note("note._pos.float_offset")
                  .branch(self.end),
                is_close=True
              )
              .branch(
                self.end, require_arg_end=True
              )
          )
        )

class LocalPos(CompressedNode):
    def __init__(self, type_: str):
        self._type = type_
        super().__init__()

    def _tree(self):
        (self
          .branch(
            Char("^")
              .font(Font.position)
              .note("note._pos.local." + self._type)
              .branch(
                OffsetFloat()
                  .font(Font.position)
                  .note("note._pos.float_offset")
                  .branch(self.end),
                is_close=True
              )
              .branch(
                self.end, require_arg_end=True
              )
          )
        )

class Pos3D(CompressedNode):
    def _tree(self):
        for cls in (Pos, LocalPos):
            (self
              .branch(
                cls("x")
                  .branch(
                    cls("y")
                      .branch(
                        cls("z")
                          .branch(self.end)
                      )
                  )
              )
            )

class Rotation(CompressedNode):
    def __init__(self, type_: str):
        self._type = type_
        super().__init__()

    def _tree(self):
        (self
          .branch(
            Float()
              .font(Font.rotation)
              .note("note._rot.absolute." + self._type)
              .branch(self.end)
          )
          .branch(
            Char("~")
              .font(Font.rotation)
              .note("note._rot.relative." + self._type)
              .branch(
                OffsetFloat()
                  .font(Font.rotation)
                  .note("note._rot.float_offset")
                  .branch(self.end),
                is_close=True
              )
              .branch(
                self.end, require_arg_end=True
              )
          )
        )

class YawPitch(CompressedNode):
    def _tree(self):
        (self
          .branch(
            Rotation("x")
              .branch(
                Rotation("y")
                  .branch(self.end)
              )
          )
        )

class GameMode(CompressedNode):
    def __init__(self, allow_5: bool):
        self.allow_5 = allow_5
        super().__init__()

    def _note_table(self) -> Dict[str, str]:
        res: Dict[str, str] = {}
        for mode in ("spectator", "adventure", "creative",
                     "survival", "default"):
            res[mode] = "note._gamemode." + mode
        res["s"] = res["survival"]
        res["c"] = res["creative"]
        res["d"] = res["default"]
        res["a"] = res["adventure"]
        return res

    def _allow_ids(self):
        res = [0, 1, 2]
        if self.allow_5:
            res.append(5)
        return res

    def _tree(self):
        (self
          .branch(
            Enumerate("spectator", "adventure", "survival", "creative",
                      "default", "s", "c", "a", "d",
                      note_table=self._note_table())
              .branch(self.end)
          )
          .branch(
            Integer()
              .one_of(*self._allow_ids())
              .font(Font.keyword)
              .note("note._gamemode._number")
              .branch(self.end)
          )
        )

def PermissionState(note: Optional[str] = None):
    note_map = {"enabled": "note._states.enabled",
                "disabled": "note._states.disabled"}
    if note is not None:
        note_map["enabled"] = note_map["disabled"] = note
    return (Enumerate("enabled", "disabled", note_table=note_map)
      .font(Font.numeric)
    )

class Series(CompressedNode):
    def __init__(self, begin: Node, content: Node,
                       seperator: Node, end: Node,
                       empty_ok: bool):
        self.begin = begin
        self.content = content
        self.seperator = seperator
        self.end_ = end
        self.empty_ok = empty_ok
        super().__init__()

    def _tree(self):
        self.end_.branch(self.end)
        self.branch(
          self.begin
            .branch(
              self.content
                .branch(
                  self.seperator
                    .branch(self.content)
                )
                .branch(
                  self.end_
                )
            )
        )
        if self.empty_ok:
            self.begin.branch(
              self.end_
            )

class KeywordCaseInsensitive(Keyword):
    def _parse(self, reader: Reader):
        if reader.read_word().lower() != self.word:
            raise ExpectationFailure("keyword", keyword=self.word)

    def _rule(self, pattern: str):
        f = self.word.find(pattern.lower())
        if f == -1:
            return RULEW_FAILED
        else:
            return RuleWeight(RULEW_STR_FIND - f)

    def _suggest(self):
        res = super()._suggest()
        for r in res:
            r.match_rule = self._rule
        return res

class SelectorArg(CompressedNode):
    class _HasItem(CompressedNode):
        def _hasitem_object(self):
            return Series(
              begin=Char("{")
                .note("note._selector.complex.hasitem.begin.object"),
              end=Char("}")
                .note("note._selector.complex.hasitem.end.object"),
              seperator=Char(",")
                .note("note._selector.complex.hasitem.seperator.object"),
              content=self._HasItemArg(),
              empty_ok=False
            )

        def _tree(self):
            (self
              .branch(
                self._hasitem_object()
                  .branch(self.end)
              )
              .branch(
                Series(
                  begin=Char("[")
                    .note("note._selector.complex.hasitem.begin.array"),
                  end=Char("]")
                    .note("note._selector.complex.hasitem.end.array"),
                  seperator=Char(",")
                    .note("note._selector.complex.hasitem.seperator.array"),
                  content=self._hasitem_object(),
                  empty_ok=False
                )
                  .branch(self.end)
              )
            )

        class _HasItemArg(CompressedNode):
            def _tree(self):
                for arg, node in (
                    ("item", IdItem()),
                    ("data", ItemData(is_test=True)),
                    ("quantity", IntRange()),
                    ("location", EntitySlot()),
                    ("slot", IntRange())
                ):
                    self.branch(
                      Keyword(arg)
                        .note("note._selector.complex.hasitem." + arg)
                        .branch(
                          Char("=")
                            .note("note._selector.complex.hasitem.equals")
                            .branch(
                              node
                                .branch(self.end)
                            )
                        )
                    )

    class _RawTag(CompressedNode):
        def _tree(self):
            (self
              .branch(
                String()
                .font(Font.tag)
                .note("note._selector.complex.tag")
                .branch(self.end)
              )
              .branch(
                # Yep, @e[tag=] is legal and it selects entities
                # without any tag.
                self.end
              )
            )

    class _ScoresArg(CompressedNode):
        def _tree(self):
            (self
              .branch(
                String()
                .note("note._scoreboard")
                .font(Font.scoreboard)
                .branch(
                  Char("=")
                    .branch(
                      IntRange()
                        .branch(self.end)
                    )
                )
              ) 
            )

    class _HasPermissionArg(CompressedNode):
        def _tree(self):
            (self
              .branch(
                IdPermission()
                  .branch(
                    Char("=")
                      .branch(
                        PermissionState()
                          .branch(self.end)
                      )
                  )
              )
            )

    @staticmethod
    def _XRotation():
        return (Float()
          .note("note._rot.absolute.x")
          .font(Font.rotation)
          .ranged(min=-90, max=90)
        )
    @staticmethod
    def _YRotation():
        return (Float()
          .note("note._rot.absolute.y")
          .font(Font.rotation)
          .ranged(min=-180, max=180)
        )

    def _tree(self):
        def _handle(arg: str, node: Node, kwds: Dict[str, Any] = {}):
            self.branch(
              KeywordCaseInsensitive(arg)
                .note("note._selector.complex.arg_names." + arg)
                .branch(
                  Char("=")
                    .note("note._selector.complex.equals")
                    .branch(
                      node
                        .branch(self.end)
                    )
                ),
              **kwds
            )
        for args in (
            ("r", Float().ranged(min=0)),
            ("rm", Float().ranged(min=0)),
            ("dx", Float()),
            ("dy", Float()),
            ("dz", Float()),
            ("x", Pos("x")),
            ("y", Pos("y")),
            ("z", Pos("z")),
            ("scores", Series(
              begin=Char("{")
                .note("note._selector.complex.scores.begin"),
              end=Char("}")
                .note("note._selector.complex.scores.end"),
              seperator=Char(",")
                .note("note._selector.complex.scores.seperator"),
              content=self._ScoresArg(),
              empty_ok=False
            )),
            ("tag", Invertable(self._RawTag())),
            ("name", Invertable(String())),
            ("type", Invertable(IdEntity())),
            ("family", Invertable(IdFamily())),
            ("rx", self._XRotation()),
            ("rxm", self._XRotation()),
            ("ry", self._YRotation()),
            ("rym", self._YRotation()),
            ("hasitem", self._HasItem()),
            ("l", Integer().ranged(min=0)),
            ("lm", Integer().ranged(min=0)),
            ("m", GameMode(allow_5=False)),
            ("c", Integer().none_of(0)),
            ("haspermission", Series(
              begin=Char("{")
                .note("note._selector.complex.haspermission.begin"),
              end=Char("}")
                .note("note._selector.complex.haspermission.end"),
              seperator=Char(",")
                .note("note._selector.complex.haspermission.seperator"),
              content=self._HasPermissionArg(),
              empty_ok=False
            ), {"version": version_ge((1, 19, 80))}),
        ):
            _handle(*args)

class Selector(CompressedNode):
    def __init__(self, note: Optional[str] = None):
        if note is None:
            self.__note_name = "note._selector.player_name"
            self.__note_filter = "note._selector.complex.root"
        else:
            self.__note_name = self.__note_filter = note
        super().__init__()

    def _tree(self):
        (self
          .branch(
            String()
              .font(Font.target)
              .note(self.__note_name)
              .branch(self.end)
          )
          .branch(
            Char("@")
              .font(Font.target)
              .note(self.__note_filter)
              .branch(
                NotedEnumerate("a", "e", "r", "p", "s", "initiator",
                               note_template="note._selector.complex.vars.%s")
                  .font(Font.target)
                  .branch(
                    Series(
                      begin=Char("[")
                        .note("note._selector.complex.begin"),
                      end=Char("]")
                        .note("note._selector.complex.end"),
                      seperator=Char(",")
                        .note("note._selector.complex.seperator"),
                      content=SelectorArg(),
                      empty_ok=False
                    )
                      .branch(self.end)
                  )
                  .branch(self.end),
                is_close=True
              )
          )
        )

class Wildcard(CompressedNode):
    def __init__(self, node: Node, wildcard_note: str = "note._wildcard"):
        self.node = node
        self.wildcard_note = wildcard_note
        super().__init__()

    def _tree(self):
        (self
          .branch(
            self.node
              .branch(self.end)
          )
          .branch(
            Char("*")
              .note(self.wildcard_note)
              .font(Font.meta)
              .branch(self.end)
          )
        )

class Swizzle(Node):
    default_font = Font.keyword

    def _parse(self, reader: Reader):
        word = reader.read_word()
        wordset = set(word)
        if not (word
                and wordset.issubset({"x", "y", "z"})
                and len(wordset) == len(word)):
            raise ExpectationFailure("swizzle")
        return wordset

    def _suggest(self):
        return [
            Suggestion(
                name="autocomp.swizzle", writes=word, note=None,
                name_kwds={"swizzle": word},
                match_rule=str_find_rule(word)
            )
            for word in ("x", "y", "z", "xy", "yz", "xz", "xyz")
        ]

class ScoreSpec(CompressedNode):
    def __init__(self, wildcard_ok=True):
        self.__wildcard = wildcard_ok
        super().__init__()

    def _tree(self):
        sel = Selector()
        if self.__wildcard:
            sel = Wildcard(sel)
        (self
          .branch(
            sel
              .branch(
                String()
                  .font(Font.scoreboard)
                  .note("note._scoreboard")
                  .branch(self.end)
              )
          )
        )

class _RawtextTranslate(SubparsingNode):
    RE_SUBSTITUTION = re.compile(r"%%[s1-9]")

    def _parse(self, marker: "Marker"):
        # Parsing
        reader = marker.reader
        pos_begin = reader.get_location()
        string = reader.read_until_eol()
        pos_end = reader.get_location()
        # Marking
        marker.font_marks.append(FontMark(
            pos_begin, pos_end, Font.string
        ))
        for m in re.finditer(self.RE_SUBSTITUTION, string):
            span = m.span()
            marker.font_marks.append(FontMark(
                pos_begin.offset(span[0]), pos_begin.offset(span[1]),
                Font.meta
            ))
        marker.ac_marks.append(AutoCompletingMark.from_node(
            pos_begin, pos_end, self, marker.version
        ))

class _JsonString(SubparsingNode):
    argument_end = False

    ESCAPES = {
        "t": "\t", "n": "\n",
        "b": "\b", "f": "\f", "r": "\r",
        '"': '"', "\\": "\\"
    }
    HEX = frozenset("0123456789abcdefABCDEF")

    def __init__(self, definition: dict = {},
                       path: List[str] = [],
                       name: Union[str, None] = None,
                       ac_node: Optional[Node] = None):
        super().__init__()
        self.__difinition = definition
        self.__path = path
        self.__name = name
        self.__tree = None
        self.__done_tree = False
        if ac_node is None:
            self.__ac_node = self
        else:
            self.__ac_node = ac_node

    def __get_tree(self) -> Union[None, Node]:
        """Get the tree that parses the content in the string."""
        if self.__done_tree:
            return self.__tree
        if self.__name is None:
            # When this string is a JSON key in a JSON object
            o = dict_getter(self.__difinition, self.__path)
            if o:
                keys = set()
                for k in o:
                    if k.startswith("!"):
                        i = k.rfind("@")
                        if i == -1:
                            continue
                        k = k[1:i]
                        keys.add(k)
                if keys:
                    self.__tree = NotedEnumerate(*keys,
                        note_template="note._json.{}._keys.%s"
                                      .format(".".join(self.__path)))
                else:
                    self.__tree = None
        else:
            # When this string is a JSON value
            lib = dict_getter(self.__difinition,
                self.__path, ["%s@string" % self.__name, "#lib"])
            if lib is None:
                self.__tree = None
            elif lib == "wildcard_selector":
                self.__tree = Wildcard(Selector())
            elif lib == "lock_mode":
                self.__tree = NotedEnumerate(
                    "lock_in_inventory", "lock_in_slot",
                    note_template="note._json._libs.lock.%s"
                )
            elif lib == "block":
                self.__tree = IdBlock()
            elif lib == "scoreboard":
                self.__tree = BareText(empty_ok=False).font(Font.scoreboard)
            elif lib == "translate":
                self.__tree = _RawtextTranslate()
            else:
                raise ValueError("Invalid lib %r" % lib)
        return self.__tree

    def _parse(self, marker: Marker):
        reader = marker.reader
        # Parsing
        pos_begin = reader.get_location()
        if reader.next() != '"':
            raise ExpectationFailure("quoted_str")
        chars = []
        col_map = []
        i = 0
        while True:
            char = reader.next()
            if char == '"' or reader.is_line_end(char):
                col_map.append(i)
                break
            if char == "\\":
                char2 = reader.next()
                esc = self.ESCAPES.get(char2)
                if esc:
                    chars.append(esc)
                    col_map.append(i)
                    col_map.append(i)
                    i += 1
                    continue
                if char2 == "u":
                    hex_ = []
                    for _ in range(4):
                        c = reader.next()
                        if c not in self.HEX:
                            raise ArgParseFailure(
                                "error.syntax.json_str_u_escape")
                        hex_.append(c)
                    for _ in range(6):
                        col_map.append(i)
                    chars.append(chr(int("".join(hex_), base=16)))
                    i += 1
                    continue
                chars.append("\\")
                col_map.append(i)
                if char2 is not None:
                    chars.append(char2)
                    col_map.append(i + 1)
                    i += 1
                i += 1
                continue
            chars.append(char)
            col_map.append(i)
            i += 1
        if char != '"':
            raise ArgParseFailure("error.syntax.unclosed_str")
        pos_end = reader.get_location()
        string = "".join(chars)
        # Marking
        p1, p2 = pos_begin.offset(1), pos_end.offset(-1)
        marker.font_marks.append(FontMark(pos_begin, p1, Font.meta))
        marker.font_marks.append(FontMark(p2, pos_end, Font.meta))
        marker.ac_marks.append(AutoCompletingMark.from_node(
            p2, pos_end, self.__ac_node, version=marker.version
        ))  # Leave body part of string for sub-node
        tree = self.__get_tree()
        failed = tree is None
        if tree is not None:
            def _get_loc(m):
                idx1 = col_map.index(m.begin.column - 1)
                idx2 = col_map.index(m.end.column - 1)
                return (p1.offset(idx1), p1.offset(idx2))
            submarker = Marker(Reader(string), version=marker.version)
            tree2 = Empty().branch(tree.finish(EOL))
            tree2.freeze()
            try:
                tree2.parse(submarker)
                submarker.trigger_checkers()
            except BaseError:
                failed = True
            else:
                for mark in submarker.font_marks:
                    marker.font_marks.append(
                        FontMark(*_get_loc(mark), mark.font)
                    )
                for mark in submarker.ac_marks:
                    marker.ac_marks.append(
                        AutoCompletingMark(*_get_loc(mark), mark.get_unit)
                    )
        if failed:
            marker.font_marks.append(FontMark(p1, p2, Font.string))
        return string

    def _suggest(self):
        tree = self.__get_tree()
        if tree is None:
            return []
        res = tree._suggest()
        def _ref(s: "HandledSuggestion"):
            s.name = json.dumps(s.name)
            s.writes = json.dumps(s.writes)
            s.match_rule = str_find_rule(s.writes)
        for s in res:
            s.set_refactor(_ref)
        return res

class _JsonKeyValPair(CompressedNode):
    def __init__(self, definition: dict, path: List[str]):
        self.__definition = definition
        self.__path = path
        super().__init__()

    def _tree(self):
        __key = None
        def _set_key(v: str):
            nonlocal __key
            __key = v
        def _get_key():
            assert __key is not None
            return "!" + __key
        (self
          .branch(
            ResultTracked(
              _JsonString(self.__definition, self.__path), _set_key
            )
              .branch(
                Char(":")
                  .branch(
                    Json(self.__definition, _get_key, self.__path)
                      .branch(self.end)
                  )
              )
          )
        )

class Json(SubparsingNode):
    WHITESPACES = frozenset(" \t\r\n")

    def __init__(self, definition: dict = {},
                       name: Union[str, Callable[[], str]] = "",
                       path: List[str] = []):
        super().__init__()
        self.__difinition = definition
        self.__path = path
        if isinstance(name, str):
            self.__get_name = lambda: name
        else:
            self.__get_name = name

    def __skip_spaces(self):
        while self.reader.peek() in self.WHITESPACES:
            self.reader.next()

    def __parse_node(self, node: Node):
        tree = Empty().branch(node.finish())
        tree.freeze()
        tree.parse(self.marker)
        pos = self.reader.get_location()
        # XXX
        if not isinstance(node, SubparsingNode):
            orig = self.marker.ac_marks[-1]
            self.marker.ac_marks[-1] = AutoCompletingMark.from_node(
                orig.begin, orig.end, self, self.marker.version
            )
        else:
            self.marker.ac_marks.append(AutoCompletingMark.from_node(
                pos.offset(-1), pos, self, self.marker.version
            ))

    def __float(self):
        # Exponent is deprecated in Minecraft
        # and `0` prefix is allowed
        self.__parse_node(Float())

    def __string(self) -> str:
        self.__parse_node(_JsonString(
            self.__difinition, self.__path, self.__name, ac_node=self
        ))

    def __object(self):
        p = self.__path.copy()
        p.append("%s@object" % self.__name)
        o = dict_getter(self.__difinition, p, ["#redirect"])
        path = o if o is not None else p
        tree = Series(
          begin=Char("{"),
          end=Char("}"),
          seperator=Char(","),
          content=_JsonKeyValPair(self.__difinition, path),
          empty_ok=True
        )
        self.__parse_node(tree)

    def __array(self):
        p = self.__path.copy()
        p.append("%s@array" % self.__name)
        o = dict_getter(self.__difinition, p, ["#redirect"])
        path = o if o is not None else p
        tree = Series(
          begin=Char("["),
          end=Char("]"),
          seperator=Char(","),
          content=Json(self.__difinition, "#value", path),
          empty_ok=True
        )
        self.__parse_node(tree)

    def __boolean(self):
        self.__parse_node(Boolean())

    def _parse(self, marker: "Marker"):
        self.marker = marker
        self.reader = marker.reader
        self.__name = self.__get_name()
        self.__skip_spaces()
        char = self.reader.peek()
        if char in DIGITS or char == "-":
            self.__float()
        elif char == '"':
            self.__string()
        elif char == "{":
            self.__object()
        elif char == "[":
            self.__array()
        elif char == "t" or char == "f":
            self.__boolean()
        else:
            raise ExpectationFailure("json")

    def _suggest(self):
        o = dict_getter(self.__difinition, self.__path)
        types = []
        if o:
            for k in o:
                i = k.rfind("@")
                if i == -1:
                    continue
                if k[:i] == self.__name:
                    types.append(k[i+1:])
        res = [
            Suggestion(
                name="autocomp.char", name_kwds={"char": "{"},
                writes="{", match_rule=char_rule("{"),
                note="note._json._suggested" if "object" in types else None),
            Suggestion(
                name="autocomp.char", name_kwds={"char": "["},
                writes="[", match_rule=char_rule("["),
                note="note._json._suggested" if "array" in types else None),
            Suggestion(
                name="autocomp.true", writes="true",
                match_rule=str_find_rule("true", RULEW_OTHER),
                note="note._json._suggested" if "boolean" in types else None),
            Suggestion(
                name="autocomp.false", writes="false",
                match_rule=str_find_rule("false", RULEW_OTHER),
                note="note._json._suggested" if "boolean" in types else None),
            Suggestion(
                name="autocomp.quoted_string", writes='"',
                match_rule=char_rule('"'),
                note="note._json._suggested" if "string" in types else None),
            # `null` is deprecated in Minecraft
            Suggestion(
                name="autocomp.float", writes="0.0",
                match_rule=char_check_rule(
                    lambda char: char in DIGITS or char == "-"
                                 or char == "."
                                 # JSON does not allow + prefix
                ),
                note="note._json._suggested" if "number" in types else None)
        ]
        res.sort(key=lambda s: s.note is None)
        return res

def ItemComponents():
    return Json(
        {
            "$item_components@object": {
                "!minecraft:can_place_on@object": {
                    "!blocks@array": {
                        "#value@string": {
                            "#lib": "block"
                        }
                    }
                },
                "!minecraft:can_destroy@object": {
                    "!blocks@array": {
                        "#value@string": {
                            "#lib": "block"
                        }
                    }
                },
                "!minecraft:item_lock@object": {
                    "!mode@string": {
                        "#lib": "lock_mode"
                    }
                },
                "!minecraft:keep_on_death@object": {}
            }
        },
        name="$item_components"
    )

def RawText():
    return Json(
    {
        "$rawtext@object": {
            "!rawtext@array": {
                "#value@object": {
                    "!text@string": {},
                    "!translate@string": {
                        "#lib": "translate"
                    },
                    "!with@array": {
                        "#value@string": {}
                    },
                    "!with@object": {
                        "#redirect": ["$rawtext@object"]
                    },
                    "!score@object": {
                        "!objective@string": {
                            "#lib": "scoreboard"
                        },
                        "!name@string": {
                            "#lib": "wildcard_selector"
                        }
                    },
                    "!selector@string": {
                        "#lib": "wildcard_selector"
                    }
                }
            }
        }
    },
        name="$rawtext"
    )

class EOL(Finish):
    # End Of Line
    argument_end = False

    def _parse(self, reader: Reader):
        if reader.is_line_end(reader.peek()):
            reader.next()
        else:
            raise ArgParseFailure("error.syntax.too_many_args")

    @staticmethod
    def _rule(s: str):
        if not s:
            return RULEW_OTHER
        else:
            return RULEW_FAILED

    def _suggest(self):
        return [Suggestion(
            name="autocomp.eol", writes="\n",
            match_rule=self._rule
        )]

def CommandName(name: str, *alias: str):
    if not alias:
        n = Keyword(name)
    else:
        n = Enumerate(name, *alias)
    return (n
      .font(Font.command)
      .note("note.%s.root" % name)
    )

def command():
    command_root = Empty()

    def _difficulty() -> Dict[str, str]:
        res: Dict[str, str] = {}
        for diff in ("peaceful", "easy", "normal", "hard"):
            res[diff] = "note.difficulty.diffs." + diff
        res["p"] = res["peaceful"]
        res["e"] = res["easy"]
        res["n"] = res["normal"]
        res["h"] = res["hard"]
        return res

    _enchant = (Empty()
      .branch(
        Integer()
          .note("note.enchant.level")
          .ranged(min=1)
          .finish(EOL)
      )
      .finish(EOL)
    )

    def _ExecuteSubcmd(word: str):
        return Keyword(word).note("note.execute.subcmds." + word)

    _execute = Empty()
    _execute_cond = (Empty()
      .branch(
        Keyword("block")
          .note("note.execute.tests.block")
          .branch(
            Pos3D()
              .branch(
                BlockSpec(bs_optional=_execute)
                  .branch(_execute)
                  .finish(EOL)
              )
          )
      )
      .branch(
        Keyword("blocks")
          .note("note.execute.tests.blocks.root")
          .branch(
            Pos3D().branch(Pos3D().branch(Pos3D()
              .branch(
                NotedEnumerate("all", "masked",
                    note_template="note.execute.tests.blocks.modes.%s")
                  .branch(_execute)
                  .finish(EOL)
              )
            ))
          )
      )
      .branch(
        Keyword("entity")
          .note("note.execute.tests.entity")
          .branch(
            Selector()
              .branch(_execute)
              .finish(EOL)
          )
      )
      .branch(
        Keyword("score")
          .note("note.execute.tests.score.root")
          .branch(
            ScoreSpec(wildcard_ok=False)
              .branch(
                Keyword("matches")
                  .note("note.execute.tests.score.matches")
                  .branch(
                    IntRange()
                      .branch(_execute)
                      .finish(EOL)
                  )
              )
              .branch(
                CharsEnumerate("=", "<=", ">=", "<", ">",
                    note_template="note.execute.tests.score.compare_ops.%s")
                  .branch(
                    ScoreSpec(wildcard_ok=False)
                      .branch(_execute)
                      .finish(EOL)
                  )
              )
          )
      )
    )

    (_execute
      .branch(
        _ExecuteSubcmd("align")
          .branch(
            Swizzle()
              .branch(_execute)
          )
      )
      .branch(
        _ExecuteSubcmd("anchored")
          .branch(
            NotedEnumerate("eyes", "feet",
                           note_template="note.execute.anchors.%s")
              .branch(_execute)
          )
      )
      .branch(
        _ExecuteSubcmd("as")
          .branch(
            Selector()
              .branch(_execute)
          )
      )
      .branch(
        _ExecuteSubcmd("at")
          .branch(
            Selector()
              .branch(_execute)
          )
      )
      .branch(
        _ExecuteSubcmd("facing")
          .branch(
            Pos3D()
              .branch(_execute)
          )
          .branch(
            Keyword("entity")
              .note("note.execute.entity_variant")
              .branch(
                Selector()
                  .branch(
                    NotedEnumerate("eyes", "feet",
                                   note_template="note.execute.anchors.%s")
                      .branch(_execute)
                  )
              )
          )
      )
      .branch(
        _ExecuteSubcmd("in")
          .branch(
            NotedEnumerate("overworld", "nether", "the_end",
                           note_template="note.execute.dims.%s")
              .branch(_execute)
          )
      )
      .branch(
        _ExecuteSubcmd("positioned")
          .branch(
            Pos3D()
              .branch(_execute)
          )
          .branch(
            Keyword("as")
              .note("note.execute.entity_variant")
              .branch(
                Selector()
                  .branch(_execute)
              )
          )
      )
      .branch(
        _ExecuteSubcmd("rotated")
          .branch(
            YawPitch()
              .branch(_execute)
          )
          .branch(
            Keyword("as")
              .note("note.execute.entity_variant")
              .branch(
                Selector()
                  .branch(_execute)
              )
          )
      )
      .branch(
        _ExecuteSubcmd("if")
          .branch(
            _execute_cond
          )
      )
      .branch(
        _ExecuteSubcmd("unless")
          .branch(
            _execute_cond
          )
      )
      .branch(
        _ExecuteSubcmd("run")
          .branch(
            command_root
          )
      )
    )

    _loot_tool = (Empty()
      .branch(
        NotedEnumerate("mainhand", "offhand",
                       note_template="note.loot.origin.tools.%s")
          .finish(EOL)
      )
      .branch(
        IdItem()
          .finish(EOL)
      )
    )
    _loot_origin = (Empty()
      .branch(
        Keyword("kill")
          .note("note.loot.origin.kill")
          .branch(
            Selector()
              .branch(_loot_tool)
              .finish(EOL)
          )
      )
      .branch(
        Keyword("loot")
          .note("note.loot.origin.loot")
          .branch(
            String()
              .note("note.loot.origin.loot_table")
              .branch(_loot_tool)
              .finish(EOL)
          )
      )
    )

    return (command_root
      .branch(
        CommandName("help", "?")
          .branch(
            Integer()
              .note("note.help.on.page")
              .finish(EOL)
          )
          .branch(
            Word()
              .note("note.help.on.command")
              .finish(EOL)
          )
          .branch(
            EOL()
              .note("note.help.on.page_1")
          )
      )
      .branch(
        CommandName("ability")
          .branch(
            Selector()
              .branch(
                NotedEnumerate("mayfly", "worldbuilder", "mute",
                               note_template="note.ability.abilities.%s")
                  .branch(
                    Boolean()
                      .note("note.ability.set")
                      .finish(EOL)
                  )
                  .branch(
                    EOL()
                      .note("note.ability.query.ability")
                  )
              )
              .branch(
                EOL()
                  .note("note.ability.query.unknown")
              )
          )
      )
      .branch(
        CommandName("alwaysday", "daylock")
          .branch(
            Boolean()
              .note("note.alwaysday.set")
              .finish(EOL)
          )
          .branch(
            EOL()
              .note("note.alwaysday.lock")
          )
      )
      .branch(
        CommandName("camerashake")
          .branch(
            Keyword("add")
              .note("note.camerashake.add.root")
              .branch(
                Selector()
                  .branch(
                    Float()
                      .note("note.camerashake.add.intensity")
                      .ranged(min=0, max=4)
                      .branch(
                        Float()
                          .note("note.camerashake.add.seconds")
                          .ranged(min=0)
                          .branch(
                            NotedEnumerate("positional", "rotational",
                                note_template="note.camerashake.add.types.%s")
                              .finish(EOL)
                          )
                          .finish(EOL)
                      )
                      .finish(EOL)
                  )
                  .finish(EOL)
              )
          )
          .branch(
            Keyword("stop")
              .note("note.camerashake.stop")
              .branch(
                Selector()
                  .finish(EOL)
              )
              .finish(EOL)
          )
      )
      .branch(
        CommandName("clear")
          .branch(
            Selector()
              .branch(
                IdItem()
                  .branch(
                    ItemData(is_test=True)
                      .branch(
                        Integer()
                          .note("note.clear.max_count")
                          .ranged(min=-1)
                          .finish(EOL)
                      )
                      .finish(EOL)
                  )
                  .finish(EOL)
              )
              .finish(EOL)
          )
          .finish(EOL)
      )
      .branch(
        CommandName("clearspawnpoint")
          .branch(
            Selector()
              .finish(EOL)
          )
          .finish(EOL)
      )
      .branch(
        CommandName("clone")
          .branch(
            Pos3D().branch(Pos3D().branch(Pos3D()
              .branch(
                NotedEnumerate("masked", "replace",
                               note_template="note.clone.masks.%s")
                  .branch(
                    NotedEnumerate("force", "move", "normal",
                                   note_template="note.clone.clones.%s")
                      .finish(EOL)
                  )
                  .finish(EOL)
              )
              .branch(
                Keyword("filtered")
                  .note("note.clone.filtered")
                  .branch(
                    NotedEnumerate("force", "move", "normal",
                                   note_template="note.clone.clones.%s")
                      .branch(
                        BlockSpec()
                          .finish(EOL)
                      )
                  )
              )
              .finish(EOL)
            ))
          )
      )
      .branch(
        CommandName("wsserver", "connect")
          .branch(
            Keyword("out")
              .note("note.wsserver.out")
              .finish(EOL)
          )
          .branch(
            BareText(empty_ok=False)
              .note("note.wsserver.address")
              .finish(EOL)
          )
      )
      .branch(
        CommandName("damage")
          .branch(
            Selector()
              .branch(
                Integer()
                  .note("note.damage.amount")
                  .branch(
                    IdDamageType()
                      .branch(
                        Keyword("entity")
                          .note("note.damage.damager")
                          .branch(
                            Selector()
                              .finish(EOL)
                          )
                      )
                      .finish(EOL)
                  )
                  .finish(EOL)
              )
          )
      )
      .branch(
        CommandName("deop")
          .branch(
            Selector()
              .finish(EOL)
          )
      )
      .branch(
        CommandName("dialogue")
          .branch(
            Keyword("open")
              .note("note.dialogue.modes.open")
              .branch(
                Selector("note.dialogue.npc")
                  .branch(
                    Selector("note.dialogue.player")
                      .branch(
                        String()
                          .note("note.dialogue.scene")
                          .finish(EOL)
                      )
                      .finish(EOL)
                  )
              )
          )
          .branch(
            Keyword("change")
              .note("note.dialogue.modes.change")
              .branch(
                Selector("note.dialogue.npc")
                  .branch(
                    String()
                      .note("note.dialogue.scene")
                      .branch(
                        Selector("note.dialogue.player")
                          .finish(EOL)
                      )
                      .finish(EOL)
                  )
              )
          )
      )
      .branch(
        CommandName("difficulty")
          .branch(
            Integer()
              .one_of(0, 1, 2, 3)
              .font(Font.keyword)
              .note("note.difficulty.int")
              .finish(EOL)
          )
          .branch(
            Enumerate("peaceful", "easy", "normal", "hard",
                      "p", "e", "n", "h",
                      note_table=_difficulty())
              .finish(EOL)
          )
      )
      .branch(
        CommandName("effect")
          .branch(
            Selector()
              .branch(
                Keyword("clear")
                  .note("note.effect.clear")
                  .finish(EOL)
              )
              .branch(
                IdEffect()
                  .branch(
                    Integer()
                      .note("note.effect.seconds")
                      .ranged(min=0)
                      .branch(
                        Integer()
                          .note("note.effect.amplifier")
                          .ranged(min=0, max=255)
                          .branch(
                            Boolean()
                              .note("note.effect.hide_particles")
                              .finish(EOL)
                          )
                          .finish(EOL)
                      )
                      .finish(EOL)
                  )
                  .finish(EOL)
              )
          )
      )
      .branch(
        CommandName("enchant")
          .branch(
            Selector()
              .branch(
                Integer()
                  .note("note.enchant.int_id")
                  .branch(_enchant)
              )
              .branch(
                IdEnchantment()
                  .branch(_enchant)
              )
          )
      )
      .branch(
        CommandName("event")
          .branch(
            Keyword("entity")
              .branch(
                Selector()
                  .branch(
                    IdEntityEvent()
                      .finish(EOL)
                  )
              )
          )
      )
      .branch(
        CommandName("execute")
          .branch(
            _execute,
            version=version_ge((1, 19, 50))
          )
          .branch(
            Selector()
              .branch(
                Pos3D()
                  .branch(
                    command_root
                  )
                  .branch(
                    Keyword("detect")
                      .note("note.execute.old.detect")
                      .branch(
                        Pos3D()
                          .branch(
                            IdBlock()
                              .branch(
                                Integer()
                                  .note("note._block_data")
                                  .branch(
                                    command_root
                                  )
                              )
                          )
                      )
                  )
              ),
            version=version_lt((1, 19, 50))
          )
      )
      .branch(
        CommandName("fill")
          .branch(
            Pos3D()
              .branch(
                Pos3D()
                  .branch(
                    BlockSpec(bs_optional=EOL())
                      .branch(
                        Keyword("replace")
                          .note("note.fill.modes.replace.root")
                          .branch(
                            BlockSpec(bs_optional=EOL())
                              .finish(EOL)
                          )
                          .branch(
                            EOL()
                              .note("note.fill.modes.replace.all")
                          )
                      )
                      .branch(
                        NotedEnumerate("destroy", "hollow", "keep", "outline",
                                       note_template="note.fill.modes.%s")
                          .finish(EOL)
                      )
                      .finish(EOL)
                  )
              )
          )
      )
      .branch(
        CommandName("fog")
          .branch(
            Selector()
              .branch(
                Keyword("push")
                  .note("note.fog.modes.push")
                  .branch(
                    IdFog()
                      .branch(
                        String()
                          .note("note.fog.user_provided_name")
                          .finish(EOL)
                      )
                  )
              )
              .branch(
                NotedEnumerate("pop", "remove",
                               note_template="note.fog.modes.%s")
                  .branch(
                    String()
                      .note("note.fog.user_provided_name")
                      .finish(EOL)
                  )
              )
          )
      )
      .branch(
        CommandName("function")
          .branch(
            BareText(empty_ok=False)
              .note("note.function.path")
              .finish(EOL)
          )
      )
      .branch(
        CommandName("gamemode")
          .branch(
            GameMode(allow_5=True)
              .finish(EOL)
          )
      )
      .branch(
        CommandName("gamerule")
          .branch(
            GameRule()
              .branch(
                Integer()
                  .note("note.gamerule.value")
                  .finish(EOL)
              )
              .branch(
                Boolean()
                  .note("note.gamerule.value")
                  .finish(EOL)
              )
              .branch(
                EOL()
                  .note("note.gamerule.query")
              )
          )
      )
      .branch(
        CommandName("give")
          .branch(
            Selector()
              .branch(
                IdItem()
                  .branch(
                    Integer()
                      .ranged(min=1, max=32767)
                      .note("note.give.amount")
                      .branch(
                        ItemData(is_test=False)
                          .branch(
                            ItemComponents()
                              .finish(EOL)
                          )
                          .finish(EOL)
                      )
                      .finish(EOL)
                  )
                  .finish(EOL)
              )
          )
      )
      .branch(
        CommandName("immutableworld")
          .branch(
            Boolean()
              .note("note.immutableworld.set")
              .finish(EOL)
          )
          .branch(
            EOL()
              .note("note.immutableworld.query")
          )
      )
      .branch(
        CommandName("inputpermission")
          .branch(
            Keyword("query")
              .note("note.inputpermission.query.root")
              .branch(
                Selector()
                  .branch(
                    IdPermission()
                      .branch(
                        PermissionState(
                          note="note.inputpermission.query.equal"
                        )
                          .finish(EOL)
                      )
                      .branch(
                        EOL()
                          .note("note.inputpermission.query.normal")
                      )
                  )
              )
          )
          .branch(
            Keyword("set")
              .note("note.inputpermission.set")
              .branch(
                Selector()
                  .branch(
                    IdPermission()
                      .branch(
                        PermissionState()
                          .finish(EOL)
                      )
                  )
              )
          ),
        version=version_ge((1, 19, 80))
      )
      .branch(
        CommandName("kick")
          .branch(
            Selector("note.kick.target")
              .branch(
                BareText(empty_ok=True)
                  .note("note.kick.reason")
                  .finish(EOL)
              )
              .finish(EOL)  # For autocompletion
          )
      )
      .branch(
        CommandName("kill")
          .branch(
            Selector()
              .finish(EOL)
          )
          .finish(EOL)
      )
      .branch(
        CommandName("list")
          .finish(EOL)
      )
      .branch(
        CommandName("locate")
          .branch(
            Keyword("biome")
              .note("note.locate.biome")
              .branch(
                IdBiome()
                  .finish(EOL)
              ),
            version=version_ge((1, 19, 10))
          )
          .branch(
            Keyword("structure")
              .note("note.locate.structure.root")
              .branch(
                IdStructure()
                  .branch(
                    Boolean()
                      .note("note.locate.structure.new_chunks")
                      .finish(EOL)
                  )
                  .finish(EOL)
              ),
            version=version_ge((1, 19, 10))
          )
          .branch(
            IdStructure()
              .branch(
                Boolean()
                  .note("note.locate.structure.new_chunks")
                  .finish(EOL)
              )
              .finish(EOL),
            version=version_lt((1, 19, 30))
          )
      )
      .branch(
        CommandName("loot")
          .branch(
            Keyword("give")
              .note("note.loot.give")
              .branch(
                Selector()
                  .branch(_loot_origin)
              )
          )
          .branch(
            Keyword("insert")
              .note("note.loot.insert")
              .branch(
                Pos3D()
                  .branch(_loot_origin)
              )
          )
          .branch(
            Keyword("spawn")
              .note("note.loot.spawn")
              .branch(
                Pos3D()
                  .branch(_loot_origin)
              )
          )
          .branch(
            Keyword("replace")
              .note("note.loot.replace.root")
              .branch(
                Keyword("entity")
                  .note("note.loot.replace.entity")
                  .branch(
                    Selector()
                      .branch(
                        EntitySlot()
                          .branch(
                            Integer()
                              .note("note.loop.replace.slot_count")
                              .branch(_loot_origin)
                          )
                          .branch(_loot_origin)
                      )
                  )
              )
              .branch(
                Keyword("block")
                  .note("note.loot.replace.block")
                  .branch(
                    Pos3D()
                      .branch(
                        BlockSlot()
                          .branch(
                            Integer()
                              .note("note.loop.replace.slot_count")
                              .branch(_loot_origin)
                          )
                          .branch(_loot_origin)
                      )
                  ),
                version=version_ge((1, 19, 40))
              ),
            version=version_ge((1, 19, 0))
          )
      )
      .branch(
        CommandName("tellraw")
          .branch(
            Selector()
              .branch(
                RawText()
                  .finish(EOL)
              )
          )
      )
    )

def mcfuncline():
    return (Empty()
      .branch(
        command()
      )
      .branch(
        Char("#")
          .font(Font.comment)
          .note("note._comment")
          .branch(
            BareText(empty_ok=True)
              .font(Font.comment)
              .finish(EOL)
          )
      )
      .branch(
        EOL()
          .note("note._empty_line")
      )
    )