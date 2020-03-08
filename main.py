#This file is responsible for running the web server and (mostly nothing else)
from flask import Flask, render_template, session, redirect, url_for, request, send_from_directory, jsonify
from flask_recaptcha import ReCaptcha
from defaults import *
from config import UserConfig
from functions import *
from colorama import Fore, init
import os

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
        return render_template("dash.html", title="Dashboard", session=session, data=DashData(), plays=RecentPlays(), config=UserConfig)
    else:
        return render_template("403.html")

@app.route("/login", methods = ["GET", "POST"])
def login():
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
            BSPostHandler([request.form["banchoman"], request.form["mainmemuicon"], request.form["loginnotif"]], session) #handles all the changes
            return redirect(url_for("BanchoSettings")) #reloads page
    else:
        return render_template("403.html")

@app.route("/rank/<id>")
def RankMap(id):
    if HasPrivilege(session["AccountId"], 3):
        return render_template("beatrank.html", title="Rank Beatmap!", data=DashData(),  session=session, beatdata=GetBmapInfo(id), config=UserConfig)
    else:
        return render_template("403.html")

@app.route("/rank", methods = ["GET", "POST"])
def RankFrom():
    if request.method == "GET":
        if HasPrivilege(session["AccountId"], 3):
            return render_template("rankform.html", title="Rank a beatmap!", data=DashData(),  session=session, config=UserConfig)
        else:
            return render_template("403.html")
    else:
        if not HasPrivilege(session["AccountId"]): #mixing things up eh
            return render_template("403.html")
        else:
            return redirect(f"/rank/{request.form['bmapid']}") #does this even work

@app.route("/users/<page>")
def Users(page = 1):
    if HasPrivilege(session["AccountId"], 6):
        return render_template("users.html", title="Users", data=DashData(),  session=session, config=UserConfig, UserData = FetchUsers(int(page)-1), page=int(page))
    else:
        return render_template("403.html")

@app.route("/index.php")
def LegacyIndex():
    """For implementing RAP funcions."""
    if request.args.get("p") == "124":
        #ranking page
        return redirect(f"/rank/{request.args.get('bsid')}")
    if request.args.get("p") == "124": #hanayo link
        return redirect(url_for("dash"))

@app.route("/rank/action", methods=["POST"])
def Rank():
    if HasPrivilege(session["AccountId"], 3):
        BeatmapNumber = request.form["beatmapnumber"]
        RankBeatmap(BeatmapNumber, request.form[f"bmapid-{BeatmapNumber}"], request.form[f"rankstatus-{BeatmapNumber}"], session)
        return redirect(f"/rank/{request.form[f'bmapid-{BeatmapNumber}']}")
    else:
        return render_template("403.html")

@app.route("/system/settings", methods = ["GET", "POST"])
def SystemSettings():
    if request.method == "GET":
        if request.method == "GET":
            return render_template("syssettings.html", data=DashData(),  session=session, title="System Settings", SysData=SystemSettingsValues(), config=UserConfig)
        if request.method == "POST":
            ApplySystemSettings([request.form["webman"], request.form["gameman"], request.form["register"], request.form["globalalert"], request.form["homealert"]], session) #why didnt i just pass request
            return render_template("syssettings.html", data=DashData(),  session=session, title="System Settings", SysData=SystemSettingsValues(), config=UserConfig)
        else:
            return render_template("403.html")

@app.route("/user/edit/<id>", methods = ["GET", "POST"])
def EditUser(id):
    if request.method == "GET":
        if HasPrivilege(session["AccountId"], 6):
            return render_template("edituser.html", data=DashData(),  session=session, title="Edit User", config=UserConfig, UserData=UserData(id), Privs = GetPrivileges())
        else:
            return render_template("403.html")
    if request.method == "POST":
        if HasPrivilege(session["AccountId"], 6):
            ApplyUserEdit(request.form)
            RAPLog(session["AccountId"], f"has edited the user {request.form['username']}")
            return render_template("edituser.html", data=DashData(),  session=session, title="Edit User", config=UserConfig, UserData=UserData(id), Privs = GetPrivileges())


