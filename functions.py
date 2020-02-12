#This file is responsible for all the functionality
from config import *
import mysql.connector
from colorama import init, Fore
import redis
import bcrypt

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
            if bcrypt.checkpw(password, PassHash):
                return [True, "You have been logged in!"]
            else:
                return [False, "Incorect password."]