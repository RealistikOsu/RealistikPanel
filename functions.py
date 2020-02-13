#This file is responsible for all the functionality
from config import *
import mysql.connector
from colorama import init, Fore
import redis
import bcrypt
import datetime

init() #initialises colorama for colours

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
    """Grabs all the values for the dashboard"""
    mycursor.execute("SELECT * FROM system_settings")
    Alert = mycursor.fetchall()[2][3] #Not the best way but it's fast!!
    if Alert == "": #checks if no aler
        Alert = False
    response = {
        "RegisteredUsers" : r.get("ripple:registered_users").decode("utf-8") ,
        "OnlineUsers" : r.get("ripple:online_users").decode("utf-8") ,
        "Alert" : Alert
    }
    return response

def LoginHandler(username, password):
    """Checks the passwords and handles the sessions"""
    mycursor.execute(f"SELECT username, password_md5, ban_datetime FROM users WHERE username_safe = '{username.lower()}'")
    User = mycursor.fetchall()
    if len(User) == 0:
        #when user not found
        return [False, "Not Found"]
    else:
        User = User[0]
        #Stores grabbed data in variables for easier access
        Username = User[0]
        PassHash = User[1]
        IsBanned = User[2]
        
        #Converts IsBanned to bool
        if IsBanned == "0":
            IsBanned = False
        else:
            IsBanned = True
        
        #shouldve been done during conversion but eh
        if IsBanned:
            return [False, "You are banned... Awkward..."]
        else:
            #nice
            if bcrypt.checkpw(password.encode('utf-8'), PassHash.encode('utf-8')):
                return [True, "You have been logged in!"]
            else:
                return [False, "Incorect password."]

def TimestampConverter(timestamp):
    """Converts timestamps into readable time"""
    date = datetime.datetime.fromtimestamp(int(timestamp)) #converting into datetime object
    #so we avoid things like 21:6
    hour = str(date.hour)
    minute = str(date.minute)
    if len(hour) == 1:
        hour = "0" + hour
    if len(minute) == 1:
        minute = "0" + minute
    return f"{hour}:{minute}"

def RecentPlays():
    """Returns recent plays"""
    #this is probably really bad
    mycursor.execute("SELECT scores.beatmap_md5, users.username, scores.userid, scores.time, scores.score, scores.pp, scores.play_mode, scores.mods FROM scores LEFT JOIN users ON users.id = scores.userid WHERE users.privileges & 1 ORDER BY scores.id DESC LIMIT 10")
    plays = mycursor.fetchall()
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
        Dicti["SongName"] = SongName
        Dicti["Score"] = f'{x[4]:,}'
        Dicti["pp"] = x[5]
        Dicti["Time"] = TimestampConverter(x[3])
        ReadableArray.append(Dicti)
    
    return ReadableArray

def FetchBSData():
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

def BSPostHandler(post):
    pass

def GetBmapInfo(id):
    """Gets beatmap info"""
    mycursor.execute(f"SELECT song_name, ar, difficulty_std, beatmapset_id FROM beatmaps WHERE beatmap_id = '{id}'")
    Data = mycursor.fetchall()
    if len(Data) == 0:
        return {
            "SongName" : "Not Found",
            "Ar" : "0",
            "Difficulty" : "0",
            "BeatmapsetId" : "",
            "Cover" : "https://a.ussr.pl/" #why this? idk
        }
    else:
        Data = Data[0]
        return {
            "SongName" : Data[0],
            "Ar" : str(Data[1]),
            "Difficulty" : str(Data[2]),
            "BeatmapsetId" : str(Data[3]),
            "Cover" : f"https://assets.ppy.sh/beatmaps/{Data[3]}/covers/cover.jpg"
        }