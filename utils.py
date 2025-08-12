import csv
import os
import re
import requests
from typing import Optional, Tuple, Dict
from dotenv import load_dotenv

load_dotenv()
CAP_DATA_PATH = os.getenv('CAP_DATA_PATH', 'sample_data/cap_comuni.csv')
OVERPASS_URL = os.getenv('OVERPASS_URL', 'https://overpass-api.de/api/interpreter')
USE_LIBPOSTAL = os.getenv('USE_LIBPOSTAL', 'true').lower() in ('1','true','yes')

# Carica mappa CAP -> lista comuni
cap_to_comuni: Dict[str, list] = {}
if os.path.exists(CAP_DATA_PATH):
    with open(CAP_DATA_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            cap = r['cap'].strip()
            comune = r['comune'].strip()
            cap_to_comuni.setdefault(cap, []).append(comune.lower())

# parsing con libpostal (se disponibile)
parsed_libpostal = None
if USE_LIBPOSTAL:
    try:
        from postal.parser import parse_address
        parsed_libpostal = parse_address
    except Exception:
        parsed_libpostal = None


def fallback_parse(address: str) -> dict:
    """Fallback semplice: cerca CAP (5 cifre), numero civico e scompone per virgole"""
    out = {}
    s = address.strip()
    # cerca CAP
    cap_match = re.search(r"\b(\d{5})\b", s)
    if cap_match:
        out['postcode'] = cap_match.group(1)
        s = s.replace(cap_match.group(1), '')
    # split per virgola
    parts = [p.strip() for p in s.split(',') if p.strip()]
    if parts:
        # ultimo pezzo potrebbe essere città/prov
        out['raw_parts'] = parts
        if len(parts) >= 1:
            # tentativo: ultima parte contiene città (e prov)
            last = parts[-1]
            # estrai provincia (sigla) se presente
            prov_match = re.search(r"\b([A-Za-z]{2})\b", last)
            if prov_match:
                out['province'] = prov_match.group(1).upper()
                city = re.sub(r"\b([A-Za-z]{2})\b", '', last).strip(' -')
            else:
                city = last
            out['city'] = city.title()
        # prima parte potrebbe essere via + civico
        street = parts[0]
        house_match = re.search(r"(\d+[A-Za-z\/]?(-\d+)?)$", street)
        if house_match:
            out['house_number'] = house_match.group(1)
            out['street'] = street[:house_match.start()].strip().title()
        else:
            out['street'] = street.title()
    return out


def parse_address(address: str) -> dict:
    if parsed_libpostal:
        try:
            parsed = parsed_libpostal(address)
            # parsed è lista di tuple (component, label)
            d = {}
            for comp, label in parsed:
                d[label] = comp.title()
            return d
        except Exception:
            return fallback_parse(address)
    else:
        return fallback_parse(address)


def cap_matches_city(cap: str, city: str) -> bool:
    if not cap or not city:
        return False
    cap = cap.strip()
    city = city.strip().lower()
    comuni = cap_to_comuni.get(cap)
    if not comuni:
        return False
    return city in comuni


def suggest_cap_for_city(city: str) -> Optional[str]:
    city = city.strip().lower()
    for cap, comuni in cap_to_comuni.items():
        if city in comuni:
            return cap
    return None


def check_street_exists_osm(street: str, city: str, province: Optional[str]=None) -> Optional[bool]:
    """Interroga Overpass per verificare se esiste una way/node con quel nome nella città"""
    if not street or not city:
        return None
    # Overpass QL: cerca way con name=street dentro amministrative area con name=city
    q = f'''[out:json][timeout:10];area[name~"^{city}$",i]->.a;(
  way["name"~"^{street}$",i](area.a);
  node["name"~"^{street}$",i](area.a);
);out center 1;'''
    try:
        resp = requests.post(OVERPASS_URL, data=q, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return len(data.get('elements', [])) > 0
    except Exception:
        return None