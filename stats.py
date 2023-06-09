"""Simple performance analyzer for `mccmdhl2`."""
import cProfile
import os

CMD = "ability @p[tag=,scores={a=..1}] mayfly true"

def test_setup():
    global mccmdhl2
    import mccmdhl2
    mccmdhl2.get_default_tree()

def test_parse_sep(cmd: str, num: int = 100):
    for _ in range(num):
        mccmdhl2.MCCmdParser(cmd).parse_line()

def test_parse(cmd: str, num: int = 100):
    parser = mccmdhl2.MCCmdParser("\n".join(cmd for _ in range(num)))
    while not parser.is_finish():
        parser.parse_line()

def main():
    if not os.path.exists("./stats"):
        os.mkdir("./stats")
    cProfile.run("test_setup()", "stats/setup.stats")
    cProfile.run("test_parse_sep(CMD)", "stats/parse_sep.stats")
    cProfile.run("test_parse(CMD)", "stats/parse.stats")

if __name__ == "__main__":
    main()
