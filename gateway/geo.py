"""Where a request came from — as far as an address can honestly say.

Three sources, in this order, and every answer says which one it used:

1. **Known networks** the company names itself (Settings → Known networks): "Swangz office", "Staff VPN".
   An address inside one is labelled with that name; it is the company's own definition, not a guess.
2. **The address type**, from the address alone: this computer, a private network, a carrier's shared
   address (100.64.0.0/10), or the public internet.
3. **An offline GeoIP table** for public addresses, imported from a CSV file the admin downloads (DB-IP
   Lite, IP2Location LITE, or any "start,end,country,region,city" file) with
   `python3 -m gateway geoip-import FILE --source "DB-IP Lite 2026-10"`. Results are always labelled
   *approximate*: an address locates the internet provider's equipment, often a city away, never a
   building. Nothing is sent to an online lookup service.

The gateway binds one database at start-up (`bind`); lookups are cached in memory and the cache is
dropped whenever networks or the GeoIP table change.
"""

import csv
import ipaddress
import threading
import time

COUNTRIES = dict(pair.split(":", 1) for pair in (
    "AD:Andorra|AE:United Arab Emirates|AF:Afghanistan|AG:Antigua and Barbuda|AL:Albania|AM:Armenia|AO:Angola|AR:Argentina|"
    "AT:Austria|AU:Australia|AZ:Azerbaijan|BA:Bosnia and Herzegovina|BB:Barbados|BD:Bangladesh|BE:Belgium|BF:Burkina Faso|"
    "BG:Bulgaria|BH:Bahrain|BI:Burundi|BJ:Benin|BN:Brunei|BO:Bolivia|BR:Brazil|BS:Bahamas|BT:Bhutan|BW:Botswana|BY:Belarus|"
    "BZ:Belize|CA:Canada|CD:DR Congo|CF:Central African Republic|CG:Congo|CH:Switzerland|CI:Côte d'Ivoire|CL:Chile|"
    "CM:Cameroon|CN:China|CO:Colombia|CR:Costa Rica|CU:Cuba|CV:Cabo Verde|CY:Cyprus|CZ:Czechia|DE:Germany|DJ:Djibouti|"
    "DK:Denmark|DM:Dominica|DO:Dominican Republic|DZ:Algeria|EC:Ecuador|EE:Estonia|EG:Egypt|ER:Eritrea|ES:Spain|ET:Ethiopia|"
    "FI:Finland|FJ:Fiji|FR:France|GA:Gabon|GB:United Kingdom|GD:Grenada|GE:Georgia|GH:Ghana|GM:Gambia|GN:Guinea|"
    "GQ:Equatorial Guinea|GR:Greece|GT:Guatemala|GW:Guinea-Bissau|GY:Guyana|HK:Hong Kong|HN:Honduras|HR:Croatia|HT:Haiti|"
    "HU:Hungary|ID:Indonesia|IE:Ireland|IL:Israel|IN:India|IQ:Iraq|IR:Iran|IS:Iceland|IT:Italy|JM:Jamaica|JO:Jordan|JP:Japan|"
    "KE:Kenya|KG:Kyrgyzstan|KH:Cambodia|KM:Comoros|KN:Saint Kitts and Nevis|KP:North Korea|KR:South Korea|KW:Kuwait|"
    "KZ:Kazakhstan|LA:Laos|LB:Lebanon|LC:Saint Lucia|LI:Liechtenstein|LK:Sri Lanka|LR:Liberia|LS:Lesotho|LT:Lithuania|"
    "LU:Luxembourg|LV:Latvia|LY:Libya|MA:Morocco|MC:Monaco|MD:Moldova|ME:Montenegro|MG:Madagascar|MK:North Macedonia|ML:Mali|"
    "MM:Myanmar|MN:Mongolia|MO:Macao|MR:Mauritania|MT:Malta|MU:Mauritius|MV:Maldives|MW:Malawi|MX:Mexico|MY:Malaysia|"
    "MZ:Mozambique|NA:Namibia|NE:Niger|NG:Nigeria|NI:Nicaragua|NL:Netherlands|NO:Norway|NP:Nepal|NZ:New Zealand|OM:Oman|"
    "PA:Panama|PE:Peru|PG:Papua New Guinea|PH:Philippines|PK:Pakistan|PL:Poland|PR:Puerto Rico|PS:Palestine|PT:Portugal|"
    "PY:Paraguay|QA:Qatar|RE:Réunion|RO:Romania|RS:Serbia|RU:Russia|RW:Rwanda|SA:Saudi Arabia|SB:Solomon Islands|"
    "SC:Seychelles|SD:Sudan|SE:Sweden|SG:Singapore|SI:Slovenia|SK:Slovakia|SL:Sierra Leone|SM:San Marino|SN:Senegal|"
    "SO:Somalia|SR:Suriname|SS:South Sudan|ST:São Tomé and Príncipe|SV:El Salvador|SY:Syria|SZ:Eswatini|TD:Chad|TG:Togo|"
    "TH:Thailand|TJ:Tajikistan|TL:Timor-Leste|TM:Turkmenistan|TN:Tunisia|TO:Tonga|TR:Türkiye|TT:Trinidad and Tobago|"
    "TW:Taiwan|TZ:Tanzania|UA:Ukraine|UG:Uganda|US:United States|UY:Uruguay|UZ:Uzbekistan|VA:Vatican City|"
    "VC:Saint Vincent and the Grenadines|VE:Venezuela|VN:Vietnam|VU:Vanuatu|WS:Samoa|YE:Yemen|ZA:South Africa|ZM:Zambia|"
    "ZW:Zimbabwe|EU:Europe|AP:Asia/Pacific|ZZ:Unknown"
).split("|"))

