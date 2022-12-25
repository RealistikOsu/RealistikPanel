# This file is responsible for running the web server and (mostly nothing else)
from __future__ import annotations

import os
import traceback
from threading import Thread

from flask import Flask
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import send_from_directory
from flask import session
from flask import url_for

import logger
from common.responses import load_panel_template
from config import config
from defaults import *
from functions import *
from updater import handle_update

app = Flask(__name__)
app.secret_key = os.urandom(24)  # encrypts the session cookie


@app.route("/")
def panel_home_redirect():
    if session["LoggedIn"]:
        return redirect(url_for("panel_dashboard"))
    else:
        return redirect(url_for("panel_login"))


@app.route("/dash/")
def panel_dashboard():
    if not has_privilege_value(session["AccountId"], Privileges.ADMIN_ACCESS_RAP):
        return no_permission_response(request.path)

    return load_panel_template(
        title="Dashboard",
        file="dash.html",
        plays=get_recent_plays(),
        Graph=get_playcount_graph_data(),
        MostPlayed=GetMostPlayed(),
    )


IP_REDIRS = {}

# TODO: MOVE
def _set_session(new_session: dict) -> None:
    session.clear()

    for key, value in new_session.items():
        session[key] = value


# TODO: rework
@app.route("/login", methods=["GET", "POST"])
def panel_login():
    if not session["LoggedIn"] and not HasPrivilege(session["AccountId"]):
        if request.method == "GET":
            redir = request.args.get("redirect")
            if redir:
                IP_REDIRS[request.headers.get("X-Real-IP")] = redir

            return render_template("login.html", conf=config)

        if request.method == "POST":
            success, data = LoginHandler(
                request.form["username"],
                request.form["password"],
            )
            if not success:
                return render_template(
                    "login.html",
                    alert=data,
                    conf=config,
                )
            else:
                _set_session(data)

                redir = IP_REDIRS.get(request.headers.get("X-Real-IP"))
                if redir:
                    del IP_REDIRS[request.headers.get("X-Real-IP")]
                    return redirect(redir)

                return redirect(url_for("panel_home_redirect"))
    else:
        return redirect(url_for("panel_dashboard"))


@app.route("/logout")
def panel_session_logout():
    _set_session(ServSession)
    return redirect(url_for("panel_home_redirect"))


@app.route("/bancho/settings", methods=["GET", "POST"])
def panel_bancho_settings():
    if not has_privilege_value(session["AccountId"], Privileges.ADMIN_MANAGE_SERVERS):
        return no_permission_response(request.path)

    error = success = None
    if request.method == "POST":
        try:
            handle_bancho_settings_edit(
                request.form["banchoman"],
                request.form["mainmemuicon"],
                request.form["loginnotif"],
                int(session["AccountId"]),
            )
            success = "Bancho settings were successfully edited!"
        except Exception as e:
            error = f"Failed to save Bancho settings with error {e}!"

    return load_panel_template(
        "banchosettings.html",
        title="Bancho Settings",
        bsdata=FetchBSData(),
        preset=FetchBSData(),
        error=error,
        success=success,
    )


@app.route("/rank/<beatmap_id>", methods=["GET", "POST"])
def panel_rank_beatmap(beatmap_id: str):
    if not has_privilege_value(session["AccountId"], Privileges.ADMIN_MANAGE_BEATMAPS):
        return no_permission_response(request.path)

    error = success = None

    if request.method == "POST":
        try:
            beatmap_index = request.form["beatmapnumber"]
            RankBeatmap(
                beatmap_index,
                request.form[f"bmapid-{beatmap_index}"],
                request.form[f"rankstatus-{beatmap_index}"],
                session,
            )
            success = f"Successfully ranked a beatmap with the ID of {beatmap_id}"
        except Exception as e:
            logger.error(traceback.format_exc())
            error = f"Failed to rank beatmap {beatmap_id} with error {e}!"

    return load_panel_template(
        "beatrank.html",
        title="Rank Beatmap!",
        Id=beatmap_id,
        beatdata=halve_list(GetBmapInfo(beatmap_id)),
        success=success,
        error=error,
    )


