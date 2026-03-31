"""
Grocery Deal Hunter API Server
POST /run-grocery-optimizer endpoint
Returns structured JSON for FlutterFlow integration.
"""

import json
import uuid
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="Grocery Deal Hunter API",
    description="API endpoint for the Grocery Deal Hunter workflow. Accepts a grocery list and returns optimized shopping results.",
    version="1.0.0",
)

# Allow all origins for FlutterFlow access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ────────────────────────────────────────────────

class GroceryOptimizerRequest(BaseModel):
    list_name: str = Field(default="My Grocery List", description="Name for this shopping list")
    grocery_list_text: str = Field(..., description="Grocery items, one per line")
    location: str = Field(default="Amsterdam, Netherlands", description="City or region for localized searches")
    radius_km: float = Field(default=5.0, ge=0.5, le=50.0, description="Max search radius in km")
    shopping_mode: str = Field(default="one_time", description="one_time | weekly")
    optimization_strategy: str = Field(default="balanced", description="single_store | multi_store | balanced")


class ItemResult(BaseModel):
    name: str
    store: str
    old_price: float
    new_price: float
    discount_label: str
    image_url: str


class StoreResult(BaseModel):
    store_name: str
    total: float


class SummaryResult(BaseModel):
    total_cost: float
    savings: float
    savings_percent: float
    recommended_strategy: str
    route_text: str


class GroceryOptimizerResponse(BaseModel):
    summary: SummaryResult
    items: list[ItemResult]
    stores: list[StoreResult]
    pdf_url: str


# ── Simulated price database (real implementation would query MCP tools) ─────

