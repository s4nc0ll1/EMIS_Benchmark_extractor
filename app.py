"""
EMIS Benchmark Dashboard
A Streamlit application to search for a company by its external ID (NIT)
and explore its industry benchmarks interactively, using the emis_api_client SDK.
"""

import streamlit as st
import pandas as pd
import logging
import sys
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

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
    COMPANY_INFO = 'company_info'
    BENCHMARK_DATA = 'benchmark_data' # Reemplaza a las claves de estados financieros

# --- Clases de Datos ---
@dataclass
class CompanyInfo:
    id: int
    name: str
    external_id: str

@dataclass
class SearchParams:
    external_id: str

class SessionManager:
    """Gestiona el estado de la sesión de Streamlit de forma centralizada."""
    
    @staticmethod
    def initialize() -> None:
        """Inicializa las variables de estado de la sesión si no existen."""
        defaults = {
            StateKey.LOGGED_IN: False,
            StateKey.EMIS_SERVICE: None,
            StateKey.COMPANY_INFO: None,
            StateKey.BENCHMARK_DATA: None
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    @staticmethod
    def logout() -> None:
        """Limpia la sesión al cerrar."""
        keys_to_delete = [k for k in st.session_state.keys()]
        for key in keys_to_delete:
            del st.session_state[key]
        SessionManager.initialize()

    @staticmethod
    def reset_search() -> None:
        """Resetea los resultados de búsqueda anteriores."""
        st.session_state[StateKey.COMPANY_INFO] = None
        st.session_state[StateKey.BENCHMARK_DATA] = None

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
            logger.info("User authenticated successfully.")
            return True
        except Exception as e:
            st.error(f"La configuración del cliente falló: {e}")
            logger.error(f"API client setup failed: {e}", exc_info=True)
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
        """Busca una empresa por su ID externo (NIT) usando el método `companies_match_get`."""
        logger.info(f"Attempting to match company with external_id: {external_id}")
        try:
            response = self.companies_api.companies_match_get(
                token=self.token, 
                external_id=[external_id],
                limit=1
            )
            self._sleep()

            if response and response.data and response.data.items:
                match_item = response.data.items[0]
                info = CompanyInfo(
                    id=match_item.company_id,
                    name=match_item.company_name,
                    external_id=external_id
                )
                logger.info(f"Successfully matched company: {info.name} (ID: {info.id})")
                return info
            else:
                logger.warning(f"No match found for external_id: {external_id}")
                st.error(f"No se encontró ninguna empresa con el NIT '{external_id}'.")
                return None
        except ApiException as e:
            logger.error(f"API Error matching company with NIT {external_id}: {e}", exc_info=True)
            st.error(f"Error de API al buscar la empresa. Código: {e.status}. Razón: {e.reason}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during company match: {e}", exc_info=True)
            st.error(f"Ocurrió un error inesperado al buscar la empresa.")
            return None

    def get_company_benchmark(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene los datos de benchmark para una empresa usando `companies_id_benchmark_get`.
        Referencia del endpoint: /v2/company/companies/{id}/benchmark
        """
        logger.info(f"Fetching benchmark data for company ID: {company_id}")
        try:
            # Se asume que el método en el SDK sigue el patrón del endpoint.
            response = self.companies_api.companies_id_benchmark_get(id=company_id, token=self.token)
            self._sleep()
            
            if response and response.data:
                logger.info(f"Successfully fetched benchmark for company ID: {company_id}")
                # El SDK envuelve la respuesta en un objeto `data`. La devolvemos como un diccionario.
                return response.data.to_dict()
            else:
                logger.warning(f"No benchmark data found for company ID: {company_id}")
                st.info("No se encontraron datos de benchmark para esta empresa.")
                return None
        except ApiException as e:
            logger.error(f"API Error getting benchmark for company {company_id}: {e}", exc_info=True)
            st.error(f"Error de API al obtener el benchmark. Código: {e.status}. Razón: {e.reason}")
            return None
        except AttributeError:
            # Captura el caso en que el método `companies_id_benchmark_get` no exista en el SDK.
            st.error("Error crítico: El método 'companies_id_benchmark_get' no parece estar disponible en el SDK 'emis_api_client' que está utilizando. Por favor, asegúrese de que el SDK esté actualizado y sea compatible con el endpoint de benchmarks.")
            logger.error("SDK method 'companies_id_benchmark_get' not found.")
            return None


class UIComponents:
    """Renderiza todos los componentes de la interfaz de usuario."""

    @staticmethod
    def render_login_page():
        st.set_page_config(page_title="Login - EMIS Benchmarks", layout="centered")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image("./static/logo2.png", width=200)
            st.title("EMIS Benchmark Dashboard")
            st.write("Por favor, introduce tu token de la API de EMIS para continuar.")
            
            token = st.text_input("EMIS API Token", type="password")
            if st.button("Login"):
                if AuthenticationService.login(token):
                    st.rerun()

    @staticmethod
    def render_sidebar() -> Optional[SearchParams]:
        st.sidebar.image("./static/logo2.png", width=150)
        st.sidebar.header("Opciones de Búsqueda")
        
        external_id = st.sidebar.text_input("NIT de la Empresa", help="Introduce el NIT o ID externo de la empresa a buscar.")
        
        if st.sidebar.button("Buscar Empresa"):
            if not external_id:
                st.sidebar.warning("El campo NIT es obligatorio.")
                return None
            return SearchParams(external_id=external_id)
        
        return None

    @staticmethod
    def render_company_info(info: CompanyInfo):
        if info:
            st.subheader("Resultados de la Búsqueda")
            st.markdown(f"""
            <div style='border: 1px solid #ddd; padding: 10px; border-radius: 5px;'>
                <p style='margin-bottom: 5px;'><strong>Empresa Encontrada:</strong> {info.name}</p>
                <p style='margin-bottom: 5px;'><strong>ID de EMIS:</strong> <code>{info.id}</code></p>
                <p style='margin-bottom: 0;'><strong>NIT Buscado:</strong> <code>{info.external_id}</code></p>
            </div>
            """, unsafe_allow_html=True)
    
    @staticmethod
    def _display_score_card(title: str, data: Dict):
        """Función auxiliar para mostrar una categoría de scores en un expander."""
        with st.expander(f"Detalles de {title}", expanded=False):
            # Transforma el diccionario en un DataFrame para una mejor visualización
            df_data = []
            for key, value in data.items():
                if isinstance(value, dict) or isinstance(value, list): continue # Omitir sub-diccionarios por simplicidad
                
                # Nombres más amigables para las claves
                friendly_name = key.replace('_', ' ').replace('score', ' Score').replace('ranking', ' Ranking').title()
                df_data.append({"Métrica": friendly_name, "Valor": value})

            if df_data:
                st.dataframe(pd.DataFrame(df_data), use_container_width=True, hide_index=True)


    @staticmethod
    def render_benchmark_data(data: Optional[Dict[str, Any]]):
        if not data or not data.get('financial_scores'):
            st.info("No hay datos de benchmark disponibles para mostrar.")
            return

        st.markdown("---")
        st.subheader("Análisis de Benchmark Financiero")
        st.markdown(f"""
        - **Perfil de Riesgo General:** `{data.get('risk_profile', 'N/A')}`
        - **Escala de Puntuación:** `{data.get('score_scale', 'N/A')}`
        """)

        financial_scores = data['financial_scores']
        
        # Crear una pestaña por cada benchmark de industria
        tab_titles = [f"Benchmark Industria {score.get('industry_code', 'N/A')}" for score in financial_scores]
        tabs = st.tabs(tab_titles)

        for i, score_data in enumerate(financial_scores):
            with tabs[i]:
                # --- Sección de Scores Principales ---
                st.write(f"**Año Fiscal del Benchmark:** `{score_data.get('period', {}).get('fiscal_year', 'N/A')}` | **Empresas en Comparación:** `{score_data.get('period', {}).get('company_count', 'N/A')}`")
                
                cols = st.columns(3)
                benchmark_info = score_data.get('benchmark', {})
                cols[0].metric(label="Riesgo Financiero", value=str(score_data.get('financial_risk', 'N/A')))
                cols[1].metric(label="Puntuación Benchmark General", value=f"{benchmark_info.get('benchmark_score', 0):.2f}")
                cols[2].metric(label="Ranking Promedio", value=f"{benchmark_info.get('average_ranking', 0):.2f}")

                # --- Sección de Scores por Categoría ---
                st.markdown("---")
                st.write("#### Desglose por Categoría")

                if 'benchmark' in score_data:
                    benchmark_details = score_data['benchmark']
                    UIComponents._display_score_card("Tamaño", benchmark_details.get('size', {}))
                    UIComponents._display_score_card("Crecimiento", benchmark_details.get('growth', {}))
                    UIComponents._display_score_card("Rentabilidad", benchmark_details.get('profitability', {}))
                    UIComponents._display_score_card("Endeudamiento", benchmark_details.get('indebtedness', {}))
                
                if 'trend' in score_data:
                    UIComponents._display_score_card("Análisis de Tendencia", score_data.get('trend', {}))


class EMISDashboardApp:
    """Clase principal de la aplicación que orquesta la UI y los servicios."""

    def __init__(self):
        SessionManager.initialize()

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
                SessionManager.logout()
                st.rerun()

        search_params = UIComponents.render_sidebar()
        
        if search_params:
            self._handle_search(search_params)
            st.rerun()

        # --- Renderizar resultados ---
        if st.session_state[StateKey.COMPANY_INFO]:
            UIComponents.render_company_info(st.session_state[StateKey.COMPANY_INFO])
        
        if st.session_state[StateKey.BENCHMARK_DATA]:
            UIComponents.render_benchmark_data(st.session_state[StateKey.BENCHMARK_DATA])

    def _handle_search(self, params: SearchParams):
        SessionManager.reset_search()
        service: EMISService = st.session_state[StateKey.EMIS_SERVICE]
        
        with st.spinner(f"Buscando empresa con NIT: {params.external_id}..."):
            company_info = service.find_company_by_external_id(params.external_id)
            st.session_state[StateKey.COMPANY_INFO] = company_info

        if company_info:
            with st.spinner(f"Obteniendo datos de benchmark para {company_info.name}..."):
                benchmark_data = service.get_company_benchmark(company_info.id)
                st.session_state[StateKey.BENCHMARK_DATA] = benchmark_data

if __name__ == "__main__":
    app = EMISDashboardApp()
    app.run()