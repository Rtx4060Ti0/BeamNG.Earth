"""Stable entry point. Only a locally verified release may run; updates cannot bypass the profile."""
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    if sys.stdout is None:
        sys.stdout = sys.stderr = (logs / f"launcher-{os.getpid()}.log").open("w", encoding="utf-8", buffering=1)
    with (ROOT / "launcher.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print("Le lanceur corrige est deja actif.")
            return 0
        current = json.loads((ROOT / "current.json").read_text(encoding="utf-8"))
        release = (ROOT / "versions" / current["release"]).resolve()
        if not release.is_relative_to((ROOT / "versions").resolve()):
            raise RuntimeError("Invalid release path")
        manifest = json.loads((release / "payload-manifest.json").read_text(encoding="utf-8"))
        bad = []
        for rel, expected in manifest["sha256"].items():
            path = (release / rel).resolve()
            if not path.is_relative_to(release) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                bad.append(rel)
        if bad:
            raise RuntimeError("Correctif incomplet ou modifie, lancement annule : " + ", ".join(bad[:8]))
        exe = Path(sys.executable).with_name("python.exe")
        extra = [x for x in sys.argv[1:] if x in ("--attach", "--check")]
        env = os.environ.copy()
        local = ROOT / "local-config.json"
        if local.is_file():
            for key,value in json.loads(local.read_text(encoding="utf-8-sig")).items():
                if key in {"BNE_USER_DIR", "BNE_GAME_DIR", "BNE_FRANCE_DB", "BNE_ROAD_QA_DIR", "BNE_REVISIT_MB"}:
                    env[key] = str(value)
        with (logs / "profile-launch.log").open("a", encoding="utf-8") as log:
            return subprocess.call([str(exe), "-u", str(release / "start_corrected.py"), *extra], cwd=release,
                                   env=env,
                                   stdout=log if "--attach" in extra else sys.stdout,
                                   stderr=log if "--attach" in extra else sys.stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW if "--attach" in extra else 0)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        raise SystemExit(1)
