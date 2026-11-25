
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

app.secret_key = "SB_7xQ9mK2pV8nL5wR4zT6aY1cF"
DATABASE = os.path.join(BASE_DIR, "Smart_Ballot.db")




def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/role")
def role():
    return render_template("role.html")


@app.route("/head-register", methods=["GET", "POST"])
def head_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 6:
            return "Invalid details. Password must have at least 6 characters.", 400

        db = get_db()

        try:
            db.execute(
                "INSERT INTO heads (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password))
            )
            db.commit()
            return "Registration successful!"

        except sqlite3.IntegrityError:
            return "This email is already registered.", 409

        finally:
            db.close()

    return render_template("head_register.html")


@app.route("/head-login", methods=["GET", "POST"])
def head_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        head = db.execute(
            "SELECT * FROM heads WHERE email = ?", (email,)
        ).fetchone()
        db.close()

        if head and check_password_hash(head["password_hash"], password):
            session["head_id"] = head["head_id"]
            session["head_name"] = head["name"]
            return redirect(url_for("head_dashboard"))

        return "Invalid email or password.", 401

    return render_template("head_login.html")


@app.route("/head-dashboard")
def head_dashboard():
    if "head_id" not in session:
        return redirect(url_for("head_login"))

    db = get_db()
    elections = db.execute(
        "SELECT * FROM elections WHERE head_id = ? ORDER BY election_id DESC",
        (session["head_id"],)
    ).fetchall()
    db.close()

    return render_template(
        "head_dashboard.html",
        head_name=session["head_name"],
        elections=elections
    )


@app.route("/create-election", methods=["GET", "POST"])
def create_election():
    if "head_id" not in session:
        return redirect(url_for("head_login"))

    if request.method == "POST":
        election_name = request.form.get("election_name", "").strip()
        election_code = request.form.get("election_code", "").strip()
        purpose = request.form.get("purpose", "").strip()

        if not election_name or not election_code:
            return "Election name and code are required.", 400

        db = get_db()

        try:
            db.execute(
                """INSERT INTO elections
                (head_id, election_name, election_code, purpose)
                VALUES (?, ?, ?, ?)""",
                (session["head_id"], election_name, election_code, purpose)
            )
            db.commit()
            return redirect(url_for("head_dashboard"))

        except sqlite3.IntegrityError:
            return "Election code already exists. Please use a different code.", 409

        finally:
            db.close()

    return render_template("create_election.html")


@app.route("/candidate-register", methods=["GET", "POST"])
def candidate_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        roll_number = request.form.get("roll_number", "").strip()
        election_code = request.form.get("election_code", "").strip()
        password = request.form.get("password", "")

        db = get_db()

        election = db.execute(
            "SELECT election_id FROM elections WHERE election_code = ?",
            (election_code,)
        ).fetchone()

        if election is None:
            db.close()
            return "Invalid election code.", 404

        try:
            db.execute(
                """INSERT INTO candidates
                (election_id, name, roll_number, password_hash)
                VALUES (?, ?, ?, ?)""",
                (election["election_id"], name, roll_number,
                 generate_password_hash(password))
            )
            db.commit()
            return "Candidate registration successful!"

        except sqlite3.IntegrityError:
            return "This roll number is already registered.", 409

        finally:
            db.close()

    return render_template("candidate_register.html")


@app.route("/candidate-login", methods=["GET", "POST"])
def candidate_login():
    if request.method == "POST":
        roll_number = request.form.get("roll_number", "").strip()
        election_code = request.form.get("election_code", "").strip()
        password = request.form.get("password", "")

        db = get_db()

        candidate = db.execute(
            """SELECT candidates.*, elections.election_code
            FROM candidates
            JOIN elections ON candidates.election_id = elections.election_id
            WHERE candidates.roll_number = ?
            AND elections.election_code = ?""",
            (roll_number, election_code)
        ).fetchone()

        db.close()

        if candidate is None:
            return "Candidate not found.", 404

        if not check_password_hash(candidate["password_hash"], password):
            return "Incorrect password.", 401

        if candidate["status"] != "approved":
            return "Your registration is pending approval.", 403

        session["candidate_id"] = candidate["candidate_id"]
        session["candidate_name"] = candidate["name"]

        return redirect(url_for("candidate_dashboard"))

    return render_template("candidate_login.html")


