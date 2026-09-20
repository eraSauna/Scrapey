"""Stabiele Kuuma-locatiecodes voor historische continuïteit.

Capaciteit, prijs en tijdsloten komen live uit Periode. Deze lijst koppelt de
Periode-identiteit aan de bestaande keys in Supabase. Toekomstige onbekende
sauna's krijgen automatisch een key in ``periode.py``.
"""

LOCATIONS = [
    dict(key="ams-bjork", naam="Ams Björk", periode_location_id="amsterdam-marineterrein",
         periode_sauna_name="Björk", periode_service_id="uDw4a2pDUAyQ3XXonN2o"),
    dict(key="ams-matsu", naam="Ams Matsu", periode_location_id="amsterdam-marineterrein",
         periode_sauna_name="Matsu", periode_service_id="G7yzdhmpEiaM1yWCPCc0"),
    dict(key="ams-noord", naam="Ams Noord", periode_location_id="amsterdam-noord",
         periode_sauna_name="Amsterdam Noord", periode_service_id="ZKtSDPE2CNDgrjRi39ZM"),
    dict(key="den-bosch", naam="Den Bosch", periode_location_id="den-bosch",
         periode_sauna_name="Den Bosch", periode_service_id="2KC4CrIgY5Twam05fjEr"),
    dict(key="egmond", naam="Egmond aan Zee", periode_location_id="egmond-aan-zee",
         periode_sauna_name="Egmond aan Zee", periode_service_id="cSiOCBqe8ETkZgvyTmIl"),
    dict(key="kallumaan", naam="Kallumaan", periode_location_id="kallumaan",
         periode_sauna_name="Kallumaan", periode_service_id="TzAhXeq4O9FKYJwZS02s"),
    dict(key="nijmegen-lent", naam="Nijmegen Lent", periode_location_id="nijmegen-lent",
         periode_sauna_name="Nijmegen Lent", periode_service_id="JggN0BBfFl24F3WRHeRn"),
    dict(key="nijmegen-nyma", naam="Nijmegen Nyma", periode_location_id="nijmegen-nyma",
         periode_sauna_name="Nijmegen NYMA", periode_service_id="Bu9WNfv2cyfImPufbULw"),
    dict(key="rotterdam-delfshaven", naam="Rotterdam Delfshaven",
         periode_location_id="rotterdam-delfshaven", periode_sauna_name="Rotterdam Delfshaven",
         periode_service_id="Pqc1jrrRSP3gIe1Vxn6R"),
    dict(key="amsterdam-aan-t-ij", naam="Amsterdam Aan 't IJ",
         periode_location_id="amsterdam-aan-t-ij", periode_sauna_name="Amsterdam Aan 't IJ",
         periode_service_id="7fC6AcqCG9i1q9sYLExl"),
]

BY_SERVICE_ID = {loc["periode_service_id"]: loc for loc in LOCATIONS}
BY_LOCATION_AND_NAME = {
    (loc["periode_location_id"], loc["periode_sauna_name"].casefold()): loc
    for loc in LOCATIONS
}


def page_url(loc):
    """Compatibiliteit voor de bewaarde Bookeo-module die Billies helpers levert."""
    slug = loc.get("slug") or loc.get("periode_location_id") or loc["key"]
    return f"https://kuuma.nl/boek-nu/{slug}/"
