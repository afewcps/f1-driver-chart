import streamlit as st
import requests
import json
import datetime
import pandas as pd

# Streamlit app title and description
st.title("F1 Constructors Championship Notion Updater")
st.write("This app updates the Formula 1 Constructors Championship data in a Notion database.")

# Notion API Konfiguration
NOTION_TOKEN = "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"
NOTION_PARENT_PAGE_ID = "1e26839379ed80edbd00df2aaf120777"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Rennorte 2025
RACE_LOCATIONS = [
    "Australia", "China", "Japan", "Bahrain", "Saudi Arabia", "Miami",
    "Emilia-Romagna", "Monaco", "Spain", "Canada", "Austria", "Great Britain",
    "Belgium", "Hungary", "Netherlands", "Italy", "Azerbaijan", "Singapore",
    "United States", "Mexico", "Brazil", "Las Vegas", "Qatar", "Abu Dhabi"
]

# Teams
TEAMS = [
    "McLaren", "Red Bull", "Mercedes", "Williams", "Aston Martin",
    "Sauber", "Ferrari", "Alpine F1 Team", "RB F1 Team", "Haas F1 Team"
]

BASE_URL = "http://api.jolpi.ca/ergast/f1/current/"

def check_if_race_happened(round_num):
    """Überprüft, ob ein Rennen bereits stattgefunden hat"""
    url = f"{BASE_URL}{round_num}/results.json"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        races = data['MRData']['RaceTable'].get('Races', [])
        if races:
            # Wenn Ergebnisse vorhanden sind, wurde das Rennen gefahren
            return True
    
    return False

def get_sprint_points(round_num):
    url = f"{BASE_URL}{round_num}/sprint.json"
    response = requests.get(url)
    points = {}
    if response.status_code == 200:
        data = response.json()
        races = data['MRData']['RaceTable']['Races']
        if races:
            for result in races[0]['SprintResults']:
                team = result['Constructor']['name']
                team_points = float(result['points'])
                points[team] = points.get(team, 0) + int(team_points)
    return points

def get_weekend_points():
    weekend_points = {team: [0] * len(RACE_LOCATIONS) for team in TEAMS}
    race_happened = [False] * len(RACE_LOCATIONS)  # Speichert, ob ein Rennen bereits stattgefunden hat

    for round_num in range(1, len(RACE_LOCATIONS) + 1):
        if check_if_race_happened(round_num):
            race_happened[round_num - 1] = True
            url = f"{BASE_URL}{round_num}/results.json"
            response = requests.get(url)

            if response.status_code == 200:
                data = response.json()
                races = data['MRData']['RaceTable']['Races']
                current_points = {team: 0 for team in TEAMS}
                sprint_points = get_sprint_points(round_num)

                if races:
                    for result in races[0]['Results']:
                        team = result['Constructor']['name']
                        if team in current_points:
                            current_points[team] += int(float(result['points']))

                    for team in sprint_points:
                        if team in current_points:
                            current_points[team] += sprint_points[team]

                    for team in weekend_points:
                        weekend_points[team][round_num - 1] = current_points.get(team, 0)

    return weekend_points, race_happened

def get_cumulative_standings(weekend_points, race_happened):
    cumulative = {team: [0] * len(RACE_LOCATIONS) for team in weekend_points}
    total_points = {team: 0 for team in weekend_points}

    for race_index in range(len(RACE_LOCATIONS)):
        if race_happened[race_index]:  # Nur Berechnungen durchführen, wenn das Rennen stattgefunden hat
            for team in weekend_points:
                total_points[team] += weekend_points[team][race_index]
                cumulative[team][race_index] = total_points[team]

    return cumulative, total_points