# Regional store catalogs with typical Dutch supermarket pricing
STORE_CATALOGS = {
    "Albert Heijn": {
        "milk": {"regular": 1.89, "promo": 1.49, "discount": "21% off", "category": "Dairy"},
        "bread": {"regular": 2.29, "promo": 2.29, "discount": "", "category": "Bakery"},
        "eggs": {"regular": 3.99, "promo": 3.49, "discount": "13% off", "category": "Dairy"},
        "chicken breast": {"regular": 8.99, "promo": 6.49, "discount": "28% off", "category": "Meat"},
        "apples": {"regular": 2.49, "promo": 1.99, "discount": "20% off", "category": "Produce"},
        "rice": {"regular": 2.79, "promo": 2.79, "discount": "", "category": "Pantry"},
        "pasta": {"regular": 1.49, "promo": 0.99, "discount": "34% off", "category": "Pantry"},
        "tomatoes": {"regular": 2.99, "promo": 1.99, "discount": "33% off", "category": "Produce"},
        "cheese": {"regular": 4.99, "promo": 3.99, "discount": "20% off", "category": "Dairy"},
        "butter": {"regular": 2.49, "promo": 1.99, "discount": "20% off", "category": "Dairy"},
        "yogurt": {"regular": 1.99, "promo": 1.49, "discount": "25% off", "category": "Dairy"},
        "orange juice": {"regular": 2.29, "promo": 1.79, "discount": "22% off", "category": "Beverages"},
        "coffee": {"regular": 9.49, "promo": 9.49, "discount": "", "category": "Beverages"},
        "potatoes": {"regular": 2.49, "promo": 1.99, "discount": "20% off", "category": "Produce"},
        "onions": {"regular": 1.49, "promo": 0.99, "discount": "34% off", "category": "Produce"},
        "bananas": {"regular": 1.79, "promo": 1.29, "discount": "28% off", "category": "Produce"},
        "salmon": {"regular": 7.99, "promo": 5.99, "discount": "25% off", "category": "Fish"},
        "olive oil": {"regular": 5.99, "promo": 4.49, "discount": "25% off", "category": "Pantry"},
    },
    "Jumbo": {
        "milk": {"regular": 1.79, "promo": 1.79, "discount": "", "category": "Dairy"},
        "bread": {"regular": 1.99, "promo": 1.49, "discount": "25% off", "category": "Bakery"},
        "eggs": {"regular": 3.49, "promo": 2.99, "discount": "14% off", "category": "Dairy"},
        "chicken breast": {"regular": 9.29, "promo": 9.29, "discount": "", "category": "Meat"},
        "apples": {"regular": 2.29, "promo": 2.29, "discount": "", "category": "Produce"},
        "rice": {"regular": 2.49, "promo": 1.99, "discount": "20% off", "category": "Pantry"},
        "pasta": {"regular": 1.29, "promo": 1.29, "discount": "", "category": "Pantry"},
        "tomatoes": {"regular": 2.79, "promo": 2.79, "discount": "", "category": "Produce"},
        "cheese": {"regular": 4.49, "promo": 3.49, "discount": "22% off", "category": "Dairy"},
        "butter": {"regular": 2.29, "promo": 2.29, "discount": "", "category": "Dairy"},
        "yogurt": {"regular": 1.79, "promo": 1.79, "discount": "", "category": "Dairy"},
        "orange juice": {"regular": 1.99, "promo": 1.99, "discount": "", "category": "Beverages"},
        "coffee": {"regular": 8.99, "promo": 6.29, "discount": "30% off", "category": "Beverages"},
        "potatoes": {"regular": 2.29, "promo": 2.29, "discount": "", "category": "Produce"},
        "onions": {"regular": 1.29, "promo": 1.29, "discount": "", "category": "Produce"},
        "bananas": {"regular": 1.69, "promo": 1.69, "discount": "", "category": "Produce"},
        "salmon": {"regular": 8.49, "promo": 8.49, "discount": "", "category": "Fish"},
        "olive oil": {"regular": 5.49, "promo": 5.49, "discount": "", "category": "Pantry"},
    },
    "Lidl": {
        "milk": {"regular": 1.59, "promo": 1.59, "discount": "", "category": "Dairy"},
        "bread": {"regular": 1.39, "promo": 1.39, "discount": "", "category": "Bakery"},
        "eggs": {"regular": 2.99, "promo": 2.49, "discount": "17% off", "category": "Dairy"},
        "chicken breast": {"regular": 7.49, "promo": 7.49, "discount": "", "category": "Meat"},
        "apples": {"regular": 1.99, "promo": 1.49, "discount": "25% off", "category": "Produce"},
        "rice": {"regular": 1.99, "promo": 1.99, "discount": "", "category": "Pantry"},
        "pasta": {"regular": 0.89, "promo": 0.89, "discount": "", "category": "Pantry"},
        "tomatoes": {"regular": 2.49, "promo": 2.49, "discount": "", "category": "Produce"},
        "cheese": {"regular": 3.99, "promo": 3.99, "discount": "", "category": "Dairy"},
        "butter": {"regular": 1.99, "promo": 1.99, "discount": "", "category": "Dairy"},
        "yogurt": {"regular": 1.49, "promo": 1.49, "discount": "", "category": "Dairy"},
        "orange juice": {"regular": 1.79, "promo": 1.79, "discount": "", "category": "Beverages"},
        "coffee": {"regular": 7.99, "promo": 7.99, "discount": "", "category": "Beverages"},
        "potatoes": {"regular": 1.99, "promo": 1.49, "discount": "25% off", "category": "Produce"},
        "onions": {"regular": 0.99, "promo": 0.99, "discount": "", "category": "Produce"},
        "bananas": {"regular": 1.49, "promo": 1.19, "discount": "20% off", "category": "Produce"},
        "salmon": {"regular": 6.99, "promo": 4.99, "discount": "29% off", "category": "Fish"},
        "olive oil": {"regular": 4.99, "promo": 4.99, "discount": "", "category": "Pantry"},
    },
    "Dirk": {
        "milk": {"regular": 1.69, "promo": 1.19, "discount": "30% off", "category": "Dairy"},
        "bread": {"regular": 1.59, "promo": 1.59, "discount": "", "category": "Bakery"},
        "eggs": {"regular": 3.29, "promo": 3.29, "discount": "", "category": "Dairy"},
        "chicken breast": {"regular": 8.49, "promo": 8.49, "discount": "", "category": "Meat"},
        "apples": {"regular": 2.19, "promo": 2.19, "discount": "", "category": "Produce"},
        "rice": {"regular": 2.29, "promo": 2.29, "discount": "", "category": "Pantry"},
        "pasta": {"regular": 1.19, "promo": 1.19, "discount": "", "category": "Pantry"},
        "tomatoes": {"regular": 2.69, "promo": 2.69, "discount": "", "category": "Produce"},
        "cheese": {"regular": 4.29, "promo": 4.29, "discount": "", "category": "Dairy"},
        "butter": {"regular": 2.19, "promo": 1.79, "discount": "18% off", "category": "Dairy"},
        "yogurt": {"regular": 1.69, "promo": 1.69, "discount": "", "category": "Dairy"},
        "orange juice": {"regular": 2.09, "promo": 2.09, "discount": "", "category": "Beverages"},
        "coffee": {"regular": 8.49, "promo": 8.49, "discount": "", "category": "Beverages"},
        "potatoes": {"regular": 2.19, "promo": 2.19, "discount": "", "category": "Produce"},
        "onions": {"regular": 1.19, "promo": 1.19, "discount": "", "category": "Produce"},
        "bananas": {"regular": 1.59, "promo": 1.59, "discount": "", "category": "Produce"},
        "salmon": {"regular": 7.49, "promo": 7.49, "discount": "", "category": "Fish"},
        "olive oil": {"regular": 5.29, "promo": 5.29, "discount": "", "category": "Pantry"},
    },
}


