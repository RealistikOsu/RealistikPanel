import json
import requests


def checkUpdates(endpoint="https://raw.githubusercontent.com/KotypeyPyEdition/RealistikPanel/master/buildinfo.json", file="buildinfo.json"):
    with open(file) as f:
        up = json.load(f)

        r = requests.get(endpoint)
        print(r.text)



def isDevBuild(config="config.json"):
    with open(config) as f:
        d = json.load(f)
        return d['DevBuild']

def update():
    pass

checkUpdates()