def find_database_id(database_title):
    url = "https://api.notion.com/v1/search"
    payload = {
        "query": database_title,
        "filter": {
            "value": "database",
            "property": "object"
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        results = response.json().get("results", [])
        for db in results:
            if db["object"] == "database" and db["title"][0]["text"]["content"] == database_title:
                st.info(f"🔎 Gefundene bestehende Datenbank: {database_title}")
                return db["id"]
    st.warning(f"⚠️ Keine bestehende Datenbank gefunden: {database_title}")
    return None

def create_database(title, include_total):
    url = "https://api.notion.com/v1/databases"

    properties = {
        "Constructor": {"title": {}}
    }

    for race in RACE_LOCATIONS:
        properties[race] = {"number": {}}

    if include_total:
        properties["Total"] = {"number": {}}

    payload = {
        "parent": {"type": "page_id", "page_id": NOTION_PARENT_PAGE_ID},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
        "is_inline": False
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        db_id = response.json()["id"]
        st.success(f"✅ Neue Datenbank erstellt: {title}")
        return db_id
    else:
        st.error(f"❌ Fehler beim Erstellen der Datenbank '{title}': {response.status_code}")
        st.error(response.text)
        return None

def add_entries_championship(database_id, weekend_points, total_points, race_happened):
    url = "https://api.notion.com/v1/pages"
    
    # Zuerst alle vorhandenen Einträge in der Datenbank löschen/archivieren
    clean_database(database_id)
    
    for team in TEAMS:
        properties = {
            "Constructor": {"title": [{"text": {"content": team}}]},
            "Total": {"number": total_points[team]}
        }

        for i, race in enumerate(RACE_LOCATIONS):
            if race_happened[i]:  # Nur Werte eintragen, wenn das Rennen stattgefunden hat
                if weekend_points[team][i] > 0:
                    properties[race] = {"number": weekend_points[team][i]}
                else:
                    properties[race] = {"number": 0}
            # Wenn das Rennen nicht stattgefunden hat, lassen wir das Feld leer

        payload = {
            "parent": {"database_id": database_id},
            "properties": properties
        }

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            st.error(f"❌ Fehler beim Einfügen von {team} in Constructors Championship: {response.status_code}")
            st.error(response.text)

def clean_database(database_id):
    """Löscht alle vorhandenen Einträge in einer Datenbank"""
    query_url = f"https://api.notion.com/v1/databases/{database_id}/query"
    response = requests.post(query_url, headers=headers)
    
    if response.status_code == 200:
        results = response.json().get("results", [])
        for page in results:
            page_id = page["id"]
            update_url = f"https://api.notion.com/v1/pages/{page_id}"
            archive_payload = {"archived": True}
            requests.patch(update_url, headers=headers, json=archive_payload)
        st.info(f"🗑️ {len(results)} Einträge aus der Datenbank entfernt")
    else:
        st.error(f"❌ Fehler beim Abfragen der Datenbank: {response.status_code}")

def update_constructors_championship():
    with st.spinner("🔄 Lade aktuelle Punkte..."):
        weekend_points, race_happened = get_weekend_points()
        cumulative, total_points = get_cumulative_standings(weekend_points, race_happened)

        # Constructors Championship
        db_championship = find_database_id("Constructors Championship")
        if not db_championship:
            db_championship = create_database("Constructors Championship", include_total=True)
        if db_championship:
            with st.spinner("➕ Füge Teams hinzu (Championship)..."):
                add_entries_championship(db_championship, weekend_points, total_points, race_happened)

        st.success("✅ Fertig! Konstrukteurswertung wurde in Notion aktualisiert.")
        
        # Display the updated standings in the app
        st.subheader("Aktuelle Konstrukteurswertung:")
        
        # Create a dataframe to display
        constructor_data = []
        
        # Sort teams by total points
        sorted_teams = sorted(TEAMS, key=lambda x: total_points[x], reverse=True)
        
        for team in sorted_teams:
            constructor_data.append({
                "Konstrukteur": team,
                "Gesamtpunkte": total_points[team]
            })
        
        if constructor_data:
            df = pd.DataFrame(constructor_data)
            st.dataframe(df)

# Add a button to trigger the update
if st.button("Konstrukteurswertung aktualisieren"):
    update_constructors_championship()
