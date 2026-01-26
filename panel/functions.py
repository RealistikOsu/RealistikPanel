# Legacy panel functionality! DO NOT extend.
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import math
import random
import string
import time
import os
from typing import Any
from typing import cast
from typing import NamedTuple
from typing import Optional
from typing import TYPE_CHECKING
from typing import TypedDict
from typing import Union

import aiohttp
import bcrypt
import pycountry
import timeago

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


async def fix_bad_user_count() -> None:
    # fix potential crashes
    # have to do it this way as the crash issue is a connector module issue
    BadUserCount = await state.database.fetch_val(
        "SELECT COUNT(*) FROM users_stats WHERE userpage_content = ''",
    )
    if not BadUserCount or BadUserCount == 0:
        return

    logger.warning(
        f"Found {BadUserCount} users with potentially problematic data!",
    )
    await state.database.execute(
        "UPDATE users_stats SET userpage_content = NULL WHERE userpage_content = ''",
    )
    logger.info("Fixed problematic data!")


# public variables
PlayerCount = [0] * 10  # list of players with baseline


class Country(TypedDict):
    code: str
    name: str


def get_countries() -> list[Country]:
    resp_list = []
    for country in pycountry.countries:
        resp_list.append(
            {
                "code": country.alpha_2,
                "name": country.name,
            },
        )

    return cast(list[Country], resp_list)


async def log_traceback(
    traceback: str,
    session: Session,
    traceback_type: TracebackType,
) -> None:
    """Logs a traceback to the database."""
    await state.sqlite.execute(
        "INSERT INTO tracebacks (user_id, traceback, time, traceback_type) VALUES (?, ?, ?, ?)",
        (
            session.user_id,
            traceback,
            int(time.time()),
            traceback_type.value,
        ),
    )


async def get_tracebacks(page: int = 0) -> list[dict[str, Any]]:
    """Gets all tracebacks."""
    tracebacks = await state.sqlite.fetch_all(
        "SELECT user_id, traceback, time, traceback_type FROM "
        f"tracebacks ORDER BY time DESC LIMIT {PAGE_SIZE} OFFSET {PAGE_SIZE * page}",
    )

    resp_list = []
    for traceback in tracebacks:
        user = await GetUser(traceback[0])
        resp_list.append(
            {
                "user": user,
                "traceback": traceback[1],
                "time": timestamp_as_date(traceback[2], False),
                "traceback_type": traceback[3],
            },
        )

    return resp_list


async def load_dashboard_data() -> dict[str, Any]:
    """Grabs all the values for the dashboard."""
    alert = await state.database.fetch_val(
        "SELECT value_string FROM system_settings WHERE name = 'website_global_alert'",
    )

    total_pp = decode_int_or(await state.redis.get("ripple:total_pp"))
    registered_users = decode_int_or(await state.redis.get("ripple:registered_users"))
    online_users = decode_int_or(await state.redis.get("ripple:online_users"))
    total_plays = decode_int_or(await state.redis.get("ripple:total_plays"))
    total_scores = decode_int_or(await state.redis.get("ripple:total_submitted_scores"))

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
    privilege_name: str


