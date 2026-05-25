/// 计算算术平均值
pub fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    values.iter().sum::<f64>() / values.len() as f64
}

/// 计算总体方差
pub fn variance(values: &[f64]) -> f64 {
    if values.len() < 2 {
        return 0.0;
    }
    let m = mean(values);
    values.iter().map(|x| (x - m).powi(2)).sum::<f64>() / (values.len() - 1) as f64
}

/// 计算标准差
pub fn std_dev(values: &[f64]) -> f64 {
    variance(values).sqrt()
}

/// 计算协方差矩阵 (N x N)
/// `returns` 为二维切片: M 行（时间序列），N 列（资产）
pub fn covariance_matrix(returns: &[Vec<f64>]) -> Vec<Vec<f64>> {
    let n_assets = if returns.is_empty() { 0 } else { returns[0].len() };
    if n_assets == 0 {
        return vec![];
    }

    let n_rows = returns.len();
    // 每种资产的均值
    let means: Vec<f64> = (0..n_assets)
        .map(|j| mean(&returns.iter().map(|row| row[j]).collect::<Vec<_>>()))
        .collect();

    let mut cov = vec![vec![0.0; n_assets]; n_assets];
    for i in 0..n_assets {
        for j in 0..n_assets {
            let c = returns
                .iter()
                .map(|row| (row[i] - means[i]) * (row[j] - means[j]))
                .sum::<f64>()
                / (n_rows - 1) as f64;
            cov[i][j] = c;
        }
    }
    cov
}

/// 计算协方差矩阵 — 从单列收益率序列（列式存储）
pub fn covariance_from_cols(returns: &[Vec<f64>]) -> Vec<Vec<f64>> {
    covariance_matrix(returns)
}

/// 计算偏度 (Skewness)
pub fn skewness(values: &[f64]) -> f64 {
    let n = values.len() as f64;
    if n < 3.0 {
        return 0.0;
    }
    let m = mean(values);
    let s = std_dev(values);
    if s == 0.0 {
        return 0.0;
    }
    let m3 = values.iter().map(|x| (x - m).powi(3)).sum::<f64>() / n;
    m3 / s.powi(3) * (n * (n - 1.0)).sqrt() / (n - 2.0)
}

/// 计算峰度 (Excess Kurtosis)
pub fn kurtosis(values: &[f64]) -> f64 {
    let n = values.len() as f64;
    if n < 4.0 {
        return 0.0;
    }
    let m = mean(values);
    let m4 = values.iter().map(|x| (x - m).powi(4)).sum::<f64>() / n;
    let s2 = variance(values);
    if s2 == 0.0 {
        return 0.0;
    }
    (n * (n + 1.0) / ((n - 1.0) * (n - 2.0) * (n - 3.0))) * (m4 / s2.powi(2))
        - 3.0 * (n - 1.0).powi(2) / ((n - 2.0) * (n - 3.0))
}