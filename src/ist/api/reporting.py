"""Reporting and export functionality.

Generates PDF reports, Excel exports, and webhook notifications.
Delegates core report generation to src/ist/backtest/report.py.
"""

import json
from datetime import datetime
from typing import Any, Optional

from ist.backtest.report import BacktestReporter
from ist.core.logging import get_logger

logger = get_logger(__name__)


class ReportGenerator:
    """Generate various report formats.
    
    Delegates core report generation to BacktestReporter.
    
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
        self._reporter = BacktestReporter()
    
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
        if report_type == "backtest":
            metrics = data.get("metrics", {})
            trades = data.get("trades", [])
            equity_curve = data.get("equity_curve", [])
            return self._reporter.generate_html_report(
                metrics=metrics,
                trades=trades,
                equity_curve=equity_curve,
                title=title,
            )
        elif report_type == "portfolio":
            return self._reporter.generate_portfolio_report(data, title)
        elif report_type == "risk":
            return self._reporter.generate_risk_report(data, title)
        else:
            return self._reporter.generate_html_report(
                metrics=data.get("metrics", {}),
                title=title,
            )
    
    def export_to_json(
        self,
        data: dict[str, Any],
        indent: int = 2
    ) -> str:
        """Export data to JSON string."""
        return self._reporter.export_to_json(data, indent)
    
    def export_trades_to_csv(self, trades: list[dict]) -> str:
        """Export trades to CSV format."""
        return self._reporter.export_trades_to_csv(trades)
    
    def export_equity_curve_to_csv(
        self,
        equity_curve: list[dict]
    ) -> str:
        """Export equity curve to CSV."""
        return self._reporter.export_equity_curve_to_csv(equity_curve)
    
    def generate_pdf_report(
        self,
        data: dict[str, Any],
        output_path: str,
        title: str = "Trading Report",
    ) -> Optional[str]:
        """Generate PDF report.
        
        Args:
            data: Report data dictionary
            output_path: Path to save PDF file
            title: Report title
            
        Returns:
            Path to generated PDF, or None if generation failed
        """
        return self._reporter.generate_pdf_report(data, output_path, title)
    
    def export_to_excel(
        self,
        data: dict[str, Any],
        output_path: str,
    ) -> Optional[str]:
        """Export data to Excel file.
        
        Args:
            data: Report data dictionary
            output_path: Path to save Excel file
            
        Returns:
            Path to generated Excel file, or None if generation failed
        """
        return self._reporter.export_to_excel(data, output_path)


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
