#This file is responsible for running the web server and (mostly nothing else)
from flask import Flask, render_template, session, redirect, url_for, request, send_from_directory, jsonify
from flask_recaptcha import ReCaptcha
from defaults import *
from config import UserConfig
from functions import *
from colorama import Fore, init
import os
from updater import *
from threading import Thread

print(f" {Fore.BLUE}Running Build {GetBuild()}")
ConsoleLog(f"RealistikPanel (Build {GetBuild()}) started!")

app = Flask(__name__)
recaptcha = ReCaptcha(app=app)
app.secret_key = os.urandom(24) #encrypts the session cookie

#recaptcha setup
if UserConfig["UseRecaptcha"]:
    #recaptcha config
    app.config.update({
        "RECAPTCHA_THEME" : "dark",
        "RECAPTCHA_SITE_KEY" : UserConfig["RecaptchaSiteKey"],
        "RECAPTCHA_SECRET_KEY" : UserConfig["RecaptchaSecret"],
        "RECAPTCHA_ENABLED" : True
    })

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
         return NoPerm(session)

@app.route("/login", methods = ["GET", "POST"])
def login():
    if not session["LoggedIn"] and not HasPrivilege(session["AccountId"]):
        if request.method == "GET":
            return render_template("login.html", conf = UserConfig)
        if request.method == "POST":
            if recaptcha.verify():
                LoginData = LoginHandler(request.form["username"], request.form["password"])
                if not LoginData[0]:
                    return render_template("login.html", alert=LoginData[1], conf = UserConfig)
                if LoginData[0]:
                    SessionToApply = LoginData[2]
                    #modifying the session
                    for key in list(SessionToApply.keys()):
                        session[key] = SessionToApply[key]
                    return redirect(url_for("home"))
            else:
                return render_template("login.html", alert="ReCaptcha Failed!", conf=UserConfig)
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
         return NoPerm(session)

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
         return NoPerm(session)

@app.route("/rank", methods = ["GET", "POST"])
def RankFrom():
    if request.method == "GET":
        if HasPrivilege(session["AccountId"], 3):
            return render_template("rankform.html", title="Rank a beatmap!", data=DashData(), session=session, config=UserConfig, SuggestedBmaps = SplitList(GetSuggestedRank()))
        else:
             return NoPerm(session)
    else:
        if not HasPrivilege(session["AccountId"]): #mixing things up eh
             return NoPerm(session)
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
         return NoPerm(session)

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
             return NoPerm(session)

@app.route("/user/edit/<id>", methods = ["GET", "POST"])
def EditUser(id):
    if request.method == "GET":
        if HasPrivilege(session["AccountId"], 6):
            return render_template("edituser.html", data=DashData(), session=session, title="Edit User", config=UserConfig, UserData=UserData(id), Privs = GetPrivileges(), UserBadges= GetUserBadges(id), badges=GetBadges())
        else:
             return NoPerm(session)
    if request.method == "POST":
        if HasPrivilege(session["AccountId"], 6):
            try:
                ApplyUserEdit(request.form, session)
                RAPLog(session["AccountId"], f"has edited the user {request.form.get('username', 'NOT FOUND')}")
                return render_template("edituser.html", data=DashData(), session=session, title="Edit User", config=UserConfig, UserData=UserData(id), Privs = GetPrivileges(), UserBadges= GetUserBadges(id), badges=GetBadges(), success=f"User {request.form.get('username', 'NOT FOUND')} has been successfully edited!")
            except Exception as e:
                print(e)
                ConsoleLog("Error while editing user!", f"{e}", 3)
                return render_template("edituser.html", data=DashData(), session=session, title="Edit User", config=UserConfig, UserData=UserData(id), Privs = GetPrivileges(), UserBadges= GetUserBadges(id), badges=GetBadges(), error="An internal error has occured while editing the user! An error has been logged to the console.")
        else:
            return NoPerm(session)


@app.route("/logs/<page>")
def Logs(page):
    if HasPrivilege(session["AccountId"], 7):
        return render_template("raplogs.html", data=DashData(), session=session, title="Logs", config=UserConfig, Logs = RAPFetch(page), page=int(page), Pages = RapLogCount())
    else:
         return NoPerm(session)

@app.route("/action/confirm/delete/<id>")
def ConfirmDelete(id):
    """Confirms deletion of acc so accidents dont happen"""
    #i almost deleted my own acc lmao
    #me forgetting to commit changes saved me
    if HasPrivilege(session["AccountId"], 6):
        AccountToBeDeleted = GetUser(id)
        return render_template("confirm.html", data=DashData(), session=session, title="Confirmation Required", config=UserConfig, action=f"delete the user {AccountToBeDeleted['Username']}", yeslink=f"/actions/delete/{id}", backlink=f"/user/edit/{id}")
    else:
         return NoPerm(session)

