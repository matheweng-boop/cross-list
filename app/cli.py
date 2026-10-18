"""Command-line tools:  uv run python -m app.cli <command>

seed [FILE]          load a YAML data file (default: synthetic demo data)
refresh [CSV ...]    run the lifecycle refresh using CSV lists (default: var/lifecycle/*.csv)
analyze PDF          show revision/date/parameter suggestions from a datasheet
import-skyworks [--offline]
                     fetch Skyworks Si86 data, build data/real/skyworks_si86.yaml and load it
import-ti [--offline]
                     fetch TI digital isolator data, build data/real/ti_digital_isolators.yaml and load it
import-novosense [--offline]
                     fetch Novosense digital isolator data and load it
load-real            load every data/real/*.yaml file
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
    elif cmd in ("import-skyworks", "import-ti", "import-novosense"):
        import yaml

        from app.services.seed import load_file
        from app.sources import novosense, skyworks, ti

        source, out = {
            "import-skyworks": (skyworks, Path("data/real/skyworks_si86.yaml")),
            "import-ti": (ti, Path("data/real/ti_digital_isolators.yaml")),
            "import-novosense": (novosense, Path("data/real/novosense_digital_isolators.yaml")),
        }[cmd]
        if "--offline" not in args:
            source.fetch()
        data = source.build()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=200))
        print(f"Built {len(data['parts'])} parts ({len(data['skipped'])} skipped) -> {out}")
        with Session(engine) as s:
            n = load_file(s, out)
            s.commit()
        print(f"Loaded {n} parts")
    elif cmd == "load-real":
        from app.services.seed import load_file

        with Session(engine) as s:
            for path in sorted(Path("data/real").glob("*.yaml")):
                print(f"{path}: {load_file(s, path)} parts")
            s.commit()
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
