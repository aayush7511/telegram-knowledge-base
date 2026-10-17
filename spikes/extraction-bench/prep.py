"""Build data/items.json: 5 Re-DocRED test docs + the first 10 sessions of HaluMem-Medium user 0,
each with its gold facts as plain sentences."""
import json
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
N_DOCS, N_SESSIONS = 5, 10


def wikidata_labels(pids: list[str]) -> dict[str, str]:
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbgetentities", "ids": "|".join(pids), "props": "labels", "languages": "en", "format": "json"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "kb-extraction-bench/0.1"})
    ents = json.load(urllib.request.urlopen(req, timeout=30))["entities"]
    return {p: ents[p]["labels"]["en"]["value"] for p in pids}


def redocred() -> list[dict]:
    docs = json.load(open(DATA / "redocred_test.json"))[:N_DOCS]
    labels = wikidata_labels(sorted({l["r"] for d in docs for l in d["labels"]}))
    items = []
    for d in docs:
        names = [v[0]["name"] for v in d["vertexSet"]]
        gold = sorted({f"{names[l['h']]} — {labels[l['r']]} — {names[l['t']]}" for l in d["labels"]})
        text = " ".join(" ".join(s) for s in d["sents"])
        items.append({"dataset": "redocred", "id": d["title"], "body": text, "gold": gold})
    return items


def halumem() -> list[dict]:
    user = json.loads(open(DATA / "halumem_medium.jsonl").readline())
    items = []
    for i, s in enumerate(user["sessions"][:N_SESSIONS]):
        body = "\n".join(f"{t['role']}: {t['content']}" for t in s["dialogue"])
        gold = [m["memory_content"] for m in s["memory_points"]]
        items.append({"dataset": "halumem", "id": f"session-{i:02d}", "body": body, "gold": gold,
                      "time": s["start_time"]})
    return items


if __name__ == "__main__":
    items = redocred() + halumem()
    (DATA / "items.json").write_text(json.dumps(items, indent=1))
    for ds in ("redocred", "halumem"):
        sel = [i for i in items if i["dataset"] == ds]
        print(ds, len(sel), "items,", sum(len(i["gold"]) for i in sel), "gold facts,",
              sum(len(i["body"]) for i in sel) // 4, "≈content tokens")
