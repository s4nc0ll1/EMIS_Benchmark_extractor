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

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="EMIS Benchmark Dashboard", layout="wide")

from emis_api_client import Configuration, ApiClient
from emis_api_client.apis.companies_api import CompaniesApi
from emis_api_client.rest import ApiException

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Brand Theme (extraído del logo corporativo)
# ---------------------------------------------------------------------------
BRAND = {
    "primary": "#FF5315",
    "primary_hover": "#E64510",
    "primary_dark": "#B33A0F",
    "primary_light": "#FFEEE8",
    "primary_soft": "#FFDDD0",
    "text": "#1A1A1A",
    "text_secondary": "#6B7280",
    "border": "#E8E5E3",
    "bg_page": "#FAF9F8",
    "bg_card": "#FFFFFF",
}
CHART_PALETTE = ["#FF5315", "#FFA36B", "#B33A0F", "#4A4A4A", "#FF8B4D", "#7A2E0A", "#D8430D", "#FFD1B3"]
RISK_COLORS = {"A": "#1F8A5F", "B": "#6FBF73", "C": "#F5B942", "D": "#FF5315", "E": "#B33A0F"}
RISK_DESCRIPTIONS = {"A": "Muy Bajo", "B": "Bajo", "C": "Medio", "D": "Alto", "E": "Muy Alto"}


