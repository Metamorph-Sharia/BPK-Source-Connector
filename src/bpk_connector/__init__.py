"""BPK source connector: targeted regulations from peraturan.bpk.go.id.

The orchestrator imports ``BPKConnector`` only. Architecture: docs/plan/02-architecture.md
"""

__version__ = "0.1.0"

from bpk_connector.connector import BPKConnector  # noqa: E402  (needs __version__)

__all__ = ["BPKConnector", "__version__"]
