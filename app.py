import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib
from flask import Flask, request, render_template, redirect, url_for, send_from_directory, session

matplotlib.use('Agg')

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Add a secret key for session management

# Set upload and result folders
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['RESULT_FOLDER'] = 'static/results/'

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULT_FOLDER'], exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv', 'txt'}

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def read_file(file_path):
    """Read file based on its extension and return the DataFrame."""
    ext = file_path.rsplit('.', 1)[1].lower()
    try:
        if ext in ['xlsx', 'xls']:
            return pd.read_excel(file_path)
        elif ext == 'csv':
            return pd.read_csv(file_path)
        elif ext == 'txt':
            return pd.read_csv(file_path, delimiter='\t')
        else:
            return None
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

@app.route('/')
def index():
    summary = session.get('summary', None)
    chart_file = session.get('chart_file', None)
    filename = session.get('filename', None)
    return render_template('index.html', summary=summary, chart_file=chart_file, filename=filename)

@app.route('/upload', methods=['POST'])
def upload_files():
    # Check if files and payment type were uploaded
    if 'file1' not in request.files or 'file2' not in request.files or 'payment_type' not in request.form:
        return render_template('index.html', error='All fields are required.')

    file1 = request.files['file1']
    file2 = request.files['file2']
    payment_type = request.form['payment_type']

    # Check if filenames are empty or file types are not allowed
    if file1.filename == '' or file2.filename == '':
        return render_template('index.html', error='Please select both files before uploading.')
    
    if not allowed_file(file1.filename) or not allowed_file(file2.filename):
        return render_template('index.html', error='Only .xlsx, .xls, .csv, and .txt files are allowed.')

    # Save files
    file1_path = os.path.join(app.config['UPLOAD_FOLDER'], file1.filename)
    file2_path = os.path.join(app.config['UPLOAD_FOLDER'], file2.filename)
    try:
        file1.save(file1_path)
        file2.save(file2_path)
    except Exception as e:
        print(f"Error saving files: {e}")
        return render_template('index.html', error='Error saving files.')

    # Process files
    output_filename, summary, chart_file = process_files(file1_path, file2_path, payment_type)

    if output_filename:
        # Store results in session
        session['summary'] = summary
        session['chart_file'] = chart_file
        session['filename'] = output_filename
        return redirect(url_for('index'))
    else:
        return render_template('index.html', error='Error during file processing.')

def process_files(file1_path, file2_path, payment_type):
    # Read the files
    df1 = read_file(file1_path)
    df2 = read_file(file2_path)

    if df1 is None or df2 is None:
        return None, None, None

    df1.columns = df1.columns.str.strip().str.lower()
    df2.columns = df2.columns.str.strip().str.lower()

    if payment_type in ['ATP', 'NEFT']:
        df1_column = 'utr no'
        df2_column = 'utr'
    else:
        df1_column = 'receipt no'
        df2_column = 'receipt no'

    if df1_column in df1.columns and df2_column in df2.columns:
        try:
            # Perform matching
            matched_data = pd.merge(df1, df2, left_on=df1_column, right_on=df2_column, how='inner')
            non_matching_data_df1 = df1[~df1[df1_column].isin(matched_data[df1_column])]
            non_matching_data_df2 = df2[~df2[df2_column].isin(matched_data[df2_column])]

            # Summary data
            matched_count = len(matched_data)
            unmatched_count_file1 = len(non_matching_data_df1)
            unmatched_count_file2 = len(non_matching_data_df2)
            total_records_cis = len(df1)
            total_records_tp = len(df2)

            summary = {
                'Total CIS Records': total_records_cis,
                'Total TP Records': total_records_tp,
                'CIS = TP (Matched)': matched_count,
                'CIS <> TP (Mismatch from CIS)': unmatched_count_file1,
                'TP <> CIS (Mismatch from TP)': unmatched_count_file2
            }

            # Generate chart based on summary data
            chart_file = 'summary_chart.png'
            chart_path = os.path.join(app.config['RESULT_FOLDER'], chart_file)

            categories = ['Total Collection CIS Records', 'Total MIS Records', 'CIS = TP (Matched)', 
                          'CIS <> TP (Mismatch from CIS)', 'TP <> CIS (Mismatch from TP)']
            counts = [
                summary['Total CIS Records'], 
                summary['Total TP Records'], 
                summary['CIS = TP (Matched)'], 
                summary['CIS <> TP (Mismatch from CIS)'], 
                summary['TP <> CIS (Mismatch from TP)']
            ]

            plt.figure(figsize=(8, 4))
            colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#c2c2f0']

            plt.pie(
                counts, 
                labels=[f'{category}\n{count:,}' for category, count in zip(categories, counts)],  
                colors=colors, 
                startangle=90, 
                counterclock=False, 
                wedgeprops={'linewidth': 5, 'edgecolor': 'white'}, 
                autopct='%1.1f%%',
                textprops={'color': 'black'}
            )

            plt.title(f'{payment_type} Reconciliation Summary\nCounts and Matches', fontsize=14)
            center_circle = plt.Circle((0, 0), 0.70, fc='white')
            fig = plt.gcf()
            fig.gca().add_artist(center_circle)

            plt.tight_layout()
            plt.savefig(chart_path)
            plt.close()

            # Save the output to an Excel file
            output_filename = f'{payment_type}_output.xlsx'
            output_file = os.path.join(app.config['RESULT_FOLDER'], output_filename)
            with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
                matched_data.to_excel(writer, sheet_name='Matched', index=False)
                non_matching_data_df1.to_excel(writer, sheet_name='Non_Matching_File1', index=False)
                non_matching_data_df2.to_excel(writer, sheet_name='Non_Matching_File2', index=False)

            print(f"Excel file saved at: {output_file}")
            return output_filename, summary, chart_file
        except Exception as e:
            print(f"Error during processing or writing to Excel: {e}")
            return None, None, None
    else:
        print(f"Error: Column {df1_column} or {df2_column} not found in the provided files.")
        return None, None, None

@app.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join(app.config['RESULT_FOLDER'], filename)
    if os.path.exists(file_path):
        return send_from_directory(app.config['RESULT_FOLDER'], filename, as_attachment=True)
    else:
        return f"Error: {filename} does not exist."

if __name__ == "__main__":
    app.run(debug=True)
