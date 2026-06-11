import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
import os
import glob
import tempfile
import subprocess
from docx import Document

# Настройка страницы
st.set_page_config(page_title="Мониторинг резистентности", layout="wide", page_icon="🦠")
st.title("🦠 Дашборд: Мониторинг антибиотикорезистентности")

# ==============================================================================
# 1. ФУНКЦИЯ ПАРСИНГА (БЕЗ ФИО И ИСХОДНОГО ФАЙЛА)
# ==============================================================================
def parse_docx_file(file_path):
    """Извлекает данные из .docx и возвращает DataFrame. При ошибке -> None"""
    try:
        doc = Document(file_path extents=True)
        metadata = {}
        microbes = {}
        results = []
        GROUP_KEYWORDS = ["лактамы", "аминогликозиды", "фторхинолоны", "макролиды", "другие группы", 
                          "критерии", "интерпретация", "дата выдачи", "документ", "должность"]

        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                full_row_text = " ".join(cells).lower()

                # --- Таблица микробов ---
                if "Наименование микроорганизма" in full_row_text and "№" in full_row_text:
                    continue
                if len(cells) >= 3 and cells[0].isdigit() and len(cells[1]) > 5:
                    microbes[int(cells[0])] = {"name": cells[1], "coe": cells[2]}

                # --- Метаданные (ФИО УДАЛЕНО НАМЕРЕННО) ---
                for i, txt in enumerate(cells):
                    t = txt.lower()
                    if "дата приема" in t and i+1 < len(cells): metadata["Дата"] = cells[i+1]
                    if "отделение" in t and "учреждение" not in t and i+1 < len(cells): metadata["Отделение"] = cells[i+1]
                    if "биоматериал" in t and i+1 < len(cells): metadata["Биоматериал"] = cells[i+1]
                    if "№ анализа" in t and i+1 < len(cells): metadata["№_анализа"] = cells[i+1]

                # --- Антибиотикограмма ---
                header = [cell.text.strip() for cell in table.rows[0].cells]
                if len(header) > 0 and "Антибиотикограмма" in header[0]:
                    col_to_microbe = {}
                    for idx, h in enumerate(header[1:], 1):
                        if h.isdigit() and int(h) in microbes:
                            col_to_microbe[idx] = int(h)
                    
                    current_group = ""
                    for r_idx, r in enumerate(table.rows):
                        if r_idx == 0: continue
                        r_cells = [c.text.strip() for c in r.cells]
                        if not r_cells: continue
                        
                        abx_name = r_cells[0]
                        if any(kw in abx_name.lower() for kw in GROUP_KEYWORDS):
                            if not any(kw in abx_name.lower() for kw in ["критерии", "интерпретация", "дата выдачи", "документ"]):
                                current_group = abx_name
                            continue
                        
                        if not abx_name: continue
                        
                        for col_idx, mid in col_to_microbe.items():
                            if col_idx < len(r_cells):
                                res = r_cells[col_idx].strip().upper()
                                if res and res != "-":
                                    results.append({
                                        "№_анализа": metadata.get("№_анализа", ""),
                                        "Дата": metadata.get("Дата", ""),
                                        "Отделение": metadata.get("Отделение", ""),
                                        "Биоматериал": metadata.get("Биоматериал", ""),
                                        "№_микроба": mid,
                                        "Микроорганизм": microbes.get(mid, {}).get("name", ""),
                                        "КОЕ": microbes.get(mid, {}).get("coe", ""),
                                        "Группа_антибиотиков": current_group,
                                        "Антибиотик": abx_name,
                                        "Результат": res
                                        # Столбцы 'ФИО' и 'Исходный файл' намеренно исключены
                                    })
                    break 

        if not results:
            return None
            
        df = pd.DataFrame(results)
        return df

    except Exception as e:
        return str(e)

# ==============================================================================
# 2. ЗАГРУЗКА И ПОДГОТОВКА ОСНОВНЫХ ДАННЫХ
# ==============================================================================
@st.cache_data
def load_data():
    file_name = 'data.xlsx' # Убедись, что твой файл называется так, или поменяй здесь
    
    if not os.path.exists(file_name):
        # Попытка найти любой xlsx, если точного имени нет
        xlsx_files = glob.glob('*.xlsx')
        if xlsx_files:
            file_name = xlsx_files[0]
        else:
            return pd.DataFrame()
    
    try:
        df = pd.read_excel(file_name)
        # Очистка пробелов
        for col in ['Антибиотик', 'Микроорганизм', 'Отделение', 'Результат', 'Биоматериал']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        return df, file_name
    except Exception as e:
        st.error(f"❌ Ошибка чтения файла: {e}")
        return pd.DataFrame(), file_name

