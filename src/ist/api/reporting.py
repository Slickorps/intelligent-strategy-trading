"""Reporting and export functionality.

Generates PDF reports, Excel exports, and webhook notifications.
"""

import json
from datetime import datetime
from typing import Any, Optional

from ist.core.logging import get_logger

logger = get_logger(__name__)


class ReportGenerator:
    """Generate various report formats.
    
    Usage:
        generator = ReportGenerator()
        
        # HTML report
        html = generator.generate_html_report(
            backtest_results,
            title="Strategy Backtest Report"
        )
        
        # JSON export
        json_data = generator.export_to_json(backtest_results)
        
        # CSV export
        csv_data = generator.export_trades_to_csv(trades)
    """
    
    def __init__(self) -> None:
        self.templates = {
            "backtest": self._backtest_template,
            "portfolio": self._portfolio_template,
            "risk": self._risk_template
        }
    
    def generate_html_report(
        self,
        data: dict[str, Any],
        title: str = "Trading Report",
        report_type: str = "backtest"
    ) -> str:
        """Generate HTML report.
        
        Args:
            data: Report data dictionary
            title: Report title
            report_type: Type of report (backtest, portfolio, risk)
            
        Returns:
            HTML string
        """
        template = self.templates.get(report_type, self._backtest_template)
        
        return template(data, title)
    
    def export_to_json(
        self,
        data: dict[str, Any],
        indent: int = 2
    ) -> str:
        """Export data to JSON string."""
        return json.dumps(data, indent=indent, default=str)
    
    def export_trades_to_csv(self, trades: list[dict]) -> str:
        """Export trades to CSV format."""
        if not trades:
            return ""
        
        # Get headers from first trade
        headers = list(trades[0].keys())
        
        # Build CSV
        lines = [",".join(headers)]
        
        for trade in trades:
            row = []
            for key in headers:
                value = trade.get(key, "")
                # Escape commas and quotes
                if isinstance(value, str) and ("," in value or '"' in value):
                    value = '"' + value.replace('"', '""') + '"'
                row.append(str(value))
            lines.append(",".join(row))
        
        return "\n".join(lines)
    
    def export_equity_curve_to_csv(
        self,
        equity_curve: list[dict]
    ) -> str:
        """Export equity curve to CSV."""
        if not equity_curve:
            return ""
        
        headers = ["date", "equity", "daily_return", "drawdown"]
        lines = [",".join(headers)]
        
        peak = 0
        for entry in equity_curve:
            date = entry.get("date", "")
            equity = entry.get("equity", 0)
            
            if equity > peak:
                peak = equity
            
            drawdown = (peak - equity) / peak if peak > 0 else 0
            
            lines.append(f"{date},{equity},,{drawdown:.4f}")
        
        return "\n".join(lines)
    
    def _backtest_template(
        self,
        data: dict[str, Any],
        title: str
    ) -> str:
        """Generate HTML backtest report."""
        metrics = data.get("metrics", {})
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 40px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4a90d9;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #4a90d9;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
            margin-top: 5px;
        }}
        .positive {{
            color: #27ae60;
        }}
        .negative {{
            color: #e74c3c;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #4a90d9;
            color: white;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #666;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <p>Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
        
        <h2>Performance Summary</h2>
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Total Return</div>
                <div class="metric-value {'positive' if metrics.get('total_return', 0) > 0 else 'negative'}">
                    {metrics.get('total_return', 0):.2%}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Sharpe Ratio</div>
                <div class="metric-value">{metrics.get('sharpe_ratio', 0):.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Max Drawdown</div>
                <div class="metric-value negative">
                    {metrics.get('max_drawdown', 0):.2%}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value">{metrics.get('win_rate', 0):.1%}</div>
            </div>
        </div>
        
        <h2>Trade Statistics</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Total Trades</td>
                <td>{metrics.get('total_trades', 0)}</td>
            </tr>
            <tr>
                <td>Winning Trades</td>
                <td>{metrics.get('winning_trades', 0)}</td>
            </tr>
            <tr>
                <td>Losing Trades</td>
                <td>{metrics.get('losing_trades', 0)}</td>
            </tr>
            <tr>
                <td>Profit Factor</td>
                <td>{metrics.get('profit_factor', 0):.2f}</td>
            </tr>
        </table>
        
        <div class="footer">
            Generated by Intelligent Strategy Trading Platform
        </div>
    </div>
</body>
</html>"""
        
        return html
    
    def _portfolio_template(
        self,
        data: dict[str, Any],
        title: str
    ) -> str:
        """Generate HTML portfolio report."""
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <p>Portfolio Value: ${data.get('equity', 0):,.2f}</p>
    </div>
</body>
</html>"""
    
    def _risk_template(
        self,
        data: dict[str, Any],
        title: str
    ) -> str:
        """Generate HTML risk report."""
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; }}
        .risk-metric {{ 
            background: #f8f9fa; 
            padding: 15px; 
            margin: 10px 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="risk-metric">
            <h3>Value at Risk (95%)</h3>
            <p>{data.get('var_95', 0):.2%}</p>
        </div>
    </div>
</body>
</html>"""


class WebhookNotifier:
    """Send webhook notifications for trading events.
    
    Usage:
        notifier = WebhookNotifier()
        
        # Add webhook endpoints
        notifier.add_webhook("slack", "https://hooks.slack.com/...")
        notifier.add_webhook("discord", "https://discord.com/api/webhooks/...")
        
        # Send notifications
        await notifier.notify_trade_filled(trade_result)
        await notifier.notify_risk_alert(risk_event)
    """
    
    def __init__(self) -> None:
        self._webhooks: dict[str, str] = {}
    
    def add_webhook(self, name: str, url: str) -> None:
        """Register webhook endpoint."""
        self._webhooks[name] = url
        logger.info(f"Webhook registered: {name}")
    
    def remove_webhook(self, name: str) -> None:
        """Remove webhook endpoint."""
        self._webhooks.pop(name, None)
    
    async def notify_trade_filled(
        self,
        trade: dict[str, Any]
    ) -> dict[str, bool]:
        """Send trade fill notification."""
        message = {
            "event": "trade_filled",
            "timestamp": datetime.utcnow().isoformat(),
            "data": trade
        }
        
        return await self._send_to_all(message)
    
    async def notify_risk_alert(
        self,
        alert_type: str,
        details: dict[str, Any]
    ) -> dict[str, bool]:
        """Send risk alert notification."""
        message = {
            "event": "risk_alert",
            "alert_type": alert_type,
            "timestamp": datetime.utcnow().isoformat(),
            "severity": details.get("severity", "warning"),
            "details": details
        }
        
        return await self._send_to_all(message)
    
    async def notify_backtest_completed(
        self,
        backtest_id: str,
        results: dict[str, Any]
    ) -> dict[str, bool]:
        """Send backtest completion notification."""
        message = {
            "event": "backtest_completed",
            "backtest_id": backtest_id,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_return": results.get("total_return", 0),
                "sharpe_ratio": results.get("sharpe_ratio", 0),
                "max_drawdown": results.get("max_drawdown", 0)
            }
        }
        
        return await self._send_to_all(message)
    
    async def _send_to_all(
        self,
        message: dict[str, Any]
    ) -> dict[str, bool]:
        """Send message to all registered webhooks."""
        results = {}
        
        for name, url in self._webhooks.items():
            try:
                success = await self._send_webhook(url, message)
                results[name] = success
            except Exception as e:
                logger.error(f"Webhook {name} failed: {e}")
                results[name] = False
        
        return results
    
    async def _send_webhook(
        self,
        url: str,
        payload: dict[str, Any]
    ) -> bool:
        """Send HTTP POST to webhook URL.
        
        In production, this would use httpx or aiohttp.
        For now, just log the payload.
        """
        logger.info(
            f"Webhook would send to {url}",
            payload=payload
        )
        return True
    
    def format_slack_message(
        self,
        event_type: str,
        data: dict[str, Any]
    ) -> dict[str, Any]:
        """Format message for Slack."""
        return {
            "text": f"Trading Event: {event_type}",
            "attachments": [
                {
                    "color": "good" if data.get("pnl", 0) > 0 else "danger",
                    "fields": [
                        {
                            "title": k,
                            "value": str(v),
                            "short": True
                        }
                        for k, v in data.items()
                    ]
                }
            ]
        }
    
    def format_discord_message(
        self,
        event_type: str,
        data: dict[str, Any]
    ) -> dict[str, Any]:
        """Format message for Discord."""
        return {
            "content": f"**Trading Event: {event_type}**",
            "embeds": [
                {
                    "color": 0x00ff00 if data.get("pnl", 0) > 0 else 0xff0000,
                    "fields": [
                        {
                            "name": k,
                            "value": str(v),
                            "inline": True
                        }
                        for k, v in data.items()
                    ],
                    "timestamp": datetime.utcnow().isoformat()
                }
            ]
        }


class EmailReporter:
    """Email report sender (placeholder for SMTP integration).
    
    In production, this would integrate with:
    - SendGrid
    - AWS SES
    - SMTP server
    """
    
    def __init__(self, smtp_config: Optional[dict] = None) -> None:
        self.config = smtp_config or {}
    
    async def send_daily_report(
        self,
        to_email: str,
        portfolio_data: dict[str, Any]
    ) -> bool:
        """Send daily portfolio report."""
        # Placeholder implementation
        logger.info(
            f"Daily report would be sent to {to_email}",
            portfolio_value=portfolio_data.get("equity", 0)
        )
        return True
    
    async def send_alert(
        self,
        to_email: str,
        subject: str,
        message: str
    ) -> bool:
        """Send alert email."""
        logger.info(
            f"Alert would be sent to {to_email}",
            subject=subject
        )
        return True
