import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
import os
import glob

# Настройка страницы
st.set_page_config(page_title="Мониторинг резистентности", layout="wide", page_icon="🦠")
st.title("🦠 Дашборд: Мониторинг антибиотикорезистентности")

# ==============================================================================
# 1. ЗАГРУЗКА И ПОДГОТОВКА ДАННЫХ
# ==============================================================================
@st.cache_data
def load_data():
    file_name = 'data.xlsx'
    
    if not os.path.exists(file_name):
        xlsx_files = glob.glob('*.xlsx')
        if xlsx_files:
            file_name = xlsx_files[0]
            st.warning(f"⚠️ Файл с точным именем не найден. Загружаю: **{file_name}**")
        else:
            st.error("❌ В папке нет ни одного .xlsx файла! Загрузите файл через панель слева.")
            return pd.DataFrame()
    
    try:
        df = pd.read_excel(file_name)
        
        # 🔥 АГРЕССИВНАЯ ОЧИСТКА ТЕКСТОВЫХ КОЛОНОК
        for col in ['Антибиотик', 'Микроорганизм', 'Отделение', 'Результат']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        
        # 🔥 РАБОТА С ДАТАМИ: 
        # Оставляем оригинальную колонку 'Дата' как есть (строка "04.05.2026") для отображения.
        # Создаем отдельную колонку 'Дата_dt' строго для внутренней фильтрации.
        if 'Дата' in df.columns:
            df['Дата_dt'] = pd.to_datetime(df['Дата'], format='%d.%m.%Y', errors='coerce')
        
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

