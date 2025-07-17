import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import io
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import gspread
from google.oauth2.service_account import Credentials

# Konfigurasi halaman
st.set_page_config(
    page_title="📊 Analisis Pendapatan & Pesanan",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS kustom untuk penataan yang lebih baik
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        text-align: center;
        color: white;
    }
    
    .metric-container {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 4px solid #667eea;
    }
    
    .status-success {
        background: #d4edda;
        color: #155724;
        padding: 0.75rem;
        border-radius: 5px;
        border-left: 4px solid #28a745;
    }
    
    .status-warning {
        background: #fff3cd;
        color: #856404;
        padding: 0.75rem;
        border-radius: 5px;
        border-left: 4px solid #ffc107;
    }
    
    .status-error {
        background: #f8d7da;
        color: #721c24;
        padding: 0.75rem;
        border-radius: 5px;
        border-left: 4px solid #dc3545;
    }
    
    .sidebar .stSelectbox > div > div {
        background-color: #f8f9fa;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
    }
    
    .upload-section {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 8px;
        border: 2px dashed #dee2e6;
        margin-bottom: 1rem;
    }
    
    .chart-container {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

class IncomeApp:
    # 1. Konfigurasi Google Sheets
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    gc = gspread.authorize(creds)

    SHEET_ID = "1Kuy05JjpsZPoYZI0DcdaY7G_2_i63tdJOKTy-PWH26M"  # dari URL Google Sheet
    SHEET_NAME = "Sheet1"

    def __init__(self):
        self.cost_data = self.load_cost_data()
    
    def load_cost_data(self):
        sheet = self.gc.open_by_key(self.SHEET_ID).worksheet(self.SHEET_NAME)
        records = sheet.get_all_records()
        return {row["product_name"]: float(row["cost_per_unit"]) for row in records}

    def save_cost_data(self, cost_dict):
        sheet = self.gc.open_by_key(self.SHEET_ID).worksheet(self.SHEET_NAME)
        sheet.clear()
        # pakai keyword atau urutan baru
        sheet.update(values=[["product_name", "cost_per_unit"]], range_name="A1")
        rows = [[k, v] for k, v in cost_dict.items()]
        sheet.update(values=rows, range_name="A2")
    
    def get_product_cost(self, product_name, cost_data):
        """Mendapatkan biaya produk dari data biaya"""
        return float(cost_data.get(product_name, 0.0))
    
    def process_data(self, pesanan_data, income_data, cost_data):
        """Memproses dan menggabungkan data"""
        # Filter pesanan selesai
        df1 = pesanan_data[pesanan_data['Order Status'] == 'Selesai']
        
        # Hapus duplikat dari data pendapatan
        df2 = income_data.drop_duplicates(subset=['Order/adjustment ID'])
        
        # Gabungkan data
        merged = pd.merge(df1, df2, left_on='Order ID', right_on='Order/adjustment ID', how='inner')
        
        if merged.empty:
            return None, None
        
        # Buat ringkasan
        summary = merged.groupby(['Seller SKU', 'Product Name', 'Variation'], as_index=False).agg(
            TotalQty=('Quantity', 'sum'),
            Revenue=('Total settlement amount', 'sum')
        )
        
        # Tambahkan perhitungan biaya
        summary['Cost per Unit'] = summary['Product Name'].apply(
            lambda x: self.get_product_cost(x, cost_data)
        )
        summary['Total Cost'] = summary['TotalQty'] * summary['Cost per Unit']
        summary['Profit'] = summary['Revenue'] - summary['Total Cost']
        summary['Profit Margin %'] = (summary['Profit'] / summary['Revenue'] * 100).round(2)
        summary['Share 60%'] = summary['Profit'] * 0.6
        summary['Share 40%'] = summary['Profit'] * 0.4
        
        return merged, summary
    
    def create_excel_report(self, merged_data, summary_data, cost_data):
        """Membuat laporan Excel"""
        output = io.BytesIO()
        
        # Hitung total
        unique_orders = merged_data.drop_duplicates(subset=['Order ID'])
        total_orders = unique_orders['Order ID'].nunique()
        total_revenue = unique_orders['Total settlement amount'].sum()
        total_qty = merged_data['Quantity'].sum()
        
        # Ringkasan berdasarkan SKU
        summary_by_sku = (
            merged_data.groupby('Seller SKU', as_index=False)
            .agg({
                'Quantity': 'sum',
                'Order ID': 'nunique',
                'Total settlement amount': 'sum'
            })
            .rename(columns={
                'Quantity': 'Total Quantity',
                'Order ID': 'Total Orders',
                'Total settlement amount': 'Total Revenue'
            })
        )
        
        # Dapatkan nama produk pertama untuk setiap SKU
        sku_products = merged_data.groupby('Seller SKU')['Product Name'].first().to_dict()
        summary_by_sku['Cost per Unit'] = summary_by_sku['Seller SKU'].map(
            lambda sku: self.get_product_cost(sku_products.get(sku, ''), cost_data)
        )
        summary_by_sku['Total Cost'] = summary_by_sku['Total Quantity'] * summary_by_sku['Cost per Unit']
        summary_by_sku['Profit'] = summary_by_sku['Total Revenue'] - summary_by_sku['Total Cost']
        summary_by_sku['Profit Margin %'] = (summary_by_sku['Profit'] / summary_by_sku['Total Revenue'] * 100).round(2)
        summary_by_sku['Share 60%'] = summary_by_sku['Profit'] * 0.6
        summary_by_sku['Share 40%'] = summary_by_sku['Profit'] * 0.4
        
        # Hitung total biaya dan profit
        total_cost = summary_by_sku['Total Cost'].sum()
        total_profit = total_revenue - total_cost
        total_share_60 = total_profit * 0.6
        total_share_40 = total_profit * 0.4
        
        # Analisis penjualan harian
        date_column = None
        possible_date_columns = [
            'Order created time(UTC)', 'Order creation time', 'Order Creation Time', 
            'Creation Time', 'Date', 'Order Date', 'Order created time', 'Created time'
        ]
        
        for col in possible_date_columns:
            if col in merged_data.columns:
                date_column = col
                break
        
        if date_column:
            try:
                merged_data_copy = merged_data.copy()
                merged_data_copy['Order Date'] = pd.to_datetime(merged_data_copy[date_column]).dt.date
                daily_sales = (
                    merged_data_copy.groupby('Order Date', as_index=False)
                    .agg({
                        'Quantity': 'sum',
                        'Order ID': 'nunique',
                        'Total settlement amount': 'sum'
                    })
                    .rename(columns={
                        'Quantity': 'Daily Quantity',
                        'Order ID': 'Daily Orders',
                        'Total settlement amount': 'Daily Revenue'
                    })
                )
            except:
                daily_sales = pd.DataFrame({
                    'Order Date': ['Data tidak tersedia'],
                    'Daily Quantity': [0],
                    'Daily Orders': [0],
                    'Daily Revenue': [0]
                })
        else:
            daily_sales = pd.DataFrame({
                'Order Date': ['Kolom tanggal tidak ditemukan'],
                'Daily Quantity': [0],
                'Daily Orders': [0],
                'Daily Revenue': [0]
            })
        
        # Produk terbaik berdasarkan profit
        top_products = summary_data.nlargest(10, 'Profit')
        
        # Buat penulis Excel
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            # Tentukan format
            title_format = workbook.add_format({
                'bold': True, 'font_size': 16, 'align': 'center',
                'bg_color': '#4472C4', 'font_color': 'white'
            })
            
            header_format = workbook.add_format({
                'bold': True, 'font_size': 12,
                'bg_color': '#D9E2F3', 'border': 1
            })
            
            currency_format = workbook.add_format({
                'num_format': '#,##0', 'border': 1
            })
            
            number_format = workbook.add_format({
                'num_format': '#,##0', 'border': 1
            })
            
            percent_format = workbook.add_format({
                'num_format': '0.00%', 'border': 1
            })
            
            # Lembar ringkasan
            overview_sheet = workbook.add_worksheet('Ringkasan')
            overview_sheet.set_column('A:B', 25)
            overview_sheet.set_column('C:C', 20)
            
            row = 0
            overview_sheet.merge_range(f'A{row+1}:C{row+1}', 'LAPORAN PENJUALAN & ANALISIS PROFIT', title_format)
            row += 2
            
            # Rentang tanggal
            if date_column and date_column in merged_data.columns:
                try:
                    date_range_start = pd.to_datetime(merged_data[date_column]).min()
                    date_range_end = pd.to_datetime(merged_data[date_column]).max()
                except:
                    date_range_start = datetime.now()
                    date_range_end = datetime.now()
            else:
                date_range_start = datetime.now()
                date_range_end = datetime.now()
            
            overview_sheet.write(row, 0, f'Periode:', header_format)
            overview_sheet.write(row, 1, f'{date_range_start.strftime("%d/%m/%Y")} - {date_range_end.strftime("%d/%m/%Y")}')
            row += 1
            
            overview_sheet.write(row, 0, f'Dibuat:', header_format)
            overview_sheet.write(row, 1, f'{datetime.now().strftime("%d %B %Y %H:%M")}')
            row += 3
            
            # Metrik kunci
            overview_sheet.write(row, 0, 'RINGKASAN PENJUALAN & PROFIT', header_format)
            row += 1
            overview_sheet.write(row, 0, 'Total Pesanan:')
            overview_sheet.write(row, 1, total_orders, number_format)
            row += 1
            overview_sheet.write(row, 0, 'Total Kuantitas:')
            overview_sheet.write(row, 1, total_qty, number_format)
            row += 1
            overview_sheet.write(row, 0, 'Total Pendapatan:')
            overview_sheet.write(row, 1, total_revenue, currency_format)
            row += 1
            overview_sheet.write(row, 0, 'Total Biaya:')
            overview_sheet.write(row, 1, total_cost, currency_format)
            row += 1
            overview_sheet.write(row, 0, 'Total Profit:')
            overview_sheet.write(row, 1, total_profit, currency_format)
            row += 1
            overview_sheet.write(row, 0, 'Bagian 60%:')
            overview_sheet.write(row, 1, total_share_60, currency_format)
            row += 1
            overview_sheet.write(row, 0, 'Bagian 40%:')
            overview_sheet.write(row, 1, total_share_40, currency_format)
            row += 2
            
            # Hitung metrik tambahan
            avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
            avg_profit_per_order = total_profit / total_orders if total_orders > 0 else 0
            overall_profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
            
            overview_sheet.write(row, 0, 'Nilai Rata-rata Pesanan:')
            overview_sheet.write(row, 1, avg_order_value, currency_format)
            row += 1
            overview_sheet.write(row, 0, 'Rata-rata Profit per Pesanan:')
            overview_sheet.write(row, 1, avg_profit_per_order, currency_format)
            row += 1
            overview_sheet.write(row, 0, 'Margin Profit Keseluruhan:')
            overview_sheet.write(row, 1, overall_profit_margin / 100, percent_format)
            
            # Tulis lembar lainnya
            summary_data.to_excel(writer, index=False, sheet_name='Ringkasan per Produk')
            summary_by_sku.to_excel(writer, index=False, sheet_name='Ringkasan per SKU')
            daily_sales.to_excel(writer, index=False, sheet_name='Penjualan Harian')
            top_products.to_excel(writer, index=False, sheet_name='Produk Teratas')
            
            # Daftar biaya produk
            if cost_data:
                cost_df = pd.DataFrame(list(cost_data.items()), columns=["Product Name", "Cost per Unit"])
                cost_df = cost_df.sort_values(by="Product Name")
                cost_df.to_excel(writer, index=False, sheet_name='Daftar Biaya Produk')
        
        output.seek(0)
        return output

    

    def generate_ai_summary(self, summary_df):
        # --- Hitung metrik BERSIH (tanpa duplikat order) ---
        if st.session_state.merged_data is None:
            return "Data belum diproses."

        unique_orders = st.session_state.merged_data.drop_duplicates(subset=['Order ID'])
        total_r = unique_orders['Total settlement amount'].sum()
        total_cost = summary_df['Total Cost'].sum()
        total_p = total_r - total_cost
        avg_m   = summary_df['Profit Margin %'].mean()

        top = summary_df.nlargest(5, 'Profit')[['Product Name', 'Profit', 'Profit Margin %']]

        prompt = f"""
    Kamu adalah Chief Data Scientist e-commerce. Buat laporan strategis 360° dari data berikut:

    📊 Total Pendapatan               : Rp {total_r:,.0f}
    📈 Total Profit                   : Rp {total_p:,.0f}
    📉 Margin Rata-rata               : {avg_m:.1f}%

    5 Produk Ter-Profit:
    {top.to_string(index=False)}

    Deliverables:
    1. Executive summary 3 kalimat
    2. 3 SKU prioritas optimize
    3. 2 pricing strategy SKU margin rendah
    4. 2 saran strategi peningkatan profit
        """

        # --- Tombol ke ChatGPT ---
        from urllib.parse import quote
        encoded = quote(prompt)
        chatgpt_url = f"https://chat.openai.com/?q={encoded}"

        st.markdown(
            f'<a href="{chatgpt_url}" target="_blank" rel="noopener noreferrer">'
            '💬 Buka ChatGPT (tab baru)</a>',
            unsafe_allow_html=True
        )

        st.text_area("📋 Copy prompt:", value=prompt, height=280)
        #return prompt  # opsional, sudah tampil di text_area
        

def show_data_upload_section():
    """Bagian unggah data yang ditingkatkan"""
    st.markdown("### 📁 Unggah Data")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<div class="upload-section">', unsafe_allow_html=True)
        st.markdown("**📊 Pesanan Selesai**")
        pesanan_file = st.file_uploader(
            "Unggah file Excel dengan pesanan selesai",
            type=['xlsx', 'xls'],
            key="pesanan",
            help="File harus berisi data pesanan dengan kolom 'Order Status'"
        )
        
        if pesanan_file:
            try:
                df = pd.read_excel(pesanan_file, header=0, skiprows=[1])
                df.columns = df.columns.str.strip()
                st.session_state.pesanan_data = df
                st.markdown(f'<div class="status-success">✅ Pesanan dimuat: {len(df):,} baris</div>', unsafe_allow_html=True)
                
                with st.expander("📋 Pratinjau Data"):
                    st.dataframe(df.head(), use_container_width=True)
                    
            except Exception as e:
                st.markdown(f'<div class="status-error">❌ Kesalahan memuat file: {str(e)}</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="upload-section">', unsafe_allow_html=True)
        st.markdown("**💰 Data Pendapatan**")
        income_file = st.file_uploader(
            "Unggah file Excel dengan data pendapatan",
            type=['xlsx', 'xls'],
            key="income",
            help="File harus berisi kolom 'Order/adjustment ID' dan 'Total settlement amount'"
        )
        
        if income_file:
            try:
                df = pd.read_excel(income_file)
                df.columns = df.columns.str.strip()
                st.session_state.income_data = df
                st.markdown(f'<div class="status-success">✅ Pendapatan dimuat: {len(df):,} baris</div>', unsafe_allow_html=True)
                
                with st.expander("📋 Pratinjau Data"):
                    st.dataframe(df.head(), use_container_width=True)
                    
            except Exception as e:
                st.markdown(f'<div class="status-error">❌ Kesalahan memuat file: {str(e)}</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

def show_metrics_dashboard():
    """Dasbor metrik yang ditingkatkan"""
    if st.session_state.summary_data is not None:
        st.markdown("### 📊 Dasbor Kinerja")
        
        # Hitung metrik kunci
        unique_orders = st.session_state.merged_data.drop_duplicates(subset=['Order ID'])
        total_orders = unique_orders['Order ID'].nunique()
        total_revenue = unique_orders['Total settlement amount'].sum()
        total_cost = st.session_state.summary_data['Total Cost'].sum()
        total_profit = total_revenue - total_cost
        total_share_60 = total_profit * 0.6
        total_share_40 = total_profit * 0.4
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
        profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        # Metrik utama
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="💼 Total Pesanan",
                value=f"{total_orders:,}",
                delta=f"AOV: Rp {avg_order_value:,.0f}"
            )
        
        with col2:
            st.metric(
                label="💰 Total Pendapatan",
                value=f"Rp {total_revenue:,.0f}",
                delta=f"Biaya: Rp {total_cost:,.0f}"
            )
        
        with col3:
            st.metric(
                label="📈 Total Profit",
                value=f"Rp {total_profit:,.0f}",
                delta=f"{profit_margin:.1f}% margin"
            )
        
        with col4:
            st.metric(
                label="🤝 Pembagian Bagian",
                value=f"60%: Rp {total_share_60:,.0f}",
                delta=f"40%: Rp {total_share_40:,.0f}"
            )
        
        # AI Summary
        st.markdown("---")
        if st.button("📄 Tampilkan Ringkasan (Copy ke ChatGPT)", type="secondary"):
            if st.session_state.summary_data is not None:
                summary_text = app.generate_ai_summary(st.session_state.summary_data)
                st.markdown("### 📋 Ringkasan Teks")
                st.code(summary_text, language="text")
            else:
                st.warning("⚠️ Proses data terlebih dahulu.")
        
        # Bagian grafik
        st.markdown("---")
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.markdown("**📊 10 Produk Teratas berdasarkan Pendapatan**")
            
            top_revenue = st.session_state.summary_data.nlargest(10, 'Revenue')
            
            fig = px.bar(
                top_revenue,
                x='Revenue',
                y='Product Name',
                orientation='h',
                title="Pendapatan per Produk",
                color='Profit Margin %',
                color_continuous_scale='RdYlGn',
                text='Revenue'
            )
            
            fig.update_layout(
                height=400,
                showlegend=False,
                yaxis={'categoryorder': 'total ascending'}
            )
            
            fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
            st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        with chart_col2:
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.markdown("**📈 Distribusi Margin Profit**")
            
            fig = px.histogram(
                st.session_state.summary_data,
                x='Profit Margin %',
                nbins=20,
                title="Distribusi Margin Profit",
                color_discrete_sequence=['#667eea']
            )
            
            fig.add_vline(
                x=st.session_state.summary_data['Profit Margin %'].mean(),
                line_dash="dash",
                line_color="red",
                annotation_text=f"Rata-rata: {st.session_state.summary_data['Profit Margin %'].mean():.1f}%"
            )
            
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Analisis terperinci
        st.markdown("---")
        st.markdown("### 🔍 Analisis Terperinci")
        
        analysis_col1, analysis_col2 = st.columns(2)
        
        with analysis_col1:
            st.markdown("**🏆 Performa Teratas**")
            
            top_profit = st.session_state.summary_data.nlargest(5, 'Profit')[['Product Name', 'Profit', 'Profit Margin %']]
            top_profit['Profit'] = top_profit['Profit'].apply(lambda x: f"Rp {x:,.0f}")
            top_profit['Profit Margin %'] = top_profit['Profit Margin %'].apply(lambda x: f"{x:.1f}%")
            
            st.dataframe(top_profit, use_container_width=True, hide_index=True)
        
        with analysis_col2:
            st.markdown("**⚠️ Produk Margin Rendah**")
            
            low_margin = st.session_state.summary_data.nsmallest(5, 'Profit Margin %')[['Product Name', 'Profit', 'Profit Margin %']]
            low_margin['Profit'] = low_margin['Profit'].apply(lambda x: f"Rp {x:,.0f}")
            low_margin['Profit Margin %'] = low_margin['Profit Margin %'].apply(lambda x: f"{x:.1f}%")
            
            st.dataframe(low_margin, use_container_width=True, hide_index=True)

def show_cost_management():
    """Antarmuka manajemen biaya yang ditingkatkan"""
    st.markdown("### 💸 Manajemen Biaya")
    
    # Bilah aksi cepat
    action_col1, action_col2, action_col3 = st.columns(3)
    
    with action_col1:
        if st.button("📥 Impor Biaya", help="Impor biaya dari file JSON"):
            st.info("Unggah file JSON dengan data biaya")
    
    with action_col2:
        if st.button("📤 Ekspor Biaya", help="Unduh data biaya saat ini"):
            st.download_button(
                label="💾 Unduh JSON",
                data=json.dumps(st.session_state.cost_data, ensure_ascii=False, indent=2),
                file_name=f"product_costs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
    
    with action_col3:
        if st.button("🔄 Segarkan Data", help="Muat ulang data biaya dari file"):
            st.session_state.cost_data = app.load_cost_data()
            st.rerun()
    
    st.markdown("---")
    
    # Form manajemen biaya
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("**Tambah/Edit Biaya Produk**")
        
        # Pemilihan produk dengan pencarian
        if st.session_state.pesanan_data is not None:
            products = sorted(st.session_state.pesanan_data['Product Name'].astype(str).unique())
            selected_product = st.selectbox(
                "🔍 Pilih Produk",
                options=products,
                key="product_select",
                help="Cari dan pilih produk dari data pesanan Anda"
            )
        else:
            selected_product = st.text_input(
                "📝 Nama Produk",
                key="product_input",
                help="Masukkan nama produk secara manual"
            )
        
        # Input biaya dengan nilai saat ini
        current_cost = st.session_state.cost_data.get(selected_product, 0.0)
        cost_input = st.number_input(
            "💰 Biaya per Unit",
            min_value=0.0,
            value=current_cost,
            format="%.2f",
            key="cost_input",
            help=f"Biaya saat ini: Rp {current_cost:,.2f}"
        )
        
        # Tombol aksi
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        
        with btn_col1:
            if st.button("💾 Simpan Biaya", type="primary"):
                if selected_product and cost_input >= 0:
                    st.session_state.cost_data[selected_product] = cost_input
                    app.save_cost_data(st.session_state.cost_data)
                    st.success(f"✅ Biaya disimpan untuk {selected_product}")
                    st.rerun()
                else:
                    st.warning("⚠️ Masukkan produk dan biaya yang valid")
        
        with btn_col2:
            if st.button("🗑️ Hapus Biaya", type="secondary"):
                if selected_product in st.session_state.cost_data:
                    del st.session_state.cost_data[selected_product]
                    app.save_cost_data(st.session_state.cost_data)
                    st.success(f"✅ Biaya dihapus untuk {selected_product}")
                    st.rerun()
                else:
                    st.warning("⚠️ Produk tidak ditemukan dalam data biaya")
        
        with btn_col3:
            if st.button("🔄 Bersihkan Formulir"):
                st.rerun()
    
    with col2:
        st.markdown("**📊 Statistik Biaya**")
        
        if st.session_state.cost_data:
            total_products = len(st.session_state.cost_data)
            avg_cost = sum(st.session_state.cost_data.values()) / total_products
            min_cost = min(st.session_state.cost_data.values())
            max_cost = max(st.session_state.cost_data.values())
            
            st.metric("📦 Total Produk", total_products)
            st.metric("💰 Rata-rata Biaya", f"Rp {avg_cost:,.0f}")
            st.metric("📉 Biaya Minimum", f"Rp {min_cost:,.0f}")
            st.metric("📈 Biaya Maksimum", f"Rp {max_cost:,.0f}")
        else:
            st.info("Tidak ada data biaya")
    
    # Tabel data biaya
    st.markdown("---")
    st.markdown("### 📋 Data Biaya Saat Ini")
    
    if st.session_state.cost_data:
        # Cari dan filter
        search_term = st.text_input("🔍 Cari produk", placeholder="Ketik untuk mencari...")
        
        cost_df = pd.DataFrame(
            list(st.session_state.cost_data.items()),
            columns=["Product Name", "Cost per Unit"]
        )
        
        if search_term:
            cost_df = cost_df[cost_df['Product Name'].str.contains(search_term, case=False, na=False)]
        
        cost_df = cost_df.sort_values("Product Name")
        
        # Format untuk tampilan
        cost_display = cost_df.copy()
        cost_display['Cost per Unit'] = cost_display['Cost per Unit'].apply(lambda x: f"Rp {x:,.0f}")
        
        st.dataframe(cost_display, use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ Tidak ada data biaya. Tambahkan beberapa biaya produk untuk memulai.")

def show_advanced_analytics():
    """Analisis lanjutan dengan grafik interaktif"""
    if st.session_state.summary_data is not None:
        st.markdown("### 📊 Analisis Lanjutan")
        
        # Pemilihan grafik
        chart_type = st.selectbox(
            "📈 Pilih Jenis Grafik",
            ["Pendapatan vs Profit (Scatter)", "Analisis Margin Profit", "Matriks Kinerja Produk", "Distribusi Penjualan"]
        )
        
        if chart_type == "Pendapatan vs Profit (Scatter)":
            fig = px.scatter(
                st.session_state.summary_data,
                x='Revenue',
                y='Profit',
                size='TotalQty',
                color='Profit Margin %',
                hover_data=['Product Name'],
                title="Analisis Pendapatan vs Profit",
                color_continuous_scale='RdYlGn',
                labels={'Revenue': 'Pendapatan (Rp)', 'Profit': 'Profit (Rp)'}
            )
            
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)
        
        elif chart_type == "Analisis Margin Profit":
            # Buat subplot
            fig = make_subplots(
                rows=2, cols=2,
                subplot_titles=('Distribusi Margin Profit', 'Produk Teratas berdasarkan Margin', 
                              'Pendapatan vs Margin', 'Kuantitas vs Margin'),
                specs=[[{"secondary_y": False}, {"secondary_y": False}],
                       [{"secondary_y": False}, {"secondary_y": False}]]
            )
            
            # Histogram
            fig.add_trace(
                go.Histogram(x=st.session_state.summary_data['Profit Margin %'], 
                           name="Distribusi Margin", showlegend=False),
                row=1, col=1
            )
            
            # Produk teratas berdasarkan margin
            top_margin = st.session_state.summary_data.nlargest(10, 'Profit Margin %')
            fig.add_trace(
                go.Bar(x=top_margin['Product Name'], y=top_margin['Profit Margin %'],
                      name="Margin Tertinggi", showlegend=False),
                row=1, col=2
            )
            
            # Scatter pendapatan vs margin
            fig.add_trace(
                go.Scatter(x=st.session_state.summary_data['Revenue'], 
                          y=st.session_state.summary_data['Profit Margin %'],
                          mode='markers', name="Pendapatan vs Margin", showlegend=False),
                row=2, col=1
            )
            
            # Scatter kuantitas vs margin
            fig.add_trace(
                go.Scatter(x=st.session_state.summary_data['TotalQty'], 
                          y=st.session_state.summary_data['Profit Margin %'],
                          mode='markers', name="Kuantitas vs Margin", showlegend=False),
                row=2, col=2
            )
            
            fig.update_layout(height=600, title_text="Analisis Komprehensif Margin Profit")
            st.plotly_chart(fig, use_container_width=True)
        
        elif chart_type == "Matriks Kinerja Produk":
            # Buat matriks kinerja dengan perbaikan untuk nilai negatif
            plot_data = st.session_state.summary_data.copy()
            
            # Pastikan nilai size selalu positif (gunakan absolut + offset kecil)
            plot_data['size_value'] = plot_data['Revenue'].abs() + 1
            
            # Buat informasi hover yang lebih informatif
            plot_data['hover_text'] = (
                plot_data['Product Name'] + '<br>' +
                'Revenue: Rp ' + plot_data['Revenue'].apply(lambda x: f"{x:,.0f}") + '<br>' +
                'Profit: Rp ' + plot_data['Profit'].apply(lambda x: f"{x:,.0f}") + '<br>' +
                'Margin: ' + plot_data['Profit Margin %'].apply(lambda x: f"{x:.1f}%")
            )
            
            fig = px.scatter(
                plot_data,
                x='TotalQty',
                y='Profit Margin %',
                size='size_value',  # Gunakan nilai yang sudah diperbaiki
                color='Profit',
                hover_name='Product Name',
                hover_data={
                    'Revenue': ':,.0f',
                    'Profit': ':,.0f',
                    'TotalQty': ':,.0f',
                    'Profit Margin %': ':.1f',
                    'size_value': False  # Sembunyikan kolom size_value dari hover
                },
                title="Matriks Kinerja Produk",
                labels={
                    'TotalQty': 'Total Kuantitas Terjual', 
                    'Profit Margin %': 'Margin Profit (%)',
                    'Profit': 'Profit (Rp)'
                },
                color_continuous_scale='RdYlGn',
                size_max=50  # Batasi ukuran maksimum marker
            )
            
            # Tambahkan garis kuadran
            median_qty = plot_data['TotalQty'].median()
            median_margin = plot_data['Profit Margin %'].median()
            
            fig.add_hline(y=median_margin, line_dash="dash", line_color="red", 
                         annotation_text=f"Margin Median: {median_margin:.1f}%")
            fig.add_vline(x=median_qty, line_dash="dash", line_color="red", 
                         annotation_text=f"Kuantitas Median: {median_qty:.0f}")
            
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)
            
            # Analisis kuadran
            st.markdown("**📊 Analisis Kuadran:**")
            quad_col1, quad_col2, quad_col3, quad_col4 = st.columns(4)
            
            # Volume tinggi, margin tinggi (Bintang)
            stars = plot_data[
                (plot_data['TotalQty'] >= median_qty) & 
                (plot_data['Profit Margin %'] >= median_margin)
            ]
            
            # Volume tinggi, margin rendah (Kuda Pekerja)
            workhorses = plot_data[
                (plot_data['TotalQty'] >= median_qty) & 
                (plot_data['Profit Margin %'] < median_margin)
            ]
            
            # Volume rendah, margin tinggi (Ceruk)
            niche = plot_data[
                (plot_data['TotalQty'] < median_qty) & 
                (plot_data['Profit Margin %'] >= median_margin)
            ]
            
            # Volume rendah, margin rendah (Masalah)
            problem = plot_data[
                (plot_data['TotalQty'] < median_qty) & 
                (plot_data['Profit Margin %'] < median_margin)
            ]
            
            with quad_col1:
                st.metric("⭐ Bintang", len(stars), "Vol Tinggi, Margin Tinggi")
                if len(stars) > 0:
                    st.caption(f"Avg Revenue: Rp {stars['Revenue'].mean():,.0f}")
            with quad_col2:
                st.metric("🐎 Kuda Pekerja", len(workhorses), "Vol Tinggi, Margin Rendah")
                if len(workhorses) > 0:
                    st.caption(f"Avg Revenue: Rp {workhorses['Revenue'].mean():,.0f}")
            with quad_col3:
                st.metric("💎 Ceruk", len(niche), "Vol Rendah, Margin Tinggi")
                if len(niche) > 0:
                    st.caption(f"Avg Revenue: Rp {niche['Revenue'].mean():,.0f}")
            with quad_col4:
                st.metric("⚠️ Masalah", len(problem), "Vol Rendah, Margin Rendah")
                if len(problem) > 0:
                    st.caption(f"Avg Revenue: Rp {problem['Revenue'].mean():,.0f}")
            
            # Tambahkan tabel produk untuk setiap kuadran
            st.markdown("---")
            st.markdown("**🔍 Detail Produk per Kuadran:**")
            
            quad_tab1, quad_tab2, quad_tab3, quad_tab4 = st.tabs(["⭐ Bintang", "🐎 Kuda Pekerja", "💎 Ceruk", "⚠️ Masalah"])
            
            with quad_tab1:
                if len(stars) > 0:
                    display_stars = stars[['Product Name', 'TotalQty', 'Revenue', 'Profit', 'Profit Margin %']].copy()
                    display_stars['Revenue'] = display_stars['Revenue'].apply(lambda x: f"Rp {x:,.0f}")
                    display_stars['Profit'] = display_stars['Profit'].apply(lambda x: f"Rp {x:,.0f}")
                    display_stars['Profit Margin %'] = display_stars['Profit Margin %'].apply(lambda x: f"{x:.1f}%")
                    st.dataframe(display_stars.sort_values('TotalQty', ascending=False), use_container_width=True, hide_index=True)
                else:
                    st.info("Tidak ada produk dalam kategori ini")
            
            with quad_tab2:
                if len(workhorses) > 0:
                    display_workhorses = workhorses[['Product Name', 'TotalQty', 'Revenue', 'Profit', 'Profit Margin %']].copy()
                    display_workhorses['Revenue'] = display_workhorses['Revenue'].apply(lambda x: f"Rp {x:,.0f}")
                    display_workhorses['Profit'] = display_workhorses['Profit'].apply(lambda x: f"Rp {x:,.0f}")
                    display_workhorses['Profit Margin %'] = display_workhorses['Profit Margin %'].apply(lambda x: f"{x:.1f}%")
                    st.dataframe(display_workhorses.sort_values('TotalQty', ascending=False), use_container_width=True, hide_index=True)
                else:
                    st.info("Tidak ada produk dalam kategori ini")
            
            with quad_tab3:
                if len(niche) > 0:
                    display_niche = niche[['Product Name', 'TotalQty', 'Revenue', 'Profit', 'Profit Margin %']].copy()
                    display_niche['Revenue'] = display_niche['Revenue'].apply(lambda x: f"Rp {x:,.0f}")
                    display_niche['Profit'] = display_niche['Profit'].apply(lambda x: f"Rp {x:,.0f}")
                    display_niche['Profit Margin %'] = display_niche['Profit Margin %'].apply(lambda x: f"{x:.1f}%")
                    st.dataframe(display_niche.sort_values('Profit Margin %', ascending=False), use_container_width=True, hide_index=True)
                else:
                    st.info("Tidak ada produk dalam kategori ini")
            
            with quad_tab4:
                if len(problem) > 0:
                    display_problem = problem[['Product Name', 'TotalQty', 'Revenue', 'Profit', 'Profit Margin %']].copy()
                    display_problem['Revenue'] = display_problem['Revenue'].apply(lambda x: f"Rp {x:,.0f}")
                    display_problem['Profit'] = display_problem['Profit'].apply(lambda x: f"Rp {x:,.0f}")
                    display_problem['Profit Margin %'] = display_problem['Profit Margin %'].apply(lambda x: f"{x:.1f}%")
                    st.dataframe(display_problem.sort_values('Profit Margin %', ascending=False), use_container_width=True, hide_index=True)
                else:
                    st.info("Tidak ada produk dalam kategori ini")
        
        elif chart_type == "Distribusi Penjualan":
            # Buat analisis distribusi
            fig = make_subplots(
                rows=2, cols=2,
                subplot_titles=('Distribusi Pendapatan', 'Distribusi Profit', 
                              'Distribusi Kuantitas', 'Pendapatan Kumulatif'),
                specs=[[{"secondary_y": False}, {"secondary_y": False}],
                       [{"secondary_y": False}, {"secondary_y": False}]]
            )
            
            # Distribusi pendapatan
            fig.add_trace(
                go.Box(y=st.session_state.summary_data['Revenue'], 
                      name="Pendapatan", showlegend=False),
                row=1, col=1
            )
            
            # Distribusi profit
            fig.add_trace(
                go.Box(y=st.session_state.summary_data['Profit'], 
                      name="Profit", showlegend=False),
                row=1, col=2
            )
            
            # Distribusi kuantitas
            fig.add_trace(
                go.Box(y=st.session_state.summary_data['TotalQty'], 
                      name="Kuantitas", showlegend=False),
                row=2, col=1
            )
            
            # Pendapatan kumulatif (Pareto)
            sorted_data = st.session_state.summary_data.sort_values('Revenue', ascending=False)
            sorted_data['Cumulative Revenue'] = sorted_data['Revenue'].cumsum()
            sorted_data['Cumulative %'] = (sorted_data['Cumulative Revenue'] / sorted_data['Revenue'].sum()) * 100
            
            fig.add_trace(
                go.Scatter(x=list(range(1, len(sorted_data) + 1)), 
                          y=sorted_data['Cumulative %'],
                          mode='lines+markers', name="Persentase Pendapatan Kumulatif", showlegend=False),
                row=2, col=2
            )
            
            fig.update_layout(height=600, title_text="Analisis Distribusi Penjualan")
            st.plotly_chart(fig, use_container_width=True)
        
        # Wawasan tambahan

                # --- 🔗 Tombol Ringkas + Lanjut ke ChatGPT ---
        st.markdown("---")
        if st.button("💬 Ringkas & Lanjut ke ChatGPT", type="primary"):
            if st.session_state.summary_data is not None:
                # --- ringkas data ---
                df = st.session_state.summary_data
                total_sku   = len(df)
                untung      = len(df[df['Profit'] > 0])
                hi_margin   = len(df[df['Profit Margin %'] > 20])
                top20_pct   = (df.nlargest(int(total_sku*0.2), 'Revenue')['Revenue'].sum() /
                               df['Revenue'].sum() * 100)
                low_margin  = len(df[df['Profit Margin %'] < 10])
                hi_vol_low  = len(df[(df['TotalQty'] >= df['TotalQty'].median()) &
                                     (df['Profit Margin %'] < 15)])

                prompt = f"""
                Kamu adalah Chief Data Scientist e-commerce. Buat laporan strategis 360° dari data berikut:
                                
                📊 Ringkasan Data:
                - Total SKU        : {total_sku}
                - Produk Untung    : {untung}
                - Margin >20 %     : {hi_margin}
                - 20 % Top SKU     : {top20_pct:.1f}% pendapatan
                - SKU margin <10 % : {low_margin}
                - SKU volume-tinggi-margin-rendah : {hi_vol_low}

                💬 Prompt ChatGPT:
                Buat:
                1. Executive summary 3 kalimat.
                2. 3 SKU prioritas optimize.
                3. 2 pricing strategy SKU margin rendah.
                4. Forecast 30 hari jika strategi 50 % rollout.
                
                """

                # encode URL-safe
                from urllib.parse import quote
                chatgpt_url = f"https://chat.openai.com/?q={quote(prompt)}"
                st.markdown(
                    f'<a href="{chatgpt_url}" target="_blank" rel="noopener noreferrer">'
                    '📲 Buka ChatGPT (tab baru)</a>',
                    unsafe_allow_html=True
                )
                st.text_area("📋 Copy prompt:", value=prompt, height=250)
            else:
                st.warning("⚠️ Proses data terlebih dahulu.")
        
        st.markdown("---")
        st.markdown("### 🔍 Wawasan Utama")
        
        insight_col1, insight_col2 = st.columns(2)
        
        with insight_col1:
            st.markdown("**📈 Wawasan Kinerja**")
            
            # Hitung wawasan
            total_products = len(st.session_state.summary_data)
            profitable_products = len(st.session_state.summary_data[st.session_state.summary_data['Profit'] > 0])
            high_margin_products = len(st.session_state.summary_data[st.session_state.summary_data['Profit Margin %'] > 20])
            
            st.write(f"• **{profitable_products}/{total_products}** produk menghasilkan profit")
            st.write(f"• **{high_margin_products}** produk memiliki margin >20%")
            st.write(f"• **Produk 20% teratas** menghasilkan **{(st.session_state.summary_data.nlargest(int(total_products*0.2), 'Revenue')['Revenue'].sum() / st.session_state.summary_data['Revenue'].sum() * 100):.1f}%** pendapatan")
        
        with insight_col2:
            st.markdown("**💡 Rekomendasi**")
            
            # Rekomendasi utama
            low_margin = st.session_state.summary_data[st.session_state.summary_data['Profit Margin %'] < 10]
            if not low_margin.empty:
                st.write(f"• Tinjau penetapan harga untuk **{len(low_margin)}** produk margin rendah")
            
            high_volume_low_margin = st.session_state.summary_data[
                (st.session_state.summary_data['TotalQty'] >= st.session_state.summary_data['TotalQty'].median()) & 
                (st.session_state.summary_data['Profit Margin %'] < 15)
            ]
            if not high_volume_low_margin.empty:
                st.write(f"• Optimalkan biaya untuk **{len(high_volume_low_margin)}** produk volume tinggi")
            
            st.write("• Fokuskan pemasaran pada produk margin tinggi")
            st.write("• Pertimbangkan menghentikan item yang secara konsisten berkinerja rendah")
    
    else:
        st.info("ℹ️ Silakan proses data Anda terlebih dahulu untuk melihat analisis lanjutan")

def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>📊 Analisis Pendapatan & Pesanan</h1>
        <p>Intelijen bisnis komprehensif untuk operasi e-commerce Anda</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Inisialisasi aplikasi
    global app
    app = IncomeApp()
    
    # Inisialisasi state sesi
    if 'cost_data' not in st.session_state:
        st.session_state.cost_data = app.load_cost_data()
    if 'pesanan_data' not in st.session_state:
        st.session_state.pesanan_data = None
    if 'income_data' not in st.session_state:
        st.session_state.income_data = None
    if 'merged_data' not in st.session_state:
        st.session_state.merged_data = None
    if 'summary_data' not in st.session_state:
        st.session_state.summary_data = None
    
    # Sidebar
    with st.sidebar:
        st.markdown("### 🎛️ Panel Kontrol")
        
        # Status data
        st.markdown("**📊 Status Data:**")
        pesanan_status = "✅ Dimuat" if st.session_state.pesanan_data is not None else "❌ Tidak dimuat"
        income_status = "✅ Dimuat" if st.session_state.income_data is not None else "❌ Tidak dimuat"
        processed_status = "✅ Diproses" if st.session_state.summary_data is not None else "❌ Tidak diproses"
        
        st.write(f"Pesanan: {pesanan_status}")
        st.write(f"Pendapatan: {income_status}")
        st.write(f"Analisis: {processed_status}")
        
        st.markdown("---")
        
        # Aksi cepat
        st.markdown("**⚡ Aksi Cepat:**")
        
        if st.button("🔄 Proses Data", type="primary", use_container_width=True):
            if st.session_state.pesanan_data is not None and st.session_state.income_data is not None:
                with st.spinner("Memproses data..."):
                    merged, summary = app.process_data(
                        st.session_state.pesanan_data, 
                        st.session_state.income_data, 
                        st.session_state.cost_data
                    )
                    
                    if merged is not None:
                        st.session_state.merged_data = merged
                        st.session_state.summary_data = summary
                        st.success("✅ Data diproses!")
                        st.rerun()
                    else:
                        st.error("❌ Tidak ditemukan data yang cocok")
            else:
                st.warning("⚠️ Unggah kedua file terlebih dahulu")
        
        if st.session_state.summary_data is not None:
            if st.button("📥 Ekspor Laporan", use_container_width=True):
                try:
                    excel_data = app.create_excel_report(
                        st.session_state.merged_data,
                        st.session_state.summary_data,
                        st.session_state.cost_data
                    )
                    
                    st.download_button(
                        label="💾 Unduh Excel",
                        data=excel_data,
                        file_name=f"income_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Kesalahan: {str(e)}")
        
        st.markdown("---")
        
        # Statistik cepat biaya
        if st.session_state.cost_data:
            st.markdown("**💰 Data Biaya:**")
            st.write(f"Produk: {len(st.session_state.cost_data)}")
            avg_cost = sum(st.session_state.cost_data.values()) / len(st.session_state.cost_data)
            st.write(f"Biaya Rata-rata: Rp {avg_cost:,.0f}")
    
    # Tab konten utama
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Dasbor", 
        "💸 Manajemen Biaya", 
        "📈 Analisis", 
        "📋 Detail Data"
    ])
    
    with tab1:
        show_data_upload_section()
        
        st.markdown("---")
        
        show_metrics_dashboard()
    
    with tab2:
        show_cost_management()
    
    with tab3:
        show_advanced_analytics()
    
    with tab4:
        st.markdown("### 📋 Detail Data")
        
        if st.session_state.summary_data is not None:
            # Tabel ringkasan dengan pencarian dan filter
            st.markdown("**📊 Tabel Ringkasan Lengkap**")
            
            # Filter
            filter_col1, filter_col2, filter_col3 = st.columns(3)
            
            with filter_col1:
                min_revenue = st.number_input("Pendapatan Minimum", min_value=0, value=0)
            with filter_col2:
                min_profit = st.number_input("Profit Minimum", value=0)
            with filter_col3:
                min_margin = st.number_input("Margin Minimum %", min_value=0.0, max_value=100.0, value=0.0)
            
            # Terapkan filter
            filtered_data = st.session_state.summary_data[
                (st.session_state.summary_data['Revenue'] >= min_revenue) &
                (st.session_state.summary_data['Profit'] >= min_profit) &
                (st.session_state.summary_data['Profit Margin %'] >= min_margin)
            ]
            
            # Format untuk tampilan
            display_data = filtered_data.copy()
            display_data['Revenue'] = display_data['Revenue'].apply(lambda x: f"Rp {x:,.0f}")
            display_data['Total Cost'] = display_data['Total Cost'].apply(lambda x: f"Rp {x:,.0f}")
            display_data['Profit'] = display_data['Profit'].apply(lambda x: f"Rp {x:,.0f}")
            display_data['Share 60%'] = display_data['Share 60%'].apply(lambda x: f"Rp {x:,.0f}")
            display_data['Share 40%'] = display_data['Share 40%'].apply(lambda x: f"Rp {x:,.0f}")
            display_data['Profit Margin %'] = display_data['Profit Margin %'].apply(lambda x: f"{x:.1f}%")
            
            st.dataframe(display_data, use_container_width=True, hide_index=True)
            
            # Ringkasan statistik
            st.markdown("**📊 Ringkasan Data Tersaring**")
            st.info("ℹ️ **Catatan:** Metrik di bawah menunjukkan data produk tersaring saja. Untuk total bisnis akurat, lihat Dasbor Kinerja yang menangani perhitungan tingkat pesanan dengan benar.")
            
            summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
            
            with summary_col1:
                st.metric("Produk Tersaring", len(filtered_data))
            with summary_col2:
                st.metric("Jumlah Pendapatan Produk", f"Rp {filtered_data['Revenue'].sum():,.0f}")
            with summary_col3:
                st.metric("Jumlah Profit Produk", f"Rp {filtered_data['Profit'].sum():,.0f}")
            with summary_col4:
                avg_margin = filtered_data['Profit Margin %'].mean()
                st.metric("Margin Rata-rata", f"{avg_margin:.1f}%")
            
            # Tambahkan perbandingan dengan total bisnis aktual
            if st.session_state.merged_data is not None:
                st.markdown("---")
                st.markdown("**🔍 Perbandingan Total Bisnis**")
                
                # Hitung total bisnis aktual (sama seperti Dasbor Kinerja)
                unique_orders = st.session_state.merged_data.drop_duplicates(subset=['Order ID'])
                actual_total_revenue = unique_orders['Total settlement amount'].sum()
                actual_total_cost = st.session_state.summary_data['Total Cost'].sum()
                actual_total_profit = actual_total_revenue - actual_total_cost
                
                comp_col1, comp_col2, comp_col3 = st.columns(3)
                
                with comp_col1:
                    st.metric(
                        "Total Pendapatan Aktual", 
                        f"Rp {actual_total_revenue:,.0f}",
                        help="Dihitung dari pesanan unik (metode Dasbor Kinerja)"
                    )
                with comp_col2:
                    st.metric(
                        "Total Profit Aktual", 
                        f"Rp {actual_total_profit:,.0f}",
                        help="Pendapatan dikurangi total biaya (metode Dasbor Kinerja)"
                    )
                with comp_col3:
                    filter_coverage = (filtered_data['Revenue'].sum() / actual_total_revenue * 100) if actual_total_revenue > 0 else 0
                    st.metric(
                        "Cakupan Filter", 
                        f"{filter_coverage:.1f}%",
                        help="Persentase total pendapatan yang dicakup oleh produk tersaring"
                    )
        
        else:
            st.info("ℹ️ Tidak ada data untuk ditampilkan. Silakan unggah dan proses data Anda terlebih dahulu.")

if __name__ == "__main__":
    main()