@app.route("/candidate-approval")
def candidate_approval():
    if "head_id" not in session:
        return redirect(url_for("head_login"))

    db = get_db()

    candidates = db.execute(
        """SELECT candidates.candidate_id,
                  candidates.name,
                  candidates.roll_number,
                  candidates.status,
                  elections.election_name
           FROM candidates
           JOIN elections ON candidates.election_id = elections.election_id
           WHERE elections.head_id = ?""",
        (session["head_id"],)
    ).fetchall()

    db.close()

    return render_template(
        "candidate_approval.html",
        candidates=candidates
    )


@app.route("/manage-candidate/<int:candidate_id>", methods=["POST"])
def manage_candidate(candidate_id):
    if "head_id" not in session:
        return redirect(url_for("head_login"))

    action = request.form.get("action")

    if action not in ["approved", "rejected"]:
        return "Invalid action.", 400

    db = get_db()

    result = db.execute(
        """UPDATE candidates
           SET status = ?
           WHERE candidate_id = ?
           AND election_id IN (
               SELECT election_id FROM elections WHERE head_id = ?
           )
           AND status = 'pending'""",
        (action, candidate_id, session["head_id"])
    )

    db.commit()
    db.close()

    if result.rowcount == 0:
        return "Candidate not found or already processed.", 404

    return redirect(url_for("candidate_approval"))


@app.route("/candidate-dashboard")
def candidate_dashboard():
    if "candidate_id" not in session:
        return redirect(url_for("candidate_login"))

    db = get_db()

    candidate = db.execute(
        """SELECT candidates.name,
                  candidates.roll_number,
                  candidates.status,
                  elections.election_name
           FROM candidates
           JOIN elections ON candidates.election_id = elections.election_id
           WHERE candidates.candidate_id = ?""",
        (session["candidate_id"],)
    ).fetchone()

    db.close()

    if candidate is None:
        return "Candidate not found.", 404

    return render_template(
        "candidate_dashboard.html",
        candidate=candidate
    )


@app.route("/voter-register", methods=["GET", "POST"])
def voter_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        roll_number = request.form.get("roll_number", "").strip()
        election_code = request.form.get("election_code", "").strip()
        password = request.form.get("password", "")

        db = get_db()

        election = db.execute(
            "SELECT election_id FROM elections WHERE election_code = ?",
            (election_code,)
        ).fetchone()

        if election is None:
            db.close()
            return "Invalid election code.", 404

        try:
            db.execute(
                """INSERT INTO voters
                (election_id, name, roll_number, password_hash)
                VALUES (?, ?, ?, ?)""",
                (election["election_id"], name, roll_number,
                 generate_password_hash(password))
            )
            db.commit()
            return "Voter registration successful!"

        except sqlite3.IntegrityError:
            return "This roll number is already registered.", 409

        finally:
            db.close()

    return render_template("voter_register.html")


@app.route("/voter-login", methods=["GET", "POST"])
def voter_login():
    if request.method == "POST":
        roll_number = request.form.get("roll_number", "").strip()
        election_code = request.form.get("election_code", "").strip()
        password = request.form.get("password", "")

        db = get_db()

        voter = db.execute(
            """SELECT voters.*, elections.election_name,
                      elections.election_code
               FROM voters
               JOIN elections ON voters.election_id = elections.election_id
               WHERE voters.roll_number = ?
               AND elections.election_code = ?""",
            (roll_number, election_code)
        ).fetchone()

        db.close()

        if voter is None:
            return "Voter not found.", 404

        if not check_password_hash(voter["password_hash"], password):
            return "Incorrect password.", 401

        session["voter_id"] = voter["voter_id"]
        session["voter_name"] = voter["name"]
        session["voter_election_id"] = voter["election_id"]

        return redirect(url_for("voter_dashboard"))

    return render_template("voter_login.html")


@app.route("/voter-dashboard")
def voter_dashboard():
    if "voter_id" not in session:
        return redirect(url_for("voter_login"))

    db = get_db()

    voter = db.execute(
        """SELECT voters.name, voters.roll_number,
                  elections.election_name, elections.election_id
           FROM voters
           JOIN elections
           ON voters.election_id = elections.election_id
           WHERE voters.voter_id = ?""",
        (session["voter_id"],)
    ).fetchone()

    if voter is None:
        db.close()
        return "Voter not found.", 404

    candidates = db.execute(
        """SELECT candidate_id, name
           FROM candidates
           WHERE election_id = ?
           AND status = 'approved'""",
        (voter["election_id"],)
    ).fetchall()

    existing_vote = db.execute(
        """SELECT vote_id FROM votes
           WHERE election_id = ? AND voter_id = ?""",
        (voter["election_id"], session["voter_id"])
    ).fetchone()

    db.close()

    return render_template(
        "voter_dashboard.html",
        voter=voter,
        candidates=candidates,
        has_voted=existing_vote is not None,
        voted=request.args.get("voted") == "1"
    )


