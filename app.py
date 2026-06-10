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

    st.subheader("💊 Все антибиотики по уровню резистентности (%R)")
    
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
        
        # 4. Сортируем по % резистентности (БЕЗ ограничения .head(10) - берем ВСЕ)
        all_abs = ab_stats.sort_values(by='%R', ascending=False).reset_index()
        
        # 5. Создаем умные подписи на графиках: "85.7% (12 из 14)"
        all_abs['label'] = all_abs.apply(
            lambda row: f"{row['%R']:.1f}% ({int(row['R'])} из {int(row['Total'])})", axis=1
        )
        
        # 6. Динамическая высота графика, чтобы все влезло и было удобно читать
        # (35 пикселей на каждый антибиотик + минимум 500)
        chart_height = max(500, len(all_abs) * 35) 
        
        fig_ab = px.bar(all_abs, x='%R', y='Антибиотик', orientation='h', 
                        color='%R', color_continuous_scale='OrRd',
                        text='label', range_x=[0, 105]) 
        
        fig_ab.update_layout(
            yaxis_title='', 
            xaxis_title='% резистентности (Кол-во R / Общее кол-во тестов)',
            height=chart_height,
            margin=dict(l=280) # Большой отступ слева для длинных названий
        )
        fig_ab.update_traces(textposition='outside', textfont_size=12, textfont_color="black")
        fig_ab.update_yaxes(autorange="reversed") # Самый опасный антибиотик строго сверху
        
        st.plotly_chart(fig_ab, use_container_width=True)
        
        # ==========================================
        # БОНУС: Интерактивная таблица со всеми данными
        # ==========================================
        st.markdown("---")
                # ==========================================
        # 🔥 ТЕПЛОВАЯ КАРТА: Микроорганизм × Антибиотик
        # ==========================================
        st.markdown("---")
        st.subheader("🔥 Антибиотикограмма: % резистентности по парам Микроб × Антибиотик")
        st.caption("💡 *Чем краснее ячейка — тем выше % резистентности. Показаны только пары, где было ≥ 3 тестов (чтобы исключить случайные 100% из 1 анализа).*")
        
        # Группируем по паре (Микроб, Антибиотик)
        pair_stats = valid_df.groupby(['Микроорганизм', 'Антибиотик'])['Результат'].value_counts().unstack(fill_value=0)
        for col in ['S', 'I', 'R']:
            if col not in pair_stats.columns:
                pair_stats[col] = 0
        pair_stats['Total'] = pair_stats['S'] + pair_stats['I'] + pair_stats['R']
        pair_stats['%R'] = (pair_stats['R'] / pair_stats['Total']) * 100
        
        # Фильтр: минимум 3 теста на пару (убираем случайности)
        pair_stats = pair_stats[pair_stats['Total'] >= 3].reset_index()
        
        if not pair_stats.empty:
            # Берем топ-15 самых частых микробов, чтобы карта влезла
            top_microbes = valid_df['Микроорганизм'].value_counts().head(15).index.tolist()
            heatmap_df = pair_stats[pair_stats['Микроорганизм'].isin(top_microbes)].copy()
            
            # Строим матрицу через pivot
            pivot = heatmap_df.pivot(index='Микроорганизм', columns='Антибиотик', values='%R').fillna(0)
            
            # Сортируем: самые "проблемные" микробы сверху, самые "проблемные" антибиотики слева
            pivot = pivot.loc[pivot.mean(axis=1).sort_values(ascending=False).index]
            pivot = pivot[pivot.mean(axis=0).sort_values(ascending=False).index]
            
            # Рисуем heatmap
            import plotly.figure_factory as ff
            
            # Подписи внутри ячеек: "85%" или пусто, если 0
            hover_text = [[f"{pivot.columns[j]}<br>{pivot.index[i]}<br>%R: {pivot.iloc[i, j]:.1f}%<br>(n={int(heatmap_df[(heatmap_df['Микроорганизм']==pivot.index[i]) & (heatmap_df['Антибиотик']==pivot.columns[j])]['Total'].values[0])})" 
                           for j in range(len(pivot.columns))] for i in range(len(pivot.index))]
            
            z_text = [[f"{v:.0f}%" if v > 0 else "" for v in row] for row in pivot.values]
            
            fig_heatmap = ff.create_annotated_heatmap(
                z=pivot.values,
                x=list(pivot.columns),
                y=list(pivot.index),
                annotation_text=z_text,
                colorscale='RdYlGn_r',  # Зеленый -> Желтый -> Красный
                showscale=True,
                hovertext=hover_text,
                hoverinfo='text',
                font_colors=['white', 'black'],
            )
            
            fig_heatmap.update_layout(
                height=max(500, len(pivot.index) * 35),
                width=max(800, len(pivot.columns) * 50),
                xaxis_title='Антибиотик',
                yaxis_title='Микроорганизм',
                xaxis=dict(tickangle=-45, tickfont=dict(size=10)),
                yaxis=dict(tickfont=dict(size=11)),
                margin=dict(l=200, b=200)
            )
            st.plotly_chart(fig_heatmap, use_container_width=True)
        else:
            st.info("Недостаточно данных для построения тепловой карты (нужно минимум 3 теста на пару).")
        
        # ==========================================
        # 📊 СВОДКА ПО ГРУППАМ АНТИБИОТИКОВ
        # ==========================================
        st.markdown("---")
        st.subheader("📊 Резистентность в разрезе групп антибиотиков")
        
        if 'Группа_антибиотиков' in valid_df.columns:
            group_stats = valid_df.groupby('Группа_антибиотиков')['Результат'].value_counts().unstack(fill_value=0)
            for col in ['S', 'I', 'R']:
                if col not in group_stats.columns:
                    group_stats[col] = 0
            group_stats['Total'] = group_stats['S'] + group_stats['I'] + group_stats['R']
            group_stats['%R'] = (group_stats['R'] / group_stats['Total']) * 100
            group_stats = group_stats.sort_values(by='%R', ascending=False).reset_index()
            
            group_stats['label'] = group_stats.apply(
                lambda row: f"{row['%R']:.1f}% ({int(row['R'])}/{int(row['Total'])})", axis=1
            )
            
            fig_groups = px.bar(group_stats, x='Группа_антибиотиков', y='%R', 
                                color='%R', color_continuous_scale='OrRd',
                                text='label', range_y=[0, 105])
            fig_groups.update_layout(
                xaxis_title='Группа антибиотиков',
                yaxis_title='% резистентности',
                height=450,
                xaxis=dict(tickangle=-20)
            )
            fig_groups.update_traces(textposition='outside', textfont_size=12)
            st.plotly_chart(fig_groups, use_container_width=True)
        
        # ==========================================
        # 📋 ПОЛНАЯ ТАБЛИЦА (осталась как была)
        # ==========================================
        st.markdown("---")
        st.subheader("📋 Полная статистика по всем антибиотикам")
        
        display_df = all_abs[['Антибиотик', 'Total', 'S', 'I', 'R', '%R']].copy()
        display_df['%R'] = display_df['%R'].round(1)
        display_df.columns = ['Антибиотик', 'Всего тестов', 'Чувствителен (S)', 'Умеренно-резист. (I)', 'Резистентен (R)', '% Резистентности']
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        st.caption("💡 *Все графики и таблица учитывают только валидные результаты S/I/R и строятся на основе текущих фильтров в боковой панели.*")
    else:
        st.info("В выбранной выборке нет валидных результатов S/I/R для построения графика.")
