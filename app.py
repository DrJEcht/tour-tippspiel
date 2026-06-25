import json
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

TIPPER = ["Steffi", "MieseGriese", "vdH", "Günni", "Chapui", "Admin", "Mike"]

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


class Tipp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipper = db.Column(db.String(100), nullable=False)
    etappe = db.Column(db.String(200), nullable=False)
    daten = db.Column(db.JSON, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("tipper", "etappe", name="unique_tipper_etappe"),
    )


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


def load_tipps():
    return [t.daten for t in Tipp.query.all()]


def save_tipp(tipp):
    bestehender_tipp = Tipp.query.filter_by(
        tipper=tipp.get("tipper"),
        etappe=tipp.get("etappe")
    ).first()

    if bestehender_tipp:
        bestehender_tipp.daten = tipp
    else:
        neuer_tipp = Tipp(
            tipper=tipp.get("tipper"),
            etappe=tipp.get("etappe"),
            daten=tipp
        )
        db.session.add(neuer_tipp)

    db.session.commit()


def berechne_rangliste():
    tipps = load_tipps()
    rangliste = {}
    referenz = None

    for tipp in tipps:
        if tipp.get("tipper") == "Admin":
            referenz = tipp
            break

    if not referenz:
        return rangliste

    for tipp in tipps:
        name = tipp.get("tipper")
        if name == "Admin":
            continue

        korrekt = {}
        punkte = 0

        for feld in BASIS_KATEGORIEN:
            tipp_wert = tipp.get(feld, "").strip()
            if not tipp_wert:
                korrekt[feld] = 0
                continue

            platz1 = referenz.get(feld, "").strip()
            platz2 = referenz.get(feld + "_platz2", "").strip()
            platz3 = referenz.get(feld + "_platz3", "").strip()

            punktzahl = 0
            if tipp_wert == platz1 and platz1 != "":
                punktzahl = 3
            elif tipp_wert == platz2 and platz2 != "":
                punktzahl = 2
            elif tipp_wert == platz3 and platz3 != "":
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
            "etappe": tipp.get("etappe"),
            "daten": tipp,
            "korrekt": korrekt
        })

    return rangliste


KATEGORIE_LABELS = {
    "etappe_gewinner_fahrer": "Etappensieger (Fahrer)",
    "etappe_gewinner_team": "Etappensieger (Team)",
    "gelbes_trikot": "Gelbes Trikot",
    "gruenes_trikot": "Grünes Trikot",
    "gepunktetes_trikot": "Gepunktetes Trikot",
    "weisses_trikot": "Weißes Trikot",
    "gesamtsieger_tour": "Gesamtsieger – Gelb",
    "gesamtsieger_gruen": "Gesamtsieger – Grün",
    "gesamtsieger_gepunktet": "Gesamtsieger – Gepunktet",
    "gesamtsieger_weiss": "Gesamtsieger – Weiß",
}


@app.route("/")
def index():
    rangliste_dict = berechne_rangliste()
    rangliste = sorted(
        rangliste_dict.items(),
        key=lambda x: x[1]["gesamtpunkte"],
        reverse=True
    )

    ausgewaehlte_etappe = request.args.get("etappe")
    etappen = load_etappen()

    if not ausgewaehlte_etappe and etappen:
        ausgewaehlte_etappe = etappen[0]

    tipps_etappe = []

    for name, daten in rangliste:
        for tipp in daten["tipps"]:
            if tipp["etappe"] == ausgewaehlte_etappe:
                punkte_summe = sum(tipp["korrekt"].values())
                tipps_etappe.append({
                    "name": name,
                    "daten": tipp["daten"],
                    "korrekt": tipp["korrekt"],
                    "punkte": punkte_summe
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

        if tipp.get("tipper") == "Admin":
            admin_code = tipp.get("admin_code", "")
            if admin_code != "Ulle":
                flash("Falscher Admin-Code!", "error")
                return redirect(url_for("tippen", tipper="Admin"))

        if tipp.get("tipper") not in TIPPER:
            flash("Ungültiger Tipper!", "error")
            return redirect(url_for("tippen"))

        save_tipp(tipp)

        flash("Tipp erfolgreich abgegeben!", "success")
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
        vorbefuellung=vorbefuellung,
        kategorie_labels=KATEGORIE_LABELS
    )


if __name__ == "__main__":
    app.run()
