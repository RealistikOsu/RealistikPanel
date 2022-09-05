#This file is responsible for running the web server and (mostly nothing else)
from flask import Flask, render_template, session, redirect, url_for, request, send_from_directory, jsonify
from defaults import *
from config import UserConfig
from functions import *
from colorama import Fore, init
import os
from updater import *
from threading import Thread

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

print(f" {Fore.BLUE}Running Build {GetBuild()}")
ConsoleLog(f"RealistikPanel (Build {GetBuild()}) started!")

app = Flask(__name__)
app.secret_key = os.urandom(24) #encrypts the session cookie

@app.route("/")
def home():
    if session["LoggedIn"]:
        return redirect(url_for("dash"))
    else:
        return redirect(url_for("login"))

@app.route("/dash/")
def dash():
    if HasPrivilege(session["AccountId"]):
        #responsible for the "HeY cHeCk OuT tHe ChAnGeLoG"
        User = GetCachedStore(session["AccountName"])
        Thread(target=UpdateUserStore, args=(session["AccountName"],)).start()
        if User["LastBuild"] == GetBuild():
            return render_template("dash.html", title="Dashboard", session=session, data=DashData(), plays=RecentPlays(), config=UserConfig, Graph=DashActData(), MostPlayed=GetMostPlayed())
        else:
            return render_template("dash.html", title="Dashboard", session=session, data=DashData(), plays=RecentPlays(), config=UserConfig, Graph=DashActData(), MostPlayed=GetMostPlayed(), info=f"Hey! RealistikPanel has been recently updated to build <b>{GetBuild()}</b>! Check out <a href='/changelogs'>what's new here!</a>")
    else:
         return NoPerm(session, request.path)

IP_REDIRS = {}
@app.route("/login", methods = ["GET", "POST"])
def login():
    if not session["LoggedIn"] and not HasPrivilege(session["AccountId"]):

        if request.method == "GET":
            redir = request.args.get("redirect")
            if redir: 
                IP_REDIRS[request.headers.get("X-Real-IP")] = redir

            return render_template("login.html", conf = UserConfig)

        if request.method == "POST":
            LoginData = LoginHandler(request.form["username"], request.form["password"])
            if not LoginData[0]:
                return render_template("login.html", alert=LoginData[1], conf = UserConfig)
            else:
                SessionToApply = LoginData[2]
                #modifying the session
                for key in list(SessionToApply.keys()):
                    session[key] = SessionToApply[key]

                redir = IP_REDIRS.get(request.headers.get("X-Real-IP"))
                if redir:
                    del IP_REDIRS[request.headers.get("X-Real-IP")]
                    return redirect(redir)

                return redirect(url_for("home"))
    else:
        return redirect(url_for("dash"))

@app.route("/logout")
def logout():
    #modifying the session
    for x in list(ServSession.keys()):
        session[x] = ServSession[x]
    return redirect(url_for("home"))

@app.route("/bancho/settings", methods = ["GET", "POST"])
def BanchoSettings():
    if HasPrivilege(session["AccountId"], 4):
        #no bypassing it.
        if request.method == "GET":
            return render_template("banchosettings.html", preset=FetchBSData(), title="Bancho Settings", data=DashData(), bsdata=FetchBSData(), session=session, config=UserConfig)
        if request.method == "POST":
            try:
                BSPostHandler([request.form["banchoman"], request.form["mainmemuicon"], request.form["loginnotif"]], session) #handles all the changes
                return render_template("banchosettings.html", preset=FetchBSData(), title="Bancho Settings", data=DashData(), bsdata=FetchBSData(), session=session, config=UserConfig, success="Bancho settings were successfully edited!")
            except Exception as e:
                print(e)
                ConsoleLog("Error while editing bancho settings!", f"{e}", 3)
                return render_template("banchosettings.html", preset=FetchBSData(), title="Bancho Settings", data=DashData(), bsdata=FetchBSData(), session=session, config=UserConfig, error="An internal error has occured while saving bancho settings! An error has been logged to the console.")

    else:
         return NoPerm(session, request.path)

