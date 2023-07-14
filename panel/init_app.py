# This file is responsible for running the web server and (mostly nothing else)
from __future__ import annotations

import os
import sys
import traceback
from threading import Thread

from flask import Flask
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for

from panel import logger
from panel import web
from panel.config import config
from panel.functions import *
from panel.web.responses import load_panel_template
from panel.web.sessions import requires_privilege

# TODO: Make better routers.
def configure_routes(app: Flask) -> None:
    @app.route("/")
    def panel_home_redirect():
        session = web.sessions.get()
        if session.logged_in:
            return redirect(url_for("panel_dashboard"))
        else:
            return redirect(url_for("panel_login"))

    @app.route("/dash/")
    @requires_privilege(Privileges.ADMIN_ACCESS_RAP)
    def panel_dashboard():
        return load_panel_template(
            title="Dashboard",
            file="dash.html",
            plays=get_recent_plays(),
            Graph=get_playcount_graph_data(),
            MostPlayed=GetMostPlayed(),
        )

    IP_REDIRS = {}

    # TODO: rework
    @app.route("/login", methods=["GET", "POST"])
    def panel_login():
        session = web.sessions.get()

        if not session.logged_in and not HasPrivilege(session.user_id):
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
                
                session.logged_in = True
                session.privileges = data.privileges # type: ignore
                session.user_id = data.user_id # type: ignore
                session.username = data.username # type: ignore
                web.sessions.set(session)

                redir = IP_REDIRS.get(request.headers.get("X-Real-IP"))
                if redir:
                    del IP_REDIRS[request.headers.get("X-Real-IP")]
                    return redirect(redir)

                return redirect(url_for("panel_home_redirect"))
        else:
            return redirect(url_for("panel_dashboard"))

    @app.route("/logout")
    def panel_session_logout():
        return redirect(url_for("panel_home_redirect"))

    @app.route("/bancho/settings", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_SERVERS)
    def panel_bancho_settings():
        session = web.sessions.get()

        error = None
        success = None
        if request.method == "POST":
            try:
                handle_bancho_settings_edit(
                    request.form["banchoman"],
                    request.form["mainmemuicon"],
                    request.form["loginnotif"],
                    session.user_id,
                )
                success = "Bancho settings were successfully edited!"
            except Exception as e:
                error = f"Failed to save Bancho settings with error {e}!"
                logger.error("Failed to save Bancho settings with error: " + traceback.format_exc())

        return load_panel_template(
            "banchosettings.html",
            title="Bancho Settings",
            bsdata=FetchBSData(),
            preset=FetchBSData(),
            error=error,
            success=success,
        )

    @app.route("/rank/<int:beatmap_id>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_BEATMAPS)
    def panel_rank_beatmap(beatmap_id: int):
        session = web.sessions.get()

        error = None
        success = None
        if request.method == "POST":
            try:
                beatmap_index = request.form["beatmapnumber"]
                RankBeatmap(
                    int(request.form[f"bmapid-{beatmap_index}"]),
                    request.form[f"rankstatus-{beatmap_index}"],
                    session,
                )
                success = f"Successfully ranked a beatmap with the ID of {beatmap_id}"
            except Exception as e:
                error = f"Failed to rank beatmap {beatmap_id} with error {e}!"
                logger.error(f"Failed to rank beatmap {beatmap_id} with error: " + traceback.format_exc())

        return load_panel_template(
            "beatrank.html",
            title="Rank Beatmap!",
            Id=beatmap_id,
            beatdata=halve_list(GetBmapInfo(beatmap_id)),
            success=success,
            error=error,
        )

    @app.route("/rank", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_BEATMAPS)
    def panel_rank_beatmap_search():
        if request.method == "POST":
            return redirect(f"/rank/{request.form['bmapid']}")

        return load_panel_template(
            "rankform.html",
            title="Rank a beatmap!",
            SuggestedBmaps=halve_list(GetSuggestedRank()),
        )

    @app.route("/users/<int:page>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    def panel_search_users(page: int = 1):

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
            pages=UserPageCount(),
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
    @requires_privilege(Privileges.ADMIN_MANAGE_SETTINGS)
    def panel_system_settings():
        session = web.sessions.get()

        error = None
        success = None
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
                    session.user_id,
                )
                success = "Successfully edited the system settings!"
            except Exception as e:
                error = "An internal error has occured while saving system settings! An error has been logged to the console."
                logger.error("An internal error has occured while saving system settings, error: " + traceback.format_exc())

        return load_panel_template(
            "syssettings.html",
            title="System Settings",
            SysData=SystemSettingsValues(),
            success=success,
            error=error,
        )

    @app.route("/user/edit/<int:user_id>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    def panel_edit_user(user_id: int):
        session = web.sessions.get()

        error = None
        success = None
        if request.method == "POST":
            try:
                resp = ApplyUserEdit(request.form, session.user_id)
                if isinstance(resp, str):
                    error = resp
                else:
                    success = "User successfully edited!"
            except Exception:
                error = "An internal error has occured while editing the user! An error has been logged to the console."
                logger.error("An internal error has occured while editing the user, error: " + traceback.format_exc())

        return load_panel_template(
            "edituser.html",
            title="Edit User",
            UserData=UserData(user_id),
            Privs=GetPrivileges(),
            UserBadges=GetUserBadges(user_id),
            badges=GetBadges(),
            ShowIPs=has_privilege_value(session.user_id, Privileges.PANEL_VIEW_IPS),
            ban_logs=fetch_user_banlogs(user_id),
            hwid_count=get_hwid_count(user_id),
            error=error,
            success=success,
        )

    @app.route("/logs/<int:page>")
    @requires_privilege(Privileges.ADMIN_VIEW_RAP_LOGS)
    def panel_view_logs(page: int):
        return load_panel_template(
            "raplogs.html",
            title="Admin Logs",
            Logs=RAPFetch(page),
            page=page,
            Pages=RapLogCount(),
        )

    @app.route("/action/confirm/delete/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    def panel_delete_user_confirm(user_id: int):
        target = GetUser(user_id)
        return load_panel_template(
            "confirm.html",
            title="Confirmation Required",
            action=f"delete the user {target['Username']}",
            yeslink=f"/actions/delete/{user_id}",
            backlink=f"/user/edit/{user_id}",
        )

    @app.route("/user/iplookup/<ip>")
    @requires_privilege(Privileges.PANEL_VIEW_IPS)
    def panel_view_user_ip(ip: str):
        IPUserLookup = FindWithIp(ip)
        UserLen = len(IPUserLookup)
        return load_panel_template(
            "iplookup.html",
            title="IP Lookup",
            ipusers=IPUserLookup,
            IPLen=UserLen,
            ip=ip,
        )

    @app.route("/ban-logs/<int:page>")
    @requires_privilege(Privileges.ADMIN_VIEW_RAP_LOGS)
    def panel_view_ban_logs(page: int):
        return load_panel_template(
            "ban_logs.html",
            title="Ban Logs",
            ban_logs=fetch_banlogs(page - 1),
            page=page,
            pages=ban_pages(),
        )

    @app.route("/badges")
    @requires_privilege(Privileges.ADMIN_MANAGE_SETTINGS)
    def panel_view_badges():
        return load_panel_template(
            "badges.html",
            title="Badges",
            badges=GetBadges(),
        )

    @app.route("/badge/edit/<int:BadgeID>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_BADGES)
    def panel_edit_badge(BadgeID: int):
        session = web.sessions.get()

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
                    session.user_id,
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
                logger.error(f"An internal error has occured while editing the badge {BadgeID}, error: " + traceback.format_exc())
                return render_template(
                    "editbadge.html",
                    data=load_dashboard_data(),
                    session=session,
                    title="Edit Badge",
                    config=config,
                    badge=GetBadge(BadgeID),
                    error="An internal error has occured while editing the badge! An error has been logged to the console.",
                )

    @app.route("/privileges")
    @requires_privilege(Privileges.ADMIN_MANAGE_SETTINGS)
    def panel_view_privileges():
        session = web.sessions.get()

        return render_template(
            "privileges.html",
            data=load_dashboard_data(),
            session=session,
            title="Privileges",
            config=config,
            privileges=GetPrivileges(),
        )

    @app.route("/privilege/edit/<int:Privilege>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_PRIVILEGES)
    def panel_edit_privilege(Privilege: int):
        session = web.sessions.get()

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
                    session.user_id,
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
                logger.error(f"An internal error has occured while editing the privilege '{Priv['Name']}' error: " + traceback.format_exc())
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

    @app.route("/changepass/<int:AccountID>", methods=["GET", "POST"])  # may change the route to something within /user
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    def panel_edit_user_password(AccountID: int):
        session = web.sessions.get()

        if request.method == "GET":
            User = GetUser(AccountID)
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
            User = GetUser(AccountID)
            return redirect(f"/user/edit/{AccountID}")

    @app.route("/donoraward/<int:AccountID>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    def panel_award_user_donor(AccountID: int):
        session = web.sessions.get()

        if request.method == "GET":
            User = GetUser(AccountID)
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
            User = GetUser(AccountID)
            RAPLog(
                session.user_id,
                f"has awarded {User['Username']} ({AccountID}) {request.form['time']} days of donor.",
            )
            return redirect(f"/user/edit/{AccountID}")

    @app.route("/donorremove/<int:AccountID>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    def panel_remove_user_donor(AccountID: int):
        session = web.sessions.get()

        RemoveSupporter(AccountID, session)
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/rankreq/<int:Page>")
    @requires_privilege(Privileges.ADMIN_MANAGE_BEATMAPS)
    def panel_view_rank_requests(Page: int):
        session = web.sessions.get()

        return render_template(
            "rankreq.html",
            data=load_dashboard_data(),
            session=session,
            title="Ranking Requests",
            config=config,
            RankRequests=GetRankRequests(Page),
            page=Page,
            pages=request_pages(),
        )

    @app.route("/clans/<int:Page>")
    @requires_privilege(Privileges.PANEL_MANAGE_CLANS)
    def panel_view_clans(Page: int):
        session = web.sessions.get()

        return render_template(
            "clansview.html",
            data=load_dashboard_data(),
            session=session,
            title="Clans",
            config=config,
            page=Page,
            Clans=GetClans(Page),
            Pages=GetClanPages(),
        )

    @app.route("/clan/<int:ClanID>", methods=["GET", "POST"])
    @requires_privilege(Privileges.PANEL_MANAGE_CLANS)
    def panel_edit_clan(ClanID: int):
        session = web.sessions.get()

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

    # TODO: probably should be an action
    @app.route("/clan/delete/<int:ClanID>")
    @requires_privilege(Privileges.PANEL_MANAGE_CLANS)
    def panel_delete_clan(ClanID: int):
        session = web.sessions.get()

        NukeClan(ClanID, session)
        return redirect("/clans/1")

    @app.route("/clan/confirmdelete/<int:clan_id>")
    @requires_privilege(Privileges.PANEL_MANAGE_CLANS)
    def panel_delete_clan_confirm(clan_id: int):
        clan = GetClan(clan_id)

        return load_panel_template(
            "confirm.html",
            title="Confirmation Required",
            action=f" delete the clan {clan['Name']}",
            yeslink=f"/clan/delete/{clan_id}",
            backlink="/clans/1",
        )

    @app.route("/stats", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_ACCESS_RAP)
    def panel_view_server_stats():

        minimum_pp = int(request.form.get("minpp", "0"))
        return load_panel_template(
            "stats.html",
            title="Server Statistics",
            StatData=GetStatistics(minimum_pp),
            MinPP=minimum_pp,
        )

    @app.route("/user/hwid/<int:user_id>/<int:page>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    def view_user_hwid_route(user_id: int, page: int = 1):

        page_info = get_hwid_page(user_id, page - 1)
        username = page_info["user"]["Username"]

        return load_panel_template(
            "userhwids.html",
            title=f"{username}'s Hardware Logs",
            hwid_logs=page_info["results"],
            user=page_info["user"],
            page=page,
            pages=hwid_pages(user_id),
            total_hwids=get_hwid_count(user_id),
        )

    # API for js
    @app.route("/js/pp/<int:bmap_id>")
    def panel_pp_api(bmap_id: int):
        try:
            return jsonify(
                {
                    "pp": round(CalcPP(bmap_id), 2),
                    "dtpp": round(CalcPPDT(bmap_id), 2),
                    "code": 200,
                },
            )
        except Exception:
            logger.error(f"Error while getting PP calculations, error: " + traceback.format_exc())
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
            logger.error(f"Error while getting API Service status, error: " + traceback.format_exc())
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
            logger.error(f"Error while getting Score Service status, error: " + traceback.format_exc())
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
            logger.error(f"Error while getting Bancho Service status, error: " + traceback.format_exc())
            return jsonify({"result": 0})

    # actions
    @app.route("/actions/comment/profile/<int:AccountID>")
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    def panel_delete_profile_comments_action(AccountID: int):
        """Wipe all comments made on this user's profile"""
        session = web.sessions.get()

        Account = GetUser(AccountID)
        DeleteProfileComments(AccountID)

        RAPLog(
            session.user_id,
            f"has removed all comments made on {Account['Username']}'s profile ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/comment/user/<int:AccountID>")
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    def panel_delete_user_commants_action(AccountID: int):
        """Wipe all comments made by this user"""
        session = web.sessions.get()
        
        Account = GetUser(AccountID)
        DeleteUserComments(AccountID)

        RAPLog(
            session.user_id,
            f"has removed all comments made by {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/wipe/<int:AccountID>")
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    def panel_wipe_user_action(AccountID: int):
        """The wipe action."""
        session = web.sessions.get()

        Account = GetUser(AccountID)
        WipeAccount(AccountID)
        RAPLog(
            session.user_id,
            f"has wiped the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/wipeap/<int:AccountID>")
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    def panel_wipe_user_ap_action(AccountID: int):
        """The wipe action."""
        session = web.sessions.get()

        Account = GetUser(AccountID)
        WipeAutopilot(AccountID)
        RAPLog(
            session.user_id,
            f"has wiped the autopilot statistics for the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/wiperx/<int:AccountID>")
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    def panel_wipe_user_rx_action(AccountID: int):
        """The wipe action."""
        session = web.sessions.get()

        Account = GetUser(AccountID)
        WipeRelax(AccountID)
        RAPLog(
            session.user_id,
            f"has wiped the relax statistics for the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/wipeva/<int:AccountID>")
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    def panel_wipe_user_va_action(AccountID: int):
        """The wipe action."""
        session = web.sessions.get()

        Account = GetUser(AccountID)
        WipeVanilla(AccountID)
        RAPLog(
            session.user_id,
            f"has wiped the vanilla statistics for the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/restrict/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    def panel_restict_user_action(user_id: int):
        session = web.sessions.get()

        Account = GetUser(user_id)
        if ResUnTrict(user_id, request.args.get("note", ""), request.args.get("reason", "")):
            RAPLog(
                session.user_id,
                f"has restricted the account {Account['Username']} ({user_id})",
            )
        else:
            RAPLog(
                session.user_id,
                f"has unrestricted the account {Account['Username']} ({user_id})",
            )
        return redirect(f"/user/edit/{user_id}")

    @app.route("/actions/freeze/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    def panel_freeze_user_action(user_id: int):
        session = web.sessions.get()

        Account = GetUser(user_id)
        FreezeHandler(user_id)
        RAPLog(
            session.user_id,
            f"has frozen the account {Account['Username']} ({user_id})",
        )
        return redirect(f"/user/edit/{user_id}")

    @app.route("/actions/ban/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_BAN_USERS)
    def panel_ban_user_action(user_id: int):
        """Do the FBI to the person."""
        session = web.sessions.get()

        Account = GetUser(user_id)
        if BanUser(user_id, request.args.get("reason", "")):
            RAPLog(
                session.user_id,
                f"has banned the account {Account['Username']} ({user_id})",
            )
        else:
            RAPLog(
                session.user_id,
                f"has unbanned the account {Account['Username']} ({user_id})",
            )
        return redirect(f"/user/edit/{user_id}")

    @app.route("/actions/hwid/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    def panel_wipe_user_hwid_action(user_id: int):
        """Clear HWID matches."""
        session = web.sessions.get()

        Account = GetUser(user_id)
        ClearHWID(user_id)
        RAPLog(
            session.user_id,
            f"has cleared the HWID matches for the account {Account['Username']} ({user_id})",
        )
        return redirect(f"/user/edit/{user_id}")

    @app.route("/actions/delete/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    def panel_delete_user_action(user_id: int):
        """Account goes bye bye forever."""
        session = web.sessions.get()

        AccountToBeDeleted = GetUser(user_id)
        DeleteAccount(user_id)
        RAPLog(
            session.user_id,
            f"has deleted the account {AccountToBeDeleted['Username']} ({user_id})",
        )
        return redirect("/users/1")

    @app.route("/actions/kick/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_KICK_USERS)
    def panel_kick_user_action(user_id: int):
        """Kick from bancho"""
        session = web.sessions.get()

        Account = GetUser(user_id)
        BanchoKick(user_id, "You have been kicked by an admin!")
        RAPLog(
            session.user_id,
            f"has kicked the account {Account['Username']} ({user_id})",
        )
        return redirect(f"/user/edit/{user_id}")

    @app.route("/actions/deletebadge/<int:badge_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_BADGES)
    def panel_delete_badge_action(badge_id: int):
        session = web.sessions.get()

        DeleteBadge(badge_id)
        RAPLog(session.user_id, f"deleted the badge with the ID of {id}")
        return redirect(url_for("panel_view_badges"))

    @app.route("/actions/createbadge")
    @requires_privilege(Privileges.ADMIN_MANAGE_BADGES)
    def panel_create_badge_action():
        session = web.sessions.get()

        Badge = CreateBadge()
        RAPLog(session.user_id, f"Created a badge with the ID of {Badge}")
        return redirect(f"/badge/edit/{Badge}")

    @app.route("/actions/createprivilege")
    @requires_privilege(Privileges.ADMIN_MANAGE_PRIVILEGES)
    def panel_create_privilege_action():
        session = web.sessions.get()

        PrivID = CreatePrivilege()
        RAPLog(
            session.user_id,
            f"Created a new privilege group with the ID of {PrivID}",
        )
        return redirect(f"/privilege/edit/{PrivID}")

    @app.route("/actions/deletepriv/<int:PrivID>")
    @requires_privilege(Privileges.ADMIN_MANAGE_PRIVILEGES)
    def panel_delete_privilege_action(PrivID: int):
        session = web.sessions.get()

        PrivData = GetPriv(PrivID)
        DelPriv(PrivID)
        RAPLog(
            session.user_id,
            f"deleted the privilege {PrivData['Name']} ({PrivData['Id']})",
        )
        return redirect(url_for("panel_view_privileges"))

    @app.route("/action/rankset/<int:BeatmapSet>")
    @requires_privilege(Privileges.ADMIN_MANAGE_BEATMAPS)
    def panel_rank_set_action(BeatmapSet: int):
        session = web.sessions.get()

        SetBMAPSetStatus(BeatmapSet, 2, session)
        RAPLog(session.user_id, f"ranked the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")

    @app.route("/action/loveset/<BeatmapSet>")
    @requires_privilege(Privileges.ADMIN_MANAGE_BEATMAPS)
    def panel_love_set_action(BeatmapSet: int):
        session = web.sessions.get()

        SetBMAPSetStatus(BeatmapSet, 5, session)
        RAPLog(session.user_id, f"loved the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")

    @app.route("/action/unrankset/<int:BeatmapSet>")
    @requires_privilege(Privileges.ADMIN_MANAGE_BEATMAPS)
    def panel_unrank_set_action(BeatmapSet: int):
        session = web.sessions.get()

        SetBMAPSetStatus(BeatmapSet, 0, session)
        RAPLog(session.user_id, f"unranked the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")

    @app.route("/action/deleterankreq/<int:ReqID>")
    @requires_privilege(Privileges.ADMIN_MANAGE_BEATMAPS)
    def panel_complete_rank_request_action(ReqID: int):
        DeleteBmapReq(ReqID)
        return redirect("/rankreq/1")

    @app.route("/action/kickclan/<int:AccountID>")
    @requires_privilege(Privileges.PANEL_MANAGE_CLANS)
    def panel_kick_user_from_clan_action(AccountID: int):
        KickFromClan(AccountID)
        return redirect("/clans/1")


def configure_error_handlers(app: Flask) -> None:
    # error handlers
    @app.errorhandler(404)
    def not_found_error_handler(_):
        return render_template("errors/404.html")

    @app.errorhandler(500)
    def code_error_handler(error):
        return render_template("errors/500.html")

    # we make sure session exists
    @app.before_request
    def pre_request():
        web.sessions.ensure()


def init_app() -> Flask:
    app = Flask(
        __name__,
        static_folder="../static",
        template_folder="../templates",
    )
    configure_routes(app)
    configure_error_handlers(app)
    web.sessions.encrypt(app)
    return app


wsgi_app = init_app()
