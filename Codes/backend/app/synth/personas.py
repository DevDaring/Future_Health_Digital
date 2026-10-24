"""The five demo personas (spec section 6). Fixed attributes, always present after seeding.
Names are invented; any resemblance to real people is coincidental."""

from __future__ import annotations

from typing import Any

PERSONAS: list[dict[str, Any]] = [
    {
        "persona": "ramesh",
        "full_name": "Ramesh Kumar",
        "phone": "+971 50 412 7781",
        "eid": "784-1985-4417820-3",
        "story": "High drop-off risk, high uplift. Malayalam navigator books a Friday-evening slot; teach-back passes.",
        "patient": dict(age=41, sex="M", nationality_group="Indian", preferred_language="ml", literacy_level=2,
                        occupation_type="construction", shift_pattern="night", preferred_days=["Fri", "Sat"], home_area="ICAD",
                        distance_km=28.0, insurance_tier="basic", prior_no_shows=2, has_smartphone=True,
                        preferred_channel="call", no_free_weekdays=False),
        "result": dict(program="DIABETES", test_code="HBA1C", value_numeric=6.1, value_text=None),
        "days_ago": 4,
        "demo_fault": None,
    },
    {
        "persona": "fatima",
        "full_name": "Fatima Al Mansoori",
        "phone": "+971 55 230 9184",
        "eid": "784-1974-2093318-6",
        "story": "Mammogram BI-RADS 4. A red-flag phrase in chat escalates instantly to a nurse.",
        "patient": dict(age=52, sex="F", nationality_group="Emirati", preferred_language="ar", literacy_level=3,
                        occupation_type="office", shift_pattern="day", preferred_days=["Mon", "Tue", "Wed", "Thu"],
                        home_area="Al Khalidiyah", distance_km=6.0, insurance_tier="thiqa", prior_no_shows=0,
                        has_smartphone=True, preferred_channel="whatsapp", no_free_weekdays=False),
        "result": dict(program="BREAST", test_code="BIRADS", value_numeric=4.0, value_text="BI-RADS 4"),
        "days_ago": 2,
        "demo_fault": None,
    },
    {
        "persona": "joy",
        "full_name": "Joy Mendoza",
        "phone": "+971 52 778 3016",
        "eid": "784-1992-6631047-1",
        "story": "Positive FIT, worried about cost, no free weekdays: cost-info template, then a day-off (Sunday) slot.",
        "patient": dict(age=34, sex="F", nationality_group="Filipino", preferred_language="tl", literacy_level=2,
                        occupation_type="domestic", shift_pattern="split", preferred_days=["Sun"], home_area="Al Reem Island",
                        distance_km=12.0, insurance_tier="basic", prior_no_shows=0, has_smartphone=True,
                        preferred_channel="whatsapp", no_free_weekdays=True),
        "result": dict(program="COLORECTAL", test_code="FIT", value_numeric=None, value_text="positive"),
        "days_ago": 6,
        "demo_fault": None,
    },
    {
        "persona": "imran",
        "full_name": "Imran Siddiqui",
        "phone": "+971 56 914 2207",
        "eid": "784-1997-8842061-9",
        "story": "HbA1c 7.4. Translation QA catches a number mismatch (7.4→4.7) and falls back to the approved translation.",
        "patient": dict(age=29, sex="M", nationality_group="Pakistani", preferred_language="ur", literacy_level=2,
                        occupation_type="driver", shift_pattern="rotating", preferred_days=["Fri", "Sat"], home_area="Baniyas",
                        distance_km=15.0, insurance_tier="basic", prior_no_shows=1, has_smartphone=True,
                        preferred_channel="whatsapp", no_free_weekdays=False),
        "result": dict(program="DIABETES", test_code="HBA1C", value_numeric=7.4, value_text=None),
        "days_ago": 3,
        "demo_fault": "mt_number_swap",
    },
    {
        "persona": "sara",
        "full_name": "Sara Lindqvist",
        "phone": "+971 50 661 4420",
        "eid": "784-1981-1150736-2",
        "story": "HbA1c 5.9 but would return anyway: low uplift, so WASL ranks her below Ramesh.",
        "patient": dict(age=45, sex="F", nationality_group="Western", preferred_language="en", literacy_level=3,
                        occupation_type="office", shift_pattern="day", preferred_days=["Mon", "Tue", "Wed", "Thu"],
                        home_area="Al Bateen", distance_km=6.0, insurance_tier="enhanced", prior_no_shows=0,
                        has_smartphone=True, preferred_channel="whatsapp", no_free_weekdays=False),
        "result": dict(program="DIABETES", test_code="HBA1C", value_numeric=5.9, value_text=None),
        "days_ago": 4,
        "demo_fault": None,
    },
]