@app.route("/rank/<id>", methods = ["GET", "POST"])
def RankMap(id):
    if HasPrivilege(session["AccountId"], 3):
        if request.method == "GET":
            return render_template("beatrank.html", title="Rank Beatmap!", data=DashData(), session=session, beatdata=SplitList(GetBmapInfo(id)), config=UserConfig, Id= id)
        if request.method == "POST":
            try:
                BeatmapNumber = request.form["beatmapnumber"]
                RankBeatmap(BeatmapNumber, request.form[f"bmapid-{BeatmapNumber}"], request.form[f"rankstatus-{BeatmapNumber}"], session)
                return render_template("beatrank.html", title="Rank Beatmap!", data=DashData(), session=session, beatdata=SplitList(GetBmapInfo(id)), config=UserConfig, success=f"Successfully ranked beatmap {id}!", Id= id)
            except Exception as e:
                print(e)
                ConsoleLog(f"Error while ranking beatmap ({id})!", f"{e}", 3)
                return render_template("beatrank.html", title="Rank Beatmap!", data=DashData(), session=session, beatdata=SplitList(GetBmapInfo(id)), config=UserConfig, error="An internal error has occured while ranking! An error has been logged to the console.", Id= id)
    else:
         return NoPerm(session, request.path)

@app.route("/rank", methods = ["GET", "POST"])
def RankFrom():
    if request.method == "GET":
        if HasPrivilege(session["AccountId"], 3):
            return render_template("rankform.html", title="Rank a beatmap!", data=DashData(), session=session, config=UserConfig, SuggestedBmaps = SplitList(GetSuggestedRank()))
        else:
             return NoPerm(session, request.path)
    else:
        if not HasPrivilege(session["AccountId"]): #mixing things up eh
             return NoPerm(session, request.path)
        else:
            return redirect(f"/rank/{request.form['bmapid']}") #does this even work

@app.route("/users/<page>", methods = ["GET", "POST"])
def Users(page = 1):
    if HasPrivilege(session["AccountId"], 6):
        if request.method == "GET":
            return render_template("users.html", title="Users", data=DashData(), session=session, config=UserConfig, UserData = FetchUsers(int(page)-1), page=int(page), Pages=UserPageCount())
        if request.method == "POST":
            return render_template("users.html", title="Users", data=DashData(), session=session, config=UserConfig, UserData = FindUserByUsername(request.form["user"], int(page)), page=int(page), User=request.form["user"], Pages=UserPageCount())
    else:
         return NoPerm(session, request.path)

@app.route("/index.php")
def LegacyIndex():
    """For implementing RAP funcions."""
    Page = request.args.get("p")
    if Page == "124":
        #ranking page
        return redirect(f"/rank/{request.args.get('bsid')}")
    elif Page == "103": #hanayo link
        Account = request.args.get("id")
        return redirect(f"/user/edit/{Account}")
    return redirect(url_for("dash")) #take them to the root

@app.route("/system/settings", methods = ["GET", "POST"])
def SystemSettings():
    if HasPrivilege(session["AccountId"], 4):
        if request.method == "GET":
            return render_template("syssettings.html", data=DashData(), session=session, title="System Settings", SysData=SystemSettingsValues(), config=UserConfig)
        if request.method == "POST":
            try:
                ApplySystemSettings([request.form["webman"], request.form["gameman"], request.form["register"], request.form["globalalert"], request.form["homealert"]], session) #why didnt i just pass request
                return render_template("syssettings.html", data=DashData(), session=session, title="System Settings", SysData=SystemSettingsValues(), config=UserConfig, success = "System settings successfully edited!")
            except Exception as e:
                print(e)
                ConsoleLog("Error while editing system settings!", f"{e}", 3)
                return render_template("syssettings.html", data=DashData(), session=session, title="System Settings", SysData=SystemSettingsValues(), config=UserConfig, error = "An internal error has occured while saving system settings! An error has been logged to the console.")
        else:
             return NoPerm(session, request.path)

