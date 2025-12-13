from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import sqlite3
import os
import pandas as pd
from werkzeug.utils import secure_filename
import re

app = Flask(__name__)
app.secret_key = 'secret_key_for_session_management'

DATABASE = 'users.db'
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
ALLOWED_EXTENSIONS = {'xls', 'xlsx'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def execute_query(query, params=(), fetch=False):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetch:
            return cursor.fetchall()
        conn.commit()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_password(password):
    regex = r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
    return re.match(regex, password)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        first_name = request.form["firstName"]
        last_name = request.form["lastName"]
        department = request.form["department"]
        username = request.form["username"]
        password = request.form["password"]
        confirm_password = request.form["confirmPassword"]

        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "error")
            return redirect(url_for("signup"))
        
        if not validate_password(password):
            flash("Password must be at least 8 characters long, contain an uppercase letter, a lowercase letter, a number, and a special character.", "error")
            return redirect(url_for("signup"))

        try:
            query = "INSERT INTO users (first_name, last_name, department, username, password) VALUES (?, ?, ?, ?, ?)"
            execute_query(query, (first_name, last_name, department, username, password))
            flash("Account created successfully. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists. Please choose another one.", "error")
            return redirect(url_for("signup"))

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        query = "SELECT * FROM users WHERE username = ? AND password = ?"
        user = execute_query(query, (username, password), fetch=True)
        if user:
            session["user"] = user[0][1]
            flash(f"Welcome back, {session['user']}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password. Please try again.", "error")
    return render_template("login.html")

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        flash("You must log in to access the dashboard.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        if 'file' not in request.files:
            flash("No file uploaded.", "error")
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash("No file selected.", "error")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            try:
                num_samples = request.form.get("num_samples", type=int)
                if not num_samples or num_samples <= 0:
                    flash("Please provide a valid number of samples.", "error")
                    return redirect(request.url)

                gender_percentages = list(map(int, request.form.getlist("gender_percentages")))
                technology_percentages = list(map(int, request.form.getlist("technology_percentages")))
                offers = request.form.getlist("offers")
                percentages = list(map(int, request.form.getlist("percentages")))

                df = pd.read_excel(file_path)
                final_sampled_df = pd.DataFrame()

                for gender, gender_percentage in zip(["Homme", "Femme"], gender_percentages):
                    gender_subset = df[df['Genre'] == gender]
                    gender_sample_size = int((gender_percentage / 100) * num_samples)

                    technology_sampled_df = pd.DataFrame()
                    for tech, tech_percentage in zip(["2G", "3G", "4G"], technology_percentages):
                        tech_subset = gender_subset[gender_subset['PROFIL'] == tech]
                        tech_sample_size = int((tech_percentage / 100) * gender_sample_size)

                        offer_sampled_df = pd.DataFrame()
                        for offer, offer_percentage in zip(offers, percentages):
                            offer_subset = tech_subset[tech_subset['OFFRE'] == offer]
                            offer_sample_size = int((offer_percentage / 100) * tech_sample_size)

                            actual_sample = min(offer_sample_size, len(offer_subset))
                            offer_sampled_df = pd.concat(
                                [offer_sampled_df, offer_subset.sample(n=actual_sample, replace=False)]
                            )

                        technology_sampled_df = pd.concat([technology_sampled_df, offer_sampled_df])

                    final_sampled_df = pd.concat([final_sampled_df, technology_sampled_df])

                final_sample_size = len(final_sampled_df)
                if final_sample_size != num_samples:
                    flash(f"Warning: The final sample size ({final_sample_size}) does not match the requested number ({num_samples}).", "warning")

                output_filename = f"sampled_{filename}"
                output_path = os.path.join(OUTPUT_FOLDER, output_filename)
                final_sampled_df.to_excel(output_path, index=False)

                flash("File processed successfully. Download your sampled file below.", "success")
                return render_template("dashboard.html", user=session["user"], file_url=output_filename)
            except Exception as e:
                flash(f"An error occurred: {str(e)}", "error")
                return redirect(request.url)
    return render_template("dashboard.html", user=session["user"])

@app.route("/download/<path:filename>")
def download_file(filename):
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    return send_file(file_path, as_attachment=True)

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
