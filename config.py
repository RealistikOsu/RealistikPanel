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
    "ServerURL" : "https://ussr.pl/",
    "HasRelax" : True,
    "Webhook" : "", #Discord webhook for posting newly ranked maps
    #Recaptcha for the login page
    "UseRecaptcha" : False,
    "RecaptchaSecret" : ""
}

class JsonFile:
    @classmethod
    def SaveDict(self, Dict, File):
        """Saves a dict as a file"""
        with open(File, 'w') as json_file:
            json.dump(Dict, json_file, indent=4)

    @classmethod
    def GetDict(self, file):
        """Returns a dict from file name"""
        if not path.exists(file):
            return {}
        else:
            with open(file) as f:
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
    #insert config check here
    print(Fore.GREEN+" Configuration loaded successfully! Loading..." + Fore.RESET)
