# The Minecraft command parser
This project is a parser for Minecraft Bedrock command, which supports:
 * syntax highlighting
 * error reporting
 * auto-completing with:
   - hints for every branch that explain the usages
   - ID hints (e.g. item ID and entity ID)
   - localization support (i.e. hint in different languages)
 * different versions of command system (from `1.19.0` to `1.20.10`!)

These almost make an IDE for command!
Use Python (3.5+) to run `main.py` and try the "IDE" we make.

## Flexible interface
This project uses a *very* flexible algorithm to make it easy to create
syntax rules. Take this syntax as an example:
```
foo spam <bar: int> [ham: bool]
foo spam <bar: int>L <victim: target>
foo eggs <honey|chocolate|boston_cream> [store: pos]
```

The parsing tree will be like:
```python
from mccmdhl2 import *
from mccmdhl2.nodes import *

tree = (Keyword("foo")  # A literal word "foo"
  .branch(Keyword("spam")
    .branch(Integer()  # An integer
      .branch(Boolean()
        .finish(EOL)  # End of line
      )
      .branch(Char("L")  # A character "L"
        .branch(Selector()
          .finish(EOL)
        ),
        is_close=True  # No space between integer and "L"
      )
      .finish(EOL)  # The "ham: bool" is optional
    )
  )
  .branch(Keyword("eggs")  # The other "eggs" branch
    .branch(Enumerate(
      "honey", "chocolate", "boston_cream"
    )  # One of the 3 choices
      .branch(Pos3D()  # Position
        .finish(EOL)
      )
      .finish(EOL)
    )
  )
)
```

Then use the tree to parse a source:
```python
test_src = """\
foo eggs boston_cream 10.2 ~-1~.5
foo eggs honey
foo spam 1 true
foo spam 3L @p[c=0, scores={money=5..}]
foo eggs vanilla_dip"""  # Last 2 lines have mistakes
parser = MCCmdParser(test_src, tree)
while not parser.is_finish():
    try:
        parser.parse_line()
    except BaseError as err:
        print("Error: %s" % parser.resolve_error(err))

# Highlight information
print("===== Highlighting =====")
for mark in parser.get_font_marks():
    print(mark)
```
Output:
```
Error: 4:18~4:19: Number can't be 0
Error: 5:9: Expect one of ('honey', 'chocolate', 'boston_cream')
===== Highlighting =====
<FontMark <Ln 1 Col 1>~<Ln 1 Col 4> keyword>
<FontMark <Ln 1 Col 5>~<Ln 1 Col 9> keyword>
<FontMark <Ln 1 Col 10>~<Ln 1 Col 22> keyword>
<FontMark <Ln 1 Col 23>~<Ln 1 Col 27> position>
...
```

To let it adapt to the auto-completing system (with the hint for every
branch), check out the `.note` method we call in `mccmdhl2/nodes.py` and
the translation system (`mccmdhl2/translator.py` and
`mccmdhl2/res/translation.json`).

## Why `mccmdhl2`?
Why is the package named `mccmdhl2`?

`mc` is the short name of Minecraft.
`cmd` is the short form of command.
`hl` means highlighter.
`mccmdhl` is actually the package name of my
[old project](https://www.github.com/CBerJun/MCCmdHighlighter)
which is also a command parser.
It used a different algorithm and this project is here to replace that one.
Therefore, we add a `2` to indicate that this is a completely re-written one.
