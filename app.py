import json
import os
from flask import Flask, request, render_template, redirect, url_for, flash
from filelock import FileLock

app = Flask(__name__)
app.secret_key = 'dein_geheimer_schluessel'

DATA_DIR = 'data'
TIPPS_FILE = os.path.join(DATA_DIR, 'tipps.json')
TIPPS_LOCK = TIPPS_FILE + '.lock'

TIPPER = ['Steffi', 'MieseGriese', 'vdH', 'Günni', 'Chapui', 'Admin']

BASIS_KATEGORIEN = [
    'etappe_gewinner_fahrer',
    'etappe_gewinner_team',
    'gelbes_trikot',
    'gruenes_trikot',
    'gepunktetes_trikot',
    'weisses_trikot',
    'gesamtsieger_tour',
    'gesamtsieger_gruen',
    'gesamtsieger_gepunktet',
    'gesamtsieger_weiss'
]

# Alle Kategorien für Admin (inkl. 2. und 3. Plätze)
def get_admin_kategorien():
    kategorien = []
    for k in BASIS_KATEGORIEN:
        kategorien.append(k)
        kategorien.append(k + '_platz2')
        kategorien.append(k + '_platz3')
    return kategorien

ALL_KATEGORIEN = get_admin_kategorien()

def read_lines_from_file(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def load_fahrer():
    return read_lines_from_file(os.path.join(DATA_DIR, 'fahrer.txt'))

def load_teams():
    return read_lines_from_file(os.path.join(DATA_DIR, 'teams.txt'))

def load_etappen():
    return read_lines_from_file(os.path.join(DATA_DIR, 'etappen.txt'))

def load_tipps():
    if not os.path.exists(TIPPS_FILE):
        return []
    with open(TIPPS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_tipps(tipps):
    os.makedirs(DATA_DIR, exist_ok=True)
    lock = FileLock(TIPPS_LOCK)
    with lock:
        with open(TIPPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(tipps, f, ensure_ascii=False, indent=2)

def normalize(text):
    if not text:
        return ''
    return text.strip().lower().replace('–', '-').replace('—', '-')

def berechne_rangliste():
    tipps = load_tipps()
    rangliste = {}
    referenz = None

    # Admin-Tipp als Referenz für korrekte Ergebnisse holen
    for tipp in tipps:
        if tipp.get('tipper') == 'Admin':
            referenz = tipp
            break

    if not referenz:
        print("Kein Admin-Tipp gefunden!")
        return rangliste

    for tipp in tipps:
        name = tipp.get('tipper')
        if name == 'Admin':
            continue

        korrekt = {}
        punkte = 0

        for feld in BASIS_KATEGORIEN:
            tipp_wert = tipp.get(feld, '').strip()
            if not tipp_wert:
                # Tipp leer, keine Punkte
                korrekt[feld] = 0
                continue

            platz1 = referenz.get(feld, '').strip()
            platz2 = referenz.get(feld + '_platz2', '').strip()
            platz3 = referenz.get(feld + '_platz3', '').strip()

            punktzahl = 0
            if tipp_wert == platz1 and platz1 != '':
                punktzahl = 3
            elif tipp_wert == platz2 and platz2 != '':
                punktzahl = 2
            elif tipp_wert == platz3 and platz3 != '':
                punktzahl = 1

            korrekt[feld] = punktzahl
            punkte += punktzahl

        if name not in rangliste:
            rangliste[name] = {
                'gesamtpunkte': 0,
                'tipps': []
            }

        rangliste[name]['gesamtpunkte'] += punkte
        rangliste[name]['tipps'].append({
            'etappe': tipp.get('etappe'),
            'daten': tipp,
            'korrekt': korrekt
        })

    return rangliste

KATEGORIE_LABELS = {
    'etappe_gewinner_fahrer': 'Etappensieger (Fahrer)',
    'etappe_gewinner_team': 'Etappensieger (Team)',
    'gelbes_trikot': 'Gelbes Trikot',
    'gruenes_trikot': 'Grünes Trikot',
    'gepunktetes_trikot': 'Gepunktetes Trikot',
    'weisses_trikot': 'Weißes Trikot',
    'gesamtsieger_tour': 'Gesamtsieger – Gelb',
    'gesamtsieger_gruen': 'Gesamtsieger – Grün',
    'gesamtsieger_gepunktet': 'Gesamtsieger – Gepunktet',
    'gesamtsieger_weiss': 'Gesamtsieger – Weiß'
}

@app.route('/')
def index():
    rangliste_dict = berechne_rangliste()
    rangliste = sorted(rangliste_dict.items(), key=lambda x: x[1]['gesamtpunkte'], reverse=True)
    return render_template('index.html', rangliste=rangliste, kategorien=BASIS_KATEGORIEN)

@app.route('/tippen', methods=['GET', 'POST'])
def tippen():
    
    
    

    if request.method == 'POST':
        tipp = request.form.to_dict()

        # Einfaches Passwort prüfen, nur wenn Admin tippt
        if tipp.get('tipper') == 'Admin':
            admin_code = tipp.get('admin_code', '')
            if admin_code != 'Ulle':
                flash('Falscher Admin-Code!', 'error')
                return redirect(url_for('tippen', tipper='Admin'))

        if tipp.get('tipper') not in TIPPER:
            flash('Ungültiger Tipper!', 'error')
            return redirect(url_for('tippen'))
    


        tipps = load_tipps()

        # Prüfen, ob Tipper + Etappe bereits existiert, dann überschreiben:
        bestehender_tipp_index = next((i for i, tp in enumerate(tipps)
                                      if tp.get('tipper') == tipp.get('tipper') and tp.get('etappe') == tipp.get('etappe')), None)
        if bestehender_tipp_index is not None:
            tipps[bestehender_tipp_index] = tipp
        else:
            tipps.append(tipp)

        save_tipps(tipps)
        flash('Tipp erfolgreich abgegeben!', 'success')
        return redirect(url_for('index'))

    # GET
    tipp_auswahl_tipper = request.args.get('tipper')
    tipp_auswahl_etappe = request.args.get('etappe')

    # Für Admin alle Kategorien, sonst nur Basis
    kategorien = ALL_KATEGORIEN if tipp_auswahl_tipper == 'Admin' else BASIS_KATEGORIEN

    # Vorbefüllung falls Tipp vorhanden
    vorbefuellung = {}
    if tipp_auswahl_tipper and tipp_auswahl_etappe:
        tipps = load_tipps()
        for t in tipps:
            if t.get('tipper') == tipp_auswahl_tipper and t.get('etappe') == tipp_auswahl_etappe:
                vorbefuellung = t
                break

    return render_template(
        'tippen.html',
        tipper=TIPPER,
        kategorien=kategorien,
        fahrer_liste=load_fahrer(),
        teams=load_teams(),
        etappen=load_etappen(),
        vorbefuellung=vorbefuellung,
        kategorie_labels=KATEGORIE_LABELS
    )

if __name__ == '__main__':
    app.run(debug=True)
