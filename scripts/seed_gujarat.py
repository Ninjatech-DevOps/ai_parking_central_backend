"""
Seed Gujarat state with all 33 districts (as cities), all talukas, and areas.
Idempotent — skips existing records by checking names.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.session import async_session_factory

import src.app.models  # noqa: F401

from src.app.models.state import State
from src.app.models.city import City
from src.app.models.taluka import Taluka
from src.app.models.village import Village
from src.app.models.area import Area

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_gujarat")

# ============================================================================
# Gujarat Data Structure — All 33 Districts & 265+ Talukas
# ============================================================================
# Format:
# {
#   "city_name": {
#       "direct_areas": ["area1", "area2"],       # city-level areas (no taluka/village)
#       "talukas": {
#           "taluka_name": {
#               "direct_areas": ["area1"],          # taluka-level areas (no village)
#               "villages": {
#                   "village_name": ["area1", "area2"],  # village-level areas
#               }
#           }
#       }
#   }
# }
# ============================================================================

GUJARAT_DATA = {
    # ========================================================================
    # NORTH GUJARAT
    # ========================================================================
    "Ahmedabad": {
        "direct_areas": [
            "Memnagar", "Satellite", "Bopal", "Navrangpura", "Maninagar",
            "Paldi", "Vastrapur", "Bodakdev", "Gurukul", "Chandkheda",
            "Gota", "Motera", "Ghatlodiya", "Ranip", "Naroda",
            "Shahibaug", "Ellis Bridge", "Ambawadi", "Thaltej", "Prahlad Nagar",
            "SG Highway", "Drive In Road", "CG Road", "Ashram Road", "Law Garden",
            "Isanpur", "Odhav", "Vastral", "Nikol", "Narol",
            "Jodhpur", "Vejalpur", "Jivraj Park", "Sarkhej", "Kankaria",
        ],
        "talukas": {
            "Daskroi": {
                "direct_areas": [],
                "villages": {
                    "Sanand": ["Sanand GIDC", "Sanand Village Road"],
                    "Bavla": ["Bavla Main Road"],
                    "Bagodara": ["Bagodara Center"],
                }
            },
            "Sanand": {
                "direct_areas": ["Sanand GIDC Industrial Area"],
                "villages": {}
            },
            "Bavla": {
                "direct_areas": ["Bavla Town Center"],
                "villages": {}
            },
            "Dholka": {
                "direct_areas": ["Dholka Main Road"],
                "villages": {
                    "Dholka": ["Dholka Bus Stand Area"],
                }
            },
            "Dhandhuka": {
                "direct_areas": ["Dhandhuka Main Road"],
                "villages": {}
            },
            "Ranpur": {
                "direct_areas": [],
                "villages": {
                    "Ranpur": ["Ranpur Center"],
                }
            },
            "Barwala": {
                "direct_areas": [],
                "villages": {}
            },
            "Mandal": {
                "direct_areas": [],
                "villages": {}
            },
            "Viramgam": {
                "direct_areas": [],
                "villages": {
                    "Viramgam": ["Viramgam Station Road", "Viramgam Market"],
                }
            },
            "Detroj-Rampura": {
                "direct_areas": [],
                "villages": {
                    "Detroj": ["Detroj Main Road"],
                    "Rampura": ["Rampura Center"],
                }
            },
        }
    },
    "Gandhinagar": {
        "direct_areas": [
            "Sector 1", "Sector 2", "Sector 7", "Sector 11", "Sector 16",
            "Sector 21", "Sector 24", "Sector 28", "Sector 30",
            "Infocity", "GIFT City", "Kudasan", "Sargasan", "Raysan",
            "Pethapur", "Adalaj", "Koba",
        ],
        "talukas": {
            "Gandhinagar": {
                "direct_areas": [],
                "villages": {}
            },
            "Kalol": {
                "direct_areas": ["Kalol GIDC"],
                "villages": {
                    "Kalol": ["Kalol Station Road"],
                    "Kadi": ["Kadi Main Road"],
                }
            },
            "Dehgam": {
                "direct_areas": [],
                "villages": {
                    "Dehgam": ["Dehgam Town Center"],
                }
            },
            "Mansa": {
                "direct_areas": [],
                "villages": {
                    "Mansa": ["Mansa Town Center"],
                }
            },
        }
    },
    "Mehsana": {
        "direct_areas": [
            "Highway Road", "Radhanpur Road", "Modhera Road",
            "Mehsana Station Area", "Gozaria", "Langhnaj",
        ],
        "talukas": {
            "Mehsana": {
                "direct_areas": [],
                "villages": {}
            },
            "Visnagar": {
                "direct_areas": [],
                "villages": {
                    "Visnagar": ["Visnagar Main Road"],
                }
            },
            "Unjha": {
                "direct_areas": [],
                "villages": {
                    "Unjha": ["Unjha Market Road"],
                }
            },
            "Kadi": {
                "direct_areas": ["Kadi GIDC"],
                "villages": {
                    "Kadi": ["Kadi Station Road"],
                }
            },
            "Vijapur": {
                "direct_areas": [],
                "villages": {
                    "Vijapur": ["Vijapur Main Road"],
                }
            },
            "Kheralu": {
                "direct_areas": [],
                "villages": {}
            },
            "Vadnagar": {
                "direct_areas": [],
                "villages": {
                    "Vadnagar": ["Vadnagar Town Center"],
                }
            },
            "Becharaji": {
                "direct_areas": ["Becharaji GIDC", "Mandal Special Investment Region"],
                "villages": {}
            },
            "Satlasana": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Banaskantha": {
        "direct_areas": [
            "Palanpur Station Road", "Palanpur Market", "Palanpur Highway",
        ],
        "talukas": {
            "Palanpur": {
                "direct_areas": ["Palanpur Main Road"],
                "villages": {
                    "Palanpur": ["Palanpur Bus Stand Area"],
                }
            },
            "Deesa": {
                "direct_areas": ["Deesa Main Road"],
                "villages": {
                    "Deesa": ["Deesa Town Center"],
                }
            },
            "Dhanera": {
                "direct_areas": [],
                "villages": {
                    "Dhanera": ["Dhanera Main Road"],
                }
            },
            "Vav": {
                "direct_areas": [],
                "villages": {}
            },
            "Tharad": {
                "direct_areas": [],
                "villages": {
                    "Tharad": ["Tharad Town Center"],
                }
            },
            "Deodar": {
                "direct_areas": [],
                "villages": {}
            },
            "Suigam": {
                "direct_areas": [],
                "villages": {}
            },
            "Danta": {
                "direct_areas": [],
                "villages": {}
            },
            "Vadgam": {
                "direct_areas": [],
                "villages": {
                    "Vadgam": ["Vadgam Main Road"],
                }
            },
            "Amirgadh": {
                "direct_areas": [],
                "villages": {}
            },
            "Dantiwada": {
                "direct_areas": [],
                "villages": {}
            },
            "Bhabhar": {
                "direct_areas": [],
                "villages": {}
            },
            "Kankrej": {
                "direct_areas": [],
                "villages": {}
            },
            "Lakhani": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Sabarkantha": {
        "direct_areas": [
            "Himmatnagar Station Road", "Himmatnagar Market",
        ],
        "talukas": {
            "Himmatnagar": {
                "direct_areas": ["Himmatnagar Main Road"],
                "villages": {}
            },
            "Idar": {
                "direct_areas": [],
                "villages": {
                    "Idar": ["Idar Town Center"],
                }
            },
            "Khedbrahma": {
                "direct_areas": [],
                "villages": {}
            },
            "Prantij": {
                "direct_areas": [],
                "villages": {
                    "Prantij": ["Prantij Main Road"],
                }
            },
            "Talod": {
                "direct_areas": [],
                "villages": {}
            },
            "Vadali": {
                "direct_areas": [],
                "villages": {}
            },
            "Vijaynagar": {
                "direct_areas": [],
                "villages": {}
            },
            "Poshina": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Aravalli": {
        "direct_areas": [
            "Modasa Main Road", "Modasa Bus Stand Area",
        ],
        "talukas": {
            "Modasa": {
                "direct_areas": ["Modasa Town Center"],
                "villages": {}
            },
            "Bhiloda": {
                "direct_areas": [],
                "villages": {}
            },
            "Meghraj": {
                "direct_areas": [],
                "villages": {}
            },
            "Malpur": {
                "direct_areas": [],
                "villages": {}
            },
            "Dhansura": {
                "direct_areas": [],
                "villages": {}
            },
            "Bayad": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Patan": {
        "direct_areas": [
            "Patan Main Road", "Patan Station Area",
        ],
        "talukas": {
            "Patan": {
                "direct_areas": [],
                "villages": {}
            },
            "Sidhpur": {
                "direct_areas": [],
                "villages": {
                    "Sidhpur": ["Sidhpur Main Road"],
                }
            },
            "Chanasma": {
                "direct_areas": [],
                "villages": {}
            },
            "Radhanpur": {
                "direct_areas": [],
                "villages": {
                    "Radhanpur": ["Radhanpur Town Center"],
                }
            },
            "Santalpur": {
                "direct_areas": [],
                "villages": {}
            },
            "Harij": {
                "direct_areas": [],
                "villages": {}
            },
            "Sami": {
                "direct_areas": [],
                "villages": {}
            },
            "Shankheshwar": {
                "direct_areas": [],
                "villages": {}
            },
            "Saraswati": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    # ========================================================================
    # CENTRAL GUJARAT
    # ========================================================================
    "Vadodara": {
        "direct_areas": [
            "Alkapuri", "Gotri", "Subhanpura", "Akota", "Manjalpur",
            "Fatehgunj", "Race Course", "Sayajigunj", "Karelibaug", "Waghodia Road",
            "Vasna", "Sama", "Tarsali", "Harni", "Makarpura",
            "Old Padra Road", "New VIP Road", "Chhani", "Bhayli",
            "Gotri Road", "Sama Savli Road", "Vasna Bhayli Road",
        ],
        "talukas": {
            "Vadodara": {
                "direct_areas": [],
                "villages": {}
            },
            "Savli": {
                "direct_areas": [],
                "villages": {
                    "Savli": ["Savli GIDC", "Savli Village"],
                }
            },
            "Dabhoi": {
                "direct_areas": ["College Road", "Dabhoi Bus Stand Area"],
                "villages": {
                    "Kayavarohan": ["Kayavarohan Temple Road"],
                    "Sarodar": ["Sarodar Main Road"],
                }
            },
            "Padra": {
                "direct_areas": ["Padra Main Road"],
                "villages": {
                    "Padra": ["Padra Station Area"],
                    "Varnama": ["Varnama Center"],
                }
            },
            "Karajan": {
                "direct_areas": [],
                "villages": {}
            },
            "Shinor": {
                "direct_areas": [],
                "villages": {
                    "Shinor": ["Shinor Main Road"],
                }
            },
            "Waghodia": {
                "direct_areas": [],
                "villages": {
                    "Waghodia": ["Waghodia Main Road"],
                }
            },
            "Desar": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Anand": {
        "direct_areas": [
            "Vallabh Vidyanagar", "Karamsad Road", "Gamdi", "Station Road",
            "Grid Char Rasta", "Lambhvel Road", "Anand-Sojitra Road",
        ],
        "talukas": {
            "Anand": {
                "direct_areas": [],
                "villages": {}
            },
            "Borsad": {
                "direct_areas": ["Borsad Main Road"],
                "villages": {
                    "Borsad": ["Borsad Station Area"],
                }
            },
            "Petlad": {
                "direct_areas": [],
                "villages": {
                    "Petlad": ["Petlad Main Road"],
                }
            },
            "Umreth": {
                "direct_areas": [],
                "villages": {
                    "Umreth": ["Umreth Town Center"],
                }
            },
            "Sojitra": {
                "direct_areas": [],
                "villages": {}
            },
            "Khambhat": {
                "direct_areas": [],
                "villages": {
                    "Khambhat": ["Khambhat Main Road"],
                }
            },
            "Tarapur": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Kheda": {
        "direct_areas": [
            "Nadiad Station Road", "Nadiad Main Road",
        ],
        "talukas": {
            "Nadiad": {
                "direct_areas": ["Nadiad Town Center"],
                "villages": {}
            },
            "Kheda": {
                "direct_areas": [],
                "villages": {}
            },
            "Kapadwanj": {
                "direct_areas": [],
                "villages": {
                    "Kapadwanj": ["Kapadwanj Main Road"],
                }
            },
            "Thasra": {
                "direct_areas": [],
                "villages": {}
            },
            "Matar": {
                "direct_areas": [],
                "villages": {}
            },
            "Mehmedabad": {
                "direct_areas": [],
                "villages": {}
            },
            "Mahudha": {
                "direct_areas": [],
                "villages": {}
            },
            "Kathlal": {
                "direct_areas": [],
                "villages": {}
            },
            "Galteshwar": {
                "direct_areas": [],
                "villages": {}
            },
            "Vaso": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Panchmahal": {
        "direct_areas": [
            "Godhra Station Road", "Godhra Main Road",
        ],
        "talukas": {
            "Godhra": {
                "direct_areas": ["Godhra Town Center"],
                "villages": {}
            },
            "Halol": {
                "direct_areas": ["Halol GIDC"],
                "villages": {
                    "Halol": ["Halol Main Road"],
                }
            },
            "Kalol": {
                "direct_areas": [],
                "villages": {}
            },
            "Jambughoda": {
                "direct_areas": [],
                "villages": {}
            },
            "Morva Hadaf": {
                "direct_areas": [],
                "villages": {}
            },
            "Shehera": {
                "direct_areas": [],
                "villages": {}
            },
            "Ghoghamba": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Mahisagar": {
        "direct_areas": [
            "Lunawada Main Road",
        ],
        "talukas": {
            "Lunawada": {
                "direct_areas": ["Lunawada Town Center"],
                "villages": {}
            },
            "Balasinor": {
                "direct_areas": [],
                "villages": {
                    "Balasinor": ["Balasinor Main Road"],
                }
            },
            "Kadana": {
                "direct_areas": [],
                "villages": {}
            },
            "Khanpur": {
                "direct_areas": [],
                "villages": {}
            },
            "Virpur": {
                "direct_areas": [],
                "villages": {}
            },
            "Santrampur": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Dahod": {
        "direct_areas": [
            "Dahod Station Road", "Dahod Main Market",
        ],
        "talukas": {
            "Dahod": {
                "direct_areas": ["Dahod Town Center"],
                "villages": {}
            },
            "Jhalod": {
                "direct_areas": [],
                "villages": {
                    "Jhalod": ["Jhalod Main Road"],
                }
            },
            "Limkheda": {
                "direct_areas": [],
                "villages": {}
            },
            "Fatepura": {
                "direct_areas": [],
                "villages": {}
            },
            "Garbada": {
                "direct_areas": [],
                "villages": {}
            },
            "Devgadh Baria": {
                "direct_areas": [],
                "villages": {
                    "Devgadh Baria": ["Devgadh Baria Main Road"],
                }
            },
            "Dhanpur": {
                "direct_areas": [],
                "villages": {}
            },
            "Sanjeli": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Chhota Udepur": {
        "direct_areas": [
            "Chhota Udepur Main Road",
        ],
        "talukas": {
            "Chhota Udepur": {
                "direct_areas": ["Chhota Udepur Town Center"],
                "villages": {}
            },
            "Sankheda": {
                "direct_areas": [],
                "villages": {
                    "Sankheda": ["Sankheda Main Road"],
                }
            },
            "Bodeli": {
                "direct_areas": [],
                "villages": {}
            },
            "Jetpur Pavi": {
                "direct_areas": [],
                "villages": {}
            },
            "Kavant": {
                "direct_areas": [],
                "villages": {}
            },
            "Nasvadi": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    # ========================================================================
    # SOUTH GUJARAT
    # ========================================================================
    "Surat": {
        "direct_areas": [
            "Adajan", "Vesu", "Athwa", "Piplod", "City Light",
            "Pal", "Althan", "Varachha", "Katargam", "Udhna",
            "Dumas Road", "Ring Road", "LP Savani Road", "Ghod Dod Road",
            "Dindoli", "Bhatar", "Parle Point", "Rander",
            "VIP Road", "New City Light", "Bharthana", "Pal Gam",
            "Majura Gate", "Athwa Gate", "Pandesara", "Sagrampura",
        ],
        "talukas": {
            "Surat City": {
                "direct_areas": [],
                "villages": {}
            },
            "Choryasi": {
                "direct_areas": [],
                "villages": {}
            },
            "Bardoli": {
                "direct_areas": ["Bardoli Main Road"],
                "villages": {
                    "Bardoli": ["Bardoli Station Area"],
                    "Madhi": ["Madhi Village"],
                }
            },
            "Kamrej": {
                "direct_areas": [],
                "villages": {
                    "Kamrej": ["Kamrej Highway"],
                }
            },
            "Olpad": {
                "direct_areas": [],
                "villages": {
                    "Olpad": ["Olpad Main Road"],
                    "Kim": ["Kim Junction"],
                }
            },
            "Mangrol": {
                "direct_areas": [],
                "villages": {}
            },
            "Mandvi": {
                "direct_areas": [],
                "villages": {}
            },
            "Palsana": {
                "direct_areas": [],
                "villages": {}
            },
            "Umarpada": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Bharuch": {
        "direct_areas": [
            "Bharuch Station Road", "Bharuch Main Market", "Zadeshwar",
        ],
        "talukas": {
            "Bharuch": {
                "direct_areas": ["Bharuch Town Center"],
                "villages": {}
            },
            "Ankleshwar": {
                "direct_areas": ["Ankleshwar GIDC"],
                "villages": {
                    "Ankleshwar": ["Ankleshwar Main Road"],
                }
            },
            "Jambusar": {
                "direct_areas": [],
                "villages": {
                    "Jambusar": ["Jambusar Main Road"],
                }
            },
            "Amod": {
                "direct_areas": [],
                "villages": {}
            },
            "Vagra": {
                "direct_areas": [],
                "villages": {}
            },
            "Hansot": {
                "direct_areas": [],
                "villages": {}
            },
            "Valia": {
                "direct_areas": [],
                "villages": {}
            },
            "Netrang": {
                "direct_areas": [],
                "villages": {}
            },
            "Jhagadia": {
                "direct_areas": ["Jhagadia GIDC"],
                "villages": {}
            },
        }
    },
    "Narmada": {
        "direct_areas": [
            "Rajpipla Main Road",
        ],
        "talukas": {
            "Nandod": {
                "direct_areas": ["Rajpipla Town Center"],
                "villages": {}
            },
            "Sagbara": {
                "direct_areas": [],
                "villages": {}
            },
            "Garudeshwar": {
                "direct_areas": [],
                "villages": {}
            },
            "Tilakwada": {
                "direct_areas": [],
                "villages": {}
            },
            "Dediapada": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Tapi": {
        "direct_areas": [
            "Vyara Main Road",
        ],
        "talukas": {
            "Vyara": {
                "direct_areas": ["Vyara Town Center"],
                "villages": {}
            },
            "Valod": {
                "direct_areas": [],
                "villages": {}
            },
            "Songadh": {
                "direct_areas": [],
                "villages": {}
            },
            "Uchchhal": {
                "direct_areas": [],
                "villages": {}
            },
            "Nizar": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Navsari": {
        "direct_areas": [
            "Navsari Station Road", "Navsari Main Market",
        ],
        "talukas": {
            "Navsari": {
                "direct_areas": ["Navsari Town Center"],
                "villages": {}
            },
            "Chikhli": {
                "direct_areas": [],
                "villages": {
                    "Chikhli": ["Chikhli Main Road"],
                }
            },
            "Gandevi": {
                "direct_areas": [],
                "villages": {}
            },
            "Vansda": {
                "direct_areas": [],
                "villages": {}
            },
            "Jalalpore": {
                "direct_areas": [],
                "villages": {}
            },
            "Khergam": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Valsad": {
        "direct_areas": [
            "Valsad Station Road", "Valsad Main Market",
        ],
        "talukas": {
            "Valsad": {
                "direct_areas": ["Valsad Town Center"],
                "villages": {}
            },
            "Vapi": {
                "direct_areas": ["Vapi GIDC", "Vapi Main Road"],
                "villages": {}
            },
            "Pardi": {
                "direct_areas": [],
                "villages": {}
            },
            "Umargam": {
                "direct_areas": [],
                "villages": {}
            },
            "Dharampur": {
                "direct_areas": [],
                "villages": {}
            },
            "Kaprada": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Dang": {
        "direct_areas": [
            "Ahwa Main Road",
        ],
        "talukas": {
            "Ahwa": {
                "direct_areas": ["Ahwa Town Center"],
                "villages": {}
            },
            "Waghai": {
                "direct_areas": [],
                "villages": {}
            },
            "Subir": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    # ========================================================================
    # SAURASHTRA
    # ========================================================================
    "Rajkot": {
        "direct_areas": [
            "Kalawad Road", "University Road", "Yagnik Road", "150 Feet Ring Road",
            "Raiya Road", "Amin Marg", "Jamnagar Road", "Gondal Road",
            "Nana Mava", "Mavdi", "Kothariya", "Trikon Baug",
            "Bhakti Nagar", "Karanpara", "Dhebar Road", "Rajputpara",
            "Sardar Nagar", "Gundawadi", "Tagore Road", "Palace Road",
        ],
        "talukas": {
            "Rajkot": {
                "direct_areas": [],
                "villages": {}
            },
            "Gondal": {
                "direct_areas": ["Gondal Main Road"],
                "villages": {
                    "Gondal": ["Gondal Station Area"],
                }
            },
            "Jetpur": {
                "direct_areas": ["Jetpur Main Road"],
                "villages": {}
            },
            "Dhoraji": {
                "direct_areas": [],
                "villages": {
                    "Dhoraji": ["Dhoraji Main Road"],
                }
            },
            "Upleta": {
                "direct_areas": [],
                "villages": {}
            },
            "Jasdan": {
                "direct_areas": [],
                "villages": {
                    "Jasdan": ["Jasdan Main Road"],
                }
            },
            "Lodhika": {
                "direct_areas": [],
                "villages": {
                    "Lodhika": ["Lodhika GIDC"],
                }
            },
            "Kotda Sangani": {
                "direct_areas": [],
                "villages": {
                    "Kotda Sangani": ["Kotda Main Road"],
                }
            },
            "Paddhari": {
                "direct_areas": [],
                "villages": {}
            },
            "Jamkandorna": {
                "direct_areas": [],
                "villages": {}
            },
            "Vinchhiya": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Jamnagar": {
        "direct_areas": [
            "Summair Club Road", "Patel Colony", "Indira Marg", "Bedi Gate",
            "Aerodrome Road", "Digvijay Plot", "Lal Bungalow",
            "Khodiyar Colony", "Jamnagar-Rajkot Highway",
        ],
        "talukas": {
            "Jamnagar": {
                "direct_areas": [],
                "villages": {}
            },
            "Lalpur": {
                "direct_areas": [],
                "villages": {
                    "Lalpur": ["Lalpur Center"],
                }
            },
            "Dhrol": {
                "direct_areas": [],
                "villages": {
                    "Dhrol": ["Dhrol Main Road"],
                }
            },
            "Jodia": {
                "direct_areas": [],
                "villages": {}
            },
            "Kalavad": {
                "direct_areas": [],
                "villages": {}
            },
            "Jamjodhpur": {
                "direct_areas": [],
                "villages": {
                    "Jamjodhpur": ["Jamjodhpur Main Road"],
                }
            },
        }
    },
    "Devbhumi Dwarka": {
        "direct_areas": [
            "Khambhalia Main Road",
        ],
        "talukas": {
            "Khambhalia": {
                "direct_areas": ["Khambhalia Town Center"],
                "villages": {}
            },
            "Dwarka": {
                "direct_areas": ["Dwarka Temple Road"],
                "villages": {}
            },
            "Bhanvad": {
                "direct_areas": [],
                "villages": {}
            },
            "Kalyanpur": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Porbandar": {
        "direct_areas": [
            "MG Road Porbandar", "Chowpatty", "Sudama Chowk",
        ],
        "talukas": {
            "Porbandar": {
                "direct_areas": ["Porbandar Town Center"],
                "villages": {}
            },
            "Ranavav": {
                "direct_areas": [],
                "villages": {}
            },
            "Kutiyana": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Junagadh": {
        "direct_areas": [
            "Kalwa Chowk", "MG Road", "Joshipura", "Zanzarda Road",
            "Gandhigram", "Majewadi Gate", "Talav Gate", "Bhavnath",
        ],
        "talukas": {
            "Junagadh City": {
                "direct_areas": [],
                "villages": {}
            },
            "Junagadh Rural": {
                "direct_areas": [],
                "villages": {}
            },
            "Keshod": {
                "direct_areas": [],
                "villages": {
                    "Keshod": ["Keshod Main Road"],
                }
            },
            "Visavadar": {
                "direct_areas": [],
                "villages": {
                    "Visavadar": ["Visavadar Main Road"],
                }
            },
            "Vanthali": {
                "direct_areas": [],
                "villages": {}
            },
            "Manavadar": {
                "direct_areas": [],
                "villages": {
                    "Manavadar": ["Manavadar Main Road"],
                }
            },
            "Mangrol": {
                "direct_areas": [],
                "villages": {
                    "Mangrol": ["Mangrol Port Area"],
                }
            },
            "Bhesan": {
                "direct_areas": [],
                "villages": {}
            },
            "Mendarda": {
                "direct_areas": [],
                "villages": {}
            },
            "Malia Hatina": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Gir Somnath": {
        "direct_areas": [
            "Veraval Main Road", "Somnath Temple Road",
        ],
        "talukas": {
            "Veraval": {
                "direct_areas": ["Veraval Town Center", "Veraval Port Area"],
                "villages": {}
            },
            "Una": {
                "direct_areas": [],
                "villages": {
                    "Una": ["Una Main Road"],
                }
            },
            "Talala": {
                "direct_areas": [],
                "villages": {}
            },
            "Kodinar": {
                "direct_areas": [],
                "villages": {
                    "Kodinar": ["Kodinar Main Road"],
                }
            },
            "Sutrapada": {
                "direct_areas": [],
                "villages": {}
            },
            "Gir Gadhada": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Amreli": {
        "direct_areas": [
            "Amreli Station Road", "Amreli Main Market",
        ],
        "talukas": {
            "Amreli": {
                "direct_areas": ["Amreli Town Center"],
                "villages": {}
            },
            "Savarkundla": {
                "direct_areas": [],
                "villages": {
                    "Savarkundla": ["Savarkundla Main Road"],
                }
            },
            "Rajula": {
                "direct_areas": [],
                "villages": {}
            },
            "Babra": {
                "direct_areas": [],
                "villages": {}
            },
            "Dhari": {
                "direct_areas": [],
                "villages": {}
            },
            "Jafrabad": {
                "direct_areas": [],
                "villages": {}
            },
            "Khambha": {
                "direct_areas": [],
                "villages": {}
            },
            "Lathi": {
                "direct_areas": [],
                "villages": {}
            },
            "Lilia": {
                "direct_areas": [],
                "villages": {}
            },
            "Kukavav": {
                "direct_areas": [],
                "villages": {}
            },
            "Bagasara": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Bhavnagar": {
        "direct_areas": [
            "Waghawadi Road", "Kalanala", "Ghogha Circle", "Amba Chowk",
            "Crescent Circle", "Khumbharwada", "Takhteshwar",
            "Kaliyabid", "Hill Drive", "Sardar Nagar",
            "Subhashnagar", "Diwanpara Road", "Meghani Circle",
        ],
        "talukas": {
            "Bhavnagar": {
                "direct_areas": [],
                "villages": {}
            },
            "Sihor": {
                "direct_areas": ["Sihor Main Road"],
                "villages": {
                    "Sihor": ["Sihor Bus Station Area"],
                }
            },
            "Palitana": {
                "direct_areas": ["Palitana Temple Road"],
                "villages": {
                    "Palitana": ["Palitana Town Center"],
                }
            },
            "Mahuva": {
                "direct_areas": [],
                "villages": {
                    "Mahuva": ["Mahuva Main Road"],
                }
            },
            "Talaja": {
                "direct_areas": [],
                "villages": {}
            },
            "Umrala": {
                "direct_areas": [],
                "villages": {}
            },
            "Vallabhipur": {
                "direct_areas": [],
                "villages": {}
            },
            "Ghogha": {
                "direct_areas": [],
                "villages": {}
            },
            "Gariadhar": {
                "direct_areas": [],
                "villages": {}
            },
            "Jesar": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Botad": {
        "direct_areas": [
            "Botad Main Road", "Botad Station Area",
        ],
        "talukas": {
            "Botad": {
                "direct_areas": ["Botad Town Center"],
                "villages": {}
            },
            "Ranpur": {
                "direct_areas": [],
                "villages": {}
            },
            "Barwala": {
                "direct_areas": [],
                "villages": {}
            },
            "Gadhada": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
    "Surendranagar": {
        "direct_areas": [
            "Surendranagar Station Road", "Wadhwan Main Road",
        ],
        "talukas": {
            "Surendranagar": {
                "direct_areas": [],
                "villages": {}
            },
            "Wadhwan": {
                "direct_areas": ["Wadhwan Town Center"],
                "villages": {}
            },
            "Limbdi": {
                "direct_areas": [],
                "villages": {
                    "Limbdi": ["Limbdi Main Road"],
                }
            },
            "Chotila": {
                "direct_areas": [],
                "villages": {}
            },
            "Muli": {
                "direct_areas": [],
                "villages": {}
            },
            "Dasada": {
                "direct_areas": [],
                "villages": {}
            },
            "Lakhtar": {
                "direct_areas": [],
                "villages": {}
            },
            "Chuda": {
                "direct_areas": [],
                "villages": {}
            },
            "Thangadh": {
                "direct_areas": [],
                "villages": {}
            },
            "Dhrangadhra": {
                "direct_areas": [],
                "villages": {
                    "Dhrangadhra": ["Dhrangadhra Main Road"],
                }
            },
        }
    },
    "Morbi": {
        "direct_areas": [
            "Morbi Main Road", "Morbi Ceramic Zone",
        ],
        "talukas": {
            "Morbi": {
                "direct_areas": ["Morbi Town Center"],
                "villages": {}
            },
            "Tankara": {
                "direct_areas": [],
                "villages": {}
            },
            "Halvad": {
                "direct_areas": [],
                "villages": {
                    "Halvad": ["Halvad Main Road"],
                }
            },
            "Maliya Miyana": {
                "direct_areas": [],
                "villages": {}
            },
            "Wankaner": {
                "direct_areas": [],
                "villages": {
                    "Wankaner": ["Wankaner Main Road"],
                }
            },
        }
    },
    # ========================================================================
    # KUTCH
    # ========================================================================
    "Kutch": {
        "direct_areas": [
            "Bhuj Main Market", "Bhuj Station Road", "Bhuj Jubilee Circle",
        ],
        "talukas": {
            "Bhuj": {
                "direct_areas": ["Bhuj Town Center", "Bhuj Madhapar"],
                "villages": {}
            },
            "Gandhidham": {
                "direct_areas": ["Gandhidham Main Road", "Adipur"],
                "villages": {}
            },
            "Anjar": {
                "direct_areas": [],
                "villages": {
                    "Anjar": ["Anjar Main Road"],
                }
            },
            "Mandvi": {
                "direct_areas": [],
                "villages": {
                    "Mandvi": ["Mandvi Beach Road", "Mandvi Port"],
                }
            },
            "Mundra": {
                "direct_areas": ["Mundra Port Area", "Mundra SEZ"],
                "villages": {}
            },
            "Bhachau": {
                "direct_areas": [],
                "villages": {}
            },
            "Rapar": {
                "direct_areas": [],
                "villages": {}
            },
            "Nakhtrana": {
                "direct_areas": [],
                "villages": {}
            },
            "Abdasa": {
                "direct_areas": [],
                "villages": {}
            },
            "Lakhpat": {
                "direct_areas": [],
                "villages": {}
            },
        }
    },
}


async def get_or_create(db: AsyncSession, model, filters: dict, defaults: dict = None):
    """Get existing record or create new one."""
    query = select(model)
    for key, value in filters.items():
        query = query.where(getattr(model, key) == value)
    result = await db.execute(query)
    instance = result.scalars().first()

    if instance:
        return instance, False

    data = {**filters, **(defaults or {})}
    instance = model(**data)
    db.add(instance)
    await db.flush()
    return instance, True


async def seed_gujarat():
    async with async_session_factory() as db:
        try:
            # Create Gujarat state
            state, created = await get_or_create(
                db, State,
                filters={"code": "GJ"},
                defaults={"name": "Gujarat", "country": "India"},
            )
            if created:
                logger.info("Created state: Gujarat")
            else:
                logger.info("State Gujarat already exists")

            total_cities = 0
            total_talukas = 0
            total_villages = 0
            total_areas = 0

            for city_name, city_data in GUJARAT_DATA.items():
                city, created = await get_or_create(
                    db, City,
                    filters={"name": city_name, "state_id": state.id},
                )
                if created:
                    total_cities += 1
                    logger.info("  Created city: %s", city_name)

                # Direct city areas (no taluka/village)
                for area_name in city_data.get("direct_areas", []):
                    _, created = await get_or_create(
                        db, Area,
                        filters={
                            "name": area_name,
                            "city_id": city.id,
                            "taluka_id": None,
                            "village_id": None,
                        },
                    )
                    if created:
                        total_areas += 1

                # Talukas
                for taluka_name, taluka_data in city_data.get("talukas", {}).items():
                    taluka, created = await get_or_create(
                        db, Taluka,
                        filters={"name": taluka_name, "city_id": city.id},
                    )
                    if created:
                        total_talukas += 1
                        logger.info("    Created taluka: %s", taluka_name)

                    # Taluka-level areas (no village)
                    for area_name in taluka_data.get("direct_areas", []):
                        _, created = await get_or_create(
                            db, Area,
                            filters={
                                "name": area_name,
                                "city_id": city.id,
                                "taluka_id": taluka.id,
                                "village_id": None,
                            },
                        )
                        if created:
                            total_areas += 1

                    # Villages under taluka
                    for village_name, village_areas in taluka_data.get("villages", {}).items():
                        village, created = await get_or_create(
                            db, Village,
                            filters={"name": village_name, "taluka_id": taluka.id},
                        )
                        if created:
                            total_villages += 1
                            logger.info("      Created village: %s", village_name)

                        # Areas under village
                        for area_name in village_areas:
                            _, created = await get_or_create(
                                db, Area,
                                filters={
                                    "name": area_name,
                                    "city_id": city.id,
                                    "taluka_id": taluka.id,
                                    "village_id": village.id,
                                },
                            )
                            if created:
                                total_areas += 1

            await db.commit()

            logger.info("")
            logger.info("=== Gujarat Seed Summary ===")
            logger.info("Cities (Districts): %d", total_cities)
            logger.info("Talukas:            %d", total_talukas)
            logger.info("Villages:           %d", total_villages)
            logger.info("Areas:              %d", total_areas)
            logger.info("============================")

        except Exception:
            await db.rollback()
            logger.exception("Gujarat seed failed")
            raise


if __name__ == "__main__":
    asyncio.run(seed_gujarat())
