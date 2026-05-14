from __future__ import annotations

import argparse
import json

from .apply import apply_feature_plan
from ..pack.manifest import init_pack_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test FeaturePlan apply engine.")
    parser.add_argument("--pack_root", required=True, help="Pack root directory path (contains pack.manifest.json).")
    parser.add_argument("--plan_json", required=True, help="Path to FeaturePlan JSON file.")
    args = parser.parse_args()

    plan_root = args.pack_root
    init_pack_manifest(plan_root)  # safe if manifest already exists? (init overwrites)

    with open(args.plan_json, "r", encoding="utf-8") as f:
        plan = json.load(f)

    res = apply_feature_plan(plan_root, plan, update_manifest=True)
    print("OK")
    print(json.dumps({"feature_name": res.feature_name, "files_written": res.files_written}, indent=2))


if __name__ == "__main__":
    main()

