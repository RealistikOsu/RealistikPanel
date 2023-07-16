# Legacy panel functionality! DO NOT extend.
from __future__ import annotations

import datetime
import hashlib
import json
import math
import random
import string
import time
from typing import Any
from typing import TYPE_CHECKING
from typing import TypedDict
from typing import NamedTuple
from typing import Union
from typing import cast

import bcrypt
import pycountry
import requests
import timeago
from discord_webhook import DiscordEmbed
from discord_webhook import DiscordWebhook

if TYPE_CHECKING:
    from panel.web.sessions import Session

from panel import logger
from panel.common.cryprography import compare_password
from panel.common.time import timestamp_as_date
from panel.common.utils import decode_int_or
from panel import state
from panel.config import config
from panel.constants.traceback import TracebackType
from panel.constants.privileges import Privileges

PAGE_SIZE = 50


def fix_bad_user_count() -> None:
    # fix potential crashes
    # have to do it this way as the crash issue is a connector module issue
    BadUserCount = state.database.fetch_val("SELECT COUNT(*) FROM users_stats WHERE userpage_content = ''")
    if not BadUserCount or BadUserCount == 0:
        return

    logger.warning(
        f"Found {BadUserCount} users with potentially problematic data!",
    )
    state.database.execute(
        "UPDATE users_stats SET userpage_content = NULL WHERE userpage_content = ''",
    )
    logger.info("Fixed problematic data!")

# public variables
PlayerCount = []  # list of players

class Country(TypedDict):
    code: str
    name: str

def get_countries() -> list[Country]:
    resp_list = []
    for country in pycountry.countries:
        resp_list.append({
            "code": country.alpha_2,
            "name": country.name,
        })

    return cast(list[Country], resp_list)

def log_traceback(traceback: str, session: "Session", traceback_type: TracebackType) -> None:
    """Logs a traceback to the database."""
    state.sqlite.execute(
        "INSERT INTO tracebacks (user_id, traceback, time, traceback_type) VALUES (?, ?, ?, ?)",
        (
            session.user_id,
            traceback,
            int(time.time()),
            traceback_type.value,
        ),
    )

def get_tracebacks(page: int = 0) -> list[dict[str, Any]]:
    """Gets all tracebacks."""
    tracebacks = state.sqlite.fetch_all(
        "SELECT user_id, traceback, time, traceback_type FROM "
        f"tracebacks ORDER BY time DESC LIMIT {PAGE_SIZE} OFFSET {PAGE_SIZE * page}",
    )

    resp_list = []
    for traceback in tracebacks:
        user = GetUser(traceback[0])
        resp_list.append({
            "user": user,
            "traceback": traceback[1],
            "time": timestamp_as_date(traceback[2], False),
            "traceback_type": traceback[3],
        })

    return resp_list