# ==============================================================================
# 2. ОСНОВНАЯ ЛОГИКА
# ==============================================================================
if not df.empty:
    st.sidebar.header("⚙️ Параметры выборки")
    
    # 🔥 НОВОЕ: Фильтр по дате с принудительным российским форматом
    if 'Дата_dt' in df.columns and not df['Дата_dt'].isna().all():
        min_date = df['Дата_dt'].min().date()
        max_date = df['Дата_dt'].max().date()
        
        date_input = st.sidebar.date_input(
            "📅 Выберите период (или одну дату):",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            format="DD.MM.YYYY"  # 🔥 Принудительный формат ДД.ММ.ГГГГ
        )
    else:
        date_input = None

    depts = st.sidebar.multiselect(
        "🏥 Выберите отделение:", 
        options=sorted(df['Отделение'].dropna().unique()), 
        default=sorted(df['Отделение'].dropna().unique())
    )
    
    microbes = st.sidebar.multiselect(
        "🦠 Выберите микроорганизм:", 
        options=sorted(df['Микроорганизм'].dropna().unique()), 
        default=sorted(df['Микроорганизм'].dropna().unique())
    )
    
    results = st.sidebar.multiselect(
        "🧪 Выберите результат (S/I/R):", 
        options=sorted(df['Результат'].dropna().unique()), 
        default=sorted(df['Результат'].dropna().unique())
    )

    # 🔥 Логика фильтрации по дате (используем скрытую колонку Дата_dt)
    if date_input:
        if isinstance(date_input, tuple) and len(date_input) == 2:
            start_date, end_date = date_input
            date_mask = (df['Дата_dt'].dt.date >= start_date) & (df['Дата_dt'].dt.date <= end_date)
            date_info = f"{start_date.strftime('%d.%m.%Y')} – {end_date.strftime('%d.%m.%Y')}"
        else:
            date_mask = (df['Дата_dt'].dt.date == date_input)
            date_info = date_input.strftime('%d.%m.%Y')
    else:
        date_mask = pd.Series(True, index=df.index)
        date_info = "весь период"

    # Применяем все фильтры вместе
    filtered_df = df[
        (df['Отделение'].isin(depts)) &
        (df['Микроорганизм'].isin(microbes)) &
        (df['Результат'].isin(results)) &
        date_mask
    ]

    # --- МЕТРИКИ ---
    st.caption(f"📅 **Отображаются данные за период:** {date_info}")
    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Всего тестов", len(filtered_df))
    col2.metric("🛑 Резистентных (R)", len(filtered_df[filtered_df['Результат'] == 'R']))
    col3.metric("🦠 Уникальных микробов", filtered_df['Микроорганизм'].nunique())
    st.markdown("---")

    # --- ГРАФИКИ ---
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("📈 Распределение по результатам (S / I / R)")
        fig_pie = px.pie(filtered_df, names='Результат', hole=0.4, color='Результат', color_discrete_map={'S':'#2ca02c', 'I':'#ff7f0e', 'R':'#d62728'})
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_right:
        st.subheader("🏥 Профиль резистентности по отделениям")
        dept_res = filtered_df.groupby(['Отделение', 'Результат']).size().reset_index(name='count')
        fig_bar = px.bar(dept_res, x='Отделение', y='count', color='Результат', barmode='stack', color_discrete_map={'S':'#2ca02c', 'I':'#ff7f0e', 'R':'#d62728'})
        st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader("🦠 Топ-10 микроорганизмов в выборке")
    top_microbes = filtered_df['Микроорганизм'].value_counts().head(10).reset_index()
    top_microbes.columns = ['Микроорганизм', 'Количество']
    fig_microbes = px.bar(top_microbes, x='Количество', y='Микроорганизм', orientation='h', color='Количество', color_continuous_scale='Reds')
    st.plotly_chart(fig_microbes, use_container_width=True)

    # --- СТАТИСТИКА ПО АНТИБИОТИКАМ ---
    st.subheader("💊 Все антибиотики по уровню резистентности (%R)")
    valid_df = filtered_df[filtered_df['Результат'].isin(['S', 'I', 'R'])].copy()
    
    if not valid_df.empty:
        ab_stats = valid_df.groupby('Антибиотик')['Результат'].value_counts().unstack(fill_value=0)
        for col in ['S', 'I', 'R']:
            if col not in ab_stats.columns: ab_stats[col] = 0
                
        ab_stats['Total'] = ab_stats['S'] + ab_stats['I'] + ab_stats['R']
        ab_stats['%R'] = (ab_stats['R'] / ab_stats['Total']) * 100
        
        all_abs = ab_stats.sort_values(by='%R', ascending=False).reset_index()
        all_abs['label'] = all_abs.apply(lambda row: f"{row['%R']:.1f}% ({int(row['R'])} из {int(row['Total'])})", axis=1)
        
        fig_ab = px.bar(all_abs, x='%R', y='Антибиотик', orientation='h', color='%R', color_continuous_scale='OrRd', text='label', range_x=[0, 105]) 
        fig_ab.update_layout(yaxis_title='', xaxis_title='% резистентности (Кол-во R / Общее кол-во тестов)', height=max(500, len(all_abs) * 35), margin=dict(l=280))
        fig_ab.update_traces(textposition='outside', textfont_size=12, textfont_color="black")
        fig_ab.update_yaxes(autorange="reversed")
        st.plotly_chart(fig_ab, use_container_width=True)

        # ==========================================
        # 🔥 ЕДИНАЯ ТЕПЛОВАЯ КАРТА: S / I / R
        # ==========================================
        st.markdown("---")
        st.subheader("🔥 Сводная антибиотикограмма: Микроб × Антибиотик (S / I / R)")
        st.caption("💡 *Цвет ячейки показывает % резистентности (R). Внутри ячейки указан процент S, I и R. Показаны только пары с ≥ 3 тестами.*")
        
        pair_stats = valid_df.groupby(['Микроорганизм', 'Антибиотик'])['Результат'].value_counts().unstack(fill_value=0).reset_index()
        for col in ['S', 'I', 'R']:
            if col not in pair_stats.columns: pair_stats[col] = 0
                
        pair_stats['Total'] = pair_stats['S'] + pair_stats['I'] + pair_stats['R']
        pair_stats['%S'] = (pair_stats['S'] / pair_stats['Total']) * 100
        pair_stats['%I'] = (pair_stats['I'] / pair_stats['Total']) * 100
        pair_stats['%R'] = (pair_stats['R'] / pair_stats['Total']) * 100
        
        heatmap_df = pair_stats[pair_stats['Total'] >= 3].copy()
        
        if not heatmap_df.empty:
            microbe_order = heatmap_df.groupby('Микроорганизм')['%R'].mean().sort_values(ascending=False).index.tolist()
            ab_order = heatmap_df.groupby('Антибиотик')['%R'].mean().sort_values(ascending=False).index.tolist()
            
            heatmap_df['Микроорганизм'] = pd.Categorical(heatmap_df['Микроорганизм'], categories=microbe_order, ordered=True)
            heatmap_df['Антибиотик'] = pd.Categorical(heatmap_df['Антибиотик'], categories=ab_order, ordered=True)
            heatmap_df = heatmap_df.sort_values(['Микроорганизм', 'Антибиотик'])
            
            pivot_color = heatmap_df.pivot(index='Микроорганизм', columns='Антибиотик', values='%R').fillna(0)
            
            z_text, hover_text = [], []
            for microbe in pivot_color.index:
                row_z, row_hover = [], []
                for ab in pivot_color.columns:
                    mask = (heatmap_df['Микроорганизм'] == microbe) & (heatmap_df['Антибиотик'] == ab)
                    if mask.any():
                        d = heatmap_df[mask].iloc[0]
                        row_z.append(f"S:{d['%S']:.0f}%\nI:{d['%I']:.0f}%\nR:{d['%R']:.0f}%")
                        row_hover.append(f"<b>{microbe}</b> + <b>{ab}</b><br>Всего тестов: {int(d['Total'])}<br>🟢 S: {int(d['S'])} ({d['%S']:.1f}%)<br>🟡 I: {int(d['I'])} ({d['%I']:.1f}%)<br>🔴 R: {int(d['R'])} ({d['%R']:.1f}%)")
                    else:
                        row_z.append("")
                        row_hover.append(f"<b>{microbe}</b> + <b>{ab}</b><br>Нет данных (< 3 тестов)")
                z_text.append(row_z)
                hover_text.append(row_hover)
            
            fig_heatmap = ff.create_annotated_heatmap(z=pivot_color.values, x=list(pivot_color.columns), y=list(pivot_color.index), annotation_text=z_text, colorscale='RdYlGn_r', showscale=True, hovertext=hover_text, hoverinfo='text', font_colors=['black', 'white'])
            fig_heatmap.update_layout(height=max(500, len(pivot_color.index) * 35), width=max(800, len(pivot_color.columns) * 65), xaxis_title='Антибиотик', yaxis_title='Микроорганизм', xaxis=dict(tickangle=-45, tickfont=dict(size=10)), yaxis=dict(tickfont=dict(size=11)), margin=dict(l=220, b=150))
            st.plotly_chart(fig_heatmap, use_container_width=True)

        # ==========================================
        # 📋 ПОЛНАЯ ТАБЛИЦА ПО АНТИБИОТИКАМ
        # ==========================================
        st.markdown("---")
        st.subheader("📋 Полная статистика по всем антибиотикам")
        
        display_df = all_abs[['Антибиотик', 'Total', 'S', 'I', 'R', '%R']].copy()
        display_df['%S'] = (display_df['S'] / display_df['Total']) * 100
        display_df['%I'] = (display_df['I'] / display_df['Total']) * 100
        
        display_df['%R'] = display_df['%R'].round(1)
        display_df['%S'] = display_df['%S'].round(1)
        display_df['%I'] = display_df['%I'].round(1)
        
        display_df = display_df[['Антибиотик', 'Total', 'S', '%S', 'I', '%I', 'R', '%R']]
        display_df.columns = ['Антибиотик', 'Всего тестов', 'Чувствителен (S)', '% Чувствительности (S)', 'Умеренно-резист. (I)', '% Умеренно-резист. (I)', 'Резистентен (R)', '% Резистентности (R)']
        
        styled_df = display_df.style.background_gradient(subset=['% Чувствительности (S)'], cmap='Greens', vmin=0, vmax=100).background_gradient(subset=['% Умеренно-резист. (I)'], cmap='YlOrBr', vmin=0, vmax=100).background_gradient(subset=['% Резистентности (R)'], cmap='Reds', vmin=0, vmax=100).format({'% Чувствительности (S)': '{:.1f}%', '% Умеренно-резист. (I)': '{:.1f}%', '% Резистентности (R)': '{:.1f}%'})
        
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

                # ==============================================================================
        # 🏆 ПОЛНАЯ СТАТИСТИКА: ВСЕ АНТИБИОТИКИ ДЛЯ КАЖДОГО МИКРООРГАНИЗМА (ПУЛЕПРОБИВАЕМЫЙ)
        # ==============================================================================
        st.markdown("---")
        st.subheader("🏆 Полная статистика: все антибиотики для каждого микроорганизма")
        st.caption("💡 *Показаны все антибиотики, отсортированные по убыванию % чувствительности (S). Учитываются только пары, протестированные ≥ 3 раз.*")

        if not valid_df.empty:
            # 🔥 НАДЕЖНЫЙ СПОСОБ ПОДСЧЕТА (избегаем ошибок unstack)
            # 1. Считаем общее количество тестов
            total_counts = valid_df.groupby(['Микроорганизм', 'Антибиотик']).size().reset_index(name='Total')

            # 2. Считаем S, I, R отдельно
            s_counts = valid_df[valid_df['Результат'] == 'S'].groupby(['Микроорганизм', 'Антибиотик']).size().reset_index(name='S')
            i_counts = valid_df[valid_df['Результат'] == 'I'].groupby(['Микроорганизм', 'Антибиотик']).size().reset_index(name='I')
            r_counts = valid_df[valid_df['Результат'] == 'R'].groupby(['Микроорганизм', 'Антибиотик']).size().reset_index(name='R')

            # 3. Объединяем все в один датафрейм
            microbe_ab_stats = total_counts.merge(s_counts, on=['Микроорганизм', 'Антибиотик'], how='left') \
                                           .merge(i_counts, on=['Микроорганизм', 'Антибиотик'], how='left') \
                                           .merge(r_counts, on=['Микроорганизм', 'Антибиотик'], how='left')

            # 4. Заполняем пропуски (NaN) нулями и делаем целыми числами
            microbe_ab_stats = microbe_ab_stats.fillna(0)
            microbe_ab_stats['S'] = microbe_ab_stats['S'].astype(int)
            microbe_ab_stats['I'] = microbe_ab_stats['I'].astype(int)
            microbe_ab_stats['R'] = microbe_ab_stats['R'].astype(int)

            # 5. Считаем проценты
            microbe_ab_stats['%S'] = (microbe_ab_stats['S'] / microbe_ab_stats['Total']) * 100
            microbe_ab_stats['%I'] = (microbe_ab_stats['I'] / microbe_ab_stats['Total']) * 100
            microbe_ab_stats['%R'] = (microbe_ab_stats['R'] / microbe_ab_stats['Total']) * 100

            # 6. Фильтр: минимум 3 теста
            microbe_ab_stats = microbe_ab_stats[microbe_ab_stats['Total'] >= 3].copy()

            # 7. Сортируем по Микробу, а внутри него - по %S (по убыванию)
            all_effective = microbe_ab_stats.sort_values(by=['Микроорганизм', '%S'], ascending=[True, False]).copy()

            # 8. Форматируем для красивого вывода
            display_all = all_effective[['Микроорганизм', 'Антибиотик', 'Total', 'S', '%S', 'I', '%I', 'R', '%R']].copy()
            display_all['%S'] = display_all['%S'].round(1)
            display_all['%I'] = display_all['%I'].round(1)
            display_all['%R'] = display_all['%R'].round(1)

            # Переименовываем колонки для максимальной понятности
            display_all.columns = [
                'Микроорганизм', 'Антибиотик', 'Всего тестов',
                'Чувствителен (S)', '% Чувствительности (S)',
                'Умеренно-резист. (I)', '% Умеренно-резист. (I)',
                'Резистентен (R)', '% Резистентности (R)'
            ]

            # 9. Добавляем цветовую индикацию для ВСЕХ трех процентов
            styled_all = display_all.style.background_gradient(
                subset=['% Чувствительности (S)'], cmap='Greens', vmin=0, vmax=100
            ).background_gradient(
                subset=['% Умеренно-резист. (I)'], cmap='YlOrBr', vmin=0, vmax=100
            ).background_gradient(
                subset=['% Резистентности (R)'], cmap='Reds', vmin=0, vmax=100
            ).format({
                '% Чувствительности (S)': '{:.1f}%',
                '% Умеренно-резист. (I)': '{:.1f}%',
                '% Резистентности (R)': '{:.1f}%'
            })

            st.dataframe(styled_all, use_container_width=True, hide_index=True)
        else:
            st.info("Нет данных для построения таблицы (проверьте фильтры или выберите другой период).")

else:
    st.stop()