def normalize_item(raw: str) -> str:
    """Normalize an item name for catalog lookup."""
    import re
    cleaned = raw.strip().lower()
    # Split into tokens, remove numeric tokens and unit-only tokens
    units = {"kg", "g", "l", "ml", "liter", "liters", "pc", "pcs", "pieces", "pack", "loaf", "dozen"}
    tokens = cleaned.split()
    kept = []
    for token in tokens:
        # Skip pure numbers like "2" or "500" or "2.5"
        if re.fullmatch(r"[\d.,]+", token):
            continue
        # Skip number+unit combos like "2L", "500g", "12pc"
        if re.fullmatch(r"[\d.,]+\s*(" + "|".join(units) + r")", token):
            continue
        # Skip standalone units
        if token in units:
            continue
        kept.append(token)
    cleaned = " ".join(kept)
    return cleaned


def find_cheapest(item_key: str, strategy: str):
    """Find cheapest store for an item across all stores."""
    results = []
    for store_name, catalog in STORE_CATALOGS.items():
        if item_key in catalog:
            entry = catalog[item_key]
            results.append({
                "store": store_name,
                "regular": entry["regular"],
                "promo": entry["promo"],
                "discount": entry["discount"],
            })
    if not results:
        return None
    # Sort by promo price
    results.sort(key=lambda x: x["promo"])
    return results


