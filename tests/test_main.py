import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from main import Pr, load_prs, page_data, store  # noqa: E402

REPO = "ykjit/ykmruby"


def pr(n: int, data: str) -> Pr:
    return Pr(number=n, title=f"PR {n}", date=f"2026-01-0{n}", data_toml="[data]\n" + data)


def zipped(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()


def meta(n: int, **extra: object) -> dict[str, object]:
    return dict(pr=n, date=f"2026-01-0{n}", title=f"PR {n}", **extra)


class Main(unittest.TestCase):
    def test_page_data(self) -> None:
        prs = [
            pr(1, '"Towers/mruby/600" = [100.0, 110.0, 120.0]\n"Richards/mruby/100" = [200.0]'),
            pr(2, '"Towers/mruby/600" = [60.0]\n"Json/mruby/100" = [300.0]'),
            pr(3, '"Towers/mruby/600" = [55.0]\n"Richards/mruby/100" = [330.0]\n'
                  '"Json/mruby/data/in.json" = [280.0]'),
        ]
        # PR 2 misses Richards, so it has no geomean; Json is not in the baseline, so it is
        # charted but left out of every geomean.
        self.assertEqual(page_data(REPO, prs), dict(
            repo=REPO,
            base=1,
            prs=[meta(1, geomean=1.0), meta(2, geomean=None), meta(3, geomean=0.908)],
            benchmarks=[
                dict(name="Json", points=[meta(2, ms=300), meta(3, ms=280)]),
                dict(name="Richards", points=[meta(1, ms=200), meta(3, ms=330)]),
                dict(name="Towers", points=[meta(1, ms=110), meta(2, ms=60), meta(3, ms=55)]),
            ],
        ))
        self.assertEqual(page_data(REPO, []), dict(repo=REPO, base=None, prs=[], benchmarks=[]))

        with self.assertRaisesRegex(AssertionError, "Towers/mruby/1200") as cm:
            page_data(REPO, [pr(1, '"Towers/mruby/600" = [1.0]\n"Towers/mruby/1200" = [2.0]')])
        self.assertEqual(cm.exception.__notes__, ["in data.toml from PR #1"])

    def test_store(self) -> None:
        results = Path(self.enterContext(tempfile.TemporaryDirectory()))
        data = b'[data]\n"Towers/mruby/600" = [0.5]\n'
        files = "https://github.com/user-attachments/files"
        body = f"Faster.\n[haste.zip]({files}/1/haste.zip)"
        merged = dict(number=7, title="Faster towers", merged_at="2026-01-05T08:00:00Z",
                      merge_commit_sha="abc", body=body)
        open_pr = dict(merged, number=8, merge_commit_sha="def")
        pulls = f"https://api.github.com/repos/{REPO}/commits/{{}}/pulls"
        urls = {
            f"{files}/1/haste.zip": zipped({"data.toml": data, "extra.toml": b"[extra]\n"}),
            f"{files}/2/haste.zip": zipped({"extra.toml": b"[extra]\n"}),
            pulls.format("abc"): json.dumps([open_pr, merged]),
            pulls.format("nopr"): json.dumps([open_pr]),
            pulls.format("noresults"):
                json.dumps([dict(merged, merge_commit_sha="noresults", body="No results.")]),
            pulls.format("nodata"): json.dumps([dict(merged, merge_commit_sha="nodata",
                                                     body=f"[haste.zip]({files}/2/haste.zip)")]),
        }
        self.assertEqual(store(REPO, "abc", results, urls.__getitem__), 7)
        self.assertEqual(load_prs(results), [Pr(number=7, title="Faster towers",
                                                date="2026-01-05T08:00:00Z",
                                                data_toml=data.decode())])
        self.assertEqual((results / "7/extra.toml").read_text(), "[extra]\n")
        self.assertIsNone(store(REPO, "nopr", results, urls.__getitem__))
        self.assertIsNone(store(REPO, "noresults", results, urls.__getitem__))
        self.assertIsNone(store(REPO, "nodata", results, urls.__getitem__))
        self.assertEqual(load_prs(results / "nowhere"), [])


if __name__ == "__main__":
    unittest.main()
