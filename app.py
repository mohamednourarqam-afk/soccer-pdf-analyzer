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

# دالة لتنظيف اسم الفرقة من الأرقام والأقواس الزايدة
def clean_header_name(text):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines: return "Unknown"
    name = lines[0]
    name = re.sub(r'\s+\d+$', '', name) # إزالة رقم الأهداف
    name = re.sub(r'\(\d+\-\d+\-\d+.*?\)', '', name) # إزالة سجل الفريق مثل (1-2-1)
    name = re.sub(r'-vs-|vs\.', '', name, flags=re.IGNORECASE) # إزالة كلمة vs
    name = re.sub(r'\([A-Za-z]+\)', '', name) # إزالة اختصارات بين أقواس مثل (RU)
    return name.strip()

@st.cache_data(show_spinner=False)
def fetch_and_process_pdf(pdf_url):
    response = requests.get(pdf_url)
    response.raise_for_status() 
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
        temp_pdf.write(response.content)
        temp_pdf_path = temp_pdf.name

    events = []
    display_roster = []
    roster_search_terms = {}
    team_names = {"left": "فريق 1", "right": "فريق 2"}
    
    left_players = set()
    right_players = set()
    left_abbr_counts = {}
    right_abbr_counts = {}
    
    with pdfplumber.open(temp_pdf_path) as pdf:
        page1 = pdf.pages[0]
        width = page1.width
        height = page1.height
        
        left_crop = page1.crop((0, 0, width/2, height))
        right_crop = page1.crop((width/2, 0, width, height))
        
        left_text = left_crop.extract_text() or ""
        right_text = right_crop.extract_text() or ""
        
        team_names["left"] = clean_header_name(left_text)
        team_names["right"] = clean_header_name(right_text)
        
        regex_pattern = r'\b(\d{1,2})\s+([A-Za-z\-\'\.]+(?:\s+[A-Za-z\-\'\.]+)*,\s*[A-Za-z\-\'\.]+(?:\s+[A-Za-z\-\'\.]+)*)'
        unique_players = set()
        
        for num, name in re.findall(regex_pattern, left_text):
            clean_name = name.replace(" ", "").lower()
            if clean_name not in unique_players:
                unique_players.add(clean_name)
                left_players.add(clean_name)
                display_roster.append({"رقم اللاعب": num, "اسم اللاعب": name, "الفرقة": team_names["left"]})
                roster_search_terms[name] = num
                if ", " in name: roster_search_terms[name.replace(", ", ",")] = num
                
        unique_players.clear()
        for num, name in re.findall(regex_pattern, right_text):
            clean_name = name.replace(" ", "").lower()
            if clean_name not in unique_players:
                unique_players.add(clean_name)
                right_players.add(clean_name)
                display_roster.append({"رقم اللاعب": num, "اسم اللاعب": name, "الفرقة": team_names["right"]})
                roster_search_terms[name] = num
                if ", " in name: roster_search_terms[name.replace(", ", ",")] = num

        pages_text = []
        for page in pdf.pages:
            text = page.extract_text()
            if text: pages_text.append(text)
            
        for text in pages_text:
            lines = text.split('\n')
            for line in lines:
                time_match = re.search(r'(\d{1,2}:\d{2})', line)
                if time_match:
                    pdf_time = time_match.group(1)
                    event_text = line.replace(pdf_time, '').strip()
                    
                    team_match = re.search(r'\b([A-Z]{2,5})\b', event_text)
                    team_abbr = team_match.group(1) if team_match else ""
                    
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
                    
                    for name, num in sorted(roster_search_terms.items(), key=lambda x: len(x[0]), reverse=True):
                        if name in details:
                            clean_name = name.replace(" ", "").lower()
                            
                            # استنتاج الاختصار بناءً على الفرقة اللي فيها اللاعب بذكاء
                            if team_abbr:
                                if clean_name in left_players:
                                    left_abbr_counts[team_abbr] = left_abbr_counts.get(team_abbr, 0) + 1
                                elif clean_name in right_players:
                                    right_abbr_counts[team_abbr] = right_abbr_counts.get(team_abbr, 0) + 1
                                    
                            formatted_name = f"{name} (#{num})"
                            if formatted_name not in details:
                                details = details.replace(name, formatted_name)
                                players_involved.append(formatted_name)

                    events.append({
                        "Team": str(team_abbr),
                        "Scoreboard Time": str(scoreboard_time),
                        "PDF Time": str(pdf_time),
                        "Half": str(current_half),
                        "Type": str(event_type),
                        "Players Involved": str(" | ".join(players_involved)),
                        "Details": str(details)
                    })
                    
    # تحديد الاختصار الصحيح لكل فرقة بدقة
    away_abbr = max(left_abbr_counts, key=left_abbr_counts.get) if left_abbr_counts else "Away"
    home_abbr = max(right_abbr_counts, key=right_abbr_counts.get) if right_abbr_counts else "Home"
                    
    return events, display_roster, team_names, away_abbr, home_abbr