@app.route("/user/edit/<id>", methods = ["GET", "POST"])
def EditUser(id):
    if request.method == "GET":
        if HasPrivilege(session["AccountId"], 6):
            return render_template("edituser.html", data=DashData(), session=session, title="Edit User", config=UserConfig, UserData=UserData(id), Privs = GetPrivileges(), UserBadges= GetUserBadges(id), badges=GetBadges(), ShowIPs = HasPrivilege(session["AccountId"], 16), ban_logs = fetch_user_banlogs(int(id)))
        else:
             return NoPerm(session, request.path)
    if request.method == "POST":
        if HasPrivilege(session["AccountId"], 6):
            try:
                ApplyUserEdit(request.form, session)
                RAPLog(session["AccountId"], f"has edited the user {request.form.get('username', 'NOT FOUND')}")
                return render_template("edituser.html", data=DashData(), session=session, title="Edit User", config=UserConfig, UserData=UserData(id), Privs = GetPrivileges(), UserBadges= GetUserBadges(id), badges=GetBadges(), success=f"User {request.form.get('username', 'NOT FOUND')} has been successfully edited!", ShowIPs = HasPrivilege(session["AccountId"], 16))
            except Exception as e:
                print(e)
                ConsoleLog("Error while editing user!", f"{e}", 3)
                return render_template("edituser.html", data=DashData(), session=session, title="Edit User", config=UserConfig, UserData=UserData(id), Privs = GetPrivileges(), UserBadges= GetUserBadges(id), badges=GetBadges(), error="An internal error has occured while editing the user! An error has been logged to the console.", ShowIPs = HasPrivilege(session["AccountId"], 16))
        else:
            return NoPerm(session, request.path)


@app.route("/logs/<page>")
def Logs(page):
    if HasPrivilege(session["AccountId"], 7):
        return render_template("raplogs.html", data=DashData(), session=session, title="Logs", config=UserConfig, Logs = RAPFetch(page), page=int(page), Pages = RapLogCount())
    else:
         return NoPerm(session, request.path)

@app.route("/action/confirm/delete/<id>")
def ConfirmDelete(id):
    """Confirms deletion of acc so accidents dont happen"""
    #i almost deleted my own acc lmao
    #me forgetting to commit changes saved me
    if HasPrivilege(session["AccountId"], 6):
        AccountToBeDeleted = GetUser(id)
        return render_template("confirm.html", data=DashData(), session=session, title="Confirmation Required", config=UserConfig, action=f"delete the user {AccountToBeDeleted['Username']}", yeslink=f"/actions/delete/{id}", backlink=f"/user/edit/{id}")
    else:
         return NoPerm(session, request.path)

@app.route("/user/iplookup/<ip>")
def IPUsers(ip):
    if HasPrivilege(session["AccountId"], 16):
        IPUserLookup  = FindWithIp(ip)
        UserLen = len(IPUserLookup)
        return render_template("iplookup.html", data=DashData(), session=session, title="IP Lookup", config=UserConfig, ipusers=IPUserLookup, IPLen = UserLen, ip=ip)
    else:
         return NoPerm(session, request.path)
     
@app.route("/ban-logs/<page>")
def BanLogs(page):
    if HasPrivilege(session["AccountId"], 7):
        return render_template("ban_logs.html", data=DashData(), session=session, title="Ban Logs", config=UserConfig, ban_logs = fetch_banlogs(int(page)-1), page=int(page), pages = ban_pages())
    else:
         return NoPerm(session, request.path)

@app.route("/badges")
def Badges():
    if HasPrivilege(session["AccountId"], 4):
        return render_template("badges.html", data=DashData(), session=session, title="Badges", config=UserConfig, badges=GetBadges())
    else:
         return NoPerm(session, request.path)

@app.route("/badge/edit/<BadgeID>", methods = ["GET", "POST"])
def EditBadge(BadgeID: int):
    if HasPrivilege(session["AccountId"], 4):
        if request.method == "GET":
            return render_template("editbadge.html", data=DashData(), session=session, title="Edit Badge", config=UserConfig, badge=GetBadge(BadgeID))
        if request.method == "POST":
            try:
                SaveBadge(request.form)
                RAPLog(session["AccountId"], f"edited the badge with the ID of {BadgeID}")
                return render_template("editbadge.html", data=DashData(), session=session, title="Edit Badge", config=UserConfig, badge=GetBadge(BadgeID), success=f"Badge {BadgeID} has been successfully edited!")
            except Exception as e:
                print(e)
                ConsoleLog("Error while editing badge!", f"{e}", 3)
                return render_template("editbadge.html", data=DashData(), session=session, title="Edit Badge", config=UserConfig, badge=GetBadge(BadgeID), error="An internal error has occured while editing the badge! An error has been logged to the console.")
    else:
         return NoPerm(session, request.path)

