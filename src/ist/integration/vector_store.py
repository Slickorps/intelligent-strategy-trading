"""Vector database integration for strategy memory.

Stores and retrieves strategy performance data, market regimes,
and research notes for RAG (Retrieval Augmented Generation).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from ist.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StrategyRecord:
    """Record of strategy execution results."""
    
    id: str
    strategy_id: str
    timestamp: datetime
    
    # Performance data
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    
    # Market context
    market_regime: str  # trending, ranging, volatile
    start_date: str
    end_date: str
    
    # Metadata
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    
    # Embedding for similarity search
    embedding: Optional[list[float]] = None


class StrategyMemory:
    """Vector-based memory for strategy performance.
    
    Enables semantic search of past strategy results
    for knowledge retrieval and pattern matching.
    
    Usage:
        memory = StrategyMemory()
        
        # Store result
        memory.store_strategy_result(
            strategy_id="trend_following_v1",
            result=backtest_result,
            metadata={"market_regime": "trending"}
        )
        
        # Query similar
        similar = memory.query_similar_strategies(
            target_sharpe=1.8,
            n_results=5
        )
    """
    
    def __init__(self, embedding_dimension: int = 128) -> None:
        self.embedding_dimension = embedding_dimension
        self._records: dict[str, StrategyRecord] = {}
        self._embeddings: dict[str, list[float]] = {}
    
    def store_strategy_result(
        self,
        strategy_id: str,
        result: dict[str, Any],
        metadata: Optional[dict] = None
    ) -> str:
        """Store strategy result with embedding.
        
        Args:
            strategy_id: Strategy identifier
            result: Backtest or live trading results
            metadata: Additional context (market regime, etc.)
            
        Returns:
            Record ID
        """
        record_id = str(uuid4())
        
        # Extract metrics
        metrics = result.get("metrics", result)
        
        record = StrategyRecord(
            id=record_id,
            strategy_id=strategy_id,
            timestamp=datetime.utcnow(),
            total_return=metrics.get("total_return", 0.0),
            sharpe_ratio=metrics.get("sharpe_ratio", 0.0),
            max_drawdown=metrics.get("max_drawdown", 0.0),
            market_regime=metadata.get("market_regime", "unknown"),
            start_date=metadata.get("start_date", ""),
            end_date=metadata.get("end_date", ""),
            tags=metadata.get("tags", []),
            notes=metadata.get("notes", "")
        )
        
        # Generate embedding
        embedding = self._generate_embedding(record)
        record.embedding = embedding
        
        # Store
        self._records[record_id] = record
        self._embeddings[record_id] = embedding
        
        logger.info(
            "Strategy result stored",
            record_id=record_id,
            strategy_id=strategy_id,
            sharpe=record.sharpe_ratio
        )
        
        return record_id
    
    def query_similar_strategies(
        self,
        target_sharpe: Optional[float] = None,
        target_return: Optional[float] = None,
        market_regime: Optional[str] = None,
        n_results: int = 5
    ) -> list[StrategyRecord]:
        """Query strategies similar to target metrics.
        
        Args:
            target_sharpe: Target Sharpe ratio for similarity
            target_return: Target return for similarity
            market_regime: Filter by market regime
            n_results: Number of results to return
            
        Returns:
            List of similar strategy records
        """
        # Build query vector
        query_vector = self._build_query_vector(
            target_sharpe or 1.0,
            target_return or 0.1
        )
        
        # Filter by regime if specified
        candidates = list(self._records.values())
        if market_regime:
            candidates = [r for r in candidates if r.market_regime == market_regime]
        
        # Calculate similarities
        scored = []
        for record in candidates:
            if record.embedding:
                similarity = self._cosine_similarity(
                    query_vector,
                    record.embedding
                )
                scored.append((similarity, record))
        
        # Sort by similarity and return top N
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [record for _, record in scored[:n_results]]
    
    def search_by_tags(
        self,
        tags: list[str],
        n_results: int = 10
    ) -> list[StrategyRecord]:
        """Search strategies by tags."""
        results = []
        
        for record in self._records.values():
            if any(tag in record.tags for tag in tags):
                results.append(record)
        
        return results[:n_results]
    
    def get_best_performing(
        self,
        metric: str = "sharpe_ratio",
        min_trades: int = 50,
        n_results: int = 5
    ) -> list[StrategyRecord]:
        """Get best performing strategies by metric.
        
        Args:
            metric: Metric to sort by (sharpe_ratio, total_return)
            min_trades: Minimum number of trades
            n_results: Number of results
            
        Returns:
            List of top performing strategy records
        """
        # Filter valid records
        valid = [
            r for r in self._records.values()
            if r.sharpe_ratio > 0  # Must be profitable
        ]
        
        # Sort by metric
        if metric == "sharpe_ratio":
            valid.sort(key=lambda r: r.sharpe_ratio, reverse=True)
        elif metric == "total_return":
            valid.sort(key=lambda r: r.total_return, reverse=True)
        elif metric == "max_drawdown":
            valid.sort(key=lambda r: r.max_drawdown)  # Lower is better
        
        return valid[:n_results]
    
    def get_market_regime_analysis(
        self,
        strategy_id: Optional[str] = None
    ) -> dict[str, list[StrategyRecord]]:
        """Analyze strategy performance by market regime.
        
        Returns:
            Dictionary mapping regime to list of records
        """
        regimes: dict[str, list[StrategyRecord]] = {}
        
        for record in self._records.values():
            if strategy_id and record.strategy_id != strategy_id:
                continue
            
            regime = record.market_regime
            if regime not in regimes:
                regimes[regime] = []
            
            regimes[regime].append(record)
        
        return regimes
    
    def generate_embedding_summary(self, record: StrategyRecord) -> str:
        """Generate text summary for embedding generation.
        
        This text can be passed to an external embedding service
        (OpenAI, HuggingFace, etc.) for vectorization.
        """
        return f"""
