from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import os

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─────────────────────────────────────────
# COLUMN NORMALIZATION
# ─────────────────────────────────────────
COLUMN_MAP = {
    # rack id aliases
    "rack":         "rack_id",
    "rackid":       "rack_id",
    "rack id":      "rack_id",
    "rack_no":      "rack_id",
    "rack_number":  "rack_id",
    "bin":          "rack_id",
    "bin_id":       "rack_id",
    "location":     "rack_id",
    "slot":         "rack_id",
    "id":           "rack_id",
    # quantity aliases
    "qty":          "quantity",
    "stock":        "quantity",
    "units":        "quantity",
    "items":        "quantity",
    "count":        "quantity",
    "stored":       "quantity",
    "filled":       "quantity",
    # capacity aliases
    "cap":          "capacity",
    "max":          "capacity",
    "max_capacity": "capacity",
    "limit":        "capacity",
    "total":        "capacity",
    "max_qty":      "capacity",
    # zone aliases
    "area":         "zone",
    "section":      "zone",
    "aisle":        "zone",
    "row":          "zone",
    "warehouse":    "zone",
    # priority aliases
    "prio":         "priority",
    "importance":   "priority",
    "urgency":      "priority",
}

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.lower().str.strip().str.replace(r'\s+', '_', regex=True)
    df = df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})
    return df

# ─────────────────────────────────────────
# STATUS + UTILIZATION
# ─────────────────────────────────────────
def get_color(utilization: float) -> str:
    if utilization == 0:    return "#39d353"
    if utilization <= 30:   return "#7ee787"
    if utilization <= 70:   return "#f0a500"
    if utilization <= 100:  return "#f85149"
    return "#bc8cff"

def add_utilization(df: pd.DataFrame) -> pd.DataFrame:
    df["utilization"] = (df["quantity"] / df["capacity"] * 100).round(2)
    df["status"]      = df["utilization"].apply(get_color)
    return df

# ─────────────────────────────────────────
# ZONE STATS
# ─────────────────────────────────────────
def compute_zone_stats(df: pd.DataFrame) -> list:
    stats = []
    for zone, group in df.groupby("zone"):
        stats.append({
            "zone":             str(zone),
            "rack_count":       int(len(group)),
            "avg_utilization":  round(float(group["utilization"].mean()), 1),
            "max_utilization":  round(float(group["utilization"].max()), 1),
            "total_quantity":   int(group["quantity"].sum()),
            "total_capacity":   int(group["capacity"].sum()),
            "overloaded_racks": int((group["utilization"] > 100).sum()),
            "empty_racks":      int((group["quantity"] == 0).sum()),
        })
    return sorted(stats, key=lambda x: x["avg_utilization"], reverse=True)

# ─────────────────────────────────────────
# INSIGHTS GENERATION
# ─────────────────────────────────────────
def generate_insights(df: pd.DataFrame) -> list:
    insights = []

    overloaded = df[df["quantity"] > df["capacity"]]
    unused     = df[df["quantity"] == 0]
    low        = df[(df["utilization"] > 0) & (df["utilization"] <= 30)]
    critical   = df[df["utilization"] >= 90]

    # Overloaded
    if len(overloaded):
        ids = ", ".join(overloaded["rack_id"].astype(str).head(3).tolist())
        insights.append(
            f"{len(overloaded)} rack(s) overloaded — redistribute load immediately ({ids})"
        )

    # Unused
    if len(unused):
        pct = round(len(unused) / len(df) * 100, 1)
        insights.append(
            f"{len(unused)} rack(s) idle ({pct}% of total) — optimize allocation"
        )

    # Critical (≥90%) but not overloaded
    nearing = df[(df["utilization"] >= 90) & (df["utilization"] <= 100)]
    if len(nearing):
        insights.append(
            f"{len(nearing)} rack(s) nearing capacity (≥90%) — plan redistribution soon"
        )

    # Zone imbalance
    if "zone" in df.columns:
        zone_avg = df.groupby("zone")["utilization"].mean()
        if len(zone_avg) > 1:
            worst_zone = zone_avg.idxmax()
            best_zone  = zone_avg.idxmin()
            gap        = round(zone_avg.max() - zone_avg.min(), 1)
            if gap > 30:
                insights.append(
                    f"Zone {worst_zone} avg {zone_avg.max():.0f}% vs Zone {best_zone} avg {zone_avg.min():.0f}% — {gap}pt imbalance, rebalance load"
                )

    # Low utilization zones
    if len(low) > len(df) * 0.4:
        insights.append("Over 40% of racks underutilized — consider consolidating inventory")

    # All good
    if not insights:
        avg_u = df["utilization"].mean()
        insights.append(f"Warehouse balanced — avg utilization {avg_u:.1f}%")

    return insights

# ─────────────────────────────────────────
# PROCESS FILE
# ─────────────────────────────────────────
def process_file(filepath: str) -> dict:
    try:
        if filepath.endswith(".csv"):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
    except Exception as e:
        return {"error": f"Could not read file: {str(e)}"}

    df = normalize_columns(df)

    # Apply defaults for missing columns
    if "capacity" not in df.columns:
        df["capacity"] = 100
    if "zone" not in df.columns:
        df["zone"] = "A"
    if "priority" not in df.columns:
        df["priority"] = "Normal"

    # Validate required columns
    for col in ["rack_id", "quantity", "capacity"]:
        if col not in df.columns:
            return {"error": f"Missing required column: '{col}'. Found: {list(df.columns)}"}

    # Clean numeric columns
    for col in ["quantity", "capacity"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Prevent division by zero
    df["capacity"] = df["capacity"].replace(0, 100)

    df = add_utilization(df)

    insights   = generate_insights(df)
    zone_stats = compute_zone_stats(df)
    top_racks  = df.sort_values("utilization", ascending=False).head(5)["rack_id"].tolist()

    # Overall stats
    summary = {
        "total_racks":      int(len(df)),
        "avg_utilization":  round(float(df["utilization"].mean()), 1),
        "total_quantity":   int(df["quantity"].sum()),
        "total_capacity":   int(df["capacity"].sum()),
        "overloaded_count": int((df["utilization"] > 100).sum()),
        "empty_count":      int((df["quantity"] == 0).sum()),
        "full_count":       int(((df["utilization"] > 70) & (df["utilization"] <= 100)).sum()),
    }

    return {
        "data":       df.to_dict(orient="records"),
        "insights":   insights,
        "top_racks":  top_racks,
        "zone_stats": zone_stats,
        "summary":    summary,
    }

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────
@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    allowed = {".csv", ".xlsx", ".xls"}
    ext     = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return jsonify({"error": f"Unsupported file type '{ext}'. Use CSV or Excel."}), 400

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    result = process_file(filepath)

    if "error" in result:
        return jsonify(result), 422

    return jsonify(result), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────────────
# RUN
# ─────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5000)
