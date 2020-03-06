#This file is responsible for all the functionality
from config import UserConfig
import mysql.connector
from colorama import init, Fore
import redis
import bcrypt
import datetime
import requests
from discord_webhook import DiscordWebhook, DiscordEmbed
import time
import hashlib 
import json

init() #initialises colourama for colours

print(f"""{Fore.BLUE}  _____            _ _     _   _ _    _____                 _ _ 
 |  __ \          | (_)   | | (_) |  |  __ \               | | |
 | |__) |___  __ _| |_ ___| |_ _| | _| |__) |_ _ _ __   ___| | |
 |  _  // _ \/ _` | | / __| __| | |/ /  ___/ _` | '_ \ / _ \ | |
 | | \ \  __/ (_| | | \__ \ |_| |   <| |  | (_| | | | |  __/ |_|
 |_|  \_\___|\__,_|_|_|___/\__|_|_|\_\_|   \__,_|_| |_|\___|_(_)
 ---------------------------------------------------------------
{Fore.RESET}""")

try:
    mydb = mysql.connector.connect(
        host=UserConfig["SQLHost"],
        user=UserConfig["SQLUser"],
        passwd=UserConfig["SQLPassword"]
    ) #connects to database
    print(f"{Fore.GREEN} Successfully connected to MySQL!")
except Exception as e:
    print(f"{Fore.RED} Failed connecting to MySQL! Abandoning!\n Error: {e}{Fore.RESET}")
    exit()

try:
    r = redis.Redis(host=UserConfig["RedisHost"], port=UserConfig["RedisPort"], db=UserConfig["RedisDb"]) #establishes redis connection
    print(f"{Fore.GREEN} Successfully connected to Redis!")
except Exception as e:
    print(f"{Fore.RED} Failed connecting to Redis! Abandoning!\n Error: {e}{Fore.RESET}")
    exit()

mycursor = mydb.cursor() #creates a thing to allow us to run mysql commands
mycursor.execute(f"USE {UserConfig['SQLDatabase']}") #Sets the db to ripple


def DashData():
    #note to self: add data caching so data isnt grabbed every time the dash is accessed
    """Grabs all the values for the dashboard."""
    mycursor.execute("SELECT value_string FROM system_settings WHERE name = 'website_global_alert'")
    Alert = mycursor.fetchall()
    if len(Alert) == 0:
        #some ps only have home alert
        mycursor.execute("SELECT value_string FROM system_settings WHERE name = 'website_home_alert'")
        #if also that doesnt exist
        Alert = mycursor.fetchall()
        if len(Alert) == 0:
            Alert = [[]]
    Alert = Alert[0][0]
    if Alert == "": #checks if no alert
        Alert = False

    totalPP = r.get("ripple:total_pp")#Not calculated by every server .decode("utf-8")
    RegisteredUsers = r.get("ripple:registered_users")
    OnlineUsers = r.get("ripple:online_users")


    #If we dont have variable(variable is None) will set it and get it again
    if not totalPP:
        r.set('ripple:total_pp', 0)
        totalPP = r.get("ripple:total_pp")
    if not RegisteredUsers:
        r.set('ripple:registered_users', 1)
        RegisteredUsers = r.get("ripple:registered_users")
    if not OnlineUsers:
        r.set('ripple:online_users', 1)
        RegisteredUsers = r.get("ripple:online_users")
    response = {
        "RegisteredUsers" : totalPP.decode("utf-8") ,
        "OnlineUsers" : OnlineUsers.decode("utf-8") ,
        "TotalPP" :  totalPP.decode("utf-8"),
        "Alert" : Alert
    }
    return response

def LoginHandler(username, password):
    """Checks the passwords and handles the sessions."""
    mycursor.execute(f"SELECT username, password_md5, ban_datetime, privileges, id FROM users WHERE username_safe = '{username.lower()}'")
    User = mycursor.fetchall()
    if len(User) == 0:
        #when user not found
        return [False, "User not found. Maybe a typo?"]
    else:
        User = User[0]
        #Stores grabbed data in variables for easier access
        Username = User[0]
        PassHash = User[1]
        IsBanned = User[2]
        Privilege = User[3]
        id = User = User[4]
        
        #Converts IsBanned to bool
        if IsBanned == "0" or not IsBanned:
            IsBanned = False
        else:
            IsBanned = True

        #shouldve been done during conversion but eh
        if IsBanned:
            return [False, "You are banned... Awkward..."]
        else:
            if HasPrivilege(id):
                if checkpw(PassHash, password):
                    return [True, "You have been logged in!", { #creating session
                        "LoggedIn" : True,
                        "AccountId" : id,
                        "AccountName" : Username,
                        "Privilege" : Privilege,
                        "exp" : datetime.datetime.utcnow() + datetime.timedelta(hours=2) #so the token expires
                    }]
                else:
                     return [False, "Incorrect password"]
            else:
                return [False, "Missing privileges!"]

