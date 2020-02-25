#This file is responsible for running the web server and (mostly nothing else)
from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from flask_recaptcha import ReCaptcha
from defaults import *
from config import UserConfig
from functions import *
from colorama import Fore, init
import os

app = Flask(__name__)
recaptcha = ReCaptcha(app=app)
app.secret_key = os.urandom(24) #encrypts the session cookie
session = ServSession

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
    return redirect(url_for("dash"))

@app.route("/dash/")
def dash():
    if HasPrivilege(session):
        return render_template("dash.html", title="Dashboard", session=session, data=DashData(), plays=RecentPlays())
    else:
        return redirect(url_for("login"))

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
    #clears session
    SessionToApply = ServSession
    #modifying the session
    for key in list(SessionToApply.keys()):
        session[key] = SessionToApply[key]
    return redirect(url_for("home"))

@app.route("/bancho/settings", methods = ["GET", "POST"])
def BanchoSettings():
    if HasPrivilege(session):
        #no bypassing it.
        if request.method == "GET":
            return render_template("banchosettings.html", preset=FetchBSData(), title="Bancho Settings", data=DashData(), bsdata=FetchBSData(), session=session)
        if request.method == "POST":
            BSPostHandler([request.form["banchoman"], request.form["mainmemuicon"], request.form["loginnotif"]], session) #handles all the changes
            return redirect(url_for("BanchoSettings")) #reloads page
    else:
        return redirect(url_for("login"))

@app.route("/rank/<id>")
def RankMap(id):
    if HasPrivilege(session):
        return render_template("beatrank.html", title="Rank Beatmap!", data=DashData(),  session=session, beatdata=GetBmapInfo(id))
    else:
        return redirect(url_for("login"))

@app.route("/rank", methods = ["GET", "POST"])
def RankFrom():
    if request.method == "GET":
        if HasPrivilege(session):
            return render_template("rankform.html", title="Rank a beatmap!", data=DashData(),  session=session)
        else:
            return redirect(url_for("login"))
    else:
        if not HasPrivilege(session): #mixing things up eh
            return redirect(url_for("login"))
        else:
            return redirect(f"/rank/{request.form['bmapid']}") #does this even work

@app.route("/users")
def Users():
    if HasPrivilege(session):
        return

@app.route("/index.php")
def LegacyIndex():
    """For implementing RAP funcions."""
    if request.args.get("p") == "124":
        #ranking page
        return redirect(f"/rank/{request.args.get('bsid')}")

@app.route("/rank/action", methods=["POST"])
def Rank():
    if HasPrivilege(session):
        BeatmapNumber = request.form["beatmapnumber"]
        RankBeatmap(BeatmapNumber, request.form[f"bmapid-{BeatmapNumber}"], request.form[f"rankstatus-{BeatmapNumber}"], session)
        return redirect(f"/rank/{request.form[f'bmapid-{BeatmapNumber}']}")
    else:
        return redirect(url_for("login"))

#error handlers
@app.errorhandler(404)
def NotFoundError(error):
    return render_template("404.html")

@app.errorhandler(500)
def BadCodeError(error):
    return render_template("500.html")

app.run(host= '0.0.0.0', port=UserConfig["Port"])