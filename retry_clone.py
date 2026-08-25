import os
import shutil
import subprocess

DOLT_PATH = r"C:\Program Files\Dolt\bin\dolt.exe"
from tvdata.config import WORKSPACE_ROOT

DEST_DIR = os.path.join(WORKSPACE_ROOT, "raw", "dolt")


def clean_and_clone(repo_name: str):
    folder_name = repo_name.split("/")[-1]
    target_path = os.path.join(DEST_DIR, folder_name)

    if os.path.exists(target_path):
        print(f"Cleaning incomplete folder: {target_path}")
        shutil.rmtree(target_path)

    cmd = [DOLT_PATH, "clone", repo_name, target_path]
    print(f"Cloning {repo_name}...")
    try:
        res = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"Successfully cloned {repo_name}!")
        print(res.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error cloning {repo_name}: {e}")
        print(e.stderr)


def main():
    repos = ["post-no-preference/earnings", "post-no-preference/options"]
    for repo in repos:
        clean_and_clone(repo)


if __name__ == "__main__":
    main()
