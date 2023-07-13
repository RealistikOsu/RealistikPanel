# Legacy panel functionality! DO NOT extend.
from __future__ import annotations

import datetime
import hashlib
import json
import math
import random
import string
import time
import traceback
from typing import NamedTuple
from typing import TypedDict
from typing import Union

import bcrypt
import mysql.connector
import pycountry
import redis
import requests
import timeago
from discord_webhook import DiscordEmbed
from discord_webhook import DiscordWebhook

from panel import logger
from panel.common.cryprography import compare_password
from panel.common.time import timestamp_as_date
from panel.common.utils import decode_int_or
from panel.common.utils import halve_list
from panel.config import config
from panel.constants.privileges import Privileges

try:
    mydb = mysql.connector.connect(
        host=config.sql_host,
        port=config.sql_port,
        user=config.sql_user,
        passwd=config.sql_password,
        db=config.sql_database,
    )
    logger.info(f"Successfully connected to MySQL!")
    mydb.autocommit = True
except Exception:
    logger.error(
        f"Failed connecting to MySQL! Abandoning!\n" + traceback.format_exc(),
    )
    exit()

try:
    r = redis.Redis(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
        db=config.redis_db,
    )
    logger.info(f"Successfully connected to Redis!")
except Exception:
    logger.error(
        f"Failed connecting to Redis! Abandoning!\n" + traceback.format_exc(),
    )
    exit()

mycursor = mydb.cursor(
    buffered=True,
)
mycursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")

# fix potential crashes
# have to do it this way as the crash issue is a connector module issue
mycursor.execute("SELECT COUNT(*) FROM users_stats WHERE userpage_content = ''")
BadUserCount = mycursor.fetchone()[0]
if BadUserCount > 0:
    logger.warning(
        f"Found {BadUserCount} users with potentially problematic data!",
    )
    mycursor.execute(
        "UPDATE users_stats SET userpage_content = NULL WHERE userpage_content = ''",
    )
    mydb.commit()
    logger.info("Fixed problematic data!")

# public variables
PlayerCount = []  # list of players


def load_dashboard_data() -> dict:
    """Grabs all the values for the dashboard."""
    mycursor.execute(
        "SELECT value_string FROM system_settings WHERE name = 'website_global_alert'",
    )
    alert = mycursor.fetchone()
    if alert is None:
        alert_message = None
    else:
        alert_message = alert[0]

    total_pp = decode_int_or(r.get("ripple:total_pp"))
    registered_users = decode_int_or(r.get("ripple:registered_users"))
    online_users = decode_int_or(r.get("ripple:online_users"))
    total_plays = decode_int_or(r.get("ripple:total_plays"))
    total_scores = decode_int_or(r.get("ripple:total_submitted_scores"))

    response = {
        "RegisteredUsers": registered_users,
        "OnlineUsers": online_users,
        "TotalPP": f"{total_pp:,}",
        "TotalPlays": f"{total_plays:,}",
        "TotalScores": f"{total_scores:,}",
        "Alert": alert_message,
    }
    return response


USER_NOT_FOUND_ERROR = "The user was not found. Maybe you have made a typo?"
USER_BANNED_ERROR = "You appear to be banned. Yikes."
USER_PASSWORD_ERROR = "The password you entered is incorrect."
USER_PRIVILEGE_ERROR = "You do not have the required privileges to access this page."


class LoginUserData(NamedTuple):
    user_id: int
    username: str
    privileges: Privileges


def LoginHandler(
    username: str,
    password: str,
) -> tuple[bool, Union[str, LoginUserData]]:
    """Checks the passwords and handles the sessions."""
    mycursor.execute(
        "SELECT username, password_md5, privileges, id FROM users WHERE username_safe = %s LIMIT 1",
        (RippleSafeUsername(username),),
    )
    user = mycursor.fetchone()
    if user is None:
        # when user not found
        return False, USER_NOT_FOUND_ERROR
    else:
        (
            username,
            password_md5,
            privileges,
            user_id,
        ) = user

        # dont  allow the bot account to log in (in case the server has a MASSIVE loophole)
        if user_id == 999:
            return False, USER_NOT_FOUND_ERROR

        if has_privilege_value(user_id, Privileges.ADMIN_ACCESS_RAP):
            if compare_password(password, password_md5):
                return (
                    True,
                    LoginUserData(
                        user_id,
                        username,
                        Privileges(privileges),
                    ),
                )
            else:
                return False, USER_PASSWORD_ERROR
        else:
            return False, USER_PRIVILEGE_ERROR


BASE_RECENT_QUERY = """
SELECT
    s.beatmap_md5, u.username, s.userid, s.time, s.score, s.pp,
    s.play_mode, s.mods, s.300_count, s.100_count, s.50_count,
    s.misses_count, b.song_name
FROM {} s
INNER JOIN users u ON u.id = s.userid
INNER JOIN beatmaps b ON b.beatmap_md5 = s.beatmap_md5
WHERE
    u.privileges & 1 AND s.pp >= %s
ORDER BY s.id DESC
LIMIT %s
"""


def get_recent_plays(total_plays: int = 20, minimum_pp: int = 0):
    """Returns recent plays."""
    divisor = 1
    if config.srv_supports_relax:
        divisor += 1
    if config.srv_supports_autopilot:
        divisor += 1
    plays_per_gamemode = total_plays // divisor

    mycursor.execute(
        BASE_RECENT_QUERY.format("scores"),
        (
            minimum_pp,
            plays_per_gamemode,
        ),
    )
    plays = mycursor.fetchall()
    if config.srv_supports_relax:
        # adding relax plays
        mycursor.execute(
            BASE_RECENT_QUERY.format("scores_relax"),
            (
                minimum_pp,
                plays_per_gamemode,
            ),
        )
        playx_rx = mycursor.fetchall()
        for plays_rx in playx_rx:
            # addint them to the list
            plays_rx = list(plays_rx)
            plays.append(plays_rx)
    if config.srv_supports_autopilot:
        # adding relax plays
        mycursor.execute(
            BASE_RECENT_QUERY.format("scores_ap"),
            (
                minimum_pp,
                plays_per_gamemode,
            ),
        )
        playx_ap = mycursor.fetchall()
        for plays_ap in playx_ap:
            # addint them to the list
            plays_ap = list(plays_ap)
            plays.append(plays_ap)

    # converting the data into something readable
    ReadableArray = []
    for x in plays:
        # yes im doing this
        # lets get the song name
        BeatmapMD5 = x[0]
        SongName = x[12]
        # make and populate a readable dict
        Dicti = {}
        Mods = ModToText(x[7])
        if Mods == "":
            Dicti["SongName"] = SongName
        else:
            Dicti["SongName"] = SongName + " +" + Mods
        Dicti["Player"] = x[1]
        Dicti["PlayerId"] = x[2]
        Dicti["Score"] = f"{x[4]:,}"
        Dicti["pp"] = round(x[5], 2)
        Dicti["Timestamp"] = x[3]
        Dicti["Time"] = timestamp_as_date(int(x[3]))
        Dicti["Accuracy"] = round(GetAccuracy(x[8], x[9], x[10], x[11]), 2)
        ReadableArray.append(Dicti)

    return ReadableArray


def FetchBSData() -> dict:
    """Fetches Bancho Settings."""
    mycursor.execute(
        "SELECT name, value_string, value_int FROM bancho_settings WHERE name = 'bancho_maintenance' OR name = 'menu_icon' OR name = 'login_notification'",
    )

    result_map = {res[0]: res[1:] for res in mycursor}

    return {
        "BanchoMan": bool(result_map["bancho_maintenance"][1]),
        "MenuIcon": result_map["menu_icon"][0],
        "LoginNotif": result_map["login_notification"][0],
    }


def handle_bancho_settings_edit(
    bancho_maintenence: str,
    menu_icon: str,
    login_notification: str,
    user_id: int,
) -> None:
    # setting blanks to bools
    bancho_maintenence = bancho_maintenence == "On"

    # SQL Queries
    if menu_icon:
        mycursor.execute(
            "UPDATE bancho_settings SET value_string = %s, value_int = 1 WHERE name = 'menu_icon'",
            (menu_icon,),
        )
    else:
        mycursor.execute(
            "UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'menu_icon'",
        )

    if login_notification:
        mycursor.execute(
            "UPDATE bancho_settings SET value_string = %s, value_int = 1 WHERE name = 'login_notification'",
            (login_notification,),
        )
    else:
        mycursor.execute(
            "UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'login_notification'",
        )

    mycursor.execute(
        "UPDATE bancho_settings SET value_int = %s WHERE name = 'bancho_maintenance'",
        (int(bancho_maintenence),),
    )

    mydb.commit()
    RAPLog(user_id, "modified the bancho settings")


def GetBmapInfo(id):
    """Gets beatmap info."""
    mycursor.execute("SELECT beatmapset_id FROM beatmaps WHERE beatmap_id = %s", (id,))
    Data = mycursor.fetchall()
    if len(Data) == 0:
        # it might be a beatmap set then
        mycursor.execute(
            "SELECT song_name, ar, difficulty_std, beatmapset_id, beatmap_id, ranked FROM beatmaps WHERE beatmapset_id = %s",
            (id,),
        )
        BMS_Data = mycursor.fetchall()
        if len(BMS_Data) == 0:  # if still havent found anything

            return [
                {
                    "SongName": "Not Found",
                    "Ar": "0",
                    "Difficulty": "0",
                    "BeatmapsetId": "",
                    "BeatmapId": 0,
                    "Cover": "https://a.ussr.pl/",  # why this%s idk
                },
            ]
    else:
        BMSID = Data[0][0]
        mycursor.execute(
            "SELECT song_name, ar, difficulty_std, beatmapset_id, beatmap_id, ranked FROM beatmaps WHERE beatmapset_id = %s",
            (BMSID,),
        )
        BMS_Data = mycursor.fetchall()
    BeatmapList = []
    for beatmap in BMS_Data:
        thing = {
            "SongName": beatmap[0],
            "Ar": str(beatmap[1]),
            "Difficulty": str(round(beatmap[2], 2)),
            "BeatmapsetId": str(beatmap[3]),
            "BeatmapId": str(beatmap[4]),
            "Ranked": beatmap[5],
            "Cover": f"https://assets.ppy.sh/beatmaps/{beatmap[3]}/covers/cover.jpg",
        }
        BeatmapList.append(thing)
    BeatmapList = sorted(BeatmapList, key=lambda i: i["Difficulty"])
    # assigning each bmap a number to be later used
    BMapNumber = 0
    for beatmap in BeatmapList:
        BMapNumber = BMapNumber + 1
        beatmap["BmapNumber"] = BMapNumber
    return BeatmapList


def has_privilege_value(user_id: int, privilege: Privileges) -> bool:
    # Fetch privileges from database.
    mycursor.execute("SELECT privileges FROM users WHERE id = %s", (user_id,))
    res = mycursor.fetchone()
    if res is None:
        return False
    user_privileges = Privileges(res[0])

    return user_privileges & privilege == privilege


