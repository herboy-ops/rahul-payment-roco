import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from flask import Flask, request, render_template, redirect, url_for, send_from_directory, session

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['RESULT_FOLDER'] = 'static/results/'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULT_FOLDER'], exist_ok=True)
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv', 'txt'}

# Helpers
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def read_file(file_path):
    ext = file_path.rsplit('.', 1)[1].lower()
    try:
        if ext in ['xlsx', 'xls']:
            return pd.read_excel(file_path)
        elif ext == 'csv':
            return pd.read_csv(file_path)
        elif ext == 'txt':
            return pd.read_csv(file_path, delimiter='\t')
        else:
            print(f"Unsupported file extension: {ext}")
            return None
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

# Routes
@app.route('/')
def index():
    return render_template('index.html', **session)

@app.route('/upload', methods=['POST'])
def upload_files():
    files = [request.files.get(f'file{i}') for i in range(1, 3)]
    if not all(files) or 'payment_type' not in request.form:
        return render_template('index.html', error='All fields are required.')
    if any(f.filename == '' or not allowed_file(f.filename) for f in files):
        return render_template('index.html', error='Invalid file type or empty file.')

    paths = [os.path.join(app.config['UPLOAD_FOLDER'], f'file{i}.{f.filename.rsplit(".", 1)[1].lower()}') for i, f in enumerate(files)]
    for file, path in zip(files, paths):
        file.save(path)

    output_filename, summary, chart_file = process_files(*paths, request.form['payment_type'])
    if output_filename:
        session.update(summary=summary, chart_file=chart_file, filename=output_filename)
        return redirect(url_for('index'))
    return render_template('index.html', error='Error during file processing.')

def process_files(file1_path, file2_path, payment_type):
    df1, df2 = read_file(file1_path), read_file(file2_path)
    if df1 is None or df2 is None:
        return None, None, None

    df1.columns = df1.columns.str.strip().str.lower()
    df2.columns = df2.columns.str.strip().str.lower()

    df1_col, df2_col = ('utr no', 'utr') if payment_type in ['ATP', 'NEFT'] else ('receipt no', 'receipt no')

    if df1_col not in df1.columns or df2_col not in df2.columns:
        print(f"Missing matching columns: {df1_col} or {df2_col}")
        return None, None, None

    try:
        matched = pd.merge(df1, df2, left_on=df1_col, right_on=df2_col, how='inner')
        unmatched_1 = df1[~df1[df1_col].isin(matched[df1_col])]
        unmatched_2 = df2[~df2[df2_col].isin(matched[df2_col])]

        summary = {
            'Total CIS Records': len(df1),
            'Total TP Records': len(df2),
            'CIS = TP (Matched)': len(matched),
            'CIS <> TP (Mismatch from CIS)': len(unmatched_1),
            'TP <> CIS (Mismatch from TP)': len(unmatched_2)
        }

        chart_file = create_summary_chart(payment_type, summary)
        output_filename = f'{payment_type}_output.xlsx'
        output_file = os.path.join(app.config['RESULT_FOLDER'], output_filename)

        with pd.ExcelWriter(output_file) as writer:
            matched.to_excel(writer, sheet_name='Matched', index=False)
            unmatched_1.to_excel(writer, sheet_name='Non_Matching_File1', index=False)
            unmatched_2.to_excel(writer, sheet_name='Non_Matching_File2', index=False)

        return output_filename, summary, chart_file
    except Exception as e:
        print(f"Processing error: {e}")
        return None, None, None

def create_summary_chart(payment_type, summary):
    categories = list(summary.keys())
    counts = list(summary.values())

    chart_file = f'{payment_type}_summary_chart.png'
    chart_path = os.path.join(app.config['RESULT_FOLDER'], chart_file)

    plt.figure(figsize=(8, 4))
    plt.pie(
        counts,
        labels=[f'{cat}\n{count:,}' for cat, count in zip(categories, counts)],
        colors=['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#c2c2f0'],
        startangle=90,
        counterclock=False,
        wedgeprops={'linewidth': 5, 'edgecolor': 'white'},
        autopct='%1.1f%%'
    )
    plt.gca().add_artist(plt.Circle((0, 0), 0.70, fc='white'))
    plt.title(f'{payment_type} Reconciliation Summary\nCounts and Matches', fontsize=14)
    plt.tight_layout()
    plt.savefig(chart_path)
    plt.close()
    return chart_file

@app.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join(app.config['RESULT_FOLDER'], filename)
    return send_from_directory(app.config['RESULT_FOLDER'], filename, as_attachment=True) if os.path.exists(file_path) else f"Error: {filename} does not exist."

if __name__ == "__main__":
    app.run(debug=True)