@app.route("/logs/<page>")
def Logs(page):
    if HasPrivilege(session["AccountId"], 7):
        return render_template("raplogs.html", data=DashData(),  session=session, title="Logs", config=UserConfig, Logs = RAPFetch(page), page=int(page))
    else:
        return render_template("403.html")

@app.route("/action/confirm/delete/<id>")
def ConfirmDelete(id):
    """Confirms deletion of acc so accidents dont happen"""
    #i almost deleted my own acc lmao
    #me forgetting to commit changes saved me
    if HasPrivilege(session["AccountId"], 6):
        AccountToBeDeleted = GetUser(id)
        return render_template("confirm.html", data=DashData(),  session=session, title="Logs", config=UserConfig, action=f"delete the user {AccountToBeDeleted['Username']}", yeslink=f"/actions/delete/{id}", backlink=f"/user/edit/{id}")

#API for js
@app.route("/api/js/pp/<id>")
def PPApi(id):
    return jsonify({
        "pp" : str(round(CalcPP(id), 2))
    })
#actions
@app.route("/actions/wipe/<id>")
def Wipe(id: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 11):
        WipeAccount(id)
        RAPLog(session["AccountId"], f"has wiped account id {id}")
        return redirect(f"/user/edit/{id}")
    else:
        return render_template("403.html")
@app.route("/actions/restrict/<id>")
def Restrict(id: int):
    """The wipe action."""
    if HasPrivilege(session["AccountId"], 6):
        ResUnTrict(id)
        RAPLog(session["AccountId"], f"has restricted account ID {id}")
        return redirect(f"/user/edit/{id}")
    else:
        return render_template("403.html")
@app.route("/actions/ban/<id>")
def Ban(id: int):
    """Do the FBI to the person."""
    if HasPrivilege(session["AccountId"], 5):
        BanUser(id)
        RAPLog(session["AccountId"], f"has banned account ID {id}")
        return redirect(f"/user/edit/{id}")
    else:
        return render_template("403.html")
@app.route("/actions/hwid/<id>")
def HWID(id: int):
    """Clear HWID matches."""
    if HasPrivilege(session["AccountId"], 6):
        ClearHWID(id)
        RAPLog(session["AccountId"], f"has cleared the HWID matches for the account ID {id}")
        return redirect(f"/user/edit/{id}")
    else:
        return render_template("403.html")
@app.route("/actions/delete/<id>")
def DeleteAcc(id: int):
    """Account goes bye bye forever."""
    if HasPrivilege(session["AccountId"], 6):
        AccountToBeDeleted = GetUser(id) #here it makes sense as the account wont be here for the admin to look up
        ClearHWID(id)
        RAPLog(session["AccountId"], f"has deleted the account {AccountToBeDeleted['Username']}")
        return redirect(f"/user/edit/{id}")
    else:
        return render_template("403.html")
@app.route("/actions/kick/<id>")
def KickFromBancho(id: int):
    """Kick from bancho"""
    if HasPrivilege(session["AccountId"], 12):
        BanchoKick(id, "You have been kicked by an admin!")
        RAPLog(session["AccountId"], f"has kicked the account ID {id}")
        return redirect(f"/user/edit/{id}")
    else:
        return render_template("403.html")

#error handlers
@app.errorhandler(404)
def NotFoundError(error):
    return render_template("404.html")

@app.errorhandler(500)
def BadCodeError(error):
    return render_template("500.html")

#we make sure session exists
@app.before_request
def BeforeRequest(): 
    if "LoggedIn" not in list(dict(session).keys()): #we checking if the session doesnt already exist
        for x in list(ServSession.keys()):
            session[x] = ServSession[x]

app.run(host= '0.0.0.0', port=UserConfig["Port"])