def apply_custom_theme() -> None:
    """Inyecta CSS para alinear la interfaz con la identidad de marca corporativa."""
    st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {{ font-family: 'Inter', -apple-system, sans-serif; }}

        .stApp {{ background-color: {BRAND["bg_page"]}; }}

        /* ---------- Headings ---------- */
        h1, h2, h3 {{ color: {BRAND["text"]} !important; font-weight: 800 !important; letter-spacing: -0.02em; }}
        h1 {{ border-bottom: 3px solid {BRAND["primary"]}; padding-bottom: 0.5rem; display: inline-block; }}

        /* ---------- Sidebar ---------- */
        [data-testid="stSidebar"] {{
            background-color: {BRAND["bg_card"]};
            border-right: 1px solid {BRAND["border"]};
        }}
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{
            color: {BRAND["primary_dark"]} !important; border-bottom: none;
        }}

        /* ---------- Buttons ---------- */
        .stButton>button, [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"] {{
            border-radius: 8px !important;
            font-weight: 600 !important;
            transition: all 0.15s ease-in-out;
        }}
        .stButton>button[kind="primary"], [data-testid="stBaseButton-primary"] {{
            background-color: {BRAND["primary"]} !important;
            border-color: {BRAND["primary"]} !important;
            box-shadow: 0 2px 6px rgba(255, 83, 21, 0.25);
        }}
        .stButton>button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {{
            background-color: {BRAND["primary_hover"]} !important;
            border-color: {BRAND["primary_hover"]} !important;
            box-shadow: 0 4px 10px rgba(255, 83, 21, 0.35);
        }}

        /* ---------- Bordered containers -> tarjetas estilo dashboard ---------- */
        [data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 14px !important;
            border-color: {BRAND["border"]} !important;
            background-color: {BRAND["bg_card"]};
            box-shadow: 0 1px 3px rgba(0,0,0,0.05), 0 1px 2px rgba(0,0,0,0.04);
            transition: box-shadow 0.2s ease;
        }}
        [data-testid="stVerticalBlockBorderWrapper"]:hover {{
            box-shadow: 0 6px 16px rgba(255, 83, 21, 0.10);
        }}

        /* ---------- Native metrics ---------- */
        [data-testid="stMetric"] {{
            background-color: {BRAND["bg_card"]};
            border: 1px solid {BRAND["border"]};
            border-radius: 12px;
            padding: 0.9rem 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }}
        [data-testid="stMetricLabel"] {{ color: {BRAND["text_secondary"]} !important; text-transform: uppercase; font-size: 0.72rem !important; letter-spacing: 0.04em; }}
        [data-testid="stMetricValue"] {{ color: {BRAND["text"]} !important; font-weight: 800 !important; }}

        /* ---------- Custom metric cards ---------- */
        .emis-metric-card {{
            background-color: {BRAND["bg_card"]};
            border: 1px solid {BRAND["border"]};
            border-radius: 12px;
            padding: 0.9rem 1.1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            margin-bottom: 0.6rem;
        }}
        .emis-metric-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem; }}
        .emis-metric-label {{ font-size: 0.72rem; color: {BRAND["text_secondary"]}; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600; }}
        .emis-metric-value {{ font-size: 1.6rem; font-weight: 800; color: {BRAND["text"]}; }}

        /* ---------- Badge "EMIS API" ---------- */
        .emis-badge {{
            display: inline-flex; align-items: center; gap: 5px;
            background-color: {BRAND["primary_light"]};
            color: {BRAND["primary_dark"]};
            font-size: 0.65rem; font-weight: 700;
            text-transform: uppercase; letter-spacing: 0.04em;
            padding: 3px 9px; border-radius: 999px;
            white-space: nowrap;
        }}
        .emis-badge::before {{
            content: ''; width: 6px; height: 6px; border-radius: 50%;
            background-color: {BRAND["primary"]}; display: inline-block;
        }}

        /* ---------- Tabs ---------- */
        [data-testid="stTabs"] button[aria-selected="true"] {{
            color: {BRAND["primary"]} !important;
            border-bottom-color: {BRAND["primary"]} !important;
            font-weight: 700 !important;
        }}
        [data-testid="stTabs"] button p {{ font-weight: 600; }}

        /* ---------- Progress bar ---------- */
        [data-testid="stProgress"] > div > div > div {{ background-color: {BRAND["primary"]} !important; }}

        /* ---------- Text inputs ---------- */
        .stTextInput input:focus {{ border-color: {BRAND["primary"]} !important; box-shadow: 0 0 0 1px {BRAND["primary"]} !important; }}

        /* ---------- Dividers ---------- */
        hr {{ border-color: {BRAND["border"]} !important; }}

        /* ---------- Tarjetas de Tendencia / Momentum ---------- */
        .emis-trend-card {{
            background-color: {BRAND["bg_card"]};
            border: 1px solid {BRAND["border"]};
            border-left: 4px solid {BRAND["border"]};
            border-radius: 10px;
            padding: 0.65rem 0.9rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            margin-bottom: 0.5rem;
        }}
        .emis-trend-label {{ font-size: 0.68rem; color: {BRAND["text_secondary"]}; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600; margin-bottom: 0.15rem; }}
        .emis-trend-risk {{ font-size: 1.3rem; font-weight: 800; line-height: 1.15; display: flex; align-items: baseline; gap: 6px; }}
        .emis-trend-risk-text {{ font-size: 0.72rem; font-weight: 600; color: {BRAND["text_secondary"]}; }}
        .emis-trend-score {{ font-size: 0.7rem; color: {BRAND["text_secondary"]}; margin-top: 0.2rem; }}

        /* ---------- Imágenes centradas dentro de su contenedor ---------- */
        [data-testid="stImage"] {{ display: flex; justify-content: center; }}
        [data-testid="stImage"] img {{ margin: 0 auto; }}

        /* ---------- Login card helpers ---------- */
        .emis-login-title {{ text-align: center; margin: 0.6rem 0 0.1rem 0; }}
        .emis-login-subtitle {{ text-align: center; color: {BRAND["text_secondary"]}; margin-bottom: 1.2rem; font-size: 0.9rem; }}
    </style>
    """, unsafe_allow_html=True)


def render_badge(text: str = "EMIS API") -> str:
    return f"<span class='emis-badge'>{text}</span>"


def truncate_label(name: str, max_len: int = 30) -> str:
    """Acorta nombres largos para ejes de gráficos, conservando el original para el hover."""
    name = str(name).strip()
    return name if len(name) <= max_len else name[:max_len - 1].rstrip() + "…"


def render_metric_card(label: str, value: str, badge: bool = True) -> None:
    badge_html = render_badge() if badge else ""
    st.markdown(f"""
        <div class="emis-metric-card">
            <div class="emis-metric-header">
                <span class="emis-metric-label">{label}</span>
                {badge_html}
            </div>
            <div class="emis-metric-value">{value}</div>
        </div>
    """, unsafe_allow_html=True)


def dual_get(d: Dict[str, Any], snake: str, camel: str, default=None):
    """Lee un campo soportando snake_case y camelCase, según cómo lo serialice la API."""
    d = d or {}
    return d.get(snake, d.get(camel, default))


TREND_RISK_LABELS = {"A": "Muy Positiva", "B": "Positiva", "C": "Estable", "D": "Negativa", "E": "Muy Negativa"}


def render_trend_badge_card(label: str, risk_letter: Optional[str], score: Optional[float] = None) -> None:
    color = RISK_COLORS.get(risk_letter, BRAND["text_secondary"])
    risk_display = risk_letter or "N/A"
    trend_text = TREND_RISK_LABELS.get(risk_letter, "Sin datos")
    score_html = f"<div class='emis-trend-score'>Score: {score:.2f}</div>" if score is not None else ""
    st.markdown(f"""
        <div class="emis-trend-card" style="border-left-color:{color};">
            <div class="emis-trend-label">{label}</div>
            <div class="emis-trend-risk" style="color:{color};">{risk_display}<span class="emis-trend-risk-text">{trend_text}</span></div>
            {score_html}
        </div>
    """, unsafe_allow_html=True)

class StateKey:
    LOGGED_IN, EMIS_SERVICE, SEARCH_RESULTS, LOCAL_BENCHMARKS, INDUSTRY_NAMES, CURRENT_PAGE = 'logged_in', 'emis_service', 'search_results', 'local_benchmarks', 'industry_names', 'current_page'

@dataclass
class CompanyInfo: id: int; name: str; external_id: str
@dataclass
class SearchParams: external_ids: List[str]

@st.cache_data
def load_local_benchmarks(file_path: str) -> Dict[str, Any]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f: data = json.load(f)
        return {str(item['company_info']['nit']): item for item in data}
    except FileNotFoundError: return {}

@st.cache_data
def load_industry_names(file_path: str) -> Dict[str, str]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f: data = json.load(f)
        return {item['code']: item['name'] for item in data}
    except FileNotFoundError: return {}

class EmailService:
    @staticmethod
    def send_report(recipients: List[str], excel_data: io.BytesIO, filename: str) -> bool:
        try:
            sender_email = st.secrets["gmail"]["user"]
            sender_password = st.secrets["gmail"]["app_password"]
        except (KeyError, FileNotFoundError):
            st.error("Error: Faltan las credenciales de correo en el archivo `secrets.toml`.")
            return False

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = f"Reporte de Benchmarks EMIS - {datetime.now():%Y-%m-%d}"

        body = "Adjunto se encuentra el reporte de benchmarks financieros generado desde el EMIS Benchmark Dashboard."
        msg.attach(MIMEText(body, 'plain'))

        part = MIMEBase('application', 'octet-stream')
        part.set_payload(excel_data.getvalue())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {filename}")
        msg.attach(part)

        try:
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, recipients, msg.as_string())
            return True
        except smtplib.SMTPAuthenticationError:
            st.error("Error de autenticación con Gmail. Verifica el usuario y la contraseña de aplicación en `secrets.toml`.")
            return False
        except Exception as e:
            st.error(f"No se pudo enviar el correo: {e}")
            return False

class SessionManager:
    @staticmethod
    def initialize() -> None:
        defaults = {
            StateKey.LOGGED_IN: False, StateKey.EMIS_SERVICE: None,
            StateKey.SEARCH_RESULTS: [], StateKey.CURRENT_PAGE: 1,
            StateKey.LOCAL_BENCHMARKS: load_local_benchmarks("./data/benchmarks.json"),
            StateKey.INDUSTRY_NAMES: load_industry_names("./data/industries.json"),
        }
        for key, value in defaults.items():
            if key not in st.session_state: st.session_state[key] = value
    @staticmethod
    def logout() -> None:
        for key in list(st.session_state.keys()): del st.session_state[key]
        SessionManager.initialize()
    @staticmethod
    def reset_search() -> None:
        st.session_state[StateKey.SEARCH_RESULTS] = []
        st.session_state[StateKey.CURRENT_PAGE] = 1

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
                return CompanyInfo(id=response.data.items[0].company_id, name=response.data.items[0].company_name, external_id=external_id)
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
        col1, col2, col3 = st.columns([1, 1.3, 1])
        with col2:
            with st.container(border=True):
                logo_col1, logo_col2, logo_col3 = st.columns([1, 1.4, 1])
                with logo_col2:
                    st.image("./static/logo2.png", width=170)
                st.markdown("<h2 class='emis-login-title'>EMIS Benchmark Dashboard</h2>", unsafe_allow_html=True)
                st.markdown("<p class='emis-login-subtitle'>Análisis de benchmarks financieros por industria</p>", unsafe_allow_html=True)
                token = st.text_input("EMIS API Token", type="password", placeholder="Introduce tu EMIS API Token")
                if st.button("Ingresar", type="primary", use_container_width=True):
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
    @staticmethod
    def render_pagination_controls(total_results: int, page_size: int, key_prefix: str):
        total_pages = (total_results + page_size - 1) // page_size
        if total_pages <= 1: return
        current_page = st.session_state[StateKey.CURRENT_PAGE]
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("⬅️ Anterior", disabled=(current_page == 1), key=f"{key_prefix}_prev"):
                st.session_state[StateKey.CURRENT_PAGE] -= 1; st.rerun()
        with col2:
            st.markdown(f"<p style='text-align: center; margin-top: 0.5rem;'>Página <b>{current_page}</b> de <b>{total_pages}</b></p>", unsafe_allow_html=True)
        with col3:
            if st.button("Siguiente ➡️", disabled=(current_page == total_pages), key=f"{key_prefix}_next"):
                st.session_state[StateKey.CURRENT_PAGE] += 1; st.rerun()
    @staticmethod
    def render_company_info(info: CompanyInfo):
        if info:
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.subheader(f"{info.name}")
                    st.markdown(f"**ID de EMIS:** `{info.id}` | **NIT Buscado:** `{info.external_id}`")
                with col2:
                    st.markdown(f"<div style='text-align:right; padding-top:0.9rem;'>{render_badge()}</div>", unsafe_allow_html=True)
    @staticmethod
    def _create_risk_benchmark_dashboard(company_data):
        company_count = company_data.get("companyCount", 5000)
        colors_active = RISK_COLORS
        risk_categories = ["A", "B", "C", "D", "E"]
        risk_descriptions = RISK_DESCRIPTIONS
        fig = go.Figure()
        for risk in risk_categories:
            is_active = risk == company_data["risk"]
            hover_text = (f"<b>Categoría: {risk}</b> ({risk_descriptions.get(risk, '')})<br>" +
                        (f"<b>Su Empresa:</b><br>• Score: {company_data['benchmarkScore']:.1f}<br>• Ranking: {company_data['averageRanking']:.0f} de {int(company_count)}"
                        if is_active else "<i>Su empresa no está aquí</i>"))
            fig.add_trace(go.Bar(name=risk, x=[risk], y=[100], marker_color=colors_active.get(risk) if is_active else "#EDEAE7",
                                marker_line=dict(color="white", width=2), hovertemplate=hover_text + "<extra></extra>", showlegend=False))
        fig.update_layout(title={"text": f"<b>Clasificación de Riesgo: <span style='color:{colors_active.get(company_data['risk'])}'>{company_data['risk']}</span></b>", "x": 0.5, "xanchor": "center"},
                          xaxis_title="Categorías de Riesgo", yaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
                          height=350, template="plotly_white", hovermode="x",
                          font=dict(family="Inter, sans-serif", color=BRAND["text"]),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig
    @staticmethod
    def _create_financial_profile_radar(benchmark_info: Dict[str, Any]) -> go.Figure:
        def score_of(section_key: str, snake: str, camel: str) -> float:
            section = benchmark_info.get(section_key) or {}
            try:
                return float(section.get(snake, section.get(camel, 0)) or 0)
            except (TypeError, ValueError):
                return 0.0
        categories = ["Tamaño", "Crecimiento", "Rentabilidad", "Endeudamiento"]
        values = [
            score_of("size", "average_size_score", "averageSizeScore"),
            score_of("growth", "average_growth_score", "averageGrowthScore"),
            score_of("profitability", "average_profitability_score", "averageProfitabilityScore"),
            score_of("indebtedness", "average_indebtedness_score", "averageIndebtednessScore"),
        ]
        categories_closed, values_closed = categories + [categories[0]], values + [values[0]]
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=values_closed, theta=categories_closed, fill="toself",
            fillcolor="rgba(255, 83, 21, 0.18)",
            line=dict(color=BRAND["primary"], width=2.5),
            marker=dict(size=6, color=BRAND["primary"]),
            hovertemplate="<b>%{theta}</b><br>Puntuación: %{r:.1f}<extra></extra>", name="Perfil"))
        fig.update_layout(
            title={"text": "<b>Perfil Financiero</b>", "x": 0.5, "xanchor": "center"},
            polar=dict(bgcolor="rgba(0,0,0,0)",
                       radialaxis=dict(visible=True, range=[0, 100], showticklabels=True,
                                        tickfont=dict(size=9, color=BRAND["text_secondary"]), gridcolor=BRAND["border"]),
                       angularaxis=dict(tickfont=dict(size=12, color=BRAND["text"]), gridcolor=BRAND["border"])),
            showlegend=False, height=350, margin=dict(l=50, r=50, t=60, b=30),
            font=dict(family="Inter, sans-serif", color=BRAND["text"]), paper_bgcolor="rgba(0,0,0,0)")
        return fig
    @staticmethod
    def render_benchmark_data(data: Optional[Dict[str, Any]]):
        if not data: st.info("No hay datos de benchmark disponibles."); return
        industry_map, financial_scores = st.session_state.get(StateKey.INDUSTRY_NAMES, {}), data.get('financial_scores') or data.get('financialScores')
        if not financial_scores: st.info("No hay datos de benchmark disponibles."); return
        st.markdown(f"**Perfil de Riesgo General:** `{data.get('risk_profile', data.get('riskProfile', 'N/A'))}` | **Escala de Puntuación:** `{data.get('score_scale', data.get('scoreScale', 'N/A'))}`")
        tab_titles = [f"{industry_map.get(str(s.get('industry_code') or s.get('industryCode')), 'Indus.')} ({s.get('industry_code') or s.get('industryCode')})" for s in financial_scores]
        tabs = st.tabs(tab_titles)
        for i, score_data in enumerate(financial_scores):
            with tabs[i]:
                period = score_data.get('period') or data.get('period', {})
                company_count = float(period.get('company_count', period.get('companyCount', 5000)) or 5000)
                benchmark_info = score_data.get('benchmark', {})
                cols = st.columns(3)
                with cols[0]: render_metric_card("Riesgo Financiero", str(benchmark_info.get('risk', 'N/A')))
                with cols[1]: render_metric_card("Puntuación Benchmark", f"{float(benchmark_info.get('benchmark_score', benchmark_info.get('benchmarkScore', 0)) or 0):.2f}")
                with cols[2]: render_metric_card("Ranking Promedio", f"{float(benchmark_info.get('average_ranking', benchmark_info.get('averageRanking', 0)) or 0):.2f}")
                if (risk := benchmark_info.get('risk')) and (company_id := data.get('companyId')) is not None:
                    graph_data = {"companyId": company_id, "risk": risk, "companyCount": company_count,
                                  "benchmarkScore": float(benchmark_info.get('benchmark_score', benchmark_info.get('benchmarkScore', 0)) or 0),
                                  "averageRanking": float(benchmark_info.get('average_ranking', benchmark_info.get('averageRanking', 0)) or 0)}
                    chart_col1, chart_col2 = st.columns(2)
                    with chart_col1:
                        fig = UIComponents._create_risk_benchmark_dashboard(graph_data)
                        st.plotly_chart(fig, use_container_width=True, key=f"risk_chart_{company_id}_{i}")
                    with chart_col2:
                        if any(benchmark_info.get(k) for k in ("size", "growth", "profitability", "indebtedness")):
                            radar_fig = UIComponents._create_financial_profile_radar(benchmark_info)
                            st.plotly_chart(radar_fig, use_container_width=True, key=f"radar_chart_{company_id}_{i}")
                        else:
                            st.info("No hay datos de perfil financiero (tamaño, crecimiento, rentabilidad, endeudamiento) disponibles.")
                else: st.warning("Datos insuficientes para generar el gráfico de riesgo.")
                trend_info = score_data.get('trend', {})
                if trend_info:
                    st.markdown("##### Tendencia / Momentum")
                    profit_loss = dual_get(trend_info, 'profit_loss', 'profitLoss', {})
                    balance = trend_info.get('balance') or {}
                    cash_flow = dual_get(trend_info, 'cash_flow', 'cashFlow', {})
                    trend_cols = st.columns(4)
                    with trend_cols[0]:
                        render_trend_badge_card("Tendencia General", trend_info.get('risk'),
                                                 float(dual_get(trend_info, 'trend_score', 'trendScore', 0) or 0))
                    with trend_cols[1]:
                        render_trend_badge_card("Utilidades", profit_loss.get('risk'),
                                                 float(dual_get(profit_loss, 'profit_loss_score', 'profitLossScore', 0) or 0))
                    with trend_cols[2]:
                        render_trend_badge_card("Balance", balance.get('risk'),
                                                 float(dual_get(balance, 'balance_score', 'balanceScore', 0) or 0))
                    with trend_cols[3]:
                        render_trend_badge_card("Flujo de Caja", cash_flow.get('risk'),
                                                 float(dual_get(cash_flow, 'cash_flow_score', 'cashFlowScore', 0) or 0))
    @staticmethod
    def render_summary_charts(df: pd.DataFrame):
        st.header("Análisis Gráfico General");
        if df.empty: return
        score_col, rank_col, risk_col = 'Benchmark_Benchmarkscore', 'Benchmark_Averageranking', 'Benchmark_Risk'
        chart_font = dict(family="Inter, sans-serif", color=BRAND["text"])
        transparent_bg = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        bar_col1, bar_col2 = st.columns(2)
        with bar_col1:
            if score_col in df.columns:
                st.subheader("Comparación de Puntuación de Benchmark"); df[score_col] = pd.to_numeric(df[score_col], errors='coerce').fillna(0)
                df = df.copy()
                df['_nombre_corto'] = df['Nombre Empresa'].apply(lambda n: truncate_label(n, 22))
                num_companies = df['Nombre Empresa'].nunique()
                chart_height = max(450, 26 * num_companies + 120)
                fig_bar = px.bar(df, x=score_col, y='_nombre_corto', orientation='h',
                                  title='Puntuación General de Benchmark', color=score_col,
                                  color_continuous_scale=[BRAND["primary_light"], BRAND["primary"], BRAND["primary_dark"]],
                                  hover_name='Nombre Empresa', custom_data=['Nombre Empresa'])
                fig_bar.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>Puntuación: %{x:.2f}<extra></extra>")
                fig_bar.update_layout(font=chart_font, **transparent_bg, height=chart_height, showlegend=False,
                                       coloraxis_showscale=False, margin=dict(l=10, r=15, t=60, b=40),
                                       yaxis=dict(title="", automargin=True, categoryorder="total ascending", tickfont=dict(size=10)),
                                       xaxis=dict(title="Puntuación de Benchmark"))
                st.plotly_chart(fig_bar, use_container_width=True)
        industry_col = 'Nombre Industria'
        with bar_col2:
            if industry_col in df.columns and score_col in df.columns and df[industry_col].notna().any():
                st.subheader("Comparación por Industria")
                industry_summary = df.groupby(industry_col)[score_col].agg(Promedio='mean', Empresas='count').reset_index()
                industry_summary['_industria_corta'] = industry_summary[industry_col].apply(lambda n: truncate_label(n, 24))
                industry_summary['_label'] = industry_summary['Empresas'].apply(lambda n: f"{int(n)} emp." if n != 1 else "1 emp.")
                num_industries = len(industry_summary)
                industry_height = max(450, 42 * num_industries + 120)
                fig_industry = px.bar(industry_summary, x='Promedio', y='_industria_corta', orientation='h',
                                       title='Puntuación Promedio por Industria', color='Promedio',
                                       color_continuous_scale=[BRAND["primary_light"], BRAND["primary"], BRAND["primary_dark"]],
                                       text='_label', custom_data=[industry_col])
                fig_industry.update_traces(textposition='outside', cliponaxis=False,
                                            textfont=dict(size=9, color=BRAND["text_secondary"]),
                                            hovertemplate="<b>%{customdata[0]}</b><br>Promedio: %{x:.2f}<extra></extra>")
                fig_industry.update_layout(font=chart_font, **transparent_bg, height=industry_height, showlegend=False,
                                            coloraxis_showscale=False, margin=dict(l=10, r=45, t=60, b=40),
                                            yaxis=dict(title="", automargin=True, categoryorder="total ascending", tickfont=dict(size=10)),
                                            xaxis=dict(title="Puntuación Promedio"))
                st.plotly_chart(fig_industry, use_container_width=True)
        col1, col2 = st.columns(2)
        with col1:
            if risk_col in df.columns:
                st.subheader("Distribución de Riesgo")
                fig_pie = px.pie(df[risk_col].value_counts().reset_index(), names=risk_col, values='count',
                                  title='Perfiles de Riesgo Financiero', color=risk_col, color_discrete_map=RISK_COLORS)
                fig_pie.update_layout(font=chart_font, **transparent_bg)
                st.plotly_chart(fig_pie, use_container_width=True)
        with col2:
            if score_col in df.columns and rank_col in df.columns:
                st.subheader("Puntuación vs. Ranking"); df[rank_col] = pd.to_numeric(df[rank_col], errors='coerce').fillna(0)
                fig_scatter = px.scatter(df, x=score_col, y=rank_col, hover_name='Nombre Empresa',
                                          title='Relación Puntuación vs. Ranking', color_discrete_sequence=[BRAND["primary"]])
                fig_scatter.update_traces(marker=dict(size=10, opacity=0.85, line=dict(width=1, color=BRAND["primary_dark"])))
                fig_scatter.update_layout(font=chart_font, **transparent_bg, showlegend=False)
                st.plotly_chart(fig_scatter, use_container_width=True)
        if industry_col in df.columns and risk_col in df.columns and score_col in df.columns:
            st.subheader("Mapa de Riesgo por Industria")
            df_tree = df.copy()
            df_tree['_industria_corta'] = df_tree[industry_col].apply(lambda n: truncate_label(n, 30))
            df_tree['_empresa_corta'] = df_tree['Nombre Empresa'].apply(lambda n: truncate_label(n, 22))
            df_tree['_tamano'] = pd.to_numeric(df_tree[score_col], errors='coerce').fillna(0).clip(lower=1)
            df_tree['_riesgo'] = df_tree[risk_col].fillna('N/A')
            fig_tree = px.treemap(df_tree, path=[px.Constant("Todas las Industrias"), '_industria_corta', '_empresa_corta'],
                                   values='_tamano', color='_riesgo', color_discrete_map={**RISK_COLORS, 'N/A': '#D9D5D2', '(?)': BRAND["bg_page"]},
                                   custom_data=['Nombre Empresa', score_col, '_riesgo'])
            fig_tree.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>Riesgo: %{customdata[2]}<br>Puntuación: %{customdata[1]:.2f}<extra></extra>",
                                    textfont=dict(size=12, family="Inter, sans-serif"), marker=dict(line=dict(width=1.5, color="white")))
            fig_tree.update_layout(font=chart_font, **transparent_bg, height=550, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig_tree, use_container_width=True)
            legend_html = " &nbsp; ".join(
                f"<span style='display:inline-flex;align-items:center;gap:5px;font-size:0.8rem;color:{BRAND['text_secondary']};'>"
                f"<span style='width:10px;height:10px;border-radius:3px;background:{RISK_COLORS[r]};display:inline-block;'></span>{r} — {RISK_DESCRIPTIONS[r]}</span>"
                for r in ["A", "B", "C", "D", "E"])
            st.markdown(f"<div style='text-align:center; margin-top:-0.5rem;'>{legend_html}</div>", unsafe_allow_html=True)
            st.caption("El tamaño de cada bloque representa la puntuación de benchmark; el color, la categoría de riesgo.")

class EMISDashboardApp:
    PAGE_SIZE = 10
    def __init__(self): SessionManager.initialize()
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
            if not benchmark_data or not (financial_scores := benchmark_data.get('financial_scores') or benchmark_data.get('financialScores')) or not company_info: continue
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
        apply_custom_theme()
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
                excel_filename = f"emis_benchmarks_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
                
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button("Descargar Reporte", output.getvalue(), excel_filename, 
                                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', type="primary")
                with col2:
                    with st.expander("✉️ Enviar Reporte"):
                        email_input = st.text_input("Correos (separados por coma o espacio)", placeholder="ejemplo1@mail.com, ejemplo2@mail.com")
                        if st.button("Enviar Reporte"):
                            if email_input:
                                recipients = [email.strip() for email in re.split(r'[, ]+', email_input) if email.strip()]
                                valid_emails = [email for email in recipients if re.match(r"[^@]+@[^@]+\.[^@]+", email)]
                                if len(valid_emails) != len(recipients):
                                    st.warning("Algunos correos no parecen válidos. Por favor, revísalos.")
                                else:
                                    with st.spinner(f"Enviando reporte a {len(valid_emails)} destinatario(s)..."):
                                        if EmailService.send_report(valid_emails, output, excel_filename):
                                            st.success("¡Reporte enviado exitosamente!")
                                        # Los mensajes de error se manejan dentro de EmailService
                            else:
                                st.warning("Por favor, introduce al menos un correo electrónico.")
            
            current_page = st.session_state[StateKey.CURRENT_PAGE]
            start_idx, end_idx = (current_page - 1) * self.PAGE_SIZE, current_page * self.PAGE_SIZE
            for result in results[start_idx:end_idx]:
                UIComponents.render_company_info(result.get("company_info"))
                UIComponents.render_benchmark_data(result.get("benchmark_data"))
                st.divider()

            UIComponents.render_pagination_controls(len(results), self.PAGE_SIZE, key_prefix="bottom")
            if not df_for_excel.empty:
                st.divider(); UIComponents.render_summary_charts(df_for_excel)

    def _handle_search(self, params: SearchParams):
        SessionManager.reset_search()
        service, local_benchmarks = st.session_state[StateKey.EMIS_SERVICE], st.session_state[StateKey.LOCAL_BENCHMARKS]
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
                    all_results.append({"company_info": company_info, "benchmark_data": service.get_company_benchmark(company_info.id)})
        progress_bar.empty()
        st.session_state[StateKey.SEARCH_RESULTS] = all_results
        st.rerun()

if __name__ == "__main__":
    app = EMISDashboardApp()
    app.run()