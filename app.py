import streamlit as st
import pdfplumber
import requests
import tempfile
import re
import pandas as pd

# ---------------- 1. دوال المعالجة ---------------- #

def get_text_color(hex_color):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return "#000000" if (r * 0.299 + g * 0.587 + b * 0.114) > 128 else "#FFFFFF"
    return "#000000"

@st.cache_data(show_spinner=False)
def fetch_and_process_pdf(pdf_url):
    response = requests.get(pdf_url)
    response.raise_for_status() 
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
        temp_pdf.write(response.content)
        temp_pdf_path = temp_pdf.name

    events = []
    display_roster = [] 
    unique_players = set()
    
    with pdfplumber.open(temp_pdf_path) as pdf:
        pages_text = []
        for page in pdf.pages:
            text = page.extract_text()
            if text: pages_text.append(text)
                
        roster_search_terms = {}
        for text in pages_text[:3]: 
            # التعديل 1: السماح بالأسماء المركبة والمسافات قبل وبعد الفاصلة
            matches = re.findall(r'\b(\d{1,2})\s+([A-Za-z\-\'\.]+(?:\s+[A-Za-z\-\'\.]+)*,\s*[A-Za-z\-\'\.]+(?:\s+[A-Za-z\-\'\.]+)*)', text)
            for num, name in matches:
                roster_search_terms[name] = num
                # إضافة نسخة احتياطية من الاسم في حال اختلاف المسافات
                if ", " in name:
                    roster_search_terms[name.replace(", ", ",")] = num
                    
                clean_name = name.replace(" ", "").lower()
                if clean_name not in unique_players:
                    unique_players.add(clean_name)
                    display_roster.append({"رقم اللاعب": num, "اسم اللاعب": name})
                    
        for text in pages_text:
            lines = text.split('\n')
            for line in lines:
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

                    event_lower = event_text.lower()
                    event_type = "Other"
                    if "shot by" in event_lower: event_type = "Shot"
                    elif "substitution" in event_lower: event_type = "Substitution"
                    elif "goal by" in event_lower: event_type = "Goal"
                    elif "foul on" in event_lower or "foul by" in event_lower: event_type = "Foul"

                    details = event_text
                    players_involved = []
                    
                    # التعديل 2: البحث بذكاء باستخدام الأسماء المستخرجة (الأطول أولاً)
                    for name, num in sorted(roster_search_terms.items(), key=lambda x: len(x[0]), reverse=True):
                        if name in details:
                            formatted_name = f"{name} (#{num})"
                            if formatted_name not in details:
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
                    
    return events, display_roster

# ---------------- 2. واجهة الموقع ---------------- #

st.set_page_config(page_title="محلل إحصائيات المباريات", page_icon="⚽", layout="wide")

st.title("⚽ محلل تقارير المباريات (NCAA Play-by-Play)")
st.markdown("حط لينك الـ PDF هنا علشان نطلعلك الداتا بالوقت المضبوط، واسم الفرقة، وأرقام اللعيبة.")

pdf_url = st.text_input("🔗 أدخل رابط ملف الـ PDF هنا:")

if st.button("🚀 حلل البيانات"):
    if pdf_url:
        with st.spinner('جاري التحليل...'):
            try:
                parsed_data, roster_data = fetch_and_process_pdf(pdf_url)
                if parsed_data:
                    st.session_state['match_data'] = pd.DataFrame(parsed_data)
                    
                    roster_df = pd.DataFrame(roster_data).sort_values(by="اسم اللاعب")
                    st.session_state['roster_data'] = roster_df
                    
                    st.success("✅ تم التحليل بنجاح!")
                else:
                    st.warning("⚠️ مقدرناش نلاقي أحداث في الملف ده، تأكد إن الملف فيه Play-by-Play.")
            except Exception as e:
                st.error(f"❌ حصلت مشكلة: {e}")
    else:
        st.warning("رجاءً أدخل رابط الـ PDF أولاً.")

# ---------------- 3. عرض البيانات والفلاتر والألوان ---------------- #

if 'match_data' in st.session_state:
    df = st.session_state['match_data']
    roster_df = st.session_state['roster_data']
    
    st.divider()
    
    with st.expander("📋 عرض قائمة أرقام وأسماء اللاعبين (Roster)"):
        st.dataframe(roster_df, use_container_width=True, hide_index=True)
        
    st.divider()
    
    teams = [t for t in df['Team'].unique() if t.strip()]
    team1 = teams[0] if len(teams) > 0 else "Team 1"
    team2 = teams[1] if len(teams) > 1 else "Team 2"
    
    st.subheader("🎨 تخصيص ألوان الفرق")
    col1, col2 = st.columns(2)
    with col1:
        color1 = st.color_picker(f"لون فريق {team1} (Home الديفولت)", "#FFFFFF")
    with col2:
        color2 = st.color_picker(f"لون فريق {team2} (Away الديفولت)", "#000000")
    
    st.divider()
    
    st.subheader("📊 تفاصيل المباراة")
    
    filter_type = st.multiselect("فلترة حسب نوع الحدث:", 
                                 options=["Shot", "Substitution", "Goal", "Foul", "Other"], 
                                 default=["Shot", "Substitution", "Goal", "Foul"])
    
    filtered_df = df[df["Type"].isin(filter_type)]
    
    st.info(f"📌 تم العثور على {len(filtered_df)} حدث بناءً على الفلتر اللي اخترته.")
    
    def color_rows(row):
        if row['Team'] == team1:
            return [f'background-color: {color1}; color: {get_text_color(color1)}'] * len(row)
        elif row['Team'] == team2:
            return [f'background-color: {color2}; color: {get_text_color(color2)}'] * len(row)
        return [''] * len(row)
    
    styled_df = filtered_df.style.apply(color_rows, axis=1)
    st.dataframe(styled_df, use_container_width=True)
