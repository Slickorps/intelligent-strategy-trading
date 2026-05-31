-- ============================================================================
-- Intelligent Strategy Trading — Analysis Queries
-- ============================================================================
-- Complex SQL queries for trading performance analysis, risk decomposition,
-- and factor exposure analysis.
-- Compatible with PostgreSQL 14+.
-- ============================================================================

-- ============================================================================
-- 1. 按月收益率透视 (Monthly Return Pivot)
-- ============================================================================
-- 按策略、年份、月份透视月度收益率，便于跨期对比

CREATE OR REPLACE FUNCTION get_monthly_returns_pivot(
    p_strategy_id UUID DEFAULT NULL,
    p_start_date DATE DEFAULT '2020-01-01',
    p_end_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    strategy_name       VARCHAR(100),
    year_month          VARCHAR(7),
    year_num            INTEGER,
    month_num           INTEGER,
    trades_in_month     BIGINT,
    gross_return        DECIMAL(15, 6),
    net_return          DECIMAL(15, 6),
    win_rate_month      DECIMAL(6, 4),
    avg_return_per_trade DECIMAL(15, 6),
    monthly_pnl         DECIMAL(15, 6)
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH monthly_stats AS (
        SELECT
            s.name,
            EXTRACT(YEAR FROM t.exit_time)::INTEGER AS yr,
            EXTRACT(MONTH FROM t.exit_time)::INTEGER AS mon,
            TO_CHAR(t.exit_time, 'YYYY-MM') AS ym,
            COUNT(t.id)::BIGINT AS trade_count,
            SUM(t.profit_loss_percent) AS gross_ret,
            SUM(t.profit_loss_percent) - SUM(t.fees) / NULLIF(SUM(t.quantity * t.entry_price), 0) * 100 AS net_ret,
            ROUND(
                COUNT(CASE WHEN t.profit_loss > 0 THEN 1 END)::DECIMAL
                / NULLIF(COUNT(*), 0),
                4
            ) AS wr,
            AVG(t.profit_loss_percent) AS avg_ret,
            SUM(t.profit_loss) AS total_pnl
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE t.status = 'CLOSED'
          AND t.exit_time BETWEEN p_start_date AND p_end_date
          AND (p_strategy_id IS NULL OR t.strategy_id = p_strategy_id)
        GROUP BY s.name, yr, mon, ym
    )
    SELECT
        ms.name,
        ms.ym,
        ms.yr,
        ms.mon,
        ms.trade_count,
        ROUND(ms.gross_ret, 4),
        ROUND(ms.net_ret, 4),
        ms.wr,
        ROUND(ms.avg_ret, 6),
        ROUND(ms.total_pnl, 4)
    FROM monthly_stats ms
    ORDER BY ms.name, ms.yr, ms.mon;
END;
$$;

COMMENT ON FUNCTION get_monthly_returns_pivot IS
    'Monthly return pivot table with win rate and PnL breakdown per strategy';

-- 使用示例:
-- SELECT * FROM get_monthly_returns_pivot(NULL, '2023-01-01', '2024-12-31');
-- 可接 PIVOT 客户端处理，或在 psql 中用 crosstab() 转置


-- ============================================================================
-- 2. 因子暴露分析 (Factor Exposure Analysis)
-- ============================================================================
-- 分析策略在不同市场因子上的暴露程度及其对收益的贡献

CREATE OR REPLACE FUNCTION get_factor_exposure_analysis(
    p_strategy_id UUID DEFAULT NULL,
    p_factor_window INTEGER DEFAULT 21  -- 滚动窗口天数
)
RETURNS TABLE (
    strategy_name       VARCHAR(100),
    factor_name         VARCHAR(50),
    exposure_beta       DECIMAL(10, 4),
    exposure_t_stat     DECIMAL(10, 4),
    exposure_p_value    DECIMAL(10, 4),
    contribution_return DECIMAL(10, 4),
    contribution_risk   DECIMAL(10, 4),
    is_significant      BOOLEAN,
    rolling_correlation DECIMAL(6, 4)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_min_date DATE;
    v_max_date DATE;
    v_total_return DECIMAL(15, 6);
BEGIN
    -- 计算日期范围
    SELECT
        MIN(t.exit_time::DATE),
        MAX(t.exit_time::DATE)
    INTO v_min_date, v_max_date
    FROM trades t
    WHERE t.status = 'CLOSED'
      AND (p_strategy_id IS NULL OR t.strategy_id = p_strategy_id);

    -- 创建临时表存储策略日收益率
    CREATE TEMP TABLE _strategy_returns ON COMMIT DROP AS
    SELECT
        s.name,
        t.exit_time::DATE AS trade_date,
        SUM(t.profit_loss_percent) AS daily_return
    FROM trades t
    JOIN strategies s ON t.strategy_id = s.id
    WHERE t.status = 'CLOSED'
      AND t.exit_time IS NOT NULL
      AND (p_strategy_id IS NULL OR t.strategy_id = p_strategy_id)
    GROUP BY s.name, t.exit_time::DATE;

    -- 因子定义（模拟因子收益，实际应从外部数据源获取）
    CREATE TEMP TABLE _factor_returns ON COMMIT DROP AS
    SELECT
        sr.trade_date,
        sr.name,
        -- 市场因子 (Market): 简单等权市场组合代理
        AVG(sr.daily_return) OVER (PARTITION BY sr.trade_date) AS market_factor,
        -- 动量因子 (Momentum): 过去21天收益率
        AVG(sr.daily_return) OVER (
            PARTITION BY sr.name
            ORDER BY sr.trade_date
            ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING
        ) AS momentum_factor,
        -- 波动率因子 (Volatility): 过去21天收益率标准差
        STDDEV(sr.daily_return) OVER (
            PARTITION BY sr.name
            ORDER BY sr.trade_date
            ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING
        ) AS volatility_factor,
        -- 规模因子 (Size): 交易量对数值的代理
        LN(COUNT(*) OVER (
            PARTITION BY sr.name, sr.trade_date
        ) + 1) AS size_factor
    FROM _strategy_returns sr;

    -- 汇总结果：滚动回归拟合 beta
    RETURN QUERY
    WITH factor_exposures AS (
        SELECT
            fr.name,
            'Market'::VARCHAR(50) AS factor,
            -- 用简单回归估计 beta
            REGR_SLOPE(fr.daily_return, fr.market_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            ) AS beta,
            REGR_R2(fr.daily_return, fr.market_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            ) AS r2,
            CORR(fr.daily_return, fr.market_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            ) AS rolling_corr
        FROM _factor_returns fr
        WHERE fr.market_factor IS NOT NULL

        UNION ALL

        SELECT
            fr.name,
            'Momentum',
            REGR_SLOPE(fr.daily_return, fr.momentum_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            ),
            REGR_R2(fr.daily_return, fr.momentum_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            ),
            CORR(fr.daily_return, fr.momentum_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            )
        FROM _factor_returns fr
        WHERE fr.momentum_factor IS NOT NULL

        UNION ALL

        SELECT
            fr.name,
            'Volatility',
            REGR_SLOPE(fr.daily_return, fr.volatility_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            ),
            REGR_R2(fr.daily_return, fr.volatility_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            ),
            CORR(fr.daily_return, fr.volatility_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            )
        FROM _factor_returns fr
        WHERE fr.volatility_factor IS NOT NULL

        UNION ALL

        SELECT
            fr.name,
            'Size',
            REGR_SLOPE(fr.daily_return, fr.size_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            ),
            REGR_R2(fr.daily_return, fr.size_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            ),
            CORR(fr.daily_return, fr.size_factor) OVER (
                PARTITION BY fr.name
                ORDER BY fr.trade_date
                ROWS BETWEEN p_factor_window PRECEDING AND CURRENT ROW
            )
        FROM _factor_returns fr
        WHERE fr.size_factor IS NOT NULL
    )
    SELECT
        fe.name,
        fe.factor,
        ROUND(AVG(fe.beta), 4) AS exposure_beta,
        ROUND(AVG(fe.beta) / NULLIF(STDDEV(fe.beta), 0), 4) AS t_stat,
        -- 近似 p-value (双尾 t 检验, df≈窗口-2)
        ROUND(
            2 * (1 - REGR_SLOPE(fe.beta, fe.r2) / NULLIF(STDDEV(fe.beta), 0)),
            4
        ) AS p_value_approx,
        ROUND(AVG(fe.r2) * 100, 4) AS contribution_return,
        ROUND(STDDEV(fe.beta) * 100, 4) AS contribution_risk,
        ABS(AVG(fe.beta) / NULLIF(STDDEV(fe.beta), 0)) > 2.0 AS is_significant,
        ROUND(AVG(fe.rolling_corr), 4) AS rolling_correlation
    FROM factor_exposures fe
    GROUP BY fe.name, fe.factor
    ORDER BY fe.name, ABS(AVG(fe.beta)) DESC;
END;
$$;

COMMENT ON FUNCTION get_factor_exposure_analysis IS
    'Multi-factor exposure analysis with rolling regression beta estimates';

-- 使用示例:
-- SELECT * FROM get_factor_exposure_analysis(NULL, 21);


-- ============================================================================
-- 3. 最大回撤区间检测 (Maximum Drawdown Detection)
-- ============================================================================
-- 识别历史最大回撤区间，包含持续时间、恢复时间和峰值谷值

CREATE OR REPLACE FUNCTION get_max_drawdown_periods(
    p_strategy_id UUID DEFAULT NULL,
    p_top_n INTEGER DEFAULT 5,
    p_min_drawdown_pct DECIMAL(5, 2) DEFAULT 1.0  -- 最小回撤百分比阈值
)
RETURNS TABLE (
    strategy_name           VARCHAR(100),
    peak_date               DATE,
    valley_date             DATE,
    recovery_date           DATE,
    drawdown_pct            DECIMAL(10, 4),
    drawdown_amount         DECIMAL(15, 6),
    duration_days           INTEGER,
    recovery_days           INTEGER,
    is_active               BOOLEAN,
    severity_rank           INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH daily_pnl AS (
        -- 计算每日累计PnL
        SELECT
            s.name,
            t.exit_time::DATE AS trade_date,
            SUM(t.profit_loss) AS daily_pnl
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE t.status = 'CLOSED'
          AND t.exit_time IS NOT NULL
          AND (p_strategy_id IS NULL OR t.strategy_id = p_strategy_id)
        GROUP BY s.name, t.exit_time::DATE
    ),
    cumulative AS (
        -- 计算累计收益和滚动峰值
        SELECT
            name,
            trade_date,
            daily_pnl,
            SUM(daily_pnl) OVER (
                PARTITION BY name
                ORDER BY trade_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS cum_pnl,
            MAX(SUM(daily_pnl)) OVER (
                PARTITION BY name
                ORDER BY trade_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS peak_pnl
        FROM daily_pnl
        GROUP BY name, trade_date, daily_pnl
    ),
    drawdowns AS (
        SELECT
            name,
            trade_date,
            cum_pnl,
            peak_pnl,
            -- 回撤 = (峰值 - 当前值) / |峰值|
            CASE
                WHEN peak_pnl = 0 THEN 0
                ELSE (peak_pnl - cum_pnl) / NULLIF(ABS(peak_pnl), 0) * 100
            END AS drawdown_pct,
            (peak_pnl - cum_pnl) AS drawdown_amount
        FROM cumulative
    ),
    drawdown_regions AS (
        -- 标记连续回撤区间
        SELECT
            name,
            trade_date,
            drawdown_pct,
            drawdown_amount,
            CASE
                WHEN drawdown_pct > 0
                     AND LAG(drawdown_pct, 1, 0) OVER (PARTITION BY name ORDER BY trade_date) <= 0
                THEN trade_date
                ELSE NULL
            END AS peak_date_mark,
            CASE
                WHEN drawdown_pct <= 0
                     AND LAG(drawdown_pct, 1, 0) OVER (PARTITION BY name ORDER BY trade_date) > 0
                THEN trade_date
                ELSE NULL
            END AS recovery_date_mark
        FROM drawdowns
        WHERE drawdown_pct > p_min_drawdown_pct
    ),
    dd_ranges AS (
        SELECT
            name,
            MAX(peak_date_mark) OVER (
                PARTITION BY name
                ORDER BY trade_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS peak_date,
            trade_date AS valley_date,
            MAX(recovery_date_mark) OVER (
                PARTITION BY name
                ORDER BY trade_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS recovery_date_mark,
            drawdown_pct,
            drawdown_amount
        FROM drawdown_regions
        WHERE drawdown_pct IS NOT NULL
    ),
    dd_consolidated AS (
        SELECT
            name,
            peak_date,
            valley_date,
            MAX(drawdown_pct) AS max_dd_pct,
            MAX(drawdown_amount) AS max_dd_amount,
            -- 如果 recovery_date_mark 存在则使用，否则标记为活跃回撤
            CASE
                WHEN MAX(recovery_date_mark) OVER (
                    PARTITION BY name, peak_date
                ) IS NOT NULL
                THEN MAX(recovery_date_mark) OVER (
                    PARTITION BY name, peak_date
                )
                ELSE NULL
            END AS recovery_date_inner,
            CASE
                WHEN MAX(recovery_date_mark) OVER (
                    PARTITION BY name, peak_date
                ) IS NULL
                THEN TRUE
                ELSE FALSE
            END AS active_dd
        FROM dd_ranges
        WHERE peak_date IS NOT NULL
        GROUP BY name, peak_date, valley_date, drawdown_pct, drawdown_amount
    )
    SELECT
        dd.name,
        dd.peak_date,
        dd.valley_date,
        dd.recovery_date_inner AS recovery_date,
        ROUND(dd.max_dd_pct, 4),
        ROUND(dd.max_dd_amount, 4),
        (dd.valley_date - dd.peak_date)::INTEGER AS duration_days,
        CASE
            WHEN dd.recovery_date_inner IS NOT NULL
            THEN (dd.recovery_date_inner - dd.valley_date)::INTEGER
            ELSE NULL
        END AS recovery_days,
        dd.active_dd,
        ROW_NUMBER() OVER (
            PARTITION BY dd.name
            ORDER BY dd.max_dd_pct DESC
        )::INTEGER AS severity_rank
    FROM dd_consolidated dd
    WHERE dd.max_dd_pct > p_min_drawdown_pct
    ORDER BY dd.name, dd.max_dd_pct DESC
    LIMIT p_top_n;
END;
$$;

COMMENT ON FUNCTION get_max_drawdown_periods IS
    'Detect and rank maximum drawdown periods with peak/valley/recovery dates';

-- 使用示例:
-- SELECT * FROM get_max_drawdown_periods(NULL, 10, 2.0);


-- ============================================================================
-- 4. 策略相关性矩阵 (Strategy Correlation Matrix)
-- ============================================================================
-- 计算多策略之间的日收益率相关性，用于组合分散化分析

CREATE OR REPLACE FUNCTION get_strategy_correlation_matrix(
    p_start_date DATE DEFAULT '2023-01-01',
    p_end_date DATE DEFAULT CURRENT_DATE,
    p_min_overlap_days INTEGER DEFAULT 30  -- 最小重叠交易日数
)
RETURNS TABLE (
    strategy_a          VARCHAR(100),
    strategy_b          VARCHAR(100),
    overlapping_days    INTEGER,
    pearson_r           DECIMAL(10, 6),
    spearman_rho        DECIMAL(10, 6),
    covariance          DECIMAL(15, 6),
    beta_ab             DECIMAL(10, 4),
    diversification_score DECIMAL(10, 4)
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH daily_returns AS (
        -- 计算各策略的日收益率时间序列
        SELECT
            s.name,
            t.exit_time::DATE AS trade_date,
            SUM(t.profit_loss_percent) AS daily_ret
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE t.status = 'CLOSED'
          AND t.exit_time BETWEEN p_start_date AND p_end_date
        GROUP BY s.name, t.exit_time::DATE
    ),
    paired_returns AS (
        -- 构建配对收益率
        SELECT
            a.name AS strategy_a,
            b.name AS strategy_b,
            a.trade_date,
            a.daily_ret AS ret_a,
            b.daily_ret AS ret_b
        FROM daily_returns a
        JOIN daily_returns b
            ON a.trade_date = b.trade_date
            AND a.name < b.name  -- 避免重复配对
    ),
    stats AS (
        SELECT
            strategy_a,
            strategy_b,
            COUNT(*) AS n_days,
            CORR(ret_a, ret_b) AS pearson,
            -- Spearman rank correlation (近似)
            CORR(
                RANK() OVER (PARTITION BY strategy_a, strategy_b ORDER BY ret_a),
                RANK() OVER (PARTITION BY strategy_a, strategy_b ORDER BY ret_b)
            ) AS spearman,
            COVAR_SAMP(ret_a, ret_b) AS cov,
            REGR_SLOPE(ret_b, ret_a) AS beta
        FROM paired_returns
        GROUP BY strategy_a, strategy_b
        HAVING COUNT(*) >= p_min_overlap_days
    )
    SELECT
        s.strategy_a,
        s.strategy_b,
        s.n_days,
        ROUND(s.pearson, 6),
        ROUND(s.spearman, 6),
        ROUND(s.cov, 6),
        ROUND(s.beta, 4),
        -- 分散化评分: 1 - |相关系数|，越高越分散
        ROUND(1 - ABS(COALESCE(s.pearson, 0)), 4) AS diversification_score
    FROM stats s
    ORDER BY s.strategy_a, s.n_days DESC;
END;
$$;

COMMENT ON FUNCTION get_strategy_correlation_matrix IS
    'Cross-strategy correlation matrix with Pearson, Spearman, and diversification scoring';

-- 使用示例:
-- SELECT * FROM get_strategy_correlation_matrix('2023-01-01', '2024-12-31', 20);


-- ============================================================================
-- 5. 交易行为分析 (Trading Behavior Analysis)
-- ============================================================================
-- 分析交易行为模式，包括持有时间分布、最佳/最差交易时段、滑点分析

CREATE OR REPLACE FUNCTION get_trading_behavior_analysis(
    p_strategy_id UUID DEFAULT NULL,
    p_year INTEGER DEFAULT EXTRACT(YEAR FROM CURRENT_DATE)
)
RETURNS TABLE (
    analysis_category    VARCHAR(50),
    metric_name          VARCHAR(100),
    metric_value         TEXT,
    insight              TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_avg_hold_hours     DECIMAL(10, 2);
    v_median_hold_hours  DECIMAL(10, 2);
    v_best_hour          INTEGER;
    v_worst_hour         INTEGER;
    v_best_day           VARCHAR(10);
    v_worst_day          VARCHAR(10);
    v_total_trades       INTEGER;
    v_avg_slippage       DECIMAL(10, 4);
    v_avg_commission_pct DECIMAL(10, 4);
BEGIN
    -- 获取年度交易数据
    CREATE TEMP TABLE _year_trades ON COMMIT DROP AS
    SELECT *
    FROM trades t
    WHERE EXTRACT(YEAR FROM t.entry_time) = p_year
      AND (p_strategy_id IS NULL OR t.strategy_id = p_strategy_id);

    -- 持有时间统计
    SELECT
        AVG(EXTRACT(EPOCH FROM (exit_time - entry_time)) / 3600.0),
        PERCENTILE_CONT(0.5) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM (exit_time - entry_time)) / 3600.0
        ),
        COUNT(*)
    INTO v_avg_hold_hours, v_median_hold_hours, v_total_trades
    FROM _year_trades
    WHERE status = 'CLOSED' AND exit_time IS NOT NULL;

    -- 最佳/最差交易小时 (按北京时间)
    WITH hourly_pnl AS (
        SELECT
            EXTRACT(HOUR FROM entry_time AT TIME ZONE 'Asia/Shanghai')::INTEGER AS hour,
            AVG(profit_loss) AS avg_pnl,
            COUNT(*) AS cnt
        FROM _year_trades
        WHERE status = 'CLOSED'
        GROUP BY hour
    )
    SELECT
        MAX(CASE WHEN rn_asc = 1 THEN hour END),
        MAX(CASE WHEN rn_desc = 1 THEN hour END)
    INTO v_best_hour, v_worst_hour
    FROM (
        SELECT hour, avg_pnl,
            ROW_NUMBER() OVER (ORDER BY avg_pnl DESC) AS rn_desc,
            ROW_NUMBER() OVER (ORDER BY avg_pnl ASC) AS rn_asc
        FROM hourly_pnl
        WHERE cnt >= 5
    ) ranked;

    -- 最佳/最差交易日
    WITH weekly_pnl AS (
        SELECT
            TO_CHAR(entry_time, 'Day') AS day_name,
            AVG(profit_loss) AS avg_pnl,
            COUNT(*) AS cnt
        FROM _year_trades
        WHERE status = 'CLOSED'
        GROUP BY day_name
    )
    SELECT
        MAX(CASE WHEN rn_desc = 1 THEN day_name END),
        MAX(CASE WHEN rn_asc = 1 THEN day_name END)
    INTO v_best_day, v_worst_day
    FROM (
        SELECT day_name, avg_pnl,
            ROW_NUMBER() OVER (ORDER BY avg_pnl DESC) AS rn_desc,
            ROW_NUMBER() OVER (ORDER BY avg_pnl ASC) AS rn_asc
        FROM weekly_pnl
        WHERE cnt >= 3
    ) ranked;

    -- 滑点估算 (基于入场价与信号价之差)
    WITH slippage_cte AS (
        SELECT
            entry_price,
            ts.price_at_signal,
            (entry_price - ts.price_at_signal) / NULLIF(ts.price_at_signal, 0) * 100 AS slippage_pct
        FROM _year_trades t
        LEFT JOIN trading_signals ts ON t.signal_id = ts.id
        WHERE t.status = 'CLOSED'
          AND ts.price_at_signal IS NOT NULL
          AND t.entry_price IS NOT NULL
    )
    SELECT AVG(ABS(slippage_pct)) INTO v_avg_slippage FROM slippage_cte;

    -- 平均佣金比例
    SELECT AVG(fees / NULLIF(quantity * entry_price, 0)) * 100
    INTO v_avg_commission_pct
    FROM _year_trades
    WHERE status = 'CLOSED' AND fees > 0;

    -- 返回结果集
    RETURN QUERY
    SELECT 'Holding Period'::VARCHAR(50), 'Average (hours)'::VARCHAR(100),
           ROUND(v_avg_hold_hours, 2)::TEXT,
           'Average time a position is held before closing'
    UNION ALL
    SELECT 'Holding Period', 'Median (hours)',
           ROUND(v_median_hold_hours, 2)::TEXT,
           'Median holding time, less sensitive to outliers'
    UNION ALL
    SELECT 'Holding Period', 'Total Trades Analyzed',
           v_total_trades::TEXT,
           'Total number of closed trades in the analysis period'
    UNION ALL
    SELECT 'Timing Analysis', 'Best Entry Hour (CST)',
           v_best_hour::TEXT,
           'Hour of day (Asia/Shanghai) with highest avg PnL'
    UNION ALL
    SELECT 'Timing Analysis', 'Worst Entry Hour (CST)',
           v_worst_hour::TEXT,
           'Hour of day (Asia/Shanghai) with lowest avg PnL'
    UNION ALL
    SELECT 'Timing Analysis', 'Best Trading Day',
           v_best_day,
           'Day of week with highest average PnL'
    UNION ALL
    SELECT 'Timing Analysis', 'Worst Trading Day',
           v_worst_day,
           'Day of week with lowest average PnL'
    UNION ALL
    SELECT 'Execution Quality', 'Avg Slippage %',
           ROUND(v_avg_slippage, 4)::TEXT,
           'Average price slippage between signal and execution'
    UNION ALL
    SELECT 'Execution Quality', 'Avg Commission %',
           ROUND(v_avg_commission_pct, 4)::TEXT,
           'Average commission as percentage of trade value';
END;
$$;

COMMENT ON FUNCTION get_trading_behavior_analysis IS
    'Trading behavior pattern analysis including holding periods, timing, and execution quality';

-- 使用示例:
-- SELECT * FROM get_trading_behavior_analysis(NULL, 2024);


-- ============================================================================
-- 6. 风险价值 VaR 回测验证 (VaR Backtest)
-- ============================================================================
-- 对 VaR 模型进行回测验证，包括 Kupiec 失败率检验和 Christoffersen 独立性检验

CREATE OR REPLACE FUNCTION get_var_backtest_validation(
    p_strategy_id UUID DEFAULT NULL,
    p_var_level DECIMAL(5, 4) DEFAULT 0.95,  -- VaR 置信水平
    p_lookback_days INTEGER DEFAULT 252       -- 历史数据窗口
)
RETURNS TABLE (
    metric_name          VARCHAR(100),
    metric_value         DECIMAL(15, 6),
    threshold_lower      DECIMAL(15, 6),
    threshold_upper      DECIMAL(15, 6),
    is_passing           BOOLEAN,
    interpretation       TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_var_threshold      DECIMAL(15, 6);
    v_total_days         INTEGER;
    v_exception_count    INTEGER;
    v_exception_rate     DECIMAL(10, 6);
    v_expected_exceptions DECIMAL(10, 6);
    v_kupiec_lr          DECIMAL(15, 6);
    v_kupiec_pvalue      DECIMAL(10, 6);
    v_chi2_critical      DECIMAL(10, 6);
    v_independence_pvalue DECIMAL(10, 6);
BEGIN
    -- 构建历史收益率序列
    CREATE TEMP TABLE _hist_returns ON COMMIT DROP AS
    SELECT
        t.exit_time::DATE AS trade_date,
        SUM(t.profit_loss_percent) AS daily_return
    FROM trades t
    WHERE t.status = 'CLOSED'
      AND t.exit_time IS NOT NULL
      AND (p_strategy_id IS NULL OR t.strategy_id = p_strategy_id)
    GROUP BY t.exit_time::DATE
    ORDER BY trade_date;

    -- 计算 VaR 阈值 (历史模拟法, p_var_level 分位数)
    SELECT PERCENTILE_CONT(1 - p_var_level) WITHIN GROUP (ORDER BY daily_return)
    INTO v_var_threshold
    FROM _hist_returns;

    -- 计算异常次数
    SELECT
        COUNT(*),
        SUM(CASE WHEN daily_return < v_var_threshold THEN 1 ELSE 0 END)
    INTO v_total_days, v_exception_count
    FROM _hist_returns;

    -- 预期异常次数
    v_expected_exceptions := v_total_days * (1 - p_var_level);

    -- 异常率
    v_exception_rate := CASE WHEN v_total_days > 0
        THEN v_exception_count::DECIMAL / v_total_days
        ELSE 0
    END;

    -- Kupiec LR (似然比检验)
    -- LR = -2 * ln( (1-p)^(T-N) * p^N / (1-(N/T))^(T-N) * (N/T)^N )
    IF v_total_days > 0 AND v_exception_count > 0 THEN
        v_kupiec_lr := -2 * (
            (v_total_days - v_exception_count) * LN(1 - (1 - p_var_level))
            + v_exception_count * LN(1 - p_var_level)
            - (v_total_days - v_exception_count) * LN(1 - v_exception_rate)
            - v_exception_count * LN(v_exception_rate)
        );
    ELSE
        v_kupiec_lr := 0;
    END IF;

    -- 近似 p-value (χ² 分布, df=1)
    -- 3.841 是 χ²(1) 在 95% 置信水平的临界值
    v_chi2_critical := 3.841;
    v_kupiec_pvalue := CASE
        WHEN v_kupiec_lr > v_chi2_critical THEN 0.05
        ELSE 0.95
    END;

    -- 独立性检验 (Christoffersen)
    -- 简化版：检验异常是否聚集
    WITH exceptions AS (
        SELECT
            trade_date,
            CASE WHEN daily_return < v_var_threshold THEN 1 ELSE 0 END AS is_exception
        FROM _hist_returns
    ),
    transitions AS (
        SELECT
            e1.is_exception AS current_val,
            e2.is_exception AS next_val,
            COUNT(*) AS cnt
        FROM exceptions e1
        JOIN exceptions e2 ON e2.trade_date = e1.trade_date + 1
        GROUP BY e1.is_exception, e2.is_exception
    ),
    trans_probs AS (
        SELECT
            current_val,
            SUM(CASE WHEN next_val = 1 THEN cnt ELSE 0 END) / NULLIF(SUM(cnt), 0) AS p_1_given_current
        FROM transitions
        GROUP BY current_val
    )
    SELECT
        CASE WHEN COUNT(*) = 2 THEN
            ABS(MAX(CASE WHEN current_val = 0 THEN p_1_given_current END)
                - MAX(CASE WHEN current_val = 1 THEN p_1_given_current END))
        ELSE 0
        END
    INTO v_independence_pvalue
    FROM trans_probs;

    -- 返回结果
    RETURN QUERY
    SELECT 'VaR Threshold'::VARCHAR(100),
           ROUND(v_var_threshold, 6),
           0::DECIMAL(15,6), 0::DECIMAL(15,6), TRUE,
           FORMAT('Historical VaR at %s%% confidence', (p_var_level * 100)::TEXT)
    UNION ALL
    SELECT 'Total Observations', v_total_days::DECIMAL(15,6),
           0, 0, TRUE, 'Number of daily return observations'
    UNION ALL
    SELECT 'Expected Exceptions', ROUND(v_expected_exceptions, 2),
           0, 0, TRUE,
           FORMAT('Expected: %s%% of observations', ((1-p_var_level)*100)::TEXT)
    UNION ALL
    SELECT 'Actual Exceptions', v_exception_count::DECIMAL(15,6),
           0, 0, TRUE, 'Number of VaR exceedances'
    UNION ALL
    SELECT 'Exception Rate', ROUND(v_exception_rate, 6),
           ROUND((1-p_var_level)*0.8, 6), ROUND((1-p_var_level)*1.2, 6),
           v_exception_rate BETWEEN (1-p_var_level)*0.8 AND (1-p_var_level)*1.2,
           'Acceptable range: ±20% of expected rate'
    UNION ALL
    SELECT 'Kupiec LR Statistic', ROUND(v_kupiec_lr, 4),
           0, ROUND(v_chi2_critical, 4),
           v_kupiec_lr < v_chi2_critical,
           'H0: Model is correct. Fail to reject if LR < 3.841 (95% confidence)'
    UNION ALL
    SELECT 'Independence Score', ROUND(v_independence_pvalue, 4),
           0, 0.5,
           v_independence_pvalue < 0.5,
           'Lower score indicates less clustering of VaR exceptions';
END;
$$;

COMMENT ON FUNCTION get_var_backtest_validation IS
    'VaR model backtest validation with Kupiec and Christoffersen tests';

-- 使用示例:
-- SELECT * FROM get_var_backtest_validation(NULL, 0.95, 252);