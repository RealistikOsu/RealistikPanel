# This file is responsible for running the web server and (mostly nothing else)
from __future__ import annotations

import traceback
from copy import copy

import aiohttp
from quart import Quart
from quart import jsonify
from quart import redirect
from quart import render_template
from quart import request
from quart import url_for
import redis.asyncio as redis

from panel import logger
from panel import web
from panel import state
from panel.adapters.mysql import MySQLPool
from panel.adapters.sqlite import Sqlite
from panel.common.utils import halve_list
from panel.config import config
from panel.constants.traceback import TracebackType
from panel.functions import *
from panel.web.responses import load_panel_template
from panel.web.responses import no_permission_response
from panel.web.sessions import requires_privilege


# TODO: Make better routers.
def configure_routes(app: Quart) -> None:
    @app.route("/")
    async def panel_home_redirect():
        session = web.sessions.get()
        if session.logged_in:
            return redirect(url_for("panel_dashboard"))
        else:
            return redirect(url_for("panel_login"))

    @app.route("/dash/")
    @requires_privilege(Privileges.ADMIN_ACCESS_RAP)
    async def panel_dashboard():
        return await load_panel_template(
            title="Dashboard",
            file="dash.html",
            route="/dash",
            plays=await get_recent_plays(),
            Graph=get_playcount_graph_data(),
            MostPlayed=await GetMostPlayed(),
        )

    IP_REDIRS = {}

    # TODO: rework
    @app.route("/login", methods=["GET", "POST"])
    async def panel_login():
        session = web.sessions.get()

        if session.logged_in and await has_privilege_value(
            session.user_id,
            Privileges.ADMIN_ACCESS_RAP,
        ):
            return redirect(url_for("panel_dashboard"))

        if request.method == "GET":
            redir = request.args.get("redirect")
            if redir:
                IP_REDIRS[request.headers.get("X-Real-IP")] = redir

            return await render_template("login.html", conf=config)

        if request.method == "POST":
            form = await request.form
            success, data = await LoginHandler(
                form["username"],
                form["password"],
            )
            if not success:
                return await render_template(
                    "login.html",
                    alert=data,
                    conf=config,
                )

            session.logged_in = True
            session.privileges = data.privileges  # type: ignore
            session.user_id = data.user_id  # type: ignore
            session.username = data.username  # type: ignore
            session.privilege_name = data.privilege_name  # type: ignore
            web.sessions.set(session)

            redir = IP_REDIRS.get(request.headers.get("X-Real-IP"))
            if redir:
                del IP_REDIRS[request.headers.get("X-Real-IP")]
                return redirect(redir)

            return redirect(url_for("panel_home_redirect"))

        return await render_template("errors/403.html")

    @app.route("/logout")
    async def panel_session_logout():
        session = web.sessions.get()

        if session.logged_in:
            session = copy(web.sessions.DEFAULT_SESSION)
            web.sessions.set(session)

        return redirect(url_for("panel_home_redirect"))

    @app.route("/bancho/settings", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_SERVERS)
    async def panel_bancho_settings():
        session = web.sessions.get()

        error = None
        success = None
        if request.method == "POST":
            form = await request.form
            try:
                await handle_bancho_settings_edit(
                    form["banchoman"],
                    form["mainmemuicon"],
                    form["loginnotif"],
                    session.user_id,
                )
                success = "Bancho settings were successfully edited!"
            except Exception:
                error = "Failed to save Bancho settings!"
                tb = traceback.format_exc()
                logger.error("Failed to save Bancho settings with error: " + tb)
                await log_traceback(tb, session, TracebackType.DANGER)

        return await load_panel_template(
            "banchosettings.html",
            title="Bancho Settings",
            route="/bancho/settings",
            bsdata=await FetchBSData(),
            preset=await FetchBSData(),
            error=error,
            success=success,
        )

    @app.route("/rank/<int:beatmap_id>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_ACCESS_RAP)
    async def panel_rank_beatmap(beatmap_id: int):
        session = web.sessions.get()

        error = None
        success = None
        if request.method == "POST":
            form = await request.form
            try:
                beatmap_index = form["beatmapnumber"]
                await RankBeatmap(
                    int(form[f"bmapid-{beatmap_index}"]),
                    form[f"rankstatus-{beatmap_index}"],
                    session,
                )
                success = f"Successfully ranked a beatmap with the ID of {beatmap_id}"
            except InsufficientPrivilegesError:
                error = "You do not have the required privileges to rank this beatmap."
            except Exception:
                error = f"Failed to rank beatmap {beatmap_id}!"
                tb = traceback.format_exc()
                logger.error(f"Failed to rank beatmap {beatmap_id} with error: " + tb)
                await log_traceback(tb, session, TracebackType.DANGER)

        try:
            return await load_panel_template(
                "beatrank.html",
                title="Rank Beatmap!",
                route="/rank",
                Id=beatmap_id,
                beatdata=await GetBmapInfo(beatmap_id, session.user_id),
                success=success,
                error=error,
            )
        except InsufficientPrivilegesError:
            return no_permission_response(session)

    @app.route("/rank", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_ACCESS_RAP)
    async def panel_rank_beatmap_search():
        if request.method == "POST":
            form = await request.form
            return redirect(f"/rank/{form['bmapid']}")

        return await load_panel_template(
            "rankform.html",
            route="/rank",
            title="Rank a beatmap!",
            SuggestedBmaps=await GetSuggestedRank(),
        )

    @app.route("/users/<int:page>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_search_users(page: int = 1):
        if page < 1:
            return redirect("/users/1")

        search_term = request.args.get("user")
        if not search_term and request.method == "POST":
            form = await request.form
            search_term = form.get("user")
            if search_term:
                return redirect(f"/users/1?user={search_term}")

        if search_term:
            user_data = await FindUserByUsername(
                search_term,
                page,
            )
            pages = await SearchUserPageCount(search_term)
        else:
            user_data = await FetchUsers(page - 1)
            pages = await UserPageCount()

        return await load_panel_template(
            "users.html",
            title="Search Users",
            route="/users",
            UserData=user_data,
            page=page,
            pages=pages,
            search_term=search_term,
        )

    @app.route("/index.php")
    async def panel_legacy_index():
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
    async def panel_system_settings():
        session = web.sessions.get()

        error = None
        success = None
        if request.method == "POST":
            form = await request.form
            try:
                await ApplySystemSettings(
                    [
                        form["webman"],
                        form["gameman"],
                        form["register"],
                        form["globalalert"],
                        form["homealert"],
                    ],
                    session.user_id,
                )
                success = "Successfully edited the system settings!"
            except Exception:
                error = "An internal error has occured while saving system settings!"
                tb = traceback.format_exc()
                logger.error(
                    "An internal error has occured while saving system settings, error: "
                    + tb,
                )
                await log_traceback(tb, session, TracebackType.DANGER)

        return await load_panel_template(
            "syssettings.html",
            title="System Settings",
            route="/system/settings",
            SysData=await SystemSettingsValues(),
            success=success,
            error=error,
        )

    @app.route("/user/edit/<int:user_id>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_edit_user(user_id: int):
        session = web.sessions.get()

        error = None
        success = None
        if request.method == "POST":
            form = await request.form
            try:
                resp = await ApplyUserEdit(form, session.user_id)
                if isinstance(resp, str):
                    error = resp
                else:
                    success = "User successfully edited!"
            except Exception:
                error = "An internal error has occured while editing the user!"
                tb = traceback.format_exc()
                logger.error(
                    "An internal error has occured while editing the user, error: "
                    + tb,
                )
                await log_traceback(tb, session, TracebackType.DANGER)

        return await load_panel_template(
            "edituser.html",
            title="Edit User",
            route="/users",
            UserData=await UserData(user_id),
            Privs=await GetPrivileges(),
            UserBadges=await GetUserBadges(user_id),
            badges=await GetBadges(),
            ShowIPs=await has_privilege_value(
                session.user_id, Privileges.PANEL_VIEW_IPS
            ),
            ban_logs=await fetch_user_banlogs(user_id),
            hwid_count=await get_hwid_count(user_id),
            countries=get_countries(),
            past_username_history=await get_username_history(user_id),
            error=error,
            success=success,
        )

    @app.route("/user/reset_avatar/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_reset_avatar(user_id: int):
        session = web.sessions.get()

        if await ResetAvatar(user_id):
            await RAPLog(session.user_id, f"reset avatar for user {user_id}")
            return redirect(f"/user/edit/{user_id}")
        else:
            return redirect(f"/user/edit/{user_id}")

    @app.route("/logs/<int:page>")
    @requires_privilege(Privileges.ADMIN_VIEW_RAP_LOGS)
    async def panel_view_logs(page: int):
        if page < 1:
            return redirect("/logs/1")

        return await load_panel_template(
            "raplogs.html",
            title="Admin Logs",
            route="/logs",
            Logs=await RAPFetch(page),
            page=page,
            Pages=await RapLogCount(),
        )

    @app.route("/action/confirm/delete/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_delete_user_confirm(user_id: int):
        target = await GetUser(user_id)
        return await load_panel_template(
            "confirm.html",
            title="Confirmation Required",
            route="/users",
            action=f"delete the user {target['Username']}",
            yeslink=f"/actions/delete/{user_id}",
            backlink=f"/user/edit/{user_id}",
        )

    @app.route("/user/iplookup/<ip>")
    @requires_privilege(Privileges.PANEL_VIEW_IPS)
    async def panel_view_user_ip(ip: str):
        IPUserLookup = await FindWithIp(ip)
        UserLen = len(IPUserLookup)
        return await load_panel_template(
            "iplookup.html",
            title="Recent IP Lookup",
            route="/users",
            ipusers=IPUserLookup,
            IPLen=UserLen,
            ip=ip,
        )

    @app.route("/user/fulliplookup/<int:user_id>")
    @requires_privilege(Privileges.PANEL_VIEW_IPS)
    async def panel_view_full_user_ip(user_id: int):
        IPUserLookup = await find_all_ips(user_id)
        return await load_panel_template(
            "fulliplookup.html",
            title="Full IP Lookup",
            route="/users",
            ipusers=IPUserLookup,
            user_id=user_id,
        )

    @app.route("/ban-logs/<int:page>")
    @requires_privilege(Privileges.ADMIN_VIEW_RAP_LOGS)
    async def panel_view_ban_logs(page: int):
        if page < 1:
            return redirect("/ban-logs/1")

        return await load_panel_template(
            "ban_logs.html",
            title="Ban Logs",
            route="/ban-logs",
            ban_logs=await fetch_banlogs(page - 1),
            page=page,
            pages=await ban_pages(),
        )

    @app.route("/badges")
    @requires_privilege(Privileges.ADMIN_MANAGE_SETTINGS)
    async def panel_view_badges():
        return await load_panel_template(
            "badges.html",
            title="Badges",
            route="/badges",
            badges=await GetBadges(),
        )

    @app.route("/badge/edit/<int:BadgeID>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_BADGES)
    async def panel_edit_badge(BadgeID: int):
        if request.method == "GET":
            return await load_panel_template(
                "editbadge.html",
                route="/badges",
                title="Edit Badge",
                badge=await GetBadge(BadgeID),
            )

        success = None
        error = None
        if request.method == "POST":
            session = web.sessions.get()
            form = await request.form
            try:
                await SaveBadge(form)
                await RAPLog(
                    session.user_id,
                    f"edited the badge with the ID of {BadgeID}",
                )

                success = f"Badge {BadgeID} has been successfully edited!"
            except Exception:
                error = "An internal error has occured while editing the badge!"
                tb = traceback.format_exc()
                logger.error(
                    f"An internal error has occured while editing the badge {BadgeID}, error: "
                    + tb,
                )
                await log_traceback(tb, session, TracebackType.DANGER)

            return await load_panel_template(
                "editbadge.html",
                route="/badges",
                title="Edit Badge",
                badge=await GetBadge(BadgeID),
                success=success,
                error=error,
            )

        return await render_template("errors/403.html")

    @app.route("/privileges")
    @requires_privilege(Privileges.ADMIN_MANAGE_SETTINGS)
    async def panel_view_privileges():
        return await load_panel_template(
            "privileges.html",
            route="/privileges",
            title="Privileges",
            privileges=await GetPrivileges(),
        )

    @app.route("/privilege/edit/<int:Privilege>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_PRIVILEGES)
    async def panel_edit_privilege(Privilege: int):
        if request.method == "GET":
            return await load_panel_template(
                "editprivilege.html",
                route="/privileges",
                title="Privileges",
                privileges=await GetPriv(Privilege),
            )

        success = None
        error = None
        if request.method == "POST":
            session = web.sessions.get()
            form = await request.form
            try:
                await UpdatePriv(form)
                Priv = await GetPriv(Privilege)
                await RAPLog(
                    session.user_id,
                    f"has edited the privilege group {Priv['Name']} ({Priv['Id']})",
                )

                success = f"Privilege {Priv['Name']} has been successfully edited!"
            except Exception:
                Priv = await GetPriv(Privilege)
                error = "An internal error has occured while editing the privileges!"
                tb = traceback.format_exc()
                logger.error(
                    f"An internal error has occured while editing the privilege '{Priv['Name']}' error: "
                    + tb,
                )
                await log_traceback(tb, session, TracebackType.DANGER)

            return await load_panel_template(
                "editprivilege.html",
                route="/privileges",
                title="Privileges",
                privileges=Priv,
                success=success,
                error=error,
            )

        return await render_template("errors/403.html")

    @app.route("/changepass/<int:AccountID>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_edit_user_password(AccountID: int):
        if request.method == "GET":
            User = await GetUser(AccountID)
            return await load_panel_template(
                "changepass.html",
                route="/users",
                title=f"Change the Password for {User['Username']}",
                User=User,
            )

        if request.method == "POST":
            session = web.sessions.get()
            form = await request.form
            await ChangePWForm(form, session)
            return redirect(f"/user/edit/{AccountID}")

        return await render_template("errors/403.html")

    @app.route("/donoraward/<int:AccountID>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_award_user_donor(AccountID: int):
        if request.method == "GET":
            User = await GetUser(AccountID)
            return await load_panel_template(
                "donoraward.html",
                route="/users",
                title=f"Award Donor to {User['Username']}",
                User=User,
            )

        if request.method == "POST":
            session = web.sessions.get()
            form = await request.form
            await GiveSupporterForm(form)
            User = await GetUser(AccountID)
            await RAPLog(
                session.user_id,
                f"has awarded {User['Username']} ({AccountID}) {form['time']} days of donor.",
            )
            return redirect(f"/user/edit/{AccountID}")

        return await render_template("errors/403.html")

    @app.route("/donorremove/<int:AccountID>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_remove_user_donor(AccountID: int):
        session = web.sessions.get()

        await RemoveSupporter(AccountID, session)
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/rankreq/<int:Page>")
    @requires_privilege(Privileges.ADMIN_ACCESS_RAP)
    async def panel_view_rank_requests(Page: int):
        if Page < 1:
            return redirect("/rankreq/1")

        session = web.sessions.get()
        allowed_modes = None

        if not await has_privilege_value(
            session.user_id, Privileges.ADMIN_MANAGE_BEATMAPS
        ):
            allowed_modes = []
            if await has_privilege_value(
                session.user_id, Privileges.ADMIN_MANAGE_STD_BEATMAPS
            ):
                allowed_modes.append(0)
            if await has_privilege_value(
                session.user_id, Privileges.ADMIN_MANAGE_TAIKO_BEATMAPS
            ):
                allowed_modes.append(1)
            if await has_privilege_value(
                session.user_id, Privileges.ADMIN_MANAGE_CATCH_BEATMAPS
            ):
                allowed_modes.append(2)
            if await has_privilege_value(
                session.user_id, Privileges.ADMIN_MANAGE_MANIA_BEATMAPS
            ):
                allowed_modes.append(3)

            if not allowed_modes:
                return await render_template("errors/403.html")

        return await load_panel_template(
            "rankreq.html",
            title="Ranking Requests",
            route="/rankreq",
            RankRequests=await GetRankRequests(Page, allowed_modes),
            page=Page,
            pages=await request_pages(allowed_modes),
        )

    @app.route("/clans/<int:Page>")
    @requires_privilege(Privileges.PANEL_MANAGE_CLANS)
    async def panel_view_clans(Page: int):
        if Page < 1:
            return redirect("/clans/1")

        search_term = request.args.get("search")

        if search_term:
            clans = await SearchClans(search_term, Page)
            pages = await GetSearchClanPages(search_term)
        else:
            clans = await GetClans(Page)
            pages = await GetClanPages()

        return await load_panel_template(
            "clansview.html",
            title="Clans",
            route="/clans",
            page=Page,
            Clans=clans,
            Pages=pages,
            search_term=search_term,
        )

    @app.route("/clan/<int:ClanID>", methods=["GET", "POST"])
    @requires_privilege(Privileges.PANEL_MANAGE_CLANS)
    async def panel_edit_clan(ClanID: int):
        if request.method == "GET":
            return await load_panel_template(
                "editclan.html",
                title="Clans",
                route="/clans",
                Clan=await GetClan(ClanID),
                Members=await GetClanMembers(ClanID),
                ClanOwner=await GetClanOwner(ClanID),
                clan_invites=await get_clan_invites(ClanID),
            )

        if request.method == "POST":
            session = web.sessions.get()
            form = await request.form
            await ApplyClanEdit(form, session)
            return await load_panel_template(
                "editclan.html",
                title="Clans",
                route="/clans",
                Clan=await GetClan(ClanID),
                Members=halve_list(await GetClanMembers(ClanID)),
                ClanOwner=await GetClanOwner(ClanID),
                success="Clan edited successfully!",
                clan_invites=await get_clan_invites(ClanID),
            )

        return await render_template("errors/403.html")

    # TODO: probably should be an action
    @app.route("/clan/delete/<int:ClanID>")
    @requires_privilege(Privileges.PANEL_MANAGE_CLANS)
    async def panel_delete_clan(ClanID: int):
        session = web.sessions.get()

        await NukeClan(ClanID, session)
        return redirect("/clans/1")

    @app.route("/clan/confirmdelete/<int:clan_id>")
    @requires_privilege(Privileges.PANEL_MANAGE_CLANS)
    async def panel_delete_clan_confirm(clan_id: int):
        clan = await GetClan(clan_id)

        return await load_panel_template(
            "confirm.html",
            route="/clans",
            title="Confirmation Required",
            action=f" delete the clan {clan['Name']}",
            yeslink=f"/clan/delete/{clan_id}",
            backlink="/clans/1",
        )

    @app.route("/stats", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_ACCESS_RAP)
    async def panel_view_server_stats():
        form = await request.form
        minimum_pp = int(form.get("minpp", "0"))
        return await load_panel_template(
            "stats.html",
            route="/stats",
            title="Server Statistics",
            StatData=await GetStatistics(minimum_pp),
            MinPP=minimum_pp,
        )

    @app.route("/user/hwid/<int:user_id>/<int:page>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def view_user_hwid_route(user_id: int, page: int = 1):
        if page < 1:
            return redirect(f"/user/hwid/{user_id}/1")

        page_info = await get_hwid_page(user_id, page - 1)
        username = page_info["user"]["Username"]

        return await load_panel_template(
            "userhwids.html",
            title=f"{username}'s Hardware Logs",
            route="/users",
            hwid_logs=page_info["results"],
            user=page_info["user"],
            page=page,
            pages=await hwid_pages(user_id),
            total_hwids=await get_hwid_count(user_id),
        )

    # API for js
    @app.route("/js/pp/<int:bmap_id>")
    async def panel_pp_api(bmap_id: int):
        try:
            return jsonify(
                {
                    "pp": round(await CalcPP(bmap_id), 2),
                    "rxpp": round(await CalcPPRX(bmap_id), 2),
                    "appp": round(await CalcPPAP(bmap_id), 2),
                    "code": 200,
                },
            )
        except Exception:
            tb = traceback.format_exc()
            logger.error(f"Error while getting PP calculations, error: " + tb)
            await log_traceback(tb, web.sessions.get(), TracebackType.DANGER)
            return jsonify({"code": 500})

    # api mirrors
    @app.route("/js/status/api")
    async def panel_api_status_api():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    config.srv_url + "api/v1/ping", timeout=1
                ) as resp:
                    return jsonify(await resp.json())
        except Exception:
            tb = traceback.format_exc()
            logger.error(f"Error while getting API Service status, error: " + tb)
            await log_traceback(tb, web.sessions.get(), TracebackType.DANGER)
            return jsonify({"code": 503})

    @app.route("/js/status/lets")
    async def panel_lets_status_api():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(config.api_ussr_url) as resp:
                    return jsonify({"server_status": int(resp.status == 404)})
        except Exception:
            tb = traceback.format_exc()
            logger.error(f"Error while getting Score Service status, error: " + tb)
            await log_traceback(tb, web.sessions.get(), TracebackType.DANGER)
            return jsonify({"server_status": 0})

    @app.route("/js/status/bancho")
    async def panel_bancho_status_api():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    config.api_bancho_url + "/api/v1/serverStatus", timeout=1
                ) as resp:
                    return jsonify(await resp.json(content_type="text/html"))
        except Exception:
            tb = traceback.format_exc()
            logger.error(f"Error while getting Bancho Service status, error: " + tb)
            await log_traceback(tb, web.sessions.get(), TracebackType.DANGER)
            return jsonify({"result": 0})

    # actions
    @app.route("/actions/comment/profile/<int:AccountID>")
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    async def panel_delete_profile_comments_action(AccountID: int):
        """Wipe all comments made on this user's profile"""
        session = web.sessions.get()

        Account = await GetUser(AccountID)
        await DeleteProfileComments(AccountID)

        await RAPLog(
            session.user_id,
            f"has removed all comments made on {Account['Username']}'s profile ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/comment/user/<int:AccountID>")
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    async def panel_delete_user_commants_action(AccountID: int):
        """Wipe all comments made by this user"""
        session = web.sessions.get()

        Account = await GetUser(AccountID)
        await DeleteUserComments(AccountID)

        await RAPLog(
            session.user_id,
            f"has removed all comments made by {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/configure/<action>/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    async def panel_action_configure(action: str, user_id: int):
        """Configures an action before execution."""
        session = web.sessions.get()

        # Get user data for the header
        user_data = await GetUser(user_id)

        # Defaults
        title = "Unknown Action"
        mods = ["va"]
        is_rollback = False

        if action == "rollback":
            title = "Rollback Account"
            is_rollback = True
            mods = []
            config_title = "Rollback Configuration"
        elif action == "wipe":
            title = "Wipe Account"
            mods = []
            config_title = "Wipe Configuration"
        elif action == "wipeva":
            title = "Wipe Vanilla Stats"
            mods = ["va"]
            config_title = "Wipe Configuration"
        elif action == "wiperx":
            title = "Wipe Relax Stats"
            mods = ["rx"]
            config_title = "Wipe Configuration"
        elif action == "wipeap":
            title = "Wipe Autopilot Stats"
            mods = ["ap"]
            config_title = "Wipe Configuration"

        return await load_panel_template(
            "useraction.html",
            title=title,
            route="/users",
            UserData=user_data,
            Action=action,
            Title=title,
            DefaultMods=mods,
            IsRollback=is_rollback,
            srv_supports_relax=config.srv_supports_relax,
            srv_supports_autopilot=config.srv_supports_autopilot,
            ConfigurationTitle=config_title,
        )

    @app.route("/actions/wipe/<int:AccountID>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    async def panel_wipe_user_action(AccountID: int):
        """The wipe action."""
        session = web.sessions.get()

        modes = [0, 1, 2, 3]
        mods = ["va", "rx", "ap"]

        if request.method == "POST":
            form = await request.form
            modes = [int(x) for x in form.getlist("modes")]
            mods = form.getlist("mods")

        Account = await GetUser(AccountID)
        await WipeUserStats(AccountID, modes, mods)

        action_desc = "wiped"
        if mods != ["va", "rx", "ap"] or modes != [0, 1, 2, 3]:
            # partial wipe
            action_desc = f"partially wiped (modes: {modes}, mods: {mods})"

        await RAPLog(
            session.user_id,
            f"has {action_desc} the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/wipeap/<int:AccountID>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    async def panel_wipe_user_ap_action(AccountID: int):
        """The wipe action."""
        session = web.sessions.get()

        modes = [0, 1, 2, 3]
        mods = ["ap"]

        if request.method == "POST":
            form = await request.form
            modes = [int(x) for x in form.getlist("modes")]
            mods = form.getlist("mods")

        Account = await GetUser(AccountID)
        await WipeUserStats(AccountID, modes, mods)
        await RAPLog(
            session.user_id,
            f"has wiped the autopilot statistics for the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/wiperx/<int:AccountID>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    async def panel_wipe_user_rx_action(AccountID: int):
        """The wipe action."""
        session = web.sessions.get()

        modes = [0, 1, 2, 3]
        mods = ["rx"]

        if request.method == "POST":
            form = await request.form
            modes = [int(x) for x in form.getlist("modes")]
            mods = form.getlist("mods")

        Account = await GetUser(AccountID)
        await WipeUserStats(AccountID, modes, mods)
        await RAPLog(
            session.user_id,
            f"has wiped the relax statistics for the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/wipeva/<int:AccountID>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    async def panel_wipe_user_va_action(AccountID: int):
        """The wipe action."""
        session = web.sessions.get()

        modes = [0, 1, 2, 3]
        mods = ["va"]

        if request.method == "POST":
            form = await request.form
            modes = [int(x) for x in form.getlist("modes")]
            mods = form.getlist("mods")

        Account = await GetUser(AccountID)
        await WipeUserStats(AccountID, modes, mods)
        await RAPLog(
            session.user_id,
            f"has wiped the vanilla statistics for the account {Account['Username']} ({AccountID})",
        )
        return redirect(f"/user/edit/{AccountID}")

    @app.route("/actions/rollback/<int:user_id>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_WIPE_USERS)
    async def panel_rollback_user_action(user_id: int):
        """Rollback user scores."""
        session = web.sessions.get()

        days = 0
        modes = [0, 1, 2, 3]
        mods = ["va", "rx", "ap"]

        if request.method == "POST":
            form = await request.form
            days = int(form.get("days", 0))
            modes = [int(x) for x in form.getlist("modes")]
            mods = form.getlist("mods")
        else:
            days = int(request.args.get("days", 0))

        if days <= 0:
            return redirect(f"/user/edit/{user_id}")

        Account = await GetUser(user_id)
        await RollbackUser(user_id, days, session.user_id, modes, mods)
        await RAPLog(
            session.user_id,
            f"has rolled back the account {Account['Username']} ({user_id}) by {days} days",
        )
        return redirect(f"/user/edit/{user_id}")

    @app.route("/actions/restrict/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_restict_user_action(user_id: int):
        session = web.sessions.get()

        Account = await GetUser(user_id)
        if await ResUnTrict(
            user_id,
            session.user_id,
            request.args.get("note", ""),
            request.args.get("reason", ""),
        ):
            await RAPLog(
                session.user_id,
                f"has restricted the account {Account['Username']} ({user_id})",
            )
        else:
            await RAPLog(
                session.user_id,
                f"has unrestricted the account {Account['Username']} ({user_id})",
            )
        return redirect(f"/user/edit/{user_id}")

    @app.route("/actions/freeze/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_freeze_user_action(user_id: int):
        session = web.sessions.get()

        Account = await GetUser(user_id)
        await FreezeHandler(user_id)
        await RAPLog(
            session.user_id,
            f"has frozen the account {Account['Username']} ({user_id})",
        )
        return redirect(f"/user/edit/{user_id}")

    @app.route("/actions/ban/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_BAN_USERS)
    async def panel_ban_user_action(user_id: int):
        """Do the FBI to the person."""
        session = web.sessions.get()

        Account = await GetUser(user_id)
        if await BanUser(user_id, session.user_id, request.args.get("reason", "")):
            await RAPLog(
                session.user_id,
                f"has banned the account {Account['Username']} ({user_id})",
            )
        else:
            await RAPLog(
                session.user_id,
                f"has unbanned the account {Account['Username']} ({user_id})",
            )
        return redirect(f"/user/edit/{user_id}")

    @app.route("/actions/hwid/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_wipe_user_hwid_action(user_id: int):
        """Clear HWID matches."""
        session = web.sessions.get()

        Account = await GetUser(user_id)
        await ClearHWID(user_id)
        await RAPLog(
            session.user_id,
            f"has cleared the HWID matches for the account {Account['Username']} ({user_id})",
        )
        return redirect(f"/user/edit/{user_id}")

    @app.route("/actions/delete/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_delete_user_action(user_id: int):
        """Account goes bye bye forever."""
        session = web.sessions.get()

        AccountToBeDeleted = await GetUser(user_id)
        await DeleteAccount(user_id)
        await RAPLog(
            session.user_id,
            f"has deleted the account {AccountToBeDeleted['Username']} ({user_id})",
        )
        return redirect("/users/1")

    @app.route("/actions/kick/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_KICK_USERS)
    async def panel_kick_user_action(user_id: int):
        """Kick from bancho"""
        session = web.sessions.get()

        Account = await GetUser(user_id)
        await BanchoKick(user_id, "You have been kicked by an admin!")
        await RAPLog(
            session.user_id,
            f"has kicked the account {Account['Username']} ({user_id})",
        )
        return redirect(f"/user/edit/{user_id}")

    @app.route("/actions/deletebadge/<int:badge_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_BADGES)
    async def panel_delete_badge_action(badge_id: int):
        session = web.sessions.get()

        await DeleteBadge(badge_id)
        await RAPLog(session.user_id, f"deleted the badge with the ID of {badge_id}")
        return redirect(url_for("panel_view_badges"))

    @app.route("/actions/createbadge")
    @requires_privilege(Privileges.ADMIN_MANAGE_BADGES)
    async def panel_create_badge_action():
        session = web.sessions.get()

        Badge = await CreateBadge()
        await RAPLog(session.user_id, f"Created a badge with the ID of {Badge}")
        return redirect(f"/badge/edit/{Badge}")

    @app.route("/actions/createprivilege")
    @requires_privilege(Privileges.ADMIN_MANAGE_PRIVILEGES)
    async def panel_create_privilege_action():
        session = web.sessions.get()

        PrivID = await CreatePrivilege()
        await RAPLog(
            session.user_id,
            f"Created a new privilege group with the ID of {PrivID}",
        )
        return redirect(f"/privilege/edit/{PrivID}")

    @app.route("/actions/deletepriv/<int:PrivID>")
    @requires_privilege(Privileges.ADMIN_MANAGE_PRIVILEGES)
    async def panel_delete_privilege_action(PrivID: int):
        session = web.sessions.get()

        PrivData = await GetPriv(PrivID)
        await DelPriv(PrivID)
        await RAPLog(
            session.user_id,
            f"deleted the privilege {PrivData['Name']} ({PrivData['Id']})",
        )
        return redirect(url_for("panel_view_privileges"))

    @app.route("/action/rankset/<int:BeatmapSet>")
    @requires_privilege(Privileges.ADMIN_ACCESS_RAP)
    async def panel_rank_set_action(BeatmapSet: int):
        session = web.sessions.get()

        try:
            await SetBMAPSetStatus(BeatmapSet, 2, session)
            await RAPLog(session.user_id, f"ranked the beatmap set {BeatmapSet}")
            return redirect(f"/rank/{BeatmapSet}")
        except InsufficientPrivilegesError:
            return no_permission_response(session)

    @app.route("/action/loveset/<int:BeatmapSet>")
    @requires_privilege(Privileges.ADMIN_ACCESS_RAP)
    async def panel_love_set_action(BeatmapSet: int):
        session = web.sessions.get()

        try:
            await SetBMAPSetStatus(BeatmapSet, 5, session)
            await RAPLog(session.user_id, f"loved the beatmap set {BeatmapSet}")
            return redirect(f"/rank/{BeatmapSet}")
        except InsufficientPrivilegesError:
            return no_permission_response(session)

    @app.route("/action/unrankset/<int:BeatmapSet>")
    @requires_privilege(Privileges.ADMIN_ACCESS_RAP)
    async def panel_unrank_set_action(BeatmapSet: int):
        session = web.sessions.get()

        try:
            await SetBMAPSetStatus(BeatmapSet, 0, session)
            await RAPLog(session.user_id, f"unranked the beatmap set {BeatmapSet}")
            return redirect(f"/rank/{BeatmapSet}")
        except InsufficientPrivilegesError:
            return no_permission_response(session)

    @app.route("/action/deleterankreq/<int:ReqID>")
    @requires_privilege(Privileges.ADMIN_MANAGE_BEATMAPS)
    async def panel_complete_rank_request_action(ReqID: int):
        await DeleteBmapReq(ReqID)
        return redirect("/rankreq/1")

    @app.route("/action/kickclan/<int:AccountID>")
    @requires_privilege(Privileges.PANEL_MANAGE_CLANS)
    async def panel_kick_user_from_clan_action(AccountID: int):
        await KickFromClan(AccountID)
        return redirect("/clans/1")

    @app.route("/actions/whitelist/<int:user_id>")
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def panel_whitelist_user_action(user_id: int):
        session = web.sessions.get()

        await apply_whitelist_change(user_id, session.user_id)
        return redirect(f"/user/edit/{user_id}")

    @app.route("/console/<int:page>")
    @requires_privilege(Privileges.PANEL_ERROR_LOGS)
    async def console(page: int):
        if page < 1:
            return redirect("/console/1")

        return await load_panel_template(
            "consolelogs.html",
            title="Console Logs",
            route="/console",
            page=page,
            pages=await traceback_pages(),
            console_logs=await get_tracebacks(page - 1),
        )

    @app.route("/user/rename/<int:user_id>", methods=["GET", "POST"])
    @requires_privilege(Privileges.ADMIN_MANAGE_USERS)
    async def rename_user(user_id: int):
        user = await GetUser(user_id)

        if user["Id"] == 0:
            return redirect("/users/1")

        error = None

        if request.method == "POST":
            form = await request.form
            ignore_name_history = form.get("no_name_history") == "on"
            error = await apply_username_change(
                user_id,
                form["username"],
                web.sessions.get().user_id,
                ignore_name_history,
            )

            if error is None:
                return redirect(f"/user/edit/{user_id}")

        return await load_panel_template(
            "user_rename.html",
            title=f"Rename {user['Username']}",
            user=user,
            error=error,
        )


def configure_error_handlers(app: Quart) -> None:
    # error handlers
    @app.errorhandler(404)
    async def not_found_error_handler(_):
        return await render_template("errors/404.html")

    @app.errorhandler(500)
    async def code_error_handler(_):
        tb = traceback.format_exc()
        session = web.sessions.get()

        await log_traceback(tb, session, TracebackType.DANGER)
        return await render_template("errors/500.html")

    # we make sure session exists
    @app.before_request
    async def pre_request():
        web.sessions.ensure()


async def init_db():
    state.database = MySQLPool(
        host=config.sql_host,
        user=config.sql_user,
        password=config.sql_password,
        database=config.sql_database,
        port=config.sql_port,
    )
    await state.database.connect()

    state.redis = redis.Redis(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
        db=config.redis_db,
    )

    state.sqlite = Sqlite("panel.db")
    await state.sqlite.connect()
    await state.sqlite.execute(
        """
        CREATE TABLE IF NOT EXISTS `tracebacks` (
            `id` INTEGER PRIMARY KEY AUTOINCREMENT,
            `user_id` INT NOT NULL,
            `traceback` TEXT NOT NULL,
            `traceback_type` INT NOT NULL,
            `time` INT NOT NULL
        );
        """,
    )
    await fix_bad_user_count()


async def close_db():
    if state.database:
        await state.database.close()
    if state.sqlite:
        await state.sqlite.close()
    if state.redis:
        await state.redis.close()


def init_app() -> Quart:
    app = Quart(
        __name__,
        static_folder="../static",
        template_folder="../templates",
    )

    app.before_serving(init_db)
    app.after_serving(close_db)

    @app.before_serving
    async def start_player_count():
        app.add_background_task(PlayerCountCollection)

    configure_routes(app)
    configure_error_handlers(app)
    web.sessions.encrypt(app)
    return app


app = init_app()