def optimize_grocery_list(req: GroceryOptimizerRequest) -> GroceryOptimizerResponse:
    """Core optimization engine."""
    raw_items = [line.strip() for line in req.grocery_list_text.strip().splitlines() if line.strip()]

    optimized_items: list[ItemResult] = []
    store_totals: dict[str, float] = {}
    total_regular = 0.0
    total_optimized = 0.0

    for raw in raw_items:
        item_key = normalize_item(raw)
        candidates = find_cheapest(item_key, req.optimization_strategy)

        if candidates:
            if req.optimization_strategy == "single_store":
                # Find the store where sum of all items is cheapest (simplified: pick most common cheapest)
                best = candidates[0]
            elif req.optimization_strategy == "multi_store":
                best = candidates[0]  # absolute cheapest per item
            else:  # balanced
                best = candidates[0]  # cheapest, but later we cap stores

            old_price = best["regular"]
            new_price = best["promo"]
            discount_label = best["discount"] if best["discount"] else "Regular price"
            store = best["store"]
        else:
            # Item not found in catalog – estimate
            old_price = 3.00
            new_price = 3.00
            discount_label = "Price estimate"
            store = "Albert Heijn"

        total_regular += old_price
        total_optimized += new_price
        store_totals[store] = store_totals.get(store, 0.0) + new_price

        optimized_items.append(ItemResult(
            name=raw.strip(),
            store=store,
            old_price=round(old_price, 2),
            new_price=round(new_price, 2),
            discount_label=discount_label,
            image_url="",
        ))

    # For single_store strategy: reassign all items to the store with lowest aggregate
    if req.optimization_strategy == "single_store" and store_totals:
        # Recalculate: for each item find price at each store, then pick store with lowest total
        store_agg: dict[str, float] = {}
        for store_name in STORE_CATALOGS:
            agg = 0.0
            for raw in raw_items:
                item_key = normalize_item(raw)
                if item_key in STORE_CATALOGS[store_name]:
                    agg += STORE_CATALOGS[store_name][item_key]["promo"]
                else:
                    agg += 3.00
            store_agg[store_name] = agg

        best_store = min(store_agg, key=store_agg.get)
        # Reassign all items
        store_totals = {}
        total_optimized = 0.0
        total_regular = 0.0
        new_items = []
        for raw in raw_items:
            item_key = normalize_item(raw)
            if item_key in STORE_CATALOGS[best_store]:
                entry = STORE_CATALOGS[best_store][item_key]
                old_price = entry["regular"]
                new_price = entry["promo"]
                discount_label = entry["discount"] if entry["discount"] else "Regular price"
            else:
                old_price = 3.00
                new_price = 3.00
                discount_label = "Price estimate"

            total_regular += old_price
            total_optimized += new_price
            store_totals[best_store] = store_totals.get(best_store, 0.0) + new_price

            new_items.append(ItemResult(
                name=raw.strip(),
                store=best_store,
                old_price=round(old_price, 2),
                new_price=round(new_price, 2),
                discount_label=discount_label,
                image_url="",
            ))
        optimized_items = new_items

    # For balanced strategy: cap at 2-3 stores
    if req.optimization_strategy == "balanced" and len(store_totals) > 3:
        # Keep top 3 stores by number of items, reassign rest
        store_item_counts = {}
        for item in optimized_items:
            store_item_counts[item.store] = store_item_counts.get(item.store, 0) + 1
        top_stores = sorted(store_item_counts, key=store_item_counts.get, reverse=True)[:3]

        store_totals = {}
        total_optimized = 0.0
        total_regular = 0.0
        new_items = []
        for itm in optimized_items:
            if itm.store in top_stores:
                new_items.append(itm)
                total_regular += itm.old_price
                total_optimized += itm.new_price
                store_totals[itm.store] = store_totals.get(itm.store, 0.0) + itm.new_price
            else:
                # Reassign to cheapest among top stores
                item_key = normalize_item(itm.name)
                best_price = 999.0
                best_store = top_stores[0]
                best_regular = itm.old_price
                best_discount = "Regular price"
                for ts in top_stores:
                    if item_key in STORE_CATALOGS[ts]:
                        p = STORE_CATALOGS[ts][item_key]["promo"]
                        if p < best_price:
                            best_price = p
                            best_store = ts
                            best_regular = STORE_CATALOGS[ts][item_key]["regular"]
                            best_discount = STORE_CATALOGS[ts][item_key]["discount"] or "Regular price"
                if best_price == 999.0:
                    best_price = 3.00
                    best_regular = 3.00
                total_regular += best_regular
                total_optimized += best_price
                store_totals[best_store] = store_totals.get(best_store, 0.0) + best_price
                new_items.append(ItemResult(
                    name=itm.name,
                    store=best_store,
                    old_price=round(best_regular, 2),
                    new_price=round(best_price, 2),
                    discount_label=best_discount,
                    image_url="",
                ))
        optimized_items = new_items

    savings = total_regular - total_optimized
    savings_pct = (savings / total_regular * 100) if total_regular > 0 else 0.0

    # Build route text
    store_names = list(store_totals.keys())
    if len(store_names) == 1:
        route_text = f"Visit {store_names[0]} to buy all items."
    else:
        route_text = "Recommended route: " + " -> ".join(store_names) + f" ({len(store_names)} stops)"

    strategy_labels = {
        "single_store": "Single Store",
        "multi_store": "Multi-Store",
        "balanced": "Balanced (2-3 stores)",
    }

    summary = SummaryResult(
        total_cost=round(total_optimized, 2),
        savings=round(savings, 2),
        savings_percent=round(savings_pct, 1),
        recommended_strategy=strategy_labels.get(req.optimization_strategy, req.optimization_strategy),
        route_text=route_text,
    )

    stores = [
        StoreResult(store_name=name, total=round(total, 2))
        for name, total in sorted(store_totals.items(), key=lambda x: -x[1])
    ]

    return GroceryOptimizerResponse(
        summary=summary,
        items=optimized_items,
        stores=stores,
        pdf_url="",
    )


# ── API Endpoints ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "Grocery Deal Hunter API",
        "version": "1.0.0",
        "endpoint": "POST /run-grocery-optimizer",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/run-grocery-optimizer", response_model=GroceryOptimizerResponse)
async def run_grocery_optimizer(req: GroceryOptimizerRequest):
    """
    Run the Grocery Deal Hunter optimization workflow.

    Accepts a grocery list and returns optimized shopping results
    with price comparisons, store assignments, and savings analysis.
    """
    if not req.grocery_list_text.strip():
        raise HTTPException(status_code=400, detail="grocery_list_text cannot be empty")

    items = [l.strip() for l in req.grocery_list_text.strip().splitlines() if l.strip()]
    if len(items) == 0:
        raise HTTPException(status_code=400, detail="No valid grocery items found in the list")

    if req.optimization_strategy not in ("single_store", "multi_store", "balanced"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid optimization_strategy '{req.optimization_strategy}'. Use: single_store, multi_store, or balanced",
        )

    result = optimize_grocery_list(req)
    return result


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