@app.route("/user/iplookup/<ip>")
def IPUsers(ip):
    if HasPrivilege(session["AccountId"], 6):
        IPUserLookup  = FindWithIp(ip)
        UserLen = len(IPUserLookup)
        return render_template("iplookup.html", data=DashData(), session=session, title="IP Lookup", config=UserConfig, ipusers=IPUserLookup, IPLen = UserLen, ip=ip)
    else:
         return NoPerm(session)

@app.route("/badges")
def Badges():
    if HasPrivilege(session["AccountId"], 4):
        return render_template("badges.html", data=DashData(), session=session, title="Badges", config=UserConfig, badges=GetBadges())
    else:
         return NoPerm(session)

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
         return NoPerm(session)

@app.route("/privileges")
def EditPrivileges():
    if HasPrivilege(session["AccountId"], 13):
        return render_template("privileges.html", data=DashData(), session=session, title="Privileges", config=UserConfig, privileges=GetPrivileges())
    else:
         return NoPerm(session)

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
         return NoPerm(session)

@app.route("/console")
def Console():
    if HasPrivilege(session["AccountId"], 14):
        return render_template("consolelogs.html", data=DashData(), session=session, title="Console Logs", config=UserConfig, logs=GetLog())
    else:
         return NoPerm(session)

@app.route("/changelogs")
def ChangeLogs():
    if HasPrivilege(session["AccountId"]):
        return render_template("changelog.html", data=DashData(), session=session, title="Change Logs", config=UserConfig, logs=Changelogs)
    else:
         return NoPerm(session)

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
         return NoPerm(session)


@app.route("/changepass/<AccountID>", methods = ["GET", "POST"]) #may change the route to something within /user
def ChangePass(AccountID):
    if HasPrivilege(session["AccountId"], 6): #may create separate perm for this
        if request.method == "GET":
            User = GetUser(int(AccountID))
            return render_template("changepass.html", data=DashData(), session=session, title=f"Change the Password for {User['Username']}", config=UserConfig, User=User)
        if request.method == "POST":
            ChangePWForm(request.form, session)
            User = GetUser(int(AccountID))
            RAPLog(session["AccountId"], f"has changed the password of {User['Username']} ({AccountID}) {request.form['time']}.")
            return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session)

@app.route("/donoraward/<AccountID>", methods = ["GET", "POST"])
def DonorAward(AccountID):
    if HasPrivilege(session["AccountId"], 6):
        if request.method == "GET":
            User = GetUser(int(AccountID))
            return render_template("donoraward.html", data=DashData(), session=session, title=f"Award Donor to {User['Username']}", config=UserConfig, User=User)
        if request.method == "POST":
            GiveSupporterForm(request.form)
            User = GetUser(int(AccountID))
            RAPLog(session["AccountId"], f"has awarded {User['Username']} ({AccountID}) {request.form['time']} months of donor.")
            return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session)

@app.route("/donorremove/<AccountID>")
def RemoveDonorRoute(AccountID):
    if HasPrivilege(session["AccountId"], 6):
        RemoveSupporter(AccountID, session)
        return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session)


@app.route("/rankreq/<Page>")
def RankReq(Page):
    if HasPrivilege(session["AccountId"], 3):
        return render_template("rankreq.html", data=DashData(), session=session, title="Ranking Requests", config=UserConfig, RankRequests = GetRankRequests(int(Page)), page = int(Page))
    else:
        return NoPerm(session)

@app.route("/clans/<Page>")
def ClanRoute(Page):
    if HasPrivilege(session["AccountId"], 15):
        return render_template("clansview.html", data=DashData(), session=session, title="Clans", config=UserConfig, page = int(Page), Clans = GetClans(Page), Pages = GetClanPages())
    else:
        return NoPerm(session)

@app.route("/clan/<ClanID>", methods = ["GET", "POST"])
def ClanEditRoute(ClanID):
    if HasPrivilege(session["AccountId"], 15):
        if request.method == "GET":
            return render_template("editclan.html", data=DashData(), session=session, title="Clans", config=UserConfig, Clan=GetClan(ClanID), Members=SplitList(GetClanMembers(ClanID)), ClanOwner = GetClanOwner(ClanID))
        ApplyClanEdit(request.form, session)
        return render_template("editclan.html", data=DashData(), session=session, title="Clans", config=UserConfig, Clan=GetClan(ClanID), Members=SplitList(GetClanMembers(ClanID)), ClanOwner = GetClanOwner(ClanID), success="Clan edited successfully!")
    else:
        return NoPerm(session)

