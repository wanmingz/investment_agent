import subprocess
import sys
from pathlib import Path


def main() -> None:
    app = Path(__file__).resolve().parents[2] / "streamlit_app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app), *sys.argv[1:]], check=True)
