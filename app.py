import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(
    page_title="Student Nurse Proficiency Tracker",
    page_icon="📋",
    layout="wide"
)

# -----------------------------
# Helper Functions
# -----------------------------

@st.cache_data

def load_file(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file)


def extract_proficiency_columns(df):
    proficiency_columns = {}

    for col in df.columns:
        if '(Overall score)' in str(col):
            clean_col = str(col)
            match = re.match(r'^(\d+\*?)\.\s*(.*?)\s*\(Overall score\)$', clean_col)

            if match:
                prof_number = match.group(1)
                prof_name = match.group(2)

                proficiency_columns[col] = {
                    'number': prof_number,
                    'name': prof_name
                }

    return proficiency_columns


def process_data(df):
    proficiency_columns = extract_proficiency_columns(df)

    respondent_col = None

    for col in df.columns:
        if str(col).strip().lower() == 'respondent':
            respondent_col = col
            break

    if respondent_col is None:
        st.error("Could not find the 'Respondent' column.")
        st.stop()

    processed_rows = []

    for _, row in df.iterrows():
        student = str(row[respondent_col]).strip()

        # Normalise spacing/capitalisation to avoid duplicates
        student = re.sub(r'\s+', ' ', student)
        student = student.title()

        if pd.isna(student):
            continue

        for original_col, details in proficiency_columns.items():
            score = row[original_col]

            # Handle different score formats safely
            manual_check = False

            if pd.isna(score):
                score_num = None
                manual_check = True
            else:
                score_str = str(score).strip()

                # Flag common problematic export values
                if score_str.lower() in [
                    'not applicable',
                    'n/a',
                    'na'
                ]:
                    score_num = None
                    manual_check = True

                elif score_str.lower() in [
                    'not answered',
                    ''
                ]:
                    score_num = 0
                    manual_check = False


                else:
                    # Extract first numeric value from strings
                    number_match = re.search(
                        r'(\d+(?:\.\d+)?)',
                        score_str
                    )

                    if number_match:
                        score_num = float(number_match.group(1))
                    else:
                        score_num = None
                        manual_check = True

            met = False if manual_check else score_num >= 1

            processed_rows.append({
                'Student': student,
                'Proficiency Number': str(details['number']).strip(),
                'Proficiency Name': details['name'],
                'Score': score_num,
                'Met': met,
                'Manual Check': manual_check,
                'Status': (
                    '⚠️ Check Manually'
                    if manual_check
                    else ('✅ Met' if met else '❌ Not Met')
                )
            })

    processed_df = pd.DataFrame(processed_rows)

    return processed_df


def create_matrix(processed_df):
    # If duplicate student/proficiency rows exist,
    # use the highest result (True beats False)
    grouped_df = processed_df.groupby(
        ['Student', 'Proficiency Number'],
        as_index=False
    )['Met'].max()

    matrix = grouped_df.pivot(
        index='Student',
        columns='Proficiency Number',
        values='Met'
    )

    # Sort proficiency columns numerically
    sorted_columns = sorted(
        matrix.columns,
        key=lambda x: int(str(x).replace('*', ''))
    )

    matrix = matrix[sorted_columns]

    matrix = matrix.fillna(False)

    display_matrix = matrix.copy()
    display_matrix = processed_df.groupby(
        ['Student', 'Proficiency Number'],
        as_index=False
    ).agg({
        'Met': 'max',
        'Manual Check': 'max'
    })

    display_matrix = display_matrix.pivot(
        index='Student',
        columns='Proficiency Number',
        values='Met'
    )

    manual_matrix = processed_df.groupby(
        ['Student', 'Proficiency Number'],
        as_index=False
    )['Manual Check'].max()

    manual_matrix = manual_matrix.pivot(
        index='Student',
        columns='Proficiency Number',
        values='Manual Check'
    )

    display_matrix = display_matrix.reindex(columns=sorted_columns)
    manual_matrix = manual_matrix.reindex(columns=sorted_columns)

    display_matrix = display_matrix.fillna(False)
    manual_matrix = manual_matrix.fillna(False)

    for col in display_matrix.columns:
        display_matrix[col] = display_matrix.apply(
            lambda row: (
                '⚠️'
                if manual_matrix.loc[row.name, col]
                else (
                  '✅'
                    if row[col] == True
                    else '❌'
                )
            ),
           axis=1
        )

    return matrix, display_matrix, manual_matrix


def export_missing_students(processed_df):
    missing = processed_df[processed_df['Met'] == False]

    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        missing.to_excel(writer, index=False, sheet_name='Missing Proficiencies')

    return output.getvalue()


# -----------------------------
# Title
# -----------------------------

st.title("📋 Student Nurse Proficiency Tracker")
st.markdown("Upload one or both proficiency spreadsheets to analyse student progress.")


# -----------------------------
# File Upload
# -----------------------------

uploaded_files = st.file_uploader(
    "Upload proficiency spreadsheets",
    type=['csv', 'xlsx'],
    accept_multiple_files=True
)

