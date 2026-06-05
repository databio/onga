"""Allow running as python -m onga_embeddings."""
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from run_comparison import main

if __name__ == "__main__":
    main()