def TimestampConverter(timestamp):
    """Converts timestamps into readable time."""
    date = datetime.datetime.fromtimestamp(int(timestamp)) #converting into datetime object
    #so we avoid things like 21:6
    hour = str(date.hour)
    minute = str(date.minute)
    #if len(hour) == 1:
        #hour = "0" + hour
    if len(minute) == 1:
        minute = "0" + minute
    return f"{hour}:{minute}"

def RecentPlays():
    """Returns recent plays."""
    #this is probably really bad
    mycursor.execute("SELECT scores.beatmap_md5, users.username, scores.userid, scores.time, scores.score, scores.pp, scores.play_mode, scores.mods FROM scores LEFT JOIN users ON users.id = scores.userid WHERE users.privileges & 1 ORDER BY scores.id DESC LIMIT 10")
    plays = mycursor.fetchall()
    if UserConfig["HasRelax"]:
        #adding relax plays
        mycursor.execute("SELECT scores_relax.beatmap_md5, users.username, scores_relax.userid, scores_relax.time, scores_relax.score, scores_relax.pp, scores_relax.play_mode, scores_relax.mods FROM scores_relax LEFT JOIN users ON users.id = scores_relax.userid WHERE users.privileges & 1 ORDER BY scores_relax.id DESC LIMIT 10")
        playx_rx = mycursor.fetchall()
        for plays_rx in playx_rx:
            #addint them to the list
            plays_rx = list(plays_rx)
            plays_rx.append("RX")
            plays.append(plays_rx)
    PlaysArray = []
    #converting into lists as theyre cooler (and easier to work with)
    for x in plays:
        PlaysArray.append(list(x))

    #converting the data into something readable
    ReadableArray = []
    for x in PlaysArray:
        #yes im doing this
        #lets get the song name
        BeatmapMD5 = x[0]
        mycursor.execute(f"SELECT song_name FROM beatmaps WHERE beatmap_md5 = '{BeatmapMD5}'")
        SongFetch = mycursor.fetchall()
        if len(SongFetch) == 0:
            #checking if none found
            SongName = "Invalid..."
        else:
            SongName = list(SongFetch[0])[0]
        #make and populate a readable dict
        Dicti = {}
        Dicti["Player"] = x[1]
        Dicti["PlayerId"] = x[2]
        #if rx
        if x[-1] == "RX":
            Dicti["SongName"] = SongName + " +Relax"
        else:
            Dicti["SongName"] = SongName
        Dicti["Score"] = f'{x[4]:,}'
        Dicti["pp"] = round(x[5])
        Dicti["Time"] = TimestampConverter(x[3])
        ReadableArray.append(Dicti)
    
    ReadableArray = sorted(ReadableArray, key=lambda k: k["Time"]) #sorting by time
    ReadableArray.reverse()
    return ReadableArray

def FetchBSData():
    """Fetches Bancho Settings."""
    mycursor.execute("SELECT name, value_string, value_int FROM bancho_settings WHERE name = 'bancho_maintenance' OR name = 'menu_icon' OR name = 'login_notification'")
    Query = list(mycursor.fetchall())
    #bancho maintenence
    if Query[0][2] == 0:
        BanchoMan = False
    else:
        BanchoMan = True
    return {
        "BanchoMan" : BanchoMan,
        "MenuIcon" : Query[1][1],
        "LoginNotif" : Query[2][1]
    }