async def LoginHandler(
    username: str,
    password: str,
) -> tuple[bool, Union[str, LoginUserData]]:
    """Checks the passwords and handles the sessions."""
    user = await state.database.fetch_one(
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

        if await has_privilege_value(user_id, Privileges.ADMIN_ACCESS_RAP):
            if compare_password(password, password_md5):
                # Get privilege name
                priv_name = await state.database.fetch_val(
                    "SELECT name FROM privileges_groups WHERE privileges = %s",
                    (privileges,),
                )
                if not priv_name:
                    priv_name = "Unknown Group"

                return (
                    True,
                    LoginUserData(user_id, username, Privileges(privileges), priv_name),
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


async def get_recent_plays(
    total_plays: int = 20,
    minimum_pp: int = 0,
) -> list[dict[str, Any]]:
    """Returns recent plays."""
    divisor = 1
    if config.srv_supports_relax:
        divisor += 1
    if config.srv_supports_autopilot:
        divisor += 1
    plays_per_gamemode = total_plays // divisor

    dash_plays = []

    plays = await state.database.fetch_all(
        BASE_RECENT_QUERY.format("scores"),
        (
            minimum_pp,
            plays_per_gamemode,
        ),
    )
    dash_plays.extend(plays)

    if config.srv_supports_relax:
        # adding relax plays
        plays_rx = await state.database.fetch_all(
            BASE_RECENT_QUERY.format("scores_relax"),
            (
                minimum_pp,
                plays_per_gamemode,
            ),
        )
        dash_plays.extend(plays_rx)

    if config.srv_supports_autopilot:
        # adding autopilot plays
        plays_ap = await state.database.fetch_all(
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


async def FetchBSData() -> dict:
    """Fetches Bancho Settings."""
    bancho_settings = await state.database.fetch_all(
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


async def handle_bancho_settings_edit(
    bancho_maintenence: str,
    menu_icon: str,
    login_notification: str,
    user_id: int,
) -> None:
    # setting blanks to bools
    bancho_maintenence_bool = bancho_maintenence == "On"

    # SQL Queries
    if menu_icon:
        await state.database.execute(
            "UPDATE bancho_settings SET value_string = %s, value_int = 1 WHERE name = 'menu_icon'",
            (menu_icon,),
        )
    else:
        await state.database.execute(
            "UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'menu_icon'",
        )

    if login_notification:
        await state.database.execute(
            "UPDATE bancho_settings SET value_string = %s, value_int = 1 WHERE name = 'login_notification'",
            (login_notification,),
        )
    else:
        await state.database.execute(
            "UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'login_notification'",
        )

    await state.database.execute(
        "UPDATE bancho_settings SET value_int = %s WHERE name = 'bancho_maintenance'",
        (int(bancho_maintenence_bool),),
    )

    await RAPLog(user_id, "modified the bancho settings")


import re


async def GetBmapInfo(
    bmap_id: int, user_id: Optional[int] = None
) -> list[dict[str, Any]]:
    """Gets beatmap info."""
    beatmapset_id = await state.database.fetch_val(
        "SELECT beatmapset_id FROM beatmaps WHERE beatmap_id = %s",
        (bmap_id,),
    )

    if not beatmapset_id:
        # it might be a beatmap set then
        beatmaps_data = await state.database.fetch_all(
            "SELECT song_name, ar, difficulty_std, beatmapset_id, beatmap_id, ranked, beatmap_md5, mode, max_combo FROM beatmaps WHERE beatmapset_id = %s",
            (bmap_id,),
        )

        if not beatmaps_data:  # if still havent found anything
            return [
                {
                    "SongName": "Not Found",
                    "DiffName": "Unknown",
                    "Ar": "0",
                    "Difficulty": "0",
                    "BeatmapsetId": "",
                    "BeatmapId": 0,
                    "Ranked": 0,
                    "BmapNumber": 0,
                    "Cover": "https://a.ussr.pl/",  # why this%s idk
                },
            ]
    else:
        beatmaps_data = await state.database.fetch_all(
            "SELECT song_name, ar, difficulty_std, beatmapset_id, beatmap_id, ranked, beatmap_md5, mode, max_combo FROM beatmaps WHERE beatmapset_id = %s",
            (beatmapset_id,),
        )

    if user_id:
        has_admin = await has_privilege_value(user_id, Privileges.ADMIN_MANAGE_BEATMAPS)
        mode_privs = {
            0: Privileges.ADMIN_MANAGE_STD_BEATMAPS,
            1: Privileges.ADMIN_MANAGE_TAIKO_BEATMAPS,
            2: Privileges.ADMIN_MANAGE_CTB_BEATMAPS,
            3: Privileges.ADMIN_MANAGE_MANIA_BEATMAPS,
        }

        if not has_admin:
            rankable_modes = []
            for mode in mode_privs:
                if await has_privilege_value(user_id, mode_privs[mode]):
                    rankable_modes.append(mode)

            if not rankable_modes:
                raise InsufficientPrivilegesError(
                    "You do not have permission to rank this beatmap."
                )

            beatmaps_data = [
                beatmap for beatmap in beatmaps_data if beatmap[7] in rankable_modes
            ]

    # Prepare payload for star rating calculation
    payload = []
    for beatmap in beatmaps_data:
        payload.append(
            {
                "beatmap_id": beatmap[4],
                "beatmap_md5": beatmap[6],
                "mode": beatmap[7],
                "mods": 0,
                "max_combo": beatmap[8] if beatmap[8] is not None else 0,
                "accuracy": 100.0,
                "miss_count": 0,
            }
        )

    # Fetch star ratings from API
    star_ratings = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.api_performance_url + "/api/v1/calculate", json=payload
            ) as resp:
                if resp.status == 200:
                    api_results = await resp.json()
                    # Map results back to beatmap_id for easy lookup
                    if isinstance(api_results, list) and len(api_results) == len(
                        payload
                    ):
                        for i, result in enumerate(api_results):
                            # result is expected to have 'stars' key
                            stars = result.get("stars")
                            if stars:
                                star_ratings[payload[i]["beatmap_id"]] = stars
                else:
                    logger.warning(f"Performance API returned status {resp.status}")
    except Exception as e:
        logger.error(f"Failed to fetch star ratings from API: {e}")

    BeatmapList = []
    for beatmap in beatmaps_data:
        full_name = beatmap[0]
        song_name = full_name
        diff_name = "Standard"

        # Regex to split "Artist - Title [Difficulty]"
        match = re.match(r"(.+)\s\[(.+)\]$", full_name)
        if match:
            song_name = match.group(1)
            diff_name = match.group(2)

        # Use calculated star rating if available, otherwise fallback to DB value
        difficulty = star_ratings.get(beatmap[4], beatmap[2])

        thing = {
            "SongName": song_name,
            "DiffName": diff_name,
            "Ar": str(beatmap[1]),
            "Difficulty": str(round(difficulty, 2)),
            "BeatmapsetId": str(beatmap[3]),
            "BeatmapId": str(beatmap[4]),
            "Ranked": beatmap[5],
            "Cover": f"https://assets.ppy.sh/beatmaps/{beatmap[3]}/covers/cover.jpg",
        }
        BeatmapList.append(thing)
    BeatmapList = sorted(BeatmapList, key=lambda i: float(i["Difficulty"]))

    # assigning each bmap a number to be later used
    BMapNumber = 0
    for beatmap in BeatmapList:
        BMapNumber = BMapNumber + 1
        beatmap["BmapNumber"] = BMapNumber
    return BeatmapList


async def has_privilege_value(user_id: int, privilege: Privileges) -> bool:
    # Fetch privileges from database.
    privileges = await state.database.fetch_val(
        "SELECT privileges FROM users WHERE id = %s",
        (user_id,),
    )

    if privileges is None:
        return False

    user_privileges = Privileges(privileges)

    return user_privileges & privilege == privilege


class InsufficientPrivilegesError(Exception):
    """Exception raised when a user does not have the required privileges."""

    def __init__(self, message: str) -> None:
        self.message = message


async def RankBeatmap(BeatmapId: int, ActionName: str, session: Session) -> None:
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

    mode = await state.database.fetch_val(
        "SELECT mode FROM beatmaps WHERE beatmap_id = %s LIMIT 1",
        (BeatmapId,),
    )

    mode_privs = {
        0: Privileges.ADMIN_MANAGE_STD_BEATMAPS,
        1: Privileges.ADMIN_MANAGE_TAIKO_BEATMAPS,
        2: Privileges.ADMIN_MANAGE_CATCH_BEATMAPS,
        3: Privileges.ADMIN_MANAGE_MANIA_BEATMAPS,
    }

    if mode is None:
        raise Exception("Beatmap not found.")

    has_admin = await has_privilege_value(
        session.user_id, Privileges.ADMIN_MANAGE_BEATMAPS
    )
    if not has_admin:
        if not await has_privilege_value(session.user_id, mode_privs[mode]):
            raise InsufficientPrivilegesError(
                f"Insufficient privileges to rank mode {mode}."
            )

    await state.database.execute(
        "UPDATE beatmaps SET ranked = %s, ranked_status_freezed = 1 WHERE beatmap_id = %s LIMIT 1",
        (
            ActionId,
            BeatmapId,
        ),
    )
    await Webhook(BeatmapId, ActionId, session)

    # USSR SUPPORT.
    # this reminds me i should swap ussr to usa
    map_md5 = await state.database.fetch_val(
        "SELECT beatmap_md5 FROM beatmaps WHERE beatmap_id = %s LIMIT 1",
        (BeatmapId,),
    )

    if map_md5:
        await refresh_bmap(map_md5)


async def send_discord_webhook(url: str, content: dict[str, Any]) -> None:
    """Async wrapper to send discord webhook"""
    async with aiohttp.ClientSession() as session:
        try:
            await session.post(url, json=content)
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")


async def FokaMessage(params: dict[str, Any]) -> None:
    """Sends a fokabot message."""
    async with aiohttp.ClientSession() as session:
        try:
            await session.get(
                config.api_bancho_url + "/api/v1/fokabotMessage", params=params
            )
        except Exception as e:
            logger.error(f"Failed to send fokabot message: {e}")


async def Webhook(BeatmapId: int, ActionId: int, session: Session) -> None:
    """Beatmap rank webhook."""
    URL = config.webhook_ranked
    if not URL:
        # if no webhook is set, dont do anything
        return

    map_data = await state.database.fetch_one(
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

    embed = {
        "description": f"Ranked by {session.username}",
        "color": 242424,
        "author": {
            "name": f"{map_data[0]} was just {TitleText}",
            "url": f"{config.srv_url}b/{BeatmapId}",
            "icon_url": f"{config.api_avatar_url}/{session.user_id}",
        },
        "footer": {"text": "via RealistikPanel!"},
        "image": {
            "url": f"https://assets.ppy.sh/beatmaps/{map_data[1]}/covers/cover.jpg"
        },
    }

    logger.info("Posting webhook....")
    await send_discord_webhook(URL, {"embeds": [embed]})

    Logtext = "unranked"
    if ActionId == 2:
        Logtext = "ranked"
    if ActionId == 5:
        Logtext = "loved"

    await RAPLog(session.user_id, f"{Logtext} the beatmap {map_data[0]} ({BeatmapId})")


async def RAPLog(
    UserID: int = 999, Text: str = "forgot to assign a text value :/"
) -> None:
    """Logs to the RAP log."""
    Timestamp = round(time.time())
    # now we putting that in oh yea
    await state.database.execute(
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

    Username = (await GetUser(UserID))["Username"]

    embed = {
        "description": f"{Username} {Text}",
        "color": 242424,
        "footer": {"text": "RealistikPanel Admin Logs"},
        "author": {
            "name": f"New action done by {Username}!",
            "url": f"{config.srv_url}u/{UserID}",
            "icon_url": f"{config.api_avatar_url}/{UserID}",
        },
    }

    await send_discord_webhook(config.webhook_admin_log, {"embeds": [embed]})


async def SystemSettingsValues() -> dict[str, Any]:
    """Fetches the system settings data."""
    system_settings = await state.database.fetch_all(
        "SELECT value_int, value_string FROM system_settings WHERE name = 'website_maintenance' OR name = 'game_maintenance' OR name = 'website_global_alert' OR name = 'website_home_alert' OR name = 'registrations_enabled'",
    )

    return {
        "webman": bool(system_settings[0][0]),
        "gameman": bool(system_settings[1][0]),
        "register": bool(system_settings[4][0]),
        "globalalert": system_settings[2][1],
        "homealert": system_settings[3][1],
    }


async def ApplySystemSettings(DataArray: list[str], user_id: int) -> None:
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
    await state.database.execute(
        "UPDATE system_settings SET value_int = %s WHERE name = 'website_maintenance'",
        (WebMan,),
    )
    await state.database.execute(
        "UPDATE system_settings SET value_int = %s WHERE name = 'game_maintenance'",
        (GameMan,),
    )
    await state.database.execute(
        "UPDATE system_settings SET value_int = %s WHERE name = 'registrations_enabled'",
        (Register,),
    )

    # if empty, disable
    if GlobalAlert != "":
        await state.database.execute(
            "UPDATE system_settings SET value_int = 1, value_string = %s WHERE name = 'website_global_alert'",
            (GlobalAlert,),
        )
    else:
        await state.database.execute(
            "UPDATE system_settings SET value_int = 0, value_string = '' WHERE name = 'website_global_alert'",
        )
    if HomeAlert != "":
        await state.database.execute(
            "UPDATE system_settings SET value_int = 1, value_string = %s WHERE name = 'website_home_alert'",
            (HomeAlert,),
        )
    else:
        await state.database.execute(
            "UPDATE system_settings SET value_int = 0, value_string = '' WHERE name = 'website_home_alert'",
        )

    await RAPLog(user_id, "updated the system settings.")


async def IsOnline(AccountId: int) -> bool:
    """Checks if given user is online."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{config.api_bancho_url}/api/status/{AccountId}"
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


async def CalcPP(BmapID: int) -> float:
    """Sends request to USSR to calc PP for beatmap id."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{config.api_ussr_url}api/v1/pp?b={BmapID}") as resp:
            reqjson = await resp.json()
            return round(reqjson["pp"][0], 2)


async def CalcPPRX(BmapID: int) -> float:
    """Sends request to USSR to calc PP for beatmap id with the Relax mod."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{config.api_ussr_url}api/v1/pp?b={BmapID}&m=128"
        ) as resp:
            reqjson = await resp.json()
            return round(reqjson["pp"][0], 2)


async def CalcPPAP(BmapID: int) -> float:
    """Sends request to USSR to calc PP for beatmap id with the Autopilot mod."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{config.api_ussr_url}api/v1/pp?b={BmapID}&m=8192"
        ) as resp:
            reqjson = await resp.json()
            return round(reqjson["pp"][0], 2)


def Unique(Alist: list) -> list:
    """Returns list of unique elements of list."""
    Uniques = []
    for x in Alist:
        if x not in Uniques:
            Uniques.append(x)
    return Uniques


async def FetchUsers(page: int = 0) -> list[dict[str, Any]]:
    """Fetches users for the users page."""
    # This is going to need a lot of patching up i can feel it
    Offset = 50 * page  # for the page system to work
    users = await state.database.fetch_all(
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
        priv_info = await state.database.fetch_one(
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
        if user[2] == 0 or user[2] == 2:
            Dict["Allowed"] = False
        else:
            Dict["Allowed"] = True
        Users.append(Dict)

    return Users


class SimpleUserData(TypedDict):
    Id: int
    Username: str
    IsOnline: bool
    Country: str


async def GetUser(user_id: int) -> SimpleUserData:
    """Gets data for user. (universal)"""
    user_data = await state.database.fetch_one(
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
        "IsOnline": await IsOnline(user_id),
        "Country": user_data[2],
    }


async def UserData(UserID: int) -> dict[str, Any]:
    """Gets data for user (specialised for user edit page)."""
    # fix badbad data
    await state.database.execute(
        "UPDATE users_stats SET userpage_content = NULL WHERE userpage_content = '' AND id = %s",
        (UserID,),
    )

    user_data = await GetUser(UserID)
    user_data2 = await state.database.fetch_one(
        "SELECT userpage_content, user_color, username_aka FROM users_stats WHERE id = %s LIMIT 1",
        (UserID,),
    )

    if not user_data2:
        user_data2 = ["", "default", ""]

    user_data3 = await state.database.fetch_one(
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
    ip_val = await state.database.fetch_val(
        "SELECT ip FROM ip_user WHERE userid = %s ORDER BY ip DESC LIMIT 1",
        (UserID,),
    )
    if not ip_val:
        ip_val = "0.0.0.0"

    # gets privilege name
    privilege_name = await state.database.fetch_val(
        "SELECT name FROM privileges_groups WHERE privileges = %s LIMIT 1",
        (user_data3[2],),
    )

    if not privilege_name:
        privilege_name = f"Unknown ({user_data3[2]})"

    # adds new info to dict
    # I dont use the discord features from RAP so i didnt include the discord settings but if you complain enough ill add them
    try:
        freeze_val = await state.database.fetch_val(
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

    whitelist = await is_whitelisted(UserID)

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
        "Avatar": f"{config.api_avatar_url}/{UserID}",
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
        "IsOnline": await IsOnline(UserID),
        "SilenceEndAgo": TimeToTimeAgo(CoolerInt(user_data3[5])),
        "Whitelisted": whitelist,
    }
    if freeze_val:
        user_data["IsFrozen"] = int(freeze_val) > 0
        user_data["FreezeDateNo"] = int(freeze_val)
        user_data["FreezeDate"] = TimeToTimeAgo(user_data["FreezeDateNo"])
    else:
        user_data["IsFrozen"] = False

    return user_data


async def RAPFetch(page: int = 1) -> list[dict[str, Any]]:
    """Fetches RAP Logs."""
    page = int(page) - 1  # makes sure is int and is in ok format
    Offset = 50 * page

    panel_logs = await state.database.fetch_all(
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
        UserData = await GetUser(user)
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


async def GetPrivileges() -> list[dict[str, Any]]:
    """Gets list of privileges."""
    privileges = await state.database.fetch_all("SELECT * FROM privileges_groups")

    if not privileges:
        return []

    Privs = []
    for x in privileges:
        Privs.append(
            {
                "Id": x[0],
                "Name": x[1],
                "Priv": x[2],
                "Colour": x[3],
            },
        )

    return Privs


async def ApplyUserEdit(form: dict[str, str], from_id: int) -> Union[None, str]:
    """Apples the user settings."""

    # getting variables from form
    UserId = int(form.get("userid", "0"))
    Aka = form.get("aka", "")
    Email = form.get("email", "")
    Country = form.get("country", "")
    UserPage = form.get("userpage", "")
    Notes = form.get("notes", "")
    Privilege = form.get("privilege", "0")
    HWIDBypass = form.get("hwid_bypass", "0") == "1"

    old_data = await GetUser(UserId)

    # fixing crash bug
    if UserPage == "":
        UserPage = None

    # stop people ascending themselves
    # OriginalPriv = int(session["Privilege"])
    if int(UserId) == from_id:
        privileges = await state.database.fetch_val(
            "SELECT privileges FROM users WHERE id = %s",
            (from_id,),
        )
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
    await SetUserBadges(UserId, BadgeList)
    # SQL Queries
    # TODO: transaction?
    await state.database.execute(
        "UPDATE users SET email = %s, notes = %s, privileges = %s, bypass_hwid = %s, country = %s WHERE id = %s",
        (
            Email,
            Notes,
            Privilege,
            HWIDBypass,
            Country,
            UserId,
        ),
    )
    await state.database.execute(
        "UPDATE users_stats SET userpage_content = %s, username_aka = %s WHERE id = %s",
        (
            UserPage,
            Aka,
            UserId,
        ),
    )

    # Refresh in pep.py - Rosu only
    await state.redis.publish("peppy:refresh_privs", json.dumps({"user_id": UserId}))
    await RAPLog(
        from_id,
        f"has edited the user {old_data['Username']} ({UserId})",
    )

    # Force pep.py to reload data.
    await BanchoKick(UserId, "Reloading data...")


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


async def DeleteProfileComments(AccId: int) -> None:
    await state.database.execute("DELETE FROM user_comments WHERE prof = %s", (AccId,))


async def DeleteUserComments(AccId: int) -> None:
    await state.database.execute("DELETE FROM user_comments WHERE op = %s", (AccId,))


async def WipeUserStats(user_id: int, modes: list[int], mods: list[str]) -> None:
    """
    Wipes user stats and scores for specific modes and mods.

    modes: List of mode IDs (0: std, 1: taiko, 2: ctb, 3: mania)
    mods: List of mod strings ("va", "rx", "ap")
    """

    # Mapping of mode ID to suffix in database columns
    mode_suffixes = {0: "_std", 1: "_taiko", 2: "_ctb", 3: "_mania"}

    # 1. Wipe Vanilla
    if "va" in mods:
        # construct update query
        updates = []
        for mode in modes:
            suffix = mode_suffixes.get(mode)
            if suffix:
                updates.extend(
                    [
                        f"ranked_score{suffix} = 0",
                        f"playcount{suffix} = 0",
                        f"total_score{suffix} = 0",
                        f"replays_watched{suffix} = 0",
                        f"total_hits{suffix} = 0",
                        f"level{suffix} = 0",
                        f"playtime{suffix} = 0",
                        f"avg_accuracy{suffix} = 0.000000000000",
                        f"pp{suffix} = 0",
                    ]
                )
                # special case for unrestricted_pp if std
                if mode == 0:
                    updates.append("unrestricted_pp = 0")

        if updates:
            query = f"UPDATE users_stats SET {', '.join(updates)} WHERE id = %s"
            await state.database.execute(query, (user_id,))

        # Delete scores
        modes_sql = ",".join([str(m) for m in modes])
        await state.database.execute(
            f"DELETE FROM scores WHERE userid = %s AND play_mode IN ({modes_sql})",
            (user_id,),
        )
        # User playcounts per map - we can't easily filter by mode here as the table doesn't have it?
        # users_beatmap_playcount: user_id, beatmap_id, count. Beatmap has mode.
        # It's a bit complex playcount wipe, maybe just leave it or do a complex join delete?
        # For now, let's stick to stats and scores which is the main thing.

    # 2. Wipe Relax
    if "rx" in mods and config.srv_supports_relax:
        updates = []
        for mode in modes:
            suffix = mode_suffixes.get(mode)
            if suffix:
                updates.extend(
                    [
                        f"ranked_score{suffix} = 0",
                        f"playcount{suffix} = 0",
                        f"total_score{suffix} = 0",
                        f"replays_watched{suffix} = 0",
                        f"total_hits{suffix} = 0",
                        f"level{suffix} = 0",
                        f"playtime{suffix} = 0",
                        f"avg_accuracy{suffix} = 0.000000000000",
                        f"pp{suffix} = 0",
                    ]
                )
                if mode == 0:
                    updates.append("unrestricted_pp = 0")

        if updates:
            query = f"UPDATE rx_stats SET {', '.join(updates)} WHERE id = %s"
            await state.database.execute(query, (user_id,))

        modes_sql = ",".join([str(m) for m in modes])
        await state.database.execute(
            f"DELETE FROM scores_relax WHERE userid = %s AND play_mode IN ({modes_sql})",
            (user_id,),
        )

    # 3. Wipe Autopilot
    if "ap" in mods and config.srv_supports_autopilot:
        updates = []
        for mode in modes:
            suffix = mode_suffixes.get(mode)
            if suffix:
                updates.extend(
                    [
                        f"ranked_score{suffix} = 0",
                        f"playcount{suffix} = 0",
                        f"total_score{suffix} = 0",
                        f"replays_watched{suffix} = 0",
                        f"total_hits{suffix} = 0",
                        f"level{suffix} = 0",
                        f"playtime{suffix} = 0",
                        f"avg_accuracy{suffix} = 0.000000000000",
                        f"pp{suffix} = 0",
                    ]
                )
                if mode == 0:
                    updates.append("unrestricted_pp = 0")

        if updates:
            query = f"UPDATE ap_stats SET {', '.join(updates)} WHERE id = %s"
            await state.database.execute(query, (user_id,))

        modes_sql = ",".join([str(m) for m in modes])
        await state.database.execute(
            f"DELETE FROM scores_ap WHERE userid = %s AND play_mode IN ({modes_sql})",
            (user_id,),
        )


async def WipeAccount(AccId: int) -> None:
    """Wipes the account with the given id."""
    await state.redis.publish(
        "peppy:disconnect",
        json.dumps(
            {
                "userID": AccId,
                "reason": "Your account has been wiped! F",
            },
        ),
    )

    # TODO: transaction?
    # Wipes EVERYTHING (all modes, all mods)
    await WipeUserStats(AccId, [0, 1, 2, 3], ["va", "rx", "ap"])


# Deprecated/Legacy wrappers if needed, but we will mostly use WipeUserStats directly
async def WipeVanilla(AccId: int) -> None:
    await WipeUserStats(AccId, [0, 1, 2, 3], ["va"])


async def WipeRelax(AccId: int) -> None:
    await WipeUserStats(AccId, [0, 1, 2, 3], ["rx"])


async def WipeAutopilot(AccId: int) -> None:
    await WipeUserStats(AccId, [0, 1, 2, 3], ["ap"])


async def RollbackUser(
    user_id: int,
    days: int,
    from_id: int,
    modes: list[int] = [0, 1, 2, 3],
    mods: list[str] = ["va", "rx", "ap"],
) -> None:
    """Rolls back user scores by X days."""
    cutoff = int(time.time()) - (days * 86400)

    tables = []
    if "va" in mods:
        tables.append(("scores", 0))
    if "rx" in mods and config.srv_supports_relax:
        tables.append(("scores_relax", 1))
    if "ap" in mods and config.srv_supports_autopilot:
        tables.append(("scores_ap", 2))

    if not tables:
        return

    # Prepare SQL for modes checking
    # We can't easily pass a list to SQL IN clause with aiomysql/databases properly without formatting,
    # but for ints it's safeish if we validate.
    # modes is list of ints 0-3.
    modes_sql = ",".join([str(m) for m in modes])

    for table, rx in tables:
        # Get beatmaps affected to recalculate first places later
        affected_maps = await state.database.fetch_all(
            f"SELECT beatmap_md5, play_mode FROM {table} WHERE userid = %s AND time > %s AND play_mode IN ({modes_sql})",
            (user_id, cutoff),
        )

        # Delete scores
        await state.database.execute(
            f"DELETE FROM {table} WHERE userid = %s AND time > %s AND play_mode IN ({modes_sql})",
            (user_id, cutoff),
        )

        # Recalculate first places for affected beatmaps
        for bmap_md5, mode in affected_maps:
            # Delete current first place entry if it was from this user
            await state.database.execute(
                "DELETE FROM first_places WHERE beatmap_md5 = %s AND user_id = %s AND relax = %s AND mode = %s",
                (bmap_md5, user_id, rx, mode),
            )
            # Recalculate
            await calc_first_place(bmap_md5, rx, mode)

    # Force pep.py to reload data if possible, though there isn't a specific "recalc stats" event
    # We'll just kick the user so they can reconnect and hopefully stats update on next play
    await BanchoKick(user_id, "Your account has been rolled back. Please reconnect.")


async def ResUnTrict(
    user_id: int, from_id: int, note: str = "", reason: str = ""
) -> bool:
    """Restricts or unrestricts account yeah."""
    if reason:
        await state.database.execute(
            "UPDATE users SET ban_reason = %s WHERE id = %s",
            (
                reason,
                user_id,
            ),
        )

    privileges = await state.database.fetch_val(
        "SELECT privileges FROM users WHERE id = %s",
        (user_id,),
    )
    if privileges is None:
        return False

    if not privileges & 1:  # if restricted
        new_privs = privileges | 1
        await state.database.execute(
            "UPDATE users SET privileges = %s, ban_datetime = 0 WHERE id = %s LIMIT 1",
            (
                new_privs,
                user_id,
            ),
        )  # unrestricts
        await state.database.execute(
            "INSERT INTO ban_logs (from_id, to_id, summary, detail) VALUES (%s, %s, %s, %s)",
            (
                from_id,
                user_id,
                "Unrestrict",
                reason if reason else "No reason provided.",
            ),
        )
        TheReturn = False
    else:
        TimeBan = round(time.time())
        await state.database.execute(
            "UPDATE users SET privileges = 2, ban_datetime = %s WHERE id = %s",
            (
                TimeBan,
                user_id,
            ),
        )  # restrict em bois
        await RemoveFromLeaderboard(user_id)
        await state.database.execute(
            "INSERT INTO ban_logs (from_id, to_id, summary, detail) VALUES (%s, %s, %s, %s)",
            (from_id, user_id, "Restrict", reason if reason else "No reason provided."),
        )
        TheReturn = True

        # We append the note if it exists to the thingy init bruv
        if note:
            await state.database.execute(
                "UPDATE users SET notes = CONCAT(notes, %s) WHERE id = %s LIMIT 1",
                ("\n" + note, user_id),
            )

        # First places KILL.
        recalc_md5s = await state.database.fetch_all(
            "SELECT beatmap_md5 FROM first_places WHERE user_id = %s",
            (user_id,),
        )

        # Delete all of their old.
        await state.database.execute(
            "DELETE FROM first_places WHERE user_id = %s",
            (user_id,),
        )
        for bmap_md5 in recalc_md5s:
            await calc_first_place(bmap_md5[0])

    await UpdateBanStatus(user_id)
    return TheReturn


async def FreezeHandler(user_id: int) -> bool:
    freeze_status = await state.database.fetch_val(
        "SELECT frozen FROM users WHERE id = %s",
        (user_id,),
    )
    if freeze_status is None:
        return False

    if freeze_status:
        await state.database.execute(
            "UPDATE users SET frozen = 0, freezedate = 0, firstloginafterfrozen = 1 WHERE id = %s",
            (user_id,),
        )
        TheReturn = False
    else:
        freezedate = datetime.datetime.now() + datetime.timedelta(days=5)
        freezedateunix = (freezedate - datetime.datetime(1970, 1, 1)).total_seconds()

        await state.database.execute(
            "UPDATE users SET frozen = 1, freezedate = %s WHERE id = %s",
            (
                freezedateunix,
                user_id,
            ),
        )

        TheReturn = True

    return TheReturn


async def BanUser(user_id: int, from_id: int, reason: str = "") -> bool:
    """User go bye bye!"""
    if reason:
        await state.database.execute(
            "UPDATE users SET ban_reason = %s WHERE id = %s",
            (
                reason,
                user_id,
            ),
        )

    privileges = await state.database.fetch_val(
        "SELECT privileges FROM users WHERE id = %s",
        (user_id,),
    )
    if privileges is None:
        return False

    Timestamp = round(time.time())
    if privileges == 0:  # if already banned
        await state.database.execute(
            "UPDATE users SET privileges = 3, ban_datetime = '0' WHERE id = %s",
            (user_id,),
        )
        await state.database.execute(
            "INSERT INTO ban_logs (from_id, to_id, summary, detail) VALUES (%s, %s, %s, %s)",
            (from_id, user_id, "Unban", reason if reason else "No reason provided."),
        )
        TheReturn = False
    else:
        await state.database.execute(
            "UPDATE users SET privileges = 0, ban_datetime = %s WHERE id = %s",
            (
                Timestamp,
                user_id,
            ),
        )
        await RemoveFromLeaderboard(user_id)
        await state.redis.publish(
            "peppy:disconnect",
            json.dumps(
                {
                    "userID": user_id,
                    "reason": f"You have been banned from {config.srv_name}. You will not be missed.",
                },
            ),
        )
        await state.database.execute(
            "INSERT INTO ban_logs (from_id, to_id, summary, detail) VALUES (%s, %s, %s, %s)",
            (from_id, user_id, "Ban", reason if reason else "No reason provided."),
        )
        TheReturn = True

    await UpdateBanStatus(user_id)
    return TheReturn


async def ClearHWID(user_id: int) -> None:
    """Clears the HWID matches for provided acc."""
    await state.database.execute("DELETE FROM hw_user WHERE userid = %s", (user_id,))


async def DeleteAccount(user_id: int) -> None:
    """Deletes the account provided. Press F to pay respects."""
    await state.redis.publish(
        "peppy:disconnect",
        json.dumps(
            {
                "userID": user_id,
                "reason": f"You have been deleted from {config.srv_name}. Bye!",
            },
        ),
    )
    # NUKE. BIG NUKE.
    await state.database.execute("DELETE FROM scores WHERE userid = %s", (user_id,))
    await state.database.execute("DELETE FROM users WHERE id = %s", (user_id,))
    await state.database.execute("DELETE FROM 2fa WHERE userid = %s", (user_id,))
    await state.database.execute(
        "DELETE FROM 2fa_telegram WHERE userid = %s", (user_id,)
    )
    await state.database.execute("DELETE FROM 2fa_totp WHERE userid = %s", (user_id,))
    await state.database.execute(
        "DELETE FROM beatmaps_rating WHERE user_id = %s", (user_id,)
    )
    await state.database.execute("DELETE FROM comments WHERE user_id = %s", (user_id,))
    await state.database.execute(
        "DELETE FROM discord_roles WHERE userid = %s", (user_id,)
    )
    await state.database.execute("DELETE FROM ip_user WHERE userid = %s", (user_id,))
    await state.database.execute(
        "DELETE FROM profile_backgrounds WHERE uid = %s", (user_id,)
    )
    await state.database.execute(
        "DELETE FROM rank_requests WHERE userid = %s", (user_id,)
    )
    await state.database.execute(
        "DELETE FROM reports WHERE to_uid = %s OR from_uid = %s",
        (
            user_id,
            user_id,
        ),
    )
    await state.database.execute("DELETE FROM tokens WHERE user = %s", (user_id,))
    await state.database.execute("DELETE FROM remember WHERE userid = %s", (user_id,))
    await state.database.execute(
        "DELETE FROM users_achievements WHERE user_id = %s",
        (user_id,),
    )
    await state.database.execute(
        "DELETE FROM users_beatmap_playcount WHERE user_id = %s",
        (user_id,),
    )
    await state.database.execute(
        "DELETE FROM users_relationships WHERE user1 = %s OR user2 = %s",
        (
            user_id,
            user_id,
        ),
    )
    await state.database.execute("DELETE FROM user_badges WHERE user = %s", (user_id,))
    await state.database.execute("DELETE FROM user_clans WHERE user = %s", (user_id,))
    await state.database.execute("DELETE FROM users_stats WHERE id = %s", (user_id,))
    if config.srv_supports_relax:
        await state.database.execute(
            "DELETE FROM scores_relax WHERE userid = %s", (user_id,)
        )
        await state.database.execute("DELETE FROM rx_stats WHERE id = %s", (user_id,))
    if config.srv_supports_autopilot:
        await state.database.execute(
            "DELETE FROM scores_ap WHERE userid = %s", (user_id,)
        )
        await state.database.execute("DELETE FROM ap_stats WHERE id = %s", (user_id,))


async def BanchoKick(id: int, reason: str) -> None:
    """Kicks the user from Bancho."""
    await state.redis.publish(
        "peppy:disconnect",
        json.dumps({"userID": id, "reason": reason}),  # lets the user know what is up
    )


async def FindWithIp(Ip: str) -> list[dict[str, Any]]:
    """Gets array of users."""
    # fetching user id of person with given ip
    occurences = await state.database.fetch_all(
        "SELECT userid, ip, occurencies FROM ip_user WHERE ip = %s",
        (Ip,),
    )

    resp_list = []
    for occurence in occurences:
        user_data = cast(dict, await GetUser(occurence[0]))
        user_data["Ip"] = occurence[1]
        user_data["Occurencies"] = occurence[2]
        resp_list.append(user_data)

    return resp_list


async def find_priv(priv: int) -> dict[str, Any]:
    priv_info = await state.database.fetch_one(
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


async def find_all_ips(user_id: int) -> list[dict[str, Any]]:
    """Gets array of users."""
    # fetching user id of person with given ip
    resp = await state.database.fetch_all(
        "SELECT ip FROM ip_user WHERE userid = %s AND ip != ''",
        (user_id,),
    )

    if not resp:
        return []

    ips = []
    for ip in resp:
        ips.append(ip[0])

    condition = ", ".join(["%s"] * len(ips))

    occurences = await state.database.fetch_all(
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

        data.append(
            {
                "user_id": user[0],
                "ip": user[1],
                "occurencies": user[2],
                "username": user[3],
                "privileges": await find_priv(user[4]),
                "priv_status": {"text": priv_status, "colour": priv_colour},
            },
        )

    return data


async def PlayerCountCollection() -> None:
    """Designed to be ran as a background task. Grabs player count every set interval and puts in array."""
    while True:
        try:
            val = await state.redis.get("ripple:online_users")
            CurrentCount = decode_int_or(val, 0)

            PlayerCount.append(CurrentCount)
            if len(PlayerCount) > 100:
                PlayerCount.pop(0)
        except Exception as e:
            logger.error(f"Failed to collect player count: {e}")

        # Async sleep for 300 seconds
        await asyncio.sleep(300)


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


async def GiveSupporter(AccountID: int, Duration: int = 30) -> None:
    """Gives the target user supporter.
    Args:
        AccountID (int): The account id of the target user.
        Duration (int): The time (in days) that the supporter rank should last
    """  # messing around with docstrings
    # checking if person already has supporter
    # also i believe there is a way better to do this, i am tired and may rewrite this and lower the query count
    privileges = await state.database.fetch_val(
        "SELECT privileges FROM users WHERE id = %s LIMIT 1",
        (AccountID,),
    )
    if not privileges:
        return

    if privileges & 4:
        # already has supporter, extending
        ends_on = await state.database.fetch_val(
            "SELECT donor_expire FROM users WHERE id = %s",
            (AccountID,),
        )
        ends_on += 86400 * Duration

        await state.database.execute(
            "UPDATE users SET donor_expire = %s WHERE id=%s",
            (
                ends_on,
                AccountID,
            ),
        )

    else:
        EndTimestamp = round(time.time()) + (86400 * Duration)
        privileges += 4  # adding donor perms

        await state.database.execute(
            "UPDATE users SET privileges = %s, donor_expire = %s WHERE id = %s",
            (
                privileges,
                EndTimestamp,
                AccountID,
            ),
        )

        # allowing them to set custom badges
        await state.database.execute(
            "UPDATE users_stats SET can_custom_badge = 1 WHERE id = %s LIMIT 1",
            (AccountID,),
        )
        # now we give them the badge
        await state.database.execute(
            "INSERT INTO user_badges (user, badge) VALUES (%s, %s)",
            (AccountID, config.srv_donor_badge_id),
        )


async def RemoveSupporter(AccountID: int, session: Session) -> None:
    """Removes supporter from the target user."""
    privileges = await state.database.fetch_val(
        "SELECT privileges FROM users WHERE id = %s LIMIT 1",
        (AccountID,),
    )
    if not privileges:
        return

    # checking if they dont have it so privs arent messed up
    if not privileges & 4:
        return

    privileges -= 4
    await state.database.execute(
        "UPDATE users SET privileges = %s, donor_expire = 0 WHERE id = %s",
        (
            privileges,
            AccountID,
        ),
    )
    # remove custom badge perms and hide custom badge
    await state.database.execute(
        "UPDATE users_stats SET can_custom_badge = 0, show_custom_badge = 0 WHERE id = %s LIMIT 1",
        (AccountID,),
    )
    # removing el donor badge
    await state.database.execute(
        "DELETE FROM user_badges WHERE user = %s AND badge = %s LIMIT 1",
        (AccountID, config.srv_donor_badge_id),
    )

    User = await GetUser(AccountID)
    await RAPLog(
        session.user_id,
        f"deleted the supporter role for {User['Username']} ({AccountID})",
    )


async def GetBadges() -> list[dict[str, Any]]:
    """Gets all the badges."""
    badges_data = await state.database.fetch_all("SELECT * FROM badges")
    Badges = []

    for badge in badges_data:
        Badges.append({"Id": badge[0], "Name": badge[1], "Icon": badge[2]})

    return Badges


async def DeleteBadge(BadgeId: int) -> None:
    """ "Delets the badge with the gived id."""
    await state.database.execute("DELETE FROM badges WHERE id = %s", (BadgeId,))
    await state.database.execute("DELETE FROM user_badges WHERE badge = %s", (BadgeId,))


async def GetBadge(BadgeID: int) -> dict[str, Any]:
    """Gets data of given badge."""
    badge_data = await state.database.fetch_one(
        "SELECT * FROM badges WHERE id = %s LIMIT 1",
        (BadgeID,),
    )

    if not badge_data:
        return {
            "Id": 0,
            "Name": "Unknown",
            "Icon": "",
        }

    return {"Id": badge_data[0], "Name": badge_data[1], "Icon": badge_data[2]}


async def SaveBadge(form: dict[str, str]) -> None:
    """Saves the edits done to the badge."""
    BadgeID = form["badgeid"]
    BadgeName = form["name"]
    BadgeIcon = form["icon"]
    await state.database.execute(
        "UPDATE badges SET name = %s, icon = %s WHERE id = %s",
        (
            BadgeName,
            BadgeIcon,
            BadgeID,
        ),
    )


async def CreateBadge() -> int:
    """Creates empty badge."""
    badge_id = await state.database.execute(
        "INSERT INTO badges (name, icon) VALUES ('New Badge', '')",
    )
    return badge_id


async def GetPriv(PrivID: int) -> dict[str, Any]:
    """Gets the priv data from ID."""
    priv_data = await state.database.fetch_one(
        "SELECT * FROM privileges_groups WHERE id = %s",
        (PrivID,),
    )

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
        "Colour": priv_data[3],
    }


async def DelPriv(PrivID: int) -> None:
    """Deletes a privilege group."""
    await state.database.execute(
        "DELETE FROM privileges_groups WHERE id = %s", (PrivID,)
    )


async def UpdatePriv(Form: dict[str, str]) -> None:
    """Updates the privilege from form."""
    # Get previous privilege number
    privileges = await state.database.fetch_val(
        "SELECT privileges FROM privileges_groups WHERE id = %s",
        (Form["id"],),
    )
    if privileges is None:
        return

    # Update group
    await state.database.execute(
        "UPDATE privileges_groups SET name = %s, privileges = %s, color = %s WHERE id = %s LIMIT 1",
        (Form["name"], Form["privilege"], Form["colour"], Form["id"]),
    )
    # update privs for users
    # TheFormPriv = int(Form["privilege"])
    # if TheFormPriv != 0 and TheFormPriv != 3 and TheFormPriv != 2: #i accidentally modded everyone because of this....
    #    mycursor.execute("UPDATE users SET privileges = REPLACE(privileges, %s, %s)", (PrevPriv, TheFormPriv,))


async def GetMostPlayed() -> dict[str, Any]:
    """Gets the beatmap with the highest playcount."""
    beatmap = await state.database.fetch_one(
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


async def GetUserBadges(AccountID: int) -> list[int]:
    """Gets badges of a user and returns as list."""
    badges = await state.database.fetch_all(
        "SELECT badge FROM user_badges WHERE user = %s",
        (AccountID,),
    )

    Badges = []
    for badge in badges:
        Badges.append(badge[0])

    # so we dont run into errors where people have no/less than 6 badges
    while len(Badges) < 6:
        Badges.append(0)

    return Badges


async def SetUserBadges(AccountID: int, Badges: list[int]) -> None:
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
    await state.database.execute(
        "DELETE FROM user_badges WHERE user = %s",
        (AccountID,),
    )  # deletes all existing badges

    for Badge in Badges:
        if Badge != 0 and Badge != 1:  # so we dont add empty badges
            await state.database.execute(
                "INSERT INTO user_badges (user, badge) VALUES (%s, %s)",
                (
                    AccountID,
                    Badge,
                ),
            )


async def GetUserID(Username: str) -> int:
    """Gets user id from username."""
    user_id = await state.database.fetch_val(
        "SELECT id FROM users WHERE username LIKE %s LIMIT 1",
        (Username,),
    )
    if not user_id:
        return 0

    return user_id


def TimeToTimeAgo(Timestamp: int) -> str:
    """Converts a seconds timestamp to a timeago string."""
    try:
        DTObj = datetime.datetime.fromtimestamp(Timestamp)
    except (OSError, ValueError):
        return "Unknown"

    CurrentTime = datetime.datetime.now()
    base_time = timeago.format(DTObj, CurrentTime)

    return f"{base_time} ({DTObj.strftime('%d/%m/%Y %H:%M')})"


async def RemoveFromLeaderboard(UserID: int) -> None:
    """Removes the user from leaderboards."""
    Modes = ["std", "ctb", "mania", "taiko"]
    for mode in Modes:
        # redis for each mode
        await state.redis.zrem(f"ripple:leaderboard:{mode}", UserID)
        if config.srv_supports_relax:
            # removes from relax leaderboards
            await state.redis.zrem(f"ripple:leaderboard_relax:{mode}", UserID)
        if config.srv_supports_autopilot:
            await state.redis.zrem(f"ripple:leaderboard_ap:{mode}", UserID)

        # removing from country leaderboards
        country = await state.database.fetch_val(
            "SELECT country FROM users WHERE id = %s LIMIT 1",
            (UserID,),
        )
        if country and country != "XX":  # check if the country is not set
            await state.redis.zrem(f"ripple:leaderboard:{mode}:{country}", UserID)
            if config.srv_supports_relax:
                await state.redis.zrem(
                    f"ripple:leaderboard_relax:{mode}:{country}", UserID
                )
            if config.srv_supports_autopilot:
                await state.redis.zrem(
                    f"ripple:leaderboard_ap:{mode}:{country}", UserID
                )


async def UpdateBanStatus(UserID: int) -> None:
    """Updates the ban statuses in bancho."""
    await state.redis.publish("peppy:ban", str(UserID))


async def SetBMAPSetStatus(BeatmapSet: int, Status: int, session: Session):
    """Sets status for all beatmaps in beatmapset."""
    has_admin = await has_privilege_value(
        session.user_id, Privileges.ADMIN_MANAGE_BEATMAPS
    )

    modes = await state.database.fetch_all(
        "SELECT DISTINCT mode FROM beatmaps WHERE beatmapset_id = %s",
        (BeatmapSet,),
    )

    mode_privs = {
        0: Privileges.ADMIN_MANAGE_STD_BEATMAPS,
        1: Privileges.ADMIN_MANAGE_TAIKO_BEATMAPS,
        2: Privileges.ADMIN_MANAGE_CATCH_BEATMAPS,
        3: Privileges.ADMIN_MANAGE_MANIA_BEATMAPS,
    }

    mode_filter = ""
    if not has_admin:
        rankable_modes = []
        for mode_row in modes:
            mode = mode_row[0]
            mode_priv = mode_privs[mode]
            if await has_privilege_value(session.user_id, mode_priv):
                rankable_modes.append(mode)

        if not rankable_modes:
            raise InsufficientPrivilegesError(
                "Insufficient privileges to rank this beatmapset."
            )

        mode_filter = "AND mode IN (" + ",".join(map(str, rankable_modes)) + ")"

    await state.database.execute(
        f"UPDATE beatmaps SET ranked = %s, ranked_status_freezed = 1 WHERE beatmapset_id = %s{mode_filter}",
        (
            Status,
            BeatmapSet,
        ),
    )

    # getting status text
    title_text = "unranked..."
    if Status == 2:
        title_text = "ranked!"
    elif Status == 5:
        title_text = "loved!"

    maps_data = await state.database.fetch_all(
        "SELECT song_name, beatmap_id, beatmap_md5 FROM beatmaps WHERE beatmapset_id = %s",
        (BeatmapSet,),
    )

    # Getting bmap name without diff
    # "might work" this guy...
    beatmap_name = maps_data[0][0].split("[")[0].rstrip()  # ¯\_(ツ)_/¯ might work

    embed = {
        "description": f"Ranked by {session.username}",
        "color": 242424,
        "author": {
            "name": f"{beatmap_name} was just {title_text}",
            "url": f"https://ussr.pl/b/{maps_data[0][1]}",
            "icon_url": f"https://a.ussr.pl/{session.user_id}",
        },
        "footer": {"text": "via RealistikPanel!"},
        "image": {
            "url": f"https://assets.ppy.sh/beatmaps/{BeatmapSet}/covers/cover.jpg"
        },
    }

    logger.info("Posting webhook...")
    await send_discord_webhook(config.webhook_ranked, {"embeds": [embed]})

    # Refresh all lbs.
    for _, _, md5 in maps_data:
        await refresh_bmap(md5)


async def FindUserByUsername(User: str, Page: int) -> list[dict[str, Any]]:
    """Finds user by their username OR email."""
    # calculating page offsets
    Offset = 50 * (Page - 1)
    # checking if its an email
    Split = User.split("@")
    if (
        len(Split) == 2
        and "."
        # if its an email, 2nd check makes sure its an email and not someone trying to be A E S T H E T I C
        in Split[1]
    ):
        users = await state.database.fetch_all(
            "SELECT id, username, privileges, allowed FROM users WHERE email LIKE %s LIMIT 50 OFFSET %s",
            (
                User,
                Offset,
            ),  # i will keep the like statement unless it causes issues
        )
    else:  # its a username
        User = f"%{User}%"  # for sql to treat is as substring
        users = await state.database.fetch_all(
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

    # gets all priv info
    for Priv in UniquePrivileges:
        priv_info = await state.database.fetch_one(
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
        country = await state.database.fetch_val(
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


async def ChangePassword(AccountID: int, NewPassword: str) -> None:
    """Changes the password of a user with given AccID"""
    BCrypted = CreateBcrypt(NewPassword)
    await state.database.execute(
        "UPDATE users SET password_md5 = %s WHERE id = %s",
        (
            BCrypted,
            AccountID,
        ),
    )
    await state.redis.publish("peppy:change_pass", json.dumps({"user_id": AccountID}))


async def ChangePWForm(
    form: dict[str, str],
    session: Session,
) -> None:  # this function may be unnecessary but ehh
    """Handles the change password POST request."""
    await ChangePassword(int(form["accid"]), form["newpass"])
    User = await GetUser(int(form["accid"]))
    await RAPLog(
        session.user_id,
        f"has changed the password of {User['Username']} ({form['accid']})",
    )


async def GiveSupporterForm(form: dict[str, str]) -> None:
    """Handles the give supporter form/POST request."""
    await GiveSupporter(int(form["accid"]), int(form["time"]))


def convert_mode_to_str(mode: int) -> str:
    return {
        0: "osu!std",
        1: "osu!taiko",
        2: "osu!catch",
        3: "osu!mania",
    }.get(mode, "osu!std")


async def GetRankRequests(
    Page: int, allowed_modes: list[int] | None = None
) -> list[dict[str, Any]]:
    """Gets all the rank requests. This may require some optimisation."""
    Page -= 1
    Offset = 50 * Page  # for the page system to work

    if allowed_modes is not None:
        modes_sql = ",".join(map(str, allowed_modes))
        requests = await state.database.fetch_all(
            f"""
            SELECT rr.id, rr.userid, rr.bid, rr.type, rr.time, rr.blacklisted
            FROM rank_requests rr
            LEFT JOIN beatmaps b ON (
                (rr.type = 's' AND rr.bid = b.beatmapset_id)
                OR (rr.type = 'b' AND rr.bid = b.beatmap_id)
            )
            WHERE rr.blacklisted = 0
            AND b.mode IN ({modes_sql})
            GROUP BY rr.id
            ORDER BY rr.id DESC
            LIMIT 50 OFFSET %s
            """,
            (Offset,),
        )
    else:
        requests = await state.database.fetch_all(
            "SELECT id, userid, bid, type, time, blacklisted FROM rank_requests WHERE blacklisted = 0 ORDER BY id DESC LIMIT 50 OFFSET %s",
            (Offset,),
        )

    # turning what we have so far into
    TheRequests = []
    UserIDs = []  # used for later fetching the users, so we dont have a repeat of 50 queries
    for request in requests:
        # getting song info, like 50 individual queries at peak lmao
        TriedSet = False
        TriedBeatmap = False
        if request[3] == "s":
            request_data = await state.database.fetch_one(
                "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmapset_id = %s LIMIT 1",
                (request[2],),
            )
            TriedSet = True
        else:
            request_data = await state.database.fetch_one(
                "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmap_id = %s LIMIT 1",
                (request[2],),
            )
            TriedBeatmap = True

        # in case it was added incorrectly for some reason?
        if not request_data and TriedBeatmap:
            request_data = await state.database.fetch_one(
                "SELECT song_name, beatmapset_id FROM beatmaps WHERE beatmapset_id = %s LIMIT 1",
                (request[2],),
            )
        elif not request_data and TriedSet:
            request_data = await state.database.fetch_one(
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
            SongName = SongName.split("[")[
                0
            ].rstrip()  # kind of a way to get rid of diff name

            BeatmapSetID = request_data[1]
            Cover = f"https://assets.ppy.sh/beatmaps/{BeatmapSetID}/covers/cover.jpg"

        modes = await state.database.fetch_all(
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
        username = await state.database.fetch_val(
            "SELECT username FROM users WHERE id = %s",
            (AccoundIdentity,),
        )

        if not username:
            Usernames[str(AccoundIdentity)] = {
                "Username": f"Unknown! ({AccoundIdentity})",
            }
        else:
            Usernames[str(AccoundIdentity)] = {"Username": username}

    # things arent going to be very performant lmao
    for i in range(0, len(TheRequests)):
        TheRequests[i]["RequestUsername"] = Usernames[str(TheRequests[i]["RequestBy"])][
            "Username"
        ]

    # flip so it shows newest first yes
    TheRequests.reverse()
    return TheRequests


async def DeleteBmapReq(Req: int) -> None:
    """Deletes the beatmap request."""
    await state.database.execute(
        "DELETE FROM rank_requests WHERE id = %s LIMIT 1", (Req,)
    )


async def SearchUserPageCount(search_term: str) -> int:
    """Gets the amount of pages for users matching search term."""
    Split = search_term.split("@")
    if len(Split) == 2 and "." in Split[1]:
        count = await state.database.fetch_val(
            "SELECT count(*) FROM users WHERE email LIKE %s",
            (search_term,),
        )
    else:
        count = await state.database.fetch_val(
            "SELECT count(*) FROM users WHERE username LIKE %s",
            (f"%{search_term}%",),
        )
    return math.ceil(count / PAGE_SIZE)


async def UserPageCount() -> int:
    """Gets the amount of pages for users."""
    count = await state.database.fetch_val("SELECT count(*) FROM users")
    return math.ceil(count / PAGE_SIZE)


async def traceback_pages() -> int:
    """Gets the number of pages for the traceback page."""
    count = await state.sqlite.fetch_val(
        "SELECT COUNT(*) FROM tracebacks",
    )

    return math.ceil(count / PAGE_SIZE)


async def RapLogCount() -> int:
    """Gets the amount of pages for rap logs."""
    count = await state.database.fetch_val("SELECT count(*) FROM rap_logs")
    return math.ceil(count / PAGE_SIZE)


async def SearchClans(search_term: str, Page: int = 1) -> list[dict[str, Any]]:
    """Searches for clans by name or tag."""
    # offsets and limits
    Page = int(Page) - 1
    Offset = 50 * Page

    clans_data = await state.database.fetch_all(
        "SELECT id, name, description, icon, tag FROM clans WHERE name LIKE %s OR tag LIKE %s LIMIT 50 OFFSET %s",
        (f"%{search_term}%", f"%{search_term}%", Offset),
    )

    Clans = []
    for Clan in clans_data:
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


async def SearchClanPages(search_term: str) -> int:
    """Gets amount of pages for searched clans."""
    count = await state.database.fetch_val(
        "SELECT count(*) FROM clans WHERE name LIKE %s OR tag LIKE %s",
        (f"%{search_term}%", f"%{search_term}%"),
    )
    return math.ceil(count / PAGE_SIZE)


async def GetClans(Page: int = 1) -> list[dict[str, Any]]:
    """Gets a list of all clans (v1)."""
    # offsets and limits
    Page = int(Page) - 1
    Offset = 50 * Page
    # the sql part
    clans_data = await state.database.fetch_all(
        "SELECT id, name, description, icon, tag FROM clans LIMIT 50 OFFSET %s",
        (Offset,),
    )
    # making cool, easy to work with dicts and arrays!
    Clans = []
    for Clan in clans_data:
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


async def GetSearchClanPages(search_term: str) -> int:
    """Gets amount of pages for searched clans."""
    count = await state.database.fetch_val(
        "SELECT count(*) FROM clans WHERE name LIKE %s OR tag LIKE %s",
        (f"%{search_term}%", f"%{search_term}%"),
    )
    return math.ceil(count / PAGE_SIZE)


async def GetClanPages() -> int:
    """Gets amount of pages for clans."""
    count = await state.database.fetch_val("SELECT count(*) FROM clans")
    return math.ceil(count / PAGE_SIZE)


async def GetClanMembers(ClanID: int) -> list[dict[str, Any]]:
    """Returns a list of clan members."""
    # ok so we assume the list isnt going to be too long
    clan_members = await state.database.fetch_all(
        "SELECT user FROM user_clans WHERE clan = %s",
        (ClanID,),
    )
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
    members_data = await state.database.fetch_all(
        f"SELECT username, id, register_datetime FROM users WHERE {Conditions}",
        tuple(args),  # here i use format as the conditions are a trusted input
    )

    # turning the data into a dictionary list
    ReturnList = []
    for User in members_data:
        ReturnList.append(
            {
                "AccountID": User[1],
                "Username": User[0],
                "RegisterTimestamp": User[2],
                "RegisterAgo": TimeToTimeAgo(User[2]),
            },
        )

    return ReturnList


async def GetClan(ClanID: int) -> dict[str, Any]:
    """Gets information for a specified clan."""
    clan_data = await state.database.fetch_one(
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
    member_count = await state.database.fetch_val(
        "SELECT COUNT(*) FROM user_clans WHERE clan = %s",
        (ClanID,),
    )
    return {
        "ID": clan_data[0],
        "Name": clan_data[1],
        "Description": clan_data[2],
        "Icon": clan_data[3],
        "Tag": clan_data[4],
        "MemberLimit": clan_data[5],
        "MemberCount": member_count,
    }


async def GetClanOwner(ClanID: int) -> dict[str, Any]:
    """Gets user info for the owner of a clan."""
    # wouldve been done quicker but i decided to play jawbreaker and only got up to 81%
    owner_id = await state.database.fetch_val(
        "SELECT user FROM user_clans WHERE clan = %s and perms = 8",
        (ClanID,),
    )
    if not owner_id:
        return {
            "AccountID": 0,
            "Username": "Unknown",
        }

    # getting account info
    username = await state.database.fetch_val(
        "SELECT username FROM users WHERE id = %s",
        (owner_id,),
    )  # will add more info maybe
    if not username:
        return {
            "AccountID": owner_id,
            "Username": "Unknown",
        }

    return {"AccountID": owner_id, "Username": username}


async def ApplyClanEdit(Form: dict[str, str], session: Session) -> None:
    """Uses the post request to set new clan settings."""
    ClanID = Form["id"]
    ClanName = Form["name"]
    ClanDesc = Form["desc"]
    ClanTag = Form["tag"]
    ClanIcon = Form["icon"]
    MemberLimit = Form["limit"]
    await state.database.execute(
        "UPDATE clans SET name = %s, description = %s, tag = %s, mlimit = %s, icon = %s WHERE id = %s LIMIT 1",
        (ClanName, ClanDesc, ClanTag, MemberLimit, ClanIcon, ClanID),
    )

    # Make all tags refresh.
    members = await state.database.fetch_all(
        "SELECT user FROM user_clans WHERE clan = %s",
        (ClanID,),
    )

    for user_id in members:
        await cache_clan(user_id[0])

    await RAPLog(session.user_id, f"edited the clan {ClanName} ({ClanID})")


async def NukeClan(ClanID: int, session: Session) -> None:
    """Deletes a clan from the face of the earth."""
    Clan = await GetClan(ClanID)
    if not Clan:
        return

    # Make all tags refresh.
    members = await state.database.fetch_all(
        "SELECT user FROM user_clans WHERE clan = %s",
        (ClanID,),
    )

    await state.database.execute("DELETE FROM clans WHERE id = %s LIMIT 1", (ClanID,))
    await state.database.execute("DELETE FROM user_clans WHERE clan = %s", (ClanID,))
    # run this after

    for user_id in members:
        await cache_clan(user_id[0])

    await RAPLog(session.user_id, f"deleted the clan {Clan['Name']} ({ClanID})")


async def KickFromClan(AccountID: int) -> None:
    """Kicks user from all clans (supposed to be only one)."""
    await state.database.execute("DELETE FROM user_clans WHERE user = %s", (AccountID,))
    await cache_clan(AccountID)


async def GetUsersRegisteredBetween(Offset: int = 0, Ahead: int = 24) -> int:
    """Gets how many players registered during a given time period (variables are in hours)."""
    # convert the hours to secconds
    Offset *= 3600
    Ahead *= 3600

    CurrentTime = round(time.time())
    # now we get the time - offset
    OffsetTime = CurrentTime - Offset
    AheadTime = OffsetTime - Ahead

    count = await state.database.fetch_val(
        "SELECT COUNT(*) FROM users WHERE register_datetime > %s AND register_datetime < %s",
        (AheadTime, OffsetTime),
    )
    return count


async def GetUsersActiveBetween(Offset: int = 0, Ahead: int = 24) -> int:
    """Gets how many players were active during a given time period (variables are in hours)."""
    # yeah this is a reuse of the last function.
    # convert the hours to secconds
    Offset *= 3600
    Ahead *= 3600

    CurrentTime = round(time.time())
    # now we get the time - offset
    OffsetTime = CurrentTime - Offset
    AheadTime = OffsetTime - Ahead

    count = await state.database.fetch_val(
        "SELECT COUNT(*) FROM users WHERE latest_activity > %s AND latest_activity < %s",
        (AheadTime, OffsetTime),
    )
    return count


def RippleSafeUsername(Username: str) -> str:
    """Generates a ripple-style safe username."""
    return Username.lower().replace(" ", "_").strip()


async def GetSuggestedRank() -> list[dict[str, Any]]:
    """Gets suggested maps to rank (based on play count)."""
    beatmaps_data = await state.database.fetch_all(
        "SELECT beatmap_id, song_name, beatmapset_id, playcount FROM beatmaps WHERE ranked = 0 ORDER BY playcount DESC LIMIT 8",
    )
    BeatmapList = []
    for TopBeatmap in beatmaps_data:
        full_name = TopBeatmap[1]
        song_name = full_name
        diff_name = "Standard"

        match = re.match(r"(.+)\s\[(.+)\]$", full_name)
        if match:
            song_name = match.group(1)
            diff_name = match.group(2)

        modes = await state.database.fetch_all(
            "SELECT mode FROM beatmaps WHERE beatmapset_id = %s",
            (TopBeatmap[2],),
        )
        unique_modes = Unique([mode[0] for mode in modes])
        string_modes = ", ".join([convert_mode_to_str(mode) for mode in unique_modes])
        BeatmapList.append(
            {
                "BeatmapId": TopBeatmap[0],
                "SongName": song_name,
                "DiffName": diff_name,
                "Cover": f"https://assets.ppy.sh/beatmaps/{TopBeatmap[2]}/covers/cover.jpg",
                "Playcount": TopBeatmap[3],
                "Modes": string_modes,
            },
        )

    return BeatmapList


async def CountRestricted() -> int:
    """Calculates the amount of restricted or banned users."""
    count = await state.database.fetch_val(
        "SELECT COUNT(*) FROM users WHERE privileges = 2"
    )
    return count


async def GetStatistics(MinPP: int = 0) -> dict[str, Any]:
    """Gets statistics for the stats page and is incredibly slow...."""
    # this is going to be a wild one
    # TODO: REWRITE or look into caching this
    MinPP = int(MinPP)
    Days = 7
    RegisterList = []
    DateList = []
    while Days != -1:
        DateList.append(f"{Days + 1}d")
        RegisterList.append(await GetUsersRegisteredBetween(24 * Days))
        Days -= 1
    UsersActiveToday = await GetUsersActiveBetween()
    RecentPlay = await get_recent_plays(500, MinPP)
    ResctictedCount = await CountRestricted()

    return {
        "RegisterGraph": {"RegisterList": RegisterList, "DateList": DateList},
        "ActiveToday": UsersActiveToday,
        "RecentPlays": RecentPlay,
        "DisallowedCount": ResctictedCount,
    }


async def CreatePrivilege() -> int:
    """Creates a new default privilege."""
    privilege_id = await state.database.execute(
        "INSERT INTO privileges_groups (name, privileges, color) VALUES ('New Privilege', 0, '')",
    )
    return privilege_id


def CoolerInt(ToInt: Any) -> int:
    """Makes a number an int butt also works with special cases etc if ToInt is None, it returns a 0! Magic."""
    if not ToInt:
        return 0
    return int(ToInt)


async def calc_first_place(beatmap_md5: str, rx: int = 0, mode: int = 0) -> None:
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
    first_place_data = await state.database.fetch_one(
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
    await state.database.execute(
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
async def cache_clan(user_id: int) -> None:
    """Updates LETS' cached clan tag for a specific user. This is a
    requirement for RealistikOsu lets, or else clan tags may get out of sync.
    """

    await state.redis.publish("rosu:clan_update", str(user_id))


async def refresh_bmap(md5: str) -> None:
    """Tells USSR to update the beatmap cache for a specific beatmap."""

    await state.redis.publish("ussr:refresh_bmap", md5)


async def refresh_username_cache(user_id: int, new_username: str) -> None:
    """Refreshes the username cache for a specific user."""

    # Handle pep.py tokens.
    await state.redis.publish(
        "peppy:disconnect",
        json.dumps(
            {
                "userID": user_id,
                "reason": "Your username has been changed. Please re-log.",
            },
        ),
    )

    # Handle USSR cache.
    await state.redis.publish(
        "peppy:change_username",
        json.dumps(
            {
                "userID": user_id,
                "newUsername": new_username,
            },
        ),
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


async def fetch_banlogs(page: int = 0) -> list[BanLog]:
    """Fetches a page of ban logs."""

    ban_logs = await state.database.fetch_all(
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


async def ban_count() -> int:
    """Returns the total number of bans."""

    count = await state.database.fetch_val("SELECT COUNT(*) FROM ban_logs")
    return count


async def ban_pages() -> int:
    """Returns the number of pages in the ban log."""

    return math.ceil(await ban_count() / PAGE_SIZE)


async def request_count(allowed_modes: list[int] | None = None) -> int:
    """Returns the total number of requests."""

    if allowed_modes is not None:
        modes_sql = ",".join(map(str, allowed_modes))
        count = await state.database.fetch_val(
            f"""
            SELECT COUNT(DISTINCT rr.id)
            FROM rank_requests rr
            INNER JOIN beatmaps b ON (
                (rr.type = 's' AND rr.bid = b.beatmapset_id)
                OR (rr.type = 'b' AND rr.bid = b.beatmap_id)
            )
            WHERE rr.blacklisted = 0 AND b.mode IN ({modes_sql})
            """
        )
    else:
        count = await state.database.fetch_val(
            "SELECT COUNT(*) FROM rank_requests WHERE blacklisted = 0",
        )
    return count


async def request_pages(allowed_modes: list[int] | None = None) -> int:
    """Returns the number of pages in the request."""

    return math.ceil(await request_count(allowed_modes) / PAGE_SIZE)


async def fetch_user_banlogs(user_id: int) -> list[BanLog]:
    """Fetches all ban logs targetting a specific user.

    Args:
        user_id (int): The target userID.

    Returns:
        list[BanLog]: A list of all banlogs for the user.
    """
    ban_logs = await state.database.fetch_all(
        BAN_LOG_BASE + "WHERE to_id = %s ORDER BY b.id DESC",
        (user_id,),
    )

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


async def get_clan_invites(clan_id: int) -> list[ClanInvite]:
    invites = await state.database.fetch_all(
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


async def create_clan_invite(clan_id: int) -> ClanInvite:
    invite_code = random_str(8)
    invite_id = await state.database.execute(
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


async def get_hwid_history(user_id: int) -> list[HWIDLog]:
    hwid_history = await state.database.fetch_all(
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


async def get_hwid_history_paginated(user_id: int, page: int = 0) -> list[HWIDLog]:
    occurences = await state.database.fetch_all(
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


async def get_hwid_matches_exact(log: HWIDLog) -> list[HWIDLog]:
    """Gets a list of exactly matching HWID logs for all users other than the
    origin of the initial log.

    Args:
        log (HWIDLog): The initial log to search for.

    Returns:
        list[HWIDLog]: A list of logs from other users that exactly match
            `log`.
    """

    occurences = await state.database.fetch_all(
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


async def get_hwid_matches_partial(log: HWIDLog) -> list[HWIDLog]:
    """Gets a list of partially matching HWID logs (just one item has to match)
    for all users other than the origin of the initial log.

    Args:
        log (HWIDLog): The initial log to search for.

    Returns:
        list[HWIDLog]: A list of logs sharing at least one hash with `log`.
    """

    occurences = await state.database.fetch_all(
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


async def get_hwid_count(user_id: int) -> int:
    count = await state.database.fetch_val(
        "SELECT COUNT(*) FROM hw_user WHERE userid = %s",
        (user_id,),
    )
    return count


async def hwid_pages(user_id: int) -> int:
    """Returns the number of pages in the ban log."""

    return math.ceil(await get_hwid_count(user_id) / PAGE_SIZE)


class HWIDResult(TypedDict):
    result: HWIDLog
    exact_matches: list[HWIDLog]
    partial_matches: list[HWIDLog]


class HWIDPage(TypedDict):
    user: SimpleUserData
    results: list[HWIDResult]


async def get_hwid_page(user_id: int, page: int = 0) -> HWIDPage:
    hw_history = await get_hwid_history_paginated(user_id, page)

    results = list[HWIDResult]()

    for log in hw_history:
        exact_matches = await get_hwid_matches_exact(log)
        partial_matches = list(
            filter(
                lambda x: x not in exact_matches, await get_hwid_matches_partial(log)
            ),
        )
        results.append(
            {
                "result": log,
                "exact_matches": exact_matches,
                "partial_matches": partial_matches,
            },
        )

    return {
        "user": await GetUser(user_id),
        "results": results,
    }


# Username history.
async def is_username_taken(username: str, ignore_user_id: int = 0) -> Optional[int]:
    """Check if a username is taken by an existing user or previously belonged to them.
    Returns `None` if not, else the user id."""

    registered_exists = await state.database.fetch_val(
        "SELECT id FROM users WHERE username LIKE %s LIMIT 1",
        (username,),
    )

    if registered_exists:
        return registered_exists

    history_exists = await state.database.fetch_val(
        "SELECT user_id FROM user_name_history WHERE username LIKE %s "
        "AND user_id != %s LIMIT 1",
        (username, ignore_user_id),
    )

    if history_exists:
        return history_exists

    return None


_USERNAME_TABLES = (
    "users_stats",
    "rx_stats",
    "ap_stats",
)


async def change_username(
    user_id: int,
    new_username: str,
    bypass_name_history: bool = False,
) -> bool:
    """Internal function to handle the renaming of the individual.

    Returns false if the username is already occupied or we are
    attempting to rename an unknown user."""

    if await is_username_taken(new_username, user_id):
        return False

    old_data = await GetUser(user_id)

    if old_data["Id"] == 0:
        return False

    # Store the old username
    if not bypass_name_history:
        await state.database.execute(
            "INSERT INTO user_name_history VALUES (NULL, %s, %s, UNIX_TIMESTAMP())",
            (
                user_id,
                old_data["Username"],
            ),
        )

    # Update existing table entries (including data repetition...)
    await state.database.execute(
        "UPDATE users SET username = %s, username_safe = %s WHERE id = %s",
        (
            new_username,
            RippleSafeUsername(new_username),
            user_id,
        ),
    )

    for username_table in _USERNAME_TABLES:
        await state.database.execute(
            f"UPDATE {username_table} SET username = %s WHERE id = %s",
            (
                new_username,
                user_id,
            ),
        )

    # If this username was previously in our name history, delete it.
    await state.database.execute(
        "DELETE FROM user_name_history WHERE username LIKE %s AND user_id = %s",
        (new_username, user_id),
    )

    # Re-log the user if they are online (can cause some weird behaviour in-game otherwise).
    await refresh_username_cache(user_id, new_username)

    return True


async def get_username_history(user_id: int) -> list[str]:
    username_history = await state.database.fetch_all(
        # XXX: Distinct should be fast enough on a small dataset like this.
        "SELECT DISTINCT(username) FROM user_name_history WHERE user_id = %s",
        (user_id,),
    )

    return [entry[0] for entry in username_history]


async def apply_username_change(
    user_id: int,
    new_username: str,
    changed_by_id: int,
    no_name_history: bool,
) -> Optional[str]:
    # Minor cleanups (we sorta trust staff to be kinda sane with the charset)
    new_username = new_username.strip()

    old_user = await GetUser(user_id)

    if new_username == old_user["Username"]:
        return "The new username may not be the same as the old."

    if taken_id := await is_username_taken(new_username, user_id):
        taken_user = await GetUser(taken_id)
        return f"This username is already occupied by {taken_user['Username']} ({taken_id})"

    if not await change_username(user_id, new_username, no_name_history):
        return "Failed to change the username. Perhaps the user doesn't exist anymore?"

    await RAPLog(
        changed_by_id,
        f"renamed {old_user['Username']} ({user_id}) to {new_username!r}",
    )
    return


async def add_to_whitelist(user_id: int) -> None:
    await state.database.execute("INSERT INTO whitelist VALUES (%s)", (user_id,))


async def remove_from_whitelist(user_id: int) -> None:
    await state.database.execute("DELETE FROM whitelist WHERE user_id = %s", (user_id,))


async def is_whitelisted(user_id: int) -> bool:
    return (
        await state.database.fetch_val(
            "SELECT user_id FROM whitelist WHERE user_id = %s",
            (user_id,),
        )
        is not None
    )


async def apply_whitelist_change(user_id: int, changed_by_id: int) -> None:
    await GetUser(user_id)

    if await is_whitelisted(user_id):
        await remove_from_whitelist(user_id)
        await RAPLog(changed_by_id, f"removed {user_id} from the whitelist")
    else:
        await add_to_whitelist(user_id)
        await RAPLog(changed_by_id, f"added {user_id} to the whitelist")


async def ResetAvatar(user_id: int) -> bool:
    """Resets the avatar of a user."""
    if not config.avatars_path:
        return False

    deleted = False

    # Iterate over files in the directory
    try:
        if not os.path.exists(config.avatars_path):
            return False

        for filename in os.listdir(config.avatars_path):
            # Check if filename starts with user_id and matches expected pattern
            # We want exact match on the name part (without extension)
            name, ext = os.path.splitext(filename)
            if name == str(user_id):
                file_path = os.path.join(config.avatars_path, filename)
                os.remove(file_path)
                deleted = True
    except Exception:
        return False

    return deleted