@app.route("/clan/delete/<ClanID>")
def ClanFinalDelete(ClanID):
    if HasPrivilege(session["AccountId"], 15):
        NukeClan(ClanID, session)
        return redirect("/clans/1")
    return NoPerm(session)

@app.route("/clan/confirmdelete/<ClanID>")
def ClanDeleteConfirm(ClanID):
    if HasPrivilege(session["AccountId"], 15):
        Clan = GetClan(ClanID)
        return render_template("confirm.html", data=DashData(), session=session, title="Confirmation Required", config=UserConfig, action=f" delete the clan {Clan['Name']}", yeslink=f"/clan/delete/{ClanID}", backlink="/clans/1")
    return NoPerm(session)

@app.route("/stats", methods = ["GET", "POST"])
def StatsRoute():
    if HasPrivilege(session["AccountId"]):
        MinPP = request.form.get("minpp", 0)
        return render_template("stats.html", data=DashData(), session=session, title="Server Statistics", config=UserConfig, StatData = GetStatistics(MinPP), MinPP = MinPP)
    return NoPerm(session)

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
        return jsonify(requests.get(UserConfig["ServerURL"] + "api/v1/ping").json())
    except:
        return jsonify({
            "code" : 503
        })
@app.route("/js/status/lets")
def LetsStatus():
    try:
        return jsonify(requests.get(UserConfig["LetsAPI"] + "v1/status").json()) #this url to provide a predictable result
    except:
        return jsonify({
            "server_status" : 0
        })
@app.route("/js/status/bancho")
def BanchoStatus():
    try:
        return jsonify(requests.get(UserConfig["BanchoURL"] + "api/v1/serverStatus").json()) #this url to provide a predictable result
    except:
        return jsonify({
            "result" : 0
        })

#actions
@app.route("/actions/wipe/<AccountID>")
def Wipe(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeAccount(AccountID)
        RAPLog(session["AccountId"], f"has wiped the account {Account['Username']} ({AccountID})")
        return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session)

@app.route("/actions/wipeap/<AccountID>")
def WipeAPRoute(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeAutopilot(AccountID)
        RAPLog(session["AccountId"], f"has wiped the autopilot statistics for the account {Account['Username']} ({AccountID})")
        return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session)

@app.route("/actions/wiperx/<AccountID>")
def WipeRXRoute(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeRelax(AccountID)
        RAPLog(session["AccountId"], f"has wiped the relax statistics for the account {Account['Username']} ({AccountID})")
        return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session)