Strategy: {record.strategy_id}
Market Regime: {record.market_regime}
Performance: Return {record.total_return:.2%}, Sharpe {record.sharpe_ratio:.2f}, DD {record.max_drawdown:.2%}
Period: {record.start_date} to {record.end_date}
Tags: {', '.join(record.tags)}
Notes: {record.notes}
"""
    
    def _generate_embedding(
        self,
        record: StrategyRecord
    ) -> list[float]:
        """Generate simple embedding from metrics.
        
        In production, this would call an external embedding service
        like OpenAI's text-embedding-ada-002 or similar.
        """
        # Simple feature-based embedding
        # [normalized_return, sharpe, inverse_drawdown, regime_encoding]
        
        features = [
            record.total_return * 10,  # Scale up for visibility
            record.sharpe_ratio,
            1.0 - record.max_drawdown,  # Higher is better
            self._encode_regime(record.market_regime)
        ]
        
        # Pad to dimension
        while len(features) < self.embedding_dimension:
            features.append(0.0)
        
        return features[:self.embedding_dimension]
    
    def _build_query_vector(
        self,
        target_sharpe: float,
        target_return: float
    ) -> list[float]:
        """Build query vector from target metrics."""
        return [
            target_return * 10,
            target_sharpe,
            0.9,  # Expect low drawdown
            0.5   # Neutral regime preference
        ] + [0.0] * (self.embedding_dimension - 4)
    
    def _encode_regime(self, regime: str) -> float:
        """Encode market regime as numeric value."""
        encoding = {
            "trending": 0.8,
            "ranging": 0.5,
            "volatile": 0.2,
            "unknown": 0.5
        }
        return encoding.get(regime, 0.5)
    
    def _cosine_similarity(
        self,
        v1: list[float],
        v2: list[float]
    ) -> float:
        """Calculate cosine similarity between vectors."""
        import numpy as np
        
        a = np.array(v1)
        b = np.array(v2)
        
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return np.dot(a, b) / (norm_a * norm_b)
    
    def export_to_format(self, format: str = "json") -> Any:
        """Export all records to specified format."""
        records = list(self._records.values())
        
        if format == "json":
            return [
                {
                    "id": r.id,
                    "strategy_id": r.strategy_id,
                    "timestamp": r.timestamp.isoformat(),
                    "total_return": r.total_return,
                    "sharpe_ratio": r.sharpe_ratio,
                    "max_drawdown": r.max_drawdown,
                    "market_regime": r.market_regime,
                    "tags": r.tags,
                    "notes": r.notes
                }
                for r in records
            ]
        
        elif format == "csv":
            # Return as list of dicts for CSV writer
            return [
                {
                    "id": r.id,
                    "strategy_id": r.strategy_id,
                    "sharpe": r.sharpe_ratio,
                    "return": r.total_return,
                    "drawdown": r.max_drawdown,
                    "regime": r.market_regime
                }
                for r in records
            ]
        
        return records


# Convenience class for simple in-memory search
class SimpleStrategySearch:
    """Simple keyword-based search without embeddings."""
    
    def __init__(self) -> None:
        self._documents: list[dict] = []
    
    def add_document(
        self,
        strategy_id: str,
        content: str,
        metadata: Optional[dict] = None
    ) -> str:
        """Add document to search index."""
        doc_id = str(uuid4())
        
        self._documents.append({
            "id": doc_id,
            "strategy_id": strategy_id,
            "content": content.lower(),
            "metadata": metadata or {},
            "timestamp": datetime.utcnow()
        })
        
        return doc_id
    
    def search(
        self,
        query: str,
        n_results: int = 5
    ) -> list[dict]:
        """Simple keyword search."""
        query = query.lower()
        query_terms = query.split()
        
        scored = []
        for doc in self._documents:
            score = sum(1 for term in query_terms if term in doc["content"])
            if score > 0:
                scored.append((score, doc))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [doc for _, doc in scored[:n_results]]