@app.route("/rank", methods=["GET", "POST"])
def panel_rank_beatmap_search():
    # We can skip the privilege check here since the endpoint we are redirecting to handles it.
    if request.method == "POST":
        return redirect(f"/rank/{request.form['bmapid']}")

    if not has_privilege_value(session["AccountId"], Privileges.ADMIN_MANAGE_BEATMAPS):
        return no_permission_response(request.path)

    return load_panel_template(
        "rankform.html",
        title="Rank a beatmap!",
        SuggestedBmaps=halve_list(GetSuggestedRank()),
    )


@app.route("/users/<page_str>", methods=["GET", "POST"])
def panel_search_users(page_str: str = "1"):
    if not has_privilege_value(session["AccountId"], Privileges.ADMIN_MANAGE_USERS):
        return no_permission_response(request.path)

    page = int(page_str)

    if request.method == "POST":
        user_data = FindUserByUsername(
            request.form["user"],
            page,
        )
    else:
        user_data = FetchUsers(page - 1)

    return load_panel_template(
        "users.html",
        title="Search Users",
        UserData=user_data,
        page=page,
        Pages=UserPageCount(),
    )


@app.route("/index.php")
def panel_legacy_index():
    """Implements support for Ripple Admin Panel's legacy redirects"""

    page = int(request.args["p"])

    if page == 124:
        set_id = request.args["bsid"]
        return redirect(f"/rank/{set_id}")
    elif page == 103:
        user_id = request.args["id"]
        return redirect(f"/user/edit/{user_id}")

    # Unsupported/default redirect
    return redirect(url_for("panel_dashboard"))


@app.route("/system/settings", methods=["GET", "POST"])
def panel_system_settings():
    if HasPrivilege(session["AccountId"], 4):
        if request.method == "GET":
            return render_template(
                "syssettings.html",
                data=load_dashboard_data(),
                session=session,
                title="System Settings",
                SysData=SystemSettingsValues(),
                config=config,
            )
        if request.method == "POST":
            try:
                ApplySystemSettings(
                    [
                        request.form["webman"],
                        request.form["gameman"],
                        request.form["register"],
                        request.form["globalalert"],
                        request.form["homealert"],
                    ],
                    session,
                )  # why didnt i just pass request
                return render_template(
                    "syssettings.html",
                    data=load_dashboard_data(),
                    session=session,
                    title="System Settings",
                    SysData=SystemSettingsValues(),
                    config=config,
                    success="System settings successfully edited!",
                )
            except Exception as e:
                logger.error(traceback.format_exc())
                return render_template(
                    "syssettings.html",
                    data=load_dashboard_data(),
                    session=session,
                    title="System Settings",
                    SysData=SystemSettingsValues(),
                    config=config,
                    error="An internal error has occured while saving system settings! An error has been logged to the console.",
                )
        else:
            return no_permission_response(request.path)