def HasPrivilege(UserID: int, ReqPriv=2):
    """Check if the person trying to access the page has perms to do it."""
    # tbh i shouldve done it where you pass the priv enum instead

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
    # 11 = Wipe account required
    # 12 = Kick users required
    # 13 = Manage Privileges
    # 14 = View RealistikPanel error/console logs
    # 15 = Manage Clans (RealistikPanel specific permission)
    # 16 = View IPs in manage users
    # THIS TOOK ME SO LONG TO FIGURE OUT WTF
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
    ViewRAPLogs = 2 << 14
    ManagePrivileges = 2 << 15
    SendAlerts = 2 << 16
    ChatMod = 2 << 17
    KickUsers = 2 << 18
    PendingVerification = 2 << 19
    TournamentStaff = 2 << 20
    Caker = 2 << 21
    ViewTopScores = 2 << 22
    # RealistikPanel Specific Perms
    RPNominate = 2 << 23
    RPNominateAccept = 2 << 24
    RPOverwatch = 2 << 25
    RPErrorLogs = 2 << 26
    RPManageClans = 2 << 27
    RPViewIPs = 2 << 28

    if ReqPriv == 0:  # dont use this like at all
        return True

    # gets users privilege
    mycursor.execute("SELECT privileges FROM users WHERE id = %s", (UserID,))
    Privilege = mycursor.fetchall()
    if len(Privilege) == 0:
        Privilege = 0
    else:
        Privilege = Privilege[0][0]

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
        result = Privilege & RPNominate
    elif ReqPriv == 9:
        result = Privilege & RPNominateAccept
    elif ReqPriv == 10:
        result = Privilege & RPOverwatch
    elif ReqPriv == 11:
        result = Privilege & WipeUsers
    elif ReqPriv == 12:
        result = Privilege & KickUsers
    elif ReqPriv == 13:
        result = Privilege & ManagePrivileges
    elif ReqPriv == 14:
        result = Privilege & RPErrorLogs
    elif ReqPriv == 15:
        result = Privilege & RPManageClans
    elif ReqPriv == 16:
        result = Privilege & RPViewIPs

    if result >= 1:
        return True
    else:
        return False


def RankBeatmap(BeatmapNumber, BeatmapId, ActionName, session):
    """Ranks a beatmap"""
    # converts actions to numbers
    if ActionName == "Loved":
        ActionName = 5
    elif ActionName == "Ranked":
        ActionName = 2
    elif ActionName == "Unranked":
        ActionName = 0
    else:
        logger.debug("Malformed action name input.")
        return
    mycursor.execute(
        "UPDATE beatmaps SET ranked = %s, ranked_status_freezed = 1 WHERE beatmap_id = %s LIMIT 1",
        (
            ActionName,
            BeatmapId,
        ),
    )
    # mycursor.execute("UPDATE scores s JOIN (SELECT userid, MAX(score) maxscore FROM scores JOIN beatmaps ON scores.beatmap_md5 = beatmaps.beatmap_md5 WHERE beatmaps.beatmap_md5 = (SELECT beatmap_md5 FROM beatmaps WHERE beatmap_id = %s LIMIT 1) GROUP BY userid) s2 ON s.score = s2.maxscore AND s.userid = s2.userid SET completed = 3", (BeatmapId,))
    mydb.commit()
    Webhook(BeatmapId, ActionName, session)

    # USSR SUPPORT.
    mycursor.execute(
        "SELECT beatmap_md5 FROM beatmaps WHERE beatmap_id = %s LIMIT 1",
        (BeatmapId,),
    )
    md5: str = mycursor.fetchone()[0]
    refresh_bmap(md5)


def FokaMessage(params) -> None:
    """Sends a fokabot message."""
    requests.get(config.api_bancho_url + "api/v1/fokabotMessage", params=params)


def Webhook(BeatmapId, ActionName, session):
    """Beatmap rank webhook."""
    URL = config.webhook_ranked
    if URL == "":
        # if no webhook is set, dont do anything
        return
    mycursor.execute(
        "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmap_id = %s",
        (BeatmapId,),
    )
    mapa = mycursor.fetchall()
    mapa = mapa[0]
    if ActionName == 0:
        TitleText = "unranked..."
    if ActionName == 2:
        TitleText = "ranked!"
    if ActionName == 5:
        TitleText = "loved!"
    webhook = DiscordWebhook(url=URL)  # creates webhook
    embed = DiscordEmbed(
        description=f"Ranked by {session['AccountName']}",
        color=242424,
    )  # this is giving me discord.py vibes
    embed.set_author(
        name=f"{mapa[0]} was just {TitleText}",
        url=config.srv_url + "b/{BeatmapId}",
        icon_url=f"{config.api_avatar_url}{session['AccountId']}",
    )
    embed.set_footer(text="via RealistikPanel!")
    embed.set_image(url=f"https://assets.ppy.sh/beatmaps/{mapa[1]}/covers/cover.jpg")
    webhook.add_embed(embed)
    logger.info("Posting webhook....")
    webhook.execute()
    if ActionName == 0:
        Logtext = "unranked"
    if ActionName == 2:
        Logtext = "ranked"
    if ActionName == 5:
        Logtext = "loved"
    RAPLog(session["AccountId"], f"{Logtext} the beatmap {mapa[0]} ({BeatmapId})")
    ingamemsg = f"[https://{config.srv_url}u/{session['AccountId']} {session['AccountName']}] {Logtext.lower()} the map [https://osu.ppy.sh/b/{BeatmapId} {mapa[0]}]"
    params = {"k": config.api_foka_key, "to": "#announce", "msg": ingamemsg}
    FokaMessage(params)


def RAPLog(UserID=999, Text="forgot to assign a text value :/"):
    """Logs to the RAP log."""
    Timestamp = round(time.time())
    # now we putting that in oh yea
    mycursor.execute(
        "INSERT INTO rap_logs (userid, text, datetime, through) VALUES (%s, %s, %s, 'RealistikPanel!')",
        (
            UserID,
            Text,
            Timestamp,
        ),
    )
    mydb.commit()
    # webhook time
    if config.webhook_admin_log:
        Username = GetUser(UserID)["Username"]
        webhook = DiscordWebhook(config.webhook_admin_log)
        embed = DiscordEmbed(description=f"{Username} {Text}", color=242424)
        embed.set_footer(text="RealistikPanel Admin Logs")
        embed.set_author(
            name=f"New action done by {Username}!",
            url=f"{config.srv_url}u/{UserID}",
            icon_url=f"{config.api_avatar_url}{UserID}",
        )
        webhook.add_embed(embed)
        webhook.execute()


def SystemSettingsValues():
    """Fetches the system settings data."""
    mycursor.execute(
        "SELECT value_int, value_string FROM system_settings WHERE name = 'website_maintenance' OR name = 'game_maintenance' OR name = 'website_global_alert' OR name = 'website_home_alert' OR name = 'registrations_enabled'",
    )
    SqlData = mycursor.fetchall()
    return {
        "webman": bool(SqlData[0][0]),
        "gameman": bool(SqlData[1][0]),
        "register": bool(SqlData[4][0]),
        "globalalert": SqlData[2][1],
        "homealert": SqlData[3][1],
    }


def ApplySystemSettings(DataArray, user_id: int):
    """Applies system settings."""
    WebMan = DataArray[0]
    GameMan = DataArray[1]
    Register = DataArray[2]
    GlobalAlert = DataArray[3]
    HomeAlert = DataArray[4]

    # i dont feel like this is the right way to do this but eh
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

    # SQL Queries
    mycursor.execute(
        "UPDATE system_settings SET value_int = %s WHERE name = 'website_maintenance'",
        (WebMan,),
    )
    mycursor.execute(
        "UPDATE system_settings SET value_int = %s WHERE name = 'game_maintenance'",
        (GameMan,),
    )
    mycursor.execute(
        "UPDATE system_settings SET value_int = %s WHERE name = 'registrations_enabled'",
        (Register,),
    )

    # if empty, disable
    if GlobalAlert != "":
        mycursor.execute(
            "UPDATE system_settings SET value_int = 1, value_string = %s WHERE name = 'website_global_alert'",
            (GlobalAlert,),
        )
    else:
        mycursor.execute(
            "UPDATE system_settings SET value_int = 0, value_string = '' WHERE name = 'website_global_alert'",
        )
    if HomeAlert != "":
        mycursor.execute(
            "UPDATE system_settings SET value_int = 1, value_string = %s WHERE name = 'website_home_alert'",
            (HomeAlert,),
        )
    else:
        mycursor.execute(
            "UPDATE system_settings SET value_int = 0, value_string = '' WHERE name = 'website_home_alert'",
        )

    mydb.commit()  # applies the changes
    RAPLog(user_id, "updated the system settings.")


def IsOnline(AccountId: int) -> bool:
    """Checks if given user is online."""
    try:
        Online = requests.get(
            url=f"{config.api_bancho_url}api/v1/isOnline?id={AccountId}",
        ).json()
        if Online["status"] == 200:
            return Online["result"]
        else:
            return False
    except Exception:
        return False


def CalcPP(BmapID):
    """Sends request to letsapi to calc PP for beatmap id."""
    reqjson = requests.get(url=f"{config.api_lets_url}v1/pp?b={BmapID}").json()
    return round(reqjson["pp"][0], 2)


def CalcPPDT(BmapID):
    """Sends request to letsapi to calc PP for beatmap id with the double time mod."""
    reqjson = requests.get(url=f"{config.api_lets_url}v1/pp?b={BmapID}&m=64").json()
    return round(reqjson["pp"][0], 2)


def Unique(Alist):
    """Returns list of unique elements of list."""
    Uniques = []
    for x in Alist:
        if x not in Uniques:
            Uniques.append(x)
    return Uniques


def FetchUsers(page=0):
    """Fetches users for the users page."""
    # This is going to need a lot of patching up i can feel it
    Offset = 50 * page  # for the page system to work
    mycursor.execute(
        "SELECT id, username, privileges, allowed, country FROM users LIMIT 50 OFFSET %s",
        (Offset,),
    )
    People = mycursor.fetchall()

    # gets list of all different privileges so an sql select call isnt ran per person
    AllPrivileges = []
    for person in People:
        AllPrivileges.append(person[2])
    UniquePrivileges = Unique(AllPrivileges)

    # How the privilege data will look
    # PrivilegeDict = {
    #    "234543": {
    #        "Name" : "Owner",
    #        "Privileges" : 234543,
    #        "Colour" : "success"
    #    }
    # }
    PrivilegeDict = {}
    # gets all priv info
    for Priv in UniquePrivileges:
        mycursor.execute(
            "SELECT name, color FROM privileges_groups WHERE privileges = %s LIMIT 1",
            (Priv,),
        )
        info = mycursor.fetchall()
        if len(info) == 0:
            PrivilegeDict[str(Priv)] = {
                "Name": f"Unknown ({Priv})",
                "Privileges": Priv,
                "Colour": "danger",
            }
        else:
            info = info[0]
            PrivilegeDict[str(Priv)] = {}
            PrivilegeDict[str(Priv)]["Name"] = info[0]
            PrivilegeDict[str(Priv)]["Privileges"] = Priv
            PrivilegeDict[str(Priv)]["Colour"] = info[1]
            if (
                PrivilegeDict[str(Priv)]["Colour"] == "default"
                or PrivilegeDict[str(Priv)]["Colour"] == ""
            ):
                # stisla doesnt have a default button so ill hard-code change it to a warning
                PrivilegeDict[str(Priv)]["Colour"] = "warning"

    # Convierting user data into cool dicts
    # Structure
    # [
    #    {
    #        "Id" : 999,
    #        "Name" : "RealistikDash",
    #        "Privilege" : PrivilegeDict["234543"],
    #        "Allowed" : True
    #    }
    # ]
    Users = []
    for user in People:
        Dict = {
            "Id": user[0],
            "Name": user[1],
            "Privilege": PrivilegeDict[str(user[2])],
            "Country": user[4],
        }
        if user[3] == 1:
            Dict["Allowed"] = True
        else:
            Dict["Allowed"] = False
        Users.append(Dict)

    return Users


