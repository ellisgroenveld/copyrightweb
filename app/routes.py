from flask import request, render_template, redirect, url_for, send_file, jsonify
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from werkzeug.utils import secure_filename
import os
import re
from fuzzywuzzy import process
from app import app

PREDEFINED_COLUMNS = [
    'Course code', 'Course name', 'url', 'Filename', 'Title', 'Owner', 'Filetype', 
    'Classification', 'Type', 'ML Prediction', 'Status', 'pagecount', 'wordcount', 
    'picturecount', 'Author', 'Publisher', 'Reliability', 'Pages * Students', 
    '#students_registered'
]

DEPARTMENTS = [
    "Applied Science Academie", "Built Environment Academie", "Academie Engineering",
    "Academie Technische Bedrijfskunde", "ICT Academie", "Academie voor Ergotherapie",
    "Academie voor Fysiotherapie", "Academie voor Logopedie", "Academie voor Mens en Techniek",
    "Academie voor Vaktherapie", "Academie Verloskunde Maastricht", "Academie voor Verpleegkunde",
    "Academie voor Sociaal Werk", "De Nieuwste Pabo", "Academie voor Commerciële Economie",
    "Academie voor Financieel Management", "Academie voor Business Studies", "De Juridische Academie",
    "Hotel Management School Maastricht", "Academie voor Facility Management", "Conservatorium Maastricht",
    "Toneelacademie Maastricht", "Maastricht Institute of Arts",
    "Academie Oriëntaalse Talen en Communicatie / Internationale Communicatie",
    "International Business School Maastricht", "School of European Studies", "Vertaalacademie"
]

CLASSIFICATIONS = ["Niet geanalyseerd", "eigen materiaal", "korte overname", "middellange overname", "open access", "onbekend", "lange overname"]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def predict_department(row):
    text = f"{row['Course code']} {row['Course name']} {row['Filename']}".lower()
    result = process.extractOne(text, DEPARTMENTS, score_cutoff=80)
    if result:
        best_match, score = result
        return best_match
    else:
        return "Unknown"

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return redirect(url_for('select_columns', filename=filename))
    return redirect(request.url)

@app.route('/select_columns/<filename>', methods=['GET', 'POST'])
def select_columns(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    df = pd.read_excel(file_path)
    columns = df.columns.tolist()
    
    if request.method == 'POST':
        selected_columns = request.form.getlist('columns')
        # Create a new DataFrame with predefined columns
        new_df = pd.DataFrame(columns=PREDEFINED_COLUMNS)
        
        # Map selected columns to predefined columns
        for i, column in enumerate(selected_columns):
            if column in df.columns:
                new_df[PREDEFINED_COLUMNS[i]] = df[column]
        
        # Predict department
        new_df['Department'] = new_df.apply(predict_department, axis=1)
        
        # Step 1: Filter by course codes
        filter_keywords = ["2324", "2024", "2023", "23-24"]
        exclude_keywords = ["2022"]
        new_df = new_df[
            new_df['Course code'].str.contains('|'.join(filter_keywords)) & 
            ~new_df['Course code'].str.contains('|'.join(exclude_keywords))
        ]
        
        # Step 2: Delete specific entries
        new_df = new_df[
            ~(new_df['Status'] == 'Deleted') | 
            (new_df['Pages * Students'] != 0)
        ]
        
        # Save the processed file
        new_file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'processed_file.xlsx')
        new_df.to_excel(new_file_path, index=False)
        
        # Redirect to KPIs page
        return redirect(url_for('show_kpis', filename='processed_file.xlsx'))
    
    return render_template('select_columns.html', columns=columns, predefined_columns=PREDEFINED_COLUMNS)