CGNAT = ipaddress.ip_network("100.64.0.0/10")
_state = {"db": None}
_cache = {}
_networks = {}  # id(db) -> [(network, row)], most specific first
_lock = threading.Lock()


def bind(db):
    """The database lookups use (one gateway per process)."""
    with _lock:
        _state["db"] = db
    invalidate()


def invalidate():
    with _lock:
        _cache.clear()
        _networks.clear()


def sort_key(addr):
    """A sortable string for an address: version then 32 hex digits, so IPv4 and IPv6 never interleave."""
    return f"{addr.version}{int(addr):032x}"


def _parse(ip):
    try:
        return ipaddress.ip_address(str(ip or "").strip().split("%")[0])
    except ValueError:
        return None


def _known_networks(db):
    nets = _networks.get(id(db))
    if nets is None:
        nets = []
        for r in db.q("SELECT cidr, label, place, kind FROM networks"):
            try:
                nets.append((ipaddress.ip_network(r["cidr"], strict=False), r))
            except ValueError:
                continue
        nets.sort(key=lambda n: n[0].prefixlen, reverse=True)  # the most specific network wins
        with _lock:
            _networks[id(db)] = nets
    return nets


def _geoip(db, addr):
    k = sort_key(addr)
    row = db.one("SELECT start, stop, country, region, city FROM geoip_ranges WHERE start <= ? ORDER BY start DESC LIMIT 1", (k,))
    if not row or row["stop"] < k or row["start"][0] != k[0]:
        return None
    return row


def describe(ip, db=None):
    """Everything that can honestly be said about where an address is, and how it is known."""
    db = db or _state["db"]
    cache_key = (id(db), str(ip or ""))
    with _lock:
        hit = _cache.get(cache_key)
    if hit is not None:
        return hit
    out = _describe(ip, db)
    with _lock:
        if len(_cache) > 20000:
            _cache.clear()
        _cache[cache_key] = out
    return out


