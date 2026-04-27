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

# ---------- STATUS ----------
def add_status(df):
    def get_status(row):
        usage = row['quantity'] / row['capacity']

        if usage == 0:
            return "green"
        elif usage <= 0.7:
            return "yellow"
        elif usage <= 1:
            return "red"
        else:
            return "purple"

    df['status'] = df.apply(get_status, axis=1)
    return df

# ---------- INSIGHTS ----------
def get_insights(df):
    insights = []

    if (df['quantity'] > df['capacity']).any():
        insights.append("Overloaded racks detected")

    if (df['quantity'] == 0).any():
        insights.append("Unused racks available")

    return insights

# ---------- PROCESS FILE ----------
def process_file(filepath):
    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)

    errors = validate(df)
    df = add_status(df)
    insights = get_insights(df)

    return {
        "data": df.to_dict(orient='records'),
        "errors": errors,
        "insights": insights
    }

# ---------- DEFAULT API ----------
@app.route('/data')
def get_data():
    file_path = os.path.join(os.path.dirname(__file__), 'data.xlsx')
    return jsonify(process_file(file_path))

# ---------- UPLOAD API ----------
@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    return jsonify(process_file(filepath))

# ---------- RUN ----------
if __name__ == '__main__':
    app.run(debug=True)