if uploaded_files:

    all_dataframes = []

    for uploaded_file in uploaded_files:
        try:
            df = load_file(uploaded_file)
            processed = process_data(df)
            all_dataframes.append(processed)

            st.success(f"Loaded: {uploaded_file.name}")

        except Exception as e:
            st.error(f"Error loading {uploaded_file.name}: {e}")

    if all_dataframes:

        combined_df = pd.concat(all_dataframes, ignore_index=True)

        # Remove duplicates if same proficiency appears twice
        combined_df = combined_df.drop_duplicates(
            subset=['Student', 'Proficiency Number']
        )

        # -----------------------------
        # Summary Metrics
        # -----------------------------

        total_students = combined_df['Student'].nunique()
        total_proficiencies = combined_df['Proficiency Number'].nunique()
        total_records = len(combined_df)
        met_count = combined_df['Met'].sum()

        completion_rate = round((met_count / total_records) * 100, 1)

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Students", total_students)
        col2.metric("Proficiencies", total_proficiencies)
        col3.metric("Completed", int(met_count))
        col4.metric("Completion Rate", f"{completion_rate}%")


        # -----------------------------
        # Tabs
        # -----------------------------

        tab1, tab2, tab3, tab4 = st.tabs([
            "👩‍⚕️ Student Overview",
            "📊 Cohort Matrix",
            "⚠️ Missing Proficiencies",
            "📥 Export"
        ])


        # -----------------------------
        # Student Overview
        # -----------------------------

        with tab1:

            st.subheader("Student Progress")

            students = sorted(combined_df['Student'].unique())

            selected_student = st.selectbox(
                "Select a student",
                students
            )

            student_df = combined_df[
                combined_df['Student'] == selected_student
            ].sort_values('Proficiency Number', key=lambda x: x.astype(int))

            met_total = student_df['Met'].sum()
            overall_total = len(student_df)
            percentage = round((met_total / overall_total) * 100, 1)

            st.progress(percentage / 100)
            st.write(f"### {percentage}% Complete ({met_total}/{overall_total})")

            show_missing_only = st.toggle("Show missing proficiencies only")

            if show_missing_only:
                student_df = student_df[student_df['Met'] == False]

            display_student = student_df[[
                'Proficiency Number',
                'Proficiency Name',
                'Score',
                'Status'
            ]]

            st.dataframe(
                display_student,
                use_container_width=True,
                hide_index=True
            )


        # -----------------------------
        # Cohort Matrix
        # -----------------------------

        with tab2:

            st.subheader("Cohort Completion Matrix")

            matrix, display_matrix, manual_matrix = create_matrix(combined_df)

            search = st.text_input("Search student")

            filtered_matrix = display_matrix.copy()

            if search:
                filtered_matrix = filtered_matrix[
                    filtered_matrix.index.str.contains(
                        search,
                        case=False,
                        na=False
                    )
                ]

            st.dataframe(
                filtered_matrix,
                use_container_width=True
            )


        # -----------------------------
        # Missing Proficiencies
        # -----------------------------

        with tab3:

            st.subheader("Students Missing Each Proficiency")

            prof_options = combined_df[[
                'Proficiency Number',
                'Proficiency Name'
            ]].drop_duplicates()

            prof_options['Sort'] = (
                prof_options['Proficiency Number']
                .astype(int)
            )

            prof_options = prof_options.sort_values('Sort')

            prof_options['Label'] = (
                prof_options['Proficiency Number']
                + ' - '
                + prof_options['Proficiency Name']
            )

            selected_prof = st.selectbox(
                "Select a proficiency",
                prof_options['Label'].tolist()
            )

            prof_number = selected_prof.split(' - ')[0].strip()

            # Students needing manual checks
            manual_students = []

            if prof_number in manual_matrix.columns:
                manual_students = manual_matrix[
                    manual_matrix[prof_number] == True
                ].index.tolist()

            # Students genuinely missing
            missing_students = [
                student for student in matrix[
                    matrix[prof_number] == False
                ].index.tolist()
                if student not in manual_students
            ]

            missing_df = pd.DataFrame({
                'Student': sorted(missing_students)
            })

            manual_df = pd.DataFrame({
                'Student': sorted(manual_students)
            })

            st.warning(
                f"{len(missing_students)} students have not yet met this proficiency."
            )

            st.dataframe(
                missing_df,
                use_container_width=True,
                hide_index=True
            )

            st.subheader("⚠️ Manual Checks Recommended")

            st.info(
                "These students contain unclear or missing exported data "
                "such as 'Not applicable' or blank values."
            )

            st.dataframe(
                manual_df,
                use_container_width=True,
                hide_index=True
            )


        # -----------------------------
        # Export
        # -----------------------------

        with tab4:

            st.subheader("Export Missing Proficiencies")

            export_data = export_missing_students(combined_df)

            st.download_button(
                label="📥 Download Missing Proficiencies Report",
                data=export_data,
                file_name='missing_proficiencies.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

            st.info(
                "This export contains all students and proficiencies "
                "that have not yet been met."
            )

else:
    st.info("Upload one or more spreadsheets to begin.")


# -----------------------------
# Footer
# -----------------------------

st.markdown('---')
st.caption('Student Nurse Proficiency Tracker • Streamlit App')