@app.route("/user/edit/<id>", methods=["GET", "POST"])
def panel_edit_user(id):
    if request.method == "GET":
        if HasPrivilege(session["AccountId"], 6):
            return render_template(
                "edituser.html",
                data=load_dashboard_data(),
                session=session,
                title="Edit User",
                config=config,
                UserData=UserData(id),
                Privs=GetPrivileges(),
                UserBadges=GetUserBadges(id),
                badges=GetBadges(),
                ShowIPs=HasPrivilege(session["AccountId"], 16),
                ban_logs=fetch_user_banlogs(int(id)),
                hwid_count=get_hwid_count(int(id)),
            )
        else:
            return no_permission_response(request.path)
    if request.method == "POST":
        if HasPrivilege(session["AccountId"], 6):
            try:
                ApplyUserEdit(request.form, session)
                RAPLog(
                    session["AccountId"],
                    f"has edited the user {request.form.get('username', 'NOT FOUND')}",
                )
                return render_template(
                    "edituser.html",
                    data=load_dashboard_data(),
                    session=session,
                    title="Edit User",
                    config=config,
                    UserData=UserData(id),
                    Privs=GetPrivileges(),
                    UserBadges=GetUserBadges(id),
                    badges=GetBadges(),
                    success=f"User {request.form.get('username', 'NOT FOUND')} has been successfully edited!",
                    ShowIPs=HasPrivilege(session["AccountId"], 16),
                    ban_logs=fetch_user_banlogs(int(id)),
                    hwid_count=get_hwid_count(int(id)),
                )
            except Exception as e:
                logger.error(traceback.format_exc())
                return render_template(
                    "edituser.html",
                    data=load_dashboard_data(),
                    session=session,
                    title="Edit User",
                    config=config,
                    UserData=UserData(id),
                    Privs=GetPrivileges(),
                    UserBadges=GetUserBadges(id),
                    badges=GetBadges(),
                    error="An internal error has occured while editing the user! An error has been logged to the console.",
                    ShowIPs=HasPrivilege(session["AccountId"], 16),
                    ban_logs=fetch_user_banlogs(int(id)),
                    hwid_count=get_hwid_count(int(id)),
                )
        else:
            return no_permission_response(request.path)


@app.route("/logs/<page>")
def panel_view_logs(page):
    if HasPrivilege(session["AccountId"], 7):
        return render_template(
            "raplogs.html",
            data=load_dashboard_data(),
            session=session,
            title="Logs",
            config=config,
            Logs=RAPFetch(page),
            page=int(page),
            Pages=RapLogCount(),
        )
    else:
        return no_permission_response(request.path)


@app.route("/action/confirm/delete/<id>")
def panel_delete_user_confirm(id):
    """Confirms deletion of acc so accidents dont happen"""
    # i almost deleted my own acc lmao
    # me forgetting to commit changes saved me
    if HasPrivilege(session["AccountId"], 6):
        AccountToBeDeleted = GetUser(id)
        return render_template(
            "confirm.html",
            data=load_dashboard_data(),
            session=session,
            title="Confirmation Required",
            config=config,
            action=f"delete the user {AccountToBeDeleted['Username']}",
            yeslink=f"/actions/delete/{id}",
            backlink=f"/user/edit/{id}",
        )
    else:
        return no_permission_response(request.path)


@app.route("/user/iplookup/<ip>")
def panel_view_user_ip(ip):
    if HasPrivilege(session["AccountId"], 16):
        IPUserLookup = FindWithIp(ip)
        UserLen = len(IPUserLookup)
        return render_template(
            "iplookup.html",
            data=load_dashboard_data(),
            session=session,
            title="IP Lookup",
            config=config,
            ipusers=IPUserLookup,
            IPLen=UserLen,
            ip=ip,
        )
    else:
        return no_permission_response(request.path)


@app.route("/ban-logs/<page>")
def panel_view_ban_logs(page):
    if HasPrivilege(session["AccountId"], 7):
        return render_template(
            "ban_logs.html",
            data=load_dashboard_data(),
            session=session,
            title="Ban Logs",
            config=config,
            ban_logs=fetch_banlogs(int(page) - 1),
            page=int(page),
            pages=ban_pages(),
        )
    else:
        return no_permission_response(request.path)


@app.route("/badges")
def panel_view_badges():
    if HasPrivilege(session["AccountId"], 4):
        return render_template(
            "badges.html",
            data=load_dashboard_data(),
            session=session,
            title="Badges",
            config=config,
            badges=GetBadges(),
        )
    else:
        return no_permission_response(request.path)