def GetUser(id):
    """Gets data for user. (universal)"""
    mycursor.execute(
        "SELECT id, username, country FROM users WHERE id = %s LIMIT 1",
        (id,),
    )
    User = mycursor.fetchone()
    if User == None:
        # if no one found
        return {
            "Id": 0,
            "Username": "Not Found",
            "IsOnline": False,
            "Country": "GB",  # RULE BRITANNIA
        }
    return {
        "Id": User[0],
        "Username": User[1],
        "IsOnline": IsOnline(id),
        "Country": User[2],
    }


def UserData(UserID):
    """Gets data for user (specialised for user edit page)."""
    # fix badbad data
    mycursor.execute(
        "UPDATE users_stats SET userpage_content = NULL WHERE userpage_content = '' AND id = %s",
        (UserID,),
    )
    mydb.commit()
    Data = GetUser(UserID)
    mycursor.execute(
        "SELECT userpage_content, user_color, username_aka FROM users_stats WHERE id = %s LIMIT 1",
        (UserID,),
    )  # Req 1
    Data1 = mycursor.fetchone()
    mycursor.execute(
        "SELECT email, register_datetime, privileges, notes, donor_expire, silence_end, silence_reason, ban_datetime, bypass_hwid, ban_reason FROM users WHERE id = %s LIMIT 1",
        (UserID,),
    )
    Data2 = mycursor.fetchone()
    # Fetches the IP
    mycursor.execute("SELECT ip FROM ip_user WHERE userid = %s LIMIT 1", (UserID,))
    Ip = mycursor.fetchone()
    if Ip == None:
        Ip = "0.0.0.0"
    else:
        Ip = Ip[0]
    # gets privilege name
    mycursor.execute(
        "SELECT name FROM privileges_groups WHERE privileges = %s LIMIT 1",
        (Data2[2],),
    )
    PrivData = mycursor.fetchone()
    if PrivData == None:
        PrivData = [[f"Unknown ({Data2[2]})"]]
    # adds new info to dict
    # I dont use the discord features from RAP so i didnt include the discord settings but if you complain enough ill add them
    try:
        mycursor.execute(
            "SELECT freezedate FROM users WHERE id = %s LIMIT 1",
            (UserID,),
        )
        Freeze = mycursor.fetchone()
    except:
        Freeze = False

    Data["UserpageContent"] = Data1[0]
    Data["UserColour"] = Data1[1]
    Data["Aka"] = Data1[2]
    Data["Email"] = Data2[0]
    Data["RegisterTime"] = Data2[1]
    Data["Privileges"] = Data2[2]
    Data["Notes"] = Data2[3]
    Data["DonorExpire"] = Data2[4]
    Data["SilenceEnd"] = Data2[5]
    Data["SilenceReason"] = Data2[6]
    Data["Avatar"] = config.api_avatar_url + str(UserID)
    Data["Ip"] = Ip
    Data["CountryFull"] = GetCFullName(Data["Country"])
    Data["PrivName"] = PrivData[0]
    Data["BypassHWID"] = Data2[8]
    Data["BanReason"] = Data2[9]

    Data["HasSupporter"] = Data["Privileges"] & 4
    Data["DonorExpireStr"] = TimeToTimeAgo(Data["DonorExpire"])

    # now for silences and ban times
    Data["IsBanned"] = CoolerInt(Data2[7]) > 0
    Data["BanedAgo"] = TimeToTimeAgo(CoolerInt(Data2[7]))
    Data["IsSilenced"] = CoolerInt(Data2[5]) > round(time.time())
    Data["SilenceEndAgo"] = TimeToTimeAgo(CoolerInt(Data2[5]))
    if Freeze:
        Data["IsFrozen"] = int(Freeze[0]) > 0
        Data["FreezeDateNo"] = int(Freeze[0])
        Data["FreezeDate"] = TimeToTimeAgo(Data["FreezeDateNo"])
    else:
        Data["IsFrozen"] = False

    # removing "None" from user page and admin notes
    if Data["Notes"] == None:
        Data["Notes"] = ""
    if Data["UserpageContent"] == None:
        Data["UserpageContent"] = ""
    return Data


def RAPFetch(page=1):
    """Fetches RAP Logs."""
    page = int(page) - 1  # makes sure is int and is in ok format
    Offset = 50 * page
    mycursor.execute(
        "SELECT * FROM rap_logs ORDER BY id DESC LIMIT 50 OFFSET %s",
        (Offset,),
    )
    Data = mycursor.fetchall()

    # Gets list of all users
    Users = []
    for dat in Data:
        if dat[1] not in Users:
            Users.append(dat[1])
    # gets all unique users so a ton of lookups arent made
    UniqueUsers = Unique(Users)

    # now we get basic data for each user
    UserDict = {}
    for user in UniqueUsers:
        UserData = GetUser(user)
        UserDict[str(user)] = UserData

    # log structure
    # [
    #    {
    #        "LogId" : 1337,
    #        "AccountData" : 1000,
    #        "Text" : "did a thing",
    #        "Via" : "RealistikPanel",
    #        "Time" : 18932905234
    #    }
    # ]
    LogArray = []
    for log in Data:
        # we making it into cool dicts
        # getting the acc data
        LogUserData = UserDict[str(log[1])]
        TheLog = {
            "LogId": log[0],
            "AccountData": LogUserData,
            "Text": log[2],
            "Time": timestamp_as_date(log[3], False),
            "Via": log[4],
        }
        LogArray.append(TheLog)
    return LogArray


def GetCFullName(ISO3166):
    """Gets the full name of the country provided."""
    Country = pycountry.countries.get(alpha_2=ISO3166)
    try:
        CountryName = Country.name
    except:
        CountryName = "Unknown"
    return CountryName


def GetPrivileges():
    """Gets list of privileges."""
    mycursor.execute("SELECT * FROM privileges_groups")
    priv = mycursor.fetchall()
    if len(priv) == 0:
        return []
    Privs = []
    for x in priv:
        Privs.append({"Id": x[0], "Name": x[1], "Priv": x[2], "Colour": x[3]})
    return Privs


def ApplyUserEdit(form, from_id: int):
    """Apples the user settings."""
    # getting variables from form
    UserId = int(form.get("userid", False))
    Username = form.get("username", False)
    Aka = form.get("aka", False)
    Email = form.get("email", False)
    Country = form.get("country", False)
    UserPage = form.get("userpage", False)
    Notes = form.get("notes", False)
    Privilege = form.get("privilege", False)
    HWIDBypass = form.get("hwid_bypass", False) == "1"

    # Creating safe username
    SafeUsername = RippleSafeUsername(Username)

    # fixing crash bug
    if UserPage == "":
        UserPage = None

    # stop people ascending themselves
    # OriginalPriv = int(session["Privilege"])
    if int(UserId) == from_id:
        mycursor.execute("SELECT privileges FROM users WHERE id = %s", (from_id,))
        OriginalPriv = mycursor.fetchall()
        if len(OriginalPriv) == 0:
            return
        OriginalPriv = OriginalPriv[0][0]
        if int(Privilege) > OriginalPriv:
            return

    # Badges

    BadgeList = [
        int(form.get("Badge1", 0)),
        int(form.get("Badge2", 0)),
        int(form.get("Badge3", 0)),
        int(form.get("Badge4", 0)),
        int(form.get("Badge5", 0)),
        int(form.get("Badge6", 0)),
    ]
    SetUserBadges(UserId, BadgeList)
    # SQL Queries
    mycursor.execute(
        "UPDATE users SET email = %s, notes = %s, username = %s, username_safe = %s, privileges=%s, bypass_hwid=%s, country=%s WHERE id = %s",
        (
            Email,
            Notes,
            Username,
            SafeUsername,
            Privilege,
            HWIDBypass,
            Country,
            UserId,
        ),
    )
    mycursor.execute(
        "UPDATE users_stats SET userpage_content = %s, username_aka = %s, username = %s WHERE id = %s",
        (
            UserPage,
            Aka,
            Username,
            UserId,
        ),
    )
    if config.srv_supports_relax:
        mycursor.execute(
            "UPDATE rx_stats SET username = %s WHERE id = %s",
            (
                Username,
                UserId,
            ),
        )
    if config.srv_supports_autopilot:
        mycursor.execute(
            "UPDATE ap_stats SET username = %s WHERE id = %s",
            (
                Username,
                UserId,
            ),
        )
    mydb.commit()

    # Refresh in pep.py - Rosu only
    r.publish("peppy:refresh_privs", json.dumps({"user_id": UserId}))
    refresh_username_cache(UserId, Username)
    RAPLog(
        from_id,
        f"has edited the user {Username} ({UserId})",
    )


def ModToText(mod: int):
    """Converts mod enum to cool string."""
    # mod enums
    Mods = ""
    if mod == 0:
        return ""
    else:
        # adding mod names to str
        # they use bitwise too just like the perms
        if mod & 1:
            Mods += "NF"
        if mod & 2:
            Mods += "EZ"
        if mod & 4:
            Mods += "NV"
        if mod & 8:
            Mods += "HD"
        if mod & 16:
            Mods += "HR"
        if mod & 32:
            Mods += "SD"
        if mod & 512:
            Mods += "NC"
        elif mod & 64:
            Mods += "DT"
        if mod & 128:
            Mods += "RX"
        if mod & 256:
            Mods += "HT"
        if mod & 1024:
            Mods += "FL"
        if mod & 2048:
            Mods += "AO"
        if mod & 4096:
            Mods += "SO"
        if mod & 8192:
            Mods += "AP"
        if mod & 16384:
            Mods += "PF"
        if mod & 32768:
            Mods += "K4"
        if mod & 65536:
            Mods += "K5"
        if mod & 131072:
            Mods += "K6"
        if mod & 262144:
            Mods += "K7"
        if mod & 524288:
            Mods += "K8"
        if mod & 1015808:
            Mods += "KM"  # idk what this is
        if mod & 1048576:
            Mods += "FI"
        if mod & 2097152:
            Mods += "RM"
        if mod & 4194304:
            Mods += "LM"
        if mod & 16777216:
            Mods += "K9"
        if mod & 33554432:
            Mods += "KX"  # key 10 but 2 char. might change to k10
        if mod & 67108864:
            Mods += "K1"
        if mod & 134217728:
            Mods += "K2"
        if mod & 268435456:
            Mods += "K3"
        return Mods


def DeleteProfileComments(AccId):
    mycursor.execute("DELETE FROM user_comments WHERE prof = %s", (AccId,))
    mydb.commit()