@app.route("/privileges")
def EditPrivileges():
    if HasPrivilege(session["AccountId"], 13):
        return render_template("privileges.html", data=DashData(), session=session, title="Privileges", config=UserConfig, privileges=GetPrivileges())
    else:
         return NoPerm(session, request.path)

@app.route("/privilege/edit/<Privilege>", methods = ["GET", "POST"])
def EditPrivilege(Privilege: int):
    if HasPrivilege(session["AccountId"], 13):
        if request.method == "GET":
            return render_template("editprivilege.html", data=DashData(), session=session, title="Privileges", config=UserConfig, privileges=GetPriv(Privilege))
        if request.method == "POST":
            try:
                UpdatePriv(request.form)
                Priv = GetPriv(Privilege)
                RAPLog(session["AccountId"], f"has edited the privilege group {Priv['Name']} ({Priv['Id']})")
                return render_template("editprivilege.html", data=DashData(), session=session, title="Privileges", config=UserConfig, privileges=Priv, success=f"Privilege {Priv['Name']} has been successfully edited!")
            except Exception as e:
                print(e)
                ConsoleLog("Error while editing privilege!", f"{e}", 3)
                Priv = GetPriv(Privilege)
                return render_template("editprivilege.html", data=DashData(), session=session, title="Privileges", config=UserConfig, privileges=Priv, error="An internal error has occured while editing the privileges! An error has been logged to the console.")
    else:
         return NoPerm(session, request.path)

@app.route("/console")
def Console():
    if HasPrivilege(session["AccountId"], 14):
        return render_template("consolelogs.html", data=DashData(), session=session, title="Console Logs", config=UserConfig, logs=GetLog())
    else:
         return NoPerm(session, request.path)

@app.route("/changelogs")
def ChangeLogs():
    if HasPrivilege(session["AccountId"]):
        return render_template("changelog.html", data=DashData(), session=session, title="Change Logs", config=UserConfig, logs=Changelogs)
    else:
         return NoPerm(session, request.path)

@app.route("/current.json")
def CurrentIPs():
    """IPs for the Ripple switcher."""
    return jsonify({
        "osu.ppy.sh": UserConfig["CurrentIP"],
        "c.ppy.sh": UserConfig["CurrentIP"],
        "c1.ppy.sh": UserConfig["CurrentIP"],
        "c2.ppy.sh": UserConfig["CurrentIP"],
        "c3.ppy.sh": UserConfig["CurrentIP"],
        "c4.ppy.sh": UserConfig["CurrentIP"],
        "c5.ppy.sh": UserConfig["CurrentIP"],
        "c6.ppy.sh": UserConfig["CurrentIP"],
        "ce.ppy.sh": UserConfig["CurrentIP"],
        "a.ppy.sh": UserConfig["CurrentIP"],
        "s.ppy.sh": UserConfig["CurrentIP"],
        "i.ppy.sh": UserConfig["CurrentIP"],
        "bm6.ppy.sh": UserConfig["CurrentIP"]
    })

@app.route("/toggledark")
def ToggleDark():
    if session["Theme"] == "dark":
        session["Theme"] = "white"
    else:
        session["Theme"] = "dark"
    return redirect(url_for("dash"))

@app.route("/admins")
def Admins():
    if HasPrivilege(session["AccountId"]):
        return render_template("admins.html", data=DashData(), session=session, title="Admins", config=UserConfig, admins=SplitList(GetStore()))
    else:
         return NoPerm(session, request.path)


@app.route("/changepass/<AccountID>", methods = ["GET", "POST"]) #may change the route to something within /user
def ChangePass(AccountID):
    if HasPrivilege(session["AccountId"], 6): #may create separate perm for this
        if request.method == "GET":
            User = GetUser(int(AccountID))
            return render_template("changepass.html", data=DashData(), session=session, title=f"Change the Password for {User['Username']}", config=UserConfig, User=User)
        if request.method == "POST":
            ChangePWForm(request.form, session)
            User = GetUser(int(AccountID))
            return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session, request.path)

@app.route("/donoraward/<AccountID>", methods = ["GET", "POST"])
def DonorAward(AccountID):
    if HasPrivilege(session["AccountId"], 6):
        if request.method == "GET":
            User = GetUser(int(AccountID))
            return render_template("donoraward.html", data=DashData(), session=session, title=f"Award Donor to {User['Username']}", config=UserConfig, User=User)
        if request.method == "POST":
            GiveSupporterForm(request.form)
            User = GetUser(int(AccountID))
            RAPLog(session["AccountId"], f"has awarded {User['Username']} ({AccountID}) {request.form['time']} days of donor.")
            return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session, request.path)

