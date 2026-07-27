# Kuuma-locaties: Bookeo account/type + metadata voor scraper en Google Sheet.
# a = Bookeo-account, type = product-id per locatie (uit de paginabron gehaald).
import datetime

START = datetime.date(2026, 7, 23)   # eerste dag in de sheet

LOCATIONS = [
    dict(key="ams-bjork", naam="Ams Björk", slug="marineterrein-bjork",
         a="3254A3FXXU175D69E71C5", type="3254PATUWN17B8204191E", maxdrop=6, prijs=17.50,
         eind=datetime.date(2027, 4, 30), we_only=[],
         slots=["07:00","08:30","10:00","11:30","13:00","14:30","16:30","18:00","19:30","21:00","22:30"]),
    dict(key="ams-matsu", naam="Ams Matsu", slug="marineterrein-matsu",
         a="3254A3FXXU175D69E71C5", type="3254X4FRFA191E02B7FD6", maxdrop=8, prijs=17.50,
         eind=datetime.date(2027, 4, 30), we_only=[],
         slots=["06:30","08:00","09:30","11:00","12:30","14:00","16:00","17:30","19:00","20:30","22:00"]),
    dict(key="ams-noord", naam="Ams Noord", slug="boek-sauna-amsterdam-noord",
         a="3254A3FXXU175D69E71C5", type="325467EJPF183698FB466", maxdrop=6, prijs=17.50,
         eind=datetime.date(2026, 12, 31), we_only=["22:45"],
         slots=["07:00","08:30","10:00","11:30","13:00","15:15","16:45","18:15","19:45","21:15","22:45"]),
    dict(key="den-bosch", naam="Den Bosch", slug="kuuma-den-bosch",
         a="32547XC6XX191747C1FE3", type="32549FJM9P199F2A9FD38", maxdrop=7, prijs=17.50,
         eind=datetime.date(2026, 12, 31), we_only=[],
         slots=["07:00","08:30","10:45","12:15","13:45","15:15","16:45","18:15","19:45","21:15"]),
    dict(key="egmond", naam="Egmond aan Zee", slug="boek-sauna-egmond-aan-zee",
         a="3254EHPF3N198F61DFBD6", type="3254XHH93619E97C3F863", maxdrop=10, prijs=17.50,
         eind=datetime.date(2026, 12, 31), we_only=[],
         slots=["07:00","08:30","10:30","12:00","13:30","15:00","17:00","18:30","20:00","21:30"]),
    dict(key="kallumaan", naam="Kallumaan", slug="drop-in-kallumaan",
         a="3254A3FXXU175D69E71C5", type="32546LKUKL1878F1D6984", maxdrop=7, prijs=15.00,
         eind=datetime.date(2026, 9, 30), we_only=[],
         slots=["07:00","09:15","11:30","13:45","16:00","18:15","20:30"]),
    dict(key="nijmegen-lent", naam="Nijmegen Lent", slug="boek-sauna-nijmegen-lent",
         a="32547XC6XX191747C1FE3", type="3254MAC9XU19174D5D1AC", maxdrop=6, prijs=17.50,
         eind=datetime.date(2026, 7, 31), we_only=[],
         slots=["07:00","08:30","10:00","11:30","13:00","14:30","16:00","17:30","19:00","20:30","22:00"]),
    dict(key="nijmegen-nyma", naam="Nijmegen Nyma", slug="kuuma-nyma",
         a="32547XC6XX191747C1FE3", type="32547WAWX619817809442", maxdrop=7, prijs=17.50,
         eind=datetime.date(2026, 11, 1), we_only=[],
         slots=["07:00","08:30","10:00","11:30","13:00","14:30","16:00","17:30","19:00","20:30"]),
    dict(key="rotterdam-delfshaven", naam="Rotterdam Delfshaven", slug="boek-sauna-rotterdam-delfshaven",
         a="32547XC6XX191747C1FE3", type="3254WA9ELT19600DB8361", maxdrop=6, prijs=17.50,
         eind=datetime.date(2027, 4, 30), we_only=[],
         slots=["07:00","08:30","10:00","11:30","13:00","14:30","16:00","17:30","19:00","20:30","22:00"]),
]

def page_url(loc):
    return f"https://kuuma.nl/boek-nu/{loc['slug']}/"
