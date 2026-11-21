import os
import subprocess

env = os.environ.copy()
for name in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).split():
    env.pop(name, None)

# Only run this helper after choosing a disposable fixture directory.
def initialize(directory):
    subprocess.run(["git", "init", str(directory)], env=env, check=True)
