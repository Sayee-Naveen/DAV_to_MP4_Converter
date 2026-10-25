"""
DAV to MP4 Converter - Application Entry Point
"""

import sys
import os

# Add local directory to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app_gui import main

if __name__ == "__main__":
    main()