def BSPostHandler(post, session):
    BanchoMan = post[0]
    MenuIcon = post[1]
    LoginNotif = post[2]

    #setting blanks to bools
    if BanchoMan == "On":
        BanchoMan = True
    else:
        BanchoMan = False
    if MenuIcon == "":
        MenuIcon = False
    if LoginNotif == "":
        LoginNotif = False

    #SQL Queries
    if MenuIcon != False: #this might be doable with just if not BanchoMan
        mycursor.execute(f"UPDATE bancho_settings SET value_string = '{MenuIcon}', value_int = 1 WHERE name = 'menu_icon'")
    else:
        mycursor.execute("UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'menu_icon'")

    if LoginNotif != False:
        mycursor.execute(f"UPDATE bancho_settings SET value_string = '{LoginNotif}', value_int = 1 WHERE name = 'login_notification'")
    else:
        mycursor.execute("UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'login_notification'")

    if BanchoMan:
        mycursor.execute("UPDATE bancho_settings SET value_int = 1 WHERE name = 'bancho_maintenance'")
    else:
        mycursor.execute("UPDATE bancho_settings SET value_int = 0 WHERE name = 'bancho_maintenance'")
    
    mydb.commit()
    RAPLog(session["AccountId"], "modified the bancho settings")

def GetBmapInfo(id):
    """Gets beatmap info."""
    mycursor.execute(f"SELECT beatmapset_id FROM beatmaps WHERE beatmap_id = '{id}'")
    Data = mycursor.fetchall()
    if len(Data) == 0:
        #it might be a beatmap set then
        mycursor.execute(f"SELECT song_name, ar, difficulty_std, beatmapset_id, beatmap_id, ranked FROM beatmaps WHERE beatmapset_id = '{id}'")
        BMS_Data = mycursor.fetchall()
        if len(BMS_Data) == 0: #if still havent found anything

            return [{
                "SongName" : "Not Found",
                "Ar" : "0",
                "Difficulty" : "0",
                "BeatmapsetId" : "",
                "BeatmapId" : 0,
                "Cover" : "https://a.ussr.pl/" #why this? idk
            }]
    else:
        BMSID = Data[0][0]
        mycursor.execute(f"SELECT song_name, ar, difficulty_std, beatmapset_id, beatmap_id, ranked FROM beatmaps WHERE beatmapset_id = '{BMSID}'")
        BMS_Data = mycursor.fetchall()
    BeatmapList = []
    for beatmap in BMS_Data:
        thing = { 
            "SongName" : beatmap[0],
            "Ar" : str(beatmap[1]),
            "Difficulty" : str(round(beatmap[2], 2)),
            "BeatmapsetId" : str(beatmap[3]),
            "BeatmapId" : str(beatmap[4]),
            "Ranked" : beatmap[5],
            "Cover" : f"https://assets.ppy.sh/beatmaps/{beatmap[3]}/covers/cover.jpg"
        }
        BeatmapList.append(thing)
    BeatmapList =  sorted(BeatmapList, key = lambda i: i["Difficulty"])
    #assigning each bmap a number to be later used
    BMapNumber = 0
    for beatmap in BeatmapList:
        BMapNumber = BMapNumber + 1
        beatmap["BmapNumber"] = BMapNumber
    return BeatmapList

def HasPrivilege(UserID, ReqPriv = 2):
    """Check if the person trying to access the page has perms to do it."""
    # 0 = no verification
    # 1 = Only registration required
    # 2 = RAP Access Required
    # 3 = Manage beatmaps required
    # 4 = manage settings required
    # 5 = Ban users required
    # 6 = Manage users required
    # 7 = View logs
    # 8 = RealistikPanel Nominate (feature not added yet)
    # 9 = RealistikPanel Nomination Accept (feature not added yet)
    # 10 = RealistikPanel Overwatch (feature not added yet)
    #THIS TOOK ME SO LONG TO FIGURE OUT WTF
    NoPriv = 0
    UserNormal = 2 << 0
    AccessRAP = 2 << 2
    ManageUsers = 2 << 3
    BanUsers = 2 << 4
    SilenceUsers = 2 << 5
    WipeUsers = 2 << 6
    ManageBeatmaps = 2 << 7
    ManageServers = 2 << 8
    ManageSettings = 2 << 9
    ManageBetaKeys = 2 << 10
    ManageReports = 2 << 11
    ManageDocs = 2 << 12
    ManageBadges = 2 << 13
    ViewRAPLogs	= 2 << 14
    ManagePrivileges = 2 << 15
    SendAlerts = 2 << 16
    ChatMod	 = 2 << 17
    KickUsers = 2 << 18
    PendingVerification = 2 << 19
    TournamentStaff  = 2 << 20
    Caker = 2 << 21
    ViewTopScores = 2 << 22
    #RealistikPanel Specific Perms
    RPNominate = 2 << 23
    RPNominateAccept = 2 << 24
    RPOverwatch = 2 << 25

    if ReqPriv == 0: #dont use this like at all
        return True

    #gets users privilege
    try:
        mycursor.execute(f"SELECT privileges FROM users WHERE id = {UserID}")
        Privilege = mycursor.fetchall()[0][0]
    except Exception:
        Privilege = 0

    if ReqPriv == 1:
        result = Privilege & UserNormal
    elif ReqPriv == 2:
        result = Privilege & AccessRAP
    elif ReqPriv == 3:
        result = Privilege & ManageBeatmaps
    elif ReqPriv == 4:
        result = Privilege & ManageSettings
    elif ReqPriv == 5:
        result = Privilege & BanUsers
    elif ReqPriv == 6:
        result = Privilege & ManageUsers
    elif ReqPriv == 7:
        result = Privilege & ViewRAPLogs
    elif ReqPriv == 8:
        result == Privilege & RPNominate
    elif ReqPriv == 9:
        result == Privilege & RPNominateAccept
    elif ReqPriv == 10:
        result == Privilege & RPOverwatch
    
    if result > 1:
        return True
    else:
        return False
    

