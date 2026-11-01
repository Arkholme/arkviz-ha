# ArkViz for Home Assistant

ArkViz is a floorplan dashboard for Home Assistant. You draw your home once and place your devices on it, and ArkViz
shows their state on the plan: lights on or off, each room's temperature, and alerts from leak sensors, smoke alarms
and locks. See [arkviz.app](https://arkviz.app) for more, and the [demo](https://demo.arkviz.app) to try it.

This repository holds ArkViz's releases for Home Assistant, which installs them from here. ArkViz needs Home Assistant
2024.7 or later.

## Install

On Home Assistant 2026.11 or later, through the Marketplace:

1. Go to Settings, then Marketplace.
2. Choose Add from link and enter `https://github.com/Arkholme/arkviz-ha`. The Marketplace asks you to connect GitHub the
   first time, which only reads public information.
3. Open ArkViz, choose Install, and follow its setup. If Home Assistant asks you to restart, restart it.

On Home Assistant 2026.10 or earlier, through [HACS](https://hacs.xyz/docs/use/download/download/):

1. In HACS, open the menu and choose Custom repositories.
2. Add `https://github.com/Arkholme/arkviz-ha` with the type Integration.
3. Find ArkViz in HACS, download it, and restart Home Assistant.
4. Go to Settings, then Devices & services, choose Add integration and pick ArkViz.

New versions appear with Home Assistant's other updates, under Settings. After updating, restart Home Assistant.

## Opening ArkViz

ArkViz appears in Home Assistant's sidebar for everyone who signs in. It's also a page of its own at `/arkviz-app/` on
your Home Assistant's address, such as `http://homeassistant.local:8123/arkviz-app/`, for a wall panel or a full screen.
It uses the sign-in Home Assistant already has in that browser, or asks you to sign in.

To take it out of the sidebar, go to Settings, then Devices & services, open ArkViz and choose Configure. Its own address
keeps working.

## Problems

Report problems in this repository's [issues](https://github.com/Arkholme/arkviz-ha/issues), with the version you're
running.

ArkViz is an independent project, not made by the Home Assistant team.