@app.route("/cast-vote", methods=["POST"])
def cast_vote():
    if "voter_id" not in session:
        return redirect(url_for("voter_login"))

    candidate_id = request.form.get("candidate_id")

    if not candidate_id:
        return "Please select a candidate.", 400

    db = get_db()

    voter = db.execute(
        "SELECT election_id FROM voters WHERE voter_id = ?",
        (session["voter_id"],)
    ).fetchone()

    if voter is None:
        db.close()
        return "Voter not found.", 404

    candidate = db.execute(
        """SELECT candidate_id FROM candidates
           WHERE candidate_id = ?
           AND election_id = ?
           AND status = 'approved'""",
        (candidate_id, voter["election_id"])
    ).fetchone()

    if candidate is None:
        db.close()
        return "Invalid candidate selection.", 400

    try:
        db.execute(
            """INSERT INTO votes
               (election_id, voter_id, candidate_id)
               VALUES (?, ?, ?)""",
            (voter["election_id"], session["voter_id"], candidate_id)
        )
        db.commit()
        return redirect(url_for("voter_dashboard", voted="1"))

    except sqlite3.IntegrityError:
        return "You have already voted in this election.", 409

    finally:
        db.close()


@app.route("/results")
def results():
    if "voter_election_id" not in session:
        return redirect(url_for("voter_login"))

    election_id = session["voter_election_id"]

    db = get_db()

    election = db.execute(
        "SELECT * FROM elections WHERE election_id = ?",
        (election_id,)
    ).fetchone()

    candidates = db.execute(
        """SELECT candidates.name,
                  candidates.roll_number,
                  COUNT(votes.vote_id) AS total_votes
           FROM candidates
           LEFT JOIN votes
           ON candidates.candidate_id = votes.candidate_id
           WHERE candidates.election_id = ?
           AND candidates.status = 'approved'
           GROUP BY candidates.candidate_id
           ORDER BY total_votes DESC""",
        (election_id,)
    ).fetchall()

    db.close()

    if election is None:
        return "Election not found.", 404

    return render_template(
        "results.html",
        election=election,
        candidates=candidates
    )