@app.route("/donorremove/<AccountID>")
def RemoveDonorRoute(AccountID):
    if HasPrivilege(session["AccountId"], 6):
        RemoveSupporter(AccountID, session)
        return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session, request.path)


@app.route("/rankreq/<Page>")
def RankReq(Page):
    if HasPrivilege(session["AccountId"], 3):
        return render_template("rankreq.html", data=DashData(), session=session, title="Ranking Requests", config=UserConfig, RankRequests = GetRankRequests(int(Page)), page = int(Page))
    else:
        return NoPerm(session, request.path)

@app.route("/clans/<Page>")
def ClanRoute(Page):
    if HasPrivilege(session["AccountId"], 15):
        return render_template("clansview.html", data=DashData(), session=session, title="Clans", config=UserConfig, page = int(Page), Clans = GetClans(Page), Pages = GetClanPages())
    else:
        return NoPerm(session, request.path)

@app.route("/clan/<ClanID>", methods = ["GET", "POST"])
def ClanEditRoute(ClanID):
    if HasPrivilege(session["AccountId"], 15):
        if request.method == "GET":
            return render_template("editclan.html", data=DashData(), session=session, title="Clans", config=UserConfig, Clan=GetClan(ClanID), Members=SplitList(GetClanMembers(ClanID)), ClanOwner = GetClanOwner(ClanID))
        ApplyClanEdit(request.form, session)
        return render_template("editclan.html", data=DashData(), session=session, title="Clans", config=UserConfig, Clan=GetClan(ClanID), Members=SplitList(GetClanMembers(ClanID)), ClanOwner = GetClanOwner(ClanID), success="Clan edited successfully!")
    else:
        return NoPerm(session, request.path)

@app.route("/clan/delete/<ClanID>")
def ClanFinalDelete(ClanID):
    if HasPrivilege(session["AccountId"], 15):
        NukeClan(ClanID, session)
        return redirect("/clans/1")
    return NoPerm(session, request.path)

@app.route("/clan/confirmdelete/<ClanID>")
def ClanDeleteConfirm(ClanID):
    if HasPrivilege(session["AccountId"], 15):
        Clan = GetClan(ClanID)
        return render_template("confirm.html", data=DashData(), session=session, title="Confirmation Required", config=UserConfig, action=f" delete the clan {Clan['Name']}", yeslink=f"/clan/delete/{ClanID}", backlink="/clans/1")
    return NoPerm(session, request.path)

@app.route("/stats", methods = ["GET", "POST"])
def StatsRoute():
    if HasPrivilege(session["AccountId"]):
        MinPP = request.form.get("minpp", 0)
        return render_template("stats.html", data=DashData(), session=session, title="Server Statistics", config=UserConfig, StatData = GetStatistics(MinPP), MinPP = MinPP)
    return NoPerm(session, request.path)

#API for js
@app.route("/js/pp/<id>")
def PPApi(id):
    try:
        return jsonify({
            "pp" : str(round(CalcPP(id), 2)),
            "dtpp" : str(round(CalcPPDT(id), 2)),
            "code" : 200
        })
    except:
        return jsonify({"code" : 500})
#api mirrors
@app.route("/js/status/api")
def ApiStatus():
    try:
        return jsonify(requests.get(UserConfig["ServerURL"] + "api/v1/ping", verify=False, timeout=1).json())
    except Exception as err:
        print("[ERROR] /js/status/api: ", err)
        return jsonify({
            "code" : 503
        })
@app.route("/js/status/lets")
def LetsStatus():
    try:
        return jsonify(requests.get(UserConfig["LetsAPI"] + "v1/status", verify=False, timeout=1).json()) #this url to provide a predictable result
    except Exception as err:
        print("[ERROR] /js/status/lets: ", err)
        return jsonify({
            "server_status" : 0
        })
@app.route("/js/status/bancho")
def BanchoStatus():
    try:
        return jsonify(requests.get(UserConfig["BanchoURL"] + "api/v1/serverStatus", verify=False, timeout=1).json()) #this url to provide a predictable result
    except Exception as err:
        print("[ERROR] /js/status/bancho: ", err)
        return jsonify({
            "result" : 0
        })