@app.route("/badge/edit/<BadgeID>", methods=["GET", "POST"])
def panel_edit_badge(BadgeID: int):
    if HasPrivilege(session["AccountId"], 4):
        if request.method == "GET":
            return render_template(
                "editbadge.html",
                data=load_dashboard_data(),
                session=session,
                title="Edit Badge",
                config=config,
                badge=GetBadge(BadgeID),
            )
        if request.method == "POST":
            try:
                SaveBadge(request.form)
                RAPLog(
                    session["AccountId"],
                    f"edited the badge with the ID of {BadgeID}",
                )
                return render_template(
                    "editbadge.html",
                    data=load_dashboard_data(),
                    session=session,
                    title="Edit Badge",
                    config=config,
                    badge=GetBadge(BadgeID),
                    success=f"Badge {BadgeID} has been successfully edited!",
                )
            except Exception as e:
                logger.error(traceback.format_exc())
                return render_template(
                    "editbadge.html",
                    data=load_dashboard_data(),
                    session=session,
                    title="Edit Badge",
                    config=config,
                    badge=GetBadge(BadgeID),
                    error="An internal error has occured while editing the badge! An error has been logged to the console.",
                )
    else:
        return no_permission_response(request.path)


@app.route("/privileges")
def panel_view_privileges():
    if HasPrivilege(session["AccountId"], 13):
        return render_template(
            "privileges.html",
            data=load_dashboard_data(),
            session=session,
            title="Privileges",
            config=config,
            privileges=GetPrivileges(),
        )
    else:
        return no_permission_response(request.path)


@app.route("/privilege/edit/<Privilege>", methods=["GET", "POST"])
def panel_edit_privilege(Privilege: int):
    if HasPrivilege(session["AccountId"], 13):
        if request.method == "GET":
            return render_template(
                "editprivilege.html",
                data=load_dashboard_data(),
                session=session,
                title="Privileges",
                config=config,
                privileges=GetPriv(Privilege),
            )
        if request.method == "POST":
            try:
                UpdatePriv(request.form)
                Priv = GetPriv(Privilege)
                RAPLog(
                    session["AccountId"],
                    f"has edited the privilege group {Priv['Name']} ({Priv['Id']})",
                )
                return render_template(
                    "editprivilege.html",
                    data=load_dashboard_data(),
                    session=session,
                    title="Privileges",
                    config=config,
                    privileges=Priv,
                    success=f"Privilege {Priv['Name']} has been successfully edited!",
                )
            except Exception as e:
                logger.error(traceback.format_exc())
                Priv = GetPriv(Privilege)
                return render_template(
                    "editprivilege.html",
                    data=load_dashboard_data(),
                    session=session,
                    title="Privileges",
                    config=config,
                    privileges=Priv,
                    error="An internal error has occured while editing the privileges! An error has been logged to the console.",
                )
    else:
        return no_permission_response(request.path)


@app.route("/changelogs")
def panel_view_changelogs():
    if HasPrivilege(session["AccountId"]):
        return render_template(
            "changelog.html",
            data=load_dashboard_data(),
            session=session,
            title="Change Logs",
            config=config,
            logs=Changelogs,
        )
    else:
        return no_permission_response(request.path)


@app.route("/current.json")
def panel_switcher_endpoints():
    """IPs for the Ripple switcher."""
    return jsonify(
        {
            "osu.ppy.sh": config.srv_switcher_ips,
            "c.ppy.sh": config.srv_switcher_ips,
            "c1.ppy.sh": config.srv_switcher_ips,
            "c2.ppy.sh": config.srv_switcher_ips,
            "c3.ppy.sh": config.srv_switcher_ips,
            "c4.ppy.sh": config.srv_switcher_ips,
            "c5.ppy.sh": config.srv_switcher_ips,
            "c6.ppy.sh": config.srv_switcher_ips,
            "ce.ppy.sh": config.srv_switcher_ips,
            "a.ppy.sh": config.srv_switcher_ips,
            "s.ppy.sh": config.srv_switcher_ips,
            "i.ppy.sh": config.srv_switcher_ips,
            "bm6.ppy.sh": config.srv_switcher_ips,
        },
    )