def RankBeatmap(BeatmapNumber, BeatmapId, ActionName, session):
    """Ranks a beatmap"""
    #converts actions to numbers
    if ActionName == "Loved":
        ActionName = 5
    elif ActionName == "Ranked":
        ActionName = 2
    elif ActionName == "Unranked":
        ActionName = 0
    else:
        print(" Received alien input from rank. what?")
        return
    try:
        mycursor.execute(f"UPDATE beatmaps SET ranked = {ActionName}, ranked_status_freezed = 1 WHERE beatmap_id = {BeatmapId} LIMIT 1")
        mycursor.execute(f"UPDATE scores s JOIN (SELECT userid, MAX(score) maxscore FROM scores JOIN beatmaps ON scores.beatmap_md5 = beatmaps.beatmap_md5 WHERE beatmaps.beatmap_md5 = (SELECT beatmap_md5 FROM beatmaps WHERE beatmap_id = {BeatmapId} LIMIT 1) GROUP BY userid) s2 ON s.score = s2.maxscore AND s.userid = s2.userid SET completed = 3")
        mydb.commit()
        Webhook(BeatmapId, ActionName, session)
        return True
    except Exception as e:
        print(" An error occured while ranking!\n " + str(e))
        return False

def Webhook(BeatmapId, ActionName, session):
    """Beatmap rank webhook."""
    URL = UserConfig["Webhook"]
    if URL == "":
        #if no webhook is set, dont do anything
        return
    headers = {'Content-Type': 'application/json'}
    mycursor.execute(f"SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmap_id = {BeatmapId}")
    mapa = mycursor.fetchall()
    mapa = mapa[0]
    if ActionName == 0:
        TitleText = "unranked :("
    if ActionName == 2:
        TitleText = "ranked!"
    if ActionName == 5:
        TitleText = "loved!"
    webhook = DiscordWebhook(url=URL) #creates webhook
    # me trying to learn the webhook
    #EmbedJson = { #json to be sent to webhook
    #    "image" : f"https://assets.ppy.sh/beatmaps/{mapa[1]}/covers/cover.jpg",
    #    "author" : {
    #        "icon_url" : f"https://a.ussr.pl/{session['AccountId']}",
    #        "url" : f"https://ussr.pl/b/{BeatmapId}",
    #        "name" : f"{mapa[0]} was just {TitleText}"
    #    },
    #    "description" : f"Ranked by {session['AccountName']}",
    #    "footer" : {
    #        "text" : "via RealistikPanel!"
    #    }
    #}
    #requests.post(URL, data=EmbedJson, headers=headers) #sends the webhook data
    embed = DiscordEmbed(description=f"Ranked by {session['AccountName']}", color=242424) #this is giving me discord.py vibes
    embed.set_author(name=f"{mapa[0]} was just {TitleText}", url=f"https://ussr.pl/b/{BeatmapId}", icon_url=f"https://a.ussr.pl/{session['AccountId']}")
    embed.set_footer(text="via RealistikPanel!")
    embed.set_image(url=f"https://assets.ppy.sh/beatmaps/{mapa[1]}/covers/cover.jpg")
    webhook.add_embed(embed)
    print(" * Posting webhook!")
    webhook.execute()
    RAPLog(session["AccountId"], f"ranked/unranked the beatmap {mapa[0]} ({BeatmapId})")