@app.route('/kpis/<filename>', methods=['GET'])
def show_kpis(filename):
    department = request.args.get('department', 'All')
    selected_classifications = request.args.getlist('classification')
    status_filter = request.args.get('status', 'All')
    pagecount_toggle = request.args.get('pagecount_toggle', 'off') == 'on'
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    df = pd.read_excel(file_path)
    
    # Filter by department if not 'All'
    if department != 'All':
        df = df[df['Department'] == department]
    
    # Filter by selected classifications
    if selected_classifications:
        df = df[df['Classification'].isin(selected_classifications)]
    
    # Filter by status if not 'All'
    if status_filter != 'All':
        df = df[df['Status'] == status_filter]
    
    # Filter by pagecount if toggle is on
    if pagecount_toggle:
        df = df[df['pagecount'] > 50]
    
    # KPIs and Visualizations
    classification_counts = df['Classification'].value_counts().to_dict()
    ml_prediction_counts = df['ML Prediction'].value_counts().to_dict()
    type_counts = df['Type'].value_counts().to_dict()
    status_counts = df['Status'].value_counts().to_dict()
    total_pages_students = df['Pages * Students'].sum()
    avg_pages_students = df['Pages * Students'].mean()
    avg_pagecount = df['pagecount'].mean()
    avg_wordcount = df['wordcount'].mean()
    picture_count = df['picturecount'].sum()
    
    highest_scoring = df[['Filename', 'url', 'pagecount', 'Classification', 'Status', 'Owner', 'Course code', 'ML Prediction', 'Reliability', 'Type', '#students_registered']].sort_values(by='pagecount', ascending=False)
    highest_scoring_list = highest_scoring.to_dict(orient='records')
    
    highest_per_course = df.groupby('Course code')['pagecount'].sum().sort_values(ascending=False).head(10).reset_index()
    
    department_counts = df['Department'].value_counts().to_dict()
    material_types_counts = df['Filetype'].value_counts().to_dict()
    
    custom_palette = ['#e81a31', '#ffffff', '#000000']
    sns.set_palette(custom_palette)
    
    plt.figure(figsize=(12, 6))
    plt.subplot(1, 3, 1)
    sns.barplot(x=list(department_counts.keys()), y=list(department_counts.values()))
    plt.xticks(rotation=90)
    plt.title('Materials by Department')
    
    plt.subplot(1, 3, 2)
    sns.barplot(x=list(material_types_counts.keys()), y=list(material_types_counts.values()))
    plt.xticks(rotation=90)
    plt.title('Material Types Distribution')
    
    plt.subplot(1, 3, 3)
    sns.barplot(x=list(status_counts.keys()), y=list(status_counts.values()))
    plt.xticks(rotation=90)
    plt.title('Material Status Distribution')
    
    plt.tight_layout()
    image_path = os.path.join('static', 'uploads', 'additional_kpis.png')
    plt.savefig(os.path.join(app.root_path, image_path))
    plt.close()
    
    if department != 'All':
        department_df = df.copy()
        department_df.to_excel(os.path.join(app.config['UPLOAD_FOLDER'], f'processed_data_{department}.xlsx'), index=False)
    
    return render_template(
        'kpis.html',
        classification_counts=classification_counts,
        ml_prediction_counts=ml_prediction_counts,
        type_counts=type_counts,
        status_counts=status_counts,
        total_pages_students=total_pages_students,
        avg_pages_students=avg_pages_students,
        avg_pagecount=avg_pagecount,
        avg_wordcount=avg_wordcount,
        picture_count=picture_count,
        highest_scoring=highest_scoring_list,
        highest_per_course=highest_per_course.to_html(),
        image_path=url_for('static', filename='uploads/additional_kpis.png'),
        departments=['All'] + sorted(DEPARTMENTS),
        classifications=sorted(CLASSIFICATIONS),
        statuses=['All', 'Deleted', 'Published'],
        selected_department=department,
        selected_classifications=selected_classifications,
        selected_status=status_filter,
        pagecount_toggle=pagecount_toggle
    )

@app.route('/full_table', methods=['GET'])
def full_table():
    department = request.args.get('department', 'All')
    selected_classifications = request.args.getlist('classification')
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'processed_file.xlsx')
    df = pd.read_excel(file_path)
    
    # Filter by department if not 'All'
    if department != 'All':
        df = df[df['Department'] == department]
    
    # Filter by selected classifications
    if selected_classifications:
        df = df[df['Classification'].isin(selected_classifications)]
    
    table_html = df.to_html(classes='data', header="true", index=False, escape=False, formatters={'Filename': lambda x: f'<a href="{df.loc[df["Filename"] == x, "url"].values[0]}" target="_blank">{x}</a>'})
    
    filtered_file_path = os.path.join(app.config['UPLOAD_FOLDER'], f'filtered_data_{department}_{"_".join(selected_classifications)}.xlsx')
    df.to_excel(filtered_file_path, index=False)
    
    return render_template(
        'full_table.html',
        table_html=table_html,
        download_url=url_for('download_filtered_dataframe', department=department, classification=",".join(selected_classifications))
    )

@app.route('/download_filtered_dataframe', methods=['GET', 'POST'])
def download_filtered_dataframe():
    department = request.form.get('department', 'All')
    classifications = request.form.get('classification', 'All').split(',')

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'processed_file.xlsx')
    df = pd.read_excel(file_path)
    
    if department != 'All':
        df = df[df['Department'] == department]
    
    if classifications and classifications != ['All']:
        df = df[df['Classification'].isin(classifications)]
    
    filtered_file_path = os.path.join(app.config['UPLOAD_FOLDER'], f'filtered_data_{department}_{"_".join(classifications)}.xlsx')
    df.to_excel(filtered_file_path, index=False)
    
    return send_file(filtered_file_path, as_attachment=True)
