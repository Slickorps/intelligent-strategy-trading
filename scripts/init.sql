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

COMMIT;
