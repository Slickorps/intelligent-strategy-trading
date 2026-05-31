-- Database initialization script for Intelligent Strategy Trading Platform
-- This script creates the necessary database schema

-- Create database if it doesn't exist
CREATE DATABASE IF NOT EXISTS trading_db;

-- Use the trading database
\c trading_db;

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Create trading strategies table
CREATE TABLE IF NOT EXISTS strategies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    parameters JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create market data table
CREATE TABLE IF NOT EXISTS market_data (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    open_price DECIMAL(15, 6),
    high_price DECIMAL(15, 6),
    low_price DECIMAL(15, 6),
    close_price DECIMAL(15, 6),
    volume BIGINT,
    timeframe VARCHAR(10) NOT NULL, -- '1m', '5m', '1h', '1d', etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timestamp, timeframe)
);

-- Create indicators table
CREATE TABLE IF NOT EXISTS indicators (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID REFERENCES strategies(id) ON DELETE CASCADE,
    indicator_type VARCHAR(50) NOT NULL, -- 'SMA', 'EMA', 'RSI', 'MACD', etc.
    parameters JSONB DEFAULT '{}',
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indicator values table
CREATE TABLE IF NOT EXISTS indicator_values (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    indicator_id UUID REFERENCES indicators(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    value DECIMAL(15, 6),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indicator_id, symbol, timestamp)
);

-- Create trading signals table
CREATE TABLE IF NOT EXISTS trading_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID REFERENCES strategies(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    signal_type VARCHAR(20) NOT NULL, -- 'BUY', 'SELL', 'HOLD'
    signal_strength DECIMAL(3, 2) DEFAULT 1.0, -- 0.0 to 1.0
    price_at_signal DECIMAL(15, 6),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    metadata JSONB DEFAULT '{}',
    is_executed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create trades table
CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID REFERENCES strategies(id) ON DELETE CASCADE,
    signal_id UUID REFERENCES trading_signals(id) ON DELETE SET NULL,
    symbol VARCHAR(20) NOT NULL,
    trade_type VARCHAR(10) NOT NULL, -- 'LONG', 'SHORT'
    entry_price DECIMAL(15, 6) NOT NULL,
    exit_price DECIMAL(15, 6),
    quantity DECIMAL(15, 6) NOT NULL,
    entry_time TIMESTAMP WITH TIME ZONE NOT NULL,
    exit_time TIMESTAMP WITH TIME ZONE,
    profit_loss DECIMAL(15, 6),
    profit_loss_percent DECIMAL(8, 4),
    fees DECIMAL(15, 6) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'OPEN', -- 'OPEN', 'CLOSED', 'CANCELLED'
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create performance metrics table
CREATE TABLE IF NOT EXISTS performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID REFERENCES strategies(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    total_return DECIMAL(15, 6) DEFAULT 0,
    max_drawdown DECIMAL(15, 6) DEFAULT 0,
    sharpe_ratio DECIMAL(8, 4) DEFAULT 0,
    win_rate DECIMAL(5, 4) DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(strategy_id, date)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_timestamp ON market_data(symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_timeframe ON market_data(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_indicator_values_indicator_symbol ON indicator_values(indicator_id, symbol);
CREATE INDEX IF NOT EXISTS idx_trading_signals_strategy_timestamp ON trading_signals(strategy_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_strategy_status ON trades(strategy_id, status);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_strategy_date ON performance_metrics(strategy_id, date);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_strategies_updated_at BEFORE UPDATE ON strategies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_indicators_updated_at BEFORE UPDATE ON indicators
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_trades_updated_at BEFORE UPDATE ON trades
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert sample data
INSERT INTO users (username, email, password_hash) VALUES 
('admin', 'admin@trading.com', '$2b$12$example_hash_here'),
('trader1', 'trader1@example.com', '$2b$12$example_hash_here')
ON CONFLICT (username) DO NOTHING;

INSERT INTO strategies (user_id, name, description, parameters) VALUES 
((SELECT id FROM users WHERE username = 'admin'), 'Simple SMA Strategy', 'Simple moving average crossover strategy', '{"fast_period": 10, "slow_period": 20}'),
((SELECT id FROM users WHERE username = 'admin'), 'RSI Mean Reversion', 'RSI-based mean reversion strategy', '{"period": 14, "oversold": 30, "overbought": 70}')
ON CONFLICT DO NOTHING;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trading_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trading_user;

-- ============================================================================
-- Stored Procedures: 回测结果聚合统计 (Backtest Aggregation)
-- ============================================================================

CREATE OR REPLACE FUNCTION get_backtest_summary(
    p_strategy_id UUID,
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT NULL
)
RETURNS TABLE (
    total_trades         BIGINT,
    winning_trades       BIGINT,
    losing_trades        BIGINT,
    win_rate             DECIMAL(6, 4),
    total_profit_loss    DECIMAL(15, 6),
    avg_profit_loss      DECIMAL(15, 6),
    max_win              DECIMAL(15, 6),
    max_loss             DECIMAL(15, 6),
    profit_factor        DECIMAL(10, 4),
    avg_holding_period   INTERVAL,
    total_fees           DECIMAL(15, 6),
    net_profit           DECIMAL(15, 6)
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH trade_stats AS (
        SELECT
            COUNT(t.id)::BIGINT AS total,
            SUM(CASE WHEN t.profit_loss > 0 THEN 1 ELSE 0 END)::BIGINT AS wins,
            SUM(CASE WHEN t.profit_loss <= 0 THEN 1 ELSE 0 END)::BIGINT AS losses,
            SUM(t.profit_loss) AS total_pl,
            AVG(t.profit_loss) AS avg_pl,
            MAX(t.profit_loss) AS max_win_val,
            MIN(t.profit_loss) AS max_loss_val,
            SUM(CASE WHEN t.profit_loss > 0 THEN t.profit_loss ELSE 0 END) AS gross_profit,
            SUM(CASE WHEN t.profit_loss < 0 THEN ABS(t.profit_loss) ELSE 0 END) AS gross_loss,
            AVG(t.exit_time - t.entry_time) AS avg_hold,
            SUM(t.fees) AS total_fee
        FROM trades t
        WHERE t.strategy_id = p_strategy_id
          AND t.status = 'CLOSED'
          AND (p_start_date IS NULL OR t.exit_time >= p_start_date)
          AND (p_end_date IS NULL OR t.exit_time <= p_end_date)
    )
    SELECT
        ts.total,
        ts.wins,
        ts.losses,
        CASE WHEN ts.total > 0
            THEN ROUND(ts.wins::DECIMAL / ts.total, 4)
            ELSE 0
        END,
        ts.total_pl,
        ts.avg_pl,
        ts.max_win_val,
        ts.max_loss_val,
        CASE WHEN ts.gross_loss > 0
            THEN ROUND(ts.gross_profit / ts.gross_loss, 4)
            ELSE ts.gross_profit
        END,
        ts.avg_hold,
        ts.total_fee,
        ts.total_pl - ts.total_fee
    FROM trade_stats ts;
END;
$$;

COMMENT ON FUNCTION get_backtest_summary IS
    'Aggregate backtest statistics for a given strategy and optional date range';


-- ============================================================================
-- Stored Procedures: 交易流水分析报表 (Trade Flow Analysis Report)
-- ============================================================================

CREATE OR REPLACE FUNCTION get_trade_flow_report(
    p_strategy_id UUID DEFAULT NULL,
    p_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    trade_id            UUID,
    strategy_name       VARCHAR(100),
    symbol              VARCHAR(20),
    trade_type          VARCHAR(10),
    entry_time          TIMESTAMP WITH TIME ZONE,
    exit_time           TIMESTAMP WITH TIME ZONE,
    entry_price         DECIMAL(15, 6),
    exit_price          DECIMAL(15, 6),
    quantity            DECIMAL(15, 6),
    profit_loss         DECIMAL(15, 6),
    profit_loss_pct     DECIMAL(8, 4),
    fees                DECIMAL(15, 6),
    holding_period      INTERVAL,
    is_winner           BOOLEAN,
    trade_score         DECIMAL(8, 4)
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.id,
        s.name,
        t.symbol,
        t.trade_type,
        t.entry_time,
        t.exit_time,
        t.entry_price,
        t.exit_price,
        t.quantity,
        t.profit_loss,
        t.profit_loss_percent,
        t.fees,
        t.exit_time - t.entry_time,
        CASE WHEN t.profit_loss > 0 THEN TRUE ELSE FALSE END,
        -- 综合评分: 收益率 * 胜率权重 / 持有时间
        ROUND(
            COALESCE(t.profit_loss_percent, 0) *
            CASE WHEN t.profit_loss > 0 THEN 1.0 ELSE 0.5 END /
            NULLIF(
                EXTRACT(EPOCH FROM (t.exit_time - t.entry_time)) / 86400.0,
                0
            ) * 100, 4
        ) AS score
    FROM trades t
    JOIN strategies s ON t.strategy_id = s.id
    WHERE t.status = 'CLOSED'
      AND (p_strategy_id IS NULL OR t.strategy_id = p_strategy_id)
    ORDER BY t.exit_time DESC
    LIMIT p_limit;
END;
$$;

COMMENT ON FUNCTION get_trade_flow_report IS
    'Detailed trade flow analysis report with scoring';


-- ============================================================================
-- Stored Procedures: 风险指标计算函数 (Risk Metrics Calculation)
-- ============================================================================

CREATE OR REPLACE FUNCTION calculate_risk_metrics(
    p_strategy_id UUID,
    p_risk_free_rate DECIMAL(8, 4) DEFAULT 0.02
)
RETURNS TABLE (
    metric_name         VARCHAR(50),
    metric_value        DECIMAL(15, 6),
    metric_description  TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_total_return      DECIMAL(15, 6);
    v_avg_return        DECIMAL(15, 6);
    v_std_return        DECIMAL(15, 6);
    v_sharpe            DECIMAL(10, 4);
    v_sortino           DECIMAL(10, 4);
    v_max_dd            DECIMAL(10, 4);
    v_calmar            DECIMAL(10, 4);
    v_win_rate          DECIMAL(6, 4);
    v_total_trades      INTEGER;
    v_avg_win           DECIMAL(15, 6);
    v_avg_loss          DECIMAL(15, 6);
    v_expectancy        DECIMAL(15, 6);
BEGIN
    -- 计算每日收益率
    CREATE TEMP TABLE _daily_returns ON COMMIT DROP AS
    SELECT
        t.exit_time::DATE AS trade_date,
        SUM(t.profit_loss_percent) AS daily_return
    FROM trades t
    WHERE t.strategy_id = p_strategy_id
      AND t.status = 'CLOSED'
      AND t.exit_time IS NOT NULL
    GROUP BY t.exit_time::DATE;

    -- 基础统计
    SELECT
        COALESCE(SUM(daily_return), 0),
        COALESCE(AVG(daily_return), 0),
        COALESCE(STDDEV(daily_return), 0)
    INTO v_total_return, v_avg_return, v_std_return
    FROM _daily_returns;

    -- Sharpe Ratio (年化)
    v_sharpe := CASE WHEN v_std_return > 0
        THEN (v_avg_return * 252 - p_risk_free_rate) / (v_std_return * SQRT(252))
        ELSE 0
    END;

    -- Sortino Ratio (仅下行风险)
    WITH downside AS (
        SELECT STDDEV(daily_return) AS downside_std
        FROM _daily_returns
        WHERE daily_return < 0
    )
    SELECT
        CASE WHEN d.downside_std > 0 AND d.downside_std IS NOT NULL
            THEN (v_avg_return * 252 - p_risk_free_rate) / (d.downside_std * SQRT(252))
            ELSE 0
        END
    INTO v_sortino
    FROM downside d;

    -- 最大回撤 (使用峰值回撤法)
    WITH cumulative AS (
        SELECT
            trade_date,
            SUM(daily_return) OVER (ORDER BY trade_date) AS cum_return,
            MAX(SUM(daily_return)) OVER (ORDER BY trade_date) AS peak
        FROM _daily_returns
        GROUP BY trade_date, daily_return
    )
    SELECT COALESCE(MAX((peak - cum_return) / NULLIF(ABS(peak), 0) * 100), 0)
    INTO v_max_dd
    FROM cumulative;

    -- Calmar Ratio
    v_calmar := CASE WHEN v_max_dd > 0
        THEN (v_total_return * 100) / v_max_dd
        ELSE 0
    END;

    -- 交易统计
    SELECT
        COUNT(*),
        ROUND(COUNT(CASE WHEN profit_loss > 0 THEN 1 END)::DECIMAL / NULLIF(COUNT(*), 0), 4),
        AVG(CASE WHEN profit_loss > 0 THEN profit_loss END),
        AVG(CASE WHEN profit_loss < 0 THEN profit_loss END)
    INTO
        v_total_trades,
        v_win_rate,
        v_avg_win,
        v_avg_loss
    FROM trades
    WHERE strategy_id = p_strategy_id
      AND status = 'CLOSED';

    -- Expectancy (期望值)
    v_expectancy := CASE
        WHEN v_avg_loss IS NOT NULL AND v_avg_loss != 0
        THEN (v_win_rate * v_avg_win + (1 - v_win_rate) * ABS(v_avg_loss)) / NULLIF(ABS(v_avg_loss), 0)
        ELSE 0
    END;

    -- 返回结果集
    RETURN QUERY
    SELECT 'Total Return'::VARCHAR(50), ROUND(v_total_return, 4)::DECIMAL(15, 6), 'Cumulative return percentage'::TEXT
    UNION ALL
    SELECT 'Avg Daily Return', ROUND(v_avg_return, 6), 'Average daily return percentage'
    UNION ALL
    SELECT 'Daily Std Dev', ROUND(v_std_return, 6), 'Standard deviation of daily returns'
    UNION ALL
    SELECT 'Sharpe Ratio (Ann.)', ROUND(v_sharpe, 4), 'Risk-adjusted return (annualized)'
    UNION ALL
    SELECT 'Sortino Ratio (Ann.)', ROUND(v_sortino, 4), 'Downside risk-adjusted return'
    UNION ALL
    SELECT 'Max Drawdown %', ROUND(v_max_dd, 4), 'Maximum peak-to-valley drawdown'
    UNION ALL
    SELECT 'Calmar Ratio', ROUND(v_calmar, 4), 'Return / Max Drawdown ratio'
    UNION ALL
    SELECT 'Win Rate', ROUND(v_win_rate, 4), 'Percentage of winning trades'
    UNION ALL
    SELECT 'Total Trades', v_total_trades::DECIMAL(15, 6), 'Total number of closed trades'
    UNION ALL
    SELECT 'Avg Win', ROUND(v_avg_win, 4), 'Average profit of winning trades'
    UNION ALL
    SELECT 'Avg Loss', ROUND(v_avg_loss, 4), 'Average loss of losing trades'
    UNION ALL
    SELECT 'Expectancy', ROUND(v_expectancy, 4), 'Expected profit per unit risk';
END;
$$;

COMMENT ON FUNCTION calculate_risk_metrics IS
    'Comprehensive risk metrics calculation including Sharpe, Sortino, Calmar ratios';


-- ============================================================================
-- 最终提交
-- ============================================================================

COMMIT;
