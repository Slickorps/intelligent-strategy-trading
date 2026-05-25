mod aggregator;
mod metrics;
mod stats;

use ndarray::Array2;
use numpy::{IntoPyArray, PyArray2};
use pyo3::prelude::*;

/// Rust 高性能数据处理引擎
#[pymodule]
fn _rust_engine(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    // ---- 统计函数 ----
    #[pyfn(m)]
    fn rust_mean(values: Vec<f64>) -> f64 {
        stats::mean(&values)
    }

    #[pyfn(m)]
    fn rust_variance(values: Vec<f64>) -> f64 {
        stats::variance(&values)
    }

    #[pyfn(m)]
    fn rust_std_dev(values: Vec<f64>) -> f64 {
        stats::std_dev(&values)
    }

    #[pyfn(m)]
    fn rust_skewness(values: Vec<f64>) -> f64 {
        stats::skewness(&values)
    }

    #[pyfn(m)]
    fn rust_kurtosis(values: Vec<f64>) -> f64 {
        stats::kurtosis(&values)
    }

    #[pyfn(m)]
    fn rust_covariance_matrix<'py>(
        py: Python<'py>,
        returns: Vec<Vec<f64>>,
    ) -> Bound<'py, PyArray2<f64>> {
        let cov = stats::covariance_matrix(&returns);
        let n = cov.len();
        let mut flat = Vec::with_capacity(n * n);
        for row in &cov {
            flat.extend_from_slice(row);
        }
        Array2::from_shape_vec((n, n), flat)
            .unwrap()
            .into_pyarray(py)
    }

    // ---- 金融指标 ----
    #[pyfn(m)]
    fn rust_sharpe_ratio(returns: Vec<f64>, risk_free_rate: f64, periods_per_year: f64) -> f64 {
        metrics::sharpe_ratio(&returns, risk_free_rate, periods_per_year)
    }

    #[pyfn(m)]
    fn rust_sortino_ratio(returns: Vec<f64>, risk_free_rate: f64, periods_per_year: f64) -> f64 {
        metrics::sortino_ratio(&returns, risk_free_rate, periods_per_year)
    }

    #[pyfn(m)]
    fn rust_max_drawdown(equity_curve: Vec<f64>) -> (f64, usize, usize) {
        metrics::max_drawdown(&equity_curve)
    }

    #[pyfn(m)]
    fn rust_calmar_ratio(
        returns: Vec<f64>,
        equity_curve: Vec<f64>,
        periods_per_year: f64,
    ) -> f64 {
        metrics::calmar_ratio(&returns, &equity_curve, periods_per_year)
    }

    #[pyfn(m)]
    fn rust_annualized_return(returns: Vec<f64>, periods_per_year: f64) -> f64 {
        metrics::annualized_return(&returns, periods_per_year)
    }

    #[pyfn(m)]
    fn rust_annualized_volatility(returns: Vec<f64>, periods_per_year: f64) -> f64 {
        metrics::annualized_volatility(&returns, periods_per_year)
    }

    #[pyfn(m)]
    fn rust_win_rate(trades: Vec<f64>) -> f64 {
        metrics::win_rate(&trades)
    }

    #[pyfn(m)]
    fn rust_profit_factor(trades: Vec<f64>) -> f64 {
        metrics::profit_factor(&trades)
    }

    #[pyfn(m)]
    fn rust_log_returns(prices: Vec<f64>) -> Vec<f64> {
        metrics::log_returns(&prices)
    }

    #[pyfn(m)]
    fn rust_simple_returns(prices: Vec<f64>) -> Vec<f64> {
        metrics::simple_returns(&prices)
    }

    Ok(())
}