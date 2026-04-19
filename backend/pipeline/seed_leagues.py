"""
Seed script: populates leagues and teams in the database on first setup.
Run with: python -m pipeline.seed_leagues
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal, create_tables
from app.db.models import League, Team
from app.core.logging import logger

LEAGUES = [
    {
        "slug": "epl",
        "name": "English Premier League",
        "country": "England",
        "fbref_id": "9",
        "understat_name": "EPL",
        "teams": [
            {"name": "Arsenal",            "short": "ARS", "lat": 51.5549, "lon": -0.1084, "cap": 60704},
            {"name": "Aston Villa",        "short": "AVL", "lat": 52.5090, "lon": -1.8847, "cap": 42785},
            {"name": "Bournemouth",        "short": "BOU", "lat": 50.7352, "lon": -1.8382, "cap": 11307},
            {"name": "Brentford",          "short": "BRE", "lat": 51.4882, "lon": -0.2887, "cap": 17250},
            {"name": "Brighton",           "short": "BHA", "lat": 50.8619, "lon": -0.0837, "cap": 31876},
            {"name": "Chelsea",            "short": "CHE", "lat": 51.4816, "lon": -0.1909, "cap": 40341},
            {"name": "Crystal Palace",     "short": "CRY", "lat": 51.3983, "lon": -0.0855, "cap": 25456},
            {"name": "Everton",            "short": "EVE", "lat": 53.4388, "lon": -2.9664, "cap": 39414},
            {"name": "Fulham",             "short": "FUL", "lat": 51.4749, "lon": -0.2217, "cap": 25700},
            {"name": "Ipswich Town",       "short": "IPS", "lat": 52.0544, "lon": 1.1450,  "cap": 29007},
            {"name": "Leicester City",     "short": "LEI", "lat": 52.6204, "lon": -1.1420, "cap": 32273},
            {"name": "Liverpool",          "short": "LIV", "lat": 53.4308, "lon": -2.9608, "cap": 61276},
            {"name": "Manchester City",    "short": "MCI", "lat": 53.4831, "lon": -2.2004, "cap": 53400},
            {"name": "Manchester United",  "short": "MUN", "lat": 53.4631, "lon": -2.2913, "cap": 74310},
            {"name": "Newcastle United",   "short": "NEW", "lat": 54.9756, "lon": -1.6218, "cap": 52305},
            {"name": "Nottingham Forest",  "short": "NFO", "lat": 52.9399, "lon": -1.1328, "cap": 30445},
            {"name": "Southampton",        "short": "SOU", "lat": 50.9058, "lon": -1.3910, "cap": 32384},
            {"name": "Tottenham Hotspur",  "short": "TOT", "lat": 51.6043, "lon": -0.0665, "cap": 62303},
            {"name": "West Ham United",    "short": "WHU", "lat": 51.5386, "lon": 0.0164,  "cap": 62500},
            {"name": "Wolverhampton",      "short": "WOL", "lat": 52.5901, "lon": -2.1306, "cap": 32050},
        ],
    },
    {
        "slug": "laliga",
        "name": "La Liga",
        "country": "Spain",
        "fbref_id": "12",
        "understat_name": "La_liga",
        "teams": [
            {"name": "Real Madrid",       "short": "RMA", "lat": 40.4531, "lon": -3.6883, "cap": 81044},
            {"name": "Barcelona",         "short": "BAR", "lat": 41.3809, "lon": 2.1228,  "cap": 99354},
            {"name": "Atletico Madrid",   "short": "ATM", "lat": 40.4361, "lon": -3.5996, "cap": 68456},
            {"name": "Sevilla",           "short": "SEV", "lat": 37.3841, "lon": -5.9705, "cap": 43883},
            {"name": "Valencia",          "short": "VAL", "lat": 39.4747, "lon": -0.3584, "cap": 49430},
            {"name": "Real Sociedad",     "short": "RSO", "lat": 43.3014, "lon": -1.9738, "cap": 40000},
            {"name": "Villarreal",        "short": "VIL", "lat": 39.9441, "lon": -0.1043, "cap": 23500},
            {"name": "Athletic Club",     "short": "ATH", "lat": 43.2642, "lon": -2.9490, "cap": 53289},
            {"name": "Real Betis",        "short": "BET", "lat": 37.3567, "lon": -5.9811, "cap": 60720},
            {"name": "Getafe",            "short": "GET", "lat": 40.3248, "lon": -3.7143, "cap": 17000},
            {"name": "Celta Vigo",        "short": "CEL", "lat": 42.2121, "lon": -8.7392, "cap": 31800},
            {"name": "Osasuna",           "short": "OSA", "lat": 42.7964, "lon": -1.6370, "cap": 23576},
            {"name": "Alaves",            "short": "ALA", "lat": 42.8491, "lon": -2.6870, "cap": 19840},
            {"name": "Las Palmas",        "short": "LPA", "lat": 28.1005, "lon": -15.4573,"cap": 32392},
            {"name": "Girona",            "short": "GIR", "lat": 41.9619, "lon": 2.8285,  "cap": 13450},
            {"name": "Rayo Vallecano",    "short": "RAY", "lat": 40.3918, "lon": -3.6567, "cap": 14708},
            {"name": "Espanyol",          "short": "ESP", "lat": 41.3470, "lon": 2.0734,  "cap": 40000},
            {"name": "Valladolid",        "short": "VLL", "lat": 41.6525, "lon": -4.7440, "cap": 26512},
            {"name": "Leganes",           "short": "LEG", "lat": 40.3335, "lon": -3.7627, "cap": 11454},
            {"name": "Mallorca",          "short": "MLL", "lat": 39.5862, "lon": 2.6611,  "cap": 23142},
        ],
    },
    {
        "slug": "seriea",
        "name": "Serie A",
        "country": "Italy",
        "fbref_id": "11",
        "understat_name": "Serie_A",
        "teams": [
            {"name": "Inter Milan",    "short": "INT", "lat": 45.4781, "lon": 9.1240,  "cap": 75923},
            {"name": "AC Milan",       "short": "MIL", "lat": 45.4781, "lon": 9.1240,  "cap": 75923},
            {"name": "Juventus",       "short": "JUV", "lat": 45.1096, "lon": 7.6413,  "cap": 41507},
            {"name": "Napoli",         "short": "NAP", "lat": 40.8279, "lon": 14.1930, "cap": 54726},
            {"name": "AS Roma",        "short": "ROM", "lat": 41.9341, "lon": 12.4548, "cap": 70634},
            {"name": "Lazio",          "short": "LAZ", "lat": 41.9341, "lon": 12.4548, "cap": 70634},
            {"name": "Atalanta",       "short": "ATA", "lat": 45.7093, "lon": 9.6766,  "cap": 21300},
            {"name": "Fiorentina",     "short": "FIO", "lat": 43.7807, "lon": 11.2827, "cap": 43147},
            {"name": "Bologna",        "short": "BOL", "lat": 44.4922, "lon": 11.3130, "cap": 38279},
            {"name": "Torino",         "short": "TOR", "lat": 45.0428, "lon": 7.6502,  "cap": 28177},
            {"name": "Udinese",        "short": "UDI", "lat": 46.0720, "lon": 13.2040, "cap": 25144},
            {"name": "Genoa",          "short": "GEN", "lat": 44.4162, "lon": 8.9520,  "cap": 36685},
            {"name": "Lecce",          "short": "LEC", "lat": 40.3583, "lon": 18.1719, "cap": 33876},
            {"name": "Cagliari",       "short": "CAG", "lat": 39.2063, "lon": 9.1296,  "cap": 16416},
            {"name": "Hellas Verona",  "short": "HEL", "lat": 45.4382, "lon": 10.9745, "cap": 31045},
            {"name": "Empoli",         "short": "EMP", "lat": 43.7250, "lon": 10.9497, "cap": 16284},
            {"name": "Monza",          "short": "MON", "lat": 45.5851, "lon": 9.2744,  "cap": 18568},
            {"name": "Parma",          "short": "PAR", "lat": 44.7922, "lon": 10.4485, "cap": 27906},
            {"name": "Como",           "short": "COM", "lat": 45.8062, "lon": 9.0815,  "cap": 13602},
            {"name": "Venezia",        "short": "VEN", "lat": 45.4394, "lon": 12.3127, "cap": 11150},
        ],
    },
    {
        "slug": "bundesliga",
        "name": "Bundesliga",
        "country": "Germany",
        "fbref_id": "20",
        "understat_name": "Bundesliga",
        "teams": [
            {"name": "Bayern Munich",     "short": "BAY", "lat": 48.2188, "lon": 11.6247, "cap": 75024},
            {"name": "Borussia Dortmund", "short": "BVB", "lat": 51.4926, "lon": 7.4516,  "cap": 81365},
            {"name": "RB Leipzig",        "short": "RBL", "lat": 51.3457, "lon": 12.3479, "cap": 47069},
            {"name": "Bayer Leverkusen",  "short": "B04", "lat": 51.0382, "lon": 7.0022,  "cap": 30210},
            {"name": "Eintracht Frankfurt","short": "SGE", "lat": 50.0685, "lon": 8.6455, "cap": 51500},
            {"name": "VfB Stuttgart",     "short": "STU", "lat": 48.7922, "lon": 9.2324,  "cap": 60441},
            {"name": "SC Freiburg",       "short": "SCF", "lat": 47.9890, "lon": 7.8900,  "cap": 34700},
            {"name": "Union Berlin",      "short": "FCU", "lat": 52.4574, "lon": 13.5672, "cap": 22012},
            {"name": "Werder Bremen",     "short": "SVW", "lat": 53.0662, "lon": 8.8376,  "cap": 42100},
            {"name": "Borussia Mönchengladbach","short": "BMG", "lat": 51.1740, "lon": 6.3851, "cap": 54022},
            {"name": "FC Augsburg",       "short": "FCA", "lat": 48.3233, "lon": 10.8866, "cap": 30660},
            {"name": "Wolfsburg",         "short": "WOB", "lat": 52.4323, "lon": 10.8000, "cap": 30000},
            {"name": "TSG Hoffenheim",    "short": "TSG", "lat": 49.2381, "lon": 8.8887,  "cap": 30150},
            {"name": "Mainz 05",          "short": "M05", "lat": 49.9844, "lon": 8.2237,  "cap": 33305},
            {"name": "Heidenheim",        "short": "HDH", "lat": 48.6756, "lon": 10.1604, "cap": 15000},
            {"name": "St. Pauli",         "short": "STP", "lat": 53.5547, "lon": 9.9680,  "cap": 29546},
            {"name": "Kiel",              "short": "KIE", "lat": 54.3559, "lon": 10.1277, "cap": 15034},
            {"name": "Holstein Kiel",     "short": "HOL", "lat": 54.3559, "lon": 10.1277, "cap": 15034},
        ],
    },
    {
        "slug": "ligue1",
        "name": "Ligue 1",
        "country": "France",
        "fbref_id": "13",
        "understat_name": "Ligue_1",
        "teams": [
            {"name": "Paris Saint-Germain","short": "PSG", "lat": 48.8414, "lon": 2.2530,  "cap": 47929},
            {"name": "Marseille",         "short": "OM",  "lat": 43.2696, "lon": 5.3955,  "cap": 67394},
            {"name": "Lyon",              "short": "OL",  "lat": 45.7653, "lon": 4.9821,  "cap": 59186},
            {"name": "Monaco",            "short": "MON", "lat": 43.7272, "lon": 7.4155,  "cap": 18523},
            {"name": "Lille",             "short": "LIL", "lat": 50.6122, "lon": 3.1302,  "cap": 50186},
            {"name": "Nice",              "short": "NIC", "lat": 43.7056, "lon": 7.1929,  "cap": 35624},
            {"name": "Lens",              "short": "LEN", "lat": 50.4359, "lon": 2.8158,  "cap": 38223},
            {"name": "Rennes",            "short": "REN", "lat": 48.1072, "lon": -1.7122, "cap": 29778},
            {"name": "Montpellier",       "short": "MON", "lat": 43.6224, "lon": 3.8130,  "cap": 32900},
            {"name": "Strasbourg",        "short": "STR", "lat": 48.5602, "lon": 7.7552,  "cap": 29230},
            {"name": "Reims",             "short": "REI", "lat": 49.2451, "lon": 4.0230,  "cap": 21684},
            {"name": "Nantes",            "short": "NAN", "lat": 47.2560, "lon": -1.5254, "cap": 37473},
            {"name": "Toulouse",          "short": "TOU", "lat": 43.5828, "lon": 1.4340,  "cap": 33150},
            {"name": "Brest",             "short": "BRE", "lat": 48.4093, "lon": -4.4778, "cap": 15097},
            {"name": "Le Havre",          "short": "HAV", "lat": 49.5027, "lon": 0.1323,  "cap": 25178},
            {"name": "Auxerre",           "short": "AUX", "lat": 47.7956, "lon": 3.5705,  "cap": 23467},
            {"name": "Saint-Etienne",     "short": "STE", "lat": 45.4608, "lon": 4.3908,  "cap": 41965},
            {"name": "Angers",            "short": "ANG", "lat": 47.4626, "lon": -0.5490, "cap": 18500},
        ],
    },
]


def seed():
    create_tables()
    db = SessionLocal()

    try:
        existing = db.query(League).count()
        if existing > 0:
            logger.info("Leagues already seeded", count=existing)
            db.close()
            return

        for league_data in LEAGUES:
            logger.info("Seeding league", name=league_data["name"])

            league = League(
                slug=league_data["slug"],
                name=league_data["name"],
                country=league_data["country"],
                fbref_id=league_data.get("fbref_id"),
                understat_name=league_data.get("understat_name"),
            )
            db.add(league)
            db.flush()

            for team_data in league_data.get("teams", []):
                team = Team(
                    league_id=league.id,
                    name=team_data["name"],
                    short_name=team_data.get("short"),
                    stadium_lat=team_data.get("lat"),
                    stadium_lon=team_data.get("lon"),
                    stadium_capacity=team_data.get("cap"),
                )
                db.add(team)

        db.commit()
        total_teams = sum(len(l["teams"]) for l in LEAGUES)
        logger.info("Seeding complete", leagues=len(LEAGUES), teams=total_teams)

    except Exception as e:
        db.rollback()
        logger.error("Seeding failed", error=str(e))
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
