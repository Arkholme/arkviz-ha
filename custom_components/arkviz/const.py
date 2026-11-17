"""Names ArkViz is known by in Home Assistant. They're kept in saved settings and addresses, so they don't change."""

DOMAIN = "arkviz"

# The sidebar address, /arkviz, and the element Home Assistant puts there
PANEL_URL = "arkviz"
PANEL_ELEMENT = "arkviz-panel"

# Where the panel and the app's files are served from
FILES_URL = "/arkviz_files"

# ArkViz as a page of its own, /arkviz-app/, for a wall panel or a full screen
APP_URL = "/arkviz-app"

# The option that shows ArkViz in the sidebar, and whether it does before anyone chooses
CONF_SIDEBAR = "sidebar"
DEFAULT_SIDEBAR = True

# The plan, in .storage/arkviz.plan
STORAGE_KEY = "arkviz.plan"
STORAGE_VERSION = 1

# The home's answers about error reports and usage metrics, in .storage/arkviz.telemetry, and where they're kept while running
TELEMETRY_STORAGE_KEY = "arkviz.telemetry"
TELEMETRY_STORAGE_VERSION = 1
DATA_TELEMETRY = "arkviz.telemetry"

# Art for art mode: the list in .storage/arkviz.art, the images themselves in arkviz/art in the configuration folder, and
# the address they're shown from
ART_STORAGE_KEY = "arkviz.art"
ART_STORAGE_VERSION = 1
ART_FOLDER = "arkviz/art"
ART_URL = "/api/arkviz/art"
DATA_ART = "arkviz.art"
