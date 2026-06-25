import os
from flask import Flask, request, render_template, redirect, url_for, flash
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
    "etappe_gewinner_fahrer": "Etappensieger",
    "etappe_gewinner_team": "Team",
    "gelbes_trikot": "Gelb",
    "gruenes_trikot": "Grün",
    "gepunktetes_trikot": "Berg",
    "weisses_trikot": "Weiß",
    "gesamtsieger_tour": "Gesamt Gelb",
    "gesamtsieger_gruen": "Gesamt Grün",
    "gesamtsieger_gepunktet": "Gesamt Berg",
    "gesamtsieger_weiss": "Gesamt Weiß",
}


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

with app.app_context():
    db.create_all()


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
    if request.method == "POST":
        tipp = request.form.to_dict()

        if tipp.get("tipper") != "Admin" and ist_etappe_gesperrt(tipp.get("etappe")):
            flash("Diese Tipprunde ist bereits gesperrt.", "error")
            return redirect(url_for("tippen"))

        if tipp.get("tipper") == "Admin":
            admin_code = tipp.get("admin_code", "")
            if admin_code != os.environ.get("ADMIN_CODE", "Ulle"):
                flash("Falscher Admin-Code!", "error")
                return redirect(url_for("tippen", tipper="Admin"))

        if tipp.get("tipper") not in TIPPER:
            flash("Ungültiger Tipper!", "error")
            return redirect(url_for("tippen"))

        save_tipp(tipp)
        flash("Tipp erfolgreich gespeichert!", "success")
        return redirect(url_for("index"))

    tipp_auswahl_tipper = request.args.get("tipper")
    tipp_auswahl_etappe = request.args.get("etappe")

    kategorien = ALL_KATEGORIEN if tipp_auswahl_tipper == "Admin" else BASIS_KATEGORIEN

    vorbefuellung = {}
    if tipp_auswahl_tipper and tipp_auswahl_etappe:
        vorhandener_tipp = Tipp.query.filter_by(
            tipper=tipp_auswahl_tipper,
            etappe=tipp_auswahl_etappe
        ).first()

        if vorhandener_tipp:
            vorbefuellung = vorhandener_tipp.daten

        return render_template(
            "tippen.html",
            tipper=TIPPER,
            kategorien=kategorien,
            fahrer_liste=load_fahrer(),
            teams=load_teams(),
            etappen=load_etappen(),
            gesperrte_etappen=[
                e for e in load_etappen()
                if ist_etappe_gesperrt(e)
            ],
            vorbefuellung=vorbefuellung,
            kategorie_labels=KATEGORIE_LABELS
        )

@app.route("/admin", methods=["GET", "POST"])
def admin():
    admin_code = request.values.get("admin_code", "")

    if admin_code != os.environ.get("ADMIN_CODE", "Ulle"):
        if request.method == "POST":
            flash("Falscher Admin-Code!", "error")
        return render_template("admin.html", eingeloggt=False)

    if request.method == "POST":
        etappe = request.form.get("etappe")
        aktion = request.form.get("aktion")

        if etappe and aktion == "sperren":
            setze_etappe_gesperrt(etappe, True)
            flash(f"{etappe} wurde gesperrt.", "success")

        elif etappe and aktion == "entsperren":
            setze_etappe_gesperrt(etappe, False)
            flash(f"{etappe} wurde wieder geöffnet.", "success")

    etappen_status = []
    for etappe in load_etappen():
        etappen_status.append({
            "etappe": etappe,
            "gesperrt": ist_etappe_gesperrt(etappe)
        })

    return render_template(
        "admin.html",
        eingeloggt=True,
        admin_code=admin_code,
        etappen_status=etappen_status
    )

if __name__ == "__main__":
    app.run()
