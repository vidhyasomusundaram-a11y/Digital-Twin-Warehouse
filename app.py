from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import os

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- VALIDATION ----------
def validate(df):
    errors = []

    if df.isnull().values.any():
        errors.append("Missing values found")

    if df.duplicated().any():
        errors.append("Duplicate entries found")

    return errors

# ---------- STATUS (HEATMAP COLORS) ----------
def add_status(df):
    def get_status(row):
        try:
            usage = row['quantity'] / row['capacity']
        except:
            return "#9e9e9e"  # fallback gray

        if usage == 0:
            return "#4caf50"   # green
        elif usage <= 0.3:
            return "#8bc34a"   # light green
        elif usage <= 0.7:
            return "#ffc107"   # yellow
        elif usage <= 1:
            return "#f44336"   # red
        else:
            return "#9c27b0"   # purple (overloaded)

    df['status'] = df.apply(get_status, axis=1)
    return df

# ---------- INSIGHTS ----------
def get_insights(df):
    insights = []

    overloaded_count = (df['quantity'] > df['capacity']).sum()
    unused_count = (df['quantity'] == 0).sum()

    if overloaded_count > 0:
        insights.append(f"{overloaded_count} racks overloaded")

    if unused_count > 0:
        insights.append(f"{unused_count} racks unused")

    return insights

# ---------- PROCESS FILE ----------
def process_file(filepath):
    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)

        # Ensure required columns exist
        required_cols = ['rack_id', 'capacity', 'quantity']
        for col in required_cols:
            if col not in df.columns:
                return {"error": f"Missing column: {col}"}

        errors = validate(df)
        df = add_status(df)
        insights = get_insights(df)

        return {
            "data": df.to_dict(orient='records'),
            "errors": errors,
            "insights": insights
        }

    except Exception as e:
        return {"error": str(e)}

# ---------- DEFAULT API ----------
@app.route('/data')
def get_data():
    file_path = os.path.join(os.path.dirname(__file__), 'data.xlsx')
    return jsonify(process_file(file_path))

# ---------- UPLOAD API ----------
@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        file = request.files['file']

        if file.filename == '':
            return jsonify({"error": "No file selected"})

        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        return jsonify(process_file(filepath))

    except Exception as e:
        return jsonify({"error": str(e)})

# ---------- RUN ----------
if __name__ == '__main__':
    app.run(debug=True)