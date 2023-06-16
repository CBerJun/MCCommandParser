"""Simple timing program for `mccmdhl2`."""
import timeit

r = timeit.timeit(
    stmt="import mccmdhl2\nmccmdhl2.get_default_tree()",
    number=1
)
print("Setup:", r)

CMD = "ability @p[tag=,scores={a=..1}] mayfly true"

r = timeit.timeit(
    stmt="""
mccmdhl2.MCCmdParser(%r).parse_line()
""" % CMD,
    setup="""
import mccmdhl2
""",
number=100)
print("100 Seperate Lines:", r)

NUM = 100
r = timeit.timeit(
    stmt="""
parser.parse_line()
""",
    setup="""
import mccmdhl2
parser = mccmdhl2.MCCmdParser((%r + "\\n") * %d)
""" % (CMD, NUM),
    number=NUM
)
print("%d Lines:" % NUM, r)
