import json
import re
import subprocess
import shutil

import pytest

from skycast import analysis as A
from skycast.cities import FRONTEND, find_city, load_cities


def test_cities_load_from_frontend():
    cities = load_cities()
    assert len(cities) >= 15
    for c in cities:
        assert len(c["hi"]) == len(c["lo"]) == len(c["rain"]) == 12
        assert len(c["places"]) >= 6
    assert find_city("Kolkata")["id"] == "kolkata"
    assert find_city("new york")["id"] == "newyork"
    assert find_city("Paris, France")["id"] == "paris"
    assert find_city("Calcutta")["id"] == "kolkata"
    assert find_city("Lisbon") is None


def test_known_best_seasons():
    def best(cid):
        c = find_city(cid)
        return A.analyse(c["hi"], c["lo"], c["rain"], c["lat"])["best"]
    assert set(best("kolkata")) >= {0, 11}          # winter
    assert 5 not in best("mumbai")                   # not the June monsoon
    assert set(best("london")) >= {5, 6, 7}          # summer
    assert set(best("dubai")) >= {0, 1, 11}          # winter
    assert 0 not in best("manali")                   # not snowbound January


def test_seasons():
    c = find_city("sydney")
    seasons = A.analyse(c["hi"], c["lo"], c["rain"], c["lat"])["seasons"]
    assert seasons[6] == "winter" and seasons[0] == "summer"
    k = find_city("kolkata")
    s = A.analyse(k["hi"], k["lo"], k["rain"], k["lat"])["seasons"]
    assert s[6] == "rainy" and s[4] == "hot"


def test_range_text():
    assert A.range_text([10, 11, 0, 1]) == "Nov – Feb"
    assert A.range_text([3]) == "April"
    assert A.range_text(list(range(12))) == "All year"
    assert A.range_text([0, 1, 5]) == "Jan – Feb and June"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_python_rules_match_frontend_js():
    """The page's JS analyse() and the Python one must agree for every built-in city."""
    html = FRONTEND.read_text(encoding="utf-8")
    js = re.search(r"/\* ---------- climate rules.*?(?=function rainWords)", html, re.S).group(0)
    cities = load_cities()
    script = "const round = Math.round;\n" + js + f"\nconsole.log(JSON.stringify({json.dumps(cities)}.map(c => analyse(c))));"
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    for c, js_res in zip(cities, out):
        py = A.analyse(c["hi"], c["lo"], c["rain"], c["lat"])
        assert py["seasons"] == js_res["seasons"], c["id"]
        assert py["best"] == js_res["best"], c["id"]
        assert py["ratings"] == js_res["ratings"], c["id"]