def load_dashboard_data() -> dict[str, Any]:
    """Grabs all the values for the dashboard."""
    alert = state.database.fetch_val(
        "SELECT value_string FROM system_settings WHERE name = 'website_global_alert'",
    )

    total_pp = decode_int_or(state.redis.get("ripple:total_pp"))
    registered_users = decode_int_or(state.redis.get("ripple:registered_users"))
    online_users = decode_int_or(state.redis.get("ripple:online_users"))
    total_plays = decode_int_or(state.redis.get("ripple:total_plays"))
    total_scores = decode_int_or(state.redis.get("ripple:total_submitted_scores"))

    response = {
        "RegisteredUsers": registered_users,
        "OnlineUsers": online_users,
        "TotalPP": f"{total_pp:,}",
        "TotalPlays": f"{total_plays:,}",
        "TotalScores": f"{total_scores:,}",
        "Alert": alert,
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
    user = state.database.fetch_one(
        "SELECT username, password_md5, privileges, id FROM users WHERE username_safe = %s LIMIT 1",
        (RippleSafeUsername(username),),
    )

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
    u.username, s.userid, s.time, s.score, s.pp,
    s.play_mode, s.mods, s.accuracy, b.song_name, s.play_mode
FROM {} s
INNER JOIN users u ON u.id = s.userid
INNER JOIN beatmaps b ON b.beatmap_md5 = s.beatmap_md5
WHERE
    u.privileges & 1 AND s.pp >= %s
ORDER BY s.id DESC
LIMIT %s
"""


def get_recent_plays(total_plays: int = 20, minimum_pp: int = 0) -> list[dict[str, Any]]:
    """Returns recent plays."""
    divisor = 1
    if config.srv_supports_relax:
        divisor += 1
    if config.srv_supports_autopilot:
        divisor += 1
    plays_per_gamemode = total_plays // divisor

    dash_plays = []

    plays = state.database.fetch_all(
        BASE_RECENT_QUERY.format("scores"),
        (
            minimum_pp,
            plays_per_gamemode,
        ),
    )
    dash_plays.extend(plays)

    if config.srv_supports_relax:
        # adding relax plays
        plays_rx = state.database.fetch_all(
            BASE_RECENT_QUERY.format("scores_relax"),
            (
                minimum_pp,
                plays_per_gamemode,
            ),
        )
        dash_plays.extend(plays_rx)

    if config.srv_supports_autopilot:
        # adding autopilot plays
        plays_ap = state.database.fetch_all(
            BASE_RECENT_QUERY.format("scores_ap"),
            (
                minimum_pp,
                plays_per_gamemode,
            ),
        )
        dash_plays.extend(plays_ap)

    # converting the data into something readable
    ReadableArray = []
    for x in dash_plays:
        # yes im doing this
        # lets get the song name
        SongName = x[8]
        # make and populate a readable dict
        Dicti = {}
        Mods = ModToText(x[6])
        if Mods == "":
            Dicti["SongName"] = SongName
        else:
            Dicti["SongName"] = SongName + " +" + Mods
        Dicti["Player"] = x[0]
        Dicti["PlayerId"] = x[1]
        Dicti["Score"] = f"{x[3]:,}"
        Dicti["pp"] = round(x[4], 2)
        Dicti["Timestamp"] = x[2]
        Dicti["Time"] = timestamp_as_date(int(x[2]))
        Dicti["Accuracy"] = round(x[7], 2)
        Dicti["Mode"] = convert_mode_to_str(x[9])
        ReadableArray.append(Dicti)

    return ReadableArray


def FetchBSData() -> dict:
    """Fetches Bancho Settings."""
    bancho_settings = state.database.fetch_all(
        "SELECT name, value_string, value_int FROM bancho_settings WHERE name = 'bancho_maintenance' OR name = 'menu_icon' OR name = 'login_notification'",
    )

    result_map = {
        bancho_setting[0]: bancho_setting[1:] for bancho_setting in bancho_settings
    }

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
    bancho_maintenence_bool = bancho_maintenence == "On"

    # SQL Queries
    if menu_icon:
        state.database.execute(
            "UPDATE bancho_settings SET value_string = %s, value_int = 1 WHERE name = 'menu_icon'",
            (menu_icon,),
        )
    else:
        state.database.execute(
            "UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'menu_icon'",
        )

    if login_notification:
        state.database.execute(
            "UPDATE bancho_settings SET value_string = %s, value_int = 1 WHERE name = 'login_notification'",
            (login_notification,),
        )
    else:
        state.database.execute(
            "UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'login_notification'",
        )

    state.database.execute(
        "UPDATE bancho_settings SET value_int = %s WHERE name = 'bancho_maintenance'",
        (int(bancho_maintenence_bool),),
    )

    RAPLog(user_id, "modified the bancho settings")


def GetBmapInfo(bmap_id: int) -> list[dict[str, Any]]:
    """Gets beatmap info."""
    beatmapset_id = state.database.fetch_val("SELECT beatmapset_id FROM beatmaps WHERE beatmap_id = %s", (bmap_id,))

    if not beatmapset_id:
        # it might be a beatmap set then
        beatmaps_data = state.database.fetch_all(
            "SELECT song_name, ar, difficulty_std, beatmapset_id, beatmap_id, ranked FROM beatmaps WHERE beatmapset_id = %s",
            (bmap_id,),
        )

        if not beatmaps_data:  # if still havent found anything
            return [{
                "SongName": "Not Found",
                "Ar": "0",
                "Difficulty": "0",
                "BeatmapsetId": "",
                "BeatmapId": 0,
                "Cover": "https://a.ussr.pl/",  # why this%s idk
            }]
    else:
        beatmaps_data = state.database.fetch_all(
            "SELECT song_name, ar, difficulty_std, beatmapset_id, beatmap_id, ranked FROM beatmaps WHERE beatmapset_id = %s",
            (beatmapset_id,),
        )

    BeatmapList = []
    for beatmap in beatmaps_data:
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
    privileges = state.database.fetch_val("SELECT privileges FROM users WHERE id = %s", (user_id,))

    if privileges is None:
        return False
    
    user_privileges = Privileges(privileges)

    return user_privileges & privilege == privilege

def RankBeatmap(BeatmapId: int, ActionName: str, session: "Session") -> None:
    """Ranks a beatmap"""

    # converts actions to numbers
    if ActionName == "Loved":
        ActionId = 5
    elif ActionName == "Ranked":
        ActionId = 2
    elif ActionName == "Unranked":
        ActionId = 0
    else:
        logger.debug("Malformed action name input.")
        return
    
    state.database.execute(
        "UPDATE beatmaps SET ranked = %s, ranked_status_freezed = 1 WHERE beatmap_id = %s LIMIT 1",
        (
            ActionId,
            BeatmapId,
        ),
    )
    Webhook(BeatmapId, ActionId, session)

    # USSR SUPPORT.
    map_md5 = state.database.fetch_val(
        "SELECT beatmap_md5 FROM beatmaps WHERE beatmap_id = %s LIMIT 1",
        (BeatmapId,),
    )

    if map_md5:
        refresh_bmap(map_md5)


def FokaMessage(params: dict[str, Any]) -> None:
    """Sends a fokabot message."""
    requests.get(config.api_bancho_url + "api/v1/fokabotMessage", params=params)


def Webhook(BeatmapId: int, ActionId: int, session: "Session") -> None:
    """Beatmap rank webhook."""
    URL = config.webhook_ranked
    if not URL:
        # if no webhook is set, dont do anything
        return
    
    map_data = state.database.fetch_one(
        "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmap_id = %s",
        (BeatmapId,),
    )
    if not map_data:
        return

    TitleText = "unranked..."
    if ActionId == 2:
        TitleText = "ranked!"
    if ActionId == 5:
        TitleText = "loved!"

    webhook = DiscordWebhook(url=URL)  # creates webhook
    embed = DiscordEmbed(
        description=f"Ranked by {session.username}",
        color=242424,
    )  # this is giving me discord.py vibes

    embed.set_author(
        name=f"{map_data[0]} was just {TitleText}",
        url=f"{config.srv_url}b/{BeatmapId}",
        icon_url=f"{config.api_avatar_url}{session.user_id}",
    )

    embed.set_footer(text="via RealistikPanel!")
    embed.set_image(url=f"https://assets.ppy.sh/beatmaps/{map_data[1]}/covers/cover.jpg")
    webhook.add_embed(embed)

    logger.info("Posting webhook....")
    webhook.execute()

    Logtext = "unranked"
    if ActionId == 2:
        Logtext = "ranked"
    if ActionId == 5:
        Logtext = "loved"

    RAPLog(session.user_id, f"{Logtext} the beatmap {map_data[0]} ({BeatmapId})")
    ingamemsg = f"[https://{config.srv_url}u/{session.user_id} {session.username}] {Logtext.lower()} the map [https://osu.ppy.sh/b/{BeatmapId} {map_data[0]}]"
    params = {"k": config.api_foka_key, "to": "#announce", "msg": ingamemsg}
    FokaMessage(params)


def RAPLog(UserID: int = 999, Text: str = "forgot to assign a text value :/") -> None:
    """Logs to the RAP log."""
    Timestamp = round(time.time())
    # now we putting that in oh yea
    state.database.execute(
        "INSERT INTO rap_logs (userid, text, datetime, through) VALUES (%s, %s, %s, 'RealistikPanel!')",
        (
            UserID,
            Text,
            Timestamp,
        ),
    )

    # webhook time
    if not config.webhook_admin_log:
        return
    
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


def SystemSettingsValues() -> dict[str, Any]:
    """Fetches the system settings data."""
    system_settings = state.database.fetch_all(
        "SELECT value_int, value_string FROM system_settings WHERE name = 'website_maintenance' OR name = 'game_maintenance' OR name = 'website_global_alert' OR name = 'website_home_alert' OR name = 'registrations_enabled'",
    )

    return {
        "webman": bool(system_settings[0][0]),
        "gameman": bool(system_settings[1][0]),
        "register": bool(system_settings[4][0]),
        "globalalert": system_settings[2][1],
        "homealert": system_settings[3][1],
    }


def ApplySystemSettings(DataArray: list[str], user_id: int) -> None:
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
    state.database.execute(
        "UPDATE system_settings SET value_int = %s WHERE name = 'website_maintenance'",
        (WebMan,),
    )
    state.database.execute(
        "UPDATE system_settings SET value_int = %s WHERE name = 'game_maintenance'",
        (GameMan,),
    )
    state.database.execute(
        "UPDATE system_settings SET value_int = %s WHERE name = 'registrations_enabled'",
        (Register,),
    )

    # if empty, disable
    if GlobalAlert != "":
        state.database.execute(
            "UPDATE system_settings SET value_int = 1, value_string = %s WHERE name = 'website_global_alert'",
            (GlobalAlert,),
        )
    else:
        state.database.execute(
            "UPDATE system_settings SET value_int = 0, value_string = '' WHERE name = 'website_global_alert'",
        )
    if HomeAlert != "":
        state.database.execute(
            "UPDATE system_settings SET value_int = 1, value_string = %s WHERE name = 'website_home_alert'",
            (HomeAlert,),
        )
    else:
        state.database.execute(
            "UPDATE system_settings SET value_int = 0, value_string = '' WHERE name = 'website_home_alert'",
        )

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


def CalcPP(BmapID: int) -> float:
    """Sends request to letsapi to calc PP for beatmap id."""
    reqjson = requests.get(url=f"{config.api_lets_url}v1/pp?b={BmapID}").json()
    return round(reqjson["pp"][0], 2)


def CalcPPRX(BmapID: int) -> float:
    """Sends request to letsapi to calc PP for beatmap id with the double time mod."""
    reqjson = requests.get(url=f"{config.api_lets_url}v1/pp?b={BmapID}&m=128").json()
    return round(reqjson["pp"][0], 2)

def CalcPPAP(BmapID: int) -> float:
    """Sends request to letsapi to calc PP for beatmap id with the double time mod."""
    reqjson = requests.get(url=f"{config.api_lets_url}v1/pp?b={BmapID}&m=8192").json()
    return round(reqjson["pp"][0], 2)


def Unique(Alist: list) -> list:
    """Returns list of unique elements of list."""
    Uniques = []
    for x in Alist:
        if x not in Uniques:
            Uniques.append(x)
    return Uniques


def FetchUsers(page: int = 0) -> list[dict[str, Any]]:
    """Fetches users for the users page."""
    # This is going to need a lot of patching up i can feel it
    Offset = 50 * page  # for the page system to work
    users = state.database.fetch_all(
        "SELECT id, username, privileges, allowed, country FROM users LIMIT 50 OFFSET %s",
        (Offset,),
    )

    # gets list of all different privileges so an sql select call isnt ran per person
    AllPrivileges = []
    for person in users:
        AllPrivileges.append(person[2])
    UniquePrivileges = Unique(AllPrivileges)


    PrivilegeDict = {}
    # gets all priv info
    for Priv in UniquePrivileges:
        priv_info = state.database.fetch_one(
            "SELECT name, color FROM privileges_groups WHERE privileges = %s LIMIT 1",
            (Priv,),
        )

        if not priv_info:
            PrivilegeDict[str(Priv)] = {
                "Name": f"Unknown ({Priv})",
                "Privileges": Priv,
                "Colour": "danger",
            }
        else:
            PrivilegeDict[str(Priv)] = {}
            PrivilegeDict[str(Priv)]["Name"] = priv_info[0]
            PrivilegeDict[str(Priv)]["Privileges"] = Priv
            PrivilegeDict[str(Priv)]["Colour"] = priv_info[1]
            if (
                PrivilegeDict[str(Priv)]["Colour"] == "default"
                or PrivilegeDict[str(Priv)]["Colour"] == ""
            ):
                # stisla doesnt have a default button so ill hard-code change it to a warning
                PrivilegeDict[str(Priv)]["Colour"] = "warning"

    Users = []
    for user in users:
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


def GetUser(user_id: int) -> dict[str, Any]:
    """Gets data for user. (universal)"""
    user_data = state.database.fetch_one(
        "SELECT id, username, country FROM users WHERE id = %s LIMIT 1",
        (user_id,),
    )

    if not user_data:
        # if no one found
        return {
            "Id": 0,
            "Username": "Not Found",
            "IsOnline": False,
            "Country": "GB",  # RULE BRITANNIA
        }
    
    return {
        "Id": user_data[0],
        "Username": user_data[1],
        "IsOnline": IsOnline(user_id),
        "Country": user_data[2],
    }


def UserData(UserID: int) -> dict[str, Any]:
    """Gets data for user (specialised for user edit page)."""
    # fix badbad data
    state.database.execute(
        "UPDATE users_stats SET userpage_content = NULL WHERE userpage_content = '' AND id = %s",
        (UserID,),
    )

    user_data = GetUser(UserID)
    user_data2 = state.database.fetch_one(
        "SELECT userpage_content, user_color, username_aka FROM users_stats WHERE id = %s LIMIT 1",
        (UserID,),
    )

    if not user_data2:
        user_data2 = ["", "default", ""]

    user_data3 = state.database.fetch_one(
        "SELECT email, register_datetime, privileges, notes, donor_expire, silence_end, silence_reason, ban_datetime, bypass_hwid, ban_reason FROM users WHERE id = %s LIMIT 1",
        (UserID,),
    )

    if not user_data3:
        user_data3 = [
            "",
            0,
            0,
            "",
            0,
            0,
            "",
            0,
            0,
            "",
        ]

    # Fetches the IP
    ip_val = state.database.fetch_val("SELECT ip FROM ip_user WHERE userid = %s ORDER BY ip DESC LIMIT 1", (UserID,))
    if not ip_val:
        ip_val = "0.0.0.0"


    # gets privilege name
    privilege_name = state.database.fetch_val(
        "SELECT name FROM privileges_groups WHERE privileges = %s LIMIT 1",
        (user_data3[2],),
    )

    if not privilege_name:
        privilege_name = f"Unknown ({user_data3[2]})"

    # adds new info to dict
    # I dont use the discord features from RAP so i didnt include the discord settings but if you complain enough ill add them
    try:
        freeze_val = state.database.fetch_val(
            "SELECT freezedate FROM users WHERE id = %s LIMIT 1",
            (UserID,),
        )
    except Exception:
        freeze_val = None

    # removing "None" from user page and admin notes
    notes = ""
    if not user_data3[3] is None:
        notes = user_data3[3].strip()

    userpage_content = ""
    if not user_data2[0] is None:
        userpage_content = user_data2[0].strip()

    user_data |= {
        "UserpageContent": userpage_content,
        "UserColour": user_data2[1],
        "Aka": user_data2[2],
        "Email": user_data3[0],
        "RegisterTime": user_data3[1],
        "Privileges": user_data3[2],
        "Notes": notes,
        "DonorExpire": user_data3[4],
        "SilenceEnd": user_data3[5],
        "SilenceReason": user_data3[6],
        "Avatar": config.api_avatar_url + str(UserID),
        "Ip": ip_val,
        "CountryFull": GetCFullName(user_data["Country"]),
        "PrivName": privilege_name,
        "BypassHWID": user_data3[8],
        "BanReason": user_data3[9].strip(),
        "HasSupporter": user_data3[2] & 4,
        "DonorExpireStr": TimeToTimeAgo(user_data3[4]),
        "IsBanned": CoolerInt(user_data3[7]) > 0,
        "BanedAgo": TimeToTimeAgo(CoolerInt(user_data3[7])),
        "IsSilenced": CoolerInt(user_data3[5]) > round(time.time()),
        "SilenceEndAgo": TimeToTimeAgo(CoolerInt(user_data3[5])),
    }
    if freeze_val:
        user_data["IsFrozen"] = int(freeze_val) > 0
        user_data["FreezeDateNo"] = int(freeze_val)
        user_data["FreezeDate"] = TimeToTimeAgo(user_data["FreezeDateNo"])
    else:
        user_data["IsFrozen"] = False

    return user_data


def RAPFetch(page: int = 1) -> list[dict[str, Any]]:
    """Fetches RAP Logs."""
    page = int(page) - 1  # makes sure is int and is in ok format
    Offset = 50 * page

    panel_logs = state.database.fetch_all(
        "SELECT * FROM rap_logs ORDER BY id DESC LIMIT 50 OFFSET %s",
        (Offset,),
    )

    # Gets list of all users
    Users = []
    for dat in panel_logs:
        if dat[1] not in Users:
            Users.append(dat[1])
    # gets all unique users so a ton of lookups arent made
    UniqueUsers = Unique(Users)

    # now we get basic data for each user
    UserDict = {}
    for user in UniqueUsers:
        UserData = GetUser(user)
        UserDict[str(user)] = UserData


    LogArray = []
    for log in panel_logs:
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


def GetCFullName(country_code: str):
    """Gets the full name of the country provided."""
    Country = pycountry.countries.get(alpha_2=country_code)

    try:
        CountryName = Country.name
    except Exception:
        CountryName = "Unknown"

    return CountryName


def GetPrivileges() -> list[dict[str, Any]]:
    """Gets list of privileges."""
    privileges = state.database.fetch_all("SELECT * FROM privileges_groups")

    if not privileges:
        return []
    
    Privs = []
    for x in privileges:
        Privs.append({
            "Id": x[0],
            "Name": x[1],
            "Priv": x[2],
            "Colour": x[3],
        })

    return Privs


def ApplyUserEdit(form: dict[str, str], from_id: int) -> Union[None, str]:
    """Apples the user settings."""
    # getting variables from form
    UserId = int(form.get("userid", "0"))
    Username = form.get("username", "")
    Aka = form.get("aka", "")
    Email = form.get("email", "")
    Country = form.get("country", "")
    UserPage = form.get("userpage", "")
    Notes = form.get("notes", "")
    Privilege = form.get("privilege", "0")
    HWIDBypass = form.get("hwid_bypass", "0") == "1"

    # Creating safe username
    SafeUsername = RippleSafeUsername(Username)

    # fixing crash bug
    if UserPage == "":
        UserPage = None

    # stop people ascending themselves
    # OriginalPriv = int(session["Privilege"])
    if int(UserId) == from_id:
        privileges = state.database.fetch_val("SELECT privileges FROM users WHERE id = %s", (from_id,))
        if privileges is None:
            return
        
        if int(Privilege) > privileges:
            return "You cannot ascend yourself."

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
    # TODO: transaction?
    state.database.execute(
        "UPDATE users SET email = %s, notes = %s, username = %s, username_safe = %s, privileges = %s, bypass_hwid = %s, country = %s WHERE id = %s",
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
    state.database.execute(
        "UPDATE users_stats SET userpage_content = %s, username_aka = %s, username = %s WHERE id = %s",
        (
            UserPage,
            Aka,
            Username,
            UserId,
        ),
    )
    if config.srv_supports_relax:
        state.database.execute(
            "UPDATE rx_stats SET username = %s WHERE id = %s",
            (
                Username,
                UserId,
            ),
        )
    if config.srv_supports_autopilot:
        state.database.execute(
            "UPDATE ap_stats SET username = %s WHERE id = %s",
            (
                Username,
                UserId,
            ),
        )

    # Refresh in pep.py - Rosu only
    state.redis.publish("peppy:refresh_privs", json.dumps({"user_id": UserId}))
    refresh_username_cache(UserId, Username)
    RAPLog(
        from_id,
        f"has edited the user {Username} ({UserId})",
    )


def ModToText(mod: int) -> str:
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


def DeleteProfileComments(AccId: int) -> None:
    state.database.execute("DELETE FROM user_comments WHERE prof = %s", (AccId,))


def DeleteUserComments(AccId: int) -> None:
    state.database.execute("DELETE FROM user_comments WHERE op = %s", (AccId,))


def WipeAccount(AccId: int) -> None:
    """Wipes the account with the given id."""
    state.redis.publish(
        "peppy:disconnect",
        json.dumps(
            {  # lets the user know what is up
                "userID": AccId,
                "reason": "Your account has been wiped! F",
            },
        ),
    )

    # TODO: transaction?

    WipeVanilla(AccId)
    if config.srv_supports_relax:
        WipeRelax(AccId)

    if config.srv_supports_autopilot:
        WipeAutopilot(AccId)


def WipeVanilla(AccId: int) -> None:
    """Wiped vanilla scores for user."""
    state.database.execute(
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
    state.database.execute("DELETE FROM scores WHERE userid = %s", (AccId,))
    state.database.execute("DELETE FROM users_beatmap_playcount WHERE user_id = %s", (AccId,))


def WipeRelax(AccId: int) -> None:
    """Wipes the relax user data."""
    state.database.execute(
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
    state.database.execute("DELETE FROM scores_relax WHERE userid = %s", (AccId,))


def WipeAutopilot(AccId: int) -> None:
    """Wipes the autopilot user data."""
    state.database.execute(
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
    state.database.execute("DELETE FROM scores_ap WHERE userid = %s", (AccId,))


def ResUnTrict(user_id: int, note: str = "", reason: str = "") -> bool:
    """Restricts or unrestricts account yeah."""
    if reason:
        state.database.execute(
            "UPDATE users SET ban_reason = %s WHERE id = %s",
            (
                reason,
                user_id,
            ),
        )

    privileges = state.database.fetch_val("SELECT privileges FROM users WHERE id = %s", (user_id,))
    if privileges is None:
        return False
    
    if not privileges & 1:  # if restricted
        new_privs = privileges | 1
        state.database.execute(
            "UPDATE users SET privileges = %s, ban_datetime = 0 WHERE id = %s LIMIT 1",
            (
                new_privs,
                user_id,
            ),
        )  # unrestricts
        TheReturn = False
    else:
        wip = "Your account has been restricted! Check with staff to see whats up."
        params = {"k": config.api_foka_key, "to": GetUser(user_id)["Username"], "msg": wip}
        FokaMessage(params)
        TimeBan = round(time.time())
        state.database.execute(
            "UPDATE users SET privileges = 2, ban_datetime = %s WHERE id = %s",
            (
                TimeBan,
                user_id,
            ),
        )  # restrict em bois
        RemoveFromLeaderboard(user_id)
        TheReturn = True

        # We append the note if it exists to the thingy init bruv
        if note:
            state.database.execute(
                "UPDATE users SET notes = CONCAT(notes, %s) WHERE id = %s LIMIT 1",
                ("\n" + note, user_id),
            )

        # First places KILL.
        recalc_md5s = state.database.fetch_all(
            "SELECT beatmap_md5 FROM first_places WHERE user_id = %s",
            (user_id,),
        )

        # Delete all of their old.
        state.database.execute("DELETE FROM first_places WHERE user_id = %s", (user_id,))
        for bmap_md5 in recalc_md5s:
            calc_first_place(bmap_md5[0])

    UpdateBanStatus(user_id)
    return TheReturn


def FreezeHandler(user_id: int) -> bool:
    freeze_status = state.database.fetch_val("SELECT frozen FROM users WHERE id = %s", (user_id,))
    if not freeze_status:
        return False
    
    if freeze_status:
        state.database.execute(
            "UPDATE users SET frozen = 0, freezedate = 0, firstloginafterfrozen = 1 WHERE id = %s",
            (user_id,),
        )
        TheReturn = False
    else:
        freezedate = datetime.datetime.now() + datetime.timedelta(days=5)
        freezedateunix = (freezedate - datetime.datetime(1970, 1, 1)).total_seconds()

        state.database.execute(
            "UPDATE users SET frozen = 1, freezedate = %s WHERE id = %s",
            (
                freezedateunix,
                user_id,
            ),
        )

        TheReturn = True
        wip = f"Your account has been frozen. Please join the {config.srv_name} Discord and submit a liveplay to a staff member in order to be unfrozen"
        params = {"k": config.api_foka_key, "to": GetUser(user_id)["Username"], "msg": wip}
        FokaMessage(params)

    return TheReturn


def BanUser(user_id: int, reason: str = "") -> bool:
    """User go bye bye!"""
    if reason:
        state.database.execute(
            "UPDATE users SET ban_reason = %s WHERE id = %s",
            (
                reason,
                user_id,
            ),
        )

    privileges = state.database.fetch_val("SELECT privileges FROM users WHERE id = %s", (user_id,))
    if privileges is None:
        return False
    
    Timestamp = round(time.time())
    if privileges == 0:  # if already banned
        state.database.execute(
            "UPDATE users SET privileges = 3, ban_datetime = '0' WHERE id = %s",
            (user_id,),
        )
        TheReturn = False
    else:
        state.database.execute(
            "UPDATE users SET privileges = 0, ban_datetime = %s WHERE id = %s",
            (
                Timestamp,
                user_id,
            ),
        )
        RemoveFromLeaderboard(user_id)
        state.redis.publish(
            "peppy:disconnect",
            json.dumps(
                {  # lets the user know what is up
                    "userID": user_id,
                    "reason": f"You have been banned from {config.srv_name}. You will not be missed.",
                },
            ),
        )
        TheReturn = True

    UpdateBanStatus(user_id)
    return TheReturn


def ClearHWID(user_id: int) -> None:
    """Clears the HWID matches for provided acc."""
    state.database.execute("DELETE FROM hw_user WHERE userid = %s", (user_id,))


def DeleteAccount(user_id: int) -> None:
    """Deletes the account provided. Press F to pay respects."""
    state.redis.publish(
        "peppy:disconnect",
        json.dumps(
            {  # lets the user know what is up
                "userID": user_id,
                "reason": f"You have been deleted from {config.srv_name}. Bye!",
            },
        ),
    )
    # NUKE. BIG NUKE.
    state.database.execute("DELETE FROM scores WHERE userid = %s", (user_id,))
    state.database.execute("DELETE FROM users WHERE id = %s", (user_id,))
    state.database.execute("DELETE FROM 2fa WHERE userid = %s", (user_id,))
    state.database.execute("DELETE FROM 2fa_telegram WHERE userid = %s", (user_id,))
    state.database.execute("DELETE FROM 2fa_totp WHERE userid = %s", (user_id,))
    state.database.execute("DELETE FROM beatmaps_rating WHERE user_id = %s", (user_id,))
    state.database.execute("DELETE FROM comments WHERE user_id = %s", (user_id,))
    state.database.execute("DELETE FROM discord_roles WHERE userid = %s", (user_id,))
    state.database.execute("DELETE FROM ip_user WHERE userid = %s", (user_id,))
    state.database.execute("DELETE FROM profile_backgrounds WHERE uid = %s", (user_id,))
    state.database.execute("DELETE FROM rank_requests WHERE userid = %s", (user_id,))
    state.database.execute(
        "DELETE FROM reports WHERE to_uid = %s OR from_uid = %s",
        (
            user_id,
            user_id,
        ),
    )
    state.database.execute("DELETE FROM tokens WHERE user = %s", (user_id,))
    state.database.execute("DELETE FROM remember WHERE userid = %s", (user_id,))
    state.database.execute("DELETE FROM users_achievements WHERE user_id = %s", (user_id,))
    state.database.execute("DELETE FROM users_beatmap_playcount WHERE user_id = %s", (user_id,))
    state.database.execute(
        "DELETE FROM users_relationships WHERE user1 = %s OR user2 = %s",
        (
            user_id,
            user_id,
        ),
    )
    state.database.execute("DELETE FROM user_badges WHERE user = %s", (user_id,))
    state.database.execute("DELETE FROM user_clans WHERE user = %s", (user_id,))
    state.database.execute("DELETE FROM users_stats WHERE id = %s", (user_id,))
    if config.srv_supports_relax:
        state.database.execute("DELETE FROM scores_relax WHERE userid = %s", (user_id,))
        state.database.execute("DELETE FROM rx_stats WHERE id = %s", (user_id,))
    if config.srv_supports_autopilot:
        state.database.execute("DELETE FROM scores_ap WHERE userid = %s", (user_id,))
        state.database.execute("DELETE FROM ap_stats WHERE id = %s", (user_id,))


def BanchoKick(id: int, reason: str) -> None:
    """Kicks the user from Bancho."""
    state.redis.publish(
        "peppy:disconnect",
        json.dumps({"userID": id, "reason": reason}),  # lets the user know what is up
    )


def FindWithIp(Ip: str) -> list[dict[str, Any]]:
    """Gets array of users."""
    # fetching user id of person with given ip
    occurences = state.database.fetch_all("SELECT userid, ip, occurencies FROM ip_user WHERE ip = %s", (Ip,))

    resp_list = []
    for occurence in occurences:
        user_data = GetUser(occurence[0])
        user_data["Ip"] = occurence[1]
        user_data["Occurencies"] = occurence[2]
        resp_list.append(user_data)

    return resp_list

def find_priv(priv: int) -> dict[str, Any]:
    priv_info = state.database.fetch_one(
        "SELECT name, color FROM privileges_groups WHERE privileges = %s LIMIT 1",
        (priv,),
    )

    if not priv_info:
        return {
            "Name": f"Unknown ({priv})",
            "Privileges": priv,
            "Colour": "danger",
        }

    resp = {
        "Name": priv_info[0],
        "Privileges": priv,
        "Colour": priv_info[1],
    }

    if resp["Colour"] == "default" or resp["Colour"] == "":
        resp["Colour"] = "warning"

    return resp

def find_all_ips(user_id: int) -> list[dict[str, Any]]:
    """Gets array of users."""
    # fetching user id of person with given ip
    resp = state.database.fetch_all("SELECT ip FROM ip_user WHERE userid = %s AND ip != ''", (user_id,))

    if not resp:
        return []

    ips = []
    for ip in resp:
        ips.append(ip[0])

    condition = ", ".join(["%s"] * len(ips))

    occurences = state.database.fetch_all(
        f"SELECT ip_user.userid, ip_user.ip, ip_user.occurencies, users.username, users.privileges FROM ip_user JOIN users ON ip_user.userid = users.id WHERE ip IN ({condition}) ORDER BY ip DESC",
        tuple(ips),
    )

    if not occurences:
        return []

    data = []
    for user in occurences:

        priv_status = "Banned"
        priv_colour = "danger"
        if (user[4] & 3) >= 3:
            priv_status = "OK"
            priv_colour = "success"
        elif (user[4] & 2) == 2:
            priv_status = "Restricted"
            priv_colour = "warning"

        data.append({
            "user_id": user[0],
            "ip": user[1],
            "occurencies": user[2],
            "username": user[3],
            "privileges": find_priv(user[4]),
            "priv_status": {"text": priv_status, "colour": priv_colour},
        })
    
    return data

def PlayerCountCollection(loop: bool = True) -> None:
    """Designed to be ran as thread. Grabs player count every set interval and puts in array."""
    while loop:
        CurrentCount = decode_int_or(state.redis.get("ripple:online_users"), 0)
        PlayerCount.append(CurrentCount)
        time.sleep(300)
        # so graph doesnt get too huge
        if len(PlayerCount) >= 100:
            PlayerCount.remove(PlayerCount[0])
    if not loop:
        CurrentCount = decode_int_or(state.redis.get("ripple:online_users"), 0)
        PlayerCount.append(CurrentCount)


def get_playcount_graph_data() -> dict[str, list[Union[int, str]]]:
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


def GiveSupporter(AccountID: int, Duration: int = 30) -> None:
    """Gives the target user supporter.
    Args:
        AccountID (int): The account id of the target user.
        Duration (int): The time (in days) that the supporter rank should last
    """  # messing around with docstrings
    # checking if person already has supporter
    # also i believe there is a way better to do this, i am tired and may rewrite this and lower the query count
    privileges = state.database.fetch_val("SELECT privileges FROM users WHERE id = %s LIMIT 1", (AccountID,))
    if not privileges:
        return

    if privileges & 4:
        # already has supporter, extending
        ends_on = state.database.fetch_val("SELECT donor_expire FROM users WHERE id = %s", (AccountID,))
        ends_on += 86400 * Duration
        
        state.database.execute(
            "UPDATE users SET donor_expire = %s WHERE id=%s",
            (
                ends_on,
                AccountID,
            ),
        )

    else:
        EndTimestamp = round(time.time()) + (86400 * Duration)
        privileges += 4  # adding donor perms

        state.database.execute(
            "UPDATE users SET privileges = %s, donor_expire = %s WHERE id = %s",
            (
                privileges,
                EndTimestamp,
                AccountID,
            ),
        )

        # allowing them to set custom badges
        state.database.execute(
            "UPDATE users_stats SET can_custom_badge = 1 WHERE id = %s LIMIT 1",
            (AccountID,),
        )
        # now we give them the badge
        state.database.execute(
            "INSERT INTO user_badges (user, badge) VALUES (%s, %s)",
            (AccountID, config.srv_donor_badge_id),
        )


def RemoveSupporter(AccountID: int, session: "Session") -> None:
    """Removes supporter from the target user."""
    privileges = state.database.fetch_val("SELECT privileges FROM users WHERE id = %s LIMIT 1", (AccountID,))
    if not privileges:
        return
    
    # checking if they dont have it so privs arent messed up
    if not privileges & 4:
        return
    
    privileges -= 4
    state.database.execute(
        "UPDATE users SET privileges = %s, donor_expire = 0 WHERE id = %s",
        (
            privileges,
            AccountID,
        ),
    )
    # remove custom badge perms and hide custom badge
    state.database.execute(
        "UPDATE users_stats SET can_custom_badge = 0, show_custom_badge = 0 WHERE id = %s LIMIT 1",
        (AccountID,),
    )
    # removing el donor badge
    state.database.execute(
        "DELETE FROM user_badges WHERE user = %s AND badge = %s LIMIT 1",
        (AccountID, config.srv_donor_badge_id),
    )

    User = GetUser(AccountID)
    RAPLog(
        session.user_id,
        f"deleted the supporter role for {User['Username']} ({AccountID})",
    )


def GetBadges() -> list[dict[str, Any]]:
    """Gets all the badges."""
    badges_data = state.database.fetch_all("SELECT * FROM badges")
    Badges = []

    for badge in badges_data:
        Badges.append({
            "Id": badge[0], 
            "Name": badge[1], 
            "Icon": badge[2]
        })

    return Badges


def DeleteBadge(BadgeId: int) -> None:
    """ "Delets the badge with the gived id."""
    state.database.execute("DELETE FROM badges WHERE id = %s", (BadgeId,))
    state.database.execute("DELETE FROM user_badges WHERE badge = %s", (BadgeId,))


def GetBadge(BadgeID: int) -> dict[str, Any]:
    """Gets data of given badge."""
    badge_data = state.database.fetch_one("SELECT * FROM badges WHERE id = %s LIMIT 1", (BadgeID,))

    if not badge_data:
        return {
            "Id": 0,
            "Name": "Unknown",
            "Icon": "",
        }

    return {
        "Id": badge_data[0], 
        "Name": badge_data[1], 
        "Icon": badge_data[2]
    }


def SaveBadge(form: dict[str, str]) -> None:
    """Saves the edits done to the badge."""
    BadgeID = form["badgeid"]
    BadgeName = form["name"]
    BadgeIcon = form["icon"]
    state.database.execute(
        "UPDATE badges SET name = %s, icon = %s WHERE id = %s",
        (
            BadgeName,
            BadgeIcon,
            BadgeID,
        ),
    )


def CreateBadge() -> int:
    """Creates empty badge."""
    badge_id = state.database.execute("INSERT INTO badges (name, icon) VALUES ('New Badge', '')")
    return badge_id


def GetPriv(PrivID: int) -> dict[str, Any]:
    """Gets the priv data from ID."""
    priv_data = state.database.fetch_one("SELECT * FROM privileges_groups WHERE id = %s", (PrivID,))

    if not priv_data:
        return {
            "Id": 0,
            "Name": "Unknown",
            "Privileges": 0,
            "Colour": "danger",
        }

    return {
        "Id": priv_data[0], 
        "Name": priv_data[1], 
        "Privileges": priv_data[2], 
        "Colour": priv_data[3]
    }


def DelPriv(PrivID: int) -> None:
    """Deletes a privilege group."""
    state.database.execute("DELETE FROM privileges_groups WHERE id = %s", (PrivID,))


def UpdatePriv(Form: dict[str, str]) -> None:
    """Updates the privilege from form."""
    # Get previous privilege number
    privileges = state.database.fetch_val(
        "SELECT privileges FROM privileges_groups WHERE id = %s",
        (Form["id"],),
    )
    if not privileges:
        return

    # Update group
    state.database.execute(
        "UPDATE privileges_groups SET name = %s, privileges = %s, color = %s WHERE id = %s LIMIT 1",
        (Form["name"], Form["privilege"], Form["colour"], Form["id"]),
    )
    # update privs for users
    #TheFormPriv = int(Form["privilege"])
    # if TheFormPriv != 0 and TheFormPriv != 3 and TheFormPriv != 2: #i accidentally modded everyone because of this....
    #    mycursor.execute("UPDATE users SET privileges = REPLACE(privileges, %s, %s)", (PrevPriv, TheFormPriv,))


def GetMostPlayed() -> dict[str, Any]:
    """Gets the beatmap with the highest playcount."""
    beatmap = state.database.fetch_one(
        "SELECT beatmap_id, song_name, beatmapset_id, playcount FROM beatmaps ORDER BY playcount DESC LIMIT 1",
    )

    if beatmap is None:
        return {
            "BeatmapId": 0,
            "SongName": "No beatmaps found",
            "Cover": "",
            "Playcount": 0,
        }

    return {
        "BeatmapId": beatmap[0],
        "SongName": beatmap[1],
        "Cover": f"https://assets.ppy.sh/beatmaps/{beatmap[2]}/covers/cover.jpg",
        "Playcount": beatmap[3],
    }


def DotsToList(Dots: str) -> list[str]:
    """Converts a comma array (like the one ripple uses for badges) to a Python list."""
    return Dots.split(",")


def ListToDots(List: list) -> str:
    """Converts Python list to comma array."""
    return ",".join(List)


def GetUserBadges(AccountID: int) -> list[int]:
    """Gets badges of a user and returns as list."""
    badges = state.database.fetch_all("SELECT badge FROM user_badges WHERE user = %s", (AccountID,))

    Badges = []
    for badge in badges:
        Badges.append(badge[0])

    # so we dont run into errors where people have no/less than 6 badges
    while len(Badges) < 6:
        Badges.append(0)

    return Badges


def SetUserBadges(AccountID: int, Badges: list[int]) -> None:
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
    state.database.execute(
        "DELETE FROM user_badges WHERE user = %s",
        (AccountID,),
    )  # deletes all existing badges

    for Badge in Badges:
        if Badge != 0 and Badge != 1:  # so we dont add empty badges
            state.database.execute(
                "INSERT INTO user_badges (user, badge) VALUES (%s, %s)",
                (
                    AccountID,
                    Badge,
                ),
            )


def GetUserID(Username: str) -> int:
    """Gets user id from username."""
    user_id = state.database.fetch_val("SELECT id FROM users WHERE username LIKE %s LIMIT 1", (Username,))
    if not user_id:
        return 0
    
    return user_id


def TimeToTimeAgo(Timestamp: int) -> str:
    """Converts a seconds timestamp to a timeago string."""
    DTObj = datetime.datetime.fromtimestamp(Timestamp)
    CurrentTime = datetime.datetime.now()
    base_time = timeago.format(DTObj, CurrentTime)

    return f"{base_time} ({DTObj.strftime('%d/%m/%Y %H:%M')})"


def RemoveFromLeaderboard(UserID: int) -> None:
    """Removes the user from leaderboards."""
    Modes = ["std", "ctb", "mania", "taiko"]
    for mode in Modes:
        # redis for each mode
        state.redis.zrem(f"ripple:leaderboard:{mode}", UserID)
        if config.srv_supports_relax:
            # removes from relax leaderboards
            state.redis.zrem(f"ripple:leaderboard_relax:{mode}", UserID)
        if config.srv_supports_autopilot:
            state.redis.zrem(f"ripple:leaderboard_ap:{mode}", UserID)

        # removing from country leaderboards
        country = state.database.fetch_val(
            "SELECT country FROM users WHERE id = %s LIMIT 1",
            (UserID,),
        )
        if country and country != "XX":  # check if the country is not set
            state.redis.zrem(f"ripple:leaderboard:{mode}:{country}", UserID)
            if config.srv_supports_relax:
                state.redis.zrem(f"ripple:leaderboard_relax:{mode}:{country}", UserID)
            if config.srv_supports_autopilot:
                state.redis.zrem(f"ripple:leaderboard_ap:{mode}:{country}", UserID)


def UpdateBanStatus(UserID: int) -> None:
    """Updates the ban statuses in bancho."""
    state.redis.publish("peppy:ban", str(UserID))


def SetBMAPSetStatus(BeatmapSet: int, Staus: int, session: "Session"):
    """Sets status for all beatmaps in beatmapset."""
    state.database.execute(
        "UPDATE beatmaps SET ranked = %s, ranked_status_freezed = 1 WHERE beatmapset_id = %s",
        (
            Staus,
            BeatmapSet,
        ),
    )

    # getting status text
    TitleText = "unranked"
    if Staus == 2:
        TitleText = "ranked"
    elif Staus == 5:
        TitleText = "loved"

    maps_data = state.database.fetch_all(
        "SELECT song_name, beatmap_id, beatmap_md5 FROM beatmaps WHERE beatmapset_id = %s",
        (BeatmapSet,),
    )

    # Getting bmap name without diff
    BmapName = maps_data[0][0].split("[")[0].rstrip()  # ¯\_(ツ)_/¯ might work
    # webhook, didnt use webhook function as it was too adapted for single map webhook
    webhook = DiscordWebhook(url=config.webhook_ranked)
    embed = DiscordEmbed(
        description=f"Ranked by {session.username}",
        color=242424,
    )

    embed.set_author(
        name=f"{BmapName} was just {TitleText}.",
        url=f"https://ussr.pl/b/{maps_data[0][1]}",
        icon_url=f"https://a.ussr.pl/{session.user_id}",
    )  # will rank to random diff but yea

    embed.set_footer(text="via RealistikPanel!")
    embed.set_image(url=f"https://assets.ppy.sh/beatmaps/{BeatmapSet}/covers/cover.jpg")
    webhook.add_embed(embed)

    logger.info("Posting webhook...")
    webhook.execute()

    # Refresh all lbs.
    for _, _, md5 in maps_data:
        refresh_bmap(md5)


def FindUserByUsername(User: str, Page: int) -> list[dict[str, Any]]:
    """Finds user by their username OR email."""
    # calculating page offsets
    Offset = 50 * (Page - 1)
    # checking if its an email
    Split = User.split("@")
    if (
        len(Split) == 2 and "." in Split[1]
    ):  # if its an email, 2nd check makes sure its an email and not someone trying to be A E S T H E T I C
        users = state.database.fetch_all(
            "SELECT id, username, privileges, allowed FROM users WHERE email LIKE %s LIMIT 50 OFFSET %s",
            (
                User,
                Offset,
            ),
        )  # i will keep the like statement unless it causes issues
    else:  # its a username
        User = f"%{User}%"  # for sql to treat is as substring
        users = state.database.fetch_all(
            "SELECT id, username, privileges, allowed FROM users WHERE username LIKE %s LIMIT 50 OFFSET %s",
            (
                User,
                Offset,
            ),
        )

    if not users:
        return []

    PrivilegeDict = {}
    AllPrivileges = []
    for person in users:
        AllPrivileges.append(person[2])
    UniquePrivileges = Unique(AllPrivileges)

    # gets all priv info (copy pasted from get users as it is based on same infestructure)
    for Priv in UniquePrivileges:
        priv_info = state.database.fetch_one(
            "SELECT name, color FROM privileges_groups WHERE privileges = %s LIMIT 1",
            (Priv,),
        )

        if not priv_info:
            PrivilegeDict[str(Priv)] = {
                "Name": f"Unknown ({Priv})",
                "Privileges": Priv,
                "Colour": "danger",
            }
        else:
            PrivilegeDict[str(Priv)] = {}
            PrivilegeDict[str(Priv)]["Name"] = priv_info[0]
            PrivilegeDict[str(Priv)]["Privileges"] = Priv
            PrivilegeDict[str(Priv)]["Colour"] = priv_info[1]
            if (
                PrivilegeDict[str(Priv)]["Colour"] == "default"
                or PrivilegeDict[str(Priv)]["Colour"] == ""
            ):
                # stisla doesnt have a default button so ill hard-code change it to a warning
                PrivilegeDict[str(Priv)]["Colour"] = "warning"

    TheUsersDict = []
    for yuser in users:
        # country query
        country = state.database.fetch_val(
            "SELECT country FROM users_stats WHERE id = %s",
            (yuser[0],),
        )

        if not country:
            country = "XX"

        Dict = {
            "Id": yuser[0],
            "Name": yuser[1],
            "Privilege": PrivilegeDict[str(yuser[2])],
            "Country": country,
        }

        if yuser[3] == 1:
            Dict["Allowed"] = True
        else:
            Dict["Allowed"] = False
        TheUsersDict.append(Dict)

    return TheUsersDict


def CreateBcrypt(Password: str):
    """Creates hashed password using the hashing methods of Ripple."""
    MD5Password = hashlib.md5(Password.encode("utf-8")).hexdigest()
    BHashed = bcrypt.hashpw(MD5Password.encode("utf-8"), bcrypt.gensalt(10))
    return BHashed.decode()


def ChangePassword(AccountID: int, NewPassword: str) -> None:
    """Changes the password of a user with given AccID"""
    BCrypted = CreateBcrypt(NewPassword)
    state.database.execute(
        "UPDATE users SET password_md5 = %s WHERE id = %s",
        (
            BCrypted,
            AccountID,
        ),
    )
    state.redis.publish("peppy:change_pass", json.dumps({"user_id": AccountID}))


def ChangePWForm(form: dict[str, str], session: "Session") -> None:  # this function may be unnecessary but ehh
    """Handles the change password POST request."""
    ChangePassword(int(form["accid"]), form["newpass"])
    User = GetUser(int(form["accid"]))
    RAPLog(
        session.user_id,
        f"has changed the password of {User['Username']} ({form['accid']})",
    )


def GiveSupporterForm(form: dict[str, str]) -> None:
    """Handles the give supporter form/POST request."""
    GiveSupporter(int(form["accid"]), int(form["time"]))

def convert_mode_to_str(mode: int) -> str:
    return {
        0: "osu!std",
        1: "osu!taiko",
        2: "osu!catch",
        3: "osu!mania",
    }.get(mode, "osu!std")

def GetRankRequests(Page: int) -> list[dict[str, Any]]:
    """Gets all the rank requests. This may require some optimisation."""
    Page -= 1
    Offset = 50 * Page  # for the page system to work
    requests = state.database.fetch_all(
        "SELECT id, userid, bid, type, time, blacklisted FROM rank_requests WHERE blacklisted = 0 LIMIT 50 OFFSET %s",
        (Offset,),
    )
    # turning what we have so far into
    TheRequests = []
    UserIDs = [] # used for later fetching the users, so we dont have a repeat of 50 queries
    for request in requests:
        # getting song info, like 50 individual queries at peak lmao
        TriedSet = False
        TriedBeatmap = False
        if request[3] == "s":
            request_data = state.database.fetch_one(
                "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmapset_id = %s LIMIT 1",
                (request[2],),
            )
            TriedSet = True
        else:
            request_data = state.database.fetch_one(
                "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmap_id = %s LIMIT 1",
                (request[2],),
            )
            TriedBeatmap = True

        # in case it was added incorrectly for some reason?
        if not request_data and TriedBeatmap:
            request_data = state.database.fetch_one(
                "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmapset_id = %s LIMIT 1",
                (request[2],),
            )
        elif not request_data and TriedSet:
            request_data = state.database.fetch_one(
                "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmap_id = %s LIMIT 1",
                (request[2],),
            )

        # if the info is bad
        if not request_data:
            SongName = "Darude - Sandstorm (Song not found)"
            BeatmapSetID = 0
            Cover = "https://i.ytimg.com/vi/erb4n8PW2qw/maxresdefault.jpg"
        else:
            SongName = request_data[0]
            SongName = SongName.split("[")[0].rstrip()  # kind of a way to get rid of diff name

            BeatmapSetID = request_data[1]
            Cover = f"https://assets.ppy.sh/beatmaps/{BeatmapSetID}/covers/cover.jpg"

        modes = state.database.fetch_all(
            "SELECT mode FROM beatmaps WHERE beatmapset_id = %s",
            (BeatmapSetID,),
        )
        unique_modes = Unique([mode[0] for mode in modes])
        string_modes = ", ".join([convert_mode_to_str(mode) for mode in unique_modes])

        # nice dict
        TheRequests.append(
            {
                "RequestID": request[0],
                "RequestBy": request[1],
                "RequestSongID": request[2],  # not specifically song id or set id
                "Type": request[3],  # s = set b = single diff
                "Time": request[4],
                "TimeFormatted": timestamp_as_date(request[4], False),
                "SongName": SongName,
                "Cover": Cover,
                "BeatmapSetID": BeatmapSetID,
                "Modes": string_modes,
            },
        )

        if request[1] not in UserIDs:
            UserIDs.append(request[1])

    # getting the Requester usernames
    Usernames = {}
    for AccoundIdentity in UserIDs:
        username = state.database.fetch_val("SELECT username FROM users WHERE id = %s", (AccoundIdentity,))

        if not username:
            Usernames[str(AccoundIdentity)] = {
                "Username": f"Unknown! ({AccoundIdentity})",
            }
        else:
            Usernames[str(AccoundIdentity)] = {"Username": username}

    # things arent going to be very performant lmao
    for i in range(0, len(TheRequests)):
        TheRequests[i]["RequestUsername"] = Usernames[str(TheRequests[i]["RequestBy"])]["Username"]

    # flip so it shows newest first yes
    TheRequests.reverse()
    return TheRequests


def DeleteBmapReq(Req: int) -> None:
    """Deletes the beatmap request."""
    state.database.execute("DELETE FROM rank_requests WHERE id = %s LIMIT 1", (Req,))


def UserPageCount() -> int:
    """Gets the amount of pages for users."""
    count = state.database.fetch_val("SELECT count(*) FROM users")
    return math.ceil(count / PAGE_SIZE)

def traceback_pages() -> int:
    """Gets the number of pages for the traceback page."""
    count = state.sqlite.fetch_val(
        "SELECT COUNT(*) FROM tracebacks",
    )

    return math.ceil(count / PAGE_SIZE)



def RapLogCount() -> int:
    """Gets the amount of pages for rap logs."""
    count = state.database.fetch_val("SELECT count(*) FROM rap_logs")
    return math.ceil(count / PAGE_SIZE)


def GetClans(Page: int = 1) -> list[dict[str, Any]]:
    """Gets a list of all clans (v1)."""
    # offsets and limits
    Page = int(Page) - 1
    Offset = 50 * Page
    # the sql part
    clans_data = state.database.fetch_all(
        "SELECT id, name, description, icon, tag FROM clans LIMIT 50 OFFSET %s",
        (Offset,),
    )
    # making cool, easy to work with dicts and arrays!
    Clans = []
    for Clan in clans_data:
        Clans.append({
            "ID": Clan[0],
            "Name": Clan[1],
            "Description": Clan[2],
            "Icon": Clan[3],
            "Tag": Clan[4],
        })

    return Clans


def GetClanPages() -> int:
    """Gets amount of pages for clans."""
    count = state.database.fetch_val("SELECT count(*) FROM clans")
    return math.ceil(count / PAGE_SIZE)


def GetClanMembers(ClanID: int) -> list[dict[str, Any]]:
    """Returns a list of clan members."""
    # ok so we assume the list isnt going to be too long
    clan_members = state.database.fetch_all("SELECT user FROM user_clans WHERE clan = %s", (ClanID,))
    if not clan_members:
        return []
    
    Conditions = ""
    args = []
    # this is so we can use one long query rather than a bunch of small ones
    for ClanUser in clan_members:
        Conditions += f"id = %s OR "
        args.append(ClanUser[0])
    Conditions = Conditions[:-4]  # remove the OR

    # getting the users
    members_data = state.database.fetch_all(
        f"SELECT username, id, register_datetime FROM users WHERE {Conditions}",
        tuple(args),
    )  # here i use format as the conditions are a trusted input

    # turning the data into a dictionary list
    ReturnList = []
    for User in members_data:
        ReturnList.append({
            "AccountID": User[1],
            "Username": User[0],
            "RegisterTimestamp": User[2],
            "RegisterAgo": TimeToTimeAgo(User[2]),
        })

    return ReturnList


def GetClan(ClanID: int) -> dict[str, Any]:
    """Gets information for a specified clan."""
    clan_data = state.database.fetch_one(
        "SELECT id, name, description, icon, tag, mlimit FROM clans WHERE id = %s LIMIT 1",
        (ClanID,),
    )
    if not clan_data:
        return {
            "ID": 0,
            "Name": "Unknown",
            "Description": "Unknown",
            "Icon": "",
            "Tag": "Unknown",
            "MemberLimit": 0,
            "MemberCount": 0,
        }
    
    # getting current member count
    member_count = state.database.fetch_val("SELECT COUNT(*) FROM user_clans WHERE clan = %s", (ClanID,))
    return {
        "ID": clan_data[0],
        "Name": clan_data[1],
        "Description": clan_data[2],
        "Icon": clan_data[3],
        "Tag": clan_data[4],
        "MemberLimit": clan_data[5],
        "MemberCount": member_count,
    }


def GetClanOwner(ClanID: int) -> dict[str, Any]:
    """Gets user info for the owner of a clan."""
    # wouldve been done quicker but i decided to play jawbreaker and only got up to 81%
    owner_id = state.database.fetch_val(
        "SELECT user FROM user_clans WHERE clan = %s and perms = 8",
        (ClanID,),
    )
    if not owner_id:
        return {
            "AccountID": 0,
            "Username": "Unknown",
        }

    # getting account info
    username = state.database.fetch_val(
        "SELECT username FROM users WHERE id = %s",
        (owner_id,),
    )  # will add more info maybe
    if not username:
        return {
            "AccountID": owner_id,
            "Username": "Unknown",
        }

    return {
        "AccountID": owner_id, 
        "Username": username
    }


def ApplyClanEdit(Form: dict[str, str], session: "Session") -> None:
    """Uses the post request to set new clan settings."""
    ClanID = Form["id"]
    ClanName = Form["name"]
    ClanDesc = Form["desc"]
    ClanTag = Form["tag"]
    ClanIcon = Form["icon"]
    MemberLimit = Form["limit"]
    state.database.execute(
        "UPDATE clans SET name = %s, description = %s, tag = %s, mlimit = %s, icon = %s WHERE id = %s LIMIT 1",
        (ClanName, ClanDesc, ClanTag, MemberLimit, ClanIcon, ClanID),
    )

    # Make all tags refresh.
    members = state.database.fetch_all("SELECT user FROM user_clans WHERE clan = %s", (ClanID,))

    for user_id in members:
        cache_clan(user_id[0])

    RAPLog(session.user_id, f"edited the clan {ClanName} ({ClanID})")


def NukeClan(ClanID: int, session: "Session") -> None:
    """Deletes a clan from the face of the earth."""
    Clan = GetClan(ClanID)
    if not Clan:
        return

    # Make all tags refresh.
    members = state.database.fetch_all("SELECT user FROM user_clans WHERE clan = %s", (ClanID,))

    state.database.execute("DELETE FROM clans WHERE id = %s LIMIT 1", (ClanID,))
    state.database.execute("DELETE FROM user_clans WHERE clan = %s", (ClanID,))
    # run this after

    for user_id in members:
        cache_clan(user_id[0])

    RAPLog(session.user_id, f"deleted the clan {Clan['Name']} ({ClanID})")


def KickFromClan(AccountID: int) -> None:
    """Kicks user from all clans (supposed to be only one)."""
    state.database.execute("DELETE FROM user_clans WHERE user = %s", (AccountID,))
    cache_clan(AccountID)


def GetUsersRegisteredBetween(Offset: int = 0, Ahead: int = 24) -> int:
    """Gets how many players registered during a given time period (variables are in hours)."""
    # convert the hours to secconds
    Offset *= 3600
    Ahead *= 3600

    CurrentTime = round(time.time())
    # now we get the time - offset
    OffsetTime = CurrentTime - Offset
    AheadTime = OffsetTime - Ahead

    count = state.database.fetch_val(
        "SELECT COUNT(*) FROM users WHERE register_datetime > %s AND register_datetime < %s",
        (AheadTime, OffsetTime),
    )
    return count


def GetUsersActiveBetween(Offset: int = 0, Ahead: int = 24) -> int:
    """Gets how many players were active during a given time period (variables are in hours)."""
    # yeah this is a reuse of the last function.
    # convert the hours to secconds
    Offset *= 3600
    Ahead *= 3600

    CurrentTime = round(time.time())
    # now we get the time - offset
    OffsetTime = CurrentTime - Offset
    AheadTime = OffsetTime - Ahead

    count = state.database.fetch_val(
        "SELECT COUNT(*) FROM users WHERE latest_activity > %s AND latest_activity < %s",
        (AheadTime, OffsetTime),
    )
    return count


def RippleSafeUsername(Username: str) -> str:
    """Generates a ripple-style safe username."""
    return Username.lower().replace(" ", "_").rstrip()


def GetSuggestedRank() -> list[dict[str, Any]]:
    """Gets suggested maps to rank (based on play count)."""
    beatmaps_data = state.database.fetch_all(
        "SELECT beatmap_id, song_name, beatmapset_id, playcount FROM beatmaps WHERE ranked = 0 ORDER BY playcount DESC LIMIT 8",
    )
    BeatmapList = []
    for TopBeatmap in beatmaps_data:
        modes = state.database.fetch_all(
            "SELECT mode FROM beatmaps WHERE beatmapset_id = %s",
            (TopBeatmap[2],),
        )
        unique_modes = Unique([mode[0] for mode in modes])
        string_modes = ", ".join([convert_mode_to_str(mode) for mode in unique_modes])
        BeatmapList.append(
            {
                "BeatmapId": TopBeatmap[0],
                "SongName": TopBeatmap[1].split("[")[0].rstrip(),
                "Cover": f"https://assets.ppy.sh/beatmaps/{TopBeatmap[2]}/covers/cover.jpg",
                "Playcount": TopBeatmap[3],
                "Modes": string_modes,
            },
        )

    return BeatmapList


def CountRestricted() -> int:
    """Calculates the amount of restricted or banned users."""
    count = state.database.fetch_val("SELECT COUNT(*) FROM users WHERE privileges = 2")
    return count

def GetStatistics(MinPP: int = 0) -> dict[str, Any]:
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


def CreatePrivilege() -> int:
    """Creates a new default privilege."""
    privilege_id = state.database.execute(
        "INSERT INTO privileges_groups (name, privileges, color) VALUES ('New Privilege', 0, '')",
    )
    return privilege_id


def CoolerInt(ToInt: Any) -> int:
    """Makes a number an int butt also works with special cases etc if ToInt is None, it returns a 0! Magic."""
    if not ToInt:
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
    first_place_data = state.database.fetch_one(
        "SELECT s.id, s.userid, s.score, s.max_combo, s.full_combo, s.mods, s.300_count,"
        "s.100_count, s.50_count, s.misses_count, s.time, s.play_mode, s.completed,"
        f"s.accuracy, s.pp, s.playtime, s.beatmap_md5 FROM {table} s RIGHT JOIN users a ON a.id = s.userid WHERE "
        "s.beatmap_md5 = %s AND s.play_mode = %s AND completed = 3 AND a.privileges & 2 ORDER BY pp "
        "DESC LIMIT 1",
        (beatmap_md5, mode),
    )

    # No scores at all.
    if not first_place_data:
        return

    # INSERT BRRRR
    state.database.execute(
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
        (*first_place_data, rx),
    )


# USSR Redis Support.
def cache_clan(user_id: int) -> None:
    """Updates LETS' cached clan tag for a specific user. This is a
    requirement for RealistikOsu lets, or else clan tags may get out of sync.
    """

    state.redis.publish("rosu:clan_update", str(user_id))


def refresh_bmap(md5: str) -> None:
    """Tells USSR to update the beatmap cache for a specific beatmap."""

    state.redis.publish("ussr:refresh_bmap", md5)


def refresh_username_cache(user_id: int, new_name: str) -> None:
    """Refreshes the username cache for a specific user."""

    state.redis.publish(
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


def fetch_banlogs(page: int = 0) -> list[BanLog]:
    """Fetches a page of ban logs."""

    ban_logs = state.database.fetch_all(
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
        for row in ban_logs
    ]


def ban_count() -> int:
    """Returns the total number of bans."""

    count = state.database.fetch_val("SELECT COUNT(*) FROM ban_logs")
    return count


def ban_pages() -> int:
    """Returns the number of pages in the ban log."""

    return math.ceil(ban_count() / PAGE_SIZE)


def request_count() -> int:
    """Returns the total number of requests."""

    count = state.database.fetch_val("SELECT COUNT(*) FROM rank_requests WHERE blacklisted = 0")
    return count


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
    ban_logs = state.database.fetch_all(BAN_LOG_BASE + "WHERE to_id = %s ORDER BY b.id DESC", (user_id,))

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
        for row in ban_logs
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
    invites = state.database.fetch_all(
        "SELECT id, clan, invite FROM clans_invites WHERE clan = %s",
        (clan_id,),
    )

    return [
        {
            "id": row[0],
            "clan_id": row[1],
            "invite_code": row[2],
        }
        for row in invites
    ]


def create_clan_invite(clan_id: int) -> ClanInvite:
    invite_code = random_str(8)
    invite_id = state.database.execute(
        "INSERT INTO clans_invites (clan, invite) VALUES (%s, %s)",
        (clan_id, invite_code),
    )

    return {
        "id": invite_id,
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
    hwid_history = state.database.fetch_all(
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
        for res in hwid_history
    ]


def get_hwid_history_paginated(user_id: int, page: int = 0) -> list[HWIDLog]:

    occurences = state.database.fetch_all(
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
        for res in occurences
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

    occurences = state.database.fetch_all(
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
        for res in occurences
    ]


def get_hwid_matches_partial(log: HWIDLog) -> list[HWIDLog]:
    """Gets a list of partially matching HWID logs (just one item has to match)
    for all users other than the origin of the initial log.

    Args:
        log (HWIDLog): The initial log to search for.

    Returns:
        list[HWIDLog]: A list of logs sharing at least one hash with `log`.
    """

    occurences = state.database.fetch_all(
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
        for res in occurences
    ]


def get_hwid_count(user_id: int) -> int:
    count = state.database.fetch_val("SELECT COUNT(*) FROM hw_user WHERE userid = %s", (user_id,))
    return count


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
