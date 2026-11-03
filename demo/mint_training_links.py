"""Enrol the demo drivers on the training platform and keep their learner tokens in the private registry, so the
Train half of an accepting reply has a link to send. Drivers that already hold a token are skipped, so it is safe to
run again.

    python demo/mint_training_links.py                 # dry run: who would be enrolled
    python demo/mint_training_links.py --apply         # enrol, write tokens into demo/registry.live.json

The guard's admin key is read in-process from CDAI Secrets Manager and never printed. Each learner is created as
group "demo" with the ten driver modules in the driver's language. The guard allows 8 admin calls a minute, so calls
are 9 s apart. Tokens go only into the registry file, which is git-ignored, never to the screen or the logs."""
import argparse
import json
import pathlib
import sys
import time
import urllib.request

import boto3

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.training import MODULES  # noqa: E402

API = "https://eknjtgbfq3.execute-api.ap-south-1.amazonaws.com"
SECRET = "cdai/advaya/guard-admin-key"
PACE = 9.0


def admin_key() -> str:
    raw = boto3.client("secretsmanager", region_name="ap-south-1").get_secret_value(SecretId=SECRET)["SecretString"]
    try:
        value = json.loads(raw)
    except ValueError:
        return raw.strip()
    if isinstance(value, dict):
        for name in ("ADMIN_KEY", "admin_key", "key"):
            if value.get(name):
                return str(value[name])
        return str(next(iter(value.values())))
    return str(value)


def call(key: str, **body) -> dict:
    body["key"] = key
    req = urllib.request.Request(API, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="demo/registry.live.json")
    ap.add_argument("--apply", action="store_true", help="enrol and write the tokens")
    a = ap.parse_args()
    path = ROOT / a.registry
    reg = json.loads(path.read_text(encoding="utf-8"))
    todo = [d for d in reg["drivers"] if not d.get("training_token")]
    print("%s: %d drivers, %d without a learner token" % (a.registry, len(reg["drivers"]), len(todo)))
    for d in todo:
        print("  %s  %-24s %s  lang=%s" % (d["cab_id"], d["driver_name"], d["vehicle_no"], d.get("language", "en")))
    if not todo:
        return 0
    if not a.apply:
        print("dry run; add --apply to enrol")
        return 0
    key, slugs, failed = admin_key(), [s for s, _ in MODULES], 0
    for i, d in enumerate(todo, 1):
        try:
            res = call(key, action="admin_create", name=d["driver_name"], mobile=d["phone"][-10:], courses=slugs,
                       group="demo", cab=d["vehicle_no"], lang=d.get("language", "en"))
        except Exception as e:   # reported, never hidden; the next driver still gets a try
            res = {"ok": False, "reason": type(e).__name__ + ": " + str(e)[:120]}
        if res.get("ok") and res.get("token"):
            d["training_token"] = res["token"]
            path.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            granted = [link["course"] for link in res.get("links", [])]
            print("  %s: enrolled, %d of %d modules granted" % (d["cab_id"], len(granted), len(slugs)))
            if len(granted) < len(slugs):
                print("    granted: " + "; ".join(granted))
        else:
            failed += 1
            print("  %s: refused: %s" % (d["cab_id"], res.get("reason")))
        if i < len(todo):
            time.sleep(PACE)
    print("done: %d enrolled, %d refused. Redeploy so the functions carry the new registry." % (len(todo) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
