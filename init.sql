-- Initialize PostgreSQL database for Intelligent Strategy Trading

-- Create tables for order management
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    internal_id VARCHAR(255) UNIQUE NOT NULL,
    broker_order_id VARCHAR(255),
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    limit_price DECIMAL(20, 8),
    stop_price DECIMAL(20, 8),
    status VARCHAR(20) NOT NULL,
    filled_quantity DECIMAL(20, 8) DEFAULT 0,
    avg_fill_price DECIMAL(20, 8),
    commission DECIMAL(20, 8) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Create index for common queries
CREATE INDEX idx_orders_symbol ON orders(symbol);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at);

-- Table for trades
CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id),
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    value DECIMAL(20, 8) NOT NULL,
    commission DECIMAL(20, 8) DEFAULT 0,
    pnl DECIMAL(20, 8),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_timestamp ON trades(timestamp);

-- Table for strategy configurations
CREATE TABLE IF NOT EXISTS strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    config JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_strategies_status ON strategies(status);

-- Table for backtest results
CREATE TABLE IF NOT EXISTS backtests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backtest_id VARCHAR(255) UNIQUE NOT NULL,
    strategy_id VARCHAR(255) REFERENCES strategies(strategy_id),
    config JSONB NOT NULL,
    results JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_backtests_strategy_id ON backtests(strategy_id);
CREATE INDEX idx_backtests_status ON backtests(status);

-- Table for portfolio snapshots
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    equity DECIMAL(20, 2) NOT NULL,
    cash DECIMAL(20, 2) NOT NULL,
    positions JSONB,
    metrics JSONB
);

CREATE INDEX idx_portfolio_snapshots_timestamp ON portfolio_snapshots(timestamp);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_strategies_updated_at BEFORE UPDATE ON strategies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