def DeleteUserComments(AccId):
    mycursor.execute("DELETE FROM user_comments WHERE op = %s", (AccId,))
    mydb.commit()


def WipeAccount(AccId):
    """Wipes the account with the given id."""
    r.publish(
        "peppy:disconnect",
        json.dumps(
            {  # lets the user know what is up
                "userID": AccId,
                "reason": "Your account has been wiped! F",
            },
        ),
    )
    if config.srv_supports_relax:
        mycursor.execute("DELETE FROM scores_relax WHERE userid = %s", (AccId,))
    if config.srv_supports_autopilot:
        mycursor.execute("DELETE FROM scores_ap WHERE userid = %s", (AccId,))
    WipeVanilla(AccId)
    if config.srv_supports_relax:
        WipeRelax(AccId)
    if config.srv_supports_autopilot:
        WipeAutopilot(AccId)


def WipeVanilla(AccId):
    """Wiped vanilla scores for user."""
    mycursor.execute(
        """UPDATE
            users_stats
        SET
            ranked_score_std = 0,
            playcount_std = 0,
            total_score_std = 0,
            replays_watched_std = 0,
            ranked_score_taiko = 0,
            playcount_taiko = 0,
            total_score_taiko = 0,
            replays_watched_taiko = 0,
            ranked_score_ctb = 0,
            playcount_ctb = 0,
            total_score_ctb = 0,
            replays_watched_ctb = 0,
            ranked_score_mania = 0,
            playcount_mania = 0,
            total_score_mania = 0,
            replays_watched_mania = 0,
            total_hits_std = 0,
            total_hits_taiko = 0,
            total_hits_ctb = 0,
            total_hits_mania = 0,
            unrestricted_pp = 0,
            level_std = 0,
            level_taiko = 0,
            level_ctb = 0,
            level_mania = 0,
            playtime_std = 0,
            playtime_taiko = 0,
            playtime_ctb = 0,
            playtime_mania = 0,
            avg_accuracy_std = 0.000000000000,
            avg_accuracy_taiko = 0.000000000000,
            avg_accuracy_ctb = 0.000000000000,
            avg_accuracy_mania = 0.000000000000,
            pp_std = 0,
            pp_taiko = 0,
            pp_ctb = 0,
            pp_mania = 0
        WHERE
            id = %s
    """,
        (AccId,),
    )
    mycursor.execute("DELETE FROM scores WHERE userid = %s", (AccId,))
    mycursor.execute("DELETE FROM users_beatmap_playcount WHERE user_id = %s", (AccId,))
    mydb.commit()


def WipeRelax(AccId):
    """Wipes the relax user data."""
    mycursor.execute(
        """UPDATE
            rx_stats
        SET
            ranked_score_std = 0,
            playcount_std = 0,
            total_score_std = 0,
            replays_watched_std = 0,
            ranked_score_taiko = 0,
            playcount_taiko = 0,
            total_score_taiko = 0,
            replays_watched_taiko = 0,
            ranked_score_ctb = 0,
            playcount_ctb = 0,
            total_score_ctb = 0,
            replays_watched_ctb = 0,
            ranked_score_mania = 0,
            playcount_mania = 0,
            total_score_mania = 0,
            replays_watched_mania = 0,
            total_hits_std = 0,
            total_hits_taiko = 0,
            total_hits_ctb = 0,
            total_hits_mania = 0,
            unrestricted_pp = 0,
            level_std = 0,
            level_taiko = 0,
            level_ctb = 0,
            level_mania = 0,
            playtime_std = 0,
            playtime_taiko = 0,
            playtime_ctb = 0,
            playtime_mania = 0,
            avg_accuracy_std = 0.000000000000,
            avg_accuracy_taiko = 0.000000000000,
            avg_accuracy_ctb = 0.000000000000,
            avg_accuracy_mania = 0.000000000000,
            pp_std = 0,
            pp_taiko = 0,
            pp_ctb = 0,
            pp_mania = 0
        WHERE
            id = %s
    """,
        (AccId,),
    )
    mycursor.execute("DELETE FROM scores_relax WHERE userid = %s", (AccId,))
    mycursor.execute("DELETE FROM rx_beatmap_playcount WHERE user_id = %s", (AccId,))
    mydb.commit()


def WipeAutopilot(AccId):
    """Wipes the autopilot user data."""
    mycursor.execute(
        """UPDATE
            ap_stats
        SET
            ranked_score_std = 0,
            playcount_std = 0,
            total_score_std = 0,
            replays_watched_std = 0,
            ranked_score_taiko = 0,
            playcount_taiko = 0,
            total_score_taiko = 0,
            replays_watched_taiko = 0,
            ranked_score_ctb = 0,
            playcount_ctb = 0,
            total_score_ctb = 0,
            replays_watched_ctb = 0,
            ranked_score_mania = 0,
            playcount_mania = 0,
            total_score_mania = 0,
            replays_watched_mania = 0,
            total_hits_std = 0,
            total_hits_taiko = 0,
            total_hits_ctb = 0,
            total_hits_mania = 0,
            unrestricted_pp = 0,
            level_std = 0,
            level_taiko = 0,
            level_ctb = 0,
            level_mania = 0,
            playtime_std = 0,
            playtime_taiko = 0,
            playtime_ctb = 0,
            playtime_mania = 0,
            avg_accuracy_std = 0.000000000000,
            avg_accuracy_taiko = 0.000000000000,
            avg_accuracy_ctb = 0.000000000000,
            avg_accuracy_mania = 0.000000000000,
            pp_std = 0,
            pp_taiko = 0,
            pp_ctb = 0,
            pp_mania = 0
        WHERE
            id = %s
    """,
        (AccId,),
    )
    mycursor.execute("DELETE FROM scores_ap WHERE userid = %s", (AccId,))
    # mycursor.execute("DELETE FROM ap_beatmap_playcount WHERE user_id = %s", (AccId,))
    mydb.commit()


def ResUnTrict(id: int, note: str = None, reason: str = None):
    """Restricts or unrestricts account yeah."""
    if reason:
        mycursor.execute(
            "UPDATE users SET ban_reason = %s WHERE id = %s",
            (
                reason,
                id,
            ),
        )

    mycursor.execute("SELECT privileges FROM users WHERE id = %s", (id,))
    Privilege = mycursor.fetchall()
    if len(Privilege) == 0:
        return
    Privilege = Privilege[0][0]
    if not Privilege & 1:  # if restricted
        new_privs = Privilege | 1
        mycursor.execute(
            "UPDATE users SET privileges = %s, ban_datetime = 0 WHERE id = %s LIMIT 1",
            (
                new_privs,
                id,
            ),
        )  # unrestricts
        TheReturn = False
    else:
        wip = "Your account has been restricted! Check with staff to see whats up."
        params = {"k": config.api_foka_key, "to": GetUser(id)["Username"], "msg": wip}
        FokaMessage(params)
        TimeBan = round(time.time())
        mycursor.execute(
            "UPDATE users SET privileges = 2, ban_datetime = %s WHERE id = %s",
            (
                TimeBan,
                id,
            ),
        )  # restrict em bois
        RemoveFromLeaderboard(id)
        TheReturn = True

        # We append the note if it exists to the thingy init bruv
        if note:
            mycursor.execute(
                "UPDATE users SET notes = CONCAT(notes, %s) WHERE id = %s LIMIT 1",
                ("\n" + note, id),
            )

        # First places KILL.
        mycursor.execute(
            "SELECT beatmap_md5 FROM first_places WHERE user_id = %s",
            (id,),
        )
        recalc_maps = mycursor.fetchall()

        # Delete all of their old.
        mycursor.execute("DELETE FROM first_places WHERE user_id = %s", (id,))
        for (bmap_md5,) in recalc_maps:
            calc_first_place(bmap_md5)
    UpdateBanStatus(id)
    mydb.commit()
    return TheReturn


def FreezeHandler(id: int):
    mycursor.execute("SELECT frozen FROM users WHERE id = %s", (id,))
    Status = mycursor.fetchall()
    if len(Status) == 0:
        return
    Frozen = Status[0][0]
    if Frozen:
        mycursor.execute(
            "UPDATE users SET frozen = 0, freezedate = 0, firstloginafterfrozen = 1 WHERE id = %s",
            (id,),
        )
        TheReturn = False
    else:
        freezedate = datetime.datetime.now() + datetime.timedelta(days=5)
        freezedateunix = (freezedate - datetime.datetime(1970, 1, 1)).total_seconds()
        mycursor.execute(
            "UPDATE users SET frozen = 1, freezedate = %s WHERE id = %s",
            (
                freezedateunix,
                id,
            ),
        )
        TheReturn = True
        wip = f"Your account has been frozen. Please join the {config.srv_name} Discord and submit a liveplay to a staff member in order to be unfrozen"
        params = {"k": config.api_foka_key, "to": GetUser(id)["Username"], "msg": wip}
        FokaMessage(params)
    mydb.commit()
    return TheReturn


def BanUser(id: int, reason: str = None):
    """User go bye bye!"""
    if reason:
        mycursor.execute(
            "UPDATE users SET ban_reason = %s WHERE id = %s",
            (
                reason,
                id,
            ),
        )

    mycursor.execute("SELECT privileges FROM users WHERE id = %s", (id,))
    Privilege = mycursor.fetchall()
    Timestamp = round(time.time())
    if len(Privilege) == 0:
        return
    Privilege = Privilege[0][0]
    if Privilege == 0:  # if already banned
        mycursor.execute(
            "UPDATE users SET privileges = 3, ban_datetime = '0' WHERE id = %s",
            (id,),
        )
        TheReturn = False
    else:
        mycursor.execute(
            "UPDATE users SET privileges = 0, ban_datetime = %s WHERE id = %s",
            (
                Timestamp,
                id,
            ),
        )
        RemoveFromLeaderboard(id)
        r.publish(
            "peppy:disconnect",
            json.dumps(
                {  # lets the user know what is up
                    "userID": id,
                    "reason": f"You have been banned from {config.srv_name}. You will not be missed.",
                },
            ),
        )
        TheReturn = True
    UpdateBanStatus(id)
    mydb.commit()
    return TheReturn


def ClearHWID(id: int):
    """Clears the HWID matches for provided acc."""
    mycursor.execute("DELETE FROM hw_user WHERE userid = %s", (id,))
    mydb.commit()