def RAPLog(UserID=999, Text="forgot to assign a text value :/"):
    """Logs to the RAP log."""
    Timestamp = round(time.time())
    #now we putting that in oh yea
    mycursor.execute(f"INSERT INTO rap_logs (userid, text, datetime, through) VALUES ({UserID}, '{Text}', {Timestamp}, 'RealistikPanel!')")
    mydb.commit()

def checkpw(dbpassword, painpassword):
    """
    By: kotypey
    password checking...
    """

    result = hashlib.md5(painpassword.encode()).hexdigest().encode('utf-8')
    dbpassword = dbpassword.encode('utf-8')
    check = bcrypt.checkpw(result, dbpassword)

    return check

def SystemSettingsValues():
    """Fetches the system settings data."""
    mycursor.execute("SELECT value_int, value_string FROM system_settings WHERE name = 'website_maintenance' OR name = 'game_maintenance' OR name = 'website_global_alert' OR name = 'website_home_alert' OR name = 'registrations_enabled'")
    SqlData = mycursor.fetchall()
    return {
        "webman": bool(SqlData[0][0]),
        "gameman" : bool(SqlData[1][0]),
        "register": bool(SqlData[4][0]),
        "globalalert": SqlData[2][1],
        "homealert": SqlData[3][1]
    }

def ApplySystemSettings(DataArray, Session):
    """Does a thing."""
    WebMan = DataArray[0]
    GameMan =DataArray[1]
    Register = DataArray[2]
    GlobalAlert = DataArray[3]
    HomeAlert = DataArray[4]

    #i dont feel like this is the right way to do this but eh
    if WebMan == "On":
        WebMan = 1
    else:
        WebMan = 0
    if GameMan == "On":
        GameMan = 1
    else:
        GameMan = 0
    if Register == "On":
        Register = 1
    else:
        Register = 0
    
    #SQL Queries
    mycursor.execute(f"UPDATE system_settings SET value_int = {WebMan} WHERE name = 'website_maintenance'")
    mycursor.execute(f"UPDATE system_settings SET value_int = {GameMan} WHERE name = 'game_maintenance'")
    mycursor.execute(f"UPDATE system_settings SET value_int = {Register} WHERE name = 'registrations_enabled'")

    #if empty, disable
    if GlobalAlert != "":
        mycursor.execute(f"UPDATE system_settings SET value_int = 1, value_string = '{GlobalAlert}' WHERE name = 'website_global_alert'")
    else:
        mycursor.execute("UPDATE system_settings SET value_int = 0, value_string = '' WHERE name = 'website_global_alert'")
    if HomeAlert != "":
        mycursor.execute(f"UPDATE system_settings SET value_int = 1, value_string = '{HomeAlert}' WHERE name = 'website_home_alert'")
    else:
        mycursor.execute("UPDATE system_settings SET value_int = 0, value_string = '' WHERE name = 'website_home_alert'")
    
    mydb.commit() #applies the changes

def IsOnline(AccountId):
    """Checks if given user is online."""
    return requests.get(url=f"{UserConfig['BanchoURL']}api/v1/isOnline?id={AccountId}").json()["result"]

def CalcPP(BmapID):
    """Sends request to letsapi to calc PP for beatmap id."""
    reqjson = requests.get(url=f"{UserConfig['LetsAPI']}v1/pp?b={BmapID}").json()
    return round(reqjson["pp"][0], 2)

def Unique(Alist):
    """Returns list of unique elements of list."""
    Uniques = []
    for x in Alist:
        if x not in Uniques:
            Uniques.append(x)
    return Uniques