df, current_file_name = load_data()

# ==============================================================================
# 3. ИНТЕРФЕЙС ЗАГРУЗКИ НОВЫХ ДАННЫХ (В САЙДБАРЕ)
# ==============================================================================
st.sidebar.markdown("---")
st.sidebar.subheader("📥 Загрузка новых данных")
st.sidebar.caption("Загрузите новые .doc или .docx файлы. Данные будут объединены с текущей таблицей.")

uploaded_files = st.sidebar.file_uploader(
    "Выберите файлы", 
    type=['doc', 'docx'], 
    accept_multiple_files=True,
    help="💡 Совет: Сохраняйте файлы как .docx в Word перед загрузкой. Это гарантирует 100% успех парсинга без необходимости конвертации."
)

if uploaded_files:
    st.sidebar.info(f"Выбрано файлов: {len(uploaded_files)}")
    
    if st.sidebar.button("🔄 Обработать и обновить таблицу"):
        progress_bar = st.sidebar.progress(0)
        status_text = st.sidebar.empty()
        
        all_new_dfs = []
        errors = []
        
        for i, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Обработка: {uploaded_file.name} ({i+1}/{len(uploaded_files)})")
            progress_bar.progress((i + 1) / len(uploaded_files))
            
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name
            
            try:
                final_path = tmp_path
                # Если это старый .doc, пытаемся конвертировать (работает только если установлен LibreOffice)
                if tmp_path.lower().endswith('.doc'):
                    docx_path = tmp_path.rsplit('.', 1)[0] + '.docx'
                    try:
                        cmd = ['libreoffice', '--headless', '--convert-to', 'docx', '--outdir', os.path.dirname(tmp_path), tmp_path]
                        res = subprocess.run(cmd, capture_output=True, text=True)
                        if res.returncode == 0 and os.path.exists(docx_path):
                            final_path = docx_path
                        else:
                            errors.append(f"{uploaded_file.name}: Не удалось конвертировать .doc (нет LibreOffice). Сохраните как .docx")
                            continue
                    except FileNotFoundError:
                        errors.append(f"{uploaded_file.name}: LibreOffice не найден. Сохраните файл как .docx")
                        continue
                
                # Парсим файл
                parsed_df = parse_docx_file(final_path)
                
                if isinstance(parsed_df, pd.DataFrame):
                    all_new_dfs.append(parsed_df)
                elif isinstance(parsed_df, str):
                    errors.append(f"{uploaded_file.name}: Ошибка парсинга ({parsed_df})")
                    
            finally:
                # Очистка временных файлов
                if os.path.exists(tmp_path): os.remove(tmp_path)
                if 'docx_path' in locals() and os.path.exists(docx_path): os.remove(docx_path)

        status_text.text("Готово!")
        progress_bar.empty()

        if all_new_dfs:
            new_data_df = pd.concat(all_new_dfs, ignore_index=True)
            
            # Объединяем с существующими данными
            if not df.empty:
                # Удаляем полностью идентичные дубликаты на случай повторной загрузки
                combined_df = pd.concat([df, new_data_df], ignore_index=True).drop_duplicates()
            else:
                combined_df = new_data_df

            # Сортировка
            if 'Дата' in combined_df.columns:
                # Пытаемся отсортировать по дате, если она в формате строки
                combined_df = combined_df.sort_values(by=["Дата", "Отделение", "Микроорганизм"])

            # Предлагаем скачать обновленный файл
            st.sidebar.success(f"✅ Успешно обработано {len(all_new_dfs)} файлов! Добавлено {len(new_data_df)} строк.")
            
            output_filename = "updated_data.xlsx"
            combined_df.to_excel(output_filename, index=False)
            
            with open(output_filename, "rb") as f:
                st.sidebar.download_button(
                    label="💾 Скачать обновленную таблицу data.xlsx",
                    data=f,
                    file_name="data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            st.sidebar.caption("⚠️ Скачайте файл и замените им старый `data.xlsx` в папке проекта (или загрузите его в GitHub, если используете Cloud).")
        
        if errors:
            with st.sidebar.expander("⚠️ Ошибки при обработке некоторых файлов"):
                for err in errors:
                    st.warning(err)

# ==============================================================================
# 4. ОСНОВНАЯ ЛОГИКА ДАШБОРДА (Если данные загружены)
# ==============================================================================
if not df.empty:
    st.sidebar.header("⚙️ Параметры выборки")
    
    # Фильтр по дате
    if 'Дата' in df.columns:
        # Преобразуем даты для фильтра (игнорируя ошибки парсинга дат)
        df['Дата_dt'] = pd.to_datetime(df['Дата'], format='%d.%m.%Y', errors='coerce')
        valid_dates = df['Дата_dt'].dropna()
        if not valid_dates.empty:
            min_date = valid_dates.min().date()
            max_date = valid_dates.max().date()
            
            date_input = st.sidebar.date_input(
                "📅 Выберите период:",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                format="DD.MM.YYYY"
            )
        else:
            date_input = None
    else:
        date_input = None

    depts = st.sidebar.multiselect("🏥 Выберите отделение:", options=sorted(df['Отделение'].dropna().unique()), default=sorted(df['Отделение'].dropna().unique()))
    microbes = st.sidebar.multiselect("🦠 Выберите микроорганизм:", options=sorted(df['Микроорганизм'].dropna().unique()), default=sorted(df['Микроорганизм'].dropna().unique()))
    results = st.sidebar.multiselect("🧪 Выберите результат (S/I/R):", options=sorted(df['Результат'].dropna().unique()), default=sorted(df['Результат'].dropna().unique()))

    # Логика фильтрации по дате
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
        # 🏆 ПОЛНАЯ СТАТИСТИКА: ВСЕ АНТИБИОТИКИ ДЛЯ КАЖДОГО МИКРООРГАНИЗМА
        # ==============================================================================
        st.markdown("---")
        st.subheader("🏆 Полная статистика: все антибиотики для каждого микроорганизма")
        st.caption("💡 *Показаны все антибиотики, отсортированные по убыванию % чувствительности (S). Учитываются только пары, протестированные ≥ 3 раз.*")
        
        microbe_ab_stats = valid_df.groupby(['Микроорганизм', 'Антибиотик'])['Результат'].value_counts().unstack(fill_value=0)
        for col in ['S', 'I', 'R']:
            if col not in microbe_ab_stats.columns: microbe_ab_stats[col] = 0
            
        microbe_ab_stats['Total'] = microbe_ab_stats['S'] + microbe_ab_stats['I'] + microbe_ab_stats['R']
        microbe_ab_stats['%S'] = (microbe_ab_stats['S'] / microbe_ab_stats['Total']) * 100
        microbe_ab_stats['%I'] = (microbe_ab_stats['I'] / microbe_ab_stats['Total']) * 100
        microbe_ab_stats['%R'] = (microbe_ab_stats['R'] / microbe_ab_stats['Total']) * 100
        microbe_ab_stats = microbe_ab_stats.reset_index()
        
        microbe_ab_stats = microbe_ab_stats[microbe_ab_stats['Total'] >= 3].copy()
        all_effective = microbe_ab_stats.sort_values(by=['Микроорганизм', '%S'], ascending=[True, False]).copy()
        
        display_all = all_effective[['Микроорганизм', 'Антибиотик', 'Total', 'S', '%S', 'I', '%I', 'R', '%R']].copy()
        display_all['%S'] = display_all['%S'].round(1)
        display_all['%I'] = display_all['%I'].round(1)
        display_all['%R'] = display_all['%R'].round(1)
        
        display_all.columns = [
            'Микроорганизм', 'Антибиотик', 'Всего тестов', 
            'Чувствителен (S)', '% Чувствительности (S)', 
            'Умеренно-резист. (I)', '% Умеренно-резист. (I)', 
            'Резистентен (R)', '% Резистентности (R)'
        ]
        
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
    st.warning("⚠️ Файл с данными не найден. Пожалуйста, загрузите `data.xlsx` или используйте панель слева для загрузки новых .doc/.docx файлов.")