#actions
@app.route("/actions/comment/profile/<AccountID>")
def DeleteCommentProfile(AccountID: int):
    """Wipe all comments made on this user's profile"""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        DeleteProfileComments(AccountID)

        RAPLog(session["AccountId"], f"has removed all comments made on {Account['Username']}'s profile ({AccountID})")
        return redirect(f"/user/edit/{AccountID}")
    else:
      
        return NoPerm(session, request.path)

@app.route("/actions/comment/user/<AccountID>")
def DeleteCommentUser(AccountID: int):
    """Wipe all comments made by this user"""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        DeleteUserComments(AccountID)

        RAPLog(session["AccountId"], f"has removed all comments made by {Account['Username']} ({AccountID})")
        return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session, request.path)

@app.route("/actions/wipe/<AccountID>")
def Wipe(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeAccount(AccountID)
        RAPLog(session["AccountId"], f"has wiped the account {Account['Username']} ({AccountID})")
        return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session, request.path)

@app.route("/actions/wipeap/<AccountID>")
def WipeAPRoute(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeAutopilot(AccountID)
        RAPLog(session["AccountId"], f"has wiped the autopilot statistics for the account {Account['Username']} ({AccountID})")
        return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session, request.path)

@app.route("/actions/wiperx/<AccountID>")
def WipeRXRoute(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeRelax(AccountID)
        RAPLog(session["AccountId"], f"has wiped the relax statistics for the account {Account['Username']} ({AccountID})")
        return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session, request.path)

@app.route("/actions/wipeva/<AccountID>")
def WipeVARoute(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeVanilla(AccountID)
        RAPLog(session["AccountId"], f"has wiped the vanilla statistics for the account {Account['Username']} ({AccountID})")
        return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session, request.path)

@app.route("/actions/restrict/<id>")
def Restrict(id: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 6):
        Account = GetUser(id)
        if ResUnTrict(id, request.args.get("note"), request.args.get("reason")):
            RAPLog(session["AccountId"], f"has restricted the account {Account['Username']} ({id})")
        else:
            RAPLog(session["AccountId"], f"has unrestricted the account {Account['Username']} ({id})")
        return redirect(f"/user/edit/{id}")
    else:
        return NoPerm(session, request.path)

@app.route("/actions/freeze/<id>")
def Freezee(id: int):
    if HasPrivilege(session["AccountId"], 6):
        Account = GetUser(id)
        FreezeHandler(id)
        RAPLog(session["AccountId"], f"has frozen the account {Account['Username']} ({id})")
        return redirect(f"/user/edit/{id}")
    else:
         return NoPerm(session, request.path)

@app.route("/actions/ban/<id>")
def Ban(id: int):
    """Do the FBI to the person."""
    if HasPrivilege(session["AccountId"], 5):
        Account = GetUser(id)
        if BanUser(id, request.args.get("reason")):
            RAPLog(session["AccountId"], f"has banned the account {Account['Username']} ({id})")
        else:
            RAPLog(session["AccountId"], f"has unbanned the account {Account['Username']} ({id})")
        return redirect(f"/user/edit/{id}")
    else:
         return NoPerm(session, request.path)
@app.route("/actions/hwid/<id>")
def HWID(id: int):
    """Clear HWID matches."""
    if HasPrivilege(session["AccountId"], 6):
        Account = GetUser(id)
        ClearHWID(id)
        RAPLog(session["AccountId"], f"has cleared the HWID matches for the account {Account['Username']} ({id})")
        return redirect(f"/user/edit/{id}")
    else:
         return NoPerm(session, request.path)
@app.route("/actions/delete/<id>")
def DeleteAcc(id: int):
    """Account goes bye bye forever."""
    if HasPrivilege(session["AccountId"], 6):
        AccountToBeDeleted = GetUser(id)
        DeleteAccount(id)
        RAPLog(session["AccountId"], f"has deleted the account {AccountToBeDeleted['Username']} ({id})")
        return redirect("/users/1")
    else:
         return NoPerm(session, request.path)