def FetchUsers(page = 0):
    """Fetches users for the users page."""
    #This is going to need a lot of patching up i can feel it
    Offset = UserConfig["PageSize"] * page #for the page system to work
    mycursor.execute(f"SELECT id, username, privileges, allowed FROM users LIMIT {UserConfig['PageSize']} OFFSET {Offset}")
    People = mycursor.fetchall()

    #gets list of all different privileges so an sql select call isnt ran per person
    AllPrivileges = []
    for person in People:
        AllPrivileges.append(person[2])
    UniquePrivileges = Unique(AllPrivileges)

    #How the privilege data will look
    #PrivilegeDict = {
    #    "234543": {
    #        "Name" : "Owner",
    #        "Privileges" : 234543,
    #        "Colour" : "success"
    #    }
    #}
    PrivilegeDict = {}
    #gets all priv info
    for Priv in UniquePrivileges:
        mycursor.execute(f"SELECT name, color FROM privileges_groups WHERE privileges = {Priv} LIMIT 1")
        info = mycursor.fetchall()
        if len(info) == 0:
            PrivilegeDict[str(Priv)] = {
                "Name" : "Unknown",
                "Privileges" : Priv,
                "Colour" : "danger"
            }
        else:
            info = info[0]
            PrivilegeDict[str(Priv)] = {}
            PrivilegeDict[str(Priv)]["Name"] = info[0]
            PrivilegeDict[str(Priv)]["Privileges"] = Priv
            PrivilegeDict[str(Priv)]["Colour"] = info[1]

    #Convierting user data into cool dicts
    #Structure
    #[
    #    {
    #        "Id" : 999,
    #        "Name" : "RealistikDash",
    #        "Privilege" : PrivilegeDict["234543"],
    #        "Allowed" : True
    #    }
    #]
    Users = []
    for user in People:
        Dict = {
            "Id" : user[0],
            "Name" : user[1],
            "Privilege" : PrivilegeDict[str(user[2])]
        }
        if user[3] == 1:
            Dict["Allowed"] = True
        else:
            Dict["Allowed"] = False
        Users.append(Dict)
    
    return Users

def GetUser(id):
    """Gets data for user. (universal)"""
    mycursor.execute(f"SELECT id, username, pp_std, country FROM users_stats WHERE id = {id} LIMIT 1")
    User = mycursor.fetchall()[0]
    return {
        "Id" : User[0],
        "Username" : User[1],
        "pp" : User[2],
        "IsOnline" : IsOnline(id),
        "Country" : User[3]
    }

def UserData(id):
    """Gets data for user. (specialised for user edit page)"""
    Data = GetUser(id)
    mycursor.execute(f"SELECT userpage_content, user_color, username_aka FROM users_stats WHERE id = {id} LIMIT 1")# Req 1
    Data1 = mycursor.fetchall()[0]
    mycursor.execute(f"SELECT email, register_datetime, privileges, notes, donor_expire, silence_end, silence_reason FROM users WHERE id = {id} LIMIT 1")
    Data2 = mycursor.fetchall()[0]
    #Fetches the IP
    mycursor.execute(f"SELECT ip FROM ip_user WHERE userid = {id} LIMIT 1")
    try:
        Ip = mycursor.fetchall()[0][0]
    except Exception:
        Ip = "0.0.0.0"
    #adds new info to dict
    #I dont use the discord features from RAP so i didnt include the discord settings but if you complain enough ill add them
    Data["UserpageContent"] = Data1[0]
    Data["UserColour"] = Data1[1]
    Data["Aka"] = Data1[2]
    Data["Email"] = Data2[0]
    Data["RegisterTime"] = Data2[1]
    Data["Privileges"] = Data2[2]
    Data["Notes"] = Data2[3]
    Data["DonorExpire"] = Data2[4]
    Data["SilenceEnd"] = Data[5]
    Data["SilenceReason"] = Data[6]
    Data["Avatar"] = UserConfig["AvatarServer"] + str(id)
    Data["Ip"] = Ip
    return Data

def RAPFetch(page = 1):
    """Fetches RAP Logs."""
    page = int(page) - 1 #makes sure is int and is in ok format
    Offset = UserConfig["PageSize"] * page
    mycursor.execute(f"SELECT * FROM rap_logs ORDER BY id DESC LIMIT {UserConfig['PageSize']} OFFSET {Offset}")
    Data = mycursor.fetchall()

    #Gets list of all users
    Users = []
    for dat in Data:
        if dat[1] not in Users:
            Users.append(dat[1])
    #gets all unique users so a ton of lookups arent made
    UniqueUsers = Unique(Users)

    #now we get basic data for each user
    UserDict = {}
    for user in UniqueUsers:
        UserData = GetUser(user)
        UserDict[str(user)] = UserData
    
    #log structure
    #[
    #    {
    #        "LogId" : 1337,
    #        "AccountData" : 1000,
    #        "Text" : "did a thing",
    #        "Via" : "RealistikPanel",
    #        "Time" : 18932905234
    #    }
    #]
    LogArray = []
    for log in Data:
        #we making it into cool dicts
        #getting the acc data
        LogUserData = UserDict[str(log[1])]
        TheLog = {
            "LogId" : log[0],
            "AccountData" : LogUserData,
            "Text" : log[2],
            "Time" : TimestampConverter(log[3]),
            "Via" : log[4]
        }
        LogArray.append(TheLog)
    return LogArray