USERS = [
    {"email": "admin@wasl.demo", "username": None, "role": "admin", "display_name": "Aisha Rahman", "languages": ["ar", "en"]},
    {"email": "coord@wasl.demo", "username": None, "role": "coordinator", "display_name": "Omar Haddad", "languages": ["ar", "en"]},
    {"email": "clinician@wasl.demo", "username": None, "role": "clinician", "display_name": "Dr. Layla Haddad", "languages": ["ar", "en"]},
    {"email": "nav@wasl.demo", "username": None, "role": "navigator", "display_name": "Priya Nair", "languages": ["ml", "hi", "en"]},
    # Jury login shown on the login page (requested for the hackathon jury).
    {"email": "jury@wasl.demo", "username": "DevTest", "role": "admin", "display_name": "Jury (DevTest)", "languages": ["en"],
     "password": "DevTest11"},
]

CLINICS = [
    {"name": "Al Khalidiyah Healthcare Centre", "area": "Al Khalidiyah", "lat": 24.4700, "lon": 54.3480,
     "languages_spoken": ["ar", "en", "hi"], "evening_hours": True, "friday_hours": False, "weekend": [],
     "programs": ["DIABETES", "COLORECTAL"]},
    {"name": "Mussafah Workers' Health Centre", "area": "Mussafah", "lat": 24.3550, "lon": 54.5050,
     "languages_spoken": ["ml", "hi", "ur", "bn", "en"], "evening_hours": True, "friday_hours": True, "weekend": ["Sat"],
     "programs": ["DIABETES"]},
    {"name": "Khalifa City Family Clinic", "area": "Khalifa City", "lat": 24.4200, "lon": 54.5780,
     "languages_spoken": ["ar", "en", "ur"], "evening_hours": False, "friday_hours": True, "weekend": [],
     "programs": ["DIABETES", "COLORECTAL", "BREAST"]},
    {"name": "Al Reem Community Clinic", "area": "Al Reem Island", "lat": 24.4980, "lon": 54.4050,
     "languages_spoken": ["en", "ar", "tl"], "evening_hours": True, "friday_hours": False, "weekend": [],
     "programs": ["DIABETES", "BREAST"]},
    {"name": "Baniyas Primary Care", "area": "Baniyas", "lat": 24.3000, "lon": 54.6300,
     "languages_spoken": ["ar", "bn", "ur", "en"], "evening_hours": False, "friday_hours": False, "weekend": [],
     "programs": ["DIABETES"]},
    {"name": "MBZ City Screening & Diagnostic Centre", "area": "Mohammed Bin Zayed City", "lat": 24.3400, "lon": 54.5400,
     "languages_spoken": ["en", "tl", "ml", "ar"], "evening_hours": True, "friday_hours": True, "weekend": ["Sat", "Sun"],
     "programs": ["DIABETES", "COLORECTAL", "BREAST"]},
]

NAMES = {
    "Emirati": (["Ahmed", "Mariam", "Khalid", "Noura", "Saeed", "Hessa", "Rashid", "Latifa"], ["Al Ketbi", "Al Dhaheri", "Al Shamsi", "Al Nuaimi", "Al Mazrouei"]),
    "Indian": (["Anil", "Deepa", "Suresh", "Lakshmi", "Vijay", "Anjali", "Manoj", "Sreeja"], ["Nair", "Pillai", "Sharma", "Menon", "Varghese", "Iyer"]),
    "Pakistani": (["Bilal", "Ayesha", "Usman", "Sana", "Hamza", "Fariha"], ["Khan", "Qureshi", "Malik", "Butt", "Chaudhry"]),
    "Bangladeshi": (["Rahim", "Nusrat", "Kamal", "Shirin", "Jahid", "Rupa"], ["Hossain", "Rahman", "Islam", "Akter", "Uddin"]),
    "Filipino": (["Maria", "Jose", "Grace", "Mark", "Liza", "Paolo"], ["Santos", "Reyes", "Cruz", "Bautista", "Garcia"]),
    "Arab expatriate": (["Omar", "Rana", "Yousef", "Lina", "Tarek", "Dina"], ["Haddad", "Khoury", "Nasser", "Saleh", "Mansour"]),
    "Western": (["James", "Emma", "Oliver", "Sophie", "Lucas", "Hannah"], ["Smith", "Müller", "Rossi", "Dubois", "Jensen"]),
    "Other": (["Daniel", "Amina", "Ivan", "Leila", "Kofi", "Mei"], ["Okafor", "Petrov", "Tan", "Mensah", "Novak"]),
}
