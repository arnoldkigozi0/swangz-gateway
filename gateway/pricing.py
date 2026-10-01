"""What each request cost, in US dollars.

Prices are per million tokens and live in the database so an admin can correct them. The seed
below is Anthropic's first-party list price (checked 2026-10-01). Cache writes are 1.25x input for
the 5-minute cache and 2x for the 1-hour cache; cache reads are listed per model because the newest
models discount them further. Models with no price row are still logged — tokens are counted and
the cost shows as "unpriced" until someone adds a row. Nothing is guessed.
"""

import time

# model, provider, input, output, cache write 5m, cache write 1h, cache read
SEED = [
    ("claude-fable-5-1", "anthropic", 10.0, 50.0, 12.5, 20.0, 0.25),
    ("claude-mythos-5-1", "anthropic", 10.0, 50.0, 12.5, 20.0, 0.25),
    ("claude-fable-5", "anthropic", 10.0, 50.0, 12.5, 20.0, 1.0),
    ("claude-mythos-5", "anthropic", 10.0, 50.0, 12.5, 20.0, 1.0),
    ("claude-opus-5-5", "anthropic", 4.0, 20.0, 5.0, 8.0, 0.20),
    ("claude-opus-5", "anthropic", 5.0, 25.0, 6.25, 10.0, 0.50),
    ("claude-opus-4-8", "anthropic", 5.0, 25.0, 6.25, 10.0, 0.50),
    ("claude-opus-4-7", "anthropic", 5.0, 25.0, 6.25, 10.0, 0.50),
    ("claude-opus-4-6", "anthropic", 5.0, 25.0, 6.25, 10.0, 0.50),
    ("claude-sonnet-5-5", "anthropic", 2.0, 10.0, 2.5, 4.0, 0.20),
    ("claude-sonnet-5", "anthropic", 2.0, 10.0, 2.5, 4.0, 0.20),
    ("claude-sonnet-4-6", "anthropic", 3.0, 15.0, 3.75, 6.0, 0.30),
    ("claude-haiku-4-5", "anthropic", 1.0, 5.0, 1.25, 2.0, 0.10),
]

FAST_MULTIPLIER = 2.0  # Anthropic fast mode bills the same model at twice the per-token rate


def seed(db):
    if db.get_setting("prices_seeded") == "1":
        return
    now = time.time()
    with db.tx():
        for model, provider, i, o, cw, cw1h, cr in SEED:
            db.x(
                "INSERT OR IGNORE INTO prices(model, provider, input, output, cache_write, cache_write_1h, cache_read, updated)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (model, provider, i, o, cw, cw1h, cr, now),
            )
        db.set_setting("prices_seeded", "1")


def find_price(prices, model):
    """Exact id first, then the longest listed id the model starts with (dated snapshots, suffixes)."""
    if not model:
        return None
    model = model.strip()
    if model in prices:
        return prices[model]
    best = None
    for name in prices:
        if model.startswith(name + "-") or model.startswith(name + "@") or model.startswith(name + "["):
            if best is None or len(name) > len(best):
                best = name
    return prices[best] if best else None


def cost(price, usage):
    """USD for one request, or None when the model has no price row."""
    if price is None:
        return None
    inp = price["input"]
    total = (
        usage["input"] * inp
        + usage["output"] * price["output"]
        + usage["cache_write"] * (price["cache_write"] if price["cache_write"] is not None else inp * 1.25)
        + usage["cache_write_1h"] * (price["cache_write_1h"] if price["cache_write_1h"] is not None else inp * 2.0)
        + usage["cache_read"] * (price["cache_read"] if price["cache_read"] is not None else inp)
    ) / 1_000_000
    if usage.get("speed") == "fast":
        total *= FAST_MULTIPLIER
    return round(total, 6)


def load(db):
    return {row["model"]: row for row in db.q("SELECT * FROM prices")}
