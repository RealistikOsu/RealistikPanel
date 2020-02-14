#This file is responsible for running the web server and (mostly nothing else)
from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from defaults import *
from config import *
from functions import *

app = Flask(__name__)
session = ServSession

@app.route("/")
def home():
    return redirect(url_for("dash"))

@app.route("/dash/")
def dash():
    if session["LoggedIn"]:
        return render_template("dash.html", title="Dashboard", session=session, data=DashData(), plays=RecentPlays())
    else:
        return redirect(url_for("login"))

@app.route("/login", methods = ["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

@app.route("/logout")
def logout():
    #clears session
    session = ServSession
    return redirect(url_for("home"))

@app.route("/bancho/settings", methods = ["GET", "POST"])
def BanchoSettings():
    #note to self: add permission checking
    if session["LoggedIn"]:
        #no bypassing it.
        if request.method == "GET":
            return render_template("banchosettings.html", preset=FetchBSData(), title="Bancho Settings", data=DashData(), bsdata=FetchBSData(), session=session)
        if request.method == "POST":
            BSPostHandler([request.form["banchoman"], request.form["mainmemuicon"], request.form["loginnotif"]]) #handles all the changes
            return redirect(url_for("BanchoSettings")) #reloads page
    else:
        return redirect(url_for("login"))

@app.route("/rank/<id>")
def RankMap(id):
    if session["LoggedIn"]:
        return render_template("beatrank.html", title="Rank Beatmap!", data=DashData(),  session=session, beatdata=GetBmapInfo(id))
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