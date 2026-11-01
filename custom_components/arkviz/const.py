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
