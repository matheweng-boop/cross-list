"""Command-line tools:  uv run python -m app.cli <command>

seed [FILE]          load a YAML data file (default: synthetic demo data)
refresh [CSV ...]    run the lifecycle refresh using CSV lists (default: var/lifecycle/*.csv)
analyze PDF          show revision/date/parameter suggestions from a datasheet
"""

import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.main import SYNTHETIC_FILE, bootstrap


def main(argv: list[str]) -> int:
    from app.db import init_engine

    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    engine = init_engine()
    bootstrap(engine, seed_synthetic=False)

    if cmd == "seed":
        from app.services.seed import load_file

        path = Path(args[0]) if args else SYNTHETIC_FILE
        with Session(engine) as s:
            n = load_file(s, path, synthetic=path == SYNTHETIC_FILE)
            s.commit()
        print(f"Loaded {n} parts from {path}")
    elif cmd == "refresh":
        from app.jobs.refresh import CsvSource, run

        paths = [Path(a) for a in args] or sorted((get_settings().data_dir / "lifecycle").glob("*.csv"))
        if not paths:
            print("No lifecycle CSV files found in var/lifecycle/")
            return 0
        with Session(engine) as s:
            print(run(s, [CsvSource(paths)]))
    elif cmd == "analyze":
        from app.parsing.datasheet import analyze

        info = analyze(Path(args[0]))
        print(f"Pages: {len(info.pages)}  Revision: {info.revision}")
        print(f"Revised: {info.revision_date}  First issue: {info.first_issue_date}")
        for sug in info.suggestions:
            print(f"  p{sug.page} {sug.key} = {sug.value}   …{sug.snippet}…")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
