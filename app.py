import streamlit as st
import pdfplumber
import requests
import tempfile
import re
import pandas as pd

# ---------------- 1. دوال المعالجة ---------------- #

@st.cache_data(show_spinner=False)
def fetch_and_process_pdf(pdf_url):
    response = requests.get(pdf_url)
    response.raise_for_status() 
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
        temp_pdf.write(response.content)
        temp_pdf_path = temp_pdf.name

    events = []
    
    with pdfplumber.open(temp_pdf_path) as pdf:
        pages_text = []
        for page in pdf.pages:
            text = page.extract_text()
            if text: pages_text.append(text)
                
        roster = {}
        for text in pages_text[:3]: 
            matches = re.findall(r'\b(\d{1,2})\s+([A-Za-z\-\']+,\s*[A-Za-z\-\']+)', text)
            for num, name in matches:
                clean_name = name.replace(" ", "").lower()
                roster[clean_name] = num
                    
        for text in pages_text:
            lines = text.split('\n')
            for line in lines:
                # التعديل الأهم: البحث عن الوقت في أي مكان في السطر مش بس في الأول
                time_match = re.search(r'(\d{1,2}:\d{2})', line)
                if time_match:
                    pdf_time = time_match.group(1)
                    event_text = line.replace(pdf_time, '').strip()
                    
                    team_match = re.search(r'\b([A-Z]{2,5})\b', event_text)
                    team = team_match.group(1) if team_match else ""
                    
                    try:
                        minutes, seconds = map(int, pdf_time.split(':'))
                        current_half = "1" if minutes < 45 else "2"
                        
                        total_half_seconds = 45 * 60 if current_half == "1" else 90 * 60
                        elapsed = (minutes * 60) + seconds
                        rem_seconds = total_half_seconds - elapsed
                        
                        if rem_seconds < 0: rem_seconds = 0
                        scoreboard_time = f"{rem_seconds // 60:02d}:{rem_seconds % 60:02d}"
                    except:
                        scoreboard_time = pdf_time
                        current_half = "Unknown"

                    # التعرف على الأحداث حتى لو الحروف كابيتال أو سمول
                    event_lower = event_text.lower()
                    event_type = "Other"
                    if "shot by" in event_lower: event_type = "Shot"
                    elif "substitution" in event_lower: event_type = "Substitution"
                    elif "goal by" in event_lower: event_type = "Goal"
                    elif "foul on" in event_lower or "foul by" in event_lower: event_type = "Foul"

                    details = event_text
                    players_involved = []
                    names_in_event = re.findall(r'([A-Za-z\-\']+,\s*[A-Za-z\-\']+)', event_text)
                    
                    for name in names_in_event:
                        clean_name = name.replace(" ", "").lower()
                        number = roster.get(clean_name, "??") 
                        
                        formatted_name = f"{name} (#{number})"
                        details = details.replace(name, formatted_name)
                        players_involved.append(formatted_name)

                    events.append({
                        "Team": str(team),
                        "Scoreboard Time": str(scoreboard_time),
                        "PDF Time": str(pdf_time),
                        "Half": str(current_half),
                        "Type": str(event_type),
                        "Players Involved": str(" | ".join(players_involved)),
                        "Details": str(details)
                    })
    return events

# ---------------- 2. واجهة الموقع ---------------- #

st.set_page_config(page_title="محلل إحصائيات المباريات", page_icon="⚽", layout="wide")

st.title("⚽ محلل تقارير المباريات (NCAA Play-by-Play)")
st.markdown("حط لينك الـ PDF هنا علشان نطلعلك الداتا بالوقت المضبوط، واسم الفرقة، وأرقام اللعيبة.")

pdf_url = st.text_input("🔗 أدخل رابط ملف الـ PDF هنا:")

if st.button("🚀 حلل البيانات"):
    if pdf_url:
        with st.spinner('جاري التحليل...'):
            try:
                parsed_data = fetch_and_process_pdf(pdf_url)
                if parsed_data:
                    st.session_state['match_data'] = pd.DataFrame(parsed_data)
                    st.success("✅ تم التحليل بنجاح!")
                else:
                    st.warning("⚠️ مقدرناش نلاقي أحداث في الملف ده، تأكد إن الملف فيه Play-by-Play.")
            except Exception as e:
                st.error(f"❌ حصلت مشكلة: {e}")
    else:
        st.warning("رجاءً أدخل رابط الـ PDF أولاً.")

if 'match_data' in st.session_state:
    df = st.session_state['match_data']
    
    st.divider()
    st.subheader("📊 تفاصيل المباراة")
    
    filter_type = st.multiselect("فلترة حسب نوع الحدث:", 
                                 options=["Shot", "Substitution", "Goal", "Foul", "Other"], 
                                 default=["Shot", "Substitution", "Goal", "Foul"])
    
    filtered_df = df[df["Type"].isin(filter_type)]
    
    # رسالة بتوضحلك هو لاقى كام حدث
    st.info(f"📌 تم العثور على {len(filtered_df)} حدث بناءً على الفلتر اللي اخترته.")
    
    # عرض الجدول بطريقة أقوى مش بتختفي
    st.write(filtered_df)