def DeleteAccount(id: int):
    """Deletes the account provided. Press F to pay respects."""
    r.publish(
        "peppy:disconnect",
        json.dumps(
            {  # lets the user know what is up
                "userID": id,
                "reason": f"You have been deleted from {config.srv_name}. Bye!",
            },
        ),
    )
    # NUKE. BIG NUKE.
    mycursor.execute("DELETE FROM scores WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM users WHERE id = %s", (id,))
    mycursor.execute("DELETE FROM 2fa WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM 2fa_telegram WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM 2fa_totp WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM beatmaps_rating WHERE user_id = %s", (id,))
    mycursor.execute("DELETE FROM comments WHERE user_id = %s", (id,))
    mycursor.execute("DELETE FROM discord_roles WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM ip_user WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM profile_backgrounds WHERE uid = %s", (id,))
    mycursor.execute("DELETE FROM rank_requests WHERE userid = %s", (id,))
    mycursor.execute(
        "DELETE FROM reports WHERE to_uid = %s OR from_uid = %s",
        (
            id,
            id,
        ),
    )
    mycursor.execute("DELETE FROM tokens WHERE user = %s", (id,))
    mycursor.execute("DELETE FROM remember WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM users_achievements WHERE user_id = %s", (id,))
    mycursor.execute("DELETE FROM users_beatmap_playcount WHERE user_id = %s", (id,))
    mycursor.execute(
        "DELETE FROM users_relationships WHERE user1 = %s OR user2 = %s",
        (
            id,
            id,
        ),
    )
    mycursor.execute("DELETE FROM user_badges WHERE user = %s", (id,))
    mycursor.execute("DELETE FROM user_clans WHERE user = %s", (id,))
    mycursor.execute("DELETE FROM users_stats WHERE id = %s", (id,))
    if config.srv_supports_relax:
        mycursor.execute("DELETE FROM scores_relax WHERE userid = %s", (id,))
        mycursor.execute("DELETE FROM rx_stats WHERE id = %s", (id,))
    if config.srv_supports_autopilot:
        mycursor.execute("DELETE FROM scores_ap WHERE userid = %s", (id,))
        mycursor.execute("DELETE FROM ap_stats WHERE id = %s", (id,))
    mydb.commit()


def BanchoKick(id: int, reason):
    """Kicks the user from Bancho."""
    r.publish(
        "peppy:disconnect",
        json.dumps({"userID": id, "reason": reason}),  # lets the user know what is up
    )


def FindWithIp(Ip):
    """Gets array of users."""
    # fetching user id of person with given ip
    mycursor.execute("SELECT userid, ip FROM ip_user WHERE ip = %s", (Ip,))
    UserTruple = mycursor.fetchall()
    # turning the data into array with ids
    UserArray = []
    for x in UserTruple:
        ListToAdd = [x[0], x[1]]  # so ip is present for later use
        UserArray.append(ListToAdd)
    UserDataArray = []  # this will have the dicts
    for User in UserArray:
        if len(User) != 0:
            UserData = GetUser(User[0])
            UserData["Ip"] = User[1]
            UserDataArray.append(UserData)
        # lets take a second here to appreciate my naming scheme
    return UserDataArray


def PlayerCountCollection(loop=True):
    """Designed to be ran as thread. Grabs player count every set interval and puts in array."""
    while loop:
        CurrentCount = decode_int_or(r.get("ripple:online_users"), 0)
        PlayerCount.append(CurrentCount)
        time.sleep(300)
        # so graph doesnt get too huge
        if len(PlayerCount) >= 100:
            PlayerCount.remove(PlayerCount[0])
    if not loop:
        CurrentCount = decode_int_or(r.get("ripple:online_users"), 0)
        PlayerCount.append(CurrentCount)


def get_playcount_graph_data():
    """Returns data for dash graphs."""
    Data = {}
    Data["PlayerCount"] = PlayerCount

    # getting time intervals
    PrevNum = 0
    IntervalList = []
    for x in PlayerCount:
        IntervalList.append(str(PrevNum) + "m")
        PrevNum += 5

    IntervalList.reverse()
    Data["IntervalList"] = IntervalList
    return Data


def GiveSupporter(AccountID: int, Duration=30):
    """Gives the target user supporter.
    Args:
        AccountID (int): The account id of the target user.
        Duration (int): The time (in days) that the supporter rank should last
    """  # messing around with docstrings
    # checking if person already has supporter
    # also i believe there is a way better to do this, i am tired and may rewrite this and lower the query count
    mycursor.execute("SELECT privileges FROM users WHERE id = %s LIMIT 1", (AccountID,))
    CurrentPriv = mycursor.fetchone()[0]
    if CurrentPriv & 4:
        # already has supporter, extending
        mycursor.execute("SELECT donor_expire FROM users WHERE id = %s", (AccountID,))
        ToEnd = mycursor.fetchone()[0]
        ToEnd += 86400 * Duration
        mycursor.execute(
            "UPDATE users SET donor_expire = %s WHERE id=%s",
            (
                ToEnd,
                AccountID,
            ),
        )
        mydb.commit()
    else:
        EndTimestamp = round(time.time()) + (86400 * Duration)
        CurrentPriv += 4  # adding donor perms
        mycursor.execute(
            "UPDATE users SET privileges = %s, donor_expire = %s WHERE id = %s",
            (
                CurrentPriv,
                EndTimestamp,
                AccountID,
            ),
        )
        # allowing them to set custom badges
        mycursor.execute(
            "UPDATE users_stats SET can_custom_badge = 1 WHERE id = %s LIMIT 1",
            (AccountID,),
        )
        # now we give them the badge
        mycursor.execute(
            "INSERT INTO user_badges (user, badge) VALUES (%s, %s)",
            (AccountID, config.srv_donor_badge_id),
        )
        mydb.commit()


def RemoveSupporter(AccountID: int, session):
    """Removes supporter from the target user."""
    mycursor.execute("SELECT privileges FROM users WHERE id = %s LIMIT 1", (AccountID,))
    CurrentPriv = mycursor.fetchone()[0]
    # checking if they dont have it so privs arent messed up
    if not CurrentPriv & 4:
        return
    CurrentPriv -= 4
    mycursor.execute(
        "UPDATE users SET privileges = %s, donor_expire = 0 WHERE id = %s",
        (
            CurrentPriv,
            AccountID,
        ),
    )
    # remove custom badge perms and hide custom badge
    mycursor.execute(
        "UPDATE users_stats SET can_custom_badge = 0, show_custom_badge = 0 WHERE id = %s LIMIT 1",
        (AccountID,),
    )
    # removing el donor badge
    mycursor.execute(
        "DELETE FROM user_badges WHERE user = %s AND badge = %s LIMIT 1",
        (AccountID, config.srv_donor_badge_id),
    )
    mydb.commit()
    User = GetUser(AccountID)
    RAPLog(
        session["AccountId"],
        f"deleted the supporter role for {User['Username']} ({AccountID})",
    )


def GetBadges():
    """Gets all the badges."""
    mycursor.execute("SELECT * FROM badges")
    Data = mycursor.fetchall()
    Badges = []
    for badge in Data:
        Badges.append({"Id": badge[0], "Name": badge[1], "Icon": badge[2]})
    return Badges


def DeleteBadge(BadgeId: int):
    """ "Delets the badge with the gived id."""
    mycursor.execute("DELETE FROM badges WHERE id = %s", (BadgeId,))
    mycursor.execute("DELETE FROM user_badges WHERE badge = %s", (BadgeId,))
    mydb.commit()


def GetBadge(BadgeID: int):
    """Gets data of given badge."""
    mycursor.execute("SELECT * FROM badges WHERE id = %s LIMIT 1", (BadgeID,))
    BadgeData = mycursor.fetchone()
    return {"Id": BadgeData[0], "Name": BadgeData[1], "Icon": BadgeData[2]}


def SaveBadge(form):
    """Saves the edits done to the badge."""
    BadgeID = form["badgeid"]
    BadgeName = form["name"]
    BadgeIcon = form["icon"]
    mycursor.execute(
        "UPDATE badges SET name = %s, icon = %s WHERE id = %s",
        (
            BadgeName,
            BadgeIcon,
            BadgeID,
        ),
    )
    mydb.commit()


def ParseReplay(replay):
    """Parses replay and returns data in dict."""
    Replay = parse_replay_file(replay)
    return {
        # "GameMode" : Replay.game_mode, #commented until enum sorted out
        "GameVersion": Replay.game_version,
        "BeatmapHash": Replay.beatmap_hash,
        "Player": Replay.player_name,
        "ReplayHash": Replay.replay_hash,
        "300s": Replay.number_300s,
        "100s": Replay.number_100s,
        "50s": Replay.number_50s,
        "Gekis": Replay.gekis,
        "Katus": Replay.katus,
        "Misses": Replay.misses,
        "Score": Replay.score,
        "Combo": Replay.max_combo,
        "IsPC": Replay.is_perfect_combo,
        "Mods": Replay.mod_combination,
        "Timestamp": Replay.timestamp,
        "LifeGraph": Replay.life_bar_graph,
        "ReplayEvents": Replay.play_data,  # useful for recreating the replay
    }


def CreateBadge():
    """Creates empty badge."""
    mycursor.execute("INSERT INTO badges (name, icon) VALUES ('New Badge', '')")
    mydb.commit()
    # checking the ID
    mycursor.execute("SELECT id FROM badges ORDER BY id DESC LIMIT 1")
    return mycursor.fetchone()[0]


def GetPriv(PrivID: int):
    """Gets the priv data from ID."""
    mycursor.execute("SELECT * FROM privileges_groups WHERE id = %s", (PrivID,))
    Priv = mycursor.fetchone()
    return {"Id": Priv[0], "Name": Priv[1], "Privileges": Priv[2], "Colour": Priv[3]}


def DelPriv(PrivID: int):
    """Deletes a privilege group."""
    mycursor.execute("DELETE FROM privileges_groups WHERE id = %s", (PrivID,))
    mydb.commit()


def UpdatePriv(Form):
    """Updates the privilege from form."""
    # Get previous privilege number
    mycursor.execute(
        "SELECT privileges FROM privileges_groups WHERE id = %s",
        (Form["id"],),
    )
    PrevPriv = mycursor.fetchone()[0]
    # Update group
    mycursor.execute(
        "UPDATE privileges_groups SET name = %s, privileges = %s, color = %s WHERE id = %s LIMIT 1",
        (Form["name"], Form["privilege"], Form["colour"], Form["id"]),
    )
    # update privs for users
    TheFormPriv = int(Form["privilege"])
    # if TheFormPriv != 0 and TheFormPriv != 3 and TheFormPriv != 2: #i accidentally modded everyone because of this....
    #    mycursor.execute("UPDATE users SET privileges = REPLACE(privileges, %s, %s)", (PrevPriv, TheFormPriv,))
    mydb.commit()


def GetMostPlayed():
    """Gets the beatmap with the highest playcount."""
    mycursor.execute(
        "SELECT beatmap_id, song_name, beatmapset_id, playcount FROM beatmaps ORDER BY playcount DESC LIMIT 1",
    )
    Beatmap = mycursor.fetchone()
    return {
        "BeatmapId": Beatmap[0],
        "SongName": Beatmap[1],
        "Cover": f"https://assets.ppy.sh/beatmaps/{Beatmap[2]}/covers/cover.jpg",
        "Playcount": Beatmap[3],
    }


def DotsToList(Dots: str):
    """Converts a comma array (like the one ripple uses for badges) to a Python list."""
    return Dots.split(",")


def ListToDots(List: list):
    """Converts Python list to comma array."""
    Result = ""
    for part in List:
        Result += str(part) + ","
    return Result[:-1]


def GetUserBadges(AccountID: int):
    """Gets badges of a user and returns as list."""
    mycursor.execute("SELECT badge FROM user_badges WHERE user = %s", (AccountID,))
    Badges = []
    SQLBadges = mycursor.fetchall()
    for badge in SQLBadges:
        Badges.append(badge[0])

    # so we dont run into errors where people have no/less than 6 badges
    while len(Badges) < 6:
        Badges.append(0)
    return Badges


