import os
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from utils import parse_address, cap_matches_city, suggest_cap_for_city, check_street_exists_osm

load_dotenv()
API_KEY = os.getenv('API_KEY', 'changeme123')

app = FastAPI(title='IndirizziAPI', description='Normalize & validate Italian addresses')

class AddressRequest(BaseModel):
    address: str
    country: Optional[str] = 'IT'  # per future estensioni

class NormalizedAddress(BaseModel):
    street: Optional[str]
    house_number: Optional[str]
    postcode: Optional[str]
    city: Optional[str]
    province: Optional[str]
    valid: bool
    corrections: list


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key is None:
        raise HTTPException(status_code=401, detail='Missing API key')
    if x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail='Invalid API key')
    return True

@app.post('/normalize-address', response_model=NormalizedAddress)
def normalize_address(req: AddressRequest, _=Depends(verify_api_key)):
    parsed = parse_address(req.address)

    street = parsed.get('road') or parsed.get('street') or parsed.get('house') or parsed.get('street_name') or parsed.get('street_name') or parsed.get('street')
    house = parsed.get('house_number') or parsed.get('house') or parsed.get('house_number')
    postcode = parsed.get('postcode') or parsed.get('postcode') or parsed.get('postalcode')
    city = parsed.get('city') or parsed.get('town') or parsed.get('village') or parsed.get('suburb') or parsed.get('state_district')
    province = parsed.get('state') or parsed.get('province')

    corrections = []
    valid = True

    # Verifica CAP <-> città
    if postcode and city:
        match = cap_matches_city(postcode, city)
        if not match:
            valid = False
            suggested = suggest_cap_for_city(city)
            corrections.append({
                'field': 'postcode',
                'issue': 'postcode does not match city',
                'suggested': suggested
            })

    # Se manca il CAP, prova a suggerirlo
    if not postcode and city:
        suggested = suggest_cap_for_city(city)
        if suggested:
            corrections.append({'field': 'postcode', 'issue': 'missing postcode', 'suggested': suggested})

    # Controllo street esistenza (opzionale, può ritornare None se Overpass non risponde)
    street_ok = None
    try:
        street_ok = check_street_exists_osm(street, city, province)
    except Exception:
        street_ok = None
    if street_ok is False:
        valid = False
        corrections.append({'field': 'street', 'issue': 'street not found in OSM for given city'})

    return NormalizedAddress(
        street=street,
        house_number=house,
        postcode=postcode,
        city=city,
        province=province,
        valid=valid,
        corrections=corrections
    )

@app.get('/health')
def health():
    return {'status': 'ok'}