"""
EMIS Financials Dashboard
A Streamlit application to search for company financial statements using an external ID (NIT)
and explore them interactively, built according to the official emis_api_client SDK documentation.
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import logging
import sys
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from emis_api_client import Configuration, ApiClient
from emis_api_client.apis.companies_api import CompaniesApi
from emis_api_client.apis.dictionary_api import DictionaryApi
from emis_api_client.rest import ApiException

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

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
    STATEMENTS_DF = 'statements_df'
    SELECTED_STATEMENT = 'selected_statement'
    STATEMENT_DETAILS = 'statement_details'

# --- Clases de Datos ---
@dataclass
class CompanyInfo:
    id: int
    name: str
    external_id: str

@dataclass
class SearchParams:
    external_id: str
    years: Optional[List[int]] = None

class SessionManager:
    """Gestiona el estado de la sesión de Streamlit de forma centralizada."""
    
    @staticmethod
    def initialize() -> None:
        """Inicializa las variables de estado de la sesión si no existen."""
        defaults = {
            StateKey.LOGGED_IN: False,
            StateKey.EMIS_SERVICE: None,
            StateKey.COMPANY_INFO: None,
            StateKey.STATEMENTS_DF: None,
            StateKey.SELECTED_STATEMENT: None,
            StateKey.STATEMENT_DETAILS: None
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
        st.session_state[StateKey.STATEMENTS_DF] = None
        st.session_state[StateKey.SELECTED_STATEMENT] = None
        st.session_state[StateKey.STATEMENT_DETAILS] = None

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
        self.dictionary_api = DictionaryApi(api_client=self.api_client)

    def _sleep(self):
        time.sleep(0.5)

    def find_company_by_external_id(self, external_id: str) -> Optional[CompanyInfo]:
        """
        Busca una empresa por su ID externo (NIT) usando el método `companies_match_get`.
        Referencia de la documentación: Namespace: emis_api_client.apis.companies_api, Class: CompaniesApi, Method: companies_match_get
        """
        logger.info(f"Attempting to match company with external_id: {external_id}")
        try:
            # Según la documentación, `external_id` debe ser una lista de strings.
            response = self.companies_api.companies_match_get(
                token=self.token, 
                external_id=[external_id],
                limit=1  # Solo nos interesa el match más relevante.
            )
            self._sleep()

            if response and response.data and response.data.items:
                # El primer item es el mejor match.
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

    def get_company_statements(self, company_id: int, years: Optional[List[int]]) -> Optional[List[Any]]:
        """
        Obtiene los estados financieros de una empresa usando `companies_id_statements_get`.
        Referencia: Namespace: emis_api_client.apis.companies_api, Class: CompaniesApi, Method: companies_id_statements_get
        """
        logger.info(f"Fetching statements for company ID: {company_id} for years: {years}")
        try:
            params = {"token": self.token, "limit": 100} # Aumentamos el límite por si acaso
            if years:
                # El SDK espera que 'year' sea un entero, no una lista. Haremos una llamada por año.
                all_statements = []
                for year in years:
                    params["year"] = year
                    response = self.companies_api.companies_id_statements_get(id=company_id, **params)
                    self._sleep()
                    if response and response.data and response.data.items:
                        all_statements.extend(response.data.items)
                return all_statements
            else:
                # Si no hay años, se hace una sola llamada para traer todos los disponibles.
                response = self.companies_api.companies_id_statements_get(id=company_id, **params)
                self._sleep()
                return response.data.items if response and response.data else []

        except ApiException as e:
            logger.error(f"API Error getting statements for company {company_id}: {e}")
            st.error(f"Error al obtener los estados financieros: {e.reason}")
            return None

    def get_statement_details(self, statement_id: int, standard_code: str) -> Optional[pd.DataFrame]:
        """
        Obtiene las cuentas y sus descripciones para un estado y estándar específicos.
        Usa: `companies_statements_id_accounts_standard_id_get` y `dictionary_standards_id_accounts_get`.
        """
        logger.info(f"Fetching details for statement {statement_id} with standard {standard_code}")
        
        # 1. Obtener las cuentas (valores)
        try:
            response_accounts = self.companies_api.companies_statements_id_accounts_standard_id_get(
                statement_id, standard_code, token=self.token, currency="COP"
            )
            self._sleep()
            if not (response_accounts and response_accounts.data and response_accounts.data.items):
                return None
            accounts = response_accounts.data.items
        except ApiException as e:
            logger.error(f"API Error getting accounts for statement {statement_id}: {e}")
            return None

        # 2. Obtener descripciones de las cuentas (cacheable)
        descriptions = self._get_account_descriptions(standard_code)

        # 3. Combinar en un DataFrame
        df_data = [{
            'Código de Cuenta': acc.code,
            'Nombre de Cuenta': descriptions.get(acc.code, 'N/A'),
            'Valor (COP)': f"{acc.value:,.2f}" if isinstance(acc.value, (int, float)) else acc.value
        } for acc in accounts]
        
        return pd.DataFrame(df_data)

    @st.cache_data(show_spinner="Cargando descripciones de cuentas...")
    def _get_account_descriptions(_self, standard_code: str) -> Dict[str, str]:
        """
        Obtiene y cachea las descripciones de las cuentas para un estándar.
        Usa: `dictionary_standards_id_accounts_get`
        """
        logger.info(f"Fetching account descriptions for standard: {standard_code}")
        try:
            desc_response = _self.dictionary_api.dictionary_standards_id_accounts_get(
                standard_code, token=_self.token, limit=100 # Límite alto para traer todas las cuentas
            )
            _self._sleep()
            if desc_response and desc_response.data and desc_response.data.items:
                return {d.id: d.name for d in desc_response.data.items}
            return {}
        except ApiException as e:
            logger.error(f"API Error getting descriptions for {standard_code}: {e}")
            st.warning(f"No se pudieron obtener las descripciones para el estándar {standard_code}.")
            return {}

class UIComponents:
    """Renderiza todos los componentes de la interfaz de usuario."""

    @staticmethod
    def render_login_page():
        st.set_page_config(page_title="Login - EMIS Financials", layout="centered")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image("./static/logo2.png", width=200)
            st.title("EMIS Financials Dashboard")
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
        years_str = st.sidebar.text_input("Años (opcional)", help="Ej: 2021, 2022, 2023. Déjalo vacío para traer todos.")
        
        if st.sidebar.button("Buscar Empresa"):
            if not external_id:
                st.sidebar.warning("El campo NIT es obligatorio.")
                return None
            
            years = None
            if years_str:
                try:
                    years = [int(y.strip()) for y in years_str.split(',') if y.strip().isdigit()]
                except ValueError:
                    st.sidebar.error("Formato de años inválido. Usa números separados por comas.")
                    return None
            
            return SearchParams(external_id=external_id, years=years)
        
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
    def render_statements_table(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if df is None or df.empty:
            st.info("No se encontraron estados financieros para los criterios seleccionados.")
            return None

        st.markdown("---")
        st.subheader(f"Estados Financieros Encontrados ({len(df)})")
        st.write("Haz clic en una fila para ver los detalles de un estado financiero.")
        
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_selection('single', use_checkbox=False, pre_selected_rows=None)
        gb.configure_column("statement_id", hide=True)
        gb.configure_column("supported_standards", hide=True)
        
        grid_options = gb.build()
        grid_response = AgGrid(
            df,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            fit_columns_on_grid_load=True,
            height=300,
            allow_unsafe_jscode=True,
        )
        
        # --- INICIO DE LA CORRECCIÓN ---
        # `selected_rows` es un DataFrame. Debemos verificar si no está vacío.
        selected_rows_df = grid_response['selected_rows']
        
        # Comprobar si el DataFrame existe y no está vacío.
        if selected_rows_df is not None and not selected_rows_df.empty:
            # Convertir la primera (y única) fila seleccionada a un diccionario.
            return selected_rows_df.to_dict('records')[0]
        
        # Si no se ha seleccionado ninguna fila, devolver None.
        return None
        
    @staticmethod
    def render_statement_details(details: Dict[str, pd.DataFrame]):
        if not details:
            return
        
        st.markdown("---")
        statement_info = st.session_state[StateKey.SELECTED_STATEMENT]
        statement_id = statement_info['statement_id']
        st.subheader(f"Detalle del Estado Financiero (ID: {statement_id})")

        # --- INICIO DE LA CORRECCIÓN ---
        # Se eliminó la referencia a 'statement_info['Tipo']' que ya no existe en el DataFrame.
        st.write(f"**Periodo:** {statement_info['Periodo']}, **Año:** {statement_info['Año']}")
        # --- FIN DE LA CORRECCIÓN ---

        # Usar st.tabs para una mejor visualización de los estándares
        if details:
            standard_codes = list(details.keys())
            tabs = st.tabs(standard_codes)
            for i, std_code in enumerate(standard_codes):
                with tabs[i]:
                    df = details[std_code]
                    if df is None or df.empty:
                        st.write("No hay datos disponibles para este estándar.")
                    else:
                        st.dataframe(df, use_container_width=True)

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
        st.set_page_config(page_title="EMIS Financials", layout="wide")
        st.title("Visor de Estados Financieros de EMIS")

        with st.sidebar:
            if st.button("Logout"):
                SessionManager.logout()
                st.rerun()

        search_params = UIComponents.render_sidebar()
        
        if search_params:
            self._handle_search(search_params)
            # Rerun to clear selection and old details after a new search
            st.rerun()

        # --- Renderizar resultados ---
        if st.session_state[StateKey.COMPANY_INFO]:
            UIComponents.render_company_info(st.session_state[StateKey.COMPANY_INFO])
        
        if st.session_state[StateKey.STATEMENTS_DF] is not None:
            selected_statement = UIComponents.render_statements_table(st.session_state[StateKey.STATEMENTS_DF])
            if selected_statement and selected_statement != st.session_state.get(StateKey.SELECTED_STATEMENT):
                st.session_state[StateKey.SELECTED_STATEMENT] = selected_statement
                self._handle_statement_selection(selected_statement)

        if st.session_state.get(StateKey.STATEMENT_DETAILS):
             UIComponents.render_statement_details(st.session_state[StateKey.STATEMENT_DETAILS])

    def _handle_search(self, params: SearchParams):
        SessionManager.reset_search()
        service: EMISService = st.session_state[StateKey.EMIS_SERVICE]
        
        with st.spinner(f"Buscando empresa con NIT: {params.external_id}..."):
            company_info = service.find_company_by_external_id(params.external_id)
            st.session_state[StateKey.COMPANY_INFO] = company_info

        if company_info:
            with st.spinner(f"Obteniendo estados financieros para {company_info.name}..."):
                statements = service.get_company_statements(company_info.id, params.years)
                if statements:
                    # --- INICIO DE LA CORRECCIÓN ---
                    # Se eliminó la referencia a 's.type' y se usa 's.year' directamente.
                    df_data = [{
                        "statement_id": s.id,
                        "Año": s.year if s.year else 'N/A', # Usar el atributo 'year' directamente. Es más simple y correcto.
                        "Periodo": s.period,
                        # "Tipo": s.type, <-- LÍNEA ELIMINADA PORQUE EL ATRIBUTO NO EXISTE
                        "Auditado": s.is_audited,
                        "Consolidado": s.is_consolidated,
                        "supported_standards": s.financial_standard.supported_standards if s.financial_standard else []
                    } for s in statements]
                    # --- FIN DE LA CORRECCIÓN ---
                        
                    st.session_state[StateKey.STATEMENTS_DF] = pd.DataFrame(df_data)
                else:
                    st.session_state[StateKey.STATEMENTS_DF] = pd.DataFrame() # DF vacío para mostrar mensaje
    def _handle_statement_selection(self, selected_statement: Dict[str, Any]):
        service: EMISService = st.session_state[StateKey.EMIS_SERVICE]
        statement_id = selected_statement['statement_id']
        standards = selected_statement['supported_standards']
        
        st.session_state[StateKey.STATEMENT_DETAILS] = {}
        
        if not standards:
            st.warning("Este estado financiero no tiene estándares soportados para mostrar detalles.")
            return

        with st.spinner(f"Cargando detalles para el estado financiero ID: {statement_id}..."):
            details_by_standard = {}
            for std_code in standards:
                details_df = service.get_statement_details(statement_id, std_code)
                details_by_standard[std_code] = details_df
            st.session_state[StateKey.STATEMENT_DETAILS] = details_by_standard
        
        st.rerun()

if __name__ == "__main__":
    app = EMISDashboardApp()
    app.run()