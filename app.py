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
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import plotly.express as px

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

# --- Clases de Datos ---
@dataclass
class CompanyInfo:
    id: int
    name: str
    external_id: str

@dataclass
class SearchParams:
    external_ids: List[str]

class SessionManager:
    """Gestiona el estado de la sesión de Streamlit de forma centralizada."""
    
    @staticmethod
    def initialize() -> None:
        defaults = {
            StateKey.LOGGED_IN: False,
            StateKey.EMIS_SERVICE: None,
            StateKey.SEARCH_RESULTS: []
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

class AuthenticationService:
    """Gestiona la autenticación del usuario."""

    @staticmethod
    def login(token: str) -> bool:
        if not token:
            st.error("Por favor, introduce tu EMIS API Token.")
            return False
        try:
            with st.spinner("Autenticando y configurando cliente API..."):
                config = Configuration()
                config.host = "https://api.emis.com/v2/company"
                api_client = ApiClient(configuration=config)
                st.session_state[StateKey.EMIS_SERVICE] = EMISService(api_client, token)
                st.session_state[StateKey.LOGGED_IN] = True
            st.success("¡Autenticación exitosa!")
            return True
        except Exception as e:
            st.error(f"La configuración del cliente falló: {e}")
            SessionManager.logout()
            return False

class EMISService:
    """Encapsula la lógica de negocio para interactuar con la API de EMIS."""

    def __init__(self, api_client: ApiClient, token: str):
        self.api_client = api_client
        self.token = token
        self.companies_api = CompaniesApi(api_client=self.api_client)

    def _sleep(self):
        time.sleep(0.5)

    def find_company_by_external_id(self, external_id: str) -> Optional[CompanyInfo]:
        try:
            response = self.companies_api.companies_match_get(token=self.token, external_id=[external_id], limit=1)
            self._sleep()
            if response and response.data and response.data.items:
                match_item = response.data.items[0]
                return CompanyInfo(id=match_item.company_id, name=match_item.company_name, external_id=external_id)
            st.warning(f"No se encontró ninguna empresa con el NIT '{external_id}'.")
            return None
        except ApiException as e:
            st.error(f"Error de API al buscar la empresa con NIT {external_id}. Código: {e.status}.")
            return None

    def get_company_benchmark(self, company_id: int) -> Optional[Dict[str, Any]]:
        try:
            response = self.companies_api.companies_id_benchmark_get(id=company_id, token=self.token)
            self._sleep()
            if response and response.data:
                return response.data.to_dict()
            st.info(f"No se encontraron datos de benchmark para la empresa con ID: {company_id}.")
            return None
        except ApiException as e:
            st.error(f"Error de API al obtener el benchmark para la empresa con ID {company_id}. Código: {e.status}.")
            return None

class UIComponents:
    """Renderiza todos los componentes de la interfaz de usuario."""

    @staticmethod
    def render_login_page():
        st.set_page_config(page_title="Login - EMIS Benchmarks", layout="centered")
        st.image("./static/logo2.png", width=200)
        st.title("EMIS Benchmark Dashboard")
        token = st.text_input("EMIS API Token", type="password")
        if st.button("Login"):
            if AuthenticationService.login(token):
                st.rerun()

    @staticmethod
    def render_sidebar() -> Optional[SearchParams]:
        st.sidebar.image("./static/logo2.png", width=150)
        st.sidebar.header("Opciones de Búsqueda")
        nits_input = st.sidebar.text_input("NIT(s) de la Empresa", help="Introduce uno o más NITs separados por comas o espacios.")
        if st.sidebar.button("Buscar Empresas"):
            if nits_input:
                nits_list = [nit.strip() for nit in re.split(r'[, ]+', nits_input) if nit.strip()]
                if nits_list:
                    return SearchParams(external_ids=nits_list)
            st.sidebar.warning("Por favor, introduce al menos un NIT válido.")
        return None

    @staticmethod
    def render_company_info(info: CompanyInfo):
        if info:
            with st.container(border=True):
                st.subheader(f"Empresa: {info.name}")
                st.markdown(f"**ID de EMIS:** `{info.id}` | **NIT Buscado:** `{info.external_id}`")

    @staticmethod
    def _display_score_card(title: str, data: Dict):
        with st.expander(f"Detalles de {title}", expanded=False):
            df_data = []
            for key, value in data.items():
                if isinstance(value, (dict, list)): continue
                friendly_name = key.replace('_', ' ').replace('score', ' Score').replace('ranking', ' Ranking').title()
                df_data.append({"Métrica": friendly_name, "Valor": str(value)})
            if df_data:
                st.dataframe(pd.DataFrame(df_data), use_container_width=True, hide_index=True)

    @staticmethod
    def render_benchmark_data(data: Optional[Dict[str, Any]]):
        if not data or not data.get('financial_scores'):
            st.info("No hay datos de benchmark disponibles para esta empresa.")
            return
        st.markdown(f"**Perfil de Riesgo General:** `{data.get('risk_profile', 'N/A')}` | **Escala de Puntuación:** `{data.get('score_scale', 'N/A')}`")
        financial_scores = data['financial_scores']
        tab_titles = [f"Benchmark Industria {score.get('industry_code', 'N/A')}" for score in financial_scores]
        tabs = st.tabs(tab_titles)
        for i, score_data in enumerate(financial_scores):
            with tabs[i]:
                period = score_data.get('period', {})
                st.write(f"**Año Fiscal:** `{period.get('fiscal_year', 'N/A')}` | **Empresas en Comparación:** `{period.get('company_count', 'N/A')}`")
                cols = st.columns(3)
                benchmark_info = score_data.get('benchmark', {})
                cols[0].metric("Riesgo Financiero", str(score_data.get('financial_risk', 'N/A')))
                cols[1].metric("Puntuación Benchmark", f"{benchmark_info.get('benchmark_score', 0):.2f}")
                cols[2].metric("Ranking Promedio", f"{benchmark_info.get('average_ranking', 0):.2f}")
                
                if 'benchmark' in score_data:
                    for section_name, section_data in score_data['benchmark'].items():
                        if isinstance(section_data, dict):
                            UIComponents._display_score_card(section_name.title(), section_data)
                if 'trend' in score_data:
                    UIComponents._display_score_card("Análisis de Tendencia", score_data.get('trend', {}))

    @staticmethod
    def render_summary_charts(df: pd.DataFrame):
        st.header("Análisis Gráfico General")
        if df.empty:
            st.info("No hay datos para generar gráficos.")
            return

        # Definir los nombres de las columnas que se usarán
        score_col = 'Benchmark_Benchmarkscore'
        rank_col = 'Benchmark_Averageranking'
        risk_col = 'Financialrisk'

        # Gráfico de barras
        if score_col in df.columns:
            st.subheader("Comparación de Puntuación de Benchmark")
            df[score_col] = pd.to_numeric(df[score_col], errors='coerce').fillna(0)
            fig_bar = px.bar(df, x='Nombre Empresa', y=score_col, color='Nombre Empresa', title='Puntuación General de Benchmark', labels={'Nombre Empresa': 'Empresa', score_col: 'Puntuación General'})
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.warning(f"No se encontró la columna '{score_col}' para el gráfico de barras.")

        col1, col2 = st.columns(2)
        with col1:
            # Gráfico de pastel
            # CORRECCIÓN: Añadir comprobación de existencia de la columna.
            if risk_col in df.columns:
                st.subheader("Distribución de Riesgo")
                risk_counts = df[risk_col].value_counts().reset_index()
                fig_pie = px.pie(risk_counts, names=risk_col, values='count', title='Perfiles de Riesgo Financiero')
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.warning(f"No se encontró la columna '{risk_col}' para el gráfico de distribución.")

        with col2:
            # Gráfico de dispersión
            if score_col in df.columns and rank_col in df.columns:
                st.subheader("Puntuación vs. Ranking")
                df[rank_col] = pd.to_numeric(df[rank_col], errors='coerce').fillna(0)
                fig_scatter = px.scatter(df, x=score_col, y=rank_col, color='Nombre Empresa', title='Relación Puntuación vs. Ranking', labels={score_col: 'Puntuación General', rank_col: 'Ranking Promedio'})
                st.plotly_chart(fig_scatter, use_container_width=True)
            else:
                st.warning(f"No se encontraron las columnas '{score_col}' y/o '{rank_col}' para el gráfico de dispersión.")

class EMISDashboardApp:
    def __init__(self):
        SessionManager.initialize()
    
    def _flatten_dict(self, d: dict, parent_key: str = '', sep: str = '_') -> dict:
        items = []
        for k, v in d.items():
            new_key = parent_key + sep + k.title().replace('_', '') if parent_key else k.title().replace('_', '')
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def _prepare_data_for_excel(self, search_results: List[Dict]) -> pd.DataFrame:
        flat_data = []
        for result in search_results:
            company_info, benchmark_data = result.get("company_info"), result.get("benchmark_data")
            if not all([company_info, benchmark_data, benchmark_data.get('financial_scores')]):
                continue
            company_base = {"NIT Buscado": company_info.external_id, "Nombre Empresa": company_info.name, "ID EMIS": company_info.id}
            for score in benchmark_data['financial_scores']:
                row = company_base.copy()
                for section_name, section_data in score.items():
                    if isinstance(section_data, dict):
                        flat_section = self._flatten_dict(section_data, parent_key=section_name.title())
                        row.update(flat_section)
                    else:
                        row[section_name.title().replace('_', '')] = section_data
                flat_data.append(row)
        return pd.DataFrame(flat_data)

    def run(self):
        if not st.session_state[StateKey.LOGGED_IN]:
            UIComponents.render_login_page()
        else:
            self._render_main_app()

    def _render_main_app(self):
        st.set_page_config(page_title="EMIS Benchmarks", layout="wide")
        st.title("Visor de Benchmarks Financieros de EMIS")

        with st.sidebar:
            if st.button("Logout"):
                SessionManager.logout(); st.rerun()

        if search_params := UIComponents.render_sidebar():
            self._handle_search(search_params)

        if results := st.session_state.get(StateKey.SEARCH_RESULTS, []):
            st.header(f"Resultados de la Búsqueda ({len(results)} empresa(s))")
            df_for_excel = self._prepare_data_for_excel(results)
            if not df_for_excel.empty:
                output = io.BytesIO()
                df_for_excel.to_excel(output, index=False, sheet_name='Benchmarks')
                st.download_button("📥 Descargar Resultados en Excel", output.getvalue(), f"emis_benchmarks_{datetime.now():%Y%m%d_%H%M%S}.xlsx", 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', type="primary")

            for result in results:
                UIComponents.render_company_info(result.get("company_info"))
                UIComponents.render_benchmark_data(result.get("benchmark_data"))
                st.divider()

            if not df_for_excel.empty:
                st.divider()
                UIComponents.render_summary_charts(df_for_excel)

    def _handle_search(self, params: SearchParams):
        SessionManager.reset_search()
        service: EMISService = st.session_state[StateKey.EMIS_SERVICE]
        progress_bar = st.progress(0, "Iniciando búsqueda...")
        all_results = []
        for i, nit in enumerate(params.external_ids):
            progress_bar.progress((i) / len(params.external_ids), f"Procesando NIT: `{nit}` ({i+1}/{len(params.external_ids)})")
            if company_info := service.find_company_by_external_id(nit):
                benchmark_data = service.get_company_benchmark(company_info.id)
                all_results.append({"company_info": company_info, "benchmark_data": benchmark_data})
        progress_bar.progress(1.0, "¡Búsqueda completada!")
        time.sleep(1)
        progress_bar.empty()
        st.session_state[StateKey.SEARCH_RESULTS] = all_results
        st.rerun()

if __name__ == "__main__":
    app = EMISDashboardApp()
    app.run()