@app.route("/actions/kick/<id>")
def KickFromBancho(id: int):
    """Kick from bancho"""
    if HasPrivilege(session["AccountId"], 12):
        Account = GetUser(id)
        BanchoKick(id, "You have been kicked by an admin!")
        RAPLog(session["AccountId"], f"has kicked the account {Account['Username']} ({id})")
        return redirect(f"/user/edit/{id}")
    else:
         return NoPerm(session, request.path)

@app.route("/actions/deletebadge/<id>")
def BadgeDeath(id:int):
    if HasPrivilege(session["AccountId"], 4):
        DeleteBadge(id)
        RAPLog(session["AccountId"], f"deleted the badge with the ID of {id}")
        return redirect(url_for("Badges"))
    else:
         return NoPerm(session, request.path)

@app.route("/actions/createbadge")
def CreateBadgeAction():
    if HasPrivilege(session["AccountId"], 4):
        Badge = CreateBadge()
        RAPLog(session["AccountId"], f"Created a badge with the ID of {Badge}")
        return redirect(f"/badge/edit/{Badge}")
    else:
         return NoPerm(session, request.path)

@app.route("/actions/createprivilege")
def CreatePrivilegeAction():
    if HasPrivilege(session["AccountId"], 13):
        PrivID = CreatePrivilege()
        RAPLog(session["AccountId"], f"Created a new privilege group with the ID of {PrivID}")
        return redirect(f"/privilege/edit/{PrivID}")
    return NoPerm(session, request.path)

@app.route("/actions/deletepriv/<PrivID>")
def PrivDeath(PrivID:int):
    if HasPrivilege(session["AccountId"], 13):
        PrivData = GetPriv(PrivID)
        DelPriv(PrivID)
        RAPLog(session["AccountId"], f"deleted the privilege {PrivData['Name']} ({PrivData['Id']})")
        return redirect(url_for("EditPrivileges"))
    else:
         return NoPerm(session, request.path)

@app.route("/action/rankset/<BeatmapSet>")
def RankSet(BeatmapSet: int):
    if HasPrivilege(session["AccountId"], 3):
        SetBMAPSetStatus(BeatmapSet, 2, session)
        RAPLog(session["AccountId"], f"ranked the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")
    else:
        return NoPerm(session, request.path)

@app.route("/action/loveset/<BeatmapSet>")
def LoveSet(BeatmapSet: int):
    if HasPrivilege(session["AccountId"], 3):
        SetBMAPSetStatus(BeatmapSet, 5, session)
        RAPLog(session["AccountId"], f"loved the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")
    else:
        return NoPerm(session, request.path)

@app.route("/action/unrankset/<BeatmapSet>")
def UnrankSet(BeatmapSet: int):
    if HasPrivilege(session["AccountId"], 3):
        SetBMAPSetStatus(BeatmapSet, 0, session)
        RAPLog(session["AccountId"], f"unranked the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")
    else:
        return NoPerm(session, request.path)

@app.route("/action/deleterankreq/<ReqID>")
def MarkRequestAsDone(ReqID):
    if HasPrivilege(session["AccountId"], 3):
        DeleteBmapReq(ReqID)
        return redirect("/rankreq/1")
    else:
        return NoPerm(session, request.path)

@app.route("/action/kickclan/<AccountID>")
def KickClanRoute(AccountID):
    if HasPrivilege(session["AccountId"], 15):
        KickFromClan(AccountID)
        return redirect("/clans/1")
    return NoPerm(session, request.path)

#error handlers
@app.errorhandler(404)
def NotFoundError(error):
    return render_template("404.html")

@app.errorhandler(500)
def BadCodeError(error):
    ConsoleLog("Misc unhandled error!", f"{error}", 3)

    #botch_sql_recovery()

    return render_template("500.html")

#we make sure session exists
@app.before_request
def BeforeRequest(): 
    if "LoggedIn" not in list(dict(session).keys()): #we checking if the session doesnt already exist
        for x in list(ServSession.keys()):
            session[x] = ServSession[x]

def NoPerm(session, path):
    """If not logged it, returns redirect to login. Else 403s. This is for convienience when page is reloaded after restart."""
    if session["LoggedIn"]:
        return render_template("403.html")
    else:
        return redirect(f"/login?redirect={path}")

if __name__ == "__main__":
    Thread(target=PlayerCountCollection, args=(True,)).start()
    UpdateCachedStore()
    app.run(host= '127.0.0.1', port=UserConfig["Port"], threaded= False)
    handleUpdate() # handle update...
