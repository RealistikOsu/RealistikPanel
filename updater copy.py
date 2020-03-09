import json
import requests
import os
import time
import sys


###########################
#                         #
#        Updater          #
#                         #
#                         #
###########################



def checkUpdates(endpoint="https://raw.githubusercontent.com/KotypeyPyEdition/RealistikPanel/updates/buildinfo.json", file="buildinfo.json"):
    with open(file) as f:
        up = json.load(f)

        r = requests.get(endpoint)
        return up['version'] is not r.json()['version']


def getLatestVersion(endpoint="https://raw.githubusercontent.com/KotypeyPyEdition/RealistikPanel/updates/buildinfo.json"):
    r = requests.get(endpoint)
    return r.json()['version']




def isDevBuild(config="config.json"):
    with open(config) as f:
        d = json.load(f)
        return d['DevBuild']



def UpdateBuild(config='buildinfo.json'):

    if not isDevBuild(): return


    with open(config) as f:
        d = json.load(f)

        currBuild = int(time.time())
        print(currBuild)

        d['version'] = currBuild

        with open(config, 'w') as data:
            json.dump(d, data)



def update():
    build = getLatestVersion()

    print(f'Updating to {build} version...')
    os.system('git pull')
    print('Panel should be updated if not updated DM me kotypey: Kotypey#9393 or RealistikDash#1939')
    exit()



def handleUpdate():
    if isDevBuild(): UpdateBuild()
    CheckUpdates = checkUpdates()
    if not checkUpdates:
        return

    print(f'Update found: {getLatestVersion()}\nto update just run with arguments --update')
    args = ' '.join(sys.argv)
    if '--update' in args:
        update()

handleUpdate()