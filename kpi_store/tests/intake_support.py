"""Made-up pick lists and filled forms for the intake tests, in the real shapes.

The tests of the check use the release's own catalogue (kpi-intake/catalogue.toml and settings.toml) with these
small lists, written by hand. So they do not change when a module is released. Every name here is invented,
except the settings file's domain ids, which the catalogue's example list holds.
"""
import copy

from kpi_store.intake.answers import Intake

X = "https://example.org/"
AREA_SUPPLY, AREA_SALES = X + "area/supply", X + "area/sales"
P_PLAN, P_PLAN_STEP, P_SELL, P_SELL_STEP, P_BARE = X + "p/plan", X + "p/plan-step", X + "p/sell", X + "p/sell-step", X + "p/bare"
M_TURNS, M_FILL = X + "m/tank-turns", X + "m/fill-rate"
ROLE_PLANNER, ROLE_CLERK = X + "role/planner", X + "role/clerk"
STEP_SHIP, STEP_BILL = X + "vs/ship", X + "vs/bill"
REL_INFORMS = X + "rel/informs"
PRODUCT, TABLE, LAYER_GOLD, LAYER_REPLICA, KIND_DERIVED, SYSTEM, SOURCE = (
    X + "dp/stock", X + "t/stock_vw", X + "layer/gold", X + "layer/replica", X + "kind/derived", X + "sys/erp", X + "src/manual")


def _process(pid, label, level, parent, area, areas):
    return {"id": pid, "label": label, "level": level, "parent": parent, "area": area, "areas": areas}


def lists():
    """Small pick lists: two business areas, a process tree of five entries, two measures, and one or two of each
    other kind."""
    areas = [{"id": AREA_SUPPLY, "label": "Supply", "in_use": True}, {"id": AREA_SALES, "label": "Sales", "in_use": True}]
    return {
        "business-areas": areas,
        "processes": [
            _process(P_PLAN, "S 1 Plan Stock", 2, "", "", [AREA_SUPPLY]),
            _process(P_PLAN_STEP, "S 1.1 Count Tanks", 4, P_PLAN, AREA_SUPPLY, [AREA_SUPPLY]),
            _process(P_SELL, "M 1 Sell Product", 2, "", "", [AREA_SALES]),
            _process(P_SELL_STEP, "M 1.1 Quote Price", 4, P_SELL, AREA_SALES, [AREA_SALES]),
            _process(P_BARE, "X 1 Unowned Work (deprecated)", 2, "", "", []),
        ],
        "measures": [
            {"id": M_TURNS, "label": "Tank Turns", "notation": "tank-turns", "other_names": ["stock turn"],
             "definition": "How often the stored volume is replaced in a month."},
            {"id": M_FILL, "label": "Fill Rate", "notation": "fill-rate", "other_names": [], "definition": "The share of orders shipped in full."},
        ],
        "roles": [{"id": ROLE_PLANNER, "label": "Stock Planner", "group": "Planning persona"},
                  {"id": ROLE_CLERK, "label": "Billing Clerk", "group": "Role register"}],
        "value-stream-steps": [{"id": STEP_SHIP, "label": "Ship Order", "group": "Order to Cash", "stage": "Deliver"},
                               {"id": STEP_BILL, "label": "Bill Order", "group": "Order to Cash", "stage": "Invoice"}],
        "measure-relationships": [{"id": REL_INFORMS, "label": "Informs: The process uses the measure as an input."}],
        "data-products": [{"id": PRODUCT, "label": "Stock Levels"}],
        "platform-tables": [{"id": TABLE, "label": "lake.gold.stock_vw", "layer": LAYER_GOLD, "product": PRODUCT}],
        "layers": [{"id": LAYER_GOLD, "label": "Gold"}, {"id": LAYER_REPLICA, "label": "Replica"}],
        "data-product-kinds": [{"id": KIND_DERIVED, "label": "Derived data product"}],
        "systems": [{"id": SYSTEM, "label": "Stock Ledger"}],
        "sources": [{"id": SOURCE, "label": "Stock manual, 2026 edition", "tier": "industry"}],
        "modules": [{"id": "core", "label": "core"}, {"id": "kpi", "label": "kpi"}],
        "areas-and-modules": [{"id": a["id"], "label": "Business area: " + a["label"]} for a in areas],
    }


def data(terms=()):
    """The lists in the shape of pick-lists.json."""
    return {"release": "A made-up release", "versions": {"core": "1.0.0", "kpi": "1.0.0"}, "lists": lists(), "terms": list(terms)}


COMPLETE = {
    "1.1": AREA_SUPPLY, "1.2": P_PLAN, "1.3": P_PLAN_STEP, "1.4": "Planners decide when to order more.", "1.5": "market-price",
    "2.1": "Days of Cover", "2.2": "How many days the stock on hand lasts at the planned rate of use.",
    "2.5": "Never run a site out of stock.",
    "3.1": "Stock on hand divided by planned daily use.", "3.2": "days", "3.3": "Daily, by site.",
    "3.5": [SOURCE], "3.5.detail": "Chapter 3, page 12.", "3.7": "anyone", "3.8": "One value for each day and each tank.", "3.9": "draft",
    "4.1": "yes", "4.2": "no", "4.3": "no", "4.4": "no", "4.5": "no", "4.6": "no", "4.7": "no",
    "4.8": "It is a ratio with no target and no named owner.",
    "5.4": "none", "6.1": [ROLE_PLANNER], "6.8": "Stock Planning Lead", "6.9": "Stock Planner", "7.1": "@no-data-yet",
}
SIGNED = {"data-owner": {"name": "A signer", "date": "2026-11-11"},
          "domain-confirmation": {"name": "A second signer", "date": "2026-11-11"},
          "architect": {"name": "A third signer", "date": "2026-11-12"}}


def intake(change=None, remove=(), sign_offs=None, **fields):
    """The complete, signed KPI form, with some answers changed or removed."""
    answers = copy.deepcopy(COMPLETE)
    answers.update(change or {})
    for key in remove:
        answers.pop(key, None)
    return Intake(form="kpi-intake", catalogue_version="1.1", kpi_name=answers.get("2.1", ""), answers=answers,
                  sign_offs=copy.deepcopy(SIGNED if sign_offs is None else sign_offs), **fields)