def SetUserBadges(AccountID: int, Badges: list):
    """Sets badge list to account."""
    """ Realised flaws with this approach
    CurrentBadges = GetUserBadges(AccountID) # so it knows which badges to keep
    ItemFor = 0
    for Badge in Badges:
        if not Badge == CurrentBadges[ItemFor]: #if its not the same
            mycursor.execute("DELETE FROM user_badges WHERE")
        ItemFor += 1
    """
    # This might not be the best and most efficient way but its all ive come up with in my application of user badges
    mycursor.execute(
        "DELETE FROM user_badges WHERE user = %s",
        (AccountID,),
    )  # deletes all existing badges
    for Badge in Badges:
        if Badge != 0 and Badge != 1:  # so we dont add empty badges
            mycursor.execute(
                "INSERT INTO user_badges (user, badge) VALUES (%s, %s)",
                (
                    AccountID,
                    Badge,
                ),
            )
    mydb.commit()


def GetLog():
    """Gets the newest 50 entries in the log."""

    with open("realistikpanel.log") as Log:
        Log = json.load(Log)

    Log = Log[-50:]
    Log.reverse()  # still wondering why it doesnt return the reversed list and instead returns none
    LogNr = 0
    # format the timestamps
    for log in Log:
        log["FormatDate"] = timestamp_as_date(log["Timestamp"])
        Log[LogNr] = log
        LogNr += 1
    return Log


def GetBuild():
    """Gets the build number of the current version of RealistikPanel."""
    with open("buildinfo.json") as file:
        BuildInfo = json.load(file)
    return BuildInfo["version"]


def GetUserID(Username: str):
    """Gets user id from username."""
    mycursor.execute("SELECT id FROM users WHERE username LIKE %s LIMIT 1", (Username,))
    Data = mycursor.fetchall()
    if len(Data) == 0:
        return 0
    return Data[0][0]


def TimeToTimeAgo(Timestamp: int):
    """Converts a seconds timestamp to a timeago string."""
    DTObj = datetime.datetime.fromtimestamp(Timestamp)
    CurrentTime = datetime.datetime.now()
    base_time = timeago.format(DTObj, CurrentTime)

    return f"{base_time} ({DTObj.strftime('%d/%m/%Y %H:%M')})"


def RemoveFromLeaderboard(UserID: int):
    """Removes the user from leaderboards."""
    Modes = ["std", "ctb", "mania", "taiko"]
    for mode in Modes:
        # redis for each mode
        r.zrem(f"ripple:leaderboard:{mode}", UserID)
        if config.srv_supports_relax:
            # removes from relax leaderboards
            r.zrem(f"ripple:leaderboard_relax:{mode}", UserID)
        if config.srv_supports_autopilot:
            r.zrem(f"ripple:leaderboard_ap:{mode}", UserID)

        # removing from country leaderboards
        mycursor.execute(
            "SELECT country FROM users WHERE id = %s LIMIT 1",
            (UserID,),
        )
        Country = mycursor.fetchone()[0]
        if Country != "XX":  # check if the country is not set
            r.zrem(f"ripple:leaderboard:{mode}:{Country}", UserID)
            if config.srv_supports_relax:
                r.zrem(f"ripple:leaderboard_relax:{mode}:{Country}", UserID)
            if config.srv_supports_autopilot:
                r.zrem(f"ripple:leaderboard_ap:{mode}:{Country}", UserID)


def UpdateBanStatus(UserID: int):
    """Updates the ban statuses in bancho."""
    r.publish("peppy:ban", UserID)


def SetBMAPSetStatus(BeatmapSet: int, Staus: int, session):
    """Sets status for all beatmaps in beatmapset."""
    mycursor.execute(
        "UPDATE beatmaps SET ranked = %s, ranked_status_freezed = 1 WHERE beatmapset_id = %s",
        (
            Staus,
            BeatmapSet,
        ),
    )
    mydb.commit()

    # getting status text
    if Staus == 0:
        TitleText = "unranked"
    elif Staus == 2:
        TitleText = "ranked"
    elif Staus == 5:
        TitleText = "loved"

    mycursor.execute(
        "SELECT song_name, beatmap_id, beatmap_md5 FROM beatmaps WHERE beatmapset_id = %s",
        (BeatmapSet,),
    )
    all_maps = mycursor.fetchall()
    MapData = all_maps[0]
    # Getting bmap name without diff
    BmapName = MapData[0].split("[")[0].rstrip()  # ¯\_(ツ)_/¯ might work
    # webhook, didnt use webhook function as it was too adapted for single map webhook
    webhook = DiscordWebhook(url=config.webhook_ranked)
    embed = DiscordEmbed(
        description=f"Ranked by {session['AccountName']}",
        color=242424,
    )
    embed.set_author(
        name=f"{BmapName} was just {TitleText}.",
        url=f"https://ussr.pl/b/{MapData[1]}",
        icon_url=f"https://a.ussr.pl/{session['AccountId']}",
    )  # will rank to random diff but yea
    embed.set_footer(text="via RealistikPanel!")
    embed.set_image(url=f"https://assets.ppy.sh/beatmaps/{BeatmapSet}/covers/cover.jpg")
    webhook.add_embed(embed)
    logger.info("Posting webhook...")
    webhook.execute()

    # Refresh all lbs.
    for _, _, md5 in all_maps:
        refresh_bmap(md5)


def FindUserByUsername(User: str, Page):
    """Finds user by their username OR email."""
    # calculating page offsets
    Offset = 50 * (Page - 1)
    # checking if its an email
    Split = User.split("@")
    if (
        len(Split) == 2 and "." in Split[1]
    ):  # if its an email, 2nd check makes sure its an email and not someone trying to be A E S T H E T I C
        mycursor.execute(
            "SELECT id, username, privileges, allowed FROM users WHERE email LIKE %s LIMIT 50 OFFSET %s",
            (
                User,
                Offset,
            ),
        )  # i will keep the like statement unless it causes issues
    else:  # its a username
        User = f"%{User}%"  # for sql to treat is as substring
        mycursor.execute(
            "SELECT id, username, privileges, allowed FROM users WHERE username LIKE %s LIMIT 50 OFFSET %s",
            (
                User,
                Offset,
            ),
        )
    Users = mycursor.fetchall()
    if len(Users) > 0:
        PrivilegeDict = {}
        AllPrivileges = []
        for person in Users:
            AllPrivileges.append(person[2])
        UniquePrivileges = Unique(AllPrivileges)
        # gets all priv info (copy pasted from get users as it is based on same infestructure)
        for Priv in UniquePrivileges:
            mycursor.execute(
                "SELECT name, color FROM privileges_groups WHERE privileges = %s LIMIT 1",
                (Priv,),
            )
            info = mycursor.fetchall()
            if len(info) == 0:
                PrivilegeDict[str(Priv)] = {
                    "Name": f"Unknown ({Priv})",
                    "Privileges": Priv,
                    "Colour": "danger",
                }
            else:
                info = info[0]
                PrivilegeDict[str(Priv)] = {}
                PrivilegeDict[str(Priv)]["Name"] = info[0]
                PrivilegeDict[str(Priv)]["Privileges"] = Priv
                PrivilegeDict[str(Priv)]["Colour"] = info[1]
                if (
                    PrivilegeDict[str(Priv)]["Colour"] == "default"
                    or PrivilegeDict[str(Priv)]["Colour"] == ""
                ):
                    # stisla doesnt have a default button so ill hard-code change it to a warning
                    PrivilegeDict[str(Priv)]["Colour"] = "warning"

        TheUsersDict = []
        for yuser in Users:
            # country query
            mycursor.execute(
                "SELECT country FROM users_stats WHERE id = %s",
                (yuser[0],),
            )
            Country = mycursor.fetchone()[0]
            Dict = {
                "Id": yuser[0],
                "Name": yuser[1],
                "Privilege": PrivilegeDict[str(yuser[2])],
                "Country": Country,
            }
            if yuser[3] == 1:
                Dict["Allowed"] = True
            else:
                Dict["Allowed"] = False
            TheUsersDict.append(Dict)

        return TheUsersDict
    else:
        return []


def CreateBcrypt(Password: str):
    """Creates hashed password using the hashing methods of Ripple."""
    MD5Password = hashlib.md5(Password.encode("utf-8")).hexdigest()
    BHashed = bcrypt.hashpw(MD5Password.encode("utf-8"), bcrypt.gensalt(10))
    return BHashed.decode()


def ChangePassword(AccountID: int, NewPassword: str):
    """Changes the password of a user with given AccID"""
    BCrypted = CreateBcrypt(NewPassword)
    mycursor.execute(
        "UPDATE users SET password_md5 = %s WHERE id = %s",
        (
            BCrypted,
            AccountID,
        ),
    )
    mydb.commit()
    r.publish("peppy:change_pass", json.dumps({"user_id": AccountID}))


def ChangePWForm(form, session):  # this function may be unnecessary but ehh
    """Handles the change password POST request."""
    ChangePassword(int(form["accid"]), form["newpass"])
    User = GetUser(form["accid"])
    RAPLog(
        session["AccountId"],
        f"has changed the password of {User['Username']} ({form['accid']})",
    )


def GiveSupporterForm(form):
    """Handles the give supporter form/POST request."""
    GiveSupporter(form["accid"], int(form["time"]))


def GetRankRequests(Page: int):
    """Gets all the rank requests. This may require some optimisation."""
    Page -= 1
    Offset = 50 * Page  # for the page system to work
    mycursor.execute(
        "SELECT id, userid, bid, type, time, blacklisted FROM rank_requests WHERE blacklisted = 0 LIMIT 50 OFFSET %s",
        (Offset,),
    )
    RankRequests = mycursor.fetchall()
    # turning what we have so far into
    TheRequests = []
    UserIDs = (
        []
    )  # used for later fetching the users, so we dont have a repeat of 50 queries
    for Request in RankRequests:
        # getting song info, like 50 individual queries at peak lmao
        TriedSet = False
        TriedBeatmap = False
        if Request[3] == "s":
            mycursor.execute(
                "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmapset_id = %s LIMIT 1",
                (Request[2],),
            )
            TriedSet = True
        else:
            mycursor.execute(
                "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmap_id = %s LIMIT 1",
                (Request[2],),
            )
            TriedBeatmap = True
        Name = mycursor.fetchall()
        # in case it was added incorrectly for some reason?
        if len(Name) == 0:
            if TriedBeatmap:
                mycursor.execute(
                    "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmapset_id = %s LIMIT 1",
                    (Request[2],),
                )
            if TriedSet:
                mycursor.execute(
                    "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmap_id = %s LIMIT 1",
                    (Request[2],),
                )
            Name = mycursor.fetchall()

        # if the info is bad
        if len(Name) == 0:
            SongName = "Darude - Sandstorm (Song not found)"
            BeatmapSetID = 0
            Cover = "https://i.ytimg.com/vi/erb4n8PW2qw/maxresdefault.jpg"
        else:
            SongName = Name[0][0]
            if Request[3] == "s":
                SongName = SongName.split("[")[
                    0
                ]  # kind of a way to get rid of diff name
            BeatmapSetID = Name[0][1]
            Cover = f"https://assets.ppy.sh/beatmaps/{BeatmapSetID}/covers/cover.jpg"
        # nice dict
        TheRequests.append(
            {
                "RequestID": Request[0],
                "RequestBy": Request[1],
                "RequestSongID": Request[2],  # not specifically song id or set id
                "Type": Request[3],  # s = set b = single diff
                "Time": Request[4],
                "TimeFormatted": timestamp_as_date(Request[4], False),
                "SongName": SongName,
                "Cover": Cover,
                "BeatmapSetID": BeatmapSetID,
            },
        )

        if Request[1] not in UserIDs:
            UserIDs.append(Request[1])
    # getting the Requester usernames
    Usernames = {}
    for AccoundIdentity in UserIDs:
        mycursor.execute("SELECT username FROM users WHERE id = %s", (AccoundIdentity,))
        TheID = mycursor.fetchall()
        if len(TheID) == 0:
            Usernames[str(AccoundIdentity)] = {
                "Username": f"Unknown! ({AccoundIdentity})",
            }
        else:
            Usernames[str(AccoundIdentity)] = {"Username": TheID[0][0]}
    # things arent going to be very performant lmao
    for i in range(0, len(TheRequests)):
        TheRequests[i]["RequestUsername"] = Usernames[str(TheRequests[i]["RequestBy"])][
            "Username"
        ]
    # flip so it shows newest first yes
    TheRequests.reverse()
    TheRequests = halve_list(TheRequests)
    return TheRequests


