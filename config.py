# the purpose of this file has changed to be a quick config fetcher
from __future__ import annotations

import json
from base64 import b64encode
from os import path
from os import urandom

from colorama import Fore
from colorama import init

init()  # Colorama thing
DefaultConfig = {  # THESE ARE DEFAULT OPRIONS FOR THE CONFIG.
    "Port": 1337,
    # SQL Info
    "SQLHost": "localhost",
    "SQLPort": "3306",
    "SQLUser": "",
    "SQLDatabase": "ripple",
    "SQLPassword": "",
    # Redis Info
    "RedisHost": "localhost",
    "RedisPort": 6379,
    "RedisDb": 0,
    "RedisPassword": "",
    # Server Settings
    "ServerName": "RealistikOsu!",
    "ServerURL": "https://ussr.pl/",
    "LetsAPI": "https://old.ussr.pl/letsapi/",
    "AvatarServer": "https://a.ussr.pl/",
    "BanchoURL": "https://c.ussr.pl/",
    "BeatmapMirror": "http://storage.ripple.moe/",
    "IpLookup": "https://ip.zxq.co/",
    "HasRelax": True,
    "HasAutopilot": True,
    "AvatarDir": "/home/RIPPLE/avatarserver/av/",
    "Webhook": "",  # Discord webhook for posting newly ranked maps
    # Recaptcha v2 for the login page
    "UseRecaptcha": False,
    "RecaptchaSecret": "",
    "RecaptchaSiteKey": "",
    # RealistikPanel Settings
    "PageSize": 50,  # number of elements per page
    "SecretKey": b64encode(urandom(64)).decode(
        "utf-8",
    ),  # generates random encryption key
    "DevBuild": False,  # for developers only to create a new buildinfo.json code
    "UserCountFetchRate": 5,  # In minutes. The interval between grabbing the player count
    "GitHubRepo": "https://github.com/RealistikOsu/RealistikPanel",  # AGPL requirement i believe
    "CurrentIP": "95.179.225.194",  # the IP for the /current.json (ripple based switchers)
    "TimezoneOffset": 1,  # offset for hours, can be negative
    "DonorBadgeID": 1002,  # This badge will be awarded to new donors!
    "VerifiedBadgeID": 1005,  # The badge that will be awarded on unfreezing a person.
    "AdminLogWebhook": "",  # if set, all admin logs (aka rap logs) will be sent to that webhook
    "TimestampType": "unix",  # type of timestamps to use (for now only on freezes), current options: unix (seconds since 1/1/1970) | ainu (day thing)
    "FokaKey": "take this from your pep.py config or it will not work",
}


class JsonFile:
    @classmethod
    def SaveDict(self, Dict, File="config.json"):
        """Saves a dict as a file"""
        with open(File, "w") as json_file:
            json.dump(Dict, json_file, indent=4)

    @classmethod
    def GetDict(self, File="config.json"):
        """Returns a dict from file name"""
        if not path.exists(File):
            return {}
        else:
            with open(File) as f:
                data = json.load(f)
            return data


UserConfig = JsonFile.GetDict("config.json")
# Config Checks
if UserConfig == {}:
    print(Fore.YELLOW + " No config found! Generating!" + Fore.RESET)
    JsonFile.SaveDict(DefaultConfig, "config.json")
    print(
        Fore.WHITE
        + " Config created! It is named config.json. Edit it accordingly and start RealistikPanel again!",
    )
    exit()
else:
    # config check and updater
    AllGood = True
    NeedSet = []
    for key in list(DefaultConfig.keys()):
        if key not in list(UserConfig.keys()):
            AllGood = False
            NeedSet.append(key)

    if AllGood:
        print(
            Fore.GREEN + " Configuration loaded successfully! Loading..." + Fore.RESET,
        )
    else:
        # fixes config
        print(Fore.BLUE + " Updating config..." + Fore.RESET)
        for Key in NeedSet:
            UserConfig[Key] = DefaultConfig[Key]
            print(
                Fore.BLUE
                + f" Option {Key} added to config. Set default to '{DefaultConfig[Key]}'."
                + Fore.RESET,
            )
        print(
            Fore.GREEN
            + " Config updated! Please edit the new values to your liking."
            + Fore.RESET,
        )
        JsonFile.SaveDict(UserConfig, "config.json")
        exit()
