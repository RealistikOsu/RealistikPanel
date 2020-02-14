#This file is responsible for running the web server and (mostly nothing else)
from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from defaults import *
from config import *
from functions import *
from colorama import Fore, init

app = Flask(__name__)
session = ServSession

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
        return render_template("login.html")

@app.route("/logout")
def logout():
    #clears session
    session = ServSession
    return redirect(url_for("home"))

@app.route("/bancho/settings", methods = ["GET", "POST"])
def BanchoSettings():
    #note to self: add permission checking
    if HasPrivilege(session):
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

#error handlers
@app.errorhandler(404)
def NotFoundError(error):
    return render_template("404.html")

@app.errorhandler(500)
def BadCodeError(error):
    return render_template("500.html")

app.run(host= '0.0.0.0', port=UserConfig["Port"])