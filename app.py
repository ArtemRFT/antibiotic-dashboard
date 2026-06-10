import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(page_title="Мониторинг резистентности", layout="wide", page_icon="🦠")
st.title("🦠 Дашборд: Мониторинг антибиотикорезистентности")

@st.cache_data
def load_data():
    # Укажите здесь точное имя вашего файла
    file_name = 'data.xlsx' 
    if not os.path.exists(file_name):
        st.error(f"❌ Файл {file_name} не найден!")
        return pd.DataFrame()
    
    try:
        df = pd.read_excel(file_name)
        # Проверка на наличие нужных колонок
        required_cols = ['Отделение', 'Микроорганизм', 'Результат', 'Антибиотик']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            st.error(f"❌ В файле отсутствуют колонки: {missing}. Проверьте структуру Excel.")
            return pd.DataFrame()
        return df
    except Exception as e:
        st.error(f"❌ Ошибка чтения файла: {e}")
        return pd.DataFrame()

df = load_data()

if not df.empty:
    st.sidebar.header("⚙️ Параметры выборки")
    
    depts = st.sidebar.multiselect("Выберите отделение:", 
                                   options=sorted(df['Отделение'].dropna().unique()), 
                                   default=sorted(df['Отделение'].dropna().unique()))
    
    microbes = st.sidebar.multiselect("Выберите микроорганизм:", 
                                      options=sorted(df['Микроорганизм'].dropna().unique()), 
                                      default=sorted(df['Микроорганизм'].dropna().unique()))
    
    results = st.sidebar.multiselect("Выберите результат (S/I/R):", 
                                     options=sorted(df['Результат'].dropna().unique()), 
                                     default=sorted(df['Результат'].dropna().unique()))

    filtered_df = df[
        (df['Отделение'].isin(depts)) &
        (df['Микроорганизм'].isin(microbes)) &
        (df['Результат'].isin(results))
    ]

    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Всего тестов", len(filtered_df))
    col2.metric("🛑 Резистентных (R)", len(filtered_df[filtered_df['Результат'] == 'R']))
    col3.metric("🦠 Уникальных микробов", filtered_df['Микроорганизм'].nunique())

    st.markdown("---")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("📈 Распределение по результатам (S / I / R)")
        fig_pie = px.pie(filtered_df, names='Результат', hole=0.4, 
                         color='Результат', 
                         color_discrete_map={'S':'#2ca02c', 'I':'#ff7f0e', 'R':'#d62728'})
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_right:
        st.subheader("🏥 Профиль резистентности по отделениям")
        dept_res = filtered_df.groupby(['Отделение', 'Результат']).size().reset_index(name='count')
        fig_bar = px.bar(dept_res, x='Отделение', y='count', color='Результат', barmode='stack',
                         color_discrete_map={'S':'#2ca02c', 'I':'#ff7f0e', 'R':'#d62728'})
        st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader("🦠 Топ-10 микроорганизмов в выборке")
    top_microbes = filtered_df['Микроорганизм'].value_counts().head(10).reset_index()
    top_microbes.columns = ['Микроорганизм', 'Количество']
    fig_microbes = px.bar(top_microbes, x='Количество', y='Микроорганизм', orientation='h', color='Количество', color_continuous_scale='Reds')
    st.plotly_chart(fig_microbes, use_container_width=True)

    st.subheader("💊 Топ-10 антибиотиков с наибольшим числом случаев резистентности (R)")
    df_r = filtered_df[filtered_df['Результат'] == 'R']
    if not df_r.empty:
        top_ab = df_r['Антибиотик'].value_counts().head(10).reset_index()
        top_ab.columns = ['Антибиотик', 'Случаев резистентности']
        fig_ab = px.bar(top_ab, x='Случаев резистентности', y='Антибиотик', orientation='h', color='Случаев резистентности', color_continuous_scale='OrRd')
        st.plotly_chart(fig_ab, use_container_width=True)
    else:
        st.info("В выбранной выборке нет результатов 'R' (Резистентность).")