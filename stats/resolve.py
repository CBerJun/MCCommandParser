"""Resolve the stats generated in this directory."""
import pstats
import os
import sys
try:
    from pstats import SortKey
except ImportError:
    CRITERIA = "cumtime"
else:
    CRITERIA = SortKey.CUMTIME

DIR = os.path.dirname(os.path.realpath(__file__))
_, THIS = os.path.split(__file__)

for fn in os.listdir(DIR):
    if fn == THIS:
        continue
    print("\n========== %s ==========" % fn)
    try:
        st = pstats.Stats(os.path.join(DIR, fn))
    except Exception:
        print("error when resolving: %s: %s" % sys.exc_info()[:2])
        continue
    st.sort_stats(CRITERIA).print_stats(10)