def _describe(ip, db):
    addr = _parse(ip)
    base = {"ip": ip or None, "kind": "unknown", "label": "unknown", "network": None, "country": None, "country_code": None,
            "region": None, "city": None, "approximate": False, "source": None, "evidence": "Not an address"}
    if addr is None:
        return base
    if getattr(addr, "ipv4_mapped", None):
        addr = addr.ipv4_mapped
    if db is not None:
        for net, row in _known_networks(db):
            if addr.version == net.version and addr in net:
                label = row["label"] + (f" · {row['place']}" if row["place"] else "")
                return {**base, "kind": "known", "label": label, "network": {"cidr": row["cidr"], "label": row["label"],
                        "place": row["place"], "kind": row["kind"]},
                        "source": "Known networks", "evidence": f"Inside {row['cidr']}, named by an administrator"}
    if addr.is_loopback:
        return {**base, "kind": "loopback", "label": "this computer", "evidence": "Loopback address"}
    if addr.version == 4 and addr in CGNAT:
        return {**base, "kind": "carrier", "label": "carrier network (shared address)",
                "evidence": "100.64.0.0/10 is shared by a mobile or broadband provider's customers"}
    if addr.is_private or addr.is_link_local:
        return {**base, "kind": "private", "label": "private network", "evidence": "Private address range"}
    if addr.is_multicast or addr.is_reserved or addr.is_unspecified:
        return {**base, "kind": "reserved", "label": "reserved address", "evidence": "Reserved address range"}
    out = {**base, "kind": "public", "label": "public internet", "evidence": "Public address; no location table imported"}
    if db is None:
        return out
    source = db.get_setting("geoip_source", "")
    row = _geoip(db, addr) if source else None
    if source and not row:
        return {**out, "evidence": f"Public address; not in the location table ({source})"}
    if not row:
        return out
    code = (row["country"] or "").upper()
    country = COUNTRIES.get(code, code) if len(code) == 2 else (row["country"] or None)
    parts = [p for p in (row["city"], country) if p]
    return {**out, "kind": "public", "label": (", ".join(parts) + " · approximate") if parts else "public internet",
            "country": country, "country_code": code if len(code) == 2 else None, "region": row["region"] or None,
            "city": row["city"] or None, "approximate": True, "source": source,
            "evidence": f"Offline location table: {source}. An address shows the internet provider's area, not a building."}


def label(ip, db=None):
    """The short form for lists: 'Swangz office · Kampala', 'Kampala, Uganda · approximate', 'private network'."""
    return describe(ip, db)["label"]


def place_key(ip, db=None):
    """What counts as the same place for 'new location' signals: a known network, else a country, else the
    address type. Coarse on purpose — a city from GeoIP moves around too much to be a signal."""
    d = describe(ip, db)
    if d["network"]:
        return "net:" + d["network"]["cidr"]
    if d["country_code"]:
        return "country:" + d["country_code"]
    return "kind:" + d["kind"]


# ---------------------------------------------------------------- importing a location table


def _to_addr(text):
    text = (text or "").strip().strip('"')
    if text.isdigit():  # IP2Location stores IPv4 as a number
        n = int(text)
        return ipaddress.ip_address(n) if n <= 0xFFFFFFFF else ipaddress.IPv6Address(n)
    return ipaddress.ip_address(text)


def import_csv(db, path, source):
    """Replace the location table with the ranges in `path`. Understands DB-IP Lite (country or city),
    IP2Location LITE (DB1/DB3/DB5) and plain "start,end,country[,region,city]". Returns rows imported."""
    if not source or not str(source).strip():
        raise ValueError("say where the table came from (--source), e.g. 'DB-IP Lite 2026-10'")
    rows = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for rec in csv.reader(f):
            if len(rec) < 3:
                continue
            try:
                start, stop = _to_addr(rec[0]), _to_addr(rec[1])
            except ValueError:
                continue  # a header line, or junk
            if start.version != stop.version or int(start) > int(stop):
                continue
            if len(rec) >= 6 and len(rec[2].strip('"')) == 2 and len(rec[3].strip('"')) == 2:
                # DB-IP city: start, end, continent, country, region, city, lat, lon
                country, region, city = rec[3], rec[4], rec[5]
            elif len(rec) >= 6:
                # IP2Location DB3/DB5: from, to, code, country name, region, city, ...
                country, region, city = rec[2], rec[4], rec[5]
            elif len(rec) >= 5:
                country, region, city = rec[2], rec[3], rec[4]
            else:
                country, region, city = rec[2], "", ""
            clean = lambda v: (v or "").strip().strip('"')[:80]  # noqa: E731
            country = clean(country)
            if country == "-":
                country = ""
            region, city = clean(region), clean(city)
            rows.append((sort_key(start), sort_key(stop), country, "" if region == "-" else region, "" if city == "-" else city))
    if not rows:
        raise ValueError("no address ranges found in that file")
    with db.tx():
        db.x("DELETE FROM geoip_ranges")
        db.conn.executemany("INSERT INTO geoip_ranges(start, stop, country, region, city) VALUES(?,?,?,?,?)", rows)
        db.set_setting("geoip_source", str(source).strip()[:120])
        db.set_setting("geoip_imported", str(time.time()))
        db.set_setting("geoip_rows", str(len(rows)))
    invalidate()
    return len(rows)


def status(db):
    source = db.get_setting("geoip_source", "")
    return {"source": source or None, "imported": float(db.get_setting("geoip_imported", "0") or 0) or None,
            "rows": int(db.get_setting("geoip_rows", "0") or 0) if source else 0}
