from __future__ import annotations

import json
import os
import sys
import time

import requests

import logger
from config import config


###########################
#                         #
#        Updater          #
#                         #
#                         #
###########################


def checkUpdates(
    endpoint="https://raw.githubusercontent.com/RealistikOsu/RealistikPanel/master/buildinfo.json",
):
    with open("buildinfo.json") as f:
        up = json.load(f)

        r = requests.get(endpoint)

        return up["version"] < r.json()["version"]


def getLatestVersion(
    endpoint="https://raw.githubusercontent.com/RealistikOsu/RealistikPanel/master/buildinfo.json",
):
    r = requests.get(endpoint)
    return r.json()["version"]


def UpdateBuild():
    if not config.app_developer_build:
        return

    logger.info("Detected Development version... disabling update notify")

    with open("buildinfo.json") as f:
        d = json.load(f)

        currBuild = int(time.time())

        d["version"] = currBuild

    with open("buildinfo.json", "w") as data:
        json.dump(d, data)


def update():
    build = getLatestVersion()

    logger.info(f"Updating to {build} version...")
    res = os.system("git pull")
    if res:
        logger.error("Failed to update panel using git.")
    else:
        logger.info("Panel updated.")
    exit()


def handle_update():
    if config.app_developer_build:
        return UpdateBuild()
    CheckUpdates = checkUpdates()
    if not CheckUpdates:
        return

    logger.info(
        f" Update found: {getLatestVersion()}\n to update just run with arguments --update",
    )
    args = " ".join(sys.argv)
    if "--update" in args:
        update()