@app.route("/toggledark")
def panel_toggle_theme():
    if session["Theme"] == "dark":
        session["Theme"] = "white"
    else:
        session["Theme"] = "dark"
    return redirect(url_for("panel_dashboard"))


@app.route(
    "/changepass/<AccountID>",
    methods=["GET", "POST"],
)  # may change the route to something within /user
def panel_edit_user_password(AccountID):
    if HasPrivilege(session["AccountId"], 6):  # may create separate perm for this
        if request.method == "GET":
            User = GetUser(int(AccountID))
            return render_template(
                "changepass.html",
                data=load_dashboard_data(),
                session=session,
                title=f"Change the Password for {User['Username']}",
                config=config,
                User=User,
            )
        if request.method == "POST":
            ChangePWForm(request.form, session)
            User = GetUser(int(AccountID))
            return redirect(f"/user/edit/{AccountID}")
    else:
        return no_permission_response(request.path)


@app.route("/donoraward/<AccountID>", methods=["GET", "POST"])
def panel_award_user_donor(AccountID):
    if HasPrivilege(session["AccountId"], 6):
        if request.method == "GET":
            User = GetUser(int(AccountID))
            return render_template(
                "donoraward.html",
                data=load_dashboard_data(),
                session=session,
                title=f"Award Donor to {User['Username']}",
                config=config,
                User=User,
            )
        if request.method == "POST":
            GiveSupporterForm(request.form)
            User = GetUser(int(AccountID))
            RAPLog(
                session["AccountId"],
                f"has awarded {User['Username']} ({AccountID}) {request.form['time']} days of donor.",
            )
            return redirect(f"/user/edit/{AccountID}")
    else:
        return no_permission_response(request.path)


@app.route("/donorremove/<AccountID>")
def panel_remove_user_donor(AccountID):
    if HasPrivilege(session["AccountId"], 6):
        RemoveSupporter(AccountID, session)
        return redirect(f"/user/edit/{AccountID}")
    else:
        return no_permission_response(request.path)


@app.route("/rankreq/<Page>")
def panel_view_rank_requests(Page):
    if HasPrivilege(session["AccountId"], 3):
        return render_template(
            "rankreq.html",
            data=load_dashboard_data(),
            session=session,
            title="Ranking Requests",
            config=config,
            RankRequests=GetRankRequests(int(Page)),
            page=int(Page),
        )
    else:
        return no_permission_response(request.path)


@app.route("/clans/<Page>")
def panel_view_clans(Page):
    if HasPrivilege(session["AccountId"], 15):
        return render_template(
            "clansview.html",
            data=load_dashboard_data(),
            session=session,
            title="Clans",
            config=config,
            page=int(Page),
            Clans=GetClans(Page),
            Pages=GetClanPages(),
        )
    else:
        return no_permission_response(request.path)


@app.route("/clan/<ClanID>", methods=["GET", "POST"])
def panel_edit_clan(ClanID):
    if HasPrivilege(session["AccountId"], 15):
        if request.method == "GET":
            return render_template(
                "editclan.html",
                data=load_dashboard_data(),
                session=session,
                title="Clans",
                config=config,
                Clan=GetClan(ClanID),
                Members=halve_list(GetClanMembers(ClanID)),
                ClanOwner=GetClanOwner(ClanID),
                clan_invites=get_clan_invites(ClanID),
            )
        ApplyClanEdit(request.form, session)
        return render_template(
            "editclan.html",
            data=load_dashboard_data(),
            session=session,
            title="Clans",
            config=config,
            Clan=GetClan(ClanID),
            Members=halve_list(GetClanMembers(ClanID)),
            ClanOwner=GetClanOwner(ClanID),
            success="Clan edited successfully!",
            clan_invites=get_clan_invites(ClanID),
        )
    else:
        return no_permission_response(request.path)


# TODO: probably should be an action
@app.route("/clan/delete/<ClanID>")
def panel_delete_clan(ClanID):
    if HasPrivilege(session["AccountId"], 15):
        NukeClan(ClanID, session)
        return redirect("/clans/1")
    return no_permission_response(request.path)


