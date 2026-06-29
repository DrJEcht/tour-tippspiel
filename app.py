import os
from flask import Flask, request, render_template, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "lokaler_test_schluessel")

database_url = os.environ.get("DATABASE_URL", "sqlite:///local.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

DATA_DIR = "data"

TIPPER = ["Steffi", "MieseGriese", "vdH", "Günni", "Chapui", "Admin"]

BASIS_KATEGORIEN = [
    "etappe_gewinner_fahrer",
    "etappe_gewinner_team",
    "gelbes_trikot",
    "gruenes_trikot",
    "gepunktetes_trikot",
    "weisses_trikot",
    "gesamtsieger_tour",
    "gesamtsieger_gruen",
    "gesamtsieger_gepunktet",
    "gesamtsieger_weiss",
]


def get_admin_kategorien():
    kategorien = []
    for k in BASIS_KATEGORIEN:
        kategorien.append(k)
        kategorien.append(k + "_platz2")
        kategorien.append(k + "_platz3")
    return kategorien


ALL_KATEGORIEN = get_admin_kategorien()


KATEGORIE_LABELS = {
    "etappe_gewinner_fahrer": "Welcher Fahrer wird Etappensieger",
    "etappe_gewinner_team": "Welches Team gewinnt die Etappe",
    "gelbes_trikot": "Welcher Fahrer ist nach der Etappe im Gelben Trikot",
    "gruenes_trikot": "Welcher Fahrer ist nach der Etappe im Grünen Trikot",
    "gepunktetes_trikot": "Welcher Fahrer ist nach der Etappe im Polka Dot Trikot",
    "weisses_trikot": "Welcher Fahrer ist nach der Etappe im Weißen Trikot",
    "gesamtsieger_tour": "Welcher Fahrer gewinnt die Gesamtwertung",
    "gesamtsieger_gruen": "Welcher Fahrer gewinnt die Sprint-Gesamtwertung",
    "gesamtsieger_gepunktet": "Welcher Fahrer gewinnt die Berg-Gesamtwertung",
    "gesamtsieger_weiss": "Welcher Fahrer gewinnt die Nachwuchs-Gesamtwertung",
}
class StartseitenInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bild_url = db.Column(db.String(500))
    text = db.Column(db.Text)

class Tipp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipper = db.Column(db.String(100), nullable=False)
    etappe = db.Column(db.String(200), nullable=False)
    daten = db.Column(db.JSON, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("tipper", "etappe", name="unique_tipper_etappe"),
    )

class EtappenStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    etappe = db.Column(db.String(200), unique=True, nullable=False)
    gesperrt = db.Column(db.Boolean, default=False)

class Benutzer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    passwort_hash = db.Column(db.String(255), nullable=False)
    ist_admin = db.Column(db.Boolean, default=False)
    aktiv = db.Column(db.Boolean, default=True)

with app.app_context():
    db.create_all()

with app.app_context():
    if not Benutzer.query.filter_by(name="Admin").first():
        admin = Benutzer(
            name="Admin",
            passwort_hash=generate_password_hash("Ulle"),
            ist_admin=True,
            aktiv=True
        )
        db.session.add(admin)
        db.session.commit()

def read_lines_from_file(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load_fahrer():
    return read_lines_from_file(os.path.join(DATA_DIR, "fahrer.txt"))


def load_teams():
    return read_lines_from_file(os.path.join(DATA_DIR, "teams.txt"))


def load_etappen():
    return read_lines_from_file(os.path.join(DATA_DIR, "etappen.txt"))

def ist_etappe_gesperrt(etappe):
    status = EtappenStatus.query.filter_by(etappe=etappe).first()
    return status.gesperrt if status else False


def setze_etappe_gesperrt(etappe, gesperrt):
    status = EtappenStatus.query.filter_by(etappe=etappe).first()

    if not status:
        status = EtappenStatus(etappe=etappe, gesperrt=gesperrt)
        db.session.add(status)
    else:
        status.gesperrt = gesperrt

    db.session.commit()
    
def load_tipps():
    return [t.daten for t in Tipp.query.all()]


def save_tipp(tipp):
    vorhandener_tipp = Tipp.query.filter_by(
        tipper=tipp.get("tipper"),
        etappe=tipp.get("etappe")
    ).first()

    if vorhandener_tipp:
        vorhandener_tipp.daten = tipp
    else:
        db.session.add(Tipp(
            tipper=tipp.get("tipper"),
            etappe=tipp.get("etappe"),
            daten=tipp
        ))

    db.session.commit()


def berechne_rangliste():
    tipps = load_tipps()
    rangliste = {}
    referenzen = {}

    for tipp in tipps:
        if tipp.get("tipper") == "Admin":
            referenzen[tipp.get("etappe")] = tipp

    for tipp in tipps:
        name = tipp.get("tipper")
        etappe = tipp.get("etappe")

        if name == "Admin":
            continue

        if etappe not in referenzen:
            continue

        referenz = referenzen[etappe]
        korrekt = {}
        punkte = 0

        for feld in BASIS_KATEGORIEN:
            tipp_wert = tipp.get(feld, "").strip()
            platz1 = referenz.get(feld, "").strip()
            platz2 = referenz.get(feld + "_platz2", "").strip()
            platz3 = referenz.get(feld + "_platz3", "").strip()

            punktzahl = 0
            if tipp_wert and tipp_wert == platz1:
                punktzahl = 3
            elif tipp_wert and tipp_wert == platz2:
                punktzahl = 2
            elif tipp_wert and tipp_wert == platz3:
                punktzahl = 1

            korrekt[feld] = punktzahl
            punkte += punktzahl

        if name not in rangliste:
            rangliste[name] = {
                "gesamtpunkte": 0,
                "tipps": []
            }

        rangliste[name]["gesamtpunkte"] += punkte
        rangliste[name]["tipps"].append({
            "etappe": etappe,
            "daten": tipp,
            "korrekt": korrekt,
            "punkte": punkte
        })

    return rangliste


@app.route("/")
def index():
    rangliste_dict = berechne_rangliste()
    rangliste = sorted(
        rangliste_dict.items(),
        key=lambda x: x[1]["gesamtpunkte"],
        reverse=True
    )

    etappen = load_etappen()
    ausgewaehlte_etappe = request.args.get("etappe") or (etappen[0] if etappen else None)

    tipps_etappe = []

    for name, daten in rangliste:
        for tipp in daten["tipps"]:
            if tipp["etappe"] == ausgewaehlte_etappe:
                tipps_etappe.append({
                    "name": name,
                    "daten": tipp["daten"],
                    "korrekt": tipp["korrekt"],
                    "punkte": tipp["punkte"]
                })

    return render_template(
        "index.html",
        rangliste=rangliste,
        kategorien=BASIS_KATEGORIEN,
        etappen=etappen,
        ausgewaehlte_etappe=ausgewaehlte_etappe,
        tipps_etappe=tipps_etappe,
        kategorie_labels=KATEGORIE_LABELS
    )


@app.route("/tippen", methods=["GET", "POST"])
def tippen():
    if "benutzer_id" not in session:
        flash("Bitte melde dich zuerst an.", "error")
        return redirect(url_for("login"))

    benutzer = Benutzer.query.get(session["benutzer_id"])

    if not benutzer or not benutzer.aktiv:
        session.clear()
        flash("Dein Benutzer ist nicht mehr aktiv.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        tipp = request.form.to_dict()
        tipp["tipper"] = benutzer.name

        if not benutzer.ist_admin and ist_etappe_gesperrt(tipp.get("etappe")):
            flash("Diese Tipprunde ist bereits gesperrt.", "error")
            return redirect(url_for("tippen"))

        save_tipp(tipp)
        flash("Tipp erfolgreich gespeichert!", "success")
        return redirect(url_for("index"))

    tipp_auswahl_etappe = request.args.get("etappe")

    kategorien = ALL_KATEGORIEN if benutzer.ist_admin else BASIS_KATEGORIEN

    vorbefuellung = {}
    if tipp_auswahl_etappe:
        vorhandener_tipp = Tipp.query.filter_by(
            tipper=benutzer.name,
            etappe=tipp_auswahl_etappe
        ).first()

        if vorhandener_tipp:
            vorbefuellung = vorhandener_tipp.daten

    etappen = load_etappen()

    return render_template(
        "tippen.html",
        aktueller_benutzer=benutzer,
        kategorien=kategorien,
        fahrer_liste=load_fahrer(),
        teams=load_teams(),
        etappen=etappen,
        gesperrte_etappen=[
            e for e in etappen
            if ist_etappe_gesperrt(e)
        ],
        vorbefuellung=vorbefuellung,
        kategorie_labels=KATEGORIE_LABELS
    )


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("ist_admin"):
        flash("Nur Admins dürfen diese Seite öffnen.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        etappe = request.form.get("etappe")
        aktion = request.form.get("aktion")

        if aktion == "benutzer_anlegen":
            name = request.form.get("name", "").strip()
            passwort = request.form.get("passwort", "").strip()
            ist_admin = request.form.get("ist_admin") == "on"

            if not name or not passwort:
                flash("Name und Passwort sind erforderlich.", "error")

            elif Benutzer.query.filter_by(name=name).first():
                flash("Benutzer existiert bereits.", "error")

            else:
                benutzer = Benutzer(
                    name=name,
                    passwort_hash=generate_password_hash(passwort),
                    ist_admin=ist_admin,
                    aktiv=True
                )
                db.session.add(benutzer)
                db.session.commit()
                flash(f"Benutzer '{name}' wurde angelegt.", "success")

        elif aktion == "benutzer_loeschen":
            benutzer_id = request.form.get("benutzer_id")
            benutzer = Benutzer.query.get(benutzer_id)

            if benutzer:
                db.session.delete(benutzer)
                db.session.commit()
                flash(f"Benutzer '{benutzer.name}' wurde gelöscht.", "success")

        elif aktion == "passwort_setzen":
            benutzer_id = request.form.get("benutzer_id")
            neues_passwort = request.form.get("neues_passwort", "").strip()
            benutzer = Benutzer.query.get(benutzer_id)

            if benutzer and neues_passwort:
                benutzer.passwort_hash = generate_password_hash(neues_passwort)
                db.session.commit()
                flash(f"Passwort von '{benutzer.name}' wurde geändert.", "success")

                elif aktion == "startseite_speichern":
            bild_url = request.form.get("bild_url", "").strip()
            text = request.form.get("text", "").strip()

            info = StartseitenInfo.query.first()
            if not info:
                info = StartseitenInfo()
                db.session.add(info)

            info.bild_url = bild_url
            info.text = text
            db.session.commit()

            flash("Startseiten-Info wurde gespeichert.", "success")
        
        elif aktion == "sperren" and etappe:
            setze_etappe_gesperrt(etappe, True)
            flash(f"{etappe} wurde gesperrt.", "success")

        elif aktion == "entsperren" and etappe:
            setze_etappe_gesperrt(etappe, False)
            flash(f"{etappe} wurde wieder geöffnet.", "success")

        return redirect(url_for("admin"))

    etappen_status = []
    for etappe in load_etappen():
        etappen_status.append({
            "etappe": etappe,
            "gesperrt": ist_etappe_gesperrt(etappe)
        })

    return render_template(
        "admin.html",
        eingeloggt=True,
        etappen_status=etappen_status,
        benutzer=Benutzer.query.order_by(Benutzer.name).all(),
        startseiten_info=StartseitenInfo.query.first()
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        passwort = request.form.get("passwort", "")

        benutzer = Benutzer.query.filter_by(name=name, aktiv=True).first()

        if not benutzer or not check_password_hash(benutzer.passwort_hash, passwort):
            flash("Name oder Passwort ist falsch.", "error")
            return redirect(url_for("login"))

        session["benutzer_id"] = benutzer.id
        session["benutzer_name"] = benutzer.name
        session["ist_admin"] = benutzer.ist_admin

        flash(f"Willkommen, {benutzer.name}!", "success")

        if benutzer.ist_admin:
            return redirect(url_for("admin"))

        return redirect(url_for("tippen"))

    benutzer_liste = Benutzer.query.filter_by(aktiv=True).order_by(Benutzer.name).all()
    return render_template("login.html", benutzer_liste=benutzer_liste)


@app.route("/logout")
def logout():
    session.clear()
    flash("Du wurdest abgemeldet.", "success")
    return redirect(url_for("index"))

@app.route("/admin/tipps", methods=["GET", "POST"])
def admin_tipps():
    if not session.get("ist_admin"):
        flash("Nur Admins dürfen diese Seite öffnen.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        aktion = request.form.get("aktion")

        if aktion == "tipp_loeschen":
            tipp_id = request.form.get("tipp_id")
            tipp = Tipp.query.get(tipp_id)

            if tipp:
                db.session.delete(tipp)
                db.session.commit()
                flash("Tipp wurde gelöscht.", "success")

        return redirect(url_for("admin_tipps"))

    tipps = Tipp.query.order_by(Tipp.etappe, Tipp.tipper).all()

    return render_template(
        "admin_tipps.html",
        tipps=tipps
    )


@app.route("/registrieren", methods=["GET", "POST"])
def registrieren():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        passwort = request.form.get("passwort", "").strip()

        if not name or not passwort:
            flash("Name und Passwort sind erforderlich.", "error")
            return redirect(url_for("registrieren"))

        if Benutzer.query.filter_by(name=name).first():
            flash("Dieser Benutzername ist bereits vergeben.", "error")
            return redirect(url_for("registrieren"))

        benutzer = Benutzer(
            name=name,
            passwort_hash=generate_password_hash(passwort),
            ist_admin=False,
            aktiv=True
        )

        db.session.add(benutzer)
        db.session.commit()

        flash("Benutzer wurde angelegt. Du kannst dich jetzt einloggen.", "success")
        return redirect(url_for("login"))

    return render_template("registrieren.html")


if __name__ == "__main__":
    app.run()