def DeleteBmapReq(Req):
    """Deletes the beatmap request."""
    mycursor.execute("DELETE FROM rank_requests WHERE id = %s LIMIT 1", (Req,))
    mydb.commit()


def UserPageCount():
    """Gets the amount of pages for users."""
    # i made it separate, fite me
    mycursor.execute("SELECT count(*) FROM users")
    TheNumber = mycursor.fetchone()[0]
    # working with page number (this is a mess...)
    return math.ceil(TheNumber / PAGE_SIZE)


def RapLogCount():
    """Gets the amount of pages for rap logs."""
    # i made it separate, fite me
    mycursor.execute("SELECT count(*) FROM rap_logs")
    TheNumber = mycursor.fetchone()[0]

    return math.ceil(TheNumber / PAGE_SIZE)


def GetClans(Page: int = 1):
    """Gets a list of all clans (v1)."""
    # offsets and limits
    Page = int(Page) - 1
    Offset = 50 * Page
    # the sql part
    mycursor.execute(
        "SELECT id, name, description, icon, tag FROM clans LIMIT 50 OFFSET %s",
        (Offset,),
    )
    ClansDB = mycursor.fetchall()
    # making cool, easy to work with dicts and arrays!
    Clans = []
    for Clan in ClansDB:
        Clans.append(
            {
                "ID": Clan[0],
                "Name": Clan[1],
                "Description": Clan[2],
                "Icon": Clan[3],
                "Tag": Clan[4],
            },
        )
    return Clans


def GetClanPages():
    """Gets amount of pages for clans."""
    mycursor.execute("SELECT count(*) FROM clans")
    TheNumber = mycursor.fetchone()[0]
    # working with page number (this is a mess...)
    TheNumber /= 50
    # if not single digit, round up
    if len(str(TheNumber)) != 0:
        NewNumber = round(TheNumber)
        # if number was rounded down
        if NewNumber == round(int(str(TheNumber).split(".")[0])):
            NewNumber += 1
        TheNumber = NewNumber
    # makign page dict
    Pages = []
    while TheNumber != 0:
        Pages.append(TheNumber)
        TheNumber -= 1
    Pages.reverse()
    return Pages


def GetAccuracy(count300, count100, count50, countMiss):
    """Converts 300, 100, 50 and miss count into osu accuracy."""
    try:
        return (50 * count50 + 100 * count100 + 300 * count300) / (
            3 * (countMiss + count50 + count100 + count300)
        )
    except ZeroDivisionError:
        return 0


def GetClanMembers(ClanID: int):
    """Returns a list of clan members."""
    # ok so we assume the list isnt going to be too long
    mycursor.execute("SELECT user FROM user_clans WHERE clan = %s", (ClanID,))
    ClanUsers = mycursor.fetchall()
    if len(ClanUsers) == 0:
        return []
    Conditions = ""
    args = []
    # this is so we can use one long query rather than a bunch of small ones
    for ClanUser in ClanUsers:
        Conditions += f"id = %s OR "
        args.append(ClanUser[0])
    Conditions = Conditions[:-4]  # remove the OR

    # getting the users
    mycursor.execute(
        f"SELECT username, id, register_datetime FROM users WHERE {Conditions}",
        args,
    )  # here i use format as the conditions are a trusted input
    UserData = mycursor.fetchall()
    # turning the data into a dictionary list
    ReturnList = []
    for User in UserData:
        ReturnList.append(
            {
                "AccountID": User[1],
                "Username": User[0],
                "RegisterTimestamp": User[2],
                "RegisterAgo": TimeToTimeAgo(User[2]),
            },
        )
    return ReturnList


def GetClan(ClanID: int):
    """Gets information for a specified clan."""
    mycursor.execute(
        "SELECT id, name, description, icon, tag, mlimit FROM clans WHERE id = %s LIMIT 1",
        (ClanID,),
    )
    Clan = mycursor.fetchone()
    if Clan == None:
        return None
    # getting current member count
    mycursor.execute("SELECT COUNT(*) FROM user_clans WHERE clan = %s", (ClanID,))
    MemberCount = mycursor.fetchone()[0]
    return {
        "ID": Clan[0],
        "Name": Clan[1],
        "Description": Clan[2],
        "Icon": Clan[3],
        "Tag": Clan[4],
        "MemberLimit": Clan[5],
        "MemberCount": MemberCount,
    }


def GetClanOwner(ClanID: int):
    """Gets user info for the owner of a clan."""
    # wouldve been done quicker but i decided to play jawbreaker and only got up to 81%
    mycursor.execute(
        "SELECT user FROM user_clans WHERE clan = %s and perms = 8",
        (ClanID,),
    )
    AccountID = mycursor.fetchone()[0]  # assuming there is an owner and clan exists
    # getting account info
    mycursor.execute(
        "SELECT username FROM users WHERE id = %s",
        (AccountID,),
    )  # will add more info maybe
    # assuming user exists
    User = mycursor.fetchone()
    return {"AccountID": AccountID, "Username": User[0]}


def ApplyClanEdit(Form, session):
    """Uses the post request to set new clan settings."""
    ClanID = Form["id"]
    ClanName = Form["name"]
    ClanDesc = Form["desc"]
    ClanTag = Form["tag"]
    ClanIcon = Form["icon"]
    MemberLimit = Form["limit"]
    mycursor.execute(
        "UPDATE clans SET name=%s, description=%s, tag=%s, mlimit=%s, icon=%s WHERE id = %s LIMIT 1",
        (ClanName, ClanDesc, ClanTag, MemberLimit, ClanIcon, ClanID),
    )
    mydb.commit()
    # Make all tags refresh.
    mycursor.execute("SELECT user FROM user_clans WHERE clan=%s", (ClanID,))
    for (user_id,) in mycursor.fetchall():
        cache_clan(user_id)
    RAPLog(session["AccountId"], f"edited the clan {ClanName} ({ClanID})")


def NukeClan(ClanID: int, session):
    """Deletes a clan from the face of the earth."""
    Clan = GetClan(ClanID)
    if not Clan:
        return

    # Make all tags refresh.
    mycursor.execute("SELECT user FROM user_clans WHERE clan=%s", (ClanID,))
    c_m_db = mycursor.fetchall()

    mycursor.execute("DELETE FROM clans WHERE id = %s LIMIT 1", (ClanID,))
    mycursor.execute("DELETE FROM user_clans WHERE clan=%s", (ClanID,))
    # run this after
    for (user_id,) in c_m_db:
        cache_clan(user_id)
    mydb.commit()
    RAPLog(session["AccountId"], f"deleted the clan {Clan['Name']} ({ClanID})")


def KickFromClan(AccountID):
    """Kicks user from all clans (supposed to be only one)."""
    mycursor.execute("DELETE FROM user_clans WHERE user = %s", (AccountID,))
    mydb.commit()
    cache_clan(AccountID)


def GetUsersRegisteredBetween(Offset: int = 0, Ahead: int = 24):
    """Gets how many players registered during a given time period (variables are in hours)."""
    # convert the hours to secconds
    Offset *= 3600
    Ahead *= 3600

    CurrentTime = round(time.time())
    # now we get the time - offset
    OffsetTime = CurrentTime - Offset
    AheadTime = OffsetTime - Ahead

    mycursor.execute(
        "SELECT COUNT(*) FROM users WHERE register_datetime > %s AND register_datetime < %s",
        (AheadTime, OffsetTime),
    )
    Count = mycursor.fetchone()
    if Count == None:
        return 0
    return Count[0]


def GetUsersActiveBetween(Offset: int = 0, Ahead: int = 24):
    """Gets how many players were active during a given time period (variables are in hours)."""
    # yeah this is a reuse of the last function.
    # convert the hours to secconds
    Offset *= 3600
    Ahead *= 3600

    CurrentTime = round(time.time())
    # now we get the time - offset
    OffsetTime = CurrentTime - Offset
    AheadTime = OffsetTime - Ahead

    mycursor.execute(
        "SELECT COUNT(*) FROM users WHERE latest_activity > %s AND latest_activity < %s",
        (AheadTime, OffsetTime),
    )
    Count = mycursor.fetchone()
    if Count == None:
        return 0
    return Count[0]


def RippleSafeUsername(Username):
    """Generates a ripple-style safe username."""
    return Username.lower().replace(" ", "_").rstrip()


def GetSuggestedRank():
    """Gets suggested maps to rank (based on play count)."""
    mycursor.execute(
        "SELECT beatmap_id, song_name, beatmapset_id, playcount FROM beatmaps WHERE ranked = 0 ORDER BY playcount DESC LIMIT 8",
    )
    Beatmaps = mycursor.fetchall()
    BeatmapList = []
    for TopBeatmap in Beatmaps:
        BeatmapList.append(
            {
                "BeatmapId": TopBeatmap[0],
                "SongName": TopBeatmap[1],
                "Cover": f"https://assets.ppy.sh/beatmaps/{TopBeatmap[2]}/covers/cover.jpg",
                "Playcount": TopBeatmap[3],
            },
        )

    return BeatmapList


def CountRestricted():
    """Calculates the amount of restricted or banned users."""
    mycursor.execute("SELECT COUNT(*) FROM users WHERE privileges = 2")
    Count = mycursor.fetchone()
    if Count == None:
        return 0
    return Count[0]


