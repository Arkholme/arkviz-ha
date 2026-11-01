# ArkViz for Home Assistant

ArkViz is a floorplan dashboard for Home Assistant. You draw your home once and place your devices on it, and ArkViz
shows their state on the plan: lights on or off, each room's temperature, and alerts from leak sensors, smoke alarms
and locks. See [arkviz.app](https://arkviz.app) for more, and the [demo](https://demo.arkviz.app) to try it.

This repository holds ArkViz's releases for Home Assistant. It needs Home Assistant 2024.7 or later.

## Install with HACS

1. In HACS, open the menu and choose Custom repositories.
2. Add `https://github.com/Arkholme/arkviz-ha` with the type Integration.
3. Find ArkViz in HACS, download it, and restart Home Assistant.
4. Go to Settings, then Devices & services, choose Add integration and pick ArkViz.

HACS shows new versions of ArkViz as updates in Home Assistant.

## Install by hand

1. Download `arkviz.zip` from the [latest release](https://github.com/Arkholme/arkviz-ha/releases/latest).
2. Unzip it into a folder named `arkviz` in Home Assistant's `config/custom_components` folder.
3. Restart Home Assistant.
4. Go to Settings, then Devices & services, choose Add integration and pick ArkViz.

To update, replace the folder with the new release's and restart Home Assistant.

## Problems

Report problems in this repository's [issues](https://github.com/Arkholme/arkviz-ha/issues), with the version you're
running.

ArkViz is an independent project, not made by the Home Assistant team.