@app.route("/clan/confirmdelete/<clan_id_str>")
def panel_delete_clan_confirm(clan_id_str: str):
    if not has_privilege_value(session["AccountId"], Privileges.PANEL_MANAGE_CLANS):
        return no_permission_response(request.path)

    clan_id = int(clan_id_str)
    clan = GetClan(clan_id)

    return load_panel_template(
        "confirm.html",
        title="Confirmation Required",
        action=f" delete the clan {clan['Name']}",
        yeslink=f"/clan/delete/{clan_id}",
        backlink="/clans/1",
    )


@app.route("/stats", methods=["GET", "POST"])
def panel_view_server_stats():
    if not has_privilege_value(session["AccountId"], Privileges.ADMIN_ACCESS_RAP):
        return

    minimum_pp = int(request.form.get("minpp", 0))
    return load_panel_template(
        "stats.html",
        title="Server Statistics",
        StatData=GetStatistics(minimum_pp),
        MinPP=minimum_pp,
    )


@app.route("/user/hwid/<user_id>/<page>")
def view_user_hwid_route(user_id: int, page: int = 1):
    if not has_privilege_value(session["AccountId"], Privileges.ADMIN_MANAGE_USERS):
        return no_permission_response(request.path)

    user_id = int(user_id)
    page = int(page)

    page_info = get_hwid_page(user_id, page - 1)
    username = page_info["user"]["Username"]

    return load_panel_template(
        "userhwids.html",
        title=f"{username}'s Hardware Logs",
        hwid_logs=page_info["results"],
        user=page_info["user"],
        page=page,
        total_hwids=get_hwid_count(user_id),
    )


# API for js
@app.route("/js/pp/<id>")
def panel_pp_api(id):
    try:
        return jsonify(
            {
                "pp": str(round(CalcPP(id), 2)),
                "dtpp": str(round(CalcPPDT(id), 2)),
                "code": 200,
            },
        )
    except:
        return jsonify({"code": 500})


# api mirrors
@app.route("/js/status/api")
def panel_api_status_api():
    try:
        return jsonify(
            requests.get(
                config.srv_url + "api/v1/ping",  # TODO: Make server api url
                timeout=1,
            ).json(),
        )
    except Exception:
        logger.error(f"JavaScript API mirror responded with an error.")
        return jsonify({"code": 503})


@app.route("/js/status/lets")
def panel_lets_status_api():
    try:
        return jsonify(
            requests.get(
                config.api_lets_url + "v1/status",
                timeout=1,
            ).json(),
        )  # this url to provide a predictable result
    except Exception:
        logger.error(f"JavaScript LetsAPI mirror responded with an error.")
        return jsonify({"server_status": 0})


@app.route("/js/status/bancho")
def panel_bancho_status_api():
    try:
        return jsonify(
            requests.get(
                config.api_bancho_url + "api/v1/serverStatus",
                timeout=1,
            ).json(),
        )  # this url to provide a predictable result
    except Exception:
        logger.error(f"JavaScript BanchoAPI mirror responded with an error.")
        return jsonify({"result": 0})


# actions
@app.route("/actions/comment/profile/<AccountID>")
def panel_delete_profile_comments_action(AccountID: int):
    """Wipe all comments made on this user's profile"""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        DeleteProfileComments(AccountID)

        RAPLog(
            session["AccountId"],
            f"has removed all comments made on {Account['Username']}'s profile ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")
    else:

        return no_permission_response(request.path)


@app.route("/actions/comment/user/<AccountID>")
def panel_delete_user_commants_action(AccountID: int):
    """Wipe all comments made by this user"""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        DeleteUserComments(AccountID)

        RAPLog(
            session["AccountId"],
            f"has removed all comments made by {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")
    else:
        return no_permission_response(request.path)