@app.route("/actions/wipeva/<AccountID>")
def WipeVARoute(AccountID: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        Account = GetUser(AccountID)
        WipeVanilla(AccountID)
        RAPLog(session["AccountId"], f"has wiped the vanilla statistics for the account {Account['Username']} ({AccountID})")
        return redirect(f"/user/edit/{AccountID}")
    else:
        return NoPerm(session)

@app.route("/actions/restrict/<id>")
def Restrict(id: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 6):
        Account = GetUser(id)
        if ResUnTrict(id):
            RAPLog(session["AccountId"], f"has restricted the account {Account['Username']} ({id})")
        else:
            RAPLog(session["AccountId"], f"has unrestricted the account {Account['Username']} ({id})")
        return redirect(f"/user/edit/{id}")
    else:
         return NoPerm(session)

@app.route("/actions/freeze/<id>")
def Freezee(id: int):
    if HasPrivilege(session["AccountId"], 6):
        Account = GetUser(id)
        FreezeHandler(id)
        return redirect(f"/user/edit/{id}")
    else:
         return NoPerm(session)

@app.route("/actions/ban/<id>")
def Ban(id: int):
    """Do the FBI to the person."""
    if HasPrivilege(session["AccountId"], 5):
        Account = GetUser(id)
        if BanUser(id):
            RAPLog(session["AccountId"], f"has banned the account {Account['Username']} ({id})")
        else:
            RAPLog(session["AccountId"], f"has unbanned the account {Account['Username']} ({id})")
        return redirect(f"/user/edit/{id}")
    else:
         return NoPerm(session)
@app.route("/actions/hwid/<id>")
def HWID(id: int):
    """Clear HWID matches."""
    if HasPrivilege(session["AccountId"], 6):
        Account = GetUser(id)
        ClearHWID(id)
        RAPLog(session["AccountId"], f"has cleared the HWID matches for the account {Account['Username']} ({id})")
        return redirect(f"/user/edit/{id}")
    else:
         return NoPerm(session)
@app.route("/actions/delete/<id>")
def DeleteAcc(id: int):
    """Account goes bye bye forever."""
    if HasPrivilege(session["AccountId"], 6):
        AccountToBeDeleted = GetUser(id)
        DeleteAccount(id)
        RAPLog(session["AccountId"], f"has deleted the account {AccountToBeDeleted['Username']} ({id})")
        return redirect("/users/1")
    else:
         return NoPerm(session)
@app.route("/actions/kick/<id>")
def KickFromBancho(id: int):
    """Kick from bancho"""
    if HasPrivilege(session["AccountId"], 12):
        Account = GetUser(id)
        BanchoKick(id, "You have been kicked by an admin!")
        RAPLog(session["AccountId"], f"has kicked the account {Account['Username']} ({id})")
        return redirect(f"/user/edit/{id}")
    else:
         return NoPerm(session)

@app.route("/actions/deletebadge/<id>")
def BadgeDeath(id:int):
    if HasPrivilege(session["AccountId"], 4):
        DeleteBadge(id)
        RAPLog(session["AccountId"], f"deleted the badge with the ID of {id}")
        return redirect(url_for("Badges"))
    else:
         return NoPerm(session)

@app.route("/actions/createbadge")
def CreateBadgeAction():
    if HasPrivilege(session["AccountId"], 4):
        Badge = CreateBadge()
        RAPLog(session["AccountId"], f"Created a badge with the ID of {Badge}")
        return redirect(f"/badge/edit/{Badge}")
    else:
         return NoPerm(session)

@app.route("/actions/createprivilege")
def CreatePrivilegeAction():
    if HasPrivilege(session["AccountId"], 13):
        PrivID = CreatePrivilege()
        RAPLog(session["AccountId"], f"Created a new privilege group with the ID of {PrivID}")
        return redirect(f"/privilege/edit/{PrivID}")
    return NoPerm(session)

@app.route("/actions/deletepriv/<PrivID>")
def PrivDeath(PrivID:int):
    if HasPrivilege(session["AccountId"], 13):
        PrivData = GetPriv(PrivID)
        DelPriv(PrivID)
        RAPLog(session["AccountId"], f"deleted the privilege {PrivData['Name']} ({PrivData['Id']})")
        return redirect(url_for("EditPrivileges"))
    else:
         return NoPerm(session)

@app.route("/action/rankset/<BeatmapSet>")
def RankSet(BeatmapSet: int):
    if HasPrivilege(session["AccountId"], 3):
        SetBMAPSetStatus(BeatmapSet, 2, session)
        RAPLog(session["AccountId"], f"ranked the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")
    else:
        return NoPerm(session)

@app.route("/action/loveset/<BeatmapSet>")
def LoveSet(BeatmapSet: int):
    if HasPrivilege(session["AccountId"], 3):
        SetBMAPSetStatus(BeatmapSet, 5, session)
        RAPLog(session["AccountId"], f"loved the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")
    else:
        return NoPerm(session)

@app.route("/action/unrankset/<BeatmapSet>")
def UnrankSet(BeatmapSet: int):
    if HasPrivilege(session["AccountId"], 3):
        SetBMAPSetStatus(BeatmapSet, 0, session)
        RAPLog(session["AccountId"], f"unranked the beatmap set {BeatmapSet}")
        return redirect(f"/rank/{BeatmapSet}")
    else:
        return NoPerm(session)

@app.route("/action/deleterankreq/<ReqID>")
def MarkRequestAsDone(ReqID):
    if HasPrivilege(session["AccountId"], 3):
        DeleteBmapReq(ReqID)
        return redirect("/rankreq/1")
    else:
        return NoPerm(session)

@app.route("/action/kickclan/<AccountID>")
def KickClanRoute(AccountID):
    if HasPrivilege(session["AccountId"], 15):
        KickFromClan(AccountID)
        return redirect("/clans/1")
    return NoPerm(session)

#error handlers
@app.errorhandler(404)
def NotFoundError(error):
    return render_template("404.html")

@app.errorhandler(500)
def BadCodeError(error):
    ConsoleLog("Misc unhandled error!", f"{error}", 3)
    return render_template("500.html")

#we make sure session exists
@app.before_request
def BeforeRequest(): 
    if "LoggedIn" not in list(dict(session).keys()): #we checking if the session doesnt already exist
        for x in list(ServSession.keys()):
            session[x] = ServSession[x]

def NoPerm(session):
    """If not logged it, returns redirect to login. Else 403s. This is for convienience when page is reloaded after restart."""
    if session["LoggedIn"]:
        return render_template("403.html")
    else:
        return redirect("/login")

if __name__ == "__main__":
    Thread(target=PlayerCountCollection, args=(True,)).start()
    UpdateCachedStore()
    app.run(host= '0.0.0.0', port=UserConfig["Port"])
    handleUpdate() # handle update...
