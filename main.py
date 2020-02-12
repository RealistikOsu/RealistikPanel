#This file is responsible for running the web server and (mostly nothing else)
from flask import Flask, render_template, session, redirect, url_for, request
from defaults import *
from functions import *
from config import *

app = Flask(__name__)
session = ServSession

@app.route("/")
def home():
    return redirect(url_for("dash"))

@app.route("/dash/")
def dash():
    if session["LoggedIn"]:
        Data = DashData()
        return render_template("dash.html", title="Dashboard", session=session, data=Data)
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

#error handlers
@app.errorhandler(404)
def NotFoundError(error):
    return render_template("404.html")

@app.errorhandler(500)
def BadCodeError(error):
    return render_template("500.html")

app.run(host= '0.0.0.0', port=UserConfig["Port"])