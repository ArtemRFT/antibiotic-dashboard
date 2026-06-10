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
        # Убираем лишние пробелы в названиях антибиотиков и отделений
df['Антибиотик'] = df['Антибиотик'].astype(str).str.strip()
df['Отделение'] = df['Отделение'].astype(str).str.strip()
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

    st.subheader("💊 Топ-10 антибиотиков по уровню резистентности (%R)")
    
    # 1. Фильтруем мусор: оставляем только строки, где Результат строго S, I или R
    # (Это уберет аномалии вроде текста "ПРОТИВОГРИБКОВЫЕ ПРЕПАРАТЫ" вместо буквы)
    valid_df = filtered_df[filtered_df['Результат'].isin(['S', 'I', 'R'])].copy()
    
    if not valid_df.empty:
        # 2. Считаем распределение S, I, R для каждого антибиотика
        ab_stats = valid_df.groupby('Антибиотик')['Результат'].value_counts().unstack(fill_value=0)
        
        # Страховка: если вдруг для какого-то антибиотика нет S, I или R, создаем нулевые колонки
        for col in ['S', 'I', 'R']:
            if col not in ab_stats.columns:
                ab_stats[col] = 0
                
        # 3. Считаем общее кол-во тестов и истинный процент резистентности (%R)
        ab_stats['Total'] = ab_stats['S'] + ab_stats['I'] + ab_stats['R']
        ab_stats['%R'] = (ab_stats['R'] / ab_stats['Total']) * 100
        
        # 4. Сортируем именно по % резистентности, а не по абсолютным числам! Берем Топ-10
        top_10_abs = ab_stats.sort_values(by='%R', ascending=False).head(10).reset_index()
        
        # 5. Создаем умные подписи на графиках: "85.7% (12 из 14)"
        top_10_abs['label'] = top_10_abs.apply(
            lambda row: f"{row['%R']:.1f}% ({int(row['R'])} из {int(row['Total'])})", axis=1
        )
        
        # 6. Строим красивый график
        fig_ab = px.bar(top_10_abs, x='%R', y='Антибиотик', orientation='h', 
                        color='%R', color_continuous_scale='OrRd',
                        text='label', range_x=[0, 105]) # range_x чуть больше 100, чтобы текст влез
        
        fig_ab.update_layout(
            yaxis_title='', 
            xaxis_title='% резистентности (Кол-во R / Общее кол-во тестов)',
            height=500,
            margin=dict(l=280) # Большой отступ слева, чтобы влезли длинные названия
        )
        fig_ab.update_traces(textposition='outside', textfont_size=12, textfont_color="black")
        fig_ab.update_yaxes(autorange="reversed") # Самый опасный антибиотик теперь сверху
        
        st.plotly_chart(fig_ab, use_container_width=True)
        
        # Небольшая сноска под графиком
        st.caption("💡 *График отсортирован по доле резистентных штаммов (%R). В скобках указано абсолютное число R и общее количество тестов для данного препарата.*")
    else:
        st.info("В выбранной выборке нет валидных результатов S/I/R для построения графика.")