def GetStatistics(MinPP=0):
    """Gets statistics for the stats page and is incredibly slow...."""
    # this is going to be a wild one
    # TODO: REWRITE or look into caching this
    MinPP = int(MinPP)
    Days = 7
    RegisterList = []
    DateList = []
    while Days != -1:
        DateList.append(f"{Days+1}d")
        RegisterList.append(GetUsersRegisteredBetween(24 * Days))
        Days -= 1
    UsersActiveToday = GetUsersActiveBetween()
    RecentPlay = get_recent_plays(500, MinPP)
    ResctictedCount = CountRestricted()

    return {
        "RegisterGraph": {"RegisterList": RegisterList, "DateList": DateList},
        "ActiveToday": UsersActiveToday,
        "RecentPlays": RecentPlay,
        "DisallowedCount": ResctictedCount,
    }


def CreatePrivilege():
    """Creates a new default privilege."""
    mycursor.execute(
        "INSERT INTO privileges_groups (name, privileges, color) VALUES ('New Privilege', 0, '')",
    )
    mydb.commit()
    # checking the ID
    mycursor.execute("SELECT id FROM privileges_groups ORDER BY id DESC LIMIT 1")
    return mycursor.fetchone()[0]


def CoolerInt(ToInt):
    """Makes a number an int butt also works with special cases etc if ToInt is None, it returns a 0! Magic."""
    if ToInt == None:
        return 0
    return int(ToInt)


def calc_first_place(beatmap_md5: str, rx: int = 0, mode: int = 0) -> None:
    """Calculates the new first place for a beatmap and inserts it into the
    datbaase.

    Args:
        beatmap_md5 (str): The MD5 of the beatmap to set the first place for.
        rx (int): THe custom mode to recalc for (0=vn, 1=rx, 2=ap)
        mode (int): The gamemode to recalc for.
    """

    # We have to work out table.
    table = {0: "scores", 1: "scores_relax", 2: "scores_ap"}.get(rx)

    # WHY IS THE ROSU IMPLEMENTATION SO SCUFFED.
    # FROM scores_ap LEFT JOIN users ON users.id = scores_ap.userid
    mycursor.execute(
        "SELECT s.id, s.userid, s.score, s.max_combo, s.full_combo, s.mods, s.300_count,"
        "s.100_count, s.50_count, s.misses_count, s.time, s.play_mode, s.completed,"
        f"s.accuracy, s.pp, s.playtime, s.beatmap_md5 FROM {table} s RIGHT JOIN users a ON a.id = s.userid WHERE "
        "s.beatmap_md5 = %s AND s.play_mode = %s AND completed = 3 AND a.privileges & 2 ORDER BY pp "
        "DESC LIMIT 1",
        (beatmap_md5, mode),
    )

    first_place_db = mycursor.fetchone()

    # No scores at all.
    if not first_place_db:
        return

    # INSERT BRRRR
    mycursor.execute(
        """
        INSERT INTO first_places
         (
            score_id,
            user_id,
            score,
            max_combo,
            full_combo,
            mods,
            300_count,
            100_count,
            50_count,
            miss_count,
            timestamp,
            mode,
            completed,
            accuracy,
            pp,
            play_time,
            beatmap_md5,
            relax
         ) VALUES
         (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (*first_place_db, rx),
    )
    mydb.commit()


# USSR Redis Support.
def cache_clan(user_id: int) -> None:
    """Updates LETS' cached clan tag for a specific user. This is a
    requirement for RealistikOsu lets, or else clan tags may get out of sync.
    """

    r.publish("rosu:clan_update", str(user_id))


def refresh_bmap(md5: str) -> None:
    """Tells USSR to update the beatmap cache for a specific beatmap."""

    r.publish("ussr:refresh_bmap", md5)


def refresh_username_cache(user_id: int, new_name: str) -> None:
    """Refreshes the username cache for a specific user."""

    r.publish(
        "peppy:change_username",
        json.dumps({"userID": user_id, "newUsername": new_name}),
    )


class BanLog(TypedDict):
    from_id: int
    from_name: str
    to_id: int
    to_name: str
    ts: int
    expity_timeago: str
    summary: str
    detail: str


BAN_LOG_BASE = (
    "SELECT from_id, f.username, to_id, t.username, UNIX_TIMESTAMP(ts), summary, detail "
    "FROM ban_logs b "
    "INNER JOIN users f ON f.id = from_id "
    "INNER JOIN users t ON t.id = to_id "
)
PAGE_SIZE = 50


def fetch_banlogs(page: int = 0) -> list[BanLog]:
    """Fetches a page of ban logs."""

    mycursor.execute(
        BAN_LOG_BASE
        + f"ORDER BY b.id DESC LIMIT {PAGE_SIZE} OFFSET {PAGE_SIZE * page}",
    )

    # Convert into dicts.
    return [
        {
            "from_id": row[0],
            "from_name": row[1],
            "to_id": row[2],
            "to_name": row[3],
            "ts": row[4],
            "summary": row[5],
            "detail": row[6],
            "expity_timeago": TimeToTimeAgo(row[4]),
        }
        for row in mycursor
    ]


def ban_count() -> int:
    """Returns the total number of bans."""

    mycursor.execute("SELECT COUNT(*) FROM ban_logs")
    return mycursor.fetchone()[0]


def ban_pages() -> int:
    """Returns the number of pages in the ban log."""

    return math.ceil(ban_count() / PAGE_SIZE)


def request_count() -> int:
    """Returns the total number of requests."""

    mycursor.execute("SELECT COUNT(*) FROM rank_requests WHERE blacklisted = 0")
    return mycursor.fetchone()[0]


def request_pages() -> int:
    """Returns the number of pages in the request."""

    return math.ceil(request_count() / PAGE_SIZE)


def fetch_user_banlogs(user_id: int) -> list[BanLog]:
    """Fetches all ban logs targetting a specific user.

    Args:
        user_id (int): The target userID.

    Returns:
        list[BanLog]: A list of all banlogs for the user.
    """
    mycursor.execute(BAN_LOG_BASE + "WHERE to_id = %s ORDER BY b.id DESC", (user_id,))

    return [
        {
            "from_id": row[0],
            "from_name": row[1],
            "to_id": row[2],
            "to_name": row[3],
            "ts": row[4],
            "summary": row[5],
            "detail": row[6],
            "expity_timeago": TimeToTimeAgo(row[4]),
        }
        for row in mycursor
    ]


RANDOM_CHARSET = string.ascii_letters + string.digits


def random_str(length: int) -> str:
    """Generates a random string of a specific length."""
    return "".join(random.choice(RANDOM_CHARSET) for _ in range(length))


class ClanInvite(TypedDict):
    id: int
    clan_id: int
    invite_code: str


def get_clan_invites(clan_id: int) -> list[ClanInvite]:
    mycursor.execute(
        "SELECT id, clan, invite FROM clans_invites WHERE clan = %s",
        (clan_id,),
    )

    return [
        {
            "id": row[0],
            "clan_id": row[1],
            "invite_code": row[2],
        }
        for row in mycursor
    ]


def create_clan_invite(clan_id: int) -> ClanInvite:
    invite_code = random_str(8)
    mycursor.execute(
        "INSERT INTO clans_invites (clan, invite) VALUES (%s, %s)",
        (clan_id, invite_code),
    )
    mydb.commit()

    return {
        "id": mycursor.lastrowid,
        "clan_id": clan_id,
        "invite_code": invite_code,
    }


# HWID Capabilities
class HWIDLog(TypedDict):
    id: int
    user_id: int
    mac: str
    unique_id: str
    disk_id: str
    occurences: int


def get_hwid_history(user_id: int) -> list[HWIDLog]:
    mycursor.execute(
        "SELECT id, userid, mac, unique_id, disk_id, occurencies FROM hw_user WHERE userid = %s",
        (user_id,),
    )

    return [
        {
            "id": res[0],
            "user_id": res[1],
            "mac": res[2],
            "unique_id": res[3],
            "disk_id": res[4],
            "occurences": res[5],
        }
        for res in mycursor
    ]


def get_hwid_history_paginated(user_id: int, page: int = 0) -> list[HWIDLog]:

    mycursor.execute(
        "SELECT id, userid, mac, unique_id, disk_id, occurencies FROM hw_user "
        f"WHERE userid = %s ORDER BY id DESC LIMIT {PAGE_SIZE} OFFSET {PAGE_SIZE * page}",
        (user_id,),
    )

    return [
        {
            "id": res[0],
            "user_id": res[1],
            "mac": res[2],
            "unique_id": res[3],
            "disk_id": res[4],
            "occurences": res[5],
        }
        for res in mycursor
    ]


def get_hwid_matches_exact(log: HWIDLog) -> list[HWIDLog]:
    """Gets a list of exactly matching HWID logs for all users other than the
    origin of the initial log.

    Args:
        log (HWIDLog): The initial log to search for.

    Returns:
        list[HWIDLog]: A list of logs from other users that exactly match
            `log`.
    """

    mycursor.execute(
        "SELECT id, userid, mac, unique_id, disk_id, occurencies FROM hw_user "
        "WHERE userid != %s AND mac = %s AND unique_id = %s AND "
        "disk_id = %s",
        (log["user_id"], log["mac"], log["unique_id"], log["disk_id"]),
    )

    return [
        {
            "id": res[0],
            "user_id": res[1],
            "mac": res[2],
            "unique_id": res[3],
            "disk_id": res[4],
            "occurences": res[5],
        }
        for res in mycursor
    ]


def get_hwid_matches_partial(log: HWIDLog) -> list[HWIDLog]:
    """Gets a list of partially matching HWID logs (just one item has to match)
    for all users other than the origin of the initial log.

    Args:
        log (HWIDLog): The initial log to search for.

    Returns:
        list[HWIDLog]: A list of logs sharing at least one hash with `log`.
    """

    mycursor.execute(
        "SELECT id, userid, mac, unique_id, disk_id, occurencies FROM hw_user "
        "WHERE userid != %s AND (mac = %s OR unique_id = %s OR "
        "disk_id = %s) AND mac != 'b4ec3c4334a0249dae95c284ec5983df'",
        (log["user_id"], log["mac"], log["unique_id"], log["disk_id"]),
    )

    return [
        {
            "id": res[0],
            "user_id": res[1],
            "mac": res[2],
            "unique_id": res[3],
            "disk_id": res[4],
            "occurences": res[5],
        }
        for res in mycursor
    ]


def get_hwid_count(user_id: int) -> int:
    mycursor.execute("SELECT COUNT(*) FROM hw_user WHERE userid = %s", (user_id,))
    return mycursor.fetchone()[0]


def hwid_pages(user_id: int) -> int:
    """Returns the number of pages in the ban log."""

    return math.ceil(get_hwid_count(user_id) / PAGE_SIZE)


class HWIDResult(TypedDict):
    result: HWIDLog
    exact_matches: list[HWIDLog]
    partial_matches: list[HWIDLog]


class HWIDPage(TypedDict):
    user: dict
    results: list[HWIDResult]


def get_hwid_page(user_id: int, page: int = 0) -> HWIDPage:
    hw_history = get_hwid_history_paginated(user_id, page)

    results = list[HWIDResult]()

    for log in hw_history:
        exact_matches = get_hwid_matches_exact(log)
        partial_matches = list(
            filter(lambda x: x not in exact_matches, get_hwid_matches_partial(log)),
        )
        results.append(
            {
                "result": log,
                "exact_matches": exact_matches,
                "partial_matches": partial_matches,
            },
        )

    return {
        "user": GetUser(user_id),
        "results": results,
    }
