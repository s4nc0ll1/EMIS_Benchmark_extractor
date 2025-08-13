from benchmark_visualization import create_risk_benchmark_dashboard

print("hello world")
sample_company_data = {
    'companyId': 8162520,
    'benchmarkScore': 42.7,
    'averageRanking': 3052,
    'risk': 'A',
    'companyCount': 5322
}
fig = create_risk_benchmark_dashboard(sample_company_data)
fig.show()
