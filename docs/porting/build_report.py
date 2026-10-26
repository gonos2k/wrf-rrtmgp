"""Build self-contained, printable HTML with native MathML using Pandoc.

Requires pandoc on PATH; no JavaScript, external equation service or model run.
Local SVG and CSS are embedded. Citations remain ordinary outbound hyperlinks.
"""

from pathlib import Path
import shutil
import subprocess

P = Path(__file__).resolve().parent


def main():
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise SystemExit("pandoc is required to build the HTML; Markdown remains directly readable")
    subprocess.run(
        [
            pandoc,
            str(P / "TECHNICAL_REPORT_ko.md"),
            "--standalone",
            "--toc",
            "--toc-depth=2",
            "--mathml",
            "--embed-resources",
            "--resource-path=" + str(P),
            "--css=" + str(P / "report.css"),
            "--output=" + str(P / "TECHNICAL_REPORT_ko.html"),
        ],
        cwd=P,
        check=True,
    )
    print("PRINTABLE_SELF_CONTAINED_HTML_CREATED; new model/solver/compiler calls=0")


if __name__ == "__main__":
    main()
