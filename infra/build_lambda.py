"""Build build/lambda.zip for all three Lambda functions: the pipeline package, the demo files, the dashboard site
and the runtime dependencies from requirements.txt as Linux wheels for Python 3.12. boto3 is left out because the
Lambda runtime already has it.

    python infra/build_lambda.py
"""
import pathlib
import shutil
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
PKG = BUILD / "pkg"
ZIP = BUILD / "lambda.zip"
LEFT_OUT = {"boto3"}                 # provided by the Lambda runtime
PLATFORMS = ("manylinux2014_x86_64", "manylinux_2_17_x86_64", "manylinux_2_28_x86_64")


def runtime_requirements() -> list:
    """requirements.txt up to the '# development only' line, without the packages the runtime provides."""
    reqs = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("# development only"):
            break
        if line and not line.startswith("#") and line.split("==")[0].strip().lower() not in LEFT_OUT:
            reqs.append(line)
    return reqs


def main() -> None:
    shutil.rmtree(BUILD, ignore_errors=True)
    PKG.mkdir(parents=True)
    platforms = [arg for p in PLATFORMS for arg in ("--platform", p)]
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "--target", str(PKG), "--implementation", "cp", "--python-version", "3.12",
                    "--only-binary=:all:", *platforms, *runtime_requirements()], check=True)
    shutil.copytree(ROOT / "pipeline", PKG / "pipeline", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (PKG / "demo").mkdir()
    for f in (ROOT / "demo").glob("*.json"):     # registry.live.json is included when present; it is never committed
        shutil.copy2(f, PKG / "demo" / f.name)
    shutil.copytree(ROOT / "dashboard" / "site", PKG / "dashboard" / "site")   # served by pipeline.dashboard
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(PKG.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(PKG).as_posix())
    print(f"{ZIP} ({ZIP.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
