#This file is responsible for all the functionality
from config import *
import mysql.connector
from colorama import init, Fore
import redis

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
    """Grabs all the values for the dashboard"""
    mycursor.execute("SELECT * FROM system_settings")
    Alert = mycursor.fetchall()[2][2] #Not the best way but it's fast!!
    if Alert == "":
        Alert = False
    response = {
        "RegisteredUsers" : str(r.get("ripple:registered_users")),
        "OnlineUsers" : str(r.get("ripple:online_users")),
        "Alert" : Alert
    }
    return response