@app.route("/statistics")
def statistics():
    if "head_id" not in session:
        return redirect(url_for("head_login"))

    db = get_db()

    # Get only elections belonging to the logged-in Head
    elections = db.execute(
        """SELECT election_id, election_name
           FROM elections
           WHERE head_id = ?
           ORDER BY election_id DESC""",
        (session["head_id"],)
    ).fetchall()

    selected_id = request.args.get("election_id")

    if selected_id:
        try:
            selected_id = int(selected_id)
        except ValueError:
            db.close()
            return "Invalid election selection.", 400

        election = db.execute(
            """SELECT * FROM elections
               WHERE election_id = ? AND head_id = ?""",
            (selected_id, session["head_id"])
        ).fetchone()
    else:
        election = db.execute(
            """SELECT * FROM elections
               WHERE head_id = ?
               ORDER BY election_id DESC
               LIMIT 1""",
            (session["head_id"],)
        ).fetchone()

    if election is None:
        db.close()
        return render_template(
            "statistics.html",
            elections=elections,
            election=None,
            total_voters=0,
            votes_cast=0,
            not_voted=0,
            candidate_labels=[],
            candidate_votes=[]
        )

    election_id = election["election_id"]

    # Count actual registered voters
    total_voters = db.execute(
        """SELECT COUNT(*) AS total
           FROM voters
           WHERE election_id = ?""",
        (election_id,)
    ).fetchone()["total"]

    # Count actual votes cast
    votes_cast = db.execute(
        """SELECT COUNT(*) AS total
           FROM votes
           WHERE election_id = ?""",
        (election_id,)
    ).fetchone()["total"]

    not_voted = max(total_voters - votes_cast, 0)

    # Get actual votes for each approved candidate
    candidate_data = db.execute(
        """SELECT candidates.name,
                  COUNT(votes.vote_id) AS total_votes
           FROM candidates
           LEFT JOIN votes
             ON candidates.candidate_id = votes.candidate_id
             AND votes.election_id = candidates.election_id
           WHERE candidates.election_id = ?
             AND candidates.status = 'approved'
           GROUP BY candidates.candidate_id, candidates.name
           ORDER BY total_votes DESC, candidates.name""",
        (election_id,)
    ).fetchall()

    db.close()

    candidate_labels = [row["name"] for row in candidate_data]
    candidate_votes = [row["total_votes"] for row in candidate_data]

    return render_template(
        "statistics.html",
        elections=elections,
        election=election,
        total_voters=total_voters,
        votes_cast=votes_cast,
        not_voted=not_voted,
        candidate_labels=candidate_labels,
        candidate_votes=candidate_votes
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/head-candidates")
def head_candidates():
    if "head_id" not in session:
        return redirect(url_for("head_login"))

    db = get_db()
    candidates = db.execute("""
        SELECT candidates.name, candidates.roll_number,
               candidates.status, elections.election_name
        FROM candidates
        JOIN elections ON candidates.election_id = elections.election_id
        WHERE elections.head_id = ?
        ORDER BY elections.election_id, candidates.name
    """, (session["head_id"],)).fetchall()
    db.close()

    return render_template("people_list.html",
                           title="All Candidates",
                           people=candidates,
                           role="candidate")


@app.route("/head-voters")
def head_voters():
    if "head_id" not in session:
        return redirect(url_for("head_login"))

    db = get_db()
    voters = db.execute("""
        SELECT voters.name, voters.roll_number,
               elections.election_name
        FROM voters
        JOIN elections ON voters.election_id = elections.election_id
        WHERE elections.head_id = ?
        ORDER BY elections.election_id, voters.name
    """, (session["head_id"],)).fetchall()
    db.close()

    return render_template("people_list.html",
                           title="All Voters",
                           people=voters,
                           role="voter")


@app.route("/candidate-candidates")
def candidate_candidates():
    if "candidate_id" not in session:
        return redirect(url_for("candidate_login"))

    db = get_db()
    candidate = db.execute(
        "SELECT election_id FROM candidates WHERE candidate_id = ?",
        (session["candidate_id"],)
    ).fetchone()

    if candidate is None:
        db.close()
        return "Candidate not found.", 404

    people = db.execute("""
        SELECT name, roll_number, status
        FROM candidates
        WHERE election_id = ?
        ORDER BY name
    """, (candidate["election_id"],)).fetchall()
    db.close()

    return render_template("people_list.html",
                           title="All Candidates in Your Election",
                           people=people,
                           role="candidate")


@app.route("/candidate-voters")
def candidate_voters():
    if "candidate_id" not in session:
        return redirect(url_for("candidate_login"))

    db = get_db()
    candidate = db.execute(
        "SELECT election_id FROM candidates WHERE candidate_id = ?",
        (session["candidate_id"],)
    ).fetchone()

    if candidate is None:
        db.close()
        return "Candidate not found.", 404

    people = db.execute("""
        SELECT name, roll_number
        FROM voters
        WHERE election_id = ?
        ORDER BY name
    """, (candidate["election_id"],)).fetchall()
    db.close()

    return render_template("people_list.html",
                           title="All Voters in Your Election",
                           people=people,
                           role="voter")


@app.route("/voter-candidates")
def voter_candidates():
    if "voter_id" not in session:
        return redirect(url_for("voter_login"))

    db = get_db()
    voter = db.execute(
        "SELECT election_id FROM voters WHERE voter_id = ?",
        (session["voter_id"],)
    ).fetchone()

    if voter is None:
        db.close()
        return "Voter not found.", 404

    people = db.execute("""
        SELECT name, roll_number, status
        FROM candidates
        WHERE election_id = ? AND status = 'approved'
        ORDER BY name
    """, (voter["election_id"],)).fetchall()
    db.close()

    return render_template("people_list.html",
                           title="Candidates in Your Election",
                           people=people,
                           role="candidate")


@app.route("/voter-voters")
def voter_voters():
    if "voter_id" not in session:
        return redirect(url_for("voter_login"))

    db = get_db()
    voter = db.execute(
        "SELECT election_id FROM voters WHERE voter_id = ?",
        (session["voter_id"],)
    ).fetchone()

    if voter is None:
        db.close()
        return "Voter not found.", 404

    people = db.execute("""
        SELECT name, roll_number
        FROM voters
        WHERE election_id = ?
        ORDER BY name
    """, (voter["election_id"],)).fetchall()
    db.close()

    return render_template("people_list.html",
                           title="Voters in Your Election",
                           people=people,
                           role="voter")



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False, use_reloader=False)

