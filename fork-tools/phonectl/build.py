"""Build phonectl.dex from src/*.java with the JDK and the Android SDK that fork-tools/.env names.

    uv run python fork-tools/phonectl/build.py

javac (--release 8, against the SDK's android.jar) makes the classes, d8 turns them into a dex. The
result, build/phonectl.dex, is what the computer pushes to the phone (device.push_phonectl). The build
folder is not committed.
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "src"
BUILD = HERE / "build"
ENV_FILE = HERE.parent / ".env"


def setting(name: str) -> str:
    """JAVA_HOME or ANDROID_HOME: fork-tools/.env first (the justfile lets it override the environment, and
    the process environment may name an older JDK or SDK), else the environment."""
    value = None
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip().strip('"')
    value = value or os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set (fork-tools/.env or the environment)")
    return value


def newest(folder: Path) -> Path:
    versions = sorted(p for p in folder.iterdir() if p.is_dir())
    if not versions:
        raise SystemExit(f"nothing in {folder}")
    return versions[-1]


def main() -> int:
    java_home, android_home = Path(setting("JAVA_HOME")), Path(setting("ANDROID_HOME"))
    javac = java_home / "bin" / ("javac.exe" if os.name == "nt" else "javac")
    platform = newest(android_home / "platforms")
    android_jar = platform / "android.jar"
    build_tools = newest(android_home / "build-tools")
    d8 = build_tools / ("d8.bat" if os.name == "nt" else "d8")
    for needed in (javac, android_jar, d8):
        if not needed.exists():
            raise SystemExit(f"missing: {needed}")

    # d8 is a launcher that runs `java`: it must be the JDK of fork-tools/.env, not whatever is first on the PATH
    tool_env = {**os.environ, "JAVA_HOME": str(java_home), "PATH": str(java_home / "bin") + os.pathsep + os.environ.get("PATH", "")}
    classes = BUILD / "classes"
    classes.mkdir(parents=True, exist_ok=True)
    sources = [str(p) for p in sorted(SRC.glob("*.java"))]
    compile_cmd = [str(javac), "--release", "8", "-Xlint:-options", "-cp", str(android_jar), "-d", str(classes), *sources]
    print("javac:", platform.name, "android.jar;", len(sources), "source file(s)")
    if subprocess.run(compile_cmd, env=tool_env).returncode != 0:
        return 1
    class_files = [str(p) for p in sorted(classes.rglob("*.class"))]
    dex_cmd = [str(d8), "--lib", str(android_jar), "--min-api", "26", "--output", str(BUILD), *class_files]
    print("d8:", build_tools.name)
    if subprocess.run(dex_cmd, env=tool_env).returncode != 0:
        return 1
    dex = BUILD / "classes.dex"
    target = BUILD / "phonectl.dex"
    target.write_bytes(dex.read_bytes())
    dex.unlink()
    print(f"{target} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
