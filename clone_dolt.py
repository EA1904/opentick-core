import os
import subprocess

DOLT_PATH = r"C:\Program Files\Dolt\bin\dolt.exe"
from tvdata.config import WORKSPACE_ROOT

DEST_DIR = os.path.join(WORKSPACE_ROOT, "raw", "dolt")


def clone_db(repo_name: str):
    print(f"\nCloning {repo_name}...")
    folder_name = repo_name.split("/")[-1]
    target_path = os.path.join(DEST_DIR, folder_name)

    if os.path.exists(target_path):
        print(f"Folder already exists: {target_path}. Skipping clone.")
        return

    cmd = [DOLT_PATH, "clone", repo_name, target_path]
    print(f"Running: {' '.join(cmd)}")

    try:
        res = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"Successfully cloned {repo_name}!")
        print(res.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error cloning {repo_name}: {e}")
        print(e.stderr)


def main():
    os.makedirs(DEST_DIR, exist_ok=True)

    repos = [
        "post-no-preference/rates",
        "post-no-preference/stocks",
        "post-no-preference/earnings",
        "post-no-preference/options",
    ]

    for repo in repos:
        clone_db(repo)

    print("\nAll Dolt databases cloning process finished.")


if __name__ == "__main__":
    main()
