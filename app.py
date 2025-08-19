"""
EMIS Benchmark Dashboard
A Streamlit application to search for multiple companies by their external IDs (NITs),
explore their industry benchmarks interactively, visualize the results, and download them as an Excel file.
"""

import streamlit as st
import pandas as pd
import logging
import sys
import time
import re
import io
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="EMIS Benchmark Dashboard", layout="wide")

from emis_api_client import Configuration, ApiClient
from emis_api_client.apis.companies_api import CompaniesApi
from emis_api_client.rest import ApiException

# --- Configuración del Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- Claves para el Estado de Sesión ---
class StateKey:
    LOGGED_IN = 'logged_in'
    EMIS_SERVICE = 'emis_service'
    SEARCH_RESULTS = 'search_results'
    LOCAL_BENCHMARKS = 'local_benchmarks'
    INDUSTRY_NAMES = 'industry_names'
    CURRENT_PAGE = 'current_page'

# --- Clases de Datos ---
@dataclass
class CompanyInfo:
    id: int
    name: str
    external_id: str

@dataclass
class SearchParams:
    external_ids: List[str]

# --- Funciones de Carga de Datos ---
@st.cache_data
def load_local_benchmarks(file_path: str) -> Dict[str, Any]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {str(item['company_info']['nit']): item for item in data}
    except FileNotFoundError: return {}

@st.cache_data
def load_industry_names(file_path: str) -> Dict[str, str]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {item['code']: item['name'] for item in data}
    except FileNotFoundError: return {}

