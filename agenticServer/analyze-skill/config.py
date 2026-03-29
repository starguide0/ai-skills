import os

# Base directory for the AgenticServer
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Path configuration
PATHS = {
    "protocols": os.path.join(BASE_DIR, "protocols"),
    "core": os.path.join(BASE_DIR, "core"),
    "tools": os.path.join(BASE_DIR, "tools")
}

# Analysis settings
SETTINGS = {
    "max_protocol_tokens": 1000,
    "default_phase": "phase0_setup"
}