@app.route("/actions/wipe/<AccountID>")
def panel_wipe_user_action(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeAccount(AccountID)
        RAPLog(
            session["AccountId"],
            f"has wiped the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")
    else:
        return no_permission_response(request.path)


@app.route("/actions/wipeap/<AccountID>")
def panel_wipe_user_ap_action(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeAutopilot(AccountID)
        RAPLog(
            session["AccountId"],
            f"has wiped the autopilot statistics for the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")
    else:
        return no_permission_response(request.path)


@app.route("/actions/wiperx/<AccountID>")
def panel_wipe_user_rx_action(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeRelax(AccountID)
        RAPLog(
            session["AccountId"],
            f"has wiped the relax statistics for the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")
    else:
        return no_permission_response(request.path)


@app.route("/actions/wipeva/<AccountID>")
def panel_wipe_user_va_action(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeVanilla(AccountID)
        RAPLog(
            session["AccountId"],
            f"has wiped the vanilla statistics for the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")
    else:
        return no_permission_response(request.path)


@app.route("/actions/restrict/<id>")
def panel_restict_user_action(id: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 6):
        Account = GetUser(id)
        if ResUnTrict(id, request.args.get("note"), request.args.get("reason")):
            RAPLog(
                session["AccountId"],
                f"has restricted the account {Account['Username']} ({id})",
            )
        else:
            RAPLog(
                session["AccountId"],
                f"has unrestricted the account {Account['Username']} ({id})",
            )
        return redirect(f"/user/edit/{id}")
    else:
        return no_permission_response(request.path)


@app.route("/actions/freeze/<id>")
def panel_freeze_user_action(id: int):
    if HasPrivilege(session["AccountId"], 6):
        Account = GetUser(id)
        FreezeHandler(id)
        RAPLog(
            session["AccountId"],
            f"has frozen the account {Account['Username']} ({id})",
        )
        return redirect(f"/user/edit/{id}")
    else:
        return no_permission_response(request.path)


@app.route("/actions/ban/<id>")
def panel_ban_user_action(id: int):
    """Do the FBI to the person."""
    if HasPrivilege(session["AccountId"], 5):
        Account = GetUser(id)
        if BanUser(id, request.args.get("reason")):
            RAPLog(
                session["AccountId"],
                f"has banned the account {Account['Username']} ({id})",
            )
        else:
            RAPLog(
                session["AccountId"],
                f"has unbanned the account {Account['Username']} ({id})",
            )
        return redirect(f"/user/edit/{id}")
    else:
        return no_permission_response(request.path)


@app.route("/actions/hwid/<id>")
def panel_wipe_user_hwid_action(id: int):
    """Clear HWID matches."""
    if HasPrivilege(session["AccountId"], 6):
        Account = GetUser(id)
        ClearHWID(id)
        RAPLog(
            session["AccountId"],
            f"has cleared the HWID matches for the account {Account['Username']} ({id})",
        )
        return redirect(f"/user/edit/{id}")
    else:
        return no_permission_response(request.path)


@app.route("/actions/delete/<id>")
def panel_delete_user_action(id: int):
    """Account goes bye bye forever."""
    if HasPrivilege(session["AccountId"], 6):
        AccountToBeDeleted = GetUser(id)
        DeleteAccount(id)
        RAPLog(
            session["AccountId"],
            f"has deleted the account {AccountToBeDeleted['Username']} ({id})",
        )
        return redirect("/users/1")
    else:
        return no_permission_response(request.path)


@app.route("/actions/kick/<id>")
def panel_kick_user_action(id: int):
    """Kick from bancho"""
    if HasPrivilege(session["AccountId"], 12):
        Account = GetUser(id)
        BanchoKick(id, "You have been kicked by an admin!")
        RAPLog(
            session["AccountId"],
            f"has kicked the account {Account['Username']} ({id})",
        )
        return redirect(f"/user/edit/{id}")
    else:
        return no_permission_response(request.path)


@app.route("/actions/deletebadge/<id>")
def panel_delete_badge_action(id: int):
    if HasPrivilege(session["AccountId"], 4):
        DeleteBadge(id)
        RAPLog(session["AccountId"], f"deleted the badge with the ID of {id}")
        return redirect(url_for("panel_view_badges"))
    else:
        return no_permission_response(request.path)


@app.route("/actions/createbadge")
def panel_create_badge_action():
    if HasPrivilege(session["AccountId"], 4):
        Badge = CreateBadge()
        RAPLog(session["AccountId"], f"Created a badge with the ID of {Badge}")
        return redirect(f"/badge/edit/{Badge}")
    else:
        return no_permission_response(request.path)


@app.route("/actions/createprivilege")
def panel_create_privilege_action():
    if HasPrivilege(session["AccountId"], 13):
        PrivID = CreatePrivilege()
        RAPLog(
            session["AccountId"],
            f"Created a new privilege group with the ID of {PrivID}",
        )
        return redirect(f"/privilege/edit/{PrivID}")
    return no_permission_response(request.path)


@app.route("/actions/deletepriv/<PrivID>")
def panel_delete_privilege_action(PrivID: int):
    if HasPrivilege(session["AccountId"], 13):
        PrivData = GetPriv(PrivID)
        DelPriv(PrivID)
        RAPLog(
            session["AccountId"],
            f"deleted the privilege {PrivData['Name']} ({PrivData['Id']})",
        )
        return redirect(url_for("panel_view_privileges"))
    else:
        return no_permission_response(request.path)


@app.route("/action/rankset/<BeatmapSet>")
def panel_rank_set_action(BeatmapSet: int):
    if HasPrivilege(session["AccountId"], 3):
        SetBMAPSetStatus(BeatmapSet, 2, session)
        RAPLog(session["AccountId"], f"ranked the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")
    else:
        return no_permission_response(request.path)


@app.route("/action/loveset/<BeatmapSet>")
def panel_love_set_action(BeatmapSet: int):
    if HasPrivilege(session["AccountId"], 3):
        SetBMAPSetStatus(BeatmapSet, 5, session)
        RAPLog(session["AccountId"], f"loved the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")
    else:
        return no_permission_response(request.path)


@app.route("/action/unrankset/<BeatmapSet>")
def panel_unrank_set_action(BeatmapSet: int):
    if HasPrivilege(session["AccountId"], 3):
        SetBMAPSetStatus(BeatmapSet, 0, session)
        RAPLog(session["AccountId"], f"unranked the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")
    else:
        return no_permission_response(request.path)


@app.route("/action/deleterankreq/<ReqID>")
def panel_complete_rank_request_action(ReqID):
    if HasPrivilege(session["AccountId"], 3):
        DeleteBmapReq(ReqID)
        return redirect("/rankreq/1")
    else:
        return no_permission_response(request.path)


@app.route("/action/kickclan/<AccountID>")
def panel_kick_user_from_clan_action(AccountID):
    if HasPrivilege(session["AccountId"], 15):
        KickFromClan(AccountID)
        return redirect("/clans/1")
    return no_permission_response(request.path)


# error handlers
@app.errorhandler(404)
def not_found_error_handler(_):
    return render_template("404.html")


@app.errorhandler(500)
def code_error_handler(error):
    return render_template("500.html")


# we make sure session exists
@app.before_request
def BeforeRequest():
    if "LoggedIn" not in list(
        dict(session).keys(),
    ):  # we checking if the session doesnt already exist
        for x in list(ServSession.keys()):
            session[x] = ServSession[x]


def no_permission_response(path: str):
    """If not logged it, returns redirect to login. Else 403s. This is for convienience when page is reloaded after restart."""
    if session["LoggedIn"]:
        return render_template("403.html")

    return redirect(f"/login?redirect={path}")


if __name__ == "__main__":
    Thread(target=PlayerCountCollection, args=(True,)).start()
    app.run(host=config.http_host, port=config.http_port, threaded=False)
    handle_update()