# ---------------- 2. واجهة الموقع ---------------- #

st.set_page_config(page_title="محلل إحصائيات المباريات", page_icon="⚽", layout="wide")
# --- زرار وضع النهار والليل ---
 dark_mode = st.toggle("🌙 تفعيل وضع الليل (HUDL Theme)", value=True)

    if dark_mode:
        theme_css = """
        <style>
            [data-testid="stAppViewContainer"] { background-color: #191A1E; color: #FFFFFF; }
            [data-testid="stHeader"] { background-color: #191A1E; }
            p, h1, h2, h3 { color: #FFFFFF !important; }
            .stButton>button { background-color: #FF5100; color: white; border: none; }
        </style>
        """
    else:
        theme_css = """
        <style>
            [data-testid="stAppViewContainer"] { background-color: #FFFFFF; color: #000000; }
            [data-testid="stHeader"] { background-color: #FFFFFF; }
            p, h1, h2, h3 { color: #000000 !important; }
        </style>
        """
    st.markdown(theme_css, unsafe_allow_html=True)
    # ------------------------------
st.title("⚽ محلل تقارير المباريات (NCAA Play-by-Play)")
st.markdown("حط لينك الـ PDF هنا علشان نطلعلك الداتا بالوقت المضبوط، واسم الفرقة، وأرقام اللعيبة.")

pdf_url = st.text_input("🔗 أدخل رابط ملف الـ PDF هنا:")

if st.button("🚀 حلل البيانات"):
    if pdf_url:
        with st.spinner('جاري التحليل واستخراج الجداول...'):
            try:
                parsed_data, roster_data, team_names, away_abbr, home_abbr = fetch_and_process_pdf(pdf_url)
                if parsed_data:
                    st.session_state['match_data'] = pd.DataFrame(parsed_data)
                    roster_df = pd.DataFrame(roster_data).sort_values(by="رقم اللاعب", key=lambda col: pd.to_numeric(col, errors='coerce'))
                    st.session_state['roster_data'] = roster_df
                    st.session_state['team_names'] = team_names
                    st.session_state['away_abbr'] = away_abbr
                    st.session_state['home_abbr'] = home_abbr
                    
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
    team_names = st.session_state['team_names']
    away_abbr = st.session_state.get('away_abbr', 'Away')
    home_abbr = st.session_state.get('home_abbr', 'Home')
    
    st.divider()
    
    team_left = team_names['left']  
    team_right = team_names['right'] 
    
    with st.expander("📋 عرض قوائم اللعيبة (الروستر)", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"### ✈️ {team_left} (الضيف - Away)")
            team1_roster = roster_df[roster_df["الفرقة"] == team_left][["رقم اللاعب", "اسم اللاعب"]]
            st.dataframe(team1_roster, use_container_width=True, hide_index=True)
            
        with col2:
            st.markdown(f"### 🏠 {team_right} (صاحب الأرض - Home)")
            team2_roster = roster_df[roster_df["الفرقة"] == team_right][["رقم اللاعب", "اسم اللاعب"]]
            st.dataframe(team2_roster, use_container_width=True, hide_index=True)

    st.divider()
    
    st.subheader("🎨 تخصيص ألوان الفرق")
    col1, col2 = st.columns(2)
    with col1:
        color_away = st.color_picker(f"لون الضيف - {team_left} ({away_abbr})", "#FFFFFF")
    with col2:
        color_home = st.color_picker(f"لون صاحب الأرض - {team_right} ({home_abbr})", "#000000")
    
    st.divider()
    
    st.subheader("📊 تفاصيل المباراة")
    
    filter_type = st.multiselect("فلترة حسب نوع الحدث:", 
                                 options=["Shot", "Substitution", "Goal", "Foul", "Other"], 
                                 default=["Shot", "Substitution", "Goal", "Foul"])
    
    filtered_df = df[df["Type"].isin(filter_type)]
    
    st.info(f"📌 تم العثور على {len(filtered_df)} حدث بناءً على الفلتر اللي اخترته.")
    
    def color_rows(row):
        if row['Team'] == away_abbr:
            return [f'background-color: {color_away}; color: {get_text_color(color_away)}'] * len(row)
        elif row['Team'] == home_abbr:
            return [f'background-color: {color_home}; color: {get_text_color(color_home)}'] * len(row)
        return [''] * len(row)
    
    styled_df = filtered_df.style.apply(color_rows, axis=1)
    st.dataframe(styled_df, use_container_width=True)
