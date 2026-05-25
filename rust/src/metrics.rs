/// 计算对数收益率序列
pub fn log_returns(prices: &[f64]) -> Vec<f64> {
    if prices.len() < 2 {
        return vec![];
    }
    prices
        .windows(2)
        .map(|w| (w[1] / w[0]).ln())
        .collect()
}

/// 计算简单收益率序列
pub fn simple_returns(prices: &[f64]) -> Vec<f64> {
    if prices.len() < 2 {
        return vec![];
    }
    prices
        .windows(2)
        .map(|w| (w[1] - w[0]) / w[0])
        .collect()
}

/// 计算年化收益率
/// `returns` 为周期收益率
/// `periods_per_year` 例如日线=252, 月线=12
pub fn annualized_return(returns: &[f64], periods_per_year: f64) -> f64 {
    if returns.is_empty() {
        return 0.0;
    }
    let total = returns.iter().map(|r| (1.0 + r).ln()).sum::<f64>();
    let geometric_mean = (total / returns.len() as f64).exp();
    geometric_mean.powf(periods_per_year) - 1.0
}

/// 计算年化波动率
pub fn annualized_volatility(returns: &[f64], periods_per_year: f64) -> f64 {
    if returns.len() < 2 {
        return 0.0;
    }
    let m = returns.iter().sum::<f64>() / returns.len() as f64;
    let variance = returns.iter().map(|r| (r - m).powi(2)).sum::<f64>() / (returns.len() - 1) as f64;
    variance.sqrt() * periods_per_year.sqrt()
}

/// 计算夏普比率
pub fn sharpe_ratio(returns: &[f64], risk_free_rate: f64, periods_per_year: f64) -> f64 {
    if returns.len() < 2 {
        return 0.0;
    }
    let excess = annualized_return(returns, periods_per_year) - risk_free_rate;
    let vol = annualized_volatility(returns, periods_per_year);
    if vol == 0.0 {
        return 0.0;
    }
    excess / vol
}

/// 计算索提诺比率 (Sortino Ratio)
/// 仅用下行标准差
pub fn sortino_ratio(returns: &[f64], risk_free_rate: f64, periods_per_year: f64) -> f64 {
    if returns.len() < 2 {
        return 0.0;
    }
    let excess = annualized_return(returns, periods_per_year) - risk_free_rate;

    // 下行方差（只计负收益的平方和）
    let m = returns.iter().sum::<f64>() / returns.len() as f64;
    let downside_var: f64 = returns
        .iter()
        .map(|r| {
            let d = r - m;
            if d < 0.0 { d.powi(2) } else { 0.0 }
        })
        .sum::<f64>()
        / (returns.len() - 1) as f64;
    let downside_vol = downside_var.sqrt() * periods_per_year.sqrt();
    if downside_vol == 0.0 {
        return 0.0;
    }
    excess / downside_vol
}

/// 计算最大回撤
/// `equity_curve` 为权益曲线（每期净值）
/// 返回 (max_drawdown_pct, peak_index, trough_index)
pub fn max_drawdown(equity_curve: &[f64]) -> (f64, usize, usize) {
    if equity_curve.len() < 2 {
        return (0.0, 0, 0);
    }

    let mut peak = equity_curve[0];
    let mut peak_idx = 0usize;
    let mut max_dd = 0.0f64;
    let mut dd_start = 0usize;
    let mut dd_end = 0usize;

    for (i, &val) in equity_curve.iter().enumerate() {
        if val > peak {
            peak = val;
            peak_idx = i;
        }
        let dd = (peak - val) / peak;
        if dd > max_dd {
            max_dd = dd;
            dd_start = peak_idx;
            dd_end = i;
        }
    }

    (max_dd, dd_start, dd_end)
}

/// 计算 Calmar 比率
pub fn calmar_ratio(returns: &[f64], equity_curve: &[f64], periods_per_year: f64) -> f64 {
    let ann_ret = annualized_return(returns, periods_per_year);
    let (mdd, _, _) = max_drawdown(equity_curve);
    if mdd == 0.0 {
        return 0.0;
    }
    ann_ret / mdd
}

/// 计算胜率
pub fn win_rate(trades: &[f64]) -> f64 {
    if trades.is_empty() {
        return 0.0;
    }
    let wins = trades.iter().filter(|&&p| p > 0.0).count() as f64;
    wins / trades.len() as f64
}

/// 计算盈亏比 (Profit Factor)
/// `trades` 为每笔交易的 P&L
pub fn profit_factor(trades: &[f64]) -> f64 {
    let gross_profit: f64 = trades.iter().filter(|&&p| p > 0.0).sum();
    let gross_loss: f64 = trades.iter().filter(|&&p| p < 0.0).map(|p| p.abs()).sum();
    if gross_loss == 0.0 {
        return if gross_profit > 0.0 { f64::INFINITY } else { 0.0 };
    }
    gross_profit / gross_loss
}

/// 从权益曲线计算累计收益
pub fn cumulative_return(equity_curve: &[f64]) -> f64 {
    if equity_curve.len() < 2 {
        return 0.0;
    }
    (equity_curve[equity_curve.len() - 1] - equity_curve[0]) / equity_curve[0]
}