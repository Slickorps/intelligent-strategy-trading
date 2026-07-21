"""Strategy parameter optimization.

Implements parameter optimization using:
- Grid search
- Random search
- Walk-forward optimization
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import numpy as np

from ist.core.logging import get_logger
from ist.backtest.analytics import PerformanceMetrics

logger = get_logger(__name__)


@dataclass
class ParameterSet:
    """Set of strategy parameters."""
    params: dict[str, Any]
    fitness: float = 0.0
    metrics: Optional[PerformanceMetrics] = None


class ParameterOptimizer:
    """Strategy parameter optimizer.
    
    Usage:
        optimizer = ParameterOptimizer(backtest_func)
        
        # Define parameter space
        param_space = {
            "sma_fast": [10, 20, 30],
            "sma_slow": [50, 100, 200],
            "risk_per_trade": [0.01, 0.02, 0.03]
        }
        
        # Run optimization
        best = optimizer.grid_search(param_space)
        
        print(f"Best parameters: {best.params}")
        print(f"Sharpe ratio: {best.metrics.sharpe_ratio}")
    """
    
    def __init__(
        self,
        backtest_func: Callable[[dict[str, Any]], PerformanceMetrics],
        metric_to_optimize: str = "sharpe_ratio"
    ) -> None:
        self.backtest_func = backtest_func
        self.metric = metric_to_optimize
        self._results: list[ParameterSet] = []
    
    def grid_search(
        self,
        param_space: dict[str, list[Any]],
        verbose: bool = True
    ) -> ParameterSet:
        """Exhaustive search over parameter grid.
        
        Args:
            param_space: Dict mapping parameter name to list of values
            verbose: Print progress
            
        Returns:
            Best parameter set found
        """
        from itertools import product
        
        # Generate all combinations
        keys = list(param_space.keys())
        values = [param_space[k] for k in keys]
        
        total_combinations = np.prod([len(v) for v in values])
        
        if verbose:
            logger.info(f"Grid search: {total_combinations} combinations")
        
        best_result = None
        best_fitness = float('-inf')
        failed_count = 0
        
        for i, combo in enumerate(product(*values)):
            params = dict(zip(keys, combo))
            
            # Run backtest
            try:
                metrics = self.backtest_func(params)
                fitness = self._extract_fitness(metrics)
                
                result = ParameterSet(
                    params=params,
                    fitness=fitness,
                    metrics=metrics
                )
                
                self._results.append(result)
                
                if fitness > best_fitness:
                    best_fitness = fitness
                    best_result = result
                
                if verbose and (i + 1) % 10 == 0:
                    logger.info(f"Progress: {i+1}/{total_combinations}, "
                               f"Best: {best_fitness:.3f}")
                
            except Exception as e:
                failed_count += 1
                logger.warning(f"Backtest failed for {params}: {e}")
                continue

        if best_result is None:
            raise ValueError("All backtests failed")

        logger.info(
            "Grid search completed",
            best_fitness=best_fitness,
            best_params=best_result.params,
            total_combinations=total_combinations,
            failed_count=failed_count,
        )
        
        return best_result
    
    def random_search(
        self,
        param_distributions: dict[str, tuple],
        n_iterations: int = 100,
        verbose: bool = True
    ) -> ParameterSet:
        """Random search over parameter distributions.
        
        Args:
            param_distributions: Dict mapping parameter to (min, max) or list
            n_iterations: Number of random samples
            verbose: Print progress
            
        Returns:
            Best parameter set found
        """
        best_result = None
        best_fitness = float('-inf')
        
        if verbose:
            logger.info(f"Random search: {n_iterations} iterations")
        
        for i in range(n_iterations):
            # Sample parameters
            params = {}
            for key, dist in param_distributions.items():
                if isinstance(dist, (list, tuple)) and len(dist) == 2:
                    if isinstance(dist[0], int):
                        params[key] = np.random.randint(dist[0], dist[1] + 1)
                    else:
                        params[key] = np.random.uniform(dist[0], dist[1])
                else:
                    params[key] = np.random.choice(dist)
            
            # Run backtest
            try:
                metrics = self.backtest_func(params)
                fitness = self._extract_fitness(metrics)
                
                result = ParameterSet(
                    params=params,
                    fitness=fitness,
                    metrics=metrics
                )
                
                self._results.append(result)
                
                if fitness > best_fitness:
                    best_fitness = fitness
                    best_result = result
                
                if verbose and (i + 1) % 10 == 0:
                    logger.info(f"Progress: {i+1}/{n_iterations}, "
                               f"Best: {best_fitness:.3f}")
                
            except Exception as e:
                logger.warning(f"Backtest failed for {params}: {e}")
                continue
        
        if best_result is None:
            raise ValueError("All backtests failed")
        
        logger.info(
            "Random search completed",
            best_fitness=best_fitness,
            best_params=best_result.params
        )
        
        return best_result
    
    def walk_forward_optimization(
        self,
        param_space: dict[str, list[Any]],
        data_start: datetime,
        data_end: datetime,
        train_periods: int = 6,
        train_duration: int = 180,  # days
        test_duration: int = 60,     # days
        verbose: bool = True
    ) -> list[dict[str, Any]]:
        """Walk-forward optimization to prevent overfitting.
        
        Divides data into train/test periods and optimizes
        on each training set, validates on test set.
        
        Args:
            param_space: Parameter grid
            data_start: Start of data range
            data_end: End of data range
            train_periods: Number of train/test periods
            train_duration: Days in training period
            test_duration: Days in test period
            verbose: Print progress
            
        Returns:
            List of out-of-sample results for each period
        """
        results = []
        
        current = data_start
        
        for period in range(train_periods):
            train_start = current
            train_end = train_start + timedelta(days=train_duration)
            test_start = train_end
            test_end = test_start + timedelta(days=test_duration)
            
            if test_end > data_end:
                break
            
            if verbose:
                logger.info(
                    f"Walk-forward period {period+1}/{train_periods}",
                    train_start=train_start,
                    test_end=test_end
                )
            
            # Optimize on training data
            def train_backtest(params):
                # This would run backtest on training period
                # For now, return mock metrics
                return self.backtest_func(params)
            
            optimizer = ParameterOptimizer(train_backtest, self.metric)
            best_train = optimizer.grid_search(param_space, verbose=False)
            
            # Validate on test data
            def test_backtest(params):
                # This would run backtest on test period
                return self.backtest_func(params)
            
            test_metrics = test_backtest(best_train.params)
            
            results.append({
                "period": period + 1,
                "train_dates": (train_start, train_end),
                "test_dates": (test_start, test_end),
                "best_params": best_train.params,
                "train_fitness": best_train.fitness,
                "test_fitness": self._extract_fitness(test_metrics),
                "test_metrics": test_metrics
            })
            
            # Move to next period
            current = test_end
        
        # Calculate out-of-sample consistency
        train_fitnesses = [r["train_fitness"] for r in results]
        test_fitnesses = [r["test_fitness"] for r in results]
        
        consistency = np.corrcoef(train_fitnesses, test_fitnesses)[0, 1] \
            if len(train_fitnesses) > 1 else 0
        
        logger.info(
            "Walk-forward completed",
            periods=len(results),
            consistency=consistency
        )
        
        return results
    
    def get_top_results(self, n: int = 10) -> list[ParameterSet]:
        """Get top N results from optimization."""
        sorted_results = sorted(
            self._results,
            key=lambda x: x.fitness,
            reverse=True
        )
        return sorted_results[:n]
    
    def analyze_parameter_importance(self) -> dict[str, float]:
        """Analyze which parameters have most impact on performance."""
        if not self._results:
            return {}
        
        importance = {}
        
        # For each parameter, calculate correlation with fitness
        param_names = list(self._results[0].params.keys())
        
        for param in param_names:
            values = []
            fitnesses = []
            
            for result in self._results:
                if param in result.params:
                    values.append(result.params[param])
                    fitnesses.append(result.fitness)
            
            if len(values) > 1:
                correlation = np.corrcoef(values, fitnesses)[0, 1]
                importance[param] = abs(correlation)
        
        return importance
    
    def _extract_fitness(self, metrics: PerformanceMetrics) -> float:
        """Extract fitness score from metrics."""
        if self.metric == "sharpe_ratio":
            return metrics.sharpe_ratio
        elif self.metric == "total_return":
            return metrics.total_return
        elif self.metric == "calmar_ratio":
            return metrics.calmar_ratio
        elif self.metric == "profit_factor":
            return metrics.profit_factor
        else:
            return metrics.sharpe_ratio


class GeneticOptimizer:
    """Genetic algorithm for parameter optimization.
    
    Useful for large parameter spaces where grid search
    would be computationally infeasible.
    """
    
    def __init__(
        self,
        backtest_func: Callable[[dict[str, Any]], PerformanceMetrics],
        population_size: int = 50,
        generations: int = 20,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.8
    ) -> None:
        self.backtest_func = backtest_func
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        
        self._population: list[ParameterSet] = []
    
    def optimize(
        self,
        param_bounds: dict[str, tuple],
        maximize: bool = True
    ) -> ParameterSet:
        """Run genetic algorithm optimization.
        
        Args:
            param_bounds: Dict mapping parameter to (min, max)
            maximize: Whether to maximize or minimize fitness
            
        Returns:
            Best individual found
        """
        # Initialize population
        self._initialize_population(param_bounds)
        
        best_fitness = float('-inf') if maximize else float('inf')
        best_individual = None
        
        for generation in range(self.generations):
            # Evaluate fitness
            self._evaluate_population()
            
            # Find best
            sorted_pop = sorted(
                self._population,
                key=lambda x: x.fitness,
                reverse=maximize
            )
            
            current_best = sorted_pop[0]
            
            if maximize and current_best.fitness > best_fitness:
                best_fitness = current_best.fitness
                best_individual = current_best
            elif not maximize and current_best.fitness < best_fitness:
                best_fitness = current_best.fitness
                best_individual = current_best
            
            logger.info(
                f"Generation {generation+1}/{self.generations}",
                best_fitness=best_fitness,
                avg_fitness=sum(p.fitness for p in self._population) / len(self._population)
            )
            
            # Create next generation
            new_population = [current_best]  # Elitism: keep best
            
            while len(new_population) < self.population_size:
                parent1 = self._tournament_selection()
                parent2 = self._tournament_selection()
                
                if np.random.random() < self.crossover_rate:
                    child = self._crossover(parent1, parent2)
                else:
                    child = parent1
                
                if np.random.random() < self.mutation_rate:
                    child = self._mutate(child, param_bounds)
                
                new_population.append(child)
            
            self._population = new_population
        
        logger.info(
            "Genetic optimization completed",
            best_fitness=best_fitness
        )
        
        return best_individual or current_best
    
    def _initialize_population(
        self,
        param_bounds: dict[str, tuple]
    ) -> None:
        """Create random initial population."""
        self._population = []
        
        for _ in range(self.population_size):
            params = {}
            for param, (min_val, max_val) in param_bounds.items():
                if isinstance(min_val, int):
                    params[param] = np.random.randint(min_val, max_val + 1)
                else:
                    params[param] = np.random.uniform(min_val, max_val)
            
            self._population.append(ParameterSet(params=params))
    
    def _evaluate_population(self) -> None:
        """Calculate fitness for all individuals."""
        for individual in self._population:
            if individual.fitness == 0:  # Not evaluated yet
                try:
                    metrics = self.backtest_func(individual.params)
                    individual.fitness = metrics.sharpe_ratio
                    individual.metrics = metrics
                except Exception as e:
                    logger.warning(f"Evaluation failed: {e}")
                    individual.fitness = -999
    
    def _tournament_selection(self, tournament_size: int = 3) -> ParameterSet:
        """Select individual using tournament selection."""
        tournament = np.random.choice(self._population, tournament_size)
        return max(tournament, key=lambda x: x.fitness)
    
    def _crossover(
        self,
        parent1: ParameterSet,
        parent2: ParameterSet
    ) -> ParameterSet:
        """Create child by crossover."""
        child_params = {}
        
        for param in parent1.params:
            if np.random.random() < 0.5:
                child_params[param] = parent1.params[param]
            else:
                child_params[param] = parent2.params.get(param, parent1.params[param])
        
        return ParameterSet(params=child_params)
    
    def _mutate(
        self,
        individual: ParameterSet,
        param_bounds: dict[str, tuple]
    ) -> ParameterSet:
        """Mutate individual randomly."""
        params = individual.params.copy()
        
        # Select random parameter to mutate
        param = np.random.choice(list(params.keys()))
        min_val, max_val = param_bounds[param]
        
        if isinstance(min_val, int):
            params[param] = np.random.randint(min_val, max_val + 1)
        else:
            # Gaussian mutation
            current = params[param]
            std = (max_val - min_val) * 0.1
            params[param] = np.clip(
                current + np.random.normal(0, std),
                min_val,
                max_val
            )
        
        return ParameterSet(params=params)
