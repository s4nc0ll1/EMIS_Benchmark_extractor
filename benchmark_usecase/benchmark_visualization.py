import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
def create_risk_benchmark_dashboard(company_data):
    """
    Args:
    
        company_data (dict): Diccionario con datos de la empresa
            - companyId: ID de la empresa
            - benchmarkScore: Score del benchmark
            - averageRanking: Ranking promedio
            - risk: Letra de riesgo (A, B, C, D)
            - companyCount: Total de empresas (opcional, default 5000)
    """
   
    # Valores por defecto
    company_count = company_data.get('companyCount', 5000)
   
    # Configuración de colores
    colors_active = {
        'A': '#2E8B57',  # Verde oscuro - Excelente
        'B': '#32CD32',  # Verde lima - Bueno
        'C': '#FFD700',  # Dorado - Regular
        'D': '#FF4500',   # Naranja rojizo - Malo
        'E': '#FF0000'   # Naranja Diablo - re-Malo
    }
   
    color_inactive = '#D3D3D3'  # Gris claro para barras inactivas
   
    # Definir las categorías de riesgo y sus descripciones
    risk_categories = ['A', 'B', 'C', 'D', 'E']
    risk_descriptions = {
        'A': 'Riesgo Muy Bajo - Excelente situación financiera',
        'B': 'Riesgo Bajo - Buena situación financiera',
        'C': 'Riesgo Medio - Situación financiera regular',
        'D': 'Riesgo Alto - Situación financiera preocupante',
        'E': 'Riesgo Muy Alto - Situación financiera Deplorable'
    }
   
    # Crear la figura
    fig = go.Figure()
   
    # Altura uniforme para todas las barras
    bar_height = 100
   
    # Crear las barras
    for risk in risk_categories:
        # Determinar si esta barra debe estar activa
        is_active = (risk == company_data['risk'])
       
        # Color de la barra
        bar_color = colors_active[risk] if is_active else color_inactive
       
        # Texto en la barra
        bar_text = f"<b>{risk}</b>" if is_active else risk
       
        # Información para el hover
        if is_active:
            hover_text = (
                f"<b>Categoría de Riesgo: {risk}</b><br>"
                f"{risk_descriptions[risk]}<br><br>"
                f"<b>Su Empresa:</b><br>"
                f"• ID: {company_data['companyId']}<br>"
                f"• Score: {company_data['benchmarkScore']:.1f}<br>"
                f"• Ranking: {company_data['averageRanking']:.0f} de {company_count}<br>"
                f"• Percentil: {((company_count - company_data['averageRanking']) / company_count * 100):.1f}%"
            )
        else:
            hover_text = (
                f"<b>Categoría de Riesgo: {risk}</b><br>"
                f"{risk_descriptions[risk]}<br><br>"
                f"<i>Su empresa no está en esta categoría</i>"
            )
       
        # Agregar la barra
        fig.add_trace(go.Bar(
            name=risk,
            x=[risk],
            y=[bar_height],
            marker_color=bar_color,
            marker_line_color='white',
            marker_line_width=2,
            # text=[bar_text],
            textposition='inside',
            textfont=dict(size=16, color='white' if is_active else '#666666'),
            hovertemplate=hover_text + '<extra></extra>',
            showlegend=False
        ))
   
    # Personalizar el layout
    fig.update_layout(
        title={
            'text': f"<b>Clasificación de Riesgo Financiero</b><br>" +
                   f"<span style='font-size:16px'>Empresa ID: {company_data['companyId']} - " +
                   f"Categoría: <span style='color:{colors_active[company_data['risk']]}'><b>{company_data['risk']}</b></span></span>",
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 20}
        },
        xaxis_title="<b>Categorías de Riesgo</b>",
        yaxis_title="",  # Sin label en el eje Y como solicitaste
        yaxis=dict(
            showticklabels=False,  # Ocultar números del eje Y
            showgrid=False,        # Sin líneas de cuadrícula
            zeroline=False         # Sin línea de cero
        ),
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=14)
        ),
        height=500,
        template="plotly_white",
        plot_bgcolor='rgba(0,0,0,0)',
        hovermode='x'
    )
   
    return fig
