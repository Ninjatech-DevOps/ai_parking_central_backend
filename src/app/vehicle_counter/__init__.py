"""Manual vehicle IN/OUT counter.

A self-contained module: an operator taps IN or OUT on a phone or tablet and
one row is logged per tap. Used at gates with no ANPR camera, during a device
outage, or at sites not yet fitted with hardware.

Deliberately isolated from the rest of the application:

* Its own SQLite database (see ``db.py``) -- NOT the shared Postgres.
* Its own declarative base, so Alembic never sees these tables.
* Its own top-level route prefix (``/vehicle-counter``), not ``/api/v1``.
* No authentication at all.

The whole module can be removed by deleting this package and the
``vehicle_counter`` lines in ``src/app/main.py``.
"""
