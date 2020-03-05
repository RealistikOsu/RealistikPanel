#This file is responsible for running the web server and (mostly nothing else)
from flask import Flask, render_template, session, redirect, url_for, request, send_from_directory, jsonify
from flask_recaptcha import ReCaptcha
from defaults import *
from config import UserConfig
from functions import *
from colorama import Fore, init
import os
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
recaptcha = ReCaptcha(app=app)

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
    return redirect(url_for("login")) #later replace with home page yeah

@app.route("/dash/")
def dash():
    if HasPrivilege(current_user["AccountId"]):
        return render_template("dash.html", title="Dashboard", session=current_user, data=DashData(), plays=RecentPlays(), config=UserConfig)
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
                login_user(LoginData[2], remember=True) #note to self: later add remember me
                return redirect(url_for("home"))
        else:
            return render_template("login.html", alert="ReCaptcha Failed!", conf=UserConfig)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("home"))

@app.route("/bancho/settings", methods = ["GET", "POST"])
def BanchoSettings():
    if HasPrivilege(current_user["AccountId"], 4):
        #no bypassing it.
        if request.method == "GET":
            return render_template("banchosettings.html", preset=FetchBSData(), title="Bancho Settings", data=DashData(), bsdata=FetchBSData(), session=current_user, config=UserConfig)
        if request.method == "POST":
            BSPostHandler([request.form["banchoman"], request.form["mainmemuicon"], request.form["loginnotif"]], current_user) #handles all the changes
            return redirect(url_for("BanchoSettings")) #reloads page
    else:
        return render_template("403.html")

@app.route("/rank/<id>")
def RankMap(id):
    if HasPrivilege(current_user["AccountId"], 3):
        return render_template("beatrank.html", title="Rank Beatmap!", data=DashData(),  session=current_user, beatdata=GetBmapInfo(id), config=UserConfig)
    else:
        return render_template("403.html")

@app.route("/rank", methods = ["GET", "POST"])
def RankFrom():
    if request.method == "GET":
        if HasPrivilege(current_user["AccountId"], 3):
            return render_template("rankform.html", title="Rank a beatmap!", data=DashData(),  session=current_user, config=UserConfig)
        else:
            return render_template("403.html")
    else:
        if not HasPrivilege(current_user["AccountId"]): #mixing things up eh
            return render_template("403.html")
        else:
            return redirect(f"/rank/{request.form['bmapid']}") #does this even work

@app.route("/users/<page>")
def Users(page = 1):
    if HasPrivilege(current_user["AccountId"], 6):
        return render_template("users.html", title="Users", data=DashData(),  session=current_user, config=UserConfig, UserData = FetchUsers(int(page)-1))
    else:
        return render_template("403.html")

@app.route("/index.php")
def LegacyIndex():
    """For implementing RAP funcions."""
    if request.args.get("p") == "124":
        #ranking page
        return redirect(f"/rank/{request.args.get('bsid')}")

@app.route("/rank/action", methods=["POST"])
def Rank():
    if HasPrivilege(current_user["AccountId"], 3):
        BeatmapNumber = request.form["beatmapnumber"]
        RankBeatmap(BeatmapNumber, request.form[f"bmapid-{BeatmapNumber}"], request.form[f"rankstatus-{BeatmapNumber}"], current_user)
        return redirect(f"/rank/{request.form[f'bmapid-{BeatmapNumber}']}")
    else:
        return render_template("403.html")

@app.route("/system/settings", methods = ["GET", "POST"])
def SystemSettings():
    if HasPrivilege(current_user["AccountId"], 4):
        if request.method == "GET":
            return render_template("syssettings.html", data=DashData(),  session=current_user, title="System Settings", SysData=SystemSettingsValues(), config=UserConfig)
        if request.method == "POST":
            ApplySystemSettings([request.form["webman"], request.form["gameman"], request.form["register"], request.form["globalalert"], request.form["homealert"]], current_user) #why didnt i just pass request
            return render_template("syssettings.html", data=DashData(),  session=current_user, title="System Settings", SysData=SystemSettingsValues(), config=UserConfig)
    else:
        return render_template("403.html")

@app.route("/user/edit/<id>")
def EditUser(id):
    if HasPrivilege(current_user["AccountId"], 6):
        return render_template("edituser.html", data=DashData(),  session=current_user, title="Edit User", config=UserConfig, UserData=UserData(id))
    else:
        return render_template("403.html")

@app.route("/logs/<page>")
def Logs(page):
    if HasPrivilege(current_user["AccountId"], 7):
        return render_template("raplogs.html", data=DashData(),  session=current_user, title="Logs", config=UserConfig, Logs = RAPFetch(page))
    else:
        return render_template("403.html")

#API for js
@app.route("/api/js/pp/<id>")
def PPApi(id):
    return jsonify({
        "pp" : str(round(CalcPP(id), 2))
    })

#error handlers
@app.errorhandler(404)
def NotFoundError(error):
    return render_template("404.html")

@app.errorhandler(500)
def BadCodeError(error):
    return render_template("500.html")

app.run(host= '0.0.0.0', port=UserConfig["Port"])