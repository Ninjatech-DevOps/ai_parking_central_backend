"""
Seed detailed Ahmedabad data with proper areas at city, taluka, and village levels.
Idempotent — skips existing.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.session import async_session_factory
import src.app.models  # noqa

from src.app.models.state import State
from src.app.models.city import City
from src.app.models.taluka import Taluka
from src.app.models.village import Village
from src.app.models.area import Area

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_ahmedabad_detail")


async def get_or_create(db, model, filters, defaults=None):
    query = select(model)
    for k, v in filters.items():
        query = query.where(getattr(model, k) == v)
    result = await db.execute(query)
    inst = result.scalars().first()
    if inst:
        return inst, False
    inst = model(**{**filters, **(defaults or {})})
    db.add(inst)
    await db.flush()
    return inst, True


# Ahmedabad detailed data
AHMEDABAD_TALUKAS = {
    "Daskroi": {
        "taluka_areas": ["Daskroi Highway Junction", "Daskroi Industrial Area", "Daskroi Bus Stand"],
        "villages": {
            "Sanand": ["Sanand GIDC", "Sanand Village Road", "Sanand Crossroad", "Sanand Market Area"],
            "Bavla": ["Bavla Main Road", "Bavla Station Road", "Bavla Market"],
            "Bagodara": ["Bagodara Center", "Bagodara Highway", "Bagodara Village Road"],
        }
    },
    "Sanand": {
        "taluka_areas": ["Sanand GIDC Industrial Area", "Sanand-Viramgam Highway", "Sanand Toll Plaza Area"],
        "villages": {
            "Bol": ["Bol Village Center"],
            "Godhavi": ["Godhavi Main Road"],
            "Khoraj": ["Khoraj Highway", "Khoraj Village"],
        }
    },
    "Dholka": {
        "taluka_areas": ["Dholka Main Road", "Dholka Town Center", "Dholka Market Area"],
        "villages": {
            "Dholka": ["Dholka Bus Stand Area", "Dholka Railway Station"],
            "Kathlal": ["Kathlal Village Road"],
            "Dhanaj": ["Dhanaj Main Road"],
        }
    },
    "Viramgam": {
        "taluka_areas": ["Viramgam Station Area", "Viramgam Highway Junction"],
        "villages": {
            "Viramgam": ["Viramgam Station Road", "Viramgam Market", "Viramgam Old Town"],
            "Mandal": ["Mandal Village Center", "Mandal Crossroad"],
        }
    },
    "Dhandhuka": {
        "taluka_areas": ["Dhandhuka Main Road", "Dhandhuka Bus Terminal"],
        "villages": {
            "Dhandhuka": ["Dhandhuka Town Center", "Dhandhuka Market"],
            "Barwala": ["Barwala Main Road"],
        }
    },
    "Detroj-Rampura": {
        "taluka_areas": ["Detroj Junction", "Rampura Highway"],
        "villages": {
            "Detroj": ["Detroj Main Road", "Detroj Village Center"],
            "Rampura": ["Rampura Center", "Rampura Market"],
        }
    },
    "Bavla": {
        "taluka_areas": ["Bavla Town Center", "Bavla GIDC", "Bavla-Bagodara Road"],
        "villages": {
            "Changodar": ["Changodar GIDC", "Changodar Main Road"],
            "Jetalpur": ["Jetalpur Village Road"],
        }
    },
    "Ranpur": {
        "taluka_areas": ["Ranpur Main Road", "Ranpur Town Center"],
        "villages": {
            "Ranpur": ["Ranpur Center", "Ranpur Market Area"],
            "Limbdi": ["Limbdi Village Road"],
        }
    },
}


async def run():
    async with async_session_factory() as db:
        try:
            # Get Ahmedabad city
            result = await db.execute(select(City).where(City.name == "Ahmedabad"))
            city = result.scalars().first()
            if not city:
                logger.error("Ahmedabad city not found!")
                return

            total_taluka_areas = 0
            total_village_areas = 0

            for taluka_name, data in AHMEDABAD_TALUKAS.items():
                # Get or skip taluka
                result = await db.execute(
                    select(Taluka).where(Taluka.name == taluka_name, Taluka.city_id == city.id)
                )
                taluka = result.scalars().first()
                if not taluka:
                    logger.warning("Taluka %s not found, skipping", taluka_name)
                    continue

                # Add taluka-level areas (village_id = NULL)
                for area_name in data.get("taluka_areas", []):
                    _, created = await get_or_create(
                        db, Area,
                        filters={"name": area_name, "city_id": city.id, "taluka_id": taluka.id, "village_id": None},
                    )
                    if created:
                        total_taluka_areas += 1

                # Villages + their areas
                for village_name, village_areas in data.get("villages", {}).items():
                    village, _ = await get_or_create(
                        db, Village,
                        filters={"name": village_name, "taluka_id": taluka.id},
                    )

                    for area_name in village_areas:
                        _, created = await get_or_create(
                            db, Area,
                            filters={"name": area_name, "city_id": city.id, "taluka_id": taluka.id, "village_id": village.id},
                        )
                        if created:
                            total_village_areas += 1

            await db.commit()

            logger.info("")
            logger.info("=== Ahmedabad Detail Seed ===")
            logger.info("Taluka-level areas added: %d", total_taluka_areas)
            logger.info("Village-level areas added: %d", total_village_areas)
            logger.info("=============================")

        except Exception:
            await db.rollback()
            logger.exception("Seed failed")
            raise


if __name__ == "__main__":
    asyncio.run(run())
