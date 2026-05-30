"""pytest bootstrap — put the project root on sys.path so tests can import
`user_data.strategies.regime_detector` etc. without an editable install.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
