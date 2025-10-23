import io
import streamlit as st
import pandas as pd
import re
from google.cloud import storage

def upload_to_gcs_from_bytes(data_bytes, dest_name):
    creds_info = json.loads(st.secrets["gcp"]["service_account_json"])
    client = storage.Client.from_service_account_info(creds_info)
    bucket = client.bucket(st.secrets["gcp"]["bucket_name"])
    blob = bucket.blob(dest_name)
    blob.upload_from_file(io.BytesIO(data_bytes), content_type="text/csv")
    st.success(f"✅ Uploaded {dest_name} to gs://{st.secrets['gcp']['bucket_name']}")


# --- Load data (unchanged) ---
@st.cache_data
def load_data():
    df = pd.read_csv("PGCF.csv")
    return df

df = load_data()

bloom_levels = ["Unfamiliar", "Remember", "Understand", "Apply", "Analyse", "Evaluate", "Create"]

# Reset index and drop empty rows in main column
df = df[df["Domains and Topics"].notna()].reset_index(drop=True)

# Identify rows that are section headers
section_mask = df["Domains and Topics"].str.match(r"^\d+\.\s")

# Parse sections with their rows
sections_list = []
current_section = None

for i, row in df.iterrows():
    topic = row["Domains and Topics"]
    if section_mask[i]:
        # Start new section
        current_section = {"header": topic, "rows": []}
        sections_list.append(current_section)
    else:
        if current_section is not None:
            current_section["rows"].append(row)

# --- Sidebar: user info + section picker ---
st.sidebar.header("Your details")
name_id = st.sidebar.text_input("Name / ID", placeholder="e.g. John Smith or JS-001")
job_title = st.sidebar.text_input("Job Title", placeholder="e.g. Biomedical Scientist")
role = st.sidebar.text_input("Role Description", placeholder="e.g.  develops in-house diagnostics, oversight of clinical trials, molecular training ")

st.sidebar.header("Select relevant domains")
section_headers = [sec["header"] for sec in sections_list]
selected_sections = st.sidebar.multiselect("Choose domains to assess", options=section_headers)

if not selected_sections:
    st.info("Please select at least one domain from the sidebar to proceed.")
    st.stop()

# --- Main UI (unchanged display flow) ---
st.title("Pathogen Genomics Competency Self-Assessment")
selections = {}

for section in sections_list:
    if section["header"] not in selected_sections:
        continue

    st.header(section["header"])

    for i, row in enumerate(section["rows"]):
        topic = row["Domains and Topics"]

        available_levels = {level: row[level] if pd.notna(row[level]) else "n/A" for level in bloom_levels}
        available_levels["N/A"] = "Not applicable"
        available_levels["Unfamiliar"] = "I have not encountered this concept before or have had limited education or training in this area"

        st.markdown(f"### {topic}")

        options_with_text = [f"{level}: {text}" for level, text in available_levels.items()]
        key = f"radio_{section['header']}_{i}_{topic[:20].replace(' ', '_')}"

        selected = st.radio(
            f"Select your level for: {topic}",
            options_with_text,
            key=key
        )

        selected_level = selected.split(":")[0]
        selected_text = available_levels[selected_level]
        selections[topic] = (selected_level, selected_text)

# --- Summary + Download ---
if "show_summary" not in st.session_state:
    st.session_state["show_summary"] = False

if st.button("Show Summary", key="show_summary_button"):
    st.session_state["show_summary"] = True

if st.session_state["show_summary"]:
    result_df = pd.DataFrame([
        {"Competency": topic, "Selected Level": level, "Description": desc}
        for topic, (level, desc) in selections.items()
    ])
    st.dataframe(result_df)

    # Add user info lines
    meta_lines = [
        f"# Name / ID: {name_id or ''}",
        f"# Job Title: {job_title or ''}",
        f"# Role: {role or ''}",
    ]

    buf = io.StringIO()
    for line in meta_lines:
        buf.write(line + "\n")
    result_df.to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode("utf-8")

    # Always show download button when summary is visible
    if st.download_button("⬇️ Download CSV", data=csv_bytes, file_name="competency_selections.csv"):
        upload_to_gcs_from_bytes(csv_bytes, "competency_selections.csv")