class SessionManager:
    @staticmethod
    def initialize() -> None:
        defaults = {
            StateKey.LOGGED_IN: False,
            StateKey.EMIS_SERVICE: None,
            StateKey.SEARCH_RESULTS: [],
            StateKey.LOCAL_BENCHMARKS: load_local_benchmarks("./data/benchmarks.json"),
            StateKey.INDUSTRY_NAMES: load_industry_names("./data/industries.json"),
            StateKey.CURRENT_PAGE: 1,
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    @staticmethod
    def logout() -> None:
        keys_to_delete = [k for k in st.session_state.keys()]
        for key in keys_to_delete:
            del st.session_state[key]
        SessionManager.initialize()

    @staticmethod
    def reset_search() -> None:
        st.session_state[StateKey.SEARCH_RESULTS] = []
        st.session_state[StateKey.CURRENT_PAGE] = 1

# ... (Clases AuthenticationService y EMISService sin cambios) ...
class AuthenticationService:
    @staticmethod
    def login(token: str) -> bool:
        if not token: st.error("Por favor, introduce tu EMIS API Token."); return False
        try:
            with st.spinner("Autenticando y configurando cliente API..."):
                config = Configuration(); config.host = "https://api.emis.com/v2/company"
                api_client = ApiClient(configuration=config)
                st.session_state[StateKey.EMIS_SERVICE] = EMISService(api_client, token)
                st.session_state[StateKey.LOGGED_IN] = True
            st.success("¡Autenticación exitosa!")
            return True
        except Exception as e:
            st.error(f"La configuración del cliente falló: {e}"); SessionManager.logout(); return False

class EMISService:
    def __init__(self, api_client: ApiClient, token: str):
        self.api_client = api_client
        self.token = token
        self.companies_api = CompaniesApi(api_client=self.api_client)
    def _sleep(self): time.sleep(0.5)
    def find_company_by_external_id(self, external_id: str) -> Optional[CompanyInfo]:
        try:
            response = self.companies_api.companies_match_get(token=self.token, external_id=[external_id], limit=1)
            self._sleep()
            if response and response.data and response.data.items:
                match_item = response.data.items[0]
                return CompanyInfo(id=match_item.company_id, name=match_item.company_name, external_id=external_id)
            st.warning(f"No se encontró ninguna empresa con el NIT '{external_id}'."); return None
        except ApiException as e: st.error(f"Error de API al buscar la empresa con NIT {external_id}. Código: {e.status}."); return None
    def get_company_benchmark(self, company_id: int) -> Optional[Dict[str, Any]]:
        try:
            response = self.companies_api.companies_id_benchmark_get(id=company_id, token=self.token)
            self._sleep()
            if response and response.data: return response.data.to_dict()
            st.info(f"No se encontraron datos de benchmark para la empresa con ID: {company_id}."); return None
        except ApiException as e: st.error(f"Error de API al obtener el benchmark para la empresa con ID {company_id}. Código: {e.status}."); return None

class UIComponents:
    @staticmethod
    def render_login_page():
        st.image("./static/logo2.png", width=200); st.title("EMIS Benchmark Dashboard")
        token = st.text_input("EMIS API Token", type="password")
        if st.button("Login"):
            if AuthenticationService.login(token): st.rerun()

    @staticmethod
    def render_sidebar() -> Optional[SearchParams]:
        st.sidebar.image("./static/logo2.png", width=150); st.sidebar.header("Opciones de Búsqueda")
        nits_input = st.sidebar.text_input("NIT(s) de la Empresa", help="Introduce uno o más NITs separados por comas o espacios.")
        if st.sidebar.button("Buscar Empresas"):
            if nits_input:
                nits_list = [nit.strip() for nit in re.split(r'[, ]+', nits_input) if nit.strip()]
                if nits_list: return SearchParams(external_ids=nits_list)
            st.sidebar.warning("Por favor, introduce al menos un NIT válido.")
        return None

    # --- FUNCIÓN DE PAGINACIÓN MODIFICADA ---
    @staticmethod
    def render_pagination_controls(total_results: int, page_size: int, key_prefix: str):
        total_pages = (total_results + page_size - 1) // page_size
        if total_pages <= 1:
            return

        current_page = st.session_state[StateKey.CURRENT_PAGE]
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("⬅️ Anterior", disabled=(current_page == 1), key=f"{key_prefix}_prev"):
                st.session_state[StateKey.CURRENT_PAGE] -= 1
                st.rerun()
        with col2:
            st.markdown(f"<p style='text-align: center; margin-top: 0.5rem;'>Página <b>{current_page}</b> de <b>{total_pages}</b></p>", unsafe_allow_html=True)
        with col3:
            if st.button("Siguiente ➡️", disabled=(current_page == total_pages), key=f"{key_prefix}_next"):
                st.session_state[StateKey.CURRENT_PAGE] += 1
                st.rerun()

    # ... (Resto de los métodos de UIComponents sin cambios) ...
    @staticmethod
    def render_company_info(info: CompanyInfo):
        if info:
            with st.container(border=True):
                st.subheader(f"Empresa: {info.name}")
                st.markdown(f"**ID de EMIS:** `{info.id}` | **NIT Buscado:** `{info.external_id}`")
    @staticmethod
    def _create_risk_benchmark_dashboard(company_data):
        company_count = company_data.get("companyCount", 5000)
        colors_active = {"A": "#2E8B57", "B": "#32CD32", "C": "#FFD700", "D": "#FF4500", "E": "#FF0000"}
        color_inactive = "#D3D3D3"
        risk_categories = ["A", "B", "C", "D", "E"]
        risk_descriptions = {"A": "Riesgo Muy Bajo", "B": "Riesgo Bajo", "C": "Riesgo Medio", "D": "Riesgo Alto", "E": "Riesgo Muy Alto"}
        fig = go.Figure()
        for risk in risk_categories:
            is_active = risk == company_data["risk"]
            bar_color = colors_active.get(risk, color_inactive) if is_active else color_inactive
            hover_text = (f"<b>Categoría: {risk}</b> ({risk_descriptions.get(risk, '')})<br>" +
                        (f"<b>Su Empresa:</b><br>• Score: {company_data['benchmarkScore']:.1f}<br>• Ranking: {company_data['averageRanking']:.0f} de {int(company_count)}"
                        if is_active else "<i>Su empresa no está aquí</i>"))
            fig.add_trace(go.Bar(name=risk, x=[risk], y=[100], marker_color=bar_color, marker_line_color="white", marker_line_width=2,
                                hovertemplate=hover_text + "<extra></extra>", showlegend=False))
        fig.update_layout(title={"text": f"<b>Clasificación de Riesgo: <span style='color:{colors_active.get(company_data['risk'])}'>{company_data['risk']}</span></b>", "x": 0.5, "xanchor": "center"},
                          xaxis_title="Categorías de Riesgo", yaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
                          height=350, template="plotly_white", hovermode="x")
        return fig
    @staticmethod
    def render_benchmark_data(data: Optional[Dict[str, Any]]):
        if not data: st.info("No hay datos de benchmark disponibles."); return
        industry_map = st.session_state.get(StateKey.INDUSTRY_NAMES, {})
        financial_scores = data.get('financial_scores') or data.get('financialScores')
        if not financial_scores: st.info("No hay datos de benchmark disponibles."); return
        risk_profile = data.get('risk_profile', data.get('riskProfile', 'N/A'))
        score_scale = data.get('score_scale', data.get('scoreScale', 'N/A'))
        st.markdown(f"**Perfil de Riesgo General:** `{risk_profile}` | **Escala de Puntuación:** `{score_scale}`")
        tab_titles = [f"{industry_map.get(str(s.get('industry_code') or s.get('industryCode')), 'Industria Desc.')} ({s.get('industry_code') or s.get('industryCode')})" for s in financial_scores]
        tabs = st.tabs(tab_titles)
        for i, score_data in enumerate(financial_scores):
            with tabs[i]:
                period = score_data.get('period') or data.get('period', {})
                fiscal_year = period.get('fiscal_year', period.get('fiscalYear', 'N/A'))
                company_count = float(period.get('company_count', period.get('companyCount', 5000)) or 5000)
                st.write(f"**Año Fiscal:** `{fiscal_year}` | **Empresas en Comparación:** `{int(company_count)}`")
                benchmark_info = score_data.get('benchmark', {})
                financial_risk = benchmark_info.get('risk', 'N/A')
                benchmark_score = float(benchmark_info.get('benchmark_score', benchmark_info.get('benchmarkScore', 0)) or 0)
                average_ranking = float(benchmark_info.get('average_ranking', benchmark_info.get('averageRanking', 0)) or 0)
                cols = st.columns(3)
                cols[0].metric("Riesgo Financiero", str(financial_risk))
                cols[1].metric("Puntuación Benchmark", f"{benchmark_score:.2f}")
                cols[2].metric("Ranking Promedio", f"{average_ranking:.2f}")
                company_id = data.get('companyId')
                risk = benchmark_info.get('risk')
                if risk and company_id is not None:
                    fig = UIComponents._create_risk_benchmark_dashboard({"companyId": company_id, "benchmarkScore": benchmark_score, "averageRanking": average_ranking, "risk": risk, "companyCount": company_count})
                    st.plotly_chart(fig, use_container_width=True, key=f"risk_chart_{company_id}_{i}")
                else: st.warning("Datos insuficientes para generar el gráfico de riesgo.")
    @staticmethod
    def render_summary_charts(df: pd.DataFrame):
        st.header("Análisis Gráfico General")
        if df.empty: return
        score_col, rank_col, risk_col = 'Benchmark_Benchmarkscore', 'Benchmark_Averageranking', 'Financialrisk'
        if score_col in df.columns:
            st.subheader("Comparación de Puntuación de Benchmark"); df[score_col] = pd.to_numeric(df[score_col], errors='coerce').fillna(0)
            fig_bar = px.bar(df, x='Nombre Empresa', y=score_col, color='Nombre Empresa', title='Puntuación General de Benchmark', labels={'Nombre Empresa': 'Empresa', score_col: 'Puntuación General'})
            st.plotly_chart(fig_bar, use_container_width=True)
        col1, col2 = st.columns(2)
        with col1:
            if risk_col in df.columns:
                st.subheader("Distribución de Riesgo"); risk_counts = df[risk_col].value_counts().reset_index()
                fig_pie = px.pie(risk_counts, names=risk_col, values='count', title='Perfiles de Riesgo Financiero')
                st.plotly_chart(fig_pie, use_container_width=True)
        with col2:
            if score_col in df.columns and rank_col in df.columns:
                st.subheader("Puntuación vs. Ranking"); df[rank_col] = pd.to_numeric(df[rank_col], errors='coerce').fillna(0)
                fig_scatter = px.scatter(df, x=score_col, y=rank_col, color='Nombre Empresa', title='Relación Puntuación vs. Ranking', labels={score_col: 'Puntuación General', rank_col: 'Ranking Promedio'})
                st.plotly_chart(fig_scatter, use_container_width=True)

class EMISDashboardApp:
    PAGE_SIZE = 10

    def __init__(self):
        SessionManager.initialize()

    def _flatten_dict(self, d: dict, parent_key: str = '', sep: str = '_') -> dict:
        items = []
        for k, v in d.items():
            new_key = parent_key + sep + k.title().replace('_', '') if parent_key else k.title().replace('_', '')
            if isinstance(v, dict): items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else: items.append((new_key, v))
        return dict(items)

    def _prepare_data_for_excel(self, search_results: List[Dict]) -> pd.DataFrame:
        flat_data, industry_map = [], st.session_state.get(StateKey.INDUSTRY_NAMES, {})
        for result in search_results:
            company_info, benchmark_data = result.get("company_info"), result.get("benchmark_data")
            if not benchmark_data: continue
            financial_scores = benchmark_data.get('financial_scores') or benchmark_data.get('financialScores')
            if not all([company_info, financial_scores]): continue
            company_base = {"NIT Buscado": company_info.external_id, "Nombre Empresa": company_info.name, "ID EMIS": company_info.id}
            for score in financial_scores:
                row = company_base.copy()
                industry_code = score.get('industry_code') or score.get('industryCode')
                row['Nombre Industria'] = industry_map.get(str(industry_code) if industry_code else '', 'N/A')
                for section_name, section_data in score.items():
                    if isinstance(section_data, dict): row.update(self._flatten_dict(section_data, parent_key=section_name.title()))
                    else: row[section_name.title().replace('_', '')] = section_data
                flat_data.append(row)
        return pd.DataFrame(flat_data)

    def run(self):
        if not st.session_state[StateKey.LOGGED_IN]: UIComponents.render_login_page()
        else: self._render_main_app()

    def _render_main_app(self):
        st.title("Visor de Benchmarks Financieros de EMIS")
        with st.sidebar:
            if st.button("Logout"): SessionManager.logout(); st.rerun()
        if search_params := UIComponents.render_sidebar(): self._handle_search(search_params)
        
        results = st.session_state.get(StateKey.SEARCH_RESULTS, [])
        if results:
            st.header(f"Resultados de la Búsqueda ({len(results)} empresa(s))")
            
            df_for_excel = self._prepare_data_for_excel(results)
            if not df_for_excel.empty:
                output = io.BytesIO()
                df_for_excel.to_excel(output, index=False, sheet_name='Benchmarks')
                st.download_button("📥 Descargar Reporte Completo en Excel", output.getvalue(), f"emis_benchmarks_{datetime.now():%Y%m%d_%H%M%S}.xlsx", 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', type="primary")

            # --- RENDERIZADO DE PAGINACIÓN MODIFICADO ---
            UIComponents.render_pagination_controls(len(results), self.PAGE_SIZE, key_prefix="top")
            st.divider()
            
            current_page = st.session_state[StateKey.CURRENT_PAGE]
            start_idx, end_idx = (current_page - 1) * self.PAGE_SIZE, current_page * self.PAGE_SIZE
            paginated_results = results[start_idx:end_idx]

            for result in paginated_results:
                UIComponents.render_company_info(result.get("company_info"))
                UIComponents.render_benchmark_data(result.get("benchmark_data"))
                st.divider()

            UIComponents.render_pagination_controls(len(results), self.PAGE_SIZE, key_prefix="bottom")

            if not df_for_excel.empty:
                st.divider()
                UIComponents.render_summary_charts(df_for_excel)

    def _handle_search(self, params: SearchParams):
        SessionManager.reset_search()
        service: EMISService = st.session_state[StateKey.EMIS_SERVICE]
        local_benchmarks: Dict[str, Any] = st.session_state[StateKey.LOCAL_BENCHMARKS]
        progress_bar = st.progress(0, "Iniciando búsqueda...")
        all_results, num_ids = [], len(params.external_ids)
        for i, nit in enumerate(params.external_ids):
            progress_bar.progress((i + 1) / num_ids, f"Procesando NIT: `{nit}` ({i+1}/{num_ids})")
            if nit in local_benchmarks:
                local_data = local_benchmarks[nit]
                company_info = CompanyInfo(id=local_data["company_info"]["company_id"], name=local_data["company_info"]["company_name"], external_id=str(local_data["company_info"]["nit"]))
                all_results.append({"company_info": company_info, "benchmark_data": local_data.get("benchmark_data")})
                time.sleep(0.05)
            else:
                if company_info := service.find_company_by_external_id(nit):
                    benchmark_data = service.get_company_benchmark(company_info.id)
                    all_results.append({"company_info": company_info, "benchmark_data": benchmark_data})
        progress_bar.empty()
        st.session_state[StateKey.SEARCH_RESULTS] = all_results
        st.rerun()

if __name__ == "__main__":
    app = EMISDashboardApp()
    app.run()