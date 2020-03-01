#the purpose of this file has changed to be a quick config fetcher
import json
from os import path
from colorama import init, Fore
init() #Colorama thing
DefaultConfig = {
    "Port" : 1337,
    #SQL Info
    "SQLHost" : "localhost",
    "SQLUser" : "",
    "SQLDatabase" : "ripple",
    "SQLPassword" : "",
    #Redis Info
    "RedisHost" : "localhost",
    "RedisPort" : 6379,
    "RedisDb" : 0,
    #Server Settings
    "ServerName" : "RealistikOsu!",
    "ServerURL" : "https://ussr.pl/",
    "LetsAPI" : "http://127.0.0.1:5002/letsapi",
    "AvatarServer" : "https://a.ussr.pl/",
    "BeatmapMirror" : "http://storage.ripple.moe/",
    "HasRelax" : True,
    "Webhook" : "", #Discord webhook for posting newly ranked maps
    #Recaptcha v2 for the login page
    "UseRecaptcha" : False,
    "RecaptchaSecret" : "",
    "RecaptchaSiteKey" : ""
}

class JsonFile:
    @classmethod
    def SaveDict(self, Dict, File="config.json"):
        """Saves a dict as a file"""
        with open(File, 'w') as json_file:
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
#Config Checks
if UserConfig == {}:
    print(Fore.YELLOW+" No config found! Generating!"+Fore.RESET)
    JsonFile.SaveDict(DefaultConfig, "config.json")
    print(Fore.WHITE+" Config created! It is named config.json. Edit it accordingly and start RealistikPanel again!")
    exit()
else:
    #config check and updater
    AllGood = True
    NeedSet = []
    for key in list(DefaultConfig.keys()):
        if key not in list(UserConfig.keys()):
            AllGood = False
            NeedSet.append(key)

    if AllGood:
        print(Fore.GREEN+" Configuration loaded successfully! Loading..." + Fore.RESET)
    else:
        #fixes config
        print(Fore.BLUE+" Updating config..." + Fore.RESET)
        for Key in NeedSet:
            UserConfig[key] = DefaultConfig[key]
            print(Fore.BLUE+f" Option {key} added to config. Set default to '{DefaultConfig[key]}'." + Fore.RESET)
        print(Fore.GREEN+" Config updated! Please edit the new values to your liking." + Fore.RESET)
        JsonFile.SaveDict(UserConfig, "config.json")
        exit()
        