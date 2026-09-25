"""Prepare and run one controlled calibration using the configured Codex profile."""
import argparse
import json
from pathlib import Path
import sys

from grading.schemas import Identity, ROOT
from grading.sol_grader import CredentialUnavailable, ModelCallError
from workflow.calibration_pipeline import CalibrationPipeline


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=ROOT)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--student-name", required=True)
    parser.add_argument("--essay-question", default=None)
    parser.add_argument("--model-profile", default=None, help="Configured calibration profile, e.g. sol_medium or luna_xhigh")
    parser.add_argument(
        "--allow-second-live-attempt",
        action="store_true",
        help="Explicitly authorize one second request when exactly one prior attempt is recorded",
    )
    args = parser.parse_args(argv)
    identity = Identity(args.student_id, args.student_name, args.class_name)
    try:
        result = CalibrationPipeline(args.project_dir, model_profile=args.model_profile).run(
            args.source,
            identity,
            args.essay_question,
            allow_second_live_attempt=args.allow_second_live_attempt,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (CredentialUnavailable, ModelCallError, ValueError, OSError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
