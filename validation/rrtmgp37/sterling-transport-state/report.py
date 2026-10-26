"""Write the result and fixed-cell step CSV from captured native evidence."""

from pathlib import Path
import json, csv, tarfile
from analyze import analyze

P = Path(__file__).resolve().parent
R = P.parents[2]
B = R.parent


def inputs():
    with tarfile.open(
        P.parent / "sterling-thermodynamic-tendencies/saved/evidence.tar.gz", "r:gz"
    ) as t:
        oldtext = t.extractfile("native/thermodynamic_operations.txt").read().decode()
    return (
        oldtext,
        (P.parent / "sterling-thermodynamic-tendencies/step-processes.csv").read_text(),
        json.loads((P.parent / "sterling-thermodynamic-tendencies/result.json").read_text()),
    )


def main():
    O = B / "udm37-sterling-transport-analysis-v1"
    raw = (B / "udm37-sterling-transport-run-v1/host/transport_faces.txt").read_text()
    prior = json.loads(
        (B / "udm37-sterling-transport-prior-v1/prior-state-and-coordinate.json").read_text()
    )
    comparison = json.loads((O / "history-comparison.json").read_text())
    r, rows = analyze(raw, prior, *inputs(), comparison)
    (P / "result.json").write_text(json.dumps(r, indent=2) + "\n")
    with (P / "step-faces.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(r["status"], r["replay_counts"])
    for h in r["hourly"]:
        for layer in h["layers"]:
            if layer["k"] == 8:
                print(h["start_hour_UTC"], json.dumps(layer))


if __name__ == "__main__":
    main()
