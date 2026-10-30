"""France profile; always pair the client mod with this server build."""
from pathlib import Path
import argparse
import datetime
import json
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parent
PROFILE = "1.7.1-beta-france.1"


def main():
    os.chdir(ROOT)
    import install
    import launcher
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-dir", default=os.environ.get("BNE_USER_DIR"))
    parser.add_argument("--game-dir", default=os.environ.get("BNE_GAME_DIR"))
    parser.add_argument("--attach", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    attach, check = args.attach, args.check
    candidates = [args.user_dir] if args.user_dir else install.candidate_user_dirs()
    if len(candidates) != 1:
        parser.error("Indiquez le dossier utilisateur BeamNG avec --user-dir ou BNE_USER_DIR.")
    user = Path(candidates[0]).expanduser().resolve()
    if not user.is_dir():
        parser.error("Le dossier utilisateur BeamNG n'existe pas.")
    target = user / "mods/unpacked/beamng_earth"
    if not target.resolve().is_relative_to(user):
        raise RuntimeError("Le dossier du mod sort du dossier utilisateur")
    src_hash = install.tree_hash(install.MOD_SRC)
    installed_hash = install.tree_hash(str(target)) if target.exists() else None
    if check:
        print(json.dumps({"profile": PROFILE, "source":src_hash,
                          "installed": installed_hash, "matched":src_hash == installed_hash}))
        return 0
    if launcher.server_port_busy():
        print("Un serveur Earth est deja actif. Aucun second serveur n'est lance.")
        return 0
    if attach and not launcher.game_alive():
        return 0
    if src_hash != installed_hash:
        if launcher.game_alive():
            print("Le jeu utilise une autre version. Fermez-le et utilisez BeamNG.Earth - correctifs pour la remettre.")
            return 2
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = user.parent / "BeamNG.Earth-backups" / ("avant-profil-" + stamp)
        backup.mkdir(parents=True, exist_ok=False)
        staging = target.with_name("beamng_earth.france-staging")
        if staging.exists():
            raise RuntimeError(f"Installation incomplete conservee pour inspection : {staging}")
        shutil.copytree(install.MOD_SRC, staging, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        if install.tree_hash(str(staging)) != src_hash:
            raise RuntimeError("La copie du correctif ne correspond pas a la source")
        if target.exists():
            install._stamp_times(str(staging), install._unchanged_times(str(target), install.MOD_SRC))
            target.rename(backup / "beamng_earth")
        try:
            staging.rename(target)
        except Exception:
            if not target.exists() and (backup / "beamng_earth").exists():
                (backup / "beamng_earth").rename(target)
            raise
        (backup / "restore.json").write_text(json.dumps({"target":str(target), "previous_hash":installed_hash,
            "new_hash":src_hash, "profile":str(ROOT)}, indent=2), encoding="utf-8")
        print("Sauvegarde :", backup)
    if not launcher.game_alive():
        install.ensure_mod_active(str(user))
    # Respect distinct road/rail levels even when only the lower tunnel is tagged.
    # In Annonay, disabling this makes the old railway cut through Rue du Quebec.
    for key, value in {"BNE_DEM_SOURCE":"ign", "BNE_GRADESEP":"on", "BNE_REVISIT_MB":"20000"}.items():
        os.environ.setdefault(key,value)
    print(f"Profil France : {PROFILE} ; niveaux route/rail et noms de communes actifs.", flush=True)
    sys.argv = [str(ROOT / "launcher.py"), "--keep-mod", "--gfx", "dx12", "--user-dir", str(user)]
    if args.game_dir:
        sys.argv += ["--game-dir", args.game_dir]
    sys.argv += (["--no-beammp"] if attach else []) + ["--", "--cache-cap", "50"]
    launcher.main()